import React, { useState, useEffect, useCallback, useRef, useContext, createContext } from "react";
import "./index.css";
import {
  Ghost,
  Home,
  BookOpen,
  Search as SearchIcon,
  MessageCircle,
  ArrowLeft,
  ChevronRight,
  Sparkles,
  Send,
  FileText,
  RefreshCw,
  WifiOff,
  Download,
  Moon,
  Sun,
  LogIn,
  LogOut,
  StickyNote,
  ListChecks,
  Paperclip,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Loader2,
  ShieldCheck,
  Users,
  Settings,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Connexion à l'API                                                    */
/* ------------------------------------------------------------------ */
//
// En déploiement réel (frontend buildé et servi par le même process
// FastAPI que l'API, sur l'OptiPlex), laisser une chaîne vide : les
// appels partent alors vers la même origine, pas de souci de CORS ni de
// contenu mixte.
const API_BASE = "";

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} sur ${path}`);
  return res.json();
}

/* ------------------------------------------------------------------ */
/* Thèmes — clair (origine) et sombre (néon, rétro 80s, avec parcimonie) */
/* ------------------------------------------------------------------ */

const uiFont = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const LIGHT = {
  name: "light",
  paper: "#F6F3EC",
  paperDim: "#EFEAE0",
  ink: "#211C30",
  inkSoft: "#5C567A",
  inkFaint: "#8C84A8",
  line: "#E2DACB",
  white: "#FFFFFF", // surfaces élevées (cartes, boutons secondaires, champs)
  onAccent: "#FFFFFF", // texte/icônes posés sur un fond de couleur (haunt, etc.)
  haunt: "#6C4FA1",
  hauntSoft: "#EEE7F7",
  spectral: "#2E9E86",
  spectralSoft: "#DDF0EA",
  brick: "#B8452E",
  brickSoft: "#F5E2DC",
  fontHeading: "Georgia, 'Iowan Old Style', 'Palatino Linotype', 'Times New Roman', serif",
  headingLetterSpacing: "normal",
  neonGlow: false,
};

// Palette "sombre" : même rôle sémantique que chaque couleur claire
// (haunt = accent principal, spectral = succès/maîtrisé, brick = alerte),
// mais rendue en néon sur fond très sombre plutôt qu'en pastel — l'effet
// rétro 80s reste ponctuel (bordures, puces, icônes actives), pas des
// aplats entiers, pour que ça reste lisible au quotidien.
const DARK = {
  name: "dark",
  paper: "#1B1330",
  paperDim: "#0F0919",
  ink: "#F3ECFF",
  inkSoft: "#B6A6DE",
  inkFaint: "#7A6C9C",
  line: "#3C2B5E",
  white: "#241A3D",
  onAccent: "#170F26",
  haunt: "#FF3EC9",
  hauntSoft: "#3A1240",
  spectral: "#2EF2C8",
  spectralSoft: "#0F3B34",
  // Corail plutôt que rouge pur : sur un fond violet, un rouge franc
  // (#FF5D5D) jure et fatigue l'œil (deux teintes qui se disputent
  // l'attention plutôt que de se compléter). Décalé vers l'orange, il
  // reste identifiable comme "alerte" sans ce clash.
  brick: "#FF6B4A",
  brickSoft: "#3D2016",
  fontHeading: "'Arial Black', 'Helvetica Neue', Arial, sans-serif",
  headingLetterSpacing: "0.3px",
  neonGlow: true,
};

const LIGHT_PALETTE = [LIGHT.haunt, LIGHT.spectral, "#A97A22", "#3E6B8A", "#5C7A38", LIGHT.brick];
const DARK_PALETTE = [DARK.haunt, DARK.spectral, "#FFD23E", "#3EC1FF", "#9DFF3E", DARK.brick];

function makeColorFor(C, palette) {
  const soft = { [C.haunt]: C.hauntSoft, [C.spectral]: C.spectralSoft, [C.brick]: C.brickSoft };
  return function colorFor(id) {
    const c = palette[id % palette.length];
    return { color: c, soft: soft[c] || C.paperDim };
  };
}

const ThemeContext = createContext(null);
function useTheme() {
  return useContext(ThemeContext);
}

function glowText(C, color, strength = 1) {
  if (!C.neonGlow) return {};
  return { textShadow: `0 0 ${6 * strength}px ${color}, 0 0 ${16 * strength}px ${color}66` };
}

/* ------------------------------------------------------------------ */
/* Petits composants partagés                                          */
/* ------------------------------------------------------------------ */

function ScreenHeader({ title, onBack, right }) {
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

function EmptyState({ text, sub, icon: Icon = Ghost }) {
  const { C } = useTheme();
  return (
    <div style={{ padding: "40px 24px", textAlign: "center" }}>
      <Icon size={34} color={C.inkFaint} strokeWidth={1.4} style={{ marginBottom: 10 }} />
      <p style={{ fontFamily: uiFont, color: C.inkSoft, fontSize: 14.5, margin: 0, lineHeight: 1.5 }}>{text}</p>
      {sub && <p style={{ fontFamily: uiFont, color: C.inkFaint, fontSize: 13, marginTop: 6 }}>{sub}</p>}
    </div>
  );
}

function Loading() {
  const { C } = useTheme();
  return (
    <div style={{ padding: "50px 24px", textAlign: "center" }}>
      <RefreshCw size={22} color={C.inkFaint} style={{ animation: "spin 1s linear infinite" }} />
      <p style={{ fontFamily: uiFont, color: C.inkFaint, fontSize: 13, marginTop: 10 }}>Chargement…</p>
    </div>
  );
}

function ApiError({ message, onRetry }) {
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

function SectionLabel({ children }) {
  const { C } = useTheme();
  return <p style={{ fontFamily: uiFont, color: C.inkSoft, fontSize: 12.5, fontWeight: 600, margin: 0 }}>{children}</p>;
}
function Divider() {
  const { C } = useTheme();
  return <div style={{ height: 1, background: C.line, margin: "16px 20px" }} />;
}

/* ------------------------------------------------------------------ */
/* Hook générique de récupération API                                   */
/* ------------------------------------------------------------------ */

function useApi(path, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    apiGet(path)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((e) => setState({ data: null, loading: false, error: e.message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}

/* ------------------------------------------------------------------ */
/* Identité de l'élève connecté (Google) — sert uniquement à attribuer  */
/* les notes déposées ; la consultation du site reste libre.            */
/* ------------------------------------------------------------------ */

function useMe() {
  const [state, setState] = useState({ eleve: null, isAdmin: false, loading: true });

  const load = useCallback(() => {
    fetch(`${API_BASE}/api/me`)
      .then((res) => (res.ok ? res.json() : { eleve: null, is_admin: false }))
      .then((data) => setState({ eleve: data.eleve || null, isAdmin: !!data.is_admin, loading: false }))
      .catch(() => setState({ eleve: null, isAdmin: false, loading: false }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function logout() {
    await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
    setState((s) => ({ ...s, eleve: null }));
  }

  // Connexion admin : mot de passe séparé, totalement indépendant des
  // comptes élèves (Google) — voir Services/config.py::ADMIN_PASSWORD.
  async function adminLogin(password) {
    const res = await fetch(`${API_BASE}/auth/admin-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur ${res.status}`);
    }
    setState((s) => ({ ...s, isAdmin: true }));
  }

  async function adminLogout() {
    await fetch(`${API_BASE}/auth/admin-logout`, { method: "POST" });
    setState((s) => ({ ...s, isAdmin: false }));
  }

  return { ...state, reload: load, logout, adminLogin, adminLogout };
}

/* ------------------------------------------------------------------ */
/* Accueil                                                              */
/* ------------------------------------------------------------------ */

function HomeScreen({ onOpenSubject, onOpenCours }) {
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

/* ------------------------------------------------------------------ */
/* Matières                                                             */
/* ------------------------------------------------------------------ */

function SubjectsScreen({ onOpenSubject }) {
  const { C, colorFor } = useTheme();
  const matieres = useApi("/api/matieres");
  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Matières</h1>
      </div>
      <div style={{ padding: "16px 20px" }}>
        {matieres.loading && <Loading />}
        {matieres.error && <ApiError message={matieres.error} onRetry={matieres.reload} />}
        {matieres.data && matieres.data.length === 0 && <EmptyState text="Aucune matière importée pour l'instant." />}
        <div className="gc-grid">
          {matieres.data?.map((m) => {
            const { color } = colorFor(m.id);
            return (
              <button
                key={m.id}
                onClick={() => onOpenSubject(m.id, m.nom)}
                style={{ background: C.white, border: `1px solid ${C.line}`, borderTop: `3px solid ${color}`, borderRadius: 12, padding: 16, cursor: "pointer", textAlign: "left", fontFamily: uiFont, display: "flex", flexDirection: "column", gap: 8 }}
              >
                <span style={{ fontSize: 16, fontWeight: 700, color: C.ink, fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing }}>{m.nom}</span>
                <div style={{ display: "flex", gap: 16, fontSize: 12.5, color: C.inkSoft }}>
                  <span>{m.nb_cours} cours</span>
                  <span>{m.nb_documents} documents</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Détail matière                                                       */
/* ------------------------------------------------------------------ */

function SubjectDetail({ subjectId, subjectName, onBack, onOpenCours }) {
  const { C, colorFor } = useTheme();
  const cours = useApi(`/api/matieres/${subjectId}/cours`, [subjectId]);
  const { color } = colorFor(subjectId);

  return (
    <div>
      <ScreenHeader title={subjectName} onBack={onBack} />
      <div style={{ padding: "16px 20px" }} className="gc-grid">
        {cours.loading && <Loading />}
        {cours.error && <ApiError message={cours.error} onRetry={cours.reload} />}
        {cours.data && cours.data.length === 0 && (
          <EmptyState text="Aucun cours importé pour cette matière." sub="Il apparaîtra ici après la prochaine synchronisation Pronote." />
        )}
        {cours.data?.map((c) => (
          <button
            key={c.id}
            onClick={() => onOpenCours(c.id)}
            style={{ background: C.white, border: `1px solid ${C.line}`, borderLeft: `3px solid ${color}`, borderRadius: 10, padding: "13px 14px", cursor: "pointer", textAlign: "left", fontFamily: uiFont }}
          >
            <div className="flex items-center justify-between">
              <span style={{ fontSize: 14.5, fontWeight: 600, color: C.ink }}>{c.titre || "Cours"}</span>
              <ChevronRight size={16} color={C.inkFaint} />
            </div>
            <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 3 }}>
              {new Date(c.date).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })} · {c.heure_debut}
              {c.professeur ? ` · ${c.professeur}` : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Détail cours                                                         */
/* ------------------------------------------------------------------ */

function CoursDetail({ coursId, onBack, me, onRequireLogin }) {
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
  const [completing, setCompleting] = useState(false);
  const [completingError, setCompletingError] = useState(null);
  const [resumeDetaille, setResumeDetaille] = useState(false);

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
    try {
      const res = await fetch(`${API_BASE}/api/cours/${coursId}/generer`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      cours.reload();
    } catch (e) {
      setGenerationError(e.message || "Impossible de lancer la génération.");
    } finally {
      setGenerating(false);
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

  return (
    <div style={{ paddingBottom: 28 }}>
      <ScreenHeader title={c.titre || "Cours"} onBack={onBack} />
      <div style={{ padding: "16px 20px 0" }}>
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

        {c.ia_resume ? (
          <div style={{ marginTop: 22 }}>
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

            {c.ia_flashcards.length > 0 && (
              <>
                <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "18px 0 8px" }}>
                  FLASHCARDS ({c.ia_flashcards.length})
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {c.ia_flashcards.map((card, i) => (
                    <Flashcard key={i} card={card} />
                  ))}
                </div>
              </>
            )}

            {c.ia_quiz.length > 0 && (
              <>
                <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "18px 0 8px" }}>
                  QUIZ ({c.ia_quiz.length} questions)
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {c.ia_quiz.map((q, i) => (
                    <QuizQuestion key={i} question={q} index={i} />
                  ))}
                </div>
              </>
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
                disabled={generating || c.ia_statut === "en_cours"}
                style={{ display: "flex", alignItems: "center", gap: 8, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "9px 16px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 600, color: C.inkSoft, cursor: generating ? "default" : "pointer" }}
              >
                <RefreshCw size={13} style={generating ? { animation: "spin 1s linear infinite" } : {}} /> Régénérer
              </button>
            </div>
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
        ) : (
          <div style={{ marginTop: 22, background: C.hauntSoft, borderRadius: 12, padding: 16, display: "flex", gap: 12, alignItems: "flex-start" }}>
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
    </div>
  );
}

function Flashcard({ card }) {
  const { C } = useTheme();
  const [revealed, setRevealed] = useState(false);
  return (
    <button
      onClick={() => setRevealed((r) => !r)}
      style={{ display: "block", width: "100%", textAlign: "left", background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer", fontFamily: uiFont }}
    >
      <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 600 }}>{card.question}</div>
      {revealed ? (
        <div style={{ fontSize: 13, color: C.spectral, marginTop: 6 }}>{card.reponse}</div>
      ) : (
        <div style={{ fontSize: 12, color: C.inkFaint, marginTop: 6 }}>Toucher pour voir la réponse</div>
      )}
    </button>
  );
}

function QuizQuestion({ question, index }) {
  const { C } = useTheme();
  const [choix, setChoix] = useState(null);
  return (
    <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "12px 14px" }}>
      <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 600, marginBottom: 8 }}>
        {index + 1}. {question.question}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {question.options.map((opt, i) => {
          const estChoisie = choix === i;
          const estCorrecte = i === question.reponse_index;
          let bg = C.paperDim;
          let border = C.line;
          if (choix !== null && estCorrecte) border = C.spectral;
          else if (estChoisie && !estCorrecte) border = C.brick;
          if (choix !== null && estCorrecte) bg = C.spectralSoft;
          else if (estChoisie && !estCorrecte) bg = C.brickSoft;
          return (
            <button
              key={i}
              onClick={() => choix === null && setChoix(i)}
              style={{ textAlign: "left", background: bg, border: `1px solid ${border}`, borderRadius: 8, padding: "8px 12px", fontFamily: uiFont, fontSize: 13, color: C.ink, cursor: choix === null ? "pointer" : "default" }}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
}

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

function TraitementsScreen({ onOpenTraitement }) {
  const { C } = useTheme();
  const traitements = useApi("/api/traitements");

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Traitements</h1>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "4px 0 0" }}>
          Actions lancées en arrière-plan : synchronisations Pronote, extractions de texte et OCR.
        </p>
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

/* ------------------------------------------------------------------ */
/* Rendu "pretty" du résultat d'un traitement (JSON / XML / Markdown    */
/* léger / texte brut) — l'OCR et l'IA renvoient surtout du JSON ou du  */
/* markdown, illisibles sans mise en forme dans un simple <pre>.        */
/* Rendu par éléments React (jamais dangerouslySetInnerHTML) : même du  */
/* texte hostile transcrit depuis une photo reste inerte, pas de risque */
/* d'injection.                                                          */
/* ------------------------------------------------------------------ */

function detecterFormat(texte) {
  const t = (texte || "").trim();
  if (!t) return "texte";
  try {
    JSON.parse(t);
    return "json";
  } catch {
    /* pas du JSON */
  }
  if (/^</.test(t) && /<\/[a-zA-Z][\w:-]*>\s*$/.test(t)) return "xml";
  if (/^#{1,4}\s|^[-*]\s|\*\*[^*]+\*\*|^\|.+\|.*\|/m.test(t)) return "markdown";
  return "texte";
}

function formatXml(xml) {
  let formatted = "";
  let pad = 0;
  xml
    .replace(/>\s*</g, ">\n<")
    .split("\n")
    .forEach((node) => {
      if (!node.trim()) return;
      let indentSuivant = 0;
      if (/^<\/\w/.test(node)) pad = Math.max(pad - 1, 0);
      else if (/^<\w[^>]*[^/]>/.test(node) && !/<\/\w[^>]*>\s*$/.test(node)) indentSuivant = 1;
      formatted += "  ".repeat(pad) + node.trim() + "\n";
      pad += indentSuivant;
    });
  return formatted.trim();
}

function renderInline(text, keyPrefix) {
  const parts = [];
  let rest = text;
  let key = 0;
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/;
  while (rest.length) {
    const m = rest.match(re);
    if (!m) {
      parts.push(rest);
      break;
    }
    if (m.index > 0) parts.push(rest.slice(0, m.index));
    const token = m[0];
    if (token.startsWith("**")) parts.push(<strong key={`${keyPrefix}-${key++}`}>{token.slice(2, -2)}</strong>);
    else parts.push(<em key={`${keyPrefix}-${key++}`}>{token.slice(1, -1)}</em>);
    rest = rest.slice(m.index + token.length);
  }
  return parts;
}

function MarkdownLite({ text }) {
  const { C } = useTheme();
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^#{1,4}\s/.test(line)) {
      const niveau = line.match(/^#+/)[0].length;
      const Titre = `h${Math.min(niveau + 3, 6)}`;
      blocks.push(
        <Titre key={i} style={{ fontFamily: uiFont, fontSize: 15 - niveau, fontWeight: 700, color: C.ink, margin: "10px 0 4px" }}>
          {renderInline(line.replace(/^#+\s*/, ""), i)}
        </Titre>
      );
      i++;
    } else if (/^\|.+\|/.test(line) && lines[i + 1] && /^\|[\s:-]+\|/.test(lines[i + 1])) {
      const entetes = line.split("|").map((c) => c.trim()).filter(Boolean);
      let j = i + 2;
      const lignes = [];
      while (j < lines.length && /^\|.+\|/.test(lines[j])) {
        lignes.push(lines[j].split("|").map((c) => c.trim()).filter(Boolean));
        j++;
      }
      blocks.push(
        <div key={i} style={{ overflowX: "auto", margin: "8px 0" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>
            <thead>
              <tr>{entetes.map((h, k) => <th key={k} style={{ textAlign: "left", padding: "4px 8px", borderBottom: `1px solid ${C.line}`, color: C.inkFaint }}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {lignes.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => <td key={ci} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.line}`, color: C.ink }}>{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = j;
    } else if (/^[-*]\s/.test(line)) {
      const items = [];
      const debut = i;
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, ""));
        i++;
      }
      blocks.push(
        <ul key={debut} style={{ margin: "4px 0", paddingLeft: 20 }}>
          {items.map((it, k) => <li key={k} style={{ fontSize: 13.5, color: C.ink, marginBottom: 2 }}>{renderInline(it, `${debut}-${k}`)}</li>)}
        </ul>
      );
    } else if (line.trim() === "") {
      i++;
    } else {
      blocks.push(
        <p key={i} style={{ fontSize: 13.5, color: C.ink, lineHeight: 1.55, margin: "4px 0" }}>{renderInline(line, i)}</p>
      );
      i++;
    }
  }
  return <div style={{ fontFamily: uiFont }}>{blocks}</div>;
}

