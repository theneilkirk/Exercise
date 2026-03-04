import argparse
import sys
from pathlib import Path
import shutil
from datetime import datetime

from db import init_db
from db import get_connection
from garmin.ingest_fit import ingest_all_fits
from compute.load_model import rebuild_load_model
from compute.export import build_export


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


def command_sync():
    """Ingest new FIT files from inbox and recalculate derived metrics."""
    ensure_project_dirs()
    init_db(DB_PATH)
    log("Starting FIT ingestion...")
    result = ingest_all_fits(DB_PATH)
    log(f"Processed {result['processed']} new FIT files, skipped {result['skipped']}.")
    log("Recalculating derived metrics...")
    conn = get_connection(DB_PATH)
    try:
        rebuild_load_model(conn)
    finally:
        conn.close()
    log("Done.")


def command_recalculate():
    """Recompute ATL/CTL/form from existing activity data without re-reading FIT files."""
    log("Recalculating derived metrics...")
    conn = get_connection(DB_PATH)
    try:
        rebuild_load_model(conn)
    finally:
        conn.close()
    log("Done.")


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


def command_set_zones():
    """Interactively add or update HR zones for a given sport and effective date."""
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
            "Enter zone LOWER bounds as fractions of LTHR.\n"
            "Upper bounds are derived so zones are contiguous with no gaps."
        )

        zone_names = ["Z1", "Z2", "Z3", "Z4", "Z5"]
        default_lowers = [0.67, 0.84, 0.91, 0.98, 1.02]
        lowers = []

        def prompt_lower(label: str, default_value: float, min_allowed: float):
            while True:
                raw = input(f"{label} lower bound [{default_value:.2f}]: ").strip()
                if not raw:
                    value = default_value
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        print("  Invalid number. Enter a value like 0.84.")
                        continue
                if not (0.0 < value < 3.0):
                    print("  Value must be between 0.0 and 3.0.")
                    continue
                if value <= min_allowed:
                    print(f"  Must be greater than {min_allowed:.3f} to keep zones strictly increasing.")
                    continue
                return value

        z1_lower = prompt_lower("Z1", default_lowers[0], 0.0)
        lowers.append(z1_lower)

        last = z1_lower
        for name, default in zip(zone_names[1:], default_lowers[1:]):
            value = prompt_lower(name, default, last)
            lowers.append(value)
            last = value

        default_cap = 1.5
        while True:
            raw = input(f"Z5 upper cap [{default_cap:.2f}]: ").strip()
            if not raw:
                cap = default_cap
            else:
                try:
                    cap = float(raw)
                except ValueError:
                    print("  Invalid number.")
                    continue
            if not (last < cap <= 3.0):
                print(f"  Cap must be greater than {last:.3f} and at most 3.0.")
                continue
            break

        zones = []
        for i, name in enumerate(zone_names):
            lo = lowers[i]
            hi = lowers[i + 1] if i < len(zone_names) - 1 else cap
            zones.append((name, lo, hi))

        upsert_hr_zones(conn, effective_date, sport, zones)

        print()
        print(f"Stored HR zones for sport='{sport}', effective_from_date={effective_date}:")
        for zone, lo, hi in zones:
            print(f"  {zone}: {lo:.3f}–{hi:.3f}")
    finally:
        conn.close()


def command_update_physiology():
    """Interactively record new physiology values with an effective date."""
    METRICS = {
        "resting_hr_bpm": ("Resting HR (bpm)",           30.0,  100.0),
        "max_hr_bpm":     ("Max HR (bpm)",                100.0, 250.0),
        "lthr_bpm":       ("Lactate Threshold HR (bpm)",  50.0,  250.0),
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
                SELECT value, effective_from_date FROM physiology_history
                WHERE metric = ? AND effective_from_date <= ?
                ORDER BY effective_from_date DESC LIMIT 1
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


def command_export():
    """Export training data to a Markdown file for AI-assisted coaching."""
    import argparse as _ap
    sub = _ap.ArgumentParser(prog="cli.py export")
    sub.add_argument(
        "--weeks", type=int, default=20,
        help="Number of weeks of history to export (default: 20)",
    )
    sub.add_argument(
        "--output", type=str, default=None,
        help="Output file path (default: data/export/training_export_YYYYMMDD.md)",
    )
    sub_args = sub.parse_args(sys.argv[2:])

    if sub_args.output:
        out_path = Path(sub_args.output)
    else:
        today_str = datetime.now().strftime("%Y%m%d")
        out_path = BASE_DIR / "data" / "export" / f"training_export_{today_str}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(DB_PATH)
    try:
        markdown = build_export(conn, weeks=sub_args.weeks)
    finally:
        conn.close()

    out_path.write_text(markdown, encoding="utf-8")
    log(f"Export written to {out_path} ({len(markdown):,} bytes)")


def command_reset():
    """Wipe the database and move all archived FIT files back to the inbox."""
    print("WARNING: This will delete the database and move all archived FIT files back to the inbox.")
    confirm = input("Type YES to continue: ").strip()
    if confirm != "YES":
        print("Aborted.")
        return

    ensure_project_dirs()

    if DB_PATH.exists():
        print("Wiping database...")
        DB_PATH.unlink()

    print("Creating blank database schema...")
    init_db(DB_PATH)

    print("Restoring archived FIT files to inbox...")
    moved = 0
    for file in ARCHIVE_DIR.glob("*"):
        if file.suffix.lower() in [".fit", ".zip"]:
            destination = INBOX_DIR / file.name
            if destination.exists():
                print(f"  Skipping (already in inbox): {file.name}")
                continue
            shutil.move(str(file), str(destination))
            moved += 1
    print(f"Restored {moved} file(s).")

    print()
    print("Reset complete. To restore your data:")
    print("  1. Restore physiology:  python scripts/cli.py update-physiology")
    print("  2. Restore HR zones:    python scripts/cli.py set-zones")
    print("  3. Re-ingest:           python scripts/cli.py sync")


def main():
    parser = argparse.ArgumentParser(
        description="Training Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  sync                ingest new FIT files and recalculate metrics  (daily use)
  recalculate         recompute ATL/CTL/form without re-reading FIT files
  update-physiology   record new HRmax/LTHR/HRrest with an effective date
  set-zones           add or update HR zone boundaries
  reset               wipe the database and restore archived FITs to inbox
  export              export training data to Markdown for AI coaching
                        [--weeks N] [--output PATH]
""",
    )
    parser.add_argument(
        "command",
        choices=["sync", "recalculate", "update-physiology", "set-zones", "reset", "export"],
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    if args.command == "sync":
        command_sync()
    elif args.command == "recalculate":
        command_recalculate()
    elif args.command == "set-zones":
        command_set_zones()
    elif args.command == "update-physiology":
        command_update_physiology()
    elif args.command == "reset":
        command_reset()
    elif args.command == "export":
        command_export()


if __name__ == "__main__":
    main()
