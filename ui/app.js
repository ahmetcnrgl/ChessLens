const api = window.chessLensApi;
const masters = api.opponents;
let position = api.initialPosition;
const files = ["a", "b", "c", "d", "e", "f", "g", "h"];
let legalSquares = new Set(api.legalSquares);
let selectedSquare = null;
let selectedMaster = null;
let focusedSquare = "e2";
let selectedEmoji = "🧠";
let boardFlipped = false;
let typingTimer;
let gameState = null;
let latestAnalysisRequest = 0;
let moveAnimations = [];
let audioContext = null;
let busy = false;
let coachingBusy = false;
let lesson = null;
let previewing = false;
let finishTyping = null;
let lastMove = null;
let coachOpen = false;
let voiceEnabled = false;
let latestCoachText = "";
let pendingCoachAnswer = null;
let recognition = null;
let listening = false;
let shownResultGameId = null;

function setActivity(text) {
  document.querySelector("#gameActivity").textContent = text;
}

function exitPreview() {
  previewing = false;
  if (gameState) position = gameState.position;
  document.querySelector("#returnToGame").hidden = true;
  document.querySelector("#boardContext").textContent = "";
  renderBoard();
}

function prepareMoveAudio() {
  if (!audioContext) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    audioContext = new AudioContext();
  }
  if (audioContext.state === "suspended") audioContext.resume();
}

function playMoveSound({ capture = false } = {}) {
  if (!audioContext) return;

  const now = audioContext.currentTime;

  // Low body: the soft wooden thump of a piece landing on the board.
  const body = audioContext.createOscillator();
  const bodyGain = audioContext.createGain();
  body.type = "triangle";
  body.frequency.setValueAtTime(capture ? 145 : 190, now);
  body.frequency.exponentialRampToValueAtTime(capture ? 72 : 95, now + 0.12);
  bodyGain.gain.setValueAtTime(0.0001, now);
  bodyGain.gain.exponentialRampToValueAtTime(capture ? 0.34 : 0.25, now + 0.006);
  bodyGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);
  body.connect(bodyGain);
  bodyGain.connect(audioContext.destination);
  body.start(now);
  body.stop(now + 0.15);

  // Short high click: the crisp edge of the piece contacting the board.
  const click = audioContext.createOscillator();
  const clickGain = audioContext.createGain();
  click.type = "square";
  click.frequency.setValueAtTime(capture ? 700 : 820, now);
  click.frequency.exponentialRampToValueAtTime(260, now + 0.035);
  clickGain.gain.setValueAtTime(0.0001, now);
  clickGain.gain.exponentialRampToValueAtTime(capture ? 0.08 : 0.055, now + 0.002);
  clickGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.045);
  click.connect(clickGain);
  clickGain.connect(audioContext.destination);
  click.start(now);
  click.stop(now + 0.05);

  if (capture) {
    // A second low hit makes captures feel heavier without needing an audio file.
    const impact = audioContext.createOscillator();
    const impactGain = audioContext.createGain();
    impact.type = "sine";
    impact.frequency.setValueAtTime(95, now + 0.025);
    impact.frequency.exponentialRampToValueAtTime(55, now + 0.14);
    impactGain.gain.setValueAtTime(0.0001, now + 0.025);
    impactGain.gain.exponentialRampToValueAtTime(0.18, now + 0.032);
    impactGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.15);
    impact.connect(impactGain);
    impactGain.connect(audioContext.destination);
    impact.start(now + 0.025);
    impact.stop(now + 0.16);
  }
}

function showScreen(screen) {
  document.querySelector("#gameResult").close();
  if (screen.id !== "gameScreen") {
    window.speechSynthesis?.cancel();
    recognition?.abort();
    closeCoach();
  }
  document.querySelectorAll(".screen").forEach((item) => item.classList.remove("active"));
  screen.classList.add("active");
  const screenLabel = document.querySelector("#screenLabel");
  if (screenLabel) screenLabel.textContent = screen === document.querySelector("#selectScreen") ? "Bir el satranç" : "Tahta başında";
}

function selectMaster(key) {
  selectedMaster = key;
  const master = key ? masters[key] : null;
  document.querySelectorAll(".master-card").forEach((card) => {
    const selected = card.dataset.master === key;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", String(selected));
  });
  const selectedName = document.querySelector("#selectedName");
  const selectedMeta = document.querySelector("#selectedMeta");
  if (selectedName) selectedName.textContent = master?.name ?? "";
  if (selectedMeta) selectedMeta.textContent = master?.level ?? "";
  document.querySelector("#startGameButton").disabled = !master;
  document.querySelector("#selectionHint").hidden = !!master;
}

