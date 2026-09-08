# Ghost Cards — Services

Logique métier de Ghost Cards : synchronisation Pronote et (bientôt)
génération IA des résumés/flashcards/quiz. Utilisé aussi bien par l'API
(`BackEnd/app/main.py`) que par les scripts en ligne de commande ci-dessous.

Toutes les commandes de cette page se lancent depuis la racine `GhostCards/`
(pas depuis `Services/` ni `BackEnd/`), avec le venv de `BackEnd/` activé :

```bash
cd ~/GhostCards
source BackEnd/.venv/bin/activate
```

```
Pronote  →  Services/pronote_sync.py  →  BackEnd/data/ghostcards.db + BackEnd/data/documents/
                                                    ↑
                                          BackEnd/app/main.py (API)  →  FrontEnd
```

(`.env`, `secrets/` et `data/` restent dans `BackEnd/`, même si le code qui
les utilise vit maintenant dans `Services/` — rien à déplacer sur le disque.)

## ⚠️ À savoir avant de commencer

- Pronote n'a pas d'API publique officielle. `pronotepy` est une bibliothèque
  communautaire qui imite ce que fait le site web — elle fonctionne bien mais
  peut casser si Pronote change son fonctionnement interne.
- Utilise uniquement ton propre compte élève. Le fichier
  `BackEnd/secrets/credentials.json` qui sera généré donne accès à ce
  compte : ne le partage jamais, ne le commite jamais dans un dépôt Git
  (le `.gitignore` fourni l'exclut déjà).
- Reste raisonnable sur la fréquence de synchronisation (2h par défaut) pour
  ne pas solliciter inutilement le serveur de l'établissement.

## Première connexion à Pronote

À faire une seule fois (le jeton généré se renouvelle ensuite tout seul à
chaque synchronisation).

> On utilise `scripts/first_login.py` plutôt que la commande
> `python3 -m pronotepy.create_login` fournie par la bibliothèque : cette
> dernière lit le JSON du QR code avec `input()`, qui ne lit qu'une seule
> ligne — un JSON collé sur plusieurs lignes casse le script et finit
> interprété comme des commandes shell. Elle n'écrit de toute façon pas de
> fichier, juste un affichage à copier-coller manuellement. Le script fourni
> lit le JSON depuis un fichier et écrit directement
> `BackEnd/secrets/credentials.json`.

1. Sur le site Pronote (dans un navigateur, connecté avec ton compte élève),
   ouvre **Mon compte → Configuration de mon compte → Connexion via
   smartphone**, qui affiche un QR code et un code PIN à 4 chiffres.
2. Enregistre le contenu JSON du QR code tel quel dans un fichier, par
   exemple `qr.json` (peu importe qu'il soit sur plusieurs lignes).
3. Lance, en remplaçant `1234` par le PIN affiché à côté du QR code :

```bash
python3 -m Services.scripts.first_login --qr-file qr.json --pin 1234
```

Le script confirme la connexion et écrit `BackEnd/secrets/credentials.json`.
Le QR code n'est valable que quelques minutes : s'il a expiré, régénère-en
un nouveau sur Pronote et relance la commande.

Connexion directe à Pronote (pas d'ENT) : c'est exactement ce que fait
`get_client()` dans `pronote_sync.py`, aucune adaptation n'est nécessaire.

## Tester la synchronisation manuellement

```bash
python3 -m Services.pronote_sync
```

Ça doit afficher un résumé JSON (`nouveaux_cours`, `nouveaux_devoirs`,
`nouveaux_documents`) et créer `BackEnd/data/ghostcards.db` ainsi que les
fichiers téléchargés dans `BackEnd/data/documents/<matière>/<année-mois>/`.

L'API (voir `BackEnd/README.md`) déclenche cette même synchronisation toute
seule, toutes les 2 heures, tant qu'elle tourne — cette commande manuelle
sert surtout à tester ou déboguer.

## Extraction de texte / OCR (documents Pronote et notes photo)

`Services/ocr.py` transcrit automatiquement en arrière-plan les PDF
Pronote scannés (sans couche de texte) et les photos/PDF déposés par un
élève sur un cours (`POST /api/cours/{id}/notes/photo`). Moteur par
défaut : **PaddleOCR** (local et gratuit, `OCR_ENGINE=paddleocr` dans
`.env`, voir `Services/config.py`) — nécessite un venv en **Python ≤3.13**
(voir `HANDOFF.md`, section OCR, pour la procédure de changement de
version sur l'OptiPlex, qui tournait jusque-là en Python 3.14). Vision
Claude reste disponible en repli (`OCR_ENGINE=claude`) si PaddleOCR
déçoit sur de l'écriture manuscrite réelle.

Chaque extraction/OCR est journalisée dans la table `traitements`, visible
et relançable depuis l'écran "Traitements" du site (nav visible seulement
pour un compte admin). Pour te passer admin, après ta première connexion
Google :

```bash
sqlite3 BackEnd/data/ghostcards.db "UPDATE eleves SET role='admin' WHERE email='ton@email';"
```

## Génération IA (résumés / flashcards / quiz)

À venir — en cours de construction, s'appuiera sur un modèle Ollama local
plutôt que l'API Anthropic (gros volume de génération, autant que ce soit
gratuit et privé).

## Authentification élève (Google)

Sert uniquement à savoir **qui** dépose une prise de notes (section 8 du
cahier des charges) : consulter les cours, résumés, flashcards et quiz reste
entièrement libre, sans connexion. Seul le dépôt d'une note nécessite d'être
connecté.

### ⚠️ Limitation importante : HTTPS et nom de domaine

Google n'autorise les URL de redirection OAuth qu'en HTTPS, à une exception
près : `http://localhost` est toléré pour développer en local. Une adresse
IP de réseau local (`http://192.168.1.117:8000`) n'est **pas** acceptée.

Concrètement :
- **Toi, sur l'OptiPlex lui-même** (ou en te connectant en SSH avec un tunnel
  vers `localhost:8000`) : ça fonctionne dès maintenant, en laissant
  `BASE_URL=http://localhost:8000`.
- **Tes camarades, depuis chez eux** : il faudra un nom de domaine pointant
  vers ton réseau (DNS dynamique si tu n'as pas d'IP fixe), un certificat
  HTTPS (ex. via un reverse proxy comme Caddy, qui gère Let's Encrypt
  automatiquement), et une redirection de port sur ta box — ce qui revient à
  exposer un serveur personnel sur Internet, avec les précautions de
  sécurité que ça implique. C'est une étape à part entière, pas juste une
  variable à changer : dis-moi quand tu veux t'y attaquer.

En attendant, le reste du site (cours, documents, assistant) fonctionne déjà
pour tout le monde sur le réseau local, connexion Google ou pas — seul le
dépôt de notes est concerné par cette limitation.

### Créer les identifiants Google OAuth

1. Va sur [Google Cloud Console](https://console.cloud.google.com/), crée un
   projet (ou réutilise un projet existant).
2. **APIs et services → Écran de consentement OAuth** : configure-le en
   "Externe", renseigne un nom d'application ("Ghost Cards"), ton email.
   Statut "Testing" (pas besoin de validation Google pour une classe) — dans
   ce mode, tu dois ajouter chaque élève comme "utilisateur test" tant que
   l'appli n'est pas publiée, **ou** publier l'appli (sans validation
   requise pour les scopes basiques `openid`, `email`, `profile`).
3. **APIs et services → Identifiants → Créer des identifiants → ID client
   OAuth**, type "Application Web".
4. **URI de redirection autorisée** : `http://localhost:8000/auth/callback`
   pour commencer (ajoute l'URL HTTPS finale plus tard, en plus, le jour où
   tu exposes le site).
5. Récupère le **Client ID** et le **Client Secret** générés.

Dans `.env` :

```
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx
BASE_URL=http://localhost:8000
SESSION_SECRET_KEY=   # génère avec: python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Qui a le droit de se connecter

Par défaut, si ni `GOOGLE_HOSTED_DOMAIN` ni `AUTHORIZED_EMAILS` ne sont
renseignés, **n'importe quel compte Google** peut se connecter et déposer
des notes. Pour une appli de classe, tu voudras probablement restreindre :

- **Comptes d'établissement (Google Workspace)**, ex. adresses
  `@moncollege.fr` : `GOOGLE_HOSTED_DOMAIN=moncollege.fr` — vérifié
  côté serveur, pas juste suggéré à Google.
- **Comptes Gmail personnels** : liste blanche d'adresses précises,
  `AUTHORIZED_EMAILS=eleve1@gmail.com,eleve2@gmail.com,...`

Redémarre l'API après toute modification de `.env`.
