from __future__ import annotations

import threading

import chess
import chess.engine

from .config import settings


class StockfishUnavailable(RuntimeError):
    """Raised when the configured Stockfish executable cannot be started."""


class StockfishAdapter:
    """Small synchronous adapter around the UCI Stockfish process.

    The rest of the application only sees normalized evaluations and UCI moves;
    it does not depend on python-chess engine details.
    """

    def __init__(
        self,
        path: str | None = None,
        depth: int | None = None,
        timeout_seconds: float | None = None,
    ):
        self.path = path or settings.stockfish_path
        self.depth = depth or settings.stockfish_depth
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.stockfish_timeout_seconds
        if self.timeout_seconds <= 0:
            raise ValueError("Stockfish timeout_seconds must be positive")
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = threading.Lock()

    def _ensure_engine(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            try:
                self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
            except (FileNotFoundError, OSError) as error:
                raise StockfishUnavailable(
                    f"Stockfish executable not found: {self.path}. "
                    "Set STOCKFISH_PATH to its full path."
                ) from error
        return self._engine

    def analyze(
        self,
        board: chess.Board,
        depth: int | None = None,
        skill_level: int = 20,
        multi_pv: int = 1,
    ) -> dict:
        if not isinstance(skill_level, int) or not 0 <= skill_level <= 20:
            raise ValueError("Stockfish skill_level must be an integer from 0 to 20")
        if not isinstance(multi_pv, int) or not 1 <= multi_pv <= 20:
            raise ValueError("Stockfish multi_pv must be an integer from 1 to 20")

        with self._lock:
            engine = self._ensure_engine()
            try:
                engine.configure({"Skill Level": skill_level})
                result = engine.analyse(
                    board,
                    chess.engine.Limit(depth=depth or self.depth, time=self.timeout_seconds),
                    multipv=multi_pv,
                )
            except chess.engine.EngineError as error:
                self.close()
                raise StockfishUnavailable("Stockfish analysis failed or timed out") from error

        infos = result if isinstance(result, list) else [result]
        infos = [candidate for candidate in infos if candidate.get("pv")]
        if not infos:
            return {"evaluation": {"kind": "centipawn", "value": 0}, "bestMove": None, "pv": [], "candidateMoves": [], "variations": []}
        info = infos[0]

        def format_evaluation(candidate: dict) -> dict:
            score = candidate["score"].pov(chess.WHITE)
            if score.is_mate():
                return {"kind": "mate", "value": score.mate()}
            return {"kind": "centipawn", "value": score.score(mate_score=100000)}

        evaluation = format_evaluation(info)

        pv = [move.uci() for move in info.get("pv", [])]
        variations = [
            {"evaluation": format_evaluation(candidate), "pv": [move.uci() for move in candidate["pv"]]}
            for candidate in infos
        ]
        candidates = [variation["pv"][0] for variation in variations]
        return {
            "evaluation": evaluation,
            "bestMove": pv[0] if pv else None,
            "pv": pv,
            "candidateMoves": candidates,
            "variations": variations,
        }

    def close(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def __del__(self):  # pragma: no cover - best-effort process cleanup
        try:
            self.close()
        except Exception:
            pass
