"""
Fixtures partagées pour la suite de tests Ghost School.

Isolation par `monkeypatch` plutôt que par sous-processus : `Services.db.
DB_PATH` et `Services.crypto_secrets.CREDENTIALS_ENCRYPTION_KEY` sont des
noms de module résolus À L'APPEL (pas figés à l'import, voir `from .config
import ...` dans ces deux modules) — les rediriger avec `monkeypatch.
setattr` suffit donc à isoler chaque test dans sa propre base SQLite
temporaire et sa propre clé de chiffrement, sans jamais toucher à la vraie
base de l'OptiPlex ni lancer de sous-processus.

`SESSION_SECRET_KEY` est la seule exception : elle est passée à
`SessionMiddleware` au moment de la création de `app` (import de `app.main`),
donc figée avant qu'un test ne puisse la repatcher — sans conséquence ici,
les tests n'ont besoin que d'une valeur cohérente sur toute leur durée, pas
d'un "vrai" secret.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

# Services/ et BackEnd/ sont deux dossiers frères sous GhostCards/ (voir
# BackEnd/app/main.py, qui fait le même ajout pour la même raison) : ce
# fichier vit sous BackEnd/tests/, donc GhostCards/ est son grand-parent.
_GHOSTCARDS_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _root in (_GHOSTCARDS_ROOT, _BACKEND_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from Services import crypto_secrets, db  # noqa: E402


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Redirige Services.db.DB_PATH vers une base SQLite jetable pour ce test."""
    chemin = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", chemin)
    return chemin


@pytest.fixture
def cle_chiffrement(monkeypatch):
    """
    Clé Fernet fraîche par test. `crypto_secrets._fernet` est un cache
    global construit une seule fois puis réutilisé (voir `_get_fernet`) —
    sans le remettre à None ici, un test pourrait hériter de la clé mise en
    cache par un test précédent au lieu de celle qu'on vient de patcher.
    """
    cle = Fernet.generate_key().decode()
    monkeypatch.setattr(crypto_secrets, "CREDENTIALS_ENCRYPTION_KEY", cle)
    monkeypatch.setattr(crypto_secrets, "_fernet", None)
    return cle


@pytest.fixture
def conn(db_path):
    """Connexion à une base fraîchement migrée (`init_db`), fermée en fin de test."""
    db.init_db()
    connexion = db.get_connection()
    yield connexion
    connexion.close()


@pytest.fixture
def app(db_path, cle_chiffrement, monkeypatch):
    """
    Application FastAPI complète (routes réelles de `app/main.py`), base et
    chiffrement isolés par les fixtures ci-dessus. `ADMIN_PASSWORD` (constante
    de `Services/config.py`, jamais en base) est repatchée directement sur le
    module `app.main` ; `pronote_url` (table `parametres`, lue via
    `Services/pronote_sync.py::config_pronote`) est insérée en base — les
    deux suivent la même logique que la vraie config (env vs Paramétrage).
    """
    from app import main as app_main

    monkeypatch.setattr(app_main, "ADMIN_PASSWORD", "motdepasse-test")
    db.init_db()
    with db.session() as connexion:
        db.set_parametre(connexion, "pronote_url", "https://demo.index-education.net/pronote/eleve.html")
    return app_main.app


@pytest.fixture
def client(app):
    """
    `TestClient(app)` SANS bloc `with` : ne déclenche pas l'évènement
    "startup" de FastAPI dans cette version de Starlette (confirmé en
    testant : aucun `init_db()`/scheduler ne s'exécute par ce biais) — la
    base est déjà migrée par la fixture `app` ci-dessus, et on évite de
    laisser un job de synchro APScheduler tourner en tâche de fond pendant
    la suite de tests.
    """
    return TestClient(app)


def fake_pronote_client(*, class_name: str, nom: str = "Élève Test", pronote_id: str = "pid-1"):
    """
    Simule un `pronotepy.Client` connecté, pour patcher
    `pronotepy.Client.qrcode_login` dans les tests de pairage/synchro — pas
    besoin d'un vrai serveur Pronote pour vérifier notre propre logique
    (vérification de classe, chiffrement, dédoublonnage...).
    """
    info = SimpleNamespace(id=pronote_id, name=nom, class_name=class_name)
    return SimpleNamespace(
        logged_in=True,
        info=info,
        export_credentials=lambda: {"jeton": f"jeton-{pronote_id}", "pronote_id": pronote_id},
    )
