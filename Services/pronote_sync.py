"""
Synchronisation Pronote → base locale + fichiers sur disque.

Fonctionnement général :
1. Connexion à Pronote avec un jeton (voir README, section "Première connexion").
2. Récupération des cours et devoirs sur une fenêtre de dates (SYNC_DAYS_BACK à
   SYNC_DAYS_FORWARD, voir config.py).
3. Pour chaque cours/devoir nouveau, téléchargement des documents attachés
   dans data/documents/, et enregistrement des métadonnées en base.

Points d'attention (issus du fonctionnement réel de Pronote / pronotepy) :
- Pronote régénère tous les identifiants internes à chaque connexion : on ne
  peut donc pas s'appuyer sur lesson.id comme clé stable. On calcule notre
  propre clé (date + heure + matière + professeur) pour éviter les doublons.
- `lesson.content` déclenche une requête réseau à part et coûte cher : on ne
  le fait que pour les cours qu'on n'a encore jamais récupérés.
- Le jeton de connexion (`credentials.json`) est à usage unique : on doit
  IMPÉRATIVEMENT le régénérer et le réenregistrer après chaque connexion,
  sinon la connexion suivante échoue.
- Certains créneaux (sorties pédagogiques) n'ont pas de matière exploitable :
  on les ignore proprement plutôt que de planter. Les cours annulés, eux,
  sont conservés (avec leur motif) plutôt qu'ignorés — voir `_sync_lessons`.
- Certains établissements utilisent Pronote pour des créneaux qui ne sont
  pas de vraies matières (réunions parents-profs, journées spéciales...) :
  liste éditable (`matieres_exclues`, écran admin Paramétrage) plutôt que
  détectée automatiquement, ces libellés étant propres à chaque établissement.
- Les notes (`client.current_period.grades`) ne se récupèrent que période
  par période, pas sur une fenêtre de dates comme cours/devoirs.

Depuis le pairage Pronote par élève (voir BackEnd/app/main.py::
pairer_eleve_pronote), la synchro ne se limite plus au seul compte de
référence (admin) : elle boucle aussi sur chaque élève ayant un jeton
Pronote chiffré enregistré (`eleves.pronote_credentials`), pour couvrir
les groupes (LV2, options...) que le compte de référence ne voit pas.
Cours/devoirs/documents restent PARTAGÉS (dédupliqués par
date+heure+matière+professeur, peu importe quel compte les a vus en
premier) ; les notes, elles, sont PERSONNELLES et scopées par
`eleve_id` — jamais mélangées entre élèves. Un compte élève dont la
synchro échoue (jeton cassé, réseau) n'interrompt jamais celle des
autres comptes ni celle du compte de référence.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import pronotepy
import requests

from . import crypto_secrets, db, ocr
from .config import (
    PRONOTE_URL,
    CREDENTIALS_PATH,
    DOCUMENTS_DIR,
    SYNC_DAYS_BACK,
    SYNC_DAYS_FORWARD,
)

log = logging.getLogger("ghostcards.pronote_sync")


class SyncError(Exception):
    pass


def _now() -> str:
    # UTC explicite (voir Services/db.py::now_iso) : l'OptiPlex tourne en
    # UTC, un horodatage naïf serait ré-interprété à tort comme étant déjà
    # dans le fuseau du navigateur qui l'affiche, décalant les heures.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_key(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _slugify(text: str) -> str:
    text = text.lower().strip()
    replacements = {"é": "e", "è": "e", "ê": "e", "à": "a", "î": "i", "ô": "o", "ç": "c", "û": "u"}
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "matiere"


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name[:150] or "fichier"


def config_pronote(conn) -> dict:
    """
    Résout la configuration Pronote effective : valeurs enregistrées via
    l'écran admin "Paramétrage" (table `parametres`) si elles existent,
    sinon les valeurs de départ définies dans .env (Services/config.py).
    Le jeton de connexion (secrets/credentials.json) n'est PAS géré ici :
    il se régénère via la procédure de première connexion (voir README),
    pas depuis un champ texte de l'écran admin.
    """
    def _int_parametre(cle: str, defaut: int) -> int:
        valeur = db.get_parametre(conn, cle)
        try:
            return int(valeur) if valeur is not None else defaut
        except ValueError:
            return defaut

    matieres_exclues_brut = db.get_parametre(
        conn, "matieres_exclues", "Réunion parents-profs, Journée du sport scolaire"
    ) or ""
    return {
        "pronote_url": db.get_parametre(conn, "pronote_url", PRONOTE_URL) or PRONOTE_URL,
        "sync_days_back": _int_parametre("sync_days_back", SYNC_DAYS_BACK),
        "sync_days_forward": _int_parametre("sync_days_forward", SYNC_DAYS_FORWARD),
        # Certains créneaux Pronote ne sont pas de vraies matières (réunions,
        # journées spéciales...) : chaque établissement les nomme à sa
        # façon, impossible à deviner automatiquement — liste éditable
        # depuis l'écran admin Paramétrage. Comparaison par slug (voir
        # `_slugify`) pour ignorer accents/casse/espaces.
        "matieres_exclues_slugs": {
            _slugify(nom) for nom in matieres_exclues_brut.split(",") if nom.strip()
        },
    }


def get_client(pronote_url: str) -> pronotepy.Client:
    """
    Se connecte à Pronote avec le jeton stocké localement et le fait pivoter
    immédiatement (obligatoire : un jeton pronotepy ne sert qu'une fois).

    `pronote_url` ne sert qu'à vérifier que Pronote est bien configuré :
    l'adresse réellement utilisée pour la connexion est celle enregistrée
    dans le jeton lui-même (pronotepy l'y inclut à l'export), pas cette
    valeur — modifier l'URL ici ne "redirige" donc pas vers un autre
    établissement, il faudrait relancer la procédure de première connexion.
    """
    if not pronote_url:
        raise SyncError("PRONOTE_URL n'est pas configurée (écran admin Paramétrage, ou .env).")
    if not CREDENTIALS_PATH.exists():
        raise SyncError(
            f"Aucun identifiant trouvé à {CREDENTIALS_PATH}. "
            "Lance d'abord la procédure de première connexion (voir README)."
        )

    creds = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    try:
        client = pronotepy.Client.token_login(**creds)
    except requests.exceptions.RequestException as e:
        # Message générique volontairement : la cause exacte (DNS, timeout,
        # proxy, coupure...) importe peu à l'admin, qui ne peut de toute
        # façon agir que sur "vérifier la connexion internet de l'OptiPlex".
        # L'exception d'origine reste dans les logs (log.exception plus bas
        # dans sync()) pour du diagnostic plus poussé si besoin.
        raise SyncError(
            "Impossible de joindre le serveur Pronote — vérifie la connexion "
            "internet de l'OptiPlex, puis réessaie."
        ) from e

    if not client.logged_in:
        raise SyncError("Échec de connexion à Pronote avec le jeton enregistré.")

    # Rotation obligatoire du jeton après usage.
    CREDENTIALS_PATH.write_text(json.dumps(client.export_credentials()), encoding="utf-8")
    return client


def _get_client_eleve(credentials_chiffrees: str) -> tuple[pronotepy.Client, str]:
    """
    Se connecte avec le jeton chiffré d'un élève (voir Services/crypto_secrets.py)
    et le fait pivoter immédiatement. Renvoie le nouveau jeton chiffré à
    persister par l'appelant (`eleves.pronote_credentials`) — contrairement
    au compte de référence, il n'y a pas UN SEUL fichier `credentials.json`
    à écrire, chaque élève a le sien en base.
    """
    creds = crypto_secrets.dechiffrer_json(credentials_chiffrees)
    try:
        client = pronotepy.Client.token_login(**creds)
    except requests.exceptions.RequestException as e:
        raise SyncError("Connexion à Pronote perdue pendant la synchronisation.") from e
    if not client.logged_in:
        raise SyncError("Jeton Pronote invalide ou expiré — l'élève doit re-pairer son compte.")
    return client, crypto_secrets.chiffrer_json(client.export_credentials())


def _dedupe_blob(data: bytes, suffix: str) -> Path:
    """
    Stocke un contenu de fichier une seule fois sous DOCUMENTS_DIR/_blobs/,
    adressé par son empreinte sha256. Pronote attache parfois le même
    fichier à plusieurs cours/devoirs (photocopie donnée dans deux classes,
    document réutilisé) : sans ça, chaque référence retéléchargerait et
    dupliquerait les mêmes octets sur le disque.
    """
    digest = hashlib.sha256(data).hexdigest()
    blob_dir = DOCUMENTS_DIR / "_blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)
    blob_path = blob_dir / f"{digest}{suffix}"
    if not blob_path.exists():
        blob_path.write_bytes(data)
    return blob_path


def _download_attachment(attachment, dest_dir, base_name: str):
    """
    Télécharge une pièce jointe Pronote sur le disque.
    Renvoie (chemin_relatif, url_externe) — l'un des deux est toujours None.
    Les attachements de type "lien" (type != 1) ne sont pas des fichiers
    téléchargeables : on garde seulement l'URL.
    """
    if getattr(attachment, "type", 1) != 1:
        return None, attachment.url

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{base_name}_{_safe_filename(attachment.name)}"
    dest_path = dest_dir / filename

    if not dest_path.exists():
        # Téléchargé dans un fichier temporaire d'abord, pour pouvoir
        # dédupliquer par contenu (voir _dedupe_blob) avant de l'installer
        # définitivement sous son nom lisible attendu par le reste du code.
        tmp_path = dest_dir / f".tmp_{filename}"
        attachment.save(str(tmp_path))
        blob_path = _dedupe_blob(tmp_path.read_bytes(), tmp_path.suffix)
        tmp_path.unlink()
        try:
            os.link(blob_path, dest_path)  # lien physique : zéro octet dupliqué
        except OSError:
            shutil.copyfile(blob_path, dest_path)  # repli si liens physiques indisponibles

    return str(dest_path.relative_to(DOCUMENTS_DIR.parent)), None


def _store_document(conn, *, cours_id=None, devoir_id=None, nom_fichier, chemin_local, url_externe, source="pronote"):
    cur = conn.execute(
        """INSERT OR IGNORE INTO documents
           (cours_id, devoir_id, nom_fichier, chemin_local, url_externe, source, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cours_id, devoir_id, nom_fichier, chemin_local or f"lien:{url_externe}", url_externe, source, _now()),
    )
    return cur.lastrowid


