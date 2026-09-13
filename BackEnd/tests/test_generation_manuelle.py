"""
Génération manuelle (v0.6.0) : un élève copie un prompt, le colle dans sa
propre IA hors Ghost School, puis importe le JSON obtenu — toujours en
attente de validation admin avant de remplacer le contenu partagé de la
classe, et désactivé par défaut pour chaque élève (comme l'assistant IA).
"""
import json
from unittest.mock import patch

import pytest

from Services import db, ia_generation, pronote_sync
from conftest import fake_pronote_client

CONTENU_VALIDE = {
    "resume_court": "Résumé court.",
    "resume_detaille": "Résumé détaillé et complet du cours.",
    "flashcards": [{"question": "Q1 ?", "reponse": "R1"}],
    "quiz": [{"question": "QCM 1 ?", "options": ["A", "B", "C", "D"], "reponse_index": 2}],
}


# --- parser_json_ia --------------------------------------------------------

def test_parser_json_ia_accepte_un_json_propre():
    assert ia_generation.parser_json_ia('{"a": 1}') == {"a": 1}


def test_parser_json_ia_extrait_un_json_entoure_de_texte():
    texte = 'Voici le résultat :\n```json\n{"a": 1}\n```\nVoilà !'
    assert ia_generation.parser_json_ia(texte) == {"a": 1}


def test_parser_json_ia_rejette_un_texte_inexploitable():
    with pytest.raises(ia_generation.GenerationError):
        ia_generation.parser_json_ia("ceci n'est pas du JSON du tout")


# --- valider_forme_generation -----------------------------------------------

def test_valider_forme_generation_accepte_une_forme_correcte():
    assert ia_generation.valider_forme_generation(dict(CONTENU_VALIDE)) == CONTENU_VALIDE


def test_valider_forme_generation_rejette_non_dict():
    with pytest.raises(ia_generation.GenerationError):
        ia_generation.valider_forme_generation(["pas", "un", "dict"])


def test_valider_forme_generation_rejette_resume_manquant():
    contenu = dict(CONTENU_VALIDE)
    del contenu["resume_court"]
    with pytest.raises(ia_generation.GenerationError, match="resume_court"):
        ia_generation.valider_forme_generation(contenu)


def test_valider_forme_generation_rejette_flashcard_incomplete():
    contenu = dict(CONTENU_VALIDE)
    contenu["flashcards"] = [{"question": "Q1 ?"}]  # pas de "reponse"
    with pytest.raises(ia_generation.GenerationError, match="Flashcard"):
        ia_generation.valider_forme_generation(contenu)


def test_valider_forme_generation_rejette_quiz_avec_3_options():
    contenu = dict(CONTENU_VALIDE)
    contenu["quiz"] = [{"question": "Q ?", "options": ["A", "B", "C"], "reponse_index": 0}]
    with pytest.raises(ia_generation.GenerationError, match="options"):
        ia_generation.valider_forme_generation(contenu)


def test_valider_forme_generation_rejette_reponse_index_hors_bornes():
    contenu = dict(CONTENU_VALIDE)
    contenu["quiz"] = [{"question": "Q ?", "options": ["A", "B", "C", "D"], "reponse_index": 4}]
    with pytest.raises(ia_generation.GenerationError, match="reponse_index"):
        ia_generation.valider_forme_generation(contenu)


def test_valider_forme_generation_rejette_flashcards_vides():
    contenu = dict(CONTENU_VALIDE)
    contenu["flashcards"] = []
    with pytest.raises(ia_generation.GenerationError):
        ia_generation.valider_forme_generation(contenu)


# --- importer_manuel (écriture directe) -------------------------------------

