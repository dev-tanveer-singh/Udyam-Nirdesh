# Udyam-Nirdesh

A funding-navigation platform for first-time entrepreneurs and students in India (Smart India Hackathon
problem statement **SIH26092**). A user describes themselves and their business idea, and the app:

- matches them against government funding schemes with a transparent, rule-based checklist,
- scores their **funding readiness** out of 100 and explains every point,
- tracks documents, applications and channel partners,
- provides EMI / what-if / funding-path calculators.

> **Prototype.** Eligibility, subsidy and margin-money rules are simplified illustrations, and partner data is
> demo data. Nothing here is a lending decision — always verify on the official scheme portal before applying.

---

## Contents

- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Demo accounts](#demo-accounts)
- [Features by role](#features-by-role)
- [API reference](#api-reference)
- [How scoring works](#how-scoring-works)
- [Frontend notes](#frontend-notes)
- [Testing](#testing)
- [Security](#security)
- [Deploying](#deploying)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

---

## Architecture

```
┌──────────────────────────┐      JSON / multipart       ┌──────────────────────────────┐
│  frontend/index.html     │  ───────────────────────►   │  FastAPI  (backend/app)      │
│  single-file web app     │   Authorization: Bearer     │                              │
│                          │  ◄───────────────────────   │  routers → services → DB     │
│  • renders results       │                             │  • auth (bcrypt + JWT)       │
│  • holds no secrets      │                             │  • rule engine / readiness   │
│  • marketplace (local)   │                             │  • EMI + funding path        │
└──────────────────────────┘                             │  • document storage          │
                                                         └──────────────┬───────────────┘
                                                                        │ SQLAlchemy
                                                                 SQLite (dev) / PostgreSQL
```

The **server is the single source of truth** for authentication, profiles, schemes, documents, partners,
applications, matching, the readiness score and the calculators. The frontend only renders what the API returns.

Still frontend-only (browser `localStorage`, not part of the core funding flow): the project marketplace,
investor connections and private channels.

## Project layout

```
udyam-nirdesh/
├── README.md
├── frontend/
│   └── index.html               single-file web app (HTML + CSS + JS)
└── backend/
    ├── README.md                backend-specific notes
    ├── requirements.txt         runtime dependencies
    ├── requirements-dev.txt     + pytest, httpx
    ├── .env.example             every setting, documented
    ├── pytest.ini
    ├── app/
    │   ├── main.py              app factory, CORS, security headers, static frontend
    │   ├── config.py            settings (environment / .env)
    │   ├── constants.py         enums + reference data (served at GET /meta)
    │   ├── database.py          engine + session
    │   ├── models.py            SQLAlchemy tables
    │   ├── schemas.py           Pydantic models — the API contract
    │   ├── security.py          password hashing, JWT, login throttling
    │   ├── deps.py              current user + role guards
    │   ├── seed.py              schemes, partners, demo accounts
    │   ├── routers/             auth · profile · schemes · documents · partners
    │   │                        applications · readiness · tools · admin · meta
    │   └── services/            eligibility · readiness · funding/EMI · geo · document storage
    └── tests/                   pytest suite + parity fixtures
```

## Quick start

**Requirements:** Python 3.10+ (developed on 3.12).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000**. FastAPI serves `frontend/index.html` itself, so the page and the API share one
origin and no CORS setup is needed.

| URL | What |
|---|---|
| http://localhost:8000 | the web app |
| http://localhost:8000/docs | interactive API docs (Swagger UI, development only) |
| http://localhost:8000/api/v1/health | health check |

The first start creates `backend/udyam.db` (SQLite) and seeds 3 schemes, 6 partners and the demo accounts.
Reset everything with `python -m app.seed --reset` (development only).

### Running the frontend from a different origin

If you open `index.html` with a static server (VS Code Live Server on `:5500`, `python -m http.server`, …):

1. Add that origin to `CORS_ORIGINS` in `backend/.env`.
2. The page auto-targets `http://localhost:8000/api/v1` when opened locally. For any other host, set this
   near the top of `index.html`:
   ```html
   <script>window.UDYAM_CONFIG = { apiBase: 'https://api.your-domain.example/api/v1' };</script>
   ```

## Configuration

Copy `backend/.env.example` to `backend/.env`. All values have development defaults.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` disables `/docs` and enforces a real `SECRET_KEY` |
| `DATABASE_URL` | `sqlite:///./udyam.db` | e.g. `postgresql+psycopg://user:pass@host/db` |
| `SECRET_KEY` | dev placeholder | **required in production**, 32+ random characters |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | token lifetime |
| `CORS_ORIGINS` | localhost dev ports | comma-separated; only for cross-origin frontends |
| `UPLOAD_DIR` | `./storage/uploads` | where document files are stored |
| `MAX_UPLOAD_BYTES` | `5242880` | 5 MB per document |
| `SEED_ON_STARTUP` | `true` | seed reference data into empty tables |
| `SEED_DEMO_USER` | `true` | creates `user@udyam.local` — **turn off in production** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@udyam.local` / *(empty)* | empty password: dev uses `admin123`; production creates no admin |
| `SERVE_FRONTEND` | `true` | serve `../frontend` from the same server |

Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

## Demo accounts

Development only.

| Role | Email | Password |
|---|---|---|
| Entrepreneur | `user@udyam.local` | `user123` |
| Admin | `admin@udyam.local` | `admin123` |

Investors and channel partners can register from the login screen. `admin` can never be self-registered.

## Features by role

| Role | Can do |
|---|---|
| **Entrepreneur / student** | profile, document uploads, scheme matching with explanations, readiness score, funding tools, partner locator, application tracking, AI assistant, project marketplace |
| **Investor** | explore and save projects, connection requests, private channels |
| **Channel partner** | relevant projects, connection requests, scheme and partner directories |
| **Admin** | overview dashboard, manage schemes and partners, view users |

The interface supports English, Hindi and Punjabi labels for navigation, plus light/dark themes.

## API reference

Base path `/api/v1`. Authenticate with `Authorization: Bearer <access_token>` from `POST /auth/login`.
Full, always-current schemas are at `/docs`.

| Method & path | Who | Purpose |
|---|---|---|
| `GET /meta` | public | states, categories, business types/stages, document types, application statuses |
| `POST /auth/register` | public | create an account (`user`, `investor` or `partner`) |
| `POST /auth/login` | public | returns `{access_token, token_type, expires_in, user}` |
| `GET /auth/me` | any | current user |
| `GET /profile` · `PUT /profile` | entrepreneur | read / replace the typed profile |
| `GET /schemes` | any | scheme catalogue |
| `GET /schemes/matches` | entrepreneur | every scheme classified against the saved profile, best first |
| `POST /schemes` · `PUT /schemes/{id}` · `DELETE /schemes/{id}` | admin | manage schemes (delete is blocked while applications reference it) |
| `GET /documents` | entrepreneur | checklist: each document type as `uploaded` or `missing` |
| `POST /documents/upload` | entrepreneur | multipart: `document_type` (slug) + `file` |
| `GET /documents/{id}/file` · `DELETE /documents/{id}` | entrepreneur | private download / removal |
| `GET /partners` | any | directory (`q`, `state`, `district`, `scheme_id` filters) |
| `GET /partners/nearby?lat&lng&radius_km&limit` | any | geospatial locator, nearest first, pan-India partners last |
| `POST /partners` · `DELETE /partners/{id}` | admin | manage partners |
| `GET /applications` · `POST /applications` | entrepreneur | list / create (`scheme_id`, optional `application_reference`) |
| `PATCH /applications/{id}` · `DELETE /applications/{id}` | entrepreneur | update `status` / reference, or remove |
| `GET /readiness` | entrepreneur | 100-point score with per-category breakdown |
| `POST /tools/emi` | entrepreneur | loan / EMI calculator |
| `POST /tools/what-if` | entrepreneur | saved profile vs. a hypothetical funding scenario |
| `GET /tools/funding-path` | entrepreneur | greedy funding plan across matched schemes and own contribution |
| `GET /admin/users` | admin | account list (never includes hashes) |

### Contract conventions

- `snake_case` everywhere; numbers are numbers (`age: 24`, `annual_income: 350000`), never strings.
- Documents use slugs: `identity_proof`, `pan`, `income_certificate`, `caste_certificate`,
  `business_registration`, `bank_statement`, `project_report`, `education_skill_certificate`.
- Application `status` is one of `not_started`, `documents_pending`, `applied`, `under_review`, `approved`, `rejected`.
- Timestamps are ISO-8601 UTC. Records are referenced by id (`scheme_id`, `document_id`, `user_id`), never by display text.
- Errors are `{"detail": "..."}` or, for validation failures, a list of `{loc, msg}` items (HTTP 422).

Example profile payload:

```json
{
  "full_name": "Aman Kumar", "age": 24, "gender": "Male", "state": "Punjab", "district": "Ludhiana",
  "category": "OBC", "occupation": "Student",
  "business_type": "Manufacturing", "business_stage": "New Business",
  "annual_income": 350000, "annual_turnover": 800000,
  "funding_required": 800000, "own_contribution": 80000, "funding_purpose": "Machinery"
}
```

## How scoring works

**Scheme matching** runs six checks per scheme — social category, business type, business stage, age, income
limit, and whether the funding amount is inside the scheme's range. Each check is `ok`, `warn` (information
missing) or `bad` (fails). Any `bad` → *Not Eligible*; otherwise any `warn` → *Potentially Eligible*; otherwise
*Eligible*. Schemes are ranked by status, then by the percentage of checks that pass.

**Readiness score (100 points)**, measured against the top-matched scheme:

| Category | Points | Based on |
|---|---|---|
| Eligibility match | 30 | the six checks above |
| Document readiness | 20 | the scheme's required documents that are uploaded |
| Financial readiness | 20 | income, turnover baseline, amount within limit, own-contribution vs. margin-money norm |
| Business & project readiness | 20 | business type/stage, funding purpose, project report |
| Application completeness | 10 | an application exists and has been submitted |

The rules live in `backend/app/services/` and are covered by a parity test that reproduces the original
JavaScript engine's results exactly.

## Frontend notes

- **No build step.** `frontend/index.html` is a single self-contained file.
- **What is stored in the browser:** the sign-in token (`sessionStorage`, or `localStorage` when "Remember login"
  is ticked), theme/language, and the frontend-only marketplace data. No passwords, profile, financial data or
  document contents.
- **Demo helpers:** the prefilled demo login and "Try the live demo" button are controlled by the `DEMO` constant
  at the top of the script. Set `enabled: false` for real deployments.
- Session expiry (HTTP 401) returns the user to the login screen automatically.

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The suite covers registration/login/throttling, role guards, profile validation, scheme CRUD, document upload
(size limits, file-type sniffing, ownership, path safety), the partner locator, applications, readiness, EMI
maths, and a **parity test** that checks the Python rule engine against outputs recorded from the original
JavaScript implementation (`tests/fixtures/`). Each test module starts from freshly seeded data.

## Security

- Passwords hashed with **bcrypt**; JWT bearer tokens, role read from the database on every request.
- Login throttling per (IP, email) with equal timing for unknown and known accounts.
- Uploads: 5 MB limit, file type decided by content (PDF, PNG, JPEG, plain text), server-generated file names,
  per-user privacy (404 for other users' files), served with `nosniff`.
- Strict request validation (unknown fields rejected), URL scheme checks, output escaped in the frontend.
- Security headers on all responses; `Cache-Control: no-store` on API responses.
- The location search rounds coordinates to ~1 km before sending them.

## Deploying

1. `ENVIRONMENT=production`, a random `SECRET_KEY` (the app refuses to start without one).
2. `SEED_DEMO_USER=false`, set `ADMIN_PASSWORD`; set `DEMO.enabled = false` in `index.html`.
3. Use **PostgreSQL** (`DATABASE_URL`) and manage the schema with **Alembic** instead of `create_all()`.
4. Store uploads on durable storage (mounted volume or object storage).
5. Serve over **HTTPS** behind a reverse proxy; set `CORS_ORIGINS` to the exact frontend origin if it is separate.
6. Cap request bodies at the proxy (e.g. nginx `client_max_body_size 6m`).
7. Run with several workers, e.g. `gunicorn -k uvicorn.workers.UvicornWorker app.main:app` — and move login
   throttling to Redis or your gateway (it is per-process today).
8. Replace the approximate demo partner coordinates with real branch locations.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Cannot reach the server" on the login screen | Backend not running, or the page points at the wrong API. Start `uvicorn` and open `http://localhost:8000`, or set `UDYAM_CONFIG.apiBase`. |
| Browser console shows a CORS error | The frontend is on another origin — add it to `CORS_ORIGINS` and restart. |
| "Invalid email or password" for the demo user | The database was seeded with different settings. Run `python -m app.seed --reset` (development only). |
| "Too many failed login attempts" (429) | Throttle triggered; wait 5 minutes or restart the server in development. |
| Upload rejected: "Unsupported file" (415) | Only PDF, PNG, JPEG and plain text are accepted; the check uses the file's content, not its extension. |
| Upload rejected: too large (413) | Files are limited to 5 MB (`MAX_UPLOAD_BYTES`). |
| Logged out unexpectedly | Access tokens last 60 minutes and there is no refresh flow yet — log in again. |
| "Near me" does nothing | Browser location permission is blocked, or the page isn't on `localhost`/HTTPS. Filter by state instead. |
| App refuses to start in production | `SECRET_KEY` is missing, default, or shorter than 32 characters. |

## Known limitations

- Rule-based prototype: scheme rules, subsidy and margin-money norms are simplified and must be verified with
  official sources; there is no live integration with government portals or banks.
- Partner data is demo data and unverified; partner coordinates are approximate.
- Documents are stored but not OCR'd or verified.
- The marketplace, investor connections and private channels are browser-local and not shared between users.
- No email verification, password reset, refresh tokens, or database migrations yet.
- The AI assistant is a rule-based explainer, not a hosted language model.
