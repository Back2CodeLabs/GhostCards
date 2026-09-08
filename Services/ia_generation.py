"""
Génération IA (résumé, flashcards, quiz) pour un cours, via un modèle
Ollama local.

Volume potentiellement important (des dizaines de cours sur l'année) :
un modèle local et gratuit est utilisé plutôt que l'API Anthropic
(réservée à l'assistant conversationnel, faible volume — voir
Services/config.py). Suit le pattern qui fonctionne déjà chez Cédric
(`flashcard.sh`) : `POST {OLLAMA_URL}/api/generate` avec `format: "json"`
et `think: false`, pour forcer une sortie JSON structurée sans le
raisonnement intermédiaire de qwen3 (qui polluerait la réponse).

Le résultat est stocké directement sur la ligne `cours` (colonnes `ia_*`,
voir Services/db.py::init_db) plutôt que dans une table séparée : une
génération remplace la précédente, il n'y a pas besoin d'historique des
contenus eux-mêmes (l'historique des *tentatives*, avec le détail de
chaque étape, reste dans `traitements`, comme pour l'OCR).
"""
import json
import logging
import time
import urllib.error
import urllib.request

from . import db
from .config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    FLASHCARDS_PAR_COURS,
    QUESTIONS_QUIZ_PAR_COURS,
    IA_TEXTE_MAX_CHARS,
)

log = logging.getLogger("ghostcards.ia_generation")

# Nombre de flashcards/questions ajoutées par un clic sur "+ 10" une fois
# une génération déjà en place (voir completer_pour_cours).
N_COMPLEMENT = 10


class GenerationError(Exception):
    pass


PROMPT_TEMPLATE = """{texte}

À partir de ce cours, produis :
1. Un résumé COURT (2 à 4 phrases, l'essentiel seulement).
2. Un résumé DÉTAILLÉ, dont la longueur doit être proportionnelle à la
   longueur du cours ci-dessus (plus le cours est long/dense, plus ce
   résumé doit être développé) — ne sacrifie pas les éléments importants
   juste pour rester court.
3. Exactement {nb_flashcards} flashcards de révision (question courte, réponse courte,
   1 phrase maximum).
4. Exactement {nb_quiz} questions de quiz à choix multiple (4 options, une seule correcte).

Réponds UNIQUEMENT avec un JSON valide, rien d'autre, dans ce format exact, en français,
sans markdown ni texte avant ou après le JSON :
{{"resume_court": "...", "resume_detaille": "...", "flashcards": [{{"question": "...", "reponse": "..."}}], "quiz": [{{"question": "...", "options": ["...", "...", "...", "..."], "reponse_index": 0}}]}}
"""

PROMPT_COMPLEMENT_TEMPLATE = """{texte}

Voici les questions déjà utilisées pour ce cours (à ne pas répéter à l'identique) :
Flashcards existantes : {questions_flashcards}
Quiz existant : {questions_quiz}

Génère {n} NOUVELLES flashcards de révision (différentes des précédentes,
question courte / réponse courte, 1 phrase maximum) et {n} NOUVELLES
questions de quiz à choix multiple (4 options, une seule correcte,
différentes des précédentes), à partir de ce même cours.

Réponds UNIQUEMENT avec un JSON valide, rien d'autre, dans ce format exact,
en français, sans markdown ni texte avant ou après le JSON :
{{"flashcards": [{{"question": "...", "reponse": "..."}}], "quiz": [{{"question": "...", "options": ["...", "...", "...", "..."], "reponse_index": 0}}]}}
"""


def _appeler_ollama(prompt: str) -> dict:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "think": False,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        # qwen3:14b en local (CPU) peut être lent : jusqu'à ~30 min observés
        # en pratique par Cédric sur un PDF de cours complet (flashcard.sh).
        with urllib.request.urlopen(req, timeout=1800) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise GenerationError(f"Ollama injoignable sur {OLLAMA_URL} : {e}") from e
    except TimeoutError as e:
        raise GenerationError(f"Ollama n'a pas répondu à temps ({OLLAMA_URL})") from e

    try:
        return json.loads(body["response"])
    except (KeyError, json.JSONDecodeError) as e:
        raise GenerationError(f"Réponse Ollama inexploitable (pas un JSON valide) : {e}") from e


def _texte_source(conn, cours: dict) -> str:
    morceaux = []
    if cours.get("description"):
        morceaux.append(cours["description"])
    docs = conn.execute(
        "SELECT texte_extrait FROM documents WHERE cours_id = ? AND texte_extrait IS NOT NULL",
        (cours["id"],),
    ).fetchall()
    morceaux.extend(d["texte_extrait"] for d in docs if d["texte_extrait"])
    return "\n\n".join(morceaux)[:IA_TEXTE_MAX_CHARS]


