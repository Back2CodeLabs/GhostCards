# Ghost School

Plateforme de révision auto-hébergée pour une (ou plusieurs) classe(s), sur
l'OptiPlex de Cédric — connectée à Pronote, verrouillée aux élèves pairés.

```
GhostCards/
  BackEnd/    API HTTP (FastAPI) — sert les données au frontend
  FrontEnd/   Interface (Vite + React)
  Services/   Logique métier : pairage/synchro Pronote, chiffrement des
              identifiants, génération IA (résumés, flashcards, quiz),
              OCR, scripts de maintenance
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
  build et service du frontend, déploiement systemd, aperçu de l'API.
- [`Services/README.md`](Services/README.md) — pairage Pronote par élève,
  synchro multi-comptes/multi-classe, chiffrement, génération IA, OCR,
  exposition HTTPS.

Convention : les commandes `python3 -m Services.xxx` (synchro manuelle,
première connexion admin, génération) se lancent depuis la racine
`GhostCards/`, avec le venv de `BackEnd/` activé :

```bash
cd ~/GhostCards
source BackEnd/.venv/bin/activate
python3 -m Services.pronote_sync
```

L'API elle-même (`uvicorn`, et le service systemd) continue de tourner
depuis `BackEnd/` comme avant.

### Tests

Suite de tests automatisés dans `BackEnd/tests/` (pytest), isolée de la
vraie base de données (fixtures dans `BackEnd/tests/conftest.py`) — voir
`BackEnd/README.md`, section "Tests", pour l'installer et la lancer. Sert
de garde-fou de non-régression sur les zones les plus délicates :
pairage/synchro Pronote, multi-classe, clé Gemini personnelle, matières à
exclure.

### Versions

Le numéro affiché dans l'en-tête de l'app (badge à côté du logo) vient de
`FrontEnd/package.json` (champ `version`), injecté au build par
`FrontEnd/vite.config.js`. À incrémenter à chaque publication sur
l'OptiPlex, avec une nouvelle entrée dans [`CHANGELOG.md`](CHANGELOG.md) —
c'est la seule source de vérité sur "qu'est-ce qui a changé et quand",
utile pour recouper un bug signalé avec la version réellement déployée à
ce moment-là.

## À venir

Liste complète et détaillée dans `HANDOFF.md`, section "État — pas
commencé". En résumé :
- Durcissement de la connexion admin (verrouillage après échecs répétés,
  MFA TOTP).
- Outil admin de recherche/fusion de doublons de documents.
- Export flashcards compatible Anki, espace enseignant (hors scope v1).
- Gamification (streaks/XP/ligues) — en attente de retours de la classe
  avant de cadrer, la partie "ligue" comparant des élèves entre eux
  méritant une décision de principe au préalable.

## Fait

- **Thème** sombre néon "rétro 80s" + thème clair, mise en page desktop et
  mobile, aperçu de lien (Open Graph/Twitter) au partage de l'URL.
- **Connexion élève par pairage Pronote self-service** (QR code + PIN,
  avec recadrage de la photo avant envoi) — remplace l'ancienne connexion
  Google. Verrouille **toute** la consultation du site (pas seulement le
  dépôt de notes) : un visiteur non connecté ne voit qu'une page d'accueil
  générique, avec un bouton pour se connecter. Vérifie l'établissement et
  la classe (voir multi-classe ci-dessous) avant de créer la session.
  Identifiants Pronote de chaque élève chiffrés au repos — voir
  `Services/README.md`.
- **Multi-classe** : plusieurs classes (ex. 2F, 2E) peuvent cohabiter sur
  la même instance — chaque cours/devoir synchronisé est rattaché à la
  classe qui l'a vu, un élève ne voit jamais le contenu d'une autre
  classe. Écran admin "Paramétrage" : gestion d'une vraie liste de classes
  autorisées au pairage. Écran admin : onglets pour filtrer par classe
  (Accueil, Matières, Élèves), ou tout voir mélangé par défaut.
- **Profil élève** : chaque élève peut associer sa propre clé Gemini
  (facultatif, gratuite) à la génération IA — prime sur le moteur choisi
  par l'admin pour ses propres générations, pour répartir la charge entre
  plusieurs clés personnelles plutôt que tout faire peser sur celle de
  l'admin.
- **Emploi du temps du jour** sur l'accueil, bandeau "Quiz du jour" pour
  découvrir la génération IA, mode examen (flashcards/quiz) avec
  animations (retournement de carte, barre de progression).
- OCR / extraction de texte (PDF Pronote scannés, photos de notes) via
  PaddleOCR (local, gratuit — vision Claude en repli), avec écran de
  diagnostic admin ("Traitements") pour voir le résultat de chaque
  extraction et la relancer — voir `Services/README.md`.
- Génération IA (résumés / flashcards / quiz) et assistant conversationnel,
  au choix via Ollama local, Claude ou Gemini — moteur et clés modifiables
  à chaud dans l'écran admin "Paramétrage", voir `Services/README.md`.
  Assistant désactivé par défaut pour un élève, activable au cas par cas
  depuis l'écran admin "Élèves". "Matières à exclure" : masque une matière
  déjà récupérée (case à cocher) sans jamais empêcher sa synchronisation.
  Historique complet des synchros/extractions/générations dans l'écran
  admin "Traitements" (Pronote, OCR, IA), fichiers Pronote dédupliqués sur
  le disque.
- Exposition hors réseau local en HTTPS (domaine + Caddy/Let's Encrypt) —
  voir `Services/README.md`, section "Exposer le site hors du réseau
  local".
- **Génération manuelle** : un élève copie le prompt exact que Ghost
  School utiliserait pour un cours, le colle dans sa propre IA (ChatGPT,
  Gemini, Claude...) hors Ghost School, puis importe la réponse — toujours
  soumis à validation admin avant de remplacer le contenu partagé de la
  classe (écran admin "Traitements" → "En attente"). Désactivé par défaut
  pour chaque élève, comme l'assistant — voir `Services/README.md`.
