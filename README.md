# Mnemosyne

A self-hosted personal widget dashboard. Notes, quick-capture inbox, bookmarks, todos (with Asana sync), calendar, and GitHub activity — composable as drag-and-resize widgets on a single dashboard.

Live: https://mnemosyne.avorial.com

## Stack

- FastAPI + Jinja2 + HTMX
- gridstack.js (drag/resize layout)
- SQLite (single file, ZFS-snapshotted)
- Docker Compose, deployed via Portainer on Proxmox

## Layout

```
app/        FastAPI application
  widgets/  one module per widget, auto-discovered
  services/ shared helpers (vault, workspace, http)
worker/     background sync loop
```

## Local development

```bash
cp .env.example .env
# edit .env
docker compose up --build
```

Then open http://localhost:8100.

## Standing rules

- Bump `VERSION` by 0.1 before every commit.
- Never commit secrets. `.gitignore` excludes `.env*`, `secrets/`, `*.db`.
