from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import chess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .coach import (
    build_current_answer, build_fallback_answer, build_fallback_coach,
    describe_line, describe_move_for_player, move_facts, resolve_question_focus,
)
from .config import settings
from .game_service import GameRecord, IllegalMoveError, GameService
from .llm_integration import OllamaCoach
from .move_analyzer import build_move_analysis
from .schemas import CoachQuestionRequest, CreateGameRequest, MoveRequest
from .stockfish_adapter import StockfishAdapter, StockfishUnavailable


OPPONENTS = {
    "capablanca": {"id": "capablanca", "name": "José", "level": "Kolay bot", "difficulty": "easy", "face": "avatar-capablanca"},
    "judit": {"id": "judit", "name": "Judit", "level": "Orta bot", "difficulty": "medium", "face": "avatar-judit"},
    "magnus": {"id": "magnus", "name": "Magnus", "level": "Zor bot", "difficulty": "hard", "face": "avatar-magnus"},
}
logger = logging.getLogger(__name__)
ANALYSIS_DEPTH = 12
ANALYSIS_SKILL_LEVEL = 20
COACH_MULTIPV = 3
FORWARD_LOOKAHEAD_DEPTH = 8
BOT_MOVE_BLOCK_SIZE = 10
# The shuffled per-game schedule keeps the best-move ratio exact without a predictable pattern.
BOT_SETTINGS_BY_DIFFICULTY = {
    "easy": {
        "depth": 4,
        "skill_level": 20,
        "multi_pv": 8,
        "candidate_pool_size": 8,
        "best_moves_per_block": 3,
    },
    "medium": {
        "depth": 7,
        "skill_level": 20,
        "multi_pv": 5,
        "candidate_pool_size": 5,
        "best_moves_per_block": 6,
    },
    "hard": {
        "depth": 10,
        "skill_level": 20,
        "multi_pv": 3,
        "candidate_pool_size": 3,
        "best_moves_per_block": 8,
    },
}


def choose_bot_move(record: GameRecord, bot_analysis: dict, settings: dict) -> str | None:
    candidates = list(dict.fromkeys(bot_analysis.get("candidateMoves", [])))
    best_move = bot_analysis.get("bestMove")
    if best_move:
        candidates = [best_move, *(move for move in candidates if move != best_move)]
    if len(candidates) < 2:
        return candidates[0] if candidates else bot_analysis.get("bestMove")

    if not record.bot_move_schedule:
        schedule = [True] * settings["best_moves_per_block"]
        schedule.extend([False] * (BOT_MOVE_BLOCK_SIZE - len(schedule)))
        random.shuffle(schedule)
        record.bot_move_schedule = schedule
    play_best = record.bot_move_schedule.pop(0)
    if play_best:
        return candidates[0]

    weaker_candidates = candidates[1:settings["candidate_pool_size"]]
    return random.choice(weaker_candidates) if weaker_candidates else candidates[0]


def serialize_game(record: GameRecord) -> dict:
    state = record.game.state()
    return {
        "gameId": record.game_id,
        "status": "finished" if state["isGameOver"] else "active",
        "playerColor": record.player_color,
        "opponent": record.opponent,
        "lastMoveId": record.last_move_id,
        **state,
    }


def format_score(score: dict | None) -> str:
    if not score:
        return "—"
    if score["kind"] == "mate":
        return f"{'+' if score['value'] > 0 else '-'}M{abs(score['value'])}"
    return f"{'+' if score['value'] >= 0 else ''}{score['value'] / 100:.2f}"


def score_to_white_percent(score: dict | None) -> int:
    if not score:
        return 50
    if score["kind"] == "mate":
        return 100 if score["value"] > 0 else 0
    return max(0, min(100, round(50 + score["value"] / 20)))


def uci_move_details(fen: str, uci: str) -> dict:
    preview = GameService.new(fen)
    return preview.play_move(uci[:2], uci[2:4], uci[4:] or None)["move"]


