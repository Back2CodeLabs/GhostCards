# Ghost School — Passation (état au 13 septembre 2026)

Ce document résume tout ce qu'il faut savoir pour reprendre le projet dans
Claude Code sans repartir de zéro ni recasser ce qui fonctionne déjà. Les
`README.md` (racine, `BackEnd/`, `Services/`) restent la doc de référence
pour l'installation et l'usage — ce fichier-ci est plutôt le "journal de
bord" des décisions et de l'état d'avancement. Sections dans l'ordre
chronologique des sessions ; la plus récente (13 septembre) est la plus
fiable si une section plus ancienne semble la contredire — l'appli a
beaucoup changé depuis le tout début du projet (ex. connexion Google →
pairage Pronote par élève, une seule classe → plusieurs).

## Qui, quoi

Cédric construit Ghost School pour sa classe — au départ une seule classe
(2F), l'appli gère maintenant plusieurs classes en parallèle sur la même
instance (2F et 2E au 13 septembre) : synchro Pronote (chaque élève avec
son propre compte), révision par flashcards/quiz générés par IA, notes
collaboratives. Auto-hébergé sur son OptiPlex personnel (Linux), exposé en
HTTPS sur `ghostschool.app` depuis le 12 septembre.

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

**Seul le venv de `BackEnd/` doit passer en Python 3.13** — pas besoin de
changer le `python3` par défaut du système : `ghostcards.service` pointe
sur `.venv/bin/uvicorn`, pas sur `/usr/bin/python3`.

Procédure complète : voir la réponse détaillée donnée dans la conversation
du 8 septembre 2026 (déploiement via PuTTY + WinSCP) — récapitulée ici :
1. Backup + arrêt du service.
2. Installer `python3.13` (deadsnakes si Ubuntu, sinon pyenv).
3. Déposer le code (WinSCP, en excluant `.git`, `.venv*`,
   `__pycache__`, `FrontEnd/node_modules`, `FrontEnd/dist`, et **sans
   jamais toucher** `BackEnd/.env`, `BackEnd/secrets/`, `BackEnd/data/`
   côté OptiPlex).
4. Recréer `BackEnd/.venv` avec `python3.13`, `pip install -r requirements.txt`.
5. `npm install && npm run build` dans `FrontEnd/`.
6. Ajouter `ADMIN_PASSWORD=...` dans `.env` (génère-en un avec
   `python3 -c "import secrets; print(secrets.token_urlsafe(16))"`).
7. `sudo systemctl daemon-reload && sudo systemctl restart ghostcards`
   (le fichier `.service` n'a pas besoin de changer : il référence
   `.venv/bin/...`, qui reste le même chemin).
8. Se connecter en admin via le petit bouton bouclier dans l'en-tête du
   site, puis test réel (photo de cahier + écran Traitements admin).

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
- `/api/me` renvoie désormais `{"eleve": {...}|null, "is_admin": bool}`
  (toujours 200, plus jamais 401 — les deux informations sont
  indépendantes, voir ci-dessous).

**Authentification admin — révisée le 8 septembre 2026, totalement
séparée des comptes élèves.** Premier jet : un champ `eleves.role`
promouvant automatiquement le premier compte Google connecté en admin.
**Rejeté par Cédric** : il ne veut *aucun* mécanisme par lequel un compte
élève pourrait devenir admin, même indirectement/accidentellement.
Remplacé par un compte admin indépendant, à mot de passe, sans lien avec
Google ni la table `eleves` :
- `Services/config.py::ADMIN_PASSWORD` (depuis `.env`, vide = connexion
  admin désactivée).
- `POST /auth/admin-login` (`{"password": "..."}`, comparaison en temps
  constant via `secrets.compare_digest`) → `request.session["is_admin"] =
  True`. `POST /auth/admin-logout` la retire.
- `_require_admin` vérifie `request.session.get("is_admin")`, plus du
  tout `eleve.role`.
- `/auth/logout` (déconnexion élève) ne vide plus que `eleve_id` de la
  session (`request.session.pop`, pas `.clear()`) pour ne pas
  déconnecter un admin en même temps, et réciproquement.
- La colonne `eleves.role` n'est plus créée pour les nouvelles installs
  (retirée de `init_db`) — elle peut rester présente, inutilisée, sur une
  base déjà migrée avec l'ancienne version, sans conséquence.

**Frontend (`FrontEnd/src/App.jsx`)** : `useMe` expose `eleve` et
`isAdmin` séparément (plus plate que la réponse API, mais deux champs
distincts, jamais couplés) + `adminLogin`/`adminLogout`. Petit bouton
bouclier dans l'en-tête (`AdminControl`, à côté du bouton de connexion
Google) ouvrant `AdminLoginScreen` (mot de passe uniquement). Nav
"Traitements" visible si `me.isAdmin`. Un `useEffect` sur `isAdmin`
ramène sur l'accueil si l'admin se déconnecte pendant qu'il consulte
l'onglet Traitements (sinon onglet fantôme, plus dans la nav mais encore
sélectionné → écran vide ; bug trouvé et corrigé pendant la vérification
navigateur). Dans `CoursDetail` : bouton "Photo / PDF" à côté du
formulaire texte ; les notes affichent un badge "Transcription en cours…"
ou "Échec" selon `statut`, avec poll sur `GET /api/cours/{id}` toutes les
4s tant qu'une note est `'traitement'`.

