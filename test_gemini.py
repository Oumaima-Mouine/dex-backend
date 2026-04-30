# test_gemini.py
# Lance avec : python test_gemini.py
# Ce script liste les modèles Gemini disponibles avec ta clé API
# et teste la génération d'une explication exemple.

import os
import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("❌ GEMINI_API_KEY non trouvée dans .env")
    exit(1)

genai.configure(api_key=API_KEY)

print("=" * 55)
print("   Modèles Gemini disponibles avec ta clé API")
print("=" * 55)

available = []
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"  ✅ {m.name}")
        available.append(m.name)

print(f"\nTotal : {len(available)} modèles disponibles")

if not available:
    print("❌ Aucun modèle disponible — vérifie ta clé API")
    exit(1)

# Choisit le meilleur modèle disponible
preferred = [
    'models/gemini-2.0-flash',
    'models/gemini-2.0-flash-lite',
    'models/gemini-1.5-flash-latest',
    'models/gemini-1.5-flash',
    'models/gemini-1.5-pro-latest',
    'models/gemini-1.5-pro',
    'models/gemini-pro',
]
chosen = None
for p in preferred:
    if p in available:
        chosen = p
        break

if not chosen:
    chosen = available[0]

print(f"\n✅ Modèle choisi : {chosen}")
print("\nTest de génération...")
print("-" * 55)

try:
    model = genai.GenerativeModel(chosen)
    response = model.generate_content(
        "Tu es expert IT OCP Safi. Explique en 1 phrase pourquoi "
        "un poste avec CPU 94%, RAM 88%, 15 erreurs est anormal."
    )
    print(f"Réponse Gemini : {response.text.strip()}")
    print("\n✅ Gemini fonctionne correctement !")
    print(f"\n👉 Copie ce nom dans llm_explain.py :\n   '{chosen}'")
except Exception as e:
    print(f"❌ Erreur : {e}")