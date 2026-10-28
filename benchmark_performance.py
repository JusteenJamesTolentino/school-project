"""Performance benchmarking utility for scheduling system database operations.

Measures:
- Department load time (JOIN query vs N+1)
- Professor load time (JOIN query vs N+1)
- Schedule load time (positional dataclass vs dictionary)
- Conflict check latency across various candidate scenarios
- Insert latency across dataset scales

Supports sample data sizes: 100, 500, 1,000, 5,000 entries.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

# Ensure admin1 is on sys.path
_ADMIN1 = Path(__file__).resolve().parent / "admin1"
if _ADMIN1.is_dir() and str(_ADMIN1) not in sys.path:
    sys.path.insert(0, str(_ADMIN1))

from scheduling_system.database import Database
from scheduling_system.models import Department, Professor, Schedule


def populate_benchmark_db(db: Database, schedule_count: int) -> tuple[list[Schedule], Schedule, Schedule]:
    """Populates the database with realistic sample departments, professors, and schedules."""
    # Create departments & programs
    dept_codes = ["CCS", "COE", "CBA", "CAS", "CED"]
    for code in dept_codes:
        db.add_department(Department(code, f"College of {code}"))
        for p_idx in range(1, 4):
            db.add_program(code, f"{code}-Prog-{p_idx}")

    # Create professors with program assignments
    profs: list[Professor] = []
    for i in range(1, 51):
        dept = dept_codes[i % len(dept_codes)]
        assigned_prog = (dept, f"{dept}-Prog-{(i % 3) + 1}")
        prof = Professor(f"Prof {i}", dept, [assigned_prog])
        db.add_professor(prof)
        profs.append(prof)

    # Create rooms
    buildings = ["Main", "Annex", "Science", "Tech"]
    floors = ["1st", "2nd", "3rd", "4th"]
    rooms = []
    for b in buildings:
        for f in floors:
            for r in range(1, 6):
                room_name = f"{b[:2].upper()}-{f[0]}{r:02d}"
                db.add_room(b, f, room_name)
                rooms.append((b, f, room_name))

    # Create schedules
    days = list(Database.DAY_ORDER)
    time_slots = [
        (420, 510),  # 7:00 - 8:30
        (510, 600),  # 8:30 - 10:00
        (600, 690),  # 10:00 - 11:30
        (720, 810),  # 12:00 - 1:30
        (810, 900),  # 1:30 - 3:00
        (900, 990),  # 3:00 - 4:30
        (990, 1080), # 4:30 - 6:00
    ]

    with db.connection:
        for i in range(schedule_count):
            dept = dept_codes[i % len(dept_codes)]
            prog = f"{dept}-Prog-{(i % 3) + 1}"
            prof = profs[i % len(profs)].name
            b, f, rm = rooms[i % len(rooms)]
            day = days[i % len(days)]
            start_m, end_m = time_slots[i % len(time_slots)]
            year = f"{(i % 4) + 1}st" if (i % 4) + 1 == 1 else f"{(i % 4) + 1}nd" if (i % 4) + 1 == 2 else f"{(i % 4) + 1}rd" if (i % 4) + 1 == 3 else "4th"
            semester = "1st Sem" if (i % 2 == 0) else "2nd Sem"
            db.connection.execute(
                """
                INSERT INTO schedules
                    (department, program, year, semester, subject, subject_type,
                     professor, room, room_building, room_floor, day, start_minutes, end_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (dept, prog, year, semester, f"SUBJ-{i % 100:03d}", "Lecture",
                 prof, rm, b, f, day, start_m, end_m),
            )

    # Return sample test candidates for conflict checking
    # 1. A candidate guaranteed to conflict with the very first schedule (same prof and time)
    first_row = db.connection.execute("SELECT * FROM schedules LIMIT 1").fetchone()
    conflicting_candidate = Schedule(
        department="OTHER",
        program="OTHER-Prog",
        year="1st",
        semester="1st Sem",
        subject="OTHER-101",
        subject_type="Lecture",
        professor=first_row["professor"],
        day=first_row["day"],
        start_minutes=first_row["start_minutes"],
        end_minutes=first_row["end_minutes"],
        room="",
    )

    # 2. A non-conflicting candidate (unique professor, unique section, empty room, Sunday night)
    non_conflicting_candidate = Schedule(
        department="COE",
        program="COE-Prog-1",
        year="1st",
        semester="1st Sem",
        subject="ADV-999",
        subject_type="Lecture",
        professor="NonExistent Professor",
        day="Sunday",
        start_minutes=1260,  # 9:00 PM
        end_minutes=1320,    # 10:00 PM
        room="",
    )

    return [], conflicting_candidate, non_conflicting_candidate


