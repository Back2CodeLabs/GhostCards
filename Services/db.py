"""
Accès à la base de données locale (SQLite).

SQLite a été choisi volontairement plutôt que Postgres/MySQL : Ghost School
tourne sur une seule machine (l'OptiPlex), donc pas besoin d'un serveur de
base de données séparé à installer, sauvegarder et surveiller. Le mode WAL
permet de lire pendant qu'une synchronisation écrit, sans verrouillage.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

from .config import DB_PATH

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
        _ensure_column(conn, "eleves", "pronote_sync_statut", "TEXT")
        _ensure_column(conn, "eleves", "pronote_sync_erreur", "TEXT")
        _ensure_column(conn, "eleves", "pronote_derniere_synchro", "TEXT")
        # NULL = note du compte Pronote de référence (l'admin) — jamais
        # renvoyée à un élève, seulement à l'admin (voir config_pronote /
        # l'API GET /api/matieres/{id}/notes, scopée par eleve_id).
        _ensure_column(conn, "notes_pronote", "eleve_id", "INTEGER REFERENCES eleves(id)")
        conn.commit()


def upsert_eleve_pronote(
    conn: sqlite3.Connection, *, pronote_id: str, nom: str, email: str, class_name: str, credentials_chiffrees: str,
) -> int:
    """
    Crée/met à jour un élève à partir d'un pairage Pronote réussi (voir
    BackEnd/app/main.py::pairer_eleve_pronote) — `pronote_id` (ClientInfo.id,
    stable pour un même compte réel) joue le rôle que `google_sub` jouait
    pour l'ancienne connexion Google.
    """
    now = now_iso()
    row = conn.execute("SELECT id FROM eleves WHERE pronote_id = ?", (pronote_id,)).fetchone()
    if row:
        conn.execute(
            """UPDATE eleves SET nom = ?, email = ?, pronote_class_name = ?, pronote_credentials = ?,
               pronote_sync_statut = 'actif', pronote_sync_erreur = NULL, derniere_connexion = ? WHERE id = ?""",
            (nom, email, class_name, credentials_chiffrees, now, row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        """INSERT INTO eleves
           (google_sub, pronote_id, nom, email, pronote_class_name, pronote_credentials,
            pronote_sync_statut, created_at, derniere_connexion)
           VALUES (?, ?, ?, ?, ?, ?, 'actif', ?, ?)""",
        (f"pronote:{pronote_id}", pronote_id, nom, email, class_name, credentials_chiffrees, now, now),
    )
    return cur.lastrowid


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


def upsert_matiere(conn: sqlite3.Connection, nom: str) -> int:
    slug = (
        nom.lower()
        .replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("à", "a").replace("î", "i").replace("ô", "o")
        .replace("ç", "c").replace(" ", "-").replace("'", "-")
    )
    row = conn.execute("SELECT id FROM matieres WHERE nom = ?", (nom,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO matieres (nom, slug) VALUES (?, ?)", (nom, slug)
    )
    return cur.lastrowid
