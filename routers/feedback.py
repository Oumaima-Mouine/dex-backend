from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


@router.get("/")
def get_feedback(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            f.id_reponse,
            f.matricule,
            f.code_poste,
            -- nom_utilisateur from postes for display
            COALESCE(p.nom_utilisateur, f.matricule) AS nom_utilisateur,
            f.sondage,
            -- Cast date to ISO string so frontend always gets 'YYYY-MM-DD'
            TO_CHAR(f.date_reponse, 'YYYY-MM-DD') AS date_reponse,
            f.note_globale,
            f.note_vitesse,
            f.note_stabilite,
            f.note_support,
            f.note_outils,
            f.commentaire,
            f.score_satisfaction
        FROM feedback_etl f
        LEFT JOIN postes_etl p ON p.code_poste = f.code_poste
        ORDER BY f.date_reponse DESC
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