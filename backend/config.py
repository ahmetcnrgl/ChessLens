from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings read once at application startup."""

    stockfish_path: str = os.getenv("STOCKFISH_PATH", "stockfish")
    stockfish_depth: int = int(os.getenv("STOCKFISH_DEPTH", "12"))
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    cors_origin: str = os.getenv("CORS_ORIGIN", "*")


settings = Settings()
