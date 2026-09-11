"""
Remet la base et les fichiers à zéro, sans toucher aux réglages (table
`parametres` : moteur IA, exclusions Pronote, etc.) ni au jeton de connexion
Pronote (`secrets/credentials.json`, géré à part — voir README).

Vide : cours, devoirs, notes_pronote, matieres, documents (lignes + fichiers
sur disque sous data/documents/), notes_eleves, eleves, traitements,
sync_log. Pense à faire une copie de `ghostcards.db` avant si tu veux
pouvoir revenir en arrière — cette action est irréversible.

Usage (depuis la racine GhostCards/, venv de BackEnd/ activé) :
    python3 -m Services.scripts.reinitialiser_donnees            # aperçu seulement
    python3 -m Services.scripts.reinitialiser_donnees --confirmer
"""
import argparse
import shutil
import sys

from Services import db
from Services.config import DOCUMENTS_DIR

# Ordre important : tables filles avant tables parentes, pour rester
# cohérent même si une contrainte de clé étrangère n'était pas en CASCADE.
TABLES = [
    "documents", "notes_eleves", "traitements", "sync_log",
    "cours", "devoirs", "notes_pronote", "matieres", "eleves",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Remet à zéro toutes les données (sauf les réglages) de Ghost School")
    parser.add_argument("--confirmer", action="store_true", help="Sans cette option, affiche seulement ce qui serait supprimé")
    args = parser.parse_args()

    db.init_db()
    with db.session() as conn:
        comptes = {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in TABLES}

        for t, n in comptes.items():
            print(f"{'[VIDÉ]' if args.confirmer else '[à vider]'} {t} — {n} ligne(s)")
        nb_fichiers = sum(1 for p in DOCUMENTS_DIR.rglob("*") if p.is_file()) if DOCUMENTS_DIR.exists() else 0
        print(f"{'[SUPPRIMÉS]' if args.confirmer else '[à supprimer]'} fichiers sous {DOCUMENTS_DIR} — {nb_fichiers} fichier(s)")

        if not args.confirmer:
            print("\nAucune suppression effectuée (aperçu). Relance avec --confirmer pour appliquer.")
            return 0

        for t in TABLES:
            conn.execute(f"DELETE FROM {t}")
            conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (t,))

    if DOCUMENTS_DIR.exists():
        shutil.rmtree(DOCUMENTS_DIR)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nTerminé. Les réglages (Paramétrage) et le jeton Pronote sont intacts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
