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
  "principalVariation": ["e5", "Nf3"]
}
```

Centipawn loss is calculated from the mover's perspective. Mate transitions are
classified separately and are not converted into fake centipawn values.
The FastAPI server can be started with `py -m uvicorn backend.main:app --reload
--port 8000` and serves both the API and the files under `ui/` at
`http://127.0.0.1:8000`. The previous Node server remains as a temporary
reference until the Python parity/smoke checks are complete.

The browser sends intent; it must not be trusted as the source of truth for FEN,
legality, score, or advantage. The backend should validate the move, update the
game state, then return the authoritative state and analysis. `gameId` and
`moveId` also give the UI enough identity to ignore stale analysis responses.

## Local Ollama coach

The LLM is an explanation layer only. Stockfish remains authoritative for the
evaluation and move classification. The local coach is disabled by default so
the application and tests remain usable without a downloaded model.

After installing a model, enable it with:

```powershell
ollama pull qwen3:8b
$env:LLM_ENABLED = "true"
$env:OLLAMA_MODEL = "qwen3:8b"
npm start
```

The server sends an allowlisted `MoveAnalysis` subset to Ollama, validates the
JSON response, and falls back to the deterministic coach text when Ollama is
unavailable or returns an invalid response. `OLLAMA_BASE_URL` can be used to
point to a different local Ollama address.

The response adds `coach.source` (`ollama` or `fallback`) and, for an Ollama
response, `coach.tone`. This makes model failures visible without making them
game-state failures.
