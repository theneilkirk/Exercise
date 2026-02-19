import sqlite3
from pathlib import Path


def get_connection(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Version table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
    """)

    # Activities table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY,
            start_time_utc TEXT NOT NULL,
            sport TEXT NOT NULL,
            duration_s INTEGER,
            distance_m REAL,
            elev_gain_m REAL,
            avg_hr REAL,
            avg_power REAL,
            avg_speed_mps REAL
        );
    """)

    # Activity metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_metrics (
            activity_id TEXT PRIMARY KEY,
            trimp_total REAL,
            load_points REAL,
            z4_5_minutes REAL,
            aerobic_efficiency REAL,
            hr_drift REAL,
            FOREIGN KEY (activity_id)
                REFERENCES activities (activity_id)
                ON DELETE CASCADE
        );
    """)

    # Daily metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_metrics (
            date TEXT PRIMARY KEY,
            load_points REAL,
            ctl REAL,
            atl REAL,
            form REAL,
            ac_ratio REAL,
            ramp_rate REAL,
            monotony REAL,
            strain REAL
        );
    """)
    
    # Observed physiology metrics from device (time-aware)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS physiology_observed (
            observed_at TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            source TEXT NOT NULL,
            PRIMARY KEY (observed_at, metric)
        );
    """)
    
    # --------------------------------------------------
    # Physiology history (time-aware thresholds)
    # --------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS physiology_history (
        effective_from_date DATE NOT NULL,
        metric TEXT NOT NULL,
        value REAL NOT NULL,
        source TEXT,
        notes TEXT,
        PRIMARY KEY (effective_from_date, metric)
    );
    """)
    
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_physiology_metric_date
    ON physiology_history(metric, effective_from_date);
    """)
    
    # --------------------------------------------------
    # HR Zone definitions (percentage of LTHR)
    # --------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS zones_hr_history (
        effective_from_date DATE NOT NULL,
        sport TEXT NOT NULL,
        zone TEXT NOT NULL,
        lower_pct REAL NOT NULL,
        upper_pct REAL NOT NULL,
        PRIMARY KEY (effective_from_date, sport, zone)
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_zones_hr_lookup
    ON zones_hr_history(sport, effective_from_date);
    """)

    # --------------------------------------------------
    # Activity HR Zone Summary
    # --------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_hr_zone_summary (
        activity_id TEXT NOT NULL,
        zone TEXT NOT NULL,
        seconds_in_zone INTEGER NOT NULL,
        PRIMARY KEY (activity_id, zone)
    );
    """)

    conn.commit()
    conn.close()