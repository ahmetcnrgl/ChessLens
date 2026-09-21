import { Chess } from "chess.js";

const game = new Chess();

// Aynı pozisyonu üç farklı amaçla görüyoruz:
// - FEN: tahtanın anlık, makine-okur durumu
// - SAN: insanın hamle listesinde gördüğü gösterim
// - UCI: motorların hamleyi kaynak-hedef kareleriyle ifade ettiği gösterim
const move = game.move({ from: "e2", to: "e4" });

console.log({
  fenAfterMove: game.fen(),
  san: move.san,
  uci: `${move.from}${move.to}${move.promotion ?? ""}`,
  sanHistory: game.history().join(" "),
  pgn: game.pgn(),
});
