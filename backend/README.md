# Smart Home MVP Backend

FastAPI backend for the Smart Home MVP. It implements PostgreSQL storage, Alembic migrations, seed data, JWT auth, device/entity CRUD, actions, events, SSE, automations, energy endpoints, and dashboard aggregation.

## Run

```bash
docker compose up --build
```

Backend: `http://localhost:8080/api`

Swagger: `http://localhost:8080/docs`

Credentials:

```text
testadmin / testpass123
```

## Environment

Copy `backend/.env.example` to `backend/.env` for local overrides.

Key variables:

- `DATABASE_URL`: async SQLAlchemy URL.
- `JWT_SECRET`: JWT signing secret.
- `JWT_EXPIRES_SECONDS`: token lifetime, default `86400`.
- `SEED_ENABLED`: idempotent seed on startup.
- `SIM_ENABLED`: background mock sensor updates.
- `CORS_ORIGINS`: comma-separated origins or `*`.

## API Overview

Base URL: `http://localhost:8080/api`

- `GET /health`
- `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
- `GET|POST /homes`
- `GET|POST /integrations`, `GET|PATCH|DELETE /integrations/{id}`, `GET /integrations/{id}/discovery`, `POST /integrations/{id}/import`
- `GET|POST /areas`, `PATCH|DELETE /areas/{id}`
- `GET|POST /devices`, `GET|PATCH|DELETE /devices/{id}`
- `GET /entities`, `GET /entities/{entity_id}`, `PATCH /entities/{entity_id}/state`, `GET /entities/{entity_id}/history`
- `POST /actions/call`
- `GET /events`, `GET /events/stream`
- `GET|POST /automations`, `GET|PATCH|DELETE /automations/{id}`, `POST /automations/{id}/run`
- `GET /energy/summary`, `/energy/consumption`, `/energy/devices`, `/energy/forecast`
- `GET /dashboard`

All endpoints except `/api/health` and `/api/auth/login` require `Authorization: Bearer <jwt>`.

## Verification

From the repository root:

```bash
python -m compileall backend/app backend/tests
backend/.venv/bin/pytest -q
docker compose up --build -d
backend/scripts/smoke.sh
docker compose down
```

Expected results:

- `compileall` completes without syntax errors.
- `pytest` passes unit and PostgreSQL-backed API integration tests. Start PostgreSQL first with `docker compose up -d postgres` if your local database is not already running.
- `smoke.sh` prints `Smoke checks passed for http://localhost:8080/api`.
- The smoke flow verifies `GET /api/health` returns `200`, unauthenticated `GET /api/auth/me` returns `401`, login returns a JWT, `GET /api/dashboard` returns seeded data, mock integration discovery/import works, motion turns `light.hallway` on, and recent events include an automation event.

## MVP Limits

There are no real Zigbee/Z-Wave/MQTT integrations. Integration onboarding uses deterministic mock discovery/import data. Energy readings, sensor changes, and forecast are deterministic/mock data. Forecast returns `confidence: "mock"` and repeats recent readings.
