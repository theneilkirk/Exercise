from collections import deque
from datetime import datetime, timedelta
import sqlite3
import statistics

# ============================
# Parameterised Model Constants
# ============================

ATL_DAYS = 7
CTL_DAYS = 42

AC_RATIO_LOW = 0.8
AC_RATIO_HIGH = 1.3

DATE_FORMAT = "%Y-%m-%d"


# ============================
# Helpers
# ============================

def ewma_alpha(days: int) -> float:
    return 2 / (days + 1)


def get_date_range(conn):
    cursor = conn.cursor()

    cursor.execute("""
        SELECT MIN(date(start_time_utc)), MAX(date(start_time_utc))
        FROM activities
    """)
    row = cursor.fetchone()

    if not row or not row[0]:
        return None, None

    start_date = datetime.strptime(row[0], DATE_FORMAT).date()
    end_date = datetime.strptime(row[1], DATE_FORMAT).date()

    return start_date, end_date


def build_continuous_dates(start_date, end_date):
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def get_daily_loads(conn):
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date(a.start_time_utc) as activity_date,
               SUM(m.load_points)
        FROM activities a
        JOIN activity_metrics m
          ON a.activity_id = m.activity_id
        GROUP BY activity_date
    """)

    return {
        datetime.strptime(row[0], DATE_FORMAT).date(): row[1]
        for row in cursor.fetchall()
    }


# ============================
# Core Computation
# ============================

def rebuild_load_model(conn):

    start_date, end_date = get_date_range(conn)
    if not start_date:
        print("No activities found. Skipping load model.")
        return

    daily_load_lookup = get_daily_loads(conn)
    date_series = build_continuous_dates(start_date, end_date)

    atl_alpha = ewma_alpha(ATL_DAYS)
    ctl_alpha = ewma_alpha(CTL_DAYS)

    atl = 0.0
    ctl = 0.0
    season_best_ctl = 0

    load_window = deque(maxlen=7)   # last 7 daily loads
    ctl_history = deque(maxlen=8)   # last 8 CTL values (to compute 7-day change)

    rows_to_insert = []

    for date in date_series:

        load = daily_load_lookup.get(date, 0.0)

        atl = atl + atl_alpha * (load - atl)
        ctl = ctl + ctl_alpha * (load - ctl)

        form = ctl - atl

        ac_ratio = None
        if ctl > 0:
            ac_ratio = atl / ctl

        season_best_ctl = max(season_best_ctl, ctl)

        load_window.append(load)
        ctl_history.append(ctl)

        # ramp_rate: CTL change over 7 days (needs 8 data points)
        ramp_rate = (ctl - ctl_history[0]) if len(ctl_history) == 8 else None

        # monotony: mean / population-stdev of last 7 loads (Foster)
        if len(load_window) >= 2:
            stdev = statistics.pstdev(load_window)
            mean_load = statistics.mean(load_window)
            monotony = (mean_load / stdev) if stdev > 0 else None
        else:
            monotony = None

        # strain: 7-day total × monotony (Foster)
        strain = (sum(load_window) * monotony) if monotony is not None else None

        rows_to_insert.append((
            date.strftime(DATE_FORMAT),
            load,
            ctl,
            atl,
            form,
            ac_ratio,
            season_best_ctl,
            ramp_rate,
            monotony,
            strain,
        ))

    cursor = conn.cursor()

    cursor.execute("DELETE FROM daily_metrics")

    cursor.executemany("""
        INSERT INTO daily_metrics (
            date,
            load_points,
            ctl,
            atl,
            form,
            ac_ratio,
            ctl_season_best,
            ramp_rate,
            monotony,
            strain
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows_to_insert)

    conn.commit()

    print("Load model rebuild complete.")
