from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from db import Base

# -------------------------
# Core / Anagrafiche
# -------------------------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)  # per auth
    timezone = Column(String, nullable=True)       # es. 'Europe/Rome'
    created_at = Column(DateTime, default=datetime.utcnow)


class Food(Base):
    __tablename__ = "foods"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True, nullable=False)
    barcode = Column(String, index=True, nullable=True)  # opzionale
    per_100g_kcal = Column(Float, default=0)
    per_100g_pro = Column(Float, default=0)
    per_100g_carb = Column(Float, default=0)
    per_100g_fat = Column(Float, default=0)
    grams_per_unit = Column(Float, nullable=True)  # opzionale, per calcolo da 'pezzi'

    items = relationship("MealItem", back_populates="food", cascade="all, delete", passive_deletes=True)


# -------------------------
# Pasti
# -------------------------

class Meal(Base):
    __tablename__ = "meals"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    when = Column(DateTime, default=datetime.utcnow, index=True)
    # Distribuzione/slot: NOT NULL nella logica applicativa (DB può risultare NULL se tabelle sono create su db esistente)
    slot = Column(String, nullable=False, default="__MISSING__")

    items = relationship("MealItem", back_populates="meal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_meals_user_when", "user_id", "when"),
    )


class MealItem(Base):
    __tablename__ = "meal_items"
    id = Column(Integer, primary_key=True)
    meal_id = Column(Integer, ForeignKey("meals.id", ondelete="CASCADE"), nullable=False, index=True)
    food_id = Column(Integer, ForeignKey("foods.id", ondelete="SET NULL"), nullable=True)

    food_name = Column(String, nullable=True)

    grams = Column(Float, default=0)
    pro   = Column(Float, default=0)
    carb  = Column(Float, default=0)
    fat   = Column(Float, default=0)

    meal = relationship("Meal", back_populates="items")
    food = relationship("Food", back_populates="items")


# -------------------------
# Allenamenti
# -------------------------

class Workout(Base):
    __tablename__ = "workouts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    when = Column(DateTime, default=datetime.utcnow, index=True)

    sets = relationship("Set", back_populates="workout", cascade="all, delete-orphan")


class Set(Base):
    __tablename__ = "sets"
    id = Column(Integer, primary_key=True)
    workout_id = Column(Integer, ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise = Column(String, nullable=False)
    reps = Column(Integer, nullable=False)
    weight_kg = Column(Float, default=0)

    workout = relationship("Workout", back_populates="sets")


# -------------------------
# Peso
# -------------------------

class WeightLog(Base):
    __tablename__ = "weight_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    when = Column(DateTime, default=datetime.utcnow, index=True)
    kg = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_weight_user_when", "user_id", "when"),
    )


# -------------------------
# Recenti (cibi usati di recente)
# -------------------------

class RecentFood(Base):
    __tablename__ = "recent_foods"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    food_id = Column(Integer, ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True)
    last_used = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "food_id", name="uq_recent_food_user_food"),
    )


# -------------------------
# Piano macros + distribuzioni (ON/OFF)
# -------------------------

class UserPlan(Base):
    __tablename__ = "user_plans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # limiti ON
    on_kcal = Column(Integer, nullable=False, default=2600)
    on_carb = Column(Integer, nullable=False, default=360)
    on_pro  = Column(Integer, nullable=False, default=194)
    on_fat  = Column(Integer, nullable=False, default=45)

    # limiti OFF
    off_kcal = Column(Integer, nullable=False, default=2200)
    off_carb = Column(Integer, nullable=False, default=200)
    off_pro  = Column(Integer, nullable=False, default=194)
    off_fat  = Column(Integer, nullable=False, default=55)

    distributions = relationship("UserDistribution", back_populates="plan", cascade="all, delete-orphan")
    targets = relationship("DistributionTarget", back_populates="plan", cascade="all, delete-orphan")


class UserDistribution(Base):
    __tablename__ = "user_distributions"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("user_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    is_on = Column(Boolean, nullable=False)  # True=ON, False=OFF
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    # fascia oraria (in minuti locali 0..1440); supporto wrap (start > end)
    start_min = Column(Integer, nullable=True)
    end_min = Column(Integer, nullable=True)

    plan = relationship("UserPlan", back_populates="distributions")


class DistributionTarget(Base):
    __tablename__ = "distribution_targets"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("user_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    is_on = Column(Boolean, nullable=False)      # True=ON, False=OFF
    name = Column(String, nullable=False)        # nome distribuzione (match by name)
    pct_carb = Column(Float, nullable=False, default=0.0)
    pct_pro  = Column(Float, nullable=False, default=0.0)
    pct_fat  = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        UniqueConstraint("plan_id", "is_on", "name", name="uq_target_plan_group_name"),
    )

    plan = relationship("UserPlan", back_populates="targets")


# -------------------------
# ON/OFF weekly schedule
# -------------------------

class UserDayMode(Base):
    __tablename__ = "user_day_modes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)  # 0=Mon .. 6=Sun
    is_on = Column(Boolean, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "weekday", name="uq_user_day_mode"),
    )
