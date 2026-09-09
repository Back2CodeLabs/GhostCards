import { ArrowLeft, Ghost, RefreshCw, WifiOff } from "lucide-react";
import { useTheme, uiFont } from "../theme";

/* ------------------------------------------------------------------ */
/* Petits composants partagés                                          */
/* ------------------------------------------------------------------ */

export function ScreenHeader({ title, onBack, right }) {
  const { C } = useTheme();
  return (
    <div
      className="flex items-center justify-between"
      style={{ padding: "18px 20px 14px", borderBottom: `1px solid ${C.line}`, background: C.paper, position: "sticky", top: 0, zIndex: 5 }}
    >
      <div className="flex items-center gap-2">
        {onBack && (
          <button onClick={onBack} style={{ border: "none", background: "transparent", cursor: "pointer", color: C.ink, display: "flex", padding: 4, marginLeft: -6 }} aria-label="Retour">
            <ArrowLeft size={20} />
          </button>
        )}
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 20, color: C.ink, margin: 0 }}>{title}</h1>
      </div>
      {right}
    </div>
  );
}

export function EmptyState({ text, sub, icon: Icon = Ghost }) {
  const { C } = useTheme();
  return (
    <div style={{ padding: "40px 24px", textAlign: "center" }}>
      <Icon size={34} color={C.inkFaint} strokeWidth={1.4} style={{ marginBottom: 10 }} />
      <p style={{ fontFamily: uiFont, color: C.inkSoft, fontSize: 14.5, margin: 0, lineHeight: 1.5 }}>{text}</p>
      {sub && <p style={{ fontFamily: uiFont, color: C.inkFaint, fontSize: 13, marginTop: 6 }}>{sub}</p>}
    </div>
  );
}

export function Loading() {
  const { C } = useTheme();
  return (
    <div style={{ padding: "50px 24px", textAlign: "center" }}>
      <RefreshCw size={22} color={C.inkFaint} style={{ animation: "spin 1s linear infinite" }} />
      <p style={{ fontFamily: uiFont, color: C.inkFaint, fontSize: 13, marginTop: 10 }}>Chargement…</p>
    </div>
  );
}

export function ApiError({ message, onRetry }) {
  const { C } = useTheme();
  return (
    <div style={{ padding: "40px 24px", textAlign: "center" }}>
      <WifiOff size={30} color={C.brick} strokeWidth={1.5} style={{ marginBottom: 10 }} />
      <p style={{ fontFamily: uiFont, color: C.brick, fontSize: 14, margin: "0 0 4px", fontWeight: 600 }}>
        Impossible de joindre le serveur Ghost Cards
      </p>
      <p style={{ fontFamily: uiFont, color: C.inkSoft, fontSize: 12.5, margin: "0 0 16px" }}>{message}</p>
      <button
        onClick={onRetry}
        style={{ background: C.white, border: `1.5px solid ${C.line}`, borderRadius: 10, padding: "9px 18px", fontFamily: uiFont, fontSize: 13, fontWeight: 600, color: C.ink, cursor: "pointer" }}
      >
        Réessayer
      </button>
    </div>
  );
}

export function SectionLabel({ children }) {
  const { C } = useTheme();
  return <p style={{ fontFamily: uiFont, color: C.inkSoft, fontSize: 12.5, fontWeight: 600, margin: 0 }}>{children}</p>;
}

export function Divider() {
  const { C } = useTheme();
  return <div style={{ height: 1, background: C.line, margin: "16px 20px" }} />;
}
