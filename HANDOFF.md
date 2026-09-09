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

## État — pas commencé

- **Exposition hors LAN** (nom de domaine + HTTPS + reverse proxy) —
  nécessaire pour que la connexion Google fonctionne pour les élèves
  depuis chez eux. Voir `Services/README.md`.
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
5. Définir `ADMIN_PASSWORD` dans `.env`, puis se connecter en admin via
   le bouton bouclier dans l'en-tête du site (indépendant des comptes
   élèves Google — voir section Authentification admin ci-dessus).
6. Tester avec un vrai PDF Pronote scanné et une vraie photo de cahier,
   en vérifiant l'écran "Traitements" (nav admin) pour voir le résultat
   réel de l'OCR PaddleOCR — pas juste le chemin heureux simulé en
   sandbox. Si la qualité déçoit sur du manuscrit, basculer
   `OCR_ENGINE=claude` dans `.env` et relancer les traitements en échec.

Prochain chantier logique une fois l'OCR validé en réel : la génération IA
(résumés/flashcards/quiz via Ollama, `Services/ia_generation.py` —
section "État — pas commencé").
