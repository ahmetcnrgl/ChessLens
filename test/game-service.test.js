import test from "node:test";
import assert from "node:assert/strict";
import { GameService, IllegalMoveError } from "../src/game/game-service.js";

test("legal move is applied and returns the updated state", () => {
  const game = new GameService();

  const result = game.playMove({ from: "e2", to: "e4" });

  assert.equal(result.move.san, "e4");
  assert.equal(result.move.uci, "e2e4");
  assert.equal(result.fenBefore, "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
  assert.equal(result.fenAfter, "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1");
  assert.equal(result.state.turn, "black");
  assert.deepEqual(result.state.history, ["e4"]);
});

test("illegal move is rejected and does not mutate the game", () => {
  const game = new GameService();
  const initialState = game.getState();

  assert.throws(
    () => game.playMove({ from: "e2", to: "e5" }),
    (error) => error instanceof IllegalMoveError && error.code === "ILLEGAL_MOVE",
  );

  assert.deepEqual(game.getState(), initialState);
});

test("a player cannot move the other side's piece", () => {
  const game = new GameService();

  assert.throws(
    () => game.playMove({ from: "e7", to: "e5" }),
    IllegalMoveError,
  );
});

test("a move that exposes its own king to check is rejected", () => {
  const game = new GameService({
    fen: "k3r3/8/8/8/4R3/8/8/4K3 w - - 0 1",
  });

  assert.throws(
    () => game.playMove({ from: "e2", to: "e3" }),
    IllegalMoveError,
  );
});

test("kingside castling is legal when the path is safe", () => {
  const game = new GameService({
    fen: "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",
  });

  const result = game.playMove({ from: "e1", to: "g1" });

  assert.equal(result.move.san, "O-O");
  assert.equal(result.move.uci, "e1g1");
  assert.equal(result.fenAfter, "r3k2r/8/8/8/8/8/8/R4RK1 b kq - 1 1");
});

test("queenside castling is legal when the path is safe", () => {
  const game = new GameService({
    fen: "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",
  });

  const result = game.playMove({ from: "e1", to: "c1" });

  assert.equal(result.move.san, "O-O-O");
  assert.equal(result.move.uci, "e1c1");
  assert.equal(result.fenAfter, "r3k2r/8/8/8/8/8/8/2KR3R b kq - 1 1");
});

test("castling through an attacked square is illegal", () => {
  const game = new GameService({
    fen: "4kr2/8/8/8/8/8/8/4K2R w K - 0 1",
  });

  assert.throws(
    () => game.playMove({ from: "e1", to: "g1" }),
    IllegalMoveError,
  );
});

test("promotion requires a valid promotion piece", () => {
  const game = new GameService({
    fen: "k7/4P3/8/8/8/8/8/4K3 w - - 0 1",
  });

  const result = game.playMove({ from: "e7", to: "e8", promotion: "q" });

  assert.equal(result.move.san, "e8=Q+");
  assert.equal(result.move.uci, "e7e8q");
  assert.equal(result.move.promotion, "q");
  assert.equal(result.state.isCheck, true);
});

test("a pawn cannot move to the last rank without promotion", () => {
  const game = new GameService({
    fen: "k7/4P3/8/8/8/8/8/4K3 w - - 0 1",
  });

  assert.throws(
    () => game.playMove({ from: "e7", to: "e8" }),
    IllegalMoveError,
  );
});

test("en passant is legal immediately after the two-square pawn move", () => {
  const game = new GameService({
    fen: "4k3/7p/8/3pP3/8/8/7P/4K3 w - d6 0 2",
  });

  const result = game.playMove({ from: "e5", to: "d6" });

  assert.equal(result.move.san, "exd6");
  assert.equal(result.fenAfter, "4k3/7p/3P4/8/8/8/7P/4K3 b - - 0 2");
});

test("en passant expires after another move", () => {
  const game = new GameService({
    fen: "4k3/7p/8/3pP3/8/8/7P/4K3 w - d6 0 2",
  });

  game.playMove({ from: "h2", to: "h3" });
  game.playMove({ from: "h7", to: "h6" });

  assert.throws(
    () => game.playMove({ from: "e5", to: "d6" }),
    IllegalMoveError,
  );
});

test("checkmate is exposed in the game state", () => {
  const game = new GameService({
    fen: "7k/6Q1/5K2/8/8/8/8/8 b - - 0 1",
  });

  const state = game.getState();

  assert.equal(state.isCheck, true);
  assert.equal(state.isCheckmate, true);
  assert.equal(state.isStalemate, false);
  assert.equal(state.isGameOver, true);
});

test("stalemate is exposed in the game state", () => {
  const game = new GameService({
    fen: "7k/5Q2/5K2/8/8/8/8/8 b - - 0 1",
  });

  const state = game.getState();

  assert.equal(state.isCheck, false);
  assert.equal(state.isCheckmate, false);
  assert.equal(state.isStalemate, true);
  assert.equal(state.isGameOver, true);
});

test("king-only position is recognized as a draw by insufficient material", () => {
  const game = new GameService({
    fen: "7k/8/8/8/8/8/8/K7 w - - 0 1",
  });

  const state = game.getState();

  assert.equal(state.isDraw, true);
  assert.equal(state.isGameOver, true);
});

test("a position at the fifty-move threshold is recognized as a draw", () => {
  const game = new GameService({
    fen: "8/8/8/8/8/8/2k5/K5R1 w - - 100 1",
  });

  const state = game.getState();

  assert.equal(state.isDraw, true);
  assert.equal(state.isGameOver, true);
});

test("the third occurrence of a position is recognized as a draw", () => {
  const game = new GameService();
  const moves = [
    ["g1", "f3"], ["g8", "f6"], ["f3", "g1"], ["f6", "g8"],
    ["g1", "f3"], ["g8", "f6"], ["f3", "g1"], ["f6", "g8"],
  ];

  for (const [from, to] of moves) game.playMove({ from, to });

  const state = game.getState();

  assert.equal(state.isDraw, true);
  assert.equal(state.isGameOver, true);
});
