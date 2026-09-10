"""
Extraction de texte : PDF Pronote (avec ou sans couche de texte) et photos
de notes manuscrites déposées par les élèves.

Moteur par défaut : PaddleOCR, local et gratuit (voir HANDOFF.md pour
l'historique de la décision — nécessite un venv Python <=3.13). Vision
Claude reste disponible en repli si PaddleOCR déçoit sur de l'écriture
manuscrite réelle. Le choix (et la clé Anthropic, partagée avec la
génération IA/l'assistant) se change à chaud depuis l'écran admin
"Paramétrage" — voir `config_ocr` ci-dessous ; `OCR_ENGINE` dans .env ne
sert que de valeur de départ.

Chaque appel à `transcribe_document`/`transcribe_note` journalise son
déroulement dans la table `traitements` (durée, succès/échec, résultat) :
c'est ce qui permet à Cédric de voir le rendu de chaque action et de la
relancer si besoin, sans avoir à fouiller les logs du service.
"""
import base64
import logging
import subprocess
import tempfile
import time
from pathlib import Path

from . import db
from .config import ANTHROPIC_API_KEY, OCR_ENGINE, OCR_MAX_PAGES, DOCUMENTS_DIR

log = logging.getLogger("ghostcards.ocr")

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

_log_traitement = db.log_traitement  # partagé avec Services/ia_generation.py et pronote_sync.py


class OcrError(Exception):
    pass


def config_ocr(conn) -> dict:
    """
    Résout la configuration OCR effective : valeurs enregistrées via
    l'écran admin "Paramétrage" (table `parametres`) si elles existent,
    sinon les valeurs de départ définies dans .env (Services/config.py).
    La clé Anthropic est PARTAGÉE avec la génération IA/l'assistant (même
    compte, voir Services/ia_generation.py::config_ia) — pas de champ
    séparé à maintenir pour l'OCR.
    """
    moteur = db.get_parametre(conn, "ocr_engine", OCR_ENGINE)
    if moteur not in ("paddleocr", "claude"):
        moteur = "paddleocr"
    return {
        "moteur": moteur,
        "anthropic_api_key": db.get_parametre(conn, "anthropic_api_key", ANTHROPIC_API_KEY),
    }


# --- Extraction PDF (texte natif) -------------------------------------------

def extract_pdf_text(path: Path) -> str:
    """Texte natif d'un PDF via poppler-utils. Vide si le PDF est scanné (pas de couche de texte)."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError as e:
        # Sans ça, l'erreur brute ("[Errno 2] No such file or directory:
        # 'pdftotext'") remonte telle quelle dans le détail du traitement.
        # Piège vécu : le paquet peut très bien être installé (poppler-utils)
        # et l'erreur persister quand même si le PATH du service systemd est
        # restreint au venv (voir BackEnd/deploy/ghostcards.service) — les
        # binaires système comme pdftotext n'y sont alors pas visibles.
        raise OcrError(
            "pdftotext introuvable — vérifie qu'il est installé (paquet système "
            "poppler-utils, `sudo apt install poppler-utils`) ET accessible depuis "
            "l'environnement du service (le PATH de BackEnd/deploy/ghostcards.service "
            "doit inclure /usr/bin en plus du venv)."
        ) from e
    if result.returncode != 0:
        raise OcrError(f"pdftotext a échoué sur {path.name} : {result.stderr.strip()}")
    return result.stdout


def count_pdf_pages(path: Path) -> int:
    try:
        result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return 1  # pdftotext/pdfinfo introuvables : déjà signalé clairement par extract_pdf_text, appelé avant.
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    return 1


def is_text_sparse(text: str, num_pages: int) -> bool:
    """
    Heuristique : un PDF scanné sans couche de texte ne renvoie quasiment
    rien via pdftotext. Seuil large (40 caractères/page) — un cours normal
    en a nettement plus.
    """
    if num_pages <= 0:
        return True
    return (len(text.strip()) / num_pages) < 40


def pdf_to_images(pdf_path: Path, out_dir: Path, max_pages: int = OCR_MAX_PAGES) -> list[Path]:
    """Convertit les pages d'un PDF en PNG (via poppler-utils), limité à max_pages."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    try:
        result = subprocess.run(
            ["pdftoppm", "-png", "-r", "150", "-l", str(max_pages), str(pdf_path), str(prefix)],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError as e:
        raise OcrError(
            "pdftoppm introuvable — vérifie qu'il est installé (paquet système "
            "poppler-utils, `sudo apt install poppler-utils`) ET accessible depuis "
            "l'environnement du service (le PATH de BackEnd/deploy/ghostcards.service "
            "doit inclure /usr/bin en plus du venv)."
        ) from e
    if result.returncode != 0:
        raise OcrError(f"pdftoppm a échoué sur {pdf_path.name} : {result.stderr.strip()}")
    return sorted(out_dir.glob("page-*.png"))


# --- OCR image ---------------------------------------------------------------

OCR_PROMPT = (
    "Transcris fidèlement tout le texte visible sur cette image (cours, notes "
    "manuscrites ou imprimées). Rends un markdown structuré (titres, listes, "
    "tableaux si présents) sans rien commenter ni ajouter. Si l'image est "
    "illisible ou vide, réponds uniquement '(rien à transcrire)'."
)

_anthropic_client = None
_anthropic_client_key = None


def _anthropic(api_key: str):
    """
    Client Anthropic mis en cache, mais recréé si la clé change (l'admin
    peut la modifier à chaud depuis l'écran "Paramétrage" — voir
    Services/ia_generation.py::_client_claude, même logique).
    """
    global _anthropic_client, _anthropic_client_key
    if not api_key:
        raise OcrError("Clé Anthropic non configurée (écran admin Paramétrage, ou ANTHROPIC_API_KEY dans .env).")
    if _anthropic_client is None or _anthropic_client_key != api_key:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
        _anthropic_client_key = api_key
    return _anthropic_client


def ocr_image_claude(image_path: Path, api_key: str) -> str:
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower(), "image/png")
    data = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
    response = _anthropic(api_key).messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": OCR_PROMPT},
            ],
        }],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


