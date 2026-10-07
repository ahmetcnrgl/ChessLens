from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings read once at application startup."""

    stockfish_path: str = os.getenv("STOCKFISH_PATH", "stockfish")
    stockfish_depth: int = int(os.getenv("STOCKFISH_DEPTH", "12"))
    stockfish_timeout_seconds: float = float(os.getenv("STOCKFISH_TIMEOUT_SECONDS", "8"))
    llm_enabled: bool = os.getenv("LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    ollama_url: str = os.getenv(
        "OLLAMA_BASE_URL",
        os.getenv("OLLAMA_URL", "http://localhost:11434"),
    )
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45"))
    cors_origin: str = os.getenv("CORS_ORIGIN", "*")


settings = Settings()
