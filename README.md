# Training Engine (local/offline)

Local, offline-first training intelligence engine that ingests Garmin `.fit` files into a single SQLite database and computes transparent, rebuildable training metrics (no vendor “black box” metrics).

## Documentation

- **Setup / administration**: install, configure, and maintain the project (virtualenv, dependencies, folders, backups, destructive operations). See `SETUP.md`.
- **Everyday data management**: ingest FIT files, manage HR zones, and rebuild derived metrics as a user. See `DATA_MANAGEMENT.md`.
- **Methodology**: full derivation of every metric (TRIMP, HR zones, ATL/CTL, Form, AC ratio, ramp rate, Foster monotony and strain) with primary references. See `METHODOLOGY.md`.

## Design principles

- **Offline-first / single-user**: everything is local.
- **Deterministic & idempotent**: derived tables are rebuildable; rerunning should reproduce the same results.
- **Transparent physiology-aware logic**: no vendor Training Effect / Recovery Time, etc.

# Training Engine (local/offline)

Local, offline-first training intelligence engine that ingests Garmin `.fit` files into a single SQLite database and computes transparent, rebuildable training metrics (no vendor “black box” metrics).

## Stack

- Python **3.11**
- SQLite (single file DB at `db/training.db`)
- Garmin FIT parsing via `fitparse`

## Repo layout

- `db/`
  - `training.db` (local database file; ignored by `.gitignore`)
- `data/`
  - `raw/garmin_fit_inbox/` (drop new `.fit`/`.zip` here)
  - `raw/garmin_fit_archive/` (processed files are moved here)
  - `work/` (temporary extraction workspace)
- `scripts/`
  - `cli.py` (entrypoint)
  - `db.py` (schema + connection)
  - `garmin/ingest_fit.py` (FIT ingest + HR zones + TRIMP)
  - `zones.py` (time-aware physiology + HR zones lookup)
  - `compute/load_model.py` (daily load aggregation: ATL/CTL EWMA, ramp rate, Foster monotony + strain)

## Setup

Create and activate your virtual environment, then:

```powershell
pip install -r requirements.txt
```

## Usage

Run from the repo root.

### 1) Initialise DB schema

```powershell
python .\scripts\cli.py init-db
```

This also creates the expected directory scaffolding (`db/`, `data/raw/...`, `data/work/`) if it doesn’t already exist.

### 2) Seed initial HR profile + zones (required for zone/TRIMP calculations)

This writes `physiology_history` + `zones_hr_history` rows into the DB.

```powershell
python .\scripts\cli.py seed-hr-zones
```

### 3) Ingest FIT files

Drop files into `data/raw/garmin_fit_inbox/` then run:

```powershell
python .\scripts\cli.py ingest-and-rebuild
```

This ingests new files and immediately rebuilds all derived metrics in one step. If you want to ingest without rebuilding (e.g. you plan to update physiology first), use `fit-ingest` followed by `rebuild-derived` separately.

What ingest currently does:

- Inserts/overwrites `activities`
- Stores device-reported values into `physiology_observed` when present (e.g. VO2max, weight)
- Computes HR time-in-zone into `activity_hr_zone_summary` (LTHR-relative zones)
- Computes Banister HRr TRIMP into `activity_metrics.trimp_total` when HRrest/HRmax exist
- Sets `activity_metrics.load_points = trimp_total` (current transparent definition)

### 4) (Optional) Full rebuild

To reset everything from scratch and replay all FITs:

1. Run the destructive **nuke** (resets DB + restores archived FITs to inbox):

   ```powershell
   python .\scripts\cli.py nuke
   ```

   Follow the printed next steps, or run:

2. Seed HR profile + zones (required for zones/TRIMP):

   ```powershell
   python .\scripts\cli.py seed-hr-zones
   ```

3. Ingest FIT files:

   ```powershell
   python .\scripts\cli.py fit-ingest
   ```

4. (Optional) Rebuild derived metrics:

   ```powershell
   python .\scripts\cli.py rebuild-derived
   ```

This command **does not re-read FIT files**; it only recomputes all derived training-load metrics from the current contents of the database:

- `daily_metrics`: load points, CTL (42-day EWMA), ATL (7-day EWMA), form (CTL − ATL), AC ratio, CTL season best, ramp rate (7-day CTL change), Foster monotony, and Foster strain.
- `activity_metrics.load_points` (re-derived from TRIMP).

It is safe to run any time you adjust physiology/zones or change the load model logic.

If you prefer a one-shot convenience command that chains all of the above:

```powershell
python .\scripts\cli.py full-rebuild
```

### Updating physiology metrics

When a metric like max HR or LTHR changes (for example Garmin revises your estimate, or you retest), record the new value with an effective date:

```powershell
python .\scripts\cli.py update-physiology
```

The CLI shows current values and prompts for Resting HR, Max HR, and LTHR — press Enter to skip any unchanged metric. After updating, run `rebuild-derived` to propagate changes.

### Tweaking HR zones over time

When your HR zones change (for example, after a new test), add a new set of zone definitions for a specific date and sport. This preserves history and lets the engine use the correct zones for each activity date.

Run:

```powershell
python .\scripts\cli.py add-hr-zones
```

The CLI will:

- **Ask for sport** (default: `running`)
- **Ask for effective_from_date** (default: today’s date, `YYYY-MM-DD`)
- **Prompt you for Z1–Z5 lower bounds** as fractions of LTHR (e.g. `0.67`, `0.84`), with sensible defaults you can accept by pressing Enter
- **Optionally prompt for a final Z5 upper cap** (e.g. `1.50`) if you want to adjust how far the last zone extends

Upper bounds for each zone are **derived automatically** so that zones are continuous with no gaps:

- `Z1 = [Z1_lower, Z2_lower)`
- `Z2 = [Z2_lower, Z3_lower)`
- `Z3 = [Z3_lower, Z4_lower)`
- `Z4 = [Z4_lower, Z5_lower)`
- `Z5 = [Z5_lower, Z5_upper_cap]`

Each run writes/overwrites the `zones_hr_history` rows for that `(effective_from_date, sport, zone)` set. Ingest + rebuild will automatically respect the time-aware physiology + zones history.

## Design principles

- **Offline-first / single-user**: everything is local.
- **Deterministic & idempotent**: derived tables are rebuildable; rerunning should reproduce the same results.
- **Transparent physiology-aware logic**: no vendor Training Effect / Recovery Time, etc.

