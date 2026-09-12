# Ghost School — Services

Logique métier de Ghost School : synchronisation Pronote et (bientôt)
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

L'écran admin "Paramétrage" affiche l'état de cette connexion (jeton
présent ou non, date et résultat de la dernière synchronisation) et
permet de modifier à chaud la fenêtre de récupération (`SYNC_DAYS_BACK`/
`SYNC_DAYS_FORWARD` dans `.env` au départ, puis table `parametres`) —
mais pas le jeton lui-même, qui reste géré uniquement via cette procédure
de première connexion.

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
défaut : **PaddleOCR** (local et gratuit) — nécessite un venv en
**Python ≤3.13** (voir `HANDOFF.md`, section OCR, pour la procédure de
changement de version sur l'OptiPlex, qui tournait jusque-là en Python
3.14). Vision Claude reste disponible en repli si PaddleOCR déçoit sur
de l'écriture manuscrite réelle — elle réutilise la clé Anthropic déjà
configurée pour la génération IA/l'assistant (pas de clé séparée). Le
choix se change à chaud depuis le sous-menu "OCR" de l'écran admin
"Paramétrage" ; `OCR_ENGINE` dans `.env` (voir `Services/config.py`) ne
sert que de valeur de départ.

**Dépendance système requise, indépendamment du moteur OCR choisi** :
`pdftotext`/`pdftoppm`/`pdfinfo` (paquet **poppler-utils**, PAS une
dépendance Python — `pip install` ne l'installe pas). Tout PDF passe
d'abord par `pdftotext` (texte natif) avant même de songer à
PaddleOCR/Claude ; si ces binaires sont introuvables, chaque transcription
échoue avec `[Errno 2] No such file or directory: 'pdftotext'` (visible
dans le détail du traitement "transcription_document"), et un cours n'a
alors que sa description Pronote comme source pour la génération IA.

```bash
sudo apt install poppler-utils
```

**Piège vécu** : cette erreur peut survenir même si le paquet est déjà
installé, si le service systemd tourne avec un `PATH` restreint au venv
(voir `Environment="PATH=..."` dans `BackEnd/deploy/ghostcards.service`)
— les binaires système ne sont alors pas visibles depuis le service, même
si `sudo apt install poppler-utils` répond "déjà la version la plus
récente" en SSH. Vérifie que ce `PATH` inclut bien `/usr/bin` en plus du
`.venv/bin`, pas seulement le venv seul.

**Piège vécu** : `NotImplementedError: (Unimplemented) ConvertPirAttribute
2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]`
sur une transcription d'image — régression connue de `paddlepaddle` 3.3.x
sur CPU avec l'accélération oneDNN (voir
[PaddlePaddle/Paddle#77340](https://github.com/PaddlePaddle/Paddle/issues/77340)),
pas propre à un document en particulier. oneDNN est désormais désactivé
par défaut (réglage "Accélération oneDNN (CPU)" dans Paramétrage → OCR,
section avancée) — un peu plus lent sur CPU, mais fonctionne ; pas de
correctif officiel de PaddlePaddle au moment de l'écriture. À réactiver
seulement si ce bug est corrigé côté PaddlePaddle, ou constaté absent sur
une machine où l'accélération apporte un vrai gain. Les transcriptions
déjà en échec pour cette raison ne se relancent pas toutes seules : bouton
"Relancer" sur chacune (ou "Transcrire" depuis l'onglet "Non traités" pour
un document qui n'a encore jamais eu de tentative) depuis
l'écran admin "Traitements".

Chaque extraction/OCR est journalisée dans la table `traitements`, visible
et relançable depuis l'écran "Traitements" du site (nav visible seulement
en étant connecté en admin) — cet écran, comme "Paramétrage", est
réparti en 3 sous-menus (Pronote / Génération IA / OCR) plutôt qu'une
seule liste mélangeant tout. L'accès admin est **totalement indépendant**
des comptes élèves (Google) — un élève ne peut jamais devenir admin :
définis `ADMIN_PASSWORD` dans `.env`, puis connecte-toi via le petit
bouton bouclier dans l'en-tête du site.

## Génération IA (résumés / flashcards / quiz) et assistant

`Services/ia_generation.py` génère résumé, flashcards et quiz d'un cours,
et fait aussi tourner l'assistant conversationnel — **les deux passent
par le même moteur**. Trois moteurs possibles : Ollama local (par
défaut, gratuit), Claude (Anthropic) ou Gemini (Google). Le choix, l'URL
et le modèle Ollama, les modèles Claude/Gemini et leurs clés se
changent **à chaud depuis le sous-menu "Génération IA" de l'écran admin
"Paramétrage"**, sans redémarrer le service —
`.env` (`IA_ENGINE`, `OLLAMA_URL`, `OLLAMA_MODEL`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`) ne sert que de valeur de départ. Un bouton "Détecter"
interroge `{url}/api/tags` sur le serveur Ollama choisi pour proposer la
liste des modèles réellement installés plutôt que de taper le nom à la
main. Chaque moteur cloud (Claude, Gemini) a sa propre clé, jamais
réutilisée automatiquement pour l'autre.

Pourquoi pas la connexion Google des élèves pour utiliser leur propre
Gemini ? Vérifié : "Sign in with Google" ne donne aucun accès à l'API
Gemini, il n'existe pas de mécanisme OAuth pour ça — chaque compte
devrait créer sa propre clé manuellement sur aistudio.google.com, pas
réaliste pour une classe.

Génération déclenchée depuis le bouton "Générer" sur la page d'un cours
— aucune commande manuelle nécessaire. Compter jusqu'à ~30 minutes pour
un cours complet avec `qwen3:14b` en CPU : normal, pas un bug.

Un cours dont le texte source (description + documents transcrits)
dépasse `IA_TEXTE_MAX_CHARS` (12000 par défaut) n'est plus tronqué
silencieusement : il est découpé en plusieurs parties, chacune résumée
séparément ("map"), puis les résumés sont fusionnés pour servir de texte
source à la génération finale ("reduce") — voir
`Services/ia_generation.py::_texte_pour_prompt`. Chaque passe (découpage,
résumé de chaque partie, fusion) est journalisée comme une étape à part
dans `traitements`, visible dans l'écran "Traitements" au même titre que
le résultat final — utile pour vérifier ce qui a réellement été transmis
au modèle sur un cours long.

**Accès à l'assistant** : désactivé par défaut pour un compte élève,
à activer au cas par cas depuis l'écran admin "Élèves" (bouton bascule).
L'admin y a toujours accès.

## Authentification élève (pairage Pronote)

Le site est **verrouillé** : consulter quoi que ce soit (cours, résumés,
flashcards, quiz) nécessite d'être connecté — élève de la classe, ou admin.
Chaque élève se connecte avec **son propre compte Pronote**, jamais avec un
compte Google : ça vérifie à la fois qu'il s'agit du bon établissement et de
la bonne classe, et ça permet à la synchro de récupérer SON groupe (LV2,
options...) en plus de celui de l'admin (voir plus haut, "Points d'attention
sur le fonctionnement de Pronote" dans `Services/pronote_sync.py`).

Contrairement à l'ancienne connexion Google, **aucune contrainte HTTPS/nom
de domaine** : le pairage est un simple envoi de formulaire au serveur, pas
une redirection OAuth externe — fonctionne aussi bien en HTTP simple sur le
réseau local. (Exposer le site à des élèves connectant depuis chez eux reste
une question à part, réseau/HTTPS, indépendante de l'authentification —
voir plus bas si besoin.)

### Comment un élève se connecte

Sur Pronote (ordinateur ou téléphone) : **Mon compte → Configuration de mon
compte → Connexion via smartphone**, qui affiche un QR code et un PIN à 4
chiffres (même procédure que la "Première connexion" de l'admin plus haut).
Sur Ghost School, écran de connexion : upload d'une capture d'écran du QR
code + saisie du PIN. Le serveur décode le QR (OpenCV), se connecte à
Pronote avec (`pronotepy.Client.qrcode_login`), vérifie établissement et
classe, puis pose un cookie de session classique — une seule fois par
appareil, pas à chaque visite. Le QR n'est valable que ~10 minutes.

### Configuration requise dans `.env`

```
CREDENTIALS_ENCRYPTION_KEY=   # génère avec : python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_SECRET_KEY=           # génère avec : python3 -c "import secrets; print(secrets.token_hex(32))"
CLASSE_ATTENDUE=2F            # valeur de départ — modifiable à chaud depuis Paramétrage → Pronote
```

`CREDENTIALS_ENCRYPTION_KEY` chiffre les jetons Pronote stockés par élève
(`eleves.pronote_credentials`, voir `Services/crypto_secrets.py`) — accès
direct au compte scolaire réel d'un mineur, sensibilité bien supérieure au
`credentials.json` unique de l'admin. Sans cette clé, le pairage échoue
avec une erreur claire plutôt que de stocker les jetons en clair.

### Vérification établissement + classe

- **Établissement** : le domaine de l'URL embarquée dans le QR doit
  correspondre à `pronote_url` (Paramétrage → Pronote) — vérifié *avant*
  même de tenter la connexion.
- **Classe** : une fois connecté, `client.info.class_name` (Pronote) doit
  correspondre à `classe_attendue` (Paramétrage → Pronote, section
  "Classe attendue") — laisse vide pour ne pas vérifier la classe.

### Admin : gérer les comptes élèves

Écran admin "Élèves" : statut de chaque élève pairé (classe constatée,
lien Pronote cassé ou non), et un bouton "Re-pairer" qui efface le jeton
stocké — l'élève reprendra le flux de connexion (upload QR + PIN) à sa
prochaine visite.

## Exposer le site hors du réseau local (HTTPS)

Une fois un nom de domaine acheté et pointé vers l'IP publique de ta box
(ex. `ghostschool.app`), avec le port **80** de la box redirigé vers le
port 8000 de l'OptiPlex, le site est déjà joignable depuis Internet — mais
en HTTP simple, ce qui veut dire que le QR code Pronote, le code PIN, et
le cookie de session de chaque élève circulent en clair sur le réseau.
Vu qu'il s'agit d'un accès direct à de vraies données scolaires de
mineurs, mets HTTPS en place avant que d'autres élèves ne se connectent
depuis l'extérieur de ton réseau local.

**Étapes** :

1. Redirige aussi le port **443** de ta box vers l'OptiPlex (en plus du
   80 déjà fait — Caddy a besoin des deux : 80 pour le défi ACME/la
   redirection vers HTTPS, 443 pour le trafic HTTPS lui-même).
2. Installe Caddy (dépôt officiel, Debian/Ubuntu) :
   ```bash
   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt update && sudo apt install caddy
   ```
3. Copie `BackEnd/deploy/Caddyfile` vers `/etc/caddy/Caddyfile` (adapte le
   nom de domaine s'il diffère de `ghostschool.app`), puis :
   ```bash
   sudo cp BackEnd/deploy/Caddyfile /etc/caddy/Caddyfile
   sudo systemctl enable --now caddy
   sudo systemctl restart caddy
   sudo systemctl status caddy --no-pager -l
   ```
   Caddy obtient et renouvelle ensuite tout seul le certificat Let's
   Encrypt — rien d'autre à faire tant que le domaine continue de pointer
   vers cette IP.
4. Une fois `https://ghostschool.app` confirmé fonctionnel, ajoute dans
   `.env` :
   ```
   SESSION_COOKIE_SECURE=true
   ```
   puis `sudo systemctl restart ghostcards.service`. Sans cette étape,
   les cookies de session restent utilisables même en HTTP (pratique
   pendant la mise en place, mais à ne pas laisser en l'état une fois
   HTTPS confirmé). **Effet de bord à connaître** : une fois activé, un
   accès de diagnostic en HTTP simple (ex. tunnel SSH vers
   `localhost:8000`) ne garde plus la session d'une requête à l'autre —
   utilise `https://ghostschool.app` même pour l'administration.
