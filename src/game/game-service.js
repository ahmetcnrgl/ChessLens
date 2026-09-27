import { Chess } from "chess.js";

export class IllegalMoveError extends Error {
  constructor(message = "Illegal chess move") {
    super(message);
    this.name = "IllegalMoveError";
    this.code = "ILLEGAL_MOVE";
  }
}

function colorFromTurn(turn) {
  return turn === "w" ? "white" : "black";
}

function toUci(move) {
  return `${move.from}${move.to}${move.promotion ?? ""}`;
}

export class GameService {
  constructor({ fen } = {}) {
    this.chess = fen ? new Chess(fen) : new Chess();
  }

  getState() {
    return {
      fen: this.chess.fen(),
      turn: colorFromTurn(this.chess.turn()),
      history: this.chess.history(),
      position: this.getPosition(),
      legalMoves: this.getLegalMoves(),
      isCheck: this.chess.isCheck(),
      isCheckmate: this.chess.isCheckmate(),
      isStalemate: this.chess.isStalemate(),
      isDraw: this.chess.isDraw(),
      isGameOver: this.chess.isGameOver(),
    };
  }

  getPosition() {
    const position = {};
    const files = ["a", "b", "c", "d", "e", "f", "g", "h"];

    this.chess.board().forEach((rank, rankIndex) => {
      rank.forEach((piece, fileIndex) => {
        if (!piece) return;
        position[`${files[fileIndex]}${8 - rankIndex}`] = `${piece.color}${piece.type}`;
      });
    });

    return position;
  }

  getLegalMoves() {
    return this.chess.moves({ verbose: true }).map((move) => ({
      from: move.from,
      to: move.to,
      promotion: move.promotion ?? null,
      san: move.san,
      uci: toUci(move),
    }));
  }

  playMove({ from, to, promotion } = {}) {
    const fenBefore = this.chess.fen();

    let move;
    try {
      move = this.chess.move({
        from,
        to,
        ...(promotion ? { promotion } : {}),
      });
    } catch {
      throw new IllegalMoveError(`Illegal move: ${from ?? "?"}${to ?? "?"}`);
    }

    if (!move) {
      throw new IllegalMoveError(`Illegal move: ${from ?? "?"}${to ?? "?"}`);
    }

    return {
      fenBefore,
      fenAfter: this.chess.fen(),
      move: {
        from: move.from,
        to: move.to,
        promotion: move.promotion ?? null,
        captured: move.captured ?? null,
        san: move.san,
        uci: toUci(move),
      },
      state: this.getState(),
    };
  }
}
