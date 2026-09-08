# Ghost Cards — BackEnd

API HTTP (FastAPI) de Ghost Cards : sert au frontend les données préparées
par `Services/` (cours, documents, résumés, flashcards, quiz), et sert le
frontend buildé en statique une fois `npm run build` lancé côté `FrontEnd/`.

Voir [`../README.md`](../README.md) pour la vue d'ensemble, et
[`../Services/README.md`](../Services/README.md) pour la synchro Pronote et
la génération IA.

## Installation

```bash
cd BackEnd
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Édite `.env` et renseigne `PRONOTE_URL` (l'URL affichée dans le navigateur
quand tu es connecté à Pronote, du type
`https://XXXXXXXX.index-education.net/pronote/eleve.html`).

Puis suis [`../Services/README.md`](../Services/README.md) pour la première
connexion à Pronote et un premier test de synchronisation, avant de lancer
l'API.

## Lancer l'API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(`--reload` en développement pour recharger automatiquement au fil des
modifications.)

L'API tourne alors sur `http://<ip-de-l-optiplex>:8000`, accessible depuis
n'importe quel appareil du réseau local. Une synchronisation Pronote
automatique est programmée toutes les 2 heures tant que le processus tourne.

Endpoints principaux :
- `GET /api/matieres` — liste des matières avec compteurs
- `GET /api/matieres/{id}/cours` — cours d'une matière
- `GET /api/cours/{id}` — détail d'un cours + documents + notes
- `GET /api/cours/recents` — derniers cours importés
- `GET /api/devoirs` — devoirs à rendre
- `GET /api/documents/{id}/fichier` — télécharge un document
- `POST /api/sync` — force une synchronisation Pronote immédiate
- `POST /api/assistant` — proxy vers l'API Anthropic (assistant IA)

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
automatiquement `/api/*` vers `http://localhost:8000` (voir
`vite.config.js`), donc l'API doit tourner en parallèle (`uvicorn
app.main:app --reload` dans un autre terminal, depuis `BackEnd/`).

### Assistant IA

L'écran Assistant appelle `/api/assistant`, qui relaie la requête vers
l'API Anthropic **côté serveur** — la clé n'est jamais exposée au
navigateur. Pour l'activer, ajoute dans `.env` :

```
ANTHROPIC_API_KEY=sk-ant-...
```

(clé à créer sur https://console.anthropic.com/settings/keys). Sans clé,
l'assistant renvoie une erreur claire plutôt que de planter.
