#!/usr/bin/env python3
import argparse
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from pynput import keyboard

from ocr_core import OCRConfig, copy_to_clipboard, ocr_file_to_text, parse_crop


def list_windows() -> List[Dict[str, Any]]:
    # Lazy import to avoid dock icon (Quartz registers as GUI app)
    import Quartz
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    return list(wins)


def pick_window_id(app_substr: str, title_substr: Optional[str]) -> Optional[int]:
    app_substr_l = app_substr.lower()
    title_substr_l = title_substr.lower() if title_substr else None

    for w in list_windows():
        owner = (w.get("kCGWindowOwnerName") or "").lower()
        title = (w.get("kCGWindowName") or "").lower()
        if app_substr_l not in owner:
            continue
        if title_substr_l and title_substr_l not in title:
            continue

        wid = w.get("kCGWindowNumber")
        layer = w.get("kCGWindowLayer", 0)
        if wid is not None and layer == 0:
            return int(wid)

    return None


def screencapture_window(window_id: int, out_png: str) -> None:
    subprocess.run(["screencapture", "-l", str(window_id), "-o", "-x", "-t", "png", out_png], check=True)


def run_once(app: str, title: Optional[str], cfg: OCRConfig, after_cmd: Optional[str]) -> None:
    t0 = time.perf_counter()

    wid = pick_window_id(app, title)
    if wid is None:
        print(f"[daemon] no window matched app='{app}' title='{title or ''}'", flush=True)
        return
    t1 = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="migaku-ocr-") as td:
        img_path = os.path.join(td, "cap.png")
        try:
            screencapture_window(wid, img_path)
        except subprocess.CalledProcessError as e:
            print(f"[daemon] screencapture failed: {e}", flush=True)
            return
        t2 = time.perf_counter()

        text = ocr_file_to_text(img_path, cfg)
        t3 = time.perf_counter()

    if not text.strip():
        print("[daemon] OCR: no text", flush=True)
        return

    copy_to_clipboard(text)

    if after_cmd:
        # naive split is fine if you keep it simple; replace with shlex if you want quoting
        subprocess.Popen(after_cmd.split(" "))

    print(
        f"[daemon] ok | pick:{(t1-t0)*1000:.0f}ms cap:{(t2-t1)*1000:.0f}ms "
        f"ocr:{(t3-t2)*1000:.0f}ms total:{(t3-t0)*1000:.0f}ms | {len(text)} chars",
        flush=True
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Resident OCR daemon: hotkey -> capture window -> ocrmac -> pbcopy")
    ap.add_argument("--app", default="DuckStation", help="Owner/app substring to match")
    ap.add_argument("--title", help="Optional window title substring")
    ap.add_argument("--hotkey", default="<cmd>+<shift>+o", help="Global hotkey (pynput format)")

    ap.add_argument("--framework", default="livetext", choices=["vision", "livetext"])
    ap.add_argument("--level", default="fast", choices=["fast", "accurate"])
    ap.add_argument("--lang", default="ja-JP")
    ap.add_argument("--extra-lang", action="append", default=[])
    ap.add_argument("--crop", help="Normalized crop x0,y0,x1,y1")
    ap.add_argument("--no-cleanup", action="store_true")

    ap.add_argument("--after", help="Optional command to run after copying text")

    args = ap.parse_args()

    crop_norm: Optional[Tuple[float, float, float, float]] = parse_crop(args.crop) if args.crop else None

    cfg = OCRConfig(
        framework=args.framework,
        level=args.level,
        languages=tuple([args.lang] + list(args.extra_lang)),
        crop_norm=crop_norm,
        cleanup_hud=not args.no_cleanup,
    )

    work_queue: queue.Queue = queue.Queue()

    def _fire():
        print("[daemon] hotkey triggered!", flush=True)
        work_queue.put(True)

    print(f"[daemon] running. hotkey={args.hotkey} (needs Accessibility permission)", flush=True)
    print(f"[daemon] watching for app='{args.app}'", flush=True)

    # Start hotkey listener in background thread
    listener = keyboard.GlobalHotKeys({args.hotkey: _fire})
    listener.start()

    # Main thread processes OCR requests
    try:
        while True:
            work_queue.get()  # Block until hotkey fires
            run_once(args.app, args.title, cfg, args.after)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
