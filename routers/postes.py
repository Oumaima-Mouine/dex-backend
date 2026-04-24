from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/postes", tags=["Postes IT"])

@router.get("/")
def get_postes(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT p.code_poste, p.nom_utilisateur, p.departement,
               p.marque, p.modele, p.os,
               m.cpu_pct, m.ram_pct, m.disque_pct,
               m.nb_erreurs, m.nb_crashs, m.ping_ms,
               m.score_dex_it,
               CASE
                 WHEN m.score_dex_it >= 7 THEN 'Bon'
                 WHEN m.score_dex_it >= 5 THEN 'Moyen'
                 ELSE 'Critique'
               END AS statut
        FROM postes_etl p
        LEFT JOIN (
            SELECT DISTINCT ON (code_poste) *
            FROM metriques_postes_etl
            ORDER BY code_poste, collecte_le DESC
        ) m ON m.code_poste = p.code_poste
        ORDER BY p.departement, p.code_poste
    """))
    return [dict(row._mapping) for row in result]

@router.get("/{code_poste}")
def get_poste(code_poste: str, db: Session = Depends(get_db)):
    result = db.execute(
        text("SELECT * FROM postes_etl WHERE code_poste = :code"),
        {"code": code_poste}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Poste introuvable")
    return dict(row._mapping)