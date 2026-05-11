# ia/llm_explain.py
# Migration Gemini → Groq (llama-3.3-70b-versatile)
# Groq est 10x plus rapide et gratuit.
# Aucun changement dans le reste du projet — même interface.

import os
import json
import re
import warnings
warnings.filterwarnings("ignore")

from groq import Groq
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

# ── Client Groq ───────────────────────────────────────────────────────────────
_groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Modèles Groq disponibles (du meilleur au fallback)
# llama-3.3-70b-versatile = meilleur rapport qualité/vitesse
# llama-3.1-8b-instant    = ultra-rapide si quota dépassé
_GROQ_MODEL = "llama-3.3-70b-versatile"
_GROQ_FALLBACK = "llama-3.1-8b-instant"


def _call_groq(prompt: str, model: str = None) -> str:
    """Appelle l'API Groq et retourne le texte brut."""
    m = model or _GROQ_MODEL
    response = _groq_client.chat.completions.create(
        model=m,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=700,
    )
    return response.choices[0].message.content.strip()


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG PAR TYPE D'ANOMALIE — noms RÉELS de votre BDD
# ("CPU", "Application", "Crash", "Réseau", "Disque", "CPU+RAM")
# ══════════════════════════════════════════════════════════════════════════════

ANOMALY_TYPE_CONFIG = {
    'CPU': {
        'label': 'CPU élevé',
        'problem_desc': (
            "Charge processeur anormalement élevée (> 90% persistant). "
            "Causes : processus incontrôlé, antivirus en scan, tâche planifiée en heures ouvrées."
        ),
        'actions_hint': (
            "Identifier le processus fautif (taskmgr → trier par CPU), "
            "désactiver les tâches planifiées lourdes (taskschd.msc) pendant les heures de travail."
        ),
    },
    'CPU+RAM': {
        'label': 'CPU + RAM saturés',
        'problem_desc': (
            "CPU et RAM saturés simultanément (> 88%). "
            "Fuite mémoire probable causant un swap excessif qui surcharge le processeur."
        ),
        'actions_hint': (
            "Identifier l'application dominante (taskmgr CPU + Mémoire), "
            "vérifier fuites mémoire (resmon.exe → Mémoire → En attente), "
            "envisager upgrade RAM si récurrent."
        ),
    },
    'RAM': {
        'label': 'RAM insuffisante',
        'problem_desc': (
            "Mémoire vive saturée. "
            "Trop d'applications ouvertes ou fuite mémoire applicative."
        ),
        'actions_hint': (
            "Identifier l'application gourmande (taskmgr → Mémoire), "
            "vérifier pagefile.sys, envisager upgrade RAM 16 Go."
        ),
    },
    'Disque': {
        'label': 'Disque saturé',
        'problem_desc': (
            "Espace disque critique. "
            "Bloque les écritures système, risque de corruption de données."
        ),
        'actions_hint': (
            "Libérer espace (cleanmgr.exe + C:\\Windows\\Temp), "
            "identifier gros dossiers (WinDirStat), archiver sur serveur OCP."
        ),
    },
    'Réseau': {
        'label': 'Latence réseau / Coupures',
        'problem_desc': (
            "Latence réseau élevée ou coupures fréquentes. "
            "Causes : câble défaillant, port switch surchargé, congestion VLAN."
        ),
        'actions_hint': (
            "Tester ping serveur SAP (cmd → ping [IP] -t), "
            "vérifier câble RJ45 et port switch, "
            "contacter équipe réseau OCP pour analyse VLAN."
        ),
    },
    'Crash': {
        'label': 'Crashs système / BSOD',
        'problem_desc': (
            "Crashs répétés ou BSOD détecté. "
            "Causes : pilote défectueux, RAM défaillante, surchauffe."
        ),
        'actions_hint': (
            "Analyser minidumps (C:\\Windows\\Minidump avec BlueScreenView), "
            "mettre à jour pilotes suspects, tester RAM (mdsched.exe)."
        ),
    },
    'Application': {
        'label': 'Application indisponible',
        'problem_desc': (
            "Application métier critique indisponible ou instable "
            "(SAP > 30min, VPN en échec, Teams instable). "
            "Causes : service arrêté, problème réseau, DLL corrompue."
        ),
        'actions_hint': (
            "Vérifier service démarré (services.msc), "
            "consulter Observateur événements (eventvwr.msc → Application), "
            "tester connectivité serveur applicatif OCP."
        ),
    },
}

