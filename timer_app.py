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
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from uuid import uuid4


ABSOLUTE_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
RELATIVE_COLON_RE = re.compile(r"^(\d{1,3}):(\d{1,2})$")
MINUTES_ONLY_RE = re.compile(r"^\d+$")
COLUMN_WIDTHS = [248, 184, 126, 100]


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
    input_mode: str  # relative or absolute
    state: str = "Running"  # Running, Paused, Stopped, Finished
    target_epoch: float | None = None  # absolute source of truth
    target_hhmm: str | None = None
    remaining_seconds: float = 0.0  # relative source of truth
    initial_seconds: int = 0
    last_tick_epoch: float | None = None
    finished_at: dt.datetime | None = None
    alerted: bool = False

    row_frame: ttk.Frame | None = field(default=None, repr=False)
    label_var: tk.StringVar | None = field(default=None, repr=False)
    remaining_var: tk.StringVar | None = field(default=None, repr=False)
    end_var: tk.StringVar | None = field(default=None, repr=False)
    drag_handle: ttk.Label | None = field(default=None, repr=False)
    remaining_btn: tk.Button | None = field(default=None, repr=False)
    end_btn: tk.Button | None = field(default=None, repr=False)
    play_pause_btn: tk.Button | None = field(default=None, repr=False)
    stop_btn: tk.Button | None = field(default=None, repr=False)
    delete_btn: tk.Button | None = field(default=None, repr=False)


class TimerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MultiDeadline Timer")
        self.root.geometry("900x760")
        self.root.minsize(800, 640)
        self.ui_font_family = pick_ui_font_family(self.root)
        self.root.option_add("*Font", f"{{{self.ui_font_family}}} 12")
        self.state_path = Path(__file__).with_name("timer_state.json")
        self.state_dirty = False

        self.timers: dict[str, TimerItem] = {}
        self.timer_order: list[str] = []
        self.trash_timers: dict[str, TimerItem] = {}
        self.trash_order: list[str] = []
        self.showing_trash = False

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
        self.drop_effect_job: str | None = None
        self.trash_toggle_btn: ttk.Button | None = None
        self.back_main_btn: ttk.Button | None = None
        self.empty_trash_btn: ttk.Button | None = None
        self.main_controls_frame: ttk.Frame | None = None
        self.trash_controls_frame: ttk.Frame | None = None
        self.error_label_widget: ttk.Label | None = None

        self.input_var = tk.StringVar()
        self.label_input_var = tk.StringVar(value="Timer")
        self.error_var = tk.StringVar(value="")

        self._build_ui()
        self._load_state()
        self._render_rows()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._autosave_loop)
        self._tick()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=10)
        container.pack(fill="both", expand=True)

        add_frame = ttk.Frame(container)
        add_frame.pack(fill="x", pady=(0, 6))
        self.main_controls_frame = add_frame

        ttk.Label(add_frame, text="Label").pack(side="left")
        label_entry = ttk.Entry(add_frame, textvariable=self.label_input_var, width=12)
        label_entry.pack(side="left", padx=(6, 10))
        self.add_label_entry = label_entry

        ttk.Label(add_frame, text="Time (HH:MM / M:SS / Minutes)").pack(side="left")
        entry = ttk.Entry(add_frame, textvariable=self.input_var, width=13)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _: self.add_timer())
        self.add_time_entry = entry

        ttk.Button(add_frame, text="Add", command=self.add_timer).pack(side="left", padx=(4, 6))

        self.trash_toggle_btn = ttk.Button(add_frame, text="🗑 Trash", command=self.toggle_trash_view)
        self.trash_toggle_btn.pack(side="left")

        trash_frame = ttk.Frame(container)
        self.trash_controls_frame = trash_frame
        self.back_main_btn = ttk.Button(trash_frame, text="← Mainに戻る", command=self.toggle_trash_view)
        self.back_main_btn.pack(side="left")
        self.empty_trash_btn = ttk.Button(trash_frame, text="Empty Trash", command=self.empty_trash)
        self.empty_trash_btn.pack(side="left", padx=(6, 0))

        error_label = ttk.Label(container, textvariable=self.error_var, foreground="red")
        error_label.pack(fill="x", pady=(0, 6))
        self.error_label_widget = error_label

        header = ttk.Frame(container)
        header.pack(fill="x")
        for idx, min_w in enumerate(COLUMN_WIDTHS):
            header.grid_columnconfigure(idx, minsize=min_w)
        ttk.Label(header, text="Label").grid(row=0, column=0, sticky="w", padx=(36, 4))
        rem_header = ttk.Frame(header)
        rem_header.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(rem_header, text="Remaining").pack(anchor="w")
        ttk.Label(rem_header, text="(Click to edit)", font=(self.ui_font_family, 9)).pack(anchor="w")

        end_header = ttk.Frame(header)
        end_header.grid(row=0, column=2, sticky="w", padx=4)
        ttk.Label(end_header, text="End Time").pack(anchor="w")
        ttk.Label(end_header, text="(Click to edit)", font=(self.ui_font_family, 9)).pack(anchor="w")
        ttk.Label(header, text="Actions").grid(row=0, column=3, sticky="w", padx=4)

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
            parsed = self._parse_time_input(raw_time)
        except ValueError as exc:
            self.error_var.set(str(exc))
            return

        now_epoch = time.time()
        self.error_var.set("")
        item = TimerItem(timer_id=str(uuid4()), label=label, input_mode=parsed["mode"])

        if parsed["mode"] == "absolute":
            item.target_epoch = parsed["target_epoch"]
            item.target_hhmm = parsed["normalized"]
            item.state = "Running"
        else:
            seconds = int(parsed["seconds"])
            item.initial_seconds = seconds
            item.remaining_seconds = float(seconds)
            item.last_tick_epoch = now_epoch
            item.state = "Running"

        self.timers[item.timer_id] = item
        self.timer_order.append(item.timer_id)
        self.input_var.set("")
        self._render_rows()
        self._mark_dirty()

    def _parse_time_input(self, value: str) -> dict[str, object]:
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
            return {
                "mode": "absolute",
                "target_epoch": target.timestamp(),
                "normalized": f"{hour:02d}:{minute:02d}",
            }

        m_rel = RELATIVE_COLON_RE.match(value)
        if m_rel:
            minutes = int(m_rel.group(1))
            seconds = int(m_rel.group(2))
            if seconds > 59:
                raise ValueError("Relative time must be M:SS with 00-59 seconds.")
            total_seconds = minutes * 60 + seconds
            if total_seconds <= 0:
                raise ValueError("Relative time must be greater than 0.")
            return {
                "mode": "relative",
                "seconds": total_seconds,
                "normalized": f"{minutes}:{seconds:02d}",
            }

        if MINUTES_ONLY_RE.match(value):
            minutes = int(value)
            if minutes <= 0:
                raise ValueError("Minutes must be greater than 0.")
            return {
                "mode": "relative",
                "seconds": minutes * 60,
                "normalized": f"{minutes}:00",
            }

        raise ValueError("Invalid format. Use HH:MM, M:SS, or minutes only.")

    def toggle_trash_view(self) -> None:
        self.showing_trash = not self.showing_trash
        self._render_rows()

    def _render_rows(self) -> None:
        for tid in self.timer_order:
            self._sync_label(tid)
        for item in list(self.timers.values()) + list(self.trash_timers.values()):
            self._clear_widget_refs(item)

        for child in self.rows_container.winfo_children():
            child.destroy()

        if self.showing_trash:
            if self.main_controls_frame and self.main_controls_frame.winfo_manager():
                self.main_controls_frame.pack_forget()
            if self.trash_controls_frame and not self.trash_controls_frame.winfo_manager():
                if self.error_label_widget and self.error_label_widget.winfo_exists():
                    self.trash_controls_frame.pack(fill="x", pady=(0, 6), before=self.error_label_widget)
                else:
                    self.trash_controls_frame.pack(fill="x", pady=(0, 6))
            if self.trash_toggle_btn:
                self.trash_toggle_btn.configure(text="🗑 Trash")
            if self.empty_trash_btn:
                self.empty_trash_btn.state(["!disabled"])
            for tid in self.trash_order:
                item = self.trash_timers.get(tid)
                if item:
                    self._create_trash_row(item)
        else:
            if self.trash_controls_frame and self.trash_controls_frame.winfo_manager():
                self.trash_controls_frame.pack_forget()
            if self.main_controls_frame and not self.main_controls_frame.winfo_manager():
                if self.error_label_widget and self.error_label_widget.winfo_exists():
                    self.main_controls_frame.pack(fill="x", pady=(0, 6), before=self.error_label_widget)
                else:
                    self.main_controls_frame.pack(fill="x", pady=(0, 6))
            if self.trash_toggle_btn:
                self.trash_toggle_btn.configure(text="🗑 Trash")
            for tid in self.timer_order:
                item = self.timers.get(tid)
                if item:
                    self._create_row(item)

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    @staticmethod
    def _clear_widget_refs(item: TimerItem) -> None:
        item.row_frame = None
        item.label_var = None
        item.remaining_var = None
        item.end_var = None
        item.drag_handle = None
        item.remaining_btn = None
        item.end_btn = None
        item.play_pause_btn = None
        item.stop_btn = None
        item.delete_btn = None

    def _create_row(self, item: TimerItem) -> None:
        row = ttk.Frame(self.rows_container, padding=(4, 4))
        row.pack(fill="x")
        for idx, min_w in enumerate(COLUMN_WIDTHS):
            row.grid_columnconfigure(idx, minsize=min_w)

        item.row_frame = row
        item.label_var = tk.StringVar(value=item.label)
        item.remaining_var = tk.StringVar(value="--:--")
        item.end_var = tk.StringVar(value="--:--")

        label_cell = ttk.Frame(row)
        label_cell.grid(row=0, column=0, sticky="we", padx=4)
        label_cell.columnconfigure(1, weight=0)

        drag_handle = ttk.Label(label_cell, text="::", cursor="fleur", width=3, anchor="center")
        drag_handle.grid(row=0, column=0, padx=(0, 4))
        item.drag_handle = drag_handle
        self._bind_drag_events(drag_handle, item.timer_id)

        label_entry = ttk.Entry(label_cell, textvariable=item.label_var, width=12)
        label_entry.grid(row=0, column=1, sticky="w")
        label_entry.bind("<FocusOut>", lambda _e, tid=item.timer_id: self._sync_label(tid))
        label_entry.bind("<Return>", lambda _e, tid=item.timer_id: self._sync_label(tid))

        remaining_btn = tk.Button(
            row,
            textvariable=item.remaining_var,
            font=(self.ui_font_family, 20, "bold"),
            bg="#efefef",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=lambda tid=item.timer_id: self.open_reset_dialog(tid, "relative"),
            padx=4,
            pady=2,
        )
        remaining_btn.grid(row=0, column=1, sticky="w", padx=4)
        item.remaining_btn = remaining_btn

        end_btn = tk.Button(
            row,
            textvariable=item.end_var,
            font=(self.ui_font_family, 12),
            bg="#efefef",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=lambda tid=item.timer_id: self.open_reset_dialog(tid, "absolute"),
            padx=4,
            pady=2,
        )
        end_btn.grid(row=0, column=2, sticky="w", padx=4)
        item.end_btn = end_btn

        btns = ttk.Frame(row)
        btns.grid(row=0, column=3, sticky="w", padx=4)
        btns.grid_rowconfigure(0, weight=1)
        btns.grid_rowconfigure(1, weight=1)

        stack = ttk.Frame(btns)
        stack.grid(row=0, column=0, rowspan=2, sticky="ns")

        play_pause_btn = tk.Button(
            stack,
            text="▶",
            width=2,
            command=lambda tid=item.timer_id: self.toggle_play_pause(tid),
            relief="groove",
            padx=0,
            pady=0,
        )
        play_pause_btn.pack(side="top", pady=(0, 3))
        item.play_pause_btn = play_pause_btn

        stop_btn = tk.Button(
            stack,
            text="⏹",
            width=2,
            command=lambda tid=item.timer_id: self.stop_timer(tid),
            relief="groove",
            padx=0,
            pady=0,
        )
        stop_btn.pack(side="top")
        item.stop_btn = stop_btn

        delete_btn = tk.Button(
            btns,
            text="ⓧ",
            width=1,
            command=lambda tid=item.timer_id: self.move_to_trash(tid),
            relief="groove",
            font=(self.ui_font_family, 10),
            padx=0,
            pady=0,
        )
        delete_btn.grid(row=0, column=1, rowspan=2, sticky="ns", padx=(10, 0))
        item.delete_btn = delete_btn

        self._refresh_row(item)

    def _create_trash_row(self, item: TimerItem) -> None:
        row = ttk.Frame(self.rows_container, padding=(4, 4))
        row.pack(fill="x")
        for idx, min_w in enumerate(COLUMN_WIDTHS):
            row.grid_columnconfigure(idx, minsize=min_w)

        ttk.Label(row, text=item.label).grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(row, text=self._display_remaining(item)).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(row, text=self._display_end(item)).grid(row=0, column=2, sticky="w", padx=4)

        actions = ttk.Frame(row)
        actions.grid(row=0, column=3, sticky="w", padx=4)
        tk.Button(
            actions,
            text="↩",
            width=2,
            command=lambda tid=item.timer_id: self.restore_from_trash(tid),
            relief="groove",
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            actions,
            text="🗑",
            width=2,
            command=lambda tid=item.timer_id: self.delete_permanently(tid),
            relief="groove",
        ).pack(side="left")

    def _bind_drag_events(self, widget: tk.Widget, timer_id: str) -> None:
        widget.bind("<ButtonPress-1>", lambda event, tid=timer_id: self._on_drag_start(event, tid))
        widget.bind("<B1-Motion>", self._on_drag_motion)
        widget.bind("<ButtonRelease-1>", self._on_drag_end)

    def _on_drag_start(self, _event: tk.Event, timer_id: str) -> None:
        if self.showing_trash:
            return
        self.dragging_timer_id = timer_id
        item = self.timers.get(timer_id)
        if item:
            self._set_row_lifted(item, True)

    def _on_drag_motion(self, event: tk.Event) -> None:
        if self.showing_trash:
            return
        timer_id = self.dragging_timer_id
        if not timer_id or timer_id not in self.timer_order:
            return
        target_index = self._target_index_from_pointer(event.y_root)
        self._move_timer_to_index(timer_id, target_index)

    def _on_drag_end(self, _event: tk.Event) -> None:
        timer_id = self.dragging_timer_id
        self.dragging_timer_id = None
        if not timer_id:
            return
        item = self.timers.get(timer_id)
        if item:
            self._play_drop_effect(item)

    def _target_index_from_pointer(self, y_root: int) -> int:
        for idx, tid in enumerate(self.timer_order):
            item = self.timers.get(tid)
            row = item.row_frame if item else None
            if not row or not row.winfo_exists():
                continue
            midpoint = row.winfo_rooty() + (row.winfo_height() // 2)
            if y_root < midpoint:
                return idx
        return len(self.timer_order)

    def _move_timer_to_index(self, timer_id: str, target_index: int) -> None:
        old_index = self.timer_order.index(timer_id)
        if old_index == target_index or old_index + 1 == target_index:
            return

        self.timer_order.pop(old_index)
        if target_index > old_index:
            target_index -= 1
        target_index = max(0, min(target_index, len(self.timer_order)))
        self.timer_order.insert(target_index, timer_id)
        self._repack_rows_by_order()
        self._mark_dirty()

    def _repack_rows_by_order(self) -> None:
        for tid in self.timer_order:
            item = self.timers.get(tid)
            row = item.row_frame if item else None
            if not row or not row.winfo_exists():
                continue
            row.pack_forget()
            row.pack(fill="x")

    def _set_row_lifted(self, item: TimerItem, lifted: bool) -> None:
        row = item.row_frame
        if not row or not row.winfo_exists():
            return
        if lifted:
            row.configure(relief="raised", borderwidth=2, padding=(8, 8))
            if item.drag_handle and item.drag_handle.winfo_exists():
                item.drag_handle.configure(text="[::]", cursor="fleur")
        else:
            row.configure(relief="flat", borderwidth=0, padding=(4, 4))
            if item.drag_handle and item.drag_handle.winfo_exists():
                item.drag_handle.configure(text="::", cursor="fleur")

    def _play_drop_effect(self, item: TimerItem) -> None:
        row = item.row_frame
        if not row or not row.winfo_exists():
            return

        if self.drop_effect_job:
            try:
                self.root.after_cancel(self.drop_effect_job)
            except tk.TclError:
                pass
            self.drop_effect_job = None

        row.configure(relief="sunken", borderwidth=2, padding=(8, 6))
        if item.drag_handle and item.drag_handle.winfo_exists():
            item.drag_handle.configure(text="::")
        self.drop_effect_job = self.root.after(120, lambda: self._clear_drop_effect(item.timer_id))

    def _clear_drop_effect(self, timer_id: str) -> None:
        self.drop_effect_job = None
        item = self.timers.get(timer_id)
        if not item:
            return
        self._set_row_lifted(item, False)

    def _sync_label(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or not item.label_var:
            return
        text = item.label_var.get().strip()
        if text and text != item.label:
            item.label = text
            self._mark_dirty()
        item.label_var.set(item.label)

    def toggle_play_pause(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item:
            return

        now_epoch = time.time()

        if item.state == "Running":
            if item.input_mode == "relative":
                item.state = "Paused"
                item.last_tick_epoch = None
                self._mark_dirty()
            return

        if item.input_mode == "absolute":
            if item.target_epoch is None:
                return
            if item.state == "Finished":
                item.target_epoch = self._next_absolute_epoch(item)
            item.state = "Running"
            item.finished_at = None
            item.alerted = False
            self._mark_dirty()
        else:
            if item.state == "Finished" or item.remaining_seconds <= 0:
                item.remaining_seconds = float(item.initial_seconds)
            item.state = "Running"
            item.last_tick_epoch = now_epoch
            item.finished_at = None
            item.alerted = False
            self._mark_dirty()

        self._refresh_row(item)

    def stop_timer(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item:
            return

        if item.input_mode == "absolute":
            if item.state == "Finished":
                return
            item.state = "Stopped"
            item.finished_at = None
            item.last_tick_epoch = None
            self.pending_alerts = [t for t in self.pending_alerts if t.timer_id != timer_id]
            if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
                self._dismiss_alert()
            self._mark_dirty()
        else:
            if item.state == "Finished":
                return
            item.state = "Stopped"
            item.remaining_seconds = float(item.initial_seconds)
            item.last_tick_epoch = None
            item.finished_at = None
            item.alerted = False
            self.pending_alerts = [t for t in self.pending_alerts if t.timer_id != timer_id]
            if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
                self._dismiss_alert()
            self._mark_dirty()

        self._refresh_row(item)

    def move_to_trash(self, timer_id: str) -> None:
        item = self.timers.pop(timer_id, None)
        if not item:
            return
        self.timer_order = [tid for tid in self.timer_order if tid != timer_id]
        self.trash_timers[item.timer_id] = item
        self.trash_order.append(item.timer_id)

        if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
            self._dismiss_alert()
        self.pending_alerts = [t for t in self.pending_alerts if t.timer_id != timer_id]

        if self.reset_target_timer_id == timer_id:
            self._close_reset_dialog()

        self._render_rows()
        self._mark_dirty()

    def restore_from_trash(self, timer_id: str) -> None:
        item = self.trash_timers.pop(timer_id, None)
        if not item:
            return
        self.trash_order = [tid for tid in self.trash_order if tid != timer_id]
        self.timers[item.timer_id] = item
        self.timer_order.append(item.timer_id)
        self._render_rows()
        self._mark_dirty()

    def delete_permanently(self, timer_id: str) -> None:
        removed = self.trash_timers.pop(timer_id, None)
        if not removed:
            return
        self.trash_order = [tid for tid in self.trash_order if tid != timer_id]
        self._render_rows()
        self._mark_dirty()

    def empty_trash(self) -> None:
        if not self.trash_order:
            return
        self.trash_timers.clear()
        self.trash_order.clear()
        self._render_rows()
        self._mark_dirty()

    def _tick(self) -> None:
        now_epoch = time.time()
        now_dt = dt.datetime.now()

        for tid in list(self.timer_order):
            item = self.timers.get(tid)
            if not item:
                continue
            self._sync_label(item.timer_id)

            if item.state == "Running":
                if item.input_mode == "absolute":
                    remaining = self._absolute_remaining(item, now_epoch)
                    if remaining <= 0:
                        item.state = "Finished"
                        item.finished_at = now_dt
                        item.alerted = True
                        self.pending_alerts.append(item)
                        self._mark_dirty()
                else:
                    if item.last_tick_epoch is None:
                        item.last_tick_epoch = now_epoch
                    delta = max(0.0, now_epoch - item.last_tick_epoch)
                    if delta > 0:
                        item.remaining_seconds = max(0.0, item.remaining_seconds - delta)
                        item.last_tick_epoch = now_epoch
                    if item.remaining_seconds <= 0:
                        item.remaining_seconds = 0.0
                        item.state = "Finished"
                        item.finished_at = now_dt
                        item.last_tick_epoch = None
                        if not item.alerted:
                            item.alerted = True
                            self.pending_alerts.append(item)
                        self._mark_dirty()

            self._refresh_row(item)

        if not self.current_alert_window and self.pending_alerts:
            next_item = self.pending_alerts.pop(0)
            if next_item.timer_id in self.timers and next_item.state == "Finished":
                self._show_fullscreen_alert(next_item)

        self.root.after(200, self._tick)

    def _next_absolute_epoch(self, item: TimerItem) -> float:
        now = dt.datetime.now()
        hhmm = item.target_hhmm
        if hhmm and ABSOLUTE_TIME_RE.match(hhmm):
            hour, minute = map(int, hhmm.split(":"))
        elif item.target_epoch is not None:
            base = dt.datetime.fromtimestamp(item.target_epoch)
            hour, minute = base.hour, base.minute
        else:
            hour, minute = now.hour, now.minute

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        item.target_hhmm = f"{hour:02d}:{minute:02d}"
        return target.timestamp()

    def _absolute_remaining(self, item: TimerItem, now_epoch: float | None = None) -> int:
        if item.target_epoch is None:
            return 0
        ref = now_epoch if now_epoch is not None else time.time()
        return max(0, int(item.target_epoch - ref))

    def _display_remaining(self, item: TimerItem) -> str:
        if item.input_mode == "absolute":
            if item.state == "Stopped":
                return "--:--"
            if item.state == "Finished":
                if self._is_alert_visible_or_pending(item):
                    return "00:00"
                return "--:--"
            return self._format_remaining(self._absolute_remaining(item))

        if item.state == "Finished":
            if self._is_alert_visible_or_pending(item):
                return "00:00"
            return self._format_remaining(int(max(0, item.initial_seconds)))
        if item.state == "Stopped":
            return self._format_remaining(int(max(0, item.initial_seconds)))
        return self._format_remaining(int(max(0, item.remaining_seconds)))

    def _is_alert_visible_or_pending(self, item: TimerItem) -> bool:
        if self.current_alert_timer and self.current_alert_timer.timer_id == item.timer_id:
            return True
        return any(p.timer_id == item.timer_id for p in self.pending_alerts)

    def _display_end(self, item: TimerItem) -> str:
        if item.input_mode == "absolute":
            if item.target_hhmm:
                return item.target_hhmm
            if item.target_epoch is not None:
                return dt.datetime.fromtimestamp(item.target_epoch).strftime("%H:%M")
            return "--:--"

        if item.state == "Stopped":
            return "--:--"
        if item.state == "Running":
            eta = dt.datetime.now() + dt.timedelta(seconds=int(max(0, item.remaining_seconds)))
            return eta.strftime("%H:%M")
        return "--:--"

    def _refresh_row(self, item: TimerItem) -> None:
        if item.remaining_var:
            item.remaining_var.set(self._display_remaining(item))
        if item.end_var:
            item.end_var.set(self._display_end(item))

        if item.remaining_btn:
            fg = "#444444" if item.input_mode == "relative" and item.state == "Paused" else "#000000"
            item.remaining_btn.configure(fg=fg, disabledforeground="#888888")

        if item.end_btn:
            fg = "#888888" if item.input_mode == "relative" and item.state == "Paused" else "#000000"
            item.end_btn.configure(fg=fg, disabledforeground="#888888")

        if not item.play_pause_btn or not item.stop_btn or not item.delete_btn:
            return

        if item.state == "Running":
            item.play_pause_btn.configure(text="⏸")
            if item.input_mode == "absolute":
                item.play_pause_btn.configure(state="disabled")
            else:
                item.play_pause_btn.configure(state="normal")
        else:
            item.play_pause_btn.configure(text="▶", state="normal")

        item.stop_btn.configure(state="normal")
        item.delete_btn.configure(state="normal")

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
            parsed = self._parse_time_input(value)
        except ValueError as exc:
            self.error_var.set(str(exc))
            return

        self.error_var.set("")
        item.input_mode = str(parsed["mode"])
        item.finished_at = None
        item.alerted = False
        item.last_tick_epoch = time.time()

        if item.input_mode == "absolute":
            item.target_epoch = float(parsed["target_epoch"])
            item.target_hhmm = str(parsed["normalized"])
            item.remaining_seconds = 0.0
            item.initial_seconds = 0
            item.state = "Running"
        else:
            secs = int(parsed["seconds"])
            item.initial_seconds = secs
            item.remaining_seconds = float(secs)
            item.target_epoch = None
            item.target_hhmm = None
            item.state = "Running"

        self._refresh_row(item)
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
            if item.target_hhmm:
                return item.target_hhmm
            if item.target_epoch is not None:
                return dt.datetime.fromtimestamp(item.target_epoch).strftime("%H:%M")
            return dt.datetime.now().strftime("%H:%M")

        if item.input_mode == "relative":
            seconds = int(max(0, item.remaining_seconds if item.state != "Stopped" else item.initial_seconds))
            return self._format_relative_input(seconds)

        # absolute timer's Remaining edit defaults to 30s relative timer creation.
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
            "input_mode": item.input_mode,
            "state": item.state,
            "target_epoch": item.target_epoch,
            "target_hhmm": item.target_hhmm,
            "remaining_seconds": int(max(0, round(item.remaining_seconds))),
            "initial_seconds": item.initial_seconds,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            "alerted": item.alerted,
        }

    def _save_state(self) -> None:
        payload = {
            "timers": [
                self._serialize_timer(self.timers[tid])
                for tid in self.timer_order
                if tid in self.timers
            ],
            "trash": [
                self._serialize_timer(self.trash_timers[tid])
                for tid in self.trash_order
                if tid in self.trash_timers
            ],
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

    @staticmethod
    def _parse_relative_text(value: str | None) -> int:
        if not value:
            return 0
        m = RELATIVE_COLON_RE.match(value)
        if not m:
            return 0
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        if seconds > 59:
            return 0
        return max(0, (minutes * 60) + seconds)

    def _deserialize_timer(self, entry: dict[str, object]) -> TimerItem | None:
        timer_id = entry.get("timer_id")
        if not isinstance(timer_id, str) or not timer_id:
            timer_id = str(uuid4())

        label = entry.get("label")
        if not isinstance(label, str) or not label:
            return None

        mode = entry.get("input_mode")
        input_mode = mode if mode in {"relative", "absolute"} else "relative"

        item = TimerItem(timer_id=timer_id, label=label, input_mode=input_mode)

        raw_state = entry.get("state")
        if isinstance(raw_state, str) and raw_state in {"Running", "Paused", "Stopped", "Finished"}:
            item.state = raw_state
        elif isinstance(raw_state, str) and raw_state in {"Running", "Paused", "Finished"}:
            item.state = raw_state
        else:
            item.state = "Stopped"

        item.finished_at = self._parse_iso_dt(entry.get("finished_at"))
        item.alerted = bool(entry.get("alerted", False))

        if input_mode == "absolute":
            target_epoch = entry.get("target_epoch")
            if isinstance(target_epoch, (int, float)):
                item.target_epoch = float(target_epoch)
            else:
                old_end = self._parse_iso_dt(entry.get("end_time"))
                if old_end:
                    item.target_epoch = old_end.timestamp()

            target_hhmm = entry.get("target_hhmm")
            if isinstance(target_hhmm, str):
                item.target_hhmm = target_hhmm
            else:
                preset_absolute = entry.get("preset_absolute")
                if isinstance(preset_absolute, str):
                    item.target_hhmm = preset_absolute
                elif item.target_epoch is not None:
                    item.target_hhmm = dt.datetime.fromtimestamp(item.target_epoch).strftime("%H:%M")

            if item.state == "Paused":
                item.state = "Stopped"

        else:
            initial_seconds = entry.get("initial_seconds")
            if isinstance(initial_seconds, (int, float)):
                item.initial_seconds = int(max(0, initial_seconds))
            else:
                item.initial_seconds = self._parse_relative_text(entry.get("preset_relative") if isinstance(entry.get("preset_relative"), str) else None)

            remaining_seconds = entry.get("remaining_seconds")
            if isinstance(remaining_seconds, (int, float)):
                item.remaining_seconds = float(max(0, remaining_seconds))
            else:
                paused_remaining = entry.get("paused_remaining")
                if isinstance(paused_remaining, (int, float)):
                    item.remaining_seconds = float(max(0, paused_remaining))
                else:
                    old_end = self._parse_iso_dt(entry.get("end_time"))
                    if old_end:
                        item.remaining_seconds = float(max(0, int((old_end - dt.datetime.now()).total_seconds())))

            if item.initial_seconds <= 0:
                item.initial_seconds = int(max(1, round(item.remaining_seconds)))

            if item.state == "Running":
                item.last_tick_epoch = time.time()
            elif item.state == "Paused":
                item.last_tick_epoch = None

        if item.input_mode == "absolute" and item.target_epoch is None:
            return None

        return item

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

        trash = payload.get("trash")
        if not isinstance(trash, list):
            trash = []

        seen_ids: set[str] = set()

        for entry in timers:
            if not isinstance(entry, dict):
                continue
            item = self._deserialize_timer(entry)
            if not item:
                continue
            while item.timer_id in seen_ids:
                item.timer_id = str(uuid4())
            seen_ids.add(item.timer_id)
            self.timers[item.timer_id] = item
            self.timer_order.append(item.timer_id)

        for entry in trash:
            if not isinstance(entry, dict):
                continue
            item = self._deserialize_timer(entry)
            if not item:
                continue
            while item.timer_id in seen_ids:
                item.timer_id = str(uuid4())
            seen_ids.add(item.timer_id)
            self.trash_timers[item.timer_id] = item
            self.trash_order.append(item.timer_id)

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


def main() -> None:
    root = tk.Tk()
    _app = TimerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
