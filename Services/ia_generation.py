"""
Moteur IA de Ghost School : génération (résumé, flashcards, quiz) pour un
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

from . import db, ocr
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

# En dessous de ce seuil, le texte source est presque certainement le
# signe d'une extraction ratée (PDF scanné mal OCRisé, timeout partiel...)
# plutôt qu'un cours réellement aussi court : générer quand même produirait
# un résumé/flashcards hors sujet (le modèle "invente" à partir de presque
# rien) plutôt que de signaler clairement le problème. Volontairement bas
# (un cours normal en a facilement 10 à 100 fois plus) pour ne jamais
# bloquer un cours légitimement bref.
TEXTE_SOURCE_MIN_CHARS = 200

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
    ollama_chunk_size = db.get_parametre(conn, "ollama_chunk_size")
    try:
        ollama_chunk_size = int(ollama_chunk_size) if ollama_chunk_size is not None else IA_TEXTE_MAX_CHARS
    except ValueError:
        ollama_chunk_size = IA_TEXTE_MAX_CHARS
    # Activé par défaut (comportement historique) : un cours trop long pour
    # tenir dans ollama_chunk_size est découpé en plusieurs parties. Peut être
    # désactivé depuis l'écran admin "Paramétrage" pour envoyer le texte
    # entier en un seul appel (ex. modèle local à grand contexte) — voir
    # `_texte_pour_prompt`.
    decoupage_actif = db.get_parametre(conn, "ollama_decoupage_actif", "1") == "1"
    return {
        "moteur": moteur,
        "anthropic_api_key": db.get_parametre(conn, "anthropic_api_key", ANTHROPIC_API_KEY),
        "gemini_api_key": db.get_parametre(conn, "gemini_api_key", GEMINI_API_KEY),
        "gemini_model": db.get_parametre(conn, "gemini_model", GEMINI_MODEL) or GEMINI_MODEL,
        "ollama_url": db.get_parametre(conn, "ollama_url", OLLAMA_URL) or OLLAMA_URL,
        "ollama_model": db.get_parametre(conn, "ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL,
        # Taille max (caractères) envoyée à Ollama en un seul appel — au-delà,
        # le texte source est découpé en plusieurs parties résumées (voir
        # `_texte_pour_prompt`). Ollama local a un contexte limité par le
        # matériel ; Claude et Gemini acceptent un contexte bien plus grand,
        # donc ce découpage ne s'applique qu'à Ollama (voir `_texte_pour_prompt`).
        "ollama_chunk_size": ollama_chunk_size,
        "ollama_decoupage_actif": decoupage_actif,
        # Consigne personnalisable des prompts (voir écran admin Paramétrage
        # → Génération IA → Prompts) : None si l'admin n'a rien personnalisé,
        # auquel cas `construire_prompt_*` retombe sur le texte par défaut
        # (PROMPT_*_CONSIGNE_DEFAUT ci-dessous). Le format JSON de sortie,
        # lui, n'est jamais personnalisable : le code qui lit la réponse de
        # l'IA dépend de ces clés exactes (voir `resultat.get("flashcards")`
        # etc. dans generer_pour_cours/completer_pour_cours).
        "prompt_generation_consigne": db.get_parametre(conn, "ia_prompt_generation_consigne", "") or None,
        "prompt_completion_consigne": db.get_parametre(conn, "ia_prompt_completion_consigne", "") or None,
    }


def lister_modeles_ollama(url: str) -> list[str]:
    """
    Interroge `{url}/api/tags` pour lister les modèles installés sur ce
    serveur Ollama — utilisé par l'écran admin "Paramétrage" pour proposer
    un choix plutôt que de laisser taper le nom du modèle à la main (et
    vérifier au passage que l'URL saisie est bien joignable).
    """
    req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise GenerationError(f"Ollama injoignable sur {url} : {e}") from e
    except TimeoutError as e:
        raise GenerationError(f"Ollama n'a pas répondu à temps ({url})") from e
    except json.JSONDecodeError as e:
        raise GenerationError(f"Réponse Ollama inexploitable : {e}") from e
    return [m["name"] for m in body.get("models", []) if m.get("name")]


# Chaque prompt envoyé à l'IA a 3 parties, dans cet ordre : le contenu du
# cours (jamais personnalisable — c'est la matière première), une CONSIGNE
# personnalisable depuis l'écran admin Paramétrage → Génération IA →
# Prompts (ce que ce fichier définit par défaut ci-dessous), et un format
# JSON de sortie fixe, non personnalisable, car le code qui lit la réponse
# de l'IA dépend de ces clés exactes (voir plus bas `resultat.get(...)`).
# `construire_prompt_generation`/`construire_prompt_completion` assemblent
# les 3 parties ; voir `config_ia` pour la résolution de la consigne
# effective (personnalisée ou par défaut).

PROMPT_GENERATION_CONSIGNE_DEFAUT = """À partir de ce cours, produis :
1. Un résumé COURT (2 à 4 phrases, l'essentiel seulement).
2. Un résumé DÉTAILLÉ, dont la longueur doit être proportionnelle à la
   longueur du cours ci-dessus (plus le cours est long/dense, plus ce
   résumé doit être développé) — ne sacrifie pas les éléments importants
   juste pour rester court.
3. Exactement {nb_flashcards} flashcards de révision (question courte, réponse courte,
   1 phrase maximum).
4. Exactement {nb_quiz} questions de quiz à choix multiple (4 options, une seule correcte)."""

GENERATION_JSON_FORMAT = (
    "Réponds UNIQUEMENT avec un JSON valide, rien d'autre, dans ce format exact, en français,\n"
    "sans markdown ni texte avant ou après le JSON :\n"
    '{"resume_court": "...", "resume_detaille": "...", "flashcards": [{"question": "...", "reponse": "..."}], '
    '"quiz": [{"question": "...", "options": ["...", "...", "...", "..."], "reponse_index": 0}]}'
)

PROMPT_COMPLEMENT_CONSIGNE_DEFAUT = """Voici les questions déjà utilisées pour ce cours (à ne pas répéter, même reformulées) :
Flashcards existantes : {questions_flashcards}
Quiz existant : {questions_quiz}

Génère {n} NOUVELLES flashcards de révision (question courte, réponse
courte, 1 phrase maximum) et {n} NOUVELLES questions de quiz à choix
multiple (4 options, une seule correcte), à partir de ce même cours.
Elles doivent porter sur des notions ou aspects DIFFÉRENTS de ceux déjà
couverts ci-dessus : une question reformulée avec d'autres mots mais qui
attend la même réponse (même notion) compte comme une répétition, pas
comme une nouvelle question. Privilégie des éléments du cours pas encore
interrogés plutôt que de redemander ce qui l'a déjà été sous un autre angle."""

COMPLEMENT_JSON_FORMAT = (
    "Réponds UNIQUEMENT avec un JSON valide, rien d'autre, dans ce format exact,\n"
    "en français, sans markdown ni texte avant ou après le JSON :\n"
    '{"flashcards": [{"question": "...", "reponse": "..."}], '
    '"quiz": [{"question": "...", "options": ["...", "...", "...", "..."], "reponse_index": 0}]}'
)


def construire_prompt_generation(texte: str, nb_flashcards: int, nb_quiz: int, consigne: str | None = None) -> str:
    consigne = (consigne or PROMPT_GENERATION_CONSIGNE_DEFAUT).replace(
        "{nb_flashcards}", str(nb_flashcards)).replace("{nb_quiz}", str(nb_quiz))
    return f"{texte}\n\n{consigne}\n\n{GENERATION_JSON_FORMAT}\n"


def construire_prompt_completion(
    texte: str, n: int, questions_flashcards: str, questions_quiz: str, consigne: str | None = None,
) -> str:
    consigne = (
        (consigne or PROMPT_COMPLEMENT_CONSIGNE_DEFAUT)
        .replace("{n}", str(n))
        .replace("{questions_flashcards}", questions_flashcards)
        .replace("{questions_quiz}", questions_quiz)
    )
    return f"{texte}\n\n{consigne}\n\n{COMPLEMENT_JSON_FORMAT}\n"


def _appeler_ollama(prompt: str, url: str, model: str) -> dict:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "format": "json",
        "think": False,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        # qwen3:14b en local (CPU) peut être lent : jusqu'à ~30 min observés
        # en pratique par Cédric sur un PDF de cours complet (flashcard.sh).
        with urllib.request.urlopen(req, timeout=1800) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise GenerationError(f"Ollama injoignable sur {url} : {e}") from e
    except TimeoutError as e:
        raise GenerationError(f"Ollama n'a pas répondu à temps ({url})") from e

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
    return _appeler_ollama(prompt, cfg["ollama_url"], cfg["ollama_model"])


def _nom_moteur(cfg: dict) -> str:
    if cfg["moteur"] == "gemini":
        return cfg["gemini_model"]
    if cfg["moteur"] == "claude":
        return CLAUDE_MODEL
    return cfg["ollama_model"]


# --- Assistant conversationnel : même moteur configuré, réponse texte -----
# (pas de JSON forcé ici, contrairement à la génération — juste une
# réponse en français comme dans une conversation normale).

def _chat_ollama(messages: list[dict], system_prompt: str, url: str, model: str) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}]
        + [{"role": m["role"], "content": m["text"]} for m in messages],
        "stream": False,
        "think": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        # Réponse interactive : timeout nettement plus court que pour la
        # génération en arrière-plan (l'élève attend devant son écran).
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise GenerationError(f"Ollama injoignable sur {url} : {e}") from e
    except TimeoutError as e:
        raise GenerationError(f"Ollama n'a pas répondu à temps ({url})") from e

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
    return _chat_ollama(messages, system_prompt, cfg["ollama_url"], cfg["ollama_model"])


