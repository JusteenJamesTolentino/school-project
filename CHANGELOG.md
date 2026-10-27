# Update log

## 2026-10-27 (Code Audit)

### Findings

| Severity | Finding | Status |
|---|---|---|
| HIGH | Professor rename/delete operations matched schedules by professor name globally, so same-named professors in another department could be modified or deleted. | Fixed |
| HIGH | Schedule edits bypassed the validation applied to new schedules, allowing invalid days, types, time ranges, or empty required fields. | Fixed |
| MEDIUM | Program rename/delete each executed the same schedule mutation twice. | Fixed |
| LOW | An incorrect Admin 1 frame annotation and an unnecessary Admin 2 import suppression hid static-analysis warnings. | Fixed |
| LOW | `WindowControls._close()` raises `NotImplementedError` as an intentional abstract contract. | Accepted |

### Fixed

- Scoped professor schedule updates and deletions to the professor's department.
- Reused one schedule validator for both inserts and updates.
- Removed duplicate program schedule mutations.
- Removed unnecessary `# type: ignore` suppressions.

### Verified for distribution

- Admin 1: 42 tests passed, 1 display-dependent test skipped.
- Admin 2: 53 tests passed.
- All Python sources compiled successfully.

## 2026-10-26 (Antigravity Bug Fixes & Improvements)

### Fixed

- **Room Conflict Detection (Critical)**: Fixed false negatives where overlapping schedules in the same room were ignored if one entry lacked building or floor information (e.g. from Excel imports). Empty building and floor attributes now correctly act as wildcards matching any room with the same name.
- **Subject Name Duplication (Critical)**: Fixed issue in `_split_subject` where subject titles without a `" - "` delimiter duplicated when formatted (e.g., converting `"Calculus"` into `"Calculus - Calculus"`). Missing delimiters now cleanly separate code and name.
- **Stale Room Building/Floor Leakage (High)**: Fixed `Admin2App.add_to_schedule` not clearing `room_building` and `room_floor` selections when adding a schedule, preventing stale room metadata from sticking to subsequent entries.
- **Cross-Program Professor Assignment (High)**: In Admin 2, switching programs now resets the selected professor to prevent inadvertently assigning professors who are not registered for the newly selected program.
- **Schedule Importer Abbreviation Support (Medium)**: Added support for standard `"LEC"` type abbreviation alongside `"LECTURE"`, `"LAB"`, and `"LABORATORY"`.
- **Curriculum Workbook Relationship Error Handling (Medium)**: Added `try/except KeyError` handling around worksheet relationship resolution in `admin1/scheduling_system/curriculum.py` to prevent uncaught exceptions on non-standard Excel files.
- **Admin 1 Sunday Support (Medium)**: Added `"Sunday"` to Admin 1's day selector board (`Database.DAY_ORDER`), enabling Sunday schedule management and preventing crashes when Sunday entries are inspected.
- **Export Path URI Handling (Medium)**: Ensured schedule HTML export uses `Path.resolve().as_uri()` to avoid relative path errors in `webbrowser.open()`.
- **Data Integrity Cascades**: Program renames/deletions and professor renames/deletions in Admin 1 now cascade updates and deletions to the `schedules` table, eliminating orphaned schedule references.
- **Helper Database Methods**: Added `delete_department` and `delete_room` to `Database` for complete CRUD management.

### Verified for distribution

- Compiled standalone Windows executables for both **Admin 1** and **Admin 2** placed in `release/antigravity-version/`.

## 2026-10-26

### Fixed

- Added login protection:
  - Admin 1: `admin1` / `group4`
  - Admin 2: `admin2` / `group4`
- Schedule conflicts now distinguish semesters and room locations.
- Rooms retain their building and floor identity in saved schedules.
- Schedule writes now validate day, type, time range, and required fields.
- Admin 2 exports HTML-escape schedule values.
- Admin 2 validates imported program and professor references when Admin 1
  reference data exists, while preserving empty-database imports.
- Sunday is now consistently supported in Admin 2.
- Malformed schedule workbook relationships now produce readable errors.
- Pending Tk notice callbacks are cancelled during application shutdown.
- Admin 1 can now import a curriculum into a newly created, empty database.
  The import dialog collects a department code, department name, and program
  name, then creates that owner before saving the curriculum.
- The empty-database schedule import in Admin 2 remains supported. Workbook
  values are used when Admin 1 reference data has not yet been created.

### Verified for distribution

- Rebuilt the Admin 1 executable with the first-curriculum import flow.
- Built an Admin 2 executable that bundles its own interface and the shared
  Admin 1 database layer.

## 2026-10-25

### Fixed

- Invalid or corrupt Excel workbooks now produce readable import errors.
- Subject edits report when the original subject is no longer present.
- Professor selection and program actions use explicit option dialogs.

### Packaging

- Packaged databases are stored in a writable local application-data folder
  and are copied from the bundled sample database on first launch.
