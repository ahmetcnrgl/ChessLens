import asyncio
import json

import chess

from backend.coach import describe_line
from backend.llm_integration import (
    OllamaCoach, _required_opponent_threat, _review_opponent_threat, build_prompt,
)


def test_last_move_prompt_keeps_attacks_and_real_reply_separate():
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    board = chess.Board(fen)
    board.push_uci("b4c2")
    analysis = {
        "fenBefore": fen, "fenAfter": board.fen(),
        "classification": "good", "mover": "black",
        "playedMove": {"uci": "b4c2"}, "bestMove": {"uci": "b4c2"},
        "actualOpponentMove": {"uci": "f5c2"},
        "evaluationBefore": {"kind": "centipawn", "value": 0},
        "evaluationAfter": {"kind": "centipawn", "value": 0},
        "bestMoveLine": [], "opponentBestLine": [],
    }

    instructions, raw = build_prompt(analysis, {"uci": "f5c2"}).split("\n", 1)
    payload = json.loads(raw)

    assert len(payload["playedMoveAttackDescriptions"]) == 2
    assert "a1 karesindeki kale" in payload["playedMoveAttackDescriptions"][0]
    assert "e3 karesindeki vezir" in payload["playedMoveAttackDescriptions"][1]
    assert payload["requiredConcreteEffect"] == payload["playedMoveAttackDescriptions"][0]
    assert "Rakip, f5 karesindeki filiyle" in payload["actualOpponentReply"]
    assert "c2 karesindeki atını aldı" in payload["actualOpponentReply"]
    serialized = json.dumps(payload, ensure_ascii=False)
    for raw_key in ("uci", "san", "fen", "BoardEvidence", "legalCapturesOfMovedPiece"):
        assert raw_key not in serialized
    assert "b4c2" not in serialized and "f5c2" not in serialized
    assert "taş kazanıldığını kanıtlamaz" in instructions


def test_alternative_lines_reach_model_as_natural_descriptions_without_move_codes():
    before = chess.Board()
    played_step = before.parse_san("e4")
    after = before.copy()
    after.push(played_step)
    alternatives = describe_line(after.fen(), ["c6", "d4", "d5", "e5"], "white")
    analysis = {
        "fenBefore": before.fen(), "fenAfter": after.fen(), "classification": "best", "mover": "white",
        "playedMove": {"uci": "e2e4"}, "bestMove": {"uci": "e2e4"},
        "evaluationBefore": {"kind": "centipawn", "value": 0},
        "evaluationAfter": {"kind": "centipawn", "value": 0},
        "bestMoveLine": [], "opponentBestLine": ["e5"],
        "alternativeOpponentLines": [{"rank": 2, "status": "hypothetical", "steps": alternatives}],
    }

    payload = json.loads(build_prompt(analysis).split("\n", 1)[1])
    line = payload["alternativeOpponentLines"][0]

    assert payload["requiredConcreteEffect"] == "e4 karesine gelen piyon d5 karesini kontrol eder."
    assert line["durum"] == "olası devam; oynanmış değil"
    assert line["adımlar"][0]["oynayan"] == "rakip"
    assert "c7 karesindeki piyonunu c6 karesine sürebilir" in line["adımlar"][0]["açıklama"]
    threat = payload["requiredOpponentThreat"]
    assert "sen d2 karesindeki piyonunu d4 karesine sürersen" in threat
    assert "rakip d7 karesindeki piyonunu d5 karesine sürerek" in threat
    assert "e4 karesindeki piyonuna saldırabilir" in threat
    assert ";" not in threat
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "c7c5" not in serialized and "b8c6" not in serialized
    assert '"uci"' not in serialized and '"san"' not in serialized and '"fenBefore"' not in serialized


def test_threat_line_labels_already_played_opponent_reply_as_actual():
    board = chess.Board()
    board.push_san("e4")
    steps = describe_line(board.fen(), ["e5", "Nf3", "Nf6"], "white")

    threat = _required_opponent_threat([{
        "steps": steps,
        "actualFirstMoveUci": "e7e5",
    }], "white")

    assert threat is not None
    assert "Rakip, e7 karesindeki piyonunu e5 karesine sürdü." in threat["text"]
    assert "Olası devamda sen g1 karesindeki atını f3 karesine taşırsan" in threat["text"]
    assert "rakip g8 karesindeki atını f6 karesine taşıyarak" in threat["text"]
    assert "e4 karesindeki piyonuna saldırabilir" in threat["text"]
    assert ";" not in threat["text"]
    assert "Olası devamda" in threat["supplementText"]
    assert "e7 karesindeki piyonunu e5 karesine" not in threat["supplementText"]


