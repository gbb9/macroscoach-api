from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

# Carica variabili da .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Crea engine e sessione
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base per i modelli SQLAlchemy (in models.py)
class Base(DeclarativeBase):
    pass

# Dependency per FastAPI: sessione DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
