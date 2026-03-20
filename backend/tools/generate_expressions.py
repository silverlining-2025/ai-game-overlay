"""AI-powered character expression generator.

Takes a base character image and generates 19 expression variants using
OpenAI's image edit (inpainting) API. Keeps body/hair/clothes pixel-identical
by masking only the face area.

Usage:
    # Generate from existing character (inpaint face)
    python -m backend.tools.generate_expressions \
        --base frontend/public/characters/nozomi/nozomi_casual_normal.webp \
        --output frontend/public/characters/keiko/ \
        --name keiko \
        --outfit casual

    # Generate with auto-detected face region
    python -m backend.tools.generate_expressions \
        --base my_character.png \
        --output frontend/public/characters/mychar/ \
        --name mychar \
        --outfit casual \
        --face-pct 25  # face is top 25% of image

    # Use Gemini instead of OpenAI
    python -m backend.tools.generate_expressions \
        --base my_character.png \
        --output output/ \
        --name mychar \
        --provider gemini

Requirements:
    pip install openai Pillow rembg
"""

from __future__ import annotations

import argparse
import base64
import io
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("gen_expr")

# All 19 expressions matching Nozomi's naming convention
EXPRESSIONS = {
    "normal":       "neutral relaxed expression, calm eyes, slight natural smile",
    "normaltalk":   "talking, mouth open mid-speech, relaxed eyes",
    "happy":        "genuinely happy, bright smile, sparkling eyes, joyful",
    "angry":        "angry, furrowed brows, sharp eyes, tense mouth",
    "angrytalk":    "angry and talking, mouth open mid-yell, fierce eyes",
    "blush":        "blushing, red cheeks, shy embarrassed look, averted eyes",
    "disgusted":    "disgusted, scrunched nose, one eye squinting, slight frown",
    "evilsmirk":    "mischievous smirk, one eyebrow raised, cunning half-smile",
    "frown":        "frowning, concerned, downturned mouth, worried eyes",
    "huh":          "confused, head slightly tilted, wide eyes, open mouth surprise",
    "normalblush":  "neutral with light blush on cheeks, calm but slightly flustered",
    "pout":         "pouting, puffed cheeks, slight frown, cute annoyed look",
    "poutangry":    "angry pout, puffed cheeks with furrowed brows",
    "poutangry2":   "intense angry pout, very puffed cheeks, strong frown",
    "sad1":         "mildly sad, downcast eyes, slight frown",
    "sad2":         "sad, watery eyes, visible frown, dejected look",
    "sad3":         "very sad, eyes closed or looking down, deep sorrow",
    "sadtalk1":     "talking while sad, mouth open, watery eyes",
    "sadtalk2":     "talking while very sad, crying, mouth open",
}


def create_face_mask(image_path: str, face_pct: int = 30) -> bytes:
    """Create a mask image where the face area is transparent (editable).

    The mask has the same dimensions as the input image.
    Transparent pixels = area to regenerate (face).
    White pixels = area to keep (body, hair, clothes).

    Args:
        image_path: Path to the base character image.
        face_pct: Percentage of the image height that is the face area (from top).

    Returns:
        PNG bytes of the mask image.
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    # Create mask: fully opaque (white) everywhere
    mask = Image.new("RGBA", (w, h), (255, 255, 255, 255))

    # Make face area transparent (this is where the model will regenerate)
    face_h = int(h * face_pct / 100)
    # Face region: centered horizontally, top portion of image
    face_left = int(w * 0.2)
    face_right = int(w * 0.8)
    face_top = int(h * 0.02)  # Small margin from top
    face_bottom = face_top + face_h

    for y in range(face_top, face_bottom):
        for x in range(face_left, face_right):
            mask.putpixel((x, y), (0, 0, 0, 0))  # Transparent = edit here

    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


def generate_openai(
    base_path: str,
    mask_bytes: bytes,
    expression_name: str,
    expression_desc: str,
    character_desc: str = "anime character",
    model: str = "gpt-image-1",
) -> bytes:
    """Generate an expression variant using OpenAI's image edit API.

    Returns PNG bytes of the generated image.
    """
    from openai import OpenAI

    client = OpenAI()

    # Read base image
    with open(base_path, "rb") as f:
        base_bytes = f.read()

    prompt = (
        f"Anime character face with {expression_desc}. "
        f"Style: {character_desc}. "
        "Keep exact same art style, same colors, same character. "
        "Only change the facial expression. Clean anime art."
    )

    response = client.images.edit(
        model=model,
        image=base_bytes,
        mask=mask_bytes,
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    # Download the generated image
    import urllib.request
    image_url = response.data[0].url
    if image_url:
        with urllib.request.urlopen(image_url) as resp:
            return resp.read()

    # If base64 response
    if response.data[0].b64_json:
        return base64.b64decode(response.data[0].b64_json)

    raise RuntimeError("No image data in response")


def generate_gemini(
    base_path: str,
    expression_name: str,
    expression_desc: str,
    character_desc: str = "anime character",
) -> bytes:
    """Generate an expression variant using Gemini's image editing.

    Returns PNG bytes of the generated image.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    # Read base image
    with open(base_path, "rb") as f:
        base_bytes = f.read()

    prompt = (
        f"Edit this anime character's facial expression to: {expression_desc}. "
        f"Keep everything else exactly the same — same hair, clothes, body, pose, art style, colors. "
        f"Only change the face. Transparent background. Same dimensions."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-06-17",
        contents=[
            types.Content(parts=[
                types.Part(inline_data=types.Blob(mime_type="image/png", data=base_bytes)),
                types.Part(text=prompt),
            ]),
        ],
        config=types.GenerateContentConfig(
            response_modalities=["image", "text"],
        ),
    )

    # Extract image from response
    for part in response.candidates[0].content.parts:
        if hasattr(part, 'inline_data') and part.inline_data:
            return part.inline_data.data

    raise RuntimeError("No image data in Gemini response")


