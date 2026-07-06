# tiny-paywall2 — Full Specification

A micropayment article **marketplace**. Any registered user can write articles and set
their own price (1¢–$5.00). Readers fund a wallet with a card via Stripe, then buy
articles instantly from that balance — no card involved at purchase time. Authors earn
80% of every sale; the platform keeps 20%. Teasers of every published article are
public; bodies are paid.

This document is the source of truth: what we are building, exactly how it works, and
the ordered steps to build it. `CLAUDE.md` describes how the code works *today*; this
file describes the target and the path. **We build test-driven** — the testing
strategy is §8, the build phases are §9; follow them in order.

Built with fable

---

## 1. Product definition

**The reader's story:**

1. A visitor sees a list of every published article: title, summary (teaser), price,
   author name. Fully public.
2. Opening an article shows the teaser plus a paywall: "Unlock for 25¢".
3. To buy, they need an account (email + password + display name) and wallet funds.
   They top up $5 / $10 / $20 via Stripe Checkout — that is the only moment a card
   appears anywhere.
4. Clicking Unlock debits their wallet and shows the body instantly. Bought articles
   stay readable on that account for as long as they remain published — unpublishing
   hides an article from everyone but its author and admins, buyers included.
5. A buyer can upvote or downvote any article they purchased — Reddit-style, at any
   time after purchase, changeable or clearable forever. Every article shows its net
   score (upvotes − downvotes) publicly; no votes yet displays as 0.

**The author's story:**

1. Any registered user can write articles: draft → edit → publish → (unpublish/edit/
   delete). Drafts are visible only to their author (and admin).
2. The author sets the price per article: 1¢ minimum, $5.00 maximum.
3. Each sale credits the author 80% of the price, immediately, into an earnings
   balance (separate from their spendable wallet).
4. When earnings reach $10.00 the author can request a payout, telling us where to
   send the money (free-text destination, e.g. a PayPal email). The platform owner
   pays them outside the app and marks the request paid.

**The admin's story (you):** admin account(s) can see, edit, unpublish, and delete any
article; see and resolve payout requests (paid / rejected). Admin is a flag set
directly in the DB, once.

**Locked decisions:**