**Vérifié dans ce sandbox (pas sur l'OptiPlex)** : migrations (`statut`,
`texte_extrait`, table `traitements`), connexion/déconnexion admin par
mot de passe (bon/mauvais mdp, `ADMIN_PASSWORD` non configuré →  erreur
claire), indépendance totale eleve/admin (`/api/me` renvoie les deux
séparément, se (dé)connecter de l'un ne touche pas l'autre), upload +
orchestration OCR (succès et échec, PDF natif vs scanné, note en échec),
endpoint de relance — via un venv Python 3.13 jetable et
`fastapi.testclient.TestClient`, avec Pronote/Anthropic/OCR mockés.
Frontend vérifié dans un vrai navigateur (build de prod servi par
FastAPI) : connexion admin par mot de passe réelle (mauvais mdp rejeté,
bon mdp accepté), nav admin, écran Traitements (liste/détail/relance
réels), les trois statuts de note (prête/en cours/échec) en desktop et
mobile, clair et sombre. **Pas encore
testé sur l'OptiPlex avec un vrai PDF scanné ni une vraie photo de
cahier** — à faire à la prochaine synchro/dépôt réel, avec une vraie clé
`ANTHROPIC_API_KEY`.

## État — fonctionnel et testé (suite de la session du 8 septembre 2026, deuxième partie)

**Génération IA (résumés/flashcards/quiz)**, implémentée dans
`Services/ia_generation.py`. Suit le pattern qui fonctionne déjà chez
Cédric (`Temp/flashcard.sh`, jamais commité — script perso partagé en
référence pour cette session, contient un token à ne pas réutiliser) :
`POST {OLLAMA_URL}/api/generate` avec `format: "json"`, `think: false`,
`stream: false`, prompt = contenu du cours suivi des instructions (dans
cet ordre, comme chez lui). **Timeout à 1800s** — qwen3:14b en CPU peut
prendre jusqu'à ~30 min sur un cours complet, observé en pratique par
Cédric ; un timeout plus court aurait fait échouer des générations
légitimes.
- Résultat stocké directement sur la ligne `cours` (colonnes `ia_statut`
  `'absent'|'en_cours'|'pret'|'echec'`, `ia_resume`, `ia_flashcards` et
  `ia_quiz` en JSON texte, `ia_erreur`) plutôt que dans une table séparée
  — une génération remplace la précédente, `GET /api/cours/{id}` les
  décode et les renvoie sans changement d'API. Migration via
  `_ensure_column`, comme le reste.
- `POST /api/cours/{id}/generer` — ouvert à tout le monde (pas de
  connexion requise, comme le reste de la consultation), no-op si déjà
  `en_cours`. **Piège trouvé et corrigé pendant la vérification
  navigateur** : le statut `en_cours` doit être posé de façon
  **synchrone** dans l'endpoint, avant de planifier la tâche de fond —
  sinon le premier rechargement du frontend (juste après la réponse HTTP)
  peut arriver avant que la tâche n'ait eu la main, ne jamais voir passer
  `en_cours`, et rester bloqué sur l'affichage précédent (le polling
  frontend ne se déclenche que sur `ia_statut === 'en_cours'`).
- Journalisé dans `traitements` (type `ia_generation`) comme l'OCR — même
  écran admin, même relance. `relancer_traitement` (dans `ocr.py`)
  dispatch maintenant aussi vers `ia_generation.generer_pour_cours` pour
  `cible_type == 'cours'`, et vers `pronote_sync.sync()` pour
  `cible_type == 'sync'` (voir point suivant).
