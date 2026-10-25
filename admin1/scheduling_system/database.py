"""SQLite persistence for the scheduling system."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

from scheduling_system.models import Department, Professor


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
        rows = self.connection.execute(
            "SELECT id, subject FROM curricula WHERE subject_code IS NULL"
        ).fetchall()
        for row in rows:
            code, name = self._split_subject(row["subject"])
            self.connection.execute(
                "UPDATE curricula SET subject_code = ?, subject_name = ? WHERE id = ?",
                (code, name, row["id"]),
            )
        self.connection.commit()

    @staticmethod
    def _split_subject(subject: str) -> tuple[str, str]:
        if " - " in subject:
            code, name = subject.split(" - ", 1)
            return code, name
        return subject, subject

    @staticmethod
    def _format_subject(code: str, name: str) -> str:
        return f"{code} - {name}" if code and name else code or name

    def load_departments(self) -> list[Department]:
        rows = self.connection.execute(
            "SELECT id, code, name FROM departments ORDER BY code"
        ).fetchall()
        departments = []
        for row in rows:
            programs = self.connection.execute(
                "SELECT name FROM programs WHERE department_id = ? ORDER BY id",
                (row["id"],),
            ).fetchall()
            departments.append(Department(row["code"], row["name"], [item["name"] for item in programs]))
        return departments

    def load_professors(self) -> list[Professor]:
        rows = self.connection.execute(
            """
            SELECT p.id, p.name, d.code AS department
            FROM professors p
            JOIN departments d ON d.id = p.department_id
            ORDER BY p.id
            """
        ).fetchall()
        professors = []
        for row in rows:
            program_rows = self.connection.execute(
                """
                SELECT d.code, pr.name
                FROM professor_programs pp
                JOIN programs pr ON pr.id = pp.program_id
                JOIN departments d ON d.id = pr.department_id
                WHERE pp.professor_id = ?
                ORDER BY pr.id
                """,
                (row["id"],),
            ).fetchall()
            programs = [(item["code"], item["name"]) for item in program_rows]
            professors.append(Professor(row["name"], row["department"], programs, row["id"]))
        return professors

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

    def delete_program(self, department_code: str, program: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                DELETE FROM programs
                WHERE name = ? AND department_id = (SELECT id FROM departments WHERE code = ?)
                """,
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
            "SELECT id FROM professors WHERE id = ?", (professor_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Professor does not exist")
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

    def delete_professor(self, professor_id: int) -> None:
        with self.connection:
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

    def close(self) -> None:
        self.connection.close()
