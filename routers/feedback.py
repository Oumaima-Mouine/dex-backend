from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


@router.get("/")
def get_feedback(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            id_reponse, matricule, sondage,
            date_reponse,
            note_globale, note_vitesse, note_stabilite,
            note_support, note_outils, commentaire,
            score_satisfaction
        FROM feedback_etl
        ORDER BY date_reponse DESC
        LIMIT 50
    """))
    return [dict(row._mapping) for row in result]


@router.get("/stats")
def get_feedback_stats(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            ROUND(AVG(note_globale)::numeric, 2)        AS moy_globale,
            ROUND(AVG(note_vitesse)::numeric, 2)        AS moy_vitesse,
            ROUND(AVG(note_stabilite)::numeric, 2)      AS moy_stabilite,
            ROUND(AVG(note_support)::numeric, 2)        AS moy_support,
            ROUND(AVG(note_outils)::numeric, 2)         AS moy_outils,
            ROUND(AVG(score_satisfaction)::numeric, 2)  AS moy_generale,
            COUNT(*)                                     AS nb_reponses
        FROM feedback_etl
    """))
    return dict(result.fetchone()._mapping)