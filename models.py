# models.py
# Les "modèles Pydantic" définissent exactement ce que chaque
# route renvoie en JSON. FastAPI les valide automatiquement.

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PosteOut(BaseModel):
    id: int
    nom_poste: str
    utilisateur: str
    departement: str
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    score_dex: Optional[float] = None
    statut: Optional[str] = None

class ScoreGlobalOut(BaseModel):
    score_global: Optional[float] = None
    moy_cpu: Optional[float] = None
    moy_ram: Optional[float] = None
    postes_critiques: Optional[int] = None
    total_postes: Optional[int] = None

class AnomalieOut(BaseModel):
    id: int
    poste_id: int
    nom_poste: str
    departement: str
    type_anomalie: str
    score_anomalie: float
    explication_ia: Optional[str] = None
    date_detection: datetime

class FeedbackStatsOut(BaseModel):
    moy_globale: Optional[float] = None
    moy_performance: Optional[float] = None
    moy_stabilite: Optional[float] = None
    moy_support: Optional[float] = None
    nb_reponses: Optional[int] = None

class ApplicationOut(BaseModel):
    nom_application: str
    disponibilite: Optional[float] = None
    temps_reponse_ms: Optional[float] = None
    score_dex_app: Optional[float] = None