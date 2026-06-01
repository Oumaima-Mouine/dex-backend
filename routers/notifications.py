# routers/notifications.py
# Gestion des notifications admin — créées automatiquement depuis anomalies & feedback
# Routes : GET /api/notifications/   POST /api/notifications/{id}/read
#          POST /api/notifications/read-all   DELETE /api/notifications/{id}
#          POST /api/notifications/generate   GET /api/notifications/unread-count

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from routers.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return current_user


def ensure_table(db: Session):
    """Crée la table notifications si elle n'existe pas encore."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          SERIAL PRIMARY KEY,
            type        VARCHAR(20)  NOT NULL DEFAULT 'info',   -- critique | alerte | info
            title       VARCHAR(200) NOT NULL,
            body        TEXT,
            source      VARCHAR(50),   -- 'anomalie' | 'feedback' | 'systeme'
            source_id   VARCHAR(50),   -- id de l'anomalie ou du feedback lié
            read        BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """))
    db.commit()


# ──────────────────────────────────────────────
# GET /api/notifications/
# ──────────────────────────────────────────────

@router.get("/")
def get_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_table(db)
    where = "WHERE read = FALSE" if unread_only else ""
    rows = db.execute(text(f"""
        SELECT id, type, title, body, source, source_id, read,
               TO_CHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS created_at
        FROM notifications
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    return [dict(r._mapping) for r in rows]


# ──────────────────────────────────────────────
# GET /api/notifications/unread-count
# ──────────────────────────────────────────────

@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_table(db)
    row = db.execute(text("SELECT COUNT(*) FROM notifications WHERE read = FALSE")).fetchone()
    return {"count": row[0]}


# ──────────────────────────────────────────────
# POST /api/notifications/{id}/read
# ──────────────────────────────────────────────

@router.post("/{notif_id}/read")
def mark_read(
    notif_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_table(db)
    db.execute(text("UPDATE notifications SET read = TRUE WHERE id = :id"), {"id": notif_id})
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# POST /api/notifications/read-all
# ──────────────────────────────────────────────

@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_table(db)
    db.execute(text("UPDATE notifications SET read = TRUE WHERE read = FALSE"))
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# DELETE /api/notifications/{id}
# ──────────────────────────────────────────────

@router.delete("/{notif_id}")
def delete_notification(
    notif_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_table(db)
    db.execute(text("DELETE FROM notifications WHERE id = :id"), {"id": notif_id})
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# POST /api/notifications/generate
# Génère des notifications depuis anomalies & feedbacks récents
# Appelé au démarrage et par le scheduler IA
# ──────────────────────────────────────────────

@router.post("/generate")
def generate_notifications(
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_table(db)
    created = _do_generate(db)
    return {"created": created}


def _do_generate(db: Session) -> int:
    """
    Logique de génération — peut être appelée depuis le scheduler sans auth.
    Retourne le nombre de notifications créées.
    """
    ensure_table(db)
    created = 0

    # ── 1. Anomalies critiques non résolues des 24h ──────────────────────────
    anomalies = db.execute(text("""
        SELECT id_anomalie, type_anomalie, severite, code_poste, description
        FROM anomalies_etl
        WHERE resolue = FALSE
          AND detecte_le >= NOW() - INTERVAL '24 hours'
    """)).fetchall()

    for a in anomalies:
        source_id = str(a.id_anomalie)
        already = db.execute(text("""
            SELECT 1 FROM notifications
            WHERE source = 'anomalie' AND source_id = :sid
        """), {"sid": source_id}).fetchone()
        if already:
            continue

        severite = (a.severite or "").lower()
        notif_type = "critique" if severite == "critique" else "alerte"
        title = f"{'🔴' if notif_type == 'critique' else '🟠'} {a.type_anomalie or 'Anomalie détectée'}"
        body = f"{a.code_poste} — {(a.description or '')[:120]}"

        db.execute(text("""
            INSERT INTO notifications (type, title, body, source, source_id)
            VALUES (:type, :title, :body, 'anomalie', :sid)
        """), {"type": notif_type, "title": title, "body": body, "sid": source_id})
        created += 1

    # ── 2. Feedbacks négatifs (note < 3) des dernières 6h ───────────────────
    feedbacks = db.execute(text("""
        SELECT id_reponse, note_globale, commentaire, code_poste
        FROM feedback_etl
        WHERE note_globale < 3
          AND date_reponse >= NOW() - INTERVAL '6 hours'
    """)).fetchall()

    for f in feedbacks:
        source_id = str(f.id_reponse)
        already = db.execute(text("""
            SELECT 1 FROM notifications
            WHERE source = 'feedback' AND source_id = :sid
        """), {"sid": source_id}).fetchone()
        if already:
            continue

        title = f"⚠️ Feedback négatif reçu (note {f.note_globale}/5)"
        body = f"{f.code_poste} — {(f.commentaire or 'Aucun commentaire')[:100]}"

        db.execute(text("""
            INSERT INTO notifications (type, title, body, source, source_id)
            VALUES ('alerte', :title, :body, 'feedback', :sid)
        """), {"title": title, "body": body, "sid": source_id})
        created += 1

    # ── 3. Score DEX global en baisse (info récapitulative) ──────────────────
    score_row = db.execute(text("""
        SELECT ROUND(AVG(score_dex_global)::numeric, 2) AS avg_score
        FROM scores_dex_etl
        WHERE date_calcul = CURRENT_DATE
    """)).fetchone()

    if score_row and score_row.avg_score is not None:
        today_key = f"score-{score_row.avg_score}"
        already = db.execute(text("""
            SELECT 1 FROM notifications
            WHERE source = 'systeme' AND source_id = :sid
              AND created_at::date = CURRENT_DATE
        """), {"sid": today_key}).fetchone()
        if not already:
            avg = float(score_row.avg_score)
            notif_type = "critique" if avg < 5 else ("alerte" if avg < 6.5 else "info")
            title = f"📊 Score DEX global du jour : {avg}/10"
            body = "Score bas — action recommandée." if avg < 6.5 else "Score satisfaisant."
            db.execute(text("""
                INSERT INTO notifications (type, title, body, source, source_id)
                VALUES (:type, :title, :body, 'systeme', :sid)
            """), {"type": notif_type, "title": title, "body": body, "sid": today_key})
            created += 1

    db.commit()
    return created