import { useState, useEffect } from "react";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { API_BASE, useApi, messageErreur } from "../api";
import { Loading, ApiError, SousMenu, SOUS_MENU_PROMPTS, SOUS_MENU_VERIFICATION } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Paramétrage — 3 sous-menus (Pronote / Génération IA / OCR), admin     */
/* uniquement. Modifiable à chaud, pas besoin de redémarrer le service.  */
/* ------------------------------------------------------------------ */

const MOTEURS_IA = [
  { id: "ollama", nom: "Ollama (local, gratuit)", desc: "URL et modèle configurables ci-dessous. Aucune donnée envoyée à l'extérieur tant que le serveur reste sur ton réseau." },
  { id: "claude", nom: "Claude (Anthropic)", desc: "Nécessite une clé API (console.anthropic.com). Le contenu des cours part chez Anthropic." },
  { id: "gemini", nom: "Gemini (Google)", desc: "Nécessite sa propre clé API (aistudio.google.com). Le contenu des cours part chez Google." },
];

const MOTEURS_OCR = [
  { id: "paddleocr", nom: "PaddleOCR (local, gratuit)", desc: "Tourne sur le serveur, aucune donnée envoyée à l'extérieur. Nécessite un venv Python ≤3.13 (voir HANDOFF.md)." },
  { id: "claude", nom: "Claude (Anthropic)", desc: "Meilleur sur l'écriture manuscrite réelle, mais coûte du crédit API par image transcrite. Réutilise la clé Anthropic du bloc Génération IA." },
];

// Moteur de VÉRIFICATION : indépendant de celui de Génération IA (voir
// Services/ia_verification.py::config_verif) — l'intérêt est justement de
// pouvoir croiser le regard d'un modèle différent de celui qui a généré.
const MOTEURS_VERIF = [
  { id: "claude", nom: "Claude (Anthropic)", desc: "Réutilise la clé Anthropic du sous-menu Génération IA. Bon choix par défaut pour vérifier un contenu généré par un modèle local." },
  { id: "gemini", nom: "Gemini (Google)", desc: "Réutilise la clé Gemini du sous-menu Génération IA." },
  { id: "ollama", nom: "Ollama (local, gratuit)", desc: "Peut être le même serveur que la génération, ou un autre modèle installé dessus — mais vérifier avec le modèle qui a généré perd l'intérêt du regard croisé." },
];

