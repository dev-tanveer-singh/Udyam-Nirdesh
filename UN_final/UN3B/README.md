# Udyam-Nirdesh — Backend (FastAPI)

REST API for the Udyam-Nirdesh frontend: authentication, profile, scheme matching, document
uploads, partner locator, applications, readiness score and funding tools.

```
backend/
├── app/
│   ├── main.py            app, CORS, security headers, optional static frontend
│   ├── config.py          settings from environment / .env
│   ├── constants.py       enums + reference data (single source of truth, served at GET /meta)
│   ├── models.py          SQLAlchemy tables
│   ├── schemas.py         Pydantic request/response models  <- the API contract
│   ├── security.py        bcrypt, JWT, login throttling
│   ├── deps.py            current-user + role guards
│   ├── seed.py            schemes, partners, demo accounts (python -m app.seed)
│   ├── routers/           auth, profile, schemes, documents, partners, applications,
│   │                      readiness, tools, admin, meta
│   └── services/          eligibility (rule engine), readiness, funding/EMI, geo, document storage
└── tests/                 pytest suite, incl. a parity test against the original JS rule engine
```

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional in development
uvicorn app.main:app --reload
```

Open **http://localhost:8000** — FastAPI serves `../frontend/index.html` itself, so there is no CORS to set up.
Interactive API docs: http://localhost:8000/docs (disabled when `ENVIRONMENT=production`).

Demo logins (development only): `user@udyam.local / user123` and `admin@udyam.local / admin123`.

Frontend on another origin (e.g. VS Code Live Server on :5500)? Add that origin to `CORS_ORIGINS`;
the frontend auto-targets `http://localhost:8000` when opened locally, or set
`window.UDYAM_CONFIG = { apiBase: 'https://api.example.com/api/v1' }` in `index.html`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## API overview (all under `/api/v1`)

| Method & path | Who | Purpose |
|---|---|---|
| `GET /meta` | public | states, categories, business types/stages, document types, application statuses |
| `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | public / any | accounts + bearer token (`admin` cannot self-register) |
| `GET/PUT /profile` | entrepreneur | typed profile (`age: int`, amounts as numbers) |
| `GET /schemes`, `GET /schemes/matches` | any / entrepreneur | catalogue; every scheme classified against the profile, best first |
| `POST/PUT/DELETE /schemes[/{id}]` | admin | manage schemes (fixed schema; validated) |
| `GET /documents`, `POST /documents/upload`, `GET /documents/{id}/file`, `DELETE /documents/{id}` | entrepreneur | multipart upload, private download |
| `GET /partners`, `GET /partners/nearby?lat&lng&radius_km` | any | directory filters; geospatial locator (haversine) |
| `POST/DELETE /partners[/{id}]` | admin | manage partners |
| `GET/POST /applications`, `PATCH/DELETE /applications/{id}` | entrepreneur | tracking, `scheme_id` + validated `status` |
| `GET /readiness` | entrepreneur | 100-point score with per-category breakdown |
| `POST /tools/emi`, `POST /tools/what-if`, `GET /tools/funding-path` | entrepreneur | calculators, run server-side |
| `GET /admin/users` | admin | account list (never includes hashes) |

## Key renames (old frontend -> API)

| Old | New |
|---|---|
| `fullName, income, turnover, funding, ownContribution, purpose` (strings) | `full_name, annual_income, annual_turnover, funding_required, own_contribution, funding_purpose` (numbers) |
| `businessType, businessStage` | `business_type, business_stage` |
| `documents["Income Certificate"]` + Base64 `documentData` | `{type:"income_certificate", status:"uploaded"/"missing", document_id}` + file stored on the server |
| scheme `min, max, cats, types, stages, ageMin, income, ownContributionPct, channel, docs, url` | `min_amount, max_amount, eligible_categories, business_types, business_stages, min_age, max_income, own_contribution_pct, application_channel, required_documents, official_url` |
| partner `{state, coverage, schemes}` | `state, district, latitude, longitude, supported_scheme_ids` (+ `partner_type`, `website_url`) |
| application `ref, created ("DD/MM/YYYY"), status ("Documents Pending")` | `application_reference, created_at` (ISO UTC), `status: "documents_pending"` |
| `currentUser` (e-mail), `session.role` | `user_id` from the token; role read from the database |
| `fundingPath()` text labels | `{source, scheme_id, amount, reason}` |

## Before deploying

- Set `ENVIRONMENT=production` and a random `SECRET_KEY` (32+ chars) — the app refuses to start otherwise.
- Set `SEED_DEMO_USER=false` and `ADMIN_PASSWORD` (or create the admin another way); set `DEMO.enabled=false` in `index.html`.
- Use PostgreSQL and Alembic migrations instead of `create_all()`; keep uploads on durable storage (volume / S3).
- Serve over HTTPS and set `CORS_ORIGINS` to the exact frontend origin(s).
- Limit request body size at the reverse proxy (e.g. nginx `client_max_body_size 6m`); the API enforces 5 MB per document after receipt.
- Login throttling is in-memory per process — use Redis or your API gateway when running several workers.
- Access tokens last 60 minutes and there is no refresh flow yet; users simply log in again.
- Partner coordinates in the seed are **approximate demo values** — replace them with real branch locations.
