import chess
import pytest

from backend.tactics import detect_knight_fork, find_opponent_knight_forks


F1 = "4k3/7p/8/8/1n6/8/7P/R3K3 b Q - 0 1"
F2 = "4k3/7p/8/8/1n6/8/7P/R3K3 w Q - 0 1"
F3 = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
F4 = "4k3/7p/8/8/1n6/8/7P/4K3 b - - 0 1"
F5 = "r3k3/7p/8/1N6/8/8/7P/4K3 w q - 0 1"
F6 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"


def test_black_knight_checks_king_and_attacks_rook():
    evidence = detect_knight_fork(F1, "b4c2")

    assert evidence == {
        "motif": "knight_fork",
        "attackerColor": "black",
        "from": "b4",
        "to": "c2",
        "targets": [
            {"square": "a1", "piece": "rook", "color": "white"},
            {"square": "e1", "piece": "king", "color": "white"},
        ],
        "checksKing": True,
        "evidenceLevel": "attacked_targets_only",
    }


def test_candidate_move_can_leave_fork_available_or_remove_second_target():
    board = chess.Board(F2)
    board.push_uci("h2h3")
    assert detect_knight_fork(board.fen(), "b4c2") is not None

    board = chess.Board(F2)
    board.push_uci("a1b1")
    assert detect_knight_fork(board.fen(), "b4c2") is None


def test_defensible_fork_reports_attacks_not_material_loss():
    evidence = detect_knight_fork(F3, "b4c2")
    assert {(target["square"], target["piece"]) for target in evidence["targets"]} == {
        ("a1", "rook"), ("e3", "queen")
    }
    assert evidence["checksKing"] is False
    assert evidence["evidenceLevel"] == "attacked_targets_only"

    board = chess.Board(F3)
    board.push_uci("b4c2")
    assert chess.Move.from_uci("f5c2") in board.legal_moves


def test_single_target_is_not_a_fork():
    assert detect_knight_fork(F4, "b4c2") is None


def test_normal_development_does_not_invent_a_fork():
    assert detect_knight_fork(F6, "g1f3") is None


def test_white_knight_fork_has_correct_perspective():
    evidence = detect_knight_fork(F5, "b5c7")
    assert evidence["attackerColor"] == "white"
    assert {(target["square"], target["piece"], target["color"]) for target in evidence["targets"]} == {
        ("a8", "rook", "black"), ("e8", "king", "black")
    }
    assert evidence["checksKing"] is True


def test_rejects_illegal_moves_and_does_not_call_a_pawn_move_a_knight_fork():
    with pytest.raises(ValueError, match="Illegal move"):
        detect_knight_fork(F1, "b4b5")
    assert detect_knight_fork(F2, "h2h3") is None


def test_candidate_move_exposes_a_hypothetical_opponent_fork():
    forks = find_opponent_knight_forks(F2, "h2h3")
    fork = next(item for item in forks if item["opponentMove"] == "b4c2")
    assert fork["status"] == "hypothetical"
    assert fork["candidateMove"] == "h2h3"
    assert fork["evidence"]["checksKing"] is True
    assert {target["square"] for target in fork["evidence"]["targets"]} == {"a1", "e1"}


def test_moving_the_rook_avoids_that_specific_fork():
    forks = find_opponent_knight_forks(F2, "a1b1")
    assert not any(item["opponentMove"] == "b4c2" for item in forks)


def test_candidate_search_rejects_a_move_the_player_cannot_make():
    with pytest.raises(ValueError, match="Illegal move"):
        find_opponent_knight_forks(F2, "b4c2")
