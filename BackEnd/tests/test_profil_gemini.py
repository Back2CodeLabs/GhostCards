"""
Profil élève (identité en lecture seule + clé Gemini personnelle) : la clé
ne doit jamais être renvoyée en clair au frontend, et doit primer sur le
moteur IA choisi par l'admin pour les générations de CET élève (voir
Services/ia_generation.py::_avec_cle_gemini_perso).
"""
from unittest.mock import patch

from Services import crypto_secrets, db, ia_generation
from conftest import fake_pronote_client


def _pairer(client, *, classe="2F", nom="Élève Test"):
    import json

    payload = {
        "qr_json": json.dumps({"url": "https://demo.index-education.net/pronote/eleve.html"}),
        "pin": "1234",
        "consentement": "true",
    }
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name=classe, nom=nom)):
        resp = client.post("/api/eleves/pairage", data=payload)
    assert resp.status_code == 200, resp.text


def test_profil_ne_renvoie_jamais_la_cle_en_clair(client):
    _pairer(client)
    client.put("/api/profil/gemini-cle", json={"cle": "AIzaSy-vraie-cle-secrete"})

    resp = client.get("/api/profil").json()
    assert resp["gemini_cle_definie"] is True
    assert "AIzaSy-vraie-cle-secrete" not in str(resp)


def test_profil_sans_cle_definie(client):
    _pairer(client)
    resp = client.get("/api/profil").json()
    assert resp["gemini_cle_definie"] is False
    assert resp["classe"] == "2F"


def test_definir_puis_effacer_la_cle(client):
    _pairer(client)
    client.put("/api/profil/gemini-cle", json={"cle": "une-cle"})
    assert client.get("/api/profil").json()["gemini_cle_definie"] is True

    client.put("/api/profil/gemini-cle", json={"cle": ""})
    assert client.get("/api/profil").json()["gemini_cle_definie"] is False


def test_profil_reserve_aux_eleves(client):
    resp = client.get("/api/profil")
    assert resp.status_code == 403

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.get("/api/profil")
    assert resp.status_code == 403


def test_cle_gemini_perso_prime_sur_le_moteur_global(conn, cle_chiffrement):
    conn.execute(
        """INSERT INTO eleves (google_sub, pronote_id, nom, email, gemini_api_key, created_at, derniere_connexion)
           VALUES ('pronote:x', 'x', 'Élève X', '', ?, ?, ?)""",
        (crypto_secrets.chiffrer_json({"cle": "ma-cle-perso"}), db.now_iso(), db.now_iso()),
    )
    conn.commit()
    eleve_id = conn.execute("SELECT id FROM eleves WHERE nom = 'Élève X'").fetchone()["id"]

    cfg = ia_generation._avec_cle_gemini_perso(conn, {"moteur": "ollama"}, eleve_id)
    assert cfg["moteur"] == "gemini"
    assert cfg["gemini_api_key"] == "ma-cle-perso"


def test_pas_de_cle_perso_garde_le_moteur_global(conn):
    conn.execute(
        """INSERT INTO eleves (google_sub, pronote_id, nom, email, created_at, derniere_connexion)
           VALUES ('pronote:y', 'y', 'Élève Y', '', ?, ?)""",
        (db.now_iso(), db.now_iso()),
    )
    conn.commit()
    eleve_id = conn.execute("SELECT id FROM eleves WHERE nom = 'Élève Y'").fetchone()["id"]

    cfg = ia_generation._avec_cle_gemini_perso(conn, {"moteur": "ollama"}, eleve_id)
    assert cfg == {"moteur": "ollama"}


def test_admin_n_est_jamais_affecte_par_une_cle_perso():
    cfg = ia_generation._avec_cle_gemini_perso(None, {"moteur": "ollama"}, None)
    assert cfg == {"moteur": "ollama"}


def test_cle_perso_illisible_retombe_sur_le_moteur_global(conn, monkeypatch):
    """
    Clé de chiffrement du serveur changée depuis, ou ligne corrompue : ne
    doit jamais faire échouer la génération, juste retomber sur le moteur
    global comme si l'élève n'avait pas de clé personnelle.
    """
    conn.execute(
        """INSERT INTO eleves (google_sub, pronote_id, nom, email, gemini_api_key, created_at, derniere_connexion)
           VALUES ('pronote:z', 'z', 'Élève Z', '', 'blob-illisible', ?, ?)""",
        (db.now_iso(), db.now_iso()),
    )
    conn.commit()
    eleve_id = conn.execute("SELECT id FROM eleves WHERE nom = 'Élève Z'").fetchone()["id"]

    cfg = ia_generation._avec_cle_gemini_perso(conn, {"moteur": "ollama"}, eleve_id)
    assert cfg == {"moteur": "ollama"}
