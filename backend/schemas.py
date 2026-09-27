from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateGameRequest(BaseModel):
    opponentId: str = "judit"
    playerColor: str = Field(default="white", pattern="^(white|black)$")


class MoveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", min_length=2, max_length=2)
    to: str = Field(min_length=2, max_length=2)
    promotion: str | None = None


class CoachResponse(BaseModel):
    text: str
    betterMove: str = "—"
    source: str = "fallback"
    tone: str | None = None


class MoveResponse(BaseModel):
    """Stable top-level contract consumed by ui/api.js and ui/app.js."""

    model_config = ConfigDict(extra="allow")

    gameId: str
    moveId: str
    playedMove: dict[str, Any]
    engineMove: dict[str, Any] | None = None
    coach: CoachResponse
