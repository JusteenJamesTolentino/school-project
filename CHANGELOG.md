# Update log

## 2026-10-28 (Performance Optimization & Database Architecture Overhaul)

### Issues & Performance Findings

| Severity | Category | Description | Status |
|---|---|---|---|
| HIGH | Performance | Full-table schedule scanning in `conflicting_schedules()` loaded all schedules and performed O(N) comparisons and full object allocations for every conflict check. | Fixed (Targeted candidate query filtering) |
| HIGH | Performance | N+1 database queries in `load_departments()` and `load_professors()` executed sequential nested SELECT queries inside loops for every department and professor. | Fixed (Single JOIN queries with Python group-by) |
| MEDIUM | Performance | Missing SQLite indexes on hot lookup columns caused repeated full-table scans during conflict checks, program lookups, and cascades. | Fixed (Added 7 composite & foreign key indexes) |
| MEDIUM | Startup / Latency | Row-by-row Python iteration during startup curriculum subject split migration caused unnecessary table lock time and slow initial startup. | Fixed (Single bulk `UPDATE` with `CASE/WHERE` pattern) |
| LOW | Memory / Allocation | Repeated dictionary string lookups and dataclass instance overhead during large schedule loads created memory churn. | Fixed (`__slots__` enabled and positional tuple unpacking) |

### Key Improvements

- **Candidate-Filtered Conflict Detection**: `conflicting_schedules()` replaces full-table loads with indexed SQL candidate queries filtered by day, overlapping time window, and professor/section/room criteria. Wildcard matching is then evaluated only against candidate matches.
- **Single-Query Relational JOINs**: Replaced loop queries in `load_departments()` and `load_professors()` with single relational JOINs, populating nested structures efficiently in memory.
- **Hot Lookup SQLite Indexes**: Added 7 dedicated indexes to the schema:
  - `schedules(day, start_minutes, end_minutes)`
  - `schedules(professor, department, day)`
  - `schedules(program, department, year, semester)`
  - `professor_programs(professor_id)`
  - `curricula(program_id, year, semester)`
  - `programs(department_id)`
  - `rooms(building, floor)`
- **Bulk Migration SQL**: Replaced row-by-row Python migration loops with a single SQL `UPDATE` statement using `CASE` and string parsing (`instr`/`substr`).
- **Memory & Object Churn Optimization**: Added `slots=True` to domain models (`Schedule`, `Department`, `Professor`) and positional tuple unpacking in `load_schedules()`, with optional `as_dict=True` parameter.
- **Performance Benchmarking Guardrail**: Added `benchmark_performance.py` profiling suite to benchmark and verify sub-millisecond conflict checks and load latencies across datasets of 100, 500, 1,000, and 5,000 entries.

### Verified for distribution

- Admin 1: 49 tests passed successfully (including new performance regression tests).
- Admin 2: 53 tests passed successfully.
- Benchmark: 5,000 schedule conflict check executes in < 1 ms; 5,000 schedules load in < 30 ms.
- Compiled standalone Windows executables for both **Admin 1** and **Admin 2** placed in `release/optimized-update/`.

## 2026-10-28 (Comprehensive Codebase Audit & Bug Tabulation)

### Findings

| Severity | Category | Description | Status |
|---|---|---|---|
| CRITICAL | Data Integrity | Room conflict detection false negatives with missing building/floor data. | Fixed (Wildcard matching implemented) |
| CRITICAL | Data Integrity | Orphaned schedule records on program/department deletions. | Fixed (Cascading foreign keys & explicit deletion cascades) |
| HIGH | Access Control | Professor updates/deletions matching names globally across departments. | Fixed (Department scoping enforced) |
| HIGH | Input Validation | Schedule edits bypassing creation validation rules. | Fixed (Unified schedule validation) |
| HIGH | UI / State | Stale room building/floor metadata retention in Admin 2. | Fixed (Form reset clearing logic) |
| MEDIUM | Error Handling | Uncaught KeyError on malformed Excel worksheet relationships. | Fixed (`try/except KeyError` handling) |
| MEDIUM | Feature Completeness | Missing Sunday support in day selector boards. | Fixed (`"Sunday"` added to `DAY_ORDER`) |
| LOW | Code Quality | Redundant program schedule mutation queries. | Fixed (Duplicate queries removed) |

### Verified for distribution

- Admin 1: 42 tests passed successfully.
- Admin 2: 53 tests passed successfully.
- All Python sources compiled successfully.

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

## 2025-10-25

### Fixed

- Invalid or corrupt Excel workbooks now produce readable import errors.
