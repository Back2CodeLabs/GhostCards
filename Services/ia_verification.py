"""
Vérification de fiabilité d'une génération IA (résumé/flashcards/quiz)
par un second modèle, distinct de celui qui a généré le contenu — voir
écran admin Paramétrage → Vérification (config indépendante de Génération
IA : rien n'empêche de générer avec Ollama en local et de vérifier avec
Claude, par exemple, pour un vrai regard croisé).

Objectif : donner un indice de fiabilité (0 à 100) par élément généré
(résumé, chaque flashcard, chaque question de quiz), en confrontant
chacun au texte source réellement utilisé pour la génération
(`cours.ia_texte_source`, déjà fusionné si Ollama avait dû découper —
voir Services/ia_generation.py::_texte_pour_prompt). Ne fait AUCUN appel
réseau si aucune génération n'existe encore pour ce cours.

Ne réutilise pas le mécanisme de découpage d'`ia_generation` : le texte
envoyé ici est déjà le texte final (post-fusion), plus court à vérifier
qu'à générer — mais un cours source vraiment long, envoyé à un moteur
Ollama à petit contexte, peut malgré tout dépasser ses limites. Pas
traité pour l'instant (voir HANDOFF.md si ça devient un problème réel).
"""
import json
import logging
import time

from . import db, ia_generation
from .config import ANTHROPIC_API_KEY, GEMINI_API_KEY, GEMINI_MODEL, OLLAMA_URL, OLLAMA_MODEL

log = logging.getLogger("ghostcards.ia_verification")

GenerationError = ia_generation.GenerationError


def config_verif(conn) -> dict:
    """
    Résout le moteur de VÉRIFICATION effectif — indépendant du moteur de
    GÉNÉRATION (voir Services/ia_generation.py::config_ia) : deux réglages
    distincts dans la table `parametres` (préfixe `verif_`), pour pouvoir
    générer avec un modèle et vérifier avec un autre. Les clés API
    (Anthropic, Gemini) restent partagées avec la génération — même
    compte, pas de champ séparé à maintenir.
    """
    moteur = db.get_parametre(conn, "verif_moteur", "claude")
    if moteur not in ("ollama", "gemini", "claude"):
        moteur = "claude"
    return {
        "moteur": moteur,
        "anthropic_api_key": db.get_parametre(conn, "anthropic_api_key", ANTHROPIC_API_KEY),
        "gemini_api_key": db.get_parametre(conn, "gemini_api_key", GEMINI_API_KEY),
        "gemini_model": db.get_parametre(conn, "verif_gemini_model", GEMINI_MODEL) or GEMINI_MODEL,
        "ollama_url": db.get_parametre(conn, "verif_ollama_url", OLLAMA_URL) or OLLAMA_URL,
        "ollama_model": db.get_parametre(conn, "verif_ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL,
    }


VERIF_PROMPT_TEMPLATE = """Voici un extrait de cours (texte source) :
---
{texte}
---

Voici un résumé, des flashcards et des questions de quiz produits automatiquement à partir de ce texte par une autre IA. Pour CHAQUE élément, vérifie s'il est bien fondé sur le texte source ci-dessus (pas d'invention, pas d'erreur factuelle, réponse de quiz réellement correcte au vu du texte) et donne un score de 0 (faux ou non fondé) à 100 (parfaitement fidèle au texte).

RÉSUMÉ COURT : {resume_court}
RÉSUMÉ DÉTAILLÉ : {resume_detaille}

FLASHCARDS (index. question / réponse) :
{flashcards_listees}

QUIZ (index. question — options — réponse indiquée) :
{quiz_liste}

Réponds UNIQUEMENT avec un JSON valide, rien d'autre, dans ce format exact :
{{"resume": {{"score": 0, "commentaire": "..."}}, "flashcards": [{{"index": 0, "score": 0, "commentaire": "..."}}], "quiz": [{{"index": 0, "score": 0, "commentaire": "..."}}], "score_global": 0}}

"commentaire" : une phrase, en français, seulement si le score est inférieur à 70 (explique précisément ce qui ne colle pas avec le texte source) ; chaîne vide sinon. "score_global" : ta confiance globale dans l'ensemble, pas juste la moyenne arithmétique — pondère par la gravité des éventuelles erreurs.
"""


def _lister_flashcards(flashcards: list[dict]) -> str:
    if not flashcards:
        return "(aucune)"
    return "\n".join(f"{i}. {c['question']} / {c['reponse']}" for i, c in enumerate(flashcards))


def _lister_quiz(quiz: list[dict]) -> str:
    if not quiz:
        return "(aucun)"
    lignes = []
    for i, q in enumerate(quiz):
        reponse = q["options"][q["reponse_index"]] if 0 <= q.get("reponse_index", -1) < len(q.get("options", [])) else "?"
        lignes.append(f"{i}. {q['question']} — options : {q['options']} — réponse indiquée : {reponse}")
    return "\n".join(lignes)


def verifier_generation(cours_id: int, *, traitement_id: int | None = None) -> None:
    """
    Lance la vérification pour un cours déjà généré et enregistre le score
    global sur `cours.ia_fiabilite` (le détail par élément reste dans le
    traitement 'ia_verification', consultable dans l'écran Traitements).

    `traitement_id` : réutilise une ligne déjà créée par l'API (voir
    BackEnd/app/main.py::verifier_generation_ia) pour renvoyer l'id tout de
    suite et laisser l'admin ouvrir le suivi sans deviner/rafraîchir la liste
    — même pattern que la synchro Pronote déclenchée manuellement.
    """
    with db.session() as conn:
        row = conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone()
        if row is None:
            raise GenerationError(f"Cours {cours_id} introuvable")
        cours = dict(row)
        cfg = config_verif(conn)

    if not cours.get("ia_resume"):
        raise GenerationError("Aucune génération IA à vérifier pour ce cours — génère d'abord un résumé.")

    flashcards = json.loads(cours["ia_flashcards"]) if cours.get("ia_flashcards") else []
    quiz = json.loads(cours["ia_quiz"]) if cours.get("ia_quiz") else []
    prompt = VERIF_PROMPT_TEMPLATE.format(
        texte=cours.get("ia_texte_source") or "",
        resume_court=cours.get("ia_resume") or "",
        resume_detaille=cours.get("ia_resume_detaille") or "",
        flashcards_listees=_lister_flashcards(flashcards),
        quiz_liste=_lister_quiz(quiz),
    )

    with db.log_traitement("ia_verification", "cours", cours_id, traitement_id=traitement_id) as ctx:
        ctx.moteur = ia_generation._nom_moteur(cfg)
        t0 = time.monotonic()
        resultat = ia_generation._appeler_ia(prompt, cfg)
        ctx.etape(
            f"appel {cfg['moteur']}", moteur=ctx.moteur,
            duree_ms=int((time.monotonic() - t0) * 1000),
            detail=f"{len(flashcards)} flashcard(s), {len(quiz)} question(s) de quiz à vérifier",
        )
        ctx.resultat = json.dumps(resultat, ensure_ascii=False)[:4000]

    with db.session() as conn:
        conn.execute("UPDATE cours SET ia_fiabilite = ? WHERE id = ?", (resultat.get("score_global"), cours_id))
