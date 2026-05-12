# main.py
# Point d'entrée du backend. Lance avec : uvicorn main:app --reload

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import postes, score_dex, anomalies, feedback, applications
from ia.scheduler import scheduler, run_ia_pipeline  # ← ajoute
from routers.auth import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
from routers.auth import router as auth_router


app = FastAPI(
    title="DEX OCP API",
    description="Backend pour la plateforme DEX OCP Safi",
    version="1.0.0"
)

# ── CORS : autorise React (port 5173) à appeler ce backend ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Enregistrement de toutes les routes ──
app.include_router(postes.router)
app.include_router(score_dex.router)
app.include_router(anomalies.router)
app.include_router(feedback.router)
app.include_router(applications.router)
app.include_router(auth_router)
@app.get("/")
def root():
    return {"message": "DEX OCP API opérationnelle ✅", "version": "1.0.0"}

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def startup_event():
    scheduler.start()
    run_ia_pipeline()   # ← lance une première fois au démarrage
    print("Scheduler IA démarré — analyse toutes les 30 min")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()