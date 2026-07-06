# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Micropayment article marketplace: any user writes articles and sets a price (1¢–$5);
readers fund a wallet via Stripe Checkout and buy articles from the balance; authors
earn 80% per sale, withdrawable via manual payouts. FastAPI backend + MongoDB (Motor,
async) + React 19/Vite frontend; the real code lives in `backend/` and `frontend/`.

**`SPEC.md` is the source of truth** for the product, data model, routes, and build
phases. This file describes how the code works today.

Development is **test-driven** (SPEC.md §8): backend behavior gets a failing pytest
test before implementation — suite in `backend/tests/`, run with `uv run pytest` from
`backend/` (requires local Mongo). Frontend/UI is verified via the manual checks in
SPEC.md §9 phases. No linters configured.

## Running

Full stack (Mongo + backend + frontend):

```
docker compose up --build
```

In containers: frontend http://localhost:3000 · backend http://localhost:8000 · Mongo 27017.

Local dev without Docker (Mongo must already be running):

```
# backend — run from backend/ (imports resolve relative to cwd); config comes from root .env
cd backend
uv run python main.py        # uvicorn with --reload, port from BACKEND_PORT (default 8000)

# frontend
cd frontend
npm install
npm run dev                  # Vite, port from root .env FRONTEND_PORT (default 3000)
```

Dev ports live in the root `.env` (`BACKEND_PORT`/`FRONTEND_PORT`); the CORS origin and
the frontend's API base URL are derived from them automatically (`backend/config.py`,
`frontend/vite.config.js`), so changing a port is a one-line edit + server restart.
Containers don't read the root `.env` and keep the 8000/3000 defaults.

## Architecture

- The browser calls the backend directly — no Vite proxy. API base URL comes from `VITE_API_URL` (defaults to `http://localhost:8000`) in `frontend/src/api/`.
- CORS in `backend/main.py` is locked to the `FRONTEND_URL` origin (default `http://localhost:3000`), allows GET/POST/PUT/DELETE, and sends credentials (cookies) — all frontend fetches go through `frontend/src/api/request.js`, which sets `credentials: 'include'`.
- Auth: server-side sessions (`auth/security.py`), cookie `session` = raw token, `require_auth`/`require_admin`/`optional_auth` dependencies in `auth/deps.py`, in-memory login rate limiting in `auth/rate_limit.py` (single-process only).
- Secrets/config live in the root `.env` (gitignored): `backend/main.py` calls `load_dotenv()`, which searches upward from `backend/` and finds it. Real environment variables win over `.env` values (dotenv default `override=False`), so docker-compose's `environment:` entries take precedence in containers.
- Backend pings Mongo and ensures indexes in the FastAPI lifespan (`backend/db/connection.py`) and raises on failure — the app will not start without a reachable `MONGO_URI`.
- One shared Motor client app-wide via `get_db_client()` in `backend/db/connection.py`; routes get the app database via `get_db()` (name from `DB_NAME` env var).
- Data model (full definition in SPEC.md §2–3): `users`, `sessions`, `articles`, `purchases`, `ledger`, `payout_requests`. All money is integer cents; balances change only inside Mongo transactions in `money/operations.py` (SPEC §2.4) — its four operations are `credit_topup`, `execute_purchase`, `reserve_payout`, `return_payout`. Indexes are created idempotently at startup by `ensure_indexes()`: users.email (unique), users.display_name (unique, case-insensitive collation), sessions.expires_at (TTL), articles.author_id, purchases (buyer_id+article_id unique; author_id; article_id), ledger (user_id; stripe_session_id partial unique for webhook idempotency), payout_requests.user_id.
- Votes (SPEC §4.4 `routes/votes.py`): purchasers up/downvote articles Reddit-style via `PUT /articles/{id}/vote` (`value: 1 | -1 | 0`, 0 clears). The vote lives as an optional `vote` field on the buyer's `purchases` doc — the purchase row is the eligibility check (no purchase → 403; authors/admins excluded automatically). Scores are aggregated at read time in `routes/articles.py` (`aggregate_scores`); `score` is on every public teaser/detail (not the admin moderation list, which aggregates nothing), `my_vote` (1/-1/0, or null for non-buyers) on detail only. Public teasers/detail also carry `purchased` (bought it, vs `owned` which adds the author/admin grant) — the frontend's "My library" filter.
- Payouts are manual (SPEC §2.4): `POST /payouts/request` reserves the full earnings balance (≥$10) into a `payout_requests` doc; admin resolves via `PUT /payouts/{id}` — "paid" flips status only (money already left on reserve), "rejected" returns the funds with a `payout_return` ledger entry.
- **Mongo must run as a (single-node) replica set** — transactions require it; startup probes for it and fails loudly (`verify_transactions_supported`). Local setup is documented in README; docker-compose configures it automatically.
- Stripe touches exactly two places: `routes/wallet.py` creates Checkout Sessions for top-ups (sync SDK, run in threadpool) and `routes/stripe_webhook.py` credits wallets after signature verification — the only code path that creates spendable money. Purchases are internal ledger moves, no Stripe. The Motor client is `tz_aware=True` — datetimes read back from Mongo are timezone-aware UTC.

## Conventions

- Backend routes: one module per resource in `backend/routes/`, each exports `router` (an `APIRouter`), registered in `backend/main.py`.
- Frontend API calls: one wrapper module per resource in `frontend/src/api/`.

## Gotchas

- The frontend container runs the Vite **dev server**, not a production build — docker-compose is a dev setup.
- `backend/` is the only uv project (root `.python-version` pins Python for it); run backend commands from inside `backend/`.
- Never put secrets in `VITE_` env vars — Vite bakes them into the public JS bundle.
