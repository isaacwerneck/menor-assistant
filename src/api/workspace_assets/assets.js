"use strict";
// Painel exclusivamente consultivo: nenhuma POST, aprovação ou recuperação de tarefas.
const targets = {
  goals: document.getElementById("goals"),
  missions: document.getElementById("missions"),
  status: document.getElementById("status"),
  refresh: document.getElementById("refresh"),
  filter: document.getElementById("mission-filter"),
};
let latestMissions = [];

function node(tag, className, content) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (content !== undefined) el.textContent = String(content).slice(0, 650);
  return el;
}

function empty(target, message, error = false) {
  target.replaceChildren(node("p", error ? "empty error" : "empty", message));
}

async function readJson(path) {
  const response = await fetch(path, {credentials: "same-origin", cache: "no-store", redirect: "error"});
  if (!response.ok) {
    if (response.status === 401) throw new Error("Sessão expirada. Entre pelo chat para consultar seus objetivos.");
    throw new Error("A API não conseguiu retornar o estado solicitado (HTTP " + response.status + ").");
  }
  const data = await response.json();
  if (!data || typeof data !== "object") throw new Error("Formato de dados inválido.");
  return data;
}

function currentConversations() {
  let items;
  try { items = JSON.parse(localStorage.getItem("menor_convs") || "[]"); }
  catch (error) { throw new Error("Não foi possível ler as conversas deste navegador."); }
  if (!Array.isArray(items)) throw new Error("Histórico de conversas com formato inválido.");
  const valid = items.filter(x => x && typeof x.id === "string" &&
    /^[a-zA-Z0-9_-]{8,80}$/.test(x.id) && typeof x.title === "string");
  return valid.slice(0, 8);
}

function showSteps(card, list) {
  if (!Array.isArray(list) || list.length === 0) return;
  const ul = node("ul", "steps");
  for (const item of list.slice(0, 10)) {
    const summary = typeof item === "string" ? item :
      item && typeof item === "object" ? item.title || item.description || item.step : null;
    if (typeof summary === "string" && summary.trim()) ul.append(node("li", "", summary));
  }
  if (ul.childNodes.length) card.append(ul);
}

function renderGoal(conversation, state, paused = null) {
  const source = paused || (state.phase === "approval" && state.return_goal) ||
    state.pending_goal || state;
  const goal = source && typeof source.goal === "string" ? source.goal : null;
  const card = node("article", "record");
  card.append(node("h3", "", goal || conversation.title || "Conversa sem título"));
  const phase = paused ? "paused" :
    typeof state.phase === "string" ? state.phase : "desconhecido";
  card.append(node("span", "state", "Fase registrada: " + phase));
  card.append(node("p", "record-meta", "Conversa: " + conversation.title));
  showSteps(card, source && source.steps);
  return card;
}

async function loadGoals() {
  targets.goals.replaceChildren();
  const conversations = currentConversations();
  if (!conversations.length) {
    empty(targets.goals, "Nenhuma conversa encontrada neste navegador.");
    return;
  }
  let shown = 0;
  let failures = 0;
  for (const conv of conversations) {
    try {
      const state = await readJson("/agent/runs/" + encodeURIComponent(conv.id));
      if (state.phase && state.phase !== "idle") {
        targets.goals.append(renderGoal(conv, state));
        shown += 1;
      }
      // Metas pausadas continuam relevantes mesmo quando a sessão está ociosa.
      for (const paused of (Array.isArray(state.paused_goals) ? state.paused_goals : []).slice(0, 6)) {
        if (paused && typeof paused.goal === "string" && paused.goal.trim()) {
          targets.goals.append(renderGoal(conv, state, paused));
          shown += 1;
        }
      }
    } catch (error) { failures += 1; }
  }
  if (!shown && !failures) empty(targets.goals,
    "Nenhum objetivo com estado registrado nas últimas conversas. Os dados não são estimados.");
  if (failures) targets.goals.append(node("p", "empty error",
    "Não foi possível consultar " + failures + " conversa(s). Nenhum estado foi presumido."));
}

const active = new Set(["gathering", "awaiting_approval", "queued", "installing", "needs_test", "blocked"]);
const closed = new Set(["ready", "failed", "cancelled"]);

function renderMission(mission) {
  const card = node("article", "record");
  card.append(node("h3", "", typeof mission.goal === "string" ? mission.goal : "Missão sem objetivo"));
  card.append(node("span", "state", "Estado: " + (mission.status || "desconhecido")));
  if (typeof mission.capability === "string") {
    card.append(node("p", "record-meta", "Capacidade: " + mission.capability));
  }
  if (typeof mission.updated_at === "string") {
    card.append(node("p", "record-meta", "Atualizado: " + mission.updated_at));
  }
  showSteps(card, mission.plan && mission.plan.steps);
  return card;
}

function drawMissions() {
  targets.missions.replaceChildren();
  const filter = targets.filter.value;
  const items = latestMissions.filter(m => filter === "all" ||
    (filter === "active" ? active.has(m.status) : closed.has(m.status)));
  if (!items.length) {
    empty(targets.missions, "Nenhuma missão encontrada para este filtro.");
    return;
  }
  for (const mission of items) targets.missions.append(renderMission(mission));
}

async function loadMissions() {
  // Dados de consulta anterior não sobrevivem a erro na atualização.
  latestMissions = [];
  const data = await readJson("/agent/missions");
  if (!Array.isArray(data.items)) throw new Error("Lista de missões inválida.");
  latestMissions = data.items.filter(x => x && typeof x === "object").slice(0, 20);
  drawMissions();
}

async function refresh() {
  targets.refresh.disabled = true;
  targets.status.textContent = "Consultando estados registrados…";
  try {
    const outcomes = await Promise.allSettled([loadGoals(), loadMissions()]);
    const errors = outcomes.filter(x => x.status === "rejected").map(x => x.reason.message);
    if (outcomes[0].status === "rejected") empty(targets.goals, errors[0], true);
    if (outcomes[1].status === "rejected") empty(targets.missions,
      outcomes[1].reason.message, true);
    targets.status.textContent = errors.length ?
      "Consulta parcial: " + errors.join(" ") : "Dados consultados. Nenhuma ação foi executada.";
  } finally { targets.refresh.disabled = false; }
}

targets.refresh.addEventListener("click", refresh);
targets.filter.addEventListener("change", drawMissions);
refresh();