function formatDateHeure(iso) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("fr-FR")} à ${d.toLocaleTimeString("fr-FR")}`;
}

/* Prompt envoyé à l'IA = contenu du cours (auto, non modifiable) + une
   CONSIGNE personnalisable ci-dessous + un format JSON de sortie fixe
   (l'application dépend de ces clés exactes pour lire la réponse). */
function PromptEditor({ titre, description, consigne, setConsigne, defaut, formatJson, C }) {
  const zoneStyle = { width: "100%", background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 10px", fontFamily: "monospace", fontSize: 12, lineHeight: 1.5, color: C.ink, outline: "none", resize: "vertical", boxSizing: "border-box" };
  const fixeStyle = { width: "100%", background: C.paper, border: `1px dashed ${C.line}`, borderRadius: 8, padding: "8px 10px", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5, color: C.inkFaint, whiteSpace: "pre-wrap", boxSizing: "border-box" };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontFamily: uiFont, fontSize: 13, fontWeight: 700, color: C.ink }}>{titre}</div>
      <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>{description}</p>

      <div style={fixeStyle}>« contenu du cours (texte extrait) » — ajouté automatiquement en premier, non modifiable</div>

      <textarea value={consigne} onChange={(e) => setConsigne(e.target.value)} rows={7} placeholder={defaut} style={zoneStyle} />
      <button
        onClick={() => setConsigne("")}
        style={{ alignSelf: "flex-start", background: "transparent", border: "none", color: C.haunt, fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, cursor: "pointer", padding: 0 }}
      >
        Réinitialiser au texte par défaut
      </button>

      <div style={fixeStyle}>{formatJson}</div>
      <p style={{ fontFamily: uiFont, fontSize: 11, color: C.inkFaint, margin: 0 }}>
        Ce format JSON reste fixe : l'application dépend de cette structure exacte pour lire la réponse de l'IA.
      </p>
    </div>
  );
}

export function ParametresScreen() {
  const { C } = useTheme();
  const parametres = useApi("/api/parametres");
  const derniereSync = useApi("/api/sync/last");
  const [sousMenu, setSousMenu] = useState("pronote");
  const [moteur, setMoteur] = useState("ollama");
  const [ollamaUrl, setOllamaUrl] = useState("");
  const [ollamaModel, setOllamaModel] = useState("");
  const [ollamaChunkSize, setOllamaChunkSize] = useState("");
  const [ollamaDecoupageActif, setOllamaDecoupageActif] = useState(true);
  const [promptGenerationConsigne, setPromptGenerationConsigne] = useState("");
  const [promptCompletionConsigne, setPromptCompletionConsigne] = useState("");
  const [ollamaModeles, setOllamaModeles] = useState([]);
  const [ollamaModelesLoading, setOllamaModelesLoading] = useState(false);
  const [ollamaModelesError, setOllamaModelesError] = useState(null);
  const [geminiModel, setGeminiModel] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [pronoteUrl, setPronoteUrl] = useState("");
  const [syncDaysBack, setSyncDaysBack] = useState("");
  const [syncDaysForward, setSyncDaysForward] = useState("");
  const [matieresExclues, setMatieresExclues] = useState("");
  const [ocrEngine, setOcrEngine] = useState("paddleocr");
  const [paddleocrEnableMkldnn, setPaddleocrEnableMkldnn] = useState(false);
  const [verifMoteur, setVerifMoteur] = useState("claude");
  const [verifOllamaUrl, setVerifOllamaUrl] = useState("");
  const [verifOllamaModel, setVerifOllamaModel] = useState("");
  const [verifGeminiModel, setVerifGeminiModel] = useState("");
  const [verifOllamaModeles, setVerifOllamaModeles] = useState([]);
  const [verifOllamaModelesLoading, setVerifOllamaModelesLoading] = useState(false);
  const [verifOllamaModelesError, setVerifOllamaModelesError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveOk, setSaveOk] = useState(false);

  useEffect(() => {
    if (parametres.data) {
      setMoteur(parametres.data.ia_moteur);
      setOllamaUrl(parametres.data.ollama_url || "");
      setOllamaModel(parametres.data.ollama_model || "");
      setOllamaChunkSize(String(parametres.data.ollama_chunk_size ?? ""));
      setOllamaDecoupageActif(parametres.data.ollama_decoupage_actif ?? true);
      setPromptGenerationConsigne(parametres.data.ia_prompt_generation_consigne || "");
      setPromptCompletionConsigne(parametres.data.ia_prompt_completion_consigne || "");
      setGeminiModel(parametres.data.gemini_model || "");
      setPronoteUrl(parametres.data.pronote_url || "");
      setSyncDaysBack(String(parametres.data.sync_days_back ?? ""));
      setSyncDaysForward(String(parametres.data.sync_days_forward ?? ""));
      setMatieresExclues(parametres.data.matieres_exclues || "");
      setOcrEngine(parametres.data.ocr_engine || "paddleocr");
      setPaddleocrEnableMkldnn(parametres.data.paddleocr_enable_mkldnn ?? false);
      setVerifMoteur(parametres.data.verif_moteur || "claude");
      setVerifOllamaUrl(parametres.data.verif_ollama_url || "");
      setVerifOllamaModel(parametres.data.verif_ollama_model || "");
      setVerifGeminiModel(parametres.data.verif_gemini_model || "");
    }
  }, [parametres.data]);

  // Factorisé pour être réutilisé par les onglets Génération IA ET
  // Vérification (deux serveurs Ollama potentiellement différents).
  async function chargerModelesOllamaGenerique(url, { setModeles, setLoading, setError }) {
    setLoading(true);
    setError(null);
    try {
      const qs = url.trim() ? `?url=${encodeURIComponent(url.trim())}` : "";
      const res = await fetch(`${API_BASE}/api/parametres/ollama-modeles${qs}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      const data = await res.json();
      setModeles(data.modeles || []);
      if (data.modeles?.length === 0) setError("Aucun modèle installé sur ce serveur Ollama.");
    } catch (e) {
      setModeles([]);
      setError(messageErreur(e, "Impossible de récupérer la liste des modèles."));
    } finally {
      setLoading(false);
    }
  }

  function chargerModelesOllama() {
    chargerModelesOllamaGenerique(ollamaUrl, { setModeles: setOllamaModeles, setLoading: setOllamaModelesLoading, setError: setOllamaModelesError });
  }

  function chargerModelesVerifOllama() {
    chargerModelesOllamaGenerique(verifOllamaUrl, { setModeles: setVerifOllamaModeles, setLoading: setVerifOllamaModelesLoading, setError: setVerifOllamaModelesError });
  }

  async function enregistrer() {
    setSaving(true);
    setSaveError(null);
    setSaveOk(false);
    try {
      const body = {
        ia_moteur: moteur,
        ollama_url: ollamaUrl.trim() || null,
        ollama_model: ollamaModel.trim() || null,
        ollama_chunk_size: ollamaChunkSize.trim() ? parseInt(ollamaChunkSize, 10) : null,
        ollama_decoupage_actif: ollamaDecoupageActif,
        ia_prompt_generation_consigne: promptGenerationConsigne,
        ia_prompt_completion_consigne: promptCompletionConsigne,
        gemini_model: geminiModel || null,
        pronote_url: pronoteUrl.trim() || null,
        sync_days_back: syncDaysBack.trim() ? parseInt(syncDaysBack, 10) : null,
        sync_days_forward: syncDaysForward.trim() ? parseInt(syncDaysForward, 10) : null,
        matieres_exclues: matieresExclues,
        ocr_engine: ocrEngine,
        paddleocr_enable_mkldnn: paddleocrEnableMkldnn,
        verif_moteur: verifMoteur,
        verif_ollama_url: verifOllamaUrl.trim() || null,
        verif_ollama_model: verifOllamaModel.trim() || null,
        verif_gemini_model: verifGeminiModel.trim() || null,
      };
      if (geminiKey.trim()) body.gemini_api_key = geminiKey.trim();
      if (anthropicKey.trim()) body.anthropic_api_key = anthropicKey.trim();
      const res = await fetch(`${API_BASE}/api/parametres`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      setGeminiKey("");
      setAnthropicKey("");
      setSaveOk(true);
      parametres.reload();
    } catch (e) {
      setSaveError(messageErreur(e, "Impossible d'enregistrer."));
    } finally {
      setSaving(false);
    }
  }

  const inputStyle = { width: "100%", background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 10px", fontFamily: uiFont, fontSize: 13, color: C.ink, outline: "none" };
  const labelStyle = { fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, display: "block", marginBottom: 4 };
  const carteStyle = { background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16 };
  const sousCarteStyle = { background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 10, padding: 14, display: "flex", flexDirection: "column", gap: 12 };

  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Paramétrage</h1>
      </div>
      <div style={{ padding: "16px 0 0" }}>
        <SousMenu actif={sousMenu} onChange={setSousMenu} extra={[SOUS_MENU_PROMPTS, SOUS_MENU_VERIFICATION]} />
      </div>
      <div style={{ padding: "0 20px 16px", display: "flex", flexDirection: "column", gap: 16 }}>
        {parametres.loading && <Loading />}
        {parametres.error && <ApiError message={parametres.error} onRetry={parametres.reload} />}

        {parametres.data && sousMenu === "pronote" && (
          <div style={carteStyle}>
            <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 17, color: C.ink, margin: "0 0 4px" }}>Pronote</h2>
            <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "0 0 14px" }}>
              Fenêtre de synchronisation et état de la connexion au service Pronote.
            </p>

            <div style={{ background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 10, padding: 14, marginBottom: 14 }}>
              <div className="flex items-center gap-2">
                {parametres.data.pronote_jeton_present ? (
                  <CheckCircle2 size={15} color={C.spectral} />
                ) : (
                  <XCircle size={15} color={C.brick} />
                )}
                <span style={{ fontFamily: uiFont, fontSize: 13, fontWeight: 700, color: parametres.data.pronote_jeton_present ? C.spectral : C.brick }}>
                  {parametres.data.pronote_jeton_present ? "Jeton de connexion présent" : "Aucun jeton de connexion"}
                </span>
              </div>
              {!parametres.data.pronote_jeton_present && (
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: "4px 0 0" }}>
                  Lance la procédure de première connexion (voir Services/README.md) pour l'activer.
                </p>
              )}

              <div style={{ height: 1, background: C.line, margin: "10px 0" }} />

              {derniereSync.loading && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: 0 }}>Vérification de la dernière synchronisation…</p>}
              {!derniereSync.loading && !derniereSync.data && (
                <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: 0 }}>Aucune synchronisation lancée pour l'instant.</p>
              )}
              {derniereSync.data && (
                <>
                  <div className="flex items-center gap-2">
                    {derniereSync.data.erreur ? (
                      <XCircle size={14} color={C.brick} />
                    ) : (
                      <CheckCircle2 size={14} color={C.spectral} />
                    )}
                    <span style={{ fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, color: derniereSync.data.erreur ? C.brick : C.spectral }}>
                      Dernière synchronisation {derniereSync.data.erreur ? "en échec" : "réussie"}
                    </span>
                  </div>
                  <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, margin: "4px 0 0" }}>
                    {formatDateHeure(derniereSync.data.finished_at || derniereSync.data.started_at)}
                    {!derniereSync.data.erreur && ` · ${derniereSync.data.nouveaux_cours} cours, ${derniereSync.data.nouveaux_devoirs} devoirs, ${derniereSync.data.nouveaux_documents} documents, ${derniereSync.data.nouvelles_notes ?? 0} notes`}
                  </p>
                  {derniereSync.data.erreur && (
                    <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "4px 0 0" }}>{derniereSync.data.erreur}</p>
                  )}
                </>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={labelStyle}>URL PRONOTE</label>
                <input value={pronoteUrl} onChange={(e) => setPronoteUrl(e.target.value)} placeholder="https://XXXX.index-education.net/pronote/eleve.html" style={inputStyle} />
                <p style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkFaint, margin: "4px 0 0" }}>
                  Sert seulement à vérifier que Pronote est configuré : l'adresse réellement utilisée pour se
                  connecter est celle enregistrée dans le jeton (voir procédure de première connexion).
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>JOURS EN ARRIÈRE</label>
                  <input type="number" min={0} value={syncDaysBack} onChange={(e) => setSyncDaysBack(e.target.value)} style={inputStyle} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>JOURS EN AVANT</label>
                  <input type="number" min={0} value={syncDaysForward} onChange={(e) => setSyncDaysForward(e.target.value)} style={inputStyle} />
                </div>
              </div>
              <p style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkFaint, margin: 0 }}>
                Fenêtre récupérée à chaque synchronisation autour d'aujourd'hui (ex. 3 jours en arrière, 10 en avant).
              </p>
              <div>
                <label style={labelStyle}>MATIÈRES À EXCLURE</label>
                <input
                  value={matieresExclues}
                  onChange={(e) => setMatieresExclues(e.target.value)}
                  placeholder="Réunion parents-profs, Journée du sport scolaire"
                  style={inputStyle}
                />
                <p style={{ fontFamily: uiFont, fontSize: 11.5, color: C.inkFaint, margin: "4px 0 0" }}>
                  Noms séparés par des virgules, tels qu'affichés dans Pronote (accents/majuscules sans
                  importance). Certains créneaux ne sont pas de vraies matières (réunions, journées
                  spéciales...) — ceux listés ici ne seront plus importés à la prochaine synchronisation.
                </p>
              </div>
            </div>
          </div>
        )}

        {parametres.data && sousMenu === "ia" && (
          <div style={carteStyle}>
            <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 17, color: C.ink, margin: "0 0 4px" }}>Génération IA</h2>
            <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "0 0 14px" }}>
              Moteur utilisé pour générer résumés/flashcards/quiz et pour l'assistant conversationnel.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
              {MOTEURS_IA.map((m) => (
                <label
                  key={m.id}
                  style={{ display: "flex", gap: 10, alignItems: "flex-start", background: C.paperDim, border: `1px solid ${moteur === m.id ? C.haunt : C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer" }}
                >
                  <input type="radio" checked={moteur === m.id} onChange={() => setMoteur(m.id)} style={{ marginTop: 3, accentColor: C.haunt }} />
                  <div>
                    <div style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.nom}</div>
                    <div style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, marginTop: 2 }}>{m.desc}</div>
                  </div>
                </label>
              ))}
            </div>

            {moteur === "ollama" && (
              <div style={sousCarteStyle}>
                <div>
                  <label style={labelStyle}>URL DU SERVEUR OLLAMA</label>
                  <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} placeholder="http://127.0.0.1:11434" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>MODÈLE</label>
                  <div className="flex items-center gap-2">
                    <input value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} placeholder="qwen3:14b" style={inputStyle} />
                    <button
                      onClick={chargerModelesOllama}
                      disabled={ollamaModelesLoading}
                      title="Interroger le serveur Ollama pour lister les modèles installés"
                      style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6, background: C.white, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 12px", fontFamily: uiFont, fontSize: 12, fontWeight: 600, color: C.inkSoft, cursor: ollamaModelesLoading ? "default" : "pointer" }}
                    >
                      <RefreshCw size={13} style={ollamaModelesLoading ? { animation: "spin 1s linear infinite" } : {}} />
                      {ollamaModelesLoading ? "Recherche…" : "Détecter"}
                    </button>
                  </div>
                  {ollamaModelesError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "6px 0 0" }}>{ollamaModelesError}</p>}
                  {ollamaModeles.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {ollamaModeles.map((nom) => (
                        <button
                          key={nom}
                          onClick={() => setOllamaModel(nom)}
                          style={{
                            background: ollamaModel === nom ? C.hauntSoft : C.white,
                            border: `1px solid ${ollamaModel === nom ? C.haunt : C.line}`,
                            color: ollamaModel === nom ? C.haunt : C.inkSoft,
                            borderRadius: 999, padding: "4px 10px", fontFamily: uiFont, fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                          }}
                        >
                          {nom}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                  "Détecter" interroge {ollamaUrl.trim() || "l'URL ci-dessus"} pour lister les modèles déjà installés
                  (<code>ollama pull …</code> sur le serveur pour en ajouter un nouveau).
                </p>

                <div className="flex items-center justify-between">
                  <div>
                    <div style={{ fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, color: C.ink }}>Découpage automatique</div>
                    <div style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, marginTop: 2, maxWidth: 380 }}>
                      Ollama tourne en local avec un contexte limité par le matériel : un cours trop long est
                      découpé en plusieurs parties, chacune résumée séparément, avant la génération finale
                      (visible étape par étape dans "Traitements").
                    </div>
                  </div>
                  <button
                    onClick={() => setOllamaDecoupageActif((v) => !v)}
                    title={ollamaDecoupageActif ? "Désactiver le découpage automatique" : "Activer le découpage automatique"}
                    style={{
                      flexShrink: 0, display: "flex", alignItems: "center", gap: 5,
                      background: ollamaDecoupageActif ? C.hauntSoft : C.paperDim,
                      border: `1px solid ${ollamaDecoupageActif ? C.haunt : C.line}`,
                      color: ollamaDecoupageActif ? C.haunt : C.inkFaint,
                      borderRadius: 999, padding: "5px 12px", fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, cursor: "pointer",
                    }}
                  >
                    {ollamaDecoupageActif ? "Activé" : "Désactivé"}
                  </button>
                </div>

                {ollamaDecoupageActif ? (
                  <div>
                    <label style={labelStyle}>TAILLE DE DÉCOUPAGE (CARACTÈRES)</label>
                    <input type="number" min={1000} step={1000} value={ollamaChunkSize} onChange={(e) => setOllamaChunkSize(e.target.value)} placeholder="12000" style={inputStyle} />
                  </div>
                ) : (
                  <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                    Désactivé : le cours entier est envoyé à Ollama en un seul appel, sans troncature ni découpage
                    — comme pour Claude/Gemini. À réserver à un modèle local à grand contexte.
                  </p>
                )}
              </div>
            )}

            {moteur === "claude" && (
              <div style={sousCarteStyle}>
                <div>
                  <label style={labelStyle}>
                    CLÉ API ANTHROPIC {parametres.data.anthropic_api_key_configuree ? "(déjà configurée — laisser vide pour ne pas la changer)" : "(non configurée)"}
                  </label>
                  <input type="password" value={anthropicKey} onChange={(e) => setAnthropicKey(e.target.value)} placeholder="sk-ant-..." style={inputStyle} />
                </div>
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                  Clé créée sur console.anthropic.com — reste stockée côté serveur, jamais renvoyée au navigateur.
                  Réutilisée par l'OCR si tu choisis Claude dans le sous-menu OCR.
                </p>
              </div>
            )}

            {moteur === "gemini" && (
              <div style={sousCarteStyle}>
                <div>
                  <label style={labelStyle}>MODÈLE GEMINI</label>
                  <input value={geminiModel} onChange={(e) => setGeminiModel(e.target.value)} placeholder="gemini-3.5-flash-lite" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>
                    CLÉ API {parametres.data.gemini_api_key_configuree ? "(déjà configurée — laisser vide pour ne pas la changer)" : "(non configurée)"}
                  </label>
                  <input type="password" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} placeholder="AIza..." style={inputStyle} />
                </div>
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                  Clé créée sur aistudio.google.com — reste stockée côté serveur, jamais renvoyée au navigateur.
                </p>
              </div>
            )}
          </div>
        )}

        {parametres.data && sousMenu === "prompts" && (
          <div style={carteStyle}>
            <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 17, color: C.ink, margin: "0 0 4px" }}>Prompts</h2>
            <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "0 0 14px" }}>
              Modifiable en partie seulement : le contenu du cours est toujours ajouté en premier, et le
              format JSON attendu en sortie reste fixe (l'application le lit tel quel). Seule la consigne du
              milieu — ce qu'on demande de produire — peut être personnalisée.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <PromptEditor
                titre="Génération initiale (résumés + flashcards + quiz)"
                description="Utilisée quand on clique sur « Générer » pour un cours."
                consigne={promptGenerationConsigne}
                setConsigne={setPromptGenerationConsigne}
                defaut={parametres.data.ia_prompt_generation_consigne_defaut}
                formatJson={parametres.data.ia_prompt_generation_format_json}
                C={C}
              />
              <PromptEditor
                titre="Complément (+ 10 flashcards / quiz)"
                description="Utilisée quand on clique sur « + 10 » pour ajouter du contenu à une génération déjà en place."
                consigne={promptCompletionConsigne}
                setConsigne={setPromptCompletionConsigne}
                defaut={parametres.data.ia_prompt_completion_consigne_defaut}
                formatJson={parametres.data.ia_prompt_completion_format_json}
                C={C}
              />
            </div>
          </div>
        )}

        {parametres.data && sousMenu === "ocr" && (
          <div style={carteStyle}>
            <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 17, color: C.ink, margin: "0 0 4px" }}>OCR</h2>
            <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "0 0 14px" }}>
              Moteur utilisé pour transcrire les PDF Pronote scannés et les photos de notes déposées par les élèves.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
              {MOTEURS_OCR.map((m) => (
                <label
                  key={m.id}
                  style={{ display: "flex", gap: 10, alignItems: "flex-start", background: C.paperDim, border: `1px solid ${ocrEngine === m.id ? C.haunt : C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer" }}
                >
                  <input type="radio" checked={ocrEngine === m.id} onChange={() => setOcrEngine(m.id)} style={{ marginTop: 3, accentColor: C.haunt }} />
                  <div>
                    <div style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.nom}</div>
                    <div style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, marginTop: 2 }}>{m.desc}</div>
                  </div>
                </label>
              ))}
            </div>

            {ocrEngine === "claude" && (
              <div style={sousCarteStyle}>
                <div>
                  <label style={labelStyle}>
                    CLÉ API ANTHROPIC {parametres.data.anthropic_api_key_configuree ? "(déjà configurée — laisser vide pour ne pas la changer)" : "(non configurée)"}
                  </label>
                  <input type="password" value={anthropicKey} onChange={(e) => setAnthropicKey(e.target.value)} placeholder="sk-ant-..." style={inputStyle} />
                </div>
                <p style={{ fontFamily: uiFont, fontSize: 12, color: C.inkFaint, margin: 0 }}>
                  Même clé que le sous-menu Génération IA (un seul compte Anthropic pour toute l'application).
                </p>
              </div>
            )}

            {ocrEngine === "paddleocr" && (
              <div style={{ marginTop: 14 }}>
                <p style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3, margin: "0 0 8px" }}>AVANCÉ</p>
                <label style={{ display: "flex", gap: 10, alignItems: "flex-start", background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={paddleocrEnableMkldnn}
                    onChange={(e) => setPaddleocrEnableMkldnn(e.target.checked)}
                    style={{ marginTop: 3, accentColor: C.haunt }}
                  />
                  <div>
                    <div style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color: C.ink }}>Accélération oneDNN (CPU)</div>
                    <div style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, marginTop: 2 }}>
                      Désactivée par défaut : une régression connue de PaddlePaddle 3.3.x fait planter
                      la transcription avec cette accélération activée, sur certaines machines
                      (<code>ConvertPirAttribute2RuntimeAttribute not support</code>, voir{" "}
                      <a href="https://github.com/PaddlePaddle/Paddle/issues/77340" target="_blank" rel="noreferrer" style={{ color: C.haunt }}>
                        PaddlePaddle/Paddle#77340
                      </a>). La transcription est un peu plus lente sans elle, mais fonctionne de
                      façon fiable. À réactiver seulement si ce bug est corrigé, ou si tu constates
                      qu'il ne se manifeste pas sur ta machine et que l'accélération apporte un vrai
                      gain de vitesse — sans effet si le moteur choisi ci-dessus est Claude (Vision).
                    </div>
                  </div>
                </label>
              </div>
            )}
          </div>
        )}

        {parametres.data && sousMenu === "verification" && (
          <div style={carteStyle}>
            <h2 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 17, color: C.ink, margin: "0 0 4px" }}>Vérification</h2>
            <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.inkFaint, margin: "0 0 14px" }}>
              Moteur utilisé pour évaluer la fiabilité d'une génération déjà en place (bouton "Vérifier" dans le
              détail d'un cours) : confronte résumé/flashcards/quiz au texte source et donne un score par élément.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
              {MOTEURS_VERIF.map((m) => (
                <label
                  key={m.id}
                  style={{ display: "flex", gap: 10, alignItems: "flex-start", background: C.paperDim, border: `1px solid ${verifMoteur === m.id ? C.haunt : C.line}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer" }}
                >
                  <input type="radio" checked={verifMoteur === m.id} onChange={() => setVerifMoteur(m.id)} style={{ marginTop: 3, accentColor: C.haunt }} />
                  <div>
                    <div style={{ fontFamily: uiFont, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.nom}</div>
                    <div style={{ fontFamily: uiFont, fontSize: 12, color: C.inkSoft, marginTop: 2 }}>{m.desc}</div>
                  </div>
                </label>
              ))}
            </div>

            {verifMoteur === "ollama" && (
              <div style={sousCarteStyle}>
                <div>
                  <label style={labelStyle}>URL DU SERVEUR OLLAMA</label>
                  <input value={verifOllamaUrl} onChange={(e) => setVerifOllamaUrl(e.target.value)} placeholder="http://127.0.0.1:11434" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>MODÈLE</label>
                  <div className="flex items-center gap-2">
                    <input value={verifOllamaModel} onChange={(e) => setVerifOllamaModel(e.target.value)} placeholder="qwen3:14b" style={inputStyle} />
                    <button
                      onClick={chargerModelesVerifOllama}
                      disabled={verifOllamaModelesLoading}
                      title="Interroger le serveur Ollama pour lister les modèles installés"
                      style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6, background: C.white, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 12px", fontFamily: uiFont, fontSize: 12, fontWeight: 600, color: C.inkSoft, cursor: verifOllamaModelesLoading ? "default" : "pointer" }}
                    >
                      <RefreshCw size={13} style={verifOllamaModelesLoading ? { animation: "spin 1s linear infinite" } : {}} />
                      {verifOllamaModelesLoading ? "Recherche…" : "Détecter"}
                    </button>
                  </div>
                  {verifOllamaModelesError && <p style={{ fontFamily: uiFont, fontSize: 12, color: C.brick, margin: "6px 0 0" }}>{verifOllamaModelesError}</p>}
                  {verifOllamaModeles.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {verifOllamaModeles.map((nom) => (
                        <button
                          key={nom}
                          onClick={() => setVerifOllamaModel(nom)}
                          style={{
                            background: verifOllamaModel === nom ? C.hauntSoft : C.white,
                            border: `1px solid ${verifOllamaModel === nom ? C.haunt : C.line}`,
                            color: verifOllamaModel === nom ? C.haunt : C.inkSoft,
                            borderRadius: 999, padding: "4px 10px", fontFamily: uiFont, fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                          }}
                        >
                          {nom}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {verifMoteur === "gemini" && (
              <div style={sousCarteStyle}>
                <div>
                  <label style={labelStyle}>MODÈLE GEMINI</label>
                  <input value={verifGeminiModel} onChange={(e) => setVerifGeminiModel(e.target.value)} placeholder="gemini-3.5-flash-lite" style={inputStyle} />
                </div>
              </div>
            )}
          </div>
        )}

        {parametres.data && (
          <div>
            <button
              onClick={enregistrer}
              disabled={saving}
              style={{ background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "9px 20px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: saving ? "default" : "pointer", opacity: saving ? 0.7 : 1 }}
            >
              {saving ? "Enregistrement…" : "Enregistrer"}
            </button>
            {saveOk && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.spectral, margin: "10px 0 0" }}>Paramètres enregistrés.</p>}
            {saveError && <p style={{ fontFamily: uiFont, fontSize: 12.5, color: C.brick, margin: "10px 0 0" }}>{saveError}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
