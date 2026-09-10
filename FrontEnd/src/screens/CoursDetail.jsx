import { useState, useEffect, useRef } from "react";
import { FileText, Download, LogIn, Paperclip, Sparkles, RefreshCw, Loader2, Ghost, GraduationCap, ShieldCheck } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi } from "../api";
import { Loading, ApiError, ScreenHeader, AvertissementIA } from "../components/Shared";
import { ExamMode } from "../components/ExamMode";

// Durée de l'animation .gc-evaporate (index.css) — le mode examen ne
// bascule qu'une fois le cours "évaporé", pas avant.
const DUREE_EVAPORATION_MS = 600;

// Dernier résultat d'examen : mémorisé par navigateur (localStorage), pas
// par compte élève — prendre un examen ne nécessite pas de connexion, donc
// pas de compte à qui l'associer côté serveur. "Pour un élève" ici veut
// dire "pour qui a passé l'examen sur cet appareil".
function sauvegarderResultatExamen(coursId, resultat) {
  try {
    localStorage.setItem(`gc_dernier_examen_${coursId}`, JSON.stringify({ ...resultat, date: new Date().toISOString() }));
  } catch {
    // localStorage indisponible (navigation privée, stockage bloqué...) :
    // le résultat reste affiché pour la session en cours, juste pas gardé.
  }
}

