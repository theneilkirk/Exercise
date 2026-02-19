import sqlite3
import zipfile
import shutil
from pathlib import Path
from datetime import timezone
from fitparse import FitFile
from collections import defaultdict
from zones import get_lthr, get_hr_zones

from db import get_connection


BASE_DIR = Path(__file__).resolve().parent.parent.parent
INBOX_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_inbox"
ARCHIVE_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_archive"
WORK_DIR = BASE_DIR / "data" / "work" / "tmp_extract"


def get_activity_id_from_filename(path: Path):
    # Example filename: 12345678901_ACTIVITY.fit
    name = path.stem
    if name.isdigit():
        return name
    if "_" in name:
        possible_id = name.split("_")[0]
        if possible_id.isdigit():
            return possible_id
    return None


def extract_activity_data(fit_path: Path):
    fitfile = FitFile(str(fit_path))

    start_time = None
    sport = None
    total_distance = None
    total_duration = None
    total_elev_gain = None

    hr_values = []
    power_values = []
    speed_values = []

    physiology_observed = {}

    # ---- Record messages (per-second data) ----
    for record in fitfile.get_messages("record"):
        data = {field.name: field.value for field in record}

        if "timestamp" in data and start_time is None:
            start_time = data["timestamp"]

        if "distance" in data:
            total_distance = data["distance"]

        if "heart_rate" in data and data["heart_rate"] is not None:
            hr_values.append(data["heart_rate"])

        if "power" in data and data["power"] is not None:
            power_values.append(data["power"])

        if "enhanced_speed" in data and data["enhanced_speed"] is not None:
            speed_values.append(data["enhanced_speed"])

    # ---- Session summary ----
    for session in fitfile.get_messages("session"):
        data = {field.name: field.value for field in session}

        sport = data.get("sport", sport)
        total_duration = data.get("total_elapsed_time", total_duration)
        total_elev_gain = data.get("total_ascent", total_elev_gain)

        # User-level metrics sometimes stored here
        for metric in ["vo2max", "lactate_threshold_heart_rate",
                       "lactate_threshold_speed", "lactate_threshold_power",
                       "weight", "age"]:
            if metric in data and data[metric] is not None:
                physiology_observed[metric] = data[metric]

    # ---- Validation ----
    if start_time is None:
        raise ValueError("Missing start_time")

    if total_duration is None:
        raise ValueError("Missing duration")

    if total_distance is None:
        print(f"WARNING: Distance missing in {fit_path.name}")

    # ---- Derived averages ----
    avg_hr = sum(hr_values) / len(hr_values) if hr_values else None
    avg_power = sum(power_values) / len(power_values) if power_values else None
    avg_speed = sum(speed_values) / len(speed_values) if speed_values else None

    start_time_utc = start_time.astimezone(timezone.utc)

    return {
        "start_time_utc": start_time_utc.isoformat(),
        "sport": sport or "unknown",
        "duration_s": total_duration,
        "distance_m": total_distance,
        "elev_gain_m": total_elev_gain,
        "avg_hr": avg_hr,
        "avg_power": avg_power,
        "avg_speed_mps": avg_speed,
        "physiology_observed": physiology_observed
    }


def activity_exists(conn, activity_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM activities WHERE activity_id = ?",
        (activity_id,)
    )
    return cursor.fetchone() is not None


def insert_activity(conn, activity_id, activity):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO activities (
            activity_id,
            start_time_utc,
            sport,
            duration_s,
            distance_m,
            elev_gain_m,
            avg_hr,
            avg_power,
            avg_speed_mps
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        activity_id,
        activity["start_time_utc"],
        activity["sport"],
        activity["duration_s"],
        activity["distance_m"],
        activity["elev_gain_m"],
        activity["avg_hr"],
        activity["avg_power"],
        activity["avg_speed_mps"],
    ))
    conn.commit()


def process_fit_file(conn, fit_path: Path):
    activity_id = get_activity_id_from_filename(fit_path)

    try:
        activity = extract_activity_data(fit_path)
    except ValueError as e:
        print(f"WARNING: {fit_path.name} skipped: {e}")
        return "skipped"

    if activity_id is None:
        activity_id = activity["start_time_utc"]

    # Always rebuild this activity
    delete_existing_activity(conn, activity_id)

    insert_activity(conn, activity_id, activity)

    insert_physiology_observed(
        conn,
        activity["start_time_utc"],
        activity["physiology_observed"]
    )

    return "processed"

def delete_existing_activity(conn, activity_id):
    cursor = conn.cursor()

    cursor.execute("DELETE FROM activity_metrics WHERE activity_id = ?", (activity_id,))
    cursor.execute("DELETE FROM activities WHERE activity_id = ?", (activity_id,))

    conn.commit()


def insert_physiology_observed(conn, observed_at, metrics: dict):
    cursor = conn.cursor()

    for metric, value in metrics.items():
        cursor.execute("""
            INSERT OR REPLACE INTO physiology_observed (
                observed_at,
                metric,
                value,
                source
            ) VALUES (?, ?, ?, ?)
        """, (
            observed_at,
            metric,
            value,
            "garmin_fit"
        ))

    conn.commit()



def ingest_all_fits(db_path: Path):
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection(db_path)

    processed = 0
    skipped = 0

    for file in INBOX_DIR.iterdir():

        try:
            if file.suffix.lower() == ".zip":
                with zipfile.ZipFile(str(file), 'r') as zip_ref:
                    zip_ref.extractall(WORK_DIR)

                for extracted in WORK_DIR.glob("*.fit"):
                    result = process_fit_file(conn, extracted)
                    if result == "processed":
                        processed += 1
                    else:
                        skipped += 1

                shutil.rmtree(WORK_DIR)
                WORK_DIR.mkdir(parents=True, exist_ok=True)

                file.rename(ARCHIVE_DIR / file.name)

            elif file.suffix.lower() == ".fit":
                result = process_fit_file(conn, file)
                if result == "processed":
                    processed += 1
                else:
                    skipped += 1

                file.rename(ARCHIVE_DIR / file.name)

        except Exception as e:
            print(f"Error processing {file.name}: {e}")

    conn.close()

    return {
        "processed": processed,
        "skipped": skipped
    }