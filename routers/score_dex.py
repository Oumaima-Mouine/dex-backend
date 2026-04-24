from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/score-dex", tags=["Score DEX"])

@router.get("/global")
def get_score_global(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            ROUND(AVG(score_dex_it)::numeric, 2)        AS score_global,
            ROUND(AVG(cpu_pct)::numeric, 2)             AS moy_cpu,
            ROUND(AVG(ram_pct)::numeric, 2)             AS moy_ram,
            ROUND(AVG(disque_pct)::numeric, 2)          AS moy_disque,
            COUNT(*) FILTER (WHERE score_dex_it < 5)   AS postes_critiques,
            COUNT(*)                                     AS total_postes
        FROM (
            SELECT DISTINCT ON (code_poste) *
            FROM metriques_postes_etl
            ORDER BY code_poste, collecte_le DESC
        ) derniere
    """))
    return dict(result.fetchone()._mapping)

@router.get("/par-departement")
def get_score_par_dept(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT p.departement,
               ROUND(AVG(m.score_dex_it)::numeric, 2) AS score_dex,
               COUNT(*) AS nb_postes
        FROM postes_etl p
        JOIN (
            SELECT DISTINCT ON (code_poste) *
            FROM metriques_postes_etl
            ORDER BY code_poste, collecte_le DESC
        ) m ON m.code_poste = p.code_poste
        GROUP BY p.departement
        ORDER BY score_dex DESC
    """))
    return [dict(row._mapping) for row in result]

@router.get("/applications")
def get_score_applications(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT a.nom,
               ROUND(AVG(m.disponibilite)::numeric, 2)   AS disponibilite,
               ROUND(AVG(m.temps_reponse_s)::numeric, 2) AS temps_reponse_s,
               ROUND(AVG(m.score_dex_app)::numeric, 2)   AS score_dex_app,
               ROUND(AVG(m.nb_erreurs)::numeric, 1)      AS moy_erreurs
        FROM applications_etl a
        JOIN metriques_apps_etl m ON m.id_app = a.id_app
        GROUP BY a.nom
        ORDER BY score_dex_app DESC
    """))
    return [dict(row._mapping) for row in result]

@router.get("/historique")
def get_historique(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT 
            DATE(collecte_le) AS jour,
            ROUND(AVG(score_dex_it)::numeric, 2) AS score_moyen,
            ROUND(AVG(cpu_pct)::numeric, 2) AS cpu_moyen,
            ROUND(AVG(ram_pct)::numeric, 2) AS ram_moyen
        FROM metriques_postes_etl
        GROUP BY DATE(collecte_le)
        ORDER BY jour DESC
        LIMIT 30
    """))
    return [dict(row._mapping) for row in result]