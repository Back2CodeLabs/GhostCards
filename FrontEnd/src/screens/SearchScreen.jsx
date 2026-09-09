import { useState } from "react";
import { Search as SearchIcon } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { useApi } from "../api";

/* ------------------------------------------------------------------ */
/* Recherche (locale, sur les données déjà chargées)                    */
/* ------------------------------------------------------------------ */

export function SearchScreen({ onOpenSubject, onOpenCours }) {
  const { C } = useTheme();
  const matieres = useApi("/api/matieres");
  const recents = useApi("/api/cours/recents?limit=50");
  const [q, setQ] = useState("");
  const query = q.trim().toLowerCase();

  const matiereResults = query ? (matieres.data || []).filter((m) => m.nom.toLowerCase().includes(query)) : [];
  const coursResults = query ? (recents.data || []).filter((c) => (c.titre || "").toLowerCase().includes(query) || c.matiere.toLowerCase().includes(query)) : [];

  const resultRowStyle = { display: "flex", justifyContent: "space-between", alignItems: "center", background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer", textAlign: "left", fontFamily: uiFont, width: "100%" };
  const tagStyle = { fontSize: 11, color: C.inkFaint, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.3 };

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Recherche</h1>
      </div>
      <div style={{ padding: "14px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "10px 14px" }}>
          <SearchIcon size={16} color={C.inkFaint} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Une matière, un cours…"
            style={{ border: "none", outline: "none", flex: 1, fontFamily: uiFont, fontSize: 14, color: C.ink, background: "transparent" }}
          />
        </div>

        {query && matiereResults.length === 0 && coursResults.length === 0 && (
          <p style={{ fontFamily: uiFont, fontSize: 13, color: C.inkFaint, marginTop: 20, textAlign: "center" }}>Aucun résultat pour « {q} ».</p>
        )}

        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
          {matiereResults.map((m) => (
            <button key={`m${m.id}`} onClick={() => onOpenSubject(m.id, m.nom)} style={resultRowStyle}>
              <span style={{ fontSize: 13.5, color: C.ink }}>{m.nom}</span>
              <span style={tagStyle}>Matière</span>
            </button>
          ))}
          {coursResults.map((c) => (
            <button key={`c${c.id}`} onClick={() => onOpenCours(c.id)} style={resultRowStyle}>
              <span style={{ fontSize: 13.5, color: C.ink }}>{c.titre || c.matiere}</span>
              <span style={tagStyle}>Cours</span>
            </button>
          ))}
        </div>

        {!query && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, marginTop: 18 }}>Cherche parmi tes matières et cours importés.</p>}
      </div>
    </div>
  );
}
