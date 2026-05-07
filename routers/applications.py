from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/applications", tags=["Applications"])


@router.get("/")
def get_applications(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            a.id_app,
            a.nom_application,
            a.categorie,
            a.version,
            a.editeur,
            a.critique,
            a.nb_licences,
            m.disponibilite_pct,
            m.temps_reponse_s,
            m.nb_erreurs,
            m.nb_crashs,
            m.nb_utilisateurs_actifs,
            m.score_dex_app,
            m.statut_disponibilite
        FROM applications_etl a
        LEFT JOIN (
            SELECT DISTINCT ON (id_app) *
            FROM metriques_apps_etl
            ORDER BY id_app, date_collecte DESC
        ) m ON m.id_app = a.id_app
        ORDER BY a.nom_application
    """))
    return [dict(row._mapping) for row in result]


@router.get("/score-dex")
def get_score_dex_apps(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT
            a.nom_application                                       AS nom,
            ROUND(AVG(m.disponibilite_pct)::numeric, 2)            AS disponibilite,
            ROUND(AVG(m.temps_reponse_s)::numeric, 2)              AS temps_reponse_s,
            ROUND(AVG(m.score_dex_app)::numeric, 2)                AS score_dex_app,
            ROUND(AVG(m.nb_erreurs)::numeric, 1)                   AS moy_erreurs,
            ROUND(AVG(m.nb_utilisateurs_actifs)::numeric, 0)       AS moy_utilisateurs
        FROM applications_etl a
        JOIN metriques_apps_etl m ON m.id_app = a.id_app
        GROUP BY a.nom_application
        ORDER BY score_dex_app DESC
    """))
    return [dict(row._mapping) for row in result]