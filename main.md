# main.py — Epic Seven Auto Bookmark

A PyQt6 desktop GUI that automates buying covenant and mystic bookmarks from the Epic Seven secret shop, using ADB screen capture + OpenCV template matching.

---

## Architecture

```
┌──────────────┐     signals      ┌──────────────┐     ADB      ┌──────────────┐
│  Ui_Main     │ ◄──────────────► │   worker      │ ◄──────────► │  emulator    │
│  (Qt GUI)    │                  │  (QThread)   │   adbutils    │  / device    │
└──────────────┘                  └──────────────┘               └──────────────┘
```

- **Ui_Main** — builds the GUI, wires signal/slots, holds the `worker` instance.
- **worker** — runs on a separate QThread; owns all automation logic (connect, screenshot, template-match, click).
- **adb device** — the Android device/emulator that runs the game, controlled via `adbutils`.

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `PyQt6` | Desktop GUI (windows, tabs, buttons, signals) |
| `adbutils` | ADB connection & device control (screenshot, click, swipe) |
| `aircv` | OpenCV-based template matching (find button locations on screen) |
| `numpy` | Array conversion for screenshot ↔ aircv |

---

## Core Logic

### 1. resource_path() (line 14)

```python
def resource_path(relative_path):
```

Resolves asset paths whether running as a bundled PyInstaller executable (`sys._MEIPASS`) or from source (`os.path.abspath(".")`).

### 2. worker (QThread) (line 24)

The automation thread. Signal/slot pairings:

| Signal | Receiver | Purpose |
|--------|----------|---------|
| `isStart` | `logBox.append` | Log "script started" |
| `isFinish(str)` | `onFinish(msg)` | Display summary and reset UI |
| `isError(str)` | `logBox.append` | Log exception message |
| `emitLog(str)` | `logBox.append` | Runtime log lines |
| `emitMoney(str)` | `moneyEdit.setText` | Live money counter update |
| `emitStone(str)` | `stoneEdit.setText` | Live skystone counter update |

#### Main loop (`run()`, line 98)

```
while expectNum > 0 AND money > 280,000 AND stones >= 3:
    1. Screenshot
    2. Template-match covenant icon → click buy
    3. Screenshot again (screen may have changed)
    4. Template-match mystic icon → click buy
    5. If needRefresh: click refresh + confirm (costs 3 stones)
    6. Else: swipe up to scroll the shop list
    7. needRefresh toggles each iteration (swipe ↔ refresh alternating)
```

**Stop conditions** (mode picked by radio button):
- **Mode 1** — stop when covenant purchases reach `expectNum`
- **Mode 2** — stop when mystic purchases reach `expectNum`
- **Mode 3** — stop when skystones spent (via refreshes) reach `expectNum`

The loop also stops when money drops below 280k or stones below 3.

#### handle_buy_button() (line 51)

After tapping a bookmark location, waits for the buy popup, template-matches the buy button, clicks it, and updates counters.

#### handle_refresh_button() (line 75)

Finds the refresh button, clicks it, waits for the confirmation dialog, template-matches "Yes" and clicks it. Costs 3 skystones per refresh.

#### Summary (line 140)

On exit, emits `isFinish` with a formatted string containing total refreshes, stones/money spent, bookmarks found, and per-bookmark expected skystone cost.

### 3. Ui_Main (line 166)

A 320×550 window with:

- **"功能" tab** — config file picker, money/stone inputs, stop-condition radio buttons, log browser, start/stop button.
- **"說明" tab** — static HTML instructions.

#### Key methods

| Method | Trigger | Action |
|--------|---------|--------|
| `selectConfigFile()` | "選取設定檔" button | Opens JSON file dialog, loads config |
| `toggleStart()` | "開始執行" / "停止執行" button | Starts worker or terminates it |
| `onFinish(msg)` | `isFinish` / manual stop | Logs summary, resets button to "開始執行" |

---

## Assets Expected

```
img/
├── covenantLocation.png      # Template for covenant bookmarks in shop list
├── mysticLocation.png        # Template for mystic bookmarks in shop list
├── buyButton-{lang}.png      # Template for the buy/confirm button
├── refreshButton-{lang}.png  # Template for the refresh button
├── refreshYesButton-{lang}.png  # Template for the refresh confirmation
└── main.ico                  # App window icon
```

`{lang}` is read from `config.json` → `e7_language` (e.g. `tw`, `en`, `kr`).

---

## config.json Format

```json
{
    "adb_addr": "127.0.0.1:5555",
    "e7_language": "tw"
}
```

| Field | Description |
|-------|-------------|
| `adb_addr` | ADB connect address (emu default: `127.0.0.1:5555`) |
| `e7_language` | Game client language, used to pick correct button templates |

---

## Key Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| Covenant buy cost | 184,000 gold | In-game price per covenant bookmark pack |
| Mystic buy cost | 280,000 gold | In-game price per mystic bookmark pack |
| Refresh cost | 3 skystones | Cost per shop refresh |
| Loop money floor | 280,000 | Loop stops if gold drops below this |
| Template threshold | 0.8–0.9 | Confidence cutoff for `aircv.find_template` |
| Window size | 320×550 | Fixed-size Qt window |

---

## Startup

```bash
python main.py
```

If bundled with PyInstaller, run the generated `.exe`. The app requires an Android emulator or device already running and reachable at the configured ADB address, with Epic Seven open on the secret shop screen.

---

## Notes

- The swipe action (`device.swipe(1400, 500, 1400, 200, 0.1)`) scrolls the shop list down; coordinates are hardcoded for a specific emulator resolution.
- `worker.terminate()` on manual stop is a hard thread kill — it does not perform graceful cleanup.
- Template-matching runs twice per iteration (covenant + mystic) even if no bookmark appeared, since screenshots are re-captured each time.
