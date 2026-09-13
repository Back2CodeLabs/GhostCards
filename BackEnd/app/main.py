"""
API locale de Ghost School.

Sert les données stockées en SQLite/disque au frontend, et expose un
déclencheur de synchronisation Pronote. Pensée pour tourner en permanence
sur l'OptiPlex (voir README pour le service systemd).
"""
import json
import logging
import secrets
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
import pronotepy
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

from Services import crypto_secrets, db, ia_generation, ia_verification, ocr, pronote_sync  # noqa: E402
from Services.config import (  # noqa: E402
    DOCUMENTS_DIR,
    SESSION_SECRET_KEY,
    SESSION_COOKIE_SECURE,
    ADMIN_PASSWORD,
    IA_ENGINE,
    OLLAMA_URL,
    OLLAMA_MODEL,
    GEMINI_MODEL,
    ANTHROPIC_API_KEY,
    PRONOTE_URL,
    CREDENTIALS_PATH,
    SYNC_DAYS_BACK,
    SYNC_DAYS_FORWARD,
    FLASHCARDS_PAR_COURS,
    QUESTIONS_QUIZ_PAR_COURS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ghostcards.api")

if not SESSION_SECRET_KEY:
    log.warning(
        "SESSION_SECRET_KEY n'est pas définie dans .env — une clé temporaire est "
        "utilisée, ce qui déconnectera tout le monde à chaque redémarrage du "
        "service. Génère-en une avec : python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

app = FastAPI(title="Ghost School API")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY or "cle-temporaire-a-remplacer-dans-.env",
    same_site="lax",
    # Marque le cookie "Secure" une fois un reverse proxy HTTPS en place
    # (voir BackEnd/deploy/Caddyfile, SESSION_COOKIE_SECURE=true dans .env)
    # — pas avant, sinon la session ne survivrait plus à un accès de
    # diagnostic en HTTP simple (tunnel SSH vers localhost:8000).
    https_only=SESSION_COOKIE_SECURE,
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
    log.info("Ghost School API démarrée — synchronisation automatique toutes les 2h.")


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown(wait=False)


# --- Authentification élève (pairage Pronote) -------------------------------
# Chaque élève lie son propre compte Pronote (voir pairer_eleve_pronote plus
# bas) — sert d'identité vérifiée (établissement + classe) ET de source de
# synchro pour son propre groupe. La consultation du site est verrouillée à
# ceux qui ont une session valide (élève ou admin) — voir _require_session.

def _current_eleve(request: Request):
    eleve_id = request.session.get("eleve_id")
    if not eleve_id:
        return None
    with db.session() as conn:
        row = conn.execute(
            "SELECT id, nom, email, avatar_url, assistant_actif, generation_manuelle_actif FROM eleves WHERE id = ?",
            (eleve_id,),
        ).fetchone()
        return dict(row) if row else None


def _require_admin(request: Request) -> None:
    """
    Outil de diagnostic réservé à Cédric (voir HANDOFF.md) — pas une
    fonctionnalité élève. Volontairement indépendant des comptes élèves
    (Pronote) : un élève ne peut jamais devenir admin, l'accès admin repose
    sur un mot de passe séparé (voir /auth/admin-login).
    """
    if not request.session.get("is_admin"):
        raise HTTPException(403, "Réservé aux administrateurs.")


def _require_session(request: Request) -> None:
    """
    Consultation du site verrouillée aux élèves de la classe (pairage
    Pronote, voir pairer_eleve_pronote) et à l'admin — contrairement à
    l'ancienne connexion Google, purement décorative pour la navigation.
    """
    if request.session.get("eleve_id") or request.session.get("is_admin"):
        return
    raise HTTPException(401, "Connexion requise.")


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


def _peut_generer_manuellement(request: Request) -> bool:
    """
    Génération manuelle (v0.6.0, voir importer_manuel_ia) : même principe
    que `_peut_utiliser_assistant` — désactivée par défaut pour un compte
    élève, activable au cas par cas depuis l'écran admin "Élèves".
    """
    if request.session.get("is_admin"):
        return True
    eleve = _current_eleve(request)
    return bool(eleve and eleve.get("generation_manuelle_actif"))


# Tailles (plus grand côté, en px) essayées successivement si le décodage
# à la résolution d'origine échoue — cv2.QRCodeDetector s'avère très
# sensible à la résolution sur une vraie photo (éclairage inégal, moiré de
# l'écran photographié, angle...) : une image peut échouer à sa taille
# native et pourtant se décoder sans problème une fois redimensionnée à
# telle ou telle taille. Constaté avec deux vraies photos de téléphone —
# aucune des deux ne passait telle quelle, chacune ne se décode qu'à
# certaines tailles (pas toujours les mêmes) : plusieurs essais valent
# mieux qu'un seuil unique deviné à l'aveugle.
_QR_TAILLES_SECOURS = (800, 1200, 1600, 600, 1000, 1400, 500, 900, 1100, 1300, 2000)


def _decoder_qr_image(image) -> str:
    detecteur = cv2.QRCodeDetector()
    donnees, _, _ = detecteur.detectAndDecode(image)
    if donnees:
        return donnees

    plus_grand_cote = max(image.shape[:2])
    for taille in _QR_TAILLES_SECOURS:
        if taille == plus_grand_cote:
            continue
        echelle = taille / plus_grand_cote
        interpolation = cv2.INTER_AREA if echelle < 1 else cv2.INTER_CUBIC
        redimensionnee = cv2.resize(image, None, fx=echelle, fy=echelle, interpolation=interpolation)
        donnees, _, _ = detecteur.detectAndDecode(redimensionnee)
        if donnees:
            return donnees
    return ""


@app.post("/api/eleves/pairage")
async def pairer_eleve_pronote(
    request: Request,
    qr: UploadFile | None = File(None),
    qr_json: str | None = Form(None),
    pin: str = Form(...),
    consentement: bool = Form(...),
):
    """
    Connexion élève par pairage Pronote self-service : l'élève génère un QR
    code sur Pronote (Mon compte → Connexion via smartphone, comme la
    procédure d'admin — voir Services/scripts/first_login.py), en upload une
    capture d'écran/photo ici avec le PIN affiché à côté (ou colle le JSON
    du QR code directement, `qr_json`, si une autre appli l'a déjà décodé —
    utile quand aucune des tailles essayées par `_decoder_qr_image` ne
    suffit sur une photo trop dégradée). Sert à la fois d'identité
    vérifiée (établissement + classe) et de source de synchro pour le groupe
    propre à cet élève (voir Services/pronote_sync.py).

    `consentement` : coché après lecture de la liste de ce qui sera
    récupéré (écran de connexion, voir FrontEnd/src/screens/Auth.jsx) —
    obligatoire, vérifié avant tout le reste (accès direct à des données
    scolaires réelles d'un mineur). Son horodatage est enregistré comme
    preuve (voir Services/db.py::upsert_eleve_pronote), pas juste vérifié
    puis oublié.

    Trois vérifications, dans cet ordre (les deux premières ne nécessitent
    même pas d'avoir tenté la connexion) :
    1. Le consentement doit être donné.
    2. L'URL Pronote embarquée dans le QR doit être sur le même domaine que
       `pronote_url` (Paramétrage) — pas le bon établissement sinon.
    3. Une fois connecté, `client.info.class_name` doit figurer dans les
       classes autorisées (écran Paramétrage → Pronote → Classes) —
       aucune classe enregistrée = non vérifié (comportement historique
       conservé pour ne pas surprendre un déploiement pas encore configuré).
    """
    if not consentement:
        raise HTTPException(400, "Le consentement à la récupération des données Pronote est obligatoire.")

    with db.session() as conn:
        pronote_url_configuree = pronote_sync.config_pronote(conn)["pronote_url"]
        classes_ok = db.classes_autorisees(conn)

    if not pronote_url_configuree:
        raise HTTPException(503, "Pronote n'est pas configuré sur ce serveur (URL manquante dans Paramétrage).")

    if qr_json and qr_json.strip():
        donnees = qr_json.strip()
    elif qr is not None:
        contenu = await qr.read()
        image = cv2.imdecode(np.frombuffer(contenu, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(400, "Image illisible — envoie une capture d'écran ou une photo nette du QR code.")
        donnees = _decoder_qr_image(image)
        if not donnees:
            raise HTTPException(
                400,
                "Aucun QR code détecté dans l'image — réessaie avec une photo bien cadrée et sans reflet, "
                "ou colle directement le JSON du QR code si tu l'as (voir « Coller le code à la place »).",
            )
    else:
        raise HTTPException(400, "Envoie une image du QR code, ou colle son contenu JSON.")

    try:
        qr_code = json.loads(donnees)
    except json.JSONDecodeError:
        raise HTTPException(400, "Ce QR code n'est pas un QR Pronote (contenu illisible).")

    domaine_attendu = urlparse(pronote_url_configuree).netloc
    domaine_qr = urlparse(qr_code.get("url", "")).netloc
    if not domaine_qr or domaine_qr != domaine_attendu:
        raise HTTPException(403, "Ce QR code ne correspond pas à l'établissement configuré pour Ghost School.")

    try:
        client = pronotepy.Client.qrcode_login(qr_code, pin, str(uuid.uuid4()))
    except pronotepy.QRCodeDecryptError:
        # Le PIN sert de clé de déchiffrement du QR (pas une simple
        # vérification a posteriori) : un PIN faux ne donne jamais un
        # message Pronote clair ("invalid confirmation code", en anglais,
        # remonté tel quel avant cette correction) — message dédié.
        raise HTTPException(
            401,
            "Code PIN incorrect, ou QR code trop ancien — régénère-le sur Pronote (Mon compte → "
            "Connexion via smartphone) et réessaie.",
        )
    except Exception as e:
        log.warning("Échec pairage Pronote (avant connexion) : %s", e, exc_info=True)
        raise HTTPException(
            401,
            "Connexion Pronote refusée — vérifie le QR code et le PIN, ou régénère-les sur Pronote si ça persiste.",
        )
    if not client.logged_in:
        raise HTTPException(401, "Connexion Pronote refusée (QR code expiré ou code PIN incorrect).")

    class_name = client.info.class_name
    if classes_ok and class_name.strip().lower() not in classes_ok:
        raise HTTPException(
            403,
            f"La classe « {class_name or 'inconnue'} » n'est pas autorisée à se connecter à Ghost School.",
        )

    # Connexion Pronote réussie à ce stade : une panne ici (clé de
    # chiffrement absente, base injoignable...) ne doit pas remonter une
    # erreur 500 brute et muette à l'élève — message clair côté client,
    # détail complet dans les logs pour diagnostic côté admin.
    try:
        credentials_chiffrees = crypto_secrets.chiffrer_json(client.export_credentials())
        with db.session() as conn:
            eleve_id = db.upsert_eleve_pronote(
                conn,
                pronote_id=client.info.id,
                nom=client.info.name,
                email=getattr(client.info, "email", "") or "",
                class_name=class_name,
                credentials_chiffrees=credentials_chiffrees,
            )
    except Exception as e:
        log.error("Échec enregistrement après pairage Pronote réussi : %s", e, exc_info=True)
        raise HTTPException(
            500,
            "Connexion Pronote réussie, mais l'enregistrement a échoué côté serveur — réessaie, "
            "et préviens l'admin si ça persiste.",
        )
    request.session["eleve_id"] = eleve_id
    return {"ok": True, "nom": client.info.name}


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


def _require_eleve(request: Request) -> int:
    """Réservé aux élèves pairés — jamais l'admin (pas de ligne `eleves` pour lui)."""
    eleve_id = request.session.get("eleve_id")
    if not eleve_id:
        raise HTTPException(403, "Réservé aux élèves.")
    return eleve_id


@app.get("/api/profil")
def profil(request: Request):
    """
    Écran "Profil" élève (FrontEnd/src/screens/ProfilScreen.jsx) : identité
    en lecture seule (Pronote fait déjà foi) + statut de la clé Gemini
    personnelle — jamais la clé elle-même, seulement si une est enregistrée
    (même principe que pour les identifiants Pronote, jamais renvoyés).
    """
    eleve_id = _require_eleve(request)
    with db.session() as conn:
        row = conn.execute(
            "SELECT nom, pronote_class_name, pronote_groupes, gemini_api_key FROM eleves WHERE id = ?", (eleve_id,)
        ).fetchone()
        return {
            "nom": row["nom"],
            "classe": row["pronote_class_name"],
            "groupes": row["pronote_groupes"],
            "gemini_cle_definie": bool(row["gemini_api_key"]),
        }


class GeminiClePayload(BaseModel):
    cle: str | None = None


@app.put("/api/profil/gemini-cle")
def definir_cle_gemini(payload: GeminiClePayload, request: Request):
    """
    Enregistre (ou efface, `cle` vide/absente) la clé Gemini personnelle de
    l'élève connecté — voir Services/ia_generation.py pour son usage
    (prioritaire sur le moteur choisi par l'admin, pour SES propres
    générations). Chiffrée au repos comme les identifiants Pronote : accès
    direct à un compte Google réel, même si le risque concret est moindre
    (juste un quota d'API à protéger, pas des données scolaires).
    """
    eleve_id = _require_eleve(request)
    cle = (payload.cle or "").strip()
    cle_chiffree = crypto_secrets.chiffrer_json({"cle": cle}) if cle else None
    with db.session() as conn:
        conn.execute("UPDATE eleves SET gemini_api_key = ? WHERE id = ?", (cle_chiffree, eleve_id))
    return {"ok": True, "gemini_cle_definie": cle_chiffree is not None}


def _classe_filtre(conn, request: Request, classe_query: str | None) -> str | None:
    """
    Classe à appliquer aux requêtes de contenu (cours/devoirs/matières)
    pour CETTE requête : un élève voit toujours SA classe
    (`eleves.pronote_class_name`), jamais un paramètre de requête — un
    admin voit la classe demandée en paramètre (`?classe=2E`), ou aucun
    filtre (`None`, les classes mélangées) si absent — vue par défaut
    décidée pour l'admin.
    """
    if request.session.get("is_admin"):
        return classe_query
    eleve_id = request.session.get("eleve_id")
    if not eleve_id:
        return None
    row = conn.execute("SELECT pronote_class_name FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    return row["pronote_class_name"] if row else None


@app.get("/api/classes")
def list_classes(request: Request):
    """Classes autorisées au pairage (écran admin Paramétrage → Pronote)."""
    _require_admin(request)
    with db.session() as conn:
        return db.lister_classes(conn)


class ClassePayload(BaseModel):
    nom: str


@app.post("/api/classes")
def ajouter_classe_endpoint(payload: ClassePayload, request: Request):
    _require_admin(request)
    nom = payload.nom.strip()
    if not nom:
        raise HTTPException(400, "Le nom de la classe ne peut pas être vide.")
    with db.session() as conn:
        classe_id = db.ajouter_classe(conn, nom)
    return {"id": classe_id, "nom": nom}


@app.delete("/api/classes/{classe_id}")
def supprimer_classe_endpoint(classe_id: int, request: Request):
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM classes WHERE id = ?", (classe_id,)).fetchone() is None:
            raise HTTPException(404, "Classe introuvable.")
        try:
            db.supprimer_classe(conn, classe_id)
        except db.DerniereClasseError as e:
            raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/matieres")
def list_matieres(request: Request, classe: str | None = None):
    """
    `classe` : optionnel, admin uniquement (voir _classe_filtre) — un élève
    n'a de toute façon accès qu'à la sienne. Filtrée (JOIN plutôt que LEFT
    JOIN sur `cours`), une matière sans aucun cours dans cette classe
    n'apparaît simplement pas — pas la peine de montrer "0 cours" pour une
    matière propre à l'autre classe.
    """
    _require_session(request)
    with db.session() as conn:
        classe_filtre = _classe_filtre(conn, request, classe)
        if classe_filtre:
            rows = conn.execute(
                """SELECT m.id, m.nom, m.slug,
                          COUNT(DISTINCT c.id) AS nb_cours,
                          COUNT(DISTINCT d.id) AS nb_documents
                   FROM matieres m
                   JOIN cours c ON c.matiere_id = m.id AND c.classe = ?
                   LEFT JOIN documents d ON d.cours_id = c.id
                   WHERE m.exclue = 0
                   GROUP BY m.id ORDER BY m.nom""",
                (classe_filtre,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT m.id, m.nom, m.slug,
                          COUNT(DISTINCT c.id) AS nb_cours,
                          COUNT(DISTINCT d.id) AS nb_documents
                   FROM matieres m
                   LEFT JOIN cours c ON c.matiere_id = m.id
                   LEFT JOIN documents d ON d.cours_id = c.id
                   WHERE m.exclue = 0
                   GROUP BY m.id ORDER BY m.nom"""
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/parametres/matieres")
def list_matieres_admin(request: Request):
    """
    Toutes les matières déjà vues par la synchro, exclue ou non (voir
    `matieres.exclue`) — pour la case à cocher de l'écran Paramétrage →
    Pronote. Se base sur ce qui a réellement été récupéré plutôt qu'une
    liste de noms tapés à l'avance : `GET /api/matieres` (utilisé pour la
    navigation) reste, lui, toujours filtré aux matières non exclues.
    """
    _require_admin(request)
    with db.session() as conn:
        rows = conn.execute("SELECT id, nom, exclue FROM matieres ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


class ExclureMatierePayload(BaseModel):
    exclue: bool


@app.put("/api/matieres/{matiere_id}/exclure")
def exclure_matiere(matiere_id: int, payload: ExclureMatierePayload, request: Request):
    """
    Masque (ou démasque) une matière déjà connue — n'affecte jamais la
    synchro elle-même (voir Services/pronote_sync.py, tout est toujours
    ingéré), seulement ce qui est montré dans l'app (accueil, matières,
    devoirs...).
    """
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM matieres WHERE id = ?", (matiere_id,)).fetchone() is None:
            raise HTTPException(404, "Matière introuvable.")
        conn.execute("UPDATE matieres SET exclue = ? WHERE id = ?", (int(payload.exclue), matiere_id))
    return {"ok": True}



# Sous-requêtes réutilisées par les deux listes de cours ci-dessous : de
# quoi afficher un petit indicateur (documents/notes/génération IA) sans
# avoir à ouvrir chaque cours pour le savoir — masqué côté frontend quand
# le compte est à 0, pas la peine d'encombrer la liste.
_COMPTES_COURS_SQL = """
    (SELECT COUNT(*) FROM documents d WHERE d.cours_id = c.id) AS nb_documents,
    (SELECT COUNT(*) FROM notes_eleves n WHERE n.cours_id = c.id) AS nb_notes
"""


@app.get("/api/matieres/{matiere_id}/cours")
def list_cours(matiere_id: int, request: Request, classe: str | None = None):
    _require_session(request)
    with db.session() as conn:
        classe_filtre = _classe_filtre(conn, request, classe)
        if classe_filtre:
            rows = conn.execute(
                f"""SELECT c.id, c.date, c.heure_debut, c.heure_fin, c.professeur, c.titre,
                           c.contenu_recupere, c.ia_statut, c.annule, c.statut, c.salle, c.groupe,
                           c.memo, c.devoir_surveille, {_COMPTES_COURS_SQL}
                    FROM cours c WHERE c.matiere_id = ? AND c.classe = ?
                    ORDER BY c.date DESC, c.heure_debut DESC""",
                (matiere_id, classe_filtre),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT c.id, c.date, c.heure_debut, c.heure_fin, c.professeur, c.titre,
                           c.contenu_recupere, c.ia_statut, c.annule, c.statut, c.salle, c.groupe,
                           c.memo, c.devoir_surveille, {_COMPTES_COURS_SQL}
                    FROM cours c WHERE c.matiere_id = ? ORDER BY c.date DESC, c.heure_debut DESC""",
                (matiere_id,),
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/matieres/{matiere_id}/notes")
def list_notes_matiere(matiere_id: int, request: Request):
    """
    Notes personnelles — jamais partagées entre élèves : un élève ne voit
    que ses propres notes (`eleve_id` = sa propre session), l'admin voit
    tout, y compris celles du compte Pronote de référence (`eleve_id` NULL).
    """
    _require_session(request)
    with db.session() as conn:
        if request.session.get("is_admin"):
            rows = conn.execute(
                """SELECT id, valeur, bareme, moyenne_classe, note_min, note_max, coefficient,
                          commentaire, date, eleve_id
                   FROM notes_pronote WHERE matiere_id = ? ORDER BY date DESC""",
                (matiere_id,),
            ).fetchall()
        else:
            eleve_id = request.session.get("eleve_id")
            rows = conn.execute(
                """SELECT id, valeur, bareme, moyenne_classe, note_min, note_max, coefficient,
                          commentaire, date
                   FROM notes_pronote WHERE matiere_id = ? AND eleve_id = ? ORDER BY date DESC""",
                (matiere_id, eleve_id),
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/cours/suggestion-ia")
def suggestion_ia(request: Request, classe: str | None = None):
    """
    Un seul cours à mettre en avant sur l'accueil ("Quiz du jour") pour que
    la génération IA (résumé/flashcards/quiz) saute aux yeux — retour de
    terrain : un élève ne savait pas que la fonctionnalité existait,
    reléguée à une petite icône dans la liste des cours (voir
    IndicateursCours, FrontEnd/src/components/Shared.jsx).

    Priorité 1 : le cours le plus récent déjà prêt (quiz à réviser tout de
    suite). Priorité 2, sinon : le plus récent qui a de quoi générer mais
    ne l'a pas encore été (même condition que /api/cours/non-generes,
    réservé lui à l'admin) — invite à découvrir "Générer" en ouvrant ce
    cours. `{}` si aucun des deux n'existe (classe toute neuve, sans
    contenu récupéré nulle part encore).

    Déclarée ici, AVANT /api/cours/{cours_id} : une route à paramètre du
    même préfixe capturerait sinon "suggestion-ia" comme un id (voir
    HANDOFF.md, piège déjà rencontré avec /api/cours/recents).
    """
    _require_session(request)
    with db.session() as conn:
        classe_filtre = _classe_filtre(conn, request, classe)
        classe_clause = "AND c.classe = ?" if classe_filtre else ""
        params = (classe_filtre,) if classe_filtre else ()

        pret = conn.execute(
            f"""SELECT c.id, m.nom AS matiere, c.titre
               FROM cours c JOIN matieres m ON m.id = c.matiere_id
               WHERE c.ia_statut = 'pret' AND m.exclue = 0 {classe_clause}
               ORDER BY c.date DESC, c.heure_debut DESC LIMIT 1""",
            params,
        ).fetchone()
        if pret:
            return {"id": pret["id"], "matiere": pret["matiere"], "titre": pret["titre"], "pret": True}

        a_generer = conn.execute(
            f"""SELECT c.id, m.nom AS matiere, c.titre
               FROM cours c JOIN matieres m ON m.id = c.matiere_id
               WHERE c.ia_statut IN ('absent', 'echec') AND m.exclue = 0 {classe_clause}
                 AND (
                   (c.description IS NOT NULL AND c.description != '')
                   OR EXISTS (
                     SELECT 1 FROM documents d
                     WHERE d.cours_id = c.id AND d.texte_extrait IS NOT NULL AND d.texte_extrait != ''
                   )
                 )
               ORDER BY c.date DESC, c.heure_debut DESC LIMIT 1""",
            params,
        ).fetchone()
        if a_generer:
            return {"id": a_generer["id"], "matiere": a_generer["matiere"], "titre": a_generer["titre"], "pret": False}
        return {}


@app.get("/api/cours/du-jour")
def cours_du_jour(request: Request, classe: str | None = None):
    """
    Emploi du temps du jour — affiché sur l'accueil à la place de la liste
    des matières (déjà consultable depuis l'onglet Matières, doublon
    inutile sur l'accueil) : ce qu'un élève veut voir en arrivant sur le
    site, c'est son planning du jour, cours annulés compris (pour le
    savoir, pas pour les cacher).

    Déclarée ici, AVANT /api/cours/{cours_id} : une route à paramètre du
    même préfixe capturerait sinon "du-jour" comme un id (voir HANDOFF.md,
    piège déjà rencontré avec /api/cours/recents).
    """
    _require_session(request)
    aujourdhui = date.today().isoformat()
    with db.session() as conn:
        classe_filtre = _classe_filtre(conn, request, classe)
        classe_clause = "AND c.classe = ?" if classe_filtre else ""
        params = (aujourdhui, classe_filtre) if classe_filtre else (aujourdhui,)
        rows = conn.execute(
            f"""SELECT c.id, c.heure_debut, c.heure_fin, c.professeur, c.salle, c.groupe, c.memo,
                       c.annule, c.statut, c.devoir_surveille, c.ia_statut, m.nom AS matiere, m.id AS matiere_id,
                       {_COMPTES_COURS_SQL}
                FROM cours c JOIN matieres m ON m.id = c.matiere_id
                WHERE c.date = ? AND m.exclue = 0 {classe_clause} ORDER BY c.heure_debut""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/cours/recents")
def recent_cours(request: Request, limit: int = 8, classe: str | None = None):
    _require_session(request)
    with db.session() as conn:
        classe_filtre = _classe_filtre(conn, request, classe)
        classe_clause = "AND c.classe = ?" if classe_filtre else ""
        params = (classe_filtre, limit) if classe_filtre else (limit,)
        rows = conn.execute(
            f"""SELECT c.id, c.date, c.heure_debut, c.titre, c.ia_statut, c.annule, c.salle,
                       c.devoir_surveille, m.nom AS matiere, m.id AS matiere_id,
                       {_COMPTES_COURS_SQL}
                FROM cours c JOIN matieres m ON m.id = c.matiere_id
                WHERE c.annule = 0 AND m.exclue = 0 {classe_clause}
                ORDER BY c.created_at DESC LIMIT ?""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/cours/non-generes")
def cours_non_generes(request: Request, classe: str | None = None):
    """
    Cours sans résumé/flashcards/quiz (jamais générés, ou dernière tentative
    en échec) qui ont pourtant de quoi générer (description et/ou document
    transcrit non vide — voir Services/ia_generation.py::texte_source) :
    sert à l'écran admin "Traitements" pour déclencher la génération sans
    avoir à ouvrir chaque cours un par un. Les cours sans aucune source
    n'apparaissent pas ici : les lister sans rien à en tirer n'aiderait pas.
    `classe` : filtre optionnel (sélecteur de classe admin).

    Déclarée ici, AVANT /api/cours/{cours_id} : une route à paramètre du
    même préfixe capturerait sinon "non-generes" comme un id (voir
    HANDOFF.md, piège déjà rencontré une fois avec /api/cours/recents).
    """
    _require_admin(request)
    with db.session() as conn:
        classe_clause = "AND c.classe = ?" if classe else ""
        params = (classe,) if classe else ()
        rows = conn.execute(
            f"""SELECT c.id, c.date, c.heure_debut, c.titre, m.nom AS matiere, c.ia_statut, c.ia_erreur
               FROM cours c JOIN matieres m ON m.id = c.matiere_id
               WHERE c.ia_statut IN ('absent', 'echec') AND m.exclue = 0 {classe_clause}
                 AND (
                   (c.description IS NOT NULL AND c.description != '')
                   OR EXISTS (
                     SELECT 1 FROM documents d
                     WHERE d.cours_id = c.id AND d.texte_extrait IS NOT NULL AND d.texte_extrait != ''
                   )
                 )
               ORDER BY c.date DESC, c.heure_debut DESC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/cours/{cours_id}")
def get_cours(cours_id: int, request: Request):
    _require_session(request)
    with db.session() as conn:
        cours = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        # Empêche un élève d'ouvrir un cours d'une autre classe en devinant/
        # collant un id (les listes, elles, le filtrent déjà) — `None` pour
        # l'admin (voir _classe_filtre) ou une ligne pas encore migrée
        # (`cours["classe"]` NULL) laisse passer sans vérifier.
        _classe_verifiee_cours(conn, request, cours)
        documents = conn.execute(
            "SELECT id, nom_fichier, url_externe FROM documents WHERE cours_id = ?", (cours_id,)
        ).fetchall()
        notes = conn.execute(
            "SELECT id, auteur, contenu, type, statut, created_at FROM notes_eleves WHERE cours_id = ? ORDER BY created_at",
            (cours_id,),
        ).fetchall()
        # Pour le lien "Voir le traitement" (admin, écran Traitements) depuis
        # la section IA du cours — voir aussi le lien inverse, gratuit, dans
        # TraitementDetail (cible_type/cible_id sont déjà dans /api/traitements/{id}).
        ia_traitement = conn.execute(
            """SELECT id FROM traitements WHERE cible_type = 'cours' AND cible_id = ?
               AND type IN ('ia_generation', 'ia_completion') ORDER BY id DESC LIMIT 1""",
            (cours_id,),
        ).fetchone()
        demande_en_attente = conn.execute(
            "SELECT 1 FROM traitements WHERE type = 'regeneration_demande' AND cible_id = ? AND statut = 'en_attente'",
            (cours_id,),
        ).fetchone()
        import_en_attente = conn.execute(
            "SELECT 1 FROM traitements WHERE type = 'import_demande' AND cible_id = ? AND statut = 'en_attente'",
            (cours_id,),
        ).fetchone()
        verif_traitement = conn.execute(
            "SELECT id FROM traitements WHERE cible_type = 'cours' AND cible_id = ? AND type = 'ia_verification' ORDER BY id DESC LIMIT 1",
            (cours_id,),
        ).fetchone()
        c = dict(cours)
        c["ia_traitement_id"] = ia_traitement["id"] if ia_traitement else None
        c["regeneration_en_attente"] = demande_en_attente is not None
        c["import_manuel_en_attente"] = import_en_attente is not None
        c["ia_verification_traitement_id"] = verif_traitement["id"] if verif_traitement else None
        # ia_flashcards/ia_quiz sont stockés en JSON texte (voir Services/ia_generation.py) :
        # décodés ici pour que le frontend reçoive de vraies structures, pas des chaînes.
        c["ia_flashcards"] = json.loads(c["ia_flashcards"]) if c.get("ia_flashcards") else []
        c["ia_quiz"] = json.loads(c["ia_quiz"]) if c.get("ia_quiz") else []
        # ia_texte_source ne sert qu'en interne (voir completer_pour_cours) —
        # pas besoin de l'envoyer au frontend, il peut être volumineux.
        c.pop("ia_texte_source", None)
        return {
            **c,
            "documents": [dict(d) for d in documents],
            "notes": [dict(n) for n in notes],
        }


def _classe_verifiee_cours(conn, request: Request, cours) -> None:
    """
    Factorise la garde déjà utilisée par get_cours ci-dessus (403 si le
    cours n'appartient pas à la classe de l'élève) — réutilisée par les
    deux endpoints de génération manuelle ci-dessous, qui portent sur un
    cours précis comme get_cours.
    """
    classe_eleve = _classe_filtre(conn, request, None)
    if classe_eleve and cours["classe"] and cours["classe"] != classe_eleve:
        raise HTTPException(403, "Ce cours n'appartient pas à ta classe.")


@app.get("/api/cours/{cours_id}/prompt-manuel")
def prompt_generation_manuelle(cours_id: int, request: Request):
    """
    Prompt prêt à copier (v0.6.0) pour qu'un élève génère lui-même le
    résumé/flashcards/quiz avec sa propre IA (ChatGPT, Gemini, Claude...),
    hors Ghost School, puis les importe (voir importer_manuel_ia
    ci-dessous) — utile quand Ollama est trop lent (jusqu'à ~30 min sur un
    cours complet, voir Services/ia_generation.py) ou indisponible.

    Même texte source et même consigne qu'une génération automatique
    (`ia_generation.construire_prompt_generation`), mais SANS le
    découpage propre à Ollama (`_texte_pour_prompt`) : un outil externe a
    un contexte largement suffisant pour un cours entier, comme c'est déjà
    le cas pour Claude/Gemini dans le pipeline existant.
    """
    _require_session(request)
    if not _peut_generer_manuellement(request):
        raise HTTPException(403, "Génération manuelle désactivée pour ton compte — demande à l'admin de l'activer.")
    with db.session() as conn:
        cours = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        _classe_verifiee_cours(conn, request, cours)
        texte = ia_generation.texte_source(conn, dict(cours))
        if not texte.strip():
            raise HTTPException(400, "Ce cours n'a ni description ni document transcrit à partir duquel générer.")
        cfg = ia_generation.config_ia(conn)
    prompt = ia_generation.construire_prompt_generation(
        texte, FLASHCARDS_PAR_COURS, QUESTIONS_QUIZ_PAR_COURS, cfg["prompt_generation_consigne"],
    )
    return {"prompt": prompt}


class ImporterManuelPayload(BaseModel):
    contenu: str


@app.post("/api/cours/{cours_id}/importer-manuel")
def importer_manuel_ia(cours_id: int, payload: ImporterManuelPayload, request: Request):
    """
    Reçoit le JSON collé par l'élève (réponse de sa propre IA au prompt de
    prompt_generation_manuelle ci-dessus), le parse/valide, puis crée
    TOUJOURS une demande en attente de validation admin (jamais
    d'application immédiate, contrairement à une première génération
    automatique) — ce texte n'est jamais passé par le prompt contrôlé de
    Ghost School, une validation systématique protège le contenu partagé
    de la classe d'un import fantaisiste ou erroné.
    """
    _require_session(request)
    if not _peut_generer_manuellement(request):
        raise HTTPException(403, "Génération manuelle désactivée pour ton compte — demande à l'admin de l'activer.")
    with db.session() as conn:
        cours = conn.execute("SELECT id, classe FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        _classe_verifiee_cours(conn, request, cours)
        existante = conn.execute(
            "SELECT id FROM traitements WHERE type = 'import_demande' AND cible_id = ? AND statut = 'en_attente'",
            (cours_id,),
        ).fetchone()
        if existante:
            return {"status": "deja_en_attente", "demande_id": existante["id"]}
        try:
            resultat = ia_generation.parser_json_ia(payload.contenu)
            resultat = ia_generation.valider_forme_generation(resultat)
        except ia_generation.GenerationError as e:
            raise HTTPException(400, str(e))
        demande_id = db.creer_demande_import(conn, cours_id, json.dumps(resultat, ensure_ascii=False))
    return {"status": "demande_en_attente", "demande_id": demande_id}


@app.post("/api/cours/{cours_id}/generer")
def generer_contenu_ia(cours_id: int, request: Request, background_tasks: BackgroundTasks):
    """
    Déclenche la génération du résumé/flashcards/quiz (Ollama, voir
    Services/ia_generation.py) ; le statut 'en_cours' empêche simplement de
    relancer une génération déjà en vol.

    Une PREMIÈRE génération (cours sans résumé encore) part immédiatement :
    il n'y a rien à consulter sans elle. Une RÉGÉNÉRATION (le bouton
    "Régénérer", sur un cours qui a déjà un résumé) coûte des tokens/du
    temps de calcul pour un résultat pas forcément différent — n'importe
    quel élève de la classe pouvant cliquer, elle passe par une demande en
    attente que l'admin valide ou rejette depuis l'écran Traitements →
    onglet "En attente", plutôt que de partir tout de suite.
    """
    _require_session(request)
    with db.session() as conn:
        cours = conn.execute("SELECT ia_statut, ia_resume FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        if cours["ia_statut"] == "en_cours":
            return {"status": "deja_en_cours"}
        if cours["ia_resume"]:
            existante = conn.execute(
                "SELECT id FROM traitements WHERE type = 'regeneration_demande' AND cible_id = ? AND statut = 'en_attente'",
                (cours_id,),
            ).fetchone()
            if existante:
                return {"status": "deja_en_attente", "demande_id": existante["id"]}
            demande_id = db.creer_demande_regeneration(conn, cours_id)
            return {"status": "demande_en_attente", "demande_id": demande_id}
        # Statut posé de façon synchrone, avant même de planifier la tâche
        # de fond : sinon le premier rechargement du frontend (juste après
        # cette réponse) peut arriver avant que la tâche n'ait eu la main,
        # et rater la transition 'en_cours' dont dépend son polling.
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))
    # eleve_id : si l'élève à l'origine du clic a sa propre clé Gemini
    # (écran Profil), elle prime sur le moteur choisi par l'admin pour
    # CETTE génération (voir Services/ia_generation.py) — None pour
    # l'admin, qui n'a pas de clé personnelle.
    background_tasks.add_task(ia_generation.generer_pour_cours, cours_id, eleve_id=request.session.get("eleve_id"))
    return {"status": "generation_lancee"}


@app.post("/api/traitements/demandes/{demande_id}/valider")
def valider_demande_regeneration(demande_id: int, request: Request, background_tasks: BackgroundTasks):
    """
    Valide une demande en attente — de deux types possibles (même table
    `traitements`, voir `db.creer_demande_regeneration`/`creer_demande_
    import`) :
    - 'regeneration_demande' : lance enfin la génération, comme un
      /generer normal (rien n'a encore été calculé, juste demandé).
    - 'import_demande' (v0.6.0) : le contenu a déjà été collé, parsé et
      validé par l'élève au moment de la demande (voir importer_manuel_ia)
      — pas d'appel modèle ici, juste l'écriture du contenu déjà en
      attente (`ia_generation.importer_manuel`), synchrone.
    """
    _require_admin(request)
    with db.session() as conn:
        row = conn.execute(
            """SELECT cible_id, type, resultat FROM traitements
               WHERE id = ? AND type IN ('regeneration_demande', 'import_demande') AND statut = 'en_attente'""",
            (demande_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Demande introuvable ou déjà traitée.")
        cours_id = row["cible_id"]
        conn.execute("UPDATE traitements SET statut = 'validee', finished_at = ? WHERE id = ?", (db.now_iso(), demande_id))
        if row["type"] == "import_demande":
            ia_generation.importer_manuel(conn, cours_id, json.loads(row["resultat"]))
            return {"status": "validee"}
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))
    background_tasks.add_task(ia_generation.generer_pour_cours, cours_id)
    return {"status": "validee"}


@app.post("/api/traitements/demandes/{demande_id}/rejeter")
def rejeter_demande_regeneration(demande_id: int, request: Request):
    """Rejette une demande en attente (régénération ou import manuel, voir valider_demande_regeneration)."""
    _require_admin(request)
    with db.session() as conn:
        row = conn.execute(
            """SELECT 1 FROM traitements
               WHERE id = ? AND type IN ('regeneration_demande', 'import_demande') AND statut = 'en_attente'""",
            (demande_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Demande introuvable ou déjà traitée.")
        conn.execute("UPDATE traitements SET statut = 'rejetee', finished_at = ? WHERE id = ?", (db.now_iso(), demande_id))
    return {"status": "rejetee"}


@app.post("/api/cours/{cours_id}/completer")
def completer_contenu_ia(cours_id: int, request: Request, background_tasks: BackgroundTasks):
    """
    Ajoute 10 flashcards et 10 questions de quiz de plus à une génération
    déjà en place (Services/ia_generation.py::completer_pour_cours), sans
    tout régénérer. Nécessite qu'une génération ait déjà réussi.
    """
    _require_session(request)
    with db.session() as conn:
        cours = conn.execute("SELECT ia_statut, ia_flashcards FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        if cours["ia_statut"] == "en_cours":
            return {"status": "deja_en_cours"}
        if not cours["ia_flashcards"]:
            raise HTTPException(400, "Génère d'abord le résumé/flashcards/quiz avant de les compléter.")
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))
    background_tasks.add_task(ia_generation.completer_pour_cours, cours_id, eleve_id=request.session.get("eleve_id"))
    return {"status": "completion_lancee"}


@app.post("/api/cours/{cours_id}/verifier")
def verifier_generation_ia(cours_id: int, request: Request, background_tasks: BackgroundTasks):
    """
    Lance une vérification de fiabilité (Services/ia_verification.py) —
    outil de diagnostic admin, pas une action élève : confronte résumé/
    flashcards/quiz au texte source avec le modèle configuré dans
    Paramétrage → Vérification (indépendant de celui de Génération IA).
    """
    _require_admin(request)
    with db.session() as conn:
        cours = conn.execute("SELECT ia_statut, ia_resume FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if cours is None:
            raise HTTPException(404, "Cours introuvable")
        if cours["ia_statut"] == "en_cours":
            raise HTTPException(400, "Une génération est en cours pour ce cours — attends qu'elle se termine.")
        if not cours["ia_resume"]:
            raise HTTPException(400, "Génère d'abord le résumé/flashcards/quiz avant de les vérifier.")
        traitement_id = db.creer_traitement(conn, type="ia_verification", cible_type="cours", cible_id=cours_id)
    background_tasks.add_task(ia_verification.verifier_generation, cours_id, traitement_id=traitement_id)
    return {"status": "verification_lancee", "traitement_id": traitement_id}


class NoteCreate(BaseModel):
    contenu: str
    type: str = "texte"  # 'texte' | 'markdown' — photo/PDF pas encore pris en charge


@app.post("/api/cours/{cours_id}/notes")
def create_note(cours_id: int, payload: NoteCreate, request: Request):
    eleve = _current_eleve(request)
    if not eleve:
        raise HTTPException(401, "Connecte-toi pour ajouter une note.")
    contenu = payload.contenu.strip()
    if not contenu:
        raise HTTPException(400, "La note est vide.")

    with db.session() as conn:
        if conn.execute("SELECT 1 FROM cours WHERE id = ?", (cours_id,)).fetchone() is None:
            raise HTTPException(404, "Cours introuvable")
        conn.execute(
            """INSERT INTO notes_eleves (cours_id, eleve_id, auteur, contenu, type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cours_id, eleve["id"], eleve["nom"], contenu, payload.type, db.now_iso()),
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
        raise HTTPException(401, "Connecte-toi pour ajouter une note.")

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
            (cours_id, eleve["id"], eleve["nom"], chemin_relatif, type_note, db.now_iso()),
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


def _classe_traitement(conn, t) -> str | None:
    """
    Classe du cours/document concerné par ce traitement, si déterminable.
    `None` pour un type qui n'est pas lié à un seul cours (ex.
    'pronote_sync', qui couvre potentiellement plusieurs classes à la
    fois) — ces lignes-là restent toujours visibles, filtre ou pas (voir
    list_traitements).
    """
    if t["cible_type"] == "cours":
        row = conn.execute("SELECT classe FROM cours WHERE id = ?", (t["cible_id"],)).fetchone()
        return row["classe"] if row else None
    if t["cible_type"] == "document":
        doc = conn.execute("SELECT cours_id, devoir_id FROM documents WHERE id = ?", (t["cible_id"],)).fetchone()
        return _classe_parent_document(conn, doc) if doc else None
    return None


@app.get("/api/traitements")
def list_traitements(request: Request, limit: int = 50, classe: str | None = None):
    """
    `classe` : filtre optionnel (sélecteur de classe admin) — sur-fetch
    quand actif (voir _classe_traitement) pour continuer à renvoyer
    jusqu'à `limit` lignes après filtrage, plutôt que d'appliquer LIMIT
    avant de filtrer et renvoyer parfois moins que demandé.
    """
    _require_admin(request)
    with db.session() as conn:
        fetch_limit = limit * 4 if classe else limit
        rows = conn.execute(
            "SELECT * FROM traitements ORDER BY id DESC LIMIT ?", (fetch_limit,)
        ).fetchall()
        if classe:
            rows = [r for r in rows if _classe_traitement(conn, r) in (None, classe)][:limit]
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


@app.get("/api/documents/non-transcrits")
def documents_non_transcrits(request: Request, classe: str | None = None):
    """
    Documents Pronote sans texte extrait : soit jamais transcrits (aucune
    ligne `traitements` pour eux — ex. téléchargés avant la mise en place
    de l'OCR automatique), soit dont la dernière tentative a échoué
    (`texte_extrait` reste NULL dans les deux cas — voir Services/ocr.py).
    Sert à l'écran admin "Traitements" pour proposer un déclenchement
    manuel, faute de ligne `traitements` existante à relancer pour le
    premier cas. `classe` : filtre optionnel (sélecteur de classe admin).
    """
    _require_admin(request)
    with db.session() as conn:
        classe_clause = "AND COALESCE(c.classe, dv.classe) = ?" if classe else ""
        params = (classe,) if classe else ()
        rows = conn.execute(
            f"""SELECT d.id, d.nom_fichier, d.created_at, m.nom AS matiere,
                      (SELECT statut FROM traitements WHERE cible_type = 'document' AND cible_id = d.id ORDER BY id DESC LIMIT 1) AS dernier_statut,
                      (SELECT erreur FROM traitements WHERE cible_type = 'document' AND cible_id = d.id ORDER BY id DESC LIMIT 1) AS derniere_erreur
               FROM documents d
               LEFT JOIN cours c ON d.cours_id = c.id
               LEFT JOIN devoirs dv ON d.devoir_id = dv.id
               LEFT JOIN matieres m ON m.id = COALESCE(c.matiere_id, dv.matiere_id)
               WHERE d.texte_extrait IS NULL AND d.chemin_local NOT LIKE 'lien:%' {classe_clause}
               ORDER BY d.created_at DESC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/documents/{document_id}/transcrire")
def transcrire_document(document_id: int, request: Request, background_tasks: BackgroundTasks):
    """
    Déclenche une transcription pour un document qui n'en a encore jamais
    eu (donc sans ligne `traitements` à relancer via l'endpoint ci-dessus).
    """
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
            raise HTTPException(404, "Document introuvable")
    background_tasks.add_task(ocr.transcribe_document, document_id)
    return {"status": "transcription_lancee"}


@app.get("/api/eleves")
def list_eleves(request: Request):
    """Liste des comptes élèves (pairage Pronote) — outil admin, jamais exposé aux élèves eux-mêmes."""
    _require_admin(request)
    with db.session() as conn:
        rows = conn.execute(
            """SELECT e.id, e.nom, e.email, e.avatar_url, e.created_at, e.derniere_connexion,
                      e.assistant_actif, e.generation_manuelle_actif, e.pronote_class_name, e.pronote_groupes,
                      e.pronote_sync_statut, e.pronote_sync_erreur, e.pronote_derniere_synchro,
                      e.consentement_pronote_le, COUNT(n.id) AS nb_notes
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


class GenerationManuelleActifPayload(BaseModel):
    actif: bool


@app.put("/api/eleves/{eleve_id}/generation-manuelle")
def set_generation_manuelle_actif(eleve_id: int, payload: GenerationManuelleActifPayload, request: Request):
    """Active/désactive la génération manuelle pour un élève précis — voir _peut_generer_manuellement."""
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM eleves WHERE id = ?", (eleve_id,)).fetchone() is None:
            raise HTTPException(404, "Élève introuvable")
        conn.execute("UPDATE eleves SET generation_manuelle_actif = ? WHERE id = ?", (int(payload.actif), eleve_id))
    return {"ok": True}


@app.post("/api/eleves/{eleve_id}/reinitialiser-pronote")
def reinitialiser_pronote_eleve(eleve_id: int, request: Request):
    """
    Force un élève à re-pairer son compte Pronote (jeton cassé, élève ayant
    quitté la classe...) : efface son jeton chiffré, il devra reprendre le
    flux de connexion (upload QR + PIN) à sa prochaine visite.
    """
    _require_admin(request)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM eleves WHERE id = ?", (eleve_id,)).fetchone() is None:
            raise HTTPException(404, "Élève introuvable")
        conn.execute(
            "UPDATE eleves SET pronote_credentials = NULL, pronote_sync_statut = NULL, pronote_sync_erreur = NULL WHERE id = ?",
            (eleve_id,),
        )
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
        ia_cfg = ia_generation.config_ia(conn)
        pronote_cfg = pronote_sync.config_pronote(conn)
        ocr_cfg = ocr.config_ocr(conn)
        verif_cfg = ia_verification.config_verif(conn)
    return {
        "ia_moteur": moteur if moteur in ("ollama", "gemini", "claude") else "ollama",
        "ollama_url": ollama_url or OLLAMA_URL,
        "ollama_model": ollama_model or OLLAMA_MODEL,
        "ollama_chunk_size": ia_cfg["ollama_chunk_size"],
        "ollama_decoupage_actif": ia_cfg["ollama_decoupage_actif"],
        # Consignes des prompts (voir Services/ia_generation.py) : la partie
        # "consigne" est personnalisable, le format JSON de sortie non (le
        # code dépend de ses clés exactes pour lire la réponse de l'IA) —
        # renvoyé quand même pour que l'écran admin montre le prompt complet.
        "ia_prompt_generation_consigne": ia_cfg["prompt_generation_consigne"] or ia_generation.PROMPT_GENERATION_CONSIGNE_DEFAUT,
        "ia_prompt_generation_consigne_defaut": ia_generation.PROMPT_GENERATION_CONSIGNE_DEFAUT,
        "ia_prompt_generation_format_json": ia_generation.GENERATION_JSON_FORMAT,
        "ia_prompt_completion_consigne": ia_cfg["prompt_completion_consigne"] or ia_generation.PROMPT_COMPLEMENT_CONSIGNE_DEFAUT,
        "ia_prompt_completion_consigne_defaut": ia_generation.PROMPT_COMPLEMENT_CONSIGNE_DEFAUT,
        "ia_prompt_completion_format_json": ia_generation.COMPLEMENT_JSON_FORMAT,
        "gemini_model": gemini_model or GEMINI_MODEL,
        "gemini_api_key_configuree": bool(gemini_key),
        "anthropic_api_key_configuree": bool(anthropic_key),
        "pronote_url": pronote_cfg["pronote_url"],
        "sync_days_back": pronote_cfg["sync_days_back"],
        "sync_days_forward": pronote_cfg["sync_days_forward"],
        "pronote_jeton_present": CREDENTIALS_PATH.exists(),
        "ocr_engine": ocr_cfg["moteur"],
        "paddleocr_enable_mkldnn": ocr_cfg["paddleocr_enable_mkldnn"],
        # Vérification (Services/ia_verification.py) : moteur indépendant de
        # celui de Génération IA (même clés Anthropic/Gemini, partagées).
        "verif_moteur": verif_cfg["moteur"],
        "verif_ollama_url": verif_cfg["ollama_url"],
        "verif_ollama_model": verif_cfg["ollama_model"],
        "verif_gemini_model": verif_cfg["gemini_model"],
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
    ollama_chunk_size: int | None = None
    ollama_decoupage_actif: bool | None = None
    ia_prompt_generation_consigne: str | None = None  # None = ne pas changer ; chaîne vide = réinitialiser au défaut
    ia_prompt_completion_consigne: str | None = None  # idem
    gemini_model: str | None = None
    gemini_api_key: str | None = None  # None = ne pas changer ; chaîne vide = effacer
    anthropic_api_key: str | None = None  # idem
    pronote_url: str | None = None
    sync_days_back: int | None = None
    sync_days_forward: int | None = None
    ocr_engine: str | None = None
    paddleocr_enable_mkldnn: bool | None = None
    verif_moteur: str | None = None
    verif_ollama_url: str | None = None
    verif_ollama_model: str | None = None
    verif_gemini_model: str | None = None


@app.put("/api/parametres")
def set_parametres(payload: ParametresIA, request: Request):
    _require_admin(request)
    if payload.ia_moteur not in ("ollama", "gemini", "claude"):
        raise HTTPException(400, "Moteur invalide (attendu 'ollama', 'gemini' ou 'claude').")
    if payload.sync_days_back is not None and payload.sync_days_back < 0:
        raise HTTPException(400, "Le nombre de jours en arrière doit être positif.")
    if payload.sync_days_forward is not None and payload.sync_days_forward < 0:
        raise HTTPException(400, "Le nombre de jours en avant doit être positif.")
    if payload.ocr_engine is not None and payload.ocr_engine not in ("paddleocr", "claude"):
        raise HTTPException(400, "Moteur OCR invalide (attendu 'paddleocr' ou 'claude').")
    if payload.ollama_chunk_size is not None and payload.ollama_chunk_size < 1000:
        raise HTTPException(400, "La taille de découpage doit être d'au moins 1000 caractères.")
    if payload.verif_moteur is not None and payload.verif_moteur not in ("ollama", "gemini", "claude"):
        raise HTTPException(400, "Moteur de vérification invalide (attendu 'ollama', 'gemini' ou 'claude').")
    with db.session() as conn:
        db.set_parametre(conn, "ia_moteur", payload.ia_moteur)
        if payload.ollama_url:
            db.set_parametre(conn, "ollama_url", payload.ollama_url)
        if payload.ollama_model:
            db.set_parametre(conn, "ollama_model", payload.ollama_model)
        if payload.ollama_chunk_size is not None:
            db.set_parametre(conn, "ollama_chunk_size", str(payload.ollama_chunk_size))
        if payload.ollama_decoupage_actif is not None:
            db.set_parametre(conn, "ollama_decoupage_actif", "1" if payload.ollama_decoupage_actif else "0")
        if payload.ia_prompt_generation_consigne is not None:
            db.set_parametre(conn, "ia_prompt_generation_consigne", payload.ia_prompt_generation_consigne)
        if payload.ia_prompt_completion_consigne is not None:
            db.set_parametre(conn, "ia_prompt_completion_consigne", payload.ia_prompt_completion_consigne)
        if payload.gemini_model:
            db.set_parametre(conn, "gemini_model", payload.gemini_model)
        if payload.gemini_api_key is not None:
            db.set_parametre(conn, "gemini_api_key", payload.gemini_api_key)
        if payload.anthropic_api_key is not None:
            db.set_parametre(conn, "anthropic_api_key", payload.anthropic_api_key)
        if payload.pronote_url:
            db.set_parametre(conn, "pronote_url", payload.pronote_url)
        if payload.sync_days_back is not None:
            db.set_parametre(conn, "sync_days_back", str(payload.sync_days_back))
        if payload.sync_days_forward is not None:
            db.set_parametre(conn, "sync_days_forward", str(payload.sync_days_forward))
        if payload.ocr_engine:
            db.set_parametre(conn, "ocr_engine", payload.ocr_engine)
        if payload.paddleocr_enable_mkldnn is not None:
            db.set_parametre(conn, "paddleocr_enable_mkldnn", "1" if payload.paddleocr_enable_mkldnn else "0")
        if payload.verif_moteur:
            db.set_parametre(conn, "verif_moteur", payload.verif_moteur)
        if payload.verif_ollama_url:
            db.set_parametre(conn, "verif_ollama_url", payload.verif_ollama_url)
        if payload.verif_ollama_model:
            db.set_parametre(conn, "verif_ollama_model", payload.verif_ollama_model)
        if payload.verif_gemini_model:
            db.set_parametre(conn, "verif_gemini_model", payload.verif_gemini_model)
    return {"ok": True}


@app.get("/api/devoirs")
def list_devoirs(request: Request, classe: str | None = None):
    _require_session(request)
    with db.session() as conn:
        classe_filtre = _classe_filtre(conn, request, classe)
        classe_clause = "AND d.classe = ?" if classe_filtre else ""
        params = (classe_filtre,) if classe_filtre else ()
        rows = conn.execute(
            f"""SELECT d.id, d.date_rendu, d.description, d.fait, m.nom AS matiere
               FROM devoirs d JOIN matieres m ON m.id = d.matiere_id
               WHERE d.fait = 0 AND m.exclue = 0 {classe_clause} ORDER BY d.date_rendu""",
            params,
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


def _classe_parent_document(conn, doc) -> str | None:
    """Classe du cours/devoir parent d'un document (l'un des deux id est toujours NULL)."""
    if doc["cours_id"]:
        row = conn.execute("SELECT classe FROM cours WHERE id = ?", (doc["cours_id"],)).fetchone()
    elif doc["devoir_id"]:
        row = conn.execute("SELECT classe FROM devoirs WHERE id = ?", (doc["devoir_id"],)).fetchone()
    else:
        return None
    return row["classe"] if row else None


def _verifier_classe_document(conn, request: Request, doc) -> None:
    """Même garde-fou que get_cours, appliqué aux documents (téléchargement/aperçu)."""
    classe_eleve = _classe_filtre(conn, request, None)
    classe_doc = _classe_parent_document(conn, doc)
    if classe_eleve and classe_doc and classe_doc != classe_eleve:
        raise HTTPException(403, "Ce document n'appartient pas à ta classe.")


@app.get("/api/documents/{document_id}/fichier")
def download_document(document_id: int, request: Request):
    _require_session(request)
    with db.session() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "Document introuvable")
        _verifier_classe_document(conn, request, doc)
    return _reponse_fichier(doc["chemin_local"], doc["nom_fichier"], inline=False)


@app.get("/api/documents/{document_id}/apercu")
def apercu_document(document_id: int, request: Request):
    _require_session(request)
    with db.session() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "Document introuvable")
        _verifier_classe_document(conn, request, doc)
    return _reponse_fichier(doc["chemin_local"], doc["nom_fichier"], inline=True)


@app.get("/api/notes/{note_id}/fichier")
def download_note_fichier(note_id: int, request: Request):
    _require_session(request)
    with db.session() as conn:
        note = conn.execute("SELECT * FROM notes_eleves WHERE id = ?", (note_id,)).fetchone()
        if note is None:
            raise HTTPException(404, "Note introuvable")
    return _reponse_fichier(note["chemin_fichier"], f"note_{note_id}{Path(note['chemin_fichier'] or '').suffix}", inline=False)


@app.get("/api/notes/{note_id}/apercu")
def apercu_note_fichier(note_id: int, request: Request):
    _require_session(request)
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
    "Tu es l'assistant IA de Ghost School, une application de révision pour un(e) élève. "
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
