import { useState, useCallback } from "react";
import Cropper from "react-easy-crop";
import { Check, X } from "lucide-react";
import { useTheme, uiFont } from "../theme";

/* ------------------------------------------------------------------ */
/* Recadrage de la photo du QR code avant envoi (écran de connexion,    */
/* voir Auth.jsx) : les vraies photos prises au téléphone contiennent   */
/* souvent l'écran entier autour du QR (reflets, bords, autre contenu   */
/* Pronote) — ne garder que le QR limite les échecs de détection côté   */
/* serveur (voir _decoder_qr_image, BackEnd/app/main.py) en plus de      */
/* réduire ce qui est envoyé.                                           */
/* ------------------------------------------------------------------ */

// Découpe `imageSrc` selon la zone `cropPixels` (repère pixel, fourni par
// react-easy-crop via onCropComplete) et renvoie un Blob JPEG — passe par
// un <canvas> hors-DOM, seule façon fiable de rogner une image côté client.
function recadrerImage(imageSrc, cropPixels) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = cropPixels.width;
      canvas.height = cropPixels.height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(
        image,
        cropPixels.x, cropPixels.y, cropPixels.width, cropPixels.height,
        0, 0, cropPixels.width, cropPixels.height
      );
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Recadrage impossible."))), "image/jpeg", 0.92);
    };
    image.onerror = () => reject(new Error("Image illisible."));
    image.src = imageSrc;
  });
}

export function CropQrCode({ imageSrc, onValider, onAnnuler }) {
  const { C } = useTheme();
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [cropPixels, setCropPixels] = useState(null);
  const [busy, setBusy] = useState(false);

  const onCropComplete = useCallback((_zone, zonePixels) => setCropPixels(zonePixels), []);

  async function valider() {
    if (!cropPixels || busy) return;
    setBusy(true);
    try {
      const blob = await recadrerImage(imageSrc, cropPixels);
      onValider(new File([blob], "qr_recadre.jpg", { type: "image/jpeg" }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 340, marginLeft: "auto", marginRight: "auto" }}>
      <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, margin: "0 0 8px" }}>
        Cadre le QR code, sans le reste de l'écran autour.
      </p>
      <div style={{ position: "relative", width: "100%", height: 280, background: C.paperDim, borderRadius: 12, overflow: "hidden" }}>
        <Cropper
          image={imageSrc}
          crop={crop}
          zoom={zoom}
          aspect={1}
          cropShape="rect"
          showGrid={false}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onCropComplete={onCropComplete}
        />
      </div>
      <input
        type="range"
        min={1}
        max={4}
        step={0.05}
        value={zoom}
        onChange={(e) => setZoom(Number(e.target.value))}
        aria-label="Zoom"
        style={{ width: "100%", marginTop: 10, accentColor: C.haunt }}
      />
      <div className="flex items-center justify-center gap-3" style={{ marginTop: 12 }}>
        <button
          onClick={onAnnuler}
          disabled={busy}
          style={{ display: "flex", alignItems: "center", gap: 6, background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "9px 16px", fontFamily: uiFont, fontSize: 13, fontWeight: 600, color: C.inkSoft, cursor: "pointer" }}
        >
          <X size={14} /> Changer de photo
        </button>
        <button
          onClick={valider}
          disabled={busy}
          style={{ display: "flex", alignItems: "center", gap: 6, background: C.haunt, border: "none", borderRadius: 10, padding: "9px 18px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, color: C.onAccent, cursor: "pointer", opacity: busy ? 0.7 : 1 }}
        >
          <Check size={14} /> {busy ? "Recadrage…" : "Valider le cadrage"}
        </button>
      </div>
    </div>
  );
}
