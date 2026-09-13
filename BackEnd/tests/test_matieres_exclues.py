"""
Matières à exclure (redesign) : masquer une matière déjà récupérée (case à
cocher) plutôt que de l'empêcher d'être synchronisée. Garde-fous sur la
migration depuis l'ancien réglage texte, et sur le fait qu'un décochage
manuel ne doit jamais être défait par un redémarrage (voir HANDOFF.md).
"""
from Services import db


def test_migration_reprend_l_ancien_reglage_texte(db_path):
    """
    Simule une vraie base d'avant le redesign : réglage `matieres_exclues`
    déjà en place (ancien champ texte à virgules), matières déjà connues.
    `init_db()` doit cocher `exclue` sur celles qui correspondent, sans
    toucher aux autres.
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO parametres (cle, valeur) VALUES ('matieres_exclues', 'Éducation Physique, Vie de classe')")
    conn.execute("INSERT INTO matieres (nom, slug) VALUES ('EDUCATION PHYSIQUE', 'education-physique')")
    conn.execute("INSERT INTO matieres (nom, slug) VALUES ('VIE DE CLASSE', 'vie-de-classe')")
    conn.execute("INSERT INTO matieres (nom, slug) VALUES ('MATHEMATIQUES', 'mathematiques')")
    conn.commit()
    conn.close()

    db.init_db()

    with db.session() as conn:
        rows = {r["nom"]: r["exclue"] for r in conn.execute("SELECT nom, exclue FROM matieres").fetchall()}
    assert rows["EDUCATION PHYSIQUE"] == 1
    assert rows["VIE DE CLASSE"] == 1
    assert rows["MATHEMATIQUES"] == 0


def test_migration_ne_s_applique_qu_une_seule_fois(db_path):
    """
    Un décochage manuel plus tard ne doit jamais être défait au prochain
    redémarrage — sans le marqueur one-shot, la migration réappliquerait
    l'ancien réglage texte (toujours en base) à chaque `init_db()`.
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO parametres (cle, valeur) VALUES ('matieres_exclues', 'Vie de classe')")
    conn.execute("INSERT INTO matieres (nom, slug) VALUES ('VIE DE CLASSE', 'vie-de-classe')")
    conn.commit()
    conn.close()

    db.init_db()
    with db.session() as conn:
        matiere_id = conn.execute("SELECT id FROM matieres WHERE nom = 'VIE DE CLASSE'").fetchone()["id"]
        conn.execute("UPDATE matieres SET exclue = 0 WHERE id = ?", (matiere_id,))

    db.init_db()
    with db.session() as conn:
        exclue = conn.execute("SELECT exclue FROM matieres WHERE nom = 'VIE DE CLASSE'").fetchone()["exclue"]
    assert exclue == 0


def test_pas_d_ancien_reglage_ne_change_rien(conn):
    """Base neuve, jamais de `matieres_exclues` : aucune matière marquée exclue."""
    db.upsert_matiere(conn, "MATHEMATIQUES")
    conn.commit()
    db.init_db()
    with db.session() as conn2:
        assert conn2.execute("SELECT exclue FROM matieres").fetchone()["exclue"] == 0


def test_matiere_exclue_masquee_de_list_matieres_mais_visible_en_admin(client):
    with db.session() as conn:
        matiere_id = db.upsert_matiere(conn, "VIE DE CLASSE")
        conn.execute("UPDATE matieres SET exclue = 1 WHERE id = ?", (matiere_id,))
        db.upsert_matiere(conn, "MATHEMATIQUES")

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})

    visibles = client.get("/api/matieres").json()
    assert [m["nom"] for m in visibles] == ["MATHEMATIQUES"]

    toutes = client.get("/api/parametres/matieres").json()
    assert {m["nom"] for m in toutes} == {"VIE DE CLASSE", "MATHEMATIQUES"}
    assert next(m for m in toutes if m["nom"] == "VIE DE CLASSE")["exclue"] == 1


def test_toggle_endpoint_masque_et_demasque(client):
    with db.session() as conn:
        matiere_id = db.upsert_matiere(conn, "MATHEMATIQUES")

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})

    resp = client.put(f"/api/matieres/{matiere_id}/exclure", json={"exclue": True})
    assert resp.status_code == 200
    assert client.get("/api/matieres").json() == []

    resp = client.put(f"/api/matieres/{matiere_id}/exclure", json={"exclue": False})
    assert resp.status_code == 200
    assert [m["nom"] for m in client.get("/api/matieres").json()] == ["MATHEMATIQUES"]


def test_toggle_endpoint_404_si_matiere_inconnue(client):
    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.put("/api/matieres/999/exclure", json={"exclue": True})
    assert resp.status_code == 404


def test_toggle_endpoint_reserve_a_l_admin(client):
    resp = client.put("/api/matieres/1/exclure", json={"exclue": True})
    assert resp.status_code == 403
