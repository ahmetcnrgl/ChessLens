from __future__ import annotations

DEFAULT_CLASSIFICATION_THRESHOLDS = {
    "best": 10,
    "good": 50,
    "inaccuracy": 100,
    "mistake": 200,
}


def calculate_centipawn_loss(evaluation_before: dict, evaluation_after: dict, mover: str) -> int:
    if evaluation_before.get("kind") != "centipawn" or evaluation_after.get("kind") != "centipawn":
        raise ValueError("Centipawn loss requires centipawn evaluations")
    raw_loss = evaluation_before["value"] - evaluation_after["value"] if mover == "white" else evaluation_after["value"] - evaluation_before["value"]
    return max(0, round(raw_loss))


def classify_centipawn_loss(loss: int, thresholds: dict | None = None) -> str:
    thresholds = thresholds or DEFAULT_CLASSIFICATION_THRESHOLDS
    if loss <= thresholds["best"]:
        return "best"
    if loss <= thresholds["good"]:
        return "good"
    if loss <= thresholds["inaccuracy"]:
        return "inaccuracy"
    if loss <= thresholds["mistake"]:
        return "mistake"
    return "blunder"


def _mate_from_mover_perspective(evaluation: dict | None, mover: str) -> int | None:
    if not evaluation or evaluation.get("kind") != "mate":
        return None
    return evaluation["value"] if mover == "white" else -evaluation["value"]


def analyze_evaluation_change(evaluation_before: dict, evaluation_after: dict, mover: str) -> dict:
    if evaluation_before.get("kind") == "centipawn" and evaluation_after.get("kind") == "centipawn":
        loss = calculate_centipawn_loss(evaluation_before, evaluation_after, mover)
        return {"classification": classify_centipawn_loss(loss), "lossInCentipawns": loss, "mateOutcome": None}

    before_mate = _mate_from_mover_perspective(evaluation_before, mover)
    after_mate = _mate_from_mover_perspective(evaluation_after, mover)
    if after_mate is not None and after_mate < 0:
        return {"classification": "blunder", "lossInCentipawns": None, "mateOutcome": "mated"}
    if before_mate is not None and before_mate > 0 and (after_mate is None or after_mate < 0):
        return {"classification": "blunder", "lossInCentipawns": None, "mateOutcome": "missed-forced-mate"}
    if after_mate is not None and after_mate > 0:
        return {"classification": "best", "lossInCentipawns": None, "mateOutcome": "found-forced-mate"}
    return {"classification": "inaccuracy", "lossInCentipawns": None, "mateOutcome": "mate-evaluation-changed"}


def build_move_analysis(**kwargs) -> dict:
    outcome = analyze_evaluation_change(kwargs["evaluationBefore"], kwargs["evaluationAfter"], kwargs["mover"])
    return {
        "fenBefore": kwargs["fenBefore"],
        "fenAfter": kwargs["fenAfter"],
        "playedMove": kwargs["playedMove"],
        "bestMove": kwargs["bestMove"],
        "mover": kwargs["mover"],
        "evaluationBefore": kwargs["evaluationBefore"],
        "evaluationAfter": kwargs["evaluationAfter"],
        **outcome,
    }