| Decision | Choice |
|---|---|
| Stack | FastAPI + Motor (async Mongo) backend, React 19/Vite frontend |
| Payments | Stripe Checkout for wallet top-ups only; purchases are internal ledger moves |
| Why a wallet | Cards cannot process sub-50¢ charges (researched 2026-07: Stripe min $0.50; PayPal micro rate 4.99%+9¢). Wallet is required for penny prices regardless of processor. |
| Top-up amounts | Presets: $5 / $10 / $20. No custom amounts in v1. |
| Revenue split | Author gets 80% of sale price (round half-up in author's favor); platform's 20% absorbs Stripe's top-up fees |
| Payouts | v1 is manual: request → owner pays externally → admin marks paid. Ledger is built properly so Stripe Connect / PayPal Payouts can automate this later without redesign. |
| Balances | `wallet_cents` (spendable) and `earnings_cents` (withdrawable) are separate. Earnings are not spendable on articles in v1. |
| Accounts | Email + password + unique display name (changeable). Server-side sessions in Mongo, 30-day cookie. |
| Authoring | Every registered user; no approval gate. Admin moderates after the fact. |
| Prices | 1–500 cents, set per article by the author. Past buyers keep access when price or content changes. |
| Content format | Plain text bodies, rendered with preserved line breaks. |
| Votes | Purchasers only (author/admin excluded — no purchase, no vote). One vote per buyer per article, `1` or `-1`, set/changed/cleared anytime. Stored as an optional `vote` field on the purchase doc — the unique `(buyer_id, article_id)` index and the purchase row itself enforce eligibility and one-vote-per-buyer for free. Score = `sum(vote)`, aggregated at read time (no denormalized counters → no drift). |
| Consistency | Mongo multi-document **transactions** for all money movement → Mongo must run as a single-node replica set (see §7). |
| Testing | **TDD.** Backend behavior is specified by a pytest suite written test-first, step by step, as each feature is built (§8). Frontend is verified by manual phase checklists (the logic lives in the backend). |

**Future mechanisms (design for, do not build):** additional payment rails (Lightning/
OpenNode, x402/stablecoins) would plug in as either extra top-up methods or direct
per-article payment — the ledger doesn't care where credit comes from. Automated
payouts replace the manual step only.

**Non-goals for v1** (do not build speculatively):

- Password reset / any email sending
- Spending earnings on articles, transfers between users
- In-app refunds of wallet balance (rare case → handled manually via Stripe dashboard + admin ledger note)
- Subscriptions, bundles, follows, comments, search, tags, pagination
- Rich text / markdown editor or rendering
- Author public profile pages (byline shows display name only)
- Stripe Connect / automated payouts
- Production deployment config

---

## 2. The money model

All amounts are **integer cents**, everywhere, always. No floats touch money.

### 2.1 Balances

Each user document carries two denormalized balances, updated only inside
transactions that also write ledger entries:

- `wallet_cents` — prepaid credit, spendable on articles. Increases on top-up,
  decreases on purchase. Never negative (enforced by conditional update, §2.4).
- `earnings_cents` — money earned from sales, withdrawable. Increases on each sale,
  decreases when a payout request reserves it.

Platform revenue is not stored as a balance; it is derivable:
`sum(purchases.platform_cents)`.

### 2.2 The split

For a sale at `price_cents`:

```
author_cents   = (price_cents * 80 + 50) // 100     # round half-up, author-favored
platform_cents = price_cents - author_cents
```

Examples: 1¢ → author 1, platform 0 · 3¢ → author 2, platform 1 ·
25¢ → author 20, platform 5 · 500¢ → author 400, platform 100.
At penny prices the platform share can be zero; that is accepted and intentional
(authors must never round down to zero).

### 2.3 The ledger

Every balance change writes a ledger entry in the same transaction. The ledger is
append-only — entries are never updated or deleted.

```
ledger {
  _id:               ObjectId,
  user_id:           ObjectId,       // whose balance moved
  balance:           "wallet" | "earnings",
  amount_cents:      int,            // signed: +credit, -debit
  type:              "topup" | "purchase" | "sale" | "payout_reserve" | "payout_return",
  stripe_session_id: str,            // topup only; partial unique index
  purchase_id:       ObjectId,       // purchase/sale only
  payout_request_id: ObjectId,       // payout_reserve/payout_return only
  created_at:        datetime        // UTC
}
```

Invariant: for any user, `sum(ledger amounts per balance) == stored balance`. Any
discrepancy is a bug; the ledger wins.

### 2.4 Money operations (the only three places balances change)

**Top-up credit** — in the Stripe webhook (§4.5), single transaction:
1. Insert ledger `topup` entry (`stripe_session_id` from the event). The partial
   unique index makes webhook replays throw `DuplicateKeyError` → catch, return 200.
2. `$inc` user's `wallet_cents` by the amount.

**Purchase** — in `POST /purchases` (§4.4), single transaction:
1. Conditional debit: `find_one_and_update({_id: buyer, wallet_cents: {$gte: price}},
   {$inc: {wallet_cents: -price}}, session=s)`. No match → abort → 402 "insufficient
   funds" (frontend offers top-up).
2. Insert `purchases` doc. Unique `(buyer_id, article_id)` index → `DuplicateKeyError`
   → abort → "already owned" (double-click safe).
3. `$inc` author's `earnings_cents` by `author_cents`.
4. Insert two ledger entries: buyer `purchase` (−price, wallet), author `sale`
   (+author_cents, earnings).

**Payout reserve / return** — request debits `earnings_cents` by the full balance and
inserts a `payout_reserve` ledger entry (transaction). Admin "paid" only flips request
status (money already left the balance). Admin "rejected" credits it back with a
`payout_return` entry (transaction).

Guards checked before every purchase transaction: article exists & published → buyer
isn't the author (an author reads their own article free; buying it would be
self-dealing) → not already owned (fast path; the unique index is the real guarantee).

---

## 3. Data model (Mongo, database name from `DB_NAME`)

### users
```
{
  _id:            ObjectId,
  email:          str,       // lowercase+trimmed; unique index
  display_name:   str,       // public byline; unique index (case-insensitive via
                             // collation strength 2); changeable; 1–40 chars
  password_hash:  str,       // bcrypt
  is_admin:       bool,      // default false; set manually in DB
  wallet_cents:   int,       // default 0
  earnings_cents: int,       // default 0
  created_at:     datetime
}
```

### sessions
```
{
  _id:         str,          // the token itself: secrets.token_urlsafe(32)
  user_id:     ObjectId,
  created_at:  datetime,
  expires_at:  datetime      // TTL index
}
```
30-day lifetime. Cookie `session`: raw token, `httpOnly`, `sameSite=lax`, `secure`
only in production.

