import { useState } from "react";
import { Users, Sparkles, RotateCcw, XCircle } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi, messageErreur } from "../api";
import { Loading, ApiError, EmptyState } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Élèves — liste admin (comptes pairés avec leur propre Pronote, voir  */
/* BackEnd/app/main.py::pairer_eleve_pronote). Jamais visible des        */
/* élèves eux-mêmes.                                                    */
/* ------------------------------------------------------------------ */

export function ElevesScreen() {
  const { C } = useTheme();
  const eleves = useApi("/api/eleves");
  const [togglingId, setTogglingId] = useState(null);
  const [reinitId, setReinitId] = useState(null);
  const [reinitError, setReinitError] = useState(null);

  async function toggleAssistant(eleve) {
    setTogglingId(eleve.id);
    try {
      await fetch(`${API_BASE}/api/eleves/${eleve.id}/assistant`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actif: !eleve.assistant_actif }),
      });
      eleves.reload();
    } finally {
      setTogglingId(null);
    }
  }

  async function forcerRepairage(eleve) {
    setReinitId(eleve.id);
    setReinitError(null);
    try {
      const res = await fetch(`${API_BASE}/api/eleves/${eleve.id}/reinitialiser-pronote`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      eleves.reload();
    } catch (e) {
      setReinitError(messageErreur(e, "Impossible de réinitialiser ce compte."));
    } finally {
      setReinitId(null);
    }
  }

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Élèves</h1>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "4px 0 0" }}>
          Comptes pairés avec leur propre Pronote (au moins une connexion). L'assistant IA est
          désactivé par défaut pour chacun.
        </p>
        {reinitError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "8px 0 0" }}>{reinitError}</p>}
      </div>
      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
        {eleves.loading && <Loading />}
        {eleves.error && <ApiError message={eleves.error} onRetry={eleves.reload} />}
        {eleves.data && eleves.data.length === 0 && (
          <EmptyState text="Aucun élève connecté pour l'instant." icon={Users} />
        )}
        {eleves.data?.map((e) => (
          <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 12, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "12px 14px" }}>
            {e.avatar_url ? (
              <img src={e.avatar_url} alt="" style={{ width: 32, height: 32, borderRadius: "50%" }} referrerPolicy="no-referrer" />
            ) : (
              <span style={{ width: 32, height: 32, borderRadius: "50%", background: C.hauntSoft, color: C.haunt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
                {(e.nom || "?").trim().charAt(0).toUpperCase()}
              </span>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 600 }}>{e.nom}</div>
              <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {e.pronote_class_name || "classe inconnue"}
                {e.pronote_sync_statut === "echec" && (
                  <span style={{ color: C.brick, marginLeft: 6 }} title={e.pronote_sync_erreur || ""}>
                    <XCircle size={11} style={{ display: "inline", verticalAlign: -1, marginRight: 3 }} />
                    lien Pronote cassé
                  </span>
                )}
              </div>
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontSize: 12, color: C.inkSoft }}>{e.nb_notes} note{e.nb_notes === 1 ? "" : "s"}</div>
              <div style={{ fontSize: 11, color: C.inkFaint, marginTop: 1 }}>
                vu le {new Date(e.derniere_connexion).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
              </div>
            </div>
            <button
              onClick={() => toggleAssistant(e)}
              disabled={togglingId === e.id}
              title={e.assistant_actif ? "Désactiver l'assistant pour cet élève" : "Activer l'assistant pour cet élève"}
              style={{
                display: "flex", alignItems: "center", gap: 5, flexShrink: 0,
                background: e.assistant_actif ? C.hauntSoft : C.paperDim,
                border: `1px solid ${e.assistant_actif ? C.haunt : C.line}`,
                borderRadius: 999, padding: "5px 10px", fontFamily: uiFont, fontSize: 11, fontWeight: 700,
                color: e.assistant_actif ? C.haunt : C.inkFaint,
                cursor: togglingId === e.id ? "default" : "pointer", opacity: togglingId === e.id ? 0.6 : 1,
              }}
            >
              <Sparkles size={12} /> {e.assistant_actif ? "Assistant ON" : "Assistant OFF"}
            </button>
            <button
              onClick={() => forcerRepairage(e)}
              disabled={reinitId === e.id}
              title="Forcer un nouveau pairage Pronote (à utiliser si le lien est cassé)"
              style={{
                display: "flex", alignItems: "center", gap: 5, flexShrink: 0,
                background: "transparent", border: `1px solid ${C.line}`, borderRadius: 999,
                padding: "5px 10px", fontFamily: uiFont, fontSize: 11, fontWeight: 700, color: C.inkFaint,
                cursor: reinitId === e.id ? "default" : "pointer", opacity: reinitId === e.id ? 0.6 : 1,
              }}
            >
              <RotateCcw size={12} /> Re-pairer
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
