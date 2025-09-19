from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import List, Optional, Literal, Dict

# -------------------------
# Meals
# -------------------------

class MealItemIn(BaseModel):
    food_name: str
    grams: float
    pro: float = 0
    carb: float = 0
    fat: float = 0

class MealIn(BaseModel):
    when: datetime = Field(default_factory=datetime.utcnow)
    slot: Optional[str] = None
    items: List[MealItemIn]

class MealUpdate(BaseModel):
    food_name: str | None = None
    grams: float | None = None

class MealOut(BaseModel):
    meal_id: int
    when: datetime
    slot: str
    items: List[MealItemIn]


# -------------------------
# Weights
# -------------------------

class WeightIn(BaseModel):
    when: datetime = Field(default_factory=datetime.utcnow)
    kg: float

# -------------------------
# Workouts
# -------------------------

class SetIn(BaseModel):
    exercise: str
    reps: int
    weight_kg: float = 0

class WorkoutIn(BaseModel):
    when: datetime = Field(default_factory=datetime.utcnow)
    sets: List[SetIn] = []

# -------------------------
# Plan / Distributions
# -------------------------

class PlanLimits(BaseModel):
    kcal: int
    carb: int
    pro: int
    fat: int

class DistributionDef(BaseModel):
    name: str
    sort_order: int
    start_min: int | None = None
    end_min: int | None = None

class DistributionPct(BaseModel):
    name: str
    pct_carb: float
    pct_pro: float
    pct_fat: float

class PlanPayload(BaseModel):
    on_distributions: List[DistributionDef] = Field(default_factory=list)
    off_distributions: List[DistributionDef] = Field(default_factory=list)
    on_limits: PlanLimits
    off_limits: PlanLimits
    on_pcts: List[DistributionPct] = Field(default_factory=list)
    off_pcts: List[DistributionPct] = Field(default_factory=list)

# -------------------------
# Schedule
# -------------------------

class SchedulePayload(BaseModel):
    on_days: List[int] = Field(default_factory=list)
    off_days: List[int] = Field(default_factory=list)

# -------------------------
# Foods search
# -------------------------

class FoodSearchOut(BaseModel):
    id: int
    name: str
    barcode: str | None = None
    per_100g: Dict[str, float]
    grams_per_unit: float | None = None


class FoodPer100In(BaseModel):
    kcal: float | None = None
    pro: float | None = None
    carb: float | None = None
    fat: float | None = None


class FoodConfirmIn(BaseModel):
    name: str
    per_100g: FoodPer100In = Field(default_factory=FoodPer100In)

# -------------------------
# Auth
# -------------------------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    timezone: str | None = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"

class MeOut(BaseModel):
    id: int
    email: EmailStr
    timezone: str | None = None
