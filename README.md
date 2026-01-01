# apple-vision-migaku-ocr

OCR pipeline for working with emulators like DuckStation: capture DuckStation window → OCR → clipboard → Migaku.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install ocrmac pillow pynput pyobjc-framework-Quartz
```

**macOS permissions required:**
- Screen Recording (for window capture)
- Accessibility (for global hotkey)

## Usage

### 1. Enable Migaku Clipboard auto-detect

Open Migaku Clipboard in Chrome (Migaku extension → Clipboard), then **enable the auto-detect toggle**. This makes Migaku automatically read from clipboard when it changes.

### 2. Run the daemon

```bash
source venv/bin/activate
python3 ocr_daemon.py --app DuckStation
```

Press **Cmd+Shift+O** to capture, OCR, and copy text to clipboard. Migaku will auto-detect the new text.

### With cropping (faster + less HUD junk)

```bash
python3 ocr_daemon.py --app DuckStation --crop 0.05,0.62,0.95,0.95
```

Adjust crop coordinates for your game's dialogue box position.

### All daemon options

| Flag | Default | Description |
|------|---------|-------------|
| `--app` | DuckStation | Window owner substring to match |
| `--title` | | Window title substring (optional) |
| `--hotkey` | `<cmd>+<shift>+o` | Global hotkey (pynput format) |
| `--framework` | livetext | `livetext` or `vision` |
| `--level` | fast | `fast` or `accurate` (vision only) |
| `--crop` | | `x0,y0,x1,y1` normalized coords (0-1) |

## Test OCR on an image

```bash
python3 ocr_core.py --image samples/screenshot.png
```

## Files

- `ocr_core.py` - OCR engine with cropping and cleanup
- `ocr_daemon.py` - Resident daemon with global hotkey
