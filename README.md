# Ghost Cards

Plateforme de révision auto-hébergée pour la classe de 3ème B, sur l'OptiPlex
de Cédric.

```
GhostCards/
  BackEnd/    API HTTP (FastAPI) — sert les données au frontend
  FrontEnd/   Interface (Vite + React)
  Services/   Logique métier : synchro Pronote, génération IA (résumés,
              flashcards, quiz), scripts de maintenance
```

Pourquoi séparer `Services/` de `BackEnd/` : `BackEnd/` ne fait que du HTTP
(recevoir une requête, répondre en JSON). `Services/` contient tout ce qui
parle à l'extérieur ou fait du travail de fond — Pronote, le modèle Ollama
local — et peut être appelé aussi bien par l'API que par des scripts en
ligne de commande (synchro manuelle, génération en masse) sans dépendre du
serveur web. Tout tourne néanmoins dans le même environnement Python (un
seul `.venv`, dans `BackEnd/`) : ce n'est pas une séparation en processus ou
en services réseau distincts, juste une séparation du code par
responsabilité.

## Démarrage rapide

Voir le README de chaque dossier pour le détail :
- [`BackEnd/README.md`](BackEnd/README.md) — installation, lancer l'API,
  build et service du frontend, déploiement systemd.
- [`Services/README.md`](Services/README.md) — connexion Pronote, synchro,
  génération IA.

Convention : les commandes `python3 -m Services.xxx` (synchro manuelle,
première connexion, génération) se lancent depuis la racine `GhostCards/`,
avec le venv de `BackEnd/` activé :

```bash
cd ~/GhostCards
source BackEnd/.venv/bin/activate
python3 -m Services.pronote_sync
```

L'API elle-même (`uvicorn`, et le service systemd) continue de tourner
depuis `BackEnd/` comme avant.

## À venir

- Génération IA (résumés / flashcards / quiz) via Ollama en local — pas
  commencé.
- Exposer le site au-delà du réseau local (nom de domaine + HTTPS), pour que
  la connexion Google fonctionne aussi pour les camarades depuis chez eux —
  voir `Services/README.md`, section Authentification.

## Fait

- Thème sombre néon "rétro 80s" + thème clair, mise en page desktop et
  mobile.
- Connexion élève via Google (`Services/README.md`) — sert à attribuer les
  prises de notes déposées sur un cours ; la consultation du site reste
  libre sans compte.
- OCR / extraction de texte (PDF Pronote scannés, photos de notes) via
  PaddleOCR (local, gratuit — vision Claude en repli), avec écran de
  diagnostic admin ("Traitements") pour voir le résultat de chaque
  extraction et la relancer — voir `Services/README.md`. Implémenté et
  vérifié en sandbox, pas encore testé sur l'OptiPlex : nécessite d'abord
  de repasser le venv en Python ≤3.13 (voir `HANDOFF.md`).
