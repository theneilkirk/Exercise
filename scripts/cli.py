import argparse
import sys
from pathlib import Path
import os
import shutil
from datetime import datetime

from db import init_db
from db import get_connection
from garmin.ingest_fit import ingest_all_fits
from compute.load_model import rebuild_load_model


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "training.db"
INBOX_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_inbox"
ARCHIVE_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_archive"
WORK_DIR = BASE_DIR / "data" / "work"


def ensure_project_dirs():
    (BASE_DIR / "db").mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def command_init_db():
    log("Initialising database...")
    ensure_project_dirs()
    init_db(DB_PATH)
    log("Database ready.")


def command_fit_ingest():
    log("Starting FIT ingestion...")
    result = ingest_all_fits(DB_PATH)
    log(f"Processed {result['processed']} new FIT files.")
    log(f"Skipped {result['skipped']} already-ingested FIT files.")
    log("FIT ingestion complete.")


def command_rebuild():
    log("Rebuilding derived metrics...")
    conn = get_connection(DB_PATH)
    try:
        rebuild_load_model(conn)
    finally:
        conn.close()
    log("Derived metrics rebuilt.")


def command_all():
    command_init_db()
    command_fit_ingest()
    command_rebuild()
    log("All tasks complete.")
    
def set_initial_hr_profile(conn):
    cur = conn.cursor()

    effective_date = "2025-10-01"

    entries = [
        ("resting_hr_bpm", 58),
        ("max_hr_bpm", 186),
        ("lthr_bpm", 168),
    ]

    for metric, value in entries:
        cur.execute("""
        INSERT OR REPLACE INTO physiology_history
        (effective_from_date, metric, value, source, notes)
        VALUES (?, ?, ?, ?, ?)
        """, (effective_date, metric, value, "manual", "Initial zone setup"))

    conn.commit()
    print("HR profile stored.")

def set_initial_hr_zones(conn):
    cur = conn.cursor()

    effective_date = "2025-10-01"
    sport = "running"
    zones = [
        ("Z1", 0.67, 0.84),
        ("Z2", 0.84, 0.91),
        ("Z3", 0.91, 0.98),
        ("Z4", 0.98, 1.02),
        ("Z5", 1.02, 1.10),
    ]

    for zone, lo, hi in zones:
        cur.execute("""
        INSERT OR REPLACE INTO zones_hr_history
        (effective_from_date, sport, zone, lower_pct, upper_pct)
        VALUES (?, ?, ?, ?, ?)
        """, (effective_date, sport, zone, lo, hi))

    conn.commit()
    print("HR zones stored.")


def upsert_physiology_metric(conn, effective_date: str, metric: str, value: float, notes: str = "Manual update"):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO physiology_history
        (effective_from_date, metric, value, source, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (effective_date, metric, value, "manual", notes),
    )
    conn.commit()


def upsert_hr_zones(conn, effective_date: str, sport: str, zones):
    """
    Insert or replace HR zones for a single (effective_from_date, sport) set.
    `zones` is an iterable of (zone_label, lower_pct, upper_pct).
    """
    cur = conn.cursor()
    for zone, lo, hi in zones:
        cur.execute(
            """
            INSERT OR REPLACE INTO zones_hr_history
            (effective_from_date, sport, zone, lower_pct, upper_pct)
            VALUES (?, ?, ?, ?, ?)
            """,
            (effective_date, sport, zone, lo, hi),
        )
    conn.commit()