document.querySelectorAll(".master-card").forEach((card) => {
  card.addEventListener("click", () => {
    selectMaster(card.dataset.master);
  });
});

document.querySelectorAll("#emojiChoices button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#emojiChoices .selected")?.classList.remove("selected");
    button.classList.add("selected");
    selectedEmoji = button.textContent;
    const headerEmoji = document.querySelector("#headerEmoji");
    if (headerEmoji) headerEmoji.textContent = selectedEmoji;
  });
});

async function prepareGame() {
  if (!selectedMaster || !masters[selectedMaster]) return;
  const button = document.querySelector("#startGameButton");
  button.disabled = true;
  button.textContent = "Tahta hazırlanıyor…";
  document.querySelector("#startError").hidden = true;
  try {
    gameState = await api.createGame({ opponentId: selectedMaster, playerColor: "white" });
    shownResultGameId = null;
    document.querySelector("#resultAccess").hidden = true;
    document.querySelector(".board-stage").classList.remove("has-result");
    position = gameState.position;
    legalSquares = new Set();
    selectedSquare = null;
    focusedSquare = "e2";
    renderBoard();
    const master = gameState.opponent;
    document.querySelector("#gameOpponentName").textContent = master.name;
    document.querySelector("#gameOpponentFace").className = `opponent-avatar ${master.face}`;
    showScreen(document.querySelector("#gameScreen"));
    updateTurnIndicator();
    finishTyping?.();
    chatThread.replaceChildren();
    lesson = null;
    lastMove = null;
    latestCoachText = "";
    pendingCoachAnswer = null;
    closeCoach();
    coachPopover.classList.add("is-empty");
    updateChances(null);
    document.querySelector("#betterQuestion").disabled = true;
    document.querySelector("#coachInput").value = "";
    exitPreview();
    document.querySelector("#showOnBoard").disabled = true;
    document.querySelector("#explainMore").disabled = true;
    setActivity("");
    showCoachAnswer(`Selam! ${master.name} ile başlayalım. Bir taş seçip hedef kareye tıkla; hamlenden sonra birlikte değerlendirelim.`);
  } catch {
    const error = document.querySelector("#startError");
    error.textContent = "Tahta açılamadı. Bağlantını kontrol edip yeniden dene.";
    error.hidden = false;
  } finally {
    button.disabled = !selectedMaster;
    button.innerHTML = 'Başla <span aria-hidden="true">→</span>';
  }
}

document.querySelector("#startGameButton").addEventListener("click", prepareGame);
document.querySelector("#changeOpponentButton").addEventListener("click", () => showScreen(document.querySelector("#selectScreen")));
document.querySelector("#homeButton").addEventListener("click", (event) => {
  event.preventDefault();
  showScreen(document.querySelector("#selectScreen"));
});


const board = document.querySelector("#board");

