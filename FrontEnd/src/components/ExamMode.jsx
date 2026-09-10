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

function ExamFlashcard({ card, onAnswer }) {
  const { C } = useTheme();
  const [revealed, setRevealed] = useState(false);
  return (
    <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 18, minHeight: 140 }}>
      <div style={{ fontSize: 15, color: C.ink, fontWeight: 700, lineHeight: 1.4 }}>{card.question}</div>
      {!revealed ? (
        <button
          onClick={() => setRevealed(true)}
          style={{ marginTop: 14, background: C.paperDim, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 14px", fontFamily: uiFont, fontSize: 12.5, color: C.inkSoft, cursor: "pointer" }}
        >
          Toucher pour voir la réponse
        </button>
      ) : (
        <>
          <div style={{ fontSize: 13.5, color: C.spectral, marginTop: 12, lineHeight: 1.5 }}>{card.reponse}</div>
          <div className="flex items-center gap-2" style={{ marginTop: 14 }}>
            <button
              onClick={() => onAnswer(true)}
              style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, justifyContent: "center", background: C.spectralSoft, color: C.spectral, border: "none", borderRadius: 8, padding: "9px 12px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}
            >
              <Check size={14} /> Je savais
            </button>
            <button
              onClick={() => onAnswer(false)}
              style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, justifyContent: "center", background: C.brickSoft, color: C.brick, border: "none", borderRadius: 8, padding: "9px 12px", fontFamily: uiFont, fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}
            >
              <X size={14} /> Je ne savais pas
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ExamQuizQuestion({ question, onAnswer }) {
  const { C } = useTheme();
  const [choix, setChoix] = useState(null);
  return (
    <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 12, padding: 18 }}>
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

function ScoreEcran({ flashcardResults, quizResults, onExit, C }) {
  const totalFlashcards = flashcardResults.length;
  const savais = flashcardResults.filter(Boolean).length;
  const totalQuiz = quizResults.length;
  const correctes = quizResults.filter(Boolean).length;
  const totalReponses = totalFlashcards + totalQuiz;
  const totalReussies = savais + correctes;
  const pourcentage = totalReponses > 0 ? Math.round((totalReussies / totalReponses) * 100) : 0;

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

export function ExamMode({ flashcards, quiz, onExit }) {
  const { C } = useTheme();
  // Séquence flashcards → quiz → score, en sautant une étape vide (un
  // cours peut n'avoir que des flashcards, ou que du quiz).
  const [phase, setPhase] = useState(flashcards.length > 0 ? "flashcards" : quiz.length > 0 ? "quiz" : "score");
  const [flashcardIndex, setFlashcardIndex] = useState(0);
  const [flashcardResults, setFlashcardResults] = useState([]);
  const [quizIndex, setQuizIndex] = useState(0);
  const [quizResults, setQuizResults] = useState([]);

  function repondreFlashcard(savais) {
    const resultats = [...flashcardResults, savais];
    setFlashcardResults(resultats);
    if (flashcardIndex + 1 < flashcards.length) setFlashcardIndex(flashcardIndex + 1);
    else setPhase(quiz.length > 0 ? "quiz" : "score");
  }

  function repondreQuiz(correcte) {
    const resultats = [...quizResults, correcte];
    setQuizResults(resultats);
    if (quizIndex + 1 < quiz.length) setQuizIndex(quizIndex + 1);
    else setPhase("score");
  }

  if (phase === "score") {
    return <ScoreEcran flashcardResults={flashcardResults} quizResults={quizResults} onExit={onExit} C={C} />;
  }

  const enFlashcards = phase === "flashcards";
  const progression = enFlashcards
    ? `Flashcard ${flashcardIndex + 1} / ${flashcards.length}`
    : `Question ${quizIndex + 1} / ${quiz.length}`;

  return (
    <div className="gc-materialize">
      <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
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
      {enFlashcards ? (
        <ExamFlashcard key={flashcardIndex} card={flashcards[flashcardIndex]} onAnswer={repondreFlashcard} />
      ) : (
        <ExamQuizQuestion key={quizIndex} question={quiz[quizIndex]} onAnswer={repondreQuiz} />
      )}
    </div>
  );
}
