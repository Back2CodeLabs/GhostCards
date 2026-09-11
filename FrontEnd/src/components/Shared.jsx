import { ArrowLeft, Ghost, RefreshCw, WifiOff, Sparkles, FileText, TriangleAlert, ScrollText, Clock, ShieldCheck, MessageSquare, MapPin, Ban } from "lucide-react";
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
        Impossible de joindre le serveur Ghost School
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

// Petits indicateurs (documents/notes/génération IA) sur une ligne de la
// liste des cours (Accueil, Matières) — un seul coup d'œil sans avoir à
// ouvrir le cours. Un compte à 0 ne s'affiche pas : pas la peine d'occuper
// de la place pour dire qu'il n'y a rien.
export function IndicateursCours({ c }) {
  const { C } = useTheme();
  const items = [];
  if (c.annule) items.push({ key: "annule", Icon: Ban, label: c.statut || "Annulé", title: c.statut || "Cours annulé", color: C.brick });
  if (c.devoir_surveille) items.push({ key: "ds", Icon: TriangleAlert, label: "Devoir surveillé", title: "Devoir surveillé", color: C.brick });
  if (c.salle) items.push({ key: "salle", Icon: MapPin, label: c.salle, title: `Salle ${c.salle}` });
  if (c.nb_documents > 0) items.push({ key: "documents", Icon: FileText, label: c.nb_documents, title: `${c.nb_documents} document(s)` });
  if (c.nb_notes > 0) items.push({ key: "notes", Icon: MessageSquare, label: c.nb_notes, title: `${c.nb_notes} note(s) d'élève` });
  if (c.ia_statut === "pret") items.push({ key: "ia", Icon: Sparkles, label: null, title: "Résumé/flashcards/quiz générés" });
  if (items.length === 0) return null;
  return (
    <div className="flex items-center gap-2" style={{ marginTop: 4, flexWrap: "wrap" }}>
      {items.map(({ key, Icon, label, title, color }) => (
        <span key={key} title={title} style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11, color: color || C.inkFaint }}>
          <Icon size={12} />
          {label != null && label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Points de vigilance connus sur la génération IA / transcription OCR — */
/* liste à COMPLÉTER à chaque fois qu'un nouveau cas de mauvaise         */
/* interprétation est identifié (voir Tests/), pour que l'avertissement  */
/* affiché aux élèves/à l'admin reste à jour plutôt qu'une formule vague.*/
/* ------------------------------------------------------------------ */

export const LIMITES_IA_CONNUES = [
  "Notations mathématiques (racines, exposants, fractions, symboles ∈/∉) : risque d'erreur plus élevé, en particulier avec un moteur OCR généraliste (PaddleOCR) qui ne comprend pas le sens mathématique du texte.",
  "Schémas et diagrammes (ensembles emboîtés, figures géométriques) : seul le texte isolé (lettres, légendes) est récupéré — les relations visuelles entre les éléments (inclusion, position) sont perdues.",
];

export function AvertissementIA({ intro }) {
  const { C } = useTheme();
  return (
    <div style={{ background: C.brickSoft, borderRadius: 10, padding: "11px 14px", display: "flex", gap: 10, alignItems: "flex-start" }}>
      <TriangleAlert size={16} color={C.brick} style={{ flexShrink: 0, marginTop: 1 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.ink, lineHeight: 1.5, margin: 0 }}>{intro}</p>
        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
          {LIMITES_IA_CONNUES.map((limite, i) => (
            <li key={i} style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkSoft, lineHeight: 1.45, marginBottom: 3 }}>{limite}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sous-menu partagé par les écrans admin "Traitements" et               */
/* "Paramétrage" — chacun y répartit son contenu en 3 catégories         */
/* (Pronote, Génération IA, OCR), au lieu d'une seule liste/page mêlant   */
/* tout. Mêmes clés dans les deux écrans pour rester cohérent.           */
/* ------------------------------------------------------------------ */

export const SOUS_MENUS = [
  { key: "pronote", label: "Pronote", Icon: RefreshCw },
  { key: "ia", label: "Génération IA", Icon: Sparkles },
  { key: "ocr", label: "OCR", Icon: FileText },
];

// Onglet "Prompts" : uniquement pertinent pour Paramétrage (rien à filtrer
// côté Traitements) — passé en `extra` plutôt qu'ajouté à SOUS_MENUS pour
// ne pas faire apparaître un onglet vide dans l'écran Traitements, qui
// partage le même composant/la même liste de base.
export const SOUS_MENU_PROMPTS = { key: "prompts", label: "Prompts", Icon: ScrollText };

// Idem : la config du modèle de vérification (Services/ia_verification.py)
// n'a rien à faire dans l'écran Traitements.
export const SOUS_MENU_VERIFICATION = { key: "verification", label: "Vérification", Icon: ShieldCheck };

// Idem, côté Traitements cette fois : les demandes de régénération en
// attente de validation admin n'ont pas leur place dans Pronote/Génération
// IA/OCR (ce ne sont pas encore des traitements exécutés).
export const SOUS_MENU_EN_ATTENTE = { key: "demandes", label: "En attente", Icon: Clock };

export function SousMenu({ actif, onChange, extra }) {
  const { C } = useTheme();
  const menus = extra ? [...SOUS_MENUS, ...extra] : SOUS_MENUS;
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "0 20px 16px" }}>
      {menus.map((m) => {
        const active = actif === m.key;
        return (
          <button
            key={m.key}
            onClick={() => onChange(m.key)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: active ? C.hauntSoft : C.white,
              border: `1px solid ${active ? C.haunt : C.line}`,
              color: active ? C.haunt : C.inkSoft,
              borderRadius: 999, padding: "7px 14px",
              fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
            }}
          >
            <m.Icon size={13} /> {m.label}
          </button>
        );
      })}
    </div>
  );
}
