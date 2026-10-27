"""Regression tests for the Admin 2 assignment workspace.

Run from the admin2 directory with:
    python -B -m unittest test_admin2 -v
"""

import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from unittest.mock import patch

from admin2_app.ui import Admin2App
from scheduling_system.database import Database as RealDatabase
from scheduling_system.models import Department, Professor, Schedule

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
WORKBOOK_XML = (
    XML_DECL
    + '<workbook xmlns="' + MAIN_NS + '" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Schedule" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
RELS_XML = (
    XML_DECL
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
    'Target="worksheets/sheet1.xml"/></Relationships>'
)


def inline_cell(reference: str, text: str) -> str:
    return f'<c r="{reference}" t="inlineStr"><is><t>{text}</t></is></c>'


def sheet_xml(rows: list[str]) -> str:
    body = "".join(
        f'<row r="{n}">' + cells + "</row>" for n, cells in enumerate(rows, 1)
    )
    return XML_DECL + f'<worksheet xmlns="{MAIN_NS}"><sheetData>{body}</sheetData></worksheet>'


def write_schedule_workbook(path: Path, rows: list[str]) -> None:
    from zipfile import ZipFile

    with ZipFile(path, "w") as workbook:
        workbook.writestr("xl/workbook.xml", WORKBOOK_XML)
        workbook.writestr("xl/_rels/workbook.xml.rels", RELS_XML)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows))


SCHEDULE_HEADERS = " ".join(
    inline_cell(f"{chr(65 + i)}1", h) for i, h in enumerate(
        ("PROGRAM", "PROFESSOR", "DAY", "TIME", "SUBJECT", "SUBJECT  TYPE",
         "ROOM", "YEAR")
    )
)


