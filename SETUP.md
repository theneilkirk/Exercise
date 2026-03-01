# Setup & administration

This document is for people installing, configuring, or maintaining the training engine on a machine (rather than just using it to manage their data).

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

## 1. Install dependencies

From the repo root, with a Python 3.11 environment activated:

```powershell
pip install -r requirements.txt
```

## 2. Create DB + folder scaffolding

This will:

- Create `db/` and `data/` subfolders (including `data/raw/garmin_fit_inbox/`, `data/raw/garmin_fit_archive/`, `data/work/`) if they do not exist.
- Create the SQLite database at `db/training.db` with the expected schema.

Run:

```powershell
python .\scripts\cli.py init-db
```

## 3. Where data lives

- **Database**: `db/training.db` — all derived tables, activities, and physiology data.
- **FIT inbox**: `data/raw/garmin_fit_inbox/` — drop new `.fit` or `.zip` files here.
- **FIT archive**: `data/raw/garmin_fit_archive/` — processed files are moved here.
- **Workspace**: `data/work/` — temporary extraction workspace.

The database and raw data directories are intentionally ignored by Git, so they stay local to the machine.

## 4. Admin / maintenance commands

These commands are intended for people operating the system (they can be exposed to users with appropriate warnings).

### Nuke (destructive reset)

Resets the database and restores all archived FITs to the inbox, so you can replay everything from scratch:

```powershell
python .\scripts\cli.py nuke
```

Follow the printed instructions after `nuke` completes. Typically you will:

1. Re-seed HR profile and zones.
2. Re-ingest FIT files.
3. (Optionally) Rebuild derived metrics.

### Full rebuild (convenience)

Runs a full deterministic rebuild of all derived training-load metrics from the current database contents:

```powershell
python .\scripts\cli.py rebuild-derived
```

This command **does not re-read FIT files**; it only recomputes all derived training-load metrics from the current contents of the database: `daily_metrics` (load points, CTL, ATL, form, AC ratio, CTL season best, ramp rate, Foster monotony, Foster strain) and `activity_metrics.load_points`. It is safe to run any time you adjust physiology/zones or change the load model logic and want the derived tables to be refreshed.

If you prefer a one-shot convenience command that chains the main steps (reset, seed, ingest, rebuild), use:

```powershell
python .\scripts\cli.py full-rebuild
```

Refer to `DATA_MANAGEMENT.md` for user-facing, step-by-step data workflows.

