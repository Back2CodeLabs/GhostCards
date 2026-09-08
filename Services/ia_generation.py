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
contenus eux-mêmes (l'historique des *tentatives* reste dans
`traitements`, comme pour l'OCR).
"""
import json
import logging
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


class GenerationError(Exception):
    pass


PROMPT_TEMPLATE = """{texte}

À partir de ce cours, produis :
1. Un résumé clair et structuré (quelques phrases à quelques paragraphes).
2. Exactement {nb_flashcards} flashcards de révision (question courte, réponse courte,
   1 phrase maximum).
3. Exactement {nb_quiz} questions de quiz à choix multiple (4 options, une seule correcte).

Réponds UNIQUEMENT avec un JSON valide, rien d'autre, dans ce format exact, en français,
sans markdown ni texte avant ou après le JSON :
{{"resume": "...", "flashcards": [{{"question": "...", "reponse": "..."}}], "quiz": [{{"question": "...", "options": ["...", "...", "...", "..."], "reponse_index": 0}}]}}
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
    """Génère résumé/flashcards/quiz pour un cours et les enregistre sur la ligne `cours`."""
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
            resultat = _appeler_ollama(prompt)
            ctx.resultat = json.dumps(resultat, ensure_ascii=False)[:4000]
    except Exception as e:  # noqa: BLE001 — déjà journalisé dans `traitements` par db.log_traitement
        with db.session() as conn:
            conn.execute("UPDATE cours SET ia_statut = 'echec', ia_erreur = ? WHERE id = ?", (str(e), cours_id))
        return

    with db.session() as conn:
        conn.execute(
            """UPDATE cours
               SET ia_statut = 'pret', ia_resume = ?, ia_flashcards = ?, ia_quiz = ?, ia_erreur = NULL
               WHERE id = ?""",
            (
                resultat.get("resume", ""),
                json.dumps(resultat.get("flashcards", []), ensure_ascii=False),
                json.dumps(resultat.get("quiz", []), ensure_ascii=False),
                cours_id,
            ),
        )