def run_benchmark(sizes: list[int], repeats: int = 5) -> list[dict[str, object]]:
    results = []
    print(f"Running performance benchmark for dataset sizes: {sizes}")
    print(f"Repetitions per test: {repeats}\n")

    for size in sizes:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / f"bench_{size}.db"
            db = Database(db_path)

            # Benchmark insertion
            t0 = time.perf_counter()
            _, conf_cand, non_conf_cand = populate_benchmark_db(db, size)
            insert_ms = (time.perf_counter() - t0) * 1000

            # 1. Benchmark load_departments
            t0 = time.perf_counter()
            for _ in range(repeats):
                _ = db.load_departments()
            dept_load_ms = ((time.perf_counter() - t0) / repeats) * 1000

            # 2. Benchmark load_professors
            t0 = time.perf_counter()
            for _ in range(repeats):
                _ = db.load_professors()
            prof_load_ms = ((time.perf_counter() - t0) / repeats) * 1000

            # 3. Benchmark load_schedules (objects)
            t0 = time.perf_counter()
            for _ in range(repeats):
                scheds = db.load_schedules()
            sched_obj_ms = ((time.perf_counter() - t0) / repeats) * 1000

            # 4. Benchmark load_schedules (dicts)
            t0 = time.perf_counter()
            for _ in range(repeats):
                scheds_dict = db.load_schedules(as_dict=True)
            sched_dict_ms = ((time.perf_counter() - t0) / repeats) * 1000

            # 5. Benchmark conflict checking: non-conflicting candidate
            t0 = time.perf_counter()
            check_repeats = max(repeats * 10, 50)
            for _ in range(check_repeats):
                c = db.conflicting_schedules(non_conf_cand)
            non_conf_ms = ((time.perf_counter() - t0) / check_repeats) * 1000

            # 6. Benchmark conflict checking: conflicting candidate
            t0 = time.perf_counter()
            for _ in range(check_repeats):
                c = db.conflicting_schedules(conf_cand)
                assert len(c) > 0, "Expected a conflict match"
            conf_ms = ((time.perf_counter() - t0) / check_repeats) * 1000

            db.close()

            row = {
                "size": size,
                "populate_ms": insert_ms,
                "dept_load_ms": dept_load_ms,
                "prof_load_ms": prof_load_ms,
                "sched_obj_ms": sched_obj_ms,
                "sched_dict_ms": sched_dict_ms,
                "conflict_check_ms": conf_ms,
                "non_conflict_check_ms": non_conf_ms,
            }
            results.append(row)
            print(
                f"Size: {size:>5} entries | Sched Load: {sched_obj_ms:>6.2f} ms | "
                f"Conflict Check: {conf_ms:>6.3f} ms | Prof Load: {prof_load_ms:>5.2f} ms"
            )

    return results


def print_results_table(results: list[dict[str, object]]) -> None:
    print("\n" + "=" * 90)
    print(" " * 28 + "BENCHMARK PERFORMANCE SUMMARY")
    print("=" * 90)
    header = (
        f"{'Size':>6} | {'Populate (ms)':>13} | {'Depts (ms)':>10} | {'Profs (ms)':>10} | "
        f"{'Scheds (ms)':>11} | {'Conflict (ms)':>13} | {'No-Conflict (ms)':>16}"
    )
    print(header)
    print("-" * 90)
    for r in results:
        print(
            f"{r['size']:>6} | "
            f"{r['populate_ms']:>13.1f} | "
            f"{r['dept_load_ms']:>10.3f} | "
            f"{r['prof_load_ms']:>10.3f} | "
            f"{r['sched_obj_ms']:>11.3f} | "
            f"{r['conflict_check_ms']:>13.3f} | "
            f"{r['non_conflict_check_ms']:>16.3f}"
        )
    print("=" * 90)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheduling Database Performance Benchmark")
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[100, 500, 1000, 5000],
        help="Sample dataset sizes (default: 100 500 1000 5000)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Number of repetitions for averaging (default: 5)",
    )
    args = parser.parse_args()
    res = run_benchmark(args.sizes, repeats=args.repeats)
    print_results_table(res)
