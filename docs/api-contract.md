# Smart Home MVP API Contract

Base URL: `/api`

All endpoints except `GET /health` and `POST /auth/login` require `Authorization: Bearer <jwt>`.

Errors use this JSON shape:

```json
{ "error": "not_found", "message": "Resource not found" }
```

Known error codes include `bad_request`, `unauthorized`, `forbidden`, `not_found`, `conflict`, `validation_error`, and `error`.

## Auth

- `POST /auth/login`
  - Body: `{ "username": "testadmin", "password": "testpass123" }`
  - Response: `{ "access_token": string, "token_type": "bearer", "expires_in": number, "user": User }`
- `POST /auth/logout`
  - Response: `{ "ok": true }`
- `GET /auth/me`
  - Response: `User` with `created_at`

## Homes

- `GET /homes`
  - Response: `Home[]`
- `POST /homes`
  - Body: `name`, optional `time_zone`, nullable `latitude`, nullable `longitude`, optional `currency`
  - Response: `Home`

## Integrations

- `GET /integrations`
  - Response: `Integration[]`
- `POST /integrations`
  - Body: `name`, optional `domain`, optional `config`
  - Response: `Integration`
- `GET /integrations/{integration_id}`
  - Response: `Integration`
- `PATCH /integrations/{integration_id}`
  - Body: partial `name`, `config`
  - Response: `Integration`
- `DELETE /integrations/{integration_id}`
  - Response: `204`
- `GET /integrations/{integration_id}/discovery`
  - Response: deterministic mock discovery rows with `discovered_id`, `suggested_entity_id`, `entities`, and `already_imported`
- `POST /integrations/{integration_id}/import`
  - Body: optional `{ "discovered_ids": string[] }`; omitted imports all discovered items
  - Response: `{ "integration_id": uuid, "imported": number, "skipped": SkippedDiscovery[], "devices": Device[] }`

Integration includes `config`, `device_count`, and ISO datetime fields. Supported onboarding domain is `demo`. Re-importing an already imported discovered device is idempotent and reports it in `skipped`.

## Areas

- `GET /areas`
  - Response: `Area[]`
- `POST /areas`
  - Body: `name`, nullable `icon`, `floor_id`, `temperature_entity_id`, `humidity_entity_id`
  - Response: `Area`
- `PATCH /areas/{area_id}`
  - Body: partial area fields
  - Response: `Area`
- `DELETE /areas/{area_id}`
  - Response: `204`

Area includes `device_count`, `entity_count`, nullable floor and sensor entity references, and ISO datetime fields.

## Devices

- `GET /devices`
  - Query: optional `area_id`, `type`, `status`
  - Response: compact `Device[]`
- `POST /devices`
  - Body: `name`, `type`, nullable `area_id`, nullable `manufacturer`, nullable `model`
  - Response: detailed `Device` with generated default `entities`
- `GET /devices/{device_id}`
  - Response: detailed `Device`
- `PATCH /devices/{device_id}`
  - Body: partial device fields
  - Response: detailed `Device`
- `DELETE /devices/{device_id}`
  - Response: `204`

Device nullable fields include `name_by_user`, `manufacturer`, `model`, `area_id`, and `area_name`.

## Entities

- `GET /entities`
  - Query: optional `domain`, `area_id`, `device_id`
  - Response: `Entity[]`
- `GET /entities/{entity_id}`
  - Response: `Entity`
- `PATCH /entities/{entity_id}/state`
  - Body: `{ "state": string, "attributes": object }`
  - Response: `{ "entity_id": string, "state": string, "attributes": object, "last_changed": datetime }`
- `GET /entities/{entity_id}/history`
  - Query: optional `from`, `to`
  - Response: state history rows with datetime fields

Entity nullable fields include `device_id`, `area_id`, `unit_of_measurement`, and `device_class`.

## Actions

- `POST /actions/call`
  - Body: `{ "domain": string, "action": string, "target": object, "data": object }`
  - Response: `{ "ok": true, "entity_id": string, "new_state": string, "attributes": object }`

Supported mock domains include `light`, `switch`, and `climate`. Sensor entities are read-only.

## Automations

- `GET /automations`
  - Response: `Automation[]`
- `POST /automations`
  - Body: `name`, optional `description`, optional `is_enabled`, optional `mode`, `trigger`, nullable `condition`, `action`
  - Response: `Automation`
- `GET /automations/{automation_id}`
  - Response: `Automation`
- `PATCH /automations/{automation_id}`
  - Body: partial automation fields
  - Response: `Automation`
- `DELETE /automations/{automation_id}`
  - Response: `204`
- `POST /automations/{automation_id}/run`
  - Response: `{ "ok": true, "run_id": uuid, "automation_id": uuid, "triggered_at": datetime }`

Automation events use `event_type: "automation_triggered"`, `source: "automation"`, nullable `entity_id`, and metadata such as `{ "triggered_by": "state_changed:binary_sensor.hallway_motion" }`.

## Events And SSE

- `GET /events`
  - Query: optional `entity_id`, `device_id`, `from`, `to`, `limit`, `offset`
  - Pagination: `limit` is clamped to `1..200`; `offset` is clamped to `>= 0`
  - Response: `{ "total": number, "limit": number, "offset": number, "events": Event[] }`
- `GET /events/stream`
  - Server-sent events stream. Data payload is JSON serialized from domain events.

Event nullable fields include `entity_id`, `old_state`, `new_state`, `user_id`, and `automation_id`.

## Energy

- `GET /energy/summary`
  - Query: optional `period`
  - Response keys: `period`, `total_kwh`, `total_cost`, `currency`, `current_power_w`, `peak_power_w`, `device_count`, `date_from`, `date_to`
- `GET /energy/consumption`
  - Query: optional `period`, optional `granularity`
  - Response: `{ "period": string, "granularity": string, "data": ConsumptionPoint[] }`
- `GET /energy/devices`
  - Query: optional `period`
  - Response: per-device energy rows, optionally including `anomaly_reason`
- `GET /energy/forecast`
  - Response: `{ "period_hours": 24, "forecast": ForecastPoint[], "total_predicted_kwh": number, "confidence": "mock" }`

## Dashboard

- `GET /dashboard`
  - Response keys: `home`, `areas`, `summary`, `recent_events`
  - Summary keys: `devices_total`, `devices_online`, `automations_active`, `energy_today_kwh`, `current_power_w`
  - Area cards include nullable `temperature` and `humidity`.
