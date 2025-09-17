#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:8000"

# calcola il lunedì di questa settimana (formato YYYY-MM-DD)
TODAY=$(date +%F)
DOW=$(date +%u)              # 1=lun ... 7=dom
OFFSET=$(( DOW-1 ))          # giorni da togliere per arrivare al lunedì
WEEK_START=$(date -d "$TODAY -$OFFSET day" +%F)

echo "▶ /health"
curl -sS $BASE/health; echo

echo "▶ /users/demo"
curl -sS -X POST $BASE/users/demo; echo

echo "▶ Inserisco pesate demo (78.6, 78.4)"
curl -sS -X POST $BASE/weight -H 'Content-Type: application/json' -d '{"kg":78.6}' >/dev/null
curl -sS -X POST $BASE/weight -H 'Content-Type: application/json' -d '{"kg":78.4}' >/dev/null
echo "ok"

echo "▶ Inserisco 2 pasti demo"
curl -sS -X POST $BASE/meals -H 'Content-Type: application/json' \
  -d '{"items":[{"food_name":"Riso","grams":120,"pro":7,"carb":80,"fat":0.6},{"food_name":"Pollo","grams":150,"pro":31,"carb":0,"fat":3}]}' >/dev/null
curl -sS -X POST $BASE/meals -H 'Content-Type: application/json' \
  -d '{"items":[{"food_name":"Yogurt","grams":150,"pro":6,"carb":8,"fat":3},{"food_name":"Banana","grams":120,"pro":1.5,"carb":27,"fat":0.3}]}' >/dev/null
echo "ok"

echo "▶ Inserisco 1 workout demo"
curl -sS -X POST $BASE/workouts -H 'Content-Type: application/json' \
  -d '{"sets":[{"exercise":"Panca piana","reps":8,"weight_kg":70},{"exercise":"Rematore","reps":8,"weight_kg":60}]}' >/dev/null
echo "ok"

echo "▶ /meals/today"
curl -sS $BASE/meals/today; echo

echo "▶ /summary/day?date=$TODAY"
curl -sS "$BASE/summary/day?date=$TODAY"; echo

echo "▶ /summary/week?start=$WEEK_START"
curl -sS "$BASE/summary/week?start=$WEEK_START"; echo

echo "▶ /check/weekly?start=$WEEK_START&protein_target_g=120&kcal_target=2300&min_workouts=3"
curl -sS "$BASE/check/weekly?start=$WEEK_START&protein_target_g=120&kcal_target=2300&min_workouts=3"; echo

echo "▶ /weights/all"
curl -sS $BASE/weights/all; echo

echo "▶ /weights/weekly"
curl -sS $BASE/weights/weekly; echo

echo "▶ /weights/trend"
curl -sS $BASE/weights/trend; echo

echo "✅ Test v2 completato"
