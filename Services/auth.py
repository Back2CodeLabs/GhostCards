"""
Authentification élève via Google (OpenID Connect).

Sert uniquement à savoir QUI dépose une prise de notes (section 8 du cahier
des charges) — la consultation du site (cours, résumés, flashcards, quiz)
reste entièrement libre, sans connexion.

Ce module ne fait qu'enregistrer le client OAuth ; les routes (/auth/login,
/auth/callback, /auth/logout, /api/me) vivent dans BackEnd/app/main.py,
qui a accès à `request` (FastAPI) et à la session.
"""
from authlib.integrations.starlette_client import OAuth

from .config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
