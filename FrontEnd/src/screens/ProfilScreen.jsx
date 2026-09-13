import { useState } from "react";
import { KeyRound, Check, Trash2 } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi, messageErreur } from "../api";
import { Loading, ApiError, ScreenHeader } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Profil élève — identité (Pronote fait foi, lecture seule) + clé      */
/* Gemini personnelle (voir BackEnd/app/main.py::definir_cle_gemini,     */
/* Services/ia_generation.py::_avec_cle_gemini_perso) : utilisée en      */
/* priorité sur le moteur choisi par l'admin pour les générations que    */
/* CET élève déclenche, pour répartir le quota Gemini entre plusieurs   */
/* clés personnelles plutôt que tout faire peser sur celle de l'admin.  */
/* ------------------------------------------------------------------ */

export function ProfilScreen() {
  const { C } = useTheme();
  const profil = useApi("/api/profil");
  const [cle, setCle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [succes, setSucces] = useState(null);

  async function enregistrer(nouvelleCle) {
    setSubmitting(true);
    setError(null);
    setSucces(null);
    try {
      const res = await fetch(`${API_BASE}/api/profil/gemini-cle`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cle: nouvelleCle }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      setCle("");
      setSucces(nouvelleCle ? "Clé enregistrée." : "Clé supprimée.");
      profil.reload();
    } catch (e) {
      setError(messageErreur(e, "Impossible d'enregistrer la clé."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <ScreenHeader title="Profil" />
      {profil.loading && <Loading />}
      {profil.error && <ApiError message={profil.error} onRetry={profil.reload} />}
      {profil.data && (
        <div style={{ padding: "16px 20px 24px" }}>
          <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: "14px 16px", marginBottom: 20 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.ink }}>{profil.data.nom}</div>
            <div style={{ fontSize: 12.5, color: C.inkSoft, marginTop: 3 }}>
              {profil.data.classe || "Classe inconnue"}
              {profil.data.groupes && ` · ${profil.data.groupes}`}
            </div>
          </div>

          <p style={{ fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, color: C.ink, margin: "0 0 6px" }}>
            Ma clé Gemini
          </p>
          <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, lineHeight: 1.5, margin: "0 0 14px" }}>
            Facultatif — associe ta propre clé Gemini (gratuite sur{" "}
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" style={{ color: C.haunt }}>
              aistudio.google.com
            </a>
            ) pour générer résumés/flashcards/quiz avec ton propre quota, plutôt que celui, partagé, de l'admin.
          </p>

          {profil.data.gemini_cle_definie ? (
            <div style={{ display: "flex", alignItems: "center", gap: 10, background: C.spectralSoft, border: `1px solid ${C.spectral}`, borderRadius: 10, padding: "12px 14px" }}>
              <Check size={16} color={C.spectral} style={{ flexShrink: 0 }} />
              <span style={{ flex: 1, fontFamily: uiFont, fontSize: 13, color: C.ink }}>Une clé Gemini est enregistrée.</span>
              <button
                onClick={() => enregistrer(null)}
                disabled={submitting}
                title="Supprimer la clé enregistrée"
                style={{ display: "flex", alignItems: "center", gap: 5, background: "transparent", border: `1px solid ${C.line}`, borderRadius: 8, padding: "6px 10px", fontFamily: uiFont, fontSize: 12, fontWeight: 600, color: C.brick, cursor: submitting ? "default" : "pointer" }}
              >
                <Trash2 size={13} /> Retirer
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "0 12px" }}>
                <KeyRound size={14} color={C.inkFaint} style={{ flexShrink: 0 }} />
                <input
                  type="password"
                  value={cle}
                  onChange={(e) => setCle(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && cle.trim() && enregistrer(cle.trim())}
                  placeholder="Colle ta clé Gemini"
                  style={{ flex: 1, border: "none", outline: "none", background: "transparent", padding: "10px 0", fontFamily: uiFont, fontSize: 13, color: C.ink }}
                />
              </div>
              <button
                onClick={() => cle.trim() && enregistrer(cle.trim())}
                disabled={submitting || !cle.trim()}
                style={{ background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "0 18px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: cle.trim() ? "pointer" : "default", opacity: submitting ? 0.7 : 1 }}
              >
                Enregistrer
              </button>
            </div>
          )}

          {error && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "10px 0 0" }}>{error}</p>}
          {succes && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.spectral, margin: "10px 0 0" }}>{succes}</p>}
        </div>
      )}
    </div>
  );
}
