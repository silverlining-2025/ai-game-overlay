"""CLIP-based game state classifier training pipeline.

Uses CoOp-style prompt tuning: freezes CLIP vision+text encoders,
learns only soft text prompt embeddings (~16K trainable params).

Usage:
    python -m tools.train_classifier --data-dir training_data/palworld
    python -m tools.train_classifier --data-dir training_data/palworld --epochs 30 --lr 1e-3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset, random_split

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
DEFAULT_DATA_DIR = "training_data/palworld"
DEFAULT_OUTPUT_DIR = "backend/models/game_classifier"
MIN_SAMPLES_PER_CLASS = 2
MIN_TOTAL_SAMPLES = 10
N_CTX = 4  # number of learnable context tokens per prompt
IMAGE_SIZE = 224

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class GameScreenshotDataset(Dataset):
    """Loads labeled screenshots from responses.jsonl and results.jsonl files."""

    def __init__(self, data_dir: str, processor):
        self.samples: list[tuple[str, str]] = []  # (image_path, label)
        self.label2idx: dict[str, int] = {}
        self.idx2label: list[str] = []
        self.processor = processor

        data_path = Path(data_dir)
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        # Collect all labeled entries
        raw_samples: list[tuple[str, str]] = []

        # --- Source 1: Manual labeling (responses.jsonl with "label" field) ---
        for session_dir in sorted(data_path.iterdir()):
            if not session_dir.is_dir():
                continue
            jsonl_path = session_dir / "responses.jsonl"
            if not jsonl_path.exists():
                continue
            for line in jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                label = entry.get("label")
                if not label:
                    continue
                image_name = entry.get("image", "")
                image_path = session_dir / image_name
                if image_path.exists():
                    raw_samples.append((str(image_path), label))

        # --- Source 2: Auto-labeling (results.jsonl with verified/proposed/clip label) ---
        for session_dir in sorted(data_path.iterdir()):
            if not session_dir.is_dir():
                continue
            jsonl_path = session_dir / "results.jsonl"
            if not jsonl_path.exists():
                continue
            for line in jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                # Use verified_label first, fall back to proposed_label, then clip_label
                label = (
                    entry.get("verified_label")
                    or entry.get("proposed_label")
                    or entry.get("clip_label")
                )
                if not label:
                    continue
                image_name = entry.get("image", "")
                # Try multiple path resolutions
                candidates = [
                    session_dir / image_name,           # relative to JSONL dir
                    data_path / image_name,              # relative to data root
                ]
                # Check if image was copied to a label subdirectory in auto_labeled/
                if label:
                    label_subdir = session_dir / label / Path(image_name).name
                    candidates.append(label_subdir)

                resolved_path = None
                for candidate in candidates:
                    if candidate.exists():
                        resolved_path = candidate
                        break

                if resolved_path is not None:
                    raw_samples.append((str(resolved_path), label))
                else:
                    log.warning(
                        "Image not found for auto-label entry, tried: %s",
                        [str(c) for c in candidates],
                    )

        if not raw_samples:
            raise ValueError(
                f"No labeled samples found in {data_dir}. "
                "Entries need a 'label' field in responses.jsonl "
                "or a 'verified_label'/'proposed_label' in results.jsonl."
            )

        # Filter classes with too few samples
        label_counts: dict[str, int] = {}
        for _, label in raw_samples:
            label_counts[label] = label_counts.get(label, 0) + 1

        valid_labels = {
            lbl
            for lbl, count in label_counts.items()
            if count >= MIN_SAMPLES_PER_CLASS
        }
        skipped = {
            lbl: count
            for lbl, count in label_counts.items()
            if lbl not in valid_labels
        }
        if skipped:
            log.warning(
                "Skipping classes with < %d samples: %s",
                MIN_SAMPLES_PER_CLASS,
                skipped,
            )

        self.samples = [
            (path, label) for path, label in raw_samples if label in valid_labels
        ]

        if len(self.samples) < MIN_TOTAL_SAMPLES:
            raise ValueError(
                f"Only {len(self.samples)} labeled samples found "
                f"(need >= {MIN_TOTAL_SAMPLES}). Label more data first."
            )

        # Build label mapping (sorted for reproducibility)
        self.idx2label = sorted(valid_labels)
        self.label2idx = {lbl: i for i, lbl in enumerate(self.idx2label)}

        log.info(
            "Loaded %d samples across %d classes: %s",
            len(self.samples),
            len(self.idx2label),
            {lbl: label_counts[lbl] for lbl in self.idx2label},
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        image_path, label = self.samples[idx]
        image = Image.open(image_path).convert("RGB")
        pixel_values = self.processor(images=image, return_tensors="pt")[
            "pixel_values"
        ].squeeze(0)
        return pixel_values, self.label2idx[label]


# ---------------------------------------------------------------------------
# CoOp Prompt Learner
# ---------------------------------------------------------------------------


class PromptLearner(nn.Module):
    """CoOp-style learnable soft prompts for CLIP.

    Instead of hand-crafted text prompts like "a photo of combat",
    we learn continuous prompt embeddings: [V1][V2]...[Vn][class_token].

    Only ~16K parameters are trainable; CLIP encoders are frozen.
    """

    def __init__(self, clip_model, class_names: list[str], n_ctx: int = N_CTX):
        super().__init__()
        from transformers import CLIPTokenizer

        self.n_ctx = n_ctx
        self.n_classes = len(class_names)

        tokenizer = CLIPTokenizer.from_pretrained(CLIP_MODEL_ID)
        text_encoder = clip_model.text_model
        embedding_layer = text_encoder.embeddings.token_embedding

        dtype = embedding_layer.weight.dtype
        embed_dim = embedding_layer.weight.shape[1]

        # Initialize context vectors from normal distribution
        ctx_vectors = torch.randn(n_ctx, embed_dim, dtype=dtype) * 0.02
        self.ctx = nn.Parameter(ctx_vectors)

        # Tokenize class names and store their embeddings
        # Format: [SOS] [ctx1..ctxN] [class tokens] [EOS] [PAD...]
        prompts_text = [f"a {name.replace('_', ' ')}" for name in class_names]
        tokenized = tokenizer(
            prompts_text, padding=True, return_tensors="pt", truncation=True
        )

        with torch.no_grad():
            all_embeddings = embedding_layer(tokenized["input_ids"])

        # Store SOS token embedding, class name embeddings, and suffix (EOS+padding)
        self.register_buffer("sos_embed", all_embeddings[:, :1, :])  # [n_cls, 1, dim]

        # We need the token embeddings for each class name (after "a ")
        # Plus the EOS/padding tokens at the end
        # Simpler: store full embeddings minus the first token, we'll reconstruct
        self.register_buffer(
            "suffix_embeds", all_embeddings[:, 1:, :]
        )  # [n_cls, seq-1, dim]
        self.register_buffer(
            "attention_mask", tokenized["attention_mask"]
        )  # [n_cls, seq]

        self.embed_dim = embed_dim

    def forward(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (prompt_embeddings, attention_mask) for all classes.

        prompt_embeddings: [n_classes, seq_len, embed_dim]
        attention_mask: [n_classes, seq_len]
        """
        ctx = self.ctx.unsqueeze(0).expand(self.n_classes, -1, -1)  # [n_cls, n_ctx, d]

        # [SOS] [learnable ctx] [class suffix tokens]
        prompts = torch.cat([self.sos_embed, ctx, self.suffix_embeds], dim=1)

        # Adjust attention mask: original mask + extra positions for context tokens
        orig_mask = self.attention_mask
        ctx_mask = torch.ones(
            self.n_classes, self.n_ctx, device=orig_mask.device, dtype=orig_mask.dtype
        )
        # Insert ctx_mask after position 0 (SOS)
        new_mask = torch.cat(
            [orig_mask[:, :1], ctx_mask, orig_mask[:, 1:]], dim=1
        )

        return prompts, new_mask


