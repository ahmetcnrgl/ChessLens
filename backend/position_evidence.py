"""Position facts derived from legal moves, independent of named tactics."""

from __future__ import annotations

from typing import Literal

import chess


MoveStatus = Literal["actual", "hypothetical"]


def compact_evidence(evidence: dict) -> dict:
    """Keep the verified events without repeating board snapshots in prompts."""
    return {key: evidence[key] for key in (
        "status", "move", "captured", "checksKing", "checkmate", "newAttacks",
        "legalCapturesOfMovedPiece", "evidenceLevel",
    )}


def _piece_at(board: chess.Board, square: chess.Square) -> dict:
    piece = board.piece_at(square)
    assert piece is not None
    return {
        "square": chess.square_name(square),
        "piece": chess.piece_name(piece.piece_type),
        "color": "white" if piece.color == chess.WHITE else "black",
    }


def observe_move(fen: str, uci: str, status: MoveStatus) -> dict:
    """Observe board changes after one legal move, without judging its quality.

    Attack sets are geometric. A target being attacked does not prove that it
    can be captured safely, and a legal capture reply is only one defense.
    The caller supplies whether the move was played or merely considered.
    """
    if status not in ("actual", "hypothetical"):
        raise ValueError("Move status must be actual or hypothetical")

    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError("Invalid chess position")
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise ValueError(f"Illegal move: {uci}")

    mover = board.piece_at(move.from_square)
    mover_color = mover.color
    previously_attacked = {
        square for square, piece in board.piece_map().items()
        if piece.color != mover_color and board.is_attacked_by(mover_color, square)
    }
    captured_square = move.to_square
    if board.is_en_passant(move):
        captured_square += -8 if mover_color == chess.WHITE else 8
    captured = _piece_at(board, captured_square) if board.is_capture(move) else None

    board.push(move)
    new_attacks = []
    for square, piece in sorted(board.piece_map().items()):
        if piece.color == mover_color or square in previously_attacked:
            continue
        if board.is_attacked_by(mover_color, square):
            new_attacks.append({
                "target": _piece_at(board, square),
                "attackers": [chess.square_name(source) for source in sorted(board.attackers(mover_color, square))],
            })

    legal_captures_of_moved_piece = [
        reply.uci() for reply in board.legal_moves
        if board.is_capture(reply) and (
            reply.to_square == move.to_square
            or (board.is_en_passant(reply) and
                reply.to_square + (-8 if board.turn == chess.WHITE else 8) == move.to_square)
        )
    ]
    return {
        "fenBefore": fen,
        "fenAfter": board.fen(),
        "status": status,
        "move": {
            "uci": move.uci(),
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "piece": chess.piece_name(mover.piece_type),
            "color": "white" if mover_color == chess.WHITE else "black",
        },
        "captured": captured,
        "checksKing": board.is_check(),
        "checkmate": board.is_checkmate(),
        "newAttacks": new_attacks,
        "legalCapturesOfMovedPiece": legal_captures_of_moved_piece,
        "evidenceLevel": "board_observation_only",
    }
