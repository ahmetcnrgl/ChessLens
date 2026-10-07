import asyncio
import json

import chess
import httpx
import pytest

from backend.coach import build_fallback_coach, describe_line
from backend.llm_integration import (
    OllamaCoach, _required_concrete_effect, _required_opponent_threat, response_context,
)


def _analysis(fen: str, played_uci: str, actual_reply_uci: str | None = None) -> dict:
    board = chess.Board(fen)
    board.push_uci(played_uci)
    return {
        "fenBefore": fen, "fenAfter": board.fen(),
        "playedMove": {"uci": played_uci}, "bestMove": {"uci": played_uci},
        "actualOpponentMove": {"uci": actual_reply_uci} if actual_reply_uci else None,
        "mover": "white" if not board.turn else "black",
        "classification": "good", "mateOutcome": None,
        "evaluationBefore": {"kind": "centipawn", "value": 0},
        "evaluationAfter": {"kind": "centipawn", "value": 0},
        "bestMoveLine": [], "opponentBestLine": [],
    }


def _response(text: str) -> dict:
    return {"summary": text, "explanation": "Bu devamı kontrol et.",
            "lesson": "Karşı hamleyi incele.", "confidence": "low"}


@pytest.mark.parametrize("claim", [
    "Rakibin vezirini kesin kazanırsın.",
    "Rakip kaleni kaybedecek.",
    "Bu hamleyle veziri alırsın.",
    "Bu konumda zorunlu mat var.",
    "Bu hamle rakibi mat eder.",
])
def test_unsupported_outcome_claims_are_rejected(claim):
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    analysis = _analysis(fen, "b4c2", "f5c2")
    context = response_context(analysis)

    with pytest.raises(ValueError):
        OllamaCoach._validate(_response(claim), context)


def test_supported_attack_and_possible_defense_are_not_called_a_win():
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    analysis = _analysis(fen, "b4c2", "f5c2")
    context = response_context(analysis)

    result = OllamaCoach._validate(_response(
        "At vezire ve kaleye saldırıyor; rakibin fili atı alabilir."
    ), context)

    assert result["source"] == "ollama"


def test_checkmate_claim_is_allowed_when_the_board_really_is_mate():
    fen = "7k/8/5KQ1/8/8/8/8/8 w - - 0 1"
    context = response_context(_analysis(fen, "g6g7"))

    result = OllamaCoach._validate(_response("Bu hamle rakibi mat eder."), context)

    assert result["source"] == "ollama"


def test_ambiguous_this_move_after_opponents_reply_is_rejected():
    board = chess.Board()
    board.push_uci("e2e4")
    analysis = {
        **_analysis(chess.STARTING_FEN, "e2e4", "e7e5"),
        "fenAfter": board.fen(),
    }
    context = response_context(analysis)
    response = {
        "summary": "e2 karesindeki piyonunu e4 karesine sürdün.",
        "explanation": "Rakip piyonunu e5 karesine sürdü. Bu hamle d5 karesini kontrol eder.",
        "lesson": "Rakibin cevabını kontrol et.", "confidence": "low",
    }

    with pytest.raises(ValueError, match="ambiguous move reference"):
        OllamaCoach._validate(response, context)


def test_model_cannot_add_an_unverified_square_to_the_lesson():
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    context = response_context(_analysis(fen, "b4c2", "f5c2"))
    answer = _response("At vezire ve kaleye saldırıyor; rakibin fili atı alabilir.")
    answer["lesson"] = "At c2 karesinden e4 karesini kontrol eder."

    result = OllamaCoach._validate(answer, context)

    assert "e4 karesini" not in result["lesson"]
    assert "hemen alıp alamayacağını" in result["lesson"]


def test_automatic_review_requires_the_real_attack_not_just_move_repetition():
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    analysis = _analysis(fen, "b4c2", "f5c2")
    context = response_context(analysis)
    context["enforceFactCoverage"] = True
    vague = _response("Atını c2 karesine taşıdın.")

    with pytest.raises(ValueError, match="attacked target"):
        OllamaCoach._validate(vague, context)

    fallback = build_fallback_coach(analysis)
    assert "a1 karesindeki kaleye" in fallback["text"]
    assert "e3 karesindeki vezire" not in fallback["text"]
    assert "f5 karesindeki filiyle" in fallback["text"]


def test_automatic_review_requires_a_concrete_effect_in_an_ordinary_opening():
    analysis = _analysis(chess.STARTING_FEN, "e2e4", "e7e5")
    context = response_context(analysis)
    context["enforceFactCoverage"] = True

    with pytest.raises(ValueError, match="positional effect"):
        OllamaCoach._validate(_response("Piyonunu sürdün, rakip de piyonunu sürdü."), context)

    assert "d5 karesini kontrol" in build_fallback_coach(analysis)["text"]


def test_vague_qwen_answer_is_supplemented_with_board_grounded_effect(monkeypatch):
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    analysis = _analysis(fen, "b4c2", "f5c2")
    requests = []

    def vague_reply(request):
        requests.append(request)
        raw = _response("Atını c2 karesine taşıdın; rakip filinle atını aldı.")
        return httpx.Response(200, json={"message": {"content": json.dumps(raw)}})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(vague_reply), **kwargs
    ))

    result = asyncio.run(OllamaCoach().explain(analysis))

    assert requests
    assert result["source"] == "ollama"
    assert result["serverSupplemented"] is True
    assert "a1 karesindeki kaleye" in result["explanation"]
    assert "Rakip, f5 karesindeki filiyle" in result["explanation"]


def test_automatic_review_includes_conditional_opponent_attack_from_alternative_line():
    analysis = _analysis(chess.STARTING_FEN, "e2e4")
    steps = describe_line(analysis["fenAfter"], ["c6", "d4", "d5", "e5"], "white")
    analysis["alternativeOpponentLines"] = [{"rank": 3, "status": "hypothetical", "steps": steps}]
    context = response_context(analysis)
    context.update({
        "automaticMoveReview": True,
        "enforceFactCoverage": True,
        "requiredConcreteEffect": _required_concrete_effect(analysis["fenBefore"], analysis["playedMove"]),
        "requiredOpponentThreat": _required_opponent_threat(analysis["alternativeOpponentLines"], "white"),
    })

    result = OllamaCoach._validate({
        "summary": "Hamlen iyi.",
        "explanation": "e4 karesine gelen piyon d5 karesini kontrol eder.",
        "lesson": "Rakibin karşılığını incele.", "confidence": "low",
    }, context)

    assert result["source"] == "ollama"
    assert result["serverSupplemented"] is True
    assert "Olası devamda" in result["explanation"]
    assert "rakip d7 karesindeki piyonunu d5 karesine sürerek" in result["explanation"]
    assert "e4 karesindeki piyonuna saldırabilir" in result["explanation"]
    assert ";" not in result["explanation"]


def test_model_self_confidence_is_not_reported_as_calibrated_high():
    fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    context = response_context(_analysis(fen, "b4c2", "f5c2"))
    answer = _response("At vezire ve kaleye saldırıyor; rakibin fili atı alabilir.")
    answer["confidence"] = "high"

    assert OllamaCoach._validate(answer, context)["confidence"] == "medium"
