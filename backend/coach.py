from __future__ import annotations

import json
import os
import re

import httpx

from .config import settings


def build_fallback_coach(analysis: dict, engine_reply: dict | None = None) -> dict:
    classification = analysis["classification"]
    labels = {
        "best": "çok iyi",
        "good": "iyi",
        "inaccuracy": "küçük bir isabetsizlik",
        "mistake": "hata",
        "blunder": "ciddi hata",
    }
    summary = f"Bu hamle {labels.get(classification, classification)} bir hamleydi."
    if analysis.get("lossInCentipawns") is not None:
        summary += f" Motor değerlendirmesinde yaklaşık {analysis['lossInCentipawns']} centipawn kayıp oluştu."
    better_move = analysis.get("bestMove", {}).get("san", "—")
    if engine_reply:
        summary += f" Stockfish cevabı: {engine_reply.get('san', '—')}."
    return {
        "summary": summary,
        "explanation": "Önce hamlenin oluşturduğu tehdidi, sonra rakibin en güçlü cevabını kontrol et.",
        "lesson": "Her hamleden önce rakibin şah çekiş, alış ve tehditlerini üçlü kontrol olarak düşün.",
        "confidence": "low",
        "text": f"{summary} Önce hamlenin oluşturduğu tehdidi, sonra rakibin en güçlü cevabını kontrol et.",
        "betterMove": better_move,
        "tone": "calm",
        "source": "fallback",
    }


def build_prompt(analysis: dict, engine_reply: dict | None = None) -> str:
    payload = {
        "classification": analysis["classification"],
        "mover": analysis["mover"],
        "playedMove": analysis["playedMove"],
        "bestMove": analysis["bestMove"],
        "evaluationBefore": analysis["evaluationBefore"],
        "evaluationAfter": analysis["evaluationAfter"],
        "lossInCentipawns": analysis.get("lossInCentipawns"),
        "engineReply": engine_reply,
    }
    return (
        "Sen Türkçe konuşan bir satranç koçusun. Yalnızca verilen motor verisini kullan. "
        "Kısa, yargılamayan ve insanın uygulayabileceği bir açıklama üret. "
        "JSON dışında hiçbir şey yazma. Alanlar: summary, explanation, lesson, confidence.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


class OllamaCoach:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model

    async def explain(self, analysis: dict, engine_reply: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "stream": False, "format": "json", "messages": [{"role": "user", "content": build_prompt(analysis, engine_reply)}]},
                )
                response.raise_for_status()
                raw = response.json().get("message", {}).get("content", "")
                parsed = json.loads(re.sub(r"^```json\s*|\s*```$", "", raw.strip()))
                return self._validate(parsed, analysis)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return build_fallback_coach(analysis, engine_reply)

    @staticmethod
    def _validate(value: dict, analysis: dict) -> dict:
        required = ("summary", "explanation", "lesson", "confidence")
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) for key in required):
            raise ValueError("Invalid coach response")
        if value["confidence"] not in {"low", "medium", "high"}:
            raise ValueError("Invalid confidence")
        cleaned = {key: value[key].strip() for key in required}
        return {
            **cleaned,
            "text": f"{cleaned['summary']} {cleaned['explanation']}",
            "betterMove": analysis.get("bestMove", {}).get("san", "—"),
            "tone": "calm",
            "source": "ollama",
        }
