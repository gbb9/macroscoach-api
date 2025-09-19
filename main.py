from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from passlib.hash import bcrypt
from zoneinfo import ZoneInfo

from db import Base, engine, get_db
from models import (
    User,
    Food,
    Meal,
    MealItem,
    Workout,
    Set,
    WeightLog,
    RecentFood,
    UserPlan,
    UserDistribution,
    DistributionTarget,
    UserDayMode,
)
from schemas import (
    MealIn, WeightIn, WorkoutIn, PlanPayload, MealUpdate,
    SchedulePayload, FoodSearchOut, FoodConfirmIn,
    RegisterIn, LoginIn, TokenOut, MeOut
)

load_dotenv()
app = FastAPI(title="MacrosCoach API")

# ---------------- CORS (dev: all) ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in prod: limita ai tuoi domini/app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DB init ----------------
Base.metadata.create_all(bind=engine)

# ---------------- Auth utils ----------------
SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGO = "HS256"
ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_MIN", "60"))

def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MINUTES),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
        uid = int(data.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    return u

# ---------------- Health ----------------
@app.get("/health")
def health():
    return {"ok": True}

# ---------------- Auth ----------------
@app.post("/auth/register", response_model=TokenOut)
def auth_register(payload: RegisterIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=payload.email).first()
    if u:
        raise HTTPException(status_code=400, detail="Email già registrata")
    u = User(email=payload.email, password_hash=bcrypt.hash(payload.password), timezone=payload.timezone or "Europe/Rome")
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"access_token": create_access_token(u)}

