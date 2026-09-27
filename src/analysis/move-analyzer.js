export const DEFAULT_CLASSIFICATION_THRESHOLDS = Object.freeze({
  best: 10,
  good: 50,
  inaccuracy: 100,
  mistake: 200,
});

function ensureCentipawnScore(evaluation) {
  if (evaluation?.kind !== "centipawn") {
    throw new Error("Centipawn loss requires centipawn evaluations");
  }
  return evaluation.value;
}

export function calculateCentipawnLoss({ evaluationBefore, evaluationAfter, mover }) {
  if (mover !== "white" && mover !== "black") {
    throw new Error(`Unknown mover: ${mover}`);
  }

  const before = ensureCentipawnScore(evaluationBefore);
  const after = ensureCentipawnScore(evaluationAfter);
  const rawLoss = mover === "white" ? before - after : after - before;

  // A move that scores better than the engine's earlier estimate has no loss.
  return Math.max(0, Math.round(rawLoss));
}

export function classifyCentipawnLoss(
  lossInCentipawns,
  thresholds = DEFAULT_CLASSIFICATION_THRESHOLDS,
) {
  if (!Number.isFinite(lossInCentipawns) || lossInCentipawns < 0) {
    throw new Error("Loss must be a non-negative finite number");
  }

  if (lossInCentipawns <= thresholds.best) return "best";
  if (lossInCentipawns <= thresholds.good) return "good";
  if (lossInCentipawns <= thresholds.inaccuracy) return "inaccuracy";
  if (lossInCentipawns <= thresholds.mistake) return "mistake";
  return "blunder";
}

function toMoverPerspectiveMate(evaluation, mover) {
  if (evaluation?.kind !== "mate") return null;
  return mover === "white" ? evaluation.value : -evaluation.value;
}

export function classifyMateChange({ evaluationBefore, evaluationAfter, mover }) {
  const beforeMate = toMoverPerspectiveMate(evaluationBefore, mover);
  const afterMate = toMoverPerspectiveMate(evaluationAfter, mover);

  // The player is now getting mated, regardless of the previous evaluation.
  if (afterMate !== null && afterMate < 0) {
    return { classification: "blunder", mateOutcome: "mated" };
  }

  // A forced mate for the player existed before the move but was lost.
  if (beforeMate !== null && beforeMate > 0 && (afterMate === null || afterMate < 0)) {
    return { classification: "blunder", mateOutcome: "missed-forced-mate" };
  }

  if (beforeMate !== null && beforeMate > 0 && afterMate !== null && afterMate > 0) {
    return { classification: "best", mateOutcome: "preserved-forced-mate" };
  }

  if (afterMate !== null && afterMate > 0) {
    return { classification: "best", mateOutcome: "found-forced-mate" };
  }

  return { classification: "inaccuracy", mateOutcome: "mate-evaluation-changed" };
}

export function analyzeEvaluationChange({
  evaluationBefore,
  evaluationAfter,
  mover,
  thresholds = DEFAULT_CLASSIFICATION_THRESHOLDS,
}) {
  if (evaluationBefore?.kind === "centipawn" && evaluationAfter?.kind === "centipawn") {
    const lossInCentipawns = calculateCentipawnLoss({
      evaluationBefore,
      evaluationAfter,
      mover,
    });

    return {
      classification: classifyCentipawnLoss(lossInCentipawns, thresholds),
      lossInCentipawns,
      mateOutcome: null,
    };
  }

  return {
    ...classifyMateChange({ evaluationBefore, evaluationAfter, mover }),
    lossInCentipawns: undefined,
  };
}

export function buildMoveAnalysis({
  fenBefore,
  fenAfter,
  playedMove,
  bestMove,
  mover,
  evaluationBefore,
  evaluationAfter,
  thresholds = DEFAULT_CLASSIFICATION_THRESHOLDS,
}) {
  const outcome = analyzeEvaluationChange({
    evaluationBefore,
    evaluationAfter,
    mover,
    thresholds,
  });

  return {
    fenBefore,
    fenAfter,
    playedMove,
    bestMove,
    mover,
    evaluationBefore,
    evaluationAfter,
    lossInCentipawns: outcome.lossInCentipawns,
    mateOutcome: outcome.mateOutcome,
    classification: outcome.classification,
  };
}