def _texte_source(conn, cours: dict) -> str:
    """
    Texte complet (description + documents transcrits), SANS troncature :
    un cours long doit pouvoir être découpé en plusieurs passes (voir
    `_texte_pour_prompt`) plutôt que de perdre silencieusement tout ce qui
    dépasse `IA_TEXTE_MAX_CHARS`.
    """
    morceaux = []
    if cours.get("description"):
        morceaux.append(cours["description"])
    docs = conn.execute(
        "SELECT texte_extrait FROM documents WHERE cours_id = ? AND texte_extrait IS NOT NULL",
        (cours["id"],),
    ).fetchall()
    morceaux.extend(d["texte_extrait"] for d in docs if d["texte_extrait"])
    return "\n\n".join(morceaux)


CHUNK_SYSTEM_PROMPT = (
    "Tu résumes un extrait de cours pour un usage pédagogique. Produis un "
    "résumé dense et fidèle de tout le contenu factuel de cet extrait "
    "(définitions, notions clés, exemples importants), en français, en "
    "texte continu, sans titre, sans markdown, sans commentaire ni "
    "reformulation de la consigne — réponds uniquement avec le résumé."
)


def _decouper_texte(texte: str, taille_max: int) -> list[str]:
    """
    Découpe `texte` en parties d'au plus `taille_max` caractères, sur des
    frontières de paragraphe (ligne vide) plutôt qu'en coupant au milieu
    d'une phrase. Renvoie `[texte]` tel quel s'il tient déjà dans une
    seule partie — c'est le cas de la grande majorité des cours.
    """
    if len(texte) <= taille_max:
        return [texte]
    paragraphes = texte.split("\n\n")
    parties = []
    courante = ""
    for p in paragraphes:
        candidate = f"{courante}\n\n{p}" if courante else p
        if len(candidate) > taille_max and courante:
            parties.append(courante)
            courante = p
        else:
            courante = candidate
    if courante:
        parties.append(courante)

    # Un paragraphe (sans ligne vide interne) peut lui-même dépasser
    # `taille_max` — la boucle ci-dessus ne le découpe pas puisqu'il n'y a
    # aucune frontière où s'arrêter. On le tranche alors brutalement plutôt
    # que de dépasser silencieusement la taille prévue pour un appel.
    resultat = []
    for partie in parties:
        if len(partie) <= taille_max:
            resultat.append(partie)
        else:
            resultat.extend(partie[i:i + taille_max] for i in range(0, len(partie), taille_max))
    return resultat


