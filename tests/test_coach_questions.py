import asyncio
import json

import chess
from fastapi.testclient import TestClient
import httpx
import pytest

import backend.main as main_module
from backend.coach import (
    build_fallback_answer, build_fallback_coach, build_move_summary, describe_line, describe_move_for_player,
    build_current_answer, move_facts, resolve_question_focus,
)
from backend.game_service import GameService
from backend.llm_integration import OllamaCoach, build_prompt, response_context


class FakeEngine:
    def analyze(self, board, depth, skill_level=20, multi_pv=1):
        move = next(iter(board.legal_moves), None)
        return {"evaluation": {"kind": "centipawn", "value": 20}, "bestMove": move.uci() if move else None, "pv": []}


class QuestionCoach:
    def __init__(self):
        self.calls = []

    async def explain(self, analysis, engine_reply):
        return {"text": "Hamle açıklaması", "betterMove": "—", "source": "fake"}

    async def answer_question(self, **context):
        self.calls.append(context)
        return {"text": f"Soruna yanıt: {context['question']}", "betterMove": "—", "source": "fake"}


def make_analysis():
    game = GameService.new()
    played = game.play_move("d2", "d4")
    return {
        "fenBefore": played["fenBefore"], "fenAfter": played["fenAfter"],
        "playedMove": played["move"], "bestMove": {"uci": "e2e4", "san": "e4"},
        "mover": "white", "classification": "good",
        "evaluationBefore": {"kind": "centipawn", "value": 40},
        "evaluationAfter": {"kind": "centipawn", "value": 20},
        "bestMoveLine": ["e4", "e5"], "opponentBestLine": ["d5"],
    }


@pytest.mark.parametrize("uci,expected", [
    ("e2e4", "e2 karesindeki piyonunu e4 karesine sür"),
    ("d2d4", "d2 karesindeki piyonunu d4 karesine sür"),
    ("g1f3", "g1 karesindeki atını f3 karesine taşı"),
])
def test_recommendation_identifies_the_exact_piece(uci, expected):
    assert describe_move_for_player(chess.STARTING_FEN, {"uci": uci}) == expected


def test_en_passant_description_names_captured_and_destination_squares():
    fen = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1"
    result = describe_move_for_player(fen, {"uci": "e5d6"})
    assert result == "e5 karesindeki piyonunla rakibin d5 karesindeki piyonunu al ve d6 karesine geç"


def test_question_reaches_coach_with_server_context_and_history():
    coach = QuestionCoach()
    client = TestClient(main_module.create_app(FakeEngine(), coach))
    game = client.post("/api/games", json={}).json()
    route = f"/api/games/{game['gameId']}"
    move = client.post(route + "/moves", json={"from": "e2", "to": "e4"}).json()
    state_before_questions = client.get(route).json()

    first = client.post(route + "/coach", json={"question": "Daha iyi hangi hamle vardı?", "moveId": move["moveId"]})
    second = client.post(route + "/coach", json={"question": "Neden daha iyi?", "moveId": move["moveId"]})

    assert first.status_code == second.status_code == 200
    assert first.json()["text"] != second.json()["text"]
    assert coach.calls[0]["question"] == "Daha iyi hangi hamle vardı?"
    assert coach.calls[0]["analysis"]["playedMove"]["uci"] == "e2e4"
    assert coach.calls[0]["analysis"]["actualOpponentMove"] == move["engineMove"]
    assert coach.calls[0]["current_fen"] == move["fen"]
    assert coach.calls[0]["history"] == []
    assert coach.calls[1]["history"][-1]["content"] == first.json()["text"]
    assert client.get(route).json() == state_before_questions

    stale = client.post(route + "/coach", json={"question": "Neden?", "moveId": "old-move"})
    assert stale.status_code == 409
    assert len(coach.calls) == 2
    assert client.post(route + "/coach", json={"question": "   "}).status_code == 422

    # A new move invalidates the previous question/answer context.
    next_move = state_before_questions["legalMoves"][0]
    assert client.post(route + "/moves", json=next_move).status_code == 200
    client.post(route + "/coach", json={"question": "Bu hamle neden iyi?"})
    assert coach.calls[-1]["history"] == []


