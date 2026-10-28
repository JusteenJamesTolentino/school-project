"""Shared imports from Admin 1's scheduling_system package."""

from scheduling_system.database import Database
from scheduling_system.models import Department, Professor, Schedule

# Theme palettes are defined inline here so we don't import the entire
# Admin 1 UI module (which triggers Tkinter style registration) just to
# read a class-level constant.
THEMES = {
    "light": {
        "background": "#f1f5f9",
        "panel": "#ffffff",
        "border": "#dbe3ee",
        "muted": "#64748b",
        "primary": "#2563eb",
        "primary_hover": "#1e40af",
        "primary_dark": "#1e40af",
        "header": "#eff6ff",
        "ink": "#0f172a",
        "danger": "#dc2626",
        "surface": "#f8fafc",
        "select_bg": "#dbeafe",
        "select_fg": "#1d4ed8",
        "highlight": "#93c5fd",
        "notice_bg": "#dbeafe",
        "notice_fg": "#1e3a8a",
        "accent": "#e0ebff",
        "button": "#ffffff",
        "dropdown": "#ffffff",
    },
    "dark": {
        "background": "#1f1e1d",
        "panel": "#171616",
        "border": "#383130",
        "muted": "#a8a29e",
        "primary": "#3b82f6",
        "primary_hover": "#1d4ed8",
        "primary_dark": "#d6d3d1",
        "header": "#292626",
        "ink": "#e8e6e3",
        "danger": "#f87171",
        "surface": "#292626",
        "select_bg": "#3f3835",
        "select_fg": "#f5f3f0",
        "highlight": "#57504b",
        "notice_bg": "#292626",
        "notice_fg": "#e8e6e3",
        "accent": "#292626",
        "button": "#171616",
        "dropdown": "#292626",
    },
}

__all__ = ["Database", "Department", "Professor", "Schedule", "THEMES"]