def _texte_pour_prompt(ctx, texte: str, cfg: dict) -> str:
    """
    Réduit `texte` à une taille exploitable en un seul appel de génération —
    UNIQUEMENT pour Ollama, dont le contexte est limité par le matériel
    local. Claude et Gemini acceptent un contexte largement suffisant pour
    un cours entier : le texte leur est transmis tel quel, sans découpage
    (aucun appel supplémentaire, aucune perte de qualité liée au découpage).

    Pour Ollama, le découpage peut lui-même être désactivé depuis ce même
    bloc (bouton "Découpage automatique") — dans ce cas le texte entier est
    envoyé sans troncature, comme pour Claude/Gemini, sans limite de taille
    demandée à l'admin. Sinon, un cours qui tient déjà dans
    `cfg["ollama_chunk_size"]` part tel quel ; un cours plus long est
    découpé en parties (voir `_decouper_texte`), chacune résumée
    séparément ("map"), puis les résumés sont concaténés ("reduce") pour
    servir de texte source à la génération finale — stratégie "plusieurs
    passes", réglable depuis le bloc Ollama de l'écran admin "Paramétrage"
    (sous-menu "Génération IA").

    Chaque passe est journalisée via `ctx.etape(...)` (voir
    Services/db.py::log_traitement) pour que l'admin voie, dans l'écran
    "Traitements", le détail intermédiaire (chaque résumé de partie) et
    pas seulement le résultat final.
    """
    if cfg["moteur"] != "ollama" or not cfg["ollama_decoupage_actif"]:
        return texte

    taille_max = cfg["ollama_chunk_size"]
    parties = _decouper_texte(texte, taille_max)
    if len(parties) == 1:
        return parties[0]

    ctx.etape(
        "découpage", statut="info",
        detail=(
            f"{len(texte)} caractère(s) au total, trop long pour un seul appel "
            f"({taille_max} max) : {len(parties)} partie(s)"
        ),
    )
    resumes = []
    for i, partie in enumerate(parties, start=1):
        t0 = time.monotonic()
        resume = repondre_conversation([{"role": "user", "text": partie}], CHUNK_SYSTEM_PROMPT, cfg)
        resumes.append(resume)
        ctx.etape(
            f"résumé partie {i}/{len(parties)}", moteur=_nom_moteur(cfg),
            duree_ms=int((time.monotonic() - t0) * 1000),
            detail=f"{len(partie)} → {len(resume)} caractère(s)",
            resultat=resume,
        )
    fusion = "\n\n".join(resumes)
    ctx.etape("fusion des résumés", statut="info", detail=f"{len(fusion)} caractère(s) au total", resultat=fusion)
    return fusion


