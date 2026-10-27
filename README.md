JUSTEEN JAMES TOLENITINO as developer.

# School Class Scheduling & Academic Management System

A comprehensive, desktop-based academic scheduling and resource management suite developed in Python and Tkinter. The system is designed to provide educational institutions with an end-to-end workflow for managing departments, degree programs, faculty assignments, classrooms, curricula, and automated timetable conflict detection.

---

## Architecture Overview

The system is partitioned into two specialized applications sharing a common SQLite persistence and domain model layer:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Shared Persistence Layer                        │
│                (SQLite: scheduling.db, authentication.py)              │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │                                │
    ┌───────────────┴───────────────┐┌───────────────┴───────────────┐
    │       Admin 1 Workspace       ││       Admin 2 Timetabler      │
    │  - Departments & Programs     ││  - Class Scheduling           │
    │  - Faculty Roster & Programs  ││  - Multi-Criteria Conflicts   │
    │  - Rooms (Building & Floor)   ││  - Excel Timetable Import     │
    │  - Curriculum (.xlsx) Import  ││  - HTML Schedule Export/Print │
    └───────────────────────────────┘└───────────────────────────────┘
```

1. **Admin 1 (`admin1/scheduling.py`)**: 
   - Manages institutional reference data: Academic Departments, Programs, Faculty members with multi-program assignments, Classrooms (with building and floor specifications), and Curriculum matrices.
   - Supports bulk curriculum ingestion via Excel (`.xlsx`) spreadsheets.
   - Provides administrative controls including real-time curriculum editor, program renames, and dark/light themes.

2. **Admin 2 (`admin2/scheduling.py`)**:
   - The operational scheduling console. Allows schedulers to place classes by Department, Program, Year level, Semester, Professor, Day of week, Time range, Subject, and Room.
   - Features real-time visual conflict detection alerting for professor double-booking, student section overlaps, and classroom clashes.
   - Supports batch schedule import from Excel (`.xlsx`) and print-ready HTML timetable exports.

---

## Authentication & Default Credentials

Access to both administrative consoles is secured via user authentication:

| Application | Username | Default Password | Role |
| :--- | :--- | :--- | :--- |
| **Admin 1** | `admin1` | `group4` | Curriculum & Academic Structure Administrator |
| **Admin 2** | `admin2` | `group4` | Class Timetable & Scheduling Administrator |

---

## Key Features & Conflict Detection Engine

- **Tri-Factor Conflict Detection**:
  - **Professor Overlap**: Prevents assigning an instructor to more than one class at overlapping time intervals on the same day.
  - **Student Section Overlap**: Ensures that students within the same Department, Program, Year level, and Semester cannot be scheduled for two concurrent subjects.
  - **Classroom / Location Clashes**: Detects room double-booking across all programs and professors. Handles building and floor metadata with wildcard matching (e.g. if an imported schedule specifies a room without building details, it safely matches against specific room entries).
- **Curriculum Matrix Management**: Add, update, and manage subjects per academic year and semester.
- **Cascading Data Integrity**: Renaming or deleting programs and professors cascades updates and cleans up dangling entries in the scheduling ledger.
- **Flexible Excel Ingestion**:
  - Admin 1 Curriculum import parsing 1st to 4th-year semester layouts.
  - Admin 2 Schedule import parsing `PROGRAM`, `PROFESSOR`, `DAY`, `TIME`, `SUBJECT`, `SUBJECT TYPE` (supporting standard `LEC`, `LECTURE`, `LAB`, and `LABORATORY`), `ROOM`, and `YEAR`.
- **Export & Print**: One-click generation of styled, printer-optimized HTML schedule matrices that open directly in your web browser.
- **Standalone Mobility**: When run as packaged Windows executables, applications automatically initialize their writable database in `%LOCALAPPDATA%`, pre-seeded with sample data.

---

## System Requirements

- **Operating System**: Windows 10 / 11 (64-bit)
- **Python**: Version 3.11 or higher (if running from source)
- **Dependencies**: Standard Python library (`tkinter`, `sqlite3`, `zipfile`, `xml.etree.ElementTree`, `dataclasses`, `pathlib`). No external pip dependencies are strictly required to run the core applications.
- **PyInstaller**: Required only if compiling binaries from source.

---

## Running from Source

Clone or navigate to the project directory:

```powershell
cd c:\Users\Justeen\code\school
```

### Launch Admin 1 (Curriculum & Setup):
```powershell
python admin1\scheduling.py
```

### Launch Admin 2 (Scheduling Console):
```powershell
python admin2\scheduling.py
```

---

## Running the Automated Test Suite

The system includes comprehensive automated regression suites covering conflict detection, database integrity, schema migrations, Excel workbook parsing, and UI operations.

Run all tests from the repository root:

```powershell
# Run Admin 1 regression tests (42 tests)
python -m unittest discover admin1

# Run Admin 2 regression tests (53 tests)
python -m unittest discover admin2
```

---

## Building Windows Executables (.exe)

Pre-built binaries are available in `/release/antigravity-version/`. If you wish to recompile the executables using PyInstaller:

### Build Admin 1:
```powershell
pyinstaller --noconfirm --onedir --windowed `
  --name "Admin1" `
  --add-data "admin1\scheduling.db;scheduling_system" `
  admin1\scheduling.py
```

### Build Admin 2:
```powershell
pyinstaller --noconfirm --onedir --windowed `
  --name "Admin2" `
  --paths "admin1" `
  --add-data "admin1\scheduling_system;scheduling_system" `
  --add-data "admin2\admin2_app\scheduling.db;admin2_app" `
  admin2\scheduling.py
```

Executables will be generated in the `dist/` directory and can be deployed directly.

---

## Release Distribution

Pre-compiled production binaries for Windows are located in:
```
release/antigravity-version/
├── Admin1/
│   └── Admin1.exe
└── Admin2/
    └── Admin2.exe
```

Both executables operate as self-contained Windows desktop applications.

## Change Log

For the complete history of bug fixes, code-audit findings, data-integrity
changes, test results, and distribution builds, see the
[CHANGELOG.md](CHANGELOG.md).
