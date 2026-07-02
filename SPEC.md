# tiny-paywall2 — Full Specification

A micro-paywall for articles. Anyone can browse teasers of every article; reading the
full body of an article costs a small one-time fee, paid per article through Stripe.
Purchases attach to an email+password account and last forever.

This document is the source of truth for what we are building and in what order.
`CLAUDE.md` describes how the codebase works *today*; this file describes where it is going.

---

## 1. Product definition

**The user story, end to end:**

1. A visitor lands on the site and sees a list of every published article: title,
   summary (teaser), and price. This list is fully public.
2. Opening an article shows the teaser plus a paywall: "Unlock for $0.75" (or whatever
   that article costs).
3. To buy, the visitor needs an account (email + password). Register/login is one form.
4. Clicking "Unlock" sends them to Stripe Checkout (hosted page). On successful payment
   they land back on the article — now fully readable.
5. Anything they've bought stays readable forever on that account, from any device.
6. The site owner (admin account) creates, edits, and deletes articles through a
   minimal admin page in the same frontend.

**Locked decisions:**

| Decision | Choice |
|---|---|
| Stack | FastAPI + Motor (async Mongo) backend, React 19/Vite frontend |
| Access model | Email + password accounts, server-side sessions in Mongo |
| Pricing | Per-article one-time purchase (tiny fee), USD |
| Payment | Stripe Checkout (hosted page) + webhook |
| Free tier | Teasers of *all* articles are public; bodies are paid |
| Admin | `is_admin` flag on a user; admin CRUD routes + minimal admin UI |
| Content format | Plain text bodies rendered with preserved line breaks (markdown is a later enhancement, not v1) |

**Non-goals for v1** (explicitly out of scope — do not build speculatively):

- Password reset / email sending of any kind
- Subscriptions or bundles
- Refund handling in-app (handled manually in the Stripe dashboard)
- Search, tags, pagination (revisit if the article count ever demands it)
- Rich text / markdown editor
- Production deployment config (docker-compose remains a dev setup; deployment is its own future task)

---

## 2. Data model (Mongo, database name from `DB_NAME`)

### users
```
{
  _id:            ObjectId,
  email:          str,        // stored lowercase+trimmed; unique index
  password_hash:  str,        // bcrypt
  is_admin:       bool,       // default false; set true manually in DB for the owner
  created_at:     datetime    // UTC
}
```

### sessions
```
{
  _id:         str,           // the session token itself: secrets.token_urlsafe(32)
  user_id:     ObjectId,
  created_at:  datetime,
  expires_at:  datetime       // TTL index; Mongo deletes expired sessions itself
}
```
- Session lifetime: **30 days**. Cookie and `expires_at` always set together.
- The cookie (`session`) stores the raw token. `httpOnly`, `sameSite=lax`,
  `secure` only in production (localhost is http).

### articles
```
{
  _id:          ObjectId,
  title:        str,
  summary:      str,          // the public teaser
  body:         str,          // the paid content — never serialized unless entitled
  price_cents:  int,          // >= 50 (Stripe's minimum charge is $0.50 USD)
  published:    bool,         // unpublished articles visible to admin only
  created_at:   datetime,
  updated_at:   datetime
}
```

### purchases
```
{
  _id:                ObjectId,
  user_id:            ObjectId,
  article_id:         ObjectId,
  stripe_session_id:  str,     // Checkout Session id; unique index (webhook idempotency)
  amount_cents:       int,     // what was actually charged
  created_at:         datetime
}
```

### Indexes (all created idempotently in `ensure_indexes()` at startup)

| Collection | Index | Why |
|---|---|---|
| users | `email` unique | duplicate registration rejected by the DB, not app code |
| sessions | `expires_at` TTL (expireAfterSeconds=0) | automatic session expiry |
| purchases | `(user_id, article_id)` unique | a user can never double-own an article |
| purchases | `stripe_session_id` unique | webhook retries can't create duplicate purchases |

No index on `articles` for v1 — list queries at this scale don't need one.

**Entitlement rule (used everywhere):** a user may read an article's body iff a
`purchases` document exists for `(user_id, article_id)` **or** the user `is_admin`.

---

## 3. Backend

### 3.1 Layout