const pieceShapes = {
  p: `
    <circle class="piece-shell" cx="50" cy="24" r="13"/>
    <path class="piece-shell" d="M40 38h20c1 9 6 17 11 23H29c5-6 10-14 11-23Z"/>
    <path class="piece-shell" d="M27 61h46l5 9H22l5-9Z"/>
    <path class="piece-shell piece-base" d="M19 72h62l6 12H13l6-12Z"/>
    <path class="piece-highlight" d="M42 43c-1 7-4 13-8 18M27 75h42"/>
  `,
  r: `
    <path class="piece-shell" d="M22 17h13v8h9v-8h12v8h9v-8h13v24H22V17Z"/>
    <path class="piece-shell" d="M29 40h42l-5 29H34l-5-29Z"/>
    <path class="piece-shell" d="M27 67h46l6 9H21l6-9Z"/>
    <path class="piece-shell piece-base" d="M16 77h68l5 11H11l5-11Z"/>
    <path class="piece-highlight" d="M30 32h32M35 44l-3 20M28 80h45"/>
  `,
  n: `
    <path class="piece-shell" d="M27 69c1-14 8-23 17-30l-13 4-9-8 14-15 6-10 9 8c19 0 29 16 29 34v17H27Z"/>
    <path class="piece-shell" d="M26 67h48l7 10H19l7-10Z"/>
    <path class="piece-shell piece-base" d="M15 78h70l5 11H10l5-11Z"/>
    <circle class="piece-eye" cx="45" cy="27" r="2.4"/>
    <path class="piece-highlight" d="M57 27c9 10 11 22 10 34M30 81h43"/>
  `,
  b: `
    <path class="piece-shell" d="M50 14c10 7 15 14 15 23 0 8-5 13-10 17 2 6 7 10 12 15H33c5-5 10-9 12-15-6-4-10-9-10-17 0-9 5-16 15-23Z"/>
    <path class="piece-cut" d="M56 23 43 42"/>
    <path class="piece-shell" d="M29 66h42l8 11H21l8-11Z"/>
    <path class="piece-shell piece-base" d="M16 78h68l5 11H11l5-11Z"/>
    <path class="piece-highlight" d="M39 70h26M29 81h43"/>
  `,
  q: `
    <circle class="piece-shell" cx="25" cy="20" r="6"/><circle class="piece-shell" cx="50" cy="14" r="6"/><circle class="piece-shell" cx="75" cy="20" r="6"/>
    <path class="piece-shell" d="m25 25 10 29 15-32 15 32 10-29-4 39H29l-4-39Z"/>
    <path class="piece-shell" d="M27 61h46l7 13H20l7-13Z"/>
    <path class="piece-shell piece-base" d="M15 76h70l5 12H10l5-12Z"/>
    <path class="piece-highlight" d="M34 59h32M28 79h44"/>
  `,
  k: `
    <path class="piece-shell" d="M46 10h8v10h9v8h-9v10h-8V28h-9v-8h9V10Z"/>
    <path class="piece-shell" d="M35 38h30l7 12-12 12 10 10H30l10-10-12-12 7-12Z"/>
    <path class="piece-shell" d="M25 69h50l6 9H19l6-9Z"/>
    <path class="piece-shell piece-base" d="M14 79h72l5 11H9l5-11Z"/>
    <path class="piece-highlight" d="M37 43h20M30 81h43"/>
  `,
};

function createChessPiece(code, squareName) {
  const color = code[0] === "w" ? "white" : "black";
  const type = code[1];
  const gradientId = `piece-${color}-${squareName}`;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("piece", `${color}-piece`);
  const colors = color === "white"
    ? ["#fffef6", "#f4f1e4", "#e2ded0"]
    : ["#53554b", "#34362d", "#23251e"];
  svg.innerHTML = `
    <defs>
      <linearGradient id="${gradientId}" x1="18%" y1="5%" x2="82%" y2="95%">
        <stop offset="0" stop-color="${colors[0]}"/>
        <stop offset=".48" stop-color="${colors[1]}"/>
        <stop offset="1" stop-color="${colors[2]}"/>
      </linearGradient>
    </defs>
    <g style="--piece-fill:url(#${gradientId})">${pieceShapes[type]}</g>`;
  return svg;
}

const pieceNames = { p: "piyon", r: "kale", n: "at", b: "fil", q: "vezir", k: "şah" };

function updateTurnIndicator(override = null) {
  const finished = gameState?.status === "finished" || gameState?.isGameOver;
  const turn = override ?? (finished ? null : gameState?.turn === gameState?.playerColor ? "player" : "opponent");
  document.querySelector("#playerIdentity").classList.toggle("is-turn", turn === "player");
  document.querySelector("#opponentIdentity").classList.toggle("is-turn", turn === "opponent");
  document.querySelector("#turnAnnouncement").textContent = finished ? "Oyun bitti." : turn === "player" ? "Sıra sende." : "Sıra rakibinde.";
}

