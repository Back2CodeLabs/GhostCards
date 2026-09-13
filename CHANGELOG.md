# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Numéro de version affiché dans l'app (voir `FrontEnd/package.json`, injecté
via `vite.config.js`) — à incrémenter à chaque publication sur l'OptiPlex,
avec une nouvelle entrée ici.

## [0.3.9] — en cours

### Added
- Bandeau "Quiz du jour" tout en haut de l'accueil : met en avant un cours
  déjà prêt à réviser, ou à défaut un cours qu'on peut générer, pour que
  la génération IA (résumé/flashcards/quiz) ne passe plus inaperçue.

### Fixed
- Un cours avec seulement une description (pas de document ni de note)
  n'affichait jamais le bouton "Générer", alors que le serveur sait déjà
  générer à partir de la seule description.

## [0.3.8] — 2026-09-13

### Changed
- Accueil : la liste des matières (doublon de l'onglet Matières) est
  remplacée par l'emploi du temps du jour, cours annulés compris.

### Added
- Le groupe Pronote (LV2, options...) d'un élève, quand il est détecté
  dans son propre emploi du temps, apparaît désormais sur sa fiche
  (écran admin Élèves) à côté de sa classe.

## [0.3.7] — 2026-09-13

### Added
- Recadrage de la photo du QR code avant envoi (zone ajustable + zoom) sur
  l'écran de connexion, au lieu d'uploader l'écran entier tel quel — moins
  de parasites autour du QR pour la détection côté serveur, moins de
  données envoyées.

## [0.3.6] — 2026-09-13

### Fixed
- Pairage Pronote : après une connexion réussie, l'écran de pairage restait
  affiché au lieu de retomber sur l'accueil (il n'était jamais dépilé de
  la navigation) — corrigé, comme pour la connexion admin.
- Message d'erreur PIN incorrect peu clair : une réponse d'erreur brute de
  pronotepy ("invalid confirmation code", en anglais) remontait telle
  quelle. Message dédié en français, avec l'action à faire (régénérer le
  QR code).
- Une panne après une connexion Pronote réussie (chiffrement, base de
  données) remontait une erreur 500 muette — message clair côté élève
  désormais, détail complet conservé dans les logs serveur pour diagnostic.

## [0.3.5] — 2026-09-13

### Added
- Vraie page d'accueil (pitch + bouton "Se connecter") pour un visiteur non
  connecté, au lieu d'imposer directement le formulaire de pairage Pronote
  (retour du premier élève testeur). Salutation personnalisée une fois
  connecté : prénom de l'élève, ou "Maître Fantôme" pour l'admin.

## [0.3.4] — 2026-09-13

