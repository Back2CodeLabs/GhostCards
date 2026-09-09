import { useTheme, uiFont } from "../theme";

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

export function ResultatFormatte({ texte }) {
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
