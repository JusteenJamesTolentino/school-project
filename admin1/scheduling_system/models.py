"""Shared domain models."""

from dataclasses import dataclass, field


@dataclass
class Department:
    code: str
    name: str
    programs: list[str] = field(default_factory=list)


@dataclass
class Professor:
    name: str
    department: str
    programs: list[tuple[str, str]]
    id: int | None = None
