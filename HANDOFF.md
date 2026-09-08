# Ghost Cards — Passation (état au 8 septembre 2026)

Ce document résume tout ce qu'il faut savoir pour reprendre le projet dans
Claude Code sans repartir de zéro ni recasser ce qui fonctionne déjà. Les
`README.md` (racine, `BackEnd/`, `Services/`) restent la doc de référence
pour l'installation et l'usage — ce fichier-ci est plutôt le "journal de
bord" des décisions et de l'état d'avancement.

## Qui, quoi

Cédric construit Ghost Cards pour la classe de 3ème B : synchro Pronote,
révision par flashcards/quiz générés par IA, notes collaboratives. Auto-hébergé
sur son OptiPlex personnel (Linux).

## Environnement réel de Cédric (à ne pas casser)

- Chemin du projet : `~/GhostCards/` avec `BackEnd/`, `FrontEnd/`, `Services/`
  au même niveau.
- Venv Python à `~/GhostCards/BackEnd/.venv` — **Python 3.14** (important :
  bloque l'installation de PaddlePaddle/PaddleOCR pour l'instant, voir plus
  bas).
- `.env`, `secrets/credentials.json`, `data/ghostcards.db`,
  `data/documents/` vivent tous dans `BackEnd/`, même si le code qui les
  utilise (`Services/config.py`, `Services/db.py`) est ailleurs.
- Service systemd : `ghostcards.service`, `User=cedric`,
  `WorkingDirectory=/home/cedric/GhostCards/BackEnd`, lance
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Fichier modèle dans
  `BackEnd/deploy/ghostcards.service`.
- Pronote : connexion **directe** (pas d'ENT).
- La base contient déjà ~44 cours + devoirs + documents réels (première
  synchro réussie le 7 septembre).
- Commandes CLI (synchro, première connexion) se lancent depuis la racine
  `~/GhostCards/`, pas depuis `BackEnd/` — convention posée lors de la
  réorganisation en `Services/`.

## Architecture

```
GhostCards/
  BackEnd/   FastAPI (app/main.py) — HTTP uniquement, sert aussi le
             frontend buildé (FrontEnd/dist) en statique une fois présent
  FrontEnd/  Vite + React, un seul fichier src/App.jsx (thème clair/sombre
             néon rétro 80s, layout mobile + desktop responsive)
  Services/  Logique métier partagée : config.py, db.py, schema.sql,
             pronote_sync.py, auth.py, scripts/first_login.py
```

`Services/` n'est pas un sous-package de `BackEnd/` : `main.py` ajoute
explicitement la racine `GhostCards/` à `sys.path` pour l'importer (voir
le commentaire en haut de `BackEnd/app/main.py`). Les imports relatifs
internes à `Services/` (`from . import db`) restent inchangés.

## État — fonctionnel et testé

- **Synchro Pronote** (`Services/pronote_sync.py`) : cours, devoirs,
  documents. Clé stable calculée (date+heure+matière+prof) car Pronote
  change ses id internes à chaque session. Token à usage unique, roté à
  chaque connexion.
- **Stockage** : SQLite (`Services/schema.sql` + `Services/db.py`), fichiers
  sur disque sous `data/documents/<matière>/<année-mois>/`.
- **API FastAPI** (`BackEnd/app/main.py`) : matières, cours, documents,
  devoirs, recherche, sync manuel/auto (toutes les 2h).
- **Frontend React** (`FrontEnd/src/App.jsx`) : accueil, matières, détail
  cours, recherche, assistant IA. Thème clair/sombre néon avec bascule,
  sidebar desktop / barre basse mobile (`FrontEnd/src/index.css`).
- **Assistant IA** : `/api/assistant`, proxy serveur vers l'API Anthropic
  (clé jamais exposée au navigateur). Modèle actuellement câblé :
  `claude-sonnet-5` — **vérifier que cette chaîne de modèle est toujours
  valide** au moment de la reprise (voir skill `product-self-knowledge` si
  disponible dans Claude Code, sinon la doc Anthropic).
- **Authentification élève (Google)** : OpenID Connect via Authlib,
  sessions signées par cookie (`SessionMiddleware`), table `eleves`.
  Sert uniquement à attribuer les notes déposées — la consultation du
  site reste libre sans compte. Restriction d'accès au choix :
  `GOOGLE_HOSTED_DOMAIN` (Workspace) ou `AUTHORIZED_EMAILS` (liste
  blanche Gmail).
  **Limitation connue et non résolue** : Google n'autorise les URI de
  redirection OAuth qu'en HTTPS (sauf `http://localhost`). Une IP LAN
  (`http://192.168.x.x:8000`) est refusée. Donc la connexion Google ne
  fonctionne aujourd'hui que pour Cédric lui-même (via localhost) — pour
  que les camarades se connectent depuis chez eux, il faut un nom de
  domaine + HTTPS + redirection de port (chantier à part, pas commencé).
