from __future__ import annotations

import os
import threading
from pathlib import Path

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

    def __init__(self, path: str | None = None, depth: int = 12):
        self.path = path or settings.stockfish_path
        self.depth = depth or settings.stockfish_depth
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
            engine.configure({"Skill Level": skill_level})
            result = engine.analyse(
                board,
                chess.engine.Limit(depth=depth or self.depth),
                multipv=multi_pv,
            )

        infos = result if isinstance(result, list) else [result]
        infos = [candidate for candidate in infos if candidate.get("pv")]
        if not infos:
            return {"evaluation": {"kind": "centipawn", "value": 0}, "bestMove": None, "pv": [], "candidateMoves": []}
        info = infos[0]

        score = info["score"].pov(chess.WHITE)
        if score.is_mate():
            evaluation = {"kind": "mate", "value": score.mate()}
        else:
            evaluation = {"kind": "centipawn", "value": score.score(mate_score=100000)}

        pv = [move.uci() for move in info.get("pv", [])]
        candidates = [candidate["pv"][0].uci() for candidate in infos]
        return {
            "evaluation": evaluation,
            "bestMove": pv[0] if pv else None,
            "pv": pv,
            "candidateMoves": candidates,
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
