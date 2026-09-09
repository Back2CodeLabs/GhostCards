import { useState } from "react";
import { Ghost, LogIn, ShieldCheck } from "lucide-react";
import { useTheme, uiFont, glowText } from "../theme";
import { API_BASE } from "../api";
import { ScreenHeader } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Connexion (Google) — sert uniquement à identifier qui dépose une     */
/* note ; le reste du site reste consultable sans compte.               */
/* ------------------------------------------------------------------ */

export function LoginScreen({ onBack }) {
  const { C } = useTheme();
  return (
    <div>
      <ScreenHeader title="Connexion" onBack={onBack} />
      <div style={{ padding: "48px 28px", textAlign: "center" }}>
        <Ghost size={38} color={C.haunt} strokeWidth={1.4} style={{ marginBottom: 16, ...glowText(C, C.haunt) }} />
        <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 20, color: C.ink, margin: "0 0 10px" }}>
          Connecte-toi pour participer
        </h2>
        <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.inkSoft, lineHeight: 1.6, margin: "0 0 26px", maxWidth: 340, marginLeft: "auto", marginRight: "auto" }}>
          La connexion sert uniquement à savoir qui a déposé quelle note, pour
          que la classe sache d'où vient chaque contribution. Consulter les
          cours, résumés et quiz reste libre, sans compte.
        </p>
        <a
          href={`${API_BASE}/auth/login`}
          style={{ display: "inline-flex", alignItems: "center", gap: 9, background: C.haunt, color: C.onAccent, borderRadius: 10, padding: "12px 22px", fontFamily: uiFont, fontSize: 14, fontWeight: 700, textDecoration: "none" }}
        >
          <LogIn size={16} /> Continuer avec Google
        </a>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Connexion admin (Cédric) — mot de passe séparé des comptes élèves,   */
/* un élève ne peut jamais devenir admin par ce biais.                  */
/* ------------------------------------------------------------------ */

export function AdminLoginScreen({ onBack, me }) {
  const { C } = useTheme();
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function submit() {
    if (!password || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await me.adminLogin(password);
      onBack();
    } catch (e) {
      setError(e.message || "Connexion admin impossible.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <ScreenHeader title="Administration" onBack={onBack} />
      <div style={{ padding: "48px 28px", textAlign: "center" }}>
        <ShieldCheck size={38} color={C.haunt} strokeWidth={1.4} style={{ marginBottom: 16, ...glowText(C, C.haunt) }} />
        <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 20, color: C.ink, margin: "0 0 10px" }}>
          Accès du Maître Fantôme
        </h2>
        <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.inkSoft, lineHeight: 1.6, margin: "0 0 22px", maxWidth: 320, marginLeft: "auto", marginRight: "auto" }}>
          Réservé au Maître Fantôme, gardien de Ghost Cards, pour voir et relancer les traitements OCR en arrière-plan.
        </p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Mot de passe admin"
          autoFocus
          style={{ width: "100%", maxWidth: 260, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "10px 14px", fontFamily: uiFont, fontSize: 14, color: C.ink, outline: "none", textAlign: "center" }}
        />
        {error && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "10px 0 0" }}>{error}</p>}
        <div>
          <button
            onClick={submit}
            disabled={submitting || !password}
            style={{ marginTop: 18, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "11px 24px", fontFamily: uiFont, fontSize: 14, fontWeight: 700, cursor: password ? "pointer" : "default", opacity: submitting ? 0.7 : 1 }}
          >
            {submitting ? "Connexion…" : "Se connecter"}
          </button>
        </div>
      </div>
    </div>
  );
}
