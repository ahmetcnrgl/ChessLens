# ChessLens UI / Backend Contract

The browser talks to the local HTTP server through `ui/api.js`. Game state remains
server-authoritative; the browser sends move intent and receives the updated state.

## Planned endpoints

```text
GET  /api/opponents
POST /api/games
GET  /api/games/:gameId
POST /api/games/:gameId/moves
POST /api/games/:gameId/coach
```

Create-game request:

```json
{ "opponentId": "judit", "playerColor": "white" }
```

Game responses must include a stable `gameId`, server-authoritative position
data, the selected opponent, and `lastMoveId`. Move responses include a unique
`moveId`, the played move, engine analysis, and the coach explanation.

Move request:

```json
{ "from": "e2", "to": "e4", "promotion": null }
```

The move response contains `gameState`, the validated `playedMove`, the optional
`engineMove`, normalized Stockfish analysis, deterministic move classification,
and a deterministic coach fallback. The analysis includes:

```json
{
  "classification": "best",
  "score": "+0.35",
  "whitePercent": 52,
  "bestMove": { "uci": "e2e4", "san": "e4" },
  "lossInCentipawns": 0,
  "mateOutcome": null,
  "bestMoveLine": ["e4", "e5", "Nf3"],
  "opponentBestLine": ["e5", "Nf3"],
  "principalVariation": ["e5", "Nf3"]
}
```

Centipawn loss is calculated from the mover's perspective. Mate transitions are
classified separately and are not converted into fake centipawn values.
The coach receives the validated `fenBefore`, `fenAfter`, `mateOutcome`, and two
short SAN lines: `bestMoveLine` starts before the user's move, while
`opponentBestLine` starts after it. `principalVariation` remains an alias for
`opponentBestLine` for existing UI consumers.
The FastAPI server can be started with `py -m uvicorn backend.main:app --reload
--port 8000` and serves both the API and the files under `ui/` at
`http://127.0.0.1:8000`. The previous Node server remains as a temporary
reference until the Python parity/smoke checks are complete.

The browser sends intent; it must not be trusted as the source of truth for FEN,
legality, score, or advantage. The backend should validate the move, update the
game state, then return the authoritative state and analysis. `gameId` and
`moveId` also give the UI enough identity to ignore stale analysis responses.

## Coach questions

`POST /api/games/:gameId/coach` accepts questions about the last move or the next
move from the current position:

```json
{ "question": "Önerdiğin hamle neden daha iyi?", "moveId": "<lastMoveId>" }
```

The question is required (1–2000 non-whitespace characters). Questions such as
`bir sonraki hamlem ne olmalı` trigger a fresh, depth-12/skill-20 analysis of the
actual current board, including the opponent's actual move. Retrospective
questions use the saved last-move analysis. Short follow-ups such as `neden?`
retain the previous topic. Switching topics clears the short chat history;
each topic retains at most three question/answer pairs. The client cannot supply
authoritative analysis. A new move resets the topic to last-move review. A stale
`moveId`, or a board change while the answer is prepared, returns
`409 STALE_COACH_CONTEXT`.

The response contains `text`, `betterMove`, `source`, `gameId`, `moveId`, `focus`
(`last-move` or `current-position`), and an optional `recommendation` containing
the corresponding `fen`, `position`, validated `move`, and readable `description`.
The board preview uses this recommendation rather than always showing the old
last-move alternative.
Follow-up answers use `betterMove: "—"` so unrelated questions do not repeatedly
append the same recommendation. If the model is unavailable, the response says
that a detailed answer could not be prepared rather than returning a pretend
generic explanation. For next-move questions, a failed model response still
returns the fresh legal recommendation and board-verified facts. A next-move
question can also be asked before the first move. A finished game or the
opponent's turn returns a factual status message without inventing a move.

The chat does not append a separate recommendation row or speak `betterMove`.
Move explanations and the board preview explicitly name the piece, origin, and
destination (for example `e2 karesindeki piyonunu e4 karesine sür`).
Square names are permitted in prose; compressed SAN/UCI and engine metrics are
not player-facing explanation text. Every supplied continuation step is legally
simulated to attach the correct actor, origin, destination, and readable move.
Bare pawn notation such as `c5 olursa` and explicit moves outside the supplied
analysis are rejected. These checks reduce known failures; they do not prove
every strategic sentence correct.

Automatic move-review `summary` is generated from the server's actual
`playedMove` and classification, not from the model's choice of move. The model
receives explicit player/opponent colors and legal move identities. Explicit
piece and actor/color claims in origin-to-destination descriptions are checked
against those identities; a conflicting explanation uses the deterministic
fallback. `source: "ollama"` identifies an accepted LLM explanation even though
its automatic summary is server-generated. This is a targeted correctness guard,
not complete semantic validation of free-form chess prose.

## Local Ollama coach

The LLM is an explanation layer only. Stockfish remains authoritative for the
evaluation and move classification. The local coach is disabled by default so
the application and tests remain usable without a downloaded model.

After installing a model, enable it with:

```powershell
ollama pull qwen3:8b
$env:LLM_ENABLED = "true"
$env:OLLAMA_MODEL = "qwen3:8b"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_TIMEOUT_SECONDS = "45"
py -m uvicorn backend.main:app --reload --port 8000
```

The server sends an allowlisted `MoveAnalysis` subset to Ollama, validates the
JSON response, and falls back to the deterministic coach text when Ollama is
unavailable or returns an invalid response. `OLLAMA_BASE_URL` can be used to
point to a different local Ollama address.

The response adds `coach.source` (`ollama` or `fallback`) and, for an Ollama
response, `coach.tone`. This makes model failures visible without making them
game-state failures.
