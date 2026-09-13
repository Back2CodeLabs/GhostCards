"""
Accès à la base de données locale (SQLite).

SQLite a été choisi volontairement plutôt que Postgres/MySQL : Ghost School
tourne sur une seule machine (l'OptiPlex), donc pas besoin d'un serveur de
base de données séparé à installer, sauvegarder et surveiller. Le mode WAL
permet de lire pendant qu'une synchronisation écrit, sans verrouillage.
"""
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

from .config import DB_PATH, CLASSE_ATTENDUE

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def now_iso() -> str:
    """
    Horodatage courant en UTC, avec le décalage explicite dans la chaîne
    ISO (ex. "2026-09-09T01:04:28+00:00"). Le frontend (`new Date(iso)`)
    convertit alors correctement vers le fuseau du navigateur qui affiche
    la page — indispensable puisque l'OptiPlex tourne en UTC alors que
    Cédric et ses élèves sont en Europe/Paris (décalage de 1h ou 2h selon
    l'heure d'été) : un `datetime.now()` naïf aurait donné une heure sans
    fuseau, que le navigateur aurait alors interprétée à tort comme étant
    déjà dans SON fuseau local, décalant l'affichage de 1h ou 2h.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coldef: str) -> None:
    """
    Ajoute une colonne à une table existante si elle n'y est pas déjà.
    Nécessaire car `CREATE TABLE IF NOT EXISTS` (schema.sql) ne modifie
    jamais une table qui existe déjà — sur une base déjà en place (comme
    la tienne), une nouvelle colonne doit être ajoutée explicitement.
    """
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def init_db() -> None:
    """Crée les tables si elles n'existent pas encore. Sûr à appeler à chaque démarrage."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_column(conn, "notes_eleves", "eleve_id", "INTEGER REFERENCES eleves(id)")
        _ensure_column(conn, "notes_eleves", "statut", "TEXT NOT NULL DEFAULT 'pret'")
        _ensure_column(conn, "documents", "texte_extrait", "TEXT")
        # Génération IA (résumé/flashcards/quiz) : stockée directement sur la
        # ligne `cours` plutôt que dans une table séparée, pour que
        # GET /api/cours/{id} les renvoie sans changement (dict(cours) les
        # inclut automatiquement).
        _ensure_column(conn, "cours", "ia_statut", "TEXT NOT NULL DEFAULT 'absent'")
        _ensure_column(conn, "cours", "ia_resume", "TEXT")
        _ensure_column(conn, "cours", "ia_resume_detaille", "TEXT")
        _ensure_column(conn, "cours", "ia_flashcards", "TEXT")
        _ensure_column(conn, "cours", "ia_quiz", "TEXT")
        _ensure_column(conn, "cours", "ia_erreur", "TEXT")
        # Texte source effectivement utilisé pour la génération initiale
        # (après découpage/résumé éventuel, voir
        # Services/ia_generation.py::_texte_pour_prompt) — mémorisé pour que
        # "+ 10 flashcards & quiz" réutilise exactement le même contenu au
        # lieu de relire les documents et de recalculer un résumé différent
        # à chaque clic.
        _ensure_column(conn, "cours", "ia_texte_source", "TEXT")
        # Indice de fiabilité (0-100) obtenu en confrontant résumé/flashcards/
        # quiz au texte source avec un second modèle — voir
        # Services/ia_verification.py. Le détail par élément (quelle
        # flashcard/question est en cause) reste dans le traitement
        # 'ia_verification' (table `traitements`), pas dupliqué ici.
        _ensure_column(conn, "cours", "ia_fiabilite", "INTEGER")
        # Détail des étapes internes d'un traitement (ex. pdftotext puis
        # bascule OCR page par page) — JSON, voir log_traitement ci-dessous.
        _ensure_column(conn, "traitements", "etapes", "TEXT")
        # Accès à l'assistant conversationnel : désactivé par défaut pour
        # un nouveau compte élève, activable au cas par cas par l'admin
        # (écran "Élèves") — l'admin y a toujours accès, lui, sans ce flag
        # (voir BackEnd/app/main.py::_peut_utiliser_assistant).
        _ensure_column(conn, "eleves", "assistant_actif", "INTEGER NOT NULL DEFAULT 0")
        # Emploi du temps enrichi (voir Services/pronote_sync.py::_sync_lessons) :
        # jusqu'ici seuls date/heure/professeur/titre/description étaient
        # gardés, alors que Pronote renvoie bien plus par créneau.
        _ensure_column(conn, "cours", "salle", "TEXT")
        _ensure_column(conn, "cours", "groupe", "TEXT")
        _ensure_column(conn, "cours", "memo", "TEXT")
        # Motif d'annulation ("Classe absente"...) — `annule` (déjà existant)
        # reste le booléen simple utilisé par le reste du code/frontend.
        _ensure_column(conn, "cours", "statut", "TEXT")
        _ensure_column(conn, "cours", "devoir_surveille", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "sync_log", "nouvelles_notes", "INTEGER DEFAULT 0")
        # Connexion élève par pairage Pronote (remplace l'ancienne connexion
        # Google — voir _require_session dans BackEnd/app/main.py) : chaque
        # élève lie SON PROPRE compte Pronote, ce qui sert à la fois d'identité
        # vérifiée (établissement + classe) et de source de synchro pour son
        # propre groupe (LV2, options...). `google_sub` reste en base (colonne
        # historique, plus jamais peuplée) pour ne pas casser d'anciennes lignes.
        _ensure_column(conn, "eleves", "pronote_id", "TEXT")
        # Jeton pronotepy rotatif, chiffré au repos (voir Services/crypto_secrets.py)
        # — accès direct au compte scolaire réel d'un mineur, sensibilité bien
        # supérieure au credentials.json unique de l'admin.
        _ensure_column(conn, "eleves", "pronote_credentials", "TEXT")
        _ensure_column(conn, "eleves", "pronote_class_name", "TEXT")
        # Groupe(s) constaté(s) dans l'emploi du temps propre à CET élève
        # (LV2, options...) — pas déductible des lignes `cours` elles-mêmes
        # une fois partagées entre élèves (voir Services/pronote_sync.py::
        # _synchroniser_eleve) ; affiché sur sa fiche (écran admin Élèves).
        _ensure_column(conn, "eleves", "pronote_groupes", "TEXT")
        # Clé Gemini personnelle (écran "Profil" élève, FrontEnd/src/screens/
        # ProfilScreen.jsx) — chiffrée au repos comme pronote_credentials.
        # Utilisée en priorité sur le moteur IA choisi par l'admin pour LES
        # GÉNÉRATIONS DÉCLENCHÉES PAR CET ÉLÈVE (voir Services/ia_generation.py),
        # pour répartir la charge/le quota Gemini entre plusieurs clés
        # personnelles plutôt que tout faire peser sur celle de l'admin —
        # même principe que le pairage Pronote par élève.
        _ensure_column(conn, "eleves", "gemini_api_key", "TEXT")
        _ensure_column(conn, "eleves", "pronote_sync_statut", "TEXT")
        _ensure_column(conn, "eleves", "pronote_sync_erreur", "TEXT")
        _ensure_column(conn, "eleves", "pronote_derniere_synchro", "TEXT")
        # Horodatage du consentement explicite donné avant le pairage (voir
        # BackEnd/app/main.py::pairer_eleve_pronote) — l'élève a vu la liste
        # de ce qui sera récupéré avant de déposer son QR code.
        _ensure_column(conn, "eleves", "consentement_pronote_le", "TEXT")
        # NULL = note du compte Pronote de référence (l'admin) — jamais
        # renvoyée à un élève, seulement à l'admin (voir config_pronote /
        # l'API GET /api/matieres/{id}/notes, scopée par eleve_id).
        _ensure_column(conn, "notes_pronote", "eleve_id", "INTEGER REFERENCES eleves(id)")
        # Multi-classe (2F, 2E...) : les classes autorisées au pairage
        # deviennent une vraie liste gérable (écran admin Paramétrage),
        # remplace l'ancien paramètre `classe_attendue` (chaîne unique).
        conn.execute(
            """CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )"""
        )
        # `classe` sur cours/devoirs : contenu partagé mais propre à une
        # classe (voir Services/pronote_sync.py — dérivée de
        # `client.info.class_name` à la synchro). `matieres` reste global
        # (vocabulaire de matières commun aux classes).
        _ensure_column(conn, "cours", "classe", "TEXT")
        _ensure_column(conn, "devoirs", "classe", "TEXT")
        # Matières à exclure : masquée (invisible dans l'app) plutôt que
        # jamais importée — voir Services/pronote_sync.py (la synchro
        # ingère désormais tout, sans exception) et _migrer_matieres_
        # exclues_defaut ci-dessous pour la reprise de l'ancien réglage.
        _ensure_column(conn, "matieres", "exclue", "INTEGER NOT NULL DEFAULT 0")
        _fusionner_eleves_dupliques(conn)
        _migrer_cles_notes_pronote(conn)
        _migrer_classe_defaut(conn)
        _migrer_matieres_exclues_defaut(conn)
        conn.commit()