```
backend/
  main.py               # app assembly: dotenv, CORS, routers, lifespan — no logic
  db/
    connection.py       # client, get_db(), verify_db_connection(), ensure_indexes()
  routes/
    auth.py             # register / login / logout / me
    articles.py         # public list/read + admin CRUD
    purchases.py        # checkout session creation + Stripe webhook
  auth/
    security.py         # hash_password, verify_password, create_session, destroy_session
    deps.py             # require_auth, require_admin, optional_auth (FastAPI dependencies)
    rate_limit.py       # in-memory attempt limiter (ported from tiny-paywall v1)
```

One module per resource (project convention). `main.py` stays an orchestrator — it
reads like a table of contents, no inline logic.

### 3.2 Response conventions

Follows the global code-structure rules, applied to HTTP:

- **Queries** (GETs) return the data document/list. Not-found → HTTP 404.
- **Operations** (POST/PUT/DELETE) return `{ "success": bool, "message": str }`,
  plus operation-specific fields (e.g. checkout returns `url`).
- Errors are raised as `HTTPException(status, detail)`; no bare 500s from expected
  failure modes. All external calls (Mongo, Stripe) wrapped in try/except with
  logging that identifies the source.

### 3.3 Auth (`routes/auth.py`)

| Route | Auth | Behavior |
|---|---|---|
| `POST /auth/register` | public, rate-limited | Validate email format + password ≥ 8 chars. Normalize email. Insert user (duplicate → 409). Create session, set cookie. → `{success, message}` |
| `POST /auth/login` | public, rate-limited | Verify credentials (same error message for bad email vs bad password — don't leak which). Create session, set cookie. Failure → 401 + record attempt. → `{success, message}` |
| `POST /auth/logout` | session required | Delete session doc, clear cookie. → `{success, message}` |
| `GET /auth/me` | session required | → `{ email, is_admin }`. No session → 401. |

**Password hashing:** `bcrypt` library, default work factor. (Add to
`backend/pyproject.toml` only — Dockerfile installs from pyproject now.)

**Dependencies (`auth/deps.py`):**
- `optional_auth` → the user doc or `None` (for public routes that personalize, like the article list)
- `require_auth` → the user doc or raises 401
- `require_admin` → the user doc or raises 401/403

**Rate limiting (`auth/rate_limit.py`):** port of v1's limiter — in-memory map of
IP → attempt count, 10 failures per 15-minute window, applies to register+login.
In-memory is acceptable: single-process deployment; document the limitation.

### 3.4 Articles (`routes/articles.py`)

| Route | Auth | Behavior |
|---|---|---|
| `GET /articles` | optional | Published articles, newest first: `[{ id, title, summary, price_cents, created_at, owned }]`. `owned` is computed from the caller's purchases (`false` when anonymous, `true` for admin). **`body` is never in list responses.** |
| `GET /articles/{id}` | optional | Teaser fields + `owned`. Includes `body` **only** when entitled. Unpublished → 404 unless admin. Malformed id → 404. |
| `POST /articles` | admin | Create. Validate: title/summary/body non-empty, `price_cents` int ≥ 50. → `{success, message, id}` |
| `PUT /articles/{id}` | admin | Full update, same validation. → `{success, message}` |
| `DELETE /articles/{id}` | admin | Delete the article. Existing purchases keep their history rows; a deleted article simply disappears from the list. → `{success, message}` |

Single read endpoint, no error-flow for normal browsing: the frontend renders the
paywall CTA when `owned` is false and `body` is absent.

### 3.5 Purchases + Stripe (`routes/purchases.py`)

**`POST /purchases/checkout`** — session required. Body: `{ article_id }`.

Guard clauses, in order: article exists and is published → not already owned →
then create the Checkout Session:

- `mode="payment"`, single line item using inline `price_data`:
  `{ currency: "usd", unit_amount: <price_cents from DB>, product_data: { name: <title> } }`
  — **price always comes from the DB, never from the client.**
- `metadata: { user_id, article_id }` — this is what the webhook consumes.
- `success_url: {FRONTEND_URL}/articles/{id}?purchase=success`
- `cancel_url:  {FRONTEND_URL}/articles/{id}`
- Returns `{ success, message, url }`; the frontend redirects to `url`.

**`POST /stripe/webhook`** — public endpoint, **signature is the auth**:

1. Read the **raw request body**; verify with `stripe.Webhook.construct_event`
   using `STRIPE_WEBHOOK_SECRET`. Bad signature → 400.
2. Handle `checkout.session.completed`: read `user_id`/`article_id` from metadata,
   insert the purchase document.
3. Idempotency: the unique indexes make replays a duplicate-key error — catch it and
   return 200 (Stripe retries on non-2xx; a replayed event is success, not failure).
4. Ignore all other event types with a 200.

Notes:
- CORS does not apply (server-to-server call from Stripe), but the webhook route must
  read the raw body — don't run it through a JSON-parsing dependency before verification.
- Local dev: `stripe listen --forward-to localhost:8000/stripe/webhook` (Stripe CLI),
  which also prints the `STRIPE_WEBHOOK_SECRET` for `.env`.
- After payment, there's a short gap before the webhook lands. The frontend handles it
  (see 4.3) — the backend does nothing special.

New backend dependency: `stripe` (pyproject only).

### 3.6 Existing code changes required along the way

- `ensure_indexes()`: add the two `purchases` indexes (Phase D).
- CORS: add `PUT` to `allow_methods` (admin edit, Phase C); move the hardcoded origin
  to `FRONTEND_URL` env var (Phase B, it's needed for Stripe URLs anyway).
- `CLAUDE.md`: keep in sync as each phase lands (it currently documents step-2 state).

---

## 4. Frontend

### 4.1 Layout

```
frontend/src/
  main.jsx              # router + app shell
  App.jsx               # layout: nav + route outlet
  api/
    auth-api.js         # register, login, logout, fetchMe
    articles-api.js     # fetchArticles, fetchArticle, create/update/deleteArticle
    purchases-api.js    # startCheckout
  pages/
    ArticleList.jsx     # home: teaser cards with price / "Read" if owned
    ArticleView.jsx     # teaser + body, or teaser + unlock button
    AuthPage.jsx        # login/register toggle form
    AdminPage.jsx       # article table + create/edit form (admin only)
  components/
    NavBar.jsx          # site title, login state, logout, admin link
```

- **Routing:** `react-router-dom` — earned, not speculative: Stripe's `success_url`
  must deep-link back to a specific article (`/articles/:id`), so real URL routing is
  required. Routes: `/`, `/articles/:id`, `/login`, `/admin`.
- **Auth state:** on app load, call `/auth/me`; hold `user` in top-level state passed
  down as props. No state library — this app has one piece of global state.
- **Every fetch** uses `credentials: "include"` (session cookie) — build one shared
  request helper in `api/` so it can't be forgotten per-call.
- API base URL stays `VITE_API_URL` (default `http://localhost:8000`).
  **Never put secrets in `VITE_` vars** — with hosted Checkout the frontend needs no
  Stripe key at all, only the redirect URL the backend returns.

### 4.2 Page behavior

- **ArticleList (`/`)** — fetch `/articles`; card per article: title, summary,
  `$X.XX`, and either "Read" (owned) or "Unlock" (not owned). Unlock when logged out
  routes to `/login` (then back).
- **ArticleView (`/articles/:id`)** — fetch the article. If `body` present, render it
  (preserved line breaks). Otherwise render teaser + unlock button → `startCheckout`
  → redirect to the returned Stripe URL.
- **AuthPage (`/login`)** — one form, login/register toggle. On success, refresh
  `user` and return the visitor to where they came from.
- **AdminPage (`/admin`)** — guard on `user.is_admin` (client-side guard is UX only;
  the backend enforces the real rule). Table of all articles; create/edit form:
  title, summary, body (textarea), price in cents, published checkbox; delete with a
  confirm step.
- **NavBar** — site name → `/`; logged out: "Login"; logged in: email + "Logout";
  admin additionally sees "Admin".

### 4.3 Post-payment return

Landing on `/articles/:id?purchase=success`: fetch the article; if `body` is absent
(webhook hasn't landed yet), re-fetch every ~2s for up to ~20s with a "confirming your
purchase…" notice, then stop with a "refresh in a moment" message. No payment
verification happens in the frontend — the webhook is the only thing that grants access.

---

## 5. Configuration

All backend config comes from the environment. Root `.env` (gitignored) supplies local
dev values via `load_dotenv()`; docker-compose supplies container values (real env vars
beat `.env` — dotenv `override=False`).

| Var | Used by | Notes |
|---|---|---|
| `MONGO_URL` | backend | `mongodb://localhost:27017` local / `mongodb://mongo:27017` compose |
| `DB_NAME` | backend | app database name |
| `FRONTEND_URL` | backend | CORS origin + Stripe success/cancel URLs (`http://localhost:3000` dev) |
| `STRIPE_SECRET_KEY` | backend | test key (`sk_test_…`) until launch |
| `STRIPE_WEBHOOK_SECRET` | backend | from `stripe listen` in dev; dashboard endpoint secret in prod |
| `VITE_API_URL` | frontend | public, not a secret; defaults to `http://localhost:8000` |

`docker-compose.yml` must pass each new backend var through (`VAR=${VAR}` pattern —
compose reads root `.env` for substitution).

---

## 6. Build order

Each phase is independently shippable and ends with manual verification (no test
framework is configured; verification is by hand against the running app for v1).

### Phase A — Foundation ✅ (done)
Scaffold fixes (CORS methods+credentials, Dockerfile installs from pyproject, dotenv,
root cleanup), `get_db()`, `ensure_indexes()` for users/sessions.

### Phase B — Auth
Backend: `auth/security.py`, `auth/deps.py`, `auth/rate_limit.py`, `routes/auth.py`;
CORS origin from `FRONTEND_URL`. Frontend: AuthPage, NavBar login state, shared fetch
helper, router skeleton.
**Verify:** register → cookie set → `/auth/me` works → logout kills it; duplicate
email → 409; wrong password → 401 with identical message to unknown email; 11th bad
attempt inside 15 min → 429; session doc appears in Mongo with correct `expires_at`.

### Phase C — Articles
Backend: `routes/articles.py` (public + admin CRUD), CORS `PUT`. Frontend:
ArticleList, ArticleView (paywall state), AdminPage. Set your own user `is_admin: true`
directly in Mongo (one-time, documented in README).
**Verify:** anonymous sees teasers, never bodies (check the network response, not the
UI); admin CRUD works end-to-end; non-admin hitting admin routes → 403; unpublished
articles invisible to non-admins; `price_cents < 50` rejected.

### Phase D — Purchases (Stripe)
Backend: `routes/purchases.py`, purchases indexes in `ensure_indexes()`. Frontend:
unlock flow, post-payment return handling.
**Verify (Stripe test mode + CLI):** full purchase with test card `4242…` unlocks the
article; `owned` flips in the list; replaying the webhook event creates no duplicate
purchase; tampered signature → 400; buying an already-owned article is refused before
Stripe; price on the Stripe page matches the DB, not anything the client sent.

### Phase E — Polish
Error/loading/empty states on every page, basic styling, 404 route, README rewrite
(setup incl. Stripe CLI, admin bootstrap, env table), final `CLAUDE.md` sync.
**Verify:** full walkthrough of the section-1 user story, fresh browser, zero console
errors.

---

## 7. Design principles (binding for all phases)

These apply the global code-structure rules to this codebase:

- One function = one job, named as a verb phrase. Orchestrators (route handlers,
  `main.py`, page components) call named helpers and read like a table of contents.
- Guard clauses at the top; happy path unindented at the bottom. Max 2 levels of nesting.
- Queries return data or `None`/`null`; operations return `{success, message}`;
  builders return the thing or `None`/`null`.
- `for` loops, not `.map/.filter/.reduce` chains, unless there's a specific reason.
- Every external call (Mongo, Stripe, fetch) wrapped in try/except (or try/catch) with
  context-rich logging.
- No speculative code. No abstraction for single-use code. Every line earns its place.
- Security invariants that must never regress:
  1. `body` never leaves the backend unless the entitlement rule passes.
  2. Prices come from the DB; client-supplied amounts are never trusted.
  3. Access is granted **only** by the signature-verified webhook.
  4. Secrets live in env vars; nothing secret in `VITE_` vars or git.
