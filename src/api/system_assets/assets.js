"use strict";
// Consultas GET no mesmo servidor; nenhum resultado define permissão de execução.
const ids = ["api-state", "api-details", "ollama-state", "ollama-explain", "models",
  "images", "skills", "tools", "diagnostics", "updated", "refresh"];
const ui = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
const sourcePaths = ["/health", "/models", "/images/status", "/agent/skills", "/tools",
  "/ops/diagnostics"];

function el(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = String(value).slice(0, 500);
  return item;
}
function clear(target, description, isError = false) {
  target.replaceChildren(el("p", "empty" + (isError ? " problem" : ""), description));
}
function addDetail(target, key, value) {
  target.append(el("dt", "", key), el("dd", "", value));
}
function card(title, status, lines = []) {
  const item = el("article", "record");
  item.append(el("h3", "", title), el("span", "state", status));
  for (const line of lines) {
    if (typeof line === "string" && line.trim()) item.append(el("p", "", line));
  }
  return item;
}
async function get(path) {
  const response = await fetch(path, {credentials: "same-origin", cache: "no-store", redirect: "error"});
  if (response.status === 401 || response.status === 403) {
    throw new Error("Acesso negado ou sessão expirada. Entre novamente pelo chat.");
  }
  if (!response.ok) throw new Error("Consulta indisponível (HTTP " + response.status + ").");
  const data = await response.json();
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("Resposta inválida da API.");
  }
  return data;
}
function renderHealth(data) {
  ui["api-details"].replaceChildren();
  const valid = data.service === "Menor API" && data.status === "online";
  ui["api-state"].textContent = valid ? "API respondeu" : "Estado não verificado";
  if (valid) {
    addDetail(ui["api-details"], "Versão informada", data.version || "Indisponível");
    addDetail(ui["api-details"], "Contrato API", data.api_contract ?? "Desconhecido");
    addDetail(ui["api-details"], "Modelo padrão", data.default_model || "Não informado");
  }
  const s = data.ollama_status;
  ui["ollama-state"].textContent = s === "online" ? "Conectado (API)" :
    s === "offline" ? "Indisponível (API)" :
      s === "degraded" ? "Degradado (API)" : "Estado não informado";
  ui["ollama-explain"].textContent = "Estado informado por /health; não é teste de inferência.";
}
function renderModels(data) {
  if (!Array.isArray(data.models)) { clear(ui.models, "Lista de modelos inválida.", true); return; }
  ui.models.replaceChildren();
  if (!data.models.length) { clear(ui.models, "Nenhum modelo informado pelo Ollama."); return; }
  for (const model of data.models.slice(0, 36)) {
    const name = typeof model.name === "string" ? model.name : "Modelo sem nome";
    const family = typeof model.details?.family === "string" ? model.details.family : "Família não informada";
    ui.models.append(card(name, "Listagem do Ollama", [family]));
  }
}
function renderImages(data) {
  ui.images.replaceChildren();
  const provider = typeof data.provider === "string" ? data.provider : "não informado";
  const state = data.configured === true ? "Configuração disponível" : "Não configurado";
  const local = data.local_model && typeof data.local_model === "object" ?
    ["Modelo local: " + (data.local_model.ready === true ? "runtime preparado" : "não confirmado")] : [];
  ui.images.append(card("Provedor: " + provider, state, [
    "Disponibilidade declarada pela API; qualidade visual não comprovada.", ...local,
  ]));
  if (data.skill && typeof data.skill === "object") {
    ui.images.append(card("Skill de imagens", data.skill.ready === true ?
      "Pronta conforme contrato" : "Não verificada", [
      typeof data.skill.status === "string" ? "Estado: " + data.skill.status : "",
    ]));
  }
}
function renderSkills(data) {
  if (!Array.isArray(data.items)) { clear(ui.skills, "Catálogo de skills inválido.", true); return; }
  ui.skills.replaceChildren();
  if (!data.items.length) { clear(ui.skills, "Nenhuma skill cadastrada."); return; }
  for (const item of data.items.slice(0, 36)) {
    const name = typeof item.name === "string" ? item.name :
      typeof item.capability === "string" ? item.capability : "Skill";
    const ready = item.ready === true ? "Pronta conforme contrato" : "Não pronta";
    ui.skills.append(card(name, ready, [
      typeof item.description === "string" ? item.description : "",
      typeof item.status === "string" ? "Estado: " + item.status : "",
    ]));
  }
}
function renderTools(data) {
  if (!Array.isArray(data.items)) { clear(ui.tools, "Catálogo de ferramentas inválido.", true); return; }
  ui.tools.replaceChildren();
  if (!data.items.length) { clear(ui.tools, "Nenhuma ferramenta cadastrada."); return; }
  for (const item of data.items.slice(0, 75)) {
    const name = typeof item.name === "string" ? item.name : "Ferramenta";
    ui.tools.append(card(name, "Registrada, não executada", [
      typeof item.description === "string" ? item.description : "",
      typeof item.risk === "string" ? "Risco: " + item.risk : "",
      item.writes === true ? "Pode modificar estado mediante autorização." : "Somente leitura, conforme catálogo.",
    ]));
  }
}
function renderDiagnostics(data) {
  if (data.contract !== "menor.ops.observability" || data.read_only !== true ||
      !data.components || typeof data.components !== "object") {
    clear(ui.diagnostics, "Contrato de diagnósticos indisponível ou incompatível.", true);
    return;
  }
  ui.diagnostics.replaceChildren();
  const names = [
    ["api", "API (loopback)"], ["ollama", "Ollama (declaração da API)"],
    ["service", "API no systemd"], ["disk", "Disco"], ["memory", "Memória"],
  ];
  for (const [key, label] of names) {
    const entry = data.components[key];
    const allowed = ["ok", "warning", "critical", "skipped", "unknown"];
    const value = entry && allowed.includes(entry.status) ? entry.status : "unknown";
    ui.diagnostics.append(card(label, "Estado: " + value, [
      "Evidência: " + (typeof entry?.evidence === "string" ? entry.evidence : "não coletada"),
      "Coletado no servidor: " + (typeof data.collected_at === "string" ?
        data.collected_at : "horário não informado"),
    ]));
  }
}

function failFor(index, error) {
  const message = error instanceof Error ? error.message : "Consulta não concluída.";
  if (index === 0) { ui["api-state"].textContent = "API não verificada";
    ui["ollama-state"].textContent = "Indisponível"; ui["api-details"].replaceChildren();
    ui["ollama-explain"].textContent = message; return; }
  const target = [null, ui.models, ui.images, ui.skills, ui.tools, ui.diagnostics][index];
  clear(target, message, true);
}
async function refresh() {
  ui.refresh.disabled = true;
  ui.updated.textContent = "Consultando fontes…";
  try {
    const responses = await Promise.allSettled(sourcePaths.map(get));
    let errors = 0;
    const renders = [renderHealth, renderModels, renderImages, renderSkills, renderTools,
      renderDiagnostics];
    responses.forEach((result, i) => {
      if (result.status === "fulfilled") renders[i](result.value);
      else { errors += 1; failFor(i, result.reason); }
    });
    const now = new Date().toLocaleString("pt-BR");
    ui.updated.textContent = "Consultado neste navegador: " + now + ". " +
      (errors ? errors + " fonte(s) indisponível(is)." : "Todas as fontes responderam.");
  } finally { ui.refresh.disabled = false; }
}
ui.refresh.addEventListener("click", refresh);
refresh();
