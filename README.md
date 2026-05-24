# beara_bones

Django-based personal site and playground. Production runs on a **Raspberry Pi 4** with **DietPi OS**, behind NGINX, using **MariaDB**. The site includes a **football data** section (HTMX + Plotly.js dashboard + ingest pipeline), and a **learning vault** (invite-only document library with PDF/markdown viewing).

## Quick start (local dev)

1. **Clone and enter the repo**

   ```bash
   cd beara_bones
   ```

2. **Install dependencies** (uses [uv](https://github.com/astral-sh/uv))

   ```bash
   uv sync
   ```

3. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Set at least `DJANGO_SECRET_KEY` (any value is fine for local dev). Local dev uses **SQLite** via `beara_bones.settings_dev`; no database vars are required.

4. **Run the dev server**

   ```bash
   make run-dev
   ```

   Open http://127.0.0.1:8000/

5. **Optional: pre-commit hooks** (lint + tests on every commit)

   ```bash
   make install-hooks
   ```

## Make targets

Run `make help` for the full list. Common targets:

| Command              | Description                                    |
| -------------------- | ---------------------------------------------- |
| `make run-dev`       | Dev server (SQLite, `settings_dev`)            |
| `make test`          | Django tests (home, data, learning)            |
| `make test-football` | Pytest for the `football` package              |
| `make test-all`      | Django + football tests                        |
| `make coverage`      | Combined coverage report                       |
| `make lint`          | Pre-commit checks (ruff, mypy, bandit, etc.)   |
| `make check`         | Lint + all tests (run before push)             |
| `make deploy`        | Production deploy after `git pull` (see below) |

### Football pipeline

| Command                 | Description                                                               |
| ----------------------- | ------------------------------------------------------------------------- |
| `make ingest`           | Phase 1: RapidAPI → MinIO (raw JSON)                                      |
| `make transform`        | Phase 2: MinIO → CSV/Parquet                                              |
| `make soda-check`       | Phase 3: Soda 4 contract verification                                     |
| `make dbt-build`        | Phase 4: dbt-duckdb build (`data_modelling/`)                             |
| `make pipeline`         | Full pipeline: ingest → transform → DuckDB → Soda → dbt → MariaDB + MinIO |
| `make pipeline-all`     | Pipeline for every League×Season in Django Admin                          |
| `make rebuild-football` | Rebuild MariaDB from MinIO (no API calls)                                 |

Pipeline output under repo root `/data/football/` is gitignored.

## Architecture

```
beara_bones/          Django project (run manage.py from beara_bones/)
  home/               Landing, about, base template, theme
  data/               Football dashboard (/data), pipeline admin
  learning/           Invite-only vault (/learning)
football/             Standalone pipeline package (not a Django app)
data_modelling/       dbt-duckdb project
tests/                Pytest for football/
```

**Request flow (production):** NGINX → Uvicorn/Gunicorn → Django. Static files via WhiteNoise. The football dashboard at `/data` uses Django templates, HTMX, and Plotly.js (no iframe). Learning documents live in MinIO (production) or `MEDIA_ROOT/learning/` (local dev without MinIO).

## Apps

### Home (`/`)

Landing page, about, and static content. Provides the shared **base template** (Bootstrap navbar, footer, theme toggle).

### Data (`/data`)

- **Dashboard:** league/season dropdowns (HTMX), cumulative points chart (Plotly.js), HTML standings table with team crests.
- **Refresh:** staff can POST to `/data/refresh` to start the pipeline in the background. A lock file prevents overlapping runs.
- **Crests:** `/data/crest/<team_id>/` proxies PNG crests from MinIO.
- **Admin:** pipeline control views for staff (`/data/admin/pipeline/`).

Dashboard figures are cached in Django’s file cache (`FOOTBALL_DASHBOARD_CACHE_TIMEOUT`, default 600s). The pipeline bumps a cache version on success so stale charts are not served after refresh.

### Learning (`/learning`)

Invite-only vault: per-user directory trees, markdown notes with wikilinks/backlinks, PDF viewing with progress, zip import/export, search and filters. Requires a valid `LearningInvite` to sign up.

## Theme system

Light/dark theme is shared across Django pages and the football dashboard.

1. **Inline script** in `home/base.html` runs before paint: reads `localStorage` key `itsbillw-theme`, falls back to `prefers-color-scheme`, sets `document.documentElement.dataset.theme`, and writes cookie `itsbillw-theme`.
2. **`home/js/theme.js`** wires the navbar toggle: updates `localStorage`, cookie, and `data-theme` on `<html>`.
3. **CSS** in `home/css/base_style.css` (and app-specific styles) use `[data-theme="light"]` / `[data-theme="dark"]` selectors.
4. **Dashboard** reads the same cookie server-side to pick Plotly template (`plotly_white` / `plotly_dark`) and re-fetches chart data on theme change via HTMX.

Theme preference persists across visits via cookie + localStorage.

## Environment variables

See `.env.example` for the full list. Summary:

| Variable                                                  | Purpose                                    |
| --------------------------------------------------------- | ------------------------------------------ |
| `DJANGO_SECRET_KEY`                                       | Required in all environments               |
| `ALLOWED_HOSTS`                                           | Comma-separated hosts (production)         |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MariaDB (production; dev uses SQLite)      |
| `RAPIDAPI_KEY`                                            | Football ingest (RapidAPI)                 |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`  | MinIO for pipeline + learning storage      |
| `MINIO_BUCKET`                                            | Football bucket (default `football`)       |
| `MINIO_LEARNING_BUCKET`                                   | Learning vault bucket (default `learning`) |
| `MINIO_SECURE`                                            | `true`/`false` for HTTPS to MinIO          |
| `LEARNING_MAX_UPLOAD_MB`                                  | Upload size limit (default 25)             |
| `LEARNING_INVITE_EXPIRY_DAYS`                             | Invite TTL (default 7)                     |

## Testing

```bash
make test-all      # Django + football
make coverage      # Combined coverage report
make check         # lint + tests
```

- **Django tests:** `beara_bones/*/tests.py` (home, data, learning)
- **Football tests:** `tests/test_football.py` (pytest)

Coverage omits migrations, settings entrypoints, and test modules. Run from repo root; Django tests use `beara_bones.settings_dev` and an in-memory/SQLite test database.

## Production deploy (Raspberry Pi / DietPi / MariaDB)

- Settings module: `beara_bones.settings.prod` (WSGI/ASGI default; `make deploy` uses this).
- PyMySQL driver — no native MySQL client build required on the Pi.
- SSL terminated at NGINX (Certbot installed via system packages); Django sets secure cookies and HSTS.

After pulling changes on the server:

```bash
make deploy
```

This runs `uv sync`, `migrate`, `collectstatic --noinput --clear`, and `sudo systemctl restart uvicorn`. Override the service name with `make deploy SYSTEMCTL_SERVICE=gunicorn` if needed.

## Project layout (detail)

- **`beara_bones/beara_bones/`** — Django config (`settings/`, `settings_dev` shim, `urls`, WSGI/ASGI)
- **`beara_bones/data/`** — Football models, HTMX dashboard, views, management commands
- **`beara_bones/learning/`** — Vault models, storage abstraction, markdown/PDF views
- **`football/`** — Ingest, transform, Soda contracts, DuckDB views, pipeline orchestration
- **`data_modelling/`** — dbt sources, staging, marts
