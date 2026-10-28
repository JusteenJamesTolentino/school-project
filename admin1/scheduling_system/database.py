"""SQLite persistence for the scheduling system."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

from scheduling_system.models import Department, Professor, Schedule


class Database:
    def __init__(self, path: Path | None = None) -> None:
        if path is not None:
            self.path = path
        elif getattr(sys, "frozen", False):
            # Keep editable data outside the PyInstaller bundle. In one-file
            # mode, files beside __file__ live in a temporary extraction dir.
            data_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Admin1"
            data_root.mkdir(parents=True, exist_ok=True)
            self.path = data_root / "scheduling.db"
            bundled_database = Path(__file__).with_name("scheduling.db")
            if not self.path.exists() and bundled_database.exists():
                shutil.copy2(bundled_database, self.path)
        else:
            self.path = Path(__file__).with_name("scheduling.db")
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS programs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                UNIQUE(department_id, name)
            );
            CREATE TABLE IF NOT EXISTS professors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS professor_programs (
                professor_id INTEGER NOT NULL REFERENCES professors(id) ON DELETE CASCADE,
                program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
                PRIMARY KEY(professor_id, program_id)
            );
            CREATE TABLE IF NOT EXISTS curricula (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
                year TEXT NOT NULL,
                semester TEXT NOT NULL,
                subject TEXT NOT NULL,
                subject_code TEXT,
                subject_name TEXT,
                UNIQUE(program_id, year, semester, subject)
            );
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building TEXT NOT NULL,
                floor TEXT NOT NULL,
                room TEXT NOT NULL,
                UNIQUE(building, floor, room)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                program TEXT NOT NULL,
                year TEXT NOT NULL DEFAULT '',
                semester TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                professor TEXT NOT NULL,
                room TEXT NOT NULL DEFAULT '',
                room_building TEXT NOT NULL DEFAULT '',
                room_floor TEXT NOT NULL DEFAULT '',
                day TEXT NOT NULL,
                start_minutes INTEGER NOT NULL,
                end_minutes INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_schedules_day_time ON schedules(day, start_minutes, end_minutes);
            CREATE INDEX IF NOT EXISTS idx_schedules_prof_dept_day ON schedules(professor, department, day);
            CREATE INDEX IF NOT EXISTS idx_schedules_section ON schedules(program, department, year, semester);
            CREATE INDEX IF NOT EXISTS idx_professor_programs_prof_id ON professor_programs(professor_id);
            CREATE INDEX IF NOT EXISTS idx_curricula_lookup ON curricula(program_id, year, semester);
            CREATE INDEX IF NOT EXISTS idx_programs_department_id ON programs(department_id);
            CREATE INDEX IF NOT EXISTS idx_rooms_building_floor ON rooms(building, floor);
            """
        )
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(curricula)").fetchall()
        }
        if "subject_code" not in columns:
            self.connection.execute("ALTER TABLE curricula ADD COLUMN subject_code TEXT")
        if "subject_name" not in columns:
            self.connection.execute("ALTER TABLE curricula ADD COLUMN subject_name TEXT")
        schedule_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(schedules)").fetchall()
        }
        if "room_building" not in schedule_columns:
            self.connection.execute(
                "ALTER TABLE schedules ADD COLUMN room_building TEXT NOT NULL DEFAULT ''"
            )
        if "room_floor" not in schedule_columns:
            self.connection.execute(
                "ALTER TABLE schedules ADD COLUMN room_floor TEXT NOT NULL DEFAULT ''"
            )
        # Single bulk UPDATE with CASE/WHERE pattern for curriculum subject split migration
        self.connection.execute(
            """
            UPDATE curricula
            SET subject_code = CASE
                    WHEN instr(subject, ' - ') > 0 THEN substr(subject, 1, instr(subject, ' - ') - 1)
                    ELSE ''
                END,
                subject_name = CASE
                    WHEN instr(subject, ' - ') > 0 THEN substr(subject, instr(subject, ' - ') + 3)
                    ELSE subject
                END
            WHERE subject_code IS NULL
            """
        )
        self.connection.commit()

    @staticmethod
    def _split_subject(subject: str) -> tuple[str, str]:
        if " - " in subject:
            code, name = subject.split(" - ", 1)
            return code, name
        return "", subject

    @staticmethod
    def _format_subject(code: str, name: str) -> str:
        return f"{code} - {name}" if code and name else code or name

    def load_departments(self, as_dict: bool = False) -> list[Department] | list[dict]:
        cursor = self.connection.cursor()
        rows = cursor.execute(
            """
            SELECT d.code, d.name, p.name
            FROM departments d
            LEFT JOIN programs p ON p.department_id = d.id
            ORDER BY d.code, p.id
            """
        ).fetchall()
        dept_map: dict[str, Department] = {}
        for code, name, prog_name in rows:
            if code not in dept_map:
                dept_map[code] = Department(code, name, [])
            if prog_name is not None:
                dept_map[code].programs.append(prog_name)
        depts = list(dept_map.values())
        if as_dict:
            return [{"code": d.code, "name": d.name, "programs": d.programs} for d in depts]
        return depts

    def load_professors(self, as_dict: bool = False) -> list[Professor] | list[dict]:
        cursor = self.connection.cursor()
        rows = cursor.execute(
            """
            SELECT p.id, p.name, d.code, d_prog.code, pr.name
            FROM professors p
            JOIN departments d ON d.id = p.department_id
            LEFT JOIN professor_programs pp ON pp.professor_id = p.id
            LEFT JOIN programs pr ON pr.id = pp.program_id
            LEFT JOIN departments d_prog ON d_prog.id = pr.department_id
            ORDER BY p.id, pr.id
            """
        ).fetchall()
        prof_map: dict[int, Professor] = {}
        for prof_id, prof_name, dept_code, prog_dept, prog_name in rows:
            if prof_id not in prof_map:
                prof_map[prof_id] = Professor(prof_name, dept_code, [], prof_id)
            if prog_name is not None and prog_dept is not None:
                prof_map[prof_id].programs.append((prog_dept, prog_name))
        profs = list(prof_map.values())
        if as_dict:
            return [
                {"id": p.id, "name": p.name, "department": p.department, "programs": p.programs}
                for p in profs
            ]
        return profs

    def _resolve_program_ids(self, programs: list[tuple[str, str]]) -> list[int]:
        ids = []
        for department_code, program_name in programs:
            row = self.connection.execute(
                """
                SELECT pr.id FROM programs pr
                JOIN departments d ON d.id = pr.department_id
                WHERE d.code = ? AND pr.name = ?
                """,
                (department_code, program_name),
            ).fetchone()
            if row:
                ids.append(row["id"])
        return ids

    def add_department(self, department: Department) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO departments (code, name) VALUES (?, ?)",
                (department.code, department.name),
            )

    def add_program(self, department_code: str, program: str) -> None:
        department = self.connection.execute(
            "SELECT id FROM departments WHERE code = ?", (department_code,)
        ).fetchone()
        if department is None:
            raise ValueError("Department does not exist")
        with self.connection:
            self.connection.execute(
                "INSERT INTO programs (department_id, name) VALUES (?, ?)",
                (department["id"], program),
            )

    def rename_program(self, department_code: str, old_name: str, new_name: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE programs SET name = ?
                WHERE name = ? AND department_id = (SELECT id FROM departments WHERE code = ?)
                """,
                (new_name, old_name, department_code),
            )
            self.connection.execute(
                "UPDATE schedules SET program = ? WHERE program = ? AND department = ?",
                (new_name, old_name, department_code),
            )

    def delete_program(self, department_code: str, program: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                DELETE FROM programs
                WHERE name = ? AND department_id = (SELECT id FROM departments WHERE code = ?)
                """,
                (program, department_code),
            )
            self.connection.execute(
                "DELETE FROM schedules WHERE program = ? AND department = ?",
                (program, department_code),
            )

    def load_program_summary(self, department_code: str, program: str) -> dict[str, int]:
        row = self.connection.execute(
            """
            SELECT pr.id,
                   (SELECT COUNT(*) FROM curricula c WHERE c.program_id = pr.id) AS subjects,
                   (SELECT COUNT(*) FROM professor_programs pp WHERE pp.program_id = pr.id) AS assignments
            FROM programs pr
            JOIN departments d ON d.id = pr.department_id
            WHERE pr.name = ? AND d.code = ?
            """,
            (program, department_code),
        ).fetchone()
        if row is None:
            raise ValueError("Program does not exist")
        return {"subjects": row["subjects"], "assignments": row["assignments"]}

    def add_professor(self, professor: Professor) -> None:
        department = self.connection.execute(
            "SELECT id FROM departments WHERE code = ?", (professor.department,)
        ).fetchone()
        if department is None:
            raise ValueError("Department does not exist")
        program_ids = self._resolve_program_ids(professor.programs)
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO professors (name, department_id) VALUES (?, ?)",
                (professor.name, department["id"]),
            )
            professor.id = cursor.lastrowid
            self.connection.executemany(
                "INSERT INTO professor_programs (professor_id, program_id) VALUES (?, ?)",
                [(professor.id, program_id) for program_id in program_ids],
            )

    def update_professor(self, professor_id: int, professor: Professor) -> None:
        row = self.connection.execute(
            """
            SELECT p.id, p.name, d.code AS department
            FROM professors p
            JOIN departments d ON d.id = p.department_id
            WHERE p.id = ?
            """,
            (professor_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Professor does not exist")
        old_name = row["name"]
        program_ids = self._resolve_program_ids(professor.programs)
        with self.connection:
            self.connection.execute(
                "UPDATE professors SET name = ? WHERE id = ?",
                (professor.name, professor_id),
            )
            self.connection.execute(
                "DELETE FROM professor_programs WHERE professor_id = ?", (professor_id,)
            )
            self.connection.executemany(
                "INSERT INTO professor_programs (professor_id, program_id) VALUES (?, ?)",
                [(professor_id, program_id) for program_id in program_ids],
            )
            if old_name != professor.name:
                self.connection.execute(
                    """
                    UPDATE schedules SET professor = ?
                    WHERE professor = ? AND department = ?
                    """,
                    (professor.name, old_name, row["department"]),
                )

    def delete_professor(self, professor_id: int) -> None:
        row = self.connection.execute(
            """
            SELECT p.name, d.code AS department
            FROM professors p
            JOIN departments d ON d.id = p.department_id
            WHERE p.id = ?
            """,
            (professor_id,),
        ).fetchone()
        with self.connection:
            if row:
                self.connection.execute(
                    """
                    DELETE FROM schedules
                    WHERE professor = ? AND department = ?
                    """,
                    (row["name"], row["department"]),
                )
            self.connection.execute(
                "DELETE FROM professors WHERE id = ?", (professor_id,)
            )

    def replace_curriculum(
        self, program: str, department: str, curriculum: dict[str, dict[str, list[str]]]
    ) -> int:
        program_row = self.connection.execute(
            """
            SELECT pr.id FROM programs pr
            JOIN departments d ON d.id = pr.department_id
            WHERE pr.name = ? AND d.code = ?
            """,
            (program, department),
        ).fetchone()
        if program_row is None:
            raise ValueError("Program does not exist")
        records = []
        seen: set[tuple[str, str, str]] = set()
        for year, semesters in curriculum.items():
            for semester, subjects in semesters.items():
                for subject in subjects:
                    key = (year, semester, subject)
                    if key in seen:
                        raise ValueError(
                            f"'{subject}' appears more than once in {year} {semester}"
                        )
                    seen.add(key)
                    records.append(
                        (
                            program_row["id"], year, semester, subject,
                            *Database._split_subject(subject),
                        )
                    )
        with self.connection:
            self.connection.execute(
                "DELETE FROM curricula WHERE program_id = ?", (program_row["id"],)
            )
            self.connection.executemany(
                """
                INSERT INTO curricula
                    (program_id, year, semester, subject, subject_code, subject_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                records,
            )
        return len(records)

    def add_subject(
        self, program: str, department: str, year: str, semester: str,
        subject_code: str, subject_name: str,
    ) -> None:
        program_row = self.connection.execute(
            """
            SELECT pr.id FROM programs pr
            JOIN departments d ON d.id = pr.department_id
            WHERE pr.name = ? AND d.code = ?
            """,
            (program, department),
        ).fetchone()
        if program_row is None:
            raise ValueError("Program does not exist")
        subject = self._format_subject(subject_code, subject_name)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO curricula
                    (program_id, year, semester, subject, subject_code, subject_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (program_row["id"], year, semester, subject, subject_code, subject_name),
            )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def add_room(self, building: str, floor: str, room: str) -> None:
        building, floor, room = (value.strip() for value in (building, floor, room))
        if not building or not floor or not room:
            raise ValueError("Building, floor, and room are required")
        with self.connection:
            self.connection.execute(
                "INSERT INTO rooms (building, floor, room) VALUES (?, ?, ?)",
                (building, floor, room),
            )

    def load_room_locations(self) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT DISTINCT building, floor FROM rooms ORDER BY building, floor"
        ).fetchall()
        return [(row["building"], row["floor"]) for row in rows]

    def load_rooms(self, building: str, floor: str) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT room FROM rooms
            WHERE building = ? AND floor = ?
            ORDER BY id
            """,
            (building, floor),
        ).fetchall()
        return [row["room"] for row in rows]

    def load_curriculum(
        self, program: str, department: str
    ) -> dict[str, dict[str, list[str]]]:
        rows = self.connection.execute(
            """
            SELECT c.year, c.semester,
                   COALESCE(c.subject_code, '') AS subject_code,
                   COALESCE(c.subject_name, c.subject) AS subject_name
            FROM curricula c
            JOIN programs pr ON pr.id = c.program_id
            JOIN departments d ON d.id = pr.department_id
            WHERE pr.name = ? AND d.code = ?
            ORDER BY c.id
            """,
            (program, department),
        ).fetchall()
        curriculum = {
            f"{year} Year": {"1st Sem": [], "2nd Sem": []}
            for year in ("1st", "2nd", "3rd", "4th")
        }
        for row in rows:
            curriculum[row["year"]][row["semester"]].append(
                self._format_subject(row["subject_code"], row["subject_name"])
            )
        return curriculum

    def update_subject(
        self,
        program: str,
        department: str,
        year: str,
        semester: str,
        old_subject: str,
        subject_code: str,
        subject_name: str,
    ) -> None:
        program_row = self.connection.execute(
            """
            SELECT pr.id FROM programs pr
            JOIN departments d ON d.id = pr.department_id
            WHERE pr.name = ? AND d.code = ?
            """,
            (program, department),
        ).fetchone()
        if program_row is None:
            raise ValueError("Program does not exist")
        old_code, old_name = self._split_subject(old_subject)
        new_subject = self._format_subject(subject_code, subject_name)
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE curricula
                SET subject = ?, subject_code = ?, subject_name = ?
                WHERE program_id = ? AND year = ? AND semester = ?
                  AND COALESCE(subject_code, '') = ?
                  AND COALESCE(subject_name, subject) = ?
                """,
                (
                    new_subject, subject_code, subject_name, program_row["id"],
                    year, semester, old_code, old_name,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    "Subject not found in this curriculum; it may have changed. "
                    "Reopen the subject and try again."
                )

    DAY_ORDER = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    @staticmethod
    def schedules_conflict(first: Schedule, second: Schedule) -> bool:
        """True when two entries overlap in time and share a professor, section, or room."""
        if first.day != second.day:
            return False
        overlaps = (first.start_minutes < second.end_minutes
                    and second.start_minutes < first.end_minutes)
        if not overlaps:
            return False
        same_professor = first.professor.strip().lower() == second.professor.strip().lower()
        same_section = (
            first.department, first.program, first.year, first.semester
        ) == (second.department, second.program, second.year, second.semester)
        same_room = False
        if bool(first.room.strip()) and first.room.strip().lower() == second.room.strip().lower():
            b1 = first.room_building.strip().lower()
            b2 = second.room_building.strip().lower()
            f1 = first.room_floor.strip().lower()
            f2 = second.room_floor.strip().lower()
            building_match = not b1 or not b2 or b1 == b2
            floor_match = not f1 or not f2 or f1 == f2
            same_room = building_match and floor_match
        return same_professor or same_section or same_room

    def conflicting_schedules(
        self, schedule: Schedule, exclude_id: int | None = None
    ) -> list[Schedule]:
        prof_pattern = schedule.professor.strip().lower()
        room_pattern = schedule.room.strip().lower()
        cursor = self.connection.cursor()
        query = """
            SELECT department, program, subject, subject_type, professor, day,
                   start_minutes, end_minutes, year, semester, room, id,
                   room_building, room_floor
            FROM schedules
            WHERE day = ?
              AND start_minutes < ?
              AND end_minutes > ?
              AND (
                  lower(trim(professor)) = ?
                  OR (department = ? AND program = ? AND year = ? AND semester = ?)
                  OR (? != '' AND lower(trim(room)) = ?)
              )
        """
        params: list[object] = [
            schedule.day,
            schedule.end_minutes,
            schedule.start_minutes,
            prof_pattern,
            schedule.department,
            schedule.program,
            schedule.year,
            schedule.semester,
            room_pattern,
            room_pattern,
        ]
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        query += """
            ORDER BY CASE day
                WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
                WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6
                ELSE 7 END,
                start_minutes, professor, subject
        """
        rows = cursor.execute(query, params).fetchall()
        candidates = [Schedule(*r) for r in rows]
        return [c for c in candidates if self.schedules_conflict(c, schedule)]

    def update_schedule(self, schedule: Schedule) -> None:
        self._validate_schedule(schedule)
        with self.connection:
            self.connection.execute(
                """
                UPDATE schedules
                SET department = ?, program = ?, year = ?, semester = ?,
                    subject = ?, subject_type = ?, professor = ?, room = ?,
                    room_building = ?, room_floor = ?,
                    day = ?, start_minutes = ?, end_minutes = ?
                WHERE id = ?
                """,
                (schedule.department, schedule.program, schedule.year, schedule.semester,
                 schedule.subject, schedule.subject_type, schedule.professor,
                 schedule.room, schedule.room_building, schedule.room_floor,
                 schedule.day, schedule.start_minutes,
                 schedule.end_minutes, schedule.id),
            )
            if self.connection.execute(
                "SELECT changes()"
            ).fetchone()[0] == 0:
                raise ValueError("Schedule does not exist")

    @classmethod
    def _validate_schedule(cls, schedule: Schedule) -> None:
        if schedule.day not in cls.DAY_ORDER:
            raise ValueError("Invalid schedule day")
        if schedule.subject_type not in {"Lecture", "Laboratory"}:
            raise ValueError("Invalid subject type")
        if schedule.start_minutes < 0 or schedule.end_minutes <= schedule.start_minutes:
            raise ValueError("Invalid schedule time range")
        if not all(value.strip() for value in (schedule.program, schedule.subject, schedule.professor)):
            raise ValueError("Schedule fields cannot be empty")

    def add_schedule(self, schedule: Schedule) -> None:
        self._validate_schedule(schedule)
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO schedules
                    (department, program, year, semester, subject, subject_type,
                     professor, room, room_building, room_floor, day, start_minutes, end_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (schedule.department, schedule.program, schedule.year, schedule.semester,
                 schedule.subject, schedule.subject_type, schedule.professor,
                schedule.room, schedule.room_building, schedule.room_floor,
                schedule.day, schedule.start_minutes, schedule.end_minutes),
            )
            schedule.id = cursor.lastrowid

    def load_schedules(self, as_dict: bool = False) -> list[Schedule] | list[dict]:
        cursor = self.connection.cursor()
        rows = cursor.execute(
            """
            SELECT department, program, subject, subject_type, professor, day,
                   start_minutes, end_minutes, year, semester, room, id,
                   room_building, room_floor
            FROM schedules
            ORDER BY CASE day
                WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
                WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6
                ELSE 7 END,
                start_minutes, professor, subject
            """
        ).fetchall()
        if as_dict:
            return [
                {
                    "department": r[0], "program": r[1], "subject": r[2], "subject_type": r[3],
                    "professor": r[4], "day": r[5], "start_minutes": r[6], "end_minutes": r[7],
                    "year": r[8], "semester": r[9], "room": r[10], "id": r[11],
                    "room_building": r[12], "room_floor": r[13],
                }
                for r in rows
            ]
        return [Schedule(*r) for r in rows]

    def load_all_rooms(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT room FROM rooms ORDER BY building, floor, room"
        ).fetchall()
        return [row["room"] for row in rows]

    def load_room_details(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT building, floor, room FROM rooms ORDER BY building, floor, room"
        ).fetchall()
        return [f"{row['building']} / {row['floor']} / {row['room']}" for row in rows]

    def delete_schedule(self, schedule_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM schedules WHERE id = ?", (schedule_id,)
            )


    def delete_department(self, code: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM schedules WHERE department = ?", (code,))
            self.connection.execute("DELETE FROM departments WHERE code = ?", (code,))

    def delete_room(self, building: str, floor: str, room: str) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM rooms WHERE building = ? AND floor = ? AND room = ?",
                (building, floor, room),
            )
    def close(self) -> None:
        self.connection.close()
