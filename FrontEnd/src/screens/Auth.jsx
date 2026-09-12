import { useState, useRef } from "react";
import { Ghost, Upload, ShieldCheck } from "lucide-react";
import { useTheme, uiFont, glowText } from "../theme";
import { messageErreur } from "../api";
import { ScreenHeader } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Connexion — pairage avec le compte Pronote personnel de l'élève :     */
/* vérifie l'établissement et la classe, et sert de source de synchro   */
/* pour son propre groupe (voir BackEnd/app/main.py::pairer_eleve_       */
/* pronote). Verrouille tout le site : plus de consultation sans compte.*/
/* ------------------------------------------------------------------ */

export function LoginScreen({ me }) {
  const { C } = useTheme();
  const [fichier, setFichier] = useState(null);
  const [pin, setPin] = useState("");
  const [consentement, setConsentement] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  async function submit() {
    if (!fichier || pin.length !== 4 || !consentement || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await me.pairerPronote(fichier, pin, consentement);
    } catch (e) {
      setError(messageErreur(e, "Pairage Pronote impossible."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <ScreenHeader title="Connexion" />
      <div style={{ padding: "40px 28px", textAlign: "center" }}>
        <Ghost size={38} color={C.haunt} strokeWidth={1.4} style={{ marginBottom: 16, ...glowText(C, C.haunt) }} />
        <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 20, color: C.ink, margin: "0 0 10px" }}>
          Rejoins Ghost School avec Pronote
        </h2>
        <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.inkSoft, lineHeight: 1.6, margin: "0 0 20px", maxWidth: 360, marginLeft: "auto", marginRight: "auto" }}>
          Ghost School est réservé à ta classe. Sur Pronote (ordinateur ou
          téléphone), va dans <b>Mon compte → Configuration de mon compte →
          Connexion via smartphone</b> : ça affiche un QR code et un code PIN
          à 4 chiffres. Prends une capture d'écran du QR code et dépose-la
          ici avec le PIN — une seule fois, ensuite tu resteras connecté sur
          cet appareil.
        </p>

        <div
          onClick={() => fileInputRef.current?.click()}
          style={{ cursor: "pointer", background: C.paperDim, border: `1px dashed ${C.line}`, borderRadius: 12, padding: "22px 16px", marginBottom: 14, maxWidth: 340, marginLeft: "auto", marginRight: "auto" }}
        >
          <Upload size={22} color={C.inkSoft} style={{ marginBottom: 6 }} />
          <p style={{ fontFamily: uiFont, fontSize: 13, color: C.ink, margin: 0, fontWeight: 600 }}>
            {fichier ? fichier.name : "Choisir la capture du QR code"}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={(e) => setFichier(e.target.files?.[0] || null)}
            style={{ display: "none" }}
          />
        </div>

        <input
          type="text"
          inputMode="numeric"
          maxLength={4}
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Code PIN (4 chiffres)"
          style={{ width: "100%", maxWidth: 260, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "10px 14px", fontFamily: uiFont, fontSize: 16, letterSpacing: 4, color: C.ink, outline: "none", textAlign: "center" }}
        />

        <div style={{ textAlign: "left", background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 12, padding: "14px 16px", marginTop: 16, maxWidth: 360, marginLeft: "auto", marginRight: "auto" }}>
          <p style={{ fontFamily: uiFont, fontSize: 12, fontWeight: 700, color: C.ink, margin: "0 0 8px" }}>
            Ce que Ghost School récupère de ton compte Pronote
          </p>
          <ul style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, lineHeight: 1.6, margin: "0 0 10px", paddingLeft: 18 }}>
            <li>Emploi du temps (matière, horaire, salle, groupe, prof, mémo) et contenu des cours — <b>partagé avec la classe</b>.</li>
            <li>Devoirs et documents attachés — <b>partagé avec la classe</b>.</li>
            <li>Tes notes et moyennes — <b>gardées privées</b>, jamais visibles par un camarade.</li>
            <li>Ton nom et ta classe, pour vérifier que tu es bien en 2F.</li>
          </ul>
          <p style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkFaint, margin: "0 0 10px" }}>
            Rien d'autre : ni absences, ni retards, ni sanctions, ni actualités de l'établissement.
            Le jeton de connexion est chiffré et sert uniquement à synchroniser automatiquement,
            sans que tu aies à te reconnecter.
          </p>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={consentement}
              onChange={(e) => setConsentement(e.target.checked)}
              style={{ marginTop: 2, accentColor: C.haunt }}
            />
            <span style={{ fontFamily: uiFont, fontSize: 12.5, color: C.ink }}>
              J'ai lu et j'accepte que Ghost School récupère ces informations depuis mon compte Pronote.
            </span>
          </label>
        </div>

        {error && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "10px 0 0", maxWidth: 340, marginLeft: "auto", marginRight: "auto" }}>{error}</p>}

        <div>
          <button
            onClick={submit}
            disabled={submitting || !fichier || pin.length !== 4 || !consentement}
            style={{ marginTop: 18, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "11px 24px", fontFamily: uiFont, fontSize: 14, fontWeight: 700, cursor: fichier && pin.length === 4 && consentement ? "pointer" : "default", opacity: submitting ? 0.7 : 1 }}
          >
            {submitting ? "Connexion…" : "Se connecter"}
          </button>
        </div>

        <p style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkFaint, marginTop: 22 }}>
          Le QR code n'est valable que quelques minutes — régénère-le sur Pronote s'il a expiré.
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Connexion admin (Cédric) — mot de passe séparé des comptes élèves,   */
/* un élève ne peut jamais devenir admin par ce biais.                  */
/* ------------------------------------------------------------------ */

export function AdminLoginScreen({ onBack, me }) {
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
      setError(messageErreur(e, "Connexion admin impossible."));
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
          Réservé au Maître Fantôme, gardien de Ghost School, pour voir et relancer les traitements OCR en arrière-plan.
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
