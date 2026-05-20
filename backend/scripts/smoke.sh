#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://localhost:8080/api}"
USERNAME="${USERNAME:-testadmin}"
PASSWORD="${PASSWORD:-testpass123}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

wait_for_backend() {
  retries="${SMOKE_RETRIES:-30}"
  delay="${SMOKE_DELAY_SECONDS:-2}"
  while [ "$retries" -gt 0 ]; do
    if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
      return 0
    fi
    retries=$((retries - 1))
    sleep "$delay"
  done
  echo "FAIL backend did not become ready at $BASE_URL/health"
  exit 1
}

request() {
  method="$1"
  path="$2"
  expected="$3"
  data="${4:-}"
  auth_token="${5:-}"
  body_file="$tmp_dir/body.json"

  if [ -n "$data" ] && [ -n "$auth_token" ]; then
    status="$(curl -sS -o "$body_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" -H "Content-Type: application/json" -H "Authorization: Bearer $auth_token" --data "$data")"
  elif [ -n "$data" ]; then
    status="$(curl -sS -o "$body_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" -H "Content-Type: application/json" --data "$data")"
  elif [ -n "$auth_token" ]; then
    status="$(curl -sS -o "$body_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" -H "Authorization: Bearer $auth_token")"
  else
    status="$(curl -sS -o "$body_file" -w "%{http_code}" -X "$method" "$BASE_URL$path")"
  fi

  if [ "$status" != "$expected" ]; then
    echo "FAIL $method $path expected $expected got $status"
    cat "$body_file"
    exit 1
  fi
}

wait_for_backend
request GET /health 200
request GET /auth/me 401

login_body="$tmp_dir/login.json"
login_status="$(curl -sS -o "$login_body" -w "%{http_code}" -X POST "$BASE_URL/auth/login" -H "Content-Type: application/json" --data "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")"
if [ "$login_status" != "200" ]; then
  echo "FAIL POST /auth/login expected 200 got $login_status"
  cat "$login_body"
  exit 1
fi

token="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1]))["access_token"])' "$login_body")"

request GET /dashboard 200 "" "$token"

integration_body="$tmp_dir/integration.json"
integration_status="$(curl -sS -o "$integration_body" -w "%{http_code}" -X POST "$BASE_URL/integrations" -H "Content-Type: application/json" -H "Authorization: Bearer $token" --data '{"name":"Smoke MQTT","domain":"mqtt","config":{"source":"smoke","host":"mock-broker"}}')"
if [ "$integration_status" != "201" ]; then
  echo "FAIL POST /integrations expected 201 got $integration_status"
  cat "$integration_body"
  exit 1
fi
integration_id="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$integration_body")"
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); assert body["domain"] == "mqtt", body' "$integration_body"

discovery_body="$tmp_dir/discovery.json"
discovery_status="$(curl -sS -o "$discovery_body" -w "%{http_code}" "$BASE_URL/integrations/$integration_id/discovery" -H "Authorization: Bearer $token")"
if [ "$discovery_status" != "200" ]; then
  echo "FAIL GET /integrations/$integration_id/discovery expected 200 got $discovery_status"
  cat "$discovery_body"
  exit 1
fi
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); strip=next(item for item in body if item["discovered_id"] == "mqtt.living_room_strip"); assert strip["entities"][0]["platform"] == "mqtt", body; assert strip["entities"][0]["attributes"]["command_topic"] == "home/living_room/strip/set", body' "$discovery_body"

import_body="$tmp_dir/import.json"
import_status="$(curl -sS -o "$import_body" -w "%{http_code}" -X POST "$BASE_URL/integrations/$integration_id/import" -H "Content-Type: application/json" -H "Authorization: Bearer $token" --data '{"discovered_ids":["mqtt.living_room_strip"]}')"
if [ "$import_status" != "200" ]; then
  echo "FAIL POST /integrations/$integration_id/import expected 200 got $import_status"
  cat "$import_body"
  exit 1
fi
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); assert body["imported"] + len(body["skipped"]) == 1, body' "$import_body"

mqtt_action_body="$tmp_dir/mqtt-action.json"
mqtt_action_status="$(curl -sS -o "$mqtt_action_body" -w "%{http_code}" -X POST "$BASE_URL/actions/call" -H "Content-Type: application/json" -H "Authorization: Bearer $token" --data '{"domain":"light","action":"turn_on","target":{"entity_id":"light.mqtt_living_room_strip"},"data":{"brightness":60}}')"
if [ "$mqtt_action_status" != "200" ]; then
  echo "FAIL POST /actions/call expected 200 got $mqtt_action_status"
  cat "$mqtt_action_body"
  exit 1
fi
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); assert body["new_state"] == "on", body; assert body["attributes"]["brightness"] == 60, body' "$mqtt_action_body"

devices_body="$tmp_dir/devices.json"
devices_status="$(curl -sS -o "$devices_body" -w "%{http_code}" "$BASE_URL/devices?type=light" -H "Authorization: Bearer $token")"
if [ "$devices_status" != "200" ]; then
  echo "FAIL GET /devices?type=light expected 200 got $devices_status"
  cat "$devices_body"
  exit 1
fi
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); assert any(item["name"] == "MQTT Living Room Strip" for item in body), body' "$devices_body"

request PATCH /entities/binary_sensor.hallway_motion/state 200 '{"state":"on"}' "$token"

entity_body="$tmp_dir/entity.json"
entity_status="$(curl -sS -o "$entity_body" -w "%{http_code}" "$BASE_URL/entities/light.hallway" -H "Authorization: Bearer $token")"
if [ "$entity_status" != "200" ]; then
  echo "FAIL GET /entities/light.hallway expected 200 got $entity_status"
  cat "$entity_body"
  exit 1
fi
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); assert body["state"] == "on", body' "$entity_body"

events_body="$tmp_dir/events.json"
events_status="$(curl -sS -o "$events_body" -w "%{http_code}" "$BASE_URL/events?limit=3" -H "Authorization: Bearer $token")"
if [ "$events_status" != "200" ]; then
  echo "FAIL GET /events?limit=3 expected 200 got $events_status"
  cat "$events_body"
  exit 1
fi
"$PYTHON_BIN" -c 'import json,sys; body=json.load(open(sys.argv[1])); assert any(item["source"] == "automation" for item in body["events"]), body' "$events_body"

echo "Smoke checks passed for $BASE_URL"
