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
### Tab strip
- System tab `General` on the far left
- User-created tabs in the middle
- `+` button near the right
- System tab `Trash` on the far right

### Normal tabs (`General` / user tabs)
- Top controls
  - `Label`
  - `Time (HH:MM / M:SS / Minutes)`
  - `Add`
  - `Delete Tab`
- Timer list
  - Label
  - Remaining  
    `(Click to edit)`
  - End Time  
    `(Click to edit)`
  - Actions (`▶/⏸`, `⏹`, `⚙`, `ⓧ`)

### Trash tab
- No new timer creation
- No settings dialog
- No normal inline editing
- Shows `Empty Trash`
- Per row: `↩` (restore) / `🗑` (delete permanently)

## 5. Tab Operations
### Create
- Press `+` to create a new user tab.
- The default name is `New Tab`.
- Duplicate tab names are allowed.

### Select
- Single-click a tab to select it and show its contents.
- Startup always selects `General`.

### Rename
- Double-click the currently selected user tab to rename it.
- `General` and `Trash` cannot be renamed.

### Reorder
- Only user-created tabs are reorderable.
- `General` stays fixed on the left, `Trash` stays fixed on the right, and `+` stays just before `Trash`.
- Drag a user tab to change its position inside the user-tab region.

### Delete
- `Delete Tab` removes the currently selected user tab.
- A non-empty tab cannot be deleted.
- `General` and `Trash` can never be deleted.

## 6. Timer Input Formats
`Time` accepts:

1. Absolute: `HH:MM` (example: `07:20`)
2. Relative: `M:SS` (example: `0:55`)
3. Minutes only: `15`

## 7. Timer Placement and Drag-and-Drop
- Every timer belongs to exactly one tab.
- Within a tab, timers can be reordered vertically by drag-and-drop.
- Dragging a timer onto another tab moves it to that tab.
- Hovering over another tab briefly opens that tab so you can drop at an arbitrary position there.
- Dragging to `Trash` is the same as soft delete.
- Dragging from `Trash` to a normal tab respects the explicit drop target.

## 8. Timer Behavior
### absolute (`HH:MM`)
- Source of truth: configured wall-clock `HH:MM`
- End Time always shows the configured `HH:MM` exactly
- It is never reverse-derived from remaining seconds in a way that can show `07:19` for a `07:20` timer
- While running, `⏸` is shown but disabled (no pause)
- `⏹` stops updates and shows Remaining as `--:--`
- After completion, Remaining shows `00:00` only while its alert is still pending/visible, then `--:--`
- `▶` starts again toward the next valid occurrence

### relative (`M:SS` / minutes)
- Source of truth: `remaining_seconds` + `initial_seconds`
- `⏸` pauses, `▶` resumes
- `⏹` resets to the initial duration and leaves the timer stopped
- After completion, Remaining shows `00:00` only while its alert is still pending/visible
- After dismissing the alert, Remaining shows the last configured relative value
- `▶` starts a fresh countdown

## 9. Timer Editing
- Click Remaining: reset as a relative duration
- Click End Time: reset as an absolute clock time
- Label is directly editable in each row inside normal tabs
- Click `⚙` to open the timer settings dialog

## 10. Timer Settings Dialog
The settings dialog currently handles repeat-related configuration.

### Absolute timer repeat
- Weekday toggles: `Sun Mon Tue Wed Thu Fri Sat`
- Default: all OFF
- Selected weekdays define which future weekdays are valid for that fixed `HH:MM`
- As soon as an occurrence fires, the timer immediately reschedules itself to the next valid weekday at the same `HH:MM`
- It does not re-trigger again on the same day right away
- Missed past occurrences while the app was closed/asleep are not replayed
- If stopped, it stays inactive until restarted, and restart computes the next valid future occurrence

### Relative timer repeat
- Toggle: `Restart automatically when this relative timer reaches zero`
- Default: OFF
- When ON, reaching zero immediately starts the next cycle with the same duration
- The timer keeps cycling internally even if left unattended
- Duplicate alerts for the same timer are deduplicated and do not pile up

### Across type changes
- Both absolute weekday settings and relative repeat settings are kept in timer state
- Irrelevant controls remain visible but disabled
- If the timer type changes back later, the previous settings for that type come back

## 11. Delete, Trash, and Restore
- `ⓧ`: soft delete to `Trash`
- When a timer enters `Trash`, the app remembers the last normal tab it came from
- `Trash` `↩`: restore to the remembered previous tab
- If that tab no longer exists, restore to `General`
- `Trash` `🗑`: permanently delete that timer
- `Empty Trash`: clear all trashed timers

## 12. Finish Alert
When a timer reaches zero, `Time is up!` is shown as a fullscreen horizontal alert.

Dismiss by:
- `ESC`
- `Enter`
- mouse click

Note:
- Even with relative repeat enabled, identical alerts for the same timer are deduplicated

## 13. Autosave / Restore
- File: `timer_state.json`
- Saved by periodic autosave and on close
- Restored at startup
- Legacy state files are migrated gracefully

The current save data includes:
- tab list
- selected tab ID
- per-tab timer order
- per-timer `tab_id`
- per-timer `last_non_trash_tab_id`
- absolute repeat weekdays
- relative repeat setting

When loading an old state file that only has `timers` and `trash`:
- active timers are migrated into `General`
- trashed timers are migrated into `Trash`

## 14. Files
- `timer_app.py`: main app
- `timer_state.json`: persisted state
- `README.md`: Japanese manual
- `README_EN.md`: English manual
