#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from PIL import Image
from ocrmac import ocrmac


# Languages supported by ocrmac's language_preference parameter
VISION_SUPPORTED_LANGS = {"en-US", "fr-FR", "it-IT", "de-DE", "es-ES", "pt-BR"}


@dataclass
class OCRConfig:
    framework: str = "livetext"        # "vision" or "livetext" (livetext better for Japanese)
    level: str = "fast"                # "fast" or "accurate" (vision only)
    languages: Tuple[str, ...] = ("ja-JP",)
    crop_norm: Optional[Tuple[float, float, float, float]] = None  # x0,y0,x1,y1 normalized
    cleanup_hud: bool = True


def parse_crop(crop: str) -> Tuple[float, float, float, float]:
    """
    crop: "x0,y0,x1,y1" in normalized [0..1] coords.
    Example: bottom dialogue box: "0.05,0.62,0.95,0.95"
    """
    parts = [p.strip() for p in crop.split(",")]
    if len(parts) != 4:
        raise ValueError("--crop must be x0,y0,x1,y1")
    x0, y0, x1, y1 = map(float, parts)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("crop must satisfy 0<=x0<x1<=1 and 0<=y0<y1<=1")
    return (x0, y0, x1, y1)


def load_and_crop(img_path: str, crop_norm) -> Image.Image:
    img = Image.open(img_path).convert("RGB")
    if not crop_norm:
        return img
    w, h = img.size
    x0, y0, x1, y1 = crop_norm
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    return img.crop(box)


def ocr_image_to_text(img: Image.Image, cfg: OCRConfig) -> str:
    if cfg.framework == "livetext":
        anns = ocrmac.OCR(img, framework="livetext").recognize()
    else:
        # Only pass language_preference for supported languages; otherwise let Vision auto-detect
        supported = [lang for lang in cfg.languages if lang in VISION_SUPPORTED_LANGS]
        if supported:
            anns = ocrmac.OCR(
                img,
                framework="vision",
                recognition_level=cfg.level,
                language_preference=supported,
            ).recognize()
        else:
            # Japanese and other languages work via auto-detection
            anns = ocrmac.OCR(
                img,
                framework="vision",
                recognition_level=cfg.level,
            ).recognize()

    # anns: list of (text, confidence, bbox)
    texts = [t for (t, _conf, _bbox) in anns if t and t.strip()]
    out = "".join(texts).strip()

    if cfg.cleanup_hud:
        # Optional cleanup for common overlay junk
        out = re.sub(r"(?:\b\d+FPS\b|\bVideo:\d+FPS\b|\bGame:\d+FPS\b|\b\d+x\d+\b)", "", out)
        out = re.sub(r"\s{2,}", " ", out).strip()

    return out


def ocr_file_to_text(img_path: str, cfg: OCRConfig) -> str:
    img = load_and_crop(img_path, cfg.crop_norm)
    return ocr_image_to_text(img, cfg)


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR an image using ocrmac and copy to clipboard.")
    ap.add_argument("--image", required=True, help="Path to PNG/JPG to OCR")
    ap.add_argument("--framework", default="livetext", choices=["vision", "livetext"])
    ap.add_argument("--level", default="fast", choices=["fast", "accurate"])
    ap.add_argument("--lang", default="ja-JP")
    ap.add_argument("--extra-lang", action="append", default=[])
    ap.add_argument("--crop", help="Normalized crop x0,y0,x1,y1")
    ap.add_argument("--no-cleanup", action="store_true", help="Disable overlay cleanup")

    args = ap.parse_args()
    img_path = os.path.abspath(os.path.expanduser(args.image))
    if not os.path.exists(img_path):
        print(f"not found: {img_path}")
        return 2

    cfg = OCRConfig(
        framework=args.framework,
        level=args.level,
        languages=tuple([args.lang] + list(args.extra_lang)),
        crop_norm=parse_crop(args.crop) if args.crop else None,
        cleanup_hud=not args.no_cleanup,
    )

    text = ocr_file_to_text(img_path, cfg)
    if not text.strip():
        print("No text recognized.")
        return 3

    copy_to_clipboard(text)
    print(f"OCR OK. Copied {len(text)} chars.")
    print("Preview:", text[:200].replace("\n", "\\n") + ("…" if len(text) > 200 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
