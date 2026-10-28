"""Targeted regression and unit tests for database performance optimizations."""

import sys
import tempfile
import unittest
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from scheduling_system.database import Database
from scheduling_system.models import Department, Professor, Schedule


class PerformanceOptimizationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_perf.db"
        self.db = Database(self.db_path)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_schema_indexes_created(self) -> None:
        """Verify that all required performance indexes are created on startup."""
        indexes = {
            row["name"]
            for row in self.db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        expected_indexes = {
            "idx_schedules_day_time",
            "idx_schedules_prof_dept_day",
            "idx_schedules_section",
            "idx_professor_programs_prof_id",
            "idx_curricula_lookup",
            "idx_programs_department_id",
            "idx_rooms_building_floor",
        }
        for idx in expected_indexes:
            self.assertIn(idx, indexes, f"Missing index: {idx}")

    def test_single_join_load_departments(self) -> None:
        """Verify load_departments loads departments with 0, 1, or multiple programs."""
        self.db.add_department(Department("EMPTY", "Empty Dept"))
        self.db.add_department(Department("CCS", "College of Computer Studies"))
        self.db.add_program("CCS", "BSCS")
        self.db.add_program("CCS", "BSIT")

        depts = self.db.load_departments()
        dept_dict = {d.code: d for d in depts}
        self.assertIn("EMPTY", dept_dict)
        self.assertEqual(dept_dict["EMPTY"].programs, [])
        self.assertIn("CCS", dept_dict)
        self.assertEqual(dept_dict["CCS"].programs, ["BSCS", "BSIT"])

        # Test dictionary return mode
        depts_dict_mode = self.db.load_departments(as_dict=True)
        self.assertIsInstance(depts_dict_mode, list)
        self.assertIsInstance(depts_dict_mode[0], dict)
        self.assertIn("code", depts_dict_mode[0])
        self.assertIn("programs", depts_dict_mode[0])

    def test_single_join_load_professors(self) -> None:
        """Verify load_professors loads professors with multiple program links or no programs."""
        self.db.add_department(Department("CCS", "College of Computer Studies"))
        self.db.add_department(Department("COE", "College of Engineering"))
        self.db.add_program("CCS", "BSCS")
        self.db.add_program("COE", "BSCpE")

        p1 = Professor("Dr. Alan Turing", "CCS", [("CCS", "BSCS"), ("COE", "BSCpE")])
        p2 = Professor("Prof. No Assignment", "COE", [])
        self.db.add_professor(p1)
        self.db.add_professor(p2)

        professors = self.db.load_professors()
        prof_dict = {p.name: p for p in professors}

        self.assertIn("Dr. Alan Turing", prof_dict)
        self.assertEqual(prof_dict["Dr. Alan Turing"].programs, [("CCS", "BSCS"), ("COE", "BSCpE")])
        self.assertIn("Prof. No Assignment", prof_dict)
        self.assertEqual(prof_dict["Prof. No Assignment"].programs, [])

        # Test dict mode
        profs_as_dict = self.db.load_professors(as_dict=True)
        self.assertIsInstance(profs_as_dict, list)
        self.assertIsInstance(profs_as_dict[0], dict)
        self.assertIn("name", profs_as_dict[0])
        self.assertIn("programs", profs_as_dict[0])

    def test_migration_curriculum_split_bulk(self) -> None:
        """Verify the bulk SQL UPDATE migration on curricula without row-by-row iteration."""
        # Manually insert curriculum rows with subject_code IS NULL
        self.db.add_department(Department("CCS", "College of Computer Studies"))
        self.db.add_program("CCS", "BSCS")
        prog_id = self.db.connection.execute("SELECT id FROM programs WHERE name = 'BSCS'").fetchone()["id"]

        self.db.connection.execute(
            """
            INSERT INTO curricula (program_id, year, semester, subject, subject_code, subject_name)
            VALUES (?, '1st', '1st Sem', 'CS101 - Introduction to Programming', NULL, NULL),
                   (?, '1st', '1st Sem', 'Calculus', NULL, NULL)
            """,
            (prog_id, prog_id),
        )
        self.db.connection.commit()

        # Trigger migration schema update
        self.db._create_schema()

        rows = self.db.connection.execute(
            "SELECT subject, subject_code, subject_name FROM curricula ORDER BY id"
        ).fetchall()

        self.assertEqual(rows[0]["subject_code"], "CS101")
        self.assertEqual(rows[0]["subject_name"], "Introduction to Programming")
        self.assertEqual(rows[1]["subject_code"], "")
        self.assertEqual(rows[1]["subject_name"], "Calculus")

    def test_conflict_detection_selective_filtering(self) -> None:
        """Verify conflicting_schedules query accurately identifies conflicts without scanning whole table."""
        base = Schedule(
            department="CCS", program="BSCS", year="1st", semester="1st Sem",
            subject="CS101", subject_type="Lecture", professor="Prof Smith",
            day="Monday", start_minutes=480, end_minutes=600, room="IL-101",
            room_building="Main", room_floor="1st",
        )
        self.db.add_schedule(base)

        # 1. Overlapping professor
        prof_conflict = Schedule(
            department="COE", program="BSCpE", year="2nd", semester="1st Sem",
            subject="CPE201", subject_type="Lecture", professor="prof smith",  # case-insensitive
            day="Monday", start_minutes=540, end_minutes=660, room="IL-202",
        )
        conflicts = self.db.conflicting_schedules(prof_conflict)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].id, base.id)

        # 2. Overlapping section
        section_conflict = Schedule(
            department="CCS", program="BSCS", year="1st", semester="1st Sem",
            subject="MATH101", subject_type="Lecture", professor="Prof Other",
            day="Monday", start_minutes=480, end_minutes=600, room="IL-303",
        )
        conflicts = self.db.conflicting_schedules(section_conflict)
        self.assertEqual(len(conflicts), 1)

        # 3. Overlapping room with building wildcard
        room_wildcard = Schedule(
            department="COE", program="BSCpE", year="3rd", semester="1st Sem",
            subject="CPE301", subject_type="Lecture", professor="Prof Third",
            day="Monday", start_minutes=500, end_minutes=560, room="il-101",
            room_building="", room_floor="",
        )
        conflicts = self.db.conflicting_schedules(room_wildcard)
        self.assertEqual(len(conflicts), 1)

        # 4. Overlapping room with different building (no conflict)
        diff_building = Schedule(
            department="COE", program="BSCpE", year="3rd", semester="1st Sem",
            subject="CPE301", subject_type="Lecture", professor="Prof Third",
            day="Monday", start_minutes=500, end_minutes=560, room="IL-101",
            room_building="Annex", room_floor="1st",
        )
        self.assertEqual(len(self.db.conflicting_schedules(diff_building)), 0)

        # 5. Non-overlapping times (touching edges)
        touching = Schedule(
            department="CCS", program="BSCS", year="1st", semester="1st Sem",
            subject="CS102", subject_type="Lecture", professor="Prof Smith",
            day="Monday", start_minutes=600, end_minutes=720, room="IL-101",
        )
        self.assertEqual(len(self.db.conflicting_schedules(touching)), 0)

        # 6. Exclude id
        self.assertEqual(len(self.db.conflicting_schedules(base, exclude_id=base.id)), 0)

        # 7. Empty room does not conflict with another empty room
        empty_room_base = Schedule(
            department="CAS", program="BAComm", year="1st", semester="1st Sem",
            subject="COMM1", subject_type="Lecture", professor="Prof A",
            day="Tuesday", start_minutes=480, end_minutes=600, room="",
        )
        empty_room_other = Schedule(
            department="CED", program="BEd", year="2nd", semester="2nd Sem",
            subject="ED1", subject_type="Lecture", professor="Prof B",
            day="Tuesday", start_minutes=480, end_minutes=600, room="",
        )
        self.db.add_schedule(empty_room_base)
        self.assertEqual(len(self.db.conflicting_schedules(empty_room_other)), 0)

    def test_model_slots_optimization(self) -> None:
        """Verify models define slots for memory optimization."""
        s = Schedule("CCS", "BSCS", "CS101", "Lecture", "Prof", "Monday", 480, 540)
        d = Department("CCS", "Computer Studies")
        p = Professor("Prof", "CCS", [])

        self.assertTrue(hasattr(s, "__slots__"))
        self.assertTrue(hasattr(d, "__slots__"))
        self.assertTrue(hasattr(p, "__slots__"))

    def test_repeated_add_update_delete_cycle(self) -> None:
        """Stress test rapid schedule operations."""
        s = Schedule(
            department="CCS", program="BSCS", year="1st", semester="1st Sem",
            subject="CS101", subject_type="Lecture", professor="Prof X",
            day="Monday", start_minutes=480, end_minutes=540, room="101",
        )
        self.db.add_schedule(s)
        self.assertIsNotNone(s.id)

        # Rapid updates
        for day in Database.DAY_ORDER:
            s.day = day
            self.db.update_schedule(s)
            loaded = self.db.load_schedules()[0]
            self.assertEqual(loaded.day, day)

        self.db.delete_schedule(s.id)
        self.assertEqual(len(self.db.load_schedules()), 0)


if __name__ == "__main__":
    unittest.main()