def test_importer_manuel_ecrit_les_colonnes_et_marque_l_origine(conn):
    matiere_id = db.upsert_matiere(conn, "MATHEMATIQUES")
    conn.execute(
        """INSERT INTO cours (external_key, matiere_id, date, heure_debut, professeur, classe, created_at, updated_at)
           VALUES ('k1', ?, '2026-09-14', '08:00', 'Mme Martin', '2F', ?, ?)""",
        (matiere_id, db.now_iso(), db.now_iso()),
    )
    cours_id = conn.execute("SELECT id FROM cours").fetchone()["id"]

    ia_generation.importer_manuel(conn, cours_id, CONTENU_VALIDE)
    conn.commit()

    cours = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
    assert cours["ia_statut"] == "pret"
    assert cours["ia_origine"] == "import"
    assert cours["ia_resume"] == CONTENU_VALIDE["resume_court"]
    assert json.loads(cours["ia_flashcards"]) == CONTENU_VALIDE["flashcards"]
    assert json.loads(cours["ia_quiz"]) == CONTENU_VALIDE["quiz"]
    assert cours["ia_texte_source"] is None


# --- API : permission par élève ---------------------------------------------

def _pairer_eleve(client, *, classe="2F", nom="Élève Test", pronote_id="p1"):
    payload = {
        "qr_json": json.dumps({"url": "https://demo.index-education.net/pronote/eleve.html"}),
        "pin": "1234",
        "consentement": "true",
    }
    with patch("pronotepy.Client.qrcode_login", return_value=fake_pronote_client(class_name=classe, nom=nom, pronote_id=pronote_id)):
        resp = client.post("/api/eleves/pairage", data=payload)
    assert resp.status_code == 200, resp.text


def _seed_cours(conn, *, classe="2F", matiere="MATHEMATIQUES", description="Un cours de test bien assez long pour générer quelque chose de sensé, largement au-dessus du seuil minimal de deux cents caractères requis avant de tenter une génération."):
    matiere_id = db.upsert_matiere(conn, matiere)
    cle = pronote_sync._stable_key(classe, "2026-09-14", "08:00", matiere, "Mme Martin")
    conn.execute(
        """INSERT INTO cours (external_key, matiere_id, date, heure_debut, professeur, classe, description, created_at, updated_at)
           VALUES (?, ?, '2026-09-14', '08:00', 'Mme Martin', ?, ?, ?, ?)""",
        (cle, matiere_id, classe, description, db.now_iso(), db.now_iso()),
    )
    return conn.execute("SELECT id FROM cours WHERE external_key = ?", (cle,)).fetchone()["id"]


def test_generation_manuelle_desactivee_par_defaut(client):
    _pairer_eleve(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)

    resp = client.get(f"/api/cours/{cours_id}/prompt-manuel")
    assert resp.status_code == 403

    resp = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)})
    assert resp.status_code == 403


def test_admin_toggle_active_la_permission(client):
    _pairer_eleve(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)
        eleve_id = conn.execute("SELECT id FROM eleves WHERE nom = 'Élève Test'").fetchone()["id"]

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.put(f"/api/eleves/{eleve_id}/generation-manuelle", json={"actif": True})
    assert resp.status_code == 200
    eleves = client.get("/api/eleves").json()
    assert next(e for e in eleves if e["id"] == eleve_id)["generation_manuelle_actif"] == 1


def test_admin_a_toujours_acces_meme_sans_le_flag(client):
    with db.session() as conn:
        cours_id = _seed_cours(conn)
    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.get(f"/api/cours/{cours_id}/prompt-manuel")
    assert resp.status_code == 200


# --- API : prompt-manuel ----------------------------------------------------

def _activer_et_pairer(client, *, classe="2F"):
    _pairer_eleve(client, classe=classe)
    with db.session() as conn:
        eleve_id = conn.execute("SELECT id FROM eleves WHERE nom = 'Élève Test'").fetchone()["id"]
    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    client.put(f"/api/eleves/{eleve_id}/generation-manuelle", json={"actif": True})
    # `admin-logout` n'efface que `is_admin` de la session — `eleve_id`
    # (posé par `_pairer_eleve` ci-dessus) reste en place, donc les appels
    # suivants sur ce même `client` agissent bien comme l'élève.
    client.post("/auth/admin-logout")
    return eleve_id


def test_prompt_manuel_contient_le_texte_du_cours(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)

    resp = client.get(f"/api/cours/{cours_id}/prompt-manuel")
    assert resp.status_code == 200
    assert "Un cours de test" in resp.json()["prompt"]
    assert "flashcards" in resp.json()["prompt"]


