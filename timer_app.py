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
from tkinter import simpledialog, ttk
from uuid import uuid4


ABSOLUTE_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
RELATIVE_COLON_RE = re.compile(r"^(\d{1,3}):(\d{1,2})$")
MINUTES_ONLY_RE = re.compile(r"^\d+$")
COLUMN_WIDTHS = [236, 184, 126, 172]
GENERAL_TAB_ID = "system-general"
TRASH_TAB_ID = "system-trash"
TAB_HOVER_DELAY_MS = 450
WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


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
class TabItem:
    tab_id: str
    name: str
    is_system: bool = False


@dataclass
class TimerItem:
    timer_id: str
    label: str
    input_mode: str  # relative or absolute
    tab_id: str = GENERAL_TAB_ID
    last_non_trash_tab_id: str = GENERAL_TAB_ID
    state: str = "Running"  # Running, Paused, Stopped, Finished
    target_epoch: float | None = None  # absolute next occurrence
    target_hhmm: str | None = None
    remaining_seconds: float = 0.0  # relative current cycle
    initial_seconds: int = 0
    last_tick_epoch: float | None = None
    finished_at: dt.datetime | None = None
    alerted: bool = False
    absolute_repeat_weekdays: list[bool] = field(default_factory=lambda: [False] * 7)
    relative_repeat_enabled: bool = False

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
    settings_btn: tk.Button | None = field(default=None, repr=False)


class TimerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MultiDeadline Timer")
        self.root.geometry("980x760")
        self.root.minsize(860, 640)
        self.ui_font_family = pick_ui_font_family(self.root)
        self.root.option_add("*Font", f"{{{self.ui_font_family}}} 12")
        self.state_path = Path(__file__).with_name("timer_state.json")
        self.state_dirty = False

        self.tabs: dict[str, TabItem] = {}
        self.user_tab_order: list[str] = []
        self.selected_tab_id = GENERAL_TAB_ID

        self.timers: dict[str, TimerItem] = {}
        self.timer_order_by_tab: dict[str, list[str]] = {}

        self.pending_alerts: list[TimerItem] = []
        self.current_alert_window: tk.Toplevel | None = None
        self.current_alert_timer: TimerItem | None = None
        self.alert_key_bindings: list[tuple[str, str]] = []

        self.reset_dialog: tk.Toplevel | None = None
        self.reset_target_timer_id: str | None = None
        self.reset_source_mode: str | None = None
        self.reset_input_var = tk.StringVar()

        self.settings_dialog: tk.Toplevel | None = None
        self.settings_target_timer_id: str | None = None
        self.settings_weekday_vars: list[tk.BooleanVar] = []
        self.settings_relative_repeat_var = tk.BooleanVar(value=False)
        self.settings_weekday_buttons: list[ttk.Checkbutton] = []
        self.settings_relative_repeat_btn: ttk.Checkbutton | None = None

        self.add_label_entry: ttk.Entry | None = None
        self.add_time_entry: ttk.Entry | None = None
        self.error_label_widget: ttk.Label | None = None
        self.main_controls_frame: ttk.Frame | None = None
        self.trash_controls_frame: ttk.Frame | None = None
        self.empty_trash_btn: ttk.Button | None = None
        self.delete_tab_btn: ttk.Button | None = None

        self.tab_widgets: dict[str, tk.Widget] = {}
        self.dragging_tab_id: str | None = None
        self.tab_plus_btn: tk.Button | None = None
        self.dragging_timer_id: str | None = None
        self.drop_effect_job: str | None = None
        self.tab_hover_job: str | None = None
        self.tab_hover_target_id: str | None = None

        self.input_var = tk.StringVar()
        self.label_input_var = tk.StringVar(value="Timer")
        self.error_var = tk.StringVar(value="")

        self._reset_tabs()
        self._build_ui()
        self._load_state()
        self._render_tab_strip()
        self._render_rows()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._autosave_loop)
        self._tick()

    def _reset_tabs(self) -> None:
        self.tabs = {
            GENERAL_TAB_ID: TabItem(tab_id=GENERAL_TAB_ID, name="General", is_system=True),
            TRASH_TAB_ID: TabItem(tab_id=TRASH_TAB_ID, name="Trash", is_system=True),
        }
        self.user_tab_order = []
        self.selected_tab_id = GENERAL_TAB_ID
        self.timer_order_by_tab = {
            GENERAL_TAB_ID: [],
            TRASH_TAB_ID: [],
        }

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=10)
        container.pack(fill="both", expand=True)

        tabs_outer = ttk.Frame(container)
        tabs_outer.pack(fill="x", pady=(0, 8))
        tabs_outer.columnconfigure(0, weight=1)

        self.tab_strip_frame = ttk.Frame(tabs_outer)
        self.tab_strip_frame.grid(row=0, column=0, sticky="we")
        self.tab_strip_frame.columnconfigure(0, weight=1)
        self.tab_strip_inner = ttk.Frame(self.tab_strip_frame)
        self.tab_strip_inner.pack(fill="x")

        self.tab_actions_frame = ttk.Frame(tabs_outer)
        self.tab_actions_frame.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.delete_tab_btn = ttk.Button(self.tab_actions_frame, text="Delete Tab", command=self.delete_selected_tab)
        self.delete_tab_btn.pack(side="left")

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

        trash_frame = ttk.Frame(container)
        self.trash_controls_frame = trash_frame
        ttk.Label(trash_frame, text="Trash tab: restore or permanently delete timers.").pack(side="left")
        self.empty_trash_btn = ttk.Button(trash_frame, text="Empty Trash", command=self.empty_trash)
        self.empty_trash_btn.pack(side="left", padx=(8, 0))

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
        self.root.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.root.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))

    def _on_rows_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _all_tab_ids(self) -> list[str]:
        return [GENERAL_TAB_ID, *self.user_tab_order, TRASH_TAB_ID]

    def _ensure_tab_order_bucket(self, tab_id: str) -> list[str]:
        return self.timer_order_by_tab.setdefault(tab_id, [])

    def _visible_timer_ids(self) -> list[str]:
        return list(self.timer_order_by_tab.get(self.selected_tab_id, []))

    def _selected_tab(self) -> TabItem:
        return self.tabs.get(self.selected_tab_id, self.tabs[GENERAL_TAB_ID])

    def _render_tab_strip(self) -> None:
        for child in self.tab_strip_inner.winfo_children():
            child.destroy()
        self.tab_widgets = {}
        self.tab_plus_btn = None

        self._create_tab_button(self.tab_strip_inner, GENERAL_TAB_ID)
        for tab_id in self.user_tab_order:
            self._create_tab_button(self.tab_strip_inner, tab_id)

        plus = tk.Button(
            self.tab_strip_inner,
            text="+",
            command=self.create_new_tab,
            relief="groove",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
        )
        plus.pack(side="left", padx=(2, 6))
        self.tab_plus_btn = plus

        self._create_tab_button(self.tab_strip_inner, TRASH_TAB_ID)

        self._refresh_tab_controls()

    def _create_tab_button(self, parent: ttk.Frame, tab_id: str) -> None:
        tab = self.tabs[tab_id]
        selected = tab_id == self.selected_tab_id
        label_text = f"🗑 {tab.name}" if tab_id == TRASH_TAB_ID else tab.name
        bg = "#d8e6ff" if selected else "#efefef"
        fg = "#7a2d00" if tab_id == TRASH_TAB_ID else "#000000"
        widget = tk.Label(
            parent,
            text=label_text,
            bg=bg,
            fg=fg,
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=5,
            cursor="hand2",
        )
        widget.pack(side="left", padx=(0, 4))
        widget.bind("<Button-1>", lambda _e, tid=tab_id: self.select_tab(tid))
        widget.bind("<Double-Button-1>", lambda _e, tid=tab_id: self.rename_selected_tab(tid))
        if not tab.is_system:
            widget.bind("<ButtonPress-1>", lambda event, tid=tab_id: self._on_tab_drag_start(event, tid), add="+")
            widget.bind("<B1-Motion>", self._on_tab_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_tab_drag_end)
        self.tab_widgets[tab_id] = widget

    def _refresh_tab_controls(self) -> None:
        is_trash = self.selected_tab_id == TRASH_TAB_ID
        if self.main_controls_frame:
            if is_trash and self.main_controls_frame.winfo_manager():
                self.main_controls_frame.pack_forget()
            elif not is_trash and not self.main_controls_frame.winfo_manager():
                if self.error_label_widget and self.error_label_widget.winfo_exists():
                    self.main_controls_frame.pack(fill="x", pady=(0, 6), before=self.error_label_widget)
                else:
                    self.main_controls_frame.pack(fill="x", pady=(0, 6))

        if self.trash_controls_frame:
            if is_trash and not self.trash_controls_frame.winfo_manager():
                if self.error_label_widget and self.error_label_widget.winfo_exists():
                    self.trash_controls_frame.pack(fill="x", pady=(0, 6), before=self.error_label_widget)
                else:
                    self.trash_controls_frame.pack(fill="x", pady=(0, 6))
            elif not is_trash and self.trash_controls_frame.winfo_manager():
                self.trash_controls_frame.pack_forget()

        if self.empty_trash_btn:
            if self.timer_order_by_tab.get(TRASH_TAB_ID):
                self.empty_trash_btn.state(["!disabled"])
            else:
                self.empty_trash_btn.state(["disabled"])

        if self.delete_tab_btn:
            selected = self.tabs.get(self.selected_tab_id)
            if selected and not selected.is_system:
                self.delete_tab_btn.state(["!disabled"])
            else:
                self.delete_tab_btn.state(["disabled"])

    def select_tab(self, tab_id: str) -> None:
        if tab_id not in self.tabs or tab_id == self.selected_tab_id:
            return
        self.selected_tab_id = tab_id
        self._cancel_tab_hover()
        self._render_tab_strip()
        self._render_rows()
        self._mark_dirty()

    def create_new_tab(self) -> None:
        tab_id = str(uuid4())
        self.tabs[tab_id] = TabItem(tab_id=tab_id, name="New Tab")
        self.user_tab_order.append(tab_id)
        self.timer_order_by_tab[tab_id] = []
        self.selected_tab_id = tab_id
        self._render_tab_strip()
        self._render_rows()
        self._mark_dirty()

    def rename_selected_tab(self, tab_id: str) -> None:
        if tab_id != self.selected_tab_id:
            self.select_tab(tab_id)
            return
        tab = self.tabs.get(tab_id)
        if not tab or tab.is_system:
            return
        new_name = simpledialog.askstring("Rename Tab", "Tab name", initialvalue=tab.name, parent=self.root)
        if new_name is None:
            return
        text = new_name.strip()
        if not text:
            return
        tab.name = text
        self._render_tab_strip()
        self._mark_dirty()

    def delete_selected_tab(self) -> None:
        tab = self.tabs.get(self.selected_tab_id)
        if not tab or tab.is_system:
            return
        if self.timer_order_by_tab.get(tab.tab_id):
            self.error_var.set("Cannot delete a non-empty tab.")
            return
        self.user_tab_order = [tid for tid in self.user_tab_order if tid != tab.tab_id]
        self.timer_order_by_tab.pop(tab.tab_id, None)
        self.tabs.pop(tab.tab_id, None)
        self.selected_tab_id = GENERAL_TAB_ID
        self._render_tab_strip()
        self._render_rows()
        self._mark_dirty()

    def _on_tab_drag_start(self, _event: tk.Event, tab_id: str) -> None:
        if tab_id not in self.user_tab_order:
            return
        self.dragging_tab_id = tab_id
        self._set_tab_lifted(tab_id, True)

    def _on_tab_drag_motion(self, event: tk.Event) -> None:
        if not self.dragging_tab_id or self.dragging_tab_id not in self.user_tab_order:
            return
        target_index = self._target_user_tab_index_from_pointer(event.x_root)
        current_index = self.user_tab_order.index(self.dragging_tab_id)
        if current_index == target_index or current_index + 1 == target_index:
            return
        self.user_tab_order.pop(current_index)
        if target_index > current_index:
            target_index -= 1
        target_index = max(0, min(target_index, len(self.user_tab_order)))
        self.user_tab_order.insert(target_index, self.dragging_tab_id)
        self._repack_tabs_by_order()
        self._mark_dirty()

    def _on_tab_drag_end(self, _event: tk.Event) -> None:
        dragged_tab_id = self.dragging_tab_id
        self.dragging_tab_id = None
        if dragged_tab_id:
            self._set_tab_lifted(dragged_tab_id, False)
            self._repack_tabs_by_order()

    def _target_user_tab_index_from_pointer(self, x_root: int) -> int:
        for idx, tab_id in enumerate(self.user_tab_order):
            widget = self.tab_widgets.get(tab_id)
            if not widget or not widget.winfo_exists():
                continue
            midpoint = widget.winfo_rootx() + (widget.winfo_width() // 2)
            if x_root < midpoint:
                return idx
        return len(self.user_tab_order)

    def _repack_tabs_by_order(self) -> None:
        general = self.tab_widgets.get(GENERAL_TAB_ID)
        trash = self.tab_widgets.get(TRASH_TAB_ID)
        if general and general.winfo_exists():
            general.pack_forget()
            general.pack(side="left", padx=(0, 4))
        for tab_id in self.user_tab_order:
            widget = self.tab_widgets.get(tab_id)
            if not widget or not widget.winfo_exists():
                continue
            widget.pack_forget()
            widget.pack(side="left", padx=(0, 4))
        if self.tab_plus_btn and self.tab_plus_btn.winfo_exists():
            self.tab_plus_btn.pack_forget()
            self.tab_plus_btn.pack(side="left", padx=(2, 6))
        if trash and trash.winfo_exists():
            trash.pack_forget()
            trash.pack(side="left", padx=(0, 4))

    def _set_tab_lifted(self, tab_id: str, lifted: bool) -> None:
        widget = self.tab_widgets.get(tab_id)
        if not widget or not widget.winfo_exists():
            return
        if lifted:
            widget.configure(relief="raised", borderwidth=2, padx=14, pady=6, cursor="fleur", bg="#c7d2e8")
        else:
            selected = tab_id == self.selected_tab_id
            bg = "#d8e6ff" if selected else "#efefef"
            widget.configure(relief="solid", borderwidth=1, padx=12, pady=5, cursor="hand2", bg=bg)

    def add_timer(self) -> None:
        if self.selected_tab_id == TRASH_TAB_ID:
            self.error_var.set("Cannot create a timer in Trash.")
            return

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
        item = TimerItem(
            timer_id=str(uuid4()),
            label=label,
            input_mode=str(parsed["mode"]),
            tab_id=self.selected_tab_id,
            last_non_trash_tab_id=self.selected_tab_id,
        )

        if item.input_mode == "absolute":
            item.target_hhmm = str(parsed["normalized"])
            item.target_epoch = self._next_absolute_epoch(item)
            item.state = "Running"
        else:
            seconds = int(parsed["seconds"])
            item.initial_seconds = seconds
            item.remaining_seconds = float(seconds)
            item.last_tick_epoch = now_epoch
            item.state = "Running"

        self.timers[item.timer_id] = item
        self._ensure_tab_order_bucket(item.tab_id).append(item.timer_id)
        self.input_var.set("")
        self._render_rows()
        self._mark_dirty()

    def _parse_time_input(self, value: str) -> dict[str, object]:
        m_abs = ABSOLUTE_TIME_RE.match(value)
        if m_abs:
            hour = int(m_abs.group(1))
            minute = int(m_abs.group(2))
            if hour > 23 or minute > 59:
                raise ValueError("Absolute time must be HH:MM (00:00-23:59).")
            return {
                "mode": "absolute",
                "hour": hour,
                "minute": minute,
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

    def _render_rows(self) -> None:
        visible_ids = self._visible_timer_ids()
        for tid in visible_ids:
            self._sync_label(tid)
        for item in self.timers.values():
            self._clear_widget_refs(item)

        for child in self.rows_container.winfo_children():
            child.destroy()

        is_trash = self.selected_tab_id == TRASH_TAB_ID
        for tid in visible_ids:
            item = self.timers.get(tid)
            if not item:
                continue
            if is_trash:
                self._create_trash_row(item)
            else:
                self._create_row(item)

        self._refresh_tab_controls()
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
        item.settings_btn = None

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
        label_cell.columnconfigure(1, weight=1)

        drag_handle = ttk.Label(label_cell, text="::", cursor="fleur", width=3, anchor="center")
        drag_handle.grid(row=0, column=0, padx=(0, 4))
        item.drag_handle = drag_handle
        self._bind_drag_events(drag_handle, item.timer_id)

        label_entry = ttk.Entry(label_cell, textvariable=item.label_var, width=16)
        label_entry.grid(row=0, column=1, sticky="we")
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

        stack = ttk.Frame(btns)
        stack.pack(side="left")

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

        settings_btn = tk.Button(
            btns,
            text="⚙",
            width=2,
            command=lambda tid=item.timer_id: self.open_settings_dialog(tid),
            relief="groove",
            padx=0,
            pady=0,
        )
        settings_btn.pack(side="left", padx=(8, 6))
        item.settings_btn = settings_btn

        delete_btn = tk.Button(
            btns,
            text="ⓧ",
            width=2,
            command=lambda tid=item.timer_id: self.move_to_trash(tid),
            relief="groove",
            font=(self.ui_font_family, 10),
            padx=0,
            pady=0,
        )
        delete_btn.pack(side="left")
        item.delete_btn = delete_btn

        self._refresh_row(item)

    def _create_trash_row(self, item: TimerItem) -> None:
        row = ttk.Frame(self.rows_container, padding=(4, 4))
        row.pack(fill="x")
        for idx, min_w in enumerate(COLUMN_WIDTHS):
            row.grid_columnconfigure(idx, minsize=min_w)

        item.row_frame = row

        label_cell = ttk.Frame(row)
        label_cell.grid(row=0, column=0, sticky="we", padx=4)
        label_cell.columnconfigure(1, weight=1)

        drag_handle = ttk.Label(label_cell, text="::", cursor="fleur", width=3, anchor="center")
        drag_handle.grid(row=0, column=0, padx=(0, 4))
        item.drag_handle = drag_handle
        self._bind_drag_events(drag_handle, item.timer_id)

        ttk.Label(label_cell, text=item.label).grid(row=0, column=1, sticky="w")
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
        if timer_id not in self.timers:
            return
        self.dragging_timer_id = timer_id
        item = self.timers[timer_id]
        self._set_row_lifted(item, True)

    def _on_drag_motion(self, event: tk.Event) -> None:
        timer_id = self.dragging_timer_id
        if not timer_id:
            return
        item = self.timers.get(timer_id)
        if not item:
            return

        hover_tab_id = self._tab_id_from_pointer(event.x_root, event.y_root)
        if hover_tab_id:
            if hover_tab_id != item.tab_id:
                self._schedule_tab_hover(timer_id, hover_tab_id)
            else:
                self._cancel_tab_hover()
            return

        self._cancel_tab_hover()
        if item.tab_id != self.selected_tab_id:
            return
        target_index = self._target_index_from_pointer(event.y_root, self.selected_tab_id, timer_id)
        self._move_timer_within_tab(timer_id, self.selected_tab_id, target_index)

    def _on_drag_end(self, event: tk.Event) -> None:
        timer_id = self.dragging_timer_id
        self.dragging_timer_id = None
        self._cancel_tab_hover()
        if not timer_id:
            return

        item = self.timers.get(timer_id)
        if not item:
            return

        drop_tab_id = self._tab_id_from_pointer(event.x_root, event.y_root)
        if drop_tab_id and drop_tab_id != item.tab_id:
            self._move_timer_to_tab(timer_id, drop_tab_id, select_target=True)
            item = self.timers.get(timer_id)

        if item and item.tab_id == self.selected_tab_id:
            target_index = self._target_index_from_pointer(event.y_root, self.selected_tab_id, timer_id)
            self._move_timer_within_tab(timer_id, self.selected_tab_id, target_index)
            self._play_drop_effect(item)
        elif item:
            self._set_row_lifted(item, False)

    def _schedule_tab_hover(self, timer_id: str, tab_id: str) -> None:
        if self.tab_hover_target_id == tab_id:
            return
        self._cancel_tab_hover()
        self.tab_hover_target_id = tab_id
        self.tab_hover_job = self.root.after(TAB_HOVER_DELAY_MS, lambda: self._activate_hover_tab(timer_id, tab_id))

    def _cancel_tab_hover(self) -> None:
        if self.tab_hover_job:
            try:
                self.root.after_cancel(self.tab_hover_job)
            except tk.TclError:
                pass
        self.tab_hover_job = None
        self.tab_hover_target_id = None

    def _activate_hover_tab(self, timer_id: str, tab_id: str) -> None:
        self.tab_hover_job = None
        self.tab_hover_target_id = None
        item = self.timers.get(timer_id)
        if not item or item.tab_id == tab_id:
            return
        self._move_timer_to_tab(timer_id, tab_id, select_target=True)

    def _tab_id_from_pointer(self, x_root: int, y_root: int) -> str | None:
        for tab_id in self._all_tab_ids():
            widget = self.tab_widgets.get(tab_id)
            if not widget or not widget.winfo_exists():
                continue
            left = widget.winfo_rootx()
            top = widget.winfo_rooty()
            right = left + widget.winfo_width()
            bottom = top + widget.winfo_height()
            if left <= x_root <= right and top <= y_root <= bottom:
                return tab_id
        return None

    def _target_index_from_pointer(self, y_root: int, tab_id: str, timer_id: str | None = None) -> int:
        order = self.timer_order_by_tab.get(tab_id, [])
        visible_order = [tid for tid in order if tid != timer_id]
        for idx, tid in enumerate(visible_order):
            item = self.timers.get(tid)
            row = item.row_frame if item else None
            if not row or not row.winfo_exists():
                continue
            midpoint = row.winfo_rooty() + (row.winfo_height() // 2)
            if y_root < midpoint:
                return idx
        return len(visible_order)

    def _move_timer_within_tab(self, timer_id: str, tab_id: str, target_index: int) -> None:
        order = self.timer_order_by_tab.get(tab_id)
        if not order or timer_id not in order:
            return
        old_index = order.index(timer_id)
        if old_index == target_index:
            return
        order.pop(old_index)
        target_index = max(0, min(target_index, len(order)))
        order.insert(target_index, timer_id)
        self._repack_rows_by_order(tab_id)
        self._mark_dirty()

    def _move_timer_to_tab(
        self,
        timer_id: str,
        target_tab_id: str,
        target_index: int | None = None,
        select_target: bool = False,
    ) -> None:
        item = self.timers.get(timer_id)
        if not item or target_tab_id not in self.tabs:
            return
        source_tab_id = item.tab_id
        if source_tab_id == target_tab_id:
            if target_index is not None:
                self._move_timer_within_tab(timer_id, target_tab_id, target_index)
            return

        source_order = self.timer_order_by_tab.get(source_tab_id, [])
        if timer_id in source_order:
            source_order.remove(timer_id)

        target_order = self._ensure_tab_order_bucket(target_tab_id)
        insert_at = len(target_order) if target_index is None else max(0, min(target_index, len(target_order)))
        target_order.insert(insert_at, timer_id)

        if target_tab_id == TRASH_TAB_ID and source_tab_id != TRASH_TAB_ID:
            item.last_non_trash_tab_id = source_tab_id
        elif source_tab_id == TRASH_TAB_ID and target_tab_id != TRASH_TAB_ID:
            item.last_non_trash_tab_id = target_tab_id

        item.tab_id = target_tab_id

        if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id and target_tab_id == TRASH_TAB_ID:
            self._dismiss_alert()
        if target_tab_id == TRASH_TAB_ID:
            self.pending_alerts = [t for t in self.pending_alerts if t.timer_id != timer_id]
            item.alerted = False
        if self.reset_target_timer_id == timer_id and target_tab_id == TRASH_TAB_ID:
            self._close_reset_dialog()
        if self.settings_target_timer_id == timer_id and target_tab_id == TRASH_TAB_ID:
            self._close_settings_dialog()

        if select_target:
            self.selected_tab_id = target_tab_id
            self._render_tab_strip()
            self._render_rows()
        else:
            if source_tab_id == self.selected_tab_id or target_tab_id == self.selected_tab_id:
                self._render_rows()
            self._render_tab_strip()
        self._mark_dirty()

    def _repack_rows_by_order(self, tab_id: str) -> None:
        if tab_id != self.selected_tab_id:
            return
        for tid in self.timer_order_by_tab.get(tab_id, []):
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
        self.drop_effect_job = self.root.after(120, lambda: self._clear_drop_effect(item.timer_id))

    def _clear_drop_effect(self, timer_id: str) -> None:
        self.drop_effect_job = None
        item = self.timers.get(timer_id)
        if not item:
            return
        self._set_row_lifted(item, False)

    def _sync_label(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or not item.label_var or item.tab_id == TRASH_TAB_ID:
            return
        text = item.label_var.get().strip()
        if text and text != item.label:
            item.label = text
            self._mark_dirty()
        item.label_var.set(item.label)

    def toggle_play_pause(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or item.tab_id == TRASH_TAB_ID:
            return

        now_epoch = time.time()

        if item.state == "Running":
            if item.input_mode == "relative":
                item.state = "Paused"
                item.last_tick_epoch = None
                self._mark_dirty()
            return

        if item.input_mode == "absolute":
            if not item.target_hhmm:
                return
            item.target_epoch = self._next_absolute_epoch(item)
            item.state = "Running"
            item.finished_at = None
            item.alerted = False
            self._remove_pending_alert(timer_id)
            self._mark_dirty()
        else:
            if item.state in {"Finished", "Stopped"} or item.remaining_seconds <= 0:
                item.remaining_seconds = float(item.initial_seconds)
            item.state = "Running"
            item.last_tick_epoch = now_epoch
            item.finished_at = None
            item.alerted = False
            self._remove_pending_alert(timer_id)
            self._mark_dirty()

        self._refresh_row(item)

    def stop_timer(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or item.tab_id == TRASH_TAB_ID:
            return

        if item.input_mode == "absolute":
            item.state = "Stopped"
            item.finished_at = None
            item.last_tick_epoch = None
            self._remove_pending_alert(timer_id)
            item.alerted = False
            if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
                self._dismiss_alert()
            self._mark_dirty()
        else:
            item.state = "Stopped"
            item.remaining_seconds = float(item.initial_seconds)
            item.last_tick_epoch = None
            item.finished_at = None
            item.alerted = False
            self._remove_pending_alert(timer_id)
            if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
                self._dismiss_alert()
            self._mark_dirty()

        self._refresh_row(item)

    def move_to_trash(self, timer_id: str) -> None:
        self._move_timer_to_tab(timer_id, TRASH_TAB_ID, select_target=False)

    def restore_from_trash(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or item.tab_id != TRASH_TAB_ID:
            return
        target_tab_id = item.last_non_trash_tab_id
        if target_tab_id not in self.tabs or target_tab_id == TRASH_TAB_ID:
            target_tab_id = GENERAL_TAB_ID
        self._move_timer_to_tab(timer_id, target_tab_id, select_target=True)

    def delete_permanently(self, timer_id: str) -> None:
        item = self.timers.pop(timer_id, None)
        if not item:
            return
        order = self.timer_order_by_tab.get(item.tab_id, [])
        if timer_id in order:
            order.remove(timer_id)
        self._remove_pending_alert(timer_id)
        if self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
            self._dismiss_alert()
        if self.reset_target_timer_id == timer_id:
            self._close_reset_dialog()
        if self.settings_target_timer_id == timer_id:
            self._close_settings_dialog()
        self._render_rows()
        self._mark_dirty()

    def empty_trash(self) -> None:
        trash_ids = list(self.timer_order_by_tab.get(TRASH_TAB_ID, []))
        if not trash_ids:
            return
        for timer_id in trash_ids:
            item = self.timers.pop(timer_id, None)
            if item and self.current_alert_timer and self.current_alert_timer.timer_id == timer_id:
                self._dismiss_alert()
            self._remove_pending_alert(timer_id)
        self.timer_order_by_tab[TRASH_TAB_ID] = []
        self._render_rows()
        self._mark_dirty()

    def _tick(self) -> None:
        now_epoch = time.time()
        now_dt = dt.datetime.now()

        for timer_id, item in list(self.timers.items()):
            if item.tab_id != TRASH_TAB_ID:
                self._sync_label(timer_id)

            if item.state == "Running":
                if item.input_mode == "absolute":
                    remaining = self._absolute_remaining(item, now_epoch)
                    if remaining <= 0:
                        self._handle_absolute_completion(item, now_dt)
                else:
                    self._advance_relative_timer(item, now_epoch, now_dt)

            if item.tab_id == self.selected_tab_id:
                self._refresh_row(item)

        if not self.current_alert_window and self.pending_alerts:
            next_item = self.pending_alerts.pop(0)
            if next_item.timer_id in self.timers and next_item.alerted:
                self._show_fullscreen_alert(next_item)

        self.root.after(200, self._tick)

    def _handle_absolute_completion(self, item: TimerItem, now_dt: dt.datetime) -> None:
        finished_dt = dt.datetime.fromtimestamp(item.target_epoch) if item.target_epoch is not None else now_dt
        self._queue_alert(item, finished_dt)

        if self._has_absolute_repeat(item):
            item.target_epoch = self._next_absolute_epoch(item, from_dt=finished_dt + dt.timedelta(seconds=1))
            item.state = "Running"
        else:
            item.state = "Finished"
        self._mark_dirty()

    def _advance_relative_timer(self, item: TimerItem, now_epoch: float, now_dt: dt.datetime) -> None:
        if item.last_tick_epoch is None:
            item.last_tick_epoch = now_epoch
            return

        delta = max(0.0, now_epoch - item.last_tick_epoch)
        if delta <= 0:
            return
        item.last_tick_epoch = now_epoch

        if item.relative_repeat_enabled and item.initial_seconds > 0:
            if delta < item.remaining_seconds:
                item.remaining_seconds = max(0.0, item.remaining_seconds - delta)
                return

            extra = delta - item.remaining_seconds
            self._queue_alert(item, now_dt)
            cycle = item.initial_seconds
            if cycle <= 0:
                item.remaining_seconds = 0.0
                item.state = "Finished"
                item.last_tick_epoch = None
                return
            remainder = extra % cycle
            item.remaining_seconds = float(cycle if remainder == 0 else cycle - remainder)
            self._mark_dirty()
            return

        item.remaining_seconds = max(0.0, item.remaining_seconds - delta)
        if item.remaining_seconds <= 0:
            item.remaining_seconds = 0.0
            item.state = "Finished"
            item.last_tick_epoch = None
            self._queue_alert(item, now_dt)
            self._mark_dirty()

    def _queue_alert(self, item: TimerItem, finished_dt: dt.datetime) -> None:
        if item.alerted:
            return
        item.alerted = True
        item.finished_at = finished_dt
        if not any(p.timer_id == item.timer_id for p in self.pending_alerts):
            self.pending_alerts.append(item)

    def _remove_pending_alert(self, timer_id: str) -> None:
        self.pending_alerts = [t for t in self.pending_alerts if t.timer_id != timer_id]

    def _next_absolute_epoch(self, item: TimerItem, from_dt: dt.datetime | None = None) -> float:
        reference = from_dt or dt.datetime.now()
        hhmm = item.target_hhmm
        if not hhmm or not ABSOLUTE_TIME_RE.match(hhmm):
            return reference.timestamp()

        hour, minute = map(int, hhmm.split(":"))
        candidate = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        weekdays = item.absolute_repeat_weekdays

        if not self._has_absolute_repeat(item):
            if candidate <= reference:
                candidate += dt.timedelta(days=1)
            return candidate.timestamp()

        for offset in range(0, 15):
            day = candidate.date() + dt.timedelta(days=offset)
            weekday_index = self._weekday_index_for_storage(day.weekday())
            if not weekdays[weekday_index]:
                continue
            day_candidate = dt.datetime.combine(day, dt.time(hour=hour, minute=minute))
            if day_candidate > reference:
                return day_candidate.timestamp()

        fallback = candidate + dt.timedelta(days=7)
        return fallback.timestamp()

    @staticmethod
    def _weekday_index_for_storage(python_weekday: int) -> int:
        return (python_weekday + 1) % 7

    @staticmethod
    def _normalize_weekdays(value: object) -> list[bool]:
        if isinstance(value, list):
            normalized = [bool(v) for v in value[:7]]
            return normalized + ([False] * (7 - len(normalized)))
        return [False] * 7

    @staticmethod
    def _has_absolute_repeat(item: TimerItem) -> bool:
        return any(item.absolute_repeat_weekdays)

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
            return item.target_hhmm or "--:--"

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
        if item.settings_btn:
            item.settings_btn.configure(state="normal")

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
        timer = self.current_alert_timer
        self.current_alert_window = None
        self.current_alert_timer = None

        if timer and timer.timer_id in self.timers:
            timer.alerted = False

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
        if not item or item.tab_id == TRASH_TAB_ID:
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

        msg = ttk.Label(frame, text="HH:MM edits absolute mode. M:SS / minutes edits relative mode.")
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
        self._remove_pending_alert(item.timer_id)
        if self.current_alert_timer and self.current_alert_timer.timer_id == item.timer_id:
            self._dismiss_alert()

        if item.input_mode == "absolute":
            item.target_hhmm = str(parsed["normalized"])
            item.target_epoch = self._next_absolute_epoch(item)
            item.remaining_seconds = 0.0
            item.initial_seconds = 0
            item.last_tick_epoch = None
            item.state = "Running"
        else:
            secs = int(parsed["seconds"])
            item.initial_seconds = secs
            item.remaining_seconds = float(secs)
            item.target_epoch = None
            item.target_hhmm = None
            item.last_tick_epoch = time.time()
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
            return dt.datetime.now().strftime("%H:%M")

        if item.input_mode == "relative":
            seconds = int(max(0, item.remaining_seconds if item.state != "Stopped" else item.initial_seconds))
            return self._format_relative_input(seconds)

        return "0:30"

    def open_settings_dialog(self, timer_id: str) -> None:
        item = self.timers.get(timer_id)
        if not item or item.tab_id == TRASH_TAB_ID:
            return

        if self.settings_dialog and self.settings_dialog.winfo_exists():
            self.settings_dialog.destroy()

        self.settings_target_timer_id = timer_id
        self.settings_weekday_vars = [tk.BooleanVar(value=flag) for flag in item.absolute_repeat_weekdays]
        self.settings_relative_repeat_var.set(item.relative_repeat_enabled)
        self.settings_weekday_buttons = []

        dlg = tk.Toplevel(self.root)
        self.settings_dialog = dlg
        dlg.title(f"Timer Settings: {item.label}")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"Label: {item.label}").pack(anchor="w")
        ttk.Label(frame, text=f"Current type: {item.input_mode}").pack(anchor="w", pady=(4, 10))

        absolute_box = ttk.LabelFrame(frame, text="Absolute Repeat (weekday filter)")
        absolute_box.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(absolute_box, padding=(8, 8))
        row.pack(fill="x")
        for idx, label in enumerate(WEEKDAY_LABELS):
            btn = ttk.Checkbutton(row, text=label, variable=self.settings_weekday_vars[idx])
            btn.pack(side="left", padx=(0, 6))
            self.settings_weekday_buttons.append(btn)

        relative_box = ttk.LabelFrame(frame, text="Relative Repeat")
        relative_box.pack(fill="x", pady=(0, 10))
        rel_row = ttk.Frame(relative_box, padding=(8, 8))
        rel_row.pack(fill="x")
        self.settings_relative_repeat_btn = ttk.Checkbutton(
            rel_row,
            text="Restart automatically when this relative timer reaches zero",
            variable=self.settings_relative_repeat_var,
        )
        self.settings_relative_repeat_btn.pack(anchor="w")

        ttk.Label(
            frame,
            text="Irrelevant controls stay visible but are disabled, so settings survive type changes.",
        ).pack(anchor="w", pady=(0, 10))

        btns = ttk.Frame(frame)
        btns.pack(anchor="e")
        ttk.Button(btns, text="Apply", command=self.apply_settings_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Close", command=self._close_settings_dialog).pack(side="left")

        dlg.bind("<Escape>", lambda _e: self._close_settings_dialog())
        self._refresh_settings_dialog(item)

    def _refresh_settings_dialog(self, item: TimerItem) -> None:
        absolute_state = "normal" if item.input_mode == "absolute" else "disabled"
        relative_state = "normal" if item.input_mode == "relative" else "disabled"

        for btn in self.settings_weekday_buttons:
            btn.configure(state=absolute_state)
        if self.settings_relative_repeat_btn:
            self.settings_relative_repeat_btn.configure(state=relative_state)

    def apply_settings_dialog(self) -> None:
        if not self.settings_target_timer_id:
            return
        item = self.timers.get(self.settings_target_timer_id)
        if not item:
            self._close_settings_dialog()
            return

        item.absolute_repeat_weekdays = [var.get() for var in self.settings_weekday_vars]
        item.relative_repeat_enabled = bool(self.settings_relative_repeat_var.get())

        if item.input_mode == "absolute" and item.state == "Running" and item.target_hhmm:
            item.target_epoch = self._next_absolute_epoch(item)

        self._mark_dirty()
        self._close_settings_dialog()

    def _close_settings_dialog(self) -> None:
        dlg = self.settings_dialog
        self.settings_dialog = None
        self.settings_target_timer_id = None
        self.settings_weekday_vars = []
        self.settings_weekday_buttons = []
        self.settings_relative_repeat_btn = None
        if dlg and dlg.winfo_exists():
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            dlg.destroy()

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
            "tab_id": item.tab_id,
            "last_non_trash_tab_id": item.last_non_trash_tab_id,
            "state": item.state,
            "target_epoch": item.target_epoch,
            "target_hhmm": item.target_hhmm,
            "remaining_seconds": int(max(0, round(item.remaining_seconds))),
            "initial_seconds": item.initial_seconds,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            "alerted": item.alerted,
            "absolute_repeat_weekdays": item.absolute_repeat_weekdays,
            "relative_repeat_enabled": item.relative_repeat_enabled,
        }

    def _save_state(self) -> None:
        payload = {
            "version": 2,
            "tabs": [
                {"tab_id": GENERAL_TAB_ID, "name": self.tabs[GENERAL_TAB_ID].name, "is_system": True},
                *[
                    {"tab_id": tab_id, "name": self.tabs[tab_id].name, "is_system": False}
                    for tab_id in self.user_tab_order
                    if tab_id in self.tabs
                ],
                {"tab_id": TRASH_TAB_ID, "name": self.tabs[TRASH_TAB_ID].name, "is_system": True},
            ],
            "selected_tab_id": self.selected_tab_id,
            "timer_order_by_tab": {
                tab_id: [tid for tid in self.timer_order_by_tab.get(tab_id, []) if tid in self.timers]
                for tab_id in self._all_tab_ids()
            },
            "timers": [self._serialize_timer(item) for item in self.timers.values()],
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

    def _deserialize_timer(self, entry: dict[str, object], default_tab_id: str) -> TimerItem | None:
        timer_id = entry.get("timer_id")
        if not isinstance(timer_id, str) or not timer_id:
            timer_id = str(uuid4())

        label = entry.get("label")
        if not isinstance(label, str) or not label:
            return None

        mode = entry.get("input_mode")
        input_mode = mode if mode in {"relative", "absolute"} else "relative"

        tab_id = entry.get("tab_id")
        if not isinstance(tab_id, str) or tab_id not in self.tabs:
            tab_id = default_tab_id

        last_non_trash_tab_id = entry.get("last_non_trash_tab_id")
        if not isinstance(last_non_trash_tab_id, str):
            last_non_trash_tab_id = GENERAL_TAB_ID if tab_id == TRASH_TAB_ID else tab_id
        if last_non_trash_tab_id not in self.tabs or last_non_trash_tab_id == TRASH_TAB_ID:
            last_non_trash_tab_id = GENERAL_TAB_ID

        item = TimerItem(
            timer_id=timer_id,
            label=label,
            input_mode=input_mode,
            tab_id=tab_id,
            last_non_trash_tab_id=last_non_trash_tab_id,
        )

        raw_state = entry.get("state")
        if isinstance(raw_state, str) and raw_state in {"Running", "Paused", "Stopped", "Finished"}:
            item.state = raw_state
        else:
            item.state = "Stopped"

        item.finished_at = self._parse_iso_dt(entry.get("finished_at"))
        item.alerted = bool(entry.get("alerted", False))
        item.absolute_repeat_weekdays = self._normalize_weekdays(entry.get("absolute_repeat_weekdays"))
        item.relative_repeat_enabled = bool(entry.get("relative_repeat_enabled", False))

        if input_mode == "absolute":
            target_hhmm = entry.get("target_hhmm")
            if isinstance(target_hhmm, str) and ABSOLUTE_TIME_RE.match(target_hhmm):
                item.target_hhmm = target_hhmm
            else:
                preset_absolute = entry.get("preset_absolute")
                if isinstance(preset_absolute, str) and ABSOLUTE_TIME_RE.match(preset_absolute):
                    item.target_hhmm = preset_absolute

            target_epoch = entry.get("target_epoch")
            if isinstance(target_epoch, (int, float)):
                item.target_epoch = float(target_epoch)
            else:
                old_end = self._parse_iso_dt(entry.get("end_time"))
                if old_end:
                    item.target_epoch = old_end.timestamp()

            if not item.target_hhmm and item.target_epoch is not None:
                item.target_hhmm = dt.datetime.fromtimestamp(item.target_epoch).strftime("%H:%M")

            if item.state == "Paused":
                item.state = "Stopped"

            if not item.target_hhmm:
                return None

            if item.state == "Running":
                if self._has_absolute_repeat(item):
                    item.target_epoch = self._next_absolute_epoch(item)
                elif item.target_epoch is None:
                    item.target_epoch = self._next_absolute_epoch(item)

        else:
            initial_seconds = entry.get("initial_seconds")
            if isinstance(initial_seconds, (int, float)):
                item.initial_seconds = int(max(0, initial_seconds))
            else:
                preset_relative = entry.get("preset_relative")
                item.initial_seconds = self._parse_relative_text(preset_relative if isinstance(preset_relative, str) else None)

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
            if item.state == "Stopped":
                item.remaining_seconds = float(item.initial_seconds)

        if item.tab_id != TRASH_TAB_ID and item.last_non_trash_tab_id == TRASH_TAB_ID:
            item.last_non_trash_tab_id = item.tab_id

        return item

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self._reset_tabs()
        self.timers = {}
        seen_ids: set[str] = set()

        if isinstance(payload.get("tabs"), list):
            self._load_tabs_from_payload(payload["tabs"])

        timers_payload = payload.get("timers")
        trash_payload = payload.get("trash") if isinstance(payload.get("trash"), list) else []
        if not isinstance(timers_payload, list):
            timers_payload = []

        order_by_tab: dict[str, list[str]] = {}
        saved_order = payload.get("timer_order_by_tab")
        if isinstance(saved_order, dict):
            for tab_id, order in saved_order.items():
                if isinstance(tab_id, str) and isinstance(order, list):
                    order_by_tab[tab_id] = [tid for tid in order if isinstance(tid, str)]

        for entry in timers_payload:
            if not isinstance(entry, dict):
                continue
            default_tab_id = GENERAL_TAB_ID
            item = self._deserialize_timer(entry, default_tab_id)
            if not item:
                continue
            while item.timer_id in seen_ids:
                item.timer_id = str(uuid4())
            seen_ids.add(item.timer_id)
            self.timers[item.timer_id] = item

        for entry in trash_payload:
            if not isinstance(entry, dict):
                continue
            item = self._deserialize_timer(entry, TRASH_TAB_ID)
            if not item:
                continue
            item.tab_id = TRASH_TAB_ID
            if item.last_non_trash_tab_id not in self.tabs or item.last_non_trash_tab_id == TRASH_TAB_ID:
                item.last_non_trash_tab_id = GENERAL_TAB_ID
            while item.timer_id in seen_ids:
                item.timer_id = str(uuid4())
            seen_ids.add(item.timer_id)
            self.timers[item.timer_id] = item

        for tab_id in self._all_tab_ids():
            self.timer_order_by_tab[tab_id] = []

        for tab_id in self._all_tab_ids():
            explicit_order = order_by_tab.get(tab_id, [])
            for timer_id in explicit_order:
                item = self.timers.get(timer_id)
                if item and item.tab_id == tab_id and timer_id not in self.timer_order_by_tab[tab_id]:
                    self.timer_order_by_tab[tab_id].append(timer_id)

        for timer_id, item in self.timers.items():
            bucket = self._ensure_tab_order_bucket(item.tab_id)
            if timer_id not in bucket:
                bucket.append(timer_id)

        selected_tab_id = payload.get("selected_tab_id")
        if isinstance(selected_tab_id, str) and selected_tab_id in self.tabs:
            self.selected_tab_id = selected_tab_id
        else:
            self.selected_tab_id = GENERAL_TAB_ID

        self.state_dirty = False

    def _load_tabs_from_payload(self, tabs_payload: list[object]) -> None:
        tabs: dict[str, TabItem] = {
            GENERAL_TAB_ID: TabItem(tab_id=GENERAL_TAB_ID, name="General", is_system=True),
            TRASH_TAB_ID: TabItem(tab_id=TRASH_TAB_ID, name="Trash", is_system=True),
        }
        user_order: list[str] = []
        for entry in tabs_payload:
            if not isinstance(entry, dict):
                continue
            tab_id = entry.get("tab_id")
            name = entry.get("name")
            is_system = bool(entry.get("is_system", False))
            if not isinstance(tab_id, str) or not isinstance(name, str):
                continue
            if tab_id == GENERAL_TAB_ID:
                tabs[GENERAL_TAB_ID] = TabItem(tab_id=GENERAL_TAB_ID, name=name, is_system=True)
                continue
            if tab_id == TRASH_TAB_ID:
                tabs[TRASH_TAB_ID] = TabItem(tab_id=TRASH_TAB_ID, name=name, is_system=True)
                continue
            tabs[tab_id] = TabItem(tab_id=tab_id, name=name, is_system=is_system)
            user_order.append(tab_id)

        self.tabs = tabs
        self.user_tab_order = user_order
        self.timer_order_by_tab = {tab_id: [] for tab_id in self._all_tab_ids()}

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
