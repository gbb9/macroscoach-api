#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:8000"
TODAY=$(date +%F)

echo "▶ /health"
curl -sS "$BASE/health"; echo

echo "▶ /users/demo"
RESP=$(curl -sS -X POST "$BASE/users/demo")
echo "$RESP"
TOKEN=$(printf '%s' "$RESP" | python3 - <<'PYJSON'
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    data = {}
print(data.get('access_token', ''))
PYJSON
)
if [ -z "$TOKEN" ]; then
  echo "❌ token non ricevuto" >&2
  exit 1
fi
AUTH_HEADER="Authorization: Bearer $TOKEN"

echo "▶ /weight (78.4 kg)"
curl -sS -X POST "$BASE/weight"   -H 'Content-Type: application/json'   -H "$AUTH_HEADER"   -d '{"kg":78.4}'; echo

echo "▶ /meals (pasto di prova)"
curl -sS -X POST "$BASE/meals"   -H 'Content-Type: application/json'   -H "$AUTH_HEADER"   -d '{"items":[{"food_name":"Pasta","grams":100,"pro":12,"carb":72,"fat":1.5},{"food_name":"Olio EVO","grams":10,"pro":0,"carb":0,"fat":100}]}'   ; echo

echo "▶ /workouts (2 set)"
curl -sS -X POST "$BASE/workouts"   -H 'Content-Type: application/json'   -H "$AUTH_HEADER"   -d '{"sets":[{"exercise":"Panca piana","reps":8,"weight_kg":70},{"exercise":"Squat","reps":6,"weight_kg":90}]}'   ; echo

echo "▶ /meals/today"
curl -sS -H "$AUTH_HEADER" "$BASE/meals/today"; echo

echo "▶ /summary/day?date=$TODAY"
curl -sS -H "$AUTH_HEADER" "$BASE/summary/day?date=$TODAY"; echo

echo "▶ /weights/all"
curl -sS -H "$AUTH_HEADER" "$BASE/weights/all"; echo

echo "▶ /workouts/all"
curl -sS -H "$AUTH_HEADER" "$BASE/workouts/all"; echo

echo "✅ Smoke test completato"
