import pytest

from backend.position_evidence import observe_move


def test_knight_fork_is_expressed_as_attacks_not_a_named_motif():
    fen = "4k3/7p/8/8/1n6/8/7P/R3K3 b Q - 0 1"
    evidence = observe_move(fen, "b4c2", "hypothetical")

    assert evidence["status"] == "hypothetical"
    assert evidence["checksKing"] is True
    assert {(attack["target"]["square"], attack["target"]["piece"]) for attack in evidence["newAttacks"]} == {
        ("a1", "rook"), ("e1", "king")
    }
    assert evidence["evidenceLevel"] == "board_observation_only"
    assert "materialLoss" not in evidence


def test_queen_and_rook_attacks_do_not_imply_the_queen_is_lost():
    fen = "3qk3/8/8/8/8/8/8/R3K3 w Q - 0 1"
    evidence = observe_move(fen, "a1d1", "actual")

    assert evidence["newAttacks"] == [{
        "target": {"square": "d8", "piece": "queen", "color": "black"},
        "attackers": ["d1"],
    }]
    assert "d8d1" in evidence["legalCapturesOfMovedPiece"]


def test_discovered_attack_by_another_piece_is_not_missed():
    fen = "q3k3/8/8/8/8/8/B7/R3K3 w Q - 0 1"
    evidence = observe_move(fen, "a2b3", "hypothetical")

    queen_attack = next(attack for attack in evidence["newAttacks"] if attack["target"]["square"] == "a8")
    assert queen_attack["attackers"] == ["a1"]
    assert evidence["move"]["piece"] == "bishop"


def test_pawn_development_creates_a_concrete_target():
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"
    evidence = observe_move(fen, "g1f3", "hypothetical")

    assert any(attack["target"] == {"square": "e5", "piece": "pawn", "color": "black"}
               for attack in evidence["newAttacks"])
    assert evidence["checksKing"] is False


def test_defensible_attack_records_the_immediate_capture_reply():
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    evidence = observe_move(fen, "b4c2", "hypothetical")

    assert {attack["target"]["square"] for attack in evidence["newAttacks"]} == {"a1", "e3"}
    assert "f5c2" in evidence["legalCapturesOfMovedPiece"]


def test_en_passant_is_a_legal_way_to_capture_the_moved_pawn():
    fen = "4k3/8/8/8/3p4/8/4P3/4K3 w - - 0 1"
    evidence = observe_move(fen, "e2e4", "actual")

    assert evidence["captured"] is None
    assert "d4e3" in evidence["legalCapturesOfMovedPiece"]


def test_invalid_status_and_illegal_move_are_not_treated_as_evidence():
    fen = "4k3/7p/8/8/1n6/8/7P/R3K3 b Q - 0 1"
    with pytest.raises(ValueError, match="status"):
        observe_move(fen, "b4c2", "maybe")
    with pytest.raises(ValueError, match="Illegal move"):
        observe_move(fen, "b4b5", "hypothetical")
