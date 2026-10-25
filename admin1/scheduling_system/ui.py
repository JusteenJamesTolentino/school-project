"""Tkinter user interface for the scheduling system."""

from __future__ import annotations

import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable
from xml.etree import ElementTree

from scheduling_system.curriculum import read_xlsx
from scheduling_system.database import Database
from scheduling_system.models import Department, Professor


class SchedulingApp:
    """Manage the scheduling workspace and its editable reference data."""

    THEMES = {
        "light": {
            "background": "#f1f5f9",
            "panel": "#ffffff",
            "border": "#dbe3ee",
            "muted": "#64748b",
            "primary": "#2563eb",
            "primary_hover": "#1e40af",
            "primary_dark": "#1e40af",
            "header": "#eff6ff",
            "ink": "#0f172a",
            "danger": "#dc2626",
            "surface": "#f8fafc",
            "select_bg": "#dbeafe",
            "select_fg": "#1d4ed8",
            "highlight": "#93c5fd",
            "notice_bg": "#dbeafe",
            "notice_fg": "#1e3a8a",
            "accent": "#e0ebff",
            "button": "#ffffff",
            "dropdown": "#ffffff",
        },
        "dark": {
            "background": "#1f1e1d",
            "panel": "#171616",
            "border": "#383130",
            "muted": "#a8a29e",
            "primary": "#3b82f6",
            "primary_hover": "#1d4ed8",
            "primary_dark": "#d6d3d1",
            "header": "#292626",
            "ink": "#e8e6e3",
            "danger": "#f87171",
            "surface": "#292626",
            "select_bg": "#3f3835",
            "select_fg": "#f5f3f0",
            "highlight": "#57504b",
            "notice_bg": "#292626",
            "notice_fg": "#e8e6e3",
            "accent": "#292626",
            "button": "#171616",
            "dropdown": "#292626",
        },
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.database = Database()
        self.theme_name = self.database.get_setting("theme", "light")
        if self.theme_name not in self.THEMES:
            self.theme_name = "light"
        self.COLORS = dict(self.THEMES[self.theme_name])

        self.root.title("Admin 1 - Scheduling Workspace")
        self.root.geometry("1280x760")
        self.root.minsize(900, 600)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass
        self.root.configure(bg=self.COLORS["background"])

        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.departments = self.database.load_departments()
        self.professors = self.database.load_professors()
        self.selected_department = tk.StringVar()
        self.selected_program = tk.StringVar()
        self.selected_period = tk.StringVar(value="AM")
        self.selected_floor = tk.StringVar()
        self.selected_year = tk.StringVar(value="1st Year")
        self.selected_day = tk.StringVar()
        self.selected_time = tk.StringVar()
        self.selected_room = tk.StringVar()
        self.selected_subject_type = tk.StringVar()
        self.curriculum: dict[str, dict[str, list[str]]] = {}
        self.notice = tk.StringVar()
        self.department_combo: ttk.Combobox
        self.program_list: tk.Listbox
        self.professor_list: tk.Listbox
        self.notice_after_id: str | None = None

        self._configure_styles()
        self._build_interface()
        self._refresh_board()

    def _close(self) -> None:
        self.database.close()
        self.root.destroy()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.COLORS["background"])
        style.configure("Panel.TFrame", background=self.COLORS["panel"])
        style.configure("Card.TFrame", background=self.COLORS["panel"], relief="flat", borderwidth=0)
        style.configure("Header.TLabel", background=self.COLORS["panel"], font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=self.COLORS["background"], font=("Segoe UI", 30, "bold"))
        style.configure("Muted.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["muted"])
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
        style.configure("TCheckbutton", background=self.COLORS["panel"], foreground=self.COLORS["ink"])
        style.configure("TRadiobutton", background=self.COLORS["panel"], foreground=self.COLORS["ink"])
        style.configure("TLabelframe", background=self.COLORS["panel"], foreground=self.COLORS["ink"])
        style.configure("TLabelframe.Label", background=self.COLORS["panel"],
                        foreground=self.COLORS["ink"])

    def _apply_theme(self, theme_name: str) -> None:
        if theme_name not in self.THEMES:
            return
        self.theme_name = theme_name
        self.COLORS = dict(self.THEMES[theme_name])
        self.database.set_setting("theme", theme_name)
        self.root.configure(bg=self.COLORS["background"])
        self._configure_styles()
        self.notice_label.configure(
            bg=self.COLORS["notice_bg"], fg=self.COLORS["notice_fg"],
        )
        self.board_canvas.configure(background=self.COLORS["surface"])
        self._refresh_board()

    def open_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("440x240")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Settings", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Theme changes apply immediately and are remembered next time you open the app.",
            style="Muted.TLabel", wraplength=360,
        ).pack(anchor="w", pady=(3, 16))
        ttk.Label(frame, text="Theme", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        theme = tk.StringVar(value=self.theme_name)
        for value, label in (("light", "Light"), ("dark", "Dark")):
            ttk.Radiobutton(
                frame, text=label, value=value, variable=theme,
                command=lambda: self._apply_theme(theme.get()),
            ).pack(anchor="w", pady=(4, 0))
        ttk.Button(frame, text="Close", command=dialog.destroy).pack(anchor="e", pady=(18, 0))

    def _build_interface(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=28, pady=24)

        action_bar = ttk.Frame(outer, style="Card.TFrame", padding=(16, 10))
        action_bar.pack(fill="x", pady=(0, 12))
        ttk.Label(action_bar, text="ADMIN 1", style="ColumnTitle.TLabel").pack(side="left", padx=(4, 18))
        ttk.Button(action_bar, text="+  Department", style="Action.TButton",
                   command=self.open_department_dialog).pack(side="left", padx=3)
        ttk.Button(action_bar, text="+  Program", style="Action.TButton",
                   command=self.open_program_dialog).pack(side="left", padx=3)
        ttk.Button(action_bar, text="+  Professor", style="Action.TButton",
                   command=self.open_professor_dialog).pack(side="left", padx=3)
        ttk.Button(action_bar, text="+  Room", style="Action.TButton",
                   command=self.open_room_dialog).pack(side="left", padx=3)
        ttk.Button(action_bar, text="+  Subject", style="Action.TButton",
                   command=self.open_subject_dialog).pack(side="left", padx=3)
        ttk.Button(action_bar, text="IMPORT SUBJECT", style="Primary.TButton",
                   command=self.import_file).pack(side="right", padx=3)
        ttk.Button(action_bar, text="⚙  Settings", style="Action.TButton",
                   command=self.open_settings_dialog).pack(side="right", padx=3)

        self.notice_label = tk.Label(
            outer, textvariable=self.notice, anchor="w",
            bg=self.COLORS["notice_bg"], fg=self.COLORS["notice_fg"],
            padx=12, pady=7, font=("Segoe UI", 9),
        )

        self.board_holder = ttk.Frame(outer, style="Card.TFrame")
        self.board_holder.pack(fill="both", expand=True)
        self.board_canvas = tk.Canvas(self.board_holder, background=self.COLORS["surface"],
                                      highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.board_holder, orient="horizontal", command=self.board_canvas.xview)
        self.board_canvas.configure(xscrollcommand=scrollbar.set)
        self.board_canvas.pack(fill="both", expand=True)
        scrollbar.pack(fill="x")
        self.board = ttk.Frame(self.board_canvas, style="Panel.TFrame")
        self.board_window = self.board_canvas.create_window((0, 0), window=self.board, anchor="nw")
        self.board.bind("<Configure>", lambda _event: self.board_canvas.configure(
            scrollregion=self.board_canvas.bbox("all")))
        self.board_canvas.bind("<Configure>", self._resize_board)

    def _resize_board(self, event: tk.Event) -> None:
        self.board_canvas.itemconfigure(self.board_window, height=max(event.height, 410))

    def _column(self, title: str, width: int,
                control_factory: Callable[[ttk.Frame], ttk.Widget] | None = None
                ) -> tuple[ttk.Frame, ttk.Frame]:
        frame = ttk.Frame(self.board, style="Panel.TFrame", width=width)
        frame.pack(side="left", fill="y")
        frame.pack_propagate(False)
        title_row = tk.Frame(frame, background=self.COLORS["header"], height=42)
        title_row.pack(fill="x", padx=1, pady=(1, 0))
        title_row.pack_propagate(False)
        tk.Label(title_row, text=title.upper(), background=self.COLORS["header"],
                 foreground=self.COLORS["primary_dark"], font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(side="left", fill="x", expand=True, padx=(11, 4))
        if control_factory is not None:
            control = control_factory(title_row)
            control.pack(side="right", padx=(6, 0))
        separator = ttk.Separator(frame, orient="horizontal")
        separator.pack(fill="x")
        content = ttk.Frame(frame, style="Panel.TFrame")
        content.pack(fill="both", expand=True, padx=12, pady=12)
        return frame, content

    def _refresh_board(self) -> None:
        for child in self.board.winfo_children():
            child.destroy()
        if self.selected_department.get() not in [d.code for d in self.departments]:
            self.selected_department.set("")
        department = self._active_department()
        if department and self.selected_program.get() in department.programs:
            self.curriculum = self.database.load_curriculum(
                self.selected_program.get(), department.code
            )
        else:
            self.curriculum = {}

        def create_department_combo(parent: ttk.Frame) -> ttk.Combobox:
            self.department_combo = ttk.Combobox(
                parent, textvariable=self.selected_department,
                state="readonly", width=9,
                values=["Select"] + [d.code for d in self.departments],
            )
            self.department_combo.bind("<<ComboboxSelected>>", self._department_changed)
            return self.department_combo

        _, department_content = self._column("Dept. / Prog.", 260, create_department_combo)
        self.program_list = tk.Listbox(
            department_content, height=12, exportselection=False, borderwidth=0,
            relief="flat", activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            highlightcolor=self.COLORS["highlight"], font=("Segoe UI", 10),
        )
        self.program_list.pack(fill="both", expand=True)
        if department:
            for program in department.programs:
                self.program_list.insert("end", program)
            if self.selected_program.get() in department.programs:
                program_index = department.programs.index(self.selected_program.get())
                self.program_list.selection_set(program_index)
                self.program_list.activate(program_index)
            self.program_list.bind("<<ListboxSelect>>", self._program_changed)
            program_actions = ttk.Frame(department_content, style="Panel.TFrame")
            program_actions.pack(fill="x", pady=(8, 0))
            ttk.Button(program_actions, text="Edit", command=self.edit_selected_program).pack(side="left")
            ttk.Button(program_actions, text="Delete", style="Danger.TButton",
                       command=self.delete_selected_program).pack(side="left", padx=(5, 0))
        else:
            department_content.pack_propagate(False)
            ttk.Label(department_content, text="Select a department to view programs.", style="Muted.TLabel",
                      wraplength=220).pack(anchor="w")

        _, professor_content = self._column("Professor", 210)
        self.professor_list = tk.Listbox(
            professor_content, height=12, exportselection=False, borderwidth=0,
            relief="flat", activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            highlightcolor=self.COLORS["highlight"], font=("Segoe UI", 10),
        )
        self.professor_list.pack(fill="both", expand=True)
        for professor in self._visible_professors():
            self.professor_list.insert("end", professor.name)
        self.professor_list.bind("<<ListboxSelect>>", self._professor_changed)
        self.professor_list.bind("<Double-Button-1>", self._edit_selected_professor)
        professor_actions = ttk.Frame(professor_content, style="Panel.TFrame")
        professor_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(professor_actions, text="Edit", command=self._edit_selected_professor).pack(side="left")
        ttk.Button(professor_actions, text="Delete", style="Danger.TButton",
                   command=self.delete_selected_professor).pack(side="left", padx=(5, 0))

        _, day_content = self._column("Day", 135)
        day_list = tk.Listbox(
            day_content, height=6, exportselection=False, borderwidth=0,
            relief="flat", activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            highlightcolor=self.COLORS["highlight"], font=("Segoe UI", 10),
        )
        day_list.pack(fill="both", expand=True)
        for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
            day_list.insert("end", day)
        if self.selected_day.get():
            day_list.selection_set(day_list.get(0, "end").index(self.selected_day.get()))
        day_list.bind("<<ListboxSelect>>", lambda _event: self._day_changed(day_list))
        def create_period_combo(parent: ttk.Frame) -> ttk.Combobox:
            combo = ttk.Combobox(
                parent, textvariable=self.selected_period, state="readonly",
                values=("AM", "PM"), width=5,
            )
            combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_board())
            return combo

        _, time_content = self._column("Time", 225, create_period_combo)
        time_list = tk.Listbox(
            time_content, height=12, exportselection=False, borderwidth=0,
            relief="flat", activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            highlightcolor=self.COLORS["highlight"], font=("Segoe UI", 10),
        )
        time_list.pack(fill="both", expand=True)
        for slot in self._visible_time_slots():
            time_list.insert("end", slot)
        if self.selected_time.get() in self._visible_time_slots():
            time_list.selection_set(self._visible_time_slots().index(self.selected_time.get()))
        time_list.bind("<<ListboxSelect>>", lambda _event: self._time_changed(time_list))

        locations = {
            f"{building} / {floor}": (building, floor)
            for building, floor in self.database.load_room_locations()
        }
        if self.selected_floor.get() not in locations:
            self.selected_floor.set(next(iter(locations), ""))

        def create_floor_combo(parent: ttk.Frame) -> ttk.Combobox:
            combo = ttk.Combobox(
                parent, textvariable=self.selected_floor, state="readonly",
                values=list(locations), width=10,
            )
            combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_board())
            return combo

        _, room_content = self._column("Room", 190, create_floor_combo)
        room_list = tk.Listbox(
            room_content, height=6, exportselection=False, borderwidth=0,
            relief="flat", activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            highlightcolor=self.COLORS["highlight"], font=("Segoe UI", 10),
        )
        room_list.pack(fill="both", expand=True)
        location = locations.get(self.selected_floor.get())
        rooms = self.database.load_rooms(*location) if location else []
        if self.selected_room.get() not in rooms:
            self.selected_room.set("")
        for room in rooms:
            room_list.insert("end", room)
        if self.selected_room.get() in rooms:
            room_list.selection_set(rooms.index(self.selected_room.get()))
        room_list.bind("<<ListboxSelect>>", lambda _event: self._room_changed(room_list))
        if not rooms:
            ttk.Label(
                room_content, text="No rooms yet. Use + Room to add one.",
                style="Muted.TLabel", wraplength=160,
            ).pack(anchor="w", pady=(8, 0))

        def create_year_combo(parent: ttk.Frame) -> ttk.Combobox:
            combo = ttk.Combobox(
                parent, textvariable=self.selected_year, state="readonly",
                values=("1st Year", "2nd Year", "3rd Year", "4th Year"), width=10,
            )
            combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_board())
            return combo

        _, subject_content = self._column("Subj.", 340, create_year_combo)
        self._build_subject_content(subject_content)
        _, subject_type_content = self._column("Subj. type", 150)
        subject_type_list = tk.Listbox(
            subject_type_content, height=2, exportselection=False, borderwidth=0,
            relief="flat", activestyle="none", background=self.COLORS["surface"],
            foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
            selectforeground=self.COLORS["select_fg"], highlightthickness=0,
            highlightcolor=self.COLORS["highlight"], font=("Segoe UI", 10),
        )
        subject_type_list.pack(fill="both", expand=True)
        for subject_type in ("Laboratory", "Lecture"):
            subject_type_list.insert("end", subject_type)
        if self.selected_subject_type.get() in subject_type_list.get(0, "end"):
            subject_type_list.selection_set(
                subject_type_list.get(0, "end").index(self.selected_subject_type.get())
            )
        subject_type_list.bind(
            "<<ListboxSelect>>",
            lambda _event: self._subject_type_changed(subject_type_list),
        )

    def _build_subject_content(self, parent: ttk.Frame) -> None:
        year_data = self.curriculum.get(self.selected_year.get(), {})
        for semester, label in (("1st Sem", "1ST SEMESTER"), ("2nd Sem", "2ND SEMESTER")):
            section = ttk.Frame(parent, style="Panel.TFrame")
            section.pack(fill="both", expand=True, pady=(0, 10))
            tk.Label(
                section, text=label, anchor="w", background=self.COLORS["accent"],
                foreground=self.COLORS["primary_dark"],
                font=("Segoe UI", 8, "bold"), padx=8, pady=5,
            ).pack(fill="x")
            subjects = year_data.get(semester, [])
            if subjects:
                subject_list = tk.Listbox(
                    section, height=min(max(len(subjects), 3), 8),
                    exportselection=False, borderwidth=0, relief="flat",
                    activestyle="none", background=self.COLORS["surface"],
                    foreground=self.COLORS["ink"], selectbackground=self.COLORS["select_bg"],
                    selectforeground=self.COLORS["select_fg"],
                    highlightthickness=0,
                    font=("Segoe UI", 10),
                )
                subject_list.pack(fill="both", expand=True)
                for subject in subjects:
                    subject_list.insert("end", subject)
                subject_list.bind(
                    "<Double-Button-1>",
                    lambda _event, sem=semester, listing=subject_list:
                    self._edit_subject(sem, listing),
                )
            else:
                ttk.Label(
                    section,
                    text="Import a curriculum workbook to show subjects.",
                    style="Muted.TLabel",
                    wraplength=260,
                ).pack(anchor="w", padx=8, pady=10)

    def _edit_subject(self, semester: str, subject_list: tk.Listbox) -> None:
        selection = subject_list.curselection()
        department = self._active_department()
        if not selection or not department or not self.selected_program.get():
            return
        old_subject = subject_list.get(selection[0])
        code, name = self.database._split_subject(old_subject)
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit subject")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("500x300")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Edit subject", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Update the subject code and subject name.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 18))
        ttk.Label(frame, text="Subject code", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        code_entry = ttk.Entry(frame)
        code_entry.insert(0, code)
        code_entry.pack(fill="x", pady=(4, 12))
        ttk.Label(frame, text="Subject name", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        name_entry = ttk.Entry(frame)
        name_entry.insert(0, name)
        name_entry.pack(fill="x", pady=(4, 18))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons, text="Save subject", style="Primary.TButton",
            command=lambda: self._save_subject(
                semester, old_subject, code_entry, name_entry, dialog,
            ),
        ).pack(side="right")
        code_entry.focus_set()

    def _save_subject(
        self,
        semester: str,
        old_subject: str,
        code_entry: ttk.Entry,
        name_entry: ttk.Entry,
        dialog: tk.Toplevel,
    ) -> None:
        department = self._active_department()
        code = code_entry.get().strip()
        name = name_entry.get().strip()
        if not department or not self.selected_program.get() or not code or not name:
            self.show_notice("Enter both a subject code and subject name")
            return
        try:
            self.database.update_subject(
                self.selected_program.get(), department.code, self.selected_year.get(),
                semester, old_subject, code, name,
            )
        except (sqlite3.Error, ValueError) as error:
            self.show_notice(f"Could not save subject: {error}")
            return
        dialog.destroy()
        self.curriculum = self.database.load_curriculum(
            self.selected_program.get(), department.code
        )
        self._refresh_board()
        self.show_notice("Subject updated")

    def _active_department(self) -> Department | None:
        return next((d for d in self.departments if d.code == self.selected_department.get()), None)

    def _visible_professors(self) -> list[Professor]:
        department = self._active_department()
        selected_program = self.selected_program.get()
        if department and selected_program:
            key = (department.code, selected_program)
            return [professor for professor in self.professors if key in professor.programs]
        return [
            professor for professor in self.professors
            if professor.department == self.selected_department.get()
        ]

    def _visible_time_slots(self) -> list[str]:
        morning = self.selected_period.get() == "AM"
        slots = []
        for index in range(28):
            start = 7 * 60 + index * 30
            if (start < 12 * 60) == morning:
                slots.append(f"{self._format_time(start)} - {self._format_time(start + 30)}")
        return slots

    @staticmethod
    def _format_time(minutes: int) -> str:
        hour, minute = divmod(minutes, 60)
        period = "PM" if hour >= 12 else "AM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {period}"

    def _department_changed(self, _event: tk.Event | None = None) -> None:
        if self.selected_department.get() == "Select":
            self.selected_department.set("")
        self.selected_program.set("")
        self._refresh_board()

    def _program_changed(self, _event: tk.Event | None = None) -> None:
        selection = self.program_list.curselection()
        if not selection:
            return
        self.selected_program.set(self.program_list.get(selection[0]))
        department = self._active_department()
        if department is not None:
            self.curriculum = self.database.load_curriculum(
                self.selected_program.get(), department.code
            )
        self._refresh_board()

    def _day_changed(self, day_list: tk.Listbox) -> None:
        selection = day_list.curselection()
        if selection:
            self.selected_day.set(day_list.get(selection[0]))

    def _time_changed(self, time_list: tk.Listbox) -> None:
        selection = time_list.curselection()
        if selection:
            self.selected_time.set(time_list.get(selection[0]))

    def _room_changed(self, room_list: tk.Listbox) -> None:
        selection = room_list.curselection()
        if selection:
            self.selected_room.set(room_list.get(selection[0]))

    def _subject_type_changed(self, subject_type_list: tk.Listbox) -> None:
        selection = subject_type_list.curselection()
        if selection:
            self.selected_subject_type.set(subject_type_list.get(selection[0]))

    def _professor_changed(self, _event: tk.Event | None = None) -> None:
        selection = self.professor_list.curselection()
        if selection:
            professor = self._visible_professors()[selection[0]]
            self.open_edit_professor_dialog(professor)

    def show_notice(self, message: str) -> None:
        self.notice.set(message)
        if not self.notice_label.winfo_ismapped():
            self.notice_label.pack(fill="x", pady=(0, 12), before=self.board_holder)
        if self.notice_after_id:
            self.root.after_cancel(self.notice_after_id)
        self.notice_after_id = self.root.after(3000, self._hide_notice)

    def _hide_notice(self) -> None:
        self.notice.set("")
        self.notice_label.pack_forget()
        self.notice_after_id = None

    def import_file(self) -> None:
        program_options = [
            f"{department.code} — {program}"
            for department in self.departments
            for program in department.programs
        ]
        if not program_options:
            self.show_notice("Create a department and program before importing a curriculum")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Import subject curriculum")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x300")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Import subject curriculum",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame, text="Choose the program that owns this curriculum.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 18))
        ttk.Label(frame, text="Program", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        selected_option = next(
            (option for option in program_options
             if option == f"{self.selected_department.get()} — {self.selected_program.get()}"),
            program_options[0],
        )
        program = tk.StringVar(value=selected_option)
        ttk.Combobox(frame, textvariable=program, state="readonly",
                     values=program_options).pack(fill="x", pady=(4, 20))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons, text="Choose XLSX", style="Primary.TButton",
            command=lambda: self._choose_curriculum_file(program, dialog),
        ).pack(side="right")

    def _choose_curriculum_file(self, program: tk.StringVar, dialog: tk.Toplevel) -> None:
        path = filedialog.askopenfilename(
            parent=dialog,
            filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return
        if Path(path).suffix.lower() != ".xlsx":
            self.show_notice("Please select an XLSX curriculum workbook")
            return
        try:
            curriculum = read_xlsx(Path(path))
            department_code, program_name = [part.strip() for part in program.get().split("—", 1)]
            total = self.database.replace_curriculum(program_name, department_code, curriculum)
        except (OSError, KeyError, ValueError, TypeError, sqlite3.Error, ElementTree.ParseError) as error:
            self.show_notice(f"Could not read workbook: {error}")
            return
        if total == 0:
            self.show_notice("No curriculum subjects were found in that workbook")
            return
        dialog.destroy()
        self.selected_department.set(department_code)
        self.selected_program.set(program_name)
        self.curriculum = curriculum
        self._refresh_board()
        self.show_notice(f"Imported {total} subjects from {Path(path).name}")

    def open_room_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Add room")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("500x430")
        dialog.minsize(500, 430)
        frame = ttk.Frame(dialog, padding=(28, 24))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Add room", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Add a room to a building floor.", style="Muted.TLabel").pack(
            anchor="w", pady=(4, 26)
        )
        locations = self.database.load_room_locations()
        active_location = next(
            (location for location in locations
             if f"{location[0]} / {location[1]}" == self.selected_floor.get()),
            ("", ""),
        )
        ttk.Label(frame, text="Building", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        building = tk.StringVar(value=active_location[0])
        ttk.Combobox(
            frame, textvariable=building,
            values=sorted({item[0] for item in locations}),
        ).pack(fill="x", pady=(6, 18), ipady=3)
        ttk.Label(frame, text="Floor", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        floor = tk.StringVar(value=active_location[1])
        ttk.Combobox(
            frame, textvariable=floor,
            values=sorted({item[1] for item in locations}),
        ).pack(fill="x", pady=(6, 18), ipady=3)
        ttk.Label(frame, text="Room code", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        room = ttk.Entry(frame)
        room.pack(fill="x", pady=(6, 26), ipady=5)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", width=12,
                   command=dialog.destroy).pack(side="right", padx=(10, 0), ipady=4)
        ttk.Button(
            buttons, text="Add room", style="Primary.TButton", width=12,
            command=lambda: self._save_room(building, floor, room, dialog),
        ).pack(side="right", ipady=4)

    def _save_room(
        self, building: tk.StringVar, floor: tk.StringVar,
        room_entry: ttk.Entry, dialog: tk.Toplevel,
    ) -> None:
        building_code = building.get().strip().upper()
        floor_name = floor.get().strip()
        room = room_entry.get().strip().upper()
        if not building_code or not floor_name or not room:
            self.show_notice("Enter a building, floor, and room code")
            return
        try:
            self.database.add_room(building_code, floor_name, room)
        except sqlite3.IntegrityError:
            self.show_notice("That room already exists on this floor")
            return
        except sqlite3.Error as error:
            self.show_notice(f"Could not save room: {error}")
            return
        dialog.destroy()
        self.selected_floor.set(f"{building_code} / {floor_name}")
        self.selected_room.set(room)
        self._refresh_board()
        self.show_notice(f"Room {room} added")

    def open_subject_dialog(self) -> None:
        program_options = [
            f"{department.code} — {program}"
            for department in self.departments
            for program in department.programs
        ]
        if not program_options:
            self.show_notice("Create a department and program before adding a subject")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Add subject")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x470")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Add subject", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Add a subject directly to a program curriculum.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 18))
        ttk.Label(frame, text="Program", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        selected = tk.StringVar(value=(
            f"{self.selected_department.get()} — {self.selected_program.get()}"
            if self.selected_program.get() else program_options[0]
        ))
        ttk.Combobox(frame, textvariable=selected, state="readonly",
                     values=program_options).pack(fill="x", pady=(4, 12))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Year", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(row, text="Semester", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=(12, 0))
        year = tk.StringVar(value=self.selected_year.get())
        semester = tk.StringVar(value="1st Sem")
        ttk.Combobox(row, textvariable=year, state="readonly",
                     values=("1st Year", "2nd Year", "3rd Year", "4th Year"),
                     width=18).grid(row=1, column=0, sticky="ew", pady=(4, 12))
        ttk.Combobox(row, textvariable=semester, state="readonly",
                     values=("1st Sem", "2nd Sem"), width=14).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(4, 12))
        ttk.Label(frame, text="Subject code", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        code = ttk.Entry(frame)
        code.pack(fill="x", pady=(4, 12))
        ttk.Label(frame, text="Subject name", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        name = ttk.Entry(frame)
        name.pack(fill="x", pady=(4, 18))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons, text="Add subject", style="Primary.TButton",
            command=lambda: self._save_manual_subject(
                selected, year, semester, code, name, dialog,
            ),
        ).pack(side="right")
        code.focus_set()

    def _save_manual_subject(
        self, selected: tk.StringVar, year: tk.StringVar, semester: tk.StringVar,
        code_entry: ttk.Entry, name_entry: ttk.Entry, dialog: tk.Toplevel,
    ) -> None:
        code = code_entry.get().strip()
        name = name_entry.get().strip()
        if not code or not name:
            self.show_notice("Enter both a subject code and subject name")
            return
        try:
            department, program = [part.strip() for part in selected.get().split("—", 1)]
            self.database.add_subject(program, department, year.get(), semester.get(), code, name)
        except sqlite3.IntegrityError:
            self.show_notice("That subject already exists in this curriculum")
            return
        except (sqlite3.Error, ValueError) as error:
            self.show_notice(f"Could not save subject: {error}")
            return
        dialog.destroy()
        self.selected_department.set(department)
        self.selected_program.set(program)
        self.curriculum = self.database.load_curriculum(program, department)
        self._refresh_board()
        self.show_notice(f"{code} added to {program}")

    def open_department_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Add department")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("520x300")
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Add department", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Departments are shared across the scheduling workspace.", style="Muted.TLabel").pack(anchor="w", pady=(3, 18))

        fields = ttk.Frame(frame)
        fields.pack(fill="x")
        ttk.Label(fields, text="Code").grid(row=0, column=0, sticky="w")
        ttk.Label(fields, text="Department name").grid(row=0, column=1, sticky="w", padx=8)
        code = ttk.Entry(fields, width=14)
        name = ttk.Entry(fields, width=38)
        code.grid(row=1, column=0, sticky="ew")
        name.grid(row=1, column=1, sticky="ew", padx=8)
        fields.columnconfigure(1, weight=1)
        ttk.Button(fields, text="Add Dept.", command=lambda: self._add_department(code, name, dialog)).grid(row=1, column=2)
        ttk.Button(frame, text="Close", command=dialog.destroy).pack(anchor="e", pady=(28, 0))

    def open_program_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Add program")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("500x300")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Add program", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Add a program to an existing department.", style="Muted.TLabel").pack(
            anchor="w", pady=(3, 20)
        )
        ttk.Label(frame, text="Department", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        department = tk.StringVar(value=self.selected_department.get())
        combo = ttk.Combobox(
            frame, textvariable=department, state="readonly",
            values=[d.code for d in self.departments],
        )
        combo.pack(fill="x", pady=(5, 14))
        if not department.get() and self.departments:
            department.set(self.departments[0].code)
        ttk.Label(frame, text="Program name", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        program = ttk.Entry(frame)
        program.pack(fill="x", pady=(5, 0))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(24, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons, text="Add program", style="Primary.TButton",
            command=lambda: self._add_program(program, department, dialog),
        ).pack(side="right")
        program.focus_set()

    def _add_department(self, code_entry: ttk.Entry, name_entry: ttk.Entry, dialog: tk.Toplevel) -> None:
        code = code_entry.get().strip().upper()
        name = name_entry.get().strip()
        if not code or not name or any(d.code == code for d in self.departments):
            self.show_notice("Enter a unique department code and name")
            return
        department = Department(code, name)
        try:
            self.database.add_department(department)
        except sqlite3.Error as error:
            self.show_notice(f"Could not save department: {error}")
            return
        self.departments = self.database.load_departments()
        self.selected_department.set(code)
        self.selected_program.set("")
        self._refresh_board()
        code_entry.delete(0, "end")
        name_entry.delete(0, "end")
        self.show_notice(f"{code} department added")

    def _add_program(self, entry: ttk.Entry, department_code: tk.StringVar,
                     dialog: tk.Toplevel) -> None:
        department = next(
            (item for item in self.departments if item.code == department_code.get()),
            None,
        )
        program = entry.get().strip()
        if not department or not program or program in department.programs:
            self.show_notice("Enter a unique program for the selected department")
            return
        try:
            self.database.add_program(department.code, program)
        except sqlite3.Error as error:
            self.show_notice(f"Could not save program: {error}")
            return
        self.departments = self.database.load_departments()
        self.selected_department.set(department.code)
        self.selected_program.set(program)
        dialog.destroy()
        self._refresh_board()
        self.show_notice(f"{program} added to {department.code}")

    def open_professor_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Add professor")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x560")
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Add professor", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Choose a home department, then assign programs from any department.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 18))
        ttk.Label(frame, text="Professor name").pack(anchor="w")
        name = ttk.Entry(frame)
        name.pack(fill="x", pady=(4, 12))
        ttk.Label(frame, text="Department").pack(anchor="w")
        department = tk.StringVar(value=self.selected_department.get())
        combo = ttk.Combobox(frame, textvariable=department, state="readonly",
                             values=[d.code for d in self.departments])
        combo.pack(fill="x", pady=(4, 12))
        programs_frame = ttk.LabelFrame(frame, text="Programs", padding=8)
        programs_frame.pack(fill="both", expand=True)
        checks: dict[tuple[str, str], tk.BooleanVar] = {}

        def rebuild_checks(_event: tk.Event | None = None) -> None:
            for child in programs_frame.winfo_children():
                child.destroy()
            checks.clear()
            programs = [
                (item.code, program)
                for item in self.departments
                for program in item.programs
            ]
            if programs:
                for department_code, program in programs:
                    value = tk.BooleanVar()
                    checks[(department_code, program)] = value
                    ttk.Checkbutton(
                        programs_frame,
                        text=f"{department_code} — {program}",
                        variable=value,
                    ).pack(anchor="w")
            else:
                ttk.Label(
                    programs_frame, text="Create at least one program first.",
                    style="Muted.TLabel",
                ).pack(anchor="w")

        combo.bind("<<ComboboxSelected>>", rebuild_checks)
        rebuild_checks()
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Add Prof.", style="Primary.TButton",
                   command=lambda: self._save_professor(name, department, checks, dialog)).pack(side="right")

    def _save_professor(self, name_entry: ttk.Entry, department: tk.StringVar,
                        checks: dict[tuple[str, str], tk.BooleanVar], dialog: tk.Toplevel) -> None:
        name = name_entry.get().strip()
        programs = [key for key, value in checks.items() if value.get()]
        if not name or not department.get() or not programs:
            self.show_notice("Enter a professor name, department, and at least one program")
            return
        professor = Professor(name, department.get(), programs)
        try:
            self.database.add_professor(professor)
        except (sqlite3.Error, ValueError) as error:
            self.show_notice(f"Could not save professor: {error}")
            return
        self.professors = self.database.load_professors()
        dialog.destroy()
        self._refresh_board()
        self.show_notice(f"{name} assigned to {len(programs)} program{'s' if len(programs) != 1 else ''}")

    def _edit_selected_professor(self, _event: tk.Event | None = None) -> None:
        selection = self.professor_list.curselection()
        if not selection:
            return
        professor = self._visible_professors()[selection[0]]
        self.open_edit_professor_dialog(professor)

    def open_edit_professor_dialog(self, professor: Professor) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit professor")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("500x500")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Edit professor", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame, text="Change the name and assign programs from any department.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 18))
        ttk.Label(frame, text="Professor name", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        name = ttk.Entry(frame)
        name.insert(0, professor.name)
        name.pack(fill="x", pady=(5, 14))
        ttk.Label(frame, text="Department", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(
            frame, text=professor.department, style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 14))
        programs_frame = ttk.LabelFrame(frame, text="Assigned programs", padding=10)
        programs_frame.pack(fill="both", expand=True)
        checks: dict[tuple[str, str], tk.BooleanVar] = {}
        programs = [
            (item.code, program)
            for item in self.departments
            for program in item.programs
        ]
        if programs:
            for department_code, program in programs:
                value = tk.BooleanVar(value=(department_code, program) in professor.programs)
                checks[(department_code, program)] = value
                ttk.Checkbutton(
                    programs_frame,
                    text=f"{department_code} — {program}",
                    variable=value,
                ).pack(anchor="w", pady=2)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(18, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(
            buttons, text="Save changes", style="Primary.TButton",
            command=lambda: self._save_professor_changes(
                professor, name, checks, dialog,
            ),
        ).pack(side="right")
        name.focus_set()

    def _find_department(self, code: str) -> Department | None:
        return next((item for item in self.departments if item.code == code), None)

    def _save_professor_changes(
        self,
        professor: Professor,
        name_entry: ttk.Entry,
        checks: dict[tuple[str, str], tk.BooleanVar],
        dialog: tk.Toplevel,
    ) -> None:
        name = name_entry.get().strip()
        programs = [key for key, value in checks.items() if value.get()]
        if not name or not programs:
            self.show_notice("Enter a professor name and select at least one program")
            return
        updated = Professor(name, professor.department, programs)
        try:
            self.database.update_professor(professor.id, updated)
        except (sqlite3.Error, ValueError) as error:
            self.show_notice(f"Could not save professor: {error}")
            return
        self.professors = self.database.load_professors()
        dialog.destroy()
        self._refresh_board()
        self.show_notice("Professor updated")

    def delete_selected_professor(self) -> None:
        selection = self.professor_list.curselection()
        if not selection:
            return
        professor = self._visible_professors()[selection[0]]
        assignments = len(professor.programs)
        if not messagebox.askyesno(
            "Delete professor",
            "This will permanently delete:\n\n"
            f"• Professor: {professor.name} ({professor.department})\n"
            f"• {assignments} program assignment{'s' if assignments != 1 else ''}",
            icon="warning",
            parent=self.root,
        ):
            return
        try:
            self.database.delete_professor(professor.id)
        except sqlite3.Error as error:
            self.show_notice(f"Could not delete professor: {error}")
            return
        self.professors = self.database.load_professors()
        self._refresh_board()
        self.show_notice(
            f"Deleted {professor.name} and "
            f"{assignments} program assignment{'s' if assignments != 1 else ''}"
        )

    def edit_selected_program(self) -> None:
        department = self._active_department()
        selection = self.program_list.curselection()
        if not department or not selection:
            return
        old_name = self.program_list.get(selection[0])
        new_name = simpledialog.askstring("Edit program name", "Program name:", initialvalue=old_name, parent=self.root)
        if not new_name or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if new_name in department.programs:
            self.show_notice("That program already exists in this department")
            return
        try:
            self.database.rename_program(department.code, old_name, new_name)
        except sqlite3.Error as error:
            self.show_notice(f"Could not save program: {error}")
            return
        self.departments = self.database.load_departments()
        self.professors = self.database.load_professors()
        if self.selected_program.get() == old_name:
            self.selected_program.set(new_name)
        self._refresh_board()
        self.show_notice("Program updated")

    def delete_selected_program(self) -> None:
        department = self._active_department()
        selection = self.program_list.curselection()
        if not department or not selection:
            return
        program = self.program_list.get(selection[0])
        summary = self.database.load_program_summary(department.code, program)
        subjects = summary["subjects"]
        assignments = summary["assignments"]
        details = [f"• Program: {program} ({department.code})"]
        if subjects:
            details.append(
                f"• All {subjects} curriculum subject{'s' if subjects != 1 else ''}"
            )
        if assignments:
            details.append(
                f"• {assignments} professor program assignment{'s' if assignments != 1 else ''}"
            )
        if not messagebox.askyesno(
            "Delete program",
            "This will permanently delete:\n\n" + "\n".join(details),
            icon="warning",
            parent=self.root,
        ):
            return
        try:
            self.database.delete_program(department.code, program)
        except sqlite3.Error as error:
            self.show_notice(f"Could not delete program: {error}")
            return
        self.departments = self.database.load_departments()
        self.professors = self.database.load_professors()
        if self.selected_program.get() == program:
            self.selected_program.set("")
        self._refresh_board()
        removed = f"Deleted {program} ({department.code})"
        if subjects:
            removed += f" and {subjects} curriculum subject{'s' if subjects != 1 else ''}"
        self.show_notice(removed)
