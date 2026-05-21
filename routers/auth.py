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
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests



router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ── Config ───────────────────────────────────────────────────────────────────
SECRET_KEY      = os.getenv("SECRET_KEY", "ocp-dex-secret-key-change-in-production")
ALGORITHM       = "HS256"
ACCESS_EXPIRE   = 60          # minutes
REFRESH_EXPIRE  = 60 * 24 * 7 # minutes (7 jours)

# pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

reset_tokens: dict = {}

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

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

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




#── Forget password ─────────────────────────────────────────
@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.execute(
        text("SELECT id, email, nom_complet FROM utilisateurs_auth WHERE email = :email"),
        {"email": body.email}
    ).fetchone()

    # Always return 200 — never reveal if email exists
    if not user:
        return {"message": "Si cet email existe, un lien a été envoyé."}

    # Generate secure one-time token (expires in 30 min)
    token      = secrets.token_urlsafe(32)
    reset_tokens[token] = {
        "user_id": user.id,
        "expires": datetime.utcnow() + timedelta(minutes=30)
    }

    reset_link  = f"http://localhost:5173/reset-password?token={token}"
    gmail_user  = os.getenv("GMAIL_USER")
    gmail_pass  = os.getenv("GMAIL_APP_PASSWORD")

    html_body = f"""
    <div style="font-family:'Segoe UI',sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;background:#fff">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:28px">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2L4 7v10l8 5 8-5V7L12 2z" fill="#1a56db" opacity="0.15"/>
          <path d="M12 2L4 7v10l8 5 8-5V7L12 2z" stroke="#1a56db" stroke-width="1.5" fill="none"/>
          <circle cx="12" cy="12" r="2.5" fill="#1a56db"/>
        </svg>
        <span style="font-size:16px;font-weight:600;color:#111827">DEX Platform</span>
      </div>

      <h2 style="font-size:22px;font-weight:700;color:#111827;margin:0 0 12px">
        Réinitialisation du mot de passe
      </h2>

      <p style="font-size:15px;color:#374151;line-height:1.6;margin:0 0 8px">
        Bonjour <strong>{user.nom_complet}</strong>,
      </p>
      <p style="font-size:14px;color:#6b7280;line-height:1.6;margin:0 0 28px">
        Nous avons reçu une demande de réinitialisation de votre mot de passe.
        Cliquez sur le bouton ci-dessous — ce lien expire dans <strong>30 minutes</strong>.
      </p>

      <a href="{reset_link}"
         style="display:inline-block;padding:14px 32px;background:#111827;color:#ffffff;
                border-radius:8px;text-decoration:none;font-size:15px;font-weight:600;
                letter-spacing:0.01em">
        Réinitialiser mon mot de passe
      </a>

      <p style="font-size:12px;color:#9ca3af;margin-top:32px;line-height:1.6">
        Si vous n'avez pas fait cette demande, ignorez cet email — votre mot de passe
        restera inchangé.<br/>Ce lien expirera automatiquement dans 30 minutes.
      </p>

      <hr style="border:none;border-top:1px solid #f1f5f9;margin:28px 0"/>
      <p style="font-size:12px;color:#d1d5db;margin:0">
        OCP Safi — DEX Platform · Ne pas répondre à cet email
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Réinitialisation de votre mot de passe — DEX Platform"
    msg["From"]    = f"DEX Platform <{gmail_user}>"
    msg["To"]      = user.email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, user.email, msg.as_string())
        print(f"[AUTH] Reset email sent to {user.email}")
    except Exception as e:
        print(f"[AUTH] Email send failed: {e}")
        # Don't expose the error to the client
        raise HTTPException(500, "Erreur d'envoi d'email. Contactez l'administrateur.")

    return {"message": "Si cet email existe, un lien a été envoyé."}


@router.get("/reset-password/verify")
def verify_reset_token(token: str):
    entry = reset_tokens.get(token)
    if not entry:
        raise HTTPException(400, "Token invalide ou expiré")
    if datetime.utcnow() > entry["expires"]:
        del reset_tokens[token]
        raise HTTPException(400, "Token expiré — veuillez refaire la demande")
    return {"valid": True}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    entry = reset_tokens.get(body.token)
    if not entry:
        raise HTTPException(400, "Token invalide ou expiré")
    if datetime.utcnow() > entry["expires"]:
        del reset_tokens[body.token]
        raise HTTPException(400, "Token expiré — veuillez refaire la demande")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 8 caractères")

    hashed = hash_password(body.new_password)
    db.execute(
        text("UPDATE utilisateurs_auth SET password_hash = :pwd WHERE id = :uid"),
        {"pwd": hashed, "uid": entry["user_id"]}
    )
    db.commit()
    del reset_tokens[body.token]
    return {"message": "Mot de passe réinitialisé avec succès"}

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

# ── Login with Google ─────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

class GoogleAuthRequest(BaseModel):
    credential: str  # the JWT token Google sends back

@router.post("/google")
def google_auth(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        # Verify the token with Google
        idinfo = id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        print(f"[google_auth] token error: {e}")  # check this in terminal
        raise HTTPException(status_code=401, detail=f"Invalid Google token : {e}")

    email      = idinfo["email"]
    nom_complet = idinfo.get("name", email)

    # Get or create user
    user = db.execute(
        text("SELECT id, nom_complet, email, role FROM utilisateurs_auth WHERE email = :email"),
        {"email": email}
    ).fetchone()

    if not user:
        result = db.execute(text("""
            INSERT INTO utilisateurs_auth (nom_complet, email, password_hash, role)
            VALUES (:nom, :email, '', 'employee')
            RETURNING id, nom_complet, email, role
        """), {"nom": nom_complet, "email": email})
        db.commit()
        user = result.fetchone()

    user_dict = dict(user._mapping)
    access  = create_token({"sub": str(user_dict["id"]), "role": user_dict["role"]}, ACCESS_EXPIRE)
    refresh = create_token({"sub": str(user_dict["id"]), "type": "refresh"}, REFRESH_EXPIRE)

    return TokenResponse(access_token=access, refresh_token=refresh, user=user_dict)


# ── POST /signout ─────────────────────────────────────────────────────────────
@router.post("/signout")
def signout():
    # Côté serveur stateless — le client supprime ses tokens
    # Pour une vraie invalidation, stocker les tokens révoqués en Redis
    return {"message": "Déconnexion réussie"}