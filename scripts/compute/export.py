from datetime import date, datetime, timedelta
import sqlite3

DATE_FORMAT = "%Y-%m-%d"


def fmt(value, decimals=1, suffix=""):
    """Format a nullable float for Markdown tables. None renders as '-'."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}{suffix}"


def get_cutoff_date(weeks: int) -> str:
    return (date.today() - timedelta(weeks=weeks)).isoformat()


def fetch_physiology_profile(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    result = {}
    for metric in ("lthr_bpm", "max_hr_bpm", "resting_hr_bpm"):
        cur.execute(
            """
            SELECT value, effective_from_date
            FROM physiology_history
            WHERE metric = ?
            ORDER BY effective_from_date DESC
            LIMIT 1
            """,
            (metric,),
        )
        row = cur.fetchone()
        result[metric] = (row[0], row[1]) if row else (None, None)

    cur.execute(
        """
        SELECT zone, lower_pct, upper_pct
        FROM zones_hr_history
        WHERE sport = 'running'
          AND effective_from_date = (
              SELECT MAX(effective_from_date)
              FROM zones_hr_history
              WHERE sport = 'running'
          )
        ORDER BY zone ASC
        """
    )
    result["hr_zones"] = cur.fetchall()  # list of (zone, lower_pct, upper_pct)

    cur.execute(
        "SELECT MAX(effective_from_date) FROM zones_hr_history WHERE sport = 'running'"
    )
    row = cur.fetchone()
    result["zones_effective_date"] = row[0] if row else None

    return result


def fetch_current_fitness(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sport, ctl, atl, form, ac_ratio, ramp_rate, ctl_season_best
        FROM daily_metrics
        WHERE date = (SELECT MAX(date) FROM daily_metrics)
          AND sport IN ('all', 'running')
        ORDER BY sport
        """
    )
    result = {"date": None, "all": {}, "running": {}}
    for row in cur.fetchall():
        sport, ctl, atl, form, ac_ratio, ramp_rate, ctl_season_best = row
        result[sport] = {
            "ctl": ctl,
            "atl": atl,
            "form": form,
            "ac_ratio": ac_ratio,
            "ramp_rate": ramp_rate,
            "ctl_season_best": ctl_season_best,
        }
    cur.execute("SELECT MAX(date) FROM daily_metrics")
    row = cur.fetchone()
    result["date"] = row[0] if row else None
    return result


def fetch_daily_metrics(conn: sqlite3.Connection, cutoff: str) -> list:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT date, sport, load_points, ctl, atl, form, ac_ratio, ramp_rate
        FROM daily_metrics
        WHERE date >= ?
          AND sport IN ('all', 'running')
        ORDER BY date ASC, sport ASC
        """,
        (cutoff,),
    )
    cols = ["date", "sport", "load_points", "ctl", "atl", "form", "ac_ratio", "ramp_rate"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_activities(conn: sqlite3.Connection, cutoff: str) -> list:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            a.activity_id,
            date(a.start_time_utc) AS activity_date,
            a.sport,
            ROUND(a.duration_s / 60.0, 0) AS duration_min,
            ROUND(a.distance_m / 1000.0, 2) AS distance_km,
            ROUND(a.elev_gain_m, 0) AS elev_gain_m,
            ROUND(a.avg_hr, 0) AS avg_hr,
            m.trimp_total
        FROM activities a
        LEFT JOIN activity_metrics m ON a.activity_id = m.activity_id
        WHERE date(a.start_time_utc) >= ?
        ORDER BY a.start_time_utc ASC
        """,
        (cutoff,),
    )
    cols = [
        "activity_id", "date", "sport", "duration_min", "distance_km",
        "elev_gain_m", "avg_hr", "trimp_total",
    ]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_zone_data(conn: sqlite3.Connection, cutoff: str) -> dict:
    """Returns {activity_id: {zone: seconds_in_zone}} for the export window."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT z.activity_id, z.zone, z.seconds_in_zone
        FROM activity_hr_zone_summary z
        JOIN activities a ON z.activity_id = a.activity_id
        WHERE date(a.start_time_utc) >= ?
        ORDER BY z.activity_id, z.zone
        """,
        (cutoff,),
    )
    result = {}
    for activity_id, zone, seconds in cur.fetchall():
        result.setdefault(activity_id, {})[zone] = seconds
    return result


def fetch_observed_physiology(conn: sqlite3.Connection) -> list:
    """Returns the most recent observed value per metric."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT metric, value, observed_at
        FROM physiology_observed
        ORDER BY observed_at DESC
        """
    )
    seen = set()
    result = []
    for metric, value, observed_at in cur.fetchall():
        if metric not in seen:
            result.append({"metric": metric, "value": value, "observed_at": observed_at})
            seen.add(metric)
    return result


