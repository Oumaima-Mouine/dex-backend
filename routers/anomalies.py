from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies IA"])

@router.get("/")
def get_anomalies(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT a.id_anomalie,   -- ← vérifie que cette ligne est présente
               a.code_poste, 
               a.id_app,
               a.type_anomalie, 
               a.severite, 
               a.description,
               a.score_anomalie, 
               a.detecte_le, 
               a.resolue,
               a.explication_ia,    -- ← et celle-ci
               p.nom_utilisateur, 
               p.departement
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

# APRÈS — accepte int ou string
@router.put("/{id_anomalie}/resolve")
def resolve_anomalie(id_anomalie: str, db: Session = Depends(get_db)):
    # Essaie de convertir en int si possible
    try:
        id_val = int(id_anomalie)
        db.execute(text("""
            UPDATE anomalies_etl SET resolue = true
            WHERE id_anomalie = :id
        """), {"id": id_val})
    except ValueError:
        # Si c'est une string type "ANO-002", cherche par id_app
        db.execute(text("""
            UPDATE anomalies_etl SET resolue = true
            WHERE id_app = :id AND resolue = false
        """), {"id": id_anomalie})
    db.commit()
    return {"message": "Anomalie résolue", "id": id_anomalie}

@router.get("/ia/status")
def get_ia_status():
    """Retourne le statut du module IA (scheduler)."""
    from ia.scheduler import scheduler
    jobs = scheduler.get_jobs()
    next_run = None
    if jobs:
        next_run = str(jobs[0].next_run_time)
    return {
        "scheduler_running": scheduler.running,
        "next_run": next_run,
        "model": "Isolation Forest",
    }

@router.post("/ia/run-now")
def run_ia_now():
    """Lance le pipeline IA immédiatement (pour la démo)."""
    from ia.scheduler import run_ia_pipeline
    import threading
    thread = threading.Thread(target=run_ia_pipeline)
    thread.start()
    return {"message": "Pipeline IA lancé en arrière-plan"}