"""
Support de plusieurs classes (2F, 2E...) : garde-fous de non-régression sur
les trois risques identifiés en mode plan avant ce chantier (voir HANDOFF.md)
— collision de déduplication entre classes, fuite de contenu d'une classe à
l'autre, et migration correcte des données déjà en base avant le passage au
multi-classe.
"""
import hashlib
from unittest.mock import patch

import pytest

from Services import db, pronote_sync
from conftest import fake_pronote_client


def _cle_cours(classe: str, date: str, heure: str, matiere: str, prof: str) -> str:
    return hashlib.sha1(f"{classe}|{date}|{heure}|{matiere}|{prof}".encode("utf-8")).hexdigest()[:20]


def test_stable_key_differe_selon_la_classe():
    """
    Deux cours identiques en date/heure/matière/professeur mais de classes
    différentes ne doivent JAMAIS produire la même clé — sans quoi le
    second serait pris pour "déjà connu" et fusionné à tort avec le premier
    (le bug que ce chantier a corrigé, voir HANDOFF.md).
    """
    cle_2f = pronote_sync._stable_key("2F", "2026-09-14", "08:00", "MATHEMATIQUES", "Mme Martin")
    cle_2e = pronote_sync._stable_key("2E", "2026-09-14", "08:00", "MATHEMATIQUES", "Mme Martin")
    assert cle_2f != cle_2e


def test_stable_key_identique_si_tout_identique():
    a = pronote_sync._stable_key("2F", "2026-09-14", "08:00", "MATHEMATIQUES", "Mme Martin")
    b = pronote_sync._stable_key("2F", "2026-09-14", "08:00", "MATHEMATIQUES", "Mme Martin")
    assert a == b


def test_classes_crud(conn):
    id_2f = db.ajouter_classe(conn, "2F")
    id_2e = db.ajouter_classe(conn, "2E")
    conn.commit()

    noms = {c["nom"] for c in db.lister_classes(conn)}
    assert noms == {"2F", "2E"}

    db.supprimer_classe(conn, id_2f)
    conn.commit()
    assert {c["nom"] for c in db.lister_classes(conn)} == {"2E"}

    with pytest.raises(db.DerniereClasseError):
        db.supprimer_classe(conn, id_2e)


def test_ajouter_classe_est_idempotent(conn):
    """`ON CONFLICT DO NOTHING` : ajouter deux fois le même nom ne crée pas de doublon."""
    id_a = db.ajouter_classe(conn, "2F")
    id_b = db.ajouter_classe(conn, "2F")
    conn.commit()
    assert id_a == id_b
    assert len(db.lister_classes(conn)) == 1


def test_classes_autorisees_normalise_casse_et_espaces(conn):
    db.ajouter_classe(conn, "2F")
    conn.commit()
    assert db.classes_autorisees(conn) == {"2f"}


def test_migration_classe_defaut_backfille_les_lignes_existantes(db_path):
    """
    Simule une vraie base d'avant le multi-classe : `classe_attendue` déjà
    réglé, des lignes `cours`/`devoirs` déjà en place avec une classe NULL et
    une external_key à l'ancienne formule (sans classe). `init_db()` doit,
    en une seule migration, créer la classe par défaut ET retagger ces
    lignes avec la nouvelle formule de clé — sans quoi elles seraient
    réimportées en double au prochain sync.
    """
    import sqlite3

    # Construit la base "à la main" (comme un vrai fichier pré-existant),
    # SANS jamais appeler init_db() avant d'avoir posé l'ancien réglage —
    # sinon la migration se marquerait "déjà faite" avant même d'avoir eu
    # de classe_attendue à reprendre (piège rencontré une première fois
    # pendant le développement, voir HANDOFF.md).
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO parametres (cle, valeur) VALUES ('classe_attendue', '2F')")
    conn.execute("INSERT INTO matieres (nom, slug) VALUES ('MATHEMATIQUES', 'mathematiques')")
    ancienne_cle = hashlib.sha1("2026-09-14T08:00:00|MATHEMATIQUES|Mme Martin".encode("utf-8")).hexdigest()[:20]
    conn.execute(
        """INSERT INTO cours (external_key, matiere_id, date, heure_debut, professeur, created_at, updated_at)
           VALUES (?, 1, '2026-09-14', '08:00', 'Mme Martin', '2026-09-01T00:00:00', '2026-09-01T00:00:00')""",
        (ancienne_cle,),
    )
    conn.commit()
    conn.close()

    db.init_db()

    with db.session() as conn:
        classes = db.lister_classes(conn)
        assert [c["nom"] for c in classes] == ["2F"]

        cours = conn.execute("SELECT classe, external_key FROM cours").fetchone()
        assert cours["classe"] == "2F"
        assert cours["external_key"] == _cle_cours("2F", "2026-09-14", "08:00", "MATHEMATIQUES", "Mme Martin")
        assert cours["external_key"] != ancienne_cle