- **Dépôt de notes (texte)** : `POST /api/cours/{id}/notes`, exige une
  session active. `notes_eleves.auteur` est renseigné automatiquement
  depuis l'identité Google, pas saisi par l'élève.

## État — fonctionnel et testé (suite de la session du 8 septembre 2026)

**OCR / extraction de texte**, démarré à la demande "il faut mettre en
place de l'OCR sur les prises de notes déposées, tout comme pour les PDF
Pronote" + "voir le rendu de toutes les actions en arrière-plan et pouvoir
relancer si pas satisfaisant". Implémenté en suivant le plan ci-dessous.

**Décision révisée le 8 septembre 2026** : moteur par défaut = **PaddleOCR
local**, pas Claude vision. Cédric préfère un moteur local/gratuit à long
terme (gros volume potentiel de photos de cahier sur toute une année
scolaire) et accepte de changer la version de Python du venv de
`BackEnd/` pour ça — voir procédure ci-dessous. Claude vision reste
disponible en repli (`OCR_ENGINE=claude` dans `.env`) si PaddleOCR déçoit
en pratique sur de l'écriture manuscrite réelle (raison qui avait motivé
le choix initial de Claude comme moteur par défaut).

### ⚠️ Prérequis avant de redéployer sur l'OptiPlex : changer la version de Python du venv

`paddlepaddle` (le framework sous-jacent à `paddleocr`) n'a de wheels que
jusqu'à **Python 3.13** au moment de l'écriture (confirmé sur PyPI :
`paddlepaddle==3.3.1` fournit des wheels `cp38` à `cp313`, rien pour
`cp314`) — alors que le venv actuel de Cédric est en **Python 3.14**.
`paddleocr` lui-même (le wrapper) a commencé à annoncer un support
Python 3.13/3.14, mais ça ne sert à rien sans un `paddlepaddle`
installable dessous.

Recréer le venv en Python 3.13 (Debian/Ubuntu — adapter selon la distro
réelle de l'OptiPlex) :

```bash
# Si python3.13 n'est pas déjà disponible :
sudo apt update && sudo apt install python3.13 python3.13-venv
# (à défaut de paquet système, voir deadsnakes PPA ou pyenv)

cd ~/GhostCards/BackEnd
mv .venv .venv-py314.bak   # garder l'ancien au cas où, à supprimer une fois validé
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # inclut désormais paddlepaddle + paddleocr
```

Puis mettre à jour `WorkingDirectory`/le venv utilisé par
`ghostcards.service` si le chemin de l'interpréteur y est fixé en dur
(voir `BackEnd/deploy/ghostcards.service`), et redémarrer le service.

**Premier appel OCR = téléchargement des modèles** : PaddleOCR télécharge
ses modèles de détection/orientation/reconnaissance au premier usage
(mis en cache hors dépôt, par PaddleX). Ça nécessite un accès réseau la
première fois et peut prendre une minute ou deux — normal, pas un bug.

**Non vérifié dans ce sandbox** : l'appel réel à PaddleOCR (`ocr_image_paddleocr`
dans `Services/ocr.py`) n'a pas pu être testé ici — l'installer aurait
consommé plusieurs centaines de Mo sur un disque déjà proche de zéro
espace libre côté machine de dev Windows, et de toute façon Linux/Windows
n'ont pas les mêmes wheels. Le code suit la doc officielle PaddleOCR 3.x
(`PaddleOCR(lang="fr", ...).predict(chemin)`, lecture de
`res.json["rec_texts"]`), mais **à valider avec une vraie photo de
cahier sur l'OptiPlex** avant de considérer le sujet clos — la forme
exacte du résultat a un peu varié entre versions de PaddleOCR/PaddleX,
`ocr_image_paddleocr` gère les deux formes vues dans la doc mais ça
reste à confirmer en conditions réelles.

**Schéma** (`Services/schema.sql` + migrations via `_ensure_column` dans
`Services/db.py::init_db`) :
- Nouvelle table `traitements` (historique append-only : chaque tentative,
  y compris une relance, crée une nouvelle ligne plutôt que d'écraser la
  précédente).