def compute_zone_pcts(zone_seconds: dict) -> dict:
    """Returns {zone: integer_pct} summing to 100, or {} if no zone data."""
    total = sum(zone_seconds.values())
    if total == 0:
        return {}
    return {zone: round(seconds / total * 100) for zone, seconds in zone_seconds.items()}


def aggregate_weekly(activities: list, zone_data: dict) -> list:
    """Groups activities by ISO week. Returns list of weekly summary dicts."""
    weeks = {}
    for act in activities:
        d = datetime.strptime(act["date"], DATE_FORMAT).date()
        iso = d.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"
        if week_key not in weeks:
            weeks[week_key] = {
                "week": week_key,
                "activity_count": 0,
                "total_duration_min": 0.0,
                "total_distance_km": 0.0,
                "total_trimp": 0.0,
                "zone_seconds": {},
            }
        w = weeks[week_key]
        w["activity_count"] += 1
        w["total_duration_min"] += act["duration_min"] or 0
        w["total_distance_km"] += act["distance_km"] or 0
        w["total_trimp"] += act["trimp_total"] or 0
        for zone, secs in zone_data.get(act["activity_id"], {}).items():
            w["zone_seconds"][zone] = w["zone_seconds"].get(zone, 0) + secs

    result = []
    for week_key in sorted(weeks.keys()):
        w = weeks[week_key]
        result.append({
            "week": w["week"],
            "activity_count": w["activity_count"],
            "total_hours": round(w["total_duration_min"] / 60, 1),
            "total_distance_km": round(w["total_distance_km"], 1),
            "total_trimp": round(w["total_trimp"], 1),
            "zone_pcts": compute_zone_pcts(w["zone_seconds"]),
        })
    return result


def _zone_cols(zone_pcts: dict) -> str:
    """Render Z1–Z5 percentage columns for a Markdown table row."""
    return " | ".join(
        str(zone_pcts[z]) if zone_pcts and z in zone_pcts else "-"
        for z in ("Z1", "Z2", "Z3", "Z4", "Z5")
    )


