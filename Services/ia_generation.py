"""
Moteur IA de Ghost Cards : génération (résumé, flashcards, quiz) pour un
cours, ET réponses de l'assistant conversationnel — les deux passent par
le même moteur configuré (Ollama par défaut, Claude ou Gemini en option),
résolu par `config_ia`. Changer de moteur dans l'écran admin
"Paramétrage" change donc aussi bien la génération que l'assistant, pas
l'un sans l'autre.

Ollama en local est gratuit et privé — approprié pour le gros volume de
génération potentiel (des dizaines de cours sur l'année). Suit le
pattern qui fonctionne déjà chez Cédric (`flashcard.sh`) :
`POST {OLLAMA_URL}/api/generate` avec `format: "json"` et `think: false`
pour la génération ; `POST {OLLAMA_URL}/api/chat` (multi-tour) pour
l'assistant.

Claude et Gemini sont proposés en option pour qui préfère la
rapidité/qualité cloud à la gratuité locale (le contenu des cours part
alors chez Anthropic/Google). Les deux clés (Anthropic, Gemini) et le
choix de moteur sont modifiables à chaud depuis l'écran admin
"Paramétrage" (table `parametres`, voir `config_ia` ci-dessous) — pas
besoin de redémarrer le service. `.env` (`ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`) ne sert que de valeur de départ, pratique pour un
premier déploiement avant d'aller cliquer dans l'admin.

Le résultat d'une génération est stocké directement sur la ligne `cours`
(colonnes `ia_*`, voir Services/db.py::init_db) plutôt que dans une table
séparée : une génération remplace la précédente, il n'y a pas besoin
d'historique des contenus eux-mêmes (l'historique des *tentatives*, avec
le détail de chaque étape, reste dans `traitements`, comme pour l'OCR).
"""
import json
import logging
import time
import urllib.error
import urllib.request

from . import db
from .config import (
    IA_ENGINE,
    OLLAMA_URL,
    OLLAMA_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    ANTHROPIC_API_KEY,
    FLASHCARDS_PAR_COURS,
    QUESTIONS_QUIZ_PAR_COURS,
    IA_TEXTE_MAX_CHARS,
)

CLAUDE_MODEL = "claude-sonnet-5"

log = logging.getLogger("ghostcards.ia_generation")

# Nombre de flashcards/questions ajoutées par un clic sur "+ 10" une fois
# une génération déjà en place (voir completer_pour_cours).
N_COMPLEMENT = 10

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GenerationError(Exception):
    pass


def config_ia(conn) -> dict:
    """
    Résout le moteur IA effectif : valeur enregistrée via l'écran admin
    "Paramétrage" (table `parametres`) si elle existe, sinon la valeur de
    départ définie dans .env (Services/config.py).
    """
    moteur = db.get_parametre(conn, "ia_moteur", IA_ENGINE)
    if moteur not in ("ollama", "gemini", "claude"):
        moteur = "ollama"
    return {
        "moteur": moteur,
        "anthropic_api_key": db.get_parametre(conn, "anthropic_api_key", ANTHROPIC_API_KEY),
        "gemini_api_key": db.get_parametre(conn, "gemini_api_key", GEMINI_API_KEY),
        "gemini_model": db.get_parametre(conn, "gemini_model", GEMINI_MODEL) or GEMINI_MODEL,
    }


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