function lireResultatExamen(coursId) {
  try {
    const brut = localStorage.getItem(`gc_dernier_examen_${coursId}`);
    return brut ? JSON.parse(brut) : null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ */
/* Détail cours                                                         */
/* ------------------------------------------------------------------ */

export function CoursDetail({ coursId, onBack, me, onRequireLogin, onOpenTraitement }) {
  const { C } = useTheme();
  const cours = useApi(`/api/cours/${coursId}`, [coursId]);
  const [noteText, setNoteText] = useState("");
  const [posting, setPosting] = useState(false);
  const [noteError, setNoteError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);

  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState(null);
  const [regenMessage, setRegenMessage] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState(null);
  const [completing, setCompleting] = useState(false);
  const [completingError, setCompletingError] = useState(null);
  const [resumeDetaille, setResumeDetaille] = useState(false);
  // "off" (cours visible normalement) → "evaporating" (animation en cours,
  // voir .gc-evaporate) → "active" (mode examen affiché, cours masqué).
  const [examPhase, setExamPhase] = useState("off");
  const [dernierExamen, setDernierExamen] = useState(() => lireResultatExamen(coursId));

  function entrerModeExamen() {
    setExamPhase("evaporating");
    setTimeout(() => setExamPhase("active"), DUREE_EVAPORATION_MS);
  }
  function quitterModeExamen() {
    setExamPhase("off");
  }
  function finirExamen(resultat) {
    sauvegarderResultatExamen(coursId, resultat);
    setDernierExamen(lireResultatExamen(coursId));
  }

  // Tant qu'une note déposée en photo/PDF est en cours de transcription
  // (OCR en arrière-plan, voir Services/ocr.py) ou que la génération IA
  // tourne (voir Services/ia_generation.py — peut prendre plusieurs
  // minutes, modèle local), on réactualise le cours pour faire apparaître
  // le résultat sans que l'élève ait à recharger.
  useEffect(() => {
    const enTraitement = cours.data?.notes?.some((n) => n.statut === "traitement");
    const iaEnCours = cours.data?.ia_statut === "en_cours";
    if (!enTraitement && !iaEnCours) return;
    const t = setInterval(() => cours.reload(), 6000);
    return () => clearInterval(t);
  }, [cours.data, cours.reload]);

  async function genererIA() {
    if (generating) return;
    setGenerating(true);
    setGenerationError(null);
    setRegenMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/cours/${coursId}/generer`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      const data = await res.json();
      // Régénérer un cours déjà généré coûte des tokens pour rien de neuf
      // si personne ne valide : ça part en demande en attente (écran admin
      // Traitements → "En attente") plutôt que de lancer tout de suite —
      // seule une PREMIÈRE génération (cours sans résumé) part directement.
      if (data.status === "demande_en_attente" || data.status === "deja_en_attente") {
        setRegenMessage("Demande de régénération envoyée — en attente de validation par un admin.");
      }
      cours.reload();
    } catch (e) {
      setGenerationError(e.message || "Impossible de lancer la génération.");
    } finally {
      setGenerating(false);
    }
  }

  async function verifierFiabilite() {
    if (verifying) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await fetch(`${API_BASE}/api/cours/${coursId}/verifier`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      const data = await res.json();
      // Navigue directement sur le suivi du traitement (comme "Lancer une
      // synchronisation Pronote" depuis l'écran Traitements) : la
      // vérification peut prendre du temps, pas la peine de rester bloqué
      // sur cette page à attendre.
      if (data.traitement_id) onOpenTraitement(data.traitement_id);
    } catch (e) {
      setVerifyError(e.message || "Impossible de lancer la vérification.");
    } finally {
      setVerifying(false);
    }
  }

  async function completerIA() {
    if (completing) return;
    setCompleting(true);
    setCompletingError(null);
    try {
      const res = await fetch(`${API_BASE}/api/cours/${coursId}/completer`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      cours.reload();
    } catch (e) {
      setCompletingError(e.message || "Impossible de lancer le complément.");
    } finally {
      setCompleting(false);
    }
  }

  async function submitNote() {
    const contenu = noteText.trim();
    if (!contenu || posting) return;
    setPosting(true);
    setNoteError(null);
    try {
      const res = await fetch(`${API_BASE}/api/cours/${coursId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contenu }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      setNoteText("");
      cours.reload();
    } catch (e) {
      setNoteError(e.message || "Impossible d'enregistrer la note.");
    } finally {
      setPosting(false);
    }
  }

  async function submitPhoto(file) {
    if (!file || uploading) return;
    setUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("fichier", file);
      const res = await fetch(`${API_BASE}/api/cours/${coursId}/notes/photo`, { method: "POST", body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      cours.reload();
    } catch (e) {
      setUploadError(e.message || "Impossible d'envoyer le fichier.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  if (cours.loading) return (<div><ScreenHeader title="Cours" onBack={onBack} /><Loading /></div>);
  if (cours.error) return (<div><ScreenHeader title="Cours" onBack={onBack} /><ApiError message={cours.error} onRetry={cours.reload} /></div>);

  const c = cours.data;
  const sansContenu = c.documents.length === 0 && c.notes.length === 0;
  // La section IA (résultat ou invite à générer) ne s'affiche pas quand il
  // n'y a rien à partir de quoi générer (voir plus bas) — l'avertissement
  // ne doit apparaître que si cette section, elle, s'affiche.
  const sectionIAVisible = !!c.ia_resume || !(sansContenu && (!c.ia_statut || c.ia_statut === "absent"));

  return (
    <div style={{ paddingBottom: 28 }}>
      <ScreenHeader title={c.titre || "Cours"} onBack={onBack} />
      {examPhase === "active" ? (
        <div style={{ padding: "16px 20px 0" }}>
          <ExamMode flashcards={c.ia_flashcards} quiz={c.ia_quiz} onExit={quitterModeExamen} onFinish={finirExamen} />
        </div>
      ) : (
      <div style={{ padding: "16px 20px 0" }} className={examPhase === "evaporating" ? "gc-evaporate" : ""}>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft, margin: 0 }}>
          {new Date(c.date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} · {c.heure_debut}
          {c.professeur ? ` · ${c.professeur}` : ""}
        </p>

        {c.description && (
          <div style={{ marginTop: 16, background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16 }}>
            <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "0 0 8px" }}>CONTENU DU COURS</p>
            <p style={{ fontFamily: uiFont, fontSize: 14, color: C.ink, lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>{c.description}</p>
          </div>
        )}

        <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "20px 0 8px" }}>
          DOCUMENTS ({c.documents.length})
        </p>
        {c.documents.length === 0 && (
          <p style={{ fontFamily: uiFont, fontSize: 13, color: C.inkFaint }}>Aucun document attaché à ce cours.</p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {c.documents.map((d) => (
            <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 10, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "11px 14px" }}>
              <a
                href={d.url_externe || `${API_BASE}/api/documents/${d.id}/apercu`}
                target="_blank"
                rel="noreferrer"
                title="Voir"
                style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}
              >
                <FileText size={16} color={C.haunt} style={{ flexShrink: 0 }} />
                <span style={{ flex: 1, minWidth: 0, fontFamily: uiFont, fontSize: 13, color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.nom_fichier}</span>
              </a>
              {!d.url_externe && (
                <a href={`${API_BASE}/api/documents/${d.id}/fichier`} title="Télécharger" style={{ flexShrink: 0, display: "flex", color: C.inkFaint }}>
                  <Download size={15} />
                </a>
              )}
            </div>
          ))}
        </div>

        <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "20px 0 8px" }}>
          NOTES DES ÉLÈVES ({c.notes.length})
        </p>
        {c.notes.some((n) => n.type !== "texte" && n.type !== "markdown") && (
          <div style={{ marginBottom: 10 }}>
            <AvertissementIA intro="Notes transcrites automatiquement à partir d'une photo ou d'un PDF déposé : la transcription peut contenir des erreurs." />
          </div>
        )}
        {c.notes.length === 0 && (
          <p style={{ fontFamily: uiFont, fontSize: 13, color: C.inkFaint }}>Personne n'a encore partagé de notes pour ce cours.</p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {c.notes.map((n) => (
            <div key={n.id} style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "11px 14px" }}>
              <div className="flex items-center justify-between">
                <span style={{ fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, color: C.haunt }}>{n.auteur}</span>
                <div className="flex items-center gap-2">
                  {n.type !== "texte" && n.type !== "markdown" && (
                    <a
                      href={`${API_BASE}/api/notes/${n.id}/apercu`}
                      target="_blank"
                      rel="noreferrer"
                      title="Voir le fichier d'origine"
                      style={{ display: "flex", color: C.inkFaint }}
                    >
                      <FileText size={14} />
                    </a>
                  )}
                  <span style={{ fontFamily: uiFont, fontSize: 11, color: C.inkFaint }}>
                    {new Date(n.created_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
                  </span>
                </div>
              </div>
              {n.statut === "traitement" && (
                <p style={{ fontFamily: uiFont, fontSize: 13, color: C.inkFaint, margin: "4px 0 0", display: "flex", alignItems: "center", gap: 6 }}>
                  <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> Transcription en cours…
                </p>
              )}
              {n.statut === "echec" && (
                <p style={{ fontFamily: uiFont, fontSize: 13, color: C.brick, margin: "4px 0 0" }}>Échec de la transcription de ce document.</p>
              )}
              {(n.statut === "pret" || !n.statut) && (
                <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.ink, margin: "4px 0 0", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{n.contenu}</p>
              )}
            </div>
          ))}
        </div>

        {me?.eleve ? (
          <div style={{ marginTop: 10 }}>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Partage une remarque, un point à retenir, une reformulation…"
              rows={3}
              style={{ width: "100%", resize: "vertical", background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "10px 12px", fontFamily: uiFont, fontSize: 13.5, color: C.ink, outline: "none" }}
            />
            {noteError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "6px 0 0" }}>{noteError}</p>}
            <div className="flex items-center gap-2" style={{ marginTop: 8 }}>
              <button
                onClick={submitNote}
                disabled={posting || !noteText.trim()}
                style={{ background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "9px 18px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: noteText.trim() ? "pointer" : "default", opacity: posting ? 0.7 : 1 }}
              >
                {posting ? "Envoi…" : "Partager cette note"}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,image/png,image/jpeg,image/webp"
                style={{ display: "none" }}
                onChange={(e) => submitPhoto(e.target.files?.[0])}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                title="Joindre une photo de cahier ou un PDF (transcrit automatiquement)"
                style={{ display: "flex", alignItems: "center", gap: 6, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "9px 14px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 600, color: C.inkSoft, cursor: uploading ? "default" : "pointer", opacity: uploading ? 0.7 : 1 }}
              >
                <Paperclip size={14} /> {uploading ? "Envoi…" : "Photo / PDF"}
              </button>
            </div>
            {uploadError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "6px 0 0" }}>{uploadError}</p>}
          </div>
        ) : (
          <button
            onClick={onRequireLogin}
            style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8, background: C.hauntSoft, color: C.haunt, border: "none", borderRadius: 10, padding: "11px 16px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: "pointer" }}
          >
            <LogIn size={15} /> Se connecter pour ajouter une note
          </button>
        )}

        {sectionIAVisible && (
          <div style={{ marginTop: 22 }}>
            <AvertissementIA intro="Contenu généré automatiquement par une IA : il peut contenir des erreurs ou des approximations — vérifie les informations importantes." />
          </div>
        )}

        {c.ia_resume ? (
          <div style={{ marginTop: 16 }}>
            <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "0 0 8px" }}>RÉSUMÉ IA</p>
            <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16 }}>
              <p style={{ fontFamily: uiFont, fontSize: 14, color: C.ink, lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>
                {resumeDetaille && c.ia_resume_detaille ? c.ia_resume_detaille : c.ia_resume}
              </p>
              {c.ia_resume_detaille && c.ia_resume_detaille !== c.ia_resume && (
                <button
                  onClick={() => setResumeDetaille((v) => !v)}
                  style={{ marginTop: 10, background: "transparent", border: "none", color: C.haunt, fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: "pointer", padding: 0 }}
                >
                  {resumeDetaille ? "Voir le résumé court" : "Voir le résumé détaillé"}
                </button>
              )}
            </div>

            {(c.ia_flashcards.length > 0 || c.ia_quiz.length > 0) && (
              <button
                onClick={entrerModeExamen}
                style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, width: "100%", marginTop: 16, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 12, padding: "13px 16px", fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, cursor: "pointer" }}
              >
                <GraduationCap size={16} /> Tester mes connaissances
                {" "}({c.ia_flashcards.length} flashcard{c.ia_flashcards.length > 1 ? "s" : ""}
                {c.ia_quiz.length > 0 ? `, ${c.ia_quiz.length} quiz` : ""})
              </button>
            )}
            {dernierExamen && (
              <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, textAlign: "center", margin: "8px 0 0" }}>
                Dernier résultat : <strong style={{ color: C.ink }}>{dernierExamen.pourcentage}%</strong>
                {" "}({dernierExamen.totalReussies}/{dernierExamen.totalReponses}) le{" "}
                {new Date(dernierExamen.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}
              </p>
            )}

            <div className="flex items-center gap-2" style={{ marginTop: 16 }}>
              <button
                onClick={completerIA}
                disabled={completing || c.ia_statut === "en_cours"}
                style={{ display: "flex", alignItems: "center", gap: 8, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "9px 16px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: completing ? "default" : "pointer", opacity: completing ? 0.7 : 1 }}
              >
                <Sparkles size={13} /> {completing ? "Lancement…" : "+ 10 flashcards & quiz"}
              </button>
              <button
                onClick={genererIA}
                disabled={generating || completing || c.ia_statut === "en_cours" || c.regeneration_en_attente}
                title={c.regeneration_en_attente ? "Une demande de régénération est déjà en attente de validation par un admin" : undefined}
                style={{ display: "flex", alignItems: "center", gap: 8, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "9px 16px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 600, color: c.regeneration_en_attente ? C.inkFaint : C.inkSoft, cursor: generating || c.regeneration_en_attente ? "default" : "pointer", opacity: c.regeneration_en_attente ? 0.7 : 1 }}
              >
                <RefreshCw size={13} style={generating ? { animation: "spin 1s linear infinite" } : {}} />
                {c.regeneration_en_attente ? "En attente de validation…" : "Régénérer"}
              </button>
              {me?.isAdmin && c.ia_traitement_id && (
                <button
                  onClick={() => onOpenTraitement(c.ia_traitement_id)}
                  style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: "none", color: C.inkFaint, fontFamily: uiFont, fontSize: 12, fontWeight: 600, cursor: "pointer", padding: "9px 4px" }}
                >
                  Voir le traitement →
                </button>
              )}
            </div>
            {me?.isAdmin && (
              <div className="flex items-center gap-2" style={{ marginTop: 10, flexWrap: "wrap" }}>
                <button
                  onClick={verifierFiabilite}
                  disabled={verifying}
                  style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: `1px solid ${C.line}`, borderRadius: 8, padding: "6px 12px", fontFamily: uiFont, fontSize: 12, fontWeight: 600, color: C.inkSoft, cursor: verifying ? "default" : "pointer" }}
                >
                  <ShieldCheck size={13} /> {verifying ? "Lancement…" : "Vérifier la fiabilité"}
                </button>
                {c.ia_fiabilite != null && (
                  <span
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 5, borderRadius: 999, padding: "4px 10px",
                      fontFamily: uiFont, fontSize: 11.5, fontWeight: 700,
                      background: c.ia_fiabilite >= 70 ? C.spectralSoft : C.brickSoft,
                      color: c.ia_fiabilite >= 70 ? C.spectral : C.brick,
                    }}
                  >
                    Fiabilité {c.ia_fiabilite}%
                  </span>
                )}
                {c.ia_verification_traitement_id && (
                  <button
                    onClick={() => onOpenTraitement(c.ia_verification_traitement_id)}
                    style={{ background: "transparent", border: "none", color: C.inkFaint, fontFamily: uiFont, fontSize: 12, fontWeight: 600, cursor: "pointer", padding: "6px 4px" }}
                  >
                    Voir le détail →
                  </button>
                )}
              </div>
            )}
            {me?.isAdmin && c.ia_fiabilite != null && c.ia_fiabilite < 70 && (
              <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "6px 0 0" }}>
                Score bas — regarde le détail de la vérification pour voir ce qui est en cause, puis envisage de
                régénérer (bouton "Régénérer" ci-dessus).
              </p>
            )}
            {verifyError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "6px 0 0" }}>{verifyError}</p>}
            {(regenMessage || c.regeneration_en_attente) && (
              <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "8px 0 0" }}>
                {regenMessage || "Une demande de régénération est en attente de validation par un admin."}
              </p>
            )}
            {c.ia_statut === "en_cours" && (
              <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "8px 0 0", display: "flex", alignItems: "center", gap: 6 }}>
                <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> Mise à jour en cours… (le contenu ci-dessus reste celui de la dernière génération réussie)
              </p>
            )}
            {c.ia_statut === "echec" && c.ia_erreur && (
              <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "8px 0 0" }}>
                La dernière tentative a échoué ({c.ia_erreur}) — le contenu ci-dessus reste celui d'avant.
              </p>
            )}
            {generationError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "8px 0 0" }}>{generationError}</p>}
            {completingError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "8px 0 0" }}>{completingError}</p>}
          </div>
        ) : sansContenu && (!c.ia_statut || c.ia_statut === "absent") ? null : (
          <div style={{ marginTop: 16, background: C.hauntSoft, borderRadius: 12, padding: 16, display: "flex", gap: 12, alignItems: "flex-start" }}>
            <Ghost size={20} color={C.haunt} style={{ flexShrink: 0, marginTop: 2 }} />
            <div style={{ flex: 1 }}>
              {c.ia_statut === "en_cours" && (
                <p style={{ fontFamily: uiFont, fontSize: 13, color: C.ink, lineHeight: 1.5, margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
                  <Loader2 size={14} style={{ animation: "spin 1s linear infinite", flexShrink: 0 }} />
                  Génération en cours… ça peut prendre plusieurs minutes (modèle local).
                </p>
              )}
              {c.ia_statut === "echec" && (
                <>
                  <p style={{ fontFamily: uiFont, fontSize: 13, color: C.brick, lineHeight: 1.5, margin: "0 0 10px" }}>
                    Échec de la génération : {c.ia_erreur}
                  </p>
                  <button
                    onClick={genererIA}
                    disabled={generating}
                    style={{ background: C.haunt, color: C.onAccent, border: "none", borderRadius: 8, padding: "7px 14px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: generating ? "default" : "pointer" }}
                  >
                    {generating ? "Lancement…" : "Réessayer"}
                  </button>
                </>
              )}
              {(!c.ia_statut || c.ia_statut === "absent") && (
                <>
                  <p style={{ fontFamily: uiFont, fontSize: 13, color: C.ink, lineHeight: 1.5, margin: "0 0 10px" }}>
                    Résumé, flashcards et quiz ne sont pas encore générés pour ce cours.
                  </p>
                  <button
                    onClick={genererIA}
                    disabled={generating}
                    style={{ display: "flex", alignItems: "center", gap: 8, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 8, padding: "8px 16px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: generating ? "default" : "pointer", opacity: generating ? 0.7 : 1 }}
                  >
                    <Sparkles size={14} /> {generating ? "Lancement…" : "Générer"}
                  </button>
                </>
              )}
              {generationError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "8px 0 0" }}>{generationError}</p>}
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