def _migrer_cles_notes_pronote(conn: sqlite3.Connection) -> None:
    """
    `external_key` des notes Pronote inclut désormais l'élève propriétaire
    (voir Services/pronote_sync.py::_sync_grades) — sans quoi deux élèves
    avec la même note le même jour dans la même matière se seraient vus
    confondus. Recalcule la clé des lignes déjà en base avec la nouvelle
    formule, sinon elles seraient réimportées en double au prochain sync
    (l'ancienne clé ne correspond plus à ce que _sync_grades recherche).
    Idempotent : sans effet si déjà migrée (même formule ⇒ même clé).
    """
    rows = conn.execute(
        """SELECT n.id, n.date, n.valeur, n.commentaire, n.eleve_id, m.nom AS matiere
           FROM notes_pronote n JOIN matieres m ON m.id = n.matiere_id"""
    ).fetchall()
    for r in rows:
        raw = "|".join(str(p) for p in [
            r["eleve_id"] or "reference", r["date"], r["matiere"], r["valeur"], (r["commentaire"] or "")[:60],
        ])
        nouvelle_cle = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
        conn.execute("UPDATE notes_pronote SET external_key = ? WHERE id = ?", (nouvelle_cle, r["id"]))


def _migrer_classe_defaut(conn: sqlite3.Connection) -> None:
    """
    Introduction de la classe (2F, 2E...) sur `cours`/`devoirs` (voir
    Services/pronote_sync.py) : si `classes` est encore vide et que
    l'ancien réglage `classe_attendue` (avant la vraie liste gérable
    d'aujourd'hui, écran Paramétrage) avait une valeur, l'utilise pour
    créer la première ligne dans `classes`. Puis renseigne `classe` sur
    les lignes `cours`/`devoirs` déjà en base qui ne l'ont pas encore
    (avec la première classe connue) et recalcule leur `external_key`
    avec la nouvelle formule (qui inclut désormais la classe), sinon
    elles seraient réimportées en double au prochain sync. Idempotent :
    sans effet une fois toutes les lignes migrées.
    """
    if conn.execute("SELECT 1 FROM classes LIMIT 1").fetchone() is None:
        # Retombe sur la variable d'env CLASSE_ATTENDUE si l'admin n'a
        # jamais explicitement enregistré le réglage depuis Paramétrage —
        # même ordre de repli que l'ancien `get_parametre(conn,
        # "classe_attendue", CLASSE_ATTENDUE)` remplacé par cette migration.
        ancienne = get_parametre(conn, "classe_attendue", CLASSE_ATTENDUE)
        if ancienne and ancienne.strip():
            conn.execute(
                "INSERT OR IGNORE INTO classes (nom, created_at) VALUES (?, ?)",
                (ancienne.strip(), now_iso()),
            )

    ligne = conn.execute("SELECT nom FROM classes ORDER BY id LIMIT 1").fetchone()
    if ligne is None:
        # Aucune classe connue nulle part (déploiement neuf, jamais
        # configuré) : rien à assigner aux lignes existantes, elles
        # resteront à classe NULL jusqu'au prochain sync réel.
        return
    classe_defaut = ligne["nom"]

    for c in conn.execute(
        """SELECT c.id, c.date, c.heure_debut, c.professeur, m.nom AS matiere
           FROM cours c JOIN matieres m ON m.id = c.matiere_id
           WHERE c.classe IS NULL"""
    ).fetchall():
        cle = hashlib.sha1(
            "|".join([classe_defaut, c["date"], c["heure_debut"], c["matiere"], c["professeur"] or ""]).encode("utf-8")
        ).hexdigest()[:20]
        conn.execute("UPDATE cours SET classe = ?, external_key = ? WHERE id = ?", (classe_defaut, cle, c["id"]))

    for d in conn.execute(
        """SELECT d.id, d.date_rendu, d.description, m.nom AS matiere
           FROM devoirs d JOIN matieres m ON m.id = d.matiere_id
           WHERE d.classe IS NULL"""
    ).fetchall():
        cle = hashlib.sha1(
            "|".join([classe_defaut, d["date_rendu"], d["matiere"], (d["description"] or "")[:60]]).encode("utf-8")
        ).hexdigest()[:20]
        conn.execute("UPDATE devoirs SET classe = ?, external_key = ? WHERE id = ?", (classe_defaut, cle, d["id"]))


