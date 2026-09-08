"""
Accès à la base de données locale (SQLite).

SQLite a été choisi volontairement plutôt que Postgres/MySQL : Ghost Cards
tourne sur une seule machine (l'OptiPlex), donc pas besoin d'un serveur de
base de données séparé à installer, sauvegarder et surveiller. Le mode WAL
permet de lire pendant qu'une synchronisation écrit, sans verrouillage.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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
        _ensure_column(conn, "eleves", "role", "TEXT NOT NULL DEFAULT 'eleve'")
        _ensure_column(conn, "notes_eleves", "statut", "TEXT NOT NULL DEFAULT 'pret'")
        _ensure_column(conn, "documents", "texte_extrait", "TEXT")
        conn.commit()


def upsert_eleve(conn: sqlite3.Connection, *, google_sub: str, email: str, nom: str, avatar_url: str | None) -> int:
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    row = conn.execute("SELECT id FROM eleves WHERE google_sub = ?", (google_sub,)).fetchone()
    if row:
        conn.execute(
            "UPDATE eleves SET email = ?, nom = ?, avatar_url = ?, derniere_connexion = ? WHERE id = ?",
            (email, nom, avatar_url, now, row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        "INSERT INTO eleves (google_sub, email, nom, avatar_url, created_at, derniere_connexion) VALUES (?, ?, ?, ?, ?, ?)",
        (google_sub, email, nom, avatar_url, now, now),
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
    from datetime import datetime

    cur = conn.execute(
        """INSERT INTO traitements (type, cible_type, cible_id, statut, created_at)
           VALUES (?, ?, ?, 'en_cours', ?)""",
        (type, cible_type, cible_id, datetime.now().isoformat(timespec="seconds")),
    )
    return cur.lastrowid


def terminer_traitement(
    conn: sqlite3.Connection, traitement_id: int, *, statut: str, moteur: str | None,
    resultat: str | None, erreur: str | None, duree_ms: int,
) -> None:
    from datetime import datetime

    conn.execute(
        """UPDATE traitements
           SET statut = ?, moteur = ?, resultat = ?, erreur = ?, duree_ms = ?, finished_at = ?
           WHERE id = ?""",
        (statut, moteur, resultat, erreur, duree_ms, datetime.now().isoformat(timespec="seconds"), traitement_id),
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