### articles
```
{
  _id:          ObjectId,
  author_id:    ObjectId,
  title:        str,         // 1–200 chars
  summary:      str,         // 1–1000 chars; always public
  body:         str,         // non-empty; the paid content — never serialized unless entitled
  price_cents:  int,         // 1–500
  status:       "draft" | "published",
  created_at:   datetime,
  updated_at:   datetime
}
```

### purchases
```
{
  _id:             ObjectId,
  buyer_id:        ObjectId,
  article_id:      ObjectId,
  author_id:       ObjectId,   // denormalized for earnings queries
  price_cents:     int,        // price at moment of sale
  author_cents:    int,
  platform_cents:  int,
  vote:            1 | -1,     // optional — absent until the buyer votes; cleared via $unset
  created_at:      datetime
}
```

### ledger — see §2.3

### payout_requests
```
{
  _id:          ObjectId,
  user_id:      ObjectId,
  amount_cents: int,           // full earnings balance at request time
  destination:  str,           // free text: "PayPal: me@example.com"; 1–200 chars
  status:       "requested" | "paid" | "rejected",
  created_at:   datetime,
  resolved_at:  datetime | null
}
```

### Indexes (all in `ensure_indexes()`, created idempotently at startup)

| Collection | Index | Why |
|---|---|---|
| users | `email` unique | duplicate registration rejected by DB |
| users | `display_name` unique, collation `{locale:"en", strength:2}` | unique bylines, case-insensitive |
| sessions | `expires_at` TTL (expireAfterSeconds=0) | auto session expiry |
| articles | `author_id` | "my articles" queries |
| purchases | `(buyer_id, article_id)` unique | can't double-own; purchase idempotency |
| purchases | `author_id` | per-author sales stats |
| purchases | `article_id` | score aggregation |
| ledger | `user_id` | history queries |
| ledger | `stripe_session_id` unique, partial (field exists) | webhook replay idempotency |
| payout_requests | `user_id` | "my payouts" queries |

**Entitlement rule (single helper, used everywhere):** a user may read an article's
body iff they purchased it, **or** they are its author, **or** they are admin.

---

## 4. Backend

### 4.1 Layout

```
backend/
  main.py               # assembly only: dotenv, CORS, routers, lifespan
  db/
    connection.py       # client, get_db(), verify_db_connection(), ensure_indexes()
  auth/
    security.py         # hash_password, verify_password, create_session, destroy_session
    deps.py             # optional_auth, require_auth, require_admin (FastAPI dependencies)
    rate_limit.py       # in-memory IP limiter (10 fails / 15 min), ported from v1
  money/
    operations.py       # credit_topup, execute_purchase, reserve_payout, return_payout
                        # — the ONLY module that changes balances; all transactional
  routes/
    auth.py             # register / login / logout / me
    articles.py         # public list/read + author CRUD + admin moderation
    wallet.py           # top-up checkout + history
    purchases.py        # buy an article
    votes.py            # purchaser up/downvotes on articles
    payouts.py          # request + mine + admin queue/resolve
    stripe_webhook.py   # POST /stripe/webhook
```

One module per resource (project convention). Route handlers are orchestrators: guard
clauses, then named helper calls — no inline money logic anywhere outside
`money/operations.py`.

### 4.2 Response conventions

- Queries (GET) return data. Not found → 404. Malformed ObjectId → 404 (helper:
  parse-or-404).
- Operations (POST/PUT/DELETE) return `{success, message}` + operation-specific fields.
- Expected failures → `HTTPException(status, detail)`: 401 no/bad session, 402
  insufficient funds, 403 not yours/not admin, 404 missing, 409 duplicate
  (email/display name/already owned), 422 validation, 429 rate-limited.
- Every Mongo/Stripe call sits in try/except with logging that names the operation and
  ids involved. Unexpected exceptions → generic 500 (no internals leaked).

### 4.3 Auth (`routes/auth.py`)

| Route | Auth | Behavior |
|---|---|---|
| `POST /auth/register` | public, rate-limited | Body: email, password (≥8), display_name (1–40, trimmed). Normalize email. Insert (dup email/name → 409 naming which). Create session + cookie. |
| `POST /auth/login` | public, rate-limited | Identical error for unknown email vs wrong password. Failure → 401 + record attempt. Success → session + cookie, clear attempts. |
| `POST /auth/logout` | session | Delete session doc, clear cookie. |
| `GET /auth/me` | session | `{email, display_name, is_admin, wallet_cents, earnings_cents}` |
| `PUT /auth/me` | session | Change display_name only (same validation; dup → 409). |

### 4.4 Articles, wallet, purchases, payouts

**`routes/articles.py`**

