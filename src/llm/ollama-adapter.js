import { buildCoachPrompt, getCoachResponseSchema, validateCoachExplanation } from "./coach-explanation.js";

function parseJsonContent(content) {
  const text = String(content ?? "").trim();
  const withoutFence = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  return JSON.parse(withoutFence);
}

export class OllamaAdapter {
  constructor({
    baseUrl = process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434",
    model = process.env.OLLAMA_MODEL ?? "qwen3:8b",
    timeoutMs = 60_000,
    fetchImpl = fetch,
  } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.model = model;
    this.timeoutMs = timeoutMs;
    this.fetchImpl = fetchImpl;
  }

  async explain({ moveAnalysis, engineMove }) {
    const prompt = buildCoachPrompt({ moveAnalysis, engineMove });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchImpl(`${this.baseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          model: this.model,
          stream: false,
          think: false,
          format: getCoachResponseSchema(),
          messages: [
            { role: "system", content: prompt.system },
            { role: "user", content: prompt.user },
          ],
          options: { temperature: 0.2 },
        }),
      });

      if (!response.ok) {
        throw new Error(`Ollama request failed: ${response.status}`);
      }

      const payload = await response.json();
      return validateCoachExplanation(parseJsonContent(payload.message?.content));
    } finally {
      clearTimeout(timeout);
    }
  }
}