- `eleves.role` (`'eleve'` par défaut) — pour passer Cédric en admin :
  `UPDATE eleves SET role='admin' WHERE email='...'` après sa première
  connexion Google (pas d'UI de gestion des rôles, ce n'est pas prévu).
- `notes_eleves.statut` (`'pret'` | `'traitement'` | `'echec'`).
- `documents.texte_extrait` (cache du texte/OCR pour un document Pronote).

**`Services/ocr.py`** : `extract_pdf_text`, `count_pdf_pages`,
`is_text_sparse` (heuristique : PDF scanné si < 40 caractères/page via
pdftotext), `pdf_to_images` (pdftoppm), `ocr_image_claude`,
`ocr_image_paddleocr` (lazy import, lève `OcrError` explicite si absent),
`transcribe_document`, `transcribe_note`, `relancer_traitement`. Chaque
orchestrateur journalise dans `traitements` via le context manager interne
`_log_traitement` (durée, succès/échec, résultat) — c'est ce qui permet la
relance et le diagnostic. `transcribe_document` bascule automatiquement
sur l'OCR image si `pdftotext` renvoie un texte trop pauvre (PDF scanné).

**`BackEnd/app/main.py`** :
- `POST /api/cours/{id}/notes/photo` (multipart, PDF/PNG/JPEG/WebP),
  traité en `BackgroundTasks`. Nécessite `python-multipart` — **ajouté à
  `requirements.txt`, à réinstaller dans le venv de l'OptiPlex avant le
  prochain redémarrage du service** (sinon `ModuleNotFoundError` au
  démarrage, cf. bugs connus plus bas).
- `GET /api/traitements`, `GET /api/traitements/{id}`, `POST
  /api/traitements/{id}/relancer` — réservés aux admins (`_require_admin`,
  403 sinon).
- `/api/me` renvoie désormais `role`.

**Frontend (`FrontEnd/src/App.jsx`)** : item de nav "Traitements" (si
`me.eleve?.role === 'admin'`), écran liste + détail (résultat/erreur,
bouton Relancer). Dans `CoursDetail` : bouton "Photo / PDF" à côté du
formulaire texte ; les notes affichent un badge "Transcription en cours…"
ou "Échec" selon `statut`, avec poll sur `GET /api/cours/{id}` toutes les
4s tant qu'une note est `'traitement'`.

**Vérifié dans ce sandbox (pas sur l'OptiPlex)** : migrations (`role`,
`statut`, `texte_extrait`, table `traitements`), autorisations admin
(401/403), upload + orchestration OCR (succès et échec, PDF natif vs
scanné, note en échec), endpoint de relance — via un venv Python 3.13
jetable et `fastapi.testclient.TestClient`, avec Pronote/Anthropic/OCR
mockés. Frontend vérifié dans le navigateur (build de prod servi par
FastAPI, session admin simulée par cookie signé) : nav admin, écran
Traitements (liste/détail/relance réels), les trois statuts de note
(prête/en cours/échec) en desktop et mobile, clair et sombre. **Pas encore
testé sur l'OptiPlex avec un vrai PDF scanné ni une vraie photo de
cahier** — à faire à la prochaine synchro/dépôt réel, avec une vraie clé
`ANTHROPIC_API_KEY`.

## État — pas commencé

