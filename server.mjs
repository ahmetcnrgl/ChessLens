import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { GameService } from "./src/game/game-service.js";
import { StockfishAdapter } from "./src/engine/stockfish-adapter.js";
import { buildMoveAnalysis } from "./src/analysis/move-analyzer.js";
import { OllamaAdapter } from "./src/llm/ollama-adapter.js";

const root = resolve(fileURLToPath(new URL(".", import.meta.url)));
const uiRoot = join(root, "ui");
const port = Number(process.env.PORT ?? 4173);
const games = new Map();
const stockfish = new StockfishAdapter();
const ollama = new OllamaAdapter();
const llmEnabled = process.env.LLM_ENABLED === "true";
const ANALYSIS_DEPTH = 12;
const ANALYSIS_SKILL_LEVEL = 20;
// Exact best-move quotas are shuffled once per block so users cannot predict the pattern.
const BOT_MOVE_BLOCK_SIZE = 10;
const BOT_SETTINGS_BY_DIFFICULTY = {
  easy: {
    depth: 4,
    skillLevel: 20,
    multiPv: 8,
    candidatePoolSize: 8,
    bestMovesPerBlock: 3,
  },
  medium: {
    depth: 7,
    skillLevel: 20,
    multiPv: 5,
    candidatePoolSize: 5,
    bestMovesPerBlock: 6,
  },
  hard: {
    depth: 10,
    skillLevel: 20,
    multiPv: 3,
    candidatePoolSize: 3,
    bestMovesPerBlock: 8,
  },
};
let gameCounter = 0;

const opponents = {
  capablanca: { id: "capablanca", name: "José", level: "Kolay bot", difficulty: "easy", face: "avatar-capablanca" },
  judit: { id: "judit", name: "Judit", level: "Orta bot", difficulty: "medium", face: "avatar-judit" },
  magnus: { id: "magnus", name: "Magnus", level: "Zor bot", difficulty: "hard", face: "avatar-magnus" },
};

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
};