@app.post("/auth/login", response_model=TokenOut)
def auth_login(payload: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=payload.email).first()
    if not u or not u.password_hash or not bcrypt.verify(payload.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    return {"access_token": create_access_token(u)}

@app.get("/users/me", response_model=MeOut)
def users_me(current: User = Depends(get_current_user)):
    return {"id": current.id, "email": current.email, "timezone": current.timezone}

# ---------------- Demo ----------------
@app.post("/users/demo")
def create_demo_user(db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email="demo@example.com").first()
    if not u:
        u = User(email="demo@example.com", password_hash=bcrypt.hash("demo"), timezone="Europe/Rome")
        db.add(u)
        db.commit()
        db.refresh(u)
    return {"user_id": u.id, "access_token": create_access_token(u)}

# ---------------- Barcode / OFF lookup ----------------
@app.get("/foods/barcode/{code}")
def food_by_barcode(code: str):
    def extract_payload(p):
        if not p:
            return None
        nutr = p.get("nutriments", {}) or {}
        kcal = nutr.get("energy-kcal_100g")
        if kcal is None:
            energy_kj = nutr.get("energy_100g")
            if energy_kj is not None:
                try:
                    kcal = float(energy_kj) / 4.184
                except Exception:
                    kcal = None

        def fget(k):
            v = nutr.get(k)
            try:
                return None if v is None else float(v)
            except Exception:
                return None

        name = p.get("product_name") or p.get("brands") or p.get("generic_name") or "Prodotto"
        return {
            "name": name,
            "per_100g": {
                "kcal": None if kcal is None else round(kcal, 1),
                "pro": fget("proteins_100g"),
                "carb": fget("carbohydrates_100g"),
                "fat": fget("fat_100g"),
            },
        }

    # 1) v2 /product
    try:
        r = requests.get(f"https://world.openfoodfacts.org/api/v2/product/{code}.json", timeout=10)
        j = r.json()
        if j.get("status") == 1 and "product" in j:
            out = extract_payload(j["product"])
            if out:
                return out
    except requests.RequestException:
        pass

    # 2) v0 /product
    try:
        r0 = requests.get(f"https://world.openfoodfacts.org/api/v0/product/{code}.json", timeout=10)
        j0 = r0.json()
        if j0.get("status") == 1 and "product" in j0:
            out = extract_payload(j0["product"])
            if out:
                return out
    except requests.RequestException:
        pass

    # 3) v2 /search?code=
    try:
        rs2 = requests.get(f"https://world.openfoodfacts.org/api/v2/search?code={code}&page_size=1", timeout=10)
        js2 = rs2.json()
        prods = js2.get("products", []) or []
        if prods:
            out = extract_payload(prods[0])
            if out:
                return out
    except requests.RequestException:
        pass

    # 4) legacy CGI search
    try:
        rl = requests.get(
            f"https://world.openfoodfacts.org/cgi/search.pl?search_simple=1&json=1&code={code}&page_size=1",
            timeout=10,
        )
        jl = rl.json()
        prods = jl.get("products", []) or []
        if prods:
            out = extract_payload(prods[0])
            if out:
                return out
    except requests.RequestException:
        pass

    raise HTTPException(status_code=404, detail=f"Barcode non trovato su OFF (code={code})")

@app.get("/barcode/search")
def barcode_search(code: str):
    return food_by_barcode(code)

# ---------------- Helper: schedule & slot ----------------
def get_today_profile_and_distributions(current: User, db: Session):
    tz = ZoneInfo(current.timezone or "Europe/Rome")
    now_local = datetime.now(tz)
    weekday = (now_local.weekday())  # 0 Mon .. 6 Sun
    mode = db.query(UserDayMode).filter_by(user_id=current.id, weekday=weekday).first()
    is_on = True if (mode and mode.is_on) else False

    plan = db.query(UserPlan).filter_by(user_id=current.id).first()
    if not plan:
        # bootstrap plan on first access
        plan = UserPlan(
            user_id=current.id,
            on_kcal=2600, on_carb=360, on_pro=194, on_fat=45,
            off_kcal=2200, off_carb=200, off_pro=194, off_fat=55,
        )
        db.add(plan); db.flush()
        on_names = ["pre-workout", "intra-workout", "post-workout", "pranzo", "cena"]
        off_names = ["colazione", "pranzo", "cena", "snack"]
        for i, n in enumerate(on_names):
            db.add(UserDistribution(plan_id=plan.id, is_on=True, name=n, sort_order=i))
        for i, n in enumerate(off_names):
            db.add(UserDistribution(plan_id=plan.id, is_on=False, name=n, sort_order=i))
        db.commit(); db.refresh(plan)

    dists = db.query(UserDistribution)        .filter(UserDistribution.plan_id==plan.id, UserDistribution.is_on==is_on)        .order_by(UserDistribution.sort_order.asc())        .all()
    limits = {
        "kcal": plan.on_kcal if is_on else plan.off_kcal,
        "carb": plan.on_carb if is_on else plan.off_carb,
        "pro":  plan.on_pro  if is_on else plan.off_pro,
        "fat":  plan.on_fat  if is_on else plan.off_fat,
    }
    return is_on, dists, limits, tz, now_local

def auto_slot_for_now(current: User, db: Session) -> str:
    is_on, dists, _, tz, now_local = get_today_profile_and_distributions(current, db)
    minute = now_local.hour*60 + now_local.minute
    # try matching any window (support wrap over midnight)
    for d in dists:
        if d.start_min is None or d.end_min is None:
            continue
        if d.start_min <= d.end_min:
            if d.start_min <= minute <= d.end_min:
                return d.name
        else:
            # wrap over midnight
            if minute >= d.start_min or minute <= d.end_min:
                return d.name
    # fallback: if there is a distribution but no window matches, choose the first and be explicit?
    # Here, per spec, we should fail hard:
    raise HTTPException(status_code=400, detail="Nessuna distribuzione corrisponde all'orario corrente: definisci le fasce in Impostazioni.")

# ---------------- Foods search ----------------
@app.get("/foods/search", response_model=List[FoodSearchOut])
def foods_search(q: str, limit: int = 20, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ql = f"%{q}%"
    rows = db.query(Food).filter(Food.name.ilike(ql)).order_by(Food.name.asc()).limit(limit).all()
    out = []
    for f in rows:
        out.append({
            "id": f.id,
            "name": f.name,
            "barcode": f.barcode,
            "per_100g": {"kcal": f.per_100g_kcal, "pro": f.per_100g_pro, "carb": f.per_100g_carb, "fat": f.per_100g_fat},
            "grams_per_unit": f.grams_per_unit
        })
    return out

@app.get("/foods/recent")
def foods_recent(
    limit: int = 10,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    rows = (
        db.query(RecentFood, Food)
        .join(Food, RecentFood.food_id == Food.id)
        .filter(RecentFood.user_id == current.id)
        .order_by(RecentFood.last_used.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "food_id": f.id,
            "name": f.name,
            "barcode": f.barcode,
            "per_100g": {"kcal": f.per_100g_kcal, "pro": f.per_100g_pro, "carb": f.per_100g_carb, "fat": f.per_100g_fat},
            "grams_per_unit": f.grams_per_unit,
        }
        for _, f in rows
    ]

@app.get("/foods/recent_by_slot")
def foods_recent_by_slot(
    slot: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # ultimi meal items con quello slot per l'utente
    items = (
        db.query(MealItem, Meal, Food)
        .join(Meal, Meal.id == MealItem.meal_id)
        .join(Food, Food.id == MealItem.food_id, isouter=True)
        .filter(Meal.user_id == current.id, Meal.slot == slot)
        .order_by(Meal.when.desc())
        .limit(limit)
        .all()
    )
    out = []
    seen = set()
    for it, m, f in items:
        key = f.id if f else it.food_name
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "food_id": f.id if f else None,
            "name": f.name if f else it.food_name,
            "barcode": f.barcode if f else None,
            "per_100g": {
                "kcal": (f.per_100g_kcal if f else None),
                "pro":  (f.per_100g_pro if f else it.pro),
                "carb": (f.per_100g_carb if f else it.carb),
                "fat":  (f.per_100g_fat if f else it.fat),
            },
            "grams_per_unit": f.grams_per_unit if f else None,
        })
    return out

@app.put("/foods/barcode/{code}")
def upsert_food_by_barcode(
    code: str,
    payload: FoodConfirmIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    name = (payload.name or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Nome alimento obbligatorio')
    per100 = payload.per_100g
    try:
        food = db.query(Food).filter_by(barcode=code).first()
        if not food:
            food = Food(barcode=code)
            db.add(food)
            db.flush()
        food.name = name
        food.per_100g_kcal = per100.kcal or 0
        food.per_100g_pro = per100.pro or 0
        food.per_100g_carb = per100.carb or 0
        food.per_100g_fat = per100.fat or 0
        rf = db.query(RecentFood).filter_by(user_id=current.id, food_id=food.id).first()
        if rf:
            rf.last_used = datetime.utcnow()
        else:
            db.add(RecentFood(user_id=current.id, food_id=food.id))
        db.commit()
        return {
            'food_id': food.id,
            'name': food.name,
            'barcode': food.barcode,
            'per_100g': {
                'kcal': food.per_100g_kcal,
                'pro': food.per_100g_pro,
                'carb': food.per_100g_carb,
                'fat': food.per_100g_fat,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f'Errore salvataggio alimento: {e}')
# ---------------- Meals ----------------
@app.post("/meals")
def create_meal(
    meal: MealIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        slot = meal.slot
        if not slot:
            # se non fornito (es. inserimento rapido), deduci da schedule+fasce
            slot = auto_slot_for_now(current, db)

        m = Meal(user_id=current.id, when=meal.when, slot=slot)
        db.add(m)
        db.flush()
        for it in meal.items:
            db.add(
                MealItem(
                    meal_id=m.id,
                    food_name=it.food_name,
                    grams=it.grams,
                    pro=it.pro,
                    carb=it.carb,
                    fat=it.fat,
                )
            )
        db.commit()
        return {"ok": True, "meal_id": m.id, "user_id": current.id, "slot": slot}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Errore create_meal: {e}")

@app.post("/meals/add_from_barcode")
def add_meal_from_barcode(
    code: str = Query(..., description="Barcode prodotto"),
    grams: float = Query(..., description="Quantità in grammi"),
    slot: Optional[str] = None,
    when: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # lookup OFF
    data = food_by_barcode(code)
    per100 = data["per_100g"] or {}

    # trova/crea Food
    food = db.query(Food).filter_by(barcode=code).first()
    if not food:
        food = Food(
            name=data["name"],
            barcode=code,
            per_100g_kcal=per100.get("kcal") or 0,
            per_100g_pro=per100.get("pro") or 0,
            per_100g_carb=per100.get("carb") or 0,
            per_100g_fat=per100.get("fat") or 0,
        )
        db.add(food)
        db.flush()

    # determina slot
    if not slot:
        slot = auto_slot_for_now(current, db)

    # crea Meal + Item
    m = Meal(user_id=current.id, when=when or datetime.utcnow(), slot=slot)
    db.add(m)
    db.flush()

    db.add(
        MealItem(
            meal_id=m.id,
            food_id=food.id,
            food_name=food.name,
            grams=grams,
            pro=food.per_100g_pro or 0,
            carb=food.per_100g_carb or 0,
            fat=food.per_100g_fat or 0,
        )
    )

    # aggiorna recenti
    rf = db.query(RecentFood).filter_by(user_id=current.id, food_id=food.id).first()
    if rf:
        rf.last_used = datetime.utcnow()
    else:
        db.add(RecentFood(user_id=current.id, food_id=food.id))

    db.commit()
    return {"ok": True, "meal_id": m.id, "food": food.name, "grams": grams, "slot": slot}

@app.get("/meals/today")
def meals_today(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # decide ON/OFF + dists + limits
    is_on, dists, limits, tz, now_local = get_today_profile_and_distributions(current, db)

    d0_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    d1_local = d0_local + timedelta(days=1)
    # convert bounds to UTC for querying naive UTC timestamps (assuming stored naive as UTC)
    d0 = d0_local.astimezone(timezone.utc).replace(tzinfo=None)
    d1 = d1_local.astimezone(timezone.utc).replace(tzinfo=None)

    meals = db.query(Meal).filter(Meal.user_id == current.id, Meal.when >= d0, Meal.when < d1).all()
    result = []
    tot_pro = tot_carb = tot_fat = 0.0
    slot_stats: Dict[str, Dict[str, float]] = {}

    for m in meals:
        items = db.query(MealItem).filter(MealItem.meal_id == m.id).all()
        pro = sum(i.pro * (i.grams / 100.0) for i in items)
        carb = sum(i.carb * (i.grams / 100.0) for i in items)
        fat = sum(i.fat * (i.grams / 100.0) for i in items)
        kcal = pro * 4 + carb * 4 + fat * 9
        tot_pro += pro
        tot_carb += carb
        tot_fat += fat
        result.append(
            {
                "meal_id": m.id,
                "when": m.when.isoformat(),
                "slot": m.slot,
                "kcal": kcal,
                "pro": pro,
                "carb": carb,
                "fat": fat,
            }
        )
        s = slot_stats.get(m.slot, {"kcal":0.0, "pro":0.0, "carb":0.0, "fat":0.0})
        s["pro"] += pro; s["carb"] += carb; s["fat"] += fat; s["kcal"] += kcal
        slot_stats[m.slot] = s

    # targets by slot using DistributionTarget (fallback uniform if missing)
    targets = db.query(DistributionTarget).join(UserPlan, UserPlan.id==DistributionTarget.plan_id)        .filter(UserPlan.user_id==current.id, DistributionTarget.is_on==is_on).all()
    pct_map = {t.name: {"carb": t.pct_carb, "pro": t.pct_pro, "fat": t.pct_fat} for t in targets}
    # if missing, build uniform across defined distributions
    names = [d.name for d in dists]
    n = max(1, len(names))
    def pct_or_uniform(name: str, key: str) -> float:
        if name in pct_map:
            return pct_map[name][key]
        return 100.0 / n

    by_slot = []
    for name in names:
        tgt = {
            "carb": limits["carb"] * pct_or_uniform(name, "carb") / 100.0,
            "pro":  limits["pro"]  * pct_or_uniform(name, "pro")  / 100.0,
            "fat":  limits["fat"]  * pct_or_uniform(name, "fat")  / 100.0,
        }
        tgt["kcal"] = tgt["carb"]*4 + tgt["pro"]*4 + tgt["fat"]*9
        used = slot_stats.get(name, {"kcal":0.0, "pro":0.0, "carb":0.0, "fat":0.0})
        by_slot.append({"slot": name, "used": used, "target": tgt})

    day = {"kcal": tot_pro * 4 + tot_carb * 4 + tot_fat * 9, "pro": tot_pro, "carb": tot_carb, "fat": tot_fat}
    return {"kcal_limits": limits, "is_on": is_on, "day_totals": day, "by_slot": by_slot, "meals": result}

@app.get("/meals/{meal_id}")
def get_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    m = db.query(Meal).filter(Meal.id == meal_id, Meal.user_id == current.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Meal non trovato")

    items = db.query(MealItem).filter(MealItem.meal_id == m.id).all()
    return {
        "meal_id": m.id,
        "when": m.when.isoformat(),
        "slot": m.slot,
        "items": [
            {"food_name": it.food_name, "grams": it.grams, "pro": it.pro, "carb": it.carb, "fat": it.fat}
            for it in items
        ],
    }

@app.patch("/meals/{meal_id}")
def update_meal(
    meal_id: int,
    payload: MealUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    item = (
        db.query(MealItem)
        .join(Meal, Meal.id == MealItem.meal_id)
        .filter(MealItem.meal_id == meal_id, Meal.user_id == current.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Meal non trovato")

    if payload.food_name is not None:
        item.food_name = payload.food_name
    if payload.grams is not None:
        try:
            item.grams = float(payload.grams)
        except Exception:
            raise HTTPException(status_code=400, detail="grams non valido")

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "meal_id": meal_id,
        "food_name": item.food_name,
        "grams": item.grams,
        "pro": item.pro,
        "carb": item.carb,
        "fat": item.fat,
    }

# ---------------- Weight ----------------
@app.post("/weight")
def add_weight(w: WeightIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    try:
        db.add(WeightLog(user_id=current.id, when=w.when, kg=w.kg))
        db.commit()
        return {"ok": True, "user_id": current.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Errore add_weight: {e}")

@app.get("/weights/all")
def weights_all(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(WeightLog).filter(WeightLog.user_id == current.id).order_by(WeightLog.when.asc()).all()
    return [{"id": r.id, "when": r.when.isoformat(), "kg": r.kg} for r in rows]

@app.get("/weights/range")
def weights_range(
    start: str,
    end: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # parse start
    try:
        d0 = datetime.fromisoformat(start)
    except Exception:
        try:
            d0 = datetime.fromisoformat(start + "T00:00:00")
        except Exception:
            raise HTTPException(status_code=400, detail="Formato start non valido. Usa YYYY-MM-DD o datetime ISO")
    # parse end
    try:
        d1 = datetime.fromisoformat(end)
    except Exception:
        try:
            d1 = datetime.fromisoformat(end + "T00:00:00") + timedelta(days=1)
        except Exception:
            raise HTTPException(status_code=400, detail="Formato end non valido. Usa YYYY-MM-DD o datetime ISO")

    rows = (
        db.query(WeightLog)
        .filter(WeightLog.user_id == current.id, WeightLog.when >= d0, WeightLog.when < d1)
        .order_by(WeightLog.when.asc())
        .all()
    )
    return [{"id": r.id, "when": r.when.isoformat(), "kg": r.kg} for r in rows]

@app.get("/weights/weekly")
def weights_weekly(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(WeightLog).filter(WeightLog.user_id == current.id).order_by(WeightLog.when.asc()).all()
    if not rows:
        return []
    weekly = {}
    for r in rows:
        d = r.when.date()
        week_start = d - timedelta(days=d.weekday())  # lunedì
        key = week_start.isoformat()
        w = weekly.get(key, {"week_start": key, "values": []})
        w["values"].append(r.kg)
        weekly[key] = w
    out = []
    for k in sorted(weekly.keys()):
        vals = weekly[k]["values"]
        avg = sum(vals) / len(vals)
        out.append({"week_start": k, "avg": round(avg, 2), "min": min(vals), "max": max(vals), "n": len(vals)})
    return out

@app.get("/weights/trend")
def weights_trend(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(WeightLog).filter(WeightLog.user_id == current.id).order_by(WeightLog.when.asc()).all()
    if len(rows) < 2:
        return {"slope_kg_per_week": None}

    x = []
    y = []
    t0 = rows[0].when
    for r in rows:
        days = (r.when - t0).total_seconds() / (60 * 60 * 24)  # giorni decimali
        x.append(days)
        y.append(r.kg)

    n = len(x)
    sumx, sumy = sum(x), sum(y)
    sumxy = sum(a * b for a, b in zip(x, y))
    sumx2 = sum(a * a for a in x)
    denom = n * sumx2 - sumx * sumx
    if denom == 0:
        return {"slope_kg_per_week": None}

    slope = (n * sumxy - sumx * sumy) / denom
    return {"slope_kg_per_week": round(slope * 7, 3)}  # variazione settimanale

# ---------------- Workouts ----------------
@app.post("/workouts")
def add_workout(w: WorkoutIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    try:
        wk = Workout(user_id=current.id, when=w.when)
        db.add(wk)
        db.flush()
        for s in w.sets:
            db.add(Set(workout_id=wk.id, exercise=s.exercise, reps=s.reps, weight_kg=s.weight_kg))
        db.commit()
        return {"ok": True, "workout_id": wk.id, "user_id": current.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Errore add_workout: {e}")

@app.get("/workouts/all")
def workouts_all(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    wks = db.query(Workout).filter(Workout.user_id == current.id).order_by(Workout.when.desc()).all()
    out = []
    for w in wks:
        sets = db.query(Set).filter(Set.workout_id == w.id).all()
        out.append(
            {
                "id": w.id,
                "when": w.when.isoformat(),
                "sets": [{"exercise": s.exercise, "reps": s.reps, "weight_kg": s.weight_kg} for s in sets],
            }
        )
    return out

# ---------------- Day / Week summaries ----------------
@app.get("/summary/day")
def summary_day(date: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    try:
        d0 = datetime.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
    d1 = d0 + timedelta(days=1)

    pro = (
        db.query(func.sum(MealItem.pro * (MealItem.grams / 100.0)))
        .join(Meal)
        .filter(Meal.user_id == current.id, Meal.when >= d0, Meal.when < d1)
        .scalar()
        or 0.0
    )
    carb = (
        db.query(func.sum(MealItem.carb * (MealItem.grams / 100.0)))
        .join(Meal)
        .filter(Meal.user_id == current.id, Meal.when >= d0, Meal.when < d1)
        .scalar()
        or 0.0
    )
    fat = (
        db.query(func.sum(MealItem.fat * (MealItem.grams / 100.0)))
        .join(Meal)
        .filter(Meal.user_id == current.id, Meal.when >= d0, Meal.when < d1)
        .scalar()
        or 0.0
    )
    kcal = pro * 4 + carb * 4 + fat * 9
    return {"kcal": kcal, "pro": pro, "carb": carb, "fat": fat, "user_id": current.id}

@app.get("/summary/week")
def summary_week(start: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    try:
        d0 = datetime.fromisoformat(start)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato start non valido. Usa YYYY-MM-DD")
    d1 = d0 + timedelta(days=7)
    meals = db.query(Meal).filter(Meal.user_id == current.id, Meal.when >= d0, Meal.when < d1).all()
    tot_pro = tot_carb = tot_fat = 0.0
    for m in meals:
        items = db.query(MealItem).filter(MealItem.meal_id == m.id).all()
        tot_pro += sum(i.pro * (i.grams / 100.0) for i in items)
        tot_carb += sum(i.carb * (i.grams / 100.0) for i in items)
        tot_fat += sum(i.fat * (i.grams / 100.0) for i in items)
    tot_kcal = tot_pro * 4 + tot_carb * 4 + tot_fat * 9
    return {"week_start": start, "totals": {"kcal": tot_kcal, "pro": tot_pro, "carb": tot_carb, "fat": tot_fat}}

@app.get("/check/weekly")
def check_weekly(
    start: str,
    protein_target_g: float = 120.0,
    kcal_target: Optional[float] = None,
    min_workouts: int = 3,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        d0 = datetime.fromisoformat(start)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato start non valido. Usa YYYY-MM-DD")
    d1 = d0 + timedelta(days=7)
    days = [d0 + timedelta(days=i) for i in range(7)]
    day_stats = []
    for day in days:
        d_end = day + timedelta(days=1)
        items = (
            db.query(MealItem)
            .join(Meal)
            .filter(Meal.user_id == current.id, Meal.when >= day, Meal.when < d_end)
            .all()
        )
        pro = sum(i.pro * (i.grams / 100.0) for i in items)
        carb = sum(i.carb * (i.grams / 100.0) for i in items)
        fat = sum(i.fat * (i.grams / 100.0) for i in items)
        kcal = pro * 4 + carb * 4 + fat * 9
        day_stats.append({"date": day.date().isoformat(), "kcal": kcal, "pro": pro, "carb": carb, "fat": fat})
    protein_days = sum(1 for d in day_stats if d["pro"] >= protein_target_g)
    kcal_days = None
    if kcal_target is not None:
        kcal_days = sum(1 for d in day_stats if abs(d["kcal"] - kcal_target) <= kcal_target * 0.1)
    workouts_count = (
        db.query(func.count(Workout.id))
        .filter(Workout.user_id == current.id, Workout.when >= d0, Workout.when < d1)
        .scalar()
        or 0
    )
    return {
        "week_start": start,
        "missions": [
            {"name": "Proteine", "days_hit": protein_days},
            {"name": "Allenamenti", "done": workouts_count, "target": min_workouts},
        ],
        "daily": day_stats,
        "kcal_days_within_±10%": kcal_days,
    }

# ---------------- Deletes ----------------
@app.delete("/meals/{meal_id}")
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    m = db.query(Meal).filter(Meal.id == meal_id, Meal.user_id == current.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Meal non trovato per questo utente")
    try:
        db.query(MealItem).filter(MealItem.meal_id == m.id).delete(synchronize_session=False)
        db.delete(m)
        db.commit()
        return {"ok": True, "deleted_meal_id": meal_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Errore delete_meal: {e}")

@app.delete("/weights/{weight_id}")
def delete_weight(
    weight_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    w = db.query(WeightLog).filter(WeightLog.id == weight_id, WeightLog.user_id == current.id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Weight non trovato per questo utente")
    try:
        db.delete(w)
        db.commit()
        return {"ok": True, "deleted_weight_id": weight_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Errore delete_weight: {e}")

# ---------------- Plan (macros + distribuzioni) ----------------
@app.get("/plan")
def get_plan(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    plan = db.query(UserPlan).filter_by(user_id=current.id).first()
    if not plan:
        # crea piano default e distribuzioni default
        plan = UserPlan(
            user_id=current.id,
            on_kcal=2600, on_carb=360, on_pro=194, on_fat=45,
            off_kcal=2200, off_carb=200, off_pro=194, off_fat=55,
        )
        db.add(plan)
        db.flush()
        on_names = ["pre-workout", "intra-workout", "post-workout", "pranzo", "cena"]
        off_names = ["colazione", "pranzo", "cena", "snack"]
        for i, n in enumerate(on_names):
            db.add(UserDistribution(plan_id=plan.id, is_on=True, name=n, sort_order=i))
        for i, n in enumerate(off_names):
            db.add(UserDistribution(plan_id=plan.id, is_on=False, name=n, sort_order=i))
        db.commit(); db.refresh(plan)

    dists = db.query(UserDistribution).filter(UserDistribution.plan_id == plan.id).order_by(
        UserDistribution.is_on.desc(), UserDistribution.sort_order.asc()
    ).all()

    # targets map
    t = db.query(DistributionTarget).filter(DistributionTarget.plan_id == plan.id).all()
    t_map = {}
    for x in t:
        key = ("ON" if x.is_on else "OFF", x.name)
        t_map[key] = {"pct_carb": x.pct_carb, "pct_pro": x.pct_pro, "pct_fat": x.pct_fat}

    return {
        "on_distributions": [
            {"name": d.name, "sort_order": d.sort_order, "start_min": d.start_min, "end_min": d.end_min}
            for d in dists if d.is_on
        ],
        "off_distributions": [
            {"name": d.name, "sort_order": d.sort_order, "start_min": d.start_min, "end_min": d.end_min}
            for d in dists if not d.is_on
        ],
        "on_limits": {"kcal": plan.on_kcal, "carb": plan.on_carb, "pro": plan.on_pro, "fat": plan.on_fat},
        "off_limits": {"kcal": plan.off_kcal, "carb": plan.off_carb, "pro": plan.off_pro, "fat": plan.off_fat},
        "on_pcts": [
            {"name": name, **vals} for (grp, name), vals in t_map.items() if grp == "ON"
        ],
        "off_pcts": [
            {"name": name, **vals} for (grp, name), vals in t_map.items() if grp == "OFF"
        ],
    }

@app.put("/plan")
def update_plan(payload: PlanPayload, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    plan = db.query(UserPlan).filter_by(user_id=current.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Nessun piano trovato per questo utente")

    # aggiorna limiti
    plan.on_kcal = payload.on_limits.kcal
    plan.on_carb = payload.on_limits.carb
    plan.on_pro = payload.on_limits.pro
    plan.on_fat = payload.on_limits.fat

    plan.off_kcal = payload.off_limits.kcal
    plan.off_carb = payload.off_limits.carb
    plan.off_pro = payload.off_limits.pro
    plan.off_fat = payload.off_limits.fat
    db.add(plan); db.flush()

    # reset & reinsert distribuzioni
    db.query(UserDistribution).filter(UserDistribution.plan_id == plan.id).delete(synchronize_session=False)
    for i, d in enumerate(payload.on_distributions):
        db.add(UserDistribution(plan_id=plan.id, is_on=True, name=d.name, sort_order=d.sort_order, start_min=d.start_min, end_min=d.end_min))
    for i, d in enumerate(payload.off_distributions):
        db.add(UserDistribution(plan_id=plan.id, is_on=False, name=d.name, sort_order=d.sort_order, start_min=d.start_min, end_min=d.end_min))

    # update targets (validate sums ~100 per gruppo)
    def validate_sum(pcts):
        sc = sum(x.pct_carb for x in pcts) if pcts else 0
        sp = sum(x.pct_pro for x in pcts) if pcts else 0
        sf = sum(x.pct_fat for x in pcts) if pcts else 0
        if any(abs(v-100.0) > 0.5 for v in (sc, sp, sf)):
            raise HTTPException(status_code=400, detail="Le percentuali C/P/F per gruppo devono sommare 100%")
    validate_sum(payload.on_pcts)
    validate_sum(payload.off_pcts)

    db.query(DistributionTarget).filter(DistributionTarget.plan_id==plan.id).delete(synchronize_session=False)
    for x in payload.on_pcts:
        db.add(DistributionTarget(plan_id=plan.id, is_on=True, name=x.name, pct_carb=x.pct_carb, pct_pro=x.pct_pro, pct_fat=x.pct_fat))
    for x in payload.off_pcts:
        db.add(DistributionTarget(plan_id=plan.id, is_on=False, name=x.name, pct_carb=x.pct_carb, pct_pro=x.pct_pro, pct_fat=x.pct_fat))

    db.commit()

    return {"ok": True}

# ---------------- Schedule ----------------
@app.get("/schedule", response_model=SchedulePayload)
def get_schedule(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(UserDayMode).filter(UserDayMode.user_id==current.id).all()
    on_days = [r.weekday for r in rows if r.is_on]
    off_days = [r.weekday for r in rows if not r.is_on]
    return {"on_days": sorted(on_days), "off_days": sorted(off_days)}

@app.put("/schedule", response_model=SchedulePayload)
def put_schedule(payload: SchedulePayload, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    set_on = set(payload.on_days)
    set_off = set(payload.off_days)
    if set_on & set_off:
        raise HTTPException(status_code=400, detail="Un giorno non può essere sia ON sia OFF")
    if not set_on and not set_off:
        raise HTTPException(status_code=400, detail="Devi impostare almeno un giorno ON o OFF")

    db.query(UserDayMode).filter(UserDayMode.user_id==current.id).delete(synchronize_session=False)
    for wd in sorted(set_on):
        db.add(UserDayMode(user_id=current.id, weekday=int(wd), is_on=True))
    for wd in sorted(set_off):
        db.add(UserDayMode(user_id=current.id, weekday=int(wd), is_on=False))
    db.commit()
    return {"on_days": sorted(set_on), "off_days": sorted(set_off)}

# ---------------- Debug ----------------
@app.get("/debug/pingdb")
def debug_pingdb(db: Session = Depends(get_db)):
    users = db.query(func.count(User.id)).scalar() or 0
    meals = db.query(func.count(Meal.id)).scalar() or 0
    workouts = db.query(func.count(Workout.id)).scalar() or 0
    weights = db.query(func.count(WeightLog.id)).scalar() or 0
    plans = db.query(func.count(UserPlan.id)).scalar() or 0
    return {
        "ok": True,
        "counts": {"users": users, "meals": meals, "workouts": workouts, "weights": weights, "plans": plans},
    }


