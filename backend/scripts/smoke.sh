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
