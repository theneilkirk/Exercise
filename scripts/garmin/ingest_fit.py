import zipfile
import shutil
from pathlib import Path
from datetime import timezone
from fitparse import FitFile
from collections import defaultdict
import math

from zones import get_lthr, get_hr_zones, get_hr_rest, get_hr_max
from db import get_connection


BASE_DIR = Path(__file__).resolve().parent.parent.parent
INBOX_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_inbox"
ARCHIVE_DIR = BASE_DIR / "data" / "raw" / "garmin_fit_archive"
WORK_DIR = BASE_DIR / "data" / "work" / "tmp_extract"


# -----------------------------
# TRIMP coefficients
# -----------------------------
# Male (Banister): 0.64, 1.92
# Female variant:  0.86, 1.67
TRIMP_A = 0.64
TRIMP_B = 1.92


# -----------------------------
# Garmin numeric sport code map
# -----------------------------
# Add new mappings here as needed (value is always a string from fitparse).
SPORT_CODE_MAP = {
    "64": "racket",
}


def get_activity_id_from_filename(path: Path):
    name = path.stem
    if name.isdigit():
        return name
    if "_" in name:
        possible_id = name.split("_")[0]
        if possible_id.isdigit():
            return possible_id
    return None


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def extract_activity_data(conn, fit_path: Path):
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

    # We store (timestamp, hr) for zone + TRIMP computation
    record_rows = []

    # ---- Record messages ----
    for record in fitfile.get_messages("record"):
        data = {field.name: field.value for field in record}

        ts = data.get("timestamp")
        hr = data.get("heart_rate")

        if ts and start_time is None:
            start_time = ts

        if "distance" in data:
            total_distance = data["distance"]

        if hr is not None:
            hr_values.append(hr)

        if data.get("power") is not None:
            power_values.append(data["power"])

        if data.get("enhanced_speed") is not None:
            speed_values.append(data["enhanced_speed"])

        if ts is not None:
            record_rows.append((ts, hr))

    # ---- Session summary ----
    for session in fitfile.get_messages("session"):
        data = {field.name: field.value for field in session}

        sport = data.get("sport", sport)
        total_duration = data.get("total_elapsed_time", total_duration)
        total_elev_gain = data.get("total_ascent", total_elev_gain)

        for metric in [
            "vo2max",
            "lactate_threshold_heart_rate",
            "lactate_threshold_speed",
            "lactate_threshold_power",
            "weight",
            "age"
        ]:
            if metric in data and data[metric] is not None:
                physiology_observed[metric] = data[metric]

    # ---- Validation ----
    if start_time is None:
        raise ValueError("Missing start_time")

    if total_duration is None:
        raise ValueError("Missing duration")

    if total_distance is None:
        print(f"WARNING: Distance missing in {fit_path.name}")

    start_time_utc = start_time.astimezone(timezone.utc)
    activity_date = start_time_utc.date().isoformat()

    # ---- Derived averages ----
    avg_hr = sum(hr_values) / len(hr_values) if hr_values else None
    avg_power = sum(power_values) / len(power_values) if power_values else None
    avg_speed = sum(speed_values) / len(speed_values) if speed_values else None

    # --------------------------------------------------
    # HR Zone Computation (LTHR-based)
    # --------------------------------------------------
    zone_seconds = defaultdict(int)

    resolved_sport = str(sport or "unknown").lower()
    # your zones are seeded as "running"; if Garmin sport strings differ, we still pass the raw sport
    lthr = get_lthr(conn, activity_date)
    zones = get_hr_zones(conn, activity_date, str(sport) if sport is not None else "running")

    if lthr and zones and record_rows:
        last_ts = None

        for ts, hr in record_rows:
            if hr is None:
                last_ts = ts
                continue

            if last_ts is not None:
                delta = (ts - last_ts).total_seconds()
                delta = max(0, min(delta, 5))  # clamp safety
            else:
                delta = 1

            intensity = hr / lthr

            for zone, lo, hi in zones:
                if lo <= intensity < hi:
                    zone_seconds[zone] += int(delta)
                    break

            last_ts = ts
    else:
        print(f"WARNING: HR zones not computed for {fit_path.name} (missing LTHR/zones/records)")

    # --------------------------------------------------
    # Banister HRr TRIMP
    # --------------------------------------------------
    trimp_total = None
    hr_rest = get_hr_rest(conn, activity_date)
    hr_max = get_hr_max(conn, activity_date)

    if hr_rest is not None and hr_max is not None and record_rows:
        denom = hr_max - hr_rest
        if denom <= 0:
            print(f"WARNING: Invalid HRrest/HRmax (rest={hr_rest}, max={hr_max}) for {fit_path.name}")
        else:
            trimp = 0.0
            last_ts = None

            for ts, hr in record_rows:
                if hr is None:
                    last_ts = ts
                    continue

                if last_ts is not None:
                    delta_s = (ts - last_ts).total_seconds()
                    delta_s = max(0, min(delta_s, 5))
                else:
                    delta_s = 1

                delta_min = delta_s / 60.0

                hrr = (hr - hr_rest) / denom
                hrr = clamp(hrr, 0.0, 1.0)

                trimp += delta_min * hrr * TRIMP_A * math.exp(TRIMP_B * hrr)

                last_ts = ts

            trimp_total = trimp
    else:
        print(f"WARNING: TRIMP not computed for {fit_path.name} (missing HRrest/HRmax/records)")

    return {
        "start_time_utc": start_time_utc.isoformat(),
        "sport": SPORT_CODE_MAP.get(str(sport), str(sport)) if sport is not None else "unknown",
        "duration_s": total_duration,
        "distance_m": total_distance,
        "elev_gain_m": total_elev_gain,
        "avg_hr": avg_hr,
        "avg_power": avg_power,
        "avg_speed_mps": avg_speed,
        "physiology_observed": physiology_observed,
        "zone_seconds": dict(zone_seconds),
        "trimp_total": trimp_total
    }


