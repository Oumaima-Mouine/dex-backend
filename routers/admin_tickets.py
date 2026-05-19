from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from routers.auth import get_current_user

router = APIRouter(prefix="/api/tickets", tags=["Tickets Admin"])


@router.get("/")
def get_all_tickets(
    statut: str = None,
    priorite: str = None,
    db: Session = Depends(get_db)
):
    query = """
        SELECT
            t.id_ticket,
            t.code_poste,
            t.titre,
            t.description,
            t.categorie,
            t.priorite,
            t.statut,
            t.cree_le,
            t.mis_a_jour_le,
            t.resolu_le,
            p.nom_utilisateur,
            p.departement,
            p.email
        FROM tickets_support t
        LEFT JOIN postes_etl p ON p.code_poste = t.code_poste
        WHERE 1=1
    """
    params = {}
    if statut:
        query += " AND t.statut = :statut"
        params["statut"] = statut
    if priorite:
        query += " AND t.priorite = :priorite"
        params["priorite"] = priorite

    query += " ORDER BY t.cree_le DESC"

    rows = db.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/stats")
def get_tickets_stats(db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT
            COUNT(*)                                      AS total,
            COUNT(*) FILTER (WHERE statut = 'Ouvert')    AS ouverts,
            COUNT(*) FILTER (WHERE statut = 'En cours')  AS en_cours,
            COUNT(*) FILTER (WHERE statut = 'Résolu')    AS resolus,
            COUNT(*) FILTER (WHERE priorite = 'Critique') AS critiques,
            COUNT(*) FILTER (WHERE priorite = 'Haute')    AS hauts
        FROM tickets_support
    """)).fetchone()
    return dict(row._mapping)


@router.patch("/{id_ticket}/statut")
def update_ticket_statut(
    id_ticket: int,
    payload: dict,
    db: Session = Depends(get_db)
):
    new_statut = payload.get("statut")
    if new_statut not in ["Ouvert", "En cours", "Résolu", "Fermé"]:
        raise HTTPException(status_code=422, detail="Statut invalide")

    resolu_le = "NOW()" if new_statut == "Résolu" else "NULL"

    db.execute(text(f"""
        UPDATE tickets_support
        SET statut = :statut,
            mis_a_jour_le = NOW(),
            resolu_le = {resolu_le}
        WHERE id_ticket = :id
    """), {"statut": new_statut, "id": id_ticket})
    db.commit()
    return {"message": "Statut mis à jour", "id_ticket": id_ticket, "statut": new_statut}