_DEPT_CONTEXT = {
    'Finance':      'SAP FI/CO actif — clôtures comptables sensibles',
    'Production':   'Ligne de production phosphate — arrêt = perte immédiate',
    'Maintenance':  'Technicien terrain — GMAO (SAP PM) requis en continu',
    'HSE':          'Sécurité/Environnement — conformité réglementaire critique',
    'Qualité':      'Contrôle qualité phosphate — outils mesure temps réel',
    'Logistique':   'SAP MM + WMS — gestion flux phosphate temps réel',
    'RH':           'SIRH et paie — confidentialité et disponibilité',
    'Commercial':   'CRM — accès client et reporting commercial',
    'IT':           'DSI OCP — infrastructure et administration systèmes',
    'Direction':    'Direction — reporting et tableaux de bord stratégiques',
}

def _get_config(type_anomalie: str) -> dict:
    """Retourne la config du type avec match exact → partiel → fallback."""
    t = (type_anomalie or '').strip()
    if t in ANOMALY_TYPE_CONFIG:
        return ANOMALY_TYPE_CONFIG[t]
    for key in ANOMALY_TYPE_CONFIG:
        if key.lower() in t.lower() or t.lower() in key.lower():
            return ANOMALY_TYPE_CONFIG[key]
    # Détection par mots-clés
    tl = t.lower()
    if 'cpu' in tl and 'ram' in tl: return ANOMALY_TYPE_CONFIG['CPU+RAM']
    if 'cpu' in tl:                 return ANOMALY_TYPE_CONFIG['CPU']
    if 'ram' in tl:                 return ANOMALY_TYPE_CONFIG['RAM']
    if any(w in tl for w in ['disque','stockage']): return ANOMALY_TYPE_CONFIG['Disque']
    if any(w in tl for w in ['réseau','reseau','ping','vpn','coupure']): return ANOMALY_TYPE_CONFIG['Réseau']
    if any(w in tl for w in ['crash','bsod']):      return ANOMALY_TYPE_CONFIG['Crash']
    if any(w in tl for w in ['application','sap','teams','app']): return ANOMALY_TYPE_CONFIG['Application']
    return ANOMALY_TYPE_CONFIG['CPU']


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCTION DU PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def _build_prompt(poste_data: dict, config: dict) -> str:
    code  = poste_data.get('code_poste', '?')
    dept  = poste_data.get('departement', 'inconnu') or 'inconnu'
    type_a = poste_data.get('type_anomalie', '?')
    desc  = poste_data.get('description', '') or ''
    score = float(poste_data.get('score_anomalie', 0) or 0)
    cpu   = float(poste_data.get('cpu_pct', 0) or 0)
    ram   = float(poste_data.get('ram_pct', 0) or 0)
    disk  = float(poste_data.get('disque_pct', 0) or 0)
    ping  = float(poste_data.get('ping_ms', 0) or 0)
    errors= int(poste_data.get('nb_erreurs', 0) or 0)
    crash = int(poste_data.get('nb_crashs', 0) or 0)
    marque= poste_data.get('marque', '') or ''
    modele= poste_data.get('modele', '') or ''

    label     = config['label']
    dept_ctx  = _DEPT_CONTEXT.get(dept, f'Département {dept} OCP Safi')

    # Section métriques
    def s(v, w, c): return '🔴' if v >= c else '🟠' if v >= w else '✅'
    m_lines = []
    if cpu > 0:    m_lines.append(f"CPU={cpu}% {s(cpu,80,90)}")
    if ram > 0:    m_lines.append(f"RAM={ram}% {s(ram,80,90)}")
    if disk > 0:   m_lines.append(f"Disque={disk}% {s(disk,75,90)}")
    if ping > 0:   m_lines.append(f"Ping={ping}ms {s(ping,100,500)}")
    if errors > 0: m_lines.append(f"Erreurs={errors}")
    if crash > 0:  m_lines.append(f"Crashs={crash}")
    metrics = ' | '.join(m_lines) if m_lines else 'voir description'

    hw = f"{marque} {modele}".strip()

    return f"""You are a senior IT expert at OCP Safi DSI (phosphate industry, Morocco).
Generate a precise EXPLANATION and RECOMMENDATIONS for this specific anomaly.
Answer in FRENCH only.

ANOMALY: {label} ({type_a})
WORKSTATION: {code}{f' [{hw}]' if hw else ''}
DEPARTMENT: {dept} — {dept_ctx}
SCORE: {score*10:.1f}/10
DESCRIPTION: "{desc}"
METRICS: {metrics}

PROBLEM: {config['problem_desc']}
ACTIONS: {config['actions_hint']}

STRICT RULES:
1. Mention the real description "{desc}" in the explanation
2. Recommendations SPECIFIC to "{label}" with exact Windows tools
3. Do NOT write generic recommendations like "close processes" alone
4. Order: Immediate → Corrective → Preventive → Follow-up

Respond ONLY with valid JSON (no markdown, no backticks):
{{
  "explication": "2-3 sentences explaining WHY '{desc}' is critical on {code} ({dept}), probable cause, concrete impact",
  "recommandations": [
    "🔴 IMMÉDIAT — specific urgent action with Windows tool for {label}",
    "🔧 CORRECTIF — fix the root cause of {label} on {code}",
    "🛡️ PRÉVENTIF — prevent recurrence of {label}",
    "📊 SUIVI — how to verify {label} is resolved on {code}"
  ]
}}"""


