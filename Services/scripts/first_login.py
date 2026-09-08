"""
Première connexion à Pronote à partir d'un QR code, sans passer par le CLI
interactif `pronotepy.create_login` (qui casse si le JSON du QR code est
collé sur plusieurs lignes, et n'écrit pas de fichier de toute façon).

Usage :
    1. Sur le site Pronote (compte élève), génère un QR code de connexion :
       Mon compte → Configuration de mon compte → Connexion via smartphone.
       Note le code PIN à 4 chiffres affiché à côté du QR code.
    2. Enregistre le contenu JSON du QR code dans un fichier, par ex. qr.json
       (le contenu exact affiché/scanné, tel quel).
    3. Lance, depuis la racine GhostCards/ (pas depuis BackEnd/) :
       python3 -m Services.scripts.first_login --qr-file qr.json --pin 1234

Le fichier credentials.json est écrit à l'emplacement défini par
CREDENTIALS_PATH (voir app/config.py / .env).
"""
import argparse
import json
import secrets
import sys

import pronotepy

from Services.config import CREDENTIALS_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Première connexion Pronote via QR code")
    parser.add_argument("--qr-file", required=True, help="Fichier contenant le JSON du QR code")
    parser.add_argument("--pin", required=True, help="Code PIN à 4 chiffres affiché à côté du QR code")
    parser.add_argument("--uuid", default=None, help="Identifiant d'appareil (laisser vide pour un aléatoire)")
    args = parser.parse_args()

    with open(args.qr_file, encoding="utf-8") as f:
        qr_code = json.load(f)

    if not qr_code.get("url", "").endswith("eleve.html") and not qr_code.get("url", "").endswith("mobile.eleve.html"):
        print(f"Attention : url inattendue dans le QR code : {qr_code.get('url')}", file=sys.stderr)

    uuid = args.uuid or secrets.token_hex(8)

    try:
        client = pronotepy.Client.qrcode_login(qr_code, args.pin, uuid)
    except Exception as e:
        print(f"Échec de connexion : {e}", file=sys.stderr)
        print(
            "Le QR code est probablement expiré (il n'est valable que quelques minutes) "
            "— régénère-en un nouveau sur Pronote et relance la commande.",
            file=sys.stderr,
        )
        return 1

    if not client.logged_in:
        print("Connexion refusée par Pronote.", file=sys.stderr)
        return 1

    CREDENTIALS_PATH.write_text(json.dumps(client.export_credentials()), encoding="utf-8")
    print(f"Connecté avec succès. Identifiants enregistrés dans {CREDENTIALS_PATH}")
    try:
        print(f"Élève : {client.info.name}")
    except AttributeError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