def _transcrire_document_silencieux(document_id: int | None) -> None:
    """
    Extraction de texte lancée juste après le téléchargement d'un document,
    une fois la transaction de sync commitée (jamais pendant : `transcribe_
    document` ouvre sa propre connexion en écriture, ce qui se bloquerait
    sur SQLite si la transaction de sync était encore ouverte).

    Sans ça, le document reste avec `texte_extrait` NULL indéfiniment (rien
    ne déclenchait jamais sa transcription) et `_texte_source` (voir
    Services/ia_generation.py) ne trouve que la description Pronote —
    souvent un simple horaire/titre de chapitre — d'où des générations IA
    hors sujet malgré un document bien attaché. Une erreur ici (PDF
    corrompu, OCR indisponible...) ne doit pas interrompre le reste de la
    synchronisation : elle est déjà journalisée comme traitement en échec
    par `transcribe_document` lui-même.
    """
    if not document_id:
        return
    try:
        ocr.transcribe_document(document_id)
    except Exception:
        log.warning("Échec de la transcription automatique du document id=%s", document_id, exc_info=True)


# Pause entre chaque compte élève synchronisé, pour ne jamais bombarder le
# serveur Pronote de l'établissement de connexions rapprochées (le serveur
# throttle déjà ça de son côté, erreur "25 — Exceeded max authorization
# requests" — voir pronotepy) : 36 comptes à 5 s d'écart ajoutent ~3 min à
# une synchro qui tourne toutes les 2h, largement acceptable.
STAGGER_ELEVES_S = 5