function renderBoard() {
  const keepFocus = board.contains(document.activeElement);
  board.replaceChildren();
  const ranks = boardFlipped ? [1,2,3,4,5,6,7,8] : [8,7,6,5,4,3,2,1];
  const visibleFiles = boardFlipped ? [...files].reverse() : files;
  ranks.forEach((rank, rankIndex) => {
    const row = document.createElement("div");
    row.className = "board-row";
    row.setAttribute("role", "row");
    visibleFiles.forEach((file, fileIndex) => {
      const name = `${file}${rank}`;
      const square = document.createElement("div");
      square.className = `square ${(files.indexOf(file) + rank) % 2 === 1 ? "light" : "dark"}`;
      square.setAttribute("role", "gridcell");
      const piece = position[name];
      const pieceLabel = piece ? `${piece[0] === "w" ? "beyaz" : "siyah"} ${pieceNames[piece[1]]}` : "boş kare";
      square.setAttribute("aria-label", `${name}, ${pieceLabel}${legalSquares.has(name) ? ", geçerli hedef" : ""}`);
      square.setAttribute("aria-selected", String(selectedSquare === name));
      square.dataset.square = name;
      square.tabIndex = name === focusedSquare ? 0 : -1;
      square.addEventListener("focus", () => {
        const previous = board.querySelector(`[data-square="${focusedSquare}"]`);
        if (previous && previous !== square) previous.tabIndex = -1;
        focusedSquare = name;
        square.tabIndex = 0;
      });
      if (!previewing && lastMove && [lastMove.from, lastMove.to].includes(name)) square.classList.add("last-move");
      if (selectedSquare === name) square.classList.add("selected");
      if (previewing && lesson && [lesson.move.from, lesson.move.to].includes(name)) square.classList.add("suggestion");
      square.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          focusedSquare = name;
          handleSquareClick(name);
          return;
        }
        const positionOnScreen = getScreenSquarePosition(name);
        const offsets = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
        let nextX = positionOnScreen.x;
        let nextY = positionOnScreen.y;
        if (offsets[event.key]) {
          nextX += offsets[event.key][0];
          nextY += offsets[event.key][1];
        } else if (event.key === "Home") nextX = 0;
        else if (event.key === "End") nextX = 7;
        else return;
        event.preventDefault();
        if (nextX < 0 || nextX > 7 || nextY < 0 || nextY > 7) return;
        const nextName = `${visibleFiles[nextX]}${ranks[nextY]}`;
        const nextSquare = board.querySelector(`[data-square="${nextName}"]`);
        square.tabIndex = -1;
        nextSquare.tabIndex = 0;
        focusedSquare = nextName;
        nextSquare.focus();
      });
      if (legalSquares.has(name)) square.classList.add("legal");
      if (piece) {
        const pieceElement = createChessPiece(piece, name);
        const animationMove = moveAnimations.find((move) => move.to === name);
        if (animationMove) {
          const source = getScreenSquarePosition(animationMove.from);
          const target = getScreenSquarePosition(animationMove.to);
          pieceElement.classList.add("piece-moving");
          pieceElement.style.setProperty("--move-x", `${(source.x - target.x) * 100}%`);
          pieceElement.style.setProperty("--move-y", `${(source.y - target.y) * 100}%`);
        }
        square.appendChild(pieceElement);
      }
      if (fileIndex === 0 || rankIndex === 7) {
        const coordinate = document.createElement("span");
        coordinate.className = "coordinate";
        coordinate.textContent = fileIndex === 0 ? rank : file;
        square.appendChild(coordinate);
      }
      square.addEventListener("click", () => {
        focusedSquare = name;
        square.focus();
        handleSquareClick(name);
      });
      row.appendChild(square);
    });
    board.appendChild(row);
  });
  if (keepFocus) board.querySelector(`[data-square="${focusedSquare}"]`)?.focus();
}

function getScreenSquarePosition(squareName) {
  const fileIndex = files.indexOf(squareName[0]);
  const rank = Number(squareName[1]);
  return {
    x: boardFlipped ? 7 - fileIndex : fileIndex,
    y: boardFlipped ? rank - 1 : 8 - rank,
  };
}

async function handleSquareClick(name) {
  if (!gameState || gameState.status === "finished" || busy || previewing) return;

  prepareMoveAudio();

  const playerCode = gameState.playerColor === "white" ? "w" : "b";
  if (name === selectedSquare) {
    selectedSquare = null;
    legalSquares.clear();
    renderBoard();
    return;
  }

  if (!selectedSquare) {
    const piece = position[name];
    if (!piece || piece[0] !== playerCode) return;
    selectedSquare = name;
    legalSquares = new Set(gameState.legalMoves.filter((move) => move.from === name).map((move) => move.to));
    renderBoard();
    return;
  }

  // Another own piece becomes the new selection instead of an invalid target.
  const piece = position[name];
  if (piece?.[0] === playerCode) {
    selectedSquare = name;
    legalSquares = new Set(gameState.legalMoves.filter((move) => move.from === name).map((move) => move.to));
    renderBoard();
    return;
  }

  if (!legalSquares.has(name)) return;
  // Play inside the user's click handler so browser autoplay policies allow it.
  prepareMoveAudio();
  playMoveSound();
  await analyzeSquare(selectedSquare, name);
}

