"""Board-verified tactical observations, without claims about forced outcomes."""

from __future__ import annotations

import chess


def detect_knight_fork(fen: str, uci: str) -> dict | None:
    """Report a legal knight move attacking two non-pawn enemy pieces.

    This is geometric evidence only. It does not establish that either target
    can be captured safely or that the opponent will lose material.
    """
    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError("Invalid chess position")

    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise ValueError(f"Illegal move: {uci}")

    attacker = board.piece_at(move.from_square)
    if attacker.piece_type != chess.KNIGHT:
        return None

    board.push(move)
    targets = []
    for square in sorted(board.attacks(move.to_square)):
        piece = board.piece_at(square)
        if piece and piece.color != attacker.color and piece.piece_type != chess.PAWN:
            targets.append({
                "square": chess.square_name(square),
                "piece": chess.piece_name(piece.piece_type),
                "color": "white" if piece.color == chess.WHITE else "black",
            })

    if len(targets) < 2:
        return None

    return {
        "motif": "knight_fork",
        "attackerColor": "white" if attacker.color == chess.WHITE else "black",
        "from": chess.square_name(move.from_square),
        "to": chess.square_name(move.to_square),
        "targets": targets,
        "checksKing": any(target["piece"] == "king" for target in targets),
        "evidenceLevel": "attacked_targets_only",
    }


def find_opponent_knight_forks(fen: str, candidate_uci: str) -> list[dict]:
    """Find legal one-move knight forks after a proposed move.

    Returned replies are possibilities, not moves the opponent has played or
    proof that the proposed move should be rejected.
    """
    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError("Invalid chess position")

    candidate = chess.Move.from_uci(candidate_uci)
    if candidate not in board.legal_moves:
        raise ValueError(f"Illegal move: {candidate_uci}")
    board.push(candidate)

    reply_fen = board.fen()
    forks = []
    for reply in list(board.legal_moves):
        piece = board.piece_at(reply.from_square)
        if piece.piece_type != chess.KNIGHT:
            continue
        evidence = detect_knight_fork(reply_fen, reply.uci())
        if evidence is not None:
            forks.append({
                "status": "hypothetical",
                "candidateMove": candidate_uci,
                "opponentMove": reply.uci(),
                "evidence": evidence,
            })
    return forks
