import initEngine from "stockfish";

const DEFAULT_DEPTH = 10;

function parseInfo(line) {
  const depth = line.match(/\bdepth (\d+)/)?.[1];
  const score = line.match(/\bscore (cp|mate) (-?\d+)/);
  const pv = line.match(/\bpv (.+)$/)?.[1];

  if (!depth || !score || !pv) return null;

  return {
    depth: Number(depth),
    score: {
      kind: score[1] === "cp" ? "centipawn" : "mate",
      value: Number(score[2]),
    },
    principalVariation: pv.split(" "),
  };
}

export async function analyze(fen, depth = DEFAULT_DEPTH) {
  const engine = await initEngine("lite-single");
  const sideToMove = fen.split(" ")[1] === "w" ? "white" : "black";

  return new Promise((resolve, reject) => {
    let latestInfo = null;
    const timeout = setTimeout(() => {
      engine.sendCommand("quit");
      reject(new Error("Stockfish analysis timed out"));
    }, 15_000);

    engine.listener = (line) => {
      const info = parseInfo(line);
      if (info) latestInfo = info;

      const bestMove = line.match(/^bestmove (\S+)/)?.[1];
      if (!bestMove || !latestInfo) return;

      clearTimeout(timeout);
      engine.sendCommand("quit");
      resolve({ bestMove, perspective: sideToMove, ...latestInfo });
    };

    engine.sendCommand("uci");
    engine.sendCommand("isready");
    engine.sendCommand(`position fen ${fen}`);
    engine.sendCommand(`go depth ${depth}`);
  });
}

const startPosition =
  "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1";

console.log(await analyze(startPosition));