def test_disabled_coach_does_not_pretend_to_answer_every_question():
    client = TestClient(main_module.create_app(FakeEngine(), coach=False))
    game = client.post("/api/games", json={}).json()
    route = f"/api/games/{game['gameId']}"
    initial = client.post(route + "/coach", json={"question": "Son hamlemi açıkla"})
    assert "İlk hamleni" in initial.json()["text"]
    client.post(route + "/moves", json={"from": "e2", "to": "e4"})
    which = client.post(route + "/coach", json={"question": "Daha iyi hangi hamle vardı?"}).json()
    why = client.post(route + "/coach", json={"question": "Neden daha iyi?"}).json()
    assert which["source"] == why["source"] == "fallback"
    assert which["text"] != why["text"]
    assert "açıklayamıyorum" in why["text"]


def test_playing_the_best_move_does_not_claim_a_missed_alternative():
    analysis = make_analysis()
    analysis["bestMove"] = analysis["playedMove"]
    answer = build_fallback_answer("Önerdiğin hamle neden daha iyi?", analysis)
    assert "Zaten önerdiğim hamleyi oynadın" in answer["text"]


def test_ollama_request_contains_actual_question_and_accepts_explained_squares(monkeypatch):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        result = {
            "summary": "e2 karesindeki piyonunu e4 karesine sürmeyi öneriyorum.",
            "explanation": "Bu öneri son hamlenden önceki konum içindi.",
            "lesson": "Taşların birlikte nasıl çalıştığını kontrol et.",
            "confidence": "low",
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(result)}})

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    analysis = make_analysis()
    result = asyncio.run(OllamaCoach().answer_question(
        question="Hangi piyonu kastediyorsun?", analysis=analysis, engine_reply=None,
        current_fen=analysis["fenAfter"], previous_explanation={"text": "Önceki yorum"}, history=[],
    ))
    assert result["source"] == "ollama"
    assert result["betterMove"] == "—"
    assert requests[0]["messages"][-1] == {"role": "user", "content": "Hangi piyonu kastediyorsun?"}
    assert requests[0]["messages"][0]["role"] == "system"
    context = json.loads(requests[0]["messages"][0]["content"].split("\n", 1)[1])
    assert context["bestMoveDescription"] == "e2 karesindeki piyonunu e4 karesine sür"
    assert "currentFen" not in context and "fenBefore" not in context and "fenAfter" not in context


@pytest.mark.parametrize("text", ["30 centipawn kaybettin.", "Nf3 oyna.", "e2e4 oyna."])
def test_compressed_notation_and_engine_metrics_are_rejected(text):
    with pytest.raises(ValueError):
        OllamaCoach._validate({"summary": text, "explanation": "Açıklama", "lesson": "Ders", "confidence": "low"}, make_analysis())


