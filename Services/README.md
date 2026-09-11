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
   "Externe", renseigne un nom d'application ("Ghost School"), ton email.
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
