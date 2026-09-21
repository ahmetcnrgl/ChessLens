import initEngine from "stockfish";

const fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1";
const engine = await initEngine("lite-single");

engine.listener = (line) => {
  console.log(`[stockfish] ${line}`);
};

engine.sendCommand("uci");
engine.sendCommand("isready");
engine.sendCommand(`position fen ${fen}`);
engine.sendCommand("go depth 10");

setTimeout(() => {
  engine.sendCommand("quit");
}, 10_000);