def test_model_timeout_produces_an_honest_question_fallback(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("test timeout", request=request)

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(timeout)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    analysis = make_analysis()
    result = asyncio.run(OllamaCoach().answer_question(
        question="Neden daha iyi?", analysis=analysis, engine_reply=None,
        current_fen=analysis["fenAfter"], previous_explanation={}, history=[],
    ))
    assert result["source"] == "fallback"
    assert "açıklayamıyorum" in result["text"]


def test_same_move_comparison_is_corrected_even_if_the_model_ignores_the_prompt(monkeypatch):
    async def incorrect_comparison(_self, messages, analysis):
        return {"summary": "Önerdiğim hamle daha iyi.", "explanation": "Piyon merkeze ilerler.", "text": "Önerdiğim hamle daha iyi. Piyon merkeze ilerler.", "source": "ollama"}

    monkeypatch.setattr(OllamaCoach, "_request", incorrect_comparison)
    analysis = make_analysis()
    analysis["bestMove"] = analysis["playedMove"]
    result = asyncio.run(OllamaCoach().answer_question(
        question="Önerdiğin hamle neden daha iyi?", analysis=analysis, engine_reply=None,
        current_fen=analysis["fenAfter"], previous_explanation={}, history=[],
    ))
    assert result["text"].startswith("Zaten önerdiğim hamleyi oynadın")
    assert "Önerdiğim hamle daha iyi" not in result["text"]


class ScenarioEngine:
    """Known legal sequence: white's next move changes after the actual c-pawn reply."""
    def __init__(self):
        self.calls = []

    def analyze(self, board, depth, skill_level=20, multi_pv=1):
        self.calls.append((board.fen(), depth, skill_level))
        choices = ["e2e4", "g1f3"] if board.turn else ["c7c5", "d7d6"]
        move = next((chess.Move.from_uci(uci) for uci in choices if chess.Move.from_uci(uci) in board.legal_moves), next(iter(board.legal_moves)))
        return {"evaluation": {"kind": "centipawn", "value": 20}, "bestMove": move.uci(), "pv": [move.uci()]}


def make_current_analysis():
    game = GameService.new()
    game.play_move("e2", "e4")
    game.play_move("c7", "c5")
    best = {"uci": "g1f3", "from": "g1", "to": "f3", "san": "Nf3"}
    return {
        "fen": game.board.fen(), "bestMove": best, "turn": "white", "playerColor": "white",
        "isGameOver": False, "bestMoveFacts": move_facts(game.board.fen(), best),
        "line": describe_line(game.board.fen(), ["Nf3", "d6"], "white"),
    }


def test_next_move_uses_fresh_actual_board_and_preserves_it():
    engine = ScenarioEngine()
    coach = QuestionCoach()
    client = TestClient(main_module.create_app(engine, coach))
    game = client.post("/api/games", json={}).json()
    route = f"/api/games/{game['gameId']}"
    move = client.post(route + "/moves", json={"from": "e2", "to": "e4"}).json()
    before = client.get(route).json()
    calls_before = len(engine.calls)
    answer = client.post(route + "/coach", json={"question": "Bir sonraki hamlem ne olmalı?", "moveId": move["moveId"]}).json()
    assert answer["focus"] == "current-position"
    assert len(engine.calls) == calls_before + 1
    assert engine.calls[-1] == (before["fen"], 12, 20)
    assert answer["recommendation"]["move"]["uci"] == "g1f3"
    assert answer["recommendation"]["fen"] == before["fen"]
    assert answer["recommendation"]["position"] == before["position"]
    assert coach.calls[-1]["current_analysis"]["fen"] == before["fen"]
    assert client.get(route).json() == before
    # 'Why?' now refers to the current recommendation, not the old e-pawn move.
    client.post(route + "/coach", json={"question": "Önerdiğin hamle neden daha iyi?"})
    assert coach.calls[-1]["focus"] == "current-position"
    client.post(route + "/coach", json={"question": "Daha iyi hangi hamle vardı?"})
    assert coach.calls[-1]["focus"] == "last-move"
    assert coach.calls[-1]["history"] == []


def test_next_move_fallback_still_gives_current_legal_recommendation():
    client = TestClient(main_module.create_app(ScenarioEngine(), coach=False))
    game = client.post("/api/games", json={}).json()
    route = f"/api/games/{game['gameId']}"
    client.post(route + "/moves", json={"from": "e2", "to": "e4"})
    answer = client.post(route + "/coach", json={"question": "Şimdi ne oynamalıyım?"}).json()
    assert answer["source"] == "fallback"
    assert "g1 karesindeki atını f3 karesine taşı" in answer["text"]
    assert "e2 karesindeki" not in answer["text"]


def test_opponent_notation_is_expanded_using_its_own_position():
    game = GameService.new()
    game.play_move("e2", "e4")
    steps = describe_line(game.board.fen(), ["c5", "Nf3", "d6"], "white")
    assert steps[0]["actor"] == "opponent"
    assert steps[0]["description"] == "Rakip, c7 karesindeki piyonunu c5 karesine sürebilir."
    assert steps[1]["description"] == "g1 karesindeki atını f3 karesine taşı"
    assert describe_line(game.board.fen(), ["e4"], "white") == []


@pytest.mark.parametrize("text", [
    "Rakibin cevabı c5 olursa avantajın artar.",
    "e4 hamlesi uzun vadeli bir üstünlük yaratabilir.",
    "Bu hamle rakibin gelişimini zorlaştırır.",
])
def test_reported_unreadable_or_unsubstantiated_answers_are_rejected(text):
    with pytest.raises(ValueError):
        OllamaCoach._validate({"summary": text, "explanation": "Açıklama", "lesson": "Ders", "confidence": "low"}, make_analysis())


def test_current_prompt_excludes_old_move_and_rejects_its_repetition(monkeypatch):
    requests = []

    def repeat_old_move(request):
        requests.append(json.loads(request.content))
        content = {"summary": "e2 karesindeki piyonunu e4 karesine sür.", "explanation": "Bu hamle merkezi kontrol eder.", "lesson": "Merkeze bak.", "confidence": "low"}
        return httpx.Response(200, json={"message": {"content": json.dumps(content)}})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(repeat_old_move), **kwargs))
    current = make_current_analysis()
    result = asyncio.run(OllamaCoach().answer_question(
        question="Bir sonraki hamlem ne olmalı?", analysis=make_analysis(), engine_reply=None,
        current_fen=current["fen"], previous_explanation={"text": "Eski piyon açıklaması"}, history=[],
        current_analysis=current, focus="current-position",
    ))
    assert result["source"] == "fallback"
    assert "g1 karesindeki atını f3 karesine taşı" in result["text"]
    assert "e2 karesindeki" not in result["text"]
    context = json.loads(requests[0]["messages"][0]["content"].split("\n", 1)[1])
    assert "playedMove" not in context
    assert context["bestMoveDescription"] == "g1 karesindeki atını f3 karesine taşı"
    serialized_context = json.dumps(context, ensure_ascii=False)
    assert '"fen"' not in serialized_context and '"uci"' not in serialized_context and '"san"' not in serialized_context


