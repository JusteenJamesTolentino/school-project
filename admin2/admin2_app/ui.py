"""Tkinter interface for Admin 2: assign schedule entries built in Admin 1."""

from __future__ import annotations

import re
import sqlite3
import tkinter as tk
import webbrowser
from datetime import datetime
from html import escape
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from xml.etree import ElementTree

from admin2_app.schedule_import import (
    canonical_day,
    canonical_type,
    parse_time_range,
    read_schedule_xlsx,
)
from admin2_app.shared import Database, Schedule, THEMES

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
YEARS = ("1st Year", "2nd Year", "3rd Year", "4th Year")
SEMESTERS = ("1st Sem", "2nd Sem")
FILTER_ALL = "All"


class Admin2App:
    """Assign each part of a schedule entry and manage the schedule list."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.database = Database()
        configured = self.database.get_setting("database_path")
        if configured:
            configured_path = Path(configured)
            if configured_path != self.database.path and configured_path.exists():
                self.database.close()
                self.database = Database(configured_path)
        self.database.set_setting("database_path", str(self.database.path))
        self.theme_name = self.database.get_setting("theme", "light")
        if self.theme_name not in THEMES:
            self.theme_name = "light"
        self.COLORS = dict(THEMES[self.theme_name])

        self.root.title("Admin 2 - Scheduling Workspace")
        self.root.geometry("1280x760")
        self.root.minsize(900, 600)
        self.root.attributes("-fullscreen", True)
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.configure(bg=self.COLORS["background"])
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Destroy>", self._cancel_notice_callback, add="+")

        self.selected = {
            "department": tk.StringVar(), "program": tk.StringVar(),
            "professor": tk.StringVar(), "day": tk.StringVar(),
            "time": tk.StringVar(), "room": tk.StringVar(),
            "room_building": tk.StringVar(), "room_floor": tk.StringVar(),
            "subject": tk.StringVar(), "subject_type": tk.StringVar(),
        }
        self.time_start: int | None = None
        self.time_end: int | None = None
        self.subject_year = ""
        self.subject_semester = ""
        self.notice = tk.StringVar()
        self.notice_after_id: str | None = None
        self.filters = {
            "day": tk.StringVar(value=FILTER_ALL),
            "time": tk.StringVar(value=FILTER_ALL),
            "professor": tk.StringVar(value=FILTER_ALL),
            "program": tk.StringVar(value=FILTER_ALL),
            "type": tk.StringVar(value=FILTER_ALL),
        }
        self.logs: list[str] = []
        self.value_labels: dict[str, ttk.Label] = {}

        self._configure_styles()
        self._build_interface()
        self.log(f"Admin 2 started (database: {self.database.path})")
        self._refresh_schedule_list()
        self._update_conflict_warning()

    def _toggle_fullscreen(self, _event: tk.Event | None = None) -> None:
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def _close(self) -> None:
        if self.notice_after_id:
            self.root.after_cancel(self.notice_after_id)
            self.notice_after_id = None
        self.database.close()
        self.root.destroy()

    def _cancel_notice_callback(self, event: tk.Event) -> None:
        if event.widget is self.root and self.notice_after_id:
            self.root.after_cancel(self.notice_after_id)
            self.notice_after_id = None

    # ------------------------------------------------------------------ styles

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.COLORS["background"])
        style.configure("Panel.TFrame", background=self.COLORS["panel"])
        style.configure("Card.TFrame", background=self.COLORS["panel"], relief="flat", borderwidth=0)
        style.configure("Header.TLabel", background=self.COLORS["panel"],
                        font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", background=self.COLORS["panel"],
                        foreground=self.COLORS["muted"])
        style.configure("ColumnTitle.TLabel", background=self.COLORS["header"],
                        foreground=self.COLORS["primary_dark"], font=("Segoe UI", 9, "bold"))
        style.configure("Primary.TButton", background=self.COLORS["primary"], foreground="white",
                        padding=(14, 7), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Primary.TButton", background=[("active", self.COLORS["primary_hover"])])
        style.configure("Action.TButton", background=self.COLORS["button"],
                        foreground=self.COLORS["primary_dark"],
                        padding=(12, 7), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Action.TButton", background=[("active", self.COLORS["accent"])])
        style.configure("Danger.TButton", foreground=self.COLORS["danger"], padding=(8, 5))
        style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9),
                        background=self.COLORS["button"], foreground=self.COLORS["ink"])
        style.map("TButton", background=[("active", self.COLORS["accent"])])
        style.configure("TCombobox", padding=4, font=("Segoe UI", 9),
                        fieldbackground=self.COLORS["dropdown"], background=self.COLORS["dropdown"],
                        foreground=self.COLORS["ink"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", self.COLORS["dropdown"])],
                  background=[("readonly", self.COLORS["dropdown"])],
                  foreground=[("readonly", self.COLORS["ink"])])
        self.root.option_add("*TCombobox*Listbox.background", self.COLORS["dropdown"])
        self.root.option_add("*TCombobox*Listbox.foreground", self.COLORS["ink"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.COLORS["select_bg"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", self.COLORS["select_fg"])
        style.configure("TEntry", padding=6,
                        fieldbackground=self.COLORS["dropdown"], foreground=self.COLORS["ink"])
        style.configure("TLabel", background=self.COLORS["panel"], foreground=self.COLORS["ink"])
        style.configure("TRadiobutton", background=self.COLORS["panel"], foreground=self.COLORS["ink"])
        style.configure("Treeview", background=self.COLORS["surface"],
                        fieldbackground=self.COLORS["surface"], foreground=self.COLORS["ink"],
                        rowheight=26, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=self.COLORS["header"],
                        foreground=self.COLORS["primary_dark"],
                        font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Treeview",
                  background=[("selected", self.COLORS["select_bg"])],
                  foreground=[("selected", self.COLORS["select_fg"])])

    # ------------------------------------------------------------------ layout

    def _build_interface(self) -> None:
        self.outer = ttk.Frame(self.root)
        self.outer.pack(fill="both", expand=True, padx=12, pady=8)

        nav = ttk.Frame(self.outer, style="Card.TFrame", padding=(16, 10))
        nav.pack(fill="x", pady=(0, 10))
        ttk.Label(nav, text="ADMIN 2", style="ColumnTitle.TLabel").pack(side="left", padx=(4, 18))
        for label, command in (
            ("SET DEPARTMENT", self.set_department),
            ("SET PROGRAM", self.set_program),
            ("SET PROF", self.set_professor),
            ("SET DAY", self.set_day),
            ("SET TIME", self.set_time),
            ("SET ROOM", self.set_room),
            ("SET SUBJECT", self.set_subject),
            ("SET SUBJECT TYPE", self.set_subject_type),
        ):
            ttk.Button(nav, text=label, style="Action.TButton",
                       command=command).pack(side="left", padx=3)

        window_controls = ttk.Frame(nav, style="Card.TFrame")
        window_controls.pack(side="right", padx=(0, 2))
        ttk.Button(window_controls, text="—", width=3,
                   command=self.root.iconify).pack(side="left", padx=1)
        ttk.Button(window_controls, text="✕", width=3, style="Danger.TButton",
                   command=self._close).pack(side="left", padx=1)
        ttk.Button(nav, text="IMPORT SCHED", style="Primary.TButton",
                   command=self.import_schedule).pack(side="right", padx=3)
        ttk.Button(nav, text="⚙  Settings", style="Action.TButton",
                   command=self.open_settings_dialog).pack(side="right", padx=3)

        self.notice_label = tk.Label(
            self.outer, textvariable=self.notice, anchor="w",
            bg=self.COLORS["notice_bg"], fg=self.COLORS["notice_fg"],
            padx=12, pady=7, font=("Segoe UI", 9),
        )

        logs_card = ttk.Frame(self.outer, style="Card.TFrame", padding=(20, 10))
        logs_card.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Label(logs_card, text="LOGS", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.logs_listbox = self._listbox(logs_card)
        self.logs_listbox.configure(height=7)
        self.logs_listbox.pack(fill="x", pady=(8, 0))

        content = ttk.Frame(self.outer)
        content.pack(fill="both", expand=True)

        preview = ttk.Frame(content, style="Card.TFrame", padding=(20, 16))
        preview.pack(side="left", fill="y")
        preview.configure(width=400)
        preview.pack_propagate(False)
        self.summary_card = preview
        ttk.Label(preview, text="PREVIEW SCHED ENTRY",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        grid = ttk.Frame(preview, style="Panel.TFrame")
        grid.pack(fill="x", pady=(10, 8))
        titles = {
            "department": "Department", "program": "Program", "professor": "Professor",
            "day": "Day", "time": "Time", "room": "Room",
            "subject": "Subject", "subject_type": "Subject type",
        }
        self.value_labels = {}
        for row, key in enumerate(titles):
            ttk.Label(grid, text=titles[key], style="Header.TLabel").grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 24))
            value = ttk.Label(grid, text="Not set", style="Muted.TLabel", wraplength=280)
            value.grid(row=row, column=1, sticky="w", pady=3)
            self.value_labels[key] = value
        grid.columnconfigure(1, weight=1)
        self.conflict_label = tk.Label(
            preview, text="", anchor="w", wraplength=350,
            bg=self.COLORS["panel"], fg=self.COLORS["danger"],
            font=("Segoe UI", 9, "bold"), justify="left",
        )
        self.conflict_label.pack(anchor="w", fill="x", pady=(2, 8))
        actions = ttk.Frame(preview, style="Panel.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="ADD TO SCHEDULE", style="Primary.TButton",
                   command=self.add_to_schedule).pack(side="left")
        ttk.Button(actions, text="Clear", command=self.clear_entry).pack(side="left", padx=(8, 0))

        list_card = ttk.Frame(content, style="Card.TFrame", padding=(20, 12))
        list_card.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ttk.Label(list_card, text="SCHEDULES", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(list_card, text="Double-click a row to edit or delete it.",
                  style="Muted.TLabel").pack(anchor="w")
        filter_bar = ttk.Frame(list_card, style="Panel.TFrame")
        filter_bar.pack(fill="x", pady=(8, 8))
        self.filter_combos: dict[str, ttk.Combobox] = {}
        for key, label in (
            ("day", "Day"), ("time", "Time"), ("professor", "Professor"),
            ("program", "Program"), ("type", "Type"),
        ):
            ttk.Label(filter_bar, text=label, style="Muted.TLabel").pack(side="left", padx=(8, 3))
            combo = ttk.Combobox(
                filter_bar, textvariable=self.filters[key], state="readonly", width=16,
            )
            combo.pack(side="left")
            combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_schedule_list())
            self.filter_combos[key] = combo
        ttk.Button(filter_bar, text="Clear filters",
                   command=self.clear_filters).pack(side="left", padx=(10, 0))
        ttk.Button(filter_bar, text="⭳  EXPORT", style="Primary.TButton",
                   command=self.export_schedule).pack(side="right")

        table_frame = ttk.Frame(list_card, style="Panel.TFrame")
        table_frame.pack(fill="both", expand=True)
        columns = ("day", "time", "program", "year", "subject", "type", "professor", "room")
        self.schedule_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = ("Day", "Time", "Program", "Year", "Subject", "Type", "Professor", "Room")
        widths = (90, 170, 150, 80, 280, 90, 180, 80)
        for column, heading, width in zip(columns, headings, widths):
            self.schedule_tree.heading(column, text=heading)
            self.schedule_tree.column(column, width=width, anchor="w", stretch=False)
        self.schedule_vscroll = ttk.Scrollbar(table_frame, orient="vertical",
                                             command=self.schedule_tree.yview)
        self.schedule_hscroll = ttk.Scrollbar(table_frame, orient="horizontal",
                                             command=self.schedule_tree.xview)
        self.schedule_tree.configure(yscrollcommand=self.schedule_vscroll.set,
                                     xscrollcommand=self.schedule_hscroll.set)
        self.schedule_tree.bind(
            "<Double-Button-1>", lambda _event: self._on_schedule_activated())
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.schedule_tree.grid(row=0, column=0, sticky="nsew")
        self.schedule_vscroll.grid(row=0, column=1, sticky="ns")
        self.schedule_hscroll.grid(row=1, column=0, sticky="ew")

        self._refresh_summary()

    def _rebuild_interface(self) -> None:
        if hasattr(self, "outer") and self.outer.winfo_exists():
            self.outer.destroy()
        self._build_interface()
        self._replay_logs()
        self._refresh_schedule_list()
        self._update_conflict_warning()

    def _listbox(self, parent: tk.Widget) -> tk.Listbox:
        return tk.Listbox(
            parent, exportselection=False, borderwidth=0, relief="flat",
            activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            font=("Segoe UI", 9),
        )

    # ------------------------------------------------------------------ logs

    def log(self, message: str) -> None:
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.logs.append(entry)
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]
        if hasattr(self, "logs_listbox") and self.logs_listbox.winfo_exists():
            self.logs_listbox.insert("end", entry)
            self.logs_listbox.see("end")

    def _replay_logs(self) -> None:
        if hasattr(self, "logs_listbox") and self.logs_listbox.winfo_exists():
            for entry in self.logs:
                self.logs_listbox.insert("end", entry)
            self.logs_listbox.see("end")

    # ------------------------------------------------------------------ summary

    def _refresh_summary(self) -> None:
        for key, label in self.value_labels.items():
            value = self.selected[key].get()
            label.configure(text=value or "Not set")
            label.configure(foreground=self.COLORS["ink"] if value else self.COLORS["muted"])

    def _candidate_schedule(self) -> Schedule | None:
        subject = self.selected["subject"].get()
        if not (self.selected["department"].get() and self.selected["program"].get()
                and self.selected["professor"].get() and self.selected["day"].get()
                and subject and self.selected["subject_type"].get()
                and self.selected["room"].get()
                and self.time_start is not None and self.time_end is not None):
            return None
        return Schedule(
            department=self.selected["department"].get(),
            program=self.selected["program"].get(),
            subject=subject,
            subject_type=self.selected["subject_type"].get(),
            professor=self.selected["professor"].get(),
            day=self.selected["day"].get(),
            start_minutes=self.time_start,
            end_minutes=self.time_end,
            year=self.subject_year,
            semester=self.subject_semester,
            room=self.selected["room"].get(),
            room_building=self.selected["room_building"].get(),
            room_floor=self.selected["room_floor"].get(),
        )

    def _update_conflict_warning(self) -> None:
        if not hasattr(self, "conflict_label") or not self.conflict_label.winfo_exists():
            return
        candidate = self._candidate_schedule()
        if candidate is None:
            self.conflict_label.configure(text="")
            return
        conflicts = self.database.conflicting_schedules(candidate)
        if not conflicts:
            self.conflict_label.configure(text="")
            return
        details = "; ".join(
            f"{c.professor} — {c.day} {c.time_display} ({c.program})" for c in conflicts[:3]
        )
        self.conflict_label.configure(
            text=f"⚠ OVERLAP: {details}" + (" …" if len(conflicts) > 3 else "")
        )

    def clear_entry(self) -> None:
        for variable in self.selected.values():
            variable.set("")
        self.time_start = self.time_end = None
        self.subject_year = self.subject_semester = ""
        self._refresh_summary()
        self._update_conflict_warning()
        self.log("Preview entry cleared")

    # ------------------------------------------------------------------ dialogs

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _modal(self, title: str, size: str) -> tuple[tk.Toplevel, ttk.Frame]:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry(size)
        self._center_dialog(dialog)
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        return dialog, frame

    def _choice_modal(self, title: str, options: list[str], on_set,
                      note: str | None = None) -> None:
        dialog, frame = self._modal(title, "440x480")
        ttk.Label(frame, text=title, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        if note:
            ttk.Label(frame, text=note, style="Muted.TLabel",
                      wraplength=380).pack(anchor="w", pady=(3, 10))
        listing = self._listbox(frame)
        listing.configure(font=("Segoe UI", 10))
        listing.pack(fill="both", expand=True, pady=(12, 14))
        for option in options:
            listing.insert("end", option)

        def confirm() -> None:
            selection = listing.curselection()
            if not selection:
                self.show_notice("Select an item first")
                return
            on_set(options[selection[0]])
            dialog.destroy()

        listing.bind("<Double-Button-1>", lambda _event: confirm())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Set", style="Primary.TButton",
                   command=confirm).pack(side="right")

    # ------------------------------------------------------------------ setters

    def set_department(self) -> None:
        departments = self.database.load_departments()
        if not departments:
            self.show_notice("No departments yet — create them in Admin 1")
            return
        options = [f"{d.code} — {d.name}" for d in departments]

        def on_set(option: str) -> None:
            code = option.split(" — ", 1)[0]
            self.selected["department"].set(code)
            for key in ("program", "professor", "subject"):
                self.selected[key].set("")
            self.subject_year = self.subject_semester = ""
            self._after_selection(f"Department set to {code}")

        self._choice_modal("Set department", options, on_set)

    def set_program(self) -> None:
        department = self._department()
        if department is None:
            self.show_notice("Set a department first")
            return
        if not department.programs:
            self.show_notice("This department has no programs — create them in Admin 1")
            return

        def on_set(option: str) -> None:
            self.selected["program"].set(option)
            self.selected["subject"].set("")
            self.selected["professor"].set("")
            self.subject_year = self.subject_semester = ""
            self._after_selection(f"Program set to {option}")

        self._choice_modal("Set program", list(department.programs), on_set)

    def set_professor(self) -> None:
        professors = self.database.load_professors()
        department = self._department()
        if department is not None:
            professors = [p for p in professors if p.department == department.code]
        program = self.selected["program"].get()
        if program and department is not None:
            professors = [
                p for p in professors
                if (department.code, program) in p.programs
            ]
        if not professors:
            self.show_notice("No professors available — create them in Admin 1")
            return
        options = [f"{p.name} ({p.department})" for p in professors]

        def on_set(option: str) -> None:
            name = option.rsplit(" (", 1)[0]
            self.selected["professor"].set(name)
            self._after_selection(f"Professor set to {name}")

        self._choice_modal("Set professor", options, on_set)

    def set_day(self) -> None:
        def on_set(option: str) -> None:
            self.selected["day"].set(option)
            self._after_selection(f"Day set to {option}")

        self._choice_modal("Set day", list(DAYS), on_set)

    def set_room(self) -> None:
        details = self.database.load_room_details()
        room_by_name: dict[str, list[str]] = {}
        for detail in details:
            room_by_name.setdefault(detail.rsplit(" / ", 1)[-1], []).append(detail)
        rooms = []
        for room in sorted(room_by_name):
            rooms.extend(
                [room] if len(room_by_name[room]) == 1 else room_by_name[room]
            )
        room_locations = {
            room: detail for room, values in room_by_name.items()
            if len(values) == 1 for detail in values
        }
        room_locations.update({detail: detail for detail in details})
        if not rooms:
            self.show_notice("No rooms available — create them in Admin 1")
            return

        def on_set(option: str) -> None:
            detail = room_locations[option]
            building, floor, room = detail.split(" / ", 2)
            self.selected["room"].set(room)
            self.selected["room_building"].set(building)
            self.selected["room_floor"].set(floor)
            self._after_selection(f"Room set to {option}")

        self._choice_modal("Set room", rooms, on_set)

    def set_subject_type(self) -> None:
        def on_set(option: str) -> None:
            self.selected["subject_type"].set(option)
            self._after_selection(f"Subject type set to {option}")

        self._choice_modal("Set subject type", ["Laboratory", "Lecture"], on_set)

    def _time_options(self) -> list[str]:
        return [self._format_time(m) for m in range(7 * 60, 21 * 60 + 1, 30)]

    def set_time(self) -> None:
        dialog, frame = self._modal("Set time", "420x330")
        ttk.Label(frame, text="Set time", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Pick a start and end time.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 12))
        options = self._time_options()
        start = tk.StringVar(value=self._format_time(self.time_start) if self.time_start is not None
                             else options[0])
        end = tk.StringVar(value=self._format_time(self.time_end) if self.time_end is not None
                           else options[12])
        ttk.Label(frame, text="Start", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        start_combo = ttk.Combobox(frame, textvariable=start, state="readonly",
                                   values=options)
        start_combo.pack(fill="x", pady=(4, 10))
        ttk.Label(frame, text="End", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        end_combo = ttk.Combobox(frame, textvariable=end, state="readonly", values=options)
        end_combo.pack(fill="x", pady=(4, 16))

        def confirm() -> None:
            start_minutes = self._parse_display_time(start.get())
            end_minutes = self._parse_display_time(end.get())
            if start_minutes is None or end_minutes is None or start_minutes >= end_minutes:
                self.show_notice("Choose an end time after the start time")
                return
            self.time_start, self.time_end = start_minutes, end_minutes
            display = f"{self._format_time(start_minutes)} - {self._format_time(end_minutes)}"
            self.selected["time"].set(display)
            self._after_selection(f"Time set to {display}")
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Set", style="Primary.TButton",
                   command=confirm).pack(side="right")

    def set_subject(self) -> None:
        department = self._department()
        program = self.selected["program"].get()
        if department is None or not program:
            self.show_notice("Set a department and program first")
            return
        curriculum = self.database.load_curriculum(program, department.code)
        if not any(subjects for semesters in curriculum.values()
                   for subjects in semesters.values()):
            self.show_notice("This program has no curriculum — import it in Admin 1")
            return

        dialog, frame = self._modal("Set subject", "480x520")
        ttk.Label(frame, text="Set subject", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        selectors = ttk.Frame(frame)
        selectors.pack(fill="x", pady=(10, 8))
        year = tk.StringVar(value=self.subject_year or YEARS[0])
        semester = tk.StringVar(value=self.subject_semester or SEMESTERS[0])
        ttk.Combobox(selectors, textvariable=year, state="readonly", values=YEARS,
                     width=12).pack(side="left")
        ttk.Combobox(selectors, textvariable=semester, state="readonly", values=SEMESTERS,
                     width=10).pack(side="left", padx=(10, 0))
        listing = self._listbox(frame)
        listing.configure(font=("Segoe UI", 10))
        listing.pack(fill="both", expand=True, pady=(8, 14))

        def subjects() -> list[str]:
            return curriculum.get(year.get(), {}).get(semester.get(), [])

        def rebuild(_event=None) -> None:
            listing.delete(0, "end")
            for subject in subjects():
                listing.insert("end", subject)
            current = self.selected["subject"].get()
            if current in subjects():
                listing.selection_set(subjects().index(current))

        def confirm() -> None:
            selection = listing.curselection()
            if not selection:
                self.show_notice("Select a subject first")
                return
            subject = listing.get(selection[0])
            self.selected["subject"].set(subject)
            self.subject_year, self.subject_semester = year.get(), semester.get()
            self._after_selection(f"Subject set to {subject}")
            dialog.destroy()

        year.trace_add("write", lambda *_: rebuild())
        semester.trace_add("write", lambda *_: rebuild())
        rebuild()
        listing.bind("<Double-Button-1>", lambda _event: confirm())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Set", style="Primary.TButton",
                   command=confirm).pack(side="right")

    def _after_selection(self, message: str) -> None:
        self._refresh_summary()
        self._update_conflict_warning()
        self.log(message)
        self.show_notice(message)

    @staticmethod
    def _canonical_year(text: str) -> str:
        year = text.strip()
        for known in YEARS:
            if year.lower() == known.lower():
                return known
        return year

    def _department(self):
        code = self.selected["department"].get()
        return next((d for d in self.database.load_departments() if d.code == code), None)

    @staticmethod
    def _format_time(minutes: int) -> str:
        hour, minute = divmod(minutes, 60)
        suffix = "PM" if hour >= 12 else "AM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {suffix}"

    @staticmethod
    def _parse_display_time(text: str) -> int | None:
        from admin2_app.schedule_import import parse_time

        try:
            return parse_time(text)
        except ValueError:
            return None

    # ------------------------------------------------------------------ add / list

    def add_to_schedule(self) -> None:
        candidate = self._candidate_schedule()
        if candidate is None:
            self.show_notice("Set all schedule fields before adding")
            self.log("Add blocked: preview entry incomplete")
            return
        conflicts = self.database.conflicting_schedules(candidate)
        if conflicts:
            details = "\n".join(
                f"• {c.professor} — {c.day} {c.time_display} ({c.program} {c.subject})"
                for c in conflicts[:5]
            )
            proceed = messagebox.askyesno(
                "Schedule overlap",
                "This entry overlaps an existing schedule:\n\n" + details +
                "\n\nAdd it anyway?",
                icon="warning", parent=self.root,
            )
            if not proceed:
                self.log("Add cancelled: overlap warning declined")
                return
        try:
            self.database.add_schedule(candidate)
        except sqlite3.Error as error:
            self.show_notice(f"Could not add schedule: {error}")
            return
        self.log(
            f"Schedule added: {candidate.subject} — {candidate.day} "
            f"{candidate.time_display} ({candidate.professor})"
            + (" — despite overlap warning" if conflicts else "")
        )
        if conflicts:
            self.log(f"Overlap warning accepted for {len(conflicts)} existing entr"
                     f"{'y' if len(conflicts) == 1 else 'ies'}")
        for key in ("professor", "day", "time", "room", "room_building", "room_floor", "subject", "subject_type"):
            self.selected[key].set("")
        self.time_start = self.time_end = None
        self.subject_year = self.subject_semester = ""
        self._refresh_summary()
        self._update_conflict_warning()
        self._refresh_schedule_list()
        self.show_notice("Schedule added")

    def _all_schedules(self) -> list[Schedule]:
        return self.database.load_schedules()

    def _filtered_schedules(self) -> list[Schedule]:
        def keep(schedule: Schedule) -> bool:
            if self.filters["day"].get() not in (FILTER_ALL, schedule.day):
                return False
            time_filter = self.filters["time"].get()
            if time_filter == "AM" and schedule.start_minutes >= 12 * 60:
                return False
            if time_filter == "PM" and schedule.start_minutes < 12 * 60:
                return False
            if self.filters["professor"].get() not in (FILTER_ALL, schedule.professor):
                return False
            if self.filters["program"].get() not in (FILTER_ALL, schedule.program):
                return False
            if self.filters["type"].get() not in (FILTER_ALL, schedule.subject_type):
                return False
            return True

        return [schedule for schedule in self._all_schedules() if keep(schedule)]

    def _refresh_schedule_list(self) -> None:
        schedules = self._all_schedules()
        options = {
            "day": [FILTER_ALL] + list(DAYS),
            "time": [FILTER_ALL, "AM", "PM"],
            "professor": [FILTER_ALL] + sorted({s.professor for s in schedules}),
            "program": [FILTER_ALL] + sorted({s.program for s in schedules}),
            "type": [FILTER_ALL, "Laboratory", "Lecture"],
        }
        for key, combo in self.filter_combos.items():
            current = self.filters[key].get()
            combo.configure(values=options[key])
            if current not in options[key]:
                self.filters[key].set(FILTER_ALL)
        self.schedule_tree.delete(*self.schedule_tree.get_children())
        for schedule in self._filtered_schedules():
            self.schedule_tree.insert(
                "", "end", iid=str(schedule.id),
                values=(schedule.day, schedule.time_display, schedule.program, schedule.year,
                        schedule.subject, schedule.subject_type, schedule.professor,
                        schedule.room),
            )

    def clear_filters(self) -> None:
        for variable in self.filters.values():
            variable.set(FILTER_ALL)
        self._refresh_schedule_list()
        self.log("Filters cleared")

    def delete_selected_schedule(self) -> None:
        selection = self.schedule_tree.selection()
        if not selection:
            self.show_notice("Select a schedule row first")
            return
        schedule_id = int(selection[0])
        schedule = next((s for s in self._all_schedules() if s.id == schedule_id), None)
        name = f"{schedule.subject} ({schedule.day} {schedule.time_display})" if schedule else str(schedule_id)
        if not messagebox.askyesno(
            "Delete schedule",
            f"This will permanently delete:\n\n• {name}",
            icon="warning", parent=self.root,
        ):
            return
        try:
            self.database.delete_schedule(schedule_id)
        except sqlite3.Error as error:
            self.show_notice(f"Could not delete schedule: {error}")
            return
        self.log(f"Schedule deleted: {name}")
        self._refresh_schedule_list()
        self._update_conflict_warning()
        self.show_notice("Schedule deleted")

    def _on_schedule_activated(self) -> None:
        selection = self.schedule_tree.selection()
        if selection:
            self._open_schedule_options(int(selection[0]))

    def _open_schedule_options(self, schedule_id: int) -> None:
        schedule = next((s for s in self._all_schedules() if s.id == schedule_id), None)
        if schedule is None:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Schedule options")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("340x270")
        self._center_dialog(dialog)
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=schedule.subject, font=("Segoe UI", 13, "bold"),
                  wraplength=280).pack(anchor="w")
        ttk.Label(
            frame,
            text=f"{schedule.day} {schedule.time_display} — {schedule.program}",
            style="Muted.TLabel", wraplength=280,
        ).pack(anchor="w", pady=(2, 16))
        ttk.Button(
            frame, text="Edit", style="Action.TButton",
            command=lambda: (dialog.destroy(), self._open_edit_schedule_dialog(schedule)),
        ).pack(fill="x", pady=(0, 8))
        ttk.Button(
            frame, text="Delete", style="Danger.TButton",
            command=lambda: (dialog.destroy(), self.delete_selected_schedule()),
        ).pack(fill="x", pady=(0, 8))
        ttk.Button(frame, text="Cancel", command=dialog.destroy).pack(fill="x")

    def _open_edit_schedule_dialog(self, schedule: Schedule) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit schedule")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("480x600")
        self._center_dialog(dialog)
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Edit schedule", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=f"{schedule.program} ({schedule.department}) — "
                 f"{schedule.year or 'no year'} {schedule.semester}".strip(),
            style="Muted.TLabel", wraplength=400,
        ).pack(anchor="w", pady=(3, 14))

        curriculum = self.database.load_curriculum(
            schedule.program, schedule.department
        ) if schedule.program and schedule.department else {}
        subject_options = curriculum.get(
            schedule.year or YEARS[0], {}
        ).get(schedule.semester or SEMESTERS[0], []) or [schedule.subject]
        professor_options = sorted({p.name for p in self.database.load_professors()})
        if schedule.professor not in professor_options:
            professor_options = [schedule.professor] + professor_options
        room_options = [""] + self.database.load_room_details()
        current_room = " / ".join(
            part for part in (schedule.room_building, schedule.room_floor, schedule.room)
            if part
        )
        if current_room and current_room not in room_options:
            room_options = [current_room] + room_options
        time_options = self._time_options()

        fields: list[tuple[str, tk.StringVar, list[str]]] = [
            ("Subject", tk.StringVar(value=schedule.subject), subject_options),
            ("Subject type", tk.StringVar(value=schedule.subject_type),
             ["Laboratory", "Lecture"]),
            ("Professor", tk.StringVar(value=schedule.professor), professor_options),
            ("Day", tk.StringVar(value=schedule.day), list(DAYS)),
            ("Start", tk.StringVar(value=self._format_time(schedule.start_minutes)),
             time_options),
            ("End", tk.StringVar(value=self._format_time(schedule.end_minutes)),
             time_options),
            ("Room", tk.StringVar(value=current_room), room_options),
        ]
        for label, variable, values in fields:
            ttk.Label(frame, text=label, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            ttk.Combobox(frame, textvariable=variable, values=values,
                         width=30).pack(anchor="w", pady=(3, 8), ipady=2)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons, text="Save changes", style="Primary.TButton",
            command=lambda: self._save_schedule_edit(schedule, fields, dialog),
        ).pack(side="right")

    def _save_schedule_edit(self, schedule: Schedule,
                            fields: list[tuple[str, tk.StringVar, list[str]]],
                            dialog: tk.Toplevel) -> None:
        values = {label: variable.get().strip() for label, variable, _ in fields}
        if not all(values[label] for label in
                   ("Subject", "Subject type", "Professor", "Day")):
            self.show_notice("Subject, type, professor, and day cannot be empty")
            return
        start_minutes = self._parse_display_time(values["Start"])
        end_minutes = self._parse_display_time(values["End"])
        if start_minutes is None or end_minutes is None or start_minutes >= end_minutes:
            self.show_notice("Choose an end time after the start time")
            return
        updated = Schedule(
            department=schedule.department, program=schedule.program,
            subject=values["Subject"], subject_type=values["Subject type"],
            professor=values["Professor"], day=values["Day"],
            start_minutes=start_minutes, end_minutes=end_minutes,
            year=schedule.year, semester=schedule.semester,
            room=values["Room"].split(" / ")[2]
            if len(values["Room"].split(" / ")) == 3 else values["Room"],
            room_building=values["Room"].split(" / ")[0]
            if len(values["Room"].split(" / ")) == 3 else "",
            room_floor=values["Room"].split(" / ")[1]
            if len(values["Room"].split(" / ")) == 3 else "",
            id=schedule.id,
        )
        conflicts = self.database.conflicting_schedules(updated, exclude_id=schedule.id)
        if conflicts:
            details = "\n".join(
                f"• {c.professor} — {c.day} {c.time_display} ({c.program} {c.subject})"
                for c in conflicts[:5]
            )
            proceed = messagebox.askyesno(
                "Schedule overlap",
                "Your changes overlap another schedule:\n\n" + details + "\n\nSave anyway?",
                icon="warning", parent=self.root,
            )
            if not proceed:
                self.log("Edit cancelled: overlap warning declined")
                return
        try:
            self.database.update_schedule(updated)
        except sqlite3.Error as error:
            self.show_notice(f"Could not save schedule: {error}")
            return
        dialog.destroy()
        self.log(
            f"Schedule updated: {updated.subject} — {updated.day} {updated.time_display}"
            + (" — despite overlap warning" if conflicts else "")
        )
        self._refresh_schedule_list()
        self._update_conflict_warning()
        self.show_notice("Schedule updated")

    # ------------------------------------------------------------------ import / export

    def import_schedule(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return
        if Path(path).suffix.lower() != ".xlsx":
            self.show_notice("Please select an XLSX schedule workbook")
            return
        try:
            rows = read_schedule_xlsx(Path(path))
        except (ValueError, OSError, KeyError, ElementTree.ParseError) as error:
            self.show_notice(f"Could not read workbook: {error}")
            self.log(f"Import failed: {error}")
            return

        def name_key(name: str) -> str:
            return re.sub(r"[^a-z0-9]", "", name.lower())

        programs = {
            name_key(program): (department.code, program)
            for department in self.database.load_departments()
            for program in department.programs
        }
        professors = {
            name_key(professor.name): professor.name
            for professor in self.database.load_professors()
        }
        reference_data_exists = bool(programs or professors)

        accepted = 0
        skipped_conflict = 0
        skipped_invalid = 0
        unmatched = 0
        pending: list[Schedule] = []
        for row in rows:
            program_text = " ".join(row.get("program", "").split())
            professor_text = " ".join(row.get("professor", "").split())
            subject = " ".join(row.get("subject", "").split())
            try:
                if not program_text:
                    raise ValueError("empty program")
                if not professor_text:
                    raise ValueError("empty professor")
                if not subject:
                    raise ValueError("empty subject")
                day = canonical_day(row.get("day", ""))
                subject_type = canonical_type(row.get("subject_type", ""))
                start_minutes, end_minutes = parse_time_range(row.get("time", ""))
            except ValueError as error:
                skipped_invalid += 1
                self.log(f"Import skipped row: {error}")
                continue
            matched_program = programs.get(name_key(program_text))
            matched_professor = professors.get(name_key(professor_text))
            if matched_program is None or matched_professor is None:
                if reference_data_exists:
                    unmatched += 1
                    missing = []
                    if matched_program is None:
                        missing.append(f"program '{program_text}'")
                    if matched_professor is None:
                        missing.append(f"professor '{professor_text}'")
                    self.log("Import skipped: " + " and ".join(missing)
                             + " is not set up in Admin 1")
                    skipped_invalid += 1
                    continue
                unmatched += 1
                missing = []
                if matched_program is None:
                    missing.append(f"program '{program_text}'")
                if matched_professor is None:
                    missing.append(f"professor '{professor_text}'")
                self.log(
                    "Import note: " + " and ".join(missing)
                    + " not set up in Admin 1 — imported with the workbook values"
                )
            entry = Schedule(
                department=matched_program[0] if matched_program else "",
                program=matched_program[1] if matched_program else program_text,
                subject=subject,
                subject_type=subject_type,
                professor=matched_professor or professor_text,
                day=day,
                start_minutes=start_minutes, end_minutes=end_minutes,
                room=row.get("room", ""),
                year=self._canonical_year(row.get("year", "")),
            )
            conflicts = self.database.conflicting_schedules(entry) + [
                earlier for earlier in pending
                if self.database.schedules_conflict(earlier, entry)
            ]
            if conflicts:
                skipped_conflict += 1
                self.log(
                    f"Import skipped (overlap): {subject} — {day} "
                    f"{entry.time_display} ({entry.professor})"
                )
                continue
            try:
                self.database.add_schedule(entry)
            except sqlite3.Error as error:
                skipped_invalid += 1
                self.log(f"Import skipped row: {error}")
                continue
            pending.append(entry)
            accepted += 1

        summary = (f"Imported {accepted} schedule{'s' if accepted != 1 else ''}"
                   f", skipped {skipped_conflict} overlap"
                   f"{'' if skipped_conflict == 1 else 's'}"
                   f", {skipped_invalid} invalid")
        if unmatched:
            summary += f" ({unmatched} row{'s' if unmatched != 1 else ''} used workbook values for program/professor)"
        self.log(f"Import finished: {summary}")
        self.show_notice(summary)
        self._refresh_schedule_list()
        self._update_conflict_warning()

    def export_schedule(self) -> None:
        schedules = self._filtered_schedules()
        if not schedules:
            self.show_notice("Nothing to export with the current filters")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".html", initialfile="schedule.html",
            filetypes=[("HTML document", "*.html"), ("All files", "*.*")],
        )
        if not path:
            return
        active_filters = ", ".join(
            f"{key}={variable.get()}" for key, variable in self.filters.items()
            if variable.get() != FILTER_ALL
        ) or "none"
        rows = "\n".join(
            "<tr>"
            + "".join(f"<td>{value}</td>" for value in (
                escape(s.day), escape(s.time_display), escape(s.program), escape(s.year),
                escape(s.subject), escape(s.subject_type), escape(s.professor),
                escape(s.room),
            ))
            + "</tr>"
            for s in schedules
        )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Class Schedule</title>
<style>
 body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 24px; }}
 h1 {{ font-size: 20px; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border: 1px solid #9aa0a6; padding: 6px 10px; font-size: 12px; text-align: left; }}
 th {{ background: #1e3a8a; color: #fff; }}
 tr:nth-child(even) td {{ background: #f3f4f6; }}
</style></head>
<body>
<h1>Class Schedule</h1>
<p>Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} — filters: {active_filters}</p>
<table>
<tr><th>Day</th><th>Time</th><th>Program</th><th>Year</th><th>Subject</th>
<th>Type</th><th>Professor</th><th>Room</th></tr>
{rows}
</table>
</body></html>
"""
        try:
            Path(path).write_text(html, encoding="utf-8")
        except OSError as error:
            self.show_notice(f"Could not export: {error}")
            return
        self.log(f"Exported {len(schedules)} schedule rows to {path}")
        self.show_notice(f"Exported {len(schedules)} rows — use Print in your browser")
        webbrowser.open(Path(path).resolve().as_uri())

    # ------------------------------------------------------------------ notice / theme / settings

    def show_notice(self, message: str) -> None:
        self.notice.set(message)
        if not self.notice_label.winfo_ismapped():
            self.notice_label.pack(fill="x", pady=(0, 10), before=self.summary_card.master)
        if self.notice_after_id:
            self.root.after_cancel(self.notice_after_id)
        self.notice_after_id = self.root.after(3000, self._hide_notice)

    def _hide_notice(self) -> None:
        self.notice.set("")
        if self.notice_label.winfo_exists():
            self.notice_label.pack_forget()
        self.notice_after_id = None

    def _apply_theme(self, theme_name: str) -> None:
        if theme_name not in THEMES:
            return
        self.theme_name = theme_name
        self.COLORS = dict(THEMES[theme_name])
        self.database.set_setting("theme", theme_name)
        self.root.configure(bg=self.COLORS["background"])
        self._configure_styles()
        self._rebuild_interface()
        self.log(f"Theme changed to {theme_name}")

    def open_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("460x340")
        self._center_dialog(dialog)
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Settings", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Theme changes apply immediately and are remembered next time you open the app.",
            style="Muted.TLabel", wraplength=380,
        ).pack(anchor="w", pady=(3, 16))
        ttk.Label(frame, text="Theme", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        theme = tk.StringVar(value=self.theme_name)
        for value, label in (("light", "Light"), ("dark", "Dark")):
            ttk.Radiobutton(
                frame, text=label, value=value, variable=theme,
                command=lambda: self._apply_theme(theme.get()),
            ).pack(anchor="w", pady=(4, 0))
        ttk.Label(frame, text="Database", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(18, 4))
        self.database_path_label = ttk.Label(
            frame, text=str(self.database.path), style="Muted.TLabel", wraplength=380,
        )
        self.database_path_label.pack(anchor="w")
        ttk.Button(
            frame, text="Change database location...",
            command=self._choose_database_location,
        ).pack(anchor="w", pady=(6, 0))
        ttk.Button(frame, text="Close", command=dialog.destroy).pack(anchor="e", pady=(18, 0))

    def _choose_database_location(self) -> None:
        directory = filedialog.askdirectory(title="Choose or create a folder for the database")
        if not directory:
            return
        self._move_database(Path(directory))

    def _move_database(self, directory: Path) -> None:
        target = directory / "scheduling.db"
        current = self.database.path
        if target == current:
            self.show_notice("The database is already stored in that folder")
            return
        created = not target.exists()
        try:
            self.database.set_setting("database_path", str(target))
            self.database.close()
            if not directory.exists():
                directory.mkdir(parents=True)
            moved = Database(target)
        except (OSError, sqlite3.Error) as error:
            self.show_notice(f"Could not create the database: {error}")
            self.database = Database(current)
            self.database.set_setting("database_path", str(current))
            return
        self.database = moved
        self.database.set_setting("database_path", str(target))
        for variable in self.selected.values():
            variable.set("")
        self.time_start = self.time_end = None
        for variable in self.filters.values():
            variable.set(FILTER_ALL)
        self._apply_theme(self.database.get_setting("theme") or "light")
        if hasattr(self, "database_path_label") and self.database_path_label.winfo_exists():
            self.database_path_label.configure(text=str(target))
        if created:
            self.show_notice(f"New database created in {directory}")
        else:
            self.show_notice(f"Using existing database in {directory}")
        self.log(f"Database switched to {target} ({'new' if created else 'existing'})")
