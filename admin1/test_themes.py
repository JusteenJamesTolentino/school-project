"""Isolated regression tests for theme settings persistence.

Run from the admin1 directory with: python -B -m unittest test_themes -v
"""

import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from unittest.mock import patch

from scheduling_system.database import Database
from scheduling_system.ui import SchedulingApp


class SettingPersistenceTests(unittest.TestCase):
    def test_theme_setting_round_trips_across_connections(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.db"
            db = Database(path)
            try:
                self.assertIsNone(db.get_setting("theme"))
                self.assertEqual(db.get_setting("theme", "light"), "light")
                db.set_setting("theme", "dark")
                self.assertEqual(db.get_setting("theme"), "dark")
                db.set_setting("theme", "light")
                self.assertEqual(db.get_setting("theme"), "light")
            finally:
                db.close()
            db = Database(path)
            try:
                self.assertEqual(db.get_setting("theme"), "light")
            finally:
                db.close()


class ThemeUITests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.db = Database(Path(":memory:"))
        self.addCleanup(self.db.close)
        with patch("scheduling_system.ui.Database", return_value=self.db):
            self.app = SchedulingApp(self.root)

    def test_defaults_to_light_theme(self) -> None:
        self.assertEqual(self.app.theme_name, "light")
        self.assertEqual(self.app.COLORS["panel"], "#ffffff")
        self.assertEqual(self.root.cget("background"), "#f1f5f9")

    def test_apply_theme_switches_colors_and_persists(self) -> None:
        self.app._apply_theme("dark")
        self.assertEqual(self.app.theme_name, "dark")
        self.assertEqual(self.app.COLORS["panel"], "#171616")
        self.assertEqual(self.app.COLORS["button"], "#171616")
        self.assertEqual(self.app.COLORS["dropdown"], "#292626")
        self.assertEqual(self.root.cget("background"), "#1f1e1d")
        self.assertEqual(self.db.get_setting("theme"), "dark")
        self.assertEqual(self.app.board_canvas.cget("background"), "#292626")
        self.assertEqual(self.app.notice_label.cget("bg"), "#292626")

    def test_readonly_combobox_uses_dropdown_colors(self) -> None:
        from tkinter import ttk

        style = ttk.Style(self.root)
        self.app._apply_theme("dark")
        self.assertEqual(
            style.lookup("TCombobox", "fieldbackground", ["readonly"]), "#292626",
        )
        self.assertEqual(style.lookup("TCombobox", "foreground", ["readonly"]), "#e8e6e3")
        self.app._apply_theme("light")
        self.assertEqual(
            style.lookup("TCombobox", "fieldbackground", ["readonly"]), "#ffffff",
        )
        self.assertEqual(style.lookup("TCombobox", "foreground", ["readonly"]), "#0f172a")

    def test_saved_theme_restored_on_next_start(self) -> None:
        self.db.set_setting("theme", "dark")
        try:
            fresh_root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        fresh_root.withdraw()
        self.addCleanup(fresh_root.destroy)
        with patch("scheduling_system.ui.Database", return_value=self.db):
            app = SchedulingApp(fresh_root)
        self.assertEqual(app.theme_name, "dark")
        self.assertEqual(app.COLORS["ink"], "#e8e6e3")

    def test_unknown_saved_theme_falls_back_to_light(self) -> None:
        self.db.set_setting("theme", "midnight")
        try:
            fresh_root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        fresh_root.withdraw()
        self.addCleanup(fresh_root.destroy)
        with patch("scheduling_system.ui.Database", return_value=self.db):
            app = SchedulingApp(fresh_root)
        self.assertEqual(app.theme_name, "light")

    def test_apply_theme_ignores_unknown_names(self) -> None:
        self.app._apply_theme("midnight")
        self.assertEqual(self.app.theme_name, "light")
        self.assertIsNone(self.db.get_setting("theme"))

    def test_dialogs_center_over_main_window(self) -> None:
        self.root.geometry("800x600")
        self.root.update_idletasks()
        dialog = tk.Toplevel(self.root)
        self.addCleanup(dialog.destroy)
        dialog.geometry("200x100")
        self.app._center_dialog(dialog)
        dialog.update_idletasks()
        expected_x = self.root.winfo_rootx() + (self.root.winfo_width() - 200) // 2
        expected_y = self.root.winfo_rooty() + (self.root.winfo_height() - 100) // 2
        self.assertEqual(dialog.winfo_x(), max(expected_x, 0))
        self.assertEqual(dialog.winfo_y(), max(expected_y, 0))

    def test_settings_dialog_contains_light_and_dark_choices(self) -> None:
        self.app.open_settings_dialog()
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        try:
            radios = [
                widget for widget in dialog.winfo_children()[0].winfo_children()
                if isinstance(widget, ttk.Radiobutton)
            ]
            self.assertEqual(len(radios), 2)
            self.assertEqual(
                sorted([radios[0].cget("value"), radios[1].cget("value")]),
                ["dark", "light"],
            )
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
