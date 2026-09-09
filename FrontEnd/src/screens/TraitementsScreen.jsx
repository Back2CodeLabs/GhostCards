import { useState, useEffect } from "react";
import { ChevronRight, ListChecks, CheckCircle2, XCircle, Loader2, Sparkles, RotateCcw, RefreshCw } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi } from "../api";
import { Loading, ApiError, EmptyState, ScreenHeader } from "../components/Shared";
import { ResultatFormatte } from "../components/ResultatFormatte";

/* ------------------------------------------------------------------ */
/* Traitements — outil de diagnostic réservé à l'admin (Cédric) :       */
/* voir le rendu de chaque extraction/OCR en arrière-plan et relancer   */
/* si le résultat n'est pas satisfaisant. Pas une fonctionnalité élève. */
/* ------------------------------------------------------------------ */

function traitementStatutInfo(C, statut) {
  if (statut === "succes") return { label: "Succès", color: C.spectral, Icon: CheckCircle2 };
  if (statut === "echec") return { label: "Échec", color: C.brick, Icon: XCircle };
  return { label: "En cours", color: C.inkFaint, Icon: Loader2 };
}

function formatDateHeure(iso) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("fr-FR")} à ${d.toLocaleTimeString("fr-FR")}`;
}

function formatDuree(ms) {
  if (ms == null) return null;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return `${m} min ${String(rs).padStart(2, "0")} s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h} h ${String(rm).padStart(2, "0")} min`;
}

// Fait tiquer un composant toutes les `intervalMs` tant que `active` est
// vrai — utilisé pour afficher un temps écoulé en direct sur un
// traitement en_cours (une génération IA peut tourner ~30 min).
function useNow(active, intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [active, intervalMs]);
  return now;
}

function traitementTitre(t) {
  if (t.type === "pronote_sync") return "Synchronisation Pronote";
  return `${t.type} · ${t.cible_type} #${t.cible_id}`;
}

