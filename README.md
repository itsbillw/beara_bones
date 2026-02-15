# beara_bones

Django-based personal site and playground. Production runs on a **Raspberry Pi 4** with **DietPi OS**, behind NGINX, using **MariaDB**. The site includes a **football data** section: dashboard (points chart + league table) and a pipeline that ingests fixtures from RapidAPI into MinIO, transforms to Parquet/DuckDB, runs Soda 4 contract verification, and builds dbt-style views.

## Local development

1. **Clone and enter the project**

   ```bash
   cd beara_bones
   ```

2. **Create a virtual environment and install dependencies (uv)**

   ```bash
   uv sync
   ```

   This installs all dependencies including dev tools (pytest, ruff, mypy, bandit, etc.).

3. **Configure environment**

   - Copy `.env.example` to `.env` and set at least `DJANGO_SECRET_KEY` (any value is fine for local dev).
   - For local testing you use **SQLite** and **development settings**; no database or `.env` DB vars are required.
   - For the **football pipeline** (ingest, transform) you need `RAPIDAPI_KEY`, and for MinIO: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, and optionally `MINIO_BUCKET`, `MINIO_SECURE`.

4. **Run the dev server**

   ```bash
   make run-dev
   ```

   Or manually:

   ```bash
   cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py runserver
   ```

   Open http://127.0.0.1:8000/

5. **Optional: install pre-commit hooks** (run once per clone so lint, type checks, and tests run on every `git commit`)

   ```bash
   make install-hooks
   ```

## Commands

| Command              | Description                                                               |
| -------------------- | ------------------------------------------------------------------------- |
| `make help`          | List all make targets                                                     |
| `make run-dev`       | Run dev server (SQLite, settings_dev)                                     |
| `make test`          | Run Django tests (home + data apps)                                       |
| `make test-football` | Run football package unit tests (pytest)                                  |
| `make test-all`      | Run Django and football tests                                             |
| `make coverage`      | Run all tests with combined coverage report (Django + football)           |
| `make install-hooks` | Install pre-commit git hooks (run once)                                   |
| `make lint`          | Run all pre-commit checks (ruff, mypy, bandit, prettier, etc.)            |
| `make check`         | Run lint + all tests (use before push)                                    |
| `make ingest`        | Pipeline phase 1: fetch fixtures from RapidAPI → MinIO                    |
| `make transform`     | Pipeline phase 2: MinIO raw JSON → CSV/Parquet                            |
| `make soda-check`    | Pipeline phase 3: Soda 4 contract verification                            |
| `make dbt-build`     | Pipeline phase 4: dbt-duckdb build (in data_modelling/)                   |
| `make pipeline`      | Full pipeline: ingest → transform → DuckDB → Soda → dbt → MariaDB + MinIO |

## Project layout

- **`beara_bones/`** – Django project root (run `manage.py` from here)
  - **`beara_bones/`** – Django config (settings, urls, wsgi, asgi)
  - **`home/`** – main app: landing page, about, static poem, base template and navbar
  - **`data/`** – data app: football dashboard (data page, fragment endpoint, refresh trigger), and `ingest_football` management command
- **`football/`** – pipeline package (ingest, transform, build_views, Soda 4 contracts); not a Django app
- **`data_modelling/`** – dbt-duckdb project (marts, staging, sources)
- **`tests/`** – pytest tests for the `football` package; Django tests live in app `tests.py` modules
- **`/data/`** (repo root) – pipeline output: `data/football/` holds fixtures (CSV, Parquet, DuckDB). Ignored by git via `/data/` in `.gitignore`.

## Data page and pipeline

- **Data page** (`/data`): loads quickly with a shell; the points chart and league table are loaded asynchronously from `/data/fragment`. The fragment is cached (by data file mtime) to avoid recomputing on every request.
- **Refresh**: POST to `/data/refresh` starts the pipeline in the background (ingest → transform → DuckDB → Soda → dbt → MariaDB + MinIO). A lock file prevents overlapping runs.
- **Pipeline**: `make pipeline` (or the refresh button) runs ingest (RapidAPI → MinIO), transform (MinIO → CSV/Parquet), loads into DuckDB, runs Soda 4 contract verification, runs dbt, then loads to MariaDB and uploads processed Parquet to MinIO. The dashboard reads from MariaDB.

## Production (Raspberry Pi 4 / DietPi / MariaDB)

- Use **production settings**: `beara_bones.settings` (default for `manage.py`).
- Set in `.env`: `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS` (comma-separated), and MariaDB vars: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
- The app uses **PyMySQL** to talk to MariaDB (no native MySQL client build required on the Pi).
- SSL is handled by NGINX and Certbot; Django is configured for HTTPS (secure cookies, HSTS, etc.).
- After pulling: run `make deploy` (runs `uv sync`, `migrate`, `collectstatic --noinput --clear`, and `sudo systemctl restart uvicorn`). Override the service with `make deploy SYSTEMCTL_SERVICE=gunicorn` if needed.
