import test from "node:test";
import assert from "node:assert/strict";
import {
  analyzeEvaluationChange,
  buildMoveAnalysis,
  calculateCentipawnLoss,
  classifyCentipawnLoss,
} from "../src/analysis/move-analyzer.js";

const cp = (value) => ({ kind: "centipawn", value });

test("calculates white's centipawn loss from before and after evaluations", () => {
  assert.equal(
    calculateCentipawnLoss({
      evaluationBefore: cp(80),
      evaluationAfter: cp(35),
      mover: "white",
    }),
    45,
  );
});

test("calculates black's centipawn loss from the opposite perspective", () => {
  assert.equal(
    calculateCentipawnLoss({
      evaluationBefore: cp(-30),
      evaluationAfter: cp(20),
      mover: "black",
    }),
    50,
  );
});

test("does not produce negative loss when the played move improves the score", () => {
  assert.equal(
    calculateCentipawnLoss({
      evaluationBefore: cp(20),
      evaluationAfter: cp(40),
      mover: "white",
    }),
    0,
  );
});

test("classifies centipawn loss using explicit thresholds", () => {
  assert.equal(classifyCentipawnLoss(10), "best");
  assert.equal(classifyCentipawnLoss(35), "good");
  assert.equal(classifyCentipawnLoss(75), "inaccuracy");
  assert.equal(classifyCentipawnLoss(150), "mistake");
  assert.equal(classifyCentipawnLoss(250), "blunder");
});

test("builds a complete move analysis package", () => {
  const result = buildMoveAnalysis({
    fenBefore: "fen-before",
    fenAfter: "fen-after",
    playedMove: { uci: "e2e4", san: "e4" },
    bestMove: { uci: "d2d4", san: "d4" },
    mover: "white",
    evaluationBefore: cp(80),
    evaluationAfter: cp(35),
  });

  assert.equal(result.lossInCentipawns, 45);
  assert.equal(result.classification, "good");
  assert.equal(result.bestMove.san, "d4");
});

test("does not treat mate scores as centipawns", () => {
  assert.throws(
    () => calculateCentipawnLoss({
      evaluationBefore: { kind: "mate", value: 3 },
      evaluationAfter: cp(50),
      mover: "white",
    }),
    /requires centipawn evaluations/,
  );
});

test("classifies losing a forced mate as a blunder", () => {
  const result = analyzeEvaluationChange({
    evaluationBefore: { kind: "mate", value: 3 },
    evaluationAfter: cp(50),
    mover: "white",
  });

  assert.deepEqual(result, {
    classification: "blunder",
    lossInCentipawns: undefined,
    mateOutcome: "missed-forced-mate",
  });
});

test("classifies moving into a forced mate as a blunder", () => {
  const result = analyzeEvaluationChange({
    evaluationBefore: cp(20),
    evaluationAfter: { kind: "mate", value: -2 },
    mover: "white",
  });

  assert.deepEqual(result, {
    classification: "blunder",
    lossInCentipawns: undefined,
    mateOutcome: "mated",
  });
});

test("keeps a move best when it preserves a forced mate", () => {
  const result = analyzeEvaluationChange({
    evaluationBefore: { kind: "mate", value: 4 },
    evaluationAfter: { kind: "mate", value: 2 },
    mover: "white",
  });

  assert.deepEqual(result, {
    classification: "best",
    lossInCentipawns: undefined,
    mateOutcome: "preserved-forced-mate",
  });
});
