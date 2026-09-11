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

// Une matière par teinte, générée à la volée plutôt que piochée dans une
// petite palette fixe : avec seulement 6 couleurs fixes, la 7e matière
// répétait la couleur de la 1re (id % 6), deux matières sans rapport
// devenant indiscernables au premier coup d'œil dans "Mes matières"/le
// bandeau de couleur des cartes. L'angle d'or (~137.5°) espace les teintes
// de façon à peu près uniforme sur le cercle chromatique même pour des id
// consécutifs, contrairement à un simple pas fixe (360°/n) qui look "arc-
// en-ciel" ordonné. Saturation/luminosité fixes par thème (calibrées pour
// rester lisibles : sombre = néon vif sur fond noir, clair = teinte foncée
// sur fond clair), seule la teinte varie par matière.
const GOLDEN_ANGLE = 137.508;

export function makeColorFor(C) {
  const isDark = C.name === "dark";
  const s = isDark ? 85 : 60;
  const l = isDark ? 65 : 35;
  return function colorFor(id) {
    const hue = ((id * GOLDEN_ANGLE) % 360 + 360) % 360;
    return {
      color: `hsl(${hue.toFixed(1)}deg ${s}% ${l}%)`,
      soft: `hsl(${hue.toFixed(1)}deg ${s}% ${l}% / ${isDark ? 0.18 : 0.12})`,
    };
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