def _appeler_gemini(prompt: str, api_key: str, model: str) -> dict:
    if not api_key:
        raise GenerationError(
            "Clé Gemini non configurée (écran admin Paramétrage, ou GEMINI_API_KEY dans .env)."
        )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model), data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise GenerationError(f"Gemini a refusé la requête (HTTP {e.code}) : {detail[:300]}") from e
    except urllib.error.URLError as e:
        raise GenerationError(f"Gemini injoignable : {e}") from e

    try:
        texte = body["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(texte)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise GenerationError(f"Réponse Gemini inexploitable (pas un JSON valide) : {e}") from e


_anthropic_client = None
_anthropic_client_key = None


def _client_claude(api_key: str):
    """
    Client Anthropic mis en cache, mais recréé si la clé change (l'admin
    peut la modifier à chaud depuis l'écran "Paramétrage" — contrairement
    à Gemini, le SDK Anthropic fige la clé à la construction du client).
    """
    if not api_key:
        raise GenerationError(
            "Clé Anthropic non configurée (écran admin Paramétrage, ou ANTHROPIC_API_KEY dans .env)."
        )
    import anthropic

    global _anthropic_client, _anthropic_client_key
    if _anthropic_client is None or _anthropic_client_key != api_key:
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
        _anthropic_client_key = api_key
    return _anthropic_client


def _appeler_claude(prompt: str, api_key: str) -> dict:
    import anthropic

    client = _client_claude(api_key)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        raise GenerationError(f"Claude a refusé la requête : {e}") from e

    texte = "".join(b.text for b in response.content if b.type == "text").strip()
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        # Contrairement à Ollama/Gemini, rien ne force Claude à ne renvoyer
        # QUE du JSON : on retente en extrayant le premier bloc {...} au cas
        # où il aurait ajouté une phrase avant/après malgré la consigne.
        debut, fin = texte.find("{"), texte.rfind("}")
        if debut != -1 and fin != -1:
            try:
                return json.loads(texte[debut:fin + 1])
            except json.JSONDecodeError:
                pass
        raise GenerationError("Réponse Claude inexploitable (pas un JSON valide).")


def _appeler_ia(prompt: str, cfg: dict) -> dict:
    if cfg["moteur"] == "gemini":
        return _appeler_gemini(prompt, cfg["gemini_api_key"], cfg["gemini_model"])
    if cfg["moteur"] == "claude":
        return _appeler_claude(prompt, cfg["anthropic_api_key"])
    return _appeler_ollama(prompt)


def _nom_moteur(cfg: dict) -> str:
    if cfg["moteur"] == "gemini":
        return cfg["gemini_model"]
    if cfg["moteur"] == "claude":
        return CLAUDE_MODEL
    return OLLAMA_MODEL


# --- Assistant conversationnel : même moteur configuré, réponse texte -----
# (pas de JSON forcé ici, contrairement à la génération — juste une
# réponse en français comme dans une conversation normale).

def _chat_ollama(messages: list[dict], system_prompt: str) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system_prompt}]
        + [{"role": m["role"], "content": m["text"]} for m in messages],
        "stream": False,
        "think": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        # Réponse interactive : timeout nettement plus court que pour la
        # génération en arrière-plan (l'élève attend devant son écran).
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise GenerationError(f"Ollama injoignable sur {OLLAMA_URL} : {e}") from e
    except TimeoutError as e:
        raise GenerationError(f"Ollama n'a pas répondu à temps ({OLLAMA_URL})") from e

    try:
        return body["message"]["content"]
    except KeyError as e:
        raise GenerationError("Réponse Ollama inexploitable (pas de message).") from e


def _chat_gemini(messages: list[dict], system_prompt: str, api_key: str, model: str) -> str:
    if not api_key:
        raise GenerationError(
            "Clé Gemini non configurée (écran admin Paramétrage, ou GEMINI_API_KEY dans .env)."
        )
    # Gemini attend "model" (pas "assistant") pour le tour de l'IA.
    contenus = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["text"]}]}
        for m in messages
    ]
    payload = json.dumps({
        "contents": contenus,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model), data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise GenerationError(f"Gemini a refusé la requête (HTTP {e.code}) : {detail[:300]}") from e
    except urllib.error.URLError as e:
        raise GenerationError(f"Gemini injoignable : {e}") from e

    try:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise GenerationError("Réponse Gemini inexploitable (pas de contenu).") from e


def _chat_claude(messages: list[dict], system_prompt: str, api_key: str) -> str:
    import anthropic

    client = _client_claude(api_key)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=600, system=system_prompt,
            messages=[{"role": m["role"], "content": m["text"]} for m in messages],
        )
    except anthropic.APIError as e:
        raise GenerationError(f"Claude a refusé la requête : {e}") from e
    return "".join(b.text for b in response.content if b.type == "text").strip()


def repondre_conversation(messages: list[dict], system_prompt: str, cfg: dict) -> str:
    """
    Réponse de l'assistant conversationnel via le moteur configuré (voir
    `config_ia`) — appelé par POST /api/assistant. `messages` : liste de
    `{"role": "user"|"assistant", "text": "..."}`.
    """
    if cfg["moteur"] == "gemini":
        return _chat_gemini(messages, system_prompt, cfg["gemini_api_key"], cfg["gemini_model"])
    if cfg["moteur"] == "claude":
        return _chat_claude(messages, system_prompt, cfg["anthropic_api_key"])
    return _chat_ollama(messages, system_prompt)


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
        cfg = config_ia(conn)
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
            ctx.moteur = _nom_moteur(cfg)
            ctx.etape("lecture du contenu source", detail=f"{len(texte)} caractère(s) (description + documents transcrits)")

            t0 = time.monotonic()
            resultat = _appeler_ia(prompt, cfg)
            ctx.etape(f"appel {cfg['moteur']}", moteur=_nom_moteur(cfg), duree_ms=int((time.monotonic() - t0) * 1000),
                       detail="format=json" if cfg["moteur"] == "gemini" else "format=json, think=false")

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
        cfg = config_ia(conn)
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
            ctx.moteur = _nom_moteur(cfg)
            ctx.etape("lecture de l'existant", detail=f"{len(flashcards_existantes)} flashcard(s), {len(quiz_existant)} question(s) déjà en place")

            t0 = time.monotonic()
            resultat = _appeler_ia(prompt, cfg)
            ctx.etape(f"appel {cfg['moteur']}", moteur=_nom_moteur(cfg), duree_ms=int((time.monotonic() - t0) * 1000))

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