def principal_variation_to_san(fen: str, pv: list[str], max_plies: int = 6) -> list[str]:
    """Convert a short, validated UCI PV into human-readable SAN moves."""
    board = chess.Board(fen)
    san_moves: list[str] = []
    for uci in pv[:max_plies]:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        san_moves.append(board.san(move))
        board.push(move)
    return san_moves


def tactical_alternative_lines(fen: str, variations: list[dict], player_color: str,
                               limit: int = 3, max_plies: int = 4) -> list[dict]:
    """Keep tactical events from engine-ranked alternatives to the top line."""
    alternatives = []
    for rank, variation in enumerate(variations[1:limit + 1], start=2):
        san_line = principal_variation_to_san(fen, variation.get("pv", []), max_plies)
        steps = describe_line(fen, san_line, player_color)
        tactical_steps = [
            step for step in steps
            if step["boardEvidence"]["newAttacks"]
            or step["boardEvidence"]["captured"]
            or step["boardEvidence"]["checksKing"]
            or step["boardEvidence"]["checkmate"]
        ]
        if tactical_steps:
            alternatives.append({
                "rank": rank,
                "status": "hypothetical",
                "steps": steps,
                "tacticalStepIndices": [steps.index(step) for step in tactical_steps],
            })
    return alternatives


