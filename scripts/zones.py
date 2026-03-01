def get_physiology_metric(conn, activity_date: str, metric: str):
    """
    Returns the most recent value for a metric with effective_from_date <= activity_date.
    activity_date: 'YYYY-MM-DD'
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT value
        FROM physiology_history
        WHERE metric = ?
          AND effective_from_date <= ?
        ORDER BY effective_from_date DESC
        LIMIT 1
    """, (metric, activity_date))
    row = cur.fetchone()
    return row[0] if row else None


def get_lthr(conn, activity_date: str):
    return get_physiology_metric(conn, activity_date, "lthr_bpm")


def get_hr_rest(conn, activity_date: str):
    return get_physiology_metric(conn, activity_date, "resting_hr_bpm")


def get_hr_max(conn, activity_date: str):
    return get_physiology_metric(conn, activity_date, "max_hr_bpm")


def get_hr_zones(conn, activity_date: str, sport: str):
    cur = conn.cursor()

    # Prefer sport-specific zones
    cur.execute("""
        SELECT zone, lower_pct, upper_pct
        FROM zones_hr_history
        WHERE sport = ?
          AND effective_from_date <= ?
        ORDER BY effective_from_date DESC
    """, (sport, activity_date))
    rows = cur.fetchall()
    if rows:
        return rows

    # Fallback: sport='any'
    cur.execute("""
        SELECT zone, lower_pct, upper_pct
        FROM zones_hr_history
        WHERE sport = 'any'
          AND effective_from_date <= ?
        ORDER BY effective_from_date DESC
    """, (activity_date,))
    rows = cur.fetchall()
    if rows:
        return rows

    # Final fallback: use 'running' zones if available for this date
    cur.execute("""
        SELECT zone, lower_pct, upper_pct
        FROM zones_hr_history
        WHERE sport = 'running'
          AND effective_from_date <= ?
        ORDER BY effective_from_date DESC
    """, (activity_date,))
    return cur.fetchall()