def test_migration_classe_defaut_est_idempotente(db_path):
    """Un second `init_db()` (redémarrage du service) ne doit rien changer de plus."""
    db.init_db()
    with db.session() as conn:
        db.ajouter_classe(conn, "2F")

    db.init_db()
    with db.session() as conn:
        assert [c["nom"] for c in db.lister_classes(conn)] == ["2F"]


def _pairer_eleve(client, *, classe: str, nom: str, pronote_id: str):
    import json

    payload = {
        "qr_json": json.dumps({"url": "https://demo.index-education.net/pronote/eleve.html"}),
        "pin": "1234",
        "consentement": "true",
    }
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name=classe, nom=nom, pronote_id=pronote_id)):
        resp = client.post("/api/eleves/pairage", data=payload)
    assert resp.status_code == 200, resp.text


def _seed_cours(conn, *, classe: str, matiere: str, date: str = "2026-09-14"):
    matiere_id = db.upsert_matiere(conn, matiere)
    cle = pronote_sync._stable_key(classe, date, "08:00", matiere, "Mme Martin")
    conn.execute(
        """INSERT INTO cours (external_key, matiere_id, date, heure_debut, professeur, classe, created_at, updated_at)
           VALUES (?, ?, ?, '08:00', 'Mme Martin', ?, ?, ?)""",
        (cle, matiere_id, date, classe, db.now_iso(), db.now_iso()),
    )


def test_eleve_ne_voit_que_le_contenu_de_sa_classe(client):
    with db.session() as conn:
        _seed_cours(conn, classe="2F", matiere="MATHEMATIQUES")
        _seed_cours(conn, classe="2E", matiere="ANGLAIS")

    _pairer_eleve(client, classe="2F", nom="Eleve 2F", pronote_id="p1")
    matieres = client.get("/api/matieres").json()
    assert [m["nom"] for m in matieres] == ["MATHEMATIQUES"]


def test_admin_voit_les_classes_melangees_par_defaut(client):
    with db.session() as conn:
        _seed_cours(conn, classe="2F", matiere="MATHEMATIQUES")
        _seed_cours(conn, classe="2E", matiere="ANGLAIS")

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    matieres = client.get("/api/matieres").json()
    assert {m["nom"] for m in matieres} == {"MATHEMATIQUES", "ANGLAIS"}


def test_admin_peut_filtrer_par_classe(client):
    with db.session() as conn:
        _seed_cours(conn, classe="2F", matiere="MATHEMATIQUES")
        _seed_cours(conn, classe="2E", matiere="ANGLAIS")

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    matieres = client.get("/api/matieres", params={"classe": "2E"}).json()
    assert [m["nom"] for m in matieres] == ["ANGLAIS"]


def test_eleve_ne_peut_pas_ouvrir_un_cours_d_une_autre_classe(client):
    with db.session() as conn:
        _seed_cours(conn, classe="2F", matiere="MATHEMATIQUES")
        _seed_cours(conn, classe="2E", matiere="ANGLAIS")
        cours_2e_id = conn.execute(
            "SELECT c.id FROM cours c JOIN matieres m ON m.id = c.matiere_id WHERE m.nom = 'ANGLAIS'"
        ).fetchone()["id"]

    _pairer_eleve(client, classe="2F", nom="Eleve 2F", pronote_id="p1")
    resp = client.get(f"/api/cours/{cours_2e_id}")
    assert resp.status_code == 403


def test_eleve_peut_ouvrir_un_cours_de_sa_propre_classe(client):
    with db.session() as conn:
        _seed_cours(conn, classe="2F", matiere="MATHEMATIQUES")
        cours_id = conn.execute("SELECT id FROM cours").fetchone()["id"]

    _pairer_eleve(client, classe="2F", nom="Eleve 2F", pronote_id="p1")
    resp = client.get(f"/api/cours/{cours_id}")
    assert resp.status_code == 200


def test_fusion_doublons_ne_fusionne_pas_deux_homonymes_de_classes_differentes(conn):
    """
    `_fusionner_eleves_dupliques` groupe par (nom, classe) — un homonyme
    entre deux classes différentes ne doit jamais être fusionné à tort.
    """
    now = db.now_iso()
    conn.execute(
        """INSERT INTO eleves (google_sub, pronote_id, nom, email, pronote_class_name, created_at, derniere_connexion)
           VALUES ('pronote:a', 'a', 'Alex Martin', '', '2F', ?, ?)""",
        (now, now),
    )
    conn.execute(
        """INSERT INTO eleves (google_sub, pronote_id, nom, email, pronote_class_name, created_at, derniere_connexion)
           VALUES ('pronote:b', 'b', 'Alex Martin', '', '2E', ?, ?)""",
        (now, now),
    )
    conn.commit()

    db._fusionner_eleves_dupliques(conn)
    conn.commit()

    lignes = conn.execute("SELECT pronote_class_name FROM eleves WHERE nom = 'Alex Martin'").fetchall()
    assert {r["pronote_class_name"] for r in lignes} == {"2F", "2E"}
