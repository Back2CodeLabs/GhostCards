import { useState } from "react";
import { Ghost, Check, X, ArrowRight } from "lucide-react";
import { useTheme, uiFont } from "../theme";

/* ------------------------------------------------------------------ */
/* Mode examen — flashcards/quiz ne sont visibles QUE depuis ce mode    */
/* (voir CoursDetail), déclenché par un bouton "Tester mes                */
/* connaissances" qui fait "s'évaporer" le reste du cours (voir la classe */
/* .gc-evaporate dans index.css) avant de basculer ici. Séquence :        */
/* flashcards (auto-évaluées) puis quiz (auto-corrigé), puis score final. */
/* ------------------------------------------------------------------ */

// Délai entre le clic sur "Je savais"/"Je ne savais pas" et l'avancement
// réel à la carte suivante : le temps de voir le check/croix (.gc-pop)
// s'afficher, sans quoi la réponse disparaît trop vite pour être un vrai
// retour visuel (voir `repondreFlashcard` plus bas, aucun feedback avant).
const DELAI_FEEDBACK_MS = 550;

function ExamFlashcard({ card, onAnswer }) {
  const { C } = useTheme();
  const [revealed, setRevealed] = useState(false);
  const [feedback, setFeedback] = useState(null); // null | true (savais) | false (pas su)

  function repondre(savais) {
    if (feedback !== null) return; // évite un double clic pendant le délai
    setFeedback(savais);
    setTimeout(() => onAnswer(savais), DELAI_FEEDBACK_MS);
  }

  const faceStyle = { background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 18, minHeight: 140 };

  return (
    <div className="gc-flip gc-card-in">
      <div className={`gc-flip-inner${revealed ? " gc-flip-retournee" : ""}`}>
        <div className="gc-flip-face" style={faceStyle}>
          <div style={{ fontSize: 15, color: C.ink, fontWeight: 700, lineHeight: 1.4 }}>{card.question}</div>
          <button
            onClick={() => setRevealed(true)}
            style={{ marginTop: 14, background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 14px", fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft, cursor: "pointer" }}
          >
            Toucher pour voir la réponse
          </button>
        </div>
        <div className="gc-flip-face gc-flip-face-arriere" style={faceStyle}>
          <div style={{ fontSize: 13.5, color: C.spectral, lineHeight: 1.5 }}>{card.reponse}</div>
          <div className="flex items-center gap-2" style={{ marginTop: 14 }}>
            <button
              onClick={() => repondre(true)}
              disabled={feedback !== null}
              style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, justifyContent: "center", background: C.spectralSoft, color: C.spectral, border: "none", borderRadius: 8, padding: "9px 12px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: feedback === null ? "pointer" : "default" }}
            >
              <Check size={14} /> Je savais
            </button>
            <button
              onClick={() => repondre(false)}
              disabled={feedback !== null}
              style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, justifyContent: "center", background: C.brickSoft, color: C.brick, border: "none", borderRadius: 8, padding: "9px 12px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: feedback === null ? "pointer" : "default" }}
            >
              <X size={14} /> Je ne savais pas
            </button>
          </div>
          {feedback !== null && (
            <div
              className="gc-pop"
              style={{
                position: "absolute", inset: 0, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center",
                background: feedback ? C.spectralSoft : C.brickSoft, opacity: 0.95,
              }}
            >
              {feedback ? <Check size={40} color={C.spectral} /> : <X size={40} color={C.brick} />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ExamQuizQuestion({ question, onAnswer }) {
  const { C } = useTheme();
  const [choix, setChoix] = useState(null);
  return (
    <div className="gc-card-in" style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 18 }}>
      <div style={{ fontSize: 15, color: C.ink, fontWeight: 700, marginBottom: 12, lineHeight: 1.4 }}>{question.question}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {question.options.map((opt, i) => {
          const estChoisie = choix === i;
          const estCorrecte = i === question.reponse_index;
          let bg = C.paperDim;
          let border = C.line;
          if (choix !== null && estCorrecte) { border = C.spectral; bg = C.spectralSoft; }
          else if (estChoisie && !estCorrecte) { border = C.brick; bg = C.brickSoft; }
          return (
            <button
              key={i}
              onClick={() => choix === null && setChoix(i)}
              className={estChoisie ? "gc-pop" : undefined}
              style={{ textAlign: "left", background: bg, border: `1px solid ${border}`, borderRadius: 8, padding: "10px 12px", fontFamily: uiFont, fontSize: 13.5, color: C.ink, cursor: choix === null ? "pointer" : "default" }}
            >
              {opt}
            </button>
          );
        })}
      </div>
      {choix !== null && (
        <button
          onClick={() => onAnswer(choix === question.reponse_index)}
          style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 6, background: C.haunt, color: C.onAccent, border: "none", borderRadius: 8, padding: "9px 16px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}
        >
          Suivant <ArrowRight size={13} />
        </button>
      )}
    </div>
  );
}

// Partagé entre l'écran de score et `onFinish` (voir ExamMode) : le
// résultat doit être calculé au même endroit pour que ce qui est affiché
// et ce qui est mémorisé (dernier résultat sur la page du cours) soient
// toujours identiques.
function calculerResultat(flashcardResults, quizResults) {
  const totalFlashcards = flashcardResults.length;
  const savais = flashcardResults.filter(Boolean).length;
  const totalQuiz = quizResults.length;
  const correctes = quizResults.filter(Boolean).length;
  const totalReponses = totalFlashcards + totalQuiz;
  const totalReussies = savais + correctes;
  const pourcentage = totalReponses > 0 ? Math.round((totalReussies / totalReponses) * 100) : 0;
  return { totalFlashcards, savais, totalQuiz, correctes, totalReponses, totalReussies, pourcentage };
}

function ScoreEcran({ flashcardResults, quizResults, onExit, C }) {
  const { totalFlashcards, savais, totalQuiz, correctes, totalReponses, totalReussies, pourcentage } =
    calculerResultat(flashcardResults, quizResults);

  return (
    <div className="gc-materialize" style={{ textAlign: "center", padding: "32px 16px" }}>
      <Ghost size={40} color={C.haunt} style={{ marginBottom: 12 }} />
      <div style={{ fontFamily: uiFont, fontSize: 34, fontWeight: 800, color: C.ink }}>{pourcentage}%</div>
      <p style={{ fontFamily: uiFont, fontSize: 13.5, color: C.inkSoft, margin: "8px 0 20px" }}>
        {totalReussies} / {totalReponses} bonnes réponses
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 280, margin: "0 auto 24px", textAlign: "left" }}>
        {totalFlashcards > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", fontFamily: uiFont, fontSize: 13, color: C.inkSoft }}>
            <span>Flashcards sues</span><span style={{ fontWeight: 700, color: C.ink }}>{savais} / {totalFlashcards}</span>
          </div>
        )}
        {totalQuiz > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", fontFamily: uiFont, fontSize: 13, color: C.inkSoft }}>
            <span>Quiz réussi</span><span style={{ fontWeight: 700, color: C.ink }}>{correctes} / {totalQuiz}</span>
          </div>
        )}
      </div>
      <button
        onClick={onExit}
        style={{ background: C.haunt, color: C.onAccent, border: "none", borderRadius: 10, padding: "10px 22px", fontFamily: uiFont, fontSize: 13, fontWeight: 700, cursor: "pointer" }}
      >
        Terminer
      </button>
    </div>
  );
}

export function ExamMode({ flashcards, quiz, onExit, onFinish }) {
  const { C } = useTheme();
  // Séquence flashcards → quiz → score, en sautant une étape vide (un
  // cours peut n'avoir que des flashcards, ou que du quiz).
  const [phase, setPhase] = useState(flashcards.length > 0 ? "flashcards" : quiz.length > 0 ? "quiz" : "score");
  const [flashcardIndex, setFlashcardIndex] = useState(0);
  const [flashcardResults, setFlashcardResults] = useState([]);
  const [quizIndex, setQuizIndex] = useState(0);
  const [quizResults, setQuizResults] = useState([]);

  // Mémorisé dès que le résultat est connu (pas seulement au clic sur
  // "Terminer") : sinon fermer l'onglet depuis l'écran de score perdrait
  // le résultat pour la page du cours (voir CoursDetail::onFinish).
  function terminer(flashcardResultsFinal, quizResultsFinal) {
    setPhase("score");
    onFinish?.(calculerResultat(flashcardResultsFinal, quizResultsFinal));
  }

  function repondreFlashcard(savais) {
    const resultats = [...flashcardResults, savais];
    setFlashcardResults(resultats);
    if (flashcardIndex + 1 < flashcards.length) setFlashcardIndex(flashcardIndex + 1);
    else if (quiz.length > 0) setPhase("quiz");
    else terminer(resultats, quizResults);
  }

  function repondreQuiz(correcte) {
    const resultats = [...quizResults, correcte];
    setQuizResults(resultats);
    if (quizIndex + 1 < quiz.length) setQuizIndex(quizIndex + 1);
    else terminer(flashcardResults, resultats);
  }

  if (phase === "score") {
    return <ScoreEcran flashcardResults={flashcardResults} quizResults={quizResults} onExit={onExit} C={C} />;
  }

  const enFlashcards = phase === "flashcards";
  const progression = enFlashcards
    ? `Flashcard ${flashcardIndex + 1} / ${flashcards.length}`
    : `Question ${quizIndex + 1} / ${quiz.length}`;

  // Une seule barre continue sur toute la session (flashcards puis quiz),
  // plutôt qu'une barre qui repart de zéro à chaque phase — donne un sens
  // de progression d'ensemble, façon appli de révision.
  const totalItems = flashcards.length + quiz.length;
  const itemsFaits = enFlashcards ? flashcardIndex : flashcards.length + quizIndex;
  const pourcentageFait = totalItems > 0 ? Math.round((itemsFaits / totalItems) * 100) : 0;

  return (
    <div className="gc-materialize">
      <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
        <span style={{ fontFamily: uiFont, fontSize: 11.5, fontWeight: 700, color: C.inkFaint, letterSpacing: 0.3 }}>
          MODE EXAMEN · {progression.toUpperCase()}
        </span>
        <button
          onClick={onExit}
          style={{ background: "transparent", border: "none", color: C.inkFaint, fontFamily: uiFont, fontSize: 12, fontWeight: 600, cursor: "pointer", padding: 0 }}
        >
          Quitter
        </button>
      </div>
      <div style={{ height: 5, background: C.paperDim, borderRadius: 999, marginBottom: 14, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pourcentageFait}%`, background: C.haunt, borderRadius: 999, transition: "width 350ms ease" }} />
      </div>
      {enFlashcards ? (
        <ExamFlashcard key={flashcardIndex} card={flashcards[flashcardIndex]} onAnswer={repondreFlashcard} />
      ) : (
        <ExamQuizQuestion key={quizIndex} question={quiz[quizIndex]} onAnswer={repondreQuiz} />
      )}
    </div>
  );
}
