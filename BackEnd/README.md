# Ghost School — BackEnd

API HTTP (FastAPI) de Ghost School : sert au frontend les données préparées
par `Services/` (cours, documents, résumés, flashcards, quiz), et sert le
frontend buildé en statique une fois `npm run build` lancé côté `FrontEnd/`.

Voir [`../README.md`](../README.md) pour la vue d'ensemble, et
[`../Services/README.md`](../Services/README.md) pour le pairage/synchro
Pronote, le multi-classe, la génération IA et l'exposition HTTPS.

## Installation

```bash
cd BackEnd
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Édite `.env` et renseigne au minimum `PRONOTE_URL` (l'URL affichée dans le
navigateur quand tu es connecté à Pronote, du type
`https://XXXXXXXX.index-education.net/pronote/eleve.html`),
`SESSION_SECRET_KEY` et `CREDENTIALS_ENCRYPTION_KEY` (génération indiquée en
commentaire dans `.env.example` — la seconde chiffre au repos les
identifiants Pronote de chaque élève, sensible car accès direct à un compte
scolaire réel de mineur).

Puis suis [`../Services/README.md`](../Services/README.md) pour la première
connexion à Pronote (compte de référence, admin) et un premier test de
synchronisation, avant de lancer l'API.

## Lancer l'API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(`--reload` en développement pour recharger automatiquement au fil des
modifications.)

L'API tourne alors sur `http://<ip-de-l-optiplex>:8000`, accessible depuis
n'importe quel appareil du réseau local. Une synchronisation Pronote
automatique est programmée toutes les 2 heures tant que le processus tourne
(tous les comptes pairés, admin compris — voir `Services/README.md`).

**Site verrouillé** : en dehors d'une poignée de routes publiques
(`/auth/admin-login`, le pairage `/api/eleves/pairage`, et la page d'accueil
statique servie par le frontend), toute l'API exige une session valide
(`_require_session` dans `app/main.py`) — élève pairé (`request.session
["eleve_id"]`) ou admin (`request.session["is_admin"]`). Un visiteur non
connecté ne peut rien consulter.

### Aperçu des endpoints (groupés par domaine)

- **Auth élève** : `POST /api/eleves/pairage` (QR + PIN, voir
  `Services/README.md`), `POST /auth/logout`, `GET /api/me`.
- **Auth admin** — indépendante des comptes élèves, mot de passe seul
  (`ADMIN_PASSWORD`) : `POST /auth/admin-login`, `POST /auth/admin-logout`.
- **Profil élève** : `GET /api/profil`, `PUT /api/profil/gemini-cle` (clé
  Gemini personnelle, voir `Services/README.md`).
- **Classes** (admin) : `GET/POST /api/classes`, `DELETE
  /api/classes/{id}` (refuse de supprimer la dernière).
- **Matières** : `GET /api/matieres` (filtrable `?classe=`), `GET
  /api/matieres/{id}/cours`, `GET /api/matieres/{id}/notes`. Admin :
  `GET /api/parametres/matieres` (toutes, y compris masquées), `PUT
  /api/matieres/{id}/exclure`.
- **Cours** : `GET /api/cours/suggestion-ia` ("Quiz du jour"), `GET
  /api/cours/du-jour`, `GET /api/cours/recents`, `GET /api/cours/{id}`,
  `POST /api/cours/{id}/generer|completer|verifier|notes`. Admin : `GET
  /api/cours/non-generes`. Génération manuelle (v0.6.0, désactivée par
  défaut par élève — voir "Élèves" ci-dessous) : `GET
  /api/cours/{id}/prompt-manuel` (prompt à copier), `POST
  /api/cours/{id}/importer-manuel` (JSON collé, toujours en attente de
  validation admin).
- **Devoirs** : `GET /api/devoirs`.
- **Documents** : `GET /api/documents/{id}/fichier|apercu`. Admin : `GET
  /api/documents/non-transcrits`, `POST /api/documents/{id}/transcrire`.
- **Élèves** (admin) : `GET /api/eleves`, `PUT /api/eleves/{id}/assistant`,
  `PUT /api/eleves/{id}/generation-manuelle`, `POST
  /api/eleves/{id}/reinitialiser-pronote` (force un re-pairage).
