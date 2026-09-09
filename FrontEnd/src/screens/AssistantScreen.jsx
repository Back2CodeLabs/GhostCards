import { useState, useEffect, useRef } from "react";
import { Sparkles, Ghost, LogIn, Send } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE } from "../api";
import { Loading } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Assistant IA                                                         */
/* ------------------------------------------------------------------ */

export function AssistantScreen({ me, onRequireLogin }) {
  const { C } = useTheme();
  const peutUtiliser = me.isAdmin || !!me.eleve?.assistant_actif;
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Salut ! Pose-moi une question sur tes cours. (Je n'ai pas encore accès au contenu détaillé de ta classe — ça arrive avec le module IA, pour l'instant je réponds avec mes connaissances générales.)" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  async function send() {
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    setError(null);
    const nextMessages = [...messages, { role: "user", text: question }];
    setMessages(nextMessages);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/assistant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${response.status}`);
      }
      const data = await response.json();
      setMessages((m) => [...m, { role: "assistant", text: data.text }]);
    } catch (e) {
      setError(e.message || "La connexion à l'assistant a échoué. Réessaie dans un instant.");
    } finally {
      setLoading(false);
    }
  }

  if (me.loading) return <Loading />;

  if (!peutUtiliser) {
    return (
      <div>
        <div style={{ padding: "20px 20px 4px" }}>
          <div className="flex items-center gap-2">
            <Sparkles size={18} color={C.haunt} />
            <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 22, color: C.ink, margin: 0 }}>Assistant IA</h1>
          </div>
        </div>
        <div style={{ padding: "48px 28px", textAlign: "center" }}>
          <Ghost size={34} color={C.inkFaint} strokeWidth={1.4} style={{ marginBottom: 14 }} />
          {me.eleve ? (
            <p style={{ fontFamily: uiFont, fontSize: 14, color: C.inkSoft, lineHeight: 1.6, margin: 0, maxWidth: 320, marginLeft: "auto", marginRight: "auto" }}>
              L'assistant n'est pas encore activé pour ton compte. Demande à ton professeur de l'activer.
            </p>
          ) : (
            <>
              <p style={{ fontFamily: uiFont, fontSize: 14, color: C.inkSoft, lineHeight: 1.6, margin: "0 0 20px", maxWidth: 320, marginLeft: "auto", marginRight: "auto" }}>
                Connecte-toi pour savoir si l'assistant est activé pour ton compte.
              </p>
              <button
                onClick={onRequireLogin}
                style={{ display: "inline-flex", alignItems: "center", gap: 8, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "11px 20px", fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, cursor: "pointer" }}
              >
                <LogIn size={15} /> Se connecter avec Google
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "20px 20px 4px" }}>
        <div className="flex items-center gap-2">
          <Sparkles size={18} color={C.haunt} />
          <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 22, color: C.ink, margin: 0 }}>Assistant IA</h1>
        </div>
      </div>
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "12px 20px" }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", marginBottom: 10 }}>
            <div style={{ maxWidth: "82%", background: m.role === "user" ? C.haunt : C.white, color: m.role === "user" ? C.onAccent : C.ink, border: m.role === "user" ? "none" : `1px solid ${C.line}`, borderRadius: 14, borderBottomRightRadius: m.role === "user" ? 4 : 14, borderBottomLeftRadius: m.role === "assistant" ? 4 : 14, padding: "10px 13px", fontFamily: uiFont, fontSize: 13.5, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 10 }}>
            <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 14, borderBottomLeftRadius: 4, padding: "10px 13px", fontFamily: uiFont, fontSize: 13.5, color: C.inkFaint }}>
              L'assistant réfléchit…
            </div>
          </div>
        )}
        {error && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, textAlign: "center" }}>{error}</p>}
      </div>
      <div style={{ padding: "10px 16px 18px", borderTop: `1px solid ${C.line}`, background: C.paper }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.white, border: `1px solid ${C.line}`, borderRadius: 999, padding: "6px 6px 6px 16px" }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Pose ta question…"
            style={{ flex: 1, border: "none", outline: "none", fontFamily: uiFont, fontSize: 14, background: "transparent", color: C.ink }}
          />
          <button onClick={send} disabled={loading || !input.trim()} style={{ width: 34, height: 34, borderRadius: "50%", border: "none", background: input.trim() ? C.haunt : C.paperDim, color: C.onAccent, display: "flex", alignItems: "center", justifyContent: "center", cursor: input.trim() ? "pointer" : "default", flexShrink: 0 }} aria-label="Envoyer">
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