- Frontend (`CoursDetail`) : remplace l'ancien message statique. Bouton
  "Générer"/"Réessayer"/"Régénérer" selon `ia_statut`, résumé affiché tel
  quel, flashcards en cartes cliquables (réponse masquée par défaut),
  quiz à choix multiple avec retour immédiat (bonne réponse en vert,
  mauvaise en rouge) — pas de score cumulé, gardé simple volontairement.
  Poll toutes les 6s tant que `ia_statut === 'en_cours'` (même effet que
  celui déjà utilisé pour l'OCR des notes).
- Le helper de journalisation (anciennement `ocr._log_traitement`) a été
  déplacé dans `Services/db.py::log_traitement`, partagé par `ocr.py`,
  `ia_generation.py` et référencé par `pronote_sync.py`.

**Synchro Pronote visible dans "Traitements"** : `pronote_sync.sync()`
journalise désormais chaque exécution (manuelle ou programmée toutes les
2h) dans la table `traitements` (type `pronote_sync`, comme l'OCR/l'IA) —
aucun changement d'API ni de frontend nécessaire, l'écran admin existant
les affiche automatiquement (libellé spécial "Synchronisation Pronote"
plutôt que le nom technique). Relançable depuis le même écran.

**Dédoublonnage des fichiers téléchargés** (`Services/pronote_sync.py::_dedupe_blob`) :
chaque pièce jointe est maintenant stockée une seule fois, adressée par
son empreinte sha256, sous `DOCUMENTS_DIR/_blobs/`. Chaque cours/devoir
garde son propre chemin lisible (`chemin_local` reste unique par ligne
`documents`, aucune migration de schéma nécessaire) mais ce chemin est un
**lien physique** (`os.link`) vers le blob partagé plutôt qu'une copie —
zéro octet dupliqué sur le disque quand Pronote attache le même fichier à
plusieurs cours. Repli en copie normale si les liens physiques ne sont
pas disponibles (ex. montage réseau). Vérifié : deux cours partageant le
même contenu produisent un seul blob et deux `documents` distincts, tous
deux lisibles avec le bon contenu.

**Liste des élèves en admin** (`GET /api/eleves`, écran "Élèves" dans la
nav admin) : comptes Google déjà connectés, avec nombre de notes
déposées et date de dernière connexion. Lecture seule, pas de gestion de
rôle (l'admin reste un compte séparé, voir plus bas — jamais question
qu'un élève devienne admin).

**Aperçu des PDF/photos (demandé le 9 septembre 2026)** : jusque-là, le
seul clic possible sur un document ou une note photo/PDF forçait un
téléchargement (`Content-Disposition: attachment`) — pas de moyen de le
voir sans le sauvegarder. Ajouté : `GET /api/documents/{id}/apercu` et
`GET /api/notes/{id}/apercu`, qui servent le même fichier avec
`Content-Disposition: inline` (paramètre `content_disposition_type`
de `FileResponse`, Starlette) — le PDF/l'image s'ouvre nativement dans
le navigateur (nouvel onglet) au lieu d'être proposé au téléchargement.
Les endpoints `/fichier` existants sont inchangés (téléchargement forcé,
conservés pour un bouton dédié). Factorisé dans `_reponse_fichier` (
`BackEnd/app/main.py`). Frontend : la ligne de document a maintenant deux
actions séparées (nom cliquable = aperçu, icône = téléchargement, cette
dernière masquée pour les liens externes) ; chaque note photo/PDF a une
petite icône "voir le fichier d'origine" à côté de sa date. Vérifié en
navigateur réel (l'onglet ouvert affiche bien l'image nativement,
titré "apercu (1×1)" par Chromium, pas une boîte de dialogue de
téléchargement).

**Remarque de Cédric à surveiller** : il a signalé un même PDF présent
sur 2 cours différents d'une matière. Le dédoublonnage (`_dedupe_blob`,
voir ci-dessus) ne s'applique qu'aux fichiers téléchargés *après* son
déploiement — si ce doublon date d'avant, les deux copies existent
toujours séparément sur le disque et ne seront pas fusionnées
automatiquement. Pas de script de nettoyage rétroactif écrit (pas
demandé) — à proposer si Cédric veut récupérer l'espace disque.

## État — fonctionnel et testé (suite du 9 septembre 2026 : suivi détaillé + IA)

**Étapes détaillées dans "Traitements"** (demandé : "il me manque les
différentes étapes et leur résultats, ex. utilisation de pdftotext").
`db.log_traitement` (`Services/db.py`) expose maintenant `ctx.etape(label,
statut=, detail=, duree_ms=, moteur=)`, appelable plusieurs fois pendant
un même traitement — stocké en JSON dans la nouvelle colonne
`traitements.etapes`, visible même si le traitement échoue en cours de
route (utile pour savoir jusqu'où il est allé). Appliqué partout :
- OCR document PDF : étape `pdftotext` puis, si bascule nécessaire,
  `détection` (pourquoi) puis une étape `ocr page N/M` par page.
- OCR note (photo/PDF) : une étape par page.
- Synchro Pronote : étapes `connexion`, `cours`, `devoirs`.
- Génération IA : étapes `lecture du contenu source`, `appel Ollama`,
  `extraction résumés/flashcards/quiz`.
**Piège rencontré** : ne jamais dupliquer le nom du moteur à la fois dans
le libellé de l'étape et via le paramètre `moteur=` — le frontend affiche
déjà `(moteur)` automatiquement à côté du libellé.

**Rendu "pretty" du résultat** (JSON / XML / Markdown) : `ResultatFormatte`
dans `FrontEnd/src/App.jsx` détecte le format et l'affiche en conséquence
— JSON réindenté, XML indenté, Markdown rendu via `MarkdownLite` (titres,
gras/italique, listes, tableaux). Rendu **par éléments React, jamais
`dangerouslySetInnerHTML`** : un texte hostile transcrit depuis une photo
reste inerte, aucun risque d'injection. Pas de nouvelle dépendance npm.

**Temps écoulé** : dates reformatées avec "à" entre date et heure
(`formatDateHeure`), durée en `ms` convertie en "X min Y s" / "X h Y min"
(`formatDuree`). Un traitement `en_cours` affiche un **chrono en direct**
(`useNow`, tick 1s) — utile pour les générations IA qui peuvent tourner
~30 min, pour distinguer "ça tourne encore" de "ça a planté".

**Résumés multiples selon la taille du cours** : le prompt Ollama demande
désormais `resume_court` (2-4 phrases) et `resume_detaille` (longueur
proportionnelle au contenu source, pour ne pas perdre d'éléments
importants sur un gros cours). Stockés dans `cours.ia_resume` (court,
même colonne qu'avant) et la nouvelle colonne `cours.ia_resume_detaille`.
Frontend : résumé court affiché par défaut, bouton "Voir le résumé
détaillé" pour basculer.

**Compléter les flashcards/quiz (+10)** sans tout régénérer :
`ia_generation.completer_pour_cours` (nouveau, type `ia_completion` dans
`traitements`) envoie à Ollama la liste des questions déjà utilisées
(pour éviter les répétitions) et ajoute le résultat aux tableaux
existants — le résumé n'est pas touché. `POST /api/cours/{id}/completer`
(même garde-fou `en_cours` posé de façon synchrone que `/generer`).
**Bug trouvé et corrigé pendant la vérification navigateur** : un échec
de complément faisait disparaître tout le contenu déjà généré (l'écran
bastardait sur `ia_statut === 'echec'`, qui masquait résumé/flashcards/
quiz existants). Corrigé : la condition d'affichage se base sur la
présence de `ia_resume` plutôt que sur `ia_statut`, avec un message
d'erreur discret sous les boutons si la dernière tentative a échoué —
le contenu précédent reste toujours visible.

## État — fonctionnel et testé (suite du 9 septembre 2026 : multi-moteur IA + accès assistant)

**Pourquoi** : question posée — "puisque les élèves se connectent avec
leur compte Google, peut-on utiliser leur Gemini ?". Réponse vérifiée par
recherche web : non, "Sign in with Google" (scopes `openid email
profile`) ne donne aucun accès Gemini — Google l'a confirmé explicitement
pour ses propres outils IA en 2026. Le seul moyen est une clé API perso
créée manuellement sur aistudio.google.com, sans lien avec la connexion —
irréaliste à demander à des collégiens/lycéens. Décision : Gemini reste
possible mais avec **une seule clé, celle de Cédric**, comme pour
Anthropic.

**Trois moteurs IA au choix, Ollama par défaut** (`Services/ia_generation.py`) :
Ollama (local, gratuit), Claude (Anthropic), Gemini (Google). Le choix
et les clés sont **modifiables à chaud depuis l'écran admin
"Paramétrage"** (nouvelle table `parametres`, clé/valeur — voir
`Services/db.py::get_parametre`/`set_parametre`) plutôt que dans `.env` —
pas besoin de redémarrer le service pour changer de moteur ou tourner
une clé. `.env` (`IA_ENGINE`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`GEMINI_MODEL`) ne sert que de valeur de départ avant toute config via
l'interface. Les clés ne sont **jamais renvoyées en clair** par
`GET /api/parametres` (juste `..._configuree: bool`), vérifié par test.
Claude et Gemini ont chacun leur propre clé (pas de réutilisation
implicite) — Claude a sa propre entrée dans le formulaire au même titre
que Gemini.

**L'assistant conversationnel utilise désormais le même moteur configuré**
que la génération (`ia_generation.repondre_conversation`, dispatch par
moteur comme `_appeler_ia`) — avant cette session il était câblé en dur
sur Claude. Adaptations par moteur : Ollama via `/api/chat` (multi-tour,
pas `/api/generate`), Gemini avec le rôle `"model"` pour le tour de l'IA
(pas `"assistant"`), Claude inchangé. Timeout court (60-120s, contre
1800s pour la génération en arrière-plan) — l'élève attend devant son
écran, pas question de le faire patienter 30 min. `main.py::_get_anthropic`
et l'import direct `anthropic` dans `main.py` ont été supprimés (code mort
une fois l'appel déplacé dans `ia_generation.py`).

**Accès à l'assistant restreint** (demandé le 9 septembre 2026) :
désactivé par défaut pour un compte élève (`eleves.assistant_actif`,
défaut 0), activable au cas par cas depuis l'écran admin "Élèves"
(bouton bascule ON/OFF, `PUT /api/eleves/{id}/assistant`). L'admin y a
toujours accès, indépendamment de ce flag. Frontend (`AssistantScreen`) :
écran de verrouillage si non autorisé, avec bouton de connexion Google si
pas encore connecté, ou message "demande à ton professeur" si connecté
mais pas activé.

**Non vérifié en conditions réelles** : les trois moteurs sont testés
avec des mocks (urlopen/Anthropic simulés) — jamais appelés avec de
vraies clés Gemini/Claude. Le endpoint Gemini exact
(`generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`,
header `x-goog-api-key`, `generationConfig.responseMimeType`) et le nom
de modèle par défaut (`gemini-3.5-flash-lite`) viennent d'une recherche
web ciblée (septembre 2026) mais pas d'un appel réel — à confirmer avec
une vraie clé avant de considérer Gemini fiable en prod. Le modèle est
éditable dans l'écran Paramétrage si le nom par défaut est erroné ou
déprécié.

## État — fonctionnel et testé (suite du 10 au 13 septembre 2026 : pairage Pronote par élève, HTTPS, multi-classe, profil)

Session la plus dense du projet à ce jour : passage d'un site à
consultation libre + connexion Google (pour attribuer des notes
déposées) à un site **entièrement verrouillé**, où chaque élève
s'authentifie avec son propre compte Pronote. Puis exposition réelle en
HTTPS, premiers retours d'élèves réels, et enfin support de plusieurs
classes sur la même instance.

### Pairage Pronote par élève (remplace la connexion Google)

Décision prise en mode plan (voir `C:\Users\cbarbotin\.claude\plans\` sur
la machine de Cédric si le fichier existe encore — sinon, l'essentiel est
ici) après avoir constaté que le compte Pronote unique de l'admin ne
voyait pas les groupes (LV2, options) des autres élèves, et qu'aucune
liste blanche par email n'était possible (Cédric ne connaît pas les
adresses de ses camarades). Solution : chaque élève scanne son PROPRE QR
Pronote (même mécanisme que la première connexion admin,
`Services/scripts/first_login.py`), ce qui sert à la fois d'identité
vérifiée (établissement + classe) et de source de synchro pour son propre
groupe.

Points clés (détail complet dans `Services/README.md`, sections
"Authentification élève" et "Profil élève") :
- **Consentement explicite** avant tout pairage : case à cocher après une
  liste précise de ce qui sera récupéré (partagé avec la classe vs gardé
  privé), horodatage enregistré comme preuve
  (`eleves.consentement_pronote_le`).
- **Chiffrement au repos** des identifiants Pronote de chaque élève
  (`Services/crypto_secrets.py`, Fernet, clé `CREDENTIALS_ENCRYPTION_KEY`)
  — délibérément séparé du `credentials.json` en clair de l'admin, vu la
  sensibilité bien supérieure (accès à de vrais comptes scolaires de
  mineurs, multiplié par 36).
- **Synchro multi-comptes** : la boucle de synchro (`Services/
  pronote_sync.py::sync()`) couvre désormais le compte de référence PUIS
  chaque élève pairé, étalés de 5 s (`STAGGER_ELEVES_S`) pour ne pas
  déclencher le rate-limit Pronote ("erreur 25"). Un compte cassé
  (jeton expiré, réseau) n'interrompt jamais les autres — statut/erreur
  par élève visibles dans l'écran admin "Élèves", avec un bouton
  "Re-pairer" qui force une nouvelle connexion.
- **Notes personnelles** (`notes_pronote.eleve_id`) scopées par élève —
  jamais mélangées ; **cours/devoirs/documents** restent partagés classe
  entière, dédupliqués par clé stable (date+heure+matière+professeur, ou
  date+matière+description pour les devoirs — voir plus bas pour la
  correction multi-classe de cette clé).
- **Détection du QR sur une vraie photo de téléphone** : `cv2.
  QRCodeDetector` s'est montré très sensible à la résolution native d'une
  photo réelle (moiré/reflets d'écran), avec des échecs constatés sur deux
  vraies photos fournies par un élève testeur — corrigé par
  `_decoder_qr_image` (`BackEnd/app/main.py`), qui réessaie plusieurs
  tailles de redimensionnement avant d'abandonner. Un lien "Coller le code
  à la place" reste en secours (colle directement le JSON décodé par une
  autre appli). Ajout ensuite d'un vrai recadrage (zone ajustable + zoom,
  `FrontEnd/src/components/CropQr.jsx`) avant l'envoi, pour réduire encore
  les échecs et les données envoyées.
- **Doublons `eleves` constatés en prod** : `pronote_id` (`ClientInfo.id`
  pronotepy) a d'abord été supposé stable pour un même compte réel — FAUX,
  c'est un id de ressource "à usage interne" régénéré à chaque nouvelle
  session/pairage. Un même élève re-pairé (ex. après déconnexion de
  l'appli Pronote côté téléphone) produisait donc une deuxième ligne
  `eleves`. Corrigé : `upsert_eleve_pronote` (`Services/db.py`) matche
  désormais par nom normalisé (classe fermée de élèves connus, homonyme
  extrêmement improbable), avec une migration (`_fusionner_eleves_
  dupliques`) qui fusionne les doublons déjà en base au démarrage — groupe
  désormais par (nom, classe) depuis le passage au multi-classe, pour
  qu'un homonyme entre deux classes différentes ne soit jamais fusionné à
  tort.

### Exposition HTTPS (`ghostschool.app`)

Domaine acheté et pointé vers l'IP publique de la box de Cédric, ports 80
ET 443 redirigés vers l'OptiPlex, Caddy installé et configuré
(`BackEnd/deploy/Caddyfile`) — obtient et renouvelle automatiquement un
certificat Let's Encrypt. **Confirmé fonctionnel** (élève et admin) depuis
le 12 septembre — voir `Services/README.md` pour la procédure complète.

Deux incidents réels rencontrés et résolus pendant la mise en place :
- **Conflit de port 443** entre Caddy et `tailscale serve` (déjà lié à ce
  port, sur l'interface Tailscale, pour un usage tailnet sans rapport) —
  Caddy échouait au démarrage (`bind: address already in use`). Corrigé
  en restreignant Caddy à l'IP réseau locale précise de l'OptiPlex
  (directive `bind` dans le Caddyfile), sans toucher à la config
  Tailscale existante.
- **`.env` corrompu par un octet non-UTF-8** après une édition à la main
  sur l'OptiPlex (déjà documenté ci-dessous dans "Bugs déjà rencontrés") —
  a fait tomber le service entièrement, sans rapport avec le code déployé.

`SESSION_COOKIE_SECURE=true` activé dans `.env` une fois HTTPS confirmé
(marque le cookie de session "Secure" — voir `Services/config.py`,
volontairement pas activé par défaut pour ne pas casser un accès de
diagnostic en HTTP simple avant que HTTPS ne soit en place).

### Premiers retours réels (élèves testeurs)

Une fois déployé, premiers vrais élèves pairés — retours pris en compte :
- **Page d'accueil** : le site plongeait directement dans le formulaire de
  pairage pour un visiteur non connecté, alors qu'un bouton "Se connecter"
  existe déjà dans l'en-tête. Remplacé par une vraie page d'accueil
  (`FrontEnd/src/screens/Landing.jsx`, pitch + bouton), le formulaire ne
  s'affichant plus que sur clic. Salutation personnalisée une fois
  connecté ("Bonjour Prénom" pour un élève, "Bonjour Maître Fantôme" pour
  l'admin — voir `prenomDe`, `FrontEnd/src/components/Shared.jsx`, qui
  isole le prénom du "NOM Prénom" renvoyé par Pronote).
- **Après pairage réussi, l'écran de connexion restait affiché** (jamais
  dépilé de la pile de navigation) — corrigé, même mécanisme que la
  connexion admin.
- **Message d'erreur PIN incorrect peu clair** : une réponse brute de
  pronotepy en anglais ("invalid confirmation code") remontait telle
  quelle — remplacée par un message dédié en français avec l'action à
  faire. Une panne après connexion Pronote réussie (chiffrement, base)
  remontait aussi une erreur 500 muette — message clair côté élève
  désormais, détail complet dans les logs serveur.
- **Interface flashcards/quiz jugée peu "ludique"** (comparée à Duolingo)
  : ajout d'un retournement de carte (question → réponse) au lieu d'un
  changement de contenu brut, d'une barre de progression continue sur
  toute la session (flashcards puis quiz), d'un petit retour visuel
  (check/croix) avant de passer à la carte suivante, et d'une légère
  animation d'entrée sur chaque nouvelle carte (`FrontEnd/src/components/
  ExamMode.jsx`).
- **Génération IA peu découvrable** : un élève ne savait pas que Ghost
  School pouvait générer résumé/flashcards/quiz, reléguée à une petite
  icône dans les listes de cours. Ajout d'un bandeau "Quiz du jour" tout
  en haut de l'accueil (`GET /api/cours/suggestion-ia`), qui met en avant
  un cours déjà prêt à réviser, ou à défaut un cours qu'on peut générer.
  A révélé au passage un vrai bug : un cours avec seulement une
  description (sans document ni note) était traité à tort comme "sans
  contenu" et n'affichait jamais le bouton "Générer" côté frontend, alors
  que le serveur sait très bien générer à partir de la seule description
  — corrigé.
- **Aperçu de lien** (WhatsApp, Discord...) au partage de l'URL : balises
  Open Graph/Twitter + une image dédiée (`FrontEnd/public/og-image.png`,
  générée en reproduisant exactement les couleurs/l'effet de fondu de
  l'en-tête de l'app). Point à savoir : WhatsApp met en cache l'aperçu
  d'un lien déjà partagé une fois — un lien déjà envoyé avant l'ajout des
  balises reste "sans aperçu" tant qu'il n'est pas repartagé avec un
  paramètre différent (ex. `?v=2`), ou revérifié via le Sharing Debugger
  de Facebook ("Scrape Again").

### Support de plusieurs classes (2F, 2E...)

Envisagé après les premiers retours ("j'envisage d'ajouter la classe 2E"),
cadré en mode plan avant de développer vu l'ampleur (comparable au passage
au pairage par élève). Le point de départ : jusque-là, **rien** dans les
tables de contenu partagé (`matieres`/`cours`/`devoirs`/`documents`)
n'avait de notion de classe — tout mélangeait déjà deux classes réelles si
elles avaient existé, avec un vrai risque de collision de déduplication
(voir plus bas).

- **`classe` sur `cours`/`devoirs`** (pas sur `matieres`, qui reste un
  vocabulaire de matières partagé entre classes), dérivée de
  `client.info.class_name` à chaque connexion — recherche confirmée sur
  `pronotepy` : `.lessons()` d'un compte est déjà intrinsèquement scopé à
  son propre établissement/classe, le mélange venait uniquement de la
  fusion faite par Ghost School, pas de la librairie. Pas besoin d'un
  second compte de référence pour 2E : comme pour les groupes, le contenu
  arrive dès qu'un élève de cette classe a pairé son compte.
- **Collision de déduplication corrigée** : la clé des cours (date+heure+
  matière+professeur) et des devoirs (date+matière+description) ne
  contenait pas la classe — deux classes avec le même prof/matière au
  même créneau (plausible dans un vrai emploi du temps) auraient vu leurs
  cours fusionnés à tort. La clé cours utilise maintenant `date` +
  `heure_debut` stockées plutôt que l'isoformat complet de pronotepy — un
  changement qui, en plus de régler la collision, rend la clé
  reconstructible depuis les seules colonnes stockées (nécessaire pour la
  migration des lignes déjà en base sans avoir à resynchroniser).
- **`classes`** (table) remplace l'ancien paramètre `classe_attendue` à
  valeur unique — une vraie liste gérable (Paramétrage → Pronote), avec
  migration automatique au démarrage qui reprend l'ancien réglage pour
  amorcer la liste et retagger les lignes déjà en base.
- **Filtre par classe** sur tous les endpoints de lecture de contenu : un
  élève voit toujours SA classe (jamais un paramètre de requête), un
  admin voit les deux classes mélangées par défaut ou une classe précise
  via un sélecteur (rangée d'onglets sur Accueil/Matières/Élèves,
  toujours visible même avec une seule classe — retour de terrain après
  un premier essai en menu déroulant, moins visible). `GET /api/cours/
  {id}` et les téléchargements de documents vérifient en plus
  l'appartenance à la classe (403 sinon), pour empêcher d'ouvrir le
  contenu d'une autre classe en devinant un id.
- **Élèves** : deuxième rangée d'onglets pour filtrer par groupe (LV2,
  options) une fois une classe sélectionnée, construite à partir des
  groupes réellement constatés chez les élèves de cette classe.

### Matières à exclure (redesign)

L'ancien mécanisme (liste de noms tapés à l'avance, comparés par slug pour
NE PAS importer certains créneaux au sync) avait deux défauts : il fallait
deviner le nom exact avant même que Pronote ne l'ait renvoyé, et il ne
nettoyait jamais rétroactivement ce qui était déjà en base avant
l'exclusion (d'où l'existence, maintenant supprimée, d'un script
`nettoyer_matieres_exclues.py` qui supprimait physiquement les données
correspondantes). Remplacé par une case à cocher par matière **déjà
récupérée** (`matieres.exclue`, Paramétrage → Pronote) : la synchro
ingère désormais tout sans exception, l'exclusion masque seulement
l'affichage (accueil, matières, devoirs, quiz du jour, cours à générer).
Migration automatique une seule fois au démarrage (marqueur en base,
`_migrer_matieres_exclues_defaut`) pour reprendre l'ancien réglage texte —
volontairement une seule fois : sans ce garde-fou, un décochage manuel
plus tard serait défait à chaque redémarrage tant que l'ancien réglage
reste en base.

### Tests automatisés

Première suite de tests persistée dans le dépôt (`BackEnd/tests/`,
pytest — jusque-là, toute vérification se faisait par scripts jetables
dans un répertoire temporaire, jamais commités). Isolation par
`monkeypatch` de `Services.db.DB_PATH`/`Services.crypto_secrets.
CREDENTIALS_ENCRYPTION_KEY` plutôt qu'un process séparé par test : ces
constantes sont des noms de module résolus à l'appel (pas figés à
l'import), donc `monkeypatch.setattr` les redirige correctement sans
sous-processus ni fichiers `.env` de test. Voir `BackEnd/tests/
conftest.py` pour le détail des fixtures, `BackEnd/README.md` section
"Tests" pour la commande.

## État — fonctionnel et testé (13 septembre 2026, suite : génération manuelle v0.6.0)

Un élève peut désormais copier le prompt exact que Ghost School utilise
pour générer résumé/flashcards/quiz (`GET /api/cours/{id}/prompt-manuel`,
même texte source et même consigne que la génération automatique — voir
`Services/ia_generation.py::construire_prompt_generation`/`texte_source`,
mais SANS le découpage propre à Ollama, un outil externe ayant un
contexte largement suffisant), le coller dans sa propre IA (ChatGPT,
Gemini, Claude...) hors Ghost School, puis coller la réponse JSON pour
l'importer (`POST /api/cours/{id}/importer-manuel`) — utile quand Ollama
est trop lent (jusqu'à ~30 min) ou indisponible.

Décisions prises en mode plan avant de développer :
- **Contenu partagé avec la classe**, pas un espace personnel séparé —
  mêmes colonnes `cours.ia_resume`/`ia_flashcards`/`ia_quiz` que la
  génération automatique ; `cours.ia_origine` ('app' | 'import') distingue
  les deux, purement informatif (badge), sans changer aucune règle de
  filtrage.
- **Toujours une validation admin avant application**, cours vierge ou
  non — contrairement à une première génération automatique (qui part
  immédiatement) : ce texte n'est jamais passé par le prompt contrôlé de
  Ghost School, un élève peut coller absolument n'importe quoi. Réutilise
  le circuit déjà en place pour la régénération (`traitements`, type
  `import_demande` à côté de `regeneration_demande`, mêmes endpoints
  `/api/traitements/demandes/{id}/valider|rejeter` généralisés) — sauf
  que le contenu à appliquer est déjà connu et validé au moment de la
  demande (`resultat` rempli dès la création), donc l'admin le relit
  (`ResultatFormatte` le met déjà en forme, aucun changement nécessaire)
  avant de décider, et la validation n'a pas besoin de relancer un appel
  modèle — juste d'écrire le contenu déjà stocké (`Services/
  ia_generation.py::importer_manuel`).
- **Désactivée par défaut pour chaque élève** (`eleves.generation_
  manuelle_actif`), comme l'assistant IA — activable au cas par cas
  depuis l'écran admin "Élèves" (`_peut_generer_manuellement`, copie
  conforme de `_peut_utiliser_assistant`).

Le JSON collé n'est contraint par AUCUN mode JSON de modèle (contrairement
à Ollama/Gemini en mode forcé) : une vraie validation de forme a été
ajoutée pour l'occasion (`Services/ia_generation.py::valider_forme_
generation` — vérifie chaque clé/type, flashcards/quiz non vides, options
au nombre de 4, `reponse_index` dans les bornes), là où la génération
automatique ne validait jusque-là RIEN de la forme (un modèle en mode JSON
forcé produit une forme correcte par construction). Le parsing tolérant
déjà écrit pour Claude (extraction d'un JSON entouré de texte parasite,
balises markdown, phrase d'intro...) a été extrait en fonction
réutilisable (`parser_json_ia`, ex-`_appeler_claude` inline) plutôt que
dupliqué.

Bug trouvé et corrigé au passage : l'écran Traitements affichait un
bouton "Relancer" sur le détail de N'IMPORTE QUEL traitement (y compris
une demande en attente), qui déclenchait en réalité une génération
immédiate via `ocr.relancer_traitement` en contournant tout le circuit de
validation. Resté invisible jusqu'ici car aucune demande n'était
cliquable vers son détail — le problème n'est apparu qu'en rendant les
demandes d'import cliquables (nécessaire pour que l'admin puisse
prévisualiser le contenu avant de le valider). Masqué pour les deux types
de demande (`regeneration_demande`, `import_demande`), qui n'ont pas de
notion de "relance" — seulement valider/rejeter.

## État — pas commencé

- ~~**Exposition hors LAN**~~ — fait (2026-09-12) : domaine
  `ghostschool.app`, HTTPS via Caddy/Let's Encrypt, `SESSION_COOKIE_SECURE
  =true`. Voir section "État — fonctionnel et testé" ci-dessus et
  `Services/README.md`, section "Exposer le site hors du réseau local".
- Export flashcards compatible Anki (mentionné dans le cahier des charges
  d'origine, jamais abordé).
- Espace enseignant (explicitement hors scope v1 dans le cahier des
  charges d'origine).
- **Durcissement de la connexion admin** (demandé le 8 septembre 2026,
  pas encore implémenté) : bloquer après 5 tentatives infructueuses
  (compteur + fenêtre de temps à définir — par IP ? par session ? à
  trancher), et ajouter un second facteur TOTP (bibliothèque `pyotp`
  côté serveur, ex. `qrcode` pour l'enrôlement initial via un flux
  d'appairage — Google Authenticator/Authy compatibles). S'ajoute au
  mot de passe `ADMIN_PASSWORD` déjà en place (`Services/config.py`,
  `POST /auth/admin-login`), ne le remplace pas.
- **Outil admin de recherche de doublons** (demandé le 9 septembre 2026,
  pas encore implémenté) : un bouton dans l'écran admin qui scanne
  `data/documents/` (ou la table `documents` par empreinte sha256, voir
  `_dedupe_blob` dans `pronote_sync.py`) et propose, pour chaque doublon
  trouvé, une comparaison (aperçu des deux fichiers/cours concernés) puis
  un choix : suppression totale (fichier + ligne `documents`), suppression
  partielle (fichier physique seulement, en reliant la ligne restante vers
  l'exemplaire conservé), ou repointer `chemin_local` d'un doublon vers
  l'autre sans rien supprimer. Sert notamment à nettoyer les doublons
  antérieurs au dédoublonnage automatique (celui-ci ne s'applique qu'aux
  fichiers téléchargés après son déploiement, voir plus haut).

- **Gamification** (streaks/XP/ligues, retour de Valentin le 13 septembre
  2026) : volontairement mise en attente le temps d'avoir plus de retours
  de la classe — la ligue/leaderboard en particulier mérite une décision
  de principe avant de développer (comparer les scores de 36 ados de
  15-16 ans peut créer une pression sociale non désirée), indépendamment
  de l'effort technique.
- **Synchro Pronote proxifiée par l'appareil de chaque élève** (question
  posée le 13 septembre 2026, à titre préventif — aucun souci constaté).
  Pas réaliste tel quel (`pronotepy` est du Python côté serveur, pas
  portable en PWA) ; la seule version faisable serait un tunnel réseau
  inverse (l'OptiPlex garde tout le code, mais fait transiter ses
  requêtes Pronote via une connexion ouverte depuis le téléphone de
  l'élève, pour que ça apparaisse venir de son IP plutôt que de
  l'OptiPlex). Pas entrepris : résoudrait un problème pas encore observé
  (aucune erreur de rate-limit dans `sync_log`/`traitements` depuis le
  pairage multi-comptes, l'étalement de 5 s entre comptes semble
  suffire), pour une fiabilité moindre (un téléphone endormi/hors wifi
  casserait silencieusement la synchro de cet élève, contraintes
  d'exécution en arrière-plan iOS/Android). À reconsidérer seulement si
  Pronote se met vraiment à bloquer/ralentir l'OptiPlex.

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
- `.env` édité à la main sur l'OptiPlex avec un octet non-UTF-8 (accent
  collé/tapé via un éditeur en Windows-1252/Latin-1) → `load_dotenv()`
  plante au démarrage (`UnicodeDecodeError`, service en échec immédiat,
  aucun rapport avec le code déployé). Repérer la ligne fautive avec
  `grep -n -P '[\x80-\xFF]' BackEnd/.env`, puis reconvertir tout le
  fichier : `iconv -f WINDOWS-1252 -t UTF-8 BackEnd/.env -o /tmp/env.utf8
  && mv /tmp/env.utf8 BackEnd/.env`.
- `ClientInfo.id` (pronotepy, exposé comme `pronote_id` côté Ghost
  School) supposé à tort stable pour un même élève réel — c'est un id de
  ressource interne à la session, régénéré à chaque nouveau pairage (ex.
  après déconnexion de l'appli Pronote côté téléphone). Provoquait une
  deuxième ligne `eleves` (doublon) à chaque re-pairage. Corrigé :
  `upsert_eleve_pronote` matche par nom normalisé plutôt que par
  `pronote_id`, et `_fusionner_eleves_dupliques` (appelée depuis
  `init_db()`) fusionne au démarrage les doublons déjà en base — groupée
  par `(nom, classe)` depuis le multi-classe, pour ne jamais fusionner un
  homonyme de deux classes différentes.
- **Trouvé en écrivant `BackEnd/tests/test_pairage.py`** (le premier essai
  du test faisait apparaître un doublon là où le test s'attendait à une
  mise à jour) : `upsert_eleve_pronote` comparait les noms via
  `lower(trim(nom))` **côté SQL** — `lower()` de SQLite est ASCII
  uniquement, donc un nom avec une majuscule accentuée (ex. "Éléonore") ne
  se matchait jamais avec lui-même d'un pairage à l'autre, créant
  exactement le doublon que la correction ci-dessus visait à éliminer. En
  plus, cette comparaison ne tenait pas compte de la classe (contrairement
  à `_fusionner_eleves_dupliques`), donc un homonyme entre 2F et 2E aurait
  pu faire écraser la ligne de l'un par le pairage de l'autre. Corrigé en
  comparant nom ET classe en Python (`.strip().lower()`, qui replie
  correctement l'unicode) plutôt qu'en SQL.
- Détection du QR Pronote (`cv2.QRCodeDetector`) fiable sur un JSON généré
  en sandbox mais en échec sur de vraies photos de téléphone (moiré/reflet
  d'écran selon la résolution native). Corrigé par `_decoder_qr_image`
  (`BackEnd/app/main.py`) qui réessaie plusieurs tailles de
  redimensionnement avant d'abandonner, plus un recadrage manuel côté
  frontend (`CropQr.jsx`) avant l'envoi.
- Caddy refusait de démarrer (`bind: address already in use`) sur le port
  443 : déjà occupé par `tailscale serve`, actif sur l'interface Tailscale
  pour un usage sans rapport. Corrigé en restreignant Caddy à l'IP réseau
  locale précise de l'OptiPlex (directive `bind` du Caddyfile), sans
  toucher à la configuration Tailscale existante.

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
- Le numéro de version (`FrontEnd/package.json`, champ `version`, source
  de vérité unique — injecté au build par `vite.config.js`) et une
  nouvelle entrée `CHANGELOG.md` sont incrémentés à chaque publication
  réelle sur l'OptiPlex (pas à chaque commit) — sert à recouper un bug
  signalé avec la version effectivement déployée à ce moment-là. Une
  demande d'ajustement mineur d'une fonctionnalité déjà livrée est
  intégrée dans la version en cours ("0.5.1" par ex.) plutôt que de
  déclencher un nouveau numéro mineur ; un chantier structurant nouveau
  (multi-classe, pairage Pronote) mérite son propre numéro mineur, décidé
  en amont en mode plan.

## Pour repartir tout de suite

Tout ce qui suit est déployé et fonctionnel sur l'OptiPlex à la date du
13 septembre 2026 : pairage Pronote par élève (plus de connexion
Google), OCR PaddleOCR, génération IA multi-moteur, HTTPS sur
`ghostschool.app`, et le support de plusieurs classes (2F, 2E). Pour
reprendre le travail :

1. `git pull` sur l'OptiPlex (`github.com/Back2CodeLabs/GhostCards`,
   branche utilisée pour les déploiements — voir la section Versioning
   plus haut).
2. Réinstaller les dépendances si `requirements.txt` a changé depuis le
   dernier déploiement (`pip install -r requirements.txt` dans le venv
   existant) — voir "Bugs déjà rencontrés" pour le piège classique
   `ModuleNotFoundError` si cette étape est oubliée.
3. Si le frontend a changé : `cd FrontEnd && npm install && npm run
   build`.
4. Redémarrer `ghostcards.service` (`sudo systemctl restart
   ghostcards`) — `init_db()` applique automatiquement toute nouvelle
   migration de schéma au démarrage, rien à faire à la main sur la base.
5. Vérifier l'écran admin "Traitements" après un premier cycle de sync
   pour confirmer qu'il n'y a pas d'erreur nouvelle (compte Pronote
   cassé, rate-limit), et l'écran "Paramétrage" pour confirmer que la
   liste des classes et les clés IA sont toujours celles attendues.

La version 0.6.0 (génération manuelle hors Ghost School par l'élève, avec
sa propre IA, puis import du résultat — voir la section dédiée dans "État
— fonctionnel et testé" ci-dessus) est développée et vérifiée en sandbox
(pytest + navigateur) au 13 septembre 2026, mais **pas encore déployée
sur l'OptiPlex** : suivre les étapes ci-dessus (`git pull`, dépendances,
build frontend, redémarrage du service) une fois prête à publier, avec
une nouvelle entrée `CHANGELOG.md` passant de "en cours" à une date réelle.
