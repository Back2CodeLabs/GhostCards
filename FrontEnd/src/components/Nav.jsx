import { Home, BookOpen, Search as SearchIcon, MessageCircle, ListChecks, Users, Settings, ShieldCheck, LogIn, LogOut } from "lucide-react";
import { useTheme, uiFont, glowText } from "../theme";

/* ------------------------------------------------------------------ */
/* Connexion admin (bouton bouclier dans l'en-tête)                     */
/* ------------------------------------------------------------------ */

export function AdminControl({ me, onOpenLogin }) {
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

/* ------------------------------------------------------------------ */
/* Connexion élève (badge compte / bouton "Se connecter" dans l'en-tête) */
/* ------------------------------------------------------------------ */

export function AuthControl({ me, onLogin }) {
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

export function Nav({ tab, setTab, isAdmin }) {
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

export function RetroGrid({ C }) {
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