def command_add_hr_zones():
    """
    Interactively add/update HR zones for a given sport and effective date.
    """
    conn = get_connection(DB_PATH)
    try:
        print("Add/update HR zones (LTHR-relative)")
        today_str = datetime.now().strftime("%Y-%m-%d")

        sport = input("Sport [running]: ").strip() or "running"
        effective_date = (
            input(f"Effective from date YYYY-MM-DD [{today_str}]: ").strip()
            or today_str
        )

        print(
            "You will enter zone LOWER bounds as fractions of LTHR.\n"
            "Upper bounds will be derived so that zones are continuous with no gaps."
        )

        # Default lower bounds from the initial seed
        zone_names = ["Z1", "Z2", "Z3", "Z4", "Z5"]
        default_lowers = [0.67, 0.84, 0.91, 0.98, 1.02]

        lowers = []

        def prompt_lower(label: str, default_value: float, min_allowed: float):
            while True:
                raw = input(
                    f"{label} lower bound [{default_value:.2f}]: "
                ).strip()
                if not raw:
                    value = default_value
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        print("  Invalid number. Enter a single value like 0.84.")
                        continue

                if not (0.0 < value < 3.0):
                    print("  Value must satisfy 0.0 < value < 3.0. Try again.")
                    continue
                if value <= min_allowed:
                    print(
                        f"  Value must be greater than {min_allowed:.3f} "
                        "to keep zones strictly increasing."
                    )
                    continue
                return value

        # Z1 lower: anchored at default, but user may override
        z1_lower = prompt_lower("Z1", default_lowers[0], 0.0)
        lowers.append(z1_lower)

        # Subsequent zone lowers must be strictly increasing
        last = z1_lower
        for name, default in zip(zone_names[1:], default_lowers[1:]):
            value = prompt_lower(name, default, last)
            lowers.append(value)
            last = value

        # Final cap for Z5 upper
        default_cap = 1.5
        while True:
            raw = input(
                f"Z5 upper cap (last zone upper) [{default_cap:.2f}]: "
            ).strip()
            if not raw:
                cap = default_cap
            else:
                try:
                    cap = float(raw)
                except ValueError:
                    print("  Invalid number. Enter a single value like 1.50.")
                    continue

            if not (last < cap <= 3.0):
                print(
                    f"  Cap must satisfy last_lower < cap <= 3.0 "
                    f"(last_lower is {last:.3f}). Try again."
                )
                continue
            break

        # Build contiguous zones: [L1, L2), [L2, L3), ..., [L5, cap]
        zones = []
        for i, name in enumerate(zone_names):
            lo = lowers[i]
            if i < len(zone_names) - 1:
                hi = lowers[i + 1]
            else:
                hi = cap
            zones.append((name, lo, hi))

        upsert_hr_zones(conn, effective_date, sport, zones)

        print()
        print(f"Stored HR zones for sport='{sport}', effective_from_date={effective_date}:")
        for zone, lo, hi in zones:
            print(f"  {zone}: {lo:.3f}–{hi:.3f}")
    finally:
        conn.close()


def command_update_physiology():
    """
    Interactively add a new row in physiology_history for one or more metrics.
    """
    METRICS = {
        "resting_hr_bpm": ("Resting HR (bpm)",              30.0, 100.0),
        "max_hr_bpm":     ("Max HR (bpm)",                  100.0, 250.0),
        "lthr_bpm":       ("Lactate Threshold HR (bpm)",    50.0,  250.0),
    }

    conn = get_connection(DB_PATH)
    try:
        print("Update physiology metrics")
        today_str = datetime.now().strftime("%Y-%m-%d")
        effective_date = (
            input(f"Effective from date YYYY-MM-DD [{today_str}]: ").strip()
            or today_str
        )
        try:
            datetime.strptime(effective_date, "%Y-%m-%d")
        except ValueError:
            print("Invalid date format. Use YYYY-MM-DD.")
            return

        cur = conn.cursor()
        print(f"\nCurrent values on or before {effective_date}:")
        for key, (label, lo, hi) in METRICS.items():
            cur.execute(
                """
                SELECT value, effective_from_date
                FROM physiology_history
                WHERE metric = ? AND effective_from_date <= ?
                ORDER BY effective_from_date DESC
                LIMIT 1
                """,
                (key, effective_date),
            )
            row = cur.fetchone()
            if row:
                print(f"  {label}: {row[0]} (from {row[1]})")
            else:
                print(f"  {label}: (no value recorded)")

        print("\nEnter new values (leave blank to skip):")
        updated = []
        for key, (label, lo, hi) in METRICS.items():
            while True:
                raw = input(f"  {label}: ").strip()
                if not raw:
                    break
                try:
                    value = float(raw)
                except ValueError:
                    print("    Invalid number.")
                    continue
                if not (lo <= value <= hi):
                    print(f"    Value must be between {lo} and {hi}.")
                    continue
                upsert_physiology_metric(conn, effective_date, key, value)
                updated.append((label, value))
                break

        print()
        if updated:
            print(f"Stored {len(updated)} metric(s) with effective_from_date={effective_date}:")
            for label, value in updated:
                print(f"  {label}: {value}")
        else:
            print("No changes made.")
    finally:
        conn.close()


