import { GameService } from "../src/game/game-service.js";
import { StockfishAdapter } from "../src/engine/stockfish-adapter.js";

const game = new GameService();
const engine = new StockfishAdapter();

console.log("Başlangıç:");
console.log(game.getState());

const humanMove = game.playMove({ from: "e2", to: "e4" });
console.log("\nİnsan hamlesi:");
console.log(humanMove.move);

const analysis = await engine.analyze(humanMove.fenAfter, { depth: 6 });
console.log("\nStockfish analizi:");
console.log(analysis);

const engineMove = game.playMove({
  from: analysis.bestMove.slice(0, 2),
  to: analysis.bestMove.slice(2, 4),
  promotion: analysis.bestMove.slice(4) || undefined,
});

console.log("\nMotor hamlesi:");
console.log(engineMove.move);

console.log("\nSon durum:");
console.log(game.getState());
