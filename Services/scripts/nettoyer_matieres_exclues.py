"""
Supprime de la base les matières déjà synchronisées avant qu'elles ne
soient ajoutées à la liste "Matières à exclure" (écran admin Paramétrage) —
la synchro elle-même n'en importe plus de nouvelles depuis leur ajout à
cette liste, mais ne retire jamais rétroactivement ce qui existait déjà.

Supprime, pour chaque matière exclue : ses cours (et documents attachés,
via ON DELETE CASCADE), ses devoirs, ses notes, puis la matière elle-même
si elle ne contient plus rien.

Usage (depuis la racine GhostCards/, venv de BackEnd/ activé) :
    python3 -m Services.scripts.nettoyer_matieres_exclues           # aperçu seulement
    python3 -m Services.scripts.nettoyer_matieres_exclues --confirmer
"""
import argparse
import sys

from Services import db
from Services.pronote_sync import _slugify


def main() -> int:
    parser = argparse.ArgumentParser(description="Nettoie les matières déjà présentes en base et listées comme exclues")
    parser.add_argument("--confirmer", action="store_true", help="Sans cette option, affiche seulement ce qui serait supprimé")
    args = parser.parse_args()

    db.init_db()
    with db.session() as conn:
        exclues_brut = db.get_parametre(
            conn, "matieres_exclues", "Réunion parents-profs, Journée du sport scolaire"
        ) or ""
        slugs_exclus = {_slugify(nom) for nom in exclues_brut.split(",") if nom.strip()}
        if not slugs_exclus:
            print("Aucune matière exclue configurée (écran admin Paramétrage) — rien à faire.")
            return 0

        matieres = conn.execute("SELECT id, nom FROM matieres").fetchall()
        a_supprimer = [m for m in matieres if _slugify(m["nom"]) in slugs_exclus]

        if not a_supprimer:
            print("Aucune matière en base ne correspond à la liste d'exclusion — rien à nettoyer.")
            return 0

        for m in a_supprimer:
            nb_cours = conn.execute("SELECT COUNT(*) AS n FROM cours WHERE matiere_id = ?", (m["id"],)).fetchone()["n"]
            nb_devoirs = conn.execute("SELECT COUNT(*) AS n FROM devoirs WHERE matiere_id = ?", (m["id"],)).fetchone()["n"]
            nb_notes = conn.execute("SELECT COUNT(*) AS n FROM notes_pronote WHERE matiere_id = ?", (m["id"],)).fetchone()["n"]
            print(f"{'[SUPPRIMÉ]' if args.confirmer else '[à supprimer]'} {m['nom']!r} — {nb_cours} cours, {nb_devoirs} devoirs, {nb_notes} notes")

        if not args.confirmer:
            print("\nAucune suppression effectuée (aperçu). Relance avec --confirmer pour appliquer.")
            return 0

        for m in a_supprimer:
            conn.execute("DELETE FROM cours WHERE matiere_id = ?", (m["id"],))
            conn.execute("DELETE FROM devoirs WHERE matiere_id = ?", (m["id"],))
            conn.execute("DELETE FROM notes_pronote WHERE matiere_id = ?", (m["id"],))
            conn.execute("DELETE FROM matieres WHERE id = ?", (m["id"],))
        print("\nTerminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
