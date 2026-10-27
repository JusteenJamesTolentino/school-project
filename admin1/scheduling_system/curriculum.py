"""Curriculum workbook parsing and format validation.

A valid workbook has its first worksheet's first row built from headers like
'1ST YEAR 1ST SEM' / '1ST YEAR 2ND SEM', with subject names below each header.
Anything else is rejected with ValueError so callers never replace a stored
curriculum with an invalid import.
"""

from __future__ import annotations

from pathlib import Path
from posixpath import normpath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


def read_xlsx(path: Path) -> dict[str, dict[str, list[str]]]:
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
    curriculum = {
        f"{year} Year": {"1st Sem": [], "2nd Sem": []}
        for year in ("1st", "2nd", "3rd", "4th")
    }
    recognized = 0
    for column, header in rows[0].items():
        normalized = header.upper().replace(" ", "")
        year = next(
            (item for item in ("1ST", "2ND", "3RD", "4TH")
             if normalized.startswith(f"{item}YEAR")),
            None,
        )
        semester = "1st Sem" if "1STSEM" in normalized else "2nd Sem" if "2NDSEM" in normalized else None
        if not year or not semester:
            continue
        recognized += 1
        year_key = {"1ST": "1st Year", "2ND": "2nd Year", "3RD": "3rd Year", "4TH": "4th Year"}[year]
        for row in rows[1:]:
            subject = row.get(column, "").strip()
            if subject:
                curriculum[year_key][semester].append(subject)
    if not recognized:
        raise ValueError(
            "Unrecognized curriculum format: the first row must contain headers "
            "like '1ST YEAR 1ST SEM' and '1ST YEAR 2ND SEM'"
        )
    if not any(
        subjects for semesters in curriculum.values() for subjects in semesters.values()
    ):
        raise ValueError("No curriculum subjects were found below the header row")
    return curriculum
