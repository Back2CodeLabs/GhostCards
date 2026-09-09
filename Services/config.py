"""
Configuration centrale de Ghost Cards.

Toutes les valeurs peuvent être surchargées par des variables d'environnement
(pratique pour un déploiement systemd sur l'OptiPlex sans toucher au code).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Services/ et BackEnd/ sont deux dossiers frères sous GhostCards/. Le code
# a été réorganisé (Services = synchro Pronote, génération IA ; BackEnd =
# API HTTP ; FrontEnd = interface), mais .env, secrets/ et data/ restent
# dans BackEnd/ comme avant la réorganisation — pas besoin de déplacer quoi
# que ce soit sur le disque.
GHOSTCARDS_ROOT = Path(__file__).resolve().parent.parent  # .../GhostCards
BASE_DIR = GHOSTCARDS_ROOT / "BackEnd"

# Charge les variables du fichier .env dans os.environ. Sans cet appel,
# .env n'est qu'un fichier texte ignoré de Python.
load_dotenv(BASE_DIR / ".env")

# --- Pronote --------------------------------------------------------------
# URL Pronote de l'établissement, ex: https://XXXX.index-education.net/pronote/eleve.html
PRONOTE_URL = os.environ.get("PRONOTE_URL", "")

# Fichier contenant les identifiants de connexion (généré une seule fois,
# voir README section "Première connexion"). Ne JAMAIS committer ce fichier.
CREDENTIALS_PATH = Path(os.environ.get("CREDENTIALS_PATH", BASE_DIR / "secrets" / "credentials.json"))

# --- Authentification élève (Google) -----------------------------------
# Sert uniquement à identifier qui dépose une note (section 8 du cahier
# des charges) — la consultation du site reste libre, seul le dépôt de
# notes nécessite d'être connecté.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# URL publique de l'application, utilisée pour construire l'URL de retour
# Google (doit correspondre EXACTEMENT à une "URI de redirection autorisée"
# déclarée dans Google Cloud Console, suffixée de /auth/callback).
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
# Secret de signature des cookies de session — génère-en un avec :
#   python3 -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")

# Qui a le droit de se connecter — deux mécanismes, au choix (l'un ou
# l'autre, ou aucun si la classe utilise des comptes Gmail personnels et
# que tu ne veux pas encore restreindre) :
# 1) Comptes d'établissement (Google Workspace) : renseigne le domaine,
#    ex. "moncollege.fr" — seuls les comptes de ce domaine pourront se
#    connecter (vérifié côté serveur, pas juste suggéré à Google).
GOOGLE_HOSTED_DOMAIN = os.environ.get("GOOGLE_HOSTED_DOMAIN", "")
# 2) Liste blanche d'adresses email précises (comptes Gmail personnels),
#    séparées par des virgules.
AUTHORIZED_EMAILS = {
    e.strip().lower() for e in os.environ.get("AUTHORIZED_EMAILS", "").split(",") if e.strip()
}

# --- Authentification admin (Cédric) ----------------------------------------
# Volontairement séparée des comptes élèves (Google) : un élève ne doit
# jamais pouvoir devenir admin, donc pas de champ "rôle" sur `eleves` — un
# simple mot de passe partagé, comparé en temps constant (voir
# `secrets.compare_digest` dans BackEnd/app/main.py), suffit pour un compte
# admin unique. Vide par défaut : la connexion admin est désactivée tant
# qu'un mot de passe n'est pas défini dans `.env`.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# --- OCR / extraction de texte ----------------------------------------------
# Utilisé à la fois pour les PDF Pronote scannés (sans couche de texte) et
# pour les photos de cahier déposées par les élèves.
# "paddleocr"  : local et gratuit (choix par défaut) — nécessite un venv
#                Python <=3.13 (PaddlePaddle n'a pas de wheels pour Python
#                3.14 au moment de l'écriture ; voir HANDOFF.md pour la
#                procédure de changement de version sur l'OptiPlex).
# "claude"     : envoie l'image à l'API Anthropic (déjà configurée plus
#                haut), meilleur sur l'écriture manuscrite mais coûte du
#                crédit API par image — utile en repli si PaddleOCR déçoit
#                sur des photos de cahier réelles.
OCR_ENGINE = os.environ.get("OCR_ENGINE", "paddleocr")
# Limite de sécurité : nombre de pages OCRisées au maximum pour un PDF
# scanné (évite qu'un gros PDF ne déclenche des dizaines d'appels).
OCR_MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", 15))

# --- Génération IA (résumés/flashcards/quiz) --------------------------------
# Moteur par défaut = Ollama en local : gros volume de génération
# potentiel (des dizaines de cours), gratuit et privé, là où l'API
# Anthropic reste réservée à l'assistant conversationnel (faible volume).
# Gemini est proposé en option (nécessite une clé API Google, le contenu
# des cours part alors chez Google) pour qui préfère la rapidité/qualité
# cloud à la gratuité locale.
#
# IMPORTANT : le moteur réellement utilisé et la clé Gemini sont
# modifiables à chaud depuis l'écran admin "Paramétrage" (stockés dans la
# table `parametres`, voir Services/db.py::get_parametre/set_parametre) —
# les variables ci-dessous ne sont que la valeur de départ, avant toute
# configuration via l'interface (utile pour un premier déploiement où
# .env est plus rapide à éditer qu'à cliquer dans l'admin).
IA_ENGINE = os.environ.get("IA_ENGINE", "ollama")  # 'ollama' | 'gemini'
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
FLASHCARDS_PAR_COURS = int(os.environ.get("FLASHCARDS_PAR_COURS", 10))
QUESTIONS_QUIZ_PAR_COURS = int(os.environ.get("QUESTIONS_QUIZ_PAR_COURS", 5))
# Longueur max de texte envoyée au modèle (caractères) — au-delà, tronqué.
IA_TEXTE_MAX_CHARS = int(os.environ.get("IA_TEXTE_MAX_CHARS", 12000))

# --- Assistant IA -----------------------------------------------------------
# Clé API Anthropic, utilisée uniquement côté serveur (jamais exposée au
# navigateur). Créée sur https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Stockage local ---------------------------------------------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DOCUMENTS_DIR = DATA_DIR / "documents"
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "ghostcards.db"))

# --- Synchronisation ---------------------------------------------------------
SYNC_DAYS_BACK = int(os.environ.get("SYNC_DAYS_BACK", 3))     # relit les derniers jours (au cas où un cours a été modifié)
SYNC_DAYS_FORWARD = int(os.environ.get("SYNC_DAYS_FORWARD", 10))  # récupère aussi l'emploi du temps à venir

# S'assure que les dossiers existent
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
