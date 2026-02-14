# MultiDeadline Timer Manual (English)

## 1. Overview
`timer_app.py` is a Tkinter desktop app for managing multiple timers at once.  
When a timer finishes, it shows a centered fullscreen horizontal alert.

- Supported OS: macOS / Windows / Linux
- Dependencies: Python standard library only

## 2. Requirements
- Python 3.x
- tkinter (usually bundled with Python)

## 3. Run
```bash
python3 timer_app.py
```

Windows:
```powershell
python timer_app.py
```

## 4. UI Layout
### Main view
- Top controls
  - `Label`
  - `Time (HH:MM / M:SS / Minutes)`
  - `Add`
  - `Trash`
- Timer list
  - Label
  - Remaining  
    `(Click to edit)`
  - End Time  
    `(Click to edit)`
  - Actions (`▶/⏸`, `⏹`, `ⓧ`)

### Trash view
- Top controls show only `← Back to Main` and `Empty Trash`
- List shows deleted timers
- Per row: `↩` (restore) / `🗑` (delete permanently)

## 5. Input Formats
`Time` accepts:

1. Absolute: `HH:MM` (example: `07:20`)
2. Relative: `M:SS` (example: `0:55`)
3. Minutes only: `15`

If absolute time is already in the past, it is scheduled for the next day.

## 6. Timer Behavior
### absolute (`HH:MM`)
- Source of truth: target wall-clock time
- While running, `⏸` is shown but disabled (no pause)
- `⏹` stops updates and shows Remaining as `--:--`
- At 00:00:
  1. show alert
  2. after alert, Remaining becomes `--:--`
  3. `▶` starts a new countdown to the next same `HH:MM`
  4. `⏹` is ignored after finish

### relative (`M:SS` / minutes)
- Source of truth: `remaining_seconds` + `initial_seconds`
- `⏸` pauses, `▶` resumes
- `⏹` does reset-stop (back to `initial_seconds`)
- At 00:00:
  1. show alert
  2. after alert, Remaining shows the last configured value (e.g. `00:30`)
  3. `▶` starts a fresh countdown
  4. `⏹` is ignored after finish

## 7. Editing
- Click Remaining: reconfigure as relative duration
- Click End Time: reconfigure as absolute clock time
- Label is directly editable in each row

## 8. Delete and Restore
- `ⓧ`: soft delete to Trash
- Trash `↩`: restore
- Trash `🗑`: permanent delete
- `Empty Trash`: clear all trashed timers

## 9. Finish Alert
When a timer reaches zero, `Time is up!` is shown as a fullscreen horizontal alert.

Dismiss by:
- `ESC`
- `Enter`
- mouse click

## 10. Autosave / Restore
- File: `timer_state.json`
- Keys: `timers` (active) and `trash` (deleted)
- Saved by periodic autosave and on close
- Restored at startup (legacy state file is migrated gracefully)

## 11. Files
- `timer_app.py`: main app
- `timer_state.json`: persisted state
- `README.md`: Japanese manual
- `README_EN.md`: English manual
