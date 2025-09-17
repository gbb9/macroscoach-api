from db import engine, Base
from models import *  # importa i modelli aggiornati (Food con barcode, RecentFood, ecc.)

if __name__ == "__main__":
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Reset schema completato")
