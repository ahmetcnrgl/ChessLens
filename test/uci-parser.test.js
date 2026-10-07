import test from "node:test";
import assert from "node:assert/strict";
import { parseBestMoveLine, parseInfoLine } from "../src/engine/uci-parser.js";

test("parses a centipawn info line", () => {
  const result = parseInfoLine(
    "info depth 12 seldepth 18 score cp 35 nodes 12345 pv e7e5 g1f3 b8c6",
  );

  assert.deepEqual(result, {
    depth: 12,
    multiPv: 1,
    score: { kind: "centipawn", value: 35 },
    principalVariation: ["e7e5", "g1f3", "b8c6"],
  });
});

test("parses a mate info line", () => {
  const result = parseInfoLine("info depth 18 score mate -3 pv h7h8q");

  assert.deepEqual(result, {
    depth: 18,
    multiPv: 1,
    score: { kind: "mate", value: -3 },
    principalVariation: ["h7h8q"],
  });
});

test("ignores unrelated UCI lines", () => {
  assert.equal(parseInfoLine("uciok"), null);
  assert.equal(parseInfoLine("info string NNUE evaluation"), null);
  assert.equal(parseBestMoveLine("readyok"), null);
});

test("parses a bestmove line", () => {
  assert.equal(parseBestMoveLine("bestmove e7e5 ponder g1f3"), "e7e5");
});
