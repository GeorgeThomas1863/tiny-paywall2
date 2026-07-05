# tiny-paywall2

A micropayment article **marketplace**. Any registered user writes articles and sets a
price (1¢–$5.00). Readers fund a wallet with a card via Stripe Checkout, then buy
articles instantly from that balance — no card at purchase time, which is what makes
penny prices possible. Authors earn 80% of every sale into a separate earnings
balance, withdrawable from $10.00 via manual payouts (request → owner pays externally
→ admin marks paid).

- FastAPI + Motor (async MongoDB) backend · React 19 / Vite frontend
- All money is integer cents, moved only inside Mongo transactions with an
  append-only ledger
- `SPEC.md` is the full design; `CLAUDE.md` describes how the code works today

## Quick start (Docker)

```
docker compose up --build
```

Frontend http://localhost:3000 · backend http://localhost:8000 · Mongo on 27017
(configured as a single-node replica set automatically). This is a **dev** setup —
the frontend container runs the Vite dev server, not a production build. You still
need Stripe keys in the root `.env` (see below) for top-ups to work.

## Local dev without Docker

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+, a local MongoDB running as
a single-node replica set (one-time setup below), and the Stripe CLI.

1. Create a root `.env` (gitignored) — see the variable table below.
2. Backend (from `backend/` — imports resolve relative to cwd):
   ```
   cd backend
   uv run python main.py        # uvicorn --reload on BACKEND_PORT (default 8000)
   ```
3. Frontend:
   ```
   cd frontend
   npm install
   npm run dev                  # Vite on FRONTEND_PORT (default 3000)
   ```
4. While developing payments, run the Stripe webhook forwarder (see Stripe section).

A root `.env.local` (also gitignored) is loaded before `.env` and wins — useful for
machine-specific overrides like ports.

## Environment variables (root `.env`)

| Var | Notes |
|---|---|
| `MONGO_URI` | Mongo connection string; append `directConnection=true` (single-member replica set) |
| `DB_NAME` | app database name (tests use `<DB_NAME>_test`) |
| `BACKEND_PORT` | dev port for uvicorn; default 8000 |
| `FRONTEND_PORT` | dev port for Vite; default 3000 |
| `FRONTEND_URL` | optional override — CORS origin + Stripe return URLs; derived from `FRONTEND_PORT` when unset |
| `STRIPE_SECRET_KEY` | `sk_test_…` until launch |
| `STRIPE_WEBHOOK_SECRET` | printed by `stripe listen` (dev) / dashboard endpoint (prod) |
| `VITE_API_URL` | optional override — frontend's API base; derived from `BACKEND_PORT` when unset |

Containers don't read the root `.env` for ports — docker-compose passes its own
environment, which wins over `.env` values.

## Mongo replica set (one-time, required)

Money moves in multi-document transactions, which MongoDB only allows on a replica
set — a **single-node** replica set is sufficient. The backend refuses to start
without transaction support (startup probe in `db/connection.py`).

Local Windows service **with authentication enabled** (keyfile is mandatory —
MongoDB requires internal auth when authorization + replication are both on):

1. Generate a keyfile (Git Bash):
   ```
   openssl rand -base64 756 > /c/ProgramData/MongoDB/mongo-keyfile
   ```
2. Edit `mongod.cfg` (usually `C:\Program Files\MongoDB\Server\<version>\bin\mongod.cfg`) — add
   `replication.replSetName` and `security.keyFile` (merge `keyFile` under the
   existing `security:` block if one exists):
   ```yaml
   replication:
     replSetName: rs0
   security:
     authorization: enabled
     keyFile: C:\ProgramData\MongoDB\mongo-keyfile
   ```
3. Restart the service from an **elevated** terminal:
   ```
   net stop MongoDB && net start MongoDB
   ```
4. Initiate the replica set once. The member `host` is the address the set
   *advertises* to every client during driver discovery — pick one all clients can
   reach. This machine binds `127.0.0.1,10.0.0.252` and other LAN machines connect
   to it, so we advertise the LAN IP (currently configured):
   ```
   mongosh mongodb://localhost:27017 --eval "rs.initiate({_id: 'rs0', members: [{_id: 0, host: '10.0.0.252:27017'}]})"
   ```
   Single-machine setups would use `localhost:27017` instead. To change it later:
   `cfg = rs.conf(); cfg.members[0].host = '<new>:27017'; rs.reconfig(cfg)`.
   If the LAN IP ever changes, update both `bindIp` in `mongod.cfg` and this
   advertised host.
5. Append `directConnection=true` to `MONGO_URI` in the root `.env`:
   `mongodb://...@localhost:27017/tiny?directConnection=true`

Reverting: remove the two config lines and restart the service.

## Stripe (test mode)

1. Create a free Stripe account; grab the **test** secret key (`sk_test_…`) from
   Developers → API keys → put it in `.env` as `STRIPE_SECRET_KEY`.
2. Install the [Stripe CLI](https://stripe.com/docs/stripe-cli) and run `stripe login` once.
3. While developing payments, run the webhook forwarder (it prints the
   `whsec_…` secret — put it in `.env` as `STRIPE_WEBHOOK_SECRET`). Use your
   `BACKEND_PORT`:
   ```
   stripe listen --forward-to localhost:8000/stripe/webhook
   ```
4. Test card: `4242 4242 4242 4242`, any future expiry, any CVC.

The webhook is the **only** code path that credits wallets — top-ups will not land
without the forwarder running.

## Admin bootstrap (one-time)

Register an account through the UI, then flag it as admin directly in Mongo:

```
mongosh "<your MONGO_URI>" --eval 'db.users.updateOne({email: "you@example.com"}, {$set: {is_admin: true}})'
```

The flag is read live on each request — no re-login needed. Admins moderate articles
and resolve payout requests at `/admin`.

## Payouts (manual in v1)

Authors request a payout from the Account page once earnings reach $10.00 — the full
balance is reserved and the request appears in the admin queue. The owner pays them
outside the app (e.g. PayPal) and marks the request **paid**; **reject** returns the
funds to the author's earnings.

## Tests

Backend behavior is covered by a pytest suite (written test-first, SPEC §8):

```
cd backend
uv run pytest
```

Requires the same local Mongo replica set; the suite runs against `<DB_NAME>_test`
and cleans it between tests. Frontend/UI is verified via the manual checklists in
SPEC.md §9.
