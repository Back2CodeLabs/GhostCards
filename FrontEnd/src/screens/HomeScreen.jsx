import { useState } from "react";
import { ChevronRight, RefreshCw } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi } from "../api";
import { Loading, ApiError, EmptyState, SectionLabel, Divider } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Accueil                                                              */
/* ------------------------------------------------------------------ */

export function HomeScreen({ onOpenSubject, onOpenCours }) {
  const { C, colorFor } = useTheme();
  const matieres = useApi("/api/matieres");
  const recents = useApi("/api/cours/recents?limit=5");
  const devoirs = useApi("/api/devoirs");
  const [syncing, setSyncing] = useState(false);

  async function refresh() {
    setSyncing(true);
    try {
      await fetch(`${API_BASE}/api/sync`, { method: "POST" });
    } catch (e) {
      /* remonté visuellement via matieres.error au prochain reload si le serveur est injoignable */
    }
    setTimeout(() => {
      matieres.reload();
      recents.reload();
      devoirs.reload();
      setSyncing(false);
    }, 1500);
  }

  return (
    <div style={{ paddingBottom: 24 }}>
      <div className="flex items-center justify-between" style={{ padding: "22px 20px 6px" }}>
        <div>
          <p style={{ fontFamily: uiFont, color: C.inkFaint, fontSize: 13, margin: 0 }}>Ghost Cards</p>
          <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 26, color: C.ink, margin: "2px 0 0" }}>Bonjour 👋</h1>
        </div>
        <button
          onClick={refresh}
          disabled={syncing}
          style={{ border: `1px solid ${C.line}`, background: C.white, borderRadius: 999, padding: "8px 14px", display: "flex", alignItems: "center", gap: 6, cursor: syncing ? "default" : "pointer", fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft }}
        >
          <RefreshCw size={13} style={syncing ? { animation: "spin 1s linear infinite" } : {}} />
          {syncing ? "Synchro…" : "Actualiser"}
        </button>
      </div>

      <section style={{ padding: "18px 20px 4px" }}>
        <SectionLabel>Mes matières</SectionLabel>
        {matieres.loading && <Loading />}
        {matieres.error && <ApiError message={matieres.error} onRetry={matieres.reload} />}
        {matieres.data && matieres.data.length === 0 && (
          <EmptyState text="Aucune matière pour l'instant." sub="Lance une synchronisation Pronote pour importer tes cours." />
        )}
        {matieres.data && matieres.data.length > 0 && (
          <div className="gc-grid" style={{ marginTop: 10 }}>
            {matieres.data.map((m) => {
              const { color } = colorFor(m.id);
              return (
                <button
                  key={m.id}
                  onClick={() => onOpenSubject(m.id, m.nom)}
                  style={{ display: "flex", alignItems: "center", gap: 12, background: C.white, border: `1px solid ${C.line}`, borderLeft: `4px solid ${color}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer", textAlign: "left", fontFamily: uiFont }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14.5, color: C.ink, fontWeight: 600 }}>{m.nom}</div>
                    <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 2 }}>
                      {m.nb_cours} cours · {m.nb_documents} documents
                    </div>
                  </div>
                  <ChevronRight size={16} color={C.inkFaint} />
                </button>
              );
            })}
          </div>
        )}
      </section>

      <Divider />

      <section style={{ padding: "4px 20px" }}>
        <SectionLabel>Devoirs à rendre</SectionLabel>
        {devoirs.loading && <Loading />}
        {devoirs.data && devoirs.data.length === 0 && (
          <p style={{ fontFamily: uiFont, fontSize: 13, color: C.inkFaint, marginTop: 10 }}>Rien en attente. 👻</p>
        )}
        {devoirs.data && devoirs.data.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            {devoirs.data.slice(0, 5).map((d) => (
              <div key={d.id} style={{ background: C.hauntSoft, borderRadius: 10, padding: "11px 14px" }}>
                <div className="flex items-center justify-between">
                  <span style={{ fontFamily: uiFont, fontSize: 13, fontWeight: 600, color: C.ink }}>{d.matiere}</span>
                  <span style={{ fontFamily: uiFont, fontSize: 11.5, color: C.haunt, fontWeight: 700 }}>
                    pour le {new Date(d.date_rendu).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
                  </span>
                </div>
                {d.description && (
                  <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft, margin: "4px 0 0" }}>
                    {d.description.slice(0, 90)}
                    {d.description.length > 90 ? "…" : ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <Divider />

      <section style={{ padding: "4px 20px" }}>
        <SectionLabel>Nouveaux cours</SectionLabel>
        {recents.loading && <Loading />}
        {recents.data && recents.data.length === 0 && (
          <p style={{ fontFamily: uiFont, fontSize: 13, color: C.inkFaint, marginTop: 10 }}>Aucun cours importé pour l'instant.</p>
        )}
        {recents.data && recents.data.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            {recents.data.map((c) => (
              <button
                key={c.id}
                onClick={() => onOpenCours(c.id)}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "transparent", border: `1px solid ${C.line}`, borderRadius: 10, padding: "11px 14px", cursor: "pointer", textAlign: "left", fontFamily: uiFont }}
              >
                <div>
                  <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 600 }}>{c.titre || c.matiere}</div>
                  <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 1 }}>
                    {c.matiere} · {new Date(c.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
                  </div>
                </div>
                <ChevronRight size={16} color={C.inkFaint} />
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
