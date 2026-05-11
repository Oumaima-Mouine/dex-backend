# run_enrich.py
# Script standalone — enrichit TOUTES les anomalies avec Groq (llama-3.3-70b)
# Placez ce fichier à la RACINE de votre projet (là où se trouve .env)
# Puis lancez : python run_enrich.py

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# ── Vérifications ──────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL  = os.getenv("DATABASE_URL")

if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY manquante dans .env")
    print("   Ajoutez : GROQ_API_KEY=votre_clé")
    print("   Obtenez une clé gratuite sur : https://console.groq.com")
    sys.exit(1)

if not DATABASE_URL:
    print("❌ DATABASE_URL manquante dans .env")
    print("   Exemple : DATABASE_URL=postgresql://user:pass@localhost/dbname")
    sys.exit(1)

from groq import Groq
from sqlalchemy import create_engine, text

client = Groq(api_key=GROQ_API_KEY)
engine = create_engine(DATABASE_URL)

# ── Modèle Groq ────────────────────────────────────────────────────────────
GROQ_MODEL    = "llama-3.3-70b-versatile"
GROQ_FALLBACK = "llama-3.1-8b-instant"

# ── Config par type d'anomalie ─────────────────────────────────────────────
TYPE_CONFIG = {
    'CPU': {
        'label': 'CPU élevé',
        'desc': "Charge processeur > 90% persistant. Processus incontrôlé, antivirus actif ou tâche planifiée.",
        'hint': "Identifier processus fautif (taskmgr → CPU), désactiver tâches planifiées lourdes (taskschd.msc).",
    },
    'CPU+RAM': {
        'label': 'CPU + RAM saturés',
        'desc': "CPU et RAM > 88% simultanément. Fuite mémoire causant un swap excessif.",
        'hint': "Identifier app dominante (taskmgr), vérifier fuites mémoire (resmon.exe → Mémoire).",
    },
    'RAM': {
        'label': 'RAM insuffisante',
        'desc': "RAM saturée. Trop d'apps ouvertes ou fuite mémoire.",
        'hint': "App gourmande (taskmgr → Mémoire), vérifier pagefile.sys, envisager upgrade 16 Go.",
    },
    'Disque': {
        'label': 'Disque saturé',
        'desc': "Espace disque critique. Bloque écritures système, risque corruption données.",
        'hint': "Libérer espace (cleanmgr.exe + C:\\Windows\\Temp), WinDirStat, archiver sur serveur OCP.",
    },
    'Réseau': {
        'label': 'Latence réseau / Coupures',
        'desc': "Latence élevée ou coupures fréquentes. Câble, switch ou congestion VLAN.",
        'hint': "Ping serveur SAP (cmd), vérifier câble RJ45, contacter équipe réseau OCP.",
    },
    'Crash': {
        'label': 'Crashs système / BSOD',
        'desc': "Crashs ou BSOD répétés. Pilote défectueux, RAM défaillante, surchauffe.",
        'hint': "BlueScreenView → C:\\Windows\\Minidump, màj pilotes, mdsched.exe.",
    },
    'Application': {
        'label': 'Application indisponible',
        'desc': "SAP/VPN/Teams indisponible ou instable. Service arrêté ou problème réseau.",
        'hint': "services.msc → démarrer service, eventvwr.msc → erreurs applicatives.",
    },
}

DEPT_CTX = {
    'Finance': 'SAP FI/CO — clôtures comptables sensibles',
    'Production': 'Ligne production phosphate — arrêt critique',
    'Maintenance': 'GMAO SAP PM — requis en continu',
    'HSE': 'Sécurité/Environnement — conformité critique',
    'Qualité': 'Contrôle qualité — mesures temps réel',
    'Logistique': 'SAP MM + WMS — gestion flux phosphate',
    'RH': 'SIRH et paie — confidentialité requise',
    'Commercial': 'CRM — accès client et reporting',
    'IT': 'DSI OCP — infrastructure et administration',
    'Direction': 'Direction — reporting stratégique',
}