function ResultatFormatte({ texte }) {
  const { C } = useTheme();
  const format = detecterFormat(texte);
  const preStyle = { margin: 0, fontFamily: "ui-monospace, Menlo, Consolas, monospace", fontSize: 12.5, color: C.ink, whiteSpace: "pre-wrap", wordBreak: "break-word" };

  if (format === "json") {
    let joli = texte;
    try {
      joli = JSON.stringify(JSON.parse(texte), null, 2);
    } catch {
      /* laissé tel quel si le JSON est tronqué (résultat coupé à 4000 caractères) */
    }
    return <pre style={preStyle}>{joli}</pre>;
  }
  if (format === "xml") return <pre style={preStyle}>{formatXml(texte)}</pre>;
  if (format === "markdown") return <MarkdownLite text={texte} />;
  return <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.ink, lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>{texte}</p>;
}

function TraitementDetail({ traitementId, onBack }) {
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

/* ------------------------------------------------------------------ */
/* Élèves — liste admin (comptes Google ayant déjà déposé une note ou    */
/* consulté le site connectés). Jamais visible des élèves eux-mêmes.     */
/* ------------------------------------------------------------------ */

function ElevesScreen() {
  const { C } = useTheme();
  const eleves = useApi("/api/eleves");
  const [togglingId, setTogglingId] = useState(null);

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

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Élèves</h1>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "4px 0 0" }}>
          Comptes Google connectés au moins une fois. L'assistant IA est désactivé par défaut pour chacun.
        </p>
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
              <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.email}</div>
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
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Paramétrage — choix du moteur IA (génération + assistant), admin      */
/* uniquement. Modifiable à chaud, pas besoin de redémarrer le service.  */
/* ------------------------------------------------------------------ */