def create_app(engine: Any | None = None, coach: Any | None = None) -> FastAPI:
    owns_engine = engine is None
    engine = engine or StockfishAdapter()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owns_engine:
            engine.close()

    app = FastAPI(title="ChessLens API", version="0.2.0", lifespan=lifespan)
    origins = [settings.cors_origin] if settings.cors_origin != "*" else ["*"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    games: dict[str, GameRecord] = {}
    coach = coach if coach is not None else (OllamaCoach() if settings.llm_enabled else None)
    if coach is None:
        logger.info("Ollama coach is disabled; set LLM_ENABLED=true to enable it")
    else:
        logger.info("Ollama coach is enabled with model %s", settings.ollama_model)

    @app.get("/api/opponents")
    async def opponents():
        return {"opponents": OPPONENTS}

    @app.post("/api/games", status_code=201)
    async def create_game(body: CreateGameRequest):
        opponent = OPPONENTS.get(body.opponentId, OPPONENTS["judit"])
        record = GameRecord.create(body.playerColor, opponent)
        games[record.game_id] = record
        return serialize_game(record)

    @app.get("/api/games/{game_id}")
    async def get_game(game_id: str):
        record = games.get(game_id)
        if not record:
            raise HTTPException(404, "GAME_NOT_FOUND")
        return serialize_game(record)

    @app.post("/api/games/{game_id}/moves")
    async def play_move(game_id: str, body: MoveRequest):
        record = games.get(game_id)
        if not record:
            raise HTTPException(404, "GAME_NOT_FOUND")
        state_before = record.game.state()
        if state_before["turn"] != record.player_color:
            raise HTTPException(409, "NOT_PLAYER_TURN")

        try:
            before_analysis = await asyncio.to_thread(
                engine.analyze,
                record.game.board.copy(stack=True),
                ANALYSIS_DEPTH,
                ANALYSIS_SKILL_LEVEL,
            )
            played = record.game.play_move(body.from_, body.to, body.promotion)
            after_analysis = await asyncio.to_thread(
                engine.analyze,
                record.game.board.copy(stack=True),
                ANALYSIS_DEPTH,
                ANALYSIS_SKILL_LEVEL,
                COACH_MULTIPV,
            )
            best_move_line = principal_variation_to_san(state_before["fen"], before_analysis.get("pv", []))
            opponent_best_line = principal_variation_to_san(played["fenAfter"], after_analysis.get("pv", []))
            move_analysis = build_move_analysis(
                fenBefore=state_before["fen"], fenAfter=played["fenAfter"], playedMove=played["move"],
                bestMove=uci_move_details(state_before["fen"], before_analysis["bestMove"]), mover=state_before["turn"],
                evaluationBefore=before_analysis["evaluation"], evaluationAfter=after_analysis["evaluation"],
                bestMoveLine=best_move_line,
                opponentBestLine=opponent_best_line,
            )
            move_analysis["alternativeOpponentLines"] = tactical_alternative_lines(
                played["fenAfter"], after_analysis.get("variations", []), record.player_color,
            )
            engine_move = None
            coach_reply = None
            if not played["state"]["isGameOver"] and after_analysis.get("bestMove"):
                coach_reply = uci_move_details(played["fenAfter"], after_analysis["bestMove"])
                bot_settings = BOT_SETTINGS_BY_DIFFICULTY.get(
                    record.opponent["difficulty"], BOT_SETTINGS_BY_DIFFICULTY["medium"]
                )
                bot_analysis = await asyncio.to_thread(
                    engine.analyze,
                    record.game.board.copy(stack=True),
                    bot_settings["depth"],
                    bot_settings["skill_level"],
                    bot_settings["multi_pv"],
                )
                if bot_analysis.get("bestMove"):
                    uci = choose_bot_move(record, bot_analysis, bot_settings)
                    engine_move = record.game.play_move(uci[:2], uci[2:4], uci[4:] or None)
            move_analysis["actualOpponentMove"] = engine_move and engine_move["move"]
            actual_reply_uci = (engine_move or {}).get("move", {}).get("uci")
            if actual_reply_uci:
                move_analysis["alternativeOpponentLines"] = [
                    line for line in move_analysis["alternativeOpponentLines"]
                    if not line.get("steps") or line["steps"][0]["move"].get("uci") != actual_reply_uci
                ]
            # The reply has now changed the position. Analyze from the real
            # board so forward warnings do not mix in branches where the bot
            # chose a different reply. Keep this shallower than the move review
            # because it is only a concise coaching look-ahead.
            if not record.game.board.is_game_over():
                forward_analysis = await asyncio.to_thread(
                    engine.analyze,
                    record.game.board.copy(stack=True),
                    FORWARD_LOOKAHEAD_DEPTH,
                    ANALYSIS_SKILL_LEVEL,
                    COACH_MULTIPV,
                )
                forward_fen = record.game.board.fen()
                forward_pv = principal_variation_to_san(
                    forward_fen, forward_analysis.get("pv", []), max_plies=3,
                )
                forward_lines = []
                if forward_pv:
                    forward_lines.append({
                        "rank": 1,
                        "status": "hypothetical",
                        "steps": describe_line(forward_fen, forward_pv, record.player_color),
                    })
                forward_lines.extend(tactical_alternative_lines(
                    forward_fen, forward_analysis.get("variations", []),
                    record.player_color, max_plies=3,
                ))
                move_analysis["forwardOpponentLines"] = forward_lines
            if hasattr(coach, "explain"):
                coach_result = await coach.explain(move_analysis, coach_reply)
            else:
                coach_result = build_fallback_coach(move_analysis, coach_reply)
            record.last_move_id = f"{record.game_id}-move-{len(record.game.board.move_stack)}"
            record.last_analysis = move_analysis
            record.last_engine_reply = coach_reply
            record.last_coach = coach_result
            record.coach_history.clear()
            record.coach_focus = "last-move"
            final_state = serialize_game(record)
            return {
                **final_state, "moveId": record.last_move_id, "playedMove": played["move"],
                "engineMove": engine_move and engine_move["move"],
                "analysis": {
                    "classification": move_analysis["classification"],
                    "score": format_score(move_analysis["evaluationAfter"]),
                    "whitePercent": score_to_white_percent(move_analysis["evaluationAfter"]),
                    "bestMove": move_analysis["bestMove"],
                    "lossInCentipawns": move_analysis["lossInCentipawns"],
                    "mateOutcome": move_analysis["mateOutcome"],
                    "bestMoveLine": move_analysis["bestMoveLine"],
                    "opponentBestLine": move_analysis["opponentBestLine"],
                    "principalVariation": move_analysis["principalVariation"],
                },
                "coach": coach_result, "gameState": final_state,
            }
        except IllegalMoveError as error:
            raise HTTPException(400, detail={"error": "ILLEGAL_MOVE", "message": str(error)})
        except StockfishUnavailable as error:
            raise HTTPException(503, detail={"error": "STOCKFISH_UNAVAILABLE", "message": str(error)})

    @app.post("/api/games/{game_id}/coach")
    async def coach_hint(game_id: str, body: CoachQuestionRequest):
        record = games.get(game_id)
        if not record:
            raise HTTPException(404, "GAME_NOT_FOUND")
        move_id = record.last_move_id
        if body.moveId is not None and body.moveId != move_id:
            raise HTTPException(409, "STALE_COACH_CONTEXT")
        focus = resolve_question_focus(body.question, record.coach_focus)
        current_board = record.game.board.copy(stack=True)
        current_fen = current_board.fen()
        current_analysis = None
        if focus == "current-position":
            current_analysis = {
                "fen": current_fen,
                "turn": "white" if current_board.turn else "black",
                "playerColor": record.player_color,
                "isGameOver": current_board.is_game_over(),
                "bestMove": None,
                "line": [],
            }
            if not current_board.is_game_over() and current_analysis["turn"] == record.player_color:
                try:
                    fresh = await asyncio.to_thread(
                        engine.analyze, current_board, ANALYSIS_DEPTH, ANALYSIS_SKILL_LEVEL, COACH_MULTIPV,
                    )
                except StockfishUnavailable as error:
                    raise HTTPException(503, detail={"error": "STOCKFISH_UNAVAILABLE", "message": str(error)})
                if fresh.get("bestMove"):
                    current_analysis["bestMove"] = uci_move_details(current_fen, fresh["bestMove"])
                    current_analysis["evaluation"] = fresh["evaluation"]
                    current_analysis["bestMoveFacts"] = move_facts(current_fen, current_analysis["bestMove"])
                    san_line = principal_variation_to_san(current_fen, fresh.get("pv", []))
                    current_analysis["line"] = describe_line(current_fen, san_line, record.player_color)
                    current_analysis["alternativeCandidateLines"] = tactical_alternative_lines(
                        current_fen, fresh.get("variations", []), record.player_color,
                    )
        history = list(record.coach_history) if focus == record.coach_focus else []
        current_has_move = current_analysis and current_analysis.get("bestMove")
        has_grounding = record.last_analysis if focus == "last-move" else current_has_move
        if has_grounding and hasattr(coach, "answer_question"):
            result = await coach.answer_question(
                question=body.question,
                analysis=record.last_analysis,
                engine_reply=record.last_engine_reply,
                current_fen=current_fen,
                previous_explanation=record.last_coach or {},
                history=list(history),
                current_analysis=current_analysis,
                focus=focus,
            )
        elif current_analysis is not None:
            result = build_current_answer(current_analysis, body.question)
        else:
            result = build_fallback_answer(body.question, record.last_analysis, record.last_engine_reply)
        # A move may have completed while Ollama was answering. Never save an old
        # answer as conversation context for a newer position.
        if record.last_move_id != move_id or record.game.board.fen() != current_fen:
            raise HTTPException(409, "STALE_COACH_CONTEXT")
        history.extend([
            {"role": "user", "content": body.question},
            {"role": "assistant", "content": result["text"]},
        ])
        record.coach_history = history[-6:]
        record.coach_focus = focus
        suggestion = current_analysis if current_analysis is not None else record.last_analysis
        recommendation = None
        if suggestion and suggestion.get("bestMove"):
            suggestion_fen = suggestion.get("fen", suggestion.get("fenBefore"))
            recommendation = {
                "fen": suggestion_fen,
                "position": GameService.new(suggestion_fen).position(),
                "move": suggestion["bestMove"],
                "description": describe_move_for_player(suggestion_fen, suggestion["bestMove"]),
            }
        return {**result, "gameId": game_id, "moveId": move_id, "focus": focus, "recommendation": recommendation}

    ui_root = Path(__file__).resolve().parent.parent / "ui"
    if ui_root.exists():
        app.mount("/", StaticFiles(directory=ui_root, html=True), name="ui")

    return app


app = create_app()
