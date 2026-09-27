import initEngine from "stockfish";
import { parseBestMoveLine, parseInfoLine } from "./uci-parser.js";

const DEFAULT_DEPTH = 10;
const DEFAULT_TIMEOUT_MS = 15_000;
const DEFAULT_SKILL_LEVEL = 20;

export class StockfishAnalysisError extends Error {
  constructor(message) {
    super(message);
    this.name = "StockfishAnalysisError";
  }
}

function toWhitePerspective(score, sideToMove) {
  if (!score || sideToMove === "white") return score;

  return {
    ...score,
    value: -score.value,
  };
}

export class StockfishAdapter {
  constructor({ engineFactory = initEngine, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
    this.engineFactory = engineFactory;
    this.timeoutMs = timeoutMs;
    this.enginePromise = null;
    this.analysisQueue = Promise.resolve();
  }

  async analyze(fen, { depth = DEFAULT_DEPTH, skillLevel = DEFAULT_SKILL_LEVEL, multiPv = 1 } = {}) {
    if (!Number.isInteger(skillLevel) || skillLevel < 0 || skillLevel > 20) {
      throw new RangeError("Stockfish skillLevel must be an integer from 0 to 20");
    }
    if (!Number.isInteger(multiPv) || multiPv < 1 || multiPv > 20) {
      throw new RangeError("Stockfish multiPv must be an integer from 1 to 20");
    }

    const run = () => this.analyzeOnce(fen, depth, skillLevel, multiPv);
    const result = this.analysisQueue.then(run, run);
    this.analysisQueue = result.catch(() => undefined);
    return result;
  }

  async getEngine() {
    if (!this.enginePromise) {
      this.enginePromise = this.engineFactory("lite-single");
    }
    return this.enginePromise;
  }

  async analyzeOnce(fen, depth, skillLevel, multiPv) {
    const engine = await this.getEngine();
    const sideToMove = fen.split(/\s+/)[1] === "w" ? "white" : "black";

    return new Promise((resolve, reject) => {
      let latestInfoDepth = -1;
      let latestInfos = new Map();
      let settled = false;

      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        callback(value);
      };

      const timeout = setTimeout(() => {
        engine.sendCommand("stop");
        finish(reject, new StockfishAnalysisError("Stockfish analysis timed out"));
      }, this.timeoutMs);

      engine.listener = (line) => {
        if (line === "readyok") {
          engine.sendCommand(`position fen ${fen}`);
          engine.sendCommand(`go depth ${depth}`);
          return;
        }

        const info = parseInfoLine(line);
        if (info) {
          if (info.depth > latestInfoDepth) {
            latestInfoDepth = info.depth;
            latestInfos = new Map();
          }
          if (info.depth === latestInfoDepth) latestInfos.set(info.multiPv, info);
        }

        if (!parseBestMoveLine(line)) return;

        const bestMove = parseBestMoveLine(line);
        const candidates = [...latestInfos.entries()]
          .sort(([leftRank], [rightRank]) => leftRank - rightRank)
          .map(([, candidate]) => candidate.principalVariation[0])
          .filter(Boolean);
        if (!candidates.includes(bestMove)) candidates.unshift(bestMove);
        const primaryInfo = latestInfos.get(1) ?? latestInfos.values().next().value ?? null;
        finish(resolve, {
          bestMove,
          candidateMoves: [...new Set(candidates)],
          score: toWhitePerspective(primaryInfo?.score ?? null, sideToMove),
          depth: primaryInfo?.depth ?? null,
          principalVariation: primaryInfo?.principalVariation ?? [],
          perspective: "white",
        });
      };

      engine.sendCommand(`setoption name Skill Level value ${skillLevel}`);
      engine.sendCommand(`setoption name MultiPV value ${multiPv}`);
      engine.sendCommand("isready");
    });
  }
}
