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
- Certains créneaux (sorties pédagogiques, cours annulés) n'ont pas de
  matière exploitable : on les ignore proprement plutôt que de planter.
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

from . import db
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

    return {
        "pronote_url": db.get_parametre(conn, "pronote_url", PRONOTE_URL) or PRONOTE_URL,
        "sync_days_back": _int_parametre("sync_days_back", SYNC_DAYS_BACK),
        "sync_days_forward": _int_parametre("sync_days_forward", SYNC_DAYS_FORWARD),
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
    conn.execute(
        """INSERT OR IGNORE INTO documents
           (cours_id, devoir_id, nom_fichier, chemin_local, url_externe, source, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cours_id, devoir_id, nom_fichier, chemin_local or f"lien:{url_externe}", url_externe, source, _now()),
    )


def sync(fetch_content: bool = True, traitement_id: int | None = None) -> dict:
    """
    Lance une synchronisation complète. Retourne un résumé (compteurs).
    C'est cette fonction qu'appellent l'API (/api/sync) et la tâche planifiée.

    Journalisée dans `traitements` (type 'pronote_sync') comme les
    extractions OCR, pour que l'admin voie aussi l'historique des synchros
    (et puisse la relancer) depuis l'écran "Traitements" — même table,
    mêmes endpoints, rien de plus à ajouter côté API/frontend. Le détail
    par étape (connexion, cours, devoirs) est journalisé via
    `db.log_traitement`, visible même si la synchro échoue en cours de
    route (utile pour savoir jusqu'où elle est allée).

    `traitement_id` : réutilise une ligne déjà créée (déclenchement manuel
    depuis l'écran admin, voir POST /api/sync) au lieu d'en créer une
    nouvelle, pour que l'API puisse renvoyer l'id tout de suite et ouvrir
    le suivi sans attendre.
    """
    db.init_db()
    started_at = _now()
    counters = {
        "nouveaux_cours": 0, "nouveaux_devoirs": 0, "nouveaux_documents": 0,
        # Détail lisible de chaque nouveauté (pas juste le compteur) — voir
        # `_sync_lessons`/`_sync_homework`, affiché dans le RÉSULTAT du
        # traitement pour savoir précisément ce qui a été importé.
        "detail_cours": [], "detail_devoirs": [],
    }
    erreur = None
    with db.session() as conn:
        cfg = config_pronote(conn)

    try:
        with db.log_traitement("pronote_sync", "sync", 0, traitement_id=traitement_id) as ctx:
            ctx.moteur = "pronotepy"

            t0 = time.monotonic()
            client = get_client(cfg["pronote_url"])
            ctx.etape("connexion", detail="Connexion à Pronote (jeton pivoté)", duree_ms=int((time.monotonic() - t0) * 1000))

            date_from = date.today() - timedelta(days=cfg["sync_days_back"])
            date_to = date.today() + timedelta(days=cfg["sync_days_forward"])

            t1 = time.monotonic()
            with db.session() as conn:
                _sync_lessons(conn, client, date_from, date_to, fetch_content, counters)
            ctx.etape(
                "cours",
                detail=f"{counters['nouveaux_cours']} nouveau(x) cours, {counters['nouveaux_documents']} document(s) téléchargé(s)",
                duree_ms=int((time.monotonic() - t1) * 1000),
            )

            t2 = time.monotonic()
            with db.session() as conn:
                _sync_homework(conn, client, date_from, date_to, counters)
            ctx.etape("devoirs", detail=f"{counters['nouveaux_devoirs']} nouveau(x) devoir(s)", duree_ms=int((time.monotonic() - t2) * 1000))

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
                """INSERT INTO sync_log (started_at, finished_at, nouveaux_cours, nouveaux_devoirs, nouveaux_documents, erreur)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (started_at, _now(), counters["nouveaux_cours"], counters["nouveaux_devoirs"], counters["nouveaux_documents"], erreur),
            )

    if erreur:
        raise SyncError(erreur)
    return counters


def _sync_lessons(conn, client, date_from, date_to, fetch_content, counters):
    try:
        lessons = client.lessons(date_from, date_to)
    except requests.exceptions.RequestException as e:
        raise SyncError("Connexion à Pronote perdue pendant la synchronisation — réessaie plus tard.") from e
    log.info("Pronote : %d créneaux reçus entre %s et %s", len(lessons), date_from, date_to)

    for lesson in lessons:
        if getattr(lesson, "canceled", False):
            continue
        subject = getattr(lesson, "subject", None)
        if subject is None:
            # sortie pédagogique ou créneau sans matière exploitable
            continue

        matiere_id = db.upsert_matiere(conn, subject.name)
        teacher = getattr(lesson, "teacher_name", "") or ""
        key = _stable_key(lesson.start.isoformat(), subject.name, teacher)

        row = conn.execute(
            "SELECT id, contenu_recupere FROM cours WHERE external_key = ?", (key,)
        ).fetchone()

        if row is None:
            cur = conn.execute(
                """INSERT INTO cours
                   (external_key, matiere_id, date, heure_debut, heure_fin, professeur,
                    titre, description, annule, contenu_recupere, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
                (
                    key, matiere_id,
                    lesson.start.date().isoformat(), lesson.start.strftime("%H:%M"),
                    lesson.end.strftime("%H:%M") if getattr(lesson, "end", None) else None,
                    teacher, None, None, _now(), _now(),
                ),
            )
            cours_id = cur.lastrowid
            already_fetched = False
            counters["nouveaux_cours"] += 1
            ligne = f"{subject.name} — {lesson.start.strftime('%d/%m %H:%M')}"
            if teacher:
                ligne += f" ({teacher})"
            counters["detail_cours"].append(ligne)
        else:
            cours_id = row["id"]
            already_fetched = bool(row["contenu_recupere"])

        if fetch_content and not already_fetched:
            _fetch_lesson_content(conn, client, lesson, cours_id, subject.name, counters)


def _fetch_lesson_content(conn, client, lesson, cours_id, subject_name, counters):
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
        _store_document(
            conn, cours_id=cours_id, nom_fichier=f.name,
            chemin_local=chemin_local, url_externe=url_externe,
        )
        counters["nouveaux_documents"] += 1


def _sync_homework(conn, client, date_from, date_to, counters):
    try:
        homeworks = client.homework(date_from, date_to)
    except requests.exceptions.RequestException as e:
        raise SyncError("Connexion à Pronote perdue pendant la synchronisation — réessaie plus tard.") from e
    log.info("Pronote : %d devoirs reçus", len(homeworks))

    for hw in homeworks:
        subject = getattr(hw, "subject", None)
        if subject is None:
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
            _store_document(
                conn, devoir_id=devoir_id, nom_fichier=f.name,
                chemin_local=chemin_local, url_externe=url_externe,
            )
            counters["nouveaux_documents"] += 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = sync()
    print(json.dumps(result, ensure_ascii=False, indent=2))