class Admin2Tests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = RealDatabase(Path(self.directory.name) / "shared.db")
        self.addCleanup(self._close_app_db)
        self.db.add_department(Department("COE", "Engineering"))
        self.db.add_program("COE", "BS CpE")
        self.db.add_program("COE", "BS ECE")
        self.db.replace_curriculum(
            "BS CpE", "COE",
            {"1st Year": {"1st Sem": ["CS101 - Programming 1"], "2nd Sem": []}},
        )
        self.db.add_professor(Professor("Jane Doe", "COE", [("COE", "BS CpE")]))
        self.db.add_room("IL", "4", "IL-401")
        self.db.add_room("IK", "1", "IK-101")

        def factory(path=None):
            return self.db if path is None else RealDatabase(path)

        with patch("admin2_app.ui.Database", side_effect=factory):
            self.app = Admin2App(self.root)
        notices = []
        self.notices = notices
        self._original_notice = self.app.show_notice
        self.app.show_notice = lambda message: notices.append(message)

    def _close_app_db(self) -> None:
        try:
            self.app.database.close()
        except Exception:
            pass

    def _restore_notice(self) -> None:
        self.app.show_notice = self._original_notice

    def _nav_buttons(self) -> list[ttk.Button]:
        card = self.app.root.winfo_children()[0].winfo_children()[0]
        return [child for child in card.winfo_children() if isinstance(child, ttk.Button)]

    @staticmethod
    def _descend(widget) -> list:
        found = []
        for child in widget.winfo_children():
            found.append(child)
            found.extend(Admin2Tests._descend(child))
        return found

    def _modal(self):
        return next(child for child in self.root.winfo_children()
                    if isinstance(child, tk.Toplevel))

    def _modal_parts(self):
        dialog = self._modal()
        listing = next(child for child in dialog.winfo_children()[0].winfo_children()
                       if isinstance(child, tk.Listbox))
        set_button = next(
            button for button in self._descend(dialog)
            if isinstance(button, ttk.Button) and button.cget("text") == "Set"
        )
        return dialog, listing, set_button

    # ------------------------------------------------------------- navigation

    def test_navigation_bar_has_all_set_buttons_import_and_settings(self) -> None:
        self._restore_notice()
        texts = [button.cget("text") for button in self._nav_buttons()]
        self.assertEqual(texts, [
            "SET DEPARTMENT", "SET PROGRAM", "SET PROF", "SET DAY",
            "SET TIME", "SET ROOM", "SET SUBJECT", "SET SUBJECT TYPE",
            "IMPORT SCHED", "⚙  Settings",
        ])

    def test_schedule_scrollbars_move_view_and_survive_theme_change(self) -> None:
        self._restore_notice()
        self.root.attributes("-fullscreen", False)
        self.root.state("normal")
        self.root.geometry("1000x760")
        self.root.deiconify()
        self.root.update()
        horizontal = self.app.schedule_hscroll
        vertical = self.app.schedule_vscroll
        self.assertEqual(str(horizontal.cget("orient")), "horizontal")
        self.assertEqual(str(vertical.cget("orient")), "vertical")
        self.assertEqual(horizontal.grid_info()["row"], 1)
        self.assertTrue(horizontal.winfo_ismapped())
        self.assertTrue(vertical.winfo_ismapped())
        self.assertLess(self.app.schedule_tree.xview()[1], 1.0)
        self.root.tk.call(horizontal.cget("command"), "moveto", 1.0)
        self.root.update_idletasks()
        self.assertGreater(self.app.schedule_tree.xview()[0], 0.0)
        self.assertAlmostEqual(self.app.schedule_tree.xview()[1], 1.0, places=2)
        self.assertEqual(horizontal.get(), self.app.schedule_tree.xview())
        for column in self.app.schedule_tree.cget("columns"):
            self.assertFalse(self.app.schedule_tree.column(column, "stretch"))
        self.app._apply_theme("dark")
        self.root.update()
        self.assertTrue(self.app.schedule_hscroll.winfo_ismapped())
        self.root.tk.call(self.app.schedule_hscroll.cget("command"), "moveto", 1.0)
        self.root.update_idletasks()
        self.assertGreater(self.app.schedule_tree.xview()[0], 0.0)
        self.root.geometry("1100x800")
        self.root.update()
        self.assertTrue(self.app.schedule_hscroll.winfo_ismapped())
        self.assertTrue(self.app.schedule_vscroll.winfo_ismapped())

    def test_window_starts_fullscreen_with_window_controls(self) -> None:
        self._restore_notice()
        try:
            self.assertTrue(self.root.attributes("-fullscreen"))
        except tk.TclError:
            self.skipTest("fullscreen attribute not supported on this platform")
        texts = [w.cget("text") for w in self._descend(self.root)
                 if isinstance(w, ttk.Button)]
        self.assertIn("—", texts)
        self.assertIn("✕", texts)
        self.assertTrue(self.root.bind("<F11>"))
        self.app._toggle_fullscreen()
        self.assertFalse(self.root.attributes("-fullscreen"))
        self.app._toggle_fullscreen()
        self.assertTrue(self.root.attributes("-fullscreen"))
        for label in self.app.value_labels.values():
            self.assertEqual(label.cget("text"), "Not set")

    # ------------------------------------------------------------- setters

    def test_set_department_sets_value_and_clears_dependents(self) -> None:
        self._restore_notice()
        self.app.selected["program"].set("BS ECE")
        self.app.set_department()
        dialog, listing, set_button = self._modal_parts()
        self.assertEqual(listing.get(0, "end"), ("COE — Engineering",))
        listing.selection_set(0)
        set_button.invoke()
        self.assertEqual(self.app.selected["department"].get(), "COE")
        self.assertEqual(self.app.selected["program"].get(), "")
        self.assertEqual(self.app.selected["subject"].get(), "")
        self.assertIn("Department set to COE", self.app.logs[-1])

    def test_set_program_requires_department(self) -> None:
        self.app.set_program()
        self.assertEqual(self.notices, ["Set a department first"])
        self.assertFalse(any(child for child in self.root.winfo_children()
                             if isinstance(child, tk.Toplevel)))

    def test_set_program_lists_programs_of_department(self) -> None:
        self._restore_notice()
        self.app.selected["department"].set("COE")
        self.app.set_program()
        _, listing, set_button = self._modal_parts()
        self.assertEqual(listing.get(0, "end"), ("BS CpE", "BS ECE"))
        listing.selection_set(1)
        set_button.invoke()
        self.assertEqual(self.app.selected["program"].get(), "BS ECE")

    def test_set_professor_filters_by_department(self) -> None:
        self._restore_notice()
        self.app.selected["department"].set("COE")
        self.app.set_professor()
        _, listing, set_button = self._modal_parts()
        self.assertEqual(listing.get(0, "end"), ("Jane Doe (COE)",))
        listing.selection_set(0)
        set_button.invoke()
        self.assertEqual(self.app.selected["professor"].get(), "Jane Doe")

    def test_set_room_lists_all_rooms(self) -> None:
        self._restore_notice()
        self.app.set_room()
        _, listing, set_button = self._modal_parts()
        self.assertEqual(listing.get(0, "end"), ("IK-101", "IL-401"))
        listing.selection_set(1)
        set_button.invoke()
        self.assertEqual(self.app.selected["room"].get(), "IL-401")
        self.assertIn("Room set to IL-401", self.app.logs[-1])

    def test_set_day_and_subject_type(self) -> None:
        self._restore_notice()
        self.app.set_day()
        _, listing, set_button = self._modal_parts()
        self.assertEqual(listing.get(0, "end"), tuple(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")))
        listing.selection_set(2)
        set_button.invoke()
        self.assertEqual(self.app.selected["day"].get(), "Wednesday")
        self.app.set_subject_type()
        _, listing, set_button = self._modal_parts()
        listing.selection_set(1)
        set_button.invoke()
        self.assertEqual(self.app.selected["subject_type"].get(), "Lecture")

    def test_set_time_uses_start_end_range(self) -> None:
        self._restore_notice()
        self.app.set_time()
        dialog = self._modal()
        combos = [w for w in self._descend(dialog) if isinstance(w, ttk.Combobox)]
        self.assertEqual(len(combos), 2)
        options = list(combos[0].cget("values"))
        self.assertEqual(options[0], "7:00 AM")
        self.assertEqual(options[-1], "9:00 PM")
        combos[0].set("7:00 AM")
        combos[1].set("1:00 PM")
        set_button = next(b for b in self._descend(dialog)
                          if isinstance(b, ttk.Button) and b.cget("text") == "Set")
        set_button.invoke()
        self.assertEqual(self.app.selected["time"].get(), "7:00 AM - 1:00 PM")
        self.assertEqual(self.app.time_start, 420)
        self.assertEqual(self.app.time_end, 780)

    def test_set_time_rejects_end_before_start(self) -> None:
        self.app.set_time()
        dialog = self._modal()
        combos = [w for w in self._descend(dialog) if isinstance(w, ttk.Combobox)]
        combos[0].set("1:00 PM")
        combos[1].set("7:00 AM")
        set_button = next(b for b in self._descend(dialog)
                          if isinstance(b, ttk.Button) and b.cget("text") == "Set")
        set_button.invoke()
        self.assertEqual(self.notices, ["Choose an end time after the start time"])
        self.assertIn(dialog, self.root.winfo_children())
        dialog.destroy()

    def test_set_subject_records_year_and_semester(self) -> None:
        self._restore_notice()
        self.app.selected["department"].set("COE")
        self.app.selected["program"].set("BS CpE")
        self.app.set_subject()
        _, listing, set_button = self._modal_parts()
        self.assertEqual(listing.get(0, "end"), ("CS101 - Programming 1",))
        listing.selection_set(0)
        set_button.invoke()
        self.assertEqual(self.app.selected["subject"].get(), "CS101 - Programming 1")
        self.assertEqual(self.app.subject_year, "1st Year")
        self.assertEqual(self.app.subject_semester, "1st Sem")

    # ------------------------------------------------------------- add + conflicts

    def _fill_entry(self, professor: str = "Jane Doe", day: str = "Monday",
                    start: int = 420, end: int = 780) -> None:
        self.app.selected["department"].set("COE")
        self.app.selected["program"].set("BS CpE")
        self.app.selected["professor"].set(professor)
        self.app.selected["day"].set(day)
        self.app.time_start, self.app.time_end = start, end
        self.app.selected["time"].set(
            f"{self.app._format_time(start)} - {self.app._format_time(end)}")
        self.app.selected["subject"].set("CS101 - Programming 1")
        self.app.selected["subject_type"].set("Lecture")
        self.app.selected["room"].set("IL-401")
        self.app.subject_year, self.app.subject_semester = "1st Year", "1st Sem"
        self.app._refresh_summary()
        self.app._update_conflict_warning()

    def test_add_to_schedule_persists_and_clears_entry(self) -> None:
        self._restore_notice()
        self._fill_entry()
        self.app.add_to_schedule()
        schedules = self.db.load_schedules()
        self.assertEqual(len(schedules), 1)
        saved = schedules[0]
        self.assertEqual(saved.subject, "CS101 - Programming 1")
        self.assertEqual(saved.time_display, "7:00 AM - 1:00 PM")
        self.assertEqual(saved.room, "IL-401")
        self.assertEqual(saved.year, "1st Year")
        self.assertEqual(len(self.app.schedule_tree.get_children()), 1)
        self.assertTrue(any("Schedule added" in entry for entry in self.app.logs))
        self.assertEqual(self.app.selected["day"].get(), "")
        self.assertEqual(self.app.selected["room"].get(), "")
        self.assertIsNone(self.app.time_start)

    def test_add_requires_room(self) -> None:
        self._fill_entry()
        self.app.selected["room"].set("")
        self.app._update_conflict_warning()
        self.app.add_to_schedule()
        self.assertEqual(self.notices, ["Set all schedule fields before adding"])
        self.assertEqual(self.db.load_schedules(), [])

    def test_add_requires_complete_entry(self) -> None:
        self.app.selected["department"].set("COE")
        self.app.add_to_schedule()
        self.assertEqual(self.notices, ["Set all schedule fields before adding"])
        self.assertEqual(self.db.load_schedules(), [])

    def test_realtime_conflict_warning_and_override_choice(self) -> None:
        self._restore_notice()
        self.db.add_schedule(Schedule(
            department="COE", program="BS CpE", subject="CS999 - Other",
            subject_type="Lecture", professor="Jane Doe", day="Monday",
            start_minutes=600, end_minutes=660, year="1st Year",
        ))
        self._fill_entry(start=540, end=720)
        self.assertIn("OVERLAP", self.app.conflict_label.cget("text"))
        self.assertIn("Jane Doe", self.app.conflict_label.cget("text"))
        with patch("admin2_app.ui.messagebox.askyesno", return_value=False):
            self.app.add_to_schedule()
        self.assertEqual(len(self.db.load_schedules()), 1)
        self.assertTrue(any("Add cancelled" in entry for entry in self.app.logs))
        with patch("admin2_app.ui.messagebox.askyesno", return_value=True) as ask:
            self.app.add_to_schedule()
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(len(self.db.load_schedules()), 2)
        self.assertTrue(any("verlap warning accepted" in entry for entry in self.app.logs))

    def test_no_conflict_warning_when_entry_incomplete(self) -> None:
        self._restore_notice()
        self._fill_entry()
        self.app.selected["professor"].set("")
        self.app._update_conflict_warning()
        self.assertEqual(self.app.conflict_label.cget("text"), "")

    # ------------------------------------------------------------- list + filters + delete

    def _seed_two_schedules(self) -> None:
        self.db.add_schedule(Schedule(
            department="COE", program="BS CpE", subject="CS101 - Programming 1",
            subject_type="Lecture", professor="Jane Doe", day="Monday",
            start_minutes=420, end_minutes=480, year="1st Year", room="IL-401",
        ))
        self.db.add_schedule(Schedule(
            department="COE", program="BS ECE", subject="EE100 - Circuits",
            subject_type="Laboratory", professor="Jane Doe", day="Tuesday",
            start_minutes=840, end_minutes=900, year="2nd Year", room="IL-405",
        ))
        self.app._refresh_schedule_list()

    def test_filters_day_time_program_and_clear(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        tree = self.app.schedule_tree
        self.assertEqual(len(tree.get_children()), 2)

        self.app.filters["day"].set("Monday")
        self.app._refresh_schedule_list()
        self.assertEqual(len(tree.get_children()), 1)
        self.assertIn("CS101", tree.item(tree.get_children()[0])["values"][4])

        self.app.clear_filters()
        self.app.filters["time"].set("PM")
        self.app._refresh_schedule_list()
        self.assertEqual(len(tree.get_children()), 1)
        self.assertIn("EE100", tree.item(tree.get_children()[0])["values"][4])

        self.app.clear_filters()
        self.app.filters["program"].set("BS CpE")
        self.app._refresh_schedule_list()
        self.assertEqual(len(tree.get_children()), 1)

        self.app.clear_filters()
        self.assertEqual(len(tree.get_children()), 2)

    def test_delete_selected_schedule_with_confirmation(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        first_id = str(self.db.load_schedules()[0].id)
        self.app.schedule_tree.selection_set(first_id)
        with patch("admin2_app.ui.messagebox.askyesno", return_value=False):
            self.app.delete_selected_schedule()
        self.assertEqual(len(self.db.load_schedules()), 2)
        with patch("admin2_app.ui.messagebox.askyesno", return_value=True):
            self.app.delete_selected_schedule()
        self.assertEqual(len(self.db.load_schedules()), 1)
        self.assertTrue(any("Schedule deleted" in entry for entry in self.app.logs))

    # ------------------------------------------------------------- edit flow

    def _options_buttons(self, schedule_id: int) -> list[ttk.Button]:
        self.app._open_schedule_options(schedule_id)
        dialog = self._modal()
        frame = dialog.winfo_children()[0]
        return [b for b in frame.winfo_children() if isinstance(b, ttk.Button)]

    def test_double_click_opens_options_modal(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        first_id = self.db.load_schedules()[0].id
        self.app.schedule_tree.selection_set(str(first_id))
        self.app._on_schedule_activated()
        buttons = [b for b in self._descend(self._modal())
                   if isinstance(b, ttk.Button)]
        self.assertEqual([b.cget("text") for b in buttons], ["Edit", "Delete", "Cancel"])

    def test_edit_updates_schedule_without_self_conflict(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        schedule = self.db.load_schedules()[0]
        self.app._open_edit_schedule_dialog(schedule)
        dialog = self._modal()
        combos = [w for w in self._descend(dialog) if isinstance(w, ttk.Combobox)]
        labels = ["Subject", "Type", "Professor", "Day", "Start", "End", "Room"]
        self.assertEqual(len(combos), 7)
        combos[labels.index("Day")].set("Friday")
        combos[labels.index("Room")].set("IK-101")
        save = next(b for b in self._descend(dialog)
                    if isinstance(b, ttk.Button) and b.cget("text") == "Save changes")
        with patch("admin2_app.ui.messagebox.askyesno") as ask:
            save.invoke()
        ask.assert_not_called()
        updated = next(s for s in self.db.load_schedules() if s.id == schedule.id)
        self.assertEqual(updated.day, "Friday")
        self.assertEqual(updated.room, "IK-101")
        self.assertEqual(len(self.db.load_schedules()), 2)
        self.assertTrue(any("Schedule updated" in entry for entry in self.app.logs))

    def test_edit_warns_on_new_overlap_and_respects_choice(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        first, second = self.db.load_schedules()
        self.app._open_edit_schedule_dialog(first)
        dialog = self._modal()
        combos = [w for w in self._descend(dialog) if isinstance(w, ttk.Combobox)]
        combos[3].set("Tuesday")          # move onto second entry's day/time
        combos[4].set("2:00 PM")
        combos[5].set("2:30 PM")
        save = next(b for b in self._descend(dialog)
                    if isinstance(b, ttk.Button) and b.cget("text") == "Save changes")
        with patch("admin2_app.ui.messagebox.askyesno", return_value=False) as ask:
            save.invoke()
        ask.assert_called_once()
        self.assertEqual(self.db.load_schedules()[0].day, "Monday")
        with patch("admin2_app.ui.messagebox.askyesno", return_value=True):
            save.invoke()
        updated_first = next(s for s in self.db.load_schedules() if s.id == first.id)
        self.assertEqual(updated_first.day, "Tuesday")
        self.assertEqual(updated_first.time_display, "2:00 PM - 2:30 PM")
        self.assertTrue(any("despite overlap warning" in entry for entry in self.app.logs))

    def test_edit_rejects_end_before_start(self) -> None:
        self._seed_two_schedules()
        schedule = self.db.load_schedules()[0]
        self.app._open_edit_schedule_dialog(schedule)
        dialog = self._modal()
        combos = [w for w in self._descend(dialog) if isinstance(w, ttk.Combobox)]
        combos[4].set("1:00 PM")
        combos[5].set("7:00 AM")
        save = next(b for b in self._descend(dialog)
                    if isinstance(b, ttk.Button) and b.cget("text") == "Save changes")
        save.invoke()
        self.assertEqual(self.notices, ["Choose an end time after the start time"])
        self.assertIn(dialog, self.root.winfo_children())
        dialog.destroy()

    # ------------------------------------------------------------- import / export

    def test_import_accepts_rows_skips_conflicts_and_bad_rows(self) -> None:
        workbook = Path(self.directory.name) / "sched.xlsx"
        rows = [
            SCHEDULE_HEADERS,
            " ".join(inline_cell(f"{chr(65 + i)}2", v) for i, v in enumerate(
                ("BSCPE", "JANE  DOE", "MONDAY", "7:00AM-1:00PM",
                 " CPE212 -  Data Structure and Algoritm ", "LECTURE", "IL-402",
                 "1st Year"))),
            " ".join(inline_cell(f"{chr(65 + i)}3", v) for i, v in enumerate(
                ("BSCPE", "Jane Doe", "MONDAY", "10:00AM-11:00AM",
                 "GEE1 - Gender and Society", "LECTURE", "", "1st Year"))),
            " ".join(inline_cell(f"{chr(65 + i)}4", v) for i, v in enumerate(
                ("UNKNOWN", "New Professor", "FRIDAY", "7:00AM-9:00AM",
                 "CS999 - Nowhere", "LECTURE", "", ""))),
            " ".join(inline_cell(f"{chr(65 + i)}5", v) for i, v in enumerate(
                ("BSCPE", "Jane Doe", "MONDAY", "25:00AM",
                 "CS998 - Bad Time", "LECTURE", "", ""))),
        ]
        write_schedule_workbook(workbook, rows)
        with patch("admin2_app.ui.filedialog.askopenfilename", return_value=str(workbook)):
            self.app.import_schedule()
        schedules = self.db.load_schedules()
        self.assertEqual(len(schedules), 1)
        imported = next(s for s in schedules if "CPE212" in s.subject)
        self.assertEqual(imported.professor, "Jane Doe")
        self.assertEqual(imported.year, "1st Year")
        self.assertEqual(imported.room, "IL-402")
        self.assertEqual(imported.day, "Monday")
        self.assertEqual(imported.time_display, "7:00 AM - 1:00 PM")
        self.assertTrue(
            self.notices
            and self.notices[0].startswith(
                "Imported 1 schedule, skipped 1 overlap, 2 invalid"
            )
        )
        self.assertTrue(any("not set up in Admin 1" in entry for entry in self.app.logs))
        self.assertTrue(any("overlap" in entry for entry in self.app.logs))
        self.assertEqual(len(self.app.schedule_tree.get_children()), 1)

    def test_import_works_on_empty_database(self) -> None:
        fresh = RealDatabase(Path(self.directory.name) / "fresh.db")
        self.addCleanup(fresh.close)
        self.db.close()
        self.db = fresh

        def factory(path=None):
            return fresh if path is None else RealDatabase(path)

        with patch("admin2_app.ui.Database", side_effect=factory):
            self.app.database = fresh
            workbook = Path(self.directory.name) / "new.xlsx"
            rows = [
                SCHEDULE_HEADERS,
                " ".join(inline_cell(f"{chr(65 + i)}2", v) for i, v in enumerate(
                    ("BS Computer Engineering", "Justeen James Tolentino",
                     "Monday", "7:00AM-1:00PM",
                     "CPE212 - Data Structure and Algoritm", "LECTURE", "IL-402",
                     "1st Year"))),
            ]
            write_schedule_workbook(workbook, rows)
            with patch("admin2_app.ui.filedialog.askopenfilename", return_value=str(workbook)):
                self.app.import_schedule()
        schedules = fresh.load_schedules()
        self.assertEqual(len(schedules), 1)
        imported = schedules[0]
        self.assertEqual(imported.program, "BS Computer Engineering")
        self.assertEqual(imported.professor, "Justeen James Tolentino")
        self.assertEqual(imported.year, "1st Year")
        self.assertEqual(imported.time_display, "7:00 AM - 1:00 PM")
        self.assertEqual(self.app.schedule_tree.get_children(), (str(imported.id),))
        self.assertIn("Imported 1 schedule", self.notices[0])
        self.assertIn("workbook values", self.notices[0])

    def test_import_rejects_bad_format(self) -> None:
        workbook = Path(self.directory.name) / "bad.xlsx"
        write_schedule_workbook(workbook, [
            " ".join(inline_cell(f"{chr(65 + i)}1", h) for i, h in enumerate(
                ("Foo", "Bar", "Baz", "Qux", "Quux", "Corge", "Grault"))),
            " ".join(inline_cell(f"{chr(65 + i)}2", v) for i, v in enumerate(
                ("a", "b", "c", "d", "e", "f", "g"))),
        ])
        with patch("admin2_app.ui.filedialog.askopenfilename", return_value=str(workbook)):
            self.app.import_schedule()
        self.assertTrue(self.notices and "Could not read workbook" in self.notices[0])
        self.assertEqual(self.db.load_schedules(), [])

    def test_export_writes_printable_html(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        export_path = Path(self.directory.name) / "export.html"
        with patch("admin2_app.ui.filedialog.asksaveasfilename", return_value=str(export_path)), \
             patch("admin2_app.ui.webbrowser.open") as opened:
            self.app.export_schedule()
        opened.assert_called_once()
        content = export_path.read_text(encoding="utf-8")
        self.assertIn("7:00 AM - 8:00 AM", content)
        self.assertIn("CS101 - Programming 1", content)
        self.assertIn("2:00 PM - 3:00 PM", content)
        self.assertTrue(any("Exported 2" in entry for entry in self.app.logs))

    def test_export_respects_filters(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        self.app.filters["day"].set("Tuesday")
        self.app._refresh_schedule_list()
        export_path = Path(self.directory.name) / "filtered.html"
        with patch("admin2_app.ui.filedialog.asksaveasfilename", return_value=str(export_path)), \
             patch("admin2_app.ui.webbrowser.open"):
            self.app.export_schedule()
        content = export_path.read_text(encoding="utf-8")
        self.assertIn("EE100", content)
        self.assertNotIn("CS101", content)

    # ------------------------------------------------------------- settings/theme/db

    def test_settings_dialog_matches_admin1(self) -> None:
        self._restore_notice()
        self.app.open_settings_dialog()
        dialog = self._modal()
        frame = dialog.winfo_children()[0]
        radios = [w for w in frame.winfo_children() if isinstance(w, ttk.Radiobutton)]
        buttons = [w for w in frame.winfo_children() if isinstance(w, ttk.Button)]
        self.assertEqual(len(radios), 2)
        self.assertEqual(sorted([radios[0].cget("value"), radios[1].cget("value")]),
                         ["dark", "light"])
        self.assertIn("Change database location...", [b.cget("text") for b in buttons])
        dialog.destroy()

    def test_theme_switch_persists_and_rebuilds_interface(self) -> None:
        self._restore_notice()
        self._seed_two_schedules()
        self.app._apply_theme("dark")
        self.assertEqual(self.db.get_setting("theme"), "dark")
        self.assertEqual(self.root.cget("background"), "#1f1e1d")
        self.assertEqual(len(self.app.schedule_tree.get_children()), 2)
        self.assertTrue(any("Theme changed to dark" in entry for entry in self.app.logs))

    def test_database_change_creates_empty_database_and_forwards_pointer(self) -> None:
        self._restore_notice()
        target_dir = Path(self.directory.name) / "admin2 data"
        with patch("admin2_app.ui.filedialog.askdirectory", return_value=str(target_dir)):
            self.app._choose_database_location()
        target = target_dir / "scheduling.db"
        self.assertTrue(target.exists())
        self.assertEqual(self.app.database.path, target)
        self.assertEqual(self.app.database.load_departments(), [])
        previous = RealDatabase(Path(self.directory.name) / "shared.db")
        try:
            self.assertEqual(previous.get_setting("database_path"), str(target))
        finally:
            previous.close()


if __name__ == "__main__":
    unittest.main()