| Route | Auth | Behavior |
|---|---|---|
| `GET /articles` | optional | Published only, newest first. Items: `{id, title, summary, price_cents, author_name, created_at, owned, purchased, score}`. `owned` = entitlement rule. `purchased` = caller actually bought it — `owned` minus the author/admin grant; drives the frontend's "My library" filter. `score` = net votes (0 when none). **No `body`, ever, in lists.** |
| `GET /articles/{id}` | optional | Teaser fields + `owned` + `score` + `my_vote` (+ `status` and `price_cents` editable context when caller is author/admin). `my_vote` is `1`/`-1`/`0` when the caller purchased the article (0 = no vote yet), `null` otherwise — the frontend's signal to render vote controls. `body` included **only** if entitled. Drafts → 404 for everyone except author/admin. |
| `GET /articles/mine` | session | All caller's articles, any status, plus per-article `sales_count` and `earned_cents` (one aggregation over purchases). |
| `GET /articles/all` | admin | Every article, any status, any author: `{id, title, summary, price_cents, author_name, created_at, status}` — no bodies, no entitlement/score fields (the moderation table renders none of them, so no score aggregation runs here). |
| `POST /articles` | session | Create as `draft`. Validate title/summary/body/price (§3 bounds). → `{success, message, id}` |
| `PUT /articles/{id}` | author or admin | Update any of title/summary/body/price_cents/status (`draft` ↔ `published`). Same validation. Buyers keep access to the current version. |
| `DELETE /articles/{id}` | author or admin | Delete. Purchase/ledger history is never touched. |

**`routes/wallet.py`**

| Route | Auth | Behavior |
|---|---|---|
| `POST /wallet/topup` | session | Body: `{amount_cents}`, must be exactly 500, 1000, or 2000. Creates Stripe Checkout Session (§4.5). → `{success, message, url}` |
| `GET /wallet/history` | session | Caller's ledger entries, newest first (both balances — this is also the author's earnings statement). |

**`routes/purchases.py`**

| Route | Auth | Behavior |
|---|---|---|
| `POST /purchases` | session | Body: `{article_id}`. Guards (§2.4), then `execute_purchase` transaction. → `{success, message}`; 402 insufficient funds; 409 already owned. |

**`routes/votes.py`**

| Route | Auth | Behavior |
|---|---|---|
| `PUT /articles/{article_id}/vote` | session | Body: `{value: 1 \| -1 \| 0}` — idempotent "set my vote"; `0` clears it (`$unset`). Guards: article exists (404) → value valid (422) → `update_one` on the caller's purchase doc; no matching purchase → 403 "Only buyers can vote" (covers author/admin/non-buyers structurally). Purchasers keep voting rights if the article is later unpublished — consistent with buyers-keep-access. → `{success, message, score, my_vote}` (score re-aggregated after the write so the frontend updates without a refetch). |

**`routes/payouts.py`**

| Route | Auth | Behavior |
|---|---|---|
| `POST /payouts/request` | session | Guard: `earnings_cents >= 1000` (else 422 explaining threshold) and no other request with status `requested` (409). Body: `{destination}`. Reserves full balance (§2.4). |
| `GET /payouts/mine` | session | Caller's requests, newest first. |
| `GET /payouts` | admin | All requests, `?status=` filter, with requester email/display_name. |
| `PUT /payouts/{id}` | admin | Body: `{status: "paid" | "rejected"}`. Only from `requested`. `paid` → set resolved_at. `rejected` → return funds (§2.4). |

### 4.5 Stripe (top-ups only)

**Creating the Checkout Session** (`POST /wallet/topup`):
- `mode="payment"`, one line item, inline `price_data`:
  `{currency: "usd", unit_amount: amount_cents, product_data: {name: "Wallet top-up"}}`.
  Amount comes from the validated preset — never free-form.
- `metadata: {user_id: str(user_id), amount_cents: str(amount_cents)}` — what the
  webhook consumes.
- `success_url: {FRONTEND_URL}/account?topup=success`,
  `cancel_url: {FRONTEND_URL}/account`.

**Webhook** (`POST /stripe/webhook`) — signature is the auth:
1. Raw request body (`await request.body()` — no JSON parsing before verification) +
   `Stripe-Signature` header → `stripe.Webhook.construct_event(payload, sig,
   STRIPE_WEBHOOK_SECRET)`. Invalid → 400.
2. `checkout.session.completed` → read metadata → `credit_topup` transaction (§2.4).
   Replay → `DuplicateKeyError` → log, return 200.
3. Every other event type → 200, ignored.