# ══════════════════════════════════════════════════════════════════════════════
# FALLBACKS SPÉCIFIQUES PAR TYPE
# ══════════════════════════════════════════════════════════════════════════════

_FALLBACK_RECS = {
    'CPU': [
        "🔴 IMMÉDIAT — Ctrl+Shift+Échap → Processus → trier par CPU → terminer le processus consommateur",
        "🔧 CORRECTIF — taskschd.msc → désactiver tout scan/indexation planifié pendant les heures de travail",
        "🛡️ PRÉVENTIF — Configurer Windows Defender pour scanner après 18h uniquement",
        "📊 SUIVI — Relancer l'analyse IA dans 30 min pour confirmer CPU < 70%",
    ],
    'CPU+RAM': [
        "🔴 IMMÉDIAT — Gestionnaire des tâches → trier CPU puis Mémoire → fermer l'application dominante",
        "🔧 CORRECTIF — resmon.exe → onglet Mémoire → colonne 'En attente' → identifier la fuite mémoire",
        "🛡️ PRÉVENTIF — Limiter les applications ouvertes ; envisager upgrade RAM 16 Go si récurrent",
        "📊 SUIVI — Vérifier CPU < 70% ET RAM disponible > 25% via resmon.exe",
    ],
    'RAM': [
        "🔴 IMMÉDIAT — Gestionnaire des tâches → Mémoire → fermer ou redémarrer l'app la plus gourmande",
        "🔧 CORRECTIF — Panneau de config → Système → Paramètres avancés → Mémoire virtuelle → gestion automatique",
        "🛡️ PRÉVENTIF — Soumettre demande upgrade RAM 16 Go si anomalie récurrente sur ce poste",
        "📊 SUIVI — Vérifier RAM disponible > 20% via resmon.exe après intervention",
    ],
    'Disque': [
        "🔴 IMMÉDIAT — cleanmgr.exe → cocher TOUS les types → vider C:\\Windows\\Temp manuellement",
        "🔧 CORRECTIF — WinDirStat → identifier dossiers > 500 Mo → archiver sur serveur partagé OCP",
        "🛡️ PRÉVENTIF — Tâche planifiée hebdomadaire : nettoyage Temp + logs > 30 jours",
        "📊 SUIVI — Vérifier espace libre > 15% après nettoyage",
    ],
    'Réseau': [
        "🔴 IMMÉDIAT — cmd → ping [IP_serveur_SAP] -t → distinguer problème local vs infrastructure OCP",
        "🔧 CORRECTIF — Vérifier câble RJ45 (LED orange = défaut), tester autre port switch, ipconfig /flushdns",
        "🛡️ PRÉVENTIF — Contacter équipe réseau OCP avec résultats ping pour analyse congestion VLAN",
        "📊 SUIVI — Vérifier ping < 50ms vers serveurs SAP OCP après intervention",
    ],
    'Crash': [
        "🔴 IMMÉDIAT — BlueScreenView → analyser C:\\Windows\\Minidump → identifier driver/module fautif",
        "🔧 CORRECTIF — Gestionnaire de périphériques → mettre à jour pilotes suspects (GPU, réseau, chipset)",
        "🛡️ PRÉVENTIF — mdsched.exe → tester RAM au prochain redémarrage",
        "📊 SUIVI — Surveiller 24h — si crashs persistent, escalader pour remplacement matériel",
    ],
    'Application': [
        "🔴 IMMÉDIAT — services.msc → chercher SAP/Teams/VPN → démarrer le service s'il est arrêté",
        "🔧 CORRECTIF — eventvwr.msc → Journaux Windows → Application → filtrer Erreur → identifier l'app fautive",
        "🛡️ PRÉVENTIF — PowerShell → Test-NetConnection [IP_serveur] -Port [port] → vérifier connectivité",
        "📊 SUIVI — Tester l'application après redémarrage ; si récurrent contacter équipe applicative OCP",
    ],
}

