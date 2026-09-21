# ChessLens UI / Backend Contract

The prototype talks only to `ui/api.js`. It currently exposes an in-memory mock
so the UI can be tested without a server. The future implementation can replace
these methods with HTTP calls without changing the screen components.

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

The browser sends intent; it must not be trusted as the source of truth for FEN,
legality, score, or advantage. The backend should validate the move, update the
game state, then return the authoritative state and analysis. `gameId` and
`moveId` also give the UI enough identity to ignore stale analysis responses.
