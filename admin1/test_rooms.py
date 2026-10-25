"""Isolated regression tests for user-managed rooms.

Run from the admin1 directory with: python -B -m unittest test_rooms -v
"""

import sqlite3
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

from scheduling_system.database import Database
from scheduling_system.ui import SchedulingApp


class RoomDatabaseTests(unittest.TestCase):
    def test_rooms_start_empty_and_persist_without_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rooms.db"
            db = Database(path)
            try:
                self.assertEqual(db.load_room_locations(), [])
                db.add_room("NORTH-WING", "Ground", "N-001")
                db.add_room("NORTH-WING", "Ground", "N-002")
                db.add_room("IK", "7", "IK-701")
                self.assertEqual(
                    db.load_room_locations(),
                    [("IK", "7"), ("NORTH-WING", "Ground")],
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    db.add_room("NORTH-WING", "Ground", "N-001")
            finally:
                db.close()
            db = Database(path)
            try:
                self.assertEqual(db.load_rooms("NORTH-WING", "Ground"), ["N-001", "N-002"])
                self.assertEqual(db.load_rooms("IK", "7"), ["IK-701"])
                self.assertEqual(db.load_rooms("IL", "2"), [])
            finally:
                db.close()


class RoomUITests(unittest.TestCase):
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

    def room_widgets(self) -> tuple[ttk.Combobox, tk.Listbox]:
        column = self.app.board.winfo_children()[4]
        combo = next(child for child in column.winfo_children()[0].winfo_children()
                     if isinstance(child, ttk.Combobox))
        listing = next(child for child in column.winfo_children()[2].winfo_children()
                       if isinstance(child, tk.Listbox))
        return combo, listing

    def test_window_starts_maximized(self) -> None:
        try:
            self.assertEqual(self.app.root.state(), "zoomed")
        except tk.TclError:
            self.skipTest("zoomed window state not supported on this platform")

    def test_empty_board_has_no_hardcoded_locations(self) -> None:
        combo, listing = self.room_widgets()
        self.assertEqual(tuple(combo["values"]), ())
        self.assertEqual(listing.get(0, "end"), ())
        self.assertEqual(self.app.selected_floor.get(), "")
        self.assertEqual(self.app.selected_room.get(), "")

    def test_board_uses_saved_locations_and_clears_stale_room(self) -> None:
        self.db.add_room("IL", "1", "IL-101")
        self.db.add_room("IK", "7", "IK-701")
        self.db.add_room("NORTH-WING", "Ground", "N-001")
        self.app.selected_floor.set("NORTH-WING / Ground")
        self.app.selected_room.set("N-001")
        self.app._refresh_board()
        combo, listing = self.room_widgets()
        self.assertEqual(tuple(combo["values"]), ("IK / 7", "IL / 1", "NORTH-WING / Ground"))
        self.assertEqual(listing.get(0, "end"), ("N-001",))
        self.assertEqual(listing.curselection(), (0,))
        self.app.selected_floor.set("IK / 7")
        self.app._refresh_board()
        self.assertEqual(self.app.selected_room.get(), "")
        self.assertEqual(self.room_widgets()[1].get(0, "end"), ("IK-701",))

    def test_add_room_dialog_allows_custom_building_and_floor(self) -> None:
        self.app.open_room_dialog()
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        try:
            frame = dialog.winfo_children()[0]
            combos = [child for child in frame.winfo_children() if isinstance(child, ttk.Combobox)]
            self.assertEqual(len(combos), 2)
            for combo in combos:
                self.assertEqual(str(combo["state"]), "normal")
                self.assertEqual(tuple(combo["values"]), ())
        finally:
            dialog.destroy()

    def test_save_room_normalizes_and_selects_new_location(self) -> None:
        self.app.show_notice = Mock()
        dialog = Mock()
        self.app._save_room(
            tk.StringVar(self.root, value=" north-wing "),
            tk.StringVar(self.root, value=" Ground "),
            Mock(get=Mock(return_value=" n-001 ")),
            dialog,
        )
        self.assertEqual(self.db.load_rooms("NORTH-WING", "Ground"), ["N-001"])
        self.assertEqual(self.app.selected_floor.get(), "NORTH-WING / Ground")
        self.assertEqual(self.app.selected_room.get(), "N-001")
        self.assertEqual(self.room_widgets()[1].get(0, "end"), ("N-001",))
        dialog.destroy.assert_called_once()

    def test_invalid_and_duplicate_rooms_do_not_change_saved_rooms(self) -> None:
        self.app.show_notice = Mock()
        dialog = Mock()
        building = tk.StringVar(self.root, value="")
        floor = tk.StringVar(self.root, value="1")
        entry = Mock(get=Mock(return_value="R-101"))
        self.app._save_room(building, floor, entry, dialog)
        self.assertEqual(self.db.load_room_locations(), [])
        dialog.destroy.assert_not_called()
        building.set("IL")
        self.db.add_room("IL", "1", "R-101")
        self.app._save_room(building, floor, entry, dialog)
        self.assertEqual(self.db.load_rooms("IL", "1"), ["R-101"])
        dialog.destroy.assert_not_called()
        self.app.show_notice.assert_called_with("That room already exists on this floor")


if __name__ == "__main__":
    unittest.main()