FALLBACK_RECS = {
    'CPU': [
        "🔴 IMMÉDIAT — Ctrl+Shift+Échap → Processus → trier CPU → terminer le processus consommateur",
        "🔧 CORRECTIF — taskschd.msc → désactiver scans/indexation pendant les heures de travail",
        "🛡️ PRÉVENTIF — Configurer Windows Defender pour scanner uniquement après 18h",
        "📊 SUIVI — Relancer l'analyse IA dans 30 min pour confirmer CPU < 70%",
    ],
    'CPU+RAM': [
        "🔴 IMMÉDIAT — Gestionnaire des tâches → trier CPU puis Mémoire → fermer l'application dominante",
        "🔧 CORRECTIF — resmon.exe → onglet Mémoire → colonne 'En attente' → identifier la fuite",
        "🛡️ PRÉVENTIF — Limiter apps ouvertes simultanément ; envisager upgrade RAM 16 Go",
        "📊 SUIVI — Vérifier CPU < 70% ET RAM > 25% disponible via resmon.exe",
    ],
    'RAM': [
        "🔴 IMMÉDIAT — Gestionnaire des tâches → Mémoire → fermer l'app la plus gourmande",
        "🔧 CORRECTIF — Panneau config → Système → Paramètres avancés → Mémoire virtuelle → automatique",
        "🛡️ PRÉVENTIF — Soumettre demande upgrade RAM 16 Go si anomalie récurrente",
        "📊 SUIVI — Vérifier RAM disponible > 20% via resmon.exe après intervention",
    ],
    'Disque': [
        "🔴 IMMÉDIAT — cleanmgr.exe → cocher TOUS les types + vider C:\\Windows\\Temp manuellement",
        "🔧 CORRECTIF — WinDirStat → identifier dossiers > 500 Mo → archiver sur serveur OCP",
        "🛡️ PRÉVENTIF — Tâche planifiée hebdomadaire : nettoyage Temp + logs > 30 jours",
        "📊 SUIVI — Vérifier espace libre > 15% après nettoyage",
    ],
    'Réseau': [
        "🔴 IMMÉDIAT — cmd → ping [IP_serveur_SAP] -t → distinguer problème local vs infrastructure",
        "🔧 CORRECTIF — Vérifier câble RJ45 (LED orange), tester autre port switch, ipconfig /flushdns",
        "🛡️ PRÉVENTIF — Contacter équipe réseau OCP pour analyse congestion VLAN",
        "📊 SUIVI — Vérifier ping < 50ms vers serveurs SAP après intervention",
    ],
    'Crash': [
        "🔴 IMMÉDIAT — BlueScreenView → analyser C:\\Windows\\Minidump → identifier driver fautif",
        "🔧 CORRECTIF — Gestionnaire de périphériques → màj pilotes suspects (GPU, réseau, chipset)",
        "🛡️ PRÉVENTIF — mdsched.exe → tester RAM au prochain redémarrage",
        "📊 SUIVI — Surveiller 24h → si crashs persistent, escalader pour remplacement matériel",
    ],
    'Application': [
        "🔴 IMMÉDIAT — services.msc → chercher SAP/Teams/VPN → démarrer si arrêté",
        "🔧 CORRECTIF — eventvwr.msc → Journaux Windows → Application → filtrer Erreur",
        "🛡️ PRÉVENTIF — PowerShell → Test-NetConnection [IP_serveur] -Port [port]",
        "📊 SUIVI — Tester l'application ; si récurrent contacter équipe applicative OCP",
    ],
}

def get_config(type_a):
    t = (type_a or '').strip()
    if t in TYPE_CONFIG: return TYPE_CONFIG[t]
    for k in TYPE_CONFIG:
        if k.lower() in t.lower() or t.lower() in k.lower():
            return TYPE_CONFIG[k]
    tl = t.lower()
    if 'cpu' in tl and 'ram' in tl: return TYPE_CONFIG['CPU+RAM']
    if 'cpu' in tl:    return TYPE_CONFIG['CPU']
    if 'ram' in tl:    return TYPE_CONFIG['RAM']
    if any(w in tl for w in ['disque','stockage']): return TYPE_CONFIG['Disque']
    if any(w in tl for w in ['réseau','reseau','ping','vpn','coupure']): return TYPE_CONFIG['Réseau']
    if any(w in tl for w in ['crash','bsod']):      return TYPE_CONFIG['Crash']
    return TYPE_CONFIG['Application']

def build_prompt(row, config):
    code  = row.get('code_poste','?')
    dept  = row.get('departement','inconnu') or 'inconnu'
    type_a= row.get('type_anomalie','?')
    desc  = row.get('description','') or ''
    score = float(row.get('score_anomalie',0) or 0)
    cpu   = float(row.get('cpu_pct',0) or 0)
    ram   = float(row.get('ram_pct',0) or 0)
    disk  = float(row.get('disque_pct',0) or 0)
    ping  = float(row.get('ping_ms',0) or 0)
    errors= int(row.get('nb_erreurs',0) or 0)
    crash = int(row.get('nb_crashs',0) or 0)
    marque= row.get('marque','') or ''
    modele= row.get('modele','') or ''

    def s(v,w,c): return '🔴' if v>=c else '🟠' if v>=w else '✅'
    m = []
    if cpu>0:    m.append(f"CPU={cpu}% {s(cpu,80,90)}")
    if ram>0:    m.append(f"RAM={ram}% {s(ram,80,90)}")
    if disk>0:   m.append(f"Disque={disk}% {s(disk,75,90)}")
    if ping>0:   m.append(f"Ping={ping}ms {s(ping,100,500)}")
    if errors>0: m.append(f"Erreurs={errors}")
    if crash>0:  m.append(f"Crashs={crash}")
    metrics = ' | '.join(m) if m else 'voir description'
    hw = f"{marque} {modele}".strip()
    dept_ctx = DEPT_CTX.get(dept, f'Département {dept} OCP Safi')
    label = config['label']

    return f"""You are a senior IT expert at OCP Safi DSI (phosphate industry, Morocco). Answer in FRENCH.

ANOMALY: {label} ({type_a})
WORKSTATION: {code}{f' [{hw}]' if hw else ''}
DEPARTMENT: {dept} — {dept_ctx}
SCORE: {score*10:.1f}/10
DESCRIPTION: "{desc}"
METRICS: {metrics}

PROBLEM: {config['desc']}
ACTIONS: {config['hint']}

Rules: mention "{desc}" in explanation, use exact Windows tools, no generic recommendations.
Order: Immediate → Corrective → Preventive → Follow-up.

Respond ONLY with valid JSON (no markdown):
{{
  "explication": "2-3 sentences on WHY '{desc}' is critical on {code} ({dept}), cause, concrete impact",
  "recommandations": [
    "🔴 IMMÉDIAT — specific action with Windows tool",
    "🔧 CORRECTIF — fix root cause",
    "🛡️ PRÉVENTIF — prevent recurrence",
    "📊 SUIVI — verify resolution"
  ]
}}"""

