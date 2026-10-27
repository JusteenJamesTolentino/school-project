"""Isolated regression tests for database location configuration.

Run from the admin1 directory with:
    python -B -m unittest test_database_config -v
"""

import sqlite3
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scheduling_system.database import Database as RealDatabase
from scheduling_system.models import Department
from scheduling_system.ui import SchedulingApp


class DatabaseConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base_dir = Path(self.directory.name) / "base"
        self.base_dir.mkdir()
        self.base_path = self.base_dir / "scheduling.db"
        self.bootstrap = RealDatabase(self.base_path)
        self.bootstrap.add_department(Department("COE", "Engineering"))
        self.bootstrap.add_program("COE", "BS CpE")
        self.app = None
        self.addCleanup(self._close_current_db)

    def _close_current_db(self) -> None:
        if self.app is not None:
            try:
                self.app.database.close()
            except sqlite3.Error:
                pass

    def run_app(self) -> SchedulingApp:
        def factory(path=None):
            return self.bootstrap if path is None else RealDatabase(path)

        with patch("scheduling_system.ui.Database", side_effect=factory):
            self.app = SchedulingApp(self.root)
        self.app.show_notice = Mock()
        return self.app

    def test_database_starts_at_default_location(self) -> None:
        app = self.run_app()
        self.assertEqual(app.database.path, self.base_path)
        self.assertEqual(app.database.get_setting("database_path"), str(self.base_path))

    def test_move_to_new_folder_creates_empty_database(self) -> None:
        app = self.run_app()
        target_dir = Path(self.directory.name) / "new home"
        with patch("scheduling_system.ui.filedialog.askdirectory",
                   return_value=str(target_dir)):
            app._choose_database_location()
        target = target_dir / "scheduling.db"
        self.assertTrue(target.exists())
        self.assertEqual(app.database.path, target)
        self.assertEqual(app.database.get_setting("database_path"), str(target))
        self.assertEqual(app.database.load_departments(), [])
        self.assertEqual(app.database.load_professors(), [])
        app.show_notice.assert_called_once()
        self.assertIn("New database created", app.show_notice.call_args[0][0])
        self.assertIn(str(target_dir), app.show_notice.call_args[0][0])

    def test_first_curriculum_import_populates_a_new_database(self) -> None:
        app = self.run_app()
        target_dir = Path(self.directory.name) / "new home"
        app._move_database(target_dir)
        app.show_notice.reset_mock()
        workbook = Path(self.directory.name) / "curriculum.xlsx"
        curriculum = {
            "1st Year": {"1st Sem": ["CS101 - Programming 1"], "2nd Sem": []},
            "2nd Year": {"1st Sem": [], "2nd Sem": []},
            "3rd Year": {"1st Sem": [], "2nd Sem": []},
            "4th Year": {"1st Sem": [], "2nd Sem": []},
        }
        code = Mock(get=Mock(return_value="CCS"))
        name = Mock(get=Mock(return_value="College of Computer Studies"))
        program = Mock(get=Mock(return_value="BS Computer Science"))
        dialog = Mock()
        with patch("scheduling_system.ui.filedialog.askopenfilename",
                   return_value=str(workbook)), \
             patch("scheduling_system.ui.read_xlsx", return_value=curriculum):
            app._choose_first_curriculum_file(code, name, program, dialog)
        self.assertEqual(
            app.database.load_departments()[0].programs, ["BS Computer Science"],
        )
        self.assertEqual(
            app.database.load_curriculum("BS Computer Science", "CCS"), curriculum,
        )
        dialog.destroy.assert_called_once()
        self.assertIn("Created CCS / BS Computer Science", app.show_notice.call_args[0][0])

    def test_move_to_folder_with_existing_database_adopts_it(self) -> None:
        target_dir = Path(self.directory.name) / "existing"
        target_dir.mkdir()
        existing = RealDatabase(target_dir / "scheduling.db")
        existing.add_department(Department("LEGACY", "Old data"))
        existing.close()
        app = self.run_app()
        with patch("scheduling_system.ui.filedialog.askdirectory",
                   return_value=str(target_dir)):
            app._choose_database_location()
        self.assertEqual(app.database.path, target_dir / "scheduling.db")
        self.assertEqual([d.code for d in app.database.load_departments()], ["LEGACY"])

    def test_move_forwards_pointer_in_previous_database(self) -> None:
        app = self.run_app()
        target_dir = Path(self.directory.name) / "elsewhere"
        with patch("scheduling_system.ui.filedialog.askdirectory",
                   return_value=str(target_dir)):
            app._choose_database_location()
        previous = RealDatabase(self.base_path)
        try:
            self.assertEqual(
                previous.get_setting("database_path"), str(target_dir / "scheduling.db"),
            )
        finally:
            previous.close()

    def test_restart_opens_configured_database(self) -> None:
        target_dir = Path(self.directory.name) / "configured"
        target_path = target_dir / "scheduling.db"
        target_dir.mkdir()
        configured = RealDatabase(target_path)
        configured.add_department(Department("CCS", "Configured data"))
        configured.set_setting("database_path", str(target_path))
        configured.close()
        self.bootstrap.set_setting("database_path", str(target_path))
        app = self.run_app()
        self.assertEqual(app.database.path, target_path)
        self.assertEqual([d.code for d in app.database.load_departments()], ["CCS"])

    def test_stale_configured_path_falls_back_to_default(self) -> None:
        self.bootstrap.set_setting(
            "database_path", str(Path(self.directory.name) / "missing" / "scheduling.db"),
        )
        app = self.run_app()
        self.assertEqual(app.database.path, self.base_path)
        self.assertEqual([d.code for d in app.database.load_departments()], ["COE"])


if __name__ == "__main__":
    unittest.main()