Local dev: `stripe listen --forward-to localhost:8000/stripe/webhook` (prints the
webhook secret for `.env`). Test card `4242 4242 4242 4242`.

Wallet credit happens **only** here. The `?topup=success` redirect is cosmetic; the
frontend polls until the webhook lands (§5.3).

---

## 5. Frontend

### 5.1 Layout

```
frontend/src/
  main.jsx              # router setup
  App.jsx               # shell: NavBar + route outlet; owns `user` state (from /auth/me on load)
  api/
    request.js          # shared fetch helper: base URL, credentials:'include',
                        # JSON, throws {status, message} on !ok — every call uses it
    auth-api.js  articles-api.js  wallet-api.js  purchases-api.js  votes-api.js  payouts-api.js
  pages/
    ArticleList.jsx     # "/"          teaser cards
    ArticleView.jsx     # "/articles/:id"  read, or teaser + unlock
    AuthPage.jsx        # "/login"     login/register toggle
    AccountPage.jsx     # "/account"   balances, top-up, payout request, ledger history
    MyArticles.jsx      # "/write"     the author's articles + stats + New
    ArticleEditor.jsx   # "/write/new", "/write/:id"  create/edit/publish/delete
    AdminPage.jsx       # "/admin"     all-articles moderation + payout queue
  components/
    NavBar.jsx
```

- `react-router-dom` (the one frontend dependency; earned: Stripe return URL and
  shareable article links need real URLs).
- Auth state: `user` in App state, refreshed via `/auth/me` after login/logout/
  purchase/top-up; passed down as props. No state library.
- Prices always displayed via one `formatCents(cents)` helper (`25¢`, `$1.50`).

### 5.2 Page behavior

- **ArticleList** — cards: title, summary, byline, price, score; button per
  entitlement: "Read" (owned) / "Unlock 25¢" / "Login to buy". Author's own show "Yours".
- **ArticleView** — body present → render (preserved line breaks). Else teaser +
  unlock button. Unlock → `POST /purchases` → success: refetch article + `user`
  (balance chip updates). 402 → inline "balance 10¢, price 25¢ — add funds" → /account.
  Never redirects to Stripe from here. Score always shown; vote controls (▲ score ▼)
  rendered only when `my_vote !== null`: clicking the inactive arrow sets that vote,
  clicking the active arrow clears it (sends `0`); update `score`/`my_vote` from the
  PUT response, no refetch.
- **AuthPage** — login/register toggle (register adds display name). On success,
  return whence they came.
- **AccountPage** — wallet balance + three top-up buttons (each → `POST /wallet/topup`
  → redirect to returned Stripe URL); earnings balance + "Request payout" (enabled at
  ≥$10, asks destination) + own payout requests; ledger history table.
- **MyArticles** — table: title, status, price, sales, earned; edit links; "New article".
- **ArticleEditor** — title, summary, body (textarea), price (entered in cents,
  1–500, shown formatted), draft/published toggle, save (POST or PUT), delete with
  confirm. Client-side validation mirrors backend (UX only — backend is the enforcement).
- **AdminPage** — guard `user.is_admin` (UX only). Tab 1: all articles (any status,
  with author) → edit/unpublish/delete. Tab 2: payout requests filtered by status →
  destination shown → "Mark paid" / "Reject" with confirm.
- **NavBar** — brand → `/`; logged in: wallet chip (`$4.75`) → /account, Write,
  Account, Admin (if admin), display name, Logout. Logged out: Login.

### 5.3 Post-top-up return

`/account?topup=success`: poll `/auth/me` every 2s (max 20s) until `wallet_cents`
increases; show "confirming payment…" then the new balance; on timeout, "payment is
processing — refresh shortly". The webhook is the only credit path; the frontend only
ever *observes*.

---

## 6. Configuration

Root `.env` (gitignored) for local dev via `load_dotenv()`; docker-compose passes real
env vars (which win — dotenv `override=False`). Compose reads the same root `.env`
for `${VAR}` substitution.

| Var | Notes |
|---|---|
| `MONGO_URI` | local: user's existing URI + `directConnection=true` once the replica set lands (§7) · compose: `mongodb://mongo:27017/?directConnection=true` |
| `DB_NAME` | app database name |
| `BACKEND_PORT` | dev port for uvicorn (`uv run python main.py`); default 8000 |
| `FRONTEND_PORT` | dev port for Vite; default 3000 |
| `FRONTEND_URL` | optional override — CORS origin + Stripe return URLs. When unset, derived as `http://localhost:{FRONTEND_PORT}` (`backend/config.py`) |
| `STRIPE_SECRET_KEY` | `sk_test_…` until launch |
| `STRIPE_WEBHOOK_SECRET` | from `stripe listen` (dev) / dashboard endpoint (prod) |
| `VITE_API_URL` | optional override — frontend's API base. When unset, derived as `http://localhost:{BACKEND_PORT}` (`frontend/vite.config.js`, which reads the root `.env`) |

