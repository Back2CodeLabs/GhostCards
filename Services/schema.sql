-- Ghost School — schéma de stockage local (SQLite)
-- Un seul fichier .db sur le disque de l'OptiPlex, pas de serveur de base de données à gérer.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS matieres (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nom     TEXT NOT NULL UNIQUE,
    slug    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cours (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Pronote change les id internes à chaque session : on calcule notre propre
    -- clé stable (date + heure + matière + professeur) pour ne jamais dupliquer un cours.
    external_key      TEXT NOT NULL UNIQUE,
    matiere_id        INTEGER NOT NULL REFERENCES matieres(id),
    date              TEXT NOT NULL,      -- YYYY-MM-DD
    heure_debut       TEXT NOT NULL,      -- HH:MM
    heure_fin         TEXT,
    professeur        TEXT,
    titre             TEXT,
    description       TEXT,
    annule            INTEGER NOT NULL DEFAULT 0,
    -- lesson.content coûte une requête Pronote dédiée : on ne la refait pas
    -- une fois qu'elle a été récupérée pour ce cours.
    contenu_recupere  INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cours_matiere ON cours(matiere_id);
CREATE INDEX IF NOT EXISTS idx_cours_date ON cours(date);

-- Notes Pronote (grades) — distinct de `notes_eleves` (prises de notes
-- perso des élèves) : ici, ce que Pronote publie comme note/moyenne.
CREATE TABLE IF NOT EXISTS notes_pronote (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Comme pour cours/devoirs : grade.id est réattribué par Pronote à
    -- chaque connexion, clé stable calculée nous-mêmes (voir pronote_sync.py).
    external_key    TEXT NOT NULL UNIQUE,
    matiere_id      INTEGER NOT NULL REFERENCES matieres(id),
    valeur          TEXT,      -- note obtenue (chaîne : Pronote renvoie parfois "Absent", "Disp.", etc.)
    bareme          TEXT,      -- note sur combien (ex. "20")
    moyenne_classe  TEXT,
    note_min        TEXT,
    note_max        TEXT,
    coefficient     TEXT,
    commentaire     TEXT,
    date            TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_pronote_matiere ON notes_pronote(matiere_id);

CREATE TABLE IF NOT EXISTS devoirs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    external_key  TEXT NOT NULL UNIQUE,
    matiere_id    INTEGER NOT NULL REFERENCES matieres(id),
    date_rendu    TEXT NOT NULL,
    description   TEXT,
    fait          INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cours_id      INTEGER REFERENCES cours(id) ON DELETE CASCADE,
    devoir_id     INTEGER REFERENCES devoirs(id) ON DELETE CASCADE,
    nom_fichier   TEXT NOT NULL,
    chemin_local  TEXT NOT NULL UNIQUE,   -- chemin relatif à DATA_DIR
    url_externe   TEXT,                   -- si l'attachement est un lien plutôt qu'un fichier téléchargeable
    source        TEXT NOT NULL DEFAULT 'pronote',  -- 'pronote' | 'note_eleve'
    created_at    TEXT NOT NULL
);

-- Élèves identifiés via Google (uniquement pour attribuer les notes
-- déposées — la consultation du site ne nécessite pas de compte).
CREATE TABLE IF NOT EXISTS eleves (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub          TEXT NOT NULL UNIQUE,  -- identifiant Google stable (claim "sub")
    email               TEXT NOT NULL,
    nom                 TEXT NOT NULL,
    avatar_url          TEXT,
    created_at          TEXT NOT NULL,
    derniere_connexion  TEXT NOT NULL
);

-- Prises de notes collaboratives des élèves (section 8 de la présentation).
-- Prête à être utilisée dès que l'écran "Notes" du site enverra du contenu ici.
CREATE TABLE IF NOT EXISTS notes_eleves (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cours_id        INTEGER REFERENCES cours(id) ON DELETE CASCADE,
    auteur          TEXT NOT NULL,
    contenu         TEXT,
    chemin_fichier  TEXT,
    type            TEXT NOT NULL DEFAULT 'texte',  -- 'texte' | 'markdown' | 'photo' | 'pdf'
    created_at      TEXT NOT NULL
);

-- Journal des traitements en arrière-plan (extraction PDF, OCR) : permet à
-- Cédric de voir le rendu de chaque action et de relancer si le résultat
-- n'est pas satisfaisant (section OCR du cahier des charges).
CREATE TABLE IF NOT EXISTS traitements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    type          TEXT NOT NULL,        -- 'pdftotext' | 'ocr_document' | 'ocr_note'
    cible_type    TEXT NOT NULL,        -- 'document' | 'note'
    cible_id      INTEGER NOT NULL,
    statut        TEXT NOT NULL DEFAULT 'en_cours',  -- 'en_cours' | 'succes' | 'echec'
    moteur        TEXT,                 -- 'pdftotext' | 'claude' | 'paddleocr'
    resultat      TEXT,                 -- texte/markdown produit
    erreur        TEXT,
    duree_ms      INTEGER,
    created_at    TEXT NOT NULL,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_traitements_cible ON traitements(cible_type, cible_id);

-- Réglages modifiables à chaud depuis l'écran admin "Paramétrage" (ex.
-- choix du moteur de génération IA, clé Gemini) : évite d'avoir à éditer
-- .env et redémarrer le service pour un simple changement de moteur.
-- Absent d'une clé = pas encore configuré, on retombe sur la valeur par
-- défaut de Services/config.py (qui lit .env).
CREATE TABLE IF NOT EXISTS parametres (
    cle     TEXT PRIMARY KEY,
    valeur  TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    nouveaux_cours      INTEGER DEFAULT 0,
    nouveaux_devoirs    INTEGER DEFAULT 0,
    nouveaux_documents  INTEGER DEFAULT 0,
    nouvelles_notes     INTEGER DEFAULT 0,
    erreur              TEXT
);
