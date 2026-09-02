#!/usr/bin/env bash
# Smoke test for the trained soil model + empirical NDVI bands.
#
# Requires the backend to be running on $API_BASE (default localhost:8000).
# Run:
#   bash ml/smoke_test.sh
#
# Exits non-zero if any check fails.

set -euo pipefail

API="${API_BASE:-http://127.0.0.1:8000}"
PASS=0; FAIL=0
hr() { printf '\n--- %s ---\n' "$*"; }
ok() { echo "  ✓ $*"; PASS=$((PASS+1)); }
nok() { echo "  ✗ $*"; FAIL=$((FAIL+1)); }

hr "1. server health"
H=$(curl -fsSL "$API/api/health")
echo "$H" | python3 -m json.tool
DB_OK=$(echo "$H" | python3 -c "import json,sys; print(json.load(sys.stdin)['database_ok'])")
[[ "$DB_OK" == "True" ]] && ok "DB reachable" || nok "DB unreachable"

hr "2. register + login a test user"
EMAIL="smoke-$(date +%s)@example.com"
curl -fsS -X POST "$API/api/auth/register" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"hunter22\",\"full_name\":\"Smoke Test\"}" \
  -o /tmp/smoke_reg.json
ok "registered $EMAIL"

TOKEN=$(curl -fsS -X POST "$API/api/auth/login-json" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"hunter22\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
ok "got JWT"

hr "3. model info (proves trained model is loaded)"
INFO=$(curl -fsSL "$API/api/model/info" -H "authorization: Bearer $TOKEN")
echo "$INFO" | python3 -m json.tool | head -30
N=$(echo "$INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['n_samples'])")
SRC=$(echo "$INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['source'])")
CV=$(echo "$INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['cv_accuracy_5fold'])")
[[ "$N" == "10000" ]] && ok "model trained on 10K real samples" || nok "n_samples wrong: $N"
[[ "$SRC" == *"Smart-Agriculture"* ]] && ok "source is real Smart-Agriculture dataset" || nok "source wrong: $SRC"
python3 -c "import sys; sys.exit(0 if float('$CV') >= 0.99 else 1)" && ok "CV acc >= 0.99 ($CV)" || nok "CV acc too low: $CV"

hr "4. score a few readings through the trained tree"
score() {
  local name="$1" ph="$2" t="$3" m="$4" ec="$5" expected="$6"
  local out
  out=$(curl -fsS -X POST "$API/api/model/score" \
    -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d "{\"ph\":$ph,\"temperature\":$t,\"moisture\":$m,\"ec\":$ec}")
  local action
  action=$(echo "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['action'])")
  if [[ "$action" == "$expected" ]]; then
    ok "$name -> action=$action (expected $expected)"
  else
    nok "$name -> action=$action (expected $expected)"
  fi
}
score "dry + low EC"     6.5 24 25 1.0 0
score "moist + low EC"   6.8 26 65 1.5 0
score "dry + high EC"    7.0 28 30 4.5 3
score "fertigation safe" 6.7 22 30 2.0 0

hr "5. create a wheat field + refresh satellite"
curl -fsS -X POST "$API/api/fields" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"Smoke Field","crop_type":"wheat","planting_date":"2026-07-01","lat":28.45,"lon":77.02}' \
  -o /tmp/smoke_field.json
FID=$(python3 -c "import json; print(json.load(open('/tmp/smoke_field.json'))['id'])")
ok "field created id=$FID"

OBS=$(curl -fsS -X POST "$API/api/fields/$FID/satellite/refresh" -H "authorization: Bearer $TOKEN")
echo "$OBS" | python3 -m json.tool | head -20
NDVI=$(echo "$OBS" | python3 -c "import json,sys; print(json.load(sys.stdin)['ndvi'])")
STATUS=$(echo "$OBS" | python3 -c "import json,sys; print(json.load(sys.stdin)['health_status'])")
[[ -n "$NDVI" && "$NDVI" != "None" ]] && ok "satellite refresh returned NDVI=$NDVI, status=$STATUS" || nok "satellite refresh returned no NDVI"

hr "6. health endpoint uses empirical bands"
H=$(curl -fsSL "$API/api/fields/$FID/health" -H "authorization: Bearer $TOKEN")
echo "$H" | python3 -m json.tool
ST=$(echo "$H" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
RSN=$(echo "$H" | python3 -c "import json,sys; r=json.load(sys.stdin)['reason']; print(r[:120])")
ok "field health: status=$ST, reason: $RSN"
python3 -c "import sys; sys.exit(0 if '$ST' in ('healthy','moderate','high_stress','unknown') else 1)" && ok "valid status enum" || nok "bad status: $ST"

hr "summary"
echo "  passed: $PASS"
echo "  failed: $FAIL"
[[ $FAIL -eq 0 ]] && { echo "✓ SMOKE TEST PASSED"; exit 0; } \
                  || { echo "✗ SMOKE TEST FAILED"; exit 1; }
