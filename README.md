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
  - `compute/load_model.py` (daily load aggregation + ATL/CTL EWMA)

## Setup

Create and activate your virtual environment (you said you’ll do this), then:

```powershell
pip install -r requirements.txt
```

## Usage

Run from the repo root.

### 1) Initialise DB schema

```powershell
python .\scripts\cli.py init-db
```

### 2) Seed initial HR profile + zones (required for zone/TRIMP calculations)

This writes `physiology_history` + `zones_hr_history` rows into the DB.

```powershell
python .\scripts\cli.py set_initial_hr_zones
```

### 3) Ingest FIT files

Drop files into `data/raw/garmin_fit_inbox/` then run:

```powershell
python .\scripts\cli.py fit-ingest
```

What ingest currently does:

- Inserts/overwrites `activities`
- Stores device-reported values into `physiology_observed` when present (e.g. VO2max, weight)
- Computes HR time-in-zone into `activity_hr_zone_summary` (LTHR-relative zones)
- Computes Banister HRr TRIMP into `activity_metrics.trimp_total` when HRrest/HRmax exist
- Sets `activity_metrics.load_points = trimp_total` (current transparent definition)

### 4) (Optional) Full rebuild

There is a destructive “nuclear rebuild” command that wipes `db/training.db`, restores archived FITs back to the inbox, then rebuilds everything.

```powershell
python .\scripts\cli.py nuke
```

## Design principles

- **Offline-first / single-user**: everything is local.
- **Deterministic & idempotent**: derived tables are rebuildable; rerunning should reproduce the same results.
- **Transparent physiology-aware logic**: no vendor Training Effect / Recovery Time, etc.

