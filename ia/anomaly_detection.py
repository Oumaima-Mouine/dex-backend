# ia/anomaly_detection.py
# Détection d'anomalies avec Isolation Forest.
# Inclut un scoring composite et une classification de sévérité affinée.

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import text
from datetime import datetime


# ── Détection ────────────────────────────────────────────────────────────────

def detect_anomalies(df: pd.DataFrame, X_scaled: np.ndarray, contamination: float = 0.1) -> pd.DataFrame:
    """
    Applique Isolation Forest sur les métriques normalisées.
    
    contamination=0.1 → 10% des postes considérés comme potentiellement anormaux.
    Retourne le DataFrame enrichi avec :
      - prediction      : -1 = anomalie, +1 = normal
      - anomaly_score   : score brut (plus négatif = plus anormal)
      - score_normalise : score entre 0 et 1 (1 = très anormal)
    """
    model = IsolationForest(
        n_estimators=200,        # plus d'arbres = plus précis
        contamination=contamination,
        max_samples='auto',
        random_state=42,
        n_jobs=-1                # utilise tous les CPU disponibles
    )

    predictions = model.fit_predict(X_scaled)
    scores      = model.score_samples(X_scaled)

    df = df.copy()
    df['prediction']    = predictions
    df['anomaly_score'] = scores

    # Normalisation robuste entre 0 et 1
    min_s = scores.min()
    max_s = scores.max()
    df['score_normalise'] = (scores - max_s) / (min_s - max_s + 1e-9)

    # Score composite : combine Isolation Forest + règles métier
    df['score_composite'] = df.apply(
        lambda row: _composite_score(row, row['score_normalise']), axis=1
    )

    return df


def _composite_score(row, iso_score: float) -> float:
    """
    Score composite = 60% Isolation Forest + 40% règles métier.
    Les règles métier pénalisent les dépassements de seuils critiques.
    """
    rule_score = 0.0
    penalties  = 0

    if row.get('cpu_pct', 0) > 90:
        rule_score += 0.4; penalties += 1
    elif row.get('cpu_pct', 0) > 80:
        rule_score += 0.2

    if row.get('ram_pct', 0) > 90:
        rule_score += 0.3; penalties += 1
    elif row.get('ram_pct', 0) > 80:
        rule_score += 0.15

    if row.get('disque_pct', 0) > 90:
        rule_score += 0.2; penalties += 1
    elif row.get('disque_pct', 0) > 80:
        rule_score += 0.1

    if row.get('nb_erreurs', 0) > 15:
        rule_score += 0.3; penalties += 1
    elif row.get('nb_erreurs', 0) > 5:
        rule_score += 0.15

    if row.get('nb_crashs', 0) > 5:
        rule_score += 0.25; penalties += 1
    elif row.get('nb_crashs', 0) > 2:
        rule_score += 0.1

    if row.get('ping_ms', 0) > 1000:
        rule_score += 0.2; penalties += 1
    elif row.get('ping_ms', 0) > 500:
        rule_score += 0.1

    # Plafonne le score des règles à 1.0
    rule_score = min(rule_score, 1.0)

    # Bonus si plusieurs seuils dépassés simultanément
    if penalties >= 3:
        rule_score = min(rule_score + 0.15, 1.0)

    return round(0.6 * iso_score + 0.4 * rule_score, 4)


# ── Classification de sévérité ───────────────────────────────────────────────

def classify_severity(score: float) -> str:
    """Sévérité basée sur le score composite (0 → 1)."""
    if score >= 0.75:
        return 'critique'
    elif score >= 0.55:
        return 'haute'
    elif score >= 0.35:
        return 'moyenne'
    else:
        return 'faible'


def determine_type(row) -> str:
    """Détermine le type principal d'anomalie selon les métriques."""
    checks = [
        (row.get('cpu_pct', 0) > 85,           'CPU élevé'),
        (row.get('ram_pct', 0) > 85,            'RAM insuffisante'),
        (row.get('disque_pct', 0) > 85,         'Disque plein'),
        (row.get('nb_erreurs', 0) > 10,         'Erreurs applicatives'),
        (row.get('nb_crashs', 0) > 3,           'Crashs fréquents'),
        (row.get('ping_ms', 0) > 500,           'Latence réseau'),
        (row.get('score_dex_it', 10) < 4,       'Score DEX critique'),
    ]
    for condition, label in checks:
        if condition:
            return label
    return 'Anomalie composite'


# ── Sauvegarde PostgreSQL ────────────────────────────────────────────────────

def save_anomalies(df_result: pd.DataFrame, engine) -> int:
    """
    Sauvegarde les anomalies détectées dans anomalies_etl.
    Supprime d'abord les anciennes anomalies non résolues de la dernière heure
    pour éviter les doublons entre deux cycles.
    Retourne le nombre de lignes insérées.
    """
    anomalies = df_result[df_result['prediction'] == -1].copy()
    anomalies  = anomalies.sort_values('score_composite', ascending=False)

    if anomalies.empty:
        print("[IA] Aucune anomalie détectée dans ce cycle.")
        return 0

    with engine.connect() as conn:
        # Supprime les anomalies non résolues de la dernière heure
        conn.execute(text("""
            DELETE FROM anomalies_etl
            WHERE resolue = false
            AND detecte_le >= NOW() - INTERVAL '1 hour'
        """))

        inserted = 0
        for _, row in anomalies.iterrows():
            severite      = classify_severity(row['score_composite'])
            type_anomalie = determine_type(row)

            description = (
                f"CPU: {row['cpu_pct']}% | "
                f"RAM: {row['ram_pct']}% | "
                f"Disque: {row['disque_pct']}% | "
                f"Erreurs: {row['nb_erreurs']} | "
                f"Crashs: {row['nb_crashs']} | "
                f"Ping: {row['ping_ms']}ms | "
                f"Score DEX: {row['score_dex_it']}/10"
            )

            conn.execute(text("""
                INSERT INTO anomalies_etl
                    (code_poste, type_anomalie, severite, score_anomalie,
                     description, detecte_le, resolue)
                VALUES
                    (:code_poste, :type_anomalie, :severite, :score_anomalie,
                     :description, :detecte_le, false)
            """), {
                'code_poste':     row['code_poste'],
                'type_anomalie':  type_anomalie,
                'severite':       severite,
                'score_anomalie': round(float(row['score_composite']), 4),
                'description':    description,
                'detecte_le':     datetime.now(),
                'confiance_ia': round(float(row['score_composite']) * 100, 1),
            })
            inserted += 1

            print(
                f"  [{severite.upper():8s}] {row['code_poste']:15s} "
                f"| {type_anomalie:22s} | score={row['score_composite']:.3f}"
            )

        conn.commit()

    print(f"[IA] {inserted} anomalies sauvegardées dans PostgreSQL.")
    return inserted