from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .coach import OllamaCoach, build_fallback_coach
from .config import settings
from .game_service import GameRecord, IllegalMoveError, GameService
from .move_analyzer import build_move_analysis
from .schemas import CreateGameRequest, MoveRequest
from .stockfish_adapter import StockfishAdapter, StockfishUnavailable


OPPONENTS = {
    "capablanca": {"id": "capablanca", "name": "José", "level": "Kolay bot", "difficulty": "easy", "face": "avatar-capablanca"},
    "judit": {"id": "judit", "name": "Judit", "level": "Orta bot", "difficulty": "medium", "face": "avatar-judit"},
    "magnus": {"id": "magnus", "name": "Magnus", "level": "Zor bot", "difficulty": "hard", "face": "avatar-magnus"},
}
ANALYSIS_DEPTH = 12
ANALYSIS_SKILL_LEVEL = 20
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
    coach = coach or OllamaCoach()

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
            )
            move_analysis = build_move_analysis(
                fenBefore=state_before["fen"], fenAfter=played["fenAfter"], playedMove=played["move"],
                bestMove=uci_move_details(state_before["fen"], before_analysis["bestMove"]), mover=state_before["turn"],
                evaluationBefore=before_analysis["evaluation"], evaluationAfter=after_analysis["evaluation"],
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
            if hasattr(coach, "explain"):
                coach_result = await coach.explain(move_analysis, coach_reply)
            else:
                coach_result = build_fallback_coach(move_analysis, coach_reply)
            record.last_move_id = f"{record.game_id}-move-{len(record.game.board.move_stack)}"
            final_state = serialize_game(record)
            return {
                **final_state, "moveId": record.last_move_id, "playedMove": played["move"],
                "engineMove": engine_move and engine_move["move"],
                "analysis": {"classification": move_analysis["classification"], "score": format_score(move_analysis["evaluationAfter"]), "whitePercent": score_to_white_percent(move_analysis["evaluationAfter"]), "bestMove": move_analysis["bestMove"], "lossInCentipawns": move_analysis["lossInCentipawns"], "mateOutcome": move_analysis["mateOutcome"], "principalVariation": after_analysis.get("pv", [])},
                "coach": coach_result, "gameState": final_state,
            }
        except IllegalMoveError as error:
            raise HTTPException(400, detail={"error": "ILLEGAL_MOVE", "message": str(error)})
        except StockfishUnavailable as error:
            raise HTTPException(503, detail={"error": "STOCKFISH_UNAVAILABLE", "message": str(error)})

    @app.post("/api/games/{game_id}/coach")
    async def coach_hint(game_id: str):
        if game_id not in games:
            raise HTTPException(404, "GAME_NOT_FOUND")
        return {"text": "Önce rakibin son hamlesini, sonra merkezdeki aday hamlelerini kontrol et.", "betterMove": "—"}

    ui_root = Path(__file__).resolve().parent.parent / "ui"
    if ui_root.exists():
        app.mount("/", StaticFiles(directory=ui_root, html=True), name="ui")

    return app


app = create_app()
