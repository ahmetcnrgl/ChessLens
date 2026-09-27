import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const port = 4181;
const baseUrl = `http://127.0.0.1:${port}`;
let serverProcess;
let game;

async function waitForServer() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/opponents`);
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await delay(100);
  }
  throw new Error("Test server did not start in time");
}

async function request(path, options) {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return {
    status: response.status,
    body: await response.json(),
  };
}

before(async () => {
  serverProcess = spawn(process.execPath, ["server.mjs"], {
    cwd: projectRoot,
    env: { ...process.env, PORT: String(port) },
    stdio: "ignore",
  });
  await waitForServer();
});

after(() => {
  serverProcess?.kill();
});

test("POST /api/games creates a server-owned game", async () => {
  const result = await request("/api/games", {
    method: "POST",
    body: JSON.stringify({ opponentId: "judit", playerColor: "white" }),
  });

  game = result.body;

  assert.equal(result.status, 201);
  assert.match(game.gameId, /^game-/);
  assert.equal(game.status, "active");
  assert.equal(game.turn, "white");
  assert.equal(game.position.e2, "wp");
  assert.ok(game.legalMoves.some((move) => move.uci === "e2e4"));
});

test("POST /api/games/:gameId/moves applies a legal move and returns an engine reply", async () => {
  const result = await request(`/api/games/${game.gameId}/moves`, {
    method: "POST",
    body: JSON.stringify({ from: "e2", to: "e4", promotion: null }),
  });

  assert.equal(result.status, 200);
  assert.equal(result.body.playedMove.uci, "e2e4");
  assert.match(result.body.engineMove.uci, /^[a-h][1-8][a-h][1-8][qrbn]?$/);
  assert.ok(["best", "good", "inaccuracy", "mistake", "blunder"].includes(result.body.analysis.classification));
  assert.equal(typeof result.body.analysis.bestMove.san, "string");
  assert.equal(typeof result.body.analysis.lossInCentipawns, "number");
  assert.equal(result.body.gameState.history[0], "e4");
  assert.equal(result.body.gameState.turn, "white");
  assert.equal(result.body.gameState.position.e4, "wp");
  assert.equal(result.body.gameState.position.e2, undefined);
});

test("illegal move returns 400 and leaves the game unchanged", async () => {
  const before = await request(`/api/games/${game.gameId}`, { method: "GET" });

  const invalid = await request(`/api/games/${game.gameId}/moves`, {
    method: "POST",
    body: JSON.stringify({ from: "e2", to: "e5", promotion: null }),
  });
  const afterInvalid = await request(`/api/games/${game.gameId}`, { method: "GET" });

  assert.equal(invalid.status, 400);
  assert.equal(invalid.body.error, "ILLEGAL_MOVE");
  assert.equal(afterInvalid.body.fen, before.body.fen);
  assert.deepEqual(afterInvalid.body.history, before.body.history);
});
