"""Shared imports from Admin 1's scheduling_system package."""

from scheduling_system.database import Database
from scheduling_system.models import Department, Professor, Schedule
from scheduling_system.ui import SchedulingApp

THEMES = SchedulingApp.THEMES

__all__ = ["Database", "Department", "Professor", "Schedule", "SchedulingApp", "THEMES"]
