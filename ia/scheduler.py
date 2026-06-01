# ia/scheduler.py
# Scheduler APScheduler — lance le pipeline IA toutes les 30 minutes.
# Importé dans main.py pour démarrer automatiquement avec FastAPI.

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from ia.preprocessing import load_metriques, prepare_features, print_summary
from ia.anomaly_detection import detect_anomalies, save_anomalies
from ia.llm_explain import enrich_anomalies_with_explanation
from database import engine
from routers.notifications import _do_generate
from database import SessionLocal
 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s — %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger("DEX-IA")


def run_ia_pipeline():
    """
    Pipeline complet :
      1. Charge les métriques depuis PostgreSQL
      2. Prépare et normalise les features
      3. Détecte les anomalies avec Isolation Forest
      4. Sauvegarde les anomalies dans PostgreSQL
      5. Enrichit chaque anomalie avec une explication Gemini
    """
    logger.info("=" * 50)
    logger.info("Démarrage du pipeline IA DEX...")

    try:
        # ── Étape 1 : Chargement ─────────────────────────────────────────────
        df = load_metriques(engine)

        if df.empty:
            logger.warning("Aucune métrique disponible — pipeline annulé.")
            return

        logger.info(f"{len(df)} postes chargés.")

        # ── Étape 2 : Préparation ────────────────────────────────────────────
        df, X_scaled, features = prepare_features(df)
        print_summary(df)

        # ── Étape 3 : Isolation Forest ───────────────────────────────────────
        df_result    = detect_anomalies(df, X_scaled, contamination=0.1)
        nb_anomalies = (df_result['prediction'] == -1).sum()
        logger.info(f"Isolation Forest : {nb_anomalies} anomalie(s) détectée(s) sur {len(df)} postes.")

        if nb_anomalies == 0:
            logger.info("Aucune anomalie — pipeline terminé.")
            return

        # ── Étape 4 : Sauvegarde ─────────────────────────────────────────────
        inserted = save_anomalies(df_result, engine)
        logger.info(f"{inserted} anomalie(s) sauvegardée(s) dans PostgreSQL.")

        # ── Étape 5 : Explications Gemini ────────────────────────────────────
        logger.info("Génération des explications IA (Gemini)...")
        enriched = enrich_anomalies_with_explanation(engine)
        logger.info(f"{enriched} explication(s) générée(s).")

        logger.info("Pipeline IA terminé avec succès.")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Erreur critique dans le pipeline IA : {e}", exc_info=True)


# ── Scheduler global (importé dans main.py) ──────────────────────────────────
scheduler = BackgroundScheduler(timezone='Europe/Paris')
scheduler.add_job(
    run_ia_pipeline,
    trigger='interval',
    minutes=30,
    id='ia_pipeline',
    replace_existing=True,
)



def run_notification_generation():
    db = SessionLocal()
    try:
        n = _do_generate(db)
        print(f"[Notifications] {n} nouvelle(s) générée(s)")
    finally:
        db.close()
 
# Planifier toutes les 15 minutes (ajuster selon besoin)
scheduler.add_job(run_notification_generation, "interval", minutes=15, id="notif_gen")