def _transcrire_documents_manquants(cours_id: int) -> None:
    """
    Rattrapage avant toute lecture du contenu source : transcrit tout
    document de ce cours encore jamais passé à l'OCR (texte_extrait NULL).

    En théorie `pronote_sync` déclenche déjà la transcription dès le
    téléchargement — mais pour un document synchronisé avant l'ajout de ce
    mécanisme, ou dont la transcription automatique a échoué, `_texte_source`
    ne renvoyait jusque-là que la description Pronote (souvent un simple
    horaire/titre de chapitre, ex. "45'. Chapitre 1"), d'où des générations
    hors sujet malgré un document bien attaché.
    """
    with db.session() as conn:
        ids = [
            row["id"] for row in conn.execute(
                "SELECT id FROM documents WHERE cours_id = ? AND texte_extrait IS NULL", (cours_id,)
            ).fetchall()
        ]
    for document_id in ids:
        try:
            ocr.transcribe_document(document_id)
        except Exception:
            log.warning("Échec de la transcription du document id=%s avant génération IA", document_id, exc_info=True)


def generer_pour_cours(cours_id: int) -> None:
    """Génère résumés (court + détaillé)/flashcards/quiz pour un cours et les enregistre sur la ligne `cours`."""
    _transcrire_documents_manquants(cours_id)
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

    if len(texte.strip()) < TEXTE_SOURCE_MIN_CHARS:
        with db.session() as conn:
            conn.execute(
                "UPDATE cours SET ia_statut = 'echec', ia_erreur = ? WHERE id = ?",
                (
                    f"Texte source trop court ({len(texte.strip())} caractère(s)) pour générer un résumé "
                    "fiable — l'extraction du document (pdftotext/OCR) a probablement échoué ou n'a "
                    "récupéré presque rien. Vérifie le document source plutôt que de relancer tel quel.",
                    cours_id,
                ),
            )
        return

    try:
        with db.log_traitement("ia_generation", "cours", cours_id) as ctx:
            ctx.moteur = _nom_moteur(cfg)
            ctx.etape(
                "lecture du contenu source",
                detail=f"{len(texte)} caractère(s) (description + documents transcrits)",
                resultat=texte,
            )

            texte_pour_prompt = _texte_pour_prompt(ctx, texte, cfg)
            prompt = construire_prompt_generation(
                texte_pour_prompt, FLASHCARDS_PAR_COURS, QUESTIONS_QUIZ_PAR_COURS, cfg["prompt_generation_consigne"],
            )

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
               SET ia_statut = 'pret', ia_resume = ?, ia_resume_detaille = ?, ia_flashcards = ?, ia_quiz = ?,
                   ia_erreur = NULL, ia_texte_source = ?
               WHERE id = ?""",
            (
                resultat.get("resume_court", resultat.get("resume", "")),
                resultat.get("resume_detaille", ""),
                json.dumps(resultat.get("flashcards", []), ensure_ascii=False),
                json.dumps(resultat.get("quiz", []), ensure_ascii=False),
                texte_pour_prompt,
                cours_id,
            ),
        )


def completer_pour_cours(cours_id: int, n: int = N_COMPLEMENT) -> None:
    """
    Ajoute `n` flashcards et `n` questions de quiz supplémentaires à une
    génération déjà en place (bouton "+ 10" côté frontend), sans toucher
    au résumé ni aux flashcards/quiz déjà générés — juste un complément.
    """
    _transcrire_documents_manquants(cours_id)
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
        texte_memorise = cours.get("ia_texte_source")
        cfg = config_ia(conn)
        flashcards_existantes = json.loads(cours["ia_flashcards"]) if cours["ia_flashcards"] else []
        quiz_existant = json.loads(cours["ia_quiz"]) if cours["ia_quiz"] else []
        conn.execute("UPDATE cours SET ia_statut = 'en_cours' WHERE id = ?", (cours_id,))

    try:
        with db.log_traitement("ia_completion", "cours", cours_id) as ctx:
            ctx.moteur = _nom_moteur(cfg)

            if texte_memorise:
                # Même texte que la génération initiale — pas de nouvel appel
                # de découpage/résumé, et surtout pas de résumé DIFFÉRENT à
                # chaque complément (le résumé d'une partie n'est pas
                # déterministe d'un appel à l'autre).
                ctx.etape(
                    "lecture du contenu source",
                    detail=f"{len(texte_memorise)} caractère(s) (identique à la génération initiale)",
                    resultat=texte_memorise,
                )
                texte_pour_prompt = texte_memorise
            else:
                # Génération initiale antérieure à l'ajout de ce champ : pas
                # de texte mémorisé, on retombe sur l'ancien comportement.
                with db.session() as conn:
                    texte_brut = _texte_source(conn, cours)
                if len(texte_brut.strip()) < TEXTE_SOURCE_MIN_CHARS:
                    raise GenerationError(
                        f"Texte source trop court ({len(texte_brut.strip())} caractère(s)) pour compléter "
                        "de façon fiable — l'extraction du document a probablement échoué."
                    )
                ctx.etape(
                    "lecture du contenu source",
                    detail=f"{len(texte_brut)} caractère(s) (description + documents transcrits)",
                    resultat=texte_brut,
                )
                texte_pour_prompt = _texte_pour_prompt(ctx, texte_brut, cfg)

            ctx.etape("lecture de l'existant", detail=f"{len(flashcards_existantes)} flashcard(s), {len(quiz_existant)} question(s) déjà en place")

            prompt = construire_prompt_completion(
                texte_pour_prompt, n,
                "; ".join(c["question"] for c in flashcards_existantes) or "(aucune)",
                "; ".join(q["question"] for q in quiz_existant) or "(aucune)",
                cfg["prompt_completion_consigne"],
            )

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
