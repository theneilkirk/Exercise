import argparse
import sys
from pathlib import Path
import os
import shutil
from datetime import datetime

from db import init_db
from garmin.ingest_fit import ingest_all_fits
from compute.load_model import rebuild_load_model


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "training.db"
INBOX_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_inbox"
ARCHIVE_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_archive"


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def command_init_db():
    log("Initialising database...")
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
    rebuild_daily_metrics(DB_PATH)
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


def nuclear_rebuild():
    print("⚠ Nuclear rebuild initiated...")

    # 1️⃣ Wipe DB
    if DB_PATH.exists():
        print("Wiping database...")
        DB_PATH.unlink()

    print("Creating blank database file...")
    DB_PATH.touch()

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

    # 3️⃣ Rebuild everything
    print("Rebuilding schema...")
    init_db(DB_PATH)

    print("Ingesting FIT files...")
    ingest_all_fits(DB_PATH)

    print("Rebuilding derived metrics...")
    rebuild_load_model(DB_PATH)

    print("✅ Nuclear rebuild complete.")



def main():
    parser = argparse.ArgumentParser(description="Training Engine CLI")
    parser.add_argument(
        "command",
        choices=["init-db", "fit-ingest", "rebuild-derived", "set_initial_hr_zones", "all", "nuke"],
        help="Command to run"
    )

    args = parser.parse_args()

    if args.command == "init-db":
        command_init_db()
    elif args.command == "fit-ingest":
        command_fit_ingest()
    elif args.command == "rebuild-derived":
        command_rebuild()
    elif args.command == "set_initial_hr_zones":
        from db import get_connection
        conn = get_connection(DB_PATH)
        set_initial_hr_profile(conn)
        set_initial_hr_zones(conn)
        conn.close()
    elif args.command == "nuke":
        nuclear_rebuild()
    elif args.command == "all":
        command_all()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()