_paddleocr_instance = None


def _paddleocr():
    """
    Charge et met en cache le pipeline PaddleOCR (l'instanciation charge les
    modèles de détection/orientation/reconnaissance en mémoire — coûteux,
    donc fait une seule fois par process, pas à chaque image).
    Nécessite un venv Python <=3.13 (PaddlePaddle n'a pas de wheels pour
    Python 3.14 au moment de l'écriture — voir HANDOFF.md).
    """
    global _paddleocr_instance
    if _paddleocr_instance is None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise OcrError(
                "paddleocr n'est pas installé dans ce venv (nécessite Python <=3.13 "
                "— voir HANDOFF.md, section OCR)."
            ) from e
        _paddleocr_instance = PaddleOCR(
            lang="fr",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _paddleocr_instance


def ocr_image_paddleocr(image_path: Path) -> str:
    """
    Moteur local et gratuit (voir HANDOFF.md pour le choix de moteur par
    défaut). Le premier appel télécharge les modèles PP-OCR (mis en cache
    par PaddleX/PaddleOCR, hors dépôt) — nécessite un accès réseau la
    première fois seulement.
    """
    lignes = []
    for res in _paddleocr().predict(str(image_path)):
        data = res.json if hasattr(res, "json") else res
        # La forme exacte (racine ou sous 'res') a varié entre versions de
        # PaddleOCR/PaddleX — on couvre les deux plutôt que de deviner.
        textes = data.get("rec_texts") or data.get("res", {}).get("rec_texts", [])
        lignes.extend(t for t in textes if t)
    return "\n".join(lignes)


def _ocr_engine_fn(cfg: dict):
    if cfg["moteur"] == "claude":
        return lambda image_path: ocr_image_claude(image_path, cfg["anthropic_api_key"])
    return ocr_image_paddleocr


# --- Orchestrateurs ------------------------------------------------------------

def _enregistrer_texte_document(document_id: int, texte: str) -> None:
    with db.session() as conn:
        conn.execute("UPDATE documents SET texte_extrait = ? WHERE id = ?", (texte, document_id))


def transcribe_document(document_id: int) -> None:
    """Extrait le texte d'un document Pronote (PDF natif, PDF scanné, ou image)."""
    with db.session() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        cfg = config_ocr(conn)
    if doc is None or not doc["chemin_local"] or doc["chemin_local"].startswith("lien:"):
        return  # lien externe, pas de fichier local à transcrire

    path = DOCUMENTS_DIR.parent / doc["chemin_local"]
    if not path.exists():
        return

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        _transcrire_pdf_document(document_id, path, cfg)
    elif suffix in _MEDIA_TYPES:
        _transcrire_image_document(document_id, path, cfg)
    # autres types (ex. .docx) : pas pris en charge pour l'instant


def _transcrire_pdf_document(document_id: int, path: Path, cfg: dict) -> None:
    with _log_traitement("transcription_document", "document", document_id) as ctx:
        t0 = time.monotonic()
        texte = extract_pdf_text(path)
        num_pages = count_pdf_pages(path)
        ctx.etape(
            "pdftotext", moteur="pdftotext",
            detail=f"{len(texte.strip())} caractère(s) extrait(s) sur {num_pages} page(s)",
            duree_ms=int((time.monotonic() - t0) * 1000),
        )

        if not is_text_sparse(texte, num_pages):
            ctx.moteur = "pdftotext"
            ctx.resultat = texte
        else:
            ctx.etape(
                "détection", statut="info",
                detail=f"texte jugé trop pauvre (seuil 40 caractères/page) — bascule sur l'OCR ({cfg['moteur']})",
            )
            with tempfile.TemporaryDirectory() as tmp:
                images = pdf_to_images(path, Path(tmp))
                morceaux = []
                for i, img in enumerate(images, start=1):
                    t1 = time.monotonic()
                    texte_page = _ocr_engine_fn(cfg)(img)
                    morceaux.append(texte_page)
                    ctx.etape(
                        f"ocr page {i}/{len(images)}", moteur=cfg["moteur"],
                        detail=f"{len(texte_page.strip())} caractère(s) extrait(s)",
                        duree_ms=int((time.monotonic() - t1) * 1000),
                    )
            texte = "\n\n".join(m for m in morceaux if m)
            ctx.moteur = cfg["moteur"]
            ctx.resultat = texte

    _enregistrer_texte_document(document_id, texte)


def _transcrire_image_document(document_id: int, path: Path, cfg: dict) -> None:
    with _log_traitement("transcription_document", "document", document_id) as ctx:
        t0 = time.monotonic()
        texte = _ocr_engine_fn(cfg)(path)
        ctx.etape(
            "ocr", moteur=cfg["moteur"],
            detail=f"{len(texte.strip())} caractère(s) extrait(s)",
            duree_ms=int((time.monotonic() - t0) * 1000),
        )
        ctx.moteur = cfg["moteur"]
        ctx.resultat = texte
    _enregistrer_texte_document(document_id, texte)


def _marquer_note_echec(note_id: int, message: str) -> None:
    with db.session() as conn:
        conn.execute("UPDATE notes_eleves SET statut = 'echec' WHERE id = ?", (note_id,))
    log.warning("Échec de la transcription de la note id=%s : %s", note_id, message)


def transcribe_note(note_id: int) -> None:
    """Transcrit la photo/PDF déposé pour une note élève, met à jour son contenu et son statut."""
    with db.session() as conn:
        note = conn.execute("SELECT * FROM notes_eleves WHERE id = ?", (note_id,)).fetchone()
        cfg = config_ocr(conn)
    if note is None or not note["chemin_fichier"]:
        return

    path = DOCUMENTS_DIR.parent / note["chemin_fichier"]
    if not path.exists():
        _marquer_note_echec(note_id, "Fichier introuvable sur le disque.")
        return

    try:
        with _log_traitement("transcription_note", "note", note_id) as ctx:
            ctx.moteur = cfg["moteur"]
            if path.suffix.lower() == ".pdf":
                with tempfile.TemporaryDirectory() as tmp:
                    images = pdf_to_images(path, Path(tmp))
                    morceaux = []
                    for i, img in enumerate(images, start=1):
                        t0 = time.monotonic()
                        texte_page = _ocr_engine_fn(cfg)(img)
                        morceaux.append(texte_page)
                        ctx.etape(
                            f"ocr page {i}/{len(images)}", moteur=cfg["moteur"],
                            detail=f"{len(texte_page.strip())} caractère(s) extrait(s)",
                            duree_ms=int((time.monotonic() - t0) * 1000),
                        )
                texte = "\n\n".join(m for m in morceaux if m)
            else:
                t0 = time.monotonic()
                texte = _ocr_engine_fn(cfg)(path)
                ctx.etape(
                    "ocr", moteur=cfg["moteur"],
                    detail=f"{len(texte.strip())} caractère(s) extrait(s)",
                    duree_ms=int((time.monotonic() - t0) * 1000),
                )
            ctx.resultat = texte
    except Exception as e:  # noqa: BLE001 — déjà journalisé dans `traitements` par _log_traitement
        _marquer_note_echec(note_id, str(e))
        return

    with db.session() as conn:
        conn.execute("UPDATE notes_eleves SET contenu = ?, statut = 'pret' WHERE id = ?", (texte, note_id))


def relancer_traitement(traitement_id: int) -> None:
    """Relit un traitement existant et refait le travail pour sa cible (nouvelle ligne d'historique)."""
    with db.session() as conn:
        row = conn.execute("SELECT type, cible_type, cible_id FROM traitements WHERE id = ?", (traitement_id,)).fetchone()
    if row is None:
        raise OcrError(f"Traitement {traitement_id} introuvable")

    if row["cible_type"] == "document":
        transcribe_document(row["cible_id"])
    elif row["cible_type"] == "note":
        transcribe_note(row["cible_id"])
    elif row["cible_type"] == "sync":
        from . import pronote_sync  # import tardif : évite toute dépendance circulaire au chargement du module
        pronote_sync.sync()
    elif row["cible_type"] == "cours":
        from . import ia_generation  # idem
        if row["type"] == "ia_completion":
            ia_generation.completer_pour_cours(row["cible_id"])
        else:
            ia_generation.generer_pour_cours(row["cible_id"])
