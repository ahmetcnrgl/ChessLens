"""Small repeatable local Qwen evaluation for grounding failures.

Run from the project root: py -m scripts.evaluate_coach
This sends two synthetic, board-legal scenarios to the configured Ollama model.
Engine evaluation is deliberately absent; the script measures grounding, not
whether a move is objectively best.
No chess result is written to disk.
"""

from __future__ import annotations

import asyncio
import json
import time

import chess
import httpx

from backend.config import settings
from backend.coach import build_fallback_coach
from backend.llm_integration import COACH_RESPONSE_SCHEMA, OllamaCoach, build_prompt, response_context


def scenarios() -> list[tuple[str, dict, dict, tuple[str, ...]]]:
    fork_fen = "4k3/8/4p3/5B2/1n6/4Q3/8/R6K b - - 0 1"
    board = chess.Board(fork_fen)
    board.push_uci("b4c2")
    defensible_attack = {
        "fenBefore": fork_fen, "fenAfter": board.fen(),
        "playedMove": {"uci": "b4c2"}, "bestMove": {"uci": "b4c2"},
        "actualOpponentMove": {"uci": "f5c2"},
        "mover": "black", "classification": "unclassified",
        "evaluationBefore": None, "evaluationAfter": None,
        "lossInCentipawns": None, "mateOutcome": None,
        "bestMoveLine": ["Nc2", "Bxc2"], "opponentBestLine": ["Bxc2"],
    }

    opening = chess.Board()
    opening.push_uci("e2e4")
    ordinary_reply = {
        "fenBefore": chess.STARTING_FEN, "fenAfter": opening.fen(),
        "playedMove": {"uci": "e2e4"}, "bestMove": {"uci": "e2e4"},
        "actualOpponentMove": {"uci": "e7e5"},
        "mover": "white", "classification": "unclassified",
        "evaluationBefore": None, "evaluationAfter": None,
        "lossInCentipawns": None, "mateOutcome": None,
        "bestMoveLine": ["e4", "e5", "Nf3"], "opponentBestLine": ["e5", "Nf3"],
    }
    return [
        ("defensible_attack", defensible_attack, {"uci": "f5c2"}, ("vezir", "kale", "fil")),
        ("ordinary_reply", ordinary_reply, {"uci": "e7e5"}, ("rakip", "e5", "d5")),
    ]


async def main() -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        for name, analysis, engine_reply, required_terms in scenarios():
            started = time.monotonic()
            prompt = build_prompt(analysis, engine_reply)
            try:
                response = await client.post(
                    f"{settings.ollama_url.rstrip('/')}/api/chat",
                    json={
                        "model": settings.ollama_model, "stream": False, "think": False,
                        "format": COACH_RESPONSE_SCHEMA, "options": {"temperature": 0.2},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": "Son hamlemi açıkla."},
                        ],
                    },
                )
                response.raise_for_status()
                raw = json.loads(response.json()["message"]["content"])
                context = response_context(analysis, engine_reply)
                context["automaticMoveReview"] = True
                context["enforceFactCoverage"] = True
                try:
                    accepted = OllamaCoach._validate(raw, context)
                    validation = {
                        "accepted": True, "text": accepted["text"], "lesson": accepted["lesson"],
                        "missingRequiredTerms": [term for term in required_terms if term not in accepted["text"].lower()],
                    }
                except (KeyError, TypeError, ValueError) as error:
                    validation = {
                        "accepted": False, "reason": str(error),
                        "fallbackText": build_fallback_coach(analysis, engine_reply)["text"],
                    }
                result = {"scenario": name, "raw": raw, "validation": validation,
                          "elapsedSeconds": round(time.monotonic() - started, 1)}
            except (httpx.HTTPError, KeyError, ValueError) as error:
                result = {"scenario": name, "error": f"{type(error).__name__}: {error}",
                          "elapsedSeconds": round(time.monotonic() - started, 1)}
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
