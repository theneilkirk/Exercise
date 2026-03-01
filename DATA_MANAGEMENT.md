# Managing your training data

This document is for users who already have the engine installed and want to manage their data: ingest FIT files, manage HR zones, and rebuild derived metrics.

For installation and system administration details, see `SETUP.md`.

All commands below are run from the repo root:

```powershell
cd path\to\repo
```

## 1. First-time setup (per user / per machine)

### 1.1 Initialise DB schema and folders

This creates the SQLite DB and the expected directory scaffolding (`db/`, `data/raw/...`, `data/work/`) if they don’t already exist:

```powershell
python .\scripts\cli.py init-db
```

### 1.2 Seed initial HR profile + zones

This seeds your baseline physiology and HR zones so that subsequent ingest can compute zone-based metrics and TRIMP:

- Writes `physiology_history` rows (e.g. LTHR, HRmax, HRrest).
- Writes `zones_hr_history` rows (Z1–Z5 bounds as fractions of LTHR).

Run:

```powershell
python .\scripts\cli.py seed-hr-zones
```

You can re-run this later when your physiology changes; see “Tweaking HR zones over time” below.

## 2. Ingesting FIT files

### 2.1 Drop files into the inbox

Copy `.fit` or `.zip` files into:

- `data/raw/garmin_fit_inbox/`

### 2.2 Run ingest

```powershell
python .\scripts\cli.py fit-ingest
```

Ingest currently:

- Inserts/overwrites `activities`.
- Stores device-reported values into `physiology_observed` when present (e.g. VO2max, weight).
- Computes HR time-in-zone into `activity_hr_zone_summary` (LTHR-relative zones).
- Computes Banister HRr TRIMP into `activity_metrics.trimp_total` when HRrest/HRmax exist.
- Sets `activity_metrics.load_points = trimp_total` (current transparent definition).

HR zones are resolved as follows for each activity date:

- **First**, zones matching the activity `sport` with `effective_from_date <= activity_date`.
- **Second**, zones where `sport = 'any'` with `effective_from_date <= activity_date`.
- **Third**, if neither exist, zones where `sport = 'running'` with `effective_from_date <= activity_date`.

In all cases, the most recent `effective_from_date` not later than the activity date is used.

Processed files are moved from `data/raw/garmin_fit_inbox/` to `data/raw/garmin_fit_archive/`.

## 3. Updating physiology over time

Both physiology metrics and HR zone definitions are stored with an `effective_from_date`. The engine always picks the most recent row not later than each activity’s date, so history is preserved automatically.

### 3.1 Updating physiology metrics (HRmax, LTHR, HRrest)

When a physiology metric changes — for example Garmin revises your estimated max HR, or you retest your LTHR — record the updated value with an effective date:

```powershell
python .\scripts\cli.py update-physiology
```

The CLI will:

- **Ask for effective_from_date** (default: today’s date, `YYYY-MM-DD`).
- **Show current values** for each metric as of that date, so you have context before editing.
- **Prompt for each metric** — Resting HR, Max HR, Lactate Threshold HR — press Enter to skip any you are not changing.

After updating, run `rebuild-derived` to propagate changes to all derived metrics (TRIMP, zone seconds, load, ATL/CTL, etc.).

### 3.2 Updating HR zones

When your HR zones change (for example after a new threshold test), add a new set of zone definitions for a specific date and sport. This preserves history and lets the engine use the correct zones for each activity date.

Run:

```powershell
python .\scripts\cli.py add-hr-zones
```

The CLI will:

- **Ask for sport** (default: `running`).
- **Ask for effective_from_date** (default: today’s date, `YYYY-MM-DD`).
- **Prompt you for Z1–Z5 lower bounds** as fractions of LTHR (e.g. `0.67`, `0.84`), with sensible defaults you can accept by pressing Enter.
- **Prompt for a Z5 upper cap** (default: `1.50`).

Upper bounds are derived automatically so that zones are continuous with no gaps. Each run writes/overwrites the `zones_hr_history` rows for that `(effective_from_date, sport, zone)` set. Ingest + rebuild will automatically respect the time-aware history.

## 4. Rebuilding derived metrics

You can safely recompute all derived training-load metrics whenever:

- You adjust physiology or HR zones.
- The load model logic changes.
- You want to ensure all derived tables are consistent with the current raw data.

Run:

```powershell
python .\scripts\cli.py rebuild-derived
```

This command **does not re-read FIT files**; it only recomputes all derived training-load metrics from the current contents of the database:

- `daily_metrics`: load points, CTL (42-day EWMA), ATL (7-day EWMA), form (CTL − ATL), AC ratio, CTL season best, ramp rate (7-day CTL change), Foster monotony, and Foster strain.
- `activity_metrics.load_points` (re-derived from TRIMP).

## 5. Full rebuild / starting over

If you want to reset everything from scratch and replay all FITs:

1. **Destructive reset** (DB + FIT locations):

   ```powershell
   python .\scripts\cli.py nuke
   ```

   This resets the DB and restores archived FITs back to the inbox. Follow the printed next steps.

2. **Re-seed HR profile + zones**:

   ```powershell
   python .\scripts\cli.py seed-hr-zones
   ```

3. **Re-ingest FIT files**:

   ```powershell
   python .\scripts\cli.py fit-ingest
   ```

4. **(Optional) Rebuild derived metrics**:

   ```powershell
   python .\scripts\cli.py rebuild-derived
   ```

If you prefer a one-shot convenience command that chains these steps:

```powershell
python .\scripts\cli.py full-rebuild
```

