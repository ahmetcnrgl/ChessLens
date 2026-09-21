const api = window.chessLensApi;
const masters = api.opponents;
let position = api.initialPosition;
const files = ["a", "b", "c", "d", "e", "f", "g", "h"];
let legalSquares = new Set(api.legalSquares);
let selectedMaster = "judit";
let selectedEmoji = "🧠";
let boardFlipped = false;
let typingTimer;
let gameState = null;
let latestAnalysisRequest = 0;

function showScreen(screen) {
  document.querySelectorAll(".screen").forEach((item) => item.classList.remove("active"));
  screen.classList.add("active");
  const screenLabel = document.querySelector("#screenLabel");
  if (screenLabel) screenLabel.textContent = screen === document.querySelector("#selectScreen") ? "Bir el satranç" : "Tahta başında";
}

function selectMaster(key) {
  selectedMaster = key;
  const master = masters[key];
  document.querySelectorAll(".master-card").forEach((card) => {
    const selected = card.dataset.master === key;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", String(selected));
  });
  const selectedName = document.querySelector("#selectedName");
  const selectedMeta = document.querySelector("#selectedMeta");
  if (selectedName) selectedName.textContent = master.name;
  if (selectedMeta) selectedMeta.textContent = master.level;
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
  const button = document.querySelector("#startGameButton");
  button.disabled = true;
  try {
    gameState = await api.createGame({ opponentId: selectedMaster, playerColor: "white" });
    position = gameState.position;
    legalSquares = new Set(gameState.legalSquares);
    renderBoard();
    const master = gameState.opponent;
    document.querySelector("#gameOpponentName").textContent = master.name;
    document.querySelector("#sidebarOpponentName").textContent = master.name;
    document.querySelector("#gameOpponentFace").className = `opponent-avatar ${master.face}`;
    showScreen(document.querySelector("#gameScreen"));
    showCoachAnswer(`Selam! Ben Lens. ${master.name} ile bu konumda önce sakin kalıp merkezdeki fikrini bulalım.`, "12. d4");
  } finally {
    button.disabled = false;
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
  svg.setAttribute("aria-label", `${color} ${type}`);
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

function renderBoard() {
  board.innerHTML = "";
  const ranks = boardFlipped ? [1,2,3,4,5,6,7,8] : [8,7,6,5,4,3,2,1];
  const visibleFiles = boardFlipped ? [...files].reverse() : files;
  ranks.forEach((rank, rankIndex) => {
    visibleFiles.forEach((file, fileIndex) => {
      const name = `${file}${rank}`;
      const square = document.createElement("div");
      square.className = `square ${(files.indexOf(file) + rank) % 2 === 1 ? "light" : "dark"}`;
      square.setAttribute("role", "gridcell");
      square.setAttribute("aria-label", name);
      if (name === "d6" || name === "e5") square.classList.add("last-move");
      if (legalSquares.has(name)) square.classList.add("legal");
      const piece = position[name];
      if (piece) {
        square.appendChild(createChessPiece(piece, name));
      }
      if (fileIndex === 0 || rankIndex === 7) {
        const coordinate = document.createElement("span");
        coordinate.className = "coordinate";
        coordinate.textContent = fileIndex === 0 ? rank : file;
        square.appendChild(coordinate);
      }
      square.addEventListener("click", () => analyzeSquare(name));
      board.appendChild(square);
    });
  });
}

async function analyzeSquare(name) {
  if (!legalSquares.has(name) || !gameState) return;
  const requestId = ++latestAnalysisRequest;
  const response = await api.analyzeMove({ gameId: gameState.gameId, from: "e2", to: name });
  if (requestId !== latestAnalysisRequest || response.gameId !== gameState.gameId) return;
  updateAdvantage(response.analysis.whitePercent, response.analysis.score);
  openCoach();
  showCoachAnswer(response.coach.text, response.coach.betterMove);
}

function updateAdvantage(percent, score) {
  document.querySelector("#advantageText").textContent = `%${percent}`;
  document.querySelector("#advantageFill").style.width = `${percent}%`;
  document.querySelector("#advantageScore").textContent = score;
  document.querySelector("#positionSummary").textContent = percent > 60 ? "Beyazın planı biraz daha rahat." : "Konum dengeli; küçük bir rahatlık var.";
}

document.querySelector("#flipButton").addEventListener("click", () => { boardFlipped = !boardFlipped; renderBoard(); });
document.querySelector("#undoButton").addEventListener("click", () => {
  openCoach();
  showCoachAnswer("Hamleyi geri aldık. Şimdi önce rakibin tehdidini, sonra merkezdeki aday hamlelerini sırayla karşılaştır.", "12. d4");
});

const coachPopover = document.querySelector("#coachPopover");
const chatThread = document.querySelector("#chatThread");

function openCoach() {
  coachPopover.hidden = false;
  coachPopover.classList.add("open");
}

function closeCoach() {
  coachPopover.classList.remove("open");
}

document.querySelector("#closeCoach")?.addEventListener("click", closeCoach);

function addUserMessage(text) {
  const message = document.createElement("div");
  message.className = "user-message";
  message.textContent = text;
  chatThread.appendChild(message);
}

function showCoachAnswer(text, move = "12. d4") {
  clearTimeout(typingTimer);
  chatThread.querySelectorAll(".typing-dots").forEach((item) => item.remove());
  const typing = document.createElement("div");
  typing.className = "typing-dots";
  typing.innerHTML = "<i></i><i></i><i></i>";
  chatThread.appendChild(typing);

  typingTimer = setTimeout(() => {
    typing.remove();
    const bubble = document.createElement("div");
    bubble.className = "coach-message";
    bubble.innerHTML = `<span class="message-label">Yazıyor…</span><p></p><div class="better-move"><span>Bir de bunu düşün</span><b>${move}</b><small>Merkezde yer kazan.</small></div>`;
    chatThread.appendChild(bubble);
    const paragraph = bubble.querySelector("p");
    let index = 0;
    const typeCharacter = () => {
      paragraph.textContent = text.slice(0, ++index);
      chatThread.scrollTop = chatThread.scrollHeight;
      if (index < text.length) typingTimer = setTimeout(typeCharacter, 12);
      else bubble.querySelector(".message-label").textContent = "Lens";
    };
    typeCharacter();
  }, 420);
}

document.querySelectorAll(".quick-prompts button").forEach((button) => {
  button.addEventListener("click", async () => {
    const question = button.dataset.question;
    addUserMessage(question);
    const response = await api.askCoach({ gameId: gameState?.gameId ?? "local-preview", question });
    showCoachAnswer(response.text, response.betterMove);
  });
});
document.querySelector("#coachForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#coachInput");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  addUserMessage(question);
  const response = await api.askCoach({ gameId: gameState?.gameId ?? "local-preview", question });
  showCoachAnswer(response.text, response.betterMove);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeCoach();
  }
});

renderBoard();
selectMaster("judit");