def test_future_opponent_capture_is_explained_as_conditional_and_not_repeated_if_actual():
    fen = "3rk3/8/8/8/8/8/3R4/4K3 b - - 0 1"
    steps = describe_line(fen, ["Rxd2"], "white")

    threat = _required_opponent_threat([{"steps": steps}], "white")

    assert threat is not None
    assert "Olası bir devamda rakip d8 karesindeki kalesiyle d2 karesindeki kalesini alırsa" in threat["text"]
    assert "d2 karesindeki kalen alınır" in threat["text"]
    assert "sonra geri alıp alamayacağını kontrol et" in threat["text"]

    already_played = _required_opponent_threat([{
        "steps": steps,
        "actualFirstMoveUci": "d8d2",
    }], "white")
    assert already_played is None


def test_opened_bishop_diagonal_is_explained_in_one_readable_if_then_sentence():
    board = chess.Board()
    for san in ["f4", "d5", "d4", "Bf5", "Nf3", "c5"]:
        board.push_san(san)
    steps = describe_line(board.fen(), ["dxc5", "e6"], "white")

    threat = _required_opponent_threat([{"steps": steps}], "white")

    assert threat is not None
    assert threat["text"] == (
        "Olası devamda sen d4 karesindeki piyonunla rakibin c5 karesindeki piyonunu alırsan, "
        "rakip e7 karesindeki piyonunu e6 karesine sürerek f8 karesindeki filinin "
        "c5 karesindeki piyona saldırı yolunu açabilir."
    )


def test_forward_threat_uses_the_board_after_actual_bot_reply_not_old_reply_branches():
    board = chess.Board()
    board.push_san("e4")
    actual_reply = board.parse_san("c6")
    actual_reply_details = {"uci": actual_reply.uci()}
    board.push(actual_reply)
    stale_branch = describe_line(chess.Board().fen(), ["e4", "e5", "Nf3", "Nf6"], "white")
    forward_branch = describe_line(board.fen(), ["Nf3", "d5"], "white")
    analysis = {
        "fenBefore": chess.STARTING_FEN,
        "fenAfter": chess.Board("rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2").fen(),
        "classification": "best", "mover": "white",
        "playedMove": {"uci": "e2e4"}, "bestMove": {"uci": "e2e4"},
        "actualOpponentMove": actual_reply_details,
        "evaluationBefore": {"kind": "centipawn", "value": 0},
        "evaluationAfter": {"kind": "centipawn", "value": 0},
        "bestMoveLine": [], "opponentBestLine": ["e5", "Nf3", "Nf6"],
        "alternativeOpponentLines": [{"rank": 2, "steps": stale_branch}],
        "forwardOpponentLines": [{"rank": 1, "steps": forward_branch}],
    }

    threat = _review_opponent_threat(analysis)
    payload = json.loads(build_prompt(analysis).split("\n", 1)[1])

    assert threat is not None
    assert "e4 karesindeki piyonuna saldırabilir" in threat["text"]
    assert "e5 karesindeki piyona saldırıyor" not in threat["text"]
    assert payload["alternativeOpponentLines"] == []
    assert payload["forwardOpponentLines"]


def test_current_question_receives_general_evidence_and_hypothetical_line(monkeypatch):
    fen = "3qk3/8/8/8/8/8/8/R3K3 w Q - 0 1"
    current = {
        "fen": fen, "playerColor": "white", "bestMove": {"uci": "a1d1"},
        "line": describe_line(fen, ["Rd1", "Qxd1+"], "white"),
    }
    messages_seen = []

    async def fake_request(self, messages, analysis):
        messages_seen.extend(messages)
        return {"summary": "Önerim", "explanation": "Bu olası devamı kontrol et.",
                "lesson": "Karşı hamleyi kontrol et.", "confidence": "low", "text": "Önerim", "source": "ollama"}

    monkeypatch.setattr(OllamaCoach, "_request", fake_request)
    asyncio.run(OllamaCoach().answer_question(
        question="Şimdi ne oynamalıyım?", analysis=None, engine_reply=None,
        current_fen=fen, previous_explanation={}, history=[], current_analysis=current,
        focus="current-position",
    ))

    context = json.loads(messages_seen[0]["content"].split("\n", 1)[1])
    assert context["newAttackDescriptions"] == ["d1 karesindeki kale, d8 karesindeki vezire saldırıyor."]
    assert context["continuation"][0]["oynayan"] == "sen"
    assert "taşı" in context["continuation"][0]["açıklama"]
    assert "boardEvidence" not in json.dumps(context)
    assert '"fen"' not in json.dumps(context)
