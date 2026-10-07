from dataclasses import replace
import json

from fastapi.testclient import TestClient

import backend.main as main_module
from backend.move_analyzer import analyze_evaluation_change
from backend.llm_integration import build_prompt


class FakeEngine:
    def analyze(self, board, depth, skill_level=20, multi_pv=1):
        # A legal move for the side to move, with a stable evaluation contract.
        move = next(iter(board.legal_moves), None)
        return {"evaluation": {"kind": "centipawn", "value": 20}, "bestMove": move.uci() if move else None, "pv": [move.uci()] if move else []}


class FakeCoach:
    async def explain(self, analysis, engine_reply):
        return {"summary": "Test koç", "explanation": "Test açıklaması", "lesson": "Test dersi", "confidence": "high", "source": "fake"}


def test_game_service_contract_and_move_flow():
    client = TestClient(main_module.create_app(FakeEngine(), FakeCoach()))
    response = client.post("/api/games", json={"opponentId": "judit", "playerColor": "white"})
    assert response.status_code == 201
    game = response.json()
    assert game["turn"] == "white"
    assert game["fen"].startswith("rnbqkbnr/")

    response = client.post(f"/api/games/{game['gameId']}/moves", json={"from": "e2", "to": "e4"})
    assert response.status_code == 200
    result = response.json()
    assert result["playedMove"]["san"] == "e4"
    assert result["engineMove"] is not None
    assert result["coach"]["source"] == "fake"


def test_illegal_move_is_explained_as_client_error():
    client = TestClient(main_module.create_app(FakeEngine(), FakeCoach()))
    game = client.post("/api/games", json={}).json()
    response = client.post(f"/api/games/{game['gameId']}/moves", json={"from": "e2", "to": "e5"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "ILLEGAL_MOVE"


def test_llm_is_opt_in_and_falls_back_without_a_coach(monkeypatch):
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, llm_enabled=False))
    client = TestClient(main_module.create_app(FakeEngine()))
    game = client.post("/api/games", json={}).json()

    response = client.post(f"/api/games/{game['gameId']}/moves", json={"from": "e2", "to": "e4"})

    assert response.status_code == 200
    assert response.json()["coach"]["source"] == "fallback"


def test_coach_prompt_contains_allowlisted_chess_context():
    analysis = {
        "fenBefore": "start-fen",
        "fenAfter": "after-fen",
        "classification": "mistake",
        "mover": "white",
        "playedMove": {"san": "f3", "uci": "f2f3"},
        "bestMove": {"san": "e4", "uci": "e2e4"},
        "evaluationBefore": {"kind": "centipawn", "value": 39},
        "evaluationAfter": {"kind": "centipawn", "value": -73},
        "lossInCentipawns": 112,
        "mateOutcome": None,
        "bestMoveLine": ["e4", "e5", "Nf3"],
        "opponentBestLine": ["e5", "e4"],
    }

    payload = json.loads(build_prompt(analysis, {"san": "e5", "uci": "e7e5"}).split("\n", 1)[1])

    assert payload["mateContext"] is None
    assert payload["playedMoveDescription"] == "—"
    assert payload["bestMoveDescription"] == "—"
    assert payload["bestMoveSteps"] == []
    assert payload["opponentSteps"] == []
    assert payload["possibleOpponentReply"] == "—"
    assert "fenBefore" not in payload and "bestMoveLine" not in payload and "engineReply" not in payload


def test_black_centipawn_loss_is_from_mover_perspective():
    result = analyze_evaluation_change({"kind": "centipawn", "value": 30}, {"kind": "centipawn", "value": 80}, "black")
    assert result["lossInCentipawns"] == 50