const MOTEURS_IA = [
  { id: "ollama", nom: "Ollama (local, gratuit)", desc: "Tourne sur l'OptiPlex. Aucune donnée envoyée à l'extérieur." },
  { id: "claude", nom: "Claude (Anthropic)", desc: "Nécessite une clé API (console.anthropic.com). Le contenu des cours part chez Anthropic." },
  { id: "gemini", nom: "Gemini (Google)", desc: "Nécessite sa propre clé API (aistudio.google.com). Le contenu des cours part chez Google." },
];

function ParametresScreen() {
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

/* ------------------------------------------------------------------ */
/* Recherche (locale, sur les données déjà chargées)                    */
/* ------------------------------------------------------------------ */

function SearchScreen({ onOpenSubject, onOpenCours }) {
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

/* ------------------------------------------------------------------ */
/* Assistant IA                                                         */
/* ------------------------------------------------------------------ */

function AssistantScreen({ me, onRequireLogin }) {
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

/* ------------------------------------------------------------------ */
/* Connexion (Google) — sert uniquement à identifier qui dépose une     */
/* note ; le reste du site reste consultable sans compte.               */
/* ------------------------------------------------------------------ */

function LoginScreen({ onBack }) {
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

function AdminLoginScreen({ onBack, me }) {
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

function AdminControl({ me, onOpenLogin }) {
  const { C } = useTheme();
  if (me.loading) return <div style={{ width: 32, height: 32 }} />;

  if (!me.isAdmin) {
    return (
      <button
        onClick={onOpenLogin}
        title="Administration"
        aria-label="Connexion administrateur"
        style={{ border: `1px solid ${C.line}`, background: C.white, borderRadius: 999, width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: C.inkFaint, flexShrink: 0 }}
      >
        <ShieldCheck size={15} />
      </button>
    );
  }
  return (
    <button
      onClick={me.adminLogout}
      title="Déconnexion admin"
      aria-label="Déconnexion administrateur"
      style={{ border: `1px solid ${C.line}`, background: C.hauntSoft, borderRadius: 999, width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: C.haunt, flexShrink: 0 }}
    >
      <ShieldCheck size={15} />
    </button>
  );
}

function AuthControl({ me, onLogin }) {
  const { C } = useTheme();
  if (me.loading) return <div style={{ width: 32, height: 32 }} />;

  if (!me.eleve) {
    return (
      <button
        onClick={onLogin}
        style={{ display: "flex", alignItems: "center", gap: 6, border: `1px solid ${C.line}`, background: C.white, borderRadius: 999, padding: "7px 12px", cursor: "pointer", fontFamily: uiFont, fontSize: 12.5, fontWeight: 600, color: C.inkSoft }}
      >
        <LogIn size={13} /> Se connecter
      </button>
    );
  }

  const initial = (me.eleve.nom || "?").trim().charAt(0).toUpperCase();
  return (
    <button
      onClick={me.logout}
      title="Se déconnecter"
      style={{ display: "flex", alignItems: "center", gap: 7, border: `1px solid ${C.line}`, background: C.white, borderRadius: 999, padding: "4px 12px 4px 4px", cursor: "pointer", fontFamily: uiFont }}
    >
      {me.eleve.avatar_url ? (
        <img src={me.eleve.avatar_url} alt="" style={{ width: 24, height: 24, borderRadius: "50%" }} referrerPolicy="no-referrer" />
      ) : (
        <span style={{ width: 24, height: 24, borderRadius: "50%", background: C.haunt, color: C.onAccent, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>
          {initial}
        </span>
      )}
      <span style={{ fontSize: 12.5, color: C.inkSoft, fontWeight: 600, maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {me.eleve.nom.split(" ")[0]}
      </span>
      <LogOut size={12} color={C.inkFaint} />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Navigation — barre basse en mobile, colonne latérale en desktop      */
/* (voir index.css, règle @media (min-width: 860px))                   */
/* ------------------------------------------------------------------ */

function Nav({ tab, setTab, isAdmin }) {
  const { C } = useTheme();
  const items = [
    { id: "home", label: "Accueil", icon: Home },
    { id: "subjects", label: "Matières", icon: BookOpen },
    { id: "search", label: "Recherche", icon: SearchIcon },
    { id: "assistant", label: "Assistant", icon: MessageCircle },
  ];
  if (isAdmin) {
    items.push({ id: "traitements", label: "Traitements", icon: ListChecks });
    items.push({ id: "eleves", label: "Élèves", icon: Users });
    items.push({ id: "parametres", label: "Paramétrage", icon: Settings });
  }
  return (
    <nav className="gc-nav" style={{ borderTop: `1px solid ${C.line}`, borderRight: `1px solid ${C.line}`, background: C.paper }}>
      {items.map((it) => {
        const Icon = it.icon;
        const active = tab === it.id;
        return (
          <button
            key={it.id}
            onClick={() => setTab(it.id)}
            style={{ flex: 1, border: "none", background: "transparent", padding: "10px 0 12px", display: "flex", flexDirection: "column", alignItems: "center", gap: 3, cursor: "pointer", color: active ? C.haunt : C.inkFaint }}
          >
            <Icon size={19} strokeWidth={active ? 2.2 : 1.8} style={active ? glowText(C, C.haunt, 0.6) : {}} />
            <span style={{ fontFamily: uiFont, fontSize: 10.5, fontWeight: active ? 700 : 500 }}>{it.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/* Décor rétro (grille en perspective, discrète, mode sombre seulement) */
/* ------------------------------------------------------------------ */

function RetroGrid({ C }) {
  if (!C.neonGlow) return null;
  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        pointerEvents: "none",
        backgroundImage: `linear-gradient(${C.line}55 1px, transparent 1px), linear-gradient(90deg, ${C.line}55 1px, transparent 1px)`,
        backgroundSize: "36px 36px",
        maskImage: "linear-gradient(to bottom, black, transparent 75%)",
        WebkitMaskImage: "linear-gradient(to bottom, black, transparent 75%)",
        opacity: 0.7,
      }}
    />
  );
}

/* ------------------------------------------------------------------ */
/* App                                                                  */
/* ------------------------------------------------------------------ */

export default function App() {
  const [themeName, setThemeName] = useState("dark");
  const [tab, setTab] = useState("home");
  const [stack, setStack] = useState([]);
  const me = useMe();

  const C = themeName === "dark" ? DARK : LIGHT;
  const palette = themeName === "dark" ? DARK_PALETTE : LIGHT_PALETTE;
  const colorFor = makeColorFor(C, palette);
  const themeValue = { C, colorFor, themeName };

  function switchTab(t) {
    setStack([]);
    setTab(t);
  }

  // Si l'admin se déconnecte pendant qu'il consulte un onglet admin, cet
  // onglet disparaît de la nav (voir Nav) : retomber sur l'accueil plutôt
  // que de laisser un onglet actif introuvable et un écran vide.
  useEffect(() => {
    if ((tab === "traitements" || tab === "eleves" || tab === "parametres") && !me.isAdmin) setTab("home");
  }, [tab, me.isAdmin]);
  function push(screen, params) {
    setStack((s) => [...s, { screen, params }]);
  }
  function pop() {
    setStack((s) => s.slice(0, -1));
  }
  function openSubject(id, nom) {
    push("subject", { id, nom });
  }
  function openCours(id) {
    push("cours", { id });
  }
  function requireLogin() {
    push("login");
  }
  function openTraitement(id) {
    push("traitement", { id });
  }
  function openAdminLogin() {
    push("admin-login");
  }

  const isAdmin = me.isAdmin;
  const top = stack[stack.length - 1];

  let content;
  if (top?.screen === "subject") {
    content = <SubjectDetail subjectId={top.params.id} subjectName={top.params.nom} onBack={pop} onOpenCours={openCours} />;
  } else if (top?.screen === "cours") {
    content = <CoursDetail coursId={top.params.id} onBack={pop} me={me} onRequireLogin={requireLogin} />;
  } else if (top?.screen === "login") {
    content = <LoginScreen onBack={pop} />;
  } else if (top?.screen === "admin-login") {
    content = <AdminLoginScreen onBack={pop} me={me} />;
  } else if (top?.screen === "traitement") {
    content = <TraitementDetail traitementId={top.params.id} onBack={pop} />;
  } else if (tab === "home") {
    content = <HomeScreen onOpenSubject={openSubject} onOpenCours={openCours} />;
  } else if (tab === "subjects") {
    content = <SubjectsScreen onOpenSubject={openSubject} />;
  } else if (tab === "search") {
    content = <SearchScreen onOpenSubject={openSubject} onOpenCours={openCours} />;
  } else if (tab === "assistant") {
    content = <AssistantScreen me={me} onRequireLogin={requireLogin} />;
  } else if (tab === "traitements" && isAdmin) {
    content = <TraitementsScreen onOpenTraitement={openTraitement} />;
  } else if (tab === "eleves" && isAdmin) {
    content = <ElevesScreen />;
  } else if (tab === "parametres" && isAdmin) {
    content = <ParametresScreen />;
  }

  return (
    <ThemeContext.Provider value={themeValue}>
      <div style={{ position: "relative", minHeight: "100vh", background: C.paperDim, fontFamily: uiFont, overflow: "hidden" }}>
        <RetroGrid C={C} />
        <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", minHeight: "100vh" }}>
          <div className="flex items-center justify-between" style={{ padding: "14px 20px", borderBottom: `1px solid ${C.line}`, background: C.paper }}>
            <div className="flex items-center gap-2">
              <Ghost size={16} color={C.haunt} style={glowText(C, C.haunt)} />
              <span style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 14, color: C.haunt, ...glowText(C, C.haunt, 0.7) }}>
                Ghost Cards
              </span>
            </div>
            <div className="flex items-center gap-2">
              <AuthControl me={me} onLogin={requireLogin} />
              <AdminControl me={me} onOpenLogin={openAdminLogin} />
              <button
                onClick={() => setThemeName((t) => (t === "dark" ? "light" : "dark"))}
                aria-label={themeName === "dark" ? "Passer en thème clair" : "Passer en thème sombre néon"}
                style={{ border: `1px solid ${C.line}`, background: C.white, borderRadius: 999, width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: C.inkSoft, flexShrink: 0 }}
              >
                {themeName === "dark" ? <Sun size={15} /> : <Moon size={15} />}
              </button>
            </div>
          </div>

          <div className="gc-shell">
            <Nav tab={tab} setTab={switchTab} isAdmin={isAdmin} />
            <main className="gc-main">
              <div className="gc-content">{content}</div>
            </main>
          </div>
        </div>
      </div>
    </ThemeContext.Provider>
  );
}