export function TraitementsScreen({ onOpenTraitement }) {
  const { C } = useTheme();
  const traitements = useApi("/api/traitements");
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);

  async function lancerSync() {
    if (syncing) return;
    setSyncing(true);
    setSyncError(null);
    try {
      const res = await fetch(`${API_BASE}/api/sync`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      const data = await res.json();
      if (data.traitement_id) onOpenTraitement(data.traitement_id);
      else traitements.reload();
    } catch (e) {
      setSyncError(e.message || "Impossible de lancer la synchronisation.");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Traitements</h1>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "4px 0 0" }}>
          Actions lancées en arrière-plan : synchronisations Pronote, extractions de texte et OCR.
        </p>
      </div>
      <div style={{ padding: "16px 20px 0" }}>
        <button
          onClick={lancerSync}
          disabled={syncing}
          style={{ display: "flex", alignItems: "center", gap: 8, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "9px 16px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: syncing ? "default" : "pointer", opacity: syncing ? 0.7 : 1 }}
        >
          <RefreshCw size={13} style={syncing ? { animation: "spin 1s linear infinite" } : {}} />
          {syncing ? "Lancement…" : "Lancer une synchronisation Pronote"}
        </button>
        {syncError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "8px 0 0" }}>{syncError}</p>}
      </div>
      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
        {traitements.loading && <Loading />}
        {traitements.error && <ApiError message={traitements.error} onRetry={traitements.reload} />}
        {traitements.data && traitements.data.length === 0 && (
          <EmptyState text="Aucun traitement pour l'instant." sub="Ils apparaîtront ici dès qu'un document ou une note sera transcrit." icon={ListChecks} />
        )}
        {traitements.data?.map((t) => {
          const { label, color, Icon } = traitementStatutInfo(C, t.statut);
          return (
            <button
              key={t.id}
              onClick={() => onOpenTraitement(t.id)}
              style={{ display: "flex", alignItems: "center", gap: 10, background: C.white, border: `1px solid ${C.line}`, borderLeft: `3px solid ${color}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer", textAlign: "left", fontFamily: uiFont }}
            >
              <Icon size={16} color={color} style={t.statut === "en_cours" ? { animation: "spin 1s linear infinite" } : {}} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 600 }}>
                  {traitementTitre(t)}
                </div>
                <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 2 }}>
                  {label} {t.moteur ? `· ${t.moteur}` : ""} · {new Date(t.created_at).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                </div>
              </div>
              <ChevronRight size={16} color={C.inkFaint} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TraitementDetail({ traitementId, onBack }) {
  const { C } = useTheme();
  const traitement = useApi(`/api/traitements/${traitementId}`, [traitementId]);
  const [relancing, setRelancing] = useState(false);
  const [relanceMsg, setRelanceMsg] = useState(null);
  const enCours = traitement.data?.statut === "en_cours";
  const now = useNow(enCours);

  // Tant que le traitement tourne (une génération IA peut prendre jusqu'à
  // ~30 min), on réactualise pour voir la fin sans recharger la page.
  useEffect(() => {
    if (!enCours) return;
    const t = setInterval(() => traitement.reload(), 5000);
    return () => clearInterval(t);
  }, [enCours, traitement.reload]);

  async function relancer() {
    setRelancing(true);
    setRelanceMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/traitements/${traitementId}/relancer`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      setRelanceMsg("Relance lancée en arrière-plan — un nouveau traitement apparaîtra dans la liste dans quelques secondes.");
    } catch (e) {
      setRelanceMsg(e.message || "Impossible de relancer ce traitement.");
    } finally {
      setRelancing(false);
    }
  }

  if (traitement.loading) return (<div><ScreenHeader title="Traitement" onBack={onBack} /><Loading /></div>);
  if (traitement.error) return (<div><ScreenHeader title="Traitement" onBack={onBack} /><ApiError message={traitement.error} onRetry={traitement.reload} /></div>);

  const t = traitement.data;
  const { label, color, Icon } = traitementStatutInfo(C, t.statut);
  const dureeAffichee = enCours
    ? formatDuree(now - new Date(t.created_at).getTime())
    : formatDuree(t.duree_ms);

  return (
    <div style={{ paddingBottom: 28 }}>
      <ScreenHeader title={traitementTitre(t)} onBack={onBack} />
      <div style={{ padding: "16px 20px 0" }}>
        <div className="flex items-center gap-2">
          <Icon size={16} color={color} />
          <span style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color }}>{label}</span>
          {t.moteur && <span style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint }}>· moteur {t.moteur}</span>}
          {dureeAffichee && (
            <span style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint }}>
              · {dureeAffichee}{enCours ? " (en cours…)" : ""}
            </span>
          )}
        </div>
        <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: "6px 0 0" }}>
          Lancé le {formatDateHeure(t.created_at)}
          {t.finished_at ? ` · terminé le ${formatDateHeure(t.finished_at)}` : ""}
        </p>

        {t.erreur && (
          <div style={{ marginTop: 16, background: C.brickSoft, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16 }}>
            <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.brick, letterSpacing: 0.3, margin: "0 0 8px" }}>ERREUR</p>
            <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.ink, lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>{t.erreur}</p>
          </div>
        )}

        {t.etapes && t.etapes.length > 0 && (
          <>
            <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "20px 0 8px" }}>
              ÉTAPES ({t.etapes.length})
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {t.etapes.map((e, i) => {
                const info =
                  e.statut === "echec" ? { color: C.brick, Icon: XCircle }
                  : e.statut === "info" ? { color: C.inkFaint, Icon: Sparkles }
                  : { color: C.spectral, Icon: CheckCircle2 };
                return (
                  <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, background: C.white, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 12px" }}>
                    <info.Icon size={14} color={info.color} style={{ flexShrink: 0, marginTop: 2 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, color: C.ink, fontWeight: 600 }}>
                        {i + 1}. {e.label}
                        {e.moteur && !e.label.toLowerCase().includes(e.moteur.toLowerCase()) ? ` (${e.moteur})` : ""}
                      </div>
                      {e.detail && <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 2 }}>{e.detail}</div>}
                    </div>
                    {e.duree_ms != null && (
                      <div style={{ fontSize: 11, color: C.inkFaint, flexShrink: 0, whiteSpace: "nowrap" }}>{formatDuree(e.duree_ms)}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {t.resultat && (
          <div style={{ marginTop: 16, background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16, overflowX: "auto" }}>
            <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "0 0 8px" }}>RÉSULTAT</p>
            <ResultatFormatte texte={t.resultat} />
          </div>
        )}

        <button
          onClick={relancer}
          disabled={relancing}
          style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 8, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "10px 18px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: relancing ? "default" : "pointer", opacity: relancing ? 0.7 : 1 }}
        >
          <RotateCcw size={15} style={relancing ? { animation: "spin 1s linear infinite" } : {}} /> {relancing ? "Relance…" : "Relancer"}
        </button>
        {relanceMsg && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft, margin: "10px 0 0" }}>{relanceMsg}</p>}
      </div>
    </div>
  );
}
