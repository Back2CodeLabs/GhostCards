import { useState, useEffect } from "react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi } from "../api";
import { Loading, ApiError } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Paramétrage — choix du moteur IA (génération + assistant), admin      */
/* uniquement. Modifiable à chaud, pas besoin de redémarrer le service.  */
/* ------------------------------------------------------------------ */

const MOTEURS_IA = [
  { id: "ollama", nom: "Ollama (local, gratuit)", desc: "Tourne sur l'OptiPlex. Aucune donnée envoyée à l'extérieur." },
  { id: "claude", nom: "Claude (Anthropic)", desc: "Nécessite une clé API (console.anthropic.com). Le contenu des cours part chez Anthropic." },
  { id: "gemini", nom: "Gemini (Google)", desc: "Nécessite sa propre clé API (aistudio.google.com). Le contenu des cours part chez Google." },
];

export function ParametresScreen() {
  const { C } = useTheme();
  const parametres = useApi("/api/parametres");
  const [moteur, setMoteur] = useState("ollama");
  const [geminiModel, setGeminiModel] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveOk, setSaveOk] = useState(false);

  useEffect(() => {
    if (parametres.data) {
      setMoteur(parametres.data.ia_moteur);
      setGeminiModel(parametres.data.gemini_model || "");
    }
  }, [parametres.data]);

  async function enregistrer() {
    setSaving(true);
    setSaveError(null);
    setSaveOk(false);
    try {
      const body = { ia_moteur: moteur, gemini_model: geminiModel || null };
      if (geminiKey.trim()) body.gemini_api_key = geminiKey.trim();
      if (anthropicKey.trim()) body.anthropic_api_key = anthropicKey.trim();
      const res = await fetch(`${API_BASE}/api/parametres`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      setGeminiKey("");
      setAnthropicKey("");
      setSaveOk(true);
      parametres.reload();
    } catch (e) {
      setSaveError(e.message || "Impossible d'enregistrer.");
    } finally {
      setSaving(false);
    }
  }

  const inputStyle = { width: "100%", background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 10px", fontFamily: uiFont, fontSize: 13, color: C.ink, outline: "none" };
  const labelStyle = { fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, display: "block", marginBottom: 4 };

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Paramétrage</h1>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "4px 0 0" }}>
          Moteur utilisé pour générer résumés/flashcards/quiz et pour l'assistant conversationnel.
        </p>
      </div>
      <div style={{ padding: "16px 20px" }}>
        {parametres.loading && <Loading />}
        {parametres.error && <ApiError message={parametres.error} onRetry={parametres.reload} />}
        {parametres.data && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 18 }}>
              {MOTEURS_IA.map((m) => (
                <label
                  key={m.id}
                  style={{ display: "flex", gap: 10, alignItems: "flex-start", background: C.white, border: `1px solid ${moteur === m.id ? C.haunt : C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer" }}
                >
                  <input type="radio" checked={moteur === m.id} onChange={() => setMoteur(m.id)} style={{ marginTop: 3 }} />
                  <div>
                    <div style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.nom}</div>
                    <div style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, marginTop: 2 }}>{m.desc}</div>
                  </div>
                </label>
              ))}
            </div>

            {moteur === "claude" && (
              <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <label style={labelStyle}>
                    CLÉ API ANTHROPIC {parametres.data.anthropic_api_key_configuree ? "(déjà configurée — laisser vide pour ne pas la changer)" : "(non configurée)"}
                  </label>
                  <input type="password" value={anthropicKey} onChange={(e) => setAnthropicKey(e.target.value)} placeholder="sk-ant-..." style={inputStyle} />
                </div>
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                  Clé créée sur console.anthropic.com — reste stockée côté serveur, jamais renvoyée au navigateur.
                </p>
              </div>
            )}

            {moteur === "gemini" && (
              <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <label style={labelStyle}>MODÈLE GEMINI</label>
                  <input value={geminiModel} onChange={(e) => setGeminiModel(e.target.value)} placeholder="gemini-3.5-flash-lite" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>
                    CLÉ API {parametres.data.gemini_api_key_configuree ? "(déjà configurée — laisser vide pour ne pas la changer)" : "(non configurée)"}
                  </label>
                  <input type="password" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} placeholder="AIza..." style={inputStyle} />
                </div>
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                  Clé créée sur aistudio.google.com — reste stockée côté serveur, jamais renvoyée au navigateur.
                </p>
              </div>
            )}

            <button
              onClick={enregistrer}
              disabled={saving}
              style={{ marginTop: 16, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "9px 20px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: saving ? "default" : "pointer", opacity: saving ? 0.7 : 1 }}
            >
              {saving ? "Enregistrement…" : "Enregistrer"}
            </button>
            {saveOk && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.spectral, margin: "10px 0 0" }}>Paramètres enregistrés.</p>}
            {saveError && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "10px 0 0" }}>{saveError}</p>}
          </>
        )}
      </div>
    </div>
  );
}
