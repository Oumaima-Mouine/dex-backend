from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies IA"])

@router.get("/")
def get_anomalies(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT a.id_anomalie, a.code_poste, a.id_app,
               a.type_anomalie, a.severite, a.description,
               a.score_anomalie, a.detecte_le, a.resolue,
               p.nom_utilisateur, p.departement
        FROM anomalies_etl a
        LEFT JOIN postes_etl p ON p.code_poste = a.code_poste
        ORDER BY a.score_anomalie DESC, a.detecte_le DESC
        LIMIT 20
    """))
    return [dict(row._mapping) for row in result]

@router.get("/stats")
def get_anomalies_stats(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE resolue = false)        AS non_resolues,
            COUNT(*) FILTER (WHERE severite = 'critique')  AS critiques,
            COUNT(*) FILTER (WHERE severite = 'haute')     AS hautes
        FROM anomalies_etl
    """))
    return dict(result.fetchone()._mapping)