"""
API locale de Ghost Cards.

Sert les données stockées en SQLite/disque au frontend, et expose un
déclencheur de synchronisation Pronote. Pensée pour tourner en permanence
sur l'OptiPlex (voir README pour le service systemd).
"""
import json
import logging
import secrets
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel

# Services/ vit à côté de BackEnd/ (voir GhostCards/README.md pour le
# schéma d'ensemble) : ce n'est pas un sous-package de `app`, donc on
# ajoute explicitement la racine GhostCards/ à sys.path pour pouvoir
# l'importer, quel que soit le répertoire de travail au lancement
# (systemd démarre avec WorkingDirectory=BackEnd/, pas GhostCards/).
_GHOSTCARDS_ROOT = Path(__file__).resolve().parents[2]  # BackEnd/app/main.py -> GhostCards/
if str(_GHOSTCARDS_ROOT) not in sys.path:
    sys.path.insert(0, str(_GHOSTCARDS_ROOT))

from Services import db, ia_generation, ocr, pronote_sync  # noqa: E402
from Services.auth import oauth  # noqa: E402
from Services.config import (  # noqa: E402
    DOCUMENTS_DIR,
    BASE_URL,
    SESSION_SECRET_KEY,
    GOOGLE_HOSTED_DOMAIN,
    AUTHORIZED_EMAILS,
    ADMIN_PASSWORD,
    IA_ENGINE,
    OLLAMA_URL,
    OLLAMA_MODEL,
    GEMINI_MODEL,
    ANTHROPIC_API_KEY,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ghostcards.api")

if not SESSION_SECRET_KEY:
    log.warning(
        "SESSION_SECRET_KEY n'est pas définie dans .env — une clé temporaire est "
        "utilisée, ce qui déconnectera tout le monde à chaque redémarrage du "
        "service. Génère-en une avec : python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

app = FastAPI(title="Ghost Cards API")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY or "cle-temporaire-a-remplacer-dans-.env",
    same_site="lax",
    https_only=False,  # déploiement en HTTP simple sur le réseau local pour l'instant
)

# Le frontend (React) tourne sur un port différent en développement.
# En production, il est servi en statique par le même serveur : ce middleware
# devient alors inutile mais reste inoffensif.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = BackgroundScheduler()


@app.on_event("startup")
def on_startup():
    db.init_db()
    # Synchronisation automatique toutes les 2 heures. Ajuste selon le rythme
    # de publication des cours de l'établissement.
    scheduler.add_job(pronote_sync.sync, "interval", hours=2, id="pronote_sync", max_instances=1)
    scheduler.start()
    log.info("Ghost Cards API démarrée — synchronisation automatique toutes les 2h.")


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown(wait=False)


# --- Authentification élève (Google) ----------------------------------------
# Sert uniquement à attribuer les notes déposées à leur auteur. Consulter
# le site (cours, résumés, flashcards, quiz) ne nécessite pas de connexion.

def _current_eleve(request: Request):
    eleve_id = request.session.get("eleve_id")
    if not eleve_id:
        return None
    with db.session() as conn:
        row = conn.execute(
            "SELECT id, nom, email, avatar_url, assistant_actif FROM eleves WHERE id = ?", (eleve_id,)
        ).fetchone()
        return dict(row) if row else None


def _require_admin(request: Request) -> None:
    """
    Outil de diagnostic réservé à Cédric (voir HANDOFF.md) — pas une
    fonctionnalité élève. Volontairement indépendant des comptes élèves
    (Google) : un élève ne peut jamais devenir admin, l'accès admin repose
    sur un mot de passe séparé (voir /auth/admin-login).
    """
    if not request.session.get("is_admin"):
        raise HTTPException(403, "Réservé aux administrateurs.")


def _peut_utiliser_assistant(request: Request) -> bool:
    """
    L'assistant est désactivé par défaut pour un compte élève (coût/volume
    des appels IA) — activable au cas par cas depuis l'écran admin
    "Élèves". L'admin y a toujours accès, sans dépendre de ce flag.
    """
    if request.session.get("is_admin"):
        return True
    eleve = _current_eleve(request)
    return bool(eleve and eleve.get("assistant_actif"))


def _email_autorise(email: str) -> bool:
    # Aucune restriction configurée -> ouvert à tout compte Google (voir
    # .env.example pour activer une restriction par domaine ou liste blanche).
    if not GOOGLE_HOSTED_DOMAIN and not AUTHORIZED_EMAILS:
        return True
    return email.lower() in AUTHORIZED_EMAILS


@app.get("/auth/login")
async def auth_login(request: Request):
    redirect_uri = f"{BASE_URL}/auth/callback"
    kwargs = {"hd": GOOGLE_HOSTED_DOMAIN} if GOOGLE_HOSTED_DOMAIN else {}
    return await oauth.google.authorize_redirect(request, redirect_uri, **kwargs)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(400, f"Échec de connexion Google : {e}")

    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.userinfo(token=token)

    email = userinfo.get("email", "")
    if GOOGLE_HOSTED_DOMAIN and userinfo.get("hd") != GOOGLE_HOSTED_DOMAIN:
        raise HTTPException(403, f"Seuls les comptes @{GOOGLE_HOSTED_DOMAIN} sont autorisés.")
    if not _email_autorise(email):
        raise HTTPException(403, "Cette adresse n'est pas autorisée à se connecter à Ghost Cards.")

    with db.session() as conn:
        eleve_id = db.upsert_eleve(
            conn,
            google_sub=userinfo["sub"],
            email=email,
            nom=userinfo.get("name") or email,
            avatar_url=userinfo.get("picture"),
        )
    request.session["eleve_id"] = eleve_id
    return RedirectResponse(url="/")


@app.post("/auth/logout")
def auth_logout(request: Request):
    request.session.pop("eleve_id", None)
    return {"ok": True}


# --- Authentification admin (Cédric) -----------------------------------
# Totalement indépendante des comptes élèves (Google) : mot de passe
# unique défini dans .env, jamais lié à un compte Google. Un élève ne peut
# donc jamais devenir admin, quel que soit son compte Google.

class AdminLogin(BaseModel):
    password: str


@app.post("/auth/admin-login")
def admin_login(payload: AdminLogin, request: Request):
    if not ADMIN_PASSWORD:
        raise HTTPException(500, "ADMIN_PASSWORD n'est pas configuré (voir .env).")
    if not secrets.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(401, "Mot de passe incorrect.")
    request.session["is_admin"] = True
    return {"ok": True}


@app.post("/auth/admin-logout")
def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    return {"ok": True}


@app.get("/api/me")
def api_me(request: Request):
    return {"eleve": _current_eleve(request), "is_admin": bool(request.session.get("is_admin"))}


@app.get("/api/matieres")
def list_matieres():
    with db.session() as conn:
        rows = conn.execute(
            """SELECT m.id, m.nom, m.slug,
                      COUNT(DISTINCT c.id) AS nb_cours,
                      COUNT(DISTINCT d.id) AS nb_documents
               FROM matieres m
               LEFT JOIN cours c ON c.matiere_id = m.id
               LEFT JOIN documents d ON d.cours_id = c.id
               GROUP BY m.id ORDER BY m.nom"""
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/matieres/{matiere_id}/cours")
def list_cours(matiere_id: int):
    with db.session() as conn:
        rows = conn.execute(
            """SELECT id, date, heure_debut, heure_fin, professeur, titre, contenu_recupere
               FROM cours WHERE matiere_id = ? ORDER BY date DESC, heure_debut DESC""",
            (matiere_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/cours/recents")
def recent_cours(limit: int = 8):
    with db.session() as conn:
        rows = conn.execute(
            """SELECT c.id, c.date, c.heure_debut, c.titre, m.nom AS matiere, m.id AS matiere_id
               FROM cours c JOIN matieres m ON m.id = c.matiere_id
               WHERE c.annule = 0
               ORDER BY c.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/cours/{cours_id}")
def get_cours(cours_id: int):
    with db.session() as conn:
        cours = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        documents = conn.execute(
            "SELECT id, nom_fichier, url_externe FROM documents WHERE cours_id = ?", (cours_id,)
        ).fetchall()
        notes = conn.execute(
            "SELECT id, auteur, contenu, type, statut, created_at FROM notes_eleves WHERE cours_id = ? ORDER BY created_at",
            (cours_id,),
        ).fetchall()
        c = dict(cours)
        # ia_flashcards/ia_quiz sont stockés en JSON texte (voir Services/ia_generation.py) :
        # décodés ici pour que le frontend reçoive de vraies structures, pas des chaînes.
        c["ia_flashcards"] = json.loads(c["ia_flashcards"]) if c.get("ia_flashcards") else []
        c["ia_quiz"] = json.loads(c["ia_quiz"]) if c.get("ia_quiz") else []
        return {
            **c,
            "documents": [dict(d) for d in documents],
            "notes": [dict(n) for n in notes],
        }


@app.post("/api/cours/{cours_id}/generer")
def generer_contenu_ia(cours_id: int, background_tasks: BackgroundTasks):
    """
    Déclenche la génération du résumé/flashcards/quiz (Ollama, voir
    Services/ia_generation.py). Ouvert à tout le monde comme le reste de
    la consultation du site (pas besoin d'être connecté) ; le statut
    'en_cours' empêche simplement de relancer une génération déjà en vol.
    """
    with db.session() as conn:
        cours = conn.execute("SELECT ia_statut FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        if cours["ia_statut"] == "en_cours":
            return {"status": "deja_en_cours"}
        # Statut posé de façon synchrone, avant même de planifier la tâche
        # de fond : sinon le premier rechargement du frontend (juste après
        # cette réponse) peut arriver avant que la tâche n'ait eu la main,
        # et rater la transition 'en_cours' dont dépend son polling.
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))
    background_tasks.add_task(ia_generation.generer_pour_cours, cours_id)
    return {"status": "generation_lancee"}


@app.post("/api/cours/{cours_id}/completer")
def completer_contenu_ia(cours_id: int, background_tasks: BackgroundTasks):
    """
    Ajoute 10 flashcards et 10 questions de quiz de plus à une génération
    déjà en place (Services/ia_generation.py::completer_pour_cours), sans
    tout régénérer. Nécessite qu'une génération ait déjà réussi.
    """
    with db.session() as conn:
        cours = conn.execute("SELECT ia_statut, ia_flashcards FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        if cours["ia_statut"] == "en_cours":
            return {"status": "deja_en_cours"}
        if not cours["ia_flashcards"]:
            raise HTTPException(400, "Génère d'abord le résumé/flashcards/quiz avant de les compléter.")
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))
    background_tasks.add_task(ia_generation.completer_pour_cours, cours_id)
    return {"status": "completion_lancee"}


class NoteCreate(BaseModel):
    contenu: str
    type: str = "texte"  # 'texte' | 'markdown' — photo/PDF pas encore pris en charge


@app.post("/api/cours/{cours_id}/notes")
def create_note(cours_id: int, payload: NoteCreate, request: Request):
    eleve = _current_eleve(request)
    if not eleve:
        raise HTTPException(401, "Connecte-toi avec Google pour ajouter une note.")
    contenu = payload.contenu.strip()
    if not contenu:
        raise HTTPException(400, "La note est vide.")

    with db.session() as conn:
        if conn.execute("SELECT 1 FROM cours WHERE id = ?", (cours_id,)).fetchone() is None:
            raise HTTPException(404, "Cours introuvable")
        conn.execute(
            """INSERT INTO notes_eleves (cours_id, eleve_id, auteur, contenu, type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cours_id, eleve["id"], eleve["nom"], contenu, payload.type, datetime.now().isoformat(timespec="seconds")),
        )
    return {"ok": True}


_TYPES_FICHIERS_NOTE = {
    "application/pdf": (".pdf", "pdf"),
    "image/png": (".png", "photo"),
    "image/jpeg": (".jpg", "photo"),
    "image/webp": (".webp", "photo"),
}


@app.post("/api/cours/{cours_id}/notes/photo")
def create_note_photo(cours_id: int, request: Request, background_tasks: BackgroundTasks, fichier: UploadFile = File(...)):
    """
    Dépôt d'une note sous forme de photo de cahier ou de PDF : le fichier est
    transcrit en arrière-plan (OCR, voir Services/ocr.py) pour ne pas bloquer
    la réponse HTTP. `statut` passe à 'pret' une fois la transcription faite
    (le frontend poll GET /api/cours/{id} pendant ce temps).
    """
    eleve = _current_eleve(request)
    if not eleve:
        raise HTTPException(401, "Connecte-toi avec Google pour ajouter une note.")

    extension_type = _TYPES_FICHIERS_NOTE.get(fichier.content_type)
    if extension_type is None:
        raise HTTPException(400, "Format non supporté (PDF, PNG, JPEG ou WebP uniquement).")
    extension, type_note = extension_type

    with db.session() as conn:
        if conn.execute("SELECT 1 FROM cours WHERE id = ?", (cours_id,)).fetchone() is None:
            raise HTTPException(404, "Cours introuvable")

        dest_dir = DOCUMENTS_DIR / "notes_eleves" / str(cours_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        nom_fichier = f"note_{eleve['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}{extension}"
        dest_path = dest_dir / nom_fichier
        dest_path.write_bytes(fichier.file.read())
        chemin_relatif = str(dest_path.relative_to(DOCUMENTS_DIR.parent))

        cur = conn.execute(
            """INSERT INTO notes_eleves (cours_id, eleve_id, auteur, chemin_fichier, type, statut, created_at)
               VALUES (?, ?, ?, ?, ?, 'traitement', ?)""",
            (cours_id, eleve["id"], eleve["nom"], chemin_relatif, type_note, datetime.now().isoformat(timespec="seconds")),
        )
        note_id = cur.lastrowid

    background_tasks.add_task(ocr.transcribe_note, note_id)
    return {"ok": True, "note_id": note_id}


def _traitement_vers_dict(row) -> dict:
    d = dict(row)
    # etapes est stocké en JSON texte (voir Services/db.py::log_traitement) :
    # décodé ici pour que le frontend reçoive une vraie liste, pas une chaîne.
    d["etapes"] = json.loads(d["etapes"]) if d.get("etapes") else []
    return d


@app.get("/api/traitements")
def list_traitements(request: Request, limit: int = 50):
    _require_admin(request)
    with db.session() as conn:
        rows = conn.execute(
            "SELECT * FROM traitements ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_traitement_vers_dict(r) for r in rows]


@app.get("/api/traitements/{traitement_id}")
def get_traitement(traitement_id: int, request: Request):
    _require_admin(request)
    with db.session() as conn:
        row = conn.execute("SELECT * FROM traitements WHERE id = ?", (traitement_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Traitement introuvable")
        return _traitement_vers_dict(row)


@app.post("/api/traitements/{traitement_id}/relancer")
def relancer_traitement(traitement_id: int, request: Request, background_tasks: BackgroundTasks):
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM traitements WHERE id = ?", (traitement_id,)).fetchone() is None:
            raise HTTPException(404, "Traitement introuvable")
    background_tasks.add_task(ocr.relancer_traitement, traitement_id)
    return {"status": "relance_lancee"}


@app.get("/api/eleves")
def list_eleves(request: Request):
    """Liste des comptes élèves (Google) — outil admin, jamais exposé aux élèves eux-mêmes."""
    _require_admin(request)
    with db.session() as conn:
        rows = conn.execute(
            """SELECT e.id, e.nom, e.email, e.avatar_url, e.created_at, e.derniere_connexion,
                      e.assistant_actif, COUNT(n.id) AS nb_notes
               FROM eleves e LEFT JOIN notes_eleves n ON n.eleve_id = e.id
               GROUP BY e.id ORDER BY e.derniere_connexion DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


class AssistantActifPayload(BaseModel):
    actif: bool


@app.put("/api/eleves/{eleve_id}/assistant")
def set_assistant_actif(eleve_id: int, payload: AssistantActifPayload, request: Request):
    """Active/désactive l'assistant pour un élève précis — voir _peut_utiliser_assistant."""
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM eleves WHERE id = ?", (eleve_id,)).fetchone() is None:
            raise HTTPException(404, "Élève introuvable")
        conn.execute("UPDATE eleves SET assistant_actif = ? WHERE id = ?", (int(payload.actif), eleve_id))
    return {"ok": True}


@app.get("/api/parametres")
def get_parametres(request: Request):
    """
    Réglages admin modifiables à chaud (moteur IA pour la génération ET
    l'assistant conversationnel — voir Services/ia_generation.py). Les
    clés (Anthropic, Gemini) ne sont jamais renvoyées en clair, seulement
    si elles sont configurées ou non (comme un champ mot de passe côté
    navigateur).
    """
    _require_admin(request)
    with db.session() as conn:
        moteur = db.get_parametre(conn, "ia_moteur", IA_ENGINE)
        ollama_url = db.get_parametre(conn, "ollama_url", OLLAMA_URL)
        ollama_model = db.get_parametre(conn, "ollama_model", OLLAMA_MODEL)
        gemini_model = db.get_parametre(conn, "gemini_model", GEMINI_MODEL)
        gemini_key = db.get_parametre(conn, "gemini_api_key", "")
        anthropic_key = db.get_parametre(conn, "anthropic_api_key", ANTHROPIC_API_KEY)
    return {
        "ia_moteur": moteur if moteur in ("ollama", "gemini", "claude") else "ollama",
        "ollama_url": ollama_url or OLLAMA_URL,
        "ollama_model": ollama_model or OLLAMA_MODEL,
        "gemini_model": gemini_model or GEMINI_MODEL,
        "gemini_api_key_configuree": bool(gemini_key),
        "anthropic_api_key_configuree": bool(anthropic_key),
    }


@app.get("/api/parametres/ollama-modeles")
def get_ollama_modeles(request: Request, url: str | None = None):
    """
    Liste les modèles installés sur le serveur Ollama (`GET {url}/api/tags`)
    pour l'écran Paramétrage — évite de taper le nom du modèle à la main et
    vérifie au passage que l'adresse saisie est joignable. `url` en query
    string permet de tester une adresse pas encore enregistrée.
    """
    _require_admin(request)
    with db.session() as conn:
        base_url = url or db.get_parametre(conn, "ollama_url", OLLAMA_URL) or OLLAMA_URL
    try:
        modeles = ia_generation.lister_modeles_ollama(base_url)
    except ia_generation.GenerationError as e:
        raise HTTPException(502, str(e))
    return {"modeles": modeles}


class ParametresIA(BaseModel):
    ia_moteur: str
    ollama_url: str | None = None
    ollama_model: str | None = None
    gemini_model: str | None = None
    gemini_api_key: str | None = None  # None = ne pas changer ; chaîne vide = effacer
    anthropic_api_key: str | None = None  # idem


@app.put("/api/parametres")
def set_parametres(payload: ParametresIA, request: Request):
    _require_admin(request)
    if payload.ia_moteur not in ("ollama", "gemini", "claude"):
        raise HTTPException(400, "Moteur invalide (attendu 'ollama', 'gemini' ou 'claude').")
    with db.session() as conn:
        db.set_parametre(conn, "ia_moteur", payload.ia_moteur)
        if payload.ollama_url:
            db.set_parametre(conn, "ollama_url", payload.ollama_url)
        if payload.ollama_model:
            db.set_parametre(conn, "ollama_model", payload.ollama_model)
        if payload.gemini_model:
            db.set_parametre(conn, "gemini_model", payload.gemini_model)
        if payload.gemini_api_key is not None:
            db.set_parametre(conn, "gemini_api_key", payload.gemini_api_key)
        if payload.anthropic_api_key is not None:
            db.set_parametre(conn, "anthropic_api_key", payload.anthropic_api_key)
    return {"ok": True}


@app.get("/api/devoirs")
def list_devoirs():
    with db.session() as conn:
        rows = conn.execute(
            """SELECT d.id, d.date_rendu, d.description, d.fait, m.nom AS matiere
               FROM devoirs d JOIN matieres m ON m.id = d.matiere_id
               WHERE d.fait = 0 ORDER BY d.date_rendu"""
        ).fetchall()
        return [dict(r) for r in rows]


def _reponse_fichier(chemin_local: str | None, nom_fichier: str, *, inline: bool) -> FileResponse:
    """
    Sert un fichier stocké sur le disque, en téléchargement forcé
    (`inline=False`, utilisé par les boutons "Télécharger") ou affichable
    directement dans le navigateur (`inline=True`, PDF/image ouverts dans
    un nouvel onglet plutôt que proposés en téléchargement).
    """
    if not chemin_local or chemin_local.startswith("lien:"):
        raise HTTPException(404, "Fichier non disponible localement")
    path = DOCUMENTS_DIR.parent / chemin_local
    if not path.exists():
        raise HTTPException(404, "Fichier absent du disque")
    return FileResponse(
        path, filename=nom_fichier,
        content_disposition_type="inline" if inline else "attachment",
    )


@app.get("/api/documents/{document_id}/fichier")
def download_document(document_id: int):
    with db.session() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "Document introuvable")
    return _reponse_fichier(doc["chemin_local"], doc["nom_fichier"], inline=False)


@app.get("/api/documents/{document_id}/apercu")
def apercu_document(document_id: int):
    with db.session() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "Document introuvable")
    return _reponse_fichier(doc["chemin_local"], doc["nom_fichier"], inline=True)


@app.get("/api/notes/{note_id}/fichier")
def download_note_fichier(note_id: int):
    with db.session() as conn:
        note = conn.execute("SELECT * FROM notes_eleves WHERE id = ?", (note_id,)).fetchone()
        if note is None:
            raise HTTPException(404, "Note introuvable")
    return _reponse_fichier(note["chemin_fichier"], f"note_{note_id}{Path(note['chemin_fichier'] or '').suffix}", inline=False)


@app.get("/api/notes/{note_id}/apercu")
def apercu_note_fichier(note_id: int):
    with db.session() as conn:
        note = conn.execute("SELECT * FROM notes_eleves WHERE id = ?", (note_id,)).fetchone()
        if note is None:
            raise HTTPException(404, "Note introuvable")
    return _reponse_fichier(note["chemin_fichier"], f"note_{note_id}{Path(note['chemin_fichier'] or '').suffix}", inline=True)


class AssistantMessage(BaseModel):
    role: str
    text: str


class AssistantRequest(BaseModel):
    messages: list[AssistantMessage]


ASSISTANT_SYSTEM_PROMPT = (
    "Tu es l'assistant IA de Ghost Cards, une application de révision pour un(e) élève. "
    "Réponds en français, simplement, en 3 à 5 phrases maximum. Tu n'as pas encore accès "
    "aux documents détaillés de la classe : si la question porte sur un point précis d'un "
    "cours, dis-le et réponds avec tes connaissances générales sur le sujet."
)


@app.post("/api/assistant")
def assistant(payload: AssistantRequest, request: Request):
    """
    Proxy vers le moteur IA configuré (Ollama par défaut, Claude ou Gemini
    en option — voir l'écran admin "Paramétrage" et
    Services/ia_generation.py::config_ia) : la clé, s'il y en a une, reste
    côté serveur, jamais exposée au navigateur. Le frontend envoie juste
    l'historique de la conversation.

    Réservé à l'admin et aux élèves activés au cas par cas (voir
    _peut_utiliser_assistant) — contrairement au reste du site, ouvert à
    tous sans connexion.
    """
    if not _peut_utiliser_assistant(request):
        raise HTTPException(
            403, "L'assistant n'est pas activé pour ton compte — demande à ton professeur."
        )
    with db.session() as conn:
        cfg = ia_generation.config_ia(conn)
    try:
        texte = ia_generation.repondre_conversation(
            [{"role": m.role, "text": m.text} for m in payload.messages],
            ASSISTANT_SYSTEM_PROMPT, cfg,
        )
    except ia_generation.GenerationError as e:
        raise HTTPException(502, str(e))

    return {"text": texte.strip() or "Je n'ai pas pu formuler de réponse, réessaie."}


@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    """
    Déclenche une synchronisation immédiate (bouton 'Actualiser' côté
    site, ou "Lancer une synchronisation" côté admin dans l'écran
    "Traitements"). La ligne `traitements` est créée ici, avant de
    lancer le travail en arrière-plan, pour pouvoir renvoyer son id tout
    de suite : l'écran admin s'en sert pour ouvrir directement le suivi
    de cette synchro sans attendre ni deviner laquelle vient d'être créée.
    """
    with db.session() as conn:
        traitement_id = db.creer_traitement(conn, type="pronote_sync", cible_type="sync", cible_id=0)
    background_tasks.add_task(pronote_sync.sync, traitement_id=traitement_id)
    return {"status": "sync_lancee", "traitement_id": traitement_id}


@app.get("/api/sync/last")
def last_sync():
    with db.session() as conn:
        row = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


# --- Frontend statique ------------------------------------------------------
# Monté EN DERNIER, volontairement : Starlette teste les routes dans l'ordre
# d'ajout, et un Mount("/") matche n'importe quel chemin. S'il était déclaré
# avant les routes /api/..., il les intercepterait toutes. Ici, /api/* est
# déjà résolu au-dessus ; seul ce qui n'a matché aucune route API retombe
# sur le frontend (utile pour le routing côté client de l'app React).
#
# Structure attendue sur le disque :
#   GhostCards/
#     BackEnd/   (ce projet — app/main.py est ici)
#     FrontEnd/  (projet Vite, dist/ après `npm run build`)
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "FrontEnd" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
    log.info("Frontend statique servi depuis %s", _FRONTEND_DIST)
else:
    log.info("Pas de frontend buildé trouvé (%s) — seule l'API est servie.", _FRONTEND_DIST)