class CoOpCLIP(nn.Module):
    """CLIP with CoOp prompt learning for game state classification."""

    def __init__(self, clip_model, class_names: list[str], n_ctx: int = N_CTX):
        super().__init__()
        self.clip_model = clip_model
        self.prompt_learner = PromptLearner(clip_model, class_names, n_ctx)
        self.logit_scale = clip_model.logit_scale

        # Freeze everything except prompt learner
        for param in clip_model.parameters():
            param.requires_grad = False

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Returns logits [batch_size, n_classes]."""
        # Get image features
        image_outputs = self.clip_model.vision_model(pixel_values=pixel_values)
        image_embeds = image_outputs.pooler_output
        image_embeds = self.clip_model.visual_projection(image_embeds)
        image_embeds = F.normalize(image_embeds, dim=-1)

        # Get text features from learned prompts
        prompt_embeds, attention_mask = self.prompt_learner()

        # Run through text encoder using the embeddings directly
        text_outputs = self.clip_model.text_model(
            inputs_embeds=prompt_embeds,
            attention_mask=attention_mask[:, : prompt_embeds.shape[1]],
        )
        text_embeds = text_outputs.pooler_output
        text_embeds = self.clip_model.text_projection(text_embeds)
        text_embeds = F.normalize(text_embeds, dim=-1)

        # Cosine similarity as logits
        logit_scale = self.logit_scale.exp()
        logits = logit_scale * image_embeds @ text_embeds.T

        return logits


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(
    data_dir: str = DEFAULT_DATA_DIR,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    epochs: int = 20,
    batch_size: int = 16,
    lr: float = 2e-3,
    val_split: float = 0.2,
    device: Optional[str] = None,
):
    """Train the CoOp CLIP classifier."""
    from transformers import CLIPModel, CLIPProcessor

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    log.info("Loading CLIP model: %s", CLIP_MODEL_ID)
    clip_model = CLIPModel.from_pretrained(CLIP_MODEL_ID)
    processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)

    log.info("Loading dataset from: %s", data_dir)
    dataset = GameScreenshotDataset(data_dir, processor)

    # Train/val split
    n_val = max(1, int(len(dataset) * val_split))
    n_train = len(dataset) - n_val
    train_set, val_set = random_split(
        dataset, [n_train, n_val], generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(
        train_set, batch_size=batch_size, shuffle=True, num_workers=0, pin_memory=True
    )
    val_loader = DataLoader(
        val_set, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True
    )

    log.info("Train: %d, Val: %d, Classes: %d", n_train, n_val, len(dataset.idx2label))
    log.info("Classes: %s", dataset.idx2label)

    # Build CoOp model
    model = CoOpCLIP(clip_model, dataset.idx2label).to(device)

    # Only optimize prompt learner parameters
    trainable_params = [p for p in model.prompt_learner.parameters() if p.requires_grad]
    total_trainable = sum(p.numel() for p in trainable_params)
    log.info("Trainable parameters: %d (%.1fK)", total_trainable, total_trainable / 1000)

    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    best_val_acc = 0.0
    best_epoch = 0

    for epoch in range(1, epochs + 1):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for pixel_values, labels in train_loader:
            pixel_values = pixel_values.to(device)
            labels = labels.to(device)

            logits = model(pixel_values)
            loss = criterion(logits, labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * labels.size(0)
            train_correct += (logits.argmax(dim=1) == labels).sum().item()
            train_total += labels.size(0)

        scheduler.step()

        # Validate
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for pixel_values, labels in val_loader:
                pixel_values = pixel_values.to(device)
                labels = labels.to(device)

                logits = model(pixel_values)
                loss = criterion(logits, labels)

                val_loss += loss.item() * labels.size(0)
                val_correct += (logits.argmax(dim=1) == labels).sum().item()
                val_total += labels.size(0)
                all_preds.extend(logits.argmax(dim=1).cpu().tolist())
                all_labels.extend(labels.cpu().tolist())

        train_acc = train_correct / max(train_total, 1)
        val_acc = val_correct / max(val_total, 1)

        log.info(
            "Epoch %2d/%d | Train Loss: %.4f Acc: %.1f%% | Val Loss: %.4f Acc: %.1f%%",
            epoch,
            epochs,
            train_loss / max(train_total, 1),
            train_acc * 100,
            val_loss / max(val_total, 1),
            val_acc * 100,
        )

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch
            _save_model(model, dataset, output_dir)

    # Final evaluation
    log.info("=" * 60)
    log.info("Best validation accuracy: %.1f%% (epoch %d)", best_val_acc * 100, best_epoch)
    log.info("=" * 60)

    # Print classification report
    from sklearn.metrics import classification_report, confusion_matrix

    target_names = [dataset.idx2label[i] for i in range(len(dataset.idx2label))]
    print("\nClassification Report (validation set):")
    print(classification_report(all_labels, all_preds, target_names=target_names, zero_division=0))

    print("\nConfusion Matrix:")
    cm = confusion_matrix(all_labels, all_preds)
    # Pretty print
    max_label_len = max(len(n) for n in target_names)
    header = " " * (max_label_len + 2) + "  ".join(
        f"{n[:6]:>6}" for n in target_names
    )
    print(header)
    for i, row in enumerate(cm):
        row_str = "  ".join(f"{v:>6}" for v in row)
        print(f"{target_names[i]:>{max_label_len}}  {row_str}")

    log.info("Model saved to: %s", output_dir)
    return best_val_acc


def _save_model(model: CoOpCLIP, dataset: GameScreenshotDataset, output_dir: str):
    """Save only the prompt learner weights + metadata."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Save prompt learner state dict (tiny: ~16K params)
    torch.save(
        model.prompt_learner.state_dict(),
        out_path / "prompt_learner.pt",
    )

    # Save metadata
    metadata = {
        "clip_model_id": CLIP_MODEL_ID,
        "n_ctx": model.prompt_learner.n_ctx,
        "class_names": dataset.idx2label,
        "label2idx": dataset.label2idx,
        "n_classes": len(dataset.idx2label),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(out_path / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Train CLIP game state classifier (CoOp prompt tuning)"
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="Path to training data (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Where to save trained model (default: %(default)s)",
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--device", default=None, help="cuda or cpu (auto-detect)")
    args = parser.parse_args()

    train(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        val_split=args.val_split,
        device=args.device,
    )


if __name__ == "__main__":
    main()