def _synchroniser_compte(client, cfg, date_from, date_to, fetch_content, counters, documents_a_transcrire, *, eleve_id=None):
    """Cours/devoirs (partagés) + notes (scopées par eleve_id) pour un client déjà connecté."""
    with db.session() as conn:
        _sync_lessons(conn, client, date_from, date_to, fetch_content, counters, documents_a_transcrire, cfg["matieres_exclues_slugs"])
    with db.session() as conn:
        _sync_homework(conn, client, date_from, date_to, counters, documents_a_transcrire, cfg["matieres_exclues_slugs"])
    with db.session() as conn:
        _sync_grades(conn, client, counters, cfg["matieres_exclues_slugs"], eleve_id=eleve_id)


def _synchroniser_eleve(eleve_row, cfg, date_from, date_to, fetch_content, counters, documents_a_transcrire, ctx):
    """
    Synchronise le compte Pronote d'UN élève, sans jamais laisser un jeton
    cassé ou un problème réseau interrompre la synchro des autres comptes
    (voir l'appelant, `sync()`) : toute erreur est capturée ici, journalisée
    à la fois dans l'étape du traitement (diagnostic admin) et sur la ligne
    `eleves` elle-même (statut visible dans l'écran "Élèves").
    """
    eleve_id, nom = eleve_row["id"], eleve_row["nom"]
    t0 = time.monotonic()
    avant = dict(counters)
    try:
        client, nouvelles_credentials = _get_client_eleve(eleve_row["pronote_credentials"])
        with db.session() as conn:
            conn.execute("UPDATE eleves SET pronote_credentials = ? WHERE id = ?", (nouvelles_credentials, eleve_id))

        _synchroniser_compte(client, cfg, date_from, date_to, fetch_content, counters, documents_a_transcrire, eleve_id=eleve_id)

        with db.session() as conn:
            conn.execute(
                "UPDATE eleves SET pronote_sync_statut = 'actif', pronote_sync_erreur = NULL, pronote_derniere_synchro = ? WHERE id = ?",
                (_now(), eleve_id),
            )
        ctx.etape(
            f"compte élève : {nom}",
            detail=(
                f"{counters['nouveaux_cours'] - avant['nouveaux_cours']} cours, "
                f"{counters['nouveaux_devoirs'] - avant['nouveaux_devoirs']} devoirs, "
                f"{counters['nouvelles_notes'] - avant['nouvelles_notes']} notes"
            ),
            duree_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:  # noqa: BLE001 — un compte élève cassé ne doit jamais faire échouer toute la synchro
        with db.session() as conn:
            conn.execute(
                "UPDATE eleves SET pronote_sync_statut = 'echec', pronote_sync_erreur = ? WHERE id = ?",
                (str(e), eleve_id),
            )
        ctx.etape(f"compte élève : {nom}", statut="echec", detail=str(e), duree_ms=int((time.monotonic() - t0) * 1000))
        log.warning("Échec de synchro pour l'élève %s (id=%s)", nom, eleve_id, exc_info=True)


def sync(fetch_content: bool = True, traitement_id: int | None = None) -> dict:
    """
    Lance une synchronisation complète : le compte de référence (admin)
    PUIS chaque élève ayant un jeton Pronote chiffré enregistré (voir
    module docstring). Retourne un résumé (compteurs), agrégé sur tous les
    comptes. C'est cette fonction qu'appellent l'API (/api/sync) et la
    tâche planifiée.

    Journalisée dans `traitements` (type 'pronote_sync') comme les
    extractions OCR, pour que l'admin voie aussi l'historique des synchros
    (et puisse la relancer) depuis l'écran "Traitements" — même table,
    mêmes endpoints, rien de plus à ajouter côté API/frontend. Le détail
    par étape (connexion, cours, devoirs, un par un par élève) est
    journalisé via `db.log_traitement`, visible même si la synchro échoue
    en cours de route (utile pour savoir jusqu'où elle est allée).

    `traitement_id` : réutilise une ligne déjà créée (déclenchement manuel
    depuis l'écran admin, voir POST /api/sync) au lieu d'en créer une
    nouvelle, pour que l'API puisse renvoyer l'id tout de suite et ouvrir
    le suivi sans attendre.
    """
    db.init_db()
    started_at = _now()
    counters = {
        "nouveaux_cours": 0, "nouveaux_devoirs": 0, "nouveaux_documents": 0, "nouvelles_notes": 0,
        # Détail lisible de chaque nouveauté (pas juste le compteur) — voir
        # `_sync_lessons`/`_sync_homework`/`_sync_grades`, affiché dans le
        # RÉSULTAT du traitement pour savoir précisément ce qui a été importé.
        "detail_cours": [], "detail_devoirs": [], "detail_notes": [],
    }
    erreur = None
    with db.session() as conn:
        cfg = config_pronote(conn)
        comptes_eleves = conn.execute(
            "SELECT id, nom, pronote_credentials FROM eleves WHERE pronote_credentials IS NOT NULL"
        ).fetchall()

    try:
        with db.log_traitement("pronote_sync", "sync", 0, traitement_id=traitement_id) as ctx:
            ctx.moteur = "pronotepy"

            t0 = time.monotonic()
            client = get_client(cfg["pronote_url"])
            ctx.etape("connexion (référence)", detail="Connexion à Pronote (jeton pivoté)", duree_ms=int((time.monotonic() - t0) * 1000))

            date_from = date.today() - timedelta(days=cfg["sync_days_back"])
            date_to = date.today() + timedelta(days=cfg["sync_days_forward"])
            documents_a_transcrire = []

            t1 = time.monotonic()
            with db.session() as conn:
                _sync_lessons(conn, client, date_from, date_to, fetch_content, counters, documents_a_transcrire, cfg["matieres_exclues_slugs"])
            ctx.etape(
                "cours",
                detail=f"{counters['nouveaux_cours']} nouveau(x) cours, {counters['nouveaux_documents']} document(s) téléchargé(s)",
                duree_ms=int((time.monotonic() - t1) * 1000),
            )

            t2 = time.monotonic()
            with db.session() as conn:
                _sync_homework(conn, client, date_from, date_to, counters, documents_a_transcrire, cfg["matieres_exclues_slugs"])
            ctx.etape("devoirs", detail=f"{counters['nouveaux_devoirs']} nouveau(x) devoir(s)", duree_ms=int((time.monotonic() - t2) * 1000))

            t4 = time.monotonic()
            try:
                with db.session() as conn:
                    _sync_grades(conn, client, counters, cfg["matieres_exclues_slugs"], eleve_id=None)
                ctx.etape("notes (référence)", detail=f"{counters['nouvelles_notes']} nouvelle(s) note(s)", duree_ms=int((time.monotonic() - t4) * 1000))
            except SyncError as e:
                # Les notes sont secondaires par rapport aux cours/devoirs :
                # une période Pronote mal configurée (ex. pas encore de
                # trimestre en cours) ne doit pas faire échouer toute la
                # synchronisation, seulement cette étape.
                ctx.etape("notes (référence)", statut="echec", detail=str(e), duree_ms=int((time.monotonic() - t4) * 1000))

            # Chaque élève pairé apporte son propre groupe (LV2, options...),
            # invisible depuis le seul compte de référence — voir le
            # docstring du module. Étalé dans le temps (STAGGER_ELEVES_S)
            # pour ne pas bombarder le serveur Pronote de connexions
            # rapprochées ; un compte cassé n'interrompt jamais les suivants.
            for i, eleve_row in enumerate(comptes_eleves):
                if i > 0:
                    time.sleep(STAGGER_ELEVES_S)
                _synchroniser_eleve(eleve_row, cfg, date_from, date_to, fetch_content, counters, documents_a_transcrire, ctx)

            if documents_a_transcrire:
                t3 = time.monotonic()
                for document_id in documents_a_transcrire:
                    _transcrire_document_silencieux(document_id)
                ctx.etape(
                    "transcription des documents",
                    detail=f"{len(documents_a_transcrire)} document(s) transcrit(s) — contenu disponible pour la génération IA",
                    duree_ms=int((time.monotonic() - t3) * 1000),
                )

            # JSON brut plutôt qu'un résumé en phrases — même traitement
            # que la génération IA (voir Services/ia_generation.py), rendu
            # en JSON indenté par le frontend (ResultatFormatte.jsx) :
            # permet de voir d'un coup d'œil si nouveaux_cours/devoirs/
            # documents sont à 0 parce qu'il n'y a réellement rien de neuf
            # dans Pronote, ou si la synchro a un problème plus profond.
            ctx.resultat = json.dumps(counters, ensure_ascii=False)[:4000]
    except Exception as e:  # noqa: BLE001 — déjà journalisé dans `traitements` par db.log_traitement
        log.exception("Échec de la synchronisation Pronote")
        erreur = str(e)
    finally:
        with db.session() as conn:
            conn.execute(
                """INSERT INTO sync_log (started_at, finished_at, nouveaux_cours, nouveaux_devoirs, nouveaux_documents, nouvelles_notes, erreur)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (started_at, _now(), counters["nouveaux_cours"], counters["nouveaux_devoirs"], counters["nouveaux_documents"], counters["nouvelles_notes"], erreur),
            )

    if erreur:
        raise SyncError(erreur)
    return counters


def _sync_lessons(conn, client, date_from, date_to, fetch_content, counters, documents_a_transcrire, matieres_exclues_slugs):
    try:
        lessons = client.lessons(date_from, date_to)
    except requests.exceptions.RequestException as e:
        raise SyncError("Connexion à Pronote perdue pendant la synchronisation — réessaie plus tard.") from e
    log.info("Pronote : %d créneaux reçus entre %s et %s", len(lessons), date_from, date_to)

    for lesson in lessons:
        subject = getattr(lesson, "subject", None)
        if subject is None:
            # sortie pédagogique ou créneau sans matière exploitable
            continue
        if _slugify(subject.name) in matieres_exclues_slugs:
            # pas une vraie matière (réunion, journée spéciale...) — voir
            # config_pronote() / écran admin Paramétrage.
            continue

        matiere_id = db.upsert_matiere(conn, subject.name)
        teacher = getattr(lesson, "teacher_name", "") or ""
        key = _stable_key(lesson.start.isoformat(), subject.name, teacher)

        # Emploi du temps enrichi : ces champs peuvent changer d'une synchro
        # à l'autre (annulation décidée après coup, salle réattribuée) même
        # pour un cours déjà connu — recalculés et réenregistrés à chaque
        # passage, contrairement au contenu (titre/description), coûteux à
        # rapatrier et rapatrié une seule fois (voir plus bas).
        annule = int(bool(getattr(lesson, "canceled", False)))
        statut = getattr(lesson, "status", None) if annule else None
        salle = ", ".join(getattr(lesson, "classrooms", None) or []) or None
        groupe = ", ".join(getattr(lesson, "group_names", None) or []) or None
        memo = getattr(lesson, "memo", None)
        devoir_surveille = int(bool(getattr(lesson, "test", False)))

        row = conn.execute(
            "SELECT id, contenu_recupere FROM cours WHERE external_key = ?", (key,)
        ).fetchone()

        if row is None:
            cur = conn.execute(
                """INSERT INTO cours
                   (external_key, matiere_id, date, heure_debut, heure_fin, professeur,
                    titre, description, annule, statut, salle, groupe, memo, devoir_surveille,
                    contenu_recupere, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    key, matiere_id,
                    lesson.start.date().isoformat(), lesson.start.strftime("%H:%M"),
                    lesson.end.strftime("%H:%M") if getattr(lesson, "end", None) else None,
                    teacher, None, None, annule, statut, salle, groupe, memo, devoir_surveille,
                    _now(), _now(),
                ),
            )
            cours_id = cur.lastrowid
            already_fetched = False
            counters["nouveaux_cours"] += 1
            ligne = f"{subject.name} — {lesson.start.strftime('%d/%m %H:%M')}"
            if teacher:
                ligne += f" ({teacher})"
            if annule:
                ligne += " [annulé]"
            counters["detail_cours"].append(ligne)
        else:
            cours_id = row["id"]
            already_fetched = bool(row["contenu_recupere"])
            conn.execute(
                """UPDATE cours SET annule = ?, statut = ?, salle = ?, groupe = ?, memo = ?,
                   devoir_surveille = ?, updated_at = ? WHERE id = ?""",
                (annule, statut, salle, groupe, memo, devoir_surveille, _now(), cours_id),
            )

        if fetch_content and not already_fetched:
            _fetch_lesson_content(conn, client, lesson, cours_id, subject.name, counters, documents_a_transcrire)


def _fetch_lesson_content(conn, client, lesson, cours_id, subject_name, counters, documents_a_transcrire):
    try:
        content = lesson.content  # requête réseau dédiée, coûteuse : une seule fois par cours
    except Exception:
        log.warning("Impossible de récupérer le contenu du cours id=%s", cours_id)
        return

    conn.execute("UPDATE cours SET contenu_recupere = 1, updated_at = ? WHERE id = ?", (_now(), cours_id))

    if content is None:
        return

    conn.execute(
        "UPDATE cours SET titre = ?, description = ?, updated_at = ? WHERE id = ?",
        (getattr(content, "title", None), getattr(content, "description", None), _now(), cours_id),
    )

    dest_dir = DOCUMENTS_DIR / _slugify(subject_name) / lesson.start.strftime("%Y-%m")
    for f in getattr(content, "files", []):
        chemin_local, url_externe = _download_attachment(f, dest_dir, base_name=f"cours{cours_id}")
        document_id = _store_document(
            conn, cours_id=cours_id, nom_fichier=f.name,
            chemin_local=chemin_local, url_externe=url_externe,
        )
        counters["nouveaux_documents"] += 1
        documents_a_transcrire.append(document_id)


def _sync_homework(conn, client, date_from, date_to, counters, documents_a_transcrire, matieres_exclues_slugs):
    try:
        homeworks = client.homework(date_from, date_to)
    except requests.exceptions.RequestException as e:
        raise SyncError("Connexion à Pronote perdue pendant la synchronisation — réessaie plus tard.") from e
    log.info("Pronote : %d devoirs reçus", len(homeworks))

    for hw in homeworks:
        subject = getattr(hw, "subject", None)
        if subject is None:
            continue
        if _slugify(subject.name) in matieres_exclues_slugs:
            continue

        matiere_id = db.upsert_matiere(conn, subject.name)
        description = hw.description or ""
        key = _stable_key(hw.date.isoformat(), subject.name, description[:60])

        row = conn.execute("SELECT id FROM devoirs WHERE external_key = ?", (key,)).fetchone()
        if row is not None:
            continue  # déjà connu : on ne retélécharge pas ses pièces jointes

        cur = conn.execute(
            """INSERT INTO devoirs (external_key, matiere_id, date_rendu, description, fait, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (key, matiere_id, hw.date.isoformat(), description, int(bool(hw.done)), _now()),
        )
        devoir_id = cur.lastrowid
        counters["nouveaux_devoirs"] += 1
        ligne = f"{subject.name} — pour le {hw.date.strftime('%d/%m/%Y')}"
        if description:
            ligne += f" : {description[:80]}{'…' if len(description) > 80 else ''}"
        counters["detail_devoirs"].append(ligne)

        dest_dir = DOCUMENTS_DIR / _slugify(subject.name) / "devoirs"
        for f in getattr(hw, "files", []):
            chemin_local, url_externe = _download_attachment(f, dest_dir, base_name=f"devoir{devoir_id}")
            document_id = _store_document(
                conn, devoir_id=devoir_id, nom_fichier=f.name,
                chemin_local=chemin_local, url_externe=url_externe,
            )
            counters["nouveaux_documents"] += 1
            documents_a_transcrire.append(document_id)


def _sync_grades(conn, client, counters, matieres_exclues_slugs, *, eleve_id=None):
    """
    Notes du trimestre/semestre en cours uniquement (`client.current_period`)
    — Pronote ne permet pas de les interroger sur une fenêtre de dates comme
    les cours/devoirs, seulement période par période. Comme pour les cours,
    grade.id est réattribué à chaque connexion : clé stable calculée nous-mêmes.

    `eleve_id` : None pour le compte de référence (admin), sinon l'élève
    propriétaire de CES notes — inclus dans la clé de dédoublonnage, sans
    quoi deux élèves ayant par coïncidence la même note le même jour dans
    la même matière verraient la seconde silencieusement ignorée comme
    "déjà connue" (la clé ne portait jusqu'ici que sur le contenu de la
    note, jamais sur qui l'a reçue).
    """
    try:
        grades = client.current_period.grades
    except requests.exceptions.RequestException as e:
        raise SyncError("Connexion à Pronote perdue pendant la synchronisation — réessaie plus tard.") from e
    log.info("Pronote : %d note(s) reçue(s) pour la période en cours", len(grades))

    for g in grades:
        subject = getattr(g, "subject", None)
        if subject is None:
            continue
        if _slugify(subject.name) in matieres_exclues_slugs:
            continue

        matiere_id = db.upsert_matiere(conn, subject.name)
        commentaire = g.comment or ""
        key = _stable_key(eleve_id or "reference", g.date.isoformat(), subject.name, str(g.grade), commentaire[:60])

        row = conn.execute("SELECT id FROM notes_pronote WHERE external_key = ?", (key,)).fetchone()
        if row is not None:
            continue  # une note publiée ne change plus ensuite : pas la peine de la réécrire

        conn.execute(
            """INSERT INTO notes_pronote
               (external_key, matiere_id, eleve_id, valeur, bareme, moyenne_classe, note_min, note_max,
                coefficient, commentaire, date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                key, matiere_id, eleve_id, g.grade, g.out_of, g.average, g.min, g.max,
                g.coefficient, commentaire, g.date.isoformat(), _now(),
            ),
        )
        counters["nouvelles_notes"] += 1
        ligne = f"{subject.name} — {g.grade}/{g.out_of}"
        if commentaire:
            ligne += f" ({commentaire[:60]})"
        counters["detail_notes"].append(ligne)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = sync()
    print(json.dumps(result, ensure_ascii=False, indent=2))
