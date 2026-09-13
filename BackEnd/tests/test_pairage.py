"""
Pairage Pronote (connexion élève) : point d'entrée le plus sensible de
l'app — accès direct à un vrai compte scolaire de mineur. Chaque échec doit
remonter un message clair en français, jamais une exception Pronote brute
ni une 500 muette (voir HANDOFF.md, section pairage, pour l'historique de
ces corrections).
"""
import json
from unittest.mock import patch

import pronotepy

from conftest import fake_pronote_client

PRONOTE_URL = "https://demo.index-education.net/pronote/eleve.html"


def _qr_json(url: str = PRONOTE_URL) -> str:
    return json.dumps({"jeton": "abc123", "login": "xyz", "url": url})


def _pairer(client, **overrides):
    payload = {"qr_json": _qr_json(), "pin": "1234", "consentement": "true"}
    payload.update(overrides)
    return client.post("/api/eleves/pairage", data=payload)


def test_consentement_obligatoire(client):
    resp = _pairer(client, consentement="false")
    assert resp.status_code == 400
    assert "consentement" in resp.json()["detail"].lower()


def test_domaine_qr_different_refuse(client):
    resp = _pairer(client, qr_json=_qr_json(url="https://autre-etablissement.index-education.net/pronote/eleve.html"))
    assert resp.status_code == 403
    assert "établissement" in resp.json()["detail"].lower()


def test_qr_json_illisible_refuse(client):
    resp = _pairer(client, qr_json="ceci n'est pas du JSON")
    assert resp.status_code == 400


def test_pin_incorrect_message_clair_en_francais(client):
    with patch("pronotepy.Client.qrcode_login", side_effect=pronotepy.QRCodeDecryptError("invalid confirmation code")):
        resp = _pairer(client)
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert "pin" in detail.lower()
    assert "invalid confirmation code" not in detail


def test_erreur_generique_ne_fuit_pas_le_detail_technique(client):
    with patch("pronotepy.Client.qrcode_login", side_effect=RuntimeError("timeout réseau interne xyz")):
        resp = _pairer(client)
    assert resp.status_code == 401
    assert "timeout réseau interne xyz" not in resp.json()["detail"]


def test_pairage_reussi_cree_eleve_et_ouvre_une_session(client):
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="2F")):
        resp = _pairer(client)
    assert resp.status_code == 200
    assert resp.json()["nom"] == "Élève Test"

    me = client.get("/api/me")
    assert me.json()["eleve"]["nom"] == "Élève Test"
    assert me.json()["is_admin"] is False


def test_classe_non_autorisee_est_refusee(client):
    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    client.post("/api/classes", json={"nom": "2F"})
    client.post("/auth/admin-logout")

    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="2E")):
        resp = _pairer(client)
    assert resp.status_code == 403
    assert "2E" in resp.json()["detail"]


def test_classe_autorisee_est_acceptee(client):
    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    client.post("/api/classes", json={"nom": "2F"})
    client.post("/auth/admin-logout")

    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="2F")):
        resp = _pairer(client)
    assert resp.status_code == 200


def test_aucune_classe_configuree_accepte_par_compatibilite(client):
    """Table `classes` vide = pas de vérification (comportement historique conservé)."""
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="3B")):
        resp = _pairer(client)
    assert resp.status_code == 200


def test_panne_apres_connexion_pronote_reussie_renvoie_message_clair(client, monkeypatch):
    """
    Une panne côté serveur APRÈS une connexion Pronote réussie (ex. chiffrement
    en échec) ne doit jamais remonter une 500 brute et muette à l'élève.
    """
    from Services import crypto_secrets as cs

    def _echoue(*_args, **_kwargs):
        raise RuntimeError("panne chiffrement simulée")

    monkeypatch.setattr(cs, "chiffrer_json", _echoue)

    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="2F")):
        resp = _pairer(client)
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "panne chiffrement simulée" not in detail
    assert "réessaie" in detail.lower()


def test_re_pairage_du_meme_eleve_ne_cree_pas_de_doublon(client):
    """
    `upsert_eleve_pronote` matche par nom normalisé, pas par `pronote_id`
    (voir Services/db.py — `pronote_id` n'est pas stable d'un pairage à
    l'autre, bug réel constaté en prod le 2026-09-13).
    """
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="2F", pronote_id="pid-1")):
        _pairer(client)
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name="2F", pronote_id="pid-2")):
        _pairer(client)

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    eleves = client.get("/api/eleves").json()
    assert len([e for e in eleves if e["nom"] == "Élève Test"]) == 1
