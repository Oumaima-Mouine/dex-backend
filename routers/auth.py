# routers/auth.py
# Authentication — Sign In / Sign Up avec JWT
# pip install python-jose[cryptography] passlib[bcrypt] python-multipart

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel 
# from passlib.context import CryptContext
import bcrypt as bcrypt_lib
from jose import JWTError, jwt
from datetime import datetime, timedelta
from database import get_db
import os

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ── Config ───────────────────────────────────────────────────────────────────
SECRET_KEY      = os.getenv("SECRET_KEY", "ocp-dex-secret-key-change-in-production")
ALGORITHM       = "HS256"
ACCESS_EXPIRE   = 60          # minutes
REFRESH_EXPIRE  = 60 * 24 * 7 # minutes (7 jours)

# pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ── Schemas Pydantic ──────────────────────────────────────────────────────────
class SignUpRequest(BaseModel):
    nom_complet: str
    email:       str
    password:    str
    updates_email: bool = False

class SignInRequest(BaseModel):
    email:    str
    password: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    user:          dict

class RefreshRequest(BaseModel):
    refresh_token: str


# ── Helpers JWT ───────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt_lib.gensalt()
    return bcrypt_lib.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt_lib.checkpw(
        plain.encode('utf-8'),
        hashed.encode('utf-8')
    )

def create_token(data: dict, expires_minutes: int) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ── Dependency — utilisateur courant ─────────────────────────────────────────
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token invalide")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expiré ou invalide")

    result = db.execute(
        text("SELECT id, nom_complet, email, role FROM utilisateurs_auth WHERE id = :id"),
        {"id": user_id}
    ).fetchone()

    if not result:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    return dict(result._mapping)


# ── POST /signup ──────────────────────────────────────────────────────────────
@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(body: SignUpRequest, db: Session = Depends(get_db)):
    # Vérifier si l'email existe déjà
    existing = db.execute(
        text("SELECT id FROM utilisateurs_auth WHERE email = :email"),
        {"email": body.email}
    ).fetchone()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte avec cet email existe déjà"
        )

    # Créer l'utilisateur
    hashed = hash_password(body.password)
    result = db.execute(text("""
        INSERT INTO utilisateurs_auth (nom_complet, email, password_hash, role, updates_email, created_at)
        VALUES (:nom, :email, :pwd, 'user', :updates, NOW())
        RETURNING id, nom_complet, email, role
    """), {
        "nom":     body.nom_complet,
        "email":   body.email,
        "pwd":     hashed,
        "updates": body.updates_email,
    })
    db.commit()
    user = dict(result.fetchone()._mapping)

    # Générer les tokens
    access  = create_token({"sub": str(user["id"]), "role": user["role"]}, ACCESS_EXPIRE)
    refresh = create_token({"sub": str(user["id"]), "type": "refresh"},   REFRESH_EXPIRE)

    return TokenResponse(access_token=access, refresh_token=refresh, user=user)


# ── POST /signin ──────────────────────────────────────────────────────────────
@router.post("/signin", response_model=TokenResponse)
def signin(body: SignInRequest, db: Session = Depends(get_db)):
    user = db.execute(
        text("SELECT id, nom_complet, email, password_hash, role FROM utilisateurs_auth WHERE email = :email"),
        {"email": body.email}
    ).fetchone()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )

    user_dict = dict(user._mapping)
    user_dict.pop("password_hash", None)

    access  = create_token({"sub": str(user_dict["id"]), "role": user_dict["role"]}, ACCESS_EXPIRE)
    refresh = create_token({"sub": str(user_dict["id"]), "type": "refresh"},         REFRESH_EXPIRE)

    return TokenResponse(access_token=access, refresh_token=refresh, user=user_dict)


# ── POST /refresh ─────────────────────────────────────────────────────────────
@router.post("/refresh")
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token invalide")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expiré")

    user = db.execute(
        text("SELECT id, role FROM utilisateurs_auth WHERE id = :id"),
        {"id": user_id}
    ).fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    access = create_token({"sub": str(user.id), "role": user.role}, ACCESS_EXPIRE)
    return {"access_token": access, "token_type": "bearer"}


# ── GET /me ───────────────────────────────────────────────────────────────────
@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


# ── POST /signout ─────────────────────────────────────────────────────────────
@router.post("/signout")
def signout():
    # Côté serveur stateless — le client supprime ses tokens
    # Pour une vraie invalidation, stocker les tokens révoqués en Redis
    return {"message": "Déconnexion réussie"}