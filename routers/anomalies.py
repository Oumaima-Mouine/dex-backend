# routers/anomalies.py
# Router FastAPI — expose les anomalies avec recommandations + confiance_ia Gemini

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database import get_db, engine
import json

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies IA"])


# ── GET / — Liste avec filtres ────────────────────────────────────────────────
@router.get("/")
def get_anomalies(
    resolues:      bool           = False,
    severite:      Optional[str]  = Query(None),
    type_anomalie: Optional[str]  = Query(None),
    departement:   Optional[str]  = Query(None),
    limit:         int            = Query(50, le=200),
    offset:        int            = Query(0),
    db: Session = Depends(get_db),
):
    conditions = [] if resolues else ["a.resolue = false"]
    if severite:      conditions.append(f"a.severite = '{severite}'")
    if type_anomalie: conditions.append(f"a.type_anomalie = '{type_anomalie}'")
    if departement:   conditions.append(f"p.departement = '{departement}'")
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

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
            a.recommandations,
            a.confiance_ia,
            p.nom_utilisateur,
            p.departement,
            p.marque,
            p.modele
        FROM anomalies_etl a
        LEFT JOIN postes_etl p ON p.code_poste = a.code_poste
        {where_clause}
        ORDER BY a.score_anomalie DESC, a.detecte_le DESC
        LIMIT {limit} OFFSET {offset}
    """))

    rows = []
    for row in result:
        d = dict(row._mapping)
        # Désérialiser recommandations JSONB → liste Python
        if d.get('recommandations'):
            if isinstance(d['recommandations'], str):
                try:
                    d['recommandations'] = json.loads(d['recommandations'])
                except Exception:
                    d['recommandations'] = []
        else:
            d['recommandations'] = []
        rows.append(d)
    return rows


# ── GET /stats ────────────────────────────────────────────────────────────────
@router.get("/stats")
def get_anomalies_stats(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE resolue = false)         AS non_resolues,
            COUNT(*) FILTER (WHERE severite = 'critique')   AS critiques,
            COUNT(*) FILTER (WHERE severite = 'haute')      AS hautes,
            COUNT(*) FILTER (WHERE severite = 'moyenne')    AS moyennes,
            COUNT(*) FILTER (WHERE resolue = true)          AS resolues
        FROM anomalies_etl
    """))
    return dict(result.fetchone()._mapping)


# ── GET /types ────────────────────────────────────────────────────────────────
@router.get("/types")
def get_anomalie_types(db: Session = Depends(get_db)):
    result = db.execute(text(
        "SELECT DISTINCT type_anomalie FROM anomalies_etl ORDER BY type_anomalie"
    ))
    return [row[0] for row in result]


# ── GET /ia/status ────────────────────────────────────────────────────────────
@router.get("/ia/status")
def get_ia_status():
    try:
        from ia.scheduler import scheduler
        jobs     = scheduler.get_jobs()
        next_run = str(jobs[0].next_run_time) if jobs else None
        return {"scheduler_running": scheduler.running, "next_run": next_run, "model": "Isolation Forest + Gemini"}
    except Exception as e:
        return {"scheduler_running": False, "next_run": None, "error": str(e)}


# ── POST /ia/run-now ──────────────────────────────────────────────────────────
@router.post("/ia/run-now")
def run_ia_now():
    try:
        from ia.scheduler import run_ia_pipeline
        import threading
        threading.Thread(target=run_ia_pipeline).start()
        return {"message": "Pipeline IA lancé en arrière-plan (Isolation Forest + Gemini)"}
    except Exception as e:
        return {"message": f"Erreur : {e}"}


# ── GET /historique/{code_poste} ──────────────────────────────────────────────
@router.get("/historique/{code_poste}")
def get_historique_poste(code_poste: str, db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT id_anomalie, type_anomalie, severite, description,
               score_anomalie, detecte_le, resolue, explication_ia,
               recommandations, confiance_ia
        FROM anomalies_etl
        WHERE code_poste = :code
        ORDER BY detecte_le DESC
        LIMIT 50
    """), {"code": code_poste})

    rows = []
    for row in result:
        d = dict(row._mapping)
        if d.get('recommandations') and isinstance(d['recommandations'], str):
            try:
                d['recommandations'] = json.loads(d['recommandations'])
            except Exception:
                d['recommandations'] = []
        rows.append(d)
    return rows


# ── GET /metriques/{code_poste} ───────────────────────────────────────────────
@router.get("/metriques/{code_poste}")
def get_metriques_poste(code_poste: str, limit: int = 12, db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT collecte_le, cpu_pct, ram_pct, disque_pct, ping_ms, nb_erreurs
        FROM metriques_postes_etl
        WHERE code_poste = :code
        ORDER BY collecte_le DESC
        LIMIT :limit
    """), {"code": code_poste, "limit": limit})
    return list(reversed([dict(row._mapping) for row in result]))


# ── POST /tickets ─────────────────────────────────────────────────────────────
@router.post("/tickets")
def create_ticket(ticket: dict):
    import uuid
    ticket_id = f"TKT-{str(uuid.uuid4())[:8].upper()}"
    return {
        "success":   True,
        "ticket_id": ticket_id,
        "message":   f"Ticket {ticket_id} créé",
        "titre":     ticket.get("titre"),
        "priorite":  ticket.get("priorite", "haute"),
        "assignee":  "Équipe IT OCP Safi",
    }


# ── PUT /{id_anomalie}/resolve ────────────────────────────────────────────────
@router.put("/{id_anomalie}/resolve")
def resolve_anomalie(id_anomalie: str, db: Session = Depends(get_db)):
    with engine.connect() as conn:
        conn.execute(text(
            "UPDATE anomalies_etl SET resolue = true WHERE id_anomalie = :id"
        ), {"id": id_anomalie})
        conn.commit()
    return {"message": "Anomalie résolue", "id": id_anomalie}