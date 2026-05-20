# Smart Home MVP Backend

This repository is the backend-only MVP for a Smart Home system. The current scope is FastAPI, PostgreSQL, seed data, integration tests, Docker compose, and API contracts for a future frontend.

Do not generate or scaffold a frontend in this phase. Do not add UI dependencies.

## Project Shape

- Backend app: `backend/app`
- Tests: `backend/tests`
- Compose entrypoint from repo root: `docker compose ...`
- API base path: `/api`
- Seed credentials: `testadmin / testpass123`

Main domain entities:

- `Home`
- `Area`
- `Device`
- `Entity`
- `EntityState`
- `Event`
- `Automation`
- `AutomationRun`
- `EnergyReading`

Architecture flow:

```text
FastAPI API routers -> services -> SQLAlchemy models -> PostgreSQL -> event bus / SSE
```

The backend uses mock/demo integrations, mock sensor updates, seeded energy readings, and a mock energy forecast. PostgreSQL and Docker are the required integration target.

Known constraints:

- Integrations are mock/demo only.
- Energy forecast is mock data based on recent readings.
- Frontend is not present.
- `localhost:5432` on a host machine can point to a local PostgreSQL instead of Docker PostgreSQL. The reliable integration target is the Docker network through compose.

## Commands

From the repository root:

```bash
docker compose up --build
```

Backend API:

```text
http://localhost:8080/api
```

Swagger:

```text
http://localhost:8080/docs
```

Local verification:

```bash
backend/.venv/bin/python -m compileall backend/app backend/tests
backend/.venv/bin/pytest -q
docker compose run --rm backend pytest -q
docker compose up --build -d
backend/scripts/smoke.sh
docker compose down
```

CI-friendly local gate:

```bash
backend/scripts/verify.sh
```

## How To Work Safely

- Keep public `/api/...` paths and response shapes stable unless the task explicitly requires a breaking API change.
- Keep the current work backend-only; do not create frontend files or install UI dependencies.
- Before and after backend changes, run compile, pytest, and Docker smoke when available.
- Do not commit `.venv`, `.pytest_cache`, `__pycache__`, or `.env`.
- Prefer adding focused tests before changing shared behavior.
- Preserve the error response shape: `{ "error": "...", "message": "..." }`.
