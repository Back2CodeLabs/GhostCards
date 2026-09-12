"""
Configuration centrale de Ghost School.

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

# --- Authentification élève (pairage Pronote) -------------------------------
# Chaque élève se connecte avec SON PROPRE compte Pronote (QR code + PIN,
# comme la procédure d'admin dans Services/scripts/first_login.py, mais en
# self-service depuis le site) : ça sert à la fois d'identité vérifiée
# (établissement + classe, voir BackEnd/app/main.py::pairer_eleve_pronote)
# et de source de synchro pour son propre groupe (LV2, options...). Remplace
# l'ancienne connexion Google, qui ne vérifiait qu'une adresse email et ne
# donnait accès à aucune donnée Pronote propre à l'élève.
#
# Secret de signature des cookies de session — génère-en un avec :
#   python3 -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")

# Clé de chiffrement (Fernet) des jetons Pronote stockés par élève (voir
# Services/crypto_secrets.py) — accès direct au compte scolaire réel d'un
# mineur, sensibilité bien supérieure au `credentials.json` unique de
# l'admin (qui reste un fichier à part, non chiffré, comme avant). Génère-en
# une avec :
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CREDENTIALS_ENCRYPTION_KEY = os.environ.get("CREDENTIALS_ENCRYPTION_KEY", "")

# Classe attendue au pairage (ex. "2F") — comparée à `ClientInfo.class_name`
# une fois la connexion Pronote de l'élève réussie ; modifiable à chaud
# depuis l'écran admin Paramétrage (table `parametres`), cette valeur de
# départ ne sert que si rien n'est encore enregistré. Vide = aucune
# vérification de classe (seul l'établissement est vérifié).
CLASSE_ATTENDUE = os.environ.get("CLASSE_ATTENDUE", "")

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