def remove_background(image_bytes: bytes) -> bytes:
    """Remove background from image using rembg (anime model)."""
    try:
        from rembg import remove
        result = remove(image_bytes, alpha_matting=True)
        return result
    except ImportError:
        log.warning("rembg not installed, skipping background removal")
        return image_bytes


def convert_to_webp(image_bytes: bytes, max_width: int = 0) -> bytes:
    """Convert PNG bytes to WebP with transparency."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    if max_width > 0 and img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=90, lossless=False)
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Generate character expression variants using AI")
    parser.add_argument("--base", required=True, help="Path to base character image (PNG/WebP)")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--name", required=True, help="Character name (e.g., 'keiko')")
    parser.add_argument("--outfit", default="casual", help="Outfit name (e.g., 'casual', 'dress')")
    parser.add_argument("--provider", default="openai", choices=["openai", "gemini"],
                        help="AI provider for image generation")
    parser.add_argument("--face-pct", type=int, default=30, dest="face_pct",
                        help="Face area as %% of image height from top (default: 30)")
    parser.add_argument("--character-desc", default="", dest="character_desc",
                        help="Character description for prompt (e.g., 'anime girl with blue hair')")
    parser.add_argument("--skip-existing", action="store_true", dest="skip_existing",
                        help="Skip expressions that already have output files")
    parser.add_argument("--max-width", type=int, default=512, dest="max_width",
                        help="Max output width in pixels (0=no resize)")
    parser.add_argument("--no-bg-remove", action="store_true", dest="no_bg_remove",
                        help="Skip background removal step")
    parser.add_argument("--expressions", nargs="*", default=None,
                        help="Generate only specific expressions (default: all 19)")

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_path = Path(args.base)
    if not base_path.exists():
        log.error("Base image not found: %s", base_path)
        sys.exit(1)

    # Filter expressions if specified
    expressions = EXPRESSIONS
    if args.expressions:
        expressions = {k: v for k, v in EXPRESSIONS.items() if k in args.expressions}
        log.info("Generating %d/%d expressions: %s", len(expressions), len(EXPRESSIONS), list(expressions.keys()))

    # Auto-detect character description from filename if not provided
    char_desc = args.character_desc or f"anime {args.name} character"

    # Create face mask for OpenAI inpainting
    mask_bytes = None
    if args.provider == "openai":
        log.info("Creating face mask (top %d%% of image)...", args.face_pct)
        mask_bytes = create_face_mask(str(base_path), args.face_pct)
        log.info("Mask created")

    total = len(expressions)
    success = 0
    failed = []
    total_cost = 0.0

    for i, (expr_name, expr_desc) in enumerate(expressions.items(), 1):
        out_file = output_dir / f"{args.name}_{args.outfit}_{expr_name}.webp"

        if args.skip_existing and out_file.exists():
            log.info("[%d/%d] %s — skipped (exists)", i, total, expr_name)
            success += 1
            continue

        log.info("[%d/%d] Generating: %s — %s", i, total, expr_name, expr_desc[:40])

        try:
            t0 = time.time()

            if args.provider == "openai":
                img_bytes = generate_openai(
                    str(base_path), mask_bytes, expr_name, expr_desc, char_desc,
                )
                est_cost = 0.08  # ~$0.08 per image edit
            else:
                img_bytes = generate_gemini(
                    str(base_path), expr_name, expr_desc, char_desc,
                )
                est_cost = 0.05  # ~$0.05 per Gemini image edit

            # Remove background if needed
            if not args.no_bg_remove:
                img_bytes = remove_background(img_bytes)

            # Convert to WebP with optional resize
            webp_bytes = convert_to_webp(img_bytes, max_width=args.max_width)

            # Save
            out_file.write_bytes(webp_bytes)
            elapsed = time.time() - t0
            total_cost += est_cost
            success += 1

            file_size = len(webp_bytes) / 1024
            log.info("[%d/%d] %s — OK (%.1fs, %.0fKB, ~$%.2f)",
                     i, total, expr_name, elapsed, file_size, est_cost)

            # Rate limit courtesy
            time.sleep(1.0)

        except Exception as e:
            log.error("[%d/%d] %s — FAILED: %s", i, total, expr_name, e)
            failed.append(expr_name)

    # Summary
    log.info("=" * 50)
    log.info("Done! %d/%d expressions generated", success, total)
    log.info("Output: %s", output_dir)
    log.info("Estimated cost: $%.2f", total_cost)
    if failed:
        log.warning("Failed: %s", ", ".join(failed))
        log.info("Re-run with --expressions %s to retry", " ".join(failed))


if __name__ == "__main__":
    main()