### Fixed
- Un même élève re-pairant son compte Pronote (ex. après une déconnexion
  de l'appli côté téléphone) créait une **deuxième ligne élève en double**
  au lieu de mettre à jour la sienne : `ClientInfo.id` (utilisé jusque-là
  comme identifiant stable côté Pronote) est en réalité régénéré à chaque
  pairage, pas un identifiant de compte durable. Le pairage matche
  désormais par nom (classe fermée à 36 élèves connus). Migration
  automatique au démarrage pour fusionner les doublons déjà présents en
  base (repéré sur un vrai doublon en production).

## [0.3.3] — 2026-09-13

### Fixed
- `BackEnd/deploy/Caddyfile` échouait à démarrer sur l'OptiPlex :
  `tailscale serve` occupe déjà le port 443 sur l'interface Tailscale
  pour un autre usage. Caddy est désormais restreint (`bind`) à l'IP
  réseau locale de l'OptiPlex, sans toucher à la config Tailscale.

## [0.3.2] — 2026-09-12

### Added
- `BackEnd/deploy/Caddyfile` + procédure documentée (`Services/README.md`)
  pour exposer le site en HTTPS (Caddy, Let's Encrypt automatique)
  maintenant que `ghostschool.app` pointe vers l'OptiPlex.
- Réglage `SESSION_COOKIE_SECURE` (faux par défaut) pour marquer le
  cookie de session "Secure" une fois HTTPS confirmé en place.

## [0.3.1] — 2026-09-12

### Fixed
- Le pairage Pronote échouait ("Aucun QR code détecté") sur une vraie
  photo prise au téléphone (fonctionnait seulement avec une capture
  d'écran) : `cv2.QRCodeDetector` s'est montré très sensible à la
  résolution d'entrée sur une photo réelle. Réessaie maintenant plusieurs
  tailles avant d'abandonner.

### Added
- Filet de secours sur l'écran de connexion : "Coller le code à la
  place" pour saisir directement le JSON du QR code si l'upload d'image
  ne suffit toujours pas.

## [0.3.0] — 2026-09-12

### Added
- Consentement explicite avant le pairage Pronote d'un élève : liste
  précise de ce qui sera récupéré (partagé avec la classe vs gardé
  privé), case à cocher obligatoire, horodatage enregistré comme preuve
  (`eleves.consentement_pronote_le`).

### Changed
- La synchronisation Pronote couvre maintenant tous les comptes élèves
  pairés, pas seulement le compte de référence (admin) : chaque élève
  apporte son propre groupe (LV2, options...), invisible depuis un seul
  compte. Cours/devoirs/documents restent partagés classe entière ; les
  notes sont scopées par élève (jamais mélangées entre élèves).
- Jeton Pronote de chaque élève tourné et rechiffré à chaque
  synchronisation ; comptes étalés de 5 s pour ne pas déclencher le
  throttling Pronote. Un compte cassé n'interrompt jamais les autres.

## [0.2.0] — 2026-09-12

### Changed
- **Connexion élève** : remplace la connexion Google par un pairage
  Pronote propre à chaque élève (upload d'une capture du QR code de
  connexion Pronote + PIN). Vérifie l'établissement (URL) et la classe
  (`class_name`, réglage "Classe attendue" dans Paramétrage → Pronote)
  avant de créer la session.
- **Consultation du site verrouillée** : il faut désormais être un élève
  pairé ou l'admin pour consulter quoi que ce soit (auparavant ouvert à
  tous, seul le dépôt de notes nécessitait une connexion).
- Les notes/moyennes Pronote (`notes_pronote`) sont scopées par élève :
  un élève ne voit plus que ses propres notes.

### Added
- Jeton Pronote de chaque élève chiffré au repos (Fernet, voir
  `Services/crypto_secrets.py`, clé via `CREDENTIALS_ENCRYPTION_KEY`).
- Écran admin "Élèves" : statut de pairage par élève (classe constatée,
  lien Pronote cassé), bouton pour forcer un re-pairage.
- Numéro de version affiché dans l'en-tête du site.

### Removed
- Connexion Google (Authlib/OAuth) et ses réglages associés
  (`GOOGLE_CLIENT_ID`/`SECRET`, `GOOGLE_HOSTED_DOMAIN`, `AUTHORIZED_EMAILS`,
  `BASE_URL`) — devenue redondante et plus permissive que le pairage
  Pronote.

## [0.1.0] — avant ce changelog

Première version fonctionnelle, développée sans suivi de version formel.
Voir `HANDOFF.md` pour l'historique détaillé session par session. Points
marquants :

- Synchronisation Pronote automatique (cours, devoirs, notes, documents),
  avec emploi du temps enrichi (salle, groupe, mémo, statut d'annulation,
  devoir surveillé) et exclusion configurable des créneaux qui ne sont pas
  de vraies matières.
- Génération IA (résumé, flashcards, quiz) multi-moteur (Ollama, Claude,
  Gemini), assistant conversationnel, vérification de fiabilité.
- OCR des documents Pronote scannés et des notes photo déposées par les
  élèves (PaddleOCR local ou Claude Vision).
- Mode examen avec effet de désintégration façon Thanos à la fin d'un
  quiz/flashcards.
- Écran admin "Traitements" (historique + relance manuelle des synchros/
  OCR/générations IA, y compris pour les documents/cours jamais traités).
- Prise de notes collaborative des élèves sur un cours (texte ou photo).
