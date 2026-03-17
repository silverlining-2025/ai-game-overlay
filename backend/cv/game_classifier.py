"""Game state classifier using CLIP — fine-tuned or zero-shot fallback.

Provides fast game state classification from a single frame:
    classifier = GameClassifier()
    label, confidence = classifier.classify(frame)

Modes:
1. Fine-tuned (CoOp): loads trained prompt embeddings from
   backend/models/game_classifier/ — higher accuracy, requires training.
2. Zero-shot: uses hand-crafted text prompts with base CLIP —
   works out of the box, lower accuracy.

Target: <10ms per frame on GPU, ~30ms on CPU.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
MODEL_DIR = Path(__file__).parent.parent / "models" / "game_classifier"

# Zero-shot label descriptions — used when no trained model exists
ZERO_SHOT_LABELS = {
    "combat_wild": "a screenshot of combat with wild monsters in an open world game",
    "exploration": "a screenshot of exploring outdoor areas in a game",
    "base_idle": "a screenshot of an idle base or camp in a game",
    "base_building": "a screenshot of building or placing structures in a base",
    "inventory_menu": "a screenshot of an inventory or item management menu",
    "map_screen": "a screenshot of a world map or minimap overlay",
    "loading_screen": "a screenshot of a loading screen with progress bar or tips",
    "pal_management": "a screenshot of managing creatures or companions",
    "char_creation": "a screenshot of character creation or customization",
    "world_select": "a screenshot of a world or save file selection menu",
    "cutscene": "a screenshot of an in-game cutscene or cinematic",
    "flying": "a screenshot of flying or riding a mount in the air",
    "workbench_craft": "a screenshot of a crafting workbench or crafting menu",
    "steam_launcher": "a screenshot of the Steam game launcher or library",
    "patch_notes": "a screenshot showing game patch notes or update information",
    "settings_option": "a screenshot of a settings or options menu",
}


class GameClassifier:
    """Classifies game state from a single frame using CLIP.

    Lazy-loads the model on first classify() call to avoid startup delay.
    Falls back to zero-shot if no trained model is available.
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        device: Optional[str] = None,
        zero_shot_labels: Optional[dict[str, str]] = None,
    ):
        self._model_dir = Path(model_dir) if model_dir else MODEL_DIR
        self._device = device
        self._zero_shot_labels = zero_shot_labels or ZERO_SHOT_LABELS

        # Lazy-loaded state
        self._loaded = False
        self._mode: str = "none"  # "finetuned", "zeroshot", or "none"
        self._clip_model = None
        self._processor = None
        self._prompt_learner = None  # for fine-tuned mode
        self._text_features = None  # for zero-shot mode
        self._class_names: list[str] = []

    @property
    def mode(self) -> str:
        """Current classification mode: 'finetuned', 'zeroshot', or 'none'."""
        return self._mode

    @property
    def class_names(self) -> list[str]:
        return self._class_names

    def _load(self) -> None:
        """Load CLIP model and classifier weights."""
        if self._loaded:
            return

        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            if self._device is None:
                self._device = "cuda" if torch.cuda.is_available() else "cpu"

            log.info("Loading CLIP model: %s (device: %s)", CLIP_MODEL_ID, self._device)
            self._clip_model = CLIPModel.from_pretrained(CLIP_MODEL_ID).to(self._device)
            self._clip_model.eval()
            self._processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)

            # Try loading fine-tuned model
            metadata_path = self._model_dir / "metadata.json"
            weights_path = self._model_dir / "prompt_learner.pt"

            if metadata_path.exists() and weights_path.exists():
                self._load_finetuned(metadata_path, weights_path)
            else:
                self._load_zeroshot()

            self._loaded = True

        except ImportError as e:
            log.error("Missing dependencies for classifier: %s", e)
            self._mode = "none"
            self._loaded = True
        except Exception as e:
            log.error("Failed to load classifier: %s", e)
            self._mode = "none"
            self._loaded = True

    def _load_finetuned(self, metadata_path: Path, weights_path: Path) -> None:
        """Load CoOp fine-tuned prompt learner."""
        import torch
        import torch.nn as nn
        import torch.nn.functional as F

        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        self._class_names = metadata["class_names"]
        n_ctx = metadata.get("n_ctx", 4)

        log.info(
            "Loading fine-tuned model (%d classes, %d ctx tokens)",
            len(self._class_names),
            n_ctx,
        )

        # Reconstruct PromptLearner from saved state_dict shapes
        # instead of importing from the training script
        state_dict = torch.load(
            weights_path, map_location=self._device, weights_only=True
        )

        class _PromptLearner(nn.Module):
            def __init__(self, sd):
                super().__init__()
                self.ctx = nn.Parameter(sd["ctx"])
                self.n_ctx = sd["ctx"].shape[0]
                self.register_buffer("sos_embed", sd["sos_embed"])
                self.register_buffer("suffix_embeds", sd["suffix_embeds"])
                self.register_buffer("attention_mask", sd["attention_mask"])
                self.n_classes = sd["sos_embed"].shape[0]

            def forward(self):
                ctx = self.ctx.unsqueeze(0).expand(self.n_classes, -1, -1)
                prompts = torch.cat(
                    [self.sos_embed, ctx, self.suffix_embeds], dim=1
                )
                orig_mask = self.attention_mask
                ctx_mask = torch.ones(
                    self.n_classes,
                    self.n_ctx,
                    device=orig_mask.device,
                    dtype=orig_mask.dtype,
                )
                new_mask = torch.cat(
                    [orig_mask[:, :1], ctx_mask, orig_mask[:, 1:]], dim=1
                )
                return prompts, new_mask

        prompt_learner = _PromptLearner(state_dict).to(self._device)
        prompt_learner.eval()

        # Store for inference
        self._prompt_learner = prompt_learner
        self._mode = "finetuned"
        log.info("Classifier ready (fine-tuned, %d classes)", len(self._class_names))

    def _load_zeroshot(self) -> None:
        """Set up zero-shot classification with text prompts."""
        import torch
        import torch.nn.functional as F

        self._class_names = list(self._zero_shot_labels.keys())
        descriptions = list(self._zero_shot_labels.values())

        log.info("No trained model found at %s, using zero-shot", self._model_dir)

        # Pre-compute text features for all labels
        inputs = self._processor(
            text=descriptions, return_tensors="pt", padding=True, truncation=True
        ).to(self._device)

        with torch.no_grad():
            text_outputs = self._clip_model.get_text_features(**inputs)
            self._text_features = F.normalize(text_outputs, dim=-1)

        self._mode = "zeroshot"
        log.info(
            "Classifier ready (zero-shot, %d classes)", len(self._class_names)
        )

    def classify(self, frame: np.ndarray) -> tuple[str, float]:
        """Classify a game frame into a state label.

        Args:
            frame: BGR or RGB numpy array (any size, will be resized).

        Returns:
            (label, confidence) — e.g. ("combat_wild", 0.87).
            Returns ("unknown", 0.0) if classifier is unavailable.
        """
        self._load()

        if self._mode == "none":
            return ("unknown", 0.0)

        try:
            import torch
            import torch.nn.functional as F
            from PIL import Image

            # Convert numpy frame to PIL (handle BGR from OpenCV)
            if frame.ndim == 3 and frame.shape[2] == 3:
                # Assume BGR from OpenCV — convert to RGB
                frame_rgb = frame[:, :, ::-1]
            else:
                frame_rgb = frame

            image = Image.fromarray(frame_rgb.astype(np.uint8))

            # Preprocess
            pixel_values = self._processor(images=image, return_tensors="pt")[
                "pixel_values"
            ].to(self._device)

            with torch.no_grad():
                logits = self._compute_logits(pixel_values)
                probs = F.softmax(logits, dim=-1).squeeze(0)
                confidence, idx = probs.max(dim=0)

            label = self._class_names[idx.item()]
            return (label, confidence.item())

        except Exception as e:
            log.error("Classification failed: %s", e)
            return ("unknown", 0.0)

    def _compute_logits(self, pixel_values) -> "torch.Tensor":
        """Compute classification logits for preprocessed pixel values."""
        import torch.nn.functional as F

        # Get image features
        image_features = self._clip_model.get_image_features(
            pixel_values=pixel_values
        )
        image_features = F.normalize(image_features, dim=-1)
        logit_scale = self._clip_model.logit_scale.exp()

        if self._mode == "finetuned":
            # Get text features from learned prompts
            prompt_embeds, attention_mask = self._prompt_learner()
            text_outputs = self._clip_model.text_model(
                inputs_embeds=prompt_embeds,
                attention_mask=attention_mask[:, : prompt_embeds.shape[1]],
            )
            text_embeds = text_outputs.pooler_output
            text_embeds = self._clip_model.text_projection(text_embeds)
            text_embeds = F.normalize(text_embeds, dim=-1)
            return logit_scale * image_features @ text_embeds.T
        else:
            # Zero-shot: use pre-computed text features
            return logit_scale * image_features @ self._text_features.T

    def classify_top_k(
        self, frame: np.ndarray, k: int = 3
    ) -> list[tuple[str, float]]:
        """Return top-k predictions with confidence scores."""
        self._load()

        if self._mode == "none":
            return [("unknown", 0.0)]

        try:
            import torch
            import torch.nn.functional as F
            from PIL import Image

            if frame.ndim == 3 and frame.shape[2] == 3:
                frame_rgb = frame[:, :, ::-1]
            else:
                frame_rgb = frame

            image = Image.fromarray(frame_rgb.astype(np.uint8))
            pixel_values = self._processor(images=image, return_tensors="pt")[
                "pixel_values"
            ].to(self._device)

            with torch.no_grad():
                logits = self._compute_logits(pixel_values)
                probs = F.softmax(logits, dim=-1).squeeze(0)
                topk = torch.topk(probs, min(k, len(self._class_names)))

            results = []
            for score, idx in zip(topk.values.tolist(), topk.indices.tolist()):
                results.append((self._class_names[idx], score))
            return results

        except Exception as e:
            log.error("Classification failed: %s", e)
            return [("unknown", 0.0)]

    def benchmark(self, frame: np.ndarray, n_runs: int = 50) -> dict:
        """Benchmark classification speed on a frame.

        Returns dict with mean_ms, min_ms, max_ms, std_ms.
        """
        self._load()

        if self._mode == "none":
            return {"mean_ms": 0, "min_ms": 0, "max_ms": 0, "std_ms": 0}

        # Warmup
        for _ in range(5):
            self.classify(frame)

        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            self.classify(frame)
            times.append((time.perf_counter() - t0) * 1000)

        return {
            "mean_ms": np.mean(times),
            "min_ms": np.min(times),
            "max_ms": np.max(times),
            "std_ms": np.std(times),
            "mode": self._mode,
            "device": str(self._device),
        }