async function analyzeSquare(from, to) {
  if (!gameState || busy) return;
  busy = true;
  const gameId = gameState.gameId;
  const beforePosition = { ...position };
  lesson = null;
  document.querySelector("#showOnBoard").disabled = true;
  document.querySelector("#betterQuestion").disabled = true;
  document.querySelector("#explainMore").disabled = true;
  setActivity("Rakibin düşünüyor…");
  updateTurnIndicator("opponent");
  try {
  const requestId = ++latestAnalysisRequest;
  const promotion = gameState.legalMoves.find(move => move.from === from && move.to === to && move.promotion === "q")?.promotion;
  const response = await api.analyzeMove({ gameId, from, to, promotion });
  if (requestId !== latestAnalysisRequest || response.gameId !== gameState.gameId) return;
  gameState = response.gameState;
  position = gameState.position;
  updateTurnIndicator();
  selectedSquare = null;
  legalSquares = new Set();
  if (response.playedMove.captured) playMoveSound({ capture: true });
  moveAnimations = [response.playedMove, response.engineMove].filter(Boolean);
  renderBoard();
  window.setTimeout(() => {
    moveAnimations = [];
  }, 360);
  lastMove = response.engineMove ?? response.playedMove;
  lesson = response.analysis.bestMove?.from ? {
    position: beforePosition,
    move: response.analysis.bestMove,
    description: response.coach.betterMove,
  } : null;
  document.querySelector("#showOnBoard").disabled = !lesson;
  document.querySelector("#explainMore").disabled = false;
  renderBoard();
  document.querySelector("#betterQuestion").disabled = false;
  updateChances(response.analysis.whitePercent, gameState);
  showCoachAnswer(response.coach.text, describeScore(response.analysis.score));
  setActivity(gameState.isGameOver ? "" : gameState.isCheck ? "Şah!" : "");
  showGameResult();
  } catch {
    setActivity("Hamle tamamlanamadı. Oyun durumu kontrol ediliyor…");
    try {
      const current = await api.getGame(gameId);
      if (gameState?.gameId === gameId) {
        gameState = current;
        position = current.position;
        updateTurnIndicator();
        selectedSquare = null;
        legalSquares.clear();
        renderBoard();
        setActivity(current.status === "finished" ? "" : current.turn === current.playerColor ? "Tekrar deneyebilirsin." : "Rakip yanıtı tamamlanamadı. Yeni oyun başlatabilirsin.");
        showGameResult();
      }
    } catch { setActivity("Bağlantı kurulamadı. Yeniden denemeden önce sayfayı yenile."); }
  } finally {
    busy = false;
    document.querySelector("#showOnBoard").disabled = !lesson;
  }
}

function describeScore(score) {
  if (!score || score === "—") return "";
  if (score.includes("M")) return score.startsWith("-") ? "Siyahın lehine mat dizisi." : "Beyazın lehine mat dizisi.";
  const value = Number(score);
  if (!Number.isFinite(value)) return "";
  if (Math.abs(value) < .3) return "Hamlenin ardından konum dengeli.";
  return `Hamlenin ardından ${value > 0 ? "beyaz" : "siyah"} ${Math.abs(value) < 1 ? "hafif" : "belirgin"} üstün.`;
}

