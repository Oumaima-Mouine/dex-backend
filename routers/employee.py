from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database import get_db
from routers.auth import get_current_user

router = APIRouter(prefix="/employee", tags=["Employee"])


# ─────────────────────────────────────────────
#  Helper: get code_poste from logged-in user
# ─────────────────────────────────────────────
def get_employee_code_poste(current_user: dict, db: Session) -> str:
    """
    Returns the code_poste linked to the authenticated employee.
    Requires utilisateurs_auth.code_poste to be populated (run the DB fix first).
    """
    result = db.execute(
        text("SELECT code_poste FROM utilisateurs_auth WHERE id = :uid"),
        {"uid": current_user["id"]}
    ).fetchone()

    if not result or not result.code_poste:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No workstation linked to your account. Contact IT."
        )
    return result.code_poste


# ─────────────────────────────────────────────
#  GET /employee/me  — profile + device info
# ─────────────────────────────────────────────
@router.get("/me")
def get_my_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    row = db.execute(
        text("""
            SELECT
                p.code_poste,
                p.nom_utilisateur,
                p.email,
                p.departement,
                p.marque,
                p.modele,
                p.os,
                p.ram_gb,
                p.stockage_gb,
                p.cpu_modele,
                p.date_achat,
                p.actif,
                p.anciennete_annees,
                p.categorie_anciennete,
                u.role,
                u.avatar_url,
                u.last_login
            FROM postes_etl p
            JOIN utilisateurs_auth u ON u.code_poste = p.code_poste
            WHERE p.code_poste = :cp
        """),
        {"cp": code_poste}
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")

    return dict(row._mapping)


# ─────────────────────────────────────────────
#  GET /employee/dex-score  — my DEX score
# ─────────────────────────────────────────────
@router.get("/dex-score")
def get_my_dex_score(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    row = db.execute(
        text("""
            SELECT
                score_technique,
                score_satisfaction,
                score_dex_global,
                statut,
                date_calcul
            FROM scores_dex_etl
            WHERE code_poste = :cp
            ORDER BY date_calcul DESC
            LIMIT 1
        """),
        {"cp": code_poste}
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No DEX score found")

    return dict(row._mapping)


# ─────────────────────────────────────────────
#  GET /employee/anomalies  — my anomalies
# ─────────────────────────────────────────────
@router.get("/anomalies")
def get_my_anomalies(
    resolved: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    query = """
        SELECT
            id_anomalie,
            type_anomalie,
            severite,
            description,
            score_anomalie,
            detecte_le,
            resolue,
            explication_ia,
            recommandations
        FROM anomalies_etl
        WHERE code_poste = :cp
    """
    params = {"cp": code_poste}

    if resolved is not None:
        query += " AND resolue = :resolved"
        params["resolved"] = resolved

    query += " ORDER BY detecte_le DESC"

    rows = db.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]


# ─────────────────────────────────────────────
#  GET /employee/metrics  — my device metrics
# ─────────────────────────────────────────────
@router.get("/metrics")
def get_my_metrics(
    days: int = 7,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    rows = db.execute(
        text("""
            SELECT
                TO_CHAR(date_collecte, 'YYYY-MM-DD') AS date_collecte,
                cpu_pct,
                ram_pct,
                disque_pct,
                ping_ms,
                temp_processeur_c,
                nb_processus,
                nb_crashs,
                score_technique,
                statut_performance
            FROM metriques_postes_etl
            WHERE code_poste = :cp
              AND date_collecte >= CURRENT_DATE - INTERVAL ':days days'
            ORDER BY date_collecte ASC
        """),
        {"cp": code_poste, "days": days}
    ).fetchall()

    return [dict(r._mapping) for r in rows]


# ─────────────────────────────────────────────
#  GET /employee/feedback  — my feedback history
# ─────────────────────────────────────────────
@router.get("/feedback")
def get_my_feedback(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    rows = db.execute(
        text("""
            SELECT
                id_reponse,
                sondage,
                TO_CHAR(date_reponse, 'YYYY-MM-DD') AS date_reponse,
                note_globale,
                note_vitesse,
                note_stabilite,
                note_support,
                note_outils,
                commentaire,
                score_satisfaction
            FROM feedback_etl
            WHERE code_poste = :cp
            ORDER BY date_reponse DESC
        """),
        {"cp": code_poste}
    ).fetchall()

    return [dict(r._mapping) for r in rows]


# ─────────────────────────────────────────────
#  POST /employee/feedback  — submit feedback
# ─────────────────────────────────────────────
@router.post("/feedback", status_code=201)
def submit_feedback(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    required = ["note_globale", "note_vitesse", "note_stabilite", "note_support", "note_outils"]
    for field in required:
        if field not in payload:
            raise HTTPException(status_code=422, detail=f"Missing field: {field}")

    notes = [payload[f] for f in required]
    score_satisfaction = round(sum(notes) / len(notes), 2)

    # Get nom_utilisateur from postes_etl to use as matricule display
    poste_row = db.execute(
        text("SELECT nom_utilisateur FROM postes_etl WHERE code_poste = :cp"),
        {"cp": code_poste}
    ).fetchone()
    nom_utilisateur = poste_row.nom_utilisateur if poste_row else code_poste

    db.execute(
        text("""
            INSERT INTO feedback_etl
                (code_poste, matricule, id_employe, sondage, date_reponse,
                 note_globale, note_vitesse, note_stabilite,
                 note_support, note_outils, commentaire, score_satisfaction)
            VALUES
                (:cp, :matricule, :id_employe, :sondage, CURRENT_DATE,
                 :note_globale, :note_vitesse, :note_stabilite,
                 :note_support, :note_outils, :commentaire, :score_satisfaction)
        """),
        {
            "cp": code_poste,
            "matricule": nom_utilisateur,
            "id_employe": current_user["id"],
            "sondage": payload.get("sondage", "Sondage DEX"),
            "note_globale": payload["note_globale"],
            "note_vitesse": payload["note_vitesse"],
            "note_stabilite": payload["note_stabilite"],
            "note_support": payload["note_support"],
            "note_outils": payload["note_outils"],
            "commentaire": payload.get("commentaire", ""),
            "score_satisfaction": score_satisfaction,
        }
    )
    db.commit()
    return {"message": "Feedback submitted", "score_satisfaction": score_satisfaction}


# ─────────────────────────────────────────────
#  GET /employee/tickets  — my support tickets
# ─────────────────────────────────────────────
@router.get("/tickets")
def get_my_tickets(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    rows = db.execute(
        text("""
            SELECT
                id_ticket,
                titre,
                description,
                categorie,
                priorite,
                statut,
                cree_le,
                mis_a_jour_le,
                resolu_le
            FROM tickets_support
            WHERE code_poste = :cp
            ORDER BY cree_le DESC
        """),
        {"cp": code_poste}
    ).fetchall()

    return [dict(r._mapping) for r in rows]


# ─────────────────────────────────────────────
#  POST /employee/tickets  — create ticket
# ─────────────────────────────────────────────
@router.post("/tickets", status_code=201)
def create_ticket(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code_poste = get_employee_code_poste(current_user, db)

    for field in ["titre", "description", "categorie"]:
        if not payload.get(field):
            raise HTTPException(status_code=422, detail=f"Missing field: {field}")

    result = db.execute(
        text("""
            INSERT INTO tickets_support
                (code_poste, titre, description, categorie, priorite, statut, cree_le, mis_a_jour_le)
            VALUES
                (:cp, :titre, :description, :categorie, :priorite, 'Ouvert', NOW(), NOW())
            RETURNING id_ticket
        """),
        {
            "cp": code_poste,
            "titre": payload["titre"],
            "description": payload["description"],
            "categorie": payload["categorie"],
            "priorite": payload.get("priorite", "Normale"),
        }
    )
    db.commit()
    ticket_id = result.fetchone()[0]
    return {"message": "Ticket created", "id_ticket": ticket_id}