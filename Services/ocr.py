"""
Extraction de texte : PDF Pronote (avec ou sans couche de texte) et photos
de notes manuscrites déposées par les élèves.

Moteur par défaut : vision Claude (voir OCR_ENGINE dans config.py et
HANDOFF.md pour les raisons — pas de wheels PaddlePaddle pour Python 3.14,
et l'écriture manuscrite est le cas le plus dur pour un OCR classique).
PaddleOCR reste prévu en option interchangeable, en lazy-import.

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
from contextlib import contextmanager
from pathlib import Path

from . import db
from .config import ANTHROPIC_API_KEY, OCR_ENGINE, OCR_MAX_PAGES, DOCUMENTS_DIR

log = logging.getLogger("ghostcards.ocr")

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class OcrError(Exception):
    pass


@contextmanager
def _log_traitement(type_: str, cible_type: str, cible_id: int):
    """
    Crée une ligne dans `traitements` au début du bloc, la complète (succès
    ou échec, durée) à la fin — quoi qu'il arrive. Le code appelant doit
    renseigner `ctx.moteur` et `ctx.resultat` avant la fin du bloc `with`.
    """
    class _Ctx:
        moteur = None
        resultat = None

    ctx = _Ctx()
    with db.session() as conn:
        traitement_id = db.creer_traitement(conn, type=type_, cible_type=cible_type, cible_id=cible_id)

    debut = time.monotonic()
    try:
        yield ctx
    except Exception as e:  # noqa: BLE001 — on journalise puis on relance pour l'appelant
        with db.session() as conn:
            db.terminer_traitement(
                conn, traitement_id, statut="echec", moteur=ctx.moteur, resultat=ctx.resultat,
                erreur=str(e), duree_ms=int((time.monotonic() - debut) * 1000),
            )
        raise
    else:
        with db.session() as conn:
            db.terminer_traitement(
                conn, traitement_id, statut="succes", moteur=ctx.moteur, resultat=ctx.resultat,
                erreur=None, duree_ms=int((time.monotonic() - debut) * 1000),
            )


# --- Extraction PDF (texte natif) -------------------------------------------

def extract_pdf_text(path: Path) -> str:
    """Texte natif d'un PDF via poppler-utils. Vide si le PDF est scanné (pas de couche de texte)."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise OcrError(f"pdftotext a échoué sur {path.name} : {result.stderr.strip()}")
    return result.stdout


def count_pdf_pages(path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30)
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
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", "150", "-l", str(max_pages), str(pdf_path), str(prefix)],
        capture_output=True, text=True, timeout=180,
    )
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


def _anthropic():
    global _anthropic_client
    if not ANTHROPIC_API_KEY:
        raise OcrError("ANTHROPIC_API_KEY n'est pas configurée (voir .env).")
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def ocr_image_claude(image_path: Path) -> str:
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower(), "image/png")
    data = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
    response = _anthropic().messages.create(
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


def _ocr_engine_fn():
    try:
        return {"claude": ocr_image_claude, "paddleocr": ocr_image_paddleocr}[OCR_ENGINE]
    except KeyError:
        raise OcrError(f"OCR_ENGINE inconnu : {OCR_ENGINE!r} (attendu 'claude' ou 'paddleocr').")


# --- Orchestrateurs ------------------------------------------------------------

def _enregistrer_texte_document(document_id: int, texte: str) -> None:
    with db.session() as conn:
        conn.execute("UPDATE documents SET texte_extrait = ? WHERE id = ?", (texte, document_id))


def transcribe_document(document_id: int) -> None:
    """Extrait le texte d'un document Pronote (PDF natif, PDF scanné, ou image)."""
    with db.session() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None or not doc["chemin_local"] or doc["chemin_local"].startswith("lien:"):
        return  # lien externe, pas de fichier local à transcrire

    path = DOCUMENTS_DIR.parent / doc["chemin_local"]
    if not path.exists():
        return

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        _transcrire_pdf_document(document_id, path)
    elif suffix in _MEDIA_TYPES:
        _transcrire_image_document(document_id, path)
    # autres types (ex. .docx) : pas pris en charge pour l'instant


def _transcrire_pdf_document(document_id: int, path: Path) -> None:
    with _log_traitement("pdftotext", "document", document_id) as ctx:
        ctx.moteur = "pdftotext"
        texte = extract_pdf_text(path)
        ctx.resultat = texte

    if not is_text_sparse(texte, count_pdf_pages(path)):
        _enregistrer_texte_document(document_id, texte)
        return

    with _log_traitement("ocr_document", "document", document_id) as ctx:
        ctx.moteur = OCR_ENGINE
        with tempfile.TemporaryDirectory() as tmp:
            images = pdf_to_images(path, Path(tmp))
            morceaux = [_ocr_engine_fn()(img) for img in images]
        texte_ocr = "\n\n".join(m for m in morceaux if m)
        ctx.resultat = texte_ocr
    _enregistrer_texte_document(document_id, texte_ocr)


def _transcrire_image_document(document_id: int, path: Path) -> None:
    with _log_traitement("ocr_document", "document", document_id) as ctx:
        ctx.moteur = OCR_ENGINE
        texte = _ocr_engine_fn()(path)
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
    if note is None or not note["chemin_fichier"]:
        return

    path = DOCUMENTS_DIR.parent / note["chemin_fichier"]
    if not path.exists():
        _marquer_note_echec(note_id, "Fichier introuvable sur le disque.")
        return

    try:
        with _log_traitement("ocr_note", "note", note_id) as ctx:
            ctx.moteur = OCR_ENGINE
            if path.suffix.lower() == ".pdf":
                with tempfile.TemporaryDirectory() as tmp:
                    images = pdf_to_images(path, Path(tmp))
                    morceaux = [_ocr_engine_fn()(img) for img in images]
                texte = "\n\n".join(m for m in morceaux if m)
            else:
                texte = _ocr_engine_fn()(path)
            ctx.resultat = texte
    except Exception as e:  # noqa: BLE001 — déjà journalisé dans `traitements` par _log_traitement
        _marquer_note_echec(note_id, str(e))
        return

    with db.session() as conn:
        conn.execute("UPDATE notes_eleves SET contenu = ?, statut = 'pret' WHERE id = ?", (texte, note_id))


def relancer_traitement(traitement_id: int) -> None:
    """Relit un traitement existant et refait le travail pour sa cible (nouvelle ligne d'historique)."""
    with db.session() as conn:
        row = conn.execute("SELECT cible_type, cible_id FROM traitements WHERE id = ?", (traitement_id,)).fetchone()
    if row is None:
        raise OcrError(f"Traitement {traitement_id} introuvable")

    if row["cible_type"] == "document":
        transcribe_document(row["cible_id"])
    elif row["cible_type"] == "note":
        transcribe_note(row["cible_id"])