def test_question_scope_recognizes_next_move_without_exact_button_text():
    for question in ["bir sonraki hamlem ne olmalı", "nasıl devam edeyim?", "Şimdi ne yapayım?", "ne oynamalıyım"]:
        assert resolve_question_focus(question) == "current-position"
    assert resolve_question_focus("Neden?", "current-position") == "current-position"


def test_hidden_tip_style_does_not_discard_a_valid_answer():
    current = make_current_analysis()
    result = OllamaCoach._validate({
        "summary": "g1 karesindeki atını f3 karesine taşı.",
        "explanation": "Bu taş d4 karesini ve e5 karesini kontrol eder.",
        "lesson": "d4 ve e5'i kontrol et.", "confidence": "medium",
    }, {"fenBefore": current["fen"], "bestMove": current["bestMove"], "focus": "current-position"})
    assert result["source"] == "ollama"
    assert "d4 ve e5" not in result["lesson"]


def test_current_answer_cannot_invent_a_pawn_on_an_empty_square():
    current = make_current_analysis()
    with pytest.raises(ValueError, match="not present"):
        OllamaCoach._validate({
            "summary": "d4 karesindeki piyonunu koru.", "explanation": "Bu piyona dikkat et.",
            "lesson": "Taşlarına bak.", "confidence": "high",
        }, {"fenBefore": current["fen"], "bestMove": current["bestMove"], "focus": "current-position"})