def generer_pour_cours(cours_id: int) -> None:
    """Génère résumés (court + détaillé)/flashcards/quiz pour un cours et les enregistre sur la ligne `cours`."""
    with db.session() as conn:
        row = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if row is None:
            raise GenerationError(f"Cours {cours_id} introuvable")
        cours = dict(row)
        texte = _texte_source(conn, cours)
        # Passage par 'en_cours' même pour un échec immédiat (contenu vide) :
        # sans ça, le frontend (qui ne poll que si ia_statut === 'en_cours')
        # peut ne jamais voir passer le statut 'echec' si son unique
        # rechargement après le déclenchement arrive avant que ce
        # traitement en arrière-plan n'ait eu le temps de tourner.
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))

    if not texte.strip():
        with db.session() as conn:
            conn.execute(
                "UPDATE cours SET ia_statut = 'echec', ia_erreur = ? WHERE id = ?",
                ("Aucun contenu de cours ni document transcrit à partir duquel générer.", cours_id),
            )
        return

    prompt = PROMPT_TEMPLATE.format(
        nb_flashcards=FLASHCARDS_PAR_COURS, nb_quiz=QUESTIONS_QUIZ_PAR_COURS, texte=texte,
    )

    try:
        with db.log_traitement("ia_generation", "cours", cours_id) as ctx:
            ctx.moteur = OLLAMA_MODEL
            ctx.etape("lecture du contenu source", detail=f"{len(texte)} caractère(s) (description + documents transcrits)")

            t0 = time.monotonic()
            resultat = _appeler_ollama(prompt)
            ctx.etape("appel Ollama", moteur=OLLAMA_MODEL, duree_ms=int((time.monotonic() - t0) * 1000),
                       detail="format=json, think=false")

            nb_fc = len(resultat.get("flashcards", []))
            nb_q = len(resultat.get("quiz", []))
            ctx.etape("extraction résumés/flashcards/quiz", detail=f"{nb_fc} flashcard(s), {nb_q} question(s) de quiz")
            ctx.resultat = json.dumps(resultat, ensure_ascii=False)[:4000]
    except Exception as e:  # noqa: BLE001 — déjà journalisé dans `traitements` par db.log_traitement
        with db.session() as conn:
            conn.execute("UPDATE cours SET ia_statut = 'echec', ia_erreur = ? WHERE id = ?", (str(e), cours_id))
        return

    with db.session() as conn:
        conn.execute(
            """UPDATE cours
               SET ia_statut = 'pret', ia_resume = ?, ia_resume_detaille = ?, ia_flashcards = ?, ia_quiz = ?, ia_erreur = NULL
               WHERE id = ?""",
            (
                resultat.get("resume_court", resultat.get("resume", "")),
                resultat.get("resume_detaille", ""),
                json.dumps(resultat.get("flashcards", []), ensure_ascii=False),
                json.dumps(resultat.get("quiz", []), ensure_ascii=False),
                cours_id,
            ),
        )


def completer_pour_cours(cours_id: int, n: int = N_COMPLEMENT) -> None:
    """
    Ajoute `n` flashcards et `n` questions de quiz supplémentaires à une
    génération déjà en place (bouton "+ 10" côté frontend), sans toucher
    au résumé ni aux flashcards/quiz déjà générés — juste un complément.
    """
    with db.session() as conn:
        row = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if row is None:
            raise GenerationError(f"Cours {cours_id} introuvable")
        cours = dict(row)
        # On se base sur la présence de contenu existant, pas sur ia_statut :
        # l'endpoint met déjà ia_statut à 'en_cours' avant d'appeler cette
        # fonction, et une relance depuis un complément en échec doit rester
        # possible (ia_statut vaudrait alors 'echec').
        if not cours.get("ia_flashcards"):
            raise GenerationError("Génère d'abord le résumé/flashcards/quiz avant de les compléter.")
        texte = _texte_source(conn, cours)
        flashcards_existantes = json.loads(cours["ia_flashcards"]) if cours["ia_flashcards"] else []
        quiz_existant = json.loads(cours["ia_quiz"]) if cours["ia_quiz"] else []
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))

    prompt = PROMPT_COMPLEMENT_TEMPLATE.format(
        texte=texte, n=n,
        questions_flashcards="; ".join(c["question"] for c in flashcards_existantes) or "(aucune)",
        questions_quiz="; ".join(q["question"] for q in quiz_existant) or "(aucune)",
    )

    try:
        with db.log_traitement("ia_completion", "cours", cours_id) as ctx:
            ctx.moteur = OLLAMA_MODEL
            ctx.etape("lecture de l'existant", detail=f"{len(flashcards_existantes)} flashcard(s), {len(quiz_existant)} question(s) déjà en place")

            t0 = time.monotonic()
            resultat = _appeler_ollama(prompt)
            ctx.etape("appel Ollama", moteur=OLLAMA_MODEL, duree_ms=int((time.monotonic() - t0) * 1000))

            nouvelles_fc = resultat.get("flashcards", [])
            nouvelles_q = resultat.get("quiz", [])
            ctx.etape("fusion avec l'existant", detail=f"+{len(nouvelles_fc)} flashcard(s), +{len(nouvelles_q)} question(s)")
            ctx.resultat = json.dumps(resultat, ensure_ascii=False)[:4000]
    except Exception as e:  # noqa: BLE001 — déjà journalisé dans `traitements` par db.log_traitement
        with db.session() as conn:
            conn.execute("UPDATE cours SET ia_statut = 'echec', ia_erreur = ? WHERE id = ?", (str(e), cours_id))
        return

    with db.session() as conn:
        conn.execute(
            "UPDATE cours SET ia_statut = 'pret', ia_flashcards = ?, ia_quiz = ?, ia_erreur = NULL WHERE id = ?",
            (
                json.dumps(flashcards_existantes + nouvelles_fc, ensure_ascii=False),
                json.dumps(quiz_existant + nouvelles_q, ensure_ascii=False),
                cours_id,
            ),
        )