def nuclear_rebuild():
    print("⚠ Nuclear rebuild initiated...")

    ensure_project_dirs()

    # 1️⃣ Wipe DB
    if DB_PATH.exists():
        print("Wiping database...")
        DB_PATH.unlink()

    print("Creating blank database file and schema...")
    init_db(DB_PATH)

    # 2️⃣ Move FIT files back to inbox
    print("Restoring archived FIT files to inbox...")
    moved = 0

    for file in ARCHIVE_DIR.glob("*"):
        if file.suffix.lower() in [".fit", ".zip"]:
            destination = INBOX_DIR / file.name

            if destination.exists():
                print(f"Skipping (already exists): {file.name}")
                continue

            shutil.move(str(file), str(destination))
            moved += 1

    print(f"Restored {moved} files.")

    print("✅ Nuclear reset complete.")
    print()
    print("Next steps:")
    print("  1) Seed HR profile + zones:")
    print("       python .\\scripts\\cli.py seed-hr-zones")
    print("  2) Ingest FIT files:")
    print("       python .\\scripts\\cli.py fit-ingest")
    print("  3) (Optional) Rebuild derived metrics:")
    print("       python .\\scripts\\cli.py rebuild-derived")


def full_rebuild():
    """
    Convenience wrapper that performs a full end-to-end rebuild:
      - nuclear_rebuild (DB reset + restore FITs to inbox)
      - seed HR profile + zones
      - ingest FIT files
      - rebuild derived metrics
    """
    print("⚙ Starting full rebuild...")

    nuclear_rebuild()

    print("Seeding HR profile + zones...")
    conn = get_connection(DB_PATH)
    try:
        set_initial_hr_profile(conn)
        set_initial_hr_zones(conn)
    finally:
        conn.close()

    print("Ingesting FIT files...")
    ingest_all_fits(DB_PATH)

    print("Rebuilding derived metrics...")
    conn = get_connection(DB_PATH)
    try:
        rebuild_load_model(conn)
    finally:
        conn.close()

    print("✅ Full rebuild complete.")



def main():
    parser = argparse.ArgumentParser(description="Training Engine CLI")
    parser.add_argument(
        "command",
        choices=[
            "init-db",
            "fit-ingest",
            "rebuild-derived",
            "add-hr-zones",
            "update-physiology",
            "seed-hr-zones",
            "all",
            "nuke",
            "full-rebuild",
        ],
        help="Command to run",
    )

    args = parser.parse_args()

    if args.command == "init-db":
        command_init_db()
    elif args.command == "fit-ingest":
        command_fit_ingest()
    elif args.command == "rebuild-derived":
        command_rebuild()
    elif args.command == "seed-hr-zones":
        conn = get_connection(DB_PATH)
        set_initial_hr_profile(conn)
        set_initial_hr_zones(conn)
        conn.close()
    elif args.command == "add-hr-zones":
        command_add_hr_zones()
    elif args.command == "update-physiology":
        command_update_physiology()
    elif args.command == "nuke":
        nuclear_rebuild()
    elif args.command == "full-rebuild":
        full_rebuild()
    elif args.command == "all":
        command_all()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()