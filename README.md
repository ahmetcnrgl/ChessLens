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
py -m uvicorn backend.main:app --reload --port 8000
```

Without Stockfish, game creation and API documentation still work, but a move
analysis returns `503 STOCKFISH_UNAVAILABLE`. This is intentional: the API must
not invent an evaluation when the authority engine is missing.

Run the Python tests with:

```powershell
py -m pytest -q
```

The old Node.js server remains temporarily as a reference while the UI adapter
is moved to the FastAPI endpoint. We will remove it only after parity tests and
the UI smoke test pass.
