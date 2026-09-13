import { Ghost, RefreshCw, Sparkles, Lock } from "lucide-react";
import { useTheme, uiFont, glowText } from "../theme";

/* ------------------------------------------------------------------ */
/* Première page vue par un visiteur non connecté : une vraie page      */
/* d'accueil (pitch + bouton "Se connecter"), plutôt que de plonger     */
/* directement dans le formulaire de pairage Pronote — celui-ci reste   */
/* accessible en un clic (bouton "Se connecter" déjà présent dans       */
/* l'en-tête, voir AuthControl) ou via le bouton ci-dessous.            */
/* ------------------------------------------------------------------ */

const ATOUTS = [
  {
    Icon: RefreshCw,
    titre: "Toujours à jour",
    texte: "Cours, devoirs et documents synchronisés automatiquement depuis Pronote.",
  },
  {
    Icon: Sparkles,
    titre: "Révise plus vite",
    texte: "Résumés, flashcards et quiz générés par IA à partir de chaque cours.",
  },
  {
    Icon: Lock,
    titre: "Tes notes restent à toi",
    texte: "Cours et devoirs sont partagés avec la classe ; tes notes, elles, ne le sont jamais.",
  },
];

export function LandingScreen({ onLogin }) {
  const { C } = useTheme();
  return (
    <div style={{ padding: "48px 28px 40px", textAlign: "center" }}>
      <Ghost size={44} color={C.haunt} strokeWidth={1.4} style={{ marginBottom: 18, ...glowText(C, C.haunt) }} />
      <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: "0 0 10px" }}>
        Ghost School
      </h1>
      <p style={{ fontFamily: uiFont, fontSize: 14, color: C.inkSoft, lineHeight: 1.6, margin: "0 0 32px", maxWidth: 360, marginLeft: "auto", marginRight: "auto" }}>
        La plateforme de révision de la classe, connectée à Pronote.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 380, marginLeft: "auto", marginRight: "auto", marginBottom: 34 }}>
        {ATOUTS.map(({ Icon, titre, texte }) => (
          <div key={titre} style={{ display: "flex", alignItems: "flex-start", gap: 12, textAlign: "left", background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 12, padding: "14px 16px" }}>
            <Icon size={18} color={C.haunt} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{titre}</div>
              <div style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft, marginTop: 2, lineHeight: 1.5 }}>{texte}</div>
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={onLogin}
        style={{ background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "12px 28px", fontFamily: uiFont, fontSize: 14.5, fontWeight: 700, cursor: "pointer" }}
      >
        Se connecter avec Pronote
      </button>

      <p style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkFaint, marginTop: 18, maxWidth: 320, marginLeft: "auto", marginRight: "auto" }}>
        Réservé aux élèves de la classe — la connexion vérifie ton compte Pronote avant de te donner accès.
      </p>
    </div>
  );
}