def call_groq(prompt, model=GROQ_MODEL):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()

def get_fallback_recs(type_a, dept=''):
    for k in FALLBACK_RECS:
        if k.lower() in (type_a or '').lower():
            recs = list(FALLBACK_RECS[k])
            if k in ('CPU','CPU+RAM') and dept in ('Production','Maintenance'):
                recs[1] = "🔧 CORRECTIF — Vérifier tâche GMAO/SAP PM en arrière-plan → replanifier hors heures de production"
            if k == 'Application' and dept == 'Finance':
                recs[0] = "🔴 IMMÉDIAT — services.msc → SAP FI/CO → démarrer si arrêté → notifier équipe Finance"
            return recs
    return FALLBACK_RECS['Application']

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Enrichissement Groq (llama-3.3-70b) — Anomalies OCP Safi")
    print("=" * 60)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                a.id_anomalie, a.code_poste, a.type_anomalie,
                a.severite, a.score_anomalie, a.description, a.resolue,
                p.departement, p.nom_utilisateur, p.marque, p.modele,
                COALESCE(m.cpu_pct, 0)    AS cpu_pct,
                COALESCE(m.ram_pct, 0)    AS ram_pct,
                COALESCE(m.disque_pct, 0) AS disque_pct,
                COALESCE(m.nb_erreurs, 0) AS nb_erreurs,
                COALESCE(m.nb_crashs, 0)  AS nb_crashs,
                COALESCE(m.ping_ms, 0)    AS ping_ms
            FROM anomalies_etl a
            LEFT JOIN postes_etl p ON p.code_poste = a.code_poste
            LEFT JOIN (
                SELECT DISTINCT ON (code_poste) *
                FROM metriques_postes_etl
                ORDER BY code_poste, collecte_le DESC
            ) m ON m.code_poste = a.code_poste
            ORDER BY a.score_anomalie DESC NULLS LAST
        """)).fetchall()

    total = len(rows)
    print(f"\n📊 {total} anomalies trouvées\n")

    if total == 0:
        print("❌ Aucune anomalie dans anomalies_etl")
        return

    success = 0
    fallbacks = 0

    for i, row in enumerate(rows, 1):
        data   = dict(row._mapping)
        code   = data['code_poste']
        type_a = data['type_anomalie']
        desc   = data.get('description','')
        dept   = data.get('departement','') or ''
        config = get_config(type_a)

        print(f"[{i:2d}/{total}] {code} | {type_a} | \"{desc}\"")

        prompt = build_prompt(data, config)
        expl   = None
        recs   = None

        # Essai Groq (modèle principal puis fallback)
        for model in [GROQ_MODEL, GROQ_FALLBACK]:
            try:
                raw = call_groq(prompt, model)
                raw = raw.replace('```json','').replace('```','').strip()
                s = raw.find('{'); e = raw.rfind('}')+1
                if s != -1 and e > s: raw = raw[s:e]
                parsed = json.loads(raw)
                expl = parsed.get('explication','').replace('\n',' ').strip()
                recs = [str(r).strip() for r in parsed.get('recommandations',[])[:4] if r]
                if expl and recs:
                    print(f"         ✅ Groq OK ({model})")
                    break
            except Exception as e:
                err = str(e)
                if '429' in err or 'rate_limit' in err.lower():
                    print(f"         ⏳ Rate limit ({model}) → modèle suivant")
                    import time; time.sleep(2)
                    continue
                print(f"         ⚠️  {model}: {e}")
                continue

        # Fallback règles métier si Groq a échoué
        if not expl or not recs:
            expl = (
                f"Anomalie '{config['label']}' détectée sur {code} ({dept}) — {desc}. "
                f"{config['desc']} Intervention IT recommandée."
            )
            recs = get_fallback_recs(type_a, dept)
            print(f"         🔄 Fallback règles métier")
            fallbacks += 1

        # Sauvegarder
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

        success += 1

    print(f"\n{'='*60}")
    print(f"✅ {success}/{total} anomalies enrichies")
    if fallbacks: print(f"🔄 {fallbacks} avec fallback règles métier")
    print("→ Rechargez votre interface DEX pour voir les nouvelles recommandations !")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