function showGameResult() {
  if (!gameState || !(gameState.status === "finished" || gameState.isGameOver) || shownResultGameId === gameState.gameId) return;
  updateTurnIndicator();
  // In checkmate the side whose turn it is has lost, including a black player.
  const won = gameState.isCheckmate && gameState.turn !== gameState.playerColor;
  const title = gameState.isCheckmate ? (won ? "Kazandın!" : "Kaybettin") : "Berabere";
  const opponent = gameState.opponent.name;
  const description = gameState.isCheckmate
    ? won ? "Başka bir rakiple oynamaya ne dersin?" : `${opponent} kazandı. Bir dahaki sefere.`
    : "Oyun berabere tamamlandı. Bir el daha oynayalım mı?";
  document.querySelector("#resultTitle").textContent = title;
  document.querySelector("#resultDescription").textContent = description;
  const winnerFace = document.querySelector("#resultAvatar");
  const faceByOpponent = { capablanca: "piece-jose-v1.png", judit: "piece-judit-v1.png", magnus: "piece-magnus-v1.png" };
  winnerFace.hidden = !gameState.isCheckmate;
  document.querySelector("#resultDrawMark").hidden = !!gameState.isCheckmate;
  if (gameState.isCheckmate) winnerFace.src = `images/${won ? "piece-player-v1.png" : faceByOpponent[gameState.opponent.id]}`;
  winnerFace.alt = gameState.isCheckmate ? `${won ? "Sen" : opponent} kazandı` : "";
  document.querySelector("#resultEyebrow").textContent = gameState.isCheckmate ? `${won ? "SEN" : opponent.toLocaleUpperCase("tr-TR")} KAZANDI` : "OYUN SONUCU";
  document.querySelector("#playAgain").hidden = won;
  document.querySelector("#chooseOpponent").hidden = !won;
  document.querySelector("#reviewResult").hidden = won;
  const dialog = document.querySelector("#gameResult");
  dialog.dataset.outcome = gameState.isCheckmate ? (won ? "win" : "loss") : "draw";
  shownResultGameId = gameState.gameId;
  document.querySelector("#resultAccess").hidden = false;
  document.querySelector(".board-stage").classList.add("has-result");
  finishTyping?.();
  window.speechSynthesis?.cancel();
  recognition?.abort();
  // A game can finish while its request is in flight and the user is on the home screen.
  if (document.querySelector("#gameScreen").classList.contains("active")) dialog.showModal();
}

const resultDialog = document.querySelector("#gameResult");
function dismissResult() {
  resultDialog.close();
  document.querySelector("#reopenResult").focus();
}
document.querySelector("#closeResult").addEventListener("click", dismissResult);
document.querySelector("#reviewResult").addEventListener("click", dismissResult);
document.querySelector("#chooseOpponent").addEventListener("click", () => {
  selectMaster(null);
  showScreen(document.querySelector("#selectScreen"));
  document.querySelector(".master-card")?.focus();
});
document.querySelector("#reopenResult").addEventListener("click", () => resultDialog.showModal());
document.querySelector("#newGameFromBoard").addEventListener("click", () => {
  selectMaster(null);
  showScreen(document.querySelector("#selectScreen"));
  document.querySelector(".master-card")?.focus();
});
document.querySelector("#playAgain").addEventListener("click", () => {
  resultDialog.close();
  prepareGame();
});

document.querySelector("#flipButton").addEventListener("click", () => { boardFlipped = !boardFlipped; renderBoard(); });
document.querySelector("#showOnBoard").addEventListener("click", () => {
  if (!lesson || busy) return;
  previewing = true;
  selectedSquare = null;
  legalSquares.clear();
  moveAnimations = [];
  position = lesson.position;
  document.querySelector("#returnToGame").hidden = false;
  document.querySelector("#boardContext").textContent = `${lesson.focus === "current-position" ? "Mevcut konum" : "Hamle öncesi"} · ${lesson.description || "Alternatif hamle tahtada gösteriliyor"}`;
  renderBoard();
});
document.querySelector("#returnToGame").addEventListener("click", exitPreview);

const coachPopover = document.querySelector("#coachPopover");
const chatThread = document.querySelector("#chatThread");

function openCoach() {
  coachOpen = true;
  coachPopover.hidden = false;
  coachPopover.classList.add("open");
  document.querySelector("#coachLauncher").hidden = true;
  document.querySelector("#coachLauncher").setAttribute("aria-expanded", "true");
  if (pendingCoachAnswer) {
    const answer = pendingCoachAnswer;
    pendingCoachAnswer = null;
    showCoachAnswer(...answer);
  }
}

function closeCoach() {
  coachOpen = false;
  finishTyping?.();
  window.speechSynthesis?.cancel();
  recognition?.abort();
  coachPopover.hidden = true;
  coachPopover.classList.remove("open");
  document.querySelector("#coachLauncher").hidden = false;
  document.querySelector("#coachLauncher").setAttribute("aria-expanded", "false");
}

document.querySelector("#closeCoach")?.addEventListener("click", closeCoach);
document.querySelector("#coachLauncher").addEventListener("click", openCoach);
document.querySelector("#jumpToLens").addEventListener("click", () => {
  openCoach();
  coachPopover.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  document.querySelector("#coachInput").focus({ preventScroll: true });
});

function addUserMessage(text) {
  const message = document.createElement("div");
  message.className = "user-message";
  message.textContent = text;
  chatThread.appendChild(message);
}

