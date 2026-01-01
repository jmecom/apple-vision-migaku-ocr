#!/usr/bin/env python3
import argparse
import subprocess
import sys

APPLE_SCRIPT = r'''
on run argv
  set browserName to item 1 of argv
  set doPaste to item 2 of argv

  tell application browserName
    activate
    set foundTab to false

    repeat with w in windows
      set ti to 1
      repeat with t in tabs of w
        set theTitle to (title of t) as text
        if theTitle contains "Migaku Clipboard" then
          set active tab index of w to ti
          set index of w to 1
          set foundTab to true
          exit repeat
        end if
        set ti to ti + 1
      end repeat
      if foundTab then exit repeat
    end repeat
  end tell

  if foundTab is false then
    return "NOT_FOUND"
  end if

  if doPaste is "1" then
    delay 0.05
    tell application "System Events"
      keystroke "v" using command down
    end tell
  end if

  return "OK"
end run
'''

def main() -> int:
    ap = argparse.ArgumentParser(description="Focus Migaku Clipboard tab and optionally paste clipboard.")
    ap.add_argument("--browser", default="Google Chrome", help="Browser app name (Google Chrome, Brave Browser, etc.)")
    ap.add_argument("--paste", action="store_true", help="Send Cmd+V after focusing")
    args = ap.parse_args()

    res = subprocess.run(
        ["osascript", "-e", APPLE_SCRIPT, args.browser, "1" if args.paste else "0"],
        capture_output=True,
        text=True,
    )

    out = (res.stdout or "").strip()
    if out == "NOT_FOUND":
        print("Migaku Clipboard tab not found. Open it once (Migaku icon → Clipboard) and leave it open.")
        return 2

    if res.returncode != 0:
        sys.stderr.write(res.stderr or "")
        return res.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
