"""
Chiffrement au repos des jetons Pronote stockés par élève (`eleves.pronote_
credentials`) — contrairement au `credentials.json` unique de l'admin (un
fichier à part, non chiffré, procédure de première connexion manuelle),
ces jetons sont créés en self-service par des mineurs et donnent un accès
direct à leur compte scolaire réel : sensibilité nettement supérieure,
d'où le chiffrement plutôt qu'un simple JSON en clair en base.
"""
import json

from cryptography.fernet import Fernet, InvalidToken

from .config import CREDENTIALS_ENCRYPTION_KEY


class SecretsError(Exception):
    pass


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not CREDENTIALS_ENCRYPTION_KEY:
            raise SecretsError(
                "CREDENTIALS_ENCRYPTION_KEY n'est pas configurée (voir .env) — "
                "génère-en une avec : python3 -c \"from cryptography.fernet import "
                "Fernet; print(Fernet.generate_key().decode())\""
            )
        try:
            _fernet = Fernet(CREDENTIALS_ENCRYPTION_KEY.encode("utf-8"))
        except (ValueError, TypeError) as e:
            raise SecretsError("CREDENTIALS_ENCRYPTION_KEY invalide (doit être une clé Fernet valide).") from e
    return _fernet


def chiffrer_json(data: dict) -> str:
    brut = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _get_fernet().encrypt(brut).decode("ascii")


def dechiffrer_json(blob: str) -> dict:
    try:
        brut = _get_fernet().decrypt(blob.encode("ascii"))
    except InvalidToken as e:
        raise SecretsError("Jeton chiffré invalide ou clé de chiffrement différente de celle utilisée à l'écriture.") from e
    return json.loads(brut.decode("utf-8"))