- **Traitements** (admin, diagnostic) : `GET /api/traitements`, `GET
  /api/traitements/{id}`, `POST /api/traitements/{id}/relancer`, +
  validation/rejet des demandes en attente (régénération ou import
  manuel, `POST /api/traitements/demandes/{id}/valider|rejeter`).
- **Paramétrage** (admin) : `GET/PUT /api/parametres` (moteur IA, Pronote,
  OCR, vérification — clés jamais renvoyées en clair).
- **Synchro** : `POST /api/sync` (force une synchronisation immédiate).
- **Assistant** : `POST /api/assistant` (voir plus bas).

Le détail précis (paramètres, réponses) est dans `app/main.py` — chaque
route y est commentée sur son "pourquoi", pas juste son "quoi".

## Tests

Suite pytest dans `tests/` (isolée : base SQLite temporaire par test, pas
la vraie base — voir `tests/conftest.py`). N'est **pas** dans
`requirements.txt` (dépendance de dev, jamais nécessaire sur l'OptiPlex en
prod) :

```bash
cd BackEnd
.venv/bin/pip install -r requirements-dev.txt   # une fois
.venv/bin/pytest tests/ -v
```

Couvre les zones les plus délicates (celles où une régression serait
silencieuse) : pairage Pronote et ses messages d'erreur, multi-classe
(dédoublonnage, filtrage, migration), clé Gemini personnelle, matières à
exclure.

## Faire tourner ça en permanence (systemd)

Pour que l'API redémarre automatiquement au démarrage de l'OptiPlex et en
cas de plantage, utilise `deploy/ghostcards.service` (déjà prêt avec tes
chemins) :

```bash
sudo cp deploy/ghostcards.service /etc/systemd/system/ghostcards.service
sudo systemctl daemon-reload
sudo systemctl enable --now ghostcards
sudo systemctl status ghostcards
```

(Adapte `User` et les chemins si ta configuration diffère.)

Pour exposer le site hors du réseau local (HTTPS, domaine) : voir
`deploy/Caddyfile` et `../Services/README.md`, section "Exposer le site
hors du réseau local".

## Frontend

Le frontend (`../FrontEnd`, voisin de ce dossier `BackEnd`) est un projet
Vite + React branché sur cette API.

```bash
cd ../FrontEnd
npm install
npm run build
```

Ça produit `FrontEnd/dist/`. Redémarre l'API (`sudo systemctl restart
ghostcards` si tu utilises le service) : `app/main.py` détecte
automatiquement ce dossier au démarrage et sert le site sur `/` — API et
frontend sur le même port, un seul service à faire tourner.

```
http://<ip-de-l-optiplex>:8000/
```

Pour du développement au jour le jour (rechargement à chaud, pas besoin de
rebuilder à chaque changement) :

```bash
cd ../FrontEnd
npm run dev
```

Ouvre alors `http://localhost:5173` — le serveur de dev proxifie
automatiquement `/api/*` et `/auth/*` vers `http://localhost:8000` (voir
`vite.config.js`), donc l'API doit tourner en parallèle (`uvicorn
app.main:app --reload` dans un autre terminal, depuis `BackEnd/`).

### Versions

Le numéro affiché dans l'en-tête de l'app vient de
`../FrontEnd/package.json` (champ `version`), injecté au build par
`vite.config.js` (`define: { __APP_VERSION__ }`). À incrémenter à chaque
publication, avec une nouvelle entrée dans `../CHANGELOG.md`.

### Assistant IA

L'écran Assistant appelle `/api/assistant`, qui relaie la conversation
**côté serveur** vers le moteur IA configuré (Ollama local, Claude ou
Gemini — le même choix et les mêmes clés que la génération de
résumés/flashcards/quiz, voir `Services/ia_generation.py::config_ia` et
l'écran admin "Paramétrage") : aucune clé n'est jamais exposée au
navigateur. Désactivé par défaut pour un élève, activable au cas par cas
depuis l'écran admin "Élèves" (`assistant_actif`) — l'admin, lui, y a
toujours accès.

Pour Claude/Gemini, ajoute dans `.env` (ou depuis l'écran Paramétrage,
modifiable à chaud) :

```
ANTHROPIC_API_KEY=sk-ant-...   # console.anthropic.com/settings/keys
GEMINI_API_KEY=...             # aistudio.google.com/apikey
```

Sans clé pour le moteur choisi, l'assistant (et la génération) renvoient
une erreur claire plutôt que de planter.
