from fastapi.testclient import TestClient

from backend.main import create_app
from backend.move_analyzer import analyze_evaluation_change


class FakeEngine:
    def analyze(self, board, depth, skill_level=20):
        # A legal move for the side to move, with a stable evaluation contract.
        move = next(iter(board.legal_moves), None)
        return {"evaluation": {"kind": "centipawn", "value": 20}, "bestMove": move.uci() if move else None, "pv": [move.uci()] if move else []}


class FakeCoach:
    async def explain(self, analysis, engine_reply):
        return {"summary": "Test koç", "explanation": "Test açıklaması", "lesson": "Test dersi", "confidence": "high", "source": "fake"}


def test_game_service_contract_and_move_flow():
    client = TestClient(create_app(FakeEngine(), FakeCoach()))
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
    client = TestClient(create_app(FakeEngine(), FakeCoach()))
    game = client.post("/api/games", json={}).json()
    response = client.post(f"/api/games/{game['gameId']}/moves", json={"from": "e2", "to": "e5"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "ILLEGAL_MOVE"


def test_black_centipawn_loss_is_from_mover_perspective():
    result = analyze_evaluation_change({"kind": "centipawn", "value": 30}, {"kind": "centipawn", "value": 80}, "black")
    assert result["lossInCentipawns"] == 50