function showCoachAnswer(text, evaluation = "") {
  if (gameState?.lastMoveId) coachPopover.classList.remove("is-empty");
  latestCoachText = [text, evaluation].filter(Boolean).join(" ");
  if (!coachOpen) {
    pendingCoachAnswer = [text, evaluation];
    document.querySelector(".launcher-note").textContent = "Yorumuma göz at";
    return;
  }
  speakCoach(latestCoachText);
  finishTyping?.();
  clearTimeout(typingTimer);
  const bubble = document.createElement("div");
  bubble.className = "coach-message";
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = "Lens";
  const paragraph = document.createElement("p");
  bubble.append(label, paragraph);
  if (evaluation) {
    const note = document.createElement("div");
    note.className = "evaluation-note";
    note.textContent = evaluation;
    bubble.append(note);
  }
  chatThread.append(bubble);
  const skip = document.createElement("button");
  skip.type = "button";
  skip.className = "finish-typing";
  skip.textContent = "Tamamını göster";
  const complete = () => {
    clearTimeout(typingTimer);
    paragraph.textContent = text;
    label.textContent = "Lens";
    bubble.removeAttribute("aria-busy");
    skip.remove();
    finishTyping = null;
  };
  finishTyping = complete;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    complete();
  } else {
    bubble.setAttribute("aria-busy", "true");
    label.textContent = "Lens yazıyor…";
    bubble.append(skip);
    skip.addEventListener("click", complete);
    let index = 0;
    const type = () => {
      index += 4;
      paragraph.textContent = text.slice(0, index);
      chatThread.scrollTop = chatThread.scrollHeight;
      if (index < text.length) typingTimer = setTimeout(type, 18);
      else complete();
    };
    type();
  }
  chatThread.scrollTop = chatThread.scrollHeight;
}

async function askCoach(question) {
  if (!gameState || coachingBusy || busy) return;
  const gameId = gameState.gameId;
  const moveId = gameState.lastMoveId;
  coachingBusy = true;
  window.speechSynthesis?.cancel();
  addUserMessage(question);
  const send = document.querySelector("#sendCoachPrompt");
  send.disabled = true;
  document.querySelector("#explainMore").disabled = true;
  setActivity("Lens yanıt hazırlıyor…");
  try {
    const response = await api.askCoach({ gameId, question, moveId });
    if (gameState?.gameId !== gameId || gameState.lastMoveId !== moveId) return;
    if (response.recommendation?.move) {
      lesson = {
        position: response.recommendation.position,
        move: response.recommendation.move,
        description: response.recommendation.description,
        focus: response.focus,
      };
      document.querySelector("#showOnBoard").disabled = false;
    }
    showCoachAnswer(response.text);
    setActivity("");
  } catch {
    if (gameState?.gameId === gameId) {
      showCoachAnswer("Şu an yanıt alamadım. Sorunu tekrar gönderebilirsin.");
      setActivity("");
    }
  } finally {
    coachingBusy = false;
    send.disabled = false;
    document.querySelector("#explainMore").disabled = !lesson;
  }
}

document.querySelector("#explainMore").addEventListener("click", () => askCoach("Önerdiğin hamle neden daha iyi?"));
document.querySelector("#betterQuestion").addEventListener("click", () => askCoach("Daha iyi hangi hamle vardı?"));
document.querySelector("#coachForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#coachInput");
  const question = input.value.trim();
  if (!question || !gameState || busy || coachingBusy) return;
  recognition?.abort();
  input.value = "";
  await askCoach(question);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && previewing) exitPreview();
  else if (event.key === "Escape" && coachOpen) {
    closeCoach();
    document.querySelector("#coachLauncher").focus();
  }
});

function updateChances(percent, state = null) {
  const valid = typeof percent === "number" && Number.isFinite(percent);
  document.querySelector(".winning-chances").hidden = !valid;
  let white = valid ? Math.max(0, Math.min(100, Math.round(percent))) : null;
  if (state?.isCheckmate) white = state.turn === "white" ? 0 : 100;
  if (state?.isDraw) white = 50;
  document.querySelector("#whiteChance").textContent = white === null ? "—" : `%${white}`;
  document.querySelector("#blackChance").textContent = white === null ? "—" : `%${100 - white}`;
  document.querySelector("#whiteChanceBar").style.width = `${white ?? 50}%`;
  document.querySelector("#chanceCaption").textContent = state?.isDraw ? "Oyun berabere" : state?.isCheckmate ? "Oyun sonucu" : valid ? "Hamlen sonrası · yaklaşık" : "İlk hamleyi bekliyoruz";
  document.querySelector("#chanceTrack").setAttribute("aria-label", white === null ? "Henüz değerlendirme yok" : `Yaklaşık konum dengesi: beyaz yüzde ${white}, siyah yüzde ${100-white}. Kazanma olasılığı değildir.`);
  document.querySelector("#chanceTrack").title = "Motor değerlendirmesinden türetilen yaklaşık üstünlük payı; beraberlik olasılığını içeren bir kazanma olasılığı değildir.";
}

