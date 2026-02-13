# beara_bones

Django-based personal site and playground. Production runs on a **Raspberry Pi 4** with **DietPi OS**, behind NGINX, using **MariaDB**.

## Local development

1. **Clone and enter the project**
   ```bash
   cd beara_bones
   ```

2. **Create a virtual environment and install dependencies (uv)**
   ```bash
   uv venv
   source .venv/bin/activate   # Linux/macOS
   uv sync
   ```

3. **Configure environment**
   - Copy `.env.example` to `.env` and set at least `DJANGO_SECRET_KEY` (any value is fine for local dev).
   - For local testing you use **SQLite** and **development settings**; no database or `.env` DB vars are required.

4. **Run the dev server**
   ```bash
   make run-dev
   ```
   Or manually:
   ```bash
   cd beara_bones && DJANGO_SETTINGS_MODULE=beara_bones.settings_dev uv run python manage.py runserver
   ```
   Open http://127.0.0.1:8000/

5. **Run tests**
   ```bash
   make test
   ```

## Production (Raspberry Pi 4 / DietPi / MariaDB)

- Use **production settings**: `beara_bones.settings` (default for `manage.py`).
- Set in `.env`: `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS` (comma-separated), and MariaDB vars: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
- The app uses **PyMySQL** to talk to MariaDB (no native MySQL client build required on the Pi).
- SSL is handled by NGINX and Certbot; Django is configured for HTTPS (secure cookies, HSTS, etc.).

## Project layout

- `beara_bones/` – Django project root (run `manage.py` from here)
  - `beara_bones/` – Django config (settings, urls, wsgi, asgi)
  - `home/` – main app (views, templates, static)

## Commands

| Command       | Description                          |
|---------------|--------------------------------------|
| `make run-dev`| Run dev server (SQLite, settings_dev)|
| `make test`   | Run Django tests                     |
| `make help`   | List all make targets                |
