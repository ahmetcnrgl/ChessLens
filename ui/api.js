/*
 * Boundary between the prototype UI and the future backend.
 * Keep DTO shapes stable; replace these mock methods with fetch calls later.
 */
const chessLensApi = (() => {
  const opponents = {
    capablanca: { id: "capablanca", name: "José", difficulty: "easy", face: "avatar-capablanca" },
    judit: { id: "judit", name: "Judit", difficulty: "medium", face: "avatar-judit" },
    magnus: { id: "magnus", name: "Magnus", difficulty: "hard", face: "avatar-magnus" },
  };

  const initialPosition = {
    a8: "br", c8: "bb", d8: "bq", e8: "bk", h8: "br",
    a6: "bp", b7: "bp", c7: "bp", d6: "bp", e5: "bp", f7: "bp", g7: "bp", h7: "bp",
    c6: "bn", f6: "bn", e7: "bb",
    a1: "wr", b1: "wn", c1: "wb", d1: "wq", e1: "wr", g1: "wk",
    a2: "wp", b2: "wp", c3: "wp", d2: "wp", e4: "wp", f2: "wp", g2: "wp", h2: "wp",
    a4: "wb", f3: "wn",
  };
  const legalSquares = ["d4", "e3", "h4", "g5"];
  let gameCounter = 0;

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const createGameId = () => `local-game-${++gameCounter}`;

  async function createGame({ opponentId, playerColor = "white" }) {
    const opponent = opponents[opponentId] ?? opponents.judit;
    return {
      gameId: createGameId(),
      status: "active",
      playerColor,
      opponent,
      position: clone(initialPosition),
      legalSquares: [...legalSquares],
      lastMoveId: null,
      coach: null,
    };
  }

  async function analyzeMove({ gameId, from, to }) {
    const best = to === "d4";
    return {
      gameId,
      moveId: `${gameId}-move-${Date.now()}`,
      status: "active",
      playedMove: { from, to, san: best ? "d4" : to },
      analysis: {
        classification: best ? "good" : "inaccuracy",
        score: best ? "+0.9" : "+0.1",
        whitePercent: best ? 64 : 52,
        bestMove: { san: "d4" },
      },
      coach: {
        text: best
          ? "d4 çok iyi bir seçim. Merkezi açıyor, filini oyuna sokuyor ve rakibin e5 piyonuna baskıyı artırıyor."
          : `${to} oynanabilir; ancak merkezdeki d4 fırsatını kaçırdığı için inisiyatifi biraz azaltıyor.`,
        betterMove: "12. d4",
      },
    };
  }

  async function askCoach({ gameId, question }) {
    const normalized = question.toLocaleLowerCase("tr");
    const text = /üstün|önde|avantaj/.test(normalized)
      ? "Bu örnek konumda beyaz biraz daha rahat. Merkezde alan kazanabilecek olması önemli; yine de siyahın karşı oyununa dikkat."
      : /neden|iyi|kötü/.test(normalized)
        ? "At gelişiyor, şahın güvende kalıyor ve merkezdeki e5 ile d4 karelerini kontrol ediyor."
        : /hamle|d4|fikir|merkez/.test(normalized)
          ? "d4 daha güçlü bir fikir. Merkezi hemen sorguluyor, c1 filinin önünü açıyor ve rakibin rahat gelişmesini engelliyor."
          : "Önce rakibin tehdidine, sonra merkezdeki aday hamlelere bak. Bu iki adım konumu daha sakin okumayı sağlar.";
    return { gameId, text, betterMove: "12. d4" };
  }

  return {
    mode: "mock",
    opponents,
    initialPosition: clone(initialPosition),
    legalSquares: [...legalSquares],
    createGame,
    analyzeMove,
    askCoach,
  };
})();

window.chessLensApi = chessLensApi;
