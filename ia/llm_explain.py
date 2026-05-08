# ia/llm_explain.py
# Génère des explications IA pour les anomalies détectées.
# Détecte automatiquement le meilleur modèle Gemini disponible.

import os
import warnings
warnings.filterwarnings("ignore")
import json

import google.generativeai as genai
from dotenv import load_dotenv
from sqlalchemy import text


load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ── Détection automatique du meilleur modèle disponible ──────────────────────
_PREFERRED_MODELS = [
    'models/gemini-2.0-flash',
    'models/gemini-2.0-flash-lite',
    'models/gemini-1.5-flash-latest',
    'models/gemini-1.5-flash',
    'models/gemini-1.5-pro-latest',
    'models/gemini-1.5-pro',
    'models/gemini-pro',
]

def _pick_best_model() -> str:
    """Retourne le meilleur modèle Gemini disponible avec la clé API actuelle."""
    try:
        available = [
            m.name for m in genai.list_models()
            if 'generateContent' in m.supported_generation_methods
        ]
        for preferred in _PREFERRED_MODELS:
            if preferred in available:
                print(f"[Gemini] Modèle sélectionné : {preferred}")
                return preferred
        if available:
            print(f"[Gemini] Modèle fallback : {available[0]}")
            return available[0]
    except Exception as e:
        print(f"[Gemini] Impossible de lister les modèles : {e}")
    return 'models/gemini-pro'  # fallback ultime

_GEMINI_MODEL = _pick_best_model()

# ── Génération d'explication ─────────────────────────────────────────────────

def generate_explanation(poste_data: dict) -> str:
    prompt = f"""Tu es un expert IT au service DSI d'OCP Safi.
Analyse ce poste et réponds UNIQUEMENT en JSON valide, sans markdown, sans backticks :
{{
  "explication": "Une phrase expliquant le problème principal",
  "recommandations": ["Action 1", "Action 2", "Action 3", "Action 4"]
}}

Poste {poste_data.get('code_poste')} :
- CPU: {poste_data.get('cpu_pct')}% | RAM: {poste_data.get('ram_pct')}%
- Disque: {poste_data.get('disque_pct')}% | Ping: {poste_data.get('ping_ms')}ms
- Erreurs: {poste_data.get('nb_erreurs')} | Crashs: {poste_data.get('nb_crashs')}
- Score DEX: {poste_data.get('score_dex_it')}/10"""

    try:
        model = genai.GenerativeModel(_GEMINI_MODEL)
        response = model.generate_content(prompt)
        text = response.text.strip().replace('```json','').replace('```','').strip()
        data = json.loads(text)
        return data.get('explication', ''), data.get('recommandations', [])
    except Exception as e:
        print(f"[Gemini] Erreur : {e}")
        return _rule_based_explanation(poste_data), _rule_based_recs(poste_data)
    

def _rule_based_recs(poste_data: dict) -> list:
    recs = []
    if (poste_data.get('cpu_pct') or 0) > 85:
        recs.append("Fermer les processus non nécessaires (Task Manager)")
        recs.append("Vérifier les tâches planifiées Windows")
    if (poste_data.get('ram_pct') or 0) > 85:
        recs.append("Identifier l'application consommant la RAM")
        recs.append("Redémarrer l'application fautive")
    if (poste_data.get('disque_pct') or 0) > 80:
        recs.append("Vider C:\\Windows\\Temp")
        recs.append("Déplacer les données vers le serveur partagé")
    if (poste_data.get('ping_ms') or 0) > 500:
        recs.append("Vérifier le câble réseau physique")
        recs.append("Contacter l'équipe infrastructure réseau")
    if not recs:
        recs = ["Planifier une inspection préventive", "Surveiller à nouveau dans 30 min"]
    return recs[:4]

def _rule_based_explanation(poste_data: dict) -> str:
    """
    Fallback : génère une explication par règles métier si Gemini échoue.
    Toujours disponible, aucune dépendance externe.
    """
    cpu  = poste_data.get('cpu_pct', 0) or 0
    ram  = poste_data.get('ram_pct', 0) or 0
    disk = poste_data.get('disque_pct', 0) or 0
    err  = poste_data.get('nb_erreurs', 0) or 0
    crash = poste_data.get('nb_crashs', 0) or 0
    ping = poste_data.get('ping_ms', 0) or 0
    score = poste_data.get('score_dex_it', 0) or 0

    problems = []
    if cpu > 90:
        problems.append(f"CPU critique à {cpu}% (processus bloqué probable)")
    elif cpu > 80:
        problems.append(f"CPU élevé à {cpu}% (surcharge applicative)")

    if ram > 90:
        problems.append(f"RAM saturée à {ram}% (manque de mémoire)")
    elif ram > 80:
        problems.append(f"RAM élevée à {ram}%")

    if disk > 90:
        problems.append(f"Disque plein à {disk}% (nettoyage urgent requis)")
    elif disk > 80:
        problems.append(f"Disque presque plein à {disk}%")

    if err > 15:
        problems.append(f"{err} erreurs applicatives (instabilité critique)")
    elif err > 5:
        problems.append(f"{err} erreurs applicatives détectées")

    if crash > 5:
        problems.append(f"{crash} crashs (redémarrage recommandé)")
    elif crash > 2:
        problems.append(f"{crash} crashs détectés")

    if ping > 1000:
        problems.append(f"Latence réseau critique à {ping}ms")
    elif ping > 500:
        problems.append(f"Latence réseau élevée à {ping}ms")

    if not problems:
        return (
            f"Anomalie composite détectée — score DEX à {score}/10, "
            f"combinaison de métriques hors normes nécessitant une inspection."
        )

    main = problems[0]
    if len(problems) > 1:
        secondary = problems[1]
        return f"{main}, combiné avec {secondary} — intervention recommandée."
    return f"{main} — vérification et optimisation recommandées."


# ── Enrichissement en masse ──────────────────────────────────────────────────

def enrich_anomalies_with_explanation(engine) -> int:
    """
    Met à jour les anomalies sans explication dans PostgreSQL.
    Retourne le nombre d'anomalies enrichies.
    """
    # 1. Récupère les anomalies sans explication
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                a.id_anomalie,
                a.code_poste,
                a.type_anomalie,
                m.cpu_pct,
                m.ram_pct,
                m.disque_pct,
                m.nb_erreurs,
                m.nb_crashs,
                m.ping_ms,
                m.score_dex_it
            FROM anomalies_etl a
            JOIN (
                SELECT DISTINCT ON (code_poste) *
                FROM metriques_postes_etl
                ORDER BY code_poste, collecte_le DESC
            ) m ON m.code_poste = a.code_poste
            WHERE a.explication_ia IS NULL
            AND a.resolue = false
            ORDER BY a.score_anomalie DESC
            LIMIT 10
        """))
        rows = result.fetchall()

    if not rows:
        print("[Gemini] Aucune anomalie à enrichir.")
        return 0

    # 2. Génère et sauvegarde chaque explication
    count = 0
    for row in rows:
        data = dict(row._mapping)
        explication = generate_explanation(data)
        explication, recommandations = generate_explanation(data)

        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE anomalies_etl
        SET explication_ia = :explication,
            recommandations = :recs::jsonb
        WHERE id_anomalie = :id
    """), {
        'explication': explication,
        'recs': json.dumps(recommandations),
        'id': data['id_anomalie'],
            })
            conn.commit()

        print(f"[Gemini] {data['code_poste']} → {explication[:70]}...")
        count += 1

    return count