# MultiDeadline Timer Manual (English)

## 1. Overview
`timer_app.py` is a Tkinter desktop app for managing multiple timers simultaneously.  
When a timer finishes, it shows a centered, horizontal, topmost alert band on the screen.

- Supported OS: macOS / Windows / Linux
- Dependencies: Python standard library only

## 2. Requirements
- Python 3.x
- tkinter (usually bundled with Python)

## 3. How to Run
Open a terminal in the project folder and run:

```bash
python3 timer_app.py
```

On Windows:

```powershell
python timer_app.py
```

## 4. UI Layout
- Top input area
  - `Label`: timer name
  - `Time`: timer input
  - `Add`: add timer
- Timer list (scrollable)
  - Label
  - Remaining (click to edit)
  - End Time (click to edit)
  - State (`Running` / `Paused` / `Finished`)
  - Start / Pause / Cancel

## 5. Adding Timers
`Time` accepts the following formats:

1. Absolute time: `HH:MM`
- Example: `07:20`
- If the time is earlier than now, it is treated as next day

2. Relative time: `M:SS`
- Example: `0:55` (55 seconds)

3. Minutes only
- Example: `15` (15 minutes)

Press `Add` or Enter to create a timer.

## 6. Basic Operations
- `Start`: resume a paused timer
- `Pause`: pause a running timer
- `Cancel`: remove a timer
- `Label` field: editable at any time, regardless of state

## 7. Editing Remaining / End Time
- Click `Remaining`: reset as relative duration
- Click `End Time`: reset as absolute clock time

The dialog opens with the timer's previously configured value.

Examples:
- A timer created with `0:55` shows `0:55` in Remaining after finish
- A timer created with `00:55` shows `00:55` in End Time after finish

## 8. Finish Alert
When a timer reaches zero, a centered horizontal band displays `Time is up!`.

Dismiss methods:
- `ESC`
- `Enter`
- Mouse click

After dismissal, focus returns to the top-left Label input field.

## 9. Auto-Restore After Restart
The app automatically saves timer state.

- State file: `timer_state.json`
- Save timing:
  - periodic autosave after changes
  - on app close
- State is loaded on startup

This allows countdowns to continue naturally after reopening the app (based on absolute end time).

## 10. OS-Based Font Selection
The app automatically picks UI fonts by OS.

- macOS: `Hiragino Sans`, etc.
- Windows: `Yu Gothic UI` / `Meiryo UI` / `Segoe UI`
- Linux: `Noto Sans CJK JP`, etc.

## 11. Troubleshooting
1. Timer cannot be added
- Check time format (`HH:MM`, `M:SS`, or minutes).

2. State is not restored
- Check whether `timer_state.json` exists and is writable.

3. Text rendering looks broken
- Install appropriate CJK/Japanese fonts for your OS.

## 12. Files
- `timer_app.py`: main application
- `timer_state.json`: auto-saved timer state
- `readme.md`: Japanese manual
- `README_EN.md`: English manual
