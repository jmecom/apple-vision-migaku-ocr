#!/usr/bin/env bash
set -euo pipefail

# 1) Capture to PNG (clipboard path avoids weird files)
tmp="$(mktemp /tmp/ocr-XXXXXX).png"
trap 'rm -f "$tmp"' EXIT

# capture (keep what you had)
if command -v pngpaste >/dev/null 2>&1; then
  screencapture -i -c || {
    echo "Capture canceled."
    exit 0
  }
  pngpaste "$tmp"
else
  screencapture -t png -i -r "$tmp" || {
    echo "Capture canceled."
    exit 0
  }
fi

echo "Saved: $tmp"
file "$tmp"
ls -lh "$tmp" || true

# point to Homebrew tessdata (auto-pick)
if ! { [[ -n "${TESSDATA_PREFIX:-}" ]] && [[ -e "$TESSDATA_PREFIX/jpn.traineddata" || -e "$TESSDATA_PREFIX/jpn_vert.traineddata" ]]; }; then
  for p in "/opt/homebrew/share/tessdata" "/usr/local/share/tessdata"; do
    [[ -e "$p/jpn.traineddata" || -e "$p/jpn_vert.traineddata" ]] && export TESSDATA_PREFIX="$p" && break
  done
fi

# --- OCR (pipe image via stdin to dodge file-open weirdness) ---
set +e
ocr_text="$(cat "$tmp" | tesseract stdin stdout -l jpn --psm 6 -c user_defined_dpi=300 2>/tmp/ocr.err)"
status=$?
set -e

# fallback to vertical if needed
if [[ $status -ne 0 || -z "${ocr_text//[[:space:]]/}" ]]; then
  set +e
  ocr_text="$(cat "$tmp" | tesseract stdin stdout -l jpn_vert --psm 7 -c user_defined_dpi=300 2>>/tmp/ocr.err)"
  status=$?
  set -e
fi

ocr_text="$(printf "%s" "$ocr_text" | sed 's/^[[:space:]]\+//; s/[[:space:]]\+$//')"
if [[ $status -ne 0 || -z "${ocr_text//[[:space:]]/}" ]]; then
  echo "No text recognized."
  echo "--- tesseract stderr ---"
  cat /tmp/ocr.err
  echo "------------------------"
  exit 1
fi

# copy & tiny preview
printf "%s" "$ocr_text" | pbcopy
chars=$(printf "%s" "$ocr_text" | wc -c | tr -d ' ')
echo "OCR OK (${chars} chars):"
printf "%s\n" "$ocr_text" | head -n 2
[ "$(printf "%s" "$ocr_text" | wc -l | tr -d ' ')" -gt 2 ] && echo "…"

osascript <<'OSA'
tell application "DeepL" to activate
delay 0.25
tell application "System Events"
  keystroke "v" using command down
end tell
OSA