function speakCoach(text) {
  if (!voiceEnabled || !coachOpen || !text || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "tr-TR";
  const voice = window.speechSynthesis.getVoices().find(item => item.lang.startsWith("tr"));
  if (voice) utterance.voice = voice;
  utterance.rate = .95;
  utterance.onerror = event => {
    if (!["canceled", "interrupted"].includes(event.error)) document.querySelector("#voiceStatus").textContent = "Sesli okuma başlatılamadı. Cihazının ses ayarlarını kontrol et.";
  };
  window.speechSynthesis.speak(utterance);
}

const voiceToggle = document.querySelector("#toggleVoice");
voiceToggle.disabled = !("speechSynthesis" in window);
if (voiceToggle.disabled) voiceToggle.title = "Bu tarayıcı sesli okumayı desteklemiyor.";
voiceToggle.addEventListener("click", () => {
  voiceEnabled = !voiceEnabled;
  voiceToggle.setAttribute("aria-pressed", String(voiceEnabled));
  voiceToggle.setAttribute("aria-label", voiceEnabled ? "Lens’in sesini kapat" : "Lens’in sesini aç");
  voiceToggle.title = voiceEnabled ? "Sesi kapat" : "Sesli oku";
  if (voiceEnabled) speakCoach(latestCoachText);
  else window.speechSynthesis?.cancel();
});

// Speech is transcribed into an editable draft; sending remains an explicit action.
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recordButton = document.querySelector("#recordVoice");
const voiceStatus = document.querySelector("#voiceStatus");
if (!SpeechRecognition) {
  recordButton.disabled = true;
  recordButton.title = "Bu tarayıcı sesle yazmayı desteklemiyor.";
  voiceStatus.textContent = "Sesle yazma bu tarayıcıda desteklenmiyor.";
}
recordButton.addEventListener("click", () => {
  if (listening) { recognition?.stop(); return; }
  window.speechSynthesis?.cancel();
  const session = new SpeechRecognition();
  recognition = session;
  const input = document.querySelector("#coachInput");
  const draft = input.value.trim();
  const gameId = gameState?.gameId;
  session.lang = "tr-TR";
  session.interimResults = true;
  session.continuous = false;
  listening = true;
  recordButton.setAttribute("aria-pressed", "true");
  recordButton.setAttribute("aria-label", "Dinlemeyi bitir");
  voiceStatus.textContent = "Dinliyorum… Bitince metni kontrol edip gönderebilirsin.";
  session.onresult = event => {
    if (recognition !== session || gameState?.gameId !== gameId || !coachOpen) return;
    const transcript = Array.from(event.results).map(result => result[0].transcript).join(" ");
    input.value = [draft, transcript].filter(Boolean).join(" ").slice(0, 400);
  };
  session.onerror = event => {
    voiceStatus.textContent = event.error === "not-allowed" ? "Mikrofon izni verilmedi. Tarayıcı ayarlarından izin verebilirsin." : event.error === "no-speech" ? "Ses duyamadım. Yeniden deneyebilirsin." : event.error === "aborted" ? "" : "Sesle yazma kullanılamıyor. Mesajını yazarak gönderebilirsin.";
  };
  session.onend = () => {
    if (recognition !== session) return;
    listening = false;
    recognition = null;
    recordButton.setAttribute("aria-pressed", "false");
    recordButton.setAttribute("aria-label", "Sesle mesaj yaz");
    if (voiceStatus.textContent.startsWith("Dinliyorum")) voiceStatus.textContent = "Mesajını kontrol edip gönderebilirsin.";
  };
  try { session.start(); } catch {
    session.onend();
    voiceStatus.textContent = "Mikrofon başlatılamadı. Yeniden deneyebilirsin.";
  }
});
window.addEventListener("pagehide", () => { recognition?.abort(); window.speechSynthesis?.cancel(); });
renderBoard();
selectMaster(null);