def _fallback_recs(type_anomalie: str, dept: str = '') -> list[str]:
    for key in _FALLBACK_RECS:
        if key.lower() in (type_anomalie or '').lower():
            recs = list(_FALLBACK_RECS[key])
            # Personnalisation département
            if key in ('CPU', 'CPU+RAM') and dept in ('Production', 'Maintenance'):
                recs[1] = "🔧 CORRECTIF — Vérifier si une tâche GMAO/SAP PM tourne en arrière-plan → replanifier hors heures de production"
            if key == 'Application' and dept == 'Finance':
                recs[0] = "🔴 IMMÉDIAT — services.msc → vérifier SAP FI/CO démarré → notifier équipe Finance immédiatement si arrêté"
            return recs
    return _FALLBACK_RECS.get('CPU', [])

def _fallback_explanation(poste_data: dict, config: dict) -> str:
    code  = poste_data.get('code_poste', '?')
    dept  = poste_data.get('departement', '') or ''
    desc  = poste_data.get('description', '') or config['label']
    score = float(poste_data.get('score_anomalie', 0) or 0)
    return (
        f"Anomalie '{config['label']}' détectée sur le poste {code} ({dept}) "
        f"avec un score de {score*10:.1f}/10. "
        f"Problème signalé : {desc}. "
        f"{config['problem_desc']} "
        f"Une intervention IT est recommandée en priorité."
    )


# ══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION PRINCIPALE — remplace generate_explanation_and_recs()
# ══════════════════════════════════════════════════════════════════════════════

