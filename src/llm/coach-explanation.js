const COACH_RESPONSE_SCHEMA = Object.freeze({
  type: "object",
  additionalProperties: false,
  required: ["summary", "explanation", "betterMove", "tone"],
  properties: {
    summary: { type: "string" },
    explanation: { type: "string" },
    betterMove: { type: "string" },
    tone: { type: "string", enum: ["encouraging", "neutral", "corrective"] },
  },
});

export function buildCoachPrompt({ moveAnalysis, engineMove }) {
  const input = {
    classification: moveAnalysis.classification,
    playedMove: moveAnalysis.playedMove.san,
    betterMove: moveAnalysis.bestMove.san,
    lossInCentipawns: moveAnalysis.lossInCentipawns ?? null,
    mateOutcome: moveAnalysis.mateOutcome,
    mover: moveAnalysis.mover,
    engineReply: engineMove?.san ?? null,
  };

  return {
    system: [
      "Sen ChessLens adlı satranç koçusun.",
      "Stockfish tarafından hesaplanan verileri değiştirme ve yeni bir hamle uydurma.",
      "Sadece verilen hamle analizini, yeni başlayan bir oyuncunun anlayacağı Türkçeyle açıkla.",
      "Yanıtı yalnızca istenen JSON formatında ver; markdown veya ek metin kullanma.",
    ].join(" "),
    user: JSON.stringify(input),
  };
}

export function validateCoachExplanation(value) {
  if (!value || typeof value !== "object") throw new Error("Coach response must be an object");

  for (const field of ["summary", "explanation", "betterMove", "tone"]) {
    if (typeof value[field] !== "string" || value[field].trim() === "") {
      throw new Error(`Coach response field is invalid: ${field}`);
    }
  }

  if (!["encouraging", "neutral", "corrective"].includes(value.tone)) {
    throw new Error("Coach response tone is invalid");
  }

  return {
    summary: value.summary.trim(),
    explanation: value.explanation.trim(),
    betterMove: value.betterMove.trim(),
    tone: value.tone,
  };
}

export function getCoachResponseSchema() {
  return COACH_RESPONSE_SCHEMA;
}
