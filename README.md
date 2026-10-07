# ChessLens

ChessLens is an AI chess coach: Stockfish establishes chess correctness and a
language model turns the structured result into an understandable explanation.

## Python FastAPI backend (current direction)

The backend is now being migrated to Python. The API contract remains the same
so the existing UI can switch from the JavaScript server without redesigning its
data flow.

```powershell
py -m pip install -r backend/requirements.txt
py -m uvicorn backend.main:app --reload --port 8000
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation
is at `/docs`.

### Stockfish configuration

The Python adapter uses the standard UCI interface and expects a native
Stockfish executable. Set its full path before starting the server:

```powershell
$env:STOCKFISH_PATH = "C:\\path\\to\\stockfish.exe"
$env:STOCKFISH_TIMEOUT_SECONDS = "8"
py -m uvicorn backend.main:app --reload --port 8000
```

Without Stockfish, game creation and API documentation still work, but a move
analysis returns `503 STOCKFISH_UNAVAILABLE`. This is intentional: the API must
not invent an evaluation when the authority engine is missing. The timeout is a
hard upper bound for one engine analysis request; lower values improve
responsiveness but can reduce analysis quality.

### Optional local LLM coach

The LLM is disabled by default. Stockfish remains the authority for legality,
evaluation, and classification; the model only turns that structured result
into a Turkish explanation. After installing a local Ollama model, enable the
coach explicitly:

The integration code is in `backend/llm_integration.py`: it builds the prompt,
sends the Ollama request, and validates the structured response. The
deterministic response used when the model is disabled or unavailable is in
`backend/coach.py`.

```powershell
ollama pull qwen3:8b
$env:LLM_ENABLED = "true"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen3:8b"
$env:OLLAMA_TIMEOUT_SECONDS = "45"
py -m uvicorn backend.main:app --reload --port 8000
```

If Ollama is unavailable or returns invalid JSON, the API keeps the move result
and returns the deterministic fallback explanation.

The coach accepts follow-up questions through `/api/games/{gameId}/coach`.
Next-move questions analyze the current board again; last-move review uses the
saved analysis. Move descriptions explicitly identify the piece and both
squares. A next-move fallback still gives the validated current recommendation
when the local model times out or returns an invalid explanation. The model
response timeout defaults to 45 seconds and is configurable above.

Run the Python tests with:

```powershell
py -m pytest -q
```

The old Node.js server remains temporarily as a reference while the UI adapter
is moved to the FastAPI endpoint. We will remove it only after parity tests and
the UI smoke test pass.
