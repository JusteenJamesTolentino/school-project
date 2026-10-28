"""Shared domain models."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Department:
    code: str
    name: str
    programs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Professor:
    name: str
    department: str
    programs: list[tuple[str, str]]
    id: int | None = None


def format_minutes(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    suffix = "PM" if hour >= 12 else "AM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute:02d} {suffix}"


@dataclass(slots=True)
class Schedule:
    """One class assignment: program, subject, professor, day, and time range."""

    department: str
    program: str
    subject: str
    subject_type: str
    professor: str
    day: str
    start_minutes: int
    end_minutes: int
    year: str = ""
    semester: str = ""
    room: str = ""
    id: int | None = None
    room_building: str = ""
    room_floor: str = ""

    @property
    def time_display(self) -> str:
        return f"{format_minutes(self.start_minutes)} - {format_minutes(self.end_minutes)}"
