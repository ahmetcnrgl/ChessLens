import test from "node:test";
import assert from "node:assert/strict";
import { OllamaAdapter } from "../src/llm/ollama-adapter.js";
import { buildCoachPrompt, validateCoachExplanation } from "../src/llm/coach-explanation.js";

const moveAnalysis = {
  classification: "inaccuracy",
  playedMove: { san: "Nc3" },
  bestMove: { san: "d4" },
  lossInCentipawns: 48,
  mateOutcome: null,
  mover: "white",
};

test("coach prompt sends only trusted move-analysis fields", () => {
  const prompt = buildCoachPrompt({ moveAnalysis, engineMove: { san: "e5" } });
  const input = JSON.parse(prompt.user);

  assert.deepEqual(input, {
    classification: "inaccuracy",
    playedMove: "Nc3",
    betterMove: "d4",
    lossInCentipawns: 48,
    mateOutcome: null,
    mover: "white",
    engineReply: "e5",
  });
  assert.match(prompt.system, /yalnızca.*JSON/i);
});

test("Ollama adapter parses and validates a JSON response", async () => {
  const adapter = new OllamaAdapter({
    model: "test-model",
    fetchImpl: async (url, options) => {
      assert.equal(url, "http://ollama.test/api/chat");
      const body = JSON.parse(options.body);
      assert.equal(body.model, "test-model");
      assert.equal(body.stream, false);
      return new Response(JSON.stringify({
        message: {
          content: JSON.stringify({
            summary: "Merkez için d4 daha güçlüydü.",
            explanation: "d4 merkeze alan kazandırır.",
            betterMove: "d4",
            tone: "corrective",
          }),
        },
      }), { status: 200 });
    },
    baseUrl: "http://ollama.test",
  });

  await assert.doesNotReject(async () => {
    const result = await adapter.explain({ moveAnalysis, engineMove: { san: "e5" } });
    assert.equal(result.betterMove, "d4");
    assert.equal(result.tone, "corrective");
  });
});

test("invalid coach output is rejected before it reaches the UI", () => {
  assert.throws(
    () => validateCoachExplanation({ summary: "Eksik" }),
    /Coach response field is invalid/,
  );
});
