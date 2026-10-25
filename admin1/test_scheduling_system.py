"""Regression tests for the scheduling system.

Run from the admin1 directory:

    python test_scheduling_system.py
"""

import tempfile
import tkinter as tk
from pathlib import Path

from scheduling_system.database import Database
from scheduling_system.models import Department, Professor


def test_database_fixes() -> None:
    db = Database(Path(tempfile.mkdtemp()) / "test.db")
    db.add_department(Department("COE", "College of Engineering"))
    db.add_department(Department("CCS", "College of Computer Studies"))
    db.add_program("COE", "BS Info")
    db.add_program("CCS", "BS Info")  # same program name in two departments

    # Professors with identical names in the same department stay distinct.
    first = Professor("John Smith", "COE", [("CCS", "BS Info")])
    second = Professor("John Smith", "COE", [("COE", "BS Info")])
    db.add_professor(first)
    db.add_professor(second)
    assert first.id is not None and first.id != second.id
    db.update_professor(second.id, Professor("John Smith II", "COE", [("COE", "BS Info")]))
    professors = db.load_professors()
    assert [p.name for p in professors] == ["John Smith", "John Smith II"]
    # The link resolved to the CCS program exactly, not the first name match.
    assert professors[0].programs == [("CCS", "BS Info")]
    db.delete_professor(first.id)
    assert [p.name for p in db.load_professors()] == ["John Smith II"]

    # A failed curriculum import must not lose the existing curriculum.
    db.replace_curriculum(
        "BS Info", "COE", {"1st Year": {"1st Sem": ["A - Alpha"], "2nd Sem": []}}
    )
    try:
        db.replace_curriculum(
            "BS Info", "COE",
            {"1st Year": {"1st Sem": ["B - Beta", "B - Beta"], "2nd Sem": []}},
        )
        raise AssertionError("duplicate subject should have been rejected")
    except ValueError as error:
        assert "B - Beta" in str(error)
    db.add_room("IL", "2", "IL-201")  # commits — must not flush a stale delete
    curriculum = db.load_curriculum("BS Info", "COE")
    assert curriculum["1st Year"]["1st Sem"] == ["A - Alpha"]
    db.close()
    print("database fixes OK")


def test_ui_logic() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        from scheduling_system.ui import SchedulingApp

        app = SchedulingApp(root)

        assert app._format_time(0) == "12:00 AM"
        assert app._format_time(12 * 60) == "12:00 PM"
        app.selected_period.set("AM")
        morning = app._visible_time_slots()
        app.selected_period.set("PM")
        afternoon = app._visible_time_slots()
        assert len(morning) == 10 and len(afternoon) == 18
        assert not set(morning) & set(afternoon)
        assert morning[-1] == "11:30 AM - 12:00 PM"
        assert afternoon[0] == "12:00 PM - 12:30 PM"

        app.selected_department.set("CCS")
        app.selected_program.set("BS Computer Science")
        visible = app._visible_professors()
        assert all(("CCS", "BS Computer Science") in p.programs for p in visible)
        assert any(p.name == "Ronald Sambillon Tinio" for p in visible)
    finally:
        root.destroy()
    print("ui logic OK")


if __name__ == "__main__":
    test_database_fixes()
    try:
        test_ui_logic()
    except tk.TclError:
        print("ui logic SKIPPED (no display available)")