New backend deps (pyproject only — Dockerfile installs from it): `bcrypt`, `stripe`.
New frontend dep: `react-router-dom`.

---

## 7. Mongo replica set (transactions prerequisite)

Multi-document transactions require a replica set. A **single-node** replica set is
sufficient and is the required dev + prod topology.

- **Local Windows service:** add to `mongod.cfg`: `replication: {replSetName: rs0}`,
  restart the service, run `rs.initiate()` once in mongosh. One-time setup,
  documented in README (Phase D).
- **docker-compose:** `command: ["--replSet", "rs0"]` on the mongo service plus a
  healthcheck that runs `rs.status()` and falls back to `rs.initiate()` — the
  standard single-node pattern; backend `depends_on` mongo `service_healthy`.
- Connection strings use `?directConnection=true` (single-member set).
- `verify_db_connection()` additionally asserts transactions work (start and abort a
  trivial one) so misconfiguration fails loudly at startup, not at first sale.

---

## 8. Testing — TDD workflow

**The rule: no backend behavior is implemented before a failing test exists for it.**
The cycle for every step in §9: write the test(s) for the §4/§2 behavior → run, watch
them fail → implement until green → move on. A phase is not complete until its whole
suite passes. The tests are the executable form of this spec — when spec and test
disagree, fix one of them deliberately, never silently.

### Stack and layout

- `pytest` + `pytest-asyncio`, with `httpx.AsyncClient` over `ASGITransport` — tests
  call the real FastAPI app in-process, through the real routes and dependencies.
- **Real Mongo, no mocks for the database** — the unique indexes, TTL behavior, and
  transactions *are* the system under test. `conftest.py` points `DB_NAME` at
  `<DB_NAME>_test`, runs `ensure_indexes()` once, and cleans collections between tests.
  Tests require the same local Mongo as dev (replica set from Phase D on).
- Dev-only deps in a `dev` dependency group in `backend/pyproject.toml`
  (`pytest`, `pytest-asyncio`, `httpx`) — not installed in the Docker image.
- Run from `backend/`: `uv run pytest`.

```
backend/tests/
  conftest.py            # test-DB env override, index setup, cleanup, client + auth fixtures
  test_auth.py  test_articles.py  test_money.py  test_wallet.py
  test_purchases.py  test_votes.py  test_payouts.py  test_stripe_webhook.py
```

### Stripe in tests

- Checkout-session creation (`POST /wallet/topup`): monkeypatch
  `stripe.checkout.Session.create`; assert it receives the validated preset amount,
  correct metadata, and return URLs. No network calls in the suite.
- Webhook: **signature verification is tested for real, not mocked** — tests build
  payloads signed with the test webhook secret (Stripe's documented
  `t=<ts>,v1=<HMAC-SHA256>` scheme) so `construct_event` executes genuinely; a
  tampered-signature test must get 400.
- The end-to-end path through real Stripe (CLI, test card) remains a manual check at
  the end of Phase D — it verifies configuration, not logic.

### What stays manual

UI behavior (rendering, navigation, devtools checks) and real-Stripe configuration —
called out explicitly as **Manual** in each phase checklist. Frontend has no unit-test
scaffold in v1: a deliberate decision, because v1 keeps all decision logic
server-side; revisit if frontend logic ever grows beyond fetch-and-render.

---

## 9. Build order

Follow phases in order; within a phase, steps in order, **test-first per §8**. Each
phase ends when its automated suite is green and the manual checks pass.
After each phase: update `CLAUDE.md` to match reality.

### Phase A — Foundation ✅ (done)
CORS methods+credentials, Dockerfile installs from pyproject, dotenv, root cleanup,
`get_db()`, initial `ensure_indexes()`.

### Phase B — Accounts & sessions

1. Add `bcrypt` to `backend/pyproject.toml`, plus the `dev` dependency group
   (`pytest`, `pytest-asyncio`, `httpx`). Scaffold `tests/conftest.py` (§8): test-DB
   override, `ensure_indexes()` setup, per-test cleanup, app client fixture — prove
   the harness with one trivial test against `GET /hello`.
2. `auth/security.py`: `hash_password`, `verify_password`, `create_session(user_id)`
   (insert session, return token + expiry), `destroy_session(token)`.