def build_export(conn: sqlite3.Connection, weeks: int = 20) -> str:
    """Fetch all data and render a complete Markdown export string."""
    today = date.today()
    today_str = today.isoformat()
    cutoff = get_cutoff_date(weeks)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    profile = fetch_physiology_profile(conn)
    fitness = fetch_current_fitness(conn)
    daily = fetch_daily_metrics(conn, cutoff)
    activities = fetch_activities(conn, cutoff)
    zone_data = fetch_zone_data(conn, cutoff)
    observed = fetch_observed_physiology(conn)
    weekly = aggregate_weekly(activities, zone_data)

    lines = []

    # --- Header ---
    lines += [
        f"# Training Export — {today_str}",
        f"Generated: {now_str}  |  Export period: {cutoff} to {today_str} ({weeks} weeks)",
        "",
        "> **Context for AI coach:** This file contains structured training data from a local",
        "> training engine using Banister HRr TRIMP for load quantification and EWMA-based",
        "> CTL (42-day) and ATL (7-day) for fitness/fatigue modelling.",
        "> The athlete is preparing for **Comrades Marathon** (87 km ultramarathon, late May/early June 2026).",
        "> Use this data to assess current fitness and advise on training periodisation.",
        "",
        "---",
        "",
    ]

    # --- Athlete Profile ---
    lines.append("## Athlete Profile")
    lines.append("")
    lthr, lthr_date = profile.get("lthr_bpm", (None, None))
    hrmax, _ = profile.get("max_hr_bpm", (None, None))
    hrrest, _ = profile.get("resting_hr_bpm", (None, None))
    phys_date = lthr_date or "(not set)"

    lines += [
        f"**Physiology** (effective from {phys_date}):",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| LTHR | {fmt(lthr, 0, ' bpm') if lthr is not None else '(not set)'} |",
        f"| HRmax | {fmt(hrmax, 0, ' bpm') if hrmax is not None else '(not set)'} |",
        f"| HRrest | {fmt(hrrest, 0, ' bpm') if hrrest is not None else '(not set)'} |",
        "",
    ]

    hr_zones = profile.get("hr_zones", [])
    zones_date = profile.get("zones_effective_date")
    if hr_zones:
        lines.append(
            f"**HR Zones — Running** (LTHR-relative, effective {zones_date or '(unknown)'}):"
        )
        lines.append("")
        if lthr is not None:
            lines += ["| Zone | Lower (×LTHR) | Upper (×LTHR) | Lower BPM | Upper BPM |", "|---|---|---|---|---|"]
            for zone, lo, hi in hr_zones:
                lines.append(f"| {zone} | {lo:.2f} | {hi:.2f} | {round(lo * lthr)} | {round(hi * lthr)} |")
        else:
            lines += ["| Zone | Lower (×LTHR) | Upper (×LTHR) |", "|---|---|---|"]
            for zone, lo, hi in hr_zones:
                lines.append(f"| {zone} | {lo:.2f} | {hi:.2f} |")
    else:
        lines.append("**HR Zones:** (not set)")

    lines += ["", "---", ""]

    # --- Current Fitness ---
    lines += [
        "## Current Fitness State",
        "",
        f"As of {fitness.get('date') or '(no data)'}:",
        "",
        "| Metric | All Sports | Running |",
        "|---|---|---|",
    ]
    fa = fitness.get("all") or {}
    fr = fitness.get("running") or {}
    lines += [
        f"| CTL (fitness) | {fmt(fa.get('ctl'))} | {fmt(fr.get('ctl'))} |",
        f"| ATL (fatigue) | {fmt(fa.get('atl'))} | {fmt(fr.get('atl'))} |",
        f"| Form (CTL−ATL) | {fmt(fa.get('form'))} | {fmt(fr.get('form'))} |",
        f"| AC Ratio | {fmt(fa.get('ac_ratio'), 2)} | {fmt(fr.get('ac_ratio'), 2)} |",
        f"| Ramp Rate (7d CTL change) | {fmt(fa.get('ramp_rate'))} | {fmt(fr.get('ramp_rate'))} |",
        f"| Season-best CTL | {fmt(fa.get('ctl_season_best'))} | {fmt(fr.get('ctl_season_best'))} |",
        "",
        "*AC ratio optimal range: 0.8–1.3. Form: >+15 very fresh, −5 to −30 productive training.*",
        "",
        "---",
        "",
    ]

    # --- Device-Observed Metrics ---
    if observed:
        lines += [
            "## Device-Observed Metrics",
            "",
            "Most recent device readings from Garmin FIT files:",
            "",
            "| Metric | Value | Last seen |",
            "|---|---|---|",
        ]
        for obs in observed:
            label = obs["metric"].replace("_", " ").title()
            lines.append(f"| {label} | {fmt(obs['value'], 1)} | {obs['observed_at'][:10]} |")
        lines += ["", "---", ""]

    # --- Weekly Summary ---
    lines += [
        f"## Weekly Summary ({weeks} weeks)",
        "",
        "| Week | Activities | Hours | Dist km | TRIMP | Z1% | Z2% | Z3% | Z4% | Z5% |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for w in weekly:
        lines.append(
            f"| {w['week']} | {w['activity_count']} | {w['total_hours']:.1f} | "
            f"{w['total_distance_km']:.1f} | {fmt(w['total_trimp'])} | {_zone_cols(w['zone_pcts'])} |"
        )
    lines += ["", "---", ""]

    # --- Daily Metrics ---
    for sport_label, sport_key in (("All Sports", "all"), ("Running", "running")):
        lines += [
            f"## Daily Metrics — {sport_label} ({weeks} weeks)",
            "",
            "| Date | Load | CTL | ATL | Form | AC Ratio | Ramp |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in daily:
            if row["sport"] != sport_key:
                continue
            lines.append(
                f"| {row['date']} | {fmt(row['load_points'])} | {fmt(row['ctl'])} | "
                f"{fmt(row['atl'])} | {fmt(row['form'])} | {fmt(row['ac_ratio'], 2)} | "
                f"{fmt(row['ramp_rate'])} |"
            )
        lines += [""]

    lines += ["---", ""]

    # --- Activity Log ---
    lines += [
        f"## Activity Log ({weeks} weeks)",
        "",
        "| Date | Sport | Min | Dist km | Elev m | Avg HR | TRIMP | Z1% | Z2% | Z3% | Z4% | Z5% |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for act in activities:
        zp = compute_zone_pcts(zone_data.get(act["activity_id"], {}))
        lines.append(
            f"| {act['date']} | {act['sport']} | {fmt(act['duration_min'], 0)} | "
            f"{fmt(act['distance_km'], 2)} | {fmt(act['elev_gain_m'], 0)} | "
            f"{fmt(act['avg_hr'], 0)} | {fmt(act['trimp_total'])} | {_zone_cols(zp)} |"
        )
    lines += ["", "---", ""]

    # --- Model Parameters ---
    lines += [
        "## Model Parameters",
        "",
        "| Parameter | Value |",
        "|---|---|",
        "| ATL time constant | 7 days |",
        "| CTL time constant | 42 days |",
        "| TRIMP formula | Banister HRr (male: A=0.64, B=1.92) |",
        "| Load currency | TRIMP total |",
        "| Form | CTL − ATL |",
        "| AC Ratio | ATL / CTL |",
        "",
        "---",
        f"*Exported by Training Engine. Data spans {cutoff} to {today_str}.*",
    ]

    return "\n".join(lines) + "\n"
