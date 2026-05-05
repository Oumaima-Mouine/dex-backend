from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine  # ← ajoute engine ici

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies IA"])


@router.get("/")
def get_anomalies(resolues: bool = False, db: Session = Depends(get_db)):
    filtre = "" if resolues else "WHERE a.resolue = false"
    result = db.execute(text(f"""
        SELECT
            a.id_anomalie,
            a.code_poste,
            a.id_app,
            a.type_anomalie,
            a.severite,
            a.description,
            a.score_anomalie,
            a.detecte_le,
            a.resolue,
            a.explication_ia,
            p.nom_utilisateur,
            p.departement
        FROM anomalies_etl a
        LEFT JOIN postes_etl p ON p.code_poste = a.code_poste
        {filtre}
        ORDER BY a.score_anomalie DESC, a.detecte_le DESC
        LIMIT 50
    """))
    return [dict(row._mapping) for row in result]


# ⚠️ IMPORTANT : /stats et /ia/status AVANT /{id_anomalie}
# sinon FastAPI interprète "stats" comme un id_anomalie
@router.get("/stats")
def get_anomalies_stats(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            COUNT(*)                                       AS total,
            COUNT(*) FILTER (WHERE resolue = false)       AS non_resolues,
            COUNT(*) FILTER (WHERE severite = 'critique') AS critiques,
            COUNT(*) FILTER (WHERE severite = 'haute')    AS hautes
        FROM anomalies_etl
    """))
    return dict(result.fetchone()._mapping)


@router.get("/ia/status")
def get_ia_status():
    from ia.scheduler import scheduler
    jobs = scheduler.get_jobs()
    next_run = str(jobs[0].next_run_time) if jobs else None
    return {
        "scheduler_running": scheduler.running,
        "next_run":          next_run,
        "model":             "Isolation Forest",
    }


@router.post("/ia/run-now")
def run_ia_now():
    from ia.scheduler import run_ia_pipeline
    import threading
    threading.Thread(target=run_ia_pipeline).start()
    return {"message": "Pipeline IA lancé en arrière-plan"}


# ⚠️ Cette route DOIT être après /stats et /ia/status
@router.put("/{id_anomalie}/resolve")
def resolve_anomalie(id_anomalie: str, db: Session = Depends(get_db)):
    try:
        real_id = int(id_anomalie)
        # C'est un entier → cherche par id_anomalie
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE anomalies_etl
                SET resolue = true
                WHERE id_anomalie = :id
            """), {"id": real_id})
            conn.commit()
    except ValueError:
        # C'est une string type "ANO-003" → cherche par id_app
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE anomalies_etl
                SET resolue = true
                WHERE id_app = :id AND resolue = false
            """), {"id": id_anomalie})
            conn.commit()

    return {"message": "Anomalie résolue", "id": id_anomalie}