3. `auth/rate_limit.py`: port v1 limiter — `check_rate_limit(ip)`,
   `record_failed_attempt(ip)`, `clear_attempts(ip)`; 10 fails / 15 min window,
   prune-on-check. In-memory (single process — documented limitation).
4. `auth/deps.py`: `optional_auth` (cookie → session lookup → user doc or None),
   `require_auth` (401), `require_admin` (403).
5. `routes/auth.py` per §4.3; cookie set/clear helpers live here.
6. `main.py`: register router; CORS origin from `FRONTEND_URL`; add `PUT` to methods.
   Update `ensure_indexes()`: users.display_name unique (collation), keep existing.
7. Frontend: `api/request.js`, `api/auth-api.js`; router skeleton (`main.jsx`,
   `App.jsx` with user state); `AuthPage`; `NavBar` (login state only for now).
8. **Tests (`test_auth.py`, written before steps 2–6):** register → `/auth/me`
   correct → logout kills the session. Duplicate email → 409; duplicate display name
   (case-insensitive) → 409. Unknown email and wrong password → identical 401 body.
   11th failure in window → 429. Session doc has correct `expires_at`; expired session
   → 401. Password stored as bcrypt hash, never plaintext. `PUT /auth/me` renames;
   collision → 409.
   **Manual:** cookie visible in devtools with `httpOnly`; login/register/logout from
   the actual UI; NavBar reflects state.

### Phase C — Articles (marketplace CRUD + gating)

1. `routes/articles.py` per §4.4: entitlement helper first (purchased/author/admin —
   purchases collection simply empty until Phase D), then list / read / mine / create /
   update / delete. Serializers: teaser dict vs full dict — the **only** place `body`
   is added.
2. `ensure_indexes()`: articles.author_id, purchases indexes (§3 — created now,
   used in D).
3. Frontend: `articles-api.js`; `ArticleList`, `ArticleView` (paywall state, unlock
   button disabled with "coming soon" tooltip **removed in D** — render it only when
   purchases API exists; until then show price + "Purchases arrive in Phase D" is NOT
   acceptable — instead: entitled users read, others see teaser + price with no dead
   button), `MyArticles`, `ArticleEditor`.
