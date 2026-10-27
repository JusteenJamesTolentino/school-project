"""Parser and database tests for schedule import and conflict detection.

Run from the admin2 directory with:
    python -B -m unittest test_schedule_lib -v
"""

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from admin2_app.schedule_import import (
    canonical_day,
    canonical_type,
    parse_time,
    parse_time_range,
    read_schedule_xlsx,
)
from scheduling_system.database import Database
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


def shared_cell(reference: str, index: int) -> str:
    return f'<c r="{reference}" t="s"><v>{index}</v></c>'


def write_workbook(path: Path, sheet: str, shared: list[str]) -> None:
    with ZipFile(path, "w") as workbook:
        workbook.writestr("xl/workbook.xml", WORKBOOK_XML)
        workbook.writestr("xl/_rels/workbook.xml.rels", RELS_XML)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet)
        items = "".join(f"<si><t>{text}</t></si>" for text in shared)
        workbook.writestr(
            "xl/sharedStrings.xml", XML_DECL + f'<sst xmlns="{MAIN_NS}">{items}</sst>'
        )


def sheet_from_shared(rows: list[list[int]]) -> str:
    body = "".join(
        f'<row r="{number}">' + "".join(shared_cell(f"{chr(65 + i)}{number}", index)
                                        for i, index in enumerate(row)) + "</row>"
        for number, row in enumerate(rows, 1)
    )
    return XML_DECL + f'<worksheet xmlns="{MAIN_NS}"><sheetData>{body}</sheetData></worksheet>'


HEADER_INDEXES = [0, 1, 2, 3, 4, 5, 6]
SHARED_HEADERS = ["PROGRAM", "PROFESSOR", "DAY", "TIME", "SUBJECT", "SUBJECT  TYPE", "ROOM"]
SHARED_EXTRA = [
    "BSCPE", "JUSTEEN JAMES TOLENTINO", "MONDAY", "7:00AM-1:00PM",
    " CPE212 -  Data Structure and Algoritm ", "LECTURE", "IL-402",
]


class TimeParsingTests(unittest.TestCase):
    def test_parse_time_accepts_common_formats(self) -> None:
        self.assertEqual(parse_time("7:00AM"), 420)
        self.assertEqual(parse_time("7:00 AM"), 420)
        self.assertEqual(parse_time("1:00PM"), 780)
        self.assertEqual(parse_time("12PM"), 720)
        self.assertEqual(parse_time("12AM"), 0)
        self.assertEqual(parse_time("7:30 pm"), 1170)

    def test_parse_time_rejects_garbage(self) -> None:
        for bad in ("13PM", "noon", "", "7:60AM"):
            with self.assertRaises(ValueError):
                parse_time(bad)

    def test_parse_time_range(self) -> None:
        self.assertEqual(parse_time_range("7:00AM-1:00PM"), (420, 780))
        self.assertEqual(parse_time_range("9:00 AM - 10:30 AM"), (540, 630))
        with self.assertRaises(ValueError):
            parse_time_range("1:00PM-7:00AM")

    def test_canonical_day_and_type(self) -> None:
        self.assertEqual(canonical_day("MONDAY"), "Monday")
        self.assertEqual(canonical_day(" friday "), "Friday")
        self.assertEqual(canonical_type("LECTURE"), "Lecture")
        self.assertEqual(canonical_type("lab"), "Laboratory")
        with self.assertRaises(ValueError):
            canonical_day("Someday")
        with self.assertRaises(ValueError):
            canonical_type("Tutorial")


class ScheduleWorkbookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "schedule.xlsx"

    def test_reference_format_parses(self) -> None:
        shared = SHARED_HEADERS + SHARED_EXTRA
        write_workbook(
            self.path,
            sheet_from_shared([HEADER_INDEXES, [7, 8, 9, 10, 11, 12, 13]]),
            shared,
        )
        rows = read_schedule_xlsx(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["program"], "BSCPE")
        self.assertEqual(rows[0]["professor"], "JUSTEEN JAMES TOLENTINO")
        self.assertEqual(rows[0]["day"], "MONDAY")
        self.assertEqual(rows[0]["time"], "7:00AM-1:00PM")
        self.assertEqual(rows[0]["subject"], "CPE212 -  Data Structure and Algoritm")
        self.assertEqual(rows[0]["subject_type"], "LECTURE")
        self.assertEqual(rows[0]["room"], "IL-402")

    def test_year_column_is_read(self) -> None:
        def inline_cell(reference: str, text: str) -> str:
            return f'<c r="{reference}" t="inlineStr"><is><t>{text}</t></is></c>'

        headers = ["PROGRAM", "PROFESSOR", "DAY", "TIME", "SUBJECT",
                   "SUBJECT  TYPE", "ROOM", "YEAR"]
        values = ["BSCPE", "Jane Doe", "MONDAY", "7:00AM-9:00AM",
                  "CS101 - Programming", "LECTURE", "IL-401", "1st Year"]
        rows_xml = (
            f'<row r="1">' + "".join(inline_cell(f"{chr(65 + i)}1", h)
                                     for i, h in enumerate(headers)) + "</row>"
            f'<row r="2">' + "".join(inline_cell(f"{chr(65 + i)}2", v)
                                     for i, v in enumerate(values)) + "</row>"
        )
        write_workbook(
            self.path,
            XML_DECL + f'<worksheet xmlns="{MAIN_NS}"><sheetData>{rows_xml}</sheetData></worksheet>',
            shared=[],
        )
        rows = read_schedule_xlsx(self.path)
        self.assertEqual(rows[0]["year"], "1st Year")

    def test_missing_required_header_is_rejected(self) -> None:
        shared = ["PROGRAM", "DAY", "TIME", "SUBJECT", "SUBJECT  TYPE", "ROOM"]
        write_workbook(
            self.path,
            sheet_from_shared([[0, 1, 2, 3, 4, 5]]),
            shared,
        )
        with self.assertRaises(ValueError) as raised:
            read_schedule_xlsx(self.path)
        self.assertIn("Unrecognized schedule format", str(raised.exception))

    def test_prof_is_accepted_as_professor_header(self) -> None:
        shared = ["PROGRAM", "PROF", "DAY", "TIME", "SUBJECT", "SUBJECT  TYPE"]
        write_workbook(
            self.path,
            sheet_from_shared([[0, 1, 2, 3, 4, 5], [6, 7, 8, 9, 10, 11]]),
            shared + ["BS CpE", "Jane Doe", "MONDAY", "7:00AM-9:00AM", "CS101 - Programming", "Lecture"],
        )
        rows = read_schedule_xlsx(self.path)
        self.assertEqual(rows[0]["professor"], "Jane Doe")

    def test_header_only_workbook_is_rejected(self) -> None:
        write_workbook(self.path, sheet_from_shared([HEADER_INDEXES]), SHARED_HEADERS)
        with self.assertRaises(ValueError):
            read_schedule_xlsx(self.path)

    def test_renamed_non_excel_file_is_rejected(self) -> None:
        self.path.write_text("not a zip")
        with self.assertRaises(ValueError):
            read_schedule_xlsx(self.path)


class ScheduleDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile as _tempfile

        self.db = Database(Path(_tempfile.mkdtemp()) / "schedules.db")
        self.addCleanup(self.db.close)

    @staticmethod
    def make(subject: str, professor: str, day: str, start: int, end: int,
             program: str = "BS CpE", year: str = "1st Year",
             room: str = "") -> Schedule:
        return Schedule(
            department="COE", program=program, subject=subject, subject_type="Lecture",
            professor=professor, day=day, start_minutes=start, end_minutes=end,
            year=year, room=room,
        )

    def test_conflict_detection(self) -> None:
        base = self.make("CS101", "Jane Doe", "Monday", 420, 780)
        self.assertTrue(Database.schedules_conflict(
            base, self.make("CS102", "Jane Doe", "Monday", 600, 660)))          # same prof overlap
        self.assertTrue(Database.schedules_conflict(
            base, self.make("CS102", "Someone Else", "Monday", 770, 900)))      # same section overlap
        self.assertFalse(Database.schedules_conflict(
            base, self.make("CS102", "Someone Else", "Monday", 780, 900)))      # touches, no overlap
        self.assertFalse(Database.schedules_conflict(
            base, self.make("CS102", "Jane Doe", "Tuesday", 420, 780)))         # other day
        self.assertFalse(Database.schedules_conflict(
            base, self.make("CS102", "Someone Else", "Monday", 420, 780, program="BS ECE")))  # other program

    def test_room_overlap_conflicts(self) -> None:
        base = self.make("CS101", "Jane Doe", "Monday", 420, 480)
        base.room = "IL-401"
        same_room = self.make("CS102", "Other Prof", "Monday", 450, 510, program="BS ECE")
        same_room.room = "il-401"
        self.assertTrue(Database.schedules_conflict(base, same_room))           # same room overlap
        same_room.day = "Tuesday"
        self.assertFalse(Database.schedules_conflict(base, same_room))          # other day
        same_room.day = "Monday"
        same_room.room = "IL-405"
        self.assertFalse(Database.schedules_conflict(base, same_room))          # different room
        empty_room = self.make("CS102", "Other Prof", "Monday", 450, 510, program="BS ECE")
        base.room = ""
        self.assertFalse(Database.schedules_conflict(base, empty_room))         # no room info

    def test_conflicting_schedules_excludes_self(self) -> None:
        first = self.make("CS101", "Jane Doe", "Monday", 420, 480)
        self.db.add_schedule(first)
        edited = self.make("CS101", "Jane Doe", "Monday", 450, 510)
        edited.id = first.id
        self.assertEqual(len(self.db.conflicting_schedules(edited)), 1)          # matches its own stored row
        self.assertEqual(self.db.conflicting_schedules(edited, exclude_id=first.id), [])

    def test_update_schedule_round_trip(self) -> None:
        entry = self.make("CS101", "Jane Doe", "Monday", 420, 480, room="IL-401")
        self.db.add_schedule(entry)
        entry.day = "Friday"
        entry.room = "IK-101"
        entry.start_minutes, entry.end_minutes = 840, 900
        self.db.update_schedule(entry)
        loaded = self.db.load_schedules()[0]
        self.assertEqual(
            (loaded.day, loaded.room, loaded.time_display),
            ("Friday", "IK-101", "2:00 PM - 3:00 PM"),
        )

    def test_load_all_rooms_orders_by_location(self) -> None:
        self.db.add_room("IL", "4", "IL-401")
        self.db.add_room("IK", "1", "IK-101")
        self.db.add_room("IK", "1", "IK-102")
        self.assertEqual(self.db.load_all_rooms(), ["IK-101", "IK-102", "IL-401"])

    def test_conflicting_schedules_uses_database_rows(self) -> None:
        first = self.make("CS101", "Jane Doe", "Monday", 420, 780)
        self.db.add_schedule(first)
        candidate = self.make("CS999", "Jane Doe", "Monday", 600, 660)
        conflicts = self.db.conflicting_schedules(candidate)
        self.assertEqual([c.subject for c in conflicts], ["CS101"])

    def test_load_ordering_and_delete(self) -> None:
        tuesday = self.make("GEE1", "Jane Doe", "Tuesday", 540, 600)
        late_monday = self.make("CS200", "Jane Doe", "Monday", 900, 960)
        early_monday = self.make("CS100", "Jane Doe", "Monday", 420, 480)
        for entry in (tuesday, late_monday, early_monday):
            self.db.add_schedule(entry)
        loaded = self.db.load_schedules()
        self.assertEqual([s.subject for s in loaded], ["CS100", "CS200", "GEE1"])
        self.db.delete_schedule(late_monday.id)
        self.assertEqual([s.subject for s in self.db.load_schedules()], ["CS100", "GEE1"])

    def test_time_display_uses_am_pm(self) -> None:
        entry = self.make("CS101", "Jane Doe", "Monday", 420, 780)
        self.assertEqual(entry.time_display, "7:00 AM - 1:00 PM")

    def test_room_overlap_with_partial_building_floor_wildcard(self) -> None:
        base = self.make("CS101", "Jane Doe", "Monday", 420, 480)
        base.room = "IL-401"
        base.room_building = "Main"
        base.room_floor = "4th"
        # Candidate has same room, but empty building/floor (e.g. from Excel import)
        candidate = self.make("CS102", "Other Prof", "Monday", 450, 510, program="BS ECE")
        candidate.room = "IL-401"
        candidate.room_building = ""
        candidate.room_floor = ""
        self.assertTrue(Database.schedules_conflict(base, candidate))

        # Different building specified should NOT conflict
        candidate.room_building = "Annex"
        self.assertFalse(Database.schedules_conflict(base, candidate))

    def test_lec_abbreviation_support(self) -> None:
        self.assertEqual(canonical_type("LEC"), "Lecture")
        self.assertEqual(canonical_type("lec"), "Lecture")

    def test_split_and_format_subject_without_delimiter(self) -> None:
        code, name = Database._split_subject("Calculus")
        self.assertEqual(code, "")
        self.assertEqual(name, "Calculus")
        self.assertEqual(Database._format_subject(code, name), "Calculus")

    def test_program_and_professor_rename_cascades(self) -> None:
        self.db.add_department(Department("CCS", "College of Computer Studies"))
        self.db.add_program("CCS", "BS CS")
        prof = Professor("Jane Doe", "CCS", [("CCS", "BS CS")])
        self.db.add_professor(prof)
        entry = Schedule("CCS", "BS CS", "CS101", "Lecture", "Jane Doe", "Monday", 420, 480)
        self.db.add_schedule(entry)

        self.db.rename_program("CCS", "BS CS", "BS Computer Science")
        self.assertEqual(self.db.load_schedules()[0].program, "BS Computer Science")

        self.db.update_professor(prof.id, Professor("Jane Smith", "CCS", [("CCS", "BS Computer Science")]))
        self.assertEqual(self.db.load_schedules()[0].professor, "Jane Smith")


if __name__ == "__main__":
    unittest.main()
