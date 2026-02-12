#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run:
  python3 timer_app.py

Requirements:
  - Python 3.x
  - Standard library only (tkinter, datetime, dataclasses, re, uuid)
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import re
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from uuid import uuid4


ABSOLUTE_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
RELATIVE_COLON_RE = re.compile(r"^(\d{1,3}):(\d{1,2})$")
MINUTES_ONLY_RE = re.compile(r"^\d+$")
COLUMN_WIDTHS = [240, 300, 220, 120, 260]


def pick_ui_font_family(root: tk.Tk) -> str:
    system = platform.system()
    if system == "Darwin":
        candidates = ["Hiragino Sans", "YuGothic", "Arial Unicode MS"]
    elif system == "Windows":
        candidates = ["Yu Gothic UI", "Meiryo UI", "Segoe UI"]
    else:
        candidates = ["Noto Sans CJK JP", "Noto Sans JP", "DejaVu Sans", "Liberation Sans"]

    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return "TkDefaultFont"


@dataclass
class TimerItem:
    timer_id: str
    label: str
    state: str  # Running, Paused, Finished
    end_time: dt.datetime | None
    paused_remaining: int = 0
    finished_at: dt.datetime | None = None
    alerted: bool = False
    input_mode: str = "relative"  # relative or absolute
    preset_relative: str | None = None
    preset_absolute: str | None = None

    row_frame: ttk.Frame | None = field(default=None, repr=False)
    label_var: tk.StringVar | None = field(default=None, repr=False)
    remaining_var: tk.StringVar | None = field(default=None, repr=False)
    end_var: tk.StringVar | None = field(default=None, repr=False)
    state_var: tk.StringVar | None = field(default=None, repr=False)


class TimerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MultiDeadline Timer")
        self.root.geometry("1260x780")
        self.root.minsize(1120, 700)
        self.ui_font_family = pick_ui_font_family(self.root)
        self.root.option_add("*Font", f"{{{self.ui_font_family}}} 13")
        self.state_path = Path(__file__).with_name("timer_state.json")
        self.state_dirty = False

        self.timers: dict[str, TimerItem] = {}
        self.timer_order: list[str] = []
        self.pending_alerts: list[TimerItem] = []
        self.current_alert_window: tk.Toplevel | None = None
        self.current_alert_timer: TimerItem | None = None
        self.alert_key_bindings: list[tuple[str, str]] = []
        self.reset_dialog: tk.Toplevel | None = None
        self.reset_target_timer_id: str | None = None
        self.reset_source_mode: str | None = None
        self.reset_input_var = tk.StringVar()
        self.add_label_entry: ttk.Entry | None = None
        self.add_time_entry: ttk.Entry | None = None
        self.dragging_timer_id: str | None = None

        self.input_var = tk.StringVar()
        self.label_input_var = tk.StringVar(value="Timer")
        self.error_var = tk.StringVar(value="")

        self._build_ui()
        self._load_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._autosave_loop)
        self._tick()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        add_frame = ttk.Frame(container)
        add_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(add_frame, text="Label").pack(side="left")
        label_entry = ttk.Entry(add_frame, textvariable=self.label_input_var, width=20)
        label_entry.pack(side="left", padx=(6, 12))
        self.add_label_entry = label_entry

        ttk.Label(add_frame, text="Time (HH:MM / M:SS / Minutes)").pack(side="left")
        entry = ttk.Entry(add_frame, textvariable=self.input_var, width=24)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _: self.add_timer())
        self.add_time_entry = entry

        add_btn = ttk.Button(add_frame, text="Add", command=self.add_timer)
        add_btn.pack(side="left", padx=(4, 0))

        ttk.Label(container, textvariable=self.error_var, foreground="red").pack(fill="x", pady=(0, 8))

        header = ttk.Frame(container)
        header.pack(fill="x")
        for idx, min_w in enumerate(COLUMN_WIDTHS):
            header.grid_columnconfigure(idx, minsize=min_w)
        ttk.Label(header, text="Label").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(header, text="Remaining (Click to edit)").grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(header, text="End Time (Click to edit)").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Label(header, text="State").grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(header, text="Actions").grid(row=0, column=4, sticky="w", padx=4)

        list_frame = ttk.Frame(container)
        list_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.rows_container = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows_container, anchor="nw")

        self.rows_container.bind("<Configure>", self._on_rows_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.root.bind("<MouseWheel>", self._on_mousewheel)

    def _on_rows_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def add_timer(self) -> None:
        raw_time = self.input_var.get().strip()
        raw_label = self.label_input_var.get().strip()
        label = raw_label if raw_label else f"Timer {len(self.timers) + 1}"

        if not raw_time:
            self.error_var.set("Time input is required.")
            return

        try:
            end_time, parsed_mode, normalized_value = self._parse_time_input(raw_time)
        except ValueError as exc:
            self.error_var.set(str(exc))
            return

        self.error_var.set("")
        item = TimerItem(
            timer_id=str(uuid4()),
            label=label,
            state="Running",
            end_time=end_time,
            input_mode=parsed_mode,
            preset_relative=normalized_value if parsed_mode == "relative" else None,
            preset_absolute=normalized_value if parsed_mode == "absolute" else None,
        )
        self.timers[item.timer_id] = item
        self.timer_order.append(item.timer_id)
        self._create_row(item)
        self._repack_rows()
        self._mark_dirty()

        self.input_var.set("")

    def _parse_time_input(self, value: str) -> tuple[dt.datetime, str, str]:
        now = dt.datetime.now()

        m_abs = ABSOLUTE_TIME_RE.match(value)
        if m_abs:
            hour = int(m_abs.group(1))
            minute = int(m_abs.group(2))
            if hour > 23 or minute > 59:
                raise ValueError("Absolute time must be HH:MM (00:00-23:59).")
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += dt.timedelta(days=1)
            return target, "absolute", f"{hour:02d}:{minute:02d}"

        m_rel = RELATIVE_COLON_RE.match(value)
        if m_rel:
            minutes = int(m_rel.group(1))
            seconds = int(m_rel.group(2))
            if seconds > 59:
                raise ValueError("Relative time must be M:SS with 00-59 seconds.")
            total_seconds = minutes * 60 + seconds
            if total_seconds <= 0:
                raise ValueError("Relative time must be greater than 0.")
            return now + dt.timedelta(seconds=total_seconds), "relative", f"{minutes}:{seconds:02d}"

        if MINUTES_ONLY_RE.match(value):
            minutes = int(value)
            if minutes <= 0:
                raise ValueError("Minutes must be greater than 0.")
            return now + dt.timedelta(minutes=minutes), "relative", f"{minutes}:00"

        raise ValueError("Invalid format. Use HH:MM, M:SS, or minutes only.")

    def _create_row(self, item: TimerItem) -> None:
        row = ttk.Frame(self.rows_container, padding=(4, 4))
        for idx, min_w in enumerate(COLUMN_WIDTHS):
            row.grid_columnconfigure(idx, minsize=min_w)

        item.row_frame = row
        item.label_var = tk.StringVar(value=item.label)
        item.remaining_var = tk.StringVar(value="--:--")
        item.end_var = tk.StringVar(value=self._format_end_time(item.end_time))
        item.state_var = tk.StringVar(value=item.state)

        label_entry = ttk.Entry(row, textvariable=item.label_var)
        label_entry.grid(row=0, column=0, sticky="we", padx=4)
        label_entry.bind("<FocusOut>", lambda _e, tid=item.timer_id: self._sync_label(tid))
        label_entry.bind("<Return>", lambda _e, tid=item.timer_id: self._sync_label(tid))

        tk.Button(
            row,
            textvariable=item.remaining_var,
            font=(self.ui_font_family, 24, "bold"),
            bg="#efefef",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=lambda tid=item.timer_id: self.open_reset_dialog(tid, "relative"),
        ).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(
            row,
            textvariable=item.end_var,
            command=lambda tid=item.timer_id: self.open_reset_dialog(tid, "absolute"),
        ).grid(row=0, column=2, sticky="w", padx=4)
        ttk.Label(row, textvariable=item.state_var).grid(row=0, column=3, sticky="w", padx=4)

        btns = ttk.Frame(row)
        btns.grid(row=0, column=4, sticky="w", padx=4)

        grip = ttk.Label(btns, text="⇅", cursor="fleur")
        grip.pack(side="left", padx=(0, 8))
        grip.bind("<ButtonPress-1>", lambda e, tid=item.timer_id: self._start_drag(e, tid))
        grip.bind("<B1-Motion>", self._drag_timer)
        grip.bind("<ButtonRelease-1>", self._end_drag)

        ttk.Button(btns, text="Start", command=lambda tid=item.timer_id: self.start_timer(tid)).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Pause", command=lambda tid=item.timer_id: self.pause_timer(tid)).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Remove", command=lambda tid=item.timer_id: self.cancel_timer(tid)).pack(side="left")

    def _repack_rows(self) -> None:
        for timer_id in self.timer_order:
            item = self.timers.get(timer_id)
            if not item or not item.row_frame or not item.row_frame.winfo_exists():
                continue
            item.row_frame.pack_forget()
            item.row_frame.pack(fill="x")
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _start_drag(self, _event: tk.Event, timer_id: str) -> None:
        if timer_id in self.timer_order:
            self.dragging_timer_id = timer_id

    def _drag_timer(self, event: tk.Event) -> None:
        timer_id = self.dragging_timer_id
        if not timer_id or timer_id not in self.timer_order:
            return

        pointer_y = event.widget.winfo_pointery() - self.rows_container.winfo_rooty()
        target_index = len(self.timer_order)
        for idx, candidate_id in enumerate(self.timer_order):
            candidate = self.timers.get(candidate_id)
            if not candidate or not candidate.row_frame or not candidate.row_frame.winfo_exists():
                continue
            center_y = candidate.row_frame.winfo_y() + (candidate.row_frame.winfo_height() // 2)
            if pointer_y < center_y:
                target_index = idx
                break

        current_index = self.timer_order.index(timer_id)
        if target_index == current_index:
            return

        self.timer_order.pop(current_index)
        if target_index > current_index:
            target_index -= 1
        self.timer_order.insert(target_index, timer_id)
        self._repack_rows()
        self._mark_dirty()

    def _end_drag(self, _event: tk.Event) -> None:
        self.dragging_timer_id = None

    def _sync_label(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or not item.label_var:
            return
        text = item.label_var.get().strip()
        if text and text != item.label:
            item.label = text
            self._mark_dirty()
        item.label_var.set(item.label)

    def start_timer(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item:
            return

        now = dt.datetime.now()
        changed = False
        if item.state == "Finished":
            restarted = self._restart_finished_timer(item)
            changed = restarted
        elif item.state == "Paused":
            if item.paused_remaining <= 0:
                item.state = "Finished"
                item.finished_at = now
                changed = True
            else:
                item.end_time = now + dt.timedelta(seconds=item.paused_remaining)
                item.state = "Running"
                changed = True

        if item.state_var:
            item.state_var.set(item.state)
        if item.end_var:
            item.end_var.set(self._format_end_time(item.end_time))
        if changed:
            self._mark_dirty()

    def _restart_finished_timer(self, item: TimerItem) -> bool:
        preset_value = item.preset_relative if item.input_mode == "relative" else item.preset_absolute
        if not preset_value:
            return False

        try:
            end_time, _, _ = self._parse_time_input(preset_value)
        except ValueError:
            return False

        item.end_time = end_time
        item.paused_remaining = 0
        item.state = "Running"
        item.finished_at = None
        item.alerted = False
        return True

    def pause_timer(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or item.state != "Running" or not item.end_time:
            return

        now = dt.datetime.now()
        remaining = max(0, int((item.end_time - now).total_seconds()))
        item.paused_remaining = remaining
        item.end_time = None
        item.state = "Paused"
        self._mark_dirty()

        if item.state_var:
            item.state_var.set(item.state)
        if item.end_var:
            item.end_var.set("--:--")

    def cancel_timer(self, timer_id: str) -> None:
        item = self.timers.pop(timer_id, None)
        if not item:
            return

        if timer_id in self.timer_order:
            self.timer_order.remove(timer_id)

        if item.row_frame and item.row_frame.winfo_exists():
            item.row_frame.destroy()

        if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
            self._dismiss_alert()

        self.pending_alerts = [t for t in self.pending_alerts if t.timer_id != timer_id]
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._mark_dirty()

        if self.reset_target_timer_id == timer_id:
            self._close_reset_dialog()

    def _tick(self) -> None:
        now = dt.datetime.now()

        for item in list(self.timers.values()):
            self._sync_label(item.timer_id)
            if item.state == "Running" and item.end_time:
                remaining = (item.end_time - now).total_seconds()
                if remaining <= 0:
                    item.state = "Finished"
                    item.finished_at = now
                    if not item.alerted:
                        self.pending_alerts.append(item)
                        item.alerted = True
                    self._mark_dirty()
                    remaining = 0
                display_remaining = int(max(0, remaining))
            elif item.state == "Paused":
                display_remaining = max(0, item.paused_remaining)
            else:
                display_remaining = 0

            if item.remaining_var:
                if item.state == "Finished" and item.input_mode == "relative" and item.preset_relative:
                    item.remaining_var.set(item.preset_relative)
                else:
                    item.remaining_var.set(self._format_remaining(display_remaining))
            if item.state_var:
                item.state_var.set(item.state)
            if item.end_var:
                if item.state == "Finished" and item.input_mode == "absolute" and item.preset_absolute:
                    item.end_var.set(item.preset_absolute)
                else:
                    item.end_var.set(self._format_end_time(item.end_time))

        if not self.current_alert_window and self.pending_alerts:
            next_item = self.pending_alerts.pop(0)
            self._show_fullscreen_alert(next_item)

        self.root.after(200, self._tick)

    def _show_fullscreen_alert(self, item: TimerItem) -> None:
        if self.current_alert_window and self.current_alert_window.winfo_exists():
            return

        self.current_alert_timer = item
        alert = tk.Toplevel(self.root)
        self.current_alert_window = alert

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        band_h = 280
        pos_y = max(0, (screen_h - band_h) // 2)

        alert.overrideredirect(True)
        alert.geometry(f"{screen_w}x{band_h}+0+{pos_y}")
        alert.configure(bg="#202020")
        alert.attributes("-topmost", True)
        alert.attributes("-alpha", 0.94)
        alert.lift()
        alert.focus_force()

        alert.bind("<Button-1>", lambda _e: self._dismiss_alert())
        esc_id = self.root.bind("<Escape>", lambda _e: self._dismiss_alert(), add="+")
        ret_id = self.root.bind("<Return>", lambda _e: self._dismiss_alert(), add="+")
        self.alert_key_bindings = [("<Escape>", esc_id), ("<Return>", ret_id)]

        finish_at = item.finished_at or dt.datetime.now()

        tk.Label(
            alert,
            text="Time is up!",
            fg="#ffffff",
            bg="#202020",
            font=(self.ui_font_family, 58, "bold"),
        ).pack(pady=(20, 4))

        tk.Label(
            alert,
            text=f"Label: {item.label}",
            fg="#ffffff",
            bg="#202020",
            font=(self.ui_font_family, 28),
        ).pack(pady=2)

        tk.Label(
            alert,
            text=f"Finished at: {finish_at.strftime('%H:%M')}",
            fg="#ffffff",
            bg="#202020",
            font=(self.ui_font_family, 24),
        ).pack(pady=2)

        tk.Label(
            alert,
            text="Press ESC / Enter or Click to dismiss",
            fg="#cccccc",
            bg="#202020",
            font=(self.ui_font_family, 14),
        ).pack(pady=(8, 0))

        self._reinforce_alert_focus()

    def _reinforce_alert_focus(self) -> None:
        alert = self.current_alert_window
        if not alert or not alert.winfo_exists():
            return

        try:
            alert.lift()
            alert.attributes("-topmost", True)
            alert.focus_force()
        except tk.TclError:
            return

        alert.after(300, self._reinforce_alert_focus)

    def _dismiss_alert(self) -> None:
        alert = self.current_alert_window
        self.current_alert_window = None
        self.current_alert_timer = None

        if alert and alert.winfo_exists():
            alert.destroy()

        for sequence, bind_id in self.alert_key_bindings:
            if bind_id:
                self.root.unbind(sequence, bind_id)
        self.alert_key_bindings = []
        self.root.after(10, self._restore_main_focus)

    def _restore_main_focus(self) -> None:
        try:
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            return

        if self.add_label_entry and self.add_label_entry.winfo_exists():
            try:
                self.add_label_entry.focus_set()
            except tk.TclError:
                pass

    def open_reset_dialog(self, timer_id: str, source_mode: str) -> None:
        item = self.timers.get(timer_id)
        if not item:
            return

        if self.reset_dialog and self.reset_dialog.winfo_exists():
            self.reset_dialog.destroy()

        self.reset_target_timer_id = timer_id
        self.reset_source_mode = source_mode
        self.reset_input_var.set(self._build_reset_initial_value(item, source_mode))

        dlg = tk.Toplevel(self.root)
        self.reset_dialog = dlg
        dlg.title(f"Reset Timer: {item.label}")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"Label: {item.label}").pack(anchor="w")
        ttk.Label(frame, text=f"Editing: {'Remaining' if source_mode == 'relative' else 'End Time'}").pack(anchor="w", pady=(4, 0))
        ttk.Label(frame, text="New time (HH:MM / M:SS / Minutes)").pack(anchor="w", pady=(8, 2))
        entry = ttk.Entry(frame, textvariable=self.reset_input_var, width=24)
        entry.pack(anchor="w")
        entry.focus_set()

        msg = ttk.Label(frame, text="HH:MM は End Time 再設定、M:SS/分 は Remaining 再設定")
        msg.pack(anchor="w", pady=(8, 10))

        btns = ttk.Frame(frame)
        btns.pack(anchor="e")
        ttk.Button(btns, text="Apply", command=self.apply_reset_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Close", command=self._close_reset_dialog).pack(side="left")

        entry.bind("<Return>", lambda _e: self.apply_reset_dialog())
        dlg.bind("<Escape>", lambda _e: self._close_reset_dialog())

    def apply_reset_dialog(self) -> None:
        if not self.reset_target_timer_id:
            return
        item = self.timers.get(self.reset_target_timer_id)
        if not item:
            self._close_reset_dialog()
            return

        value = self.reset_input_var.get().strip()
        if not value:
            self.error_var.set("Reset time is required.")
            return

        try:
            end_time, parsed_mode, normalized_value = self._parse_time_input(value)
        except ValueError as exc:
            self.error_var.set(str(exc))
            return

        self.error_var.set("")
        item.end_time = end_time
        item.paused_remaining = 0
        item.state = "Running"
        item.finished_at = None
        item.alerted = False
        item.input_mode = parsed_mode
        if parsed_mode == "absolute":
            item.preset_absolute = normalized_value
            item.preset_relative = None
        else:
            item.preset_relative = normalized_value
            item.preset_absolute = None
        if item.state_var:
            item.state_var.set(item.state)
        if item.end_var:
            item.end_var.set(self._format_end_time(item.end_time))
        self._mark_dirty()
        self._close_reset_dialog()

    def _close_reset_dialog(self) -> None:
        dlg = self.reset_dialog
        self.reset_dialog = None
        self.reset_target_timer_id = None
        self.reset_source_mode = None
        if dlg and dlg.winfo_exists():
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            dlg.destroy()

    def _build_reset_initial_value(self, item: TimerItem, source_mode: str) -> str:
        if source_mode == "absolute":
            if item.preset_absolute:
                return item.preset_absolute
            if item.end_time:
                return item.end_time.strftime("%H:%M")
            return dt.datetime.now().strftime("%H:%M")

        if item.preset_relative:
            return item.preset_relative
        if item.state == "Paused":
            return self._format_relative_input(item.paused_remaining)
        if item.state == "Running" and item.end_time:
            remaining = max(0, int((item.end_time - dt.datetime.now()).total_seconds()))
            return self._format_relative_input(remaining)
        return "0:30"

    def _mark_dirty(self) -> None:
        self.state_dirty = True

    def _autosave_loop(self) -> None:
        if self.state_dirty:
            self._save_state()
        self.root.after(1000, self._autosave_loop)

    def _serialize_timer(self, item: TimerItem) -> dict[str, object]:
        return {
            "timer_id": item.timer_id,
            "label": item.label,
            "state": item.state,
            "end_time": item.end_time.isoformat() if item.end_time else None,
            "paused_remaining": item.paused_remaining,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            "alerted": item.alerted,
            "input_mode": item.input_mode,
            "preset_relative": item.preset_relative,
            "preset_absolute": item.preset_absolute,
        }

    def _save_state(self) -> None:
        payload = {
            "timers": [
                self._serialize_timer(self.timers[timer_id])
                for timer_id in self.timer_order
                if timer_id in self.timers
            ]
        }
        tmp_path = self.state_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(self.state_path)
            self.state_dirty = False
        except OSError as exc:
            self.error_var.set(f"Failed to save state: {exc}")

    @staticmethod
    def _parse_iso_dt(value: object) -> dt.datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return None

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        timers = payload.get("timers")
        if not isinstance(timers, list):
            return

        for entry in timers:
            if not isinstance(entry, dict):
                continue
            timer_id = entry.get("timer_id")
            if not isinstance(timer_id, str) or not timer_id:
                timer_id = str(uuid4())
            if timer_id in self.timers:
                timer_id = str(uuid4())

            label = entry.get("label")
            state = entry.get("state")
            if not isinstance(label, str) or not isinstance(state, str):
                continue

            item = TimerItem(
                timer_id=timer_id,
                label=label,
                state=state if state in {"Running", "Paused", "Finished"} else "Paused",
                end_time=self._parse_iso_dt(entry.get("end_time")),
                paused_remaining=int(entry.get("paused_remaining", 0) or 0),
                finished_at=self._parse_iso_dt(entry.get("finished_at")),
                alerted=bool(entry.get("alerted", False)),
                input_mode=entry.get("input_mode", "relative") if entry.get("input_mode") in {"relative", "absolute"} else "relative",
                preset_relative=entry.get("preset_relative") if isinstance(entry.get("preset_relative"), str) else None,
                preset_absolute=entry.get("preset_absolute") if isinstance(entry.get("preset_absolute"), str) else None,
            )

            # Guard against inconsistent state.
            if item.state == "Running" and item.end_time is None:
                item.state = "Paused"
                item.paused_remaining = max(0, item.paused_remaining)

            self.timers[item.timer_id] = item
            self.timer_order.append(item.timer_id)
            self._create_row(item)

        self._repack_rows()

        self.state_dirty = False

    def _on_close(self) -> None:
        if self.state_dirty:
            self._save_state()
        self.root.destroy()

    @staticmethod
    def _format_relative_input(total_seconds: int) -> str:
        minutes, seconds = divmod(max(0, total_seconds), 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _format_remaining(total_seconds: int) -> str:
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _format_end_time(end_time: dt.datetime | None) -> str:
        if end_time is None:
            return "--:--"
        return end_time.strftime("%H:%M")


def main() -> None:
    root = tk.Tk()
    app = TimerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