4. Admin: article moderation half of `AdminPage` (payout tab comes in E).
5. Set your own user `is_admin: true` in mongosh (document the one-liner in README).
6. **Tests (`test_articles.py`, written before step 1's implementation):** anonymous
   list and detail responses contain no `body` key (assert on the JSON, not the UI).
   Draft → 404 for anonymous/other users, full access for author and admin. Author
   edits/publishes/unpublishes/deletes own; 403 on someone else's; admin succeeds on
   anyone's. Validation: empty title/summary/body, price 0, price 501 → 422.
   `/articles/mine` returns all statuses with zeroed stats. Buyers-keep-access rule is
   asserted in Phase D once purchases exist.
   **Manual:** browse list/detail/editor/my-articles in the UI; admin moderation tab;
   the mongosh `is_admin` one-liner works as documented.

### Phase D — Money: wallet, top-ups, purchases

1. Replica set setup (§7): local mongod.cfg + `rs.initiate()`; compose mongo command +
   healthcheck; `MONGO_URI` gains `directConnection=true`; extend
   `verify_db_connection()` with the transaction probe. Document local setup in README.
2. Add `stripe` to pyproject. Add `FRONTEND_URL`, `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET` pass-through to compose.
3. `money/operations.py`: `credit_topup(user_id, amount_cents, stripe_session_id)` and
   `execute_purchase(buyer, article)` — each per §2.4, each a single transaction,
   each returning `{success, message}`. (`reserve_payout`/`return_payout` are built in
   Phase E alongside their routes and tests — money code never lands untested.)
4. `ensure_indexes()`: ledger indexes (user_id; stripe_session_id partial unique).
5. `routes/wallet.py` (topup checkout + history), `routes/purchases.py`,
   `routes/stripe_webhook.py` per §4.4–4.5.
6. Frontend: `wallet-api.js`, `purchases-api.js`; `AccountPage` (balances, top-up
   buttons, history, `?topup=success` polling); wire the real unlock flow in
   `ArticleView` incl. 402 → add-funds prompt; NavBar wallet chip.
7. **Tests (written before steps 3–5):**
   - `test_money.py` — split-rounding table (1¢→1/0, 3¢→2/1, 25¢→20/5, 500¢→400/100);
     after any sequence of operations, ledger sums equal stored balances (§2 invariant 6).
   - `test_purchases.py` — happy path: buyer −price / author +author_cents / purchase
     row has the split / two correct ledger rows / body now served. Insufficient
     balance → 402, nothing changed. Repeat purchase → 409, charged once (also covers
     double-click). Buying own article → rejected. Draft/missing article → 404.
     Buyer keeps body access after author edits price/content.
   - `test_wallet.py` — topup rejects non-preset amounts (422); Session.create called
     with correct amount/metadata/URLs (monkeypatched); history returns caller's
     ledger newest-first.
   - `test_stripe_webhook.py` — genuinely-signed event credits wallet + ledger row;
     same event replayed → still credited exactly once; tampered signature → 400;
     unrelated event types → 200 no-op.
   **Manual (Stripe CLI running):** real $5 top-up with `4242…` → "confirming…" →
   balance in UI; unlock flow + 402 add-funds prompt in UI; NavBar chip updates;
   `stripe events resend` on the real event → no double credit.

### Phase E — Payouts, polish, docs

1. `routes/payouts.py` per §4.4; payout tab in `AdminPage`; payout request UI in
   `AccountPage`.
2. Polish: loading/empty/error states on every page; 404 route; basic styling pass
   (clean, minimal); confirm dialogs on destructive actions.
3. README rewrite: what the app is, full local setup (uv, npm, Mongo replica set
   one-time init, Stripe CLI), env table, admin bootstrap one-liner, compose usage.
   Final `CLAUDE.md` sync.
4. **Tests (`test_payouts.py`, written before step 1):** request at ≥$10 → earnings
   0, request `requested`, ledger `payout_reserve`; below threshold → 422; second
   request while one pending → 409; admin reject → funds return + `payout_return`
   ledger row; admin paid → status/resolved_at change only, no money moves; non-admin
   on admin routes → 403; resolving an already-resolved request → rejected.
   **Manual:** full §1 walkthrough — fresh browser, two accounts (author + reader) +
   admin: write → publish → top up → buy → read → earnings → payout → mark paid.
   Zero console errors throughout. Full suite green one last time.

### Phase F — Votes

1. `routes/votes.py` per §4.4; `ensure_indexes()` gains `purchases.article_id`;
   register router in `main.py`.
2. `routes/articles.py`: score aggregation query (`$match` article ids → `$group` by
   `article_id` → `$sum: "$vote"`; missing row → 0 in the serializer, same pattern as
   sales stats); `score` on teasers and detail; `my_vote` on detail (refactor the
   purchase-existence check to return the purchase doc so `owned` and `my_vote` come
   from one query).
3. Frontend: `votes-api.js`; score on `ArticleList` cards; vote controls on
   `ArticleView` per §5.2; vote-button styling.
4. **Tests (`test_votes.py`, written before steps 1–2):** vote requires auth → 401;
   non-purchaser and the author → 403; purchaser upvotes → 200, detail shows
   `score: 1`, `my_vote: 1`; switching up→down flips score 1 → −1 (no double count);
   `value: 0` clears → score 0; invalid value → 422; missing article → 404; two
   buyers voting opposite ways → score 0; listing carries `score`; non-purchaser
   detail has `my_vote: null`; article with no votes → `score: 0`.
   **Manual:** buy with a smoke account, vote up, toggle to down, clear; score
   visible on list and detail, logged out too; author sees score but no controls.

---

## 10. Binding design principles

The global code-structure rules, applied here:

- One function = one job, verb-phrase names. Route handlers and page components are
  orchestrators calling named helpers — table-of-contents readability.
- Guard clauses first; happy path unindented at the end. Max 2 nesting levels.
- Queries return data or `None`; operations return `{success, message}`; builders
  return the thing or `None`.
- `for` loops over `.map/.filter/.reduce` unless there's a specific reason.
- Every external call (Mongo, Stripe, fetch) in try/except with source-identifying logs.
- No speculative code; no single-use abstractions; every line earns its place.

**Money invariants — never regress:**
1. All money is integer cents.
2. Balances change **only** in `money/operations.py`, only inside transactions, and
   every change writes a ledger entry in that transaction. Ledger is append-only.
3. `wallet_cents` can never go negative (conditional-update debit).
4. Wallet credit originates **only** from the signature-verified Stripe webhook.
5. Prices and amounts come from the DB / validated presets — never from the client.
6. Ledger-sum == stored balance, per user, per balance, at all times.

**Content invariant:** `body` never leaves the backend unless the entitlement rule
passes — one serializer owns this.

**Secrets:** env vars only; nothing secret in `VITE_` vars or git.
