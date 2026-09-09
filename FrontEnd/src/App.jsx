import React, { useState, useEffect } from "react";
import "./index.css";
import { Ghost, Moon, Sun } from "lucide-react";

import { ThemeContext, uiFont, glowText, makeColorFor, LIGHT, DARK, LIGHT_PALETTE, DARK_PALETTE } from "./theme";
import { useMe } from "./api";

import { Nav, AuthControl, AdminControl, RetroGrid } from "./components/Nav";

import { HomeScreen } from "./screens/HomeScreen";
import { SubjectsScreen, SubjectDetail } from "./screens/SubjectsScreen";
import { CoursDetail } from "./screens/CoursDetail";
import { TraitementsScreen, TraitementDetail } from "./screens/TraitementsScreen";
import { ElevesScreen } from "./screens/ElevesScreen";
import { ParametresScreen } from "./screens/ParametresScreen";
import { SearchScreen } from "./screens/SearchScreen";
import { AssistantScreen } from "./screens/AssistantScreen";
import { LoginScreen, AdminLoginScreen } from "./screens/Auth";

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
              <Ghost className="gc-brand-icon" size={16} color={C.haunt} style={glowText(C, C.haunt)} />
              <span className="gc-brand-text" style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 14, color: C.haunt, ...glowText(C, C.haunt, 0.7) }}>
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