def test_opponent_question_fallback_does_not_repeat_next_move_answer():
    current = make_current_analysis()
    next_move = build_current_answer(current, "Bir sonraki hamlem ne olmalı?")
    reply = build_current_answer(current, "Rakibim ne yaparsa dikkat etmeliyim?")
    assert reply["text"] != next_move["text"]
    assert "d7 karesindeki piyonunu d6 karesine sürebilir" in reply["text"]
    assert "rakibin kesin bu hamleyi oynayacağı anlamına gelmez" in reply["text"]


def test_opponent_capture_uses_opponents_piece_and_players_target():
    game = GameService.new()
    game.play_move("e2", "e4")
    game.play_move("d7", "d5")
    steps = describe_line(game.board.fen(), ["exd5", "Qxd5"], "white")
    assert steps[1]["description"] == "Rakip, d8 karesindeki veziriyle d5 karesindeki piyonunu alabilir."


def make_screenshot_analysis(second_move=False):
    game = GameService.new()
    played = game.play_move("e2", "e4")
    reply = game.play_move("b8", "c6")
    if second_move:
        played = game.play_move("f2", "f4")
        reply = game.play_move("g7", "g6")
    return {
        "fenBefore": played["fenBefore"], "fenAfter": played["fenAfter"],
        "playedMove": played["move"], "bestMove": {"uci": "d2d4"} if second_move else played["move"],
        "actualOpponentMove": reply["move"], "mover": "white",
        "classification": "inaccuracy" if second_move else "best",
        "evaluationBefore": {"kind": "centipawn", "value": 20},
        "evaluationAfter": {"kind": "centipawn", "value": 10},
        "bestMoveLine": ["d4", "d5"] if second_move else ["e4", "Nc6"],
        "opponentBestLine": ["g6"] if second_move else ["Nc6"],
    }


@pytest.mark.parametrize("text", [
    "Beyaz, b8 karesindeki atını c6 karesine taşıdı.",
    "Sen, b8 karesindeki atını c6 karesine taşıdın.",
    "b8 karesindeki atını c6 karesine taşı.",
    "Rakip, e2 karesindeki piyonunu e4 karesine sürdü.",
    "Rakip, b8 karesindeki filini c6 karesine taşıdı.",
])
def test_screenshot_move_cannot_be_assigned_to_the_wrong_player_or_piece(text):
    with pytest.raises(ValueError):
        OllamaCoach._validate({
            "summary": text, "explanation": "Taşlarının güvenliğine bak.",
            "lesson": "Rakibin cevabını kontrol et.", "confidence": "low",
        }, response_context(make_screenshot_analysis()))


@pytest.mark.parametrize("actor", ["Siyah", "Rakip"])
def test_black_knight_reply_is_valid_when_attributed_correctly(actor):
    result = OllamaCoach._validate({
        "summary": "e2 karesindeki piyonunu e4 karesine sürdün.",
        "explanation": f"{actor}, b8 karesindeki atını c6 karesine taşıdı.",
        "lesson": "Rakibin cevabını kontrol et.", "confidence": "low",
    }, response_context(make_screenshot_analysis()))
    assert result["source"] == "ollama"


@pytest.mark.parametrize("second_move,expected", [
    (False, "e2 karesindeki piyonunu e4 karesine sürdün."),
    (True, "f2 karesindeki piyonunu f4 karesine sürdün."),
])
def test_automatic_summary_and_fallback_name_the_actual_player_move(second_move, expected):
    analysis = make_screenshot_analysis(second_move)
    context = response_context(analysis)
    context["automaticMoveReview"] = True
    result = OllamaCoach._validate({
        "summary": "Beyaz, b8 karesindeki atını c6 karesine taşıdı.",
        "explanation": "Hamleni seçerken rakibin olası karşılığını kontrol et.",
        "lesson": "Taşlarına bak.", "confidence": "low",
    }, context)
    assert result["summary"].startswith(expected)
    assert "Beyaz" not in result["text"]
    fallback = build_fallback_coach(analysis)
    assert fallback["text"].startswith(expected)
    assert fallback["text"].count("Rakip,") == 1


