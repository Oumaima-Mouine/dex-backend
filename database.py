# database.py
# Ce fichier crée la connexion vers PostgreSQL.
# Toutes les routes l'importent pour parler à la BDD.

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()  # Charge les variables du fichier .env

DB_URL = (
    f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    """Fournit une session BDD à chaque route, puis la ferme automatiquement."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()