# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Per-article micro-paywall: public teasers, tiny one-time Stripe fee to unlock each
article, email+password accounts. FastAPI backend + MongoDB (Motor, async) + React
19/Vite frontend; the real code lives in `backend/` and `frontend/`.

**`SPEC.md` is the source of truth** for the product, data model, routes, and build
phases. This file describes how the code works today.

No tests or linters are configured yet; verification is manual (see SPEC.md phases).

## Running

Full stack (Mongo + backend + frontend):

```
docker compose up --build
```

Frontend: http://localhost:3000 · Backend: http://localhost:8000 · Mongo: 27017

Local dev without Docker (Mongo must already be running):

```
# backend — run from backend/ (imports resolve relative to cwd); MONGO_URL comes from root .env
cd backend
uv run uvicorn main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

## Architecture

- The browser calls the backend directly — no Vite proxy. API base URL comes from `VITE_API_URL` (defaults to `http://localhost:8000`) in `frontend/src/api/`.
- CORS in `backend/main.py` is locked to origin `http://localhost:3000`, allows GET/POST/DELETE, and sends credentials (cookies) — frontend fetches to authed endpoints need `credentials: 'include'`.
- Secrets/config live in the root `.env` (gitignored): `backend/main.py` calls `load_dotenv()`, which searches upward from `backend/` and finds it. Real environment variables win over `.env` values (dotenv default `override=False`), so docker-compose's `environment:` entries take precedence in containers.
- Backend pings Mongo and ensures indexes in the FastAPI lifespan (`backend/db/connection.py`) and raises on failure — the app will not start without a reachable `MONGO_URL`.
- One shared Motor client app-wide via `get_db_client()` in `backend/db/connection.py`; routes get the app database via `get_db()` (name from `DB_NAME` env var).
- Data model (full definition in SPEC.md §2): `users`, `sessions`, `articles`, `purchases`. Indexes are created idempotently at startup by `ensure_indexes()` — currently users.email (unique) and sessions.expires_at (TTL); the purchases indexes land in Phase D.

## Conventions

- Backend routes: one module per resource in `backend/routes/`, each exports `router` (an `APIRouter`), registered in `backend/main.py`.
- Frontend API calls: one wrapper module per resource in `frontend/src/api/`.

## Gotchas

- The frontend container runs the Vite **dev server**, not a production build — docker-compose is a dev setup.
- `backend/` is the only uv project (root `.python-version` pins Python for it); run backend commands from inside `backend/`.
- Never put secrets in `VITE_` env vars — Vite bakes them into the public JS bundle.
