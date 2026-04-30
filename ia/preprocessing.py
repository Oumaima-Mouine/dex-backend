# ia/preprocessing.py
# Chargement et préparation des données pour Isolation Forest.
# Inclut la gestion des valeurs manquantes et un feature engineering amélioré.

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text


# ── Chargement depuis PostgreSQL ─────────────────────────────────────────────

def load_metriques(engine) -> pd.DataFrame:
    """
    Charge la dernière métrique de chaque poste depuis PostgreSQL.
    Retourne un DataFrame avec les métriques + infos du poste.
    """
    query = text("""
        SELECT
            m.code_poste,
            p.nom_utilisateur,
            p.departement,
            p.marque,
            p.os,
            m.cpu_pct,
            m.ram_pct,
            m.disque_pct,
            m.nb_erreurs,
            m.nb_crashs,
            m.ping_ms,
            m.score_dex_it,
            m.collecte_le
        FROM (
            SELECT DISTINCT ON (code_poste) *
            FROM metriques_postes_etl
            ORDER BY code_poste, collecte_le DESC
        ) m
        JOIN postes_etl p ON p.code_poste = m.code_poste
        WHERE p.actif = true
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    print(f"[Preprocessing] {len(df)} postes chargés depuis PostgreSQL.")
    return df


def load_metriques_historique(engine, jours: int = 7) -> pd.DataFrame:
    """
    Charge l'historique des métriques sur N jours pour une analyse temporelle.
    Utile pour détecter des tendances de dégradation progressive.
    """
    query = text("""
        SELECT
            m.code_poste,
            m.cpu_pct,
            m.ram_pct,
            m.disque_pct,
            m.nb_erreurs,
            m.nb_crashs,
            m.ping_ms,
            m.score_dex_it,
            m.collecte_le,
            p.departement
        FROM metriques_postes_etl m
        JOIN postes_etl p ON p.code_poste = m.code_poste
        WHERE m.collecte_le >= NOW() - INTERVAL ':jours days'
        AND p.actif = true
        ORDER BY m.code_poste, m.collecte_le DESC
    """)

    with engine.connect() as conn:
        try:
            df = pd.read_sql(query.bindparams(jours=jours), conn)
        except Exception:
            # Fallback si la requête avec bindparams ne marche pas
            df = pd.read_sql(text(f"""
                SELECT m.code_poste, m.cpu_pct, m.ram_pct, m.disque_pct,
                       m.nb_erreurs, m.nb_crashs, m.ping_ms, m.score_dex_it,
                       m.collecte_le, p.departement
                FROM metriques_postes_etl m
                JOIN postes_etl p ON p.code_poste = m.code_poste
                WHERE m.collecte_le >= NOW() - INTERVAL '{jours} days'
                ORDER BY m.code_poste, m.collecte_le DESC
            """), conn)
    return df


# ── Préparation des features ─────────────────────────────────────────────────

FEATURE_COLS = ['cpu_pct', 'ram_pct', 'disque_pct', 'nb_erreurs', 'nb_crashs', 'ping_ms']

# Seuils normaux pour le feature engineering (valeurs métier OCP)
THRESHOLDS = {
    'cpu_pct':    {'warn': 70, 'crit': 85},
    'ram_pct':    {'warn': 75, 'crit': 88},
    'disque_pct': {'warn': 75, 'crit': 85},
    'nb_erreurs': {'warn': 3,  'crit': 10},
    'nb_crashs':  {'warn': 1,  'crit': 3},
    'ping_ms':    {'warn': 150,'crit': 500},
}


def prepare_features(df: pd.DataFrame):
    """
    Prépare les features pour Isolation Forest :
    1. Gère les valeurs manquantes (médiane par département si possible)
    2. Ajoute des features dérivées (dépassements de seuils)
    3. Normalise avec StandardScaler
    
    Retourne : (df_enrichi, X_scaled, liste_features)
    """
    df = df.copy()

    # ── 1. Gestion des NaN ───────────────────────────────────────────────────
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0
            continue

        if df[col].isna().any():
            # Essaie d'abord la médiane par département
            if 'departement' in df.columns:
                dept_median = df.groupby('departement')[col].transform('median')
                df[col] = df[col].fillna(dept_median)
            # Puis la médiane globale
            df[col] = df[col].fillna(df[col].median())
            # Puis 0 si toujours NaN
            df[col] = df[col].fillna(0)

    # ── 2. Features dérivées ─────────────────────────────────────────────────
    # Score de dépassement : nombre de métriques en zone critique
    df['nb_seuils_critiques'] = sum(
        (df[col] > THRESHOLDS[col]['crit']).astype(int)
        for col in FEATURE_COLS
        if col in THRESHOLDS
    )

    # Ratio charge globale (CPU + RAM normalisés)
    df['charge_globale'] = (df['cpu_pct'] + df['ram_pct']) / 2

    # Indicateur d'instabilité applicative
    df['instabilite_app'] = df['nb_erreurs'] + (df['nb_crashs'] * 3)

    # Score DEX inversé (anomalie si score bas)
    if 'score_dex_it' in df.columns:
        df['dex_anomalie'] = (10 - df['score_dex_it'].fillna(5)).clip(0, 10)

    # ── 3. Sélection finale des features ────────────────────────────────────
    extended_features = FEATURE_COLS + [
        'nb_seuils_critiques',
        'charge_globale',
        'instabilite_app',
    ]
    if 'dex_anomalie' in df.columns:
        extended_features.append('dex_anomalie')

    # Filtre les colonnes qui existent vraiment
    features_used = [f for f in extended_features if f in df.columns]

    X = df[features_used].copy()

    # ── 4. Normalisation StandardScaler ─────────────────────────────────────
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(
        f"[Preprocessing] Features utilisées ({len(features_used)}) : "
        f"{', '.join(features_used)}"
    )

    return df, X_scaled, features_used


# ── Analyse rapide ───────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    """Affiche un résumé rapide des métriques chargées."""
    print("\n[Preprocessing] Résumé des métriques :")
    print(f"  Postes analysés : {len(df)}")
    for col in FEATURE_COLS:
        if col in df.columns:
            print(
                f"  {col:15s} | "
                f"moy={df[col].mean():6.1f} | "
                f"max={df[col].max():6.1f} | "
                f"NaN={df[col].isna().sum()}"
            )
    if 'nb_seuils_critiques' in df.columns:
        critiques = (df['nb_seuils_critiques'] >= 2).sum()
        print(f"  Postes avec 2+ seuils critiques : {critiques}")
    print()