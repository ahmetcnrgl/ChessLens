import test from "node:test";
import assert from "node:assert/strict";
import { Chess } from "chess.js";
import { StockfishAdapter } from "../src/engine/stockfish-adapter.js";

test("analyzes a FEN and returns a legal best move", async () => {
  const fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1";
  const result = await new StockfishAdapter({ timeoutMs: 15_000 }).analyze(fen, {
    depth: 4,
  });
  const game = new Chess(fen);

  assert.match(result.bestMove, /^[a-h][1-8][a-h][1-8][qrbn]?$/);
  assert.doesNotThrow(() => {
    game.move({
      from: result.bestMove.slice(0, 2),
      to: result.bestMove.slice(2, 4),
      promotion: result.bestMove.slice(4) || undefined,
    });
  });
  assert.equal(result.perspective, "white");
  assert.ok(result.depth >= 1);
  assert.ok(result.principalVariation.length >= 1);
});
