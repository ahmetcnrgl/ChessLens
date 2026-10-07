from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import chess


class IllegalMoveError(ValueError):
    """Raised when a requested move is not legal in the current position."""


def color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


def move_to_dict(board: chess.Board, move: chess.Move) -> dict:
    return {
        "from": chess.square_name(move.from_square),
        "to": chess.square_name(move.to_square),
        "promotion": chess.piece_symbol(move.promotion) if move.promotion else None,
        "captured": board.piece_at(move.to_square).symbol() if board.is_capture(move) and board.piece_at(move.to_square) else None,
        "san": board.san(move),
        "uci": move.uci(),
    }


@dataclass
class GameService:
    board: chess.Board
    san_history: list[str] | None = None

    @classmethod
    def new(cls, fen: str | None = None) -> "GameService":
        return cls(chess.Board(fen) if fen else chess.Board(), [])

    def position(self) -> dict[str, str]:
        return {
            chess.square_name(square): piece.color and f"w{piece.symbol().lower()}" or f"b{piece.symbol().lower()}"
            for square, piece in self.board.piece_map().items()
        }

    def legal_moves(self) -> list[dict]:
        return [move_to_dict(self.board, move) for move in self.board.legal_moves]

    def state(self) -> dict:
        return {
            "fen": self.board.fen(),
            "turn": color_name(self.board.turn),
            "history": self.san_history or [],
            "position": self.position(),
            "legalMoves": self.legal_moves(),
            "isCheck": self.board.is_check(),
            "isCheckmate": self.board.is_checkmate(),
            "isStalemate": self.board.is_stalemate(),
            "isDraw": self.board.is_fifty_moves() or self.board.is_insufficient_material() or self.board.is_repetition(3),
            "isGameOver": self.board.is_game_over(),
        }

    def play_move(self, from_square: str, to_square: str, promotion: str | None = None) -> dict:
        fen_before = self.board.fen()
        uci = f"{from_square}{to_square}{promotion or ''}"
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as error:
            raise IllegalMoveError(f"Illegal move: {uci}") from error

        if move not in self.board.legal_moves:
            raise IllegalMoveError(f"Illegal move: {uci}")

        details = move_to_dict(self.board, move)
        self.board.push(move)
        if self.san_history is None:
            self.san_history = []
        self.san_history.append(details["san"])
        return {
            "fenBefore": fen_before,
            "fenAfter": self.board.fen(),
            "move": details,
            "state": self.state(),
        }


@dataclass
class GameRecord:
    game_id: str
    game: GameService
    player_color: str
    opponent: dict
    last_move_id: str | None = None
    bot_move_schedule: list[bool] = field(default_factory=list)
    last_analysis: dict | None = None
    last_engine_reply: dict | None = None
    last_coach: dict | None = None
    coach_history: list[dict[str, str]] = field(default_factory=list)
    coach_focus: str = "last-move"

    @classmethod
    def create(cls, player_color: str, opponent: dict) -> "GameRecord":
        return cls(str(uuid4()), GameService.new(), player_color, opponent)
