"""Isolated regression tests for curriculum import validation and delete dialogs.

Run from the admin1 directory with:
    python -B -m unittest test_import_validation -v
"""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch
from zipfile import ZipFile

from scheduling_system.curriculum import read_xlsx
from scheduling_system.database import Database
from scheduling_system.models import Department, Professor
from scheduling_system.ui import SchedulingApp

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

WORKBOOK_XML = (
    XML_DECL
    + '<workbook xmlns="' + MAIN_NS + '" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Curriculum" sheetId="1" r:id="rId1"/></sheets></workbook>'
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


def rich_cell(reference: str, *runs: str) -> str:
    body = "".join(f"<r><t>{run}</t></r>" for run in runs)
    return f'<c r="{reference}" t="inlineStr"><is>{body}</is></c>'


def sheet_xml(rows: list[str]) -> str:
    body = "".join(f'<row r="{number}">{cells}</row>' for number, cells in enumerate(rows, 1))
    return XML_DECL + f'<worksheet xmlns="{MAIN_NS}"><sheetData>{body}</sheetData></worksheet>'


def write_workbook(path: Path, sheet: str, shared: list[str] | None = None) -> None:
    with ZipFile(path, "w") as workbook:
        workbook.writestr("xl/workbook.xml", WORKBOOK_XML)
        workbook.writestr("xl/_rels/workbook.xml.rels", RELS_XML)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet)
        if shared is not None:
            items = "".join(f"<si><t>{text}</t></si>" for text in shared)
            workbook.writestr(
                "xl/sharedStrings.xml",
                XML_DECL + f'<sst xmlns="{MAIN_NS}">{items}</sst>',
            )


def shared_cell(reference: str, index: int) -> str:
    return f'<c r="{reference}" t="s"><v>{index}</v></c>'


HEADERS_ROW = " ".join(
    inline_cell(f"{column}1", header)
    for column, header in (
        ("A", "1ST YEAR 1ST SEM"), ("B", "1ST YEAR 2ND SEM"),
    )
)


class ImportValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "workbook.xlsx"

    def test_reference_format_parses(self) -> None:
        write_workbook(self.path, sheet_xml([
            HEADERS_ROW,
            inline_cell("A2", "CS101 - Programming 1"),
            inline_cell("B2", "CS102 - Programming 2"),
        ]))
        curriculum = read_xlsx(self.path)
        self.assertEqual(curriculum["1st Year"]["1st Sem"], ["CS101 - Programming 1"])
        self.assertEqual(curriculum["1st Year"]["2nd Sem"], ["CS102 - Programming 2"])

    def test_rich_text_inline_cells_parse(self) -> None:
        write_workbook(self.path, sheet_xml([
            HEADERS_ROW,
            rich_cell("A2", "CS", "101", " - Programming 1"),
        ]))
        self.assertEqual(read_xlsx(self.path)["1st Year"]["1st Sem"], ["CS101 - Programming 1"])

    def test_shared_string_cells_parse(self) -> None:
        write_workbook(
            self.path,
            sheet_xml([HEADERS_ROW, shared_cell("A2", 1)]),
            shared=["HEADER", "CS101 - Programming 1"],
        )
        self.assertEqual(read_xlsx(self.path)["1st Year"]["1st Sem"], ["CS101 - Programming 1"])

    def test_unrecognized_headers_are_rejected(self) -> None:
        write_workbook(self.path, sheet_xml([
            inline_cell("A1", "Subject"), inline_cell("B1", "Units"),
            inline_cell("A2", "CS101"),
        ]))
        with self.assertRaises(ValueError) as raised:
            read_xlsx(self.path)
        self.assertIn("Unrecognized curriculum format", str(raised.exception))

    def test_headers_without_subjects_are_rejected(self) -> None:
        write_workbook(self.path, sheet_xml([HEADERS_ROW]))
        with self.assertRaises(ValueError) as raised:
            read_xlsx(self.path)
        self.assertIn("No curriculum subjects", str(raised.exception))

    def test_workbook_without_rows_is_rejected(self) -> None:
        write_workbook(self.path, sheet_xml([]))
        with self.assertRaises(ValueError):
            read_xlsx(self.path)


class DialogFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.db = Database(Path(":memory:"))
        self.addCleanup(self.db.close)
        self.db.add_department(Department("COE", "Engineering"))
        self.db.add_program("COE", "BS CpE")
        self.db.replace_curriculum(
            "BS CpE", "COE",
            {"1st Year": {"1st Sem": ["CS101 - Programming 1"], "2nd Sem": []}},
        )
        self.db.add_professor(Professor("Jane Doe", "COE", [("COE", "BS CpE")]))
        with patch("scheduling_system.ui.Database", return_value=self.db):
            self.app = SchedulingApp(self.root)
        self.app.show_notice = Mock()

    def test_invalid_import_rejected_before_database_changes(self) -> None:
        before = self.db.load_curriculum("BS CpE", "COE")
        with patch("scheduling_system.ui.read_xlsx", side_effect=ValueError("bad format")), \
             patch("scheduling_system.ui.filedialog.askopenfilename", return_value="bad.xlsx"):
            self.app._choose_curriculum_file(
                tk.StringVar(self.root, value="COE — BS CpE"), Mock(),
            )
        self.assertEqual(self.db.load_curriculum("BS CpE", "COE"), before)
        self.app.show_notice.assert_called_once()
        self.assertIn("bad format", self.app.show_notice.call_args[0][0])

    def test_program_delete_dialog_lists_curriculum_and_can_cancel(self) -> None:
        self.app.selected_department.set("COE")
        self.app.selected_program.set("BS CpE")
        self.app._refresh_board()
        program_list = self.app.program_list
        program_list.selection_set(0)
        with patch("scheduling_system.ui.messagebox.askyesno", return_value=False) as ask:
            self.app.delete_selected_program()
        message = ask.call_args[0][1]
        self.assertIn("BS CpE (COE)", message)
        self.assertIn("1 curriculum subject", message)
        self.assertIn("1 professor program assignment", message)
        self.assertEqual(self.db.load_curriculum("BS CpE", "COE")["1st Year"]["1st Sem"],
                         ["CS101 - Programming 1"])

    def test_confirmed_program_delete_removes_curriculum(self) -> None:
        self.app.selected_department.set("COE")
        self.app.selected_program.set("BS CpE")
        self.app._refresh_board()
        self.app.program_list.selection_set(0)
        with patch("scheduling_system.ui.messagebox.askyesno", return_value=True):
            self.app.delete_selected_program()
        self.assertEqual(
            self.db.load_departments()[0].programs, [],
        )
        with self.assertRaises(ValueError):
            self.db.load_program_summary("COE", "BS CpE")
        self.app.show_notice.assert_called_once()
        self.assertIn("1 curriculum subject", self.app.show_notice.call_args[0][0])

    def test_professor_delete_dialog_lists_assignments_and_can_cancel(self) -> None:
        self.app.selected_department.set("COE")
        self.app._refresh_board()
        self.app.professor_list.selection_set(0)
        with patch("scheduling_system.ui.messagebox.askyesno", return_value=False) as ask:
            self.app.delete_selected_professor()
        self.assertIn("Jane Doe (COE)", ask.call_args[0][1])
        self.assertIn("1 program assignment", ask.call_args[0][1])
        self.assertEqual([p.name for p in self.db.load_professors()], ["Jane Doe"])


class BugFixRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.db = Database(Path(":memory:"))
        self.addCleanup(self.db.close)
        self.db.add_department(Department("COE", "Engineering"))
        self.db.add_program("COE", "BS CpE")
        self.db.replace_curriculum(
            "BS CpE", "COE",
            {"1st Year": {"1st Sem": ["CS101 - Programming 1"], "2nd Sem": []}},
        )
        self.db.add_professor(Professor("Jane Doe", "COE", [("COE", "BS CpE")]))
        with patch("scheduling_system.ui.Database", return_value=self.db):
            self.app = SchedulingApp(self.root)

    def test_professor_single_click_no_longer_opens_edit_dialog(self) -> None:
        self.app.selected_department.set("COE")
        self.app._refresh_board()
        self.assertEqual(self.app.professor_list.bind("<<ListboxSelect>>"), "")
        self.assertTrue(self.app.professor_list.bind("<Double-Button-1>"))
        self.app.professor_list.selection_set(0)
        with patch.object(SchedulingApp, "open_edit_professor_dialog") as open_dialog:
            self.app.professor_list.event_generate("<<ListboxSelect>>")
            self.root.update()
        open_dialog.assert_not_called()

    def _modal_buttons(self) -> list[ttk.Button]:
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        frame = dialog.winfo_children()[0]
        return [child for child in frame.winfo_children() if isinstance(child, ttk.Button)]

    def test_single_program_click_shows_options_modal(self) -> None:
        self.app.selected_department.set("COE")
        self.app._refresh_board()
        self.app.program_list.selection_set(0)
        self.app._program_changed()
        self.assertEqual(self.app.selected_program.get(), "BS CpE")
        self.assertEqual(
            self.app.curriculum["1st Year"]["1st Sem"], ["CS101 - Programming 1"],
        )
        buttons = self._modal_buttons()
        self.assertEqual([b.cget("text") for b in buttons], ["Edit", "Delete", "Cancel"])

    def test_professor_options_modal_offers_edit_and_delete(self) -> None:
        self.app.selected_department.set("COE")
        self.app._refresh_board()
        self.app.professor_list.selection_set(0)
        with patch("scheduling_system.ui.messagebox.askyesno", return_value=False) as ask, \
             patch.object(SchedulingApp, "open_edit_professor_dialog") as open_edit:
            self.app._open_professor_options()
            buttons = self._modal_buttons()
            self.assertEqual([b.cget("text") for b in buttons], ["Edit", "Delete", "Cancel"])
            buttons[1].invoke()
            self.assertIn("Jane Doe", ask.call_args[0][1])
            self.assertEqual([p.name for p in self.db.load_professors()], ["Jane Doe"])
            self.app._open_professor_options()
            buttons = self._modal_buttons()
            buttons[0].invoke()
            self.assertEqual(open_edit.call_count, 1)
            self.assertEqual(open_edit.call_args[0][0].name, "Jane Doe")

    def test_program_options_modal_offers_edit_and_delete(self) -> None:
        self.app.selected_department.set("COE")
        self.app._refresh_board()
        self.app.program_list.selection_set(0)
        with patch("scheduling_system.ui.messagebox.askyesno", return_value=False) as ask, \
             patch("scheduling_system.ui.simpledialog.askstring", return_value=None):
            self.app._open_program_options()
            buttons = self._modal_buttons()
            self.assertEqual([b.cget("text") for b in buttons], ["Edit", "Delete", "Cancel"])
            buttons[1].invoke()
            self.assertIn("BS CpE (COE)", ask.call_args[0][1])
            self.assertEqual(self.db.load_departments()[0].programs, ["BS CpE"])
            self.app._open_program_options()
            buttons = self._modal_buttons()
            buttons[0].invoke()
            self.assertEqual(self.db.load_departments()[0].programs, ["BS CpE"])

    def test_renamed_non_excel_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-excel.xlsx"
            path.write_text("This is definitely not a zip archive")
            with self.assertRaises(ValueError) as raised:
                read_xlsx(path)
        self.assertIn("not a valid Excel workbook", str(raised.exception))

    def test_corrupt_shared_string_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.xlsx"
            write_workbook(
                path,
                sheet_xml([HEADERS_ROW, shared_cell("A2", 99)]),
                shared=["HEADER"],
            )
            with self.assertRaises(ValueError) as raised:
                read_xlsx(path)
        self.assertIn("invalid shared string reference", str(raised.exception))

    def test_stale_subject_edit_raises_and_changes_nothing(self) -> None:
        with self.assertRaises(ValueError) as raised:
            self.db.update_subject(
                "BS CpE", "COE", "1st Year", "1st Sem",
                "CS101 - Wrong Name", "CS999", "Renamed",
            )
        self.assertIn("Subject not found", str(raised.exception))
        curriculum = self.db.load_curriculum("BS CpE", "COE")
        self.assertEqual(
            curriculum["1st Year"]["1st Sem"], ["CS101 - Programming 1"],
        )


if __name__ == "__main__":
    unittest.main()
