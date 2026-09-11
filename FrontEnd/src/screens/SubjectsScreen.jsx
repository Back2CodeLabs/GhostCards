import { ChevronRight } from "lucide-react";
import { useTheme, uiFont } from "../theme";
import { useApi } from "../api";
import { Loading, ApiError, EmptyState, ScreenHeader, IndicateursCours } from "../components/Shared";

/* ------------------------------------------------------------------ */
/* Matières                                                             */
/* ------------------------------------------------------------------ */

export function SubjectsScreen({ onOpenSubject }) {
  const { C, colorFor } = useTheme();
  const matieres = useApi("/api/matieres");
  return (
    <div>
      <div style={{ padding: "20px 20px 4px" }}>
        <h1 style={{ fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing, fontSize: 24, color: C.ink, margin: 0 }}>Matières</h1>
      </div>
      <div style={{ padding: "16px 20px" }}>
        {matieres.loading && <Loading />}
        {matieres.error && <ApiError message={matieres.error} onRetry={matieres.reload} />}
        {matieres.data && matieres.data.length === 0 && <EmptyState text="Aucune matière importée pour l'instant." />}
        <div className="gc-grid">
          {matieres.data?.map((m) => {
            const { color } = colorFor(m.id);
            return (
              <button
                key={m.id}
                onClick={() => onOpenSubject(m.id, m.nom)}
                style={{ background: C.white, border: `1px solid ${C.line}`, borderTop: `3px solid ${color}`, borderRadius: 12, padding: 16, cursor: "pointer", textAlign: "left", fontFamily: uiFont, display: "flex", flexDirection: "column", gap: 8 }}
              >
                <span style={{ fontSize: 16, fontWeight: 700, color: C.ink, fontFamily: C.fontHeading, letterSpacing: C.headingLetterSpacing }}>{m.nom}</span>
                <div style={{ display: "flex", gap: 16, fontSize: 12.5, color: C.inkSoft }}>
                  <span>{m.nb_cours} cours</span>
                  <span>{m.nb_documents} documents</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Détail matière                                                       */
/* ------------------------------------------------------------------ */

export function SubjectDetail({ subjectId, subjectName, onBack, onOpenCours }) {
  const { C, colorFor } = useTheme();
  const cours = useApi(`/api/matieres/${subjectId}/cours`, [subjectId]);
  const notes = useApi(`/api/matieres/${subjectId}/notes`, [subjectId]);
  const { color } = colorFor(subjectId);

  return (
    <div>
      <ScreenHeader title={subjectName} onBack={onBack} />
      {notes.data && notes.data.length > 0 && (
        <div style={{ padding: "0 20px 4px" }}>
          <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3 }}>NOTES</span>
            {notes.data.map((n) => (
              <div key={n.id} className="flex items-center justify-between" style={{ fontFamily: uiFont, fontSize: 13, color: C.ink }}>
                <span>
                  {n.commentaire || new Date(n.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
                  {n.coefficient && n.coefficient !== "0" && n.coefficient !== "1" ? ` · coef. ${n.coefficient}` : ""}
                </span>
                <span style={{ fontWeight: 700, color: C.haunt }}>
                  {n.valeur}/{n.bareme}
                  {n.moyenne_classe ? <span style={{ fontWeight: 400, color: C.inkFaint }}> · classe {n.moyenne_classe}</span> : null}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div style={{ padding: "16px 20px" }} className="gc-grid">
        {cours.loading && <Loading />}
        {cours.error && <ApiError message={cours.error} onRetry={cours.reload} />}
        {cours.data && cours.data.length === 0 && (
          <EmptyState text="Aucun cours importé pour cette matière." sub="Il apparaîtra ici après la prochaine synchronisation Pronote." />
        )}
        {cours.data?.map((c) => (
          <button
            key={c.id}
            onClick={() => onOpenCours(c.id)}
            style={{ background: C.white, border: `1px solid ${C.line}`, borderLeft: `3px solid ${color}`, borderRadius: 10, padding: "13px 14px", cursor: "pointer", textAlign: "left", fontFamily: uiFont }}
          >
            <div className="flex items-center justify-between">
              <span style={{ fontSize: 14.5, fontWeight: 600, color: C.ink }}>{c.titre || "Cours"}</span>
              <ChevronRight size={16} color={C.inkFaint} />
            </div>
            <div style={{ fontSize: 12, color: C.inkSoft, marginTop: 3 }}>
              {new Date(c.date).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })} · {c.heure_debut}
              {c.professeur ? ` · ${c.professeur}` : ""}
              {c.groupe ? ` · ${c.groupe}` : ""}
            </div>
            <IndicateursCours c={c} />
          </button>
        ))}
      </div>
    </div>
  );
}