- **Génération IA (résumés/flashcards/quiz)** (`Services/ia_generation.py`
  n'existe pas encore, seule la config existe : `OLLAMA_URL`,
  `OLLAMA_MODEL` (`qwen3:14b`), `FLASHCARDS_PAR_COURS`,
  `QUESTIONS_QUIZ_PAR_COURS`, `IA_TEXTE_MAX_CHARS`). Doit s'appuyer sur
  Ollama en local (`Services/config.py` explique pourquoi : gros volume,
  gratuit, privé — contrairement à l'assistant conversationnel qui reste
  sur l'API Anthropic). Cédric a un script bash qui fait déjà ça
  manuellement (`flashcard.sh` + un bot Telegram `pdf_drop_bot.py`,
  partagés en exemple dans la conversation d'origine, PAS repris tels
  quels mais qui montrent le pattern d'appel Ollama qui fonctionne chez
  lui : `curl .../api/generate` avec `format: "json"`, `think: false`).
- **Exposition hors LAN** (nom de domaine + HTTPS + reverse proxy) —
  nécessaire pour que la connexion Google fonctionne pour les élèves
  depuis chez eux. Voir `Services/README.md`.
- Export flashcards compatible Anki (mentionné dans le cahier des charges
  d'origine, jamais abordé).
- Espace enseignant (explicitement hors scope v1 dans le cahier des
  charges d'origine).

## Bugs déjà rencontrés et corrigés (ne pas réintroduire)

- `load_dotenv()` n'était jamais appelé dans `config.py` malgré
  `python-dotenv` installé → `.env` silencieusement ignoré. Corrigé :
  `load_dotenv(BASE_DIR / ".env")` explicite en haut de `config.py`.
- Ordre des routes FastAPI : `/api/cours/{cours_id}` déclarée avant
  `/api/cours/recents` capturait "recents" comme un id → 422. Toute
  nouvelle route à segment fixe doit être déclarée AVANT une route à
  paramètre du même préfixe.
- `StaticFiles` monté sur `/` doit être ajouté **en dernier** dans
  `main.py` (après toutes les routes `/api/...`), sinon il les
  intercepte toutes (`Mount("/")` matche n'importe quel chemin).
- `pronotepy.create_login` (CLI officiel) casse si le JSON du QR code est
  collé sur plusieurs lignes (`input()` ne lit qu'une ligne) — remplacé
  par `Services/scripts/first_login.py`, qui lit un fichier.
- Dépendances ajoutées à `requirements.txt` en cours de route
  (`anthropic`, `pydantic`, `authlib`, `itsdangerous`) doivent être
  réinstallées dans le venv avant redémarrage du service — cause
  classique de `ModuleNotFoundError` au démarrage systemd.
- `CREATE TABLE IF NOT EXISTS` ne modifie jamais une table déjà créée :
  toute nouvelle colonne sur une table existante doit passer par le
  helper `_ensure_column` dans `Services/db.py`, pas juste être ajoutée
  au `CREATE TABLE` dans `schema.sql`.

## Conventions établies pendant la session

- Toute modification de schéma sur une table déjà existante = migration
  via `_ensure_column`, jamais en supposant que `schema.sql` suffit.
- Toute nouvelle route FastAPI à segment fixe (ex. `/recents`, `/notes`)
  doit être déclarée avant une route à paramètre du même préfixe.
- Avant de livrer du code, il a été systématiquement testé dans ce
  sandbox : `python3 -m py_compile`, `fastapi.testclient.TestClient` pour
  le backend (y compris en simulant le `cwd` exact de systemd), et
  Playwright (Chromium headless, déjà installé) pour des captures d'écran
  réelles du frontend buildé — mobile/desktop, thème clair/sombre,
  connecté/déconnecté. Recommandé de garder ce niveau de vérification
  dans Claude Code plutôt que de livrer du code non exécuté.
- Secrets déjà partagés en clair dans la conversation (token Pronote,
  token bot Telegram) ont été signalés comme à régénérer plutôt que
  réutilisés tels quels.

## Pour repartir tout de suite

L'OCR (voir section "État — fonctionnel et testé" ci-dessus) est
implémenté et vérifié en sandbox, mais **pas encore déployé ni testé sur
l'OptiPlex**. Avant de l'utiliser en vrai :
1. `git pull` sur l'OptiPlex (le dépôt est maintenant sur
   `github.com/Back2CodeLabs/GhostCards` — voir section Versioning).
2. **Recréer le venv en Python 3.13** (voir "Prérequis" ci-dessus) — le
   venv actuel est en Python 3.14, incompatible avec `paddlepaddle`.
3. Dans le nouveau venv : `pip install -r requirements.txt` (inclut
   maintenant `python-multipart`, `paddlepaddle`, `paddleocr`).
4. Redémarrer `ghostcards.service` — `init_db()` applique les migrations
   automatiquement au démarrage.
5. Passer son propre compte en admin : `UPDATE eleves SET role='admin'
   WHERE email='...'` dans `data/ghostcards.db`.
6. Tester avec un vrai PDF Pronote scanné et une vraie photo de cahier,
   en vérifiant l'écran "Traitements" (nav admin) pour voir le résultat
   réel de l'OCR PaddleOCR — pas juste le chemin heureux simulé en
   sandbox. Si la qualité déçoit sur du manuscrit, basculer
   `OCR_ENGINE=claude` dans `.env` et relancer les traitements en échec.

Prochain chantier logique une fois l'OCR validé en réel : la génération IA
(résumés/flashcards/quiz via Ollama, `Services/ia_generation.py` —
section "État — pas commencé").
