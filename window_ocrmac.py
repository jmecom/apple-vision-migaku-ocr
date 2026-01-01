#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

from ocrmac import ocrmac  # pip install ocrmac


def list_on_screen_windows() -> List[Dict[str, Any]]:
    # Lazy import so --image mode doesn't require Quartz
    import Quartz  # type: ignore

    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    return list(wins)


def window_label(w: Dict[str, Any]) -> str:
    owner = w.get("kCGWindowOwnerName", "") or ""
    title = w.get("kCGWindowName", "") or ""
    wid = w.get("kCGWindowNumber", "")
    layer = w.get("kCGWindowLayer", "")
    if not title:
        title = "<no title>"
    return f"[{wid}] {owner} — {title} (layer {layer})"


def filter_windows(
    windows: List[Dict[str, Any]],
    app_substr: Optional[str],
    title_substr: Optional[str],
) -> List[Dict[str, Any]]:
    def match(s: str, needle: Optional[str]) -> bool:
        if not needle:
            return True
        return needle.lower() in (s or "").lower()

    out = []
    for w in windows:
        owner = w.get("kCGWindowOwnerName", "") or ""
        title = w.get("kCGWindowName", "") or ""
        if match(owner, app_substr) and match(title, title_substr):
            out.append(w)
    return out


def pick_window_interactively(windows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not windows:
        raise RuntimeError("No windows to choose from.")

    print("Select a window:")
    for i, w in enumerate(windows):
        print(f"{i:3d}: {window_label(w)}")

    while True:
        raw = input("Enter number: ").strip()
        try:
            idx = int(raw)
            if 0 <= idx < len(windows):
                return windows[idx]
        except ValueError:
            pass
        print("Invalid selection. Try again.")


def screencapture_window(window_id: int, out_png: str) -> None:
    cmd = ["screencapture", "-l", str(window_id), "-o", "-x", "-t", "png", out_png]
    subprocess.run(cmd, check=True)


def ocr_image_to_text(
    path: str,
    framework: str,
    recognition_level: str,
    languages: List[str],
) -> str:
    """
    framework: 'livetext' or 'vision'
    recognition_level: 'fast' or 'accurate' (Vision backend only)
    languages: language tags like ['ja-JP'] (Vision backend uses language_preference)
    """
    if framework == "livetext":
        anns = ocrmac.OCR(path, framework="livetext").recognize()
    else:
        anns = ocrmac.OCR(
            path,
            framework="vision",
            recognition_level=recognition_level,
            language_preference=languages,
        ).recognize()

    # anns is list of (text, confidence, bbox)  [oai_citation:1‡GitHub](https://github.com/straussmaximilian/ocrmac?utm_source=chatgpt.com)
    texts = [t for (t, _conf, _bbox) in anns if t and t.strip()]
    return "".join(texts).strip()


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="OCR a macOS window (screenshot it) OR OCR a sample image file, then copy text to clipboard."
    )

    # Test mode
    ap.add_argument("--image", help="Path to a PNG/JPG to OCR (test mode; skips window capture).")

    # Window mode filters
    ap.add_argument("--app", help="Substring of app/owner name to filter (e.g. DuckStation).")
    ap.add_argument("--title", help="Substring of window title to filter.")
    ap.add_argument(
        "--noninteractive",
        action="store_true",
        help="Auto-pick the first matching window (requires --app and/or --title).",
    )

    ap.add_argument(
        "--framework",
        default="auto",
        choices=["auto", "livetext", "vision"],
        help="OCR backend. 'auto' tries livetext then falls back to vision.",
    )
    ap.add_argument(
        "--level",
        default="accurate",
        choices=["fast", "accurate"],
        help="Recognition level for Vision backend.",
    )
    ap.add_argument(
        "--lang",
        default="ja-JP",
        help="Primary language tag (e.g. ja-JP, en-US). For vision backend.",
    )
    ap.add_argument(
        "--extra-lang",
        action="append",
        default=[],
        help="Additional language tags (repeatable). For vision backend.",
    )

    args = ap.parse_args()
    langs = [args.lang] + list(args.extra_lang)

    # --- Determine image path (test mode vs window mode) ---
    if args.image:
        img_path = os.path.abspath(os.path.expanduser(args.image))
        if not os.path.exists(img_path):
            print(f"--image not found: {img_path}", file=sys.stderr)
            return 2
    else:
        # Window mode requires Quartz + Screen Recording permission
        if not (args.app or args.title) and args.noninteractive:
            print("--noninteractive requires --app and/or --title", file=sys.stderr)
            return 2

        try:
            wins = list_on_screen_windows()
        except Exception as e:
            print(
                "Failed to list windows. If you’re missing Quartz bindings:\n"
                "  pip install pyobjc-framework-Quartz\n"
                f"Error: {e}",
                file=sys.stderr,
            )
            return 3

        wins = filter_windows(wins, args.app, args.title)
        if not wins:
            print("No windows matched your filters.", file=sys.stderr)
            return 4

        chosen = wins[0] if args.noninteractive else pick_window_interactively(wins)
        wid = chosen.get("kCGWindowNumber")
        if wid is None:
            print("Selected window has no kCGWindowNumber; can't capture.", file=sys.stderr)
            return 5

        with tempfile.TemporaryDirectory(prefix="window-ocr-") as td:
            tmp_img = os.path.join(td, "capture.png")
            try:
                screencapture_window(int(wid), tmp_img)
            except subprocess.CalledProcessError as e:
                print(
                    "screencapture failed. You likely need Screen Recording permission for your Terminal/Python.\n"
                    f"Error: {e}",
                    file=sys.stderr,
                )
                return 6
            img_path = tmp_img

            # OCR + clipboard
            text = run_ocr_pipeline(img_path, args.framework, args.level, langs)
            if not text.strip():
                print("No text recognized.", file=sys.stderr)
                return 7
            copy_to_clipboard(text)
            print_ok_preview(text)
            return 0

    # If we’re here, we’re in --image mode (no temp dir needed)
    text = run_ocr_pipeline(img_path, args.framework, args.level, langs)
    if not text.strip():
        print("No text recognized.", file=sys.stderr)
        return 7
    copy_to_clipboard(text)
    print_ok_preview(text)
    return 0


def run_ocr_pipeline(img_path: str, framework_choice: str, level: str, langs: List[str]) -> str:
    text = ""
    if framework_choice in ("auto", "livetext"):
        try:
            text = ocr_image_to_text(img_path, "livetext", level, langs)
        except Exception:
            text = ""

    if not text and framework_choice in ("auto", "vision"):
        text = ocr_image_to_text(img_path, "vision", level, langs)

    return text


def print_ok_preview(text: str) -> None:
    print(f"OCR OK. Copied {len(text)} chars to clipboard.")
    preview = text[:200].replace("\n", "\\n")
    print(f"Preview: {preview}{'…' if len(text) > 200 else ''}")


if __name__ == "__main__":
    raise SystemExit(main())