def test_prompt_manuel_404_si_cours_inconnu(client):
    _activer_et_pairer(client)
    resp = client.get("/api/cours/999999/prompt-manuel")
    assert resp.status_code == 404


def test_prompt_manuel_400_si_cours_vide(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn, description="")
    resp = client.get(f"/api/cours/{cours_id}/prompt-manuel")
    assert resp.status_code == 400


def test_prompt_manuel_refuse_un_cours_d_une_autre_classe(client):
    _activer_et_pairer(client, classe="2F")
    with db.session() as conn:
        cours_id = _seed_cours(conn, classe="2E")
    resp = client.get(f"/api/cours/{cours_id}/prompt-manuel")
    assert resp.status_code == 403


# --- API : importer-manuel ---------------------------------------------------

def test_importer_manuel_cree_toujours_une_demande_meme_sur_cours_vierge(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)

    resp = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)})
    assert resp.status_code == 200
    assert resp.json()["status"] == "demande_en_attente"

    with db.session() as conn:
        cours = conn.execute("SELECT ia_statut, ia_resume FROM cours WHERE id = ?", (cours_id,)).fetchone()
    assert cours["ia_statut"] == "absent"
    assert cours["ia_resume"] is None


def test_importer_manuel_400_si_json_invalide(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)
    resp = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": "n'importe quoi"})
    assert resp.status_code == 400


def test_importer_manuel_400_si_forme_invalide(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)
    contenu = dict(CONTENU_VALIDE)
    contenu["flashcards"] = "pas une liste"
    resp = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(contenu)})
    assert resp.status_code == 400


def test_importer_manuel_ne_duplique_pas_une_demande_deja_en_attente(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)

    r1 = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)})
    r2 = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)})
    assert r1.json()["demande_id"] == r2.json()["demande_id"]
    assert r2.json()["status"] == "deja_en_attente"


def test_importer_manuel_refuse_un_cours_d_une_autre_classe(client):
    _activer_et_pairer(client, classe="2F")
    with db.session() as conn:
        cours_id = _seed_cours(conn, classe="2E")
    resp = client.post(f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)})
    assert resp.status_code == 403


# --- API : validation/rejet admin -------------------------------------------

def test_admin_valide_une_demande_d_import_applique_le_contenu(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)
    demande_id = client.post(
        f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)}
    ).json()["demande_id"]

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.post(f"/api/traitements/demandes/{demande_id}/valider")
    assert resp.status_code == 200
    assert resp.json()["status"] == "validee"

    cours = client.get(f"/api/cours/{cours_id}").json()
    assert cours["ia_statut"] == "pret"
    assert cours["ia_origine"] == "import"
    assert cours["ia_resume"] == CONTENU_VALIDE["resume_court"]
    assert cours["ia_flashcards"] == CONTENU_VALIDE["flashcards"]


def test_admin_rejette_une_demande_d_import_n_applique_rien(client):
    _activer_et_pairer(client)
    with db.session() as conn:
        cours_id = _seed_cours(conn)
    demande_id = client.post(
        f"/api/cours/{cours_id}/importer-manuel", json={"contenu": json.dumps(CONTENU_VALIDE)}
    ).json()["demande_id"]

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.post(f"/api/traitements/demandes/{demande_id}/rejeter")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejetee"

    cours = client.get(f"/api/cours/{cours_id}").json()
    assert cours["ia_statut"] == "absent"
    assert cours["ia_resume"] is None

    # Une demande déjà traitée ne peut pas être re-traitée.
    resp = client.post(f"/api/traitements/demandes/{demande_id}/valider")
    assert resp.status_code == 404


def test_regeneration_demande_toujours_fonctionnelle_apres_generalisation(client):
    """
    Non-régression : la généralisation de valider/rejeter pour l'import
    manuel ne doit rien changer au comportement existant de la
    régénération (voir Services/db.py::creer_demande_regeneration).
    """
    with db.session() as conn:
        cours_id = _seed_cours(conn)
        demande_id = db.creer_demande_regeneration(conn, cours_id)

    client.post("/auth/admin-login", json={"password": "motdepasse-test"})
    resp = client.post(f"/api/traitements/demandes/{demande_id}/rejeter")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejetee"
