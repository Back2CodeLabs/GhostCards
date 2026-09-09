import { useContext, createContext } from "react";

/* ------------------------------------------------------------------ */
/* Thèmes — clair et sombre (néon, rétro 80s, avec parcimonie)          */
/* ------------------------------------------------------------------ */

export const uiFont = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

// Palette "claire" — même identité rétro 80s que le mode sombre (même
// famille de teintes violet/magenta, même police de titres bien trapue),
// juste rejouée en plein jour : fond très clair à peine teinté de lavande
// au lieu du violet profond, couleurs d'accent assombries pour rester
// lisibles sur fond clair (le magenta/turquoise/corail du mode sombre sont
// calibrés pour un fond noir et perdraient tout contraste ici tels quels).
export const LIGHT = {
  name: "light",
  paper: "#FCF9FF",
  paperDim: "#F1E8FB",
  ink: "#2B1C42",
  inkSoft: "#6A5A8A",
  inkFaint: "#A093B8",
  line: "#E6DAF5",
  white: "#FFFFFF", // surfaces élevées (cartes, boutons secondaires, champs)
  onAccent: "#FFFFFF", // texte/icônes posés sur un fond de couleur (haunt, etc.)
  haunt: "#AE1C93",
  hauntSoft: "#F7DFF1",
  spectral: "#0E8C74",
  spectralSoft: "#DCF3EC",
  brick: "#CB4A22",
  brickSoft: "#FAE2D6",
  fontHeading: "'Arial Black', 'Helvetica Neue', Arial, sans-serif",
  headingLetterSpacing: "0.3px",
  neonGlow: false,
};

// Palette "sombre" : même rôle sémantique que chaque couleur claire
// (haunt = accent principal, spectral = succès/maîtrisé, brick = alerte),
// mais rendue en néon sur fond très sombre plutôt qu'en pastel — l'effet
// rétro 80s reste ponctuel (bordures, puces, icônes actives), pas des
// aplats entiers, pour que ça reste lisible au quotidien.
export const DARK = {
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

export const LIGHT_PALETTE = [LIGHT.haunt, LIGHT.spectral, "#B4860F", "#2E6FA3", "#5C8A2E", LIGHT.brick];
export const DARK_PALETTE = [DARK.haunt, DARK.spectral, "#FFD23E", "#3EC1FF", "#9DFF3E", DARK.brick];

export function makeColorFor(C, palette) {
  const soft = { [C.haunt]: C.hauntSoft, [C.spectral]: C.spectralSoft, [C.brick]: C.brickSoft };
  return function colorFor(id) {
    const c = palette[id % palette.length];
    return { color: c, soft: soft[c] || C.paperDim };
  };
}

export const ThemeContext = createContext(null);
export function useTheme() {
  return useContext(ThemeContext);
}

export function glowText(C, color, strength = 1) {
  if (!C.neonGlow) return {};
  return { textShadow: `0 0 ${6 * strength}px ${color}, 0 0 ${16 * strength}px ${color}66` };
}