class DerniereClasseError(Exception):
    pass


def lister_classes(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT id, nom FROM classes ORDER BY nom").fetchall()]


def ajouter_classe(conn: sqlite3.Connection, nom: str) -> int:
    nom = nom.strip()
    conn.execute(
        "INSERT INTO classes (nom, created_at) VALUES (?, ?) ON CONFLICT(nom) DO NOTHING", (nom, now_iso())
    )
    return conn.execute("SELECT id FROM classes WHERE nom = ?", (nom,)).fetchone()["id"]


def supprimer_classe(conn: sqlite3.Connection, classe_id: int) -> None:
    """
    Refuse de supprimer la dernière classe restante : une table `classes`
    vide rouvre le pairage à n'importe quelle classe (comportement de
    compatibilité documenté, voir `classes_autorisees`/`pairer_eleve_
    pronote`) — jamais voulu par accident.
    """
    total = conn.execute("SELECT COUNT(*) AS n FROM classes").fetchone()["n"]
    if total <= 1:
        raise DerniereClasseError("Impossible de supprimer la dernière classe restante.")
    conn.execute("DELETE FROM classes WHERE id = ?", (classe_id,))


def classes_autorisees(conn: sqlite3.Connection) -> set[str]:
    """Ensemble normalisé (minuscules) des classes acceptées au pairage — voir pairer_eleve_pronote."""
    return {r["nom"].strip().lower() for r in conn.execute("SELECT nom FROM classes").fetchall()}


def upsert_eleve_pronote(
    conn: sqlite3.Connection, *, pronote_id: str, nom: str, email: str, class_name: str, credentials_chiffrees: str,
) -> int:
    """
    Crée/met à jour un élève à partir d'un pairage Pronote réussi (voir
    BackEnd/app/main.py::pairer_eleve_pronote). Match par nom normalisé, PAS
    par `pronote_id` : contrairement à ce qu'indiquait cette docstring
    avant correction, `pronote_id` (ClientInfo.id) N'EST PAS stable pour un
    même compte réel — c'est un id de ressource "à usage interne" côté
    Pronote, régénéré à chaque nouvelle session/pairage (confirmé par un
    doublon réel en prod le 2026-09-13 : un même élève re-pairé a produit
    deux `pronote_id` différents, donc deux lignes `eleves`). `pronote_id`
    reste stocké à titre indicatif (dernier pairage connu) mais ne sert
    plus de clé de correspondance. Sur l'effectif d'une seule classe (36
    élèves), un homonyme est extrêmement improbable ; le cas échéant,
    l'admin peut forcer un nouveau pairage propre (bouton "Re-pairer",
    ElevesScreen). Le consentement doit déjà avoir été vérifié par
    l'appelant (ce n'est pas cette fonction qui décide) — l'horodatage ici
    sert juste de preuve, mis à jour à chaque pairage/re-pairage.
    """
    now = now_iso()
    nom_normalise = nom.strip().lower()
    row = conn.execute(
        "SELECT id FROM eleves WHERE pronote_id IS NOT NULL AND lower(trim(nom)) = ?", (nom_normalise,)
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE eleves SET nom = ?, email = ?, pronote_id = ?, pronote_class_name = ?, pronote_credentials = ?,
               pronote_sync_statut = 'actif', pronote_sync_erreur = NULL, derniere_connexion = ?,
               consentement_pronote_le = ? WHERE id = ?""",
            (nom, email, pronote_id, class_name, credentials_chiffrees, now, now, row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        """INSERT INTO eleves
           (google_sub, pronote_id, nom, email, pronote_class_name, pronote_credentials,
            pronote_sync_statut, created_at, derniere_connexion, consentement_pronote_le)
           VALUES (?, ?, ?, ?, ?, ?, 'actif', ?, ?, ?)""",
        (f"pronote:{pronote_id}", pronote_id, nom, email, class_name, credentials_chiffrees, now, now, now),
    )
    return cur.lastrowid


def _fusionner_eleves_dupliques(conn: sqlite3.Connection) -> None:
    """
    Corrige les doublons produits avant la correction ci-dessus
    d'`upsert_eleve_pronote` (constaté en prod le 2026-09-13, `pronote_id`
    non stable d'un pairage à l'autre pour un même élève réel). Regroupe
    les lignes `eleves` pairées par (nom normalisé, classe) — pas le nom
    seul : une fois plusieurs classes réelles en présence (2F, 2E...), un
    homonyme entre deux classes différentes ne doit jamais être fusionné.
    Pour chaque groupe de plus d'une ligne, garde celle synchronisée le
    plus récemment, supprime les `notes_pronote` des lignes éliminées
    (même élève réel ⇒ mêmes notes, déjà couvertes par la ligne conservée
    une fois resynchronisée), puis supprime ces lignes. Idempotent : sans
    effet si aucun doublon.
    """
    rows = conn.execute(
        """SELECT id, nom, pronote_class_name, pronote_derniere_synchro, derniere_connexion
           FROM eleves WHERE pronote_id IS NOT NULL"""
    ).fetchall()
    groupes: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for r in rows:
        cle = (r["nom"].strip().lower(), (r["pronote_class_name"] or "").strip().lower())
        groupes.setdefault(cle, []).append(r)

    for membres in groupes.values():
        if len(membres) < 2:
            continue
        membres.sort(key=lambda r: r["pronote_derniere_synchro"] or r["derniere_connexion"] or "", reverse=True)
        doublons = membres[1:]
        for d in doublons:
            conn.execute("DELETE FROM notes_pronote WHERE eleve_id = ?", (d["id"],))
            conn.execute("DELETE FROM eleves WHERE id = ?", (d["id"],))


@contextmanager
def session():
    """Context manager pratique : with db.session() as conn: ..."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def creer_traitement(conn: sqlite3.Connection, *, type: str, cible_type: str, cible_id: int) -> int:
    cur = conn.execute(
        """INSERT INTO traitements (type, cible_type, cible_id, statut, created_at)
           VALUES (?, ?, ?, 'en_cours', ?)""",
        (type, cible_type, cible_id, now_iso()),
    )
    return cur.lastrowid


def creer_demande_regeneration(conn: sqlite3.Connection, cours_id: int) -> int:
    """
    Demande de régénération en attente de validation admin (voir écran
    Traitements → onglet "En attente") — pas un vrai traitement en cours,
    juste une ligne d'attente réutilisant la même table (mêmes colonnes,
    même écran de suivi) : statut 'en_attente', complétée en 'validee' ou
    'rejetee' par BackEnd/app/main.py, jamais par `log_traitement`.
    """
    cur = conn.execute(
        """INSERT INTO traitements (type, cible_type, cible_id, statut, created_at)
           VALUES ('regeneration_demande', 'cours', ?, 'en_attente', ?)""",
        (cours_id, now_iso()),
    )
    return cur.lastrowid


def terminer_traitement(
    conn: sqlite3.Connection, traitement_id: int, *, statut: str, moteur: str | None,
    resultat: str | None, erreur: str | None, duree_ms: int, etapes: str | None = None,
) -> None:
    conn.execute(
        """UPDATE traitements
           SET statut = ?, moteur = ?, resultat = ?, erreur = ?, duree_ms = ?, etapes = ?, finished_at = ?
           WHERE id = ?""",
        (statut, moteur, resultat, erreur, duree_ms, etapes, now_iso(), traitement_id),
    )


@contextmanager
def log_traitement(type_: str, cible_type: str, cible_id: int, *, traitement_id: int | None = None):
    """
    Context manager partagé par tous les producteurs de `traitements`
    (OCR, génération IA, synchro Pronote) : crée une ligne au début du
    bloc, la complète (succès/échec, durée, étapes) à la fin — quoi qu'il
    arrive. Le code appelant doit renseigner `ctx.moteur` et `ctx.resultat`
    avant la fin du bloc `with`, et peut journaliser des étapes
    intermédiaires via `ctx.etape(label, ...)` (ex. "pdftotext" puis
    "ocr page 1/3") — visibles dans l'écran admin même si le traitement
    échoue en cours de route, pour comprendre jusqu'où il est allé.
    `ctx.etape(..., resultat=...)` attache en plus un contenu (ex. le
    texte source lu pour cette étape), rendu comme `ctx.resultat` côté
    frontend — utile pour vérifier ce qui a réellement été envoyé au
    modèle, pas juste sa longueur.

    `traitement_id` : passe une ligne déjà créée (typiquement par l'API,
    avant de lancer le travail en arrière-plan) plutôt que d'en créer une
    nouvelle — utilisé par le déclenchement manuel de synchro Pronote pour
    renvoyer immédiatement l'id au frontend et lui permettre d'ouvrir le
    suivi sans deviner/rafraîchir la liste.
    """
    import json as _json
    import time

    class _Ctx:
        def __init__(self):
            self.moteur = None
            self.resultat = None
            self.etapes = []

        def etape(self, label: str, *, statut: str = "succes", detail: str | None = None,
                   duree_ms: int | None = None, moteur: str | None = None, resultat: str | None = None) -> None:
            self.etapes.append({
                "label": label, "statut": statut, "detail": detail,
                "duree_ms": duree_ms, "moteur": moteur, "resultat": resultat,
            })

    ctx = _Ctx()
    if traitement_id is None:
        with session() as conn:
            traitement_id = creer_traitement(conn, type=type_, cible_type=cible_type, cible_id=cible_id)

    debut = time.monotonic()
    try:
        yield ctx
    except Exception as e:  # noqa: BLE001 — on journalise puis on relance pour l'appelant
        with session() as conn:
            terminer_traitement(
                conn, traitement_id, statut="echec", moteur=ctx.moteur, resultat=ctx.resultat,
                erreur=str(e), duree_ms=int((time.monotonic() - debut) * 1000),
                etapes=_json.dumps(ctx.etapes, ensure_ascii=False) if ctx.etapes else None,
            )
        raise
    else:
        with session() as conn:
            terminer_traitement(
                conn, traitement_id, statut="succes", moteur=ctx.moteur, resultat=ctx.resultat,
                erreur=None, duree_ms=int((time.monotonic() - debut) * 1000),
                etapes=_json.dumps(ctx.etapes, ensure_ascii=False) if ctx.etapes else None,
            )


def get_parametre(conn: sqlite3.Connection, cle: str, defaut: str | None = None) -> str | None:
    row = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return row["valeur"] if row is not None else defaut


def set_parametre(conn: sqlite3.Connection, cle: str, valeur: str) -> None:
    conn.execute(
        "INSERT INTO parametres (cle, valeur) VALUES (?, ?) "
        "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
        (cle, valeur),
    )


def _slug_matiere(nom: str) -> str:
    return (
        nom.lower()
        .replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("à", "a").replace("î", "i").replace("ô", "o")
        .replace("ç", "c").replace(" ", "-").replace("'", "-")
    )


def upsert_matiere(conn: sqlite3.Connection, nom: str) -> int:
    row = conn.execute("SELECT id FROM matieres WHERE nom = ?", (nom,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO matieres (nom, slug) VALUES (?, ?)", (nom, _slug_matiere(nom))
    )
    return cur.lastrowid


def _migrer_matieres_exclues_defaut(conn: sqlite3.Connection) -> None:
    """
    Ancien réglage `matieres_exclues` (noms tapés à la main, comparés par
    slug pour NE PAS importer certains créneaux au sync — voir Services/
    pronote_sync.py) remplacé par une case à cocher par matière déjà
    connue (écran Paramétrage), qui masque plutôt que d'empêcher l'import.
    Migre une seule fois (marqueur `_migration_matieres_exclues_faite`) :
    reprend l'ancienne liste pour cocher `exclue` sur les matières déjà en
    base qui y correspondent, puis n'y touche plus JAMAIS — sans ce
    garde-fou, un décochage manuel plus tard serait défait à chaque
    redémarrage tant que l'ancien réglage reste en base.
    """
    if get_parametre(conn, "_migration_matieres_exclues_faite") == "1":
        return
    set_parametre(conn, "_migration_matieres_exclues_faite", "1")
    ancienne = get_parametre(conn, "matieres_exclues") or ""
    slugs_exclus = {_slug_matiere(nom.strip()) for nom in ancienne.split(",") if nom.strip()}
    if not slugs_exclus:
        return
    for r in conn.execute("SELECT id, slug FROM matieres").fetchall():
        if r["slug"] in slugs_exclus:
            conn.execute("UPDATE matieres SET exclue = 1 WHERE id = ?", (r["id"],))