def test_invalid_ownership_in_ollama_explanation_uses_grounded_fallback(monkeypatch):
    def wrong_owner(request):
        result = {
            "summary": "Hamlen değerlendirildi.",
            "explanation": "Beyaz, b8 karesindeki atını c6 karesine taşıdı.",
            "lesson": "Taşlarını kontrol et.", "confidence": "high",
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(result)}})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(wrong_owner), **kwargs))
    result = asyncio.run(OllamaCoach().explain(make_screenshot_analysis()))
    assert result["source"] == "fallback"
    assert result["text"].startswith("e2 karesindeki piyonunu e4 karesine sürdün.")
    assert "Rakip, b8 karesindeki atını c6 karesine taşıdı." in result["text"]
    assert "Beyaz," not in result["text"]


def test_black_player_ownership_is_relative_to_player_not_white():
    game = GameService.new()
    game.play_move("e2", "e4")
    played = game.play_move("c7", "c5")
    reply = game.play_move("g1", "f3")
    analysis = {
        **make_analysis(), "fenBefore": played["fenBefore"], "fenAfter": played["fenAfter"],
        "playedMove": played["move"], "bestMove": played["move"], "actualOpponentMove": reply["move"],
        "mover": "black", "bestMoveLine": ["c5", "Nf3"], "opponentBestLine": ["Nf3"],
    }
    prompt = json.loads(build_prompt(analysis).split("\n", 1)[1])
    assert prompt["playedMoveIsBest"] is True
    assert prompt["playedMoveDescription"].startswith("c7 karesindeki piyonunu c5 karesine sür")
    assert prompt["actualOpponentReply"].startswith("Rakip, g1 karesindeki atını f3 karesine taşı")
    assert "playedMoveIdentity" not in prompt and "actualOpponentIdentity" not in prompt
    assert build_move_summary(analysis).startswith("c7 karesindeki piyonunu c5 karesine sürdün.")
    context = response_context(analysis)
    value = {
        "summary": "Sen, c7 karesindeki piyonunu c5 karesine sürdün.",
        "explanation": "Beyaz, g1 karesindeki atını f3 karesine taşıdı.",
        "lesson": "Taşlarına bak.", "confidence": "low",
    }
    assert OllamaCoach._validate(value, context)["source"] == "ollama"
    with pytest.raises(ValueError, match="wrong player"):
        OllamaCoach._validate({**value, "summary": "Beyaz, c7 karesindeki piyonunu c5 karesine sürdü."}, context)


def test_current_continuation_keeps_opponents_identity_in_its_own_position():
    current = make_current_analysis()
    context = {
        "fenBefore": current["fen"], "bestMove": current["bestMove"],
        "playerColor": current["playerColor"], "focus": "current-position",
        "contextMoves": [step["move"] for step in current["line"]],
        "moveEvidence": [step["identity"] for step in current["line"]],
    }
    value = {
        "summary": "g1 karesindeki atını f3 karesine taşı.",
        "explanation": "Sen, d7 karesindeki piyonunu d6 karesine sür.",
        "lesson": "Rakibin cevabını kontrol et.", "confidence": "low",
    }
    with pytest.raises(ValueError, match="wrong player"):
        OllamaCoach._validate(value, context)
    correct = {**value, "explanation": "Rakip, d7 karesindeki piyonunu d6 karesine sürebilir."}
    assert OllamaCoach._validate(correct, context)["source"] == "ollama"


def test_control_fact_names_the_moved_piece_and_square():
    assert move_facts(chess.STARTING_FEN, {"uci": "e2e4"}) == [
        "e4 karesine gelen piyon d5 karesini kontrol eder.",
    ]
