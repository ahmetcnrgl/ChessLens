const chessLensApi = (() => {
  const opponents = {
    capablanca: { id: "capablanca", name: "José", level: "Kolay bot", difficulty: "easy", face: "avatar-capablanca" },
    judit: { id: "judit", name: "Judit", level: "Orta bot", difficulty: "medium", face: "avatar-judit" },
    magnus: { id: "magnus", name: "Magnus", level: "Zor bot", difficulty: "hard", face: "avatar-magnus" },
  };

  async function request(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.message ?? body.error ?? "API request failed");
    return body;
  }

  return {
    mode: "http",
    opponents,
    initialPosition: {},
    legalSquares: [],
    getGame: (gameId) => request(`/api/games/${gameId}`),
    createGame: ({ opponentId, playerColor = "white" }) => request("/api/games", {
      method: "POST",
      body: JSON.stringify({ opponentId, playerColor }),
    }),
    analyzeMove: ({ gameId, from, to, promotion }) => request(`/api/games/${gameId}/moves`, {
      method: "POST",
      body: JSON.stringify({ from, to, promotion: promotion ?? null }),
    }),
    askCoach: ({ gameId, question, moveId }) => request(`/api/games/${gameId}/coach`, {
      method: "POST",
      body: JSON.stringify({ question, moveId }),
    }),
  };
})();

window.chessLensApi = chessLensApi;
