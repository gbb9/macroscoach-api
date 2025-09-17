#!/usr/bin/env bash
set -euo pipefail
BASE="http://localhost:8000"

curl -sS -X POST $BASE/users/demo >/dev/null

# 3 pesate
for KG in 78.9 78.6 78.4; do
  curl -sS -X POST $BASE/weight -H 'Content-Type: application/json' -d "{\"kg\":$KG}" >/dev/null
done

# 2 pasti
curl -sS -X POST $BASE/meals -H 'Content-Type: application/json' \
  -d '{"items":[{"food_name":"Yogurt","grams":150,"pro":6,"carb":8,"fat":3},{"food_name":"Miele","grams":15,"pro":0,"carb":82,"fat":0}]}' >/dev/null

curl -sS -X POST $BASE/meals -H 'Content-Type: application/json' \
  -d '{"items":[{"food_name":"Riso","grams":120,"pro":7,"carb":80,"fat":0.6},{"food_name":"Petto di pollo","grams":150,"pro":31,"carb":0,"fat":3}]}'>/dev/null

# 1 workout
curl -sS -X POST $BASE/workouts -H 'Content-Type: application/json' \
  -d '{"sets":[{"exercise":"Lat machine","reps":10,"weight_kg":50},{"exercise":"Rematore","reps":8,"weight_kg":60}]}' >/dev/null

echo "✅ Dati demo inseriti"