def generate_explanation_and_recs(poste_data: dict) -> tuple[str, list[str]]:
    """
    Génère via Groq (llama-3.3-70b) une explication + 4 recommandations
    ciblées selon le type d'anomalie réel de la BDD.
    Fallback automatique si Groq échoue.
    """
    code   = poste_data.get('code_poste', '?')
    type_a = poste_data.get('type_anomalie', '?')
    dept   = poste_data.get('departement', '') or ''

    config = _get_config(type_a)
    prompt = _build_prompt(poste_data, config)

    print(f"[Groq] ⏳ {code} | {type_a} → {config['label']}")

    # Essai modèle principal
    for model in [_GROQ_MODEL, _GROQ_FALLBACK]:
        try:
            raw = _call_groq(prompt, model)
            raw = raw.replace('```json', '').replace('```', '').strip()

            # Extraire le JSON même si du texte entoure
            start = raw.find('{')
            end   = raw.rfind('}') + 1
            if start != -1 and end > start:
                raw = raw[start:end]

            data = json.loads(raw)
            expl = data.get('explication', '').replace('\n', ' ').strip()
            recs = [str(r).strip() for r in data.get('recommandations', [])[:4] if r]

            if not expl or len(recs) == 0:
                raise ValueError("Réponse incomplète")

            print(f"[Groq] ✅ {code} | {type_a} | modèle={model} | {len(recs)} recs")
            return expl, recs

        except json.JSONDecodeError as e:
            print(f"[Groq] ⚠️  JSON invalide ({model}) {code}: {e} — essai fallback modèle")
            continue
        except Exception as e:
            err = str(e)
            if 'rate_limit' in err.lower() or '429' in err:
                print(f"[Groq] ⏳ Rate limit ({model}) — passage au modèle suivant")
                continue
            print(f"[Groq] ❌ Erreur ({model}) {code}: {e}")
            break

    # Fallback règles métier
    print(f"[Groq] 🔄 Fallback règles pour {code} | {type_a}")
    return _fallback_explanation(poste_data, config), _fallback_recs(type_a, dept)


# ══════════════════════════════════════════════════════════════════════════════
# ENRICHISSEMENT EN MASSE — appelé par le scheduler
# ══════════════════════════════════════════════════════════════════════════════

def enrich_anomalies_with_explanation(engine, force_regen: bool = False) -> int:
    """
    Enrichit les anomalies avec explication + recommandations via Groq.

    force_regen=False (défaut) : seulement les anomalies avec explication_ia NULL
    force_regen=True           : régénère TOUTES les anomalies non résolues
    """
    condition = "" if force_regen else "AND a.explication_ia IS NULL"

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                a.id_anomalie,
                a.code_poste,
                a.type_anomalie,
                a.severite,
                a.score_anomalie,
                a.description,
                p.departement,
                p.nom_utilisateur,
                p.marque,
                p.modele,
                COALESCE(m.cpu_pct, 0)      AS cpu_pct,
                COALESCE(m.ram_pct, 0)      AS ram_pct,
                COALESCE(m.disque_pct, 0)   AS disque_pct,
                COALESCE(m.nb_erreurs, 0)   AS nb_erreurs,
                COALESCE(m.nb_crashs, 0)    AS nb_crashs,
                COALESCE(m.ping_ms, 0)      AS ping_ms,
                COALESCE(m.score_dex_it, 0) AS score_dex_it
            FROM anomalies_etl a
            LEFT JOIN postes_etl p ON p.code_poste = a.code_poste
            LEFT JOIN (
                SELECT DISTINCT ON (code_poste) *
                FROM metriques_postes_etl
                ORDER BY code_poste, collecte_le DESC
            ) m ON m.code_poste = a.code_poste
            WHERE 1=1
            {condition}
            ORDER BY a.score_anomalie DESC NULLS LAST
            LIMIT 20
        """)).fetchall()

    if not rows:
        print("[Groq] Aucune anomalie à enrichir.")
        return 0

    mode = "FORCÉ" if force_regen else "normal (NULL uniquement)"
    print(f"[Groq] Mode : {mode} — {len(rows)} anomalie(s)")

    count = 0
    for row in rows:
        data = dict(row._mapping)
        expl, recs = generate_explanation_and_recs(data)

        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE anomalies_etl
                SET explication_ia  = :expl,
                    recommandations = CAST(:recs AS JSONB)
                WHERE id_anomalie   = :id
            """), {
                'expl': expl,
                'recs': json.dumps(recs, ensure_ascii=False),
                'id':   data['id_anomalie'],
            })
            conn.commit()

        print(f"[Groq] ✅ {data['code_poste']} | {data['type_anomalie']} → sauvegardé")
        count += 1

    return count


def force_reenrich_all(engine) -> int:
    """Force la régénération de toutes les anomalies. Lance une seule fois."""
    print("[Groq] 🔄 Régénération forcée de toutes les recommandations...")
    total = enrich_anomalies_with_explanation(engine, force_regen=True)
    print(f"[Groq] ✅ {total} anomalie(s) enrichie(s) avec Groq.")
    return total