function sendJson(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  let raw = "";
  for await (const chunk of request) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

function serializeGame(record) {
  return {
    gameId: record.gameId,
    status: record.game.getState().isGameOver ? "finished" : "active",
    playerColor: record.playerColor,
    opponent: record.opponent,
    lastMoveId: record.lastMoveId,
    ...record.game.getState(),
  };
}

function formatScore(score) {
  if (!score) return "—";
  if (score.kind === "mate") return `${score.value > 0 ? "+" : "-"}M${Math.abs(score.value)}`;
  return `${score.value >= 0 ? "+" : ""}${(score.value / 100).toFixed(2)}`;
}

function scoreToWhitePercent(score) {
  if (!score) return 50;
  if (score.kind === "mate") return score.value > 0 ? 100 : 0;
  return Math.max(0, Math.min(100, Math.round(50 + score.value / 20)));
}

function uciToMove(uci) {
  return {
    from: uci.slice(0, 2),
    to: uci.slice(2, 4),
    promotion: uci.slice(4) || undefined,
  };
}

function makeBotMoveSchedule(bestMovesPerBlock) {
  const schedule = Array.from({ length: BOT_MOVE_BLOCK_SIZE }, (_, index) => index < bestMovesPerBlock);
  for (let index = schedule.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [schedule[index], schedule[swapIndex]] = [schedule[swapIndex], schedule[index]];
  }
  return schedule;
}

function chooseBotMove(record, botAnalysis, settings) {
  let candidates = [...new Set(botAnalysis.candidateMoves?.length
    ? botAnalysis.candidateMoves
    : [botAnalysis.bestMove])].filter(Boolean);
  if (botAnalysis.bestMove) {
    candidates = [botAnalysis.bestMove, ...candidates.filter((move) => move !== botAnalysis.bestMove)];
  }
  if (candidates.length < 2) return candidates[0] ?? botAnalysis.bestMove;

  if (!record.botMoveSchedule.length) {
    record.botMoveSchedule = makeBotMoveSchedule(settings.bestMovesPerBlock);
  }
  const playBest = record.botMoveSchedule.shift();
  if (playBest) return candidates[0];

  const weakerCandidates = candidates.slice(1, settings.candidatePoolSize);
  return weakerCandidates[Math.floor(Math.random() * weakerCandidates.length)] ?? candidates[0];
}

function getMoveDetails(fen, uci) {
  const preview = new GameService({ fen });
  return preview.playMove(uciToMove(uci)).move;
}

function buildFallbackCoach(moveAnalysis, engineMove) {
  const messages = {
    best: `${moveAnalysis.playedMove.san} güçlü bir seçim. Motorun ilk tercihine çok yakın kaldın.`,
    good: `${moveAnalysis.playedMove.san} konumu koruyan iyi bir hamle.`,
    inaccuracy: `${moveAnalysis.playedMove.san} oynanabilir; ancak ${moveAnalysis.bestMove.san} daha etkin bir plandı.`,
    mistake: `${moveAnalysis.playedMove.san} rakibe gereğinden fazla fırsat verdi. ${moveAnalysis.bestMove.san} konumu daha sağlam tutuyordu.`,
    blunder: `${moveAnalysis.playedMove.san} önemli bir fırsatı kaçırdı. Burada önce ${moveAnalysis.bestMove.san} hamlesini incele.`,
  };
  return {
    text: `${messages[moveAnalysis.classification] ?? "Hamleni birlikte inceleyelim."} Benzer bir konumda önce rakibin tehdidini, sonra en aktif iki aday hamleni karşılaştır.`,
    betterMove: moveAnalysis.bestMove.san,
    source: "fallback",
  };
}

async function buildCoachResponse(moveAnalysis, engineMove) {
  const fallback = buildFallbackCoach(moveAnalysis, engineMove);
  if (!llmEnabled) return fallback;

  try {
    const explanation = await ollama.explain({
      moveAnalysis,
      engineMove: engineMove?.move ?? null,
    });
    return {
      text: `${explanation.summary} ${explanation.explanation}`,
      betterMove: explanation.betterMove,
      source: "ollama",
      tone: explanation.tone,
    };
  } catch (error) {
    console.warn(`Ollama coach unavailable; using fallback: ${error.message}`);
    return fallback;
  }
}

async function handleApi(request, response, url) {
  if (request.method === "GET" && url.pathname === "/api/opponents") {
    sendJson(response, 200, { opponents });
    return true;
  }

  if (request.method === "POST" && url.pathname === "/api/games") {
    const body = await readJson(request);
    const opponent = opponents[body.opponentId] ?? opponents.judit;
    const gameId = `game-${++gameCounter}`;
    const record = {
      gameId,
      game: new GameService(),
      opponent,
      playerColor: body.playerColor ?? "white",
      botMoveSchedule: [],
      lastMoveId: null,
      lastAnalysis: null,
    };
    games.set(gameId, record);
    sendJson(response, 201, serializeGame(record));
    return true;
  }

  const gameMatch = url.pathname.match(/^\/api\/games\/([^/]+)$/);
  if (request.method === "GET" && gameMatch) {
    const record = games.get(gameMatch[1]);
    if (!record) {
      sendJson(response, 404, { error: "GAME_NOT_FOUND" });
      return true;
    }
    sendJson(response, 200, serializeGame(record));
    return true;
  }

  const moveMatch = url.pathname.match(/^\/api\/games\/([^/]+)\/moves$/);
  if (request.method === "POST" && moveMatch) {
    const record = games.get(moveMatch[1]);
    if (!record) {
      sendJson(response, 404, { error: "GAME_NOT_FOUND" });
      return true;
    }

    const body = await readJson(request);
    const stateBefore = record.game.getState();
    if (stateBefore.turn !== record.playerColor) {
      sendJson(response, 409, { error: "NOT_PLAYER_TURN" });
      return true;
    }

    try {
      const beforeAnalysis = await stockfish.analyze(stateBefore.fen, {
        depth: ANALYSIS_DEPTH,
        skillLevel: ANALYSIS_SKILL_LEVEL,
      });
      const played = record.game.playMove(body);
      const afterAnalysis = await stockfish.analyze(played.fenAfter, {
        depth: ANALYSIS_DEPTH,
        skillLevel: ANALYSIS_SKILL_LEVEL,
      });
      const moveAnalysis = buildMoveAnalysis({
        fenBefore: stateBefore.fen,
        fenAfter: played.fenAfter,
        playedMove: played.move,
        bestMove: getMoveDetails(stateBefore.fen, beforeAnalysis.bestMove),
        mover: stateBefore.turn,
        evaluationBefore: beforeAnalysis.score,
        evaluationAfter: afterAnalysis.score,
      });

      let engineMove = null;
      let coachReply = null;
      if (!played.state.isGameOver && afterAnalysis.bestMove !== "0000") {
        coachReply = getMoveDetails(played.fenAfter, afterAnalysis.bestMove);
        const botSettings = BOT_SETTINGS_BY_DIFFICULTY[record.opponent.difficulty] ?? BOT_SETTINGS_BY_DIFFICULTY.medium;
        const botAnalysis = await stockfish.analyze(played.fenAfter, {
          depth: botSettings.depth,
          skillLevel: botSettings.skillLevel,
          multiPv: botSettings.multiPv,
        });
        if (botAnalysis.bestMove !== "0000") {
          const selectedMove = chooseBotMove(record, botAnalysis, botSettings);
          engineMove = record.game.playMove(uciToMove(selectedMove));
        }
      }

      const coach = await buildCoachResponse(moveAnalysis, coachReply ? { move: coachReply } : null);

      record.lastMoveId = `${record.gameId}-move-${Date.now()}`;
      record.lastAnalysis = { moveAnalysis, coach };
      const finalState = serializeGame(record);
      sendJson(response, 200, {
        ...finalState,
        moveId: record.lastMoveId,
        playedMove: played.move,
        engineMove: engineMove?.move ?? null,
        analysis: {
          classification: moveAnalysis.classification,
          score: formatScore(moveAnalysis.evaluationAfter),
          whitePercent: scoreToWhitePercent(moveAnalysis.evaluationAfter),
          bestMove: moveAnalysis.bestMove,
          lossInCentipawns: moveAnalysis.lossInCentipawns ?? null,
          mateOutcome: moveAnalysis.mateOutcome,
          principalVariation: afterAnalysis.principalVariation,
        },
        coach,
        gameState: finalState,
      });
    } catch (error) {
      if (error.code === "ILLEGAL_MOVE") {
        sendJson(response, 400, { error: error.code, message: error.message });
      } else {
        console.error(error);
        sendJson(response, 500, { error: "MOVE_FAILED" });
      }
    }
    return true;
  }

  const coachMatch = url.pathname.match(/^\/api\/games\/([^/]+)\/coach$/);
  if (request.method === "POST" && coachMatch) {
    const record = games.get(coachMatch[1]);
    if (!record) {
      sendJson(response, 404, { error: "GAME_NOT_FOUND" });
      return true;
    }
    const body = await readJson(request);
    const latest = record.lastAnalysis;
    if (!latest) {
      sendJson(response, 200, {
        text: "Henüz inceleyeceğimiz bir hamle yok. İlk hamleni yaptıktan sonra birlikte değerlendirebiliriz.",
        betterMove: null,
      });
      return true;
    }
    const question = String(body.question ?? "").toLocaleLowerCase("tr");
    const { moveAnalysis, coach } = latest;
    let text = coach.text;
    if (/üstün|önde|avantaj/.test(question)) {
      text = `Motor değerlendirmesi ${formatScore(moveAnalysis.evaluationAfter)}. Artı değer beyazın, eksi değer siyahın lehine; bu sayı kazanma yüzdesi değildir.`;
    } else if (/açıkla|neden|iyi|kötü/.test(question)) {
      const loss = moveAnalysis.lossInCentipawns;
      text = loss === undefined
        ? coach.text
        : `${coach.text} Bu sınıflandırma, hamlenin motorun en iyi seçimine göre yaklaşık ${loss} centipawn kaybetmesine dayanıyor.`;
    }
    sendJson(response, 200, {
      text,
      betterMove: coach.betterMove ?? null,
      moveId: record.lastMoveId,
    });
    return true;
  }

  return false;
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${port}`);

  try {
    if (url.pathname.startsWith("/api/")) {
      const handled = await handleApi(request, response, url);
      if (!handled) sendJson(response, 404, { error: "NOT_FOUND" });
      return;
    }

    const requestedPath = url.pathname === "/" ? "/index.html" : url.pathname;
    const filePath = normalize(join(uiRoot, requestedPath));
    if (!filePath.startsWith(uiRoot)) {
      response.writeHead(403);
      response.end("Forbidden");
      return;
    }

    const body = await readFile(filePath);
    response.writeHead(200, { "Content-Type": mimeTypes[extname(filePath)] ?? "application/octet-stream" });
    response.end(body);
  } catch (error) {
    if (error instanceof SyntaxError) sendJson(response, 400, { error: "INVALID_JSON" });
    else {
      response.writeHead(404);
      response.end("Not found");
    }
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`ChessLens app: http://127.0.0.1:${port}`);
});
