#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_TOKEN="${API_TOKEN:-dev-token-1}"

hdr_auth="Authorization: Bearer ${API_TOKEN}"
hdr_json="Content-Type: application/json"

echo "Base URL: ${BASE_URL}"
echo "Token:    ${API_TOKEN}"
echo

# 1) Create experiment
echo "==> Creating experiment..."
payload='{
  "name": "CTA Test Demo",
  "description": "Demo experiment created by scripts/demo.sh",
  "variants": [
    { "key": "control", "allocation_percent": 50, "metadata": { "note": "baseline" } },
    { "key": "treatment", "allocation_percent": 50, "metadata": { "note": "new CTA" } }
  ]
}'

exp_json="$(curl -sS -X POST "${BASE_URL}/experiments" -H "${hdr_auth}" -H "${hdr_json}" -d "${payload}")"
exp_id="$(echo "${exp_json}" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])')"

echo "Created experiment_id: ${exp_id}"
echo

# 2) Idempotent assignment
user="user_demo_123"
echo "==> Getting assignment for ${user} (first call)..."
a1="$(curl -sS "${BASE_URL}/experiments/${exp_id}/assignment/${user}" -H "${hdr_auth}")"
v1="$(echo "${a1}" | python -c 'import sys,json; print(json.load(sys.stdin)["variant_id"])')"
k1="$(echo "${a1}" | python -c 'import sys,json; print(json.load(sys.stdin)["variant_key"])')"
echo "Assigned variant: ${k1} (${v1})"

echo "==> Getting assignment for ${user} (second call, should match)..."
a2="$(curl -sS "${BASE_URL}/experiments/${exp_id}/assignment/${user}" -H "${hdr_auth}")"
v2="$(echo "${a2}" | python -c 'import sys,json; print(json.load(sys.stdin)["variant_id"])')"
k2="$(echo "${a2}" | python -c 'import sys,json; print(json.load(sys.stdin)["variant_key"])')"
echo "Assigned variant: ${k2} (${v2})"

if [[ "${v1}" != "${v2}" ]]; then
  echo "Idempotency failed: variant_id changed!"
  exit 1
fi
echo "Idempotency OK"
echo

# 3) Record events (requires user assignment in some implementations)
now="$(python -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat())')"

echo "==> Recording events..."
ev_click="$(cat <<EOF
{
  "experiment_id": "${exp_id}",
  "user_id": "${user}",
  "type": "click",
  "timestamp": "${now}",
  "properties": { "button": "cta", "page": "landing" }
}
EOF
)"

ev_purchase="$(cat <<EOF
{
  "experiment_id": "${exp_id}",
  "user_id": "${user}",
  "type": "purchase",
  "timestamp": "${now}",
  "properties": { "amount": 49.99, "currency": "USD" }
}
EOF
)"

e1="$(curl -sS -X POST "${BASE_URL}/events" -H "${hdr_auth}" -H "${hdr_json}" -d "${ev_click}")"
id1="$(echo "${e1}" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])')"
echo "  click event id: ${id1}"

e2="$(curl -sS -X POST "${BASE_URL}/events" -H "${hdr_auth}" -H "${hdr_json}" -d "${ev_purchase}")"
id2="$(echo "${e2}" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])')"
echo "  purchase event id: ${id2}"
echo

# 4) Results endpoint
echo "==> Fetching results (event_type=click)..."
curl -sS "${BASE_URL}/experiments/${exp_id}/results?event_type=click" -H "${hdr_auth}" | python -m json.tool
echo

echo "==> Fetching results (event_type=purchase)..."
curl -sS "${BASE_URL}/experiments/${exp_id}/results?event_type=purchase" -H "${hdr_auth}" | python -m json.tool
echo

echo "Done."
