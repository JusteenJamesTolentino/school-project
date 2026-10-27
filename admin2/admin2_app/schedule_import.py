"""Schedule workbook parsing and format validation.

A valid workbook has a header row containing PROGRAM, PROFESSOR (or PROF),
DAY, TIME, SUBJECT, and SUBJECT TYPE (ROOM and YEAR are optional), with one
schedule row below per entry. Times look like 7:00AM-1:00PM. Anything else is
rejected with ValueError so an invalid file never reaches the database.
"""

from __future__ import annotations

import re
from pathlib import Path
from posixpath import normpath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

_TIME_PATTERN = re.compile(
    r"^\s*(\d{1,2})(?::(\d{2}))?\s*([AP]\.?M\.?)\s*$", re.IGNORECASE
)
_DAY_NAMES = {
    "MONDAY": "Monday", "TUESDAY": "Tuesday", "WEDNESDAY": "Wednesday",
    "THURSDAY": "Thursday", "FRIDAY": "Friday", "SATURDAY": "Saturday",
    "SUNDAY": "Sunday",
}
_TYPE_NAMES = {
    "LEC": "Lecture", "LECTURE": "Lecture", "LAB": "Laboratory", "LABORATORY": "Laboratory",
}


def normalize_header(header: str) -> str:
    return " ".join(header.upper().split())


def parse_time(text: str) -> int:
    """Convert '7:00AM', '1:00 PM', '12am', ... to minutes since midnight."""
    match = _TIME_PATTERN.match(text)
    if not match:
        raise ValueError(f"Cannot read time '{text.strip()}'")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3).replace(".", "").upper()
    if hour < 1 or hour > 12 or minute > 59:
        raise ValueError(f"Cannot read time '{text.strip()}'")
    display_hour = hour % 12
    return display_hour * 60 + minute + (720 if suffix == "PM" else 0)


def parse_time_range(text: str) -> tuple[int, int]:
    """Convert '7:00AM-1:00PM' into (start, end) minutes since midnight."""
    parts = text.split("-")
    if len(parts) != 2:
        raise ValueError(f"Cannot read time range '{text.strip()}'")
    start, end = parse_time(parts[0]), parse_time(parts[1])
    if start >= end:
        raise ValueError(f"Time range '{text.strip()}' ends before it starts")
    return start, end


def canonical_day(text: str) -> str:
    day = _DAY_NAMES.get(text.strip().upper())
    if day is None:
        raise ValueError(f"Unknown day '{text.strip()}'")
    return day


def canonical_type(text: str) -> str:
    subject_type = _TYPE_NAMES.get(text.strip().upper())
    if subject_type is None:
        raise ValueError(f"Unknown subject type '{text.strip()}'")
    return subject_type


def read_schedule_xlsx(path: Path) -> list[dict[str, str]]:
    """Return raw schedule rows: program, professor, day, time, subject, type, room."""
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationships_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    ns = {"m": namespace}
    try:
        workbook = ZipFile(path)
    except BadZipFile as error:
        raise ValueError("The file is not a valid Excel workbook (.xlsx)") from error
    with workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(text.text or "" for text in item.findall(".//m:t", ns))
                for item in root.findall("m:si", ns)
            ]
        relationships = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{{{package_namespace}}}Relationship")
        }
        workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        sheet = workbook_root.find("m:sheets/m:sheet", ns)
        if sheet is None:
            raise ValueError("The workbook has no worksheets")
        relationship_id = sheet.attrib[f"{{{relationships_namespace}}}id"]
        try:
            worksheet_path = relationship_map[relationship_id].lstrip("/")
        except KeyError as error:
            raise ValueError("The workbook has an invalid worksheet relationship") from error
        if not worksheet_path.startswith("xl/"):
            worksheet_path = "xl/" + worksheet_path
        worksheet = ElementTree.fromstring(workbook.read(normpath(worksheet_path)))
        rows: list[dict[str, str]] = []
        for row in worksheet.findall(".//m:sheetData/m:row", ns):
            values: dict[str, str] = {}
            for cell in row.findall("m:c", ns):
                reference = cell.attrib.get("r", "")
                column = "".join(character for character in reference if character.isalpha())
                if cell.attrib.get("t") == "inlineStr":
                    value = "".join(
                        text.text or "" for text in cell.findall("m:is//m:t", ns)
                    )
                else:
                    value_node = cell.find("m:v", ns)
                    value = (value_node.text or "") if value_node is not None else ""
                    if cell.attrib.get("t") == "s" and value:
                        try:
                            value = shared_strings[int(value)]
                        except (IndexError, ValueError) as error:
                            raise ValueError(
                                "The workbook contains an invalid shared string reference"
                            ) from error
                values[column] = value.strip()
            rows.append(values)

    if not rows:
        raise ValueError("The workbook has no data rows")

    header_map = {}
    for column, header in rows[0].items():
        header_map[normalize_header(header)] = column
    aliases = {
        "PROGRAM": "program", "PROFESSOR": "professor", "PROF": "professor",
        "DAY": "day", "TIME": "time", "SUBJECT": "subject",
        "SUBJECT TYPE": "subject_type", "SUBJ TYPE": "subject_type",
        "TYPE": "subject_type", "ROOM": "room", "YEAR": "year",
    }
    columns = {}
    for header, field in aliases.items():
        if header in header_map:
            columns[field] = header_map[header]
    missing = [
        needed for needed in ("program", "professor", "day", "time", "subject", "subject_type")
        if needed not in columns
    ]
    if missing:
        raise ValueError(
            "Unrecognized schedule format: the first row must contain headers "
            "PROGRAM, PROFESSOR, DAY, TIME, SUBJECT, and SUBJECT TYPE"
        )

    schedules = []
    for row in rows[1:]:
        entry = {
            field: row.get(column, "").strip()
            for field, column in columns.items()
        }
        if any(entry.values()):
            schedules.append(entry)
    if not schedules:
        raise ValueError("No schedule rows were found below the header row")
    return schedules