def delete_existing_activity(conn, activity_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM activity_hr_zone_summary WHERE activity_id = ?", (activity_id,))
    cursor.execute("DELETE FROM activity_metrics WHERE activity_id = ?", (activity_id,))
    cursor.execute("DELETE FROM activities WHERE activity_id = ?", (activity_id,))
    conn.commit()


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


def insert_zone_summary(conn, activity_id, zone_seconds: dict):
    cursor = conn.cursor()
    for zone, seconds in zone_seconds.items():
        cursor.execute("""
            INSERT INTO activity_hr_zone_summary
            (activity_id, zone, seconds_in_zone)
            VALUES (?, ?, ?)
        """, (activity_id, zone, seconds))
    conn.commit()


def insert_activity_metrics(conn, activity_id, trimp_total):
    cursor = conn.cursor()

    # For now, we define load_points == TRIMP. This is transparent and will
    # plug straight into ATL/CTL next.
    load_points = trimp_total

    cursor.execute("""
        INSERT OR REPLACE INTO activity_metrics
        (activity_id, trimp_total, load_points)
        VALUES (?, ?, ?)
    """, (activity_id, trimp_total, load_points))

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


def process_fit_file(conn, fit_path: Path):
    activity_id = get_activity_id_from_filename(fit_path)

    try:
        activity = extract_activity_data(conn, fit_path)
    except ValueError as e:
        print(f"WARNING: {fit_path.name} skipped: {e}")
        return "skipped"

    if activity_id is None:
        activity_id = activity["start_time_utc"]

    delete_existing_activity(conn, activity_id)

    insert_activity(conn, activity_id, activity)
    insert_zone_summary(conn, activity_id, activity["zone_seconds"])
    insert_activity_metrics(conn, activity_id, activity["trimp_total"])

    insert_physiology_observed(
        conn,
        activity["start_time_utc"],
        activity["physiology_observed"]
    )

    return "processed"


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

    return {"processed": processed, "skipped": skipped}
