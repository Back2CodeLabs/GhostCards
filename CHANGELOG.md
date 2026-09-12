# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Numéro de version affiché dans l'app (voir `FrontEnd/package.json`, injecté
via `vite.config.js`) — à incrémenter à chaque publication sur l'OptiPlex,
avec une nouvelle entrée ici.

## [0.2.0] — en cours

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
