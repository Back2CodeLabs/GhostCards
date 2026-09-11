import html2canvas from "html2canvas";

/* ------------------------------------------------------------------ */
/* Effet "disparition Thanos" (Avengers: Infinity War) sur un élément    */
/* du DOM — adapté du CodePen de Szymon (scorpsy93/pen/qwzELx) : capture */
/* l'élément en image (html2canvas), la décompose en dizaines de        */
/* fragments de pixels qui s'envolent et s'estompent en éventail         */
/* (gauche → droite, comme la poussière originale), plutôt qu'un simple  */
/* fondu uniforme.                                                       */
/*                                                                       */
/* Contrairement au CodePen d'origine (qui insère les fragments en       */
/* frère du nœud d'origine, dans le DOM géré par la page statique), on   */
/* les ajoute ici dans un calque à part collé sur `document.body`,       */
/* entièrement en dehors de l'arbre que React gère — pour ne jamais      */
/* perturber sa réconciliation quand le composant qui a déclenché        */
/* l'effet se démonte/re-rend pendant l'animation.                       */
/* ------------------------------------------------------------------ */

const NUM_FRAMES = 40;
const REPETITION_COUNT = 2; // chaque pixel est assigné à 2 fragments
const STAGGER_S = 1.35; // étalement du déclenchement entre le 1er et le dernier fragment
const TRANSITION_S = 1; // durée d'envol/fondu de chaque fragment une fois déclenché
const TIMEOUT_MS = 4000; // si html2canvas ne répond pas (mobile sous-puissant...), on abandonne l'effet plutôt que de bloquer indéfiniment le passage au mode examen

// Firefox (constaté sur Android) rend `getImageData` vide/transparent si
// le canvas produit par html2canvas n'a jamais été posé dans le DOM —
// bug connu d'html2canvas sur Firefox (niklasvh/html2canvas#2254), Chrome
// n'a pas ce problème. On le colle donc brièvement hors champ (pas en
// `display:none`, qui déclenche le même bug que ne pas l'ajouter du tout)
// le temps de lire ses pixels, puis on le retire aussitôt.
function lireImageData(sourceCanvas) {
  const { width, height } = sourceCanvas;
  sourceCanvas.style.cssText = "position:fixed; left:-99999px; top:0; opacity:0; pointer-events:none;";
  document.body.appendChild(sourceCanvas);
  try {
    return sourceCanvas.getContext("2d").getImageData(0, 0, width, height);
  } finally {
    sourceCanvas.remove();
  }
}

// Découpe le canvas source en `count` fragments : chaque pixel est
// assigné aléatoirement à l'un d'eux, mais avec un biais sur sa position
// x — les pixels de gauche atterrissent plutôt dans les premiers
// fragments (déclenchés tôt), ceux de droite dans les derniers
// (déclenchés tard), d'où le balayage gauche → droite façon Thanos.
function decouperEnFragments(sourceCanvas, count) {
  const { width, height } = sourceCanvas;
  const ctx = sourceCanvas.getContext("2d");
  const original = lireImageData(sourceCanvas);
  const imageDatas = Array.from({ length: count }, () => ctx.createImageData(width, height));

  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      for (let r = 0; r < REPETITION_COUNT; r++) {
        const indexFragment = Math.min(
          count - 1,
          Math.floor((count * (Math.random() + (2 * x) / width)) / 3),
        );
        const indexPixel = (y * width + x) * 4;
        for (let offset = 0; offset < 4; offset++) {
          imageDatas[indexFragment].data[indexPixel + offset] = original.data[indexPixel + offset];
        }
      }
    }
  }

  return imageDatas.map((data) => {
    const c = document.createElement("canvas");
    c.width = width;
    c.height = height;
    c.getContext("2d").putImageData(data, 0, 0);
    return c;
  });
}

/**
 * Déclenche l'effet sur `element` (masqué pendant l'opération, à démonter
 * par l'appelant une fois `onDone` appelé). N'échoue jamais bruyamment :
 * si html2canvas plante (élément trop complexe, police externe non
 * chargée...), on retombe silencieusement sur `onDone` immédiat plutôt que
 * de bloquer la suite (le mode examen doit s'ouvrir dans tous les cas).
 *
 * `backgroundColor` : la couleur de fond RÉELLE derrière `element` (celle
 * de l'écran, pas de l'élément lui-même) — la plupart des espaces entre
 * les blocs de contenu sont transparents et laissent voir le fond de la
 * page porté par un ancêtre bien plus haut dans l'arbre (voir App.jsx),
 * jamais capturé sinon : sans cette couleur, html2canvas rendrait ces
 * zones transparentes et les fragments donneraient un effet troué plutôt
 * qu'un vrai bloc de contenu qui se désintègre.
 */
export async function disintegrate(element, { onDone, backgroundColor = null } = {}) {
  const termine = () => onDone?.();
  let sourceCanvas;
  try {
    const rect = element.getBoundingClientRect();
    sourceCanvas = await Promise.race([
      html2canvas(element, { backgroundColor, scale: window.devicePixelRatio || 1 }),
      new Promise((_, reject) => setTimeout(() => reject(new Error("html2canvas timeout")), TIMEOUT_MS)),
    ]);

    const overlay = document.createElement("div");
    overlay.style.cssText = `position:fixed; left:${rect.left}px; top:${rect.top}px; width:${rect.width}px; height:${rect.height}px; pointer-events:none; z-index:9999; overflow:visible;`;
    document.body.appendChild(overlay);

    const fragments = decouperEnFragments(sourceCanvas, NUM_FRAMES);
    fragments.forEach((fragment, i) => {
      fragment.style.cssText = `position:absolute; left:0; top:0; width:100%; height:100%; opacity:1; transform:translate(0,0) rotate(0deg); transition: transform ${TRANSITION_S}s ease-out, opacity ${TRANSITION_S}s ease-out; transition-delay:${(STAGGER_S * i) / fragments.length}s;`;
      overlay.appendChild(fragment);
    });

    element.style.visibility = "hidden";

    // Force le reflow avant de fixer l'état final : sans ça le navigateur
    // fusionne les deux changements de style et la transition ne se joue
    // pas (même piège que dans le CodePen d'origine).
    void overlay.offsetLeft;

    fragments.forEach((fragment) => {
      const angle = 2 * Math.PI * (Math.random() - 0.5);
      const dx = 70 * Math.cos(angle);
      const dy = 40 * Math.sin(angle) - 25; // léger biais vers le haut : la poussière s'envole plus qu'elle ne tombe
      const rotation = 20 * (Math.random() - 0.5);
      fragment.style.transform = `translate(${dx}px, ${dy}px) rotate(${rotation}deg)`;
      fragment.style.opacity = "0";
    });

    setTimeout(() => {
      overlay.remove();
      // Remet `element` visible avant de rendre la main : React réutilise
      // parfois le même nœud DOM pour le contenu suivant (deux branches
      // `<div>` au même endroit dans un ternaire, sans clé distincte) —
      // sans ça, le `visibility: hidden` posé plus haut resterait collé
      // sur ce qui s'affiche ensuite à cet endroit.
      element.style.visibility = "";
      termine();
    }, (STAGGER_S + TRANSITION_S) * 1000);
  } catch (e) {
    console.warn("Effet de désintégration indisponible, on continue sans.", e);
    termine();
  }
}
