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
function metric(id, bar, value) {
  const valid = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
  document.getElementById(id).textContent = valid ? value.toFixed(1) + "%" : "Indisponível";
  const progress = document.getElementById(bar);
  progress.value = valid ? value : 0;
  progress.setAttribute("aria-label", valid ? value.toFixed(1) + "%" : "Métrica indisponível");
}
let livePending = false;
async function refreshLive() {
  if (livePending || (typeof document.hidden === "boolean" && document.hidden)) return;
  livePending = true;
  const summary = document.getElementById("live-updated");
  try {
    const data = await get("/workspace/system/live");
    metric("live-cpu", "cpu-bar", data.cpu_percent);
    metric("live-ram", "ram-bar", data.ram_percent);
    metric("live-gpu", "gpu-bar", data.gpu_percent);
    const ram = document.getElementById("live-ram-detail");
    ram.textContent = typeof data.ram_used_mib === "number" &&
      typeof data.ram_total_mib === "number"
      ? (data.ram_used_mib / 1024).toFixed(1) + " / " +
        (data.ram_total_mib / 1024).toFixed(1) + " GiB ocupados (exclui cache recuperável)"
      : "Memória indisponível";
    const target = document.getElementById("live-models");
    target.replaceChildren();
    if (Array.isArray(data.loaded_models) && data.loaded_models.length) {
      for (const model of data.loaded_models.slice(0, 8)) {
        if (typeof model.name !== "string") continue;
        target.append(card(model.name, "Carregado no Ollama", [
          typeof model.size_mib === "number" ? "Pesos e buffers: " +
            (model.size_mib / 1024).toFixed(1) + " GiB" : "",
          typeof model.gpu_loaded_mib === "number" ?
            "Memória reportada em GPU: " + (model.gpu_loaded_mib / 1024).toFixed(1) +
            " GiB (não é uso percentual)" : "Offload não verificado",
        ]));
      }
    } else {
      clear(target, data.ollama === "available" ? "Nenhum modelo carregado no momento." :
        "Ollama não respondeu à consulta de modelos carregados.");
    }
    summary.textContent = "Última leitura: " + new Date().toLocaleTimeString("pt-BR") +
      ". CPU inicial pode estar indisponível até a segunda amostra.";
  } catch (error) {
    summary.textContent = "Métricas indisponíveis: " +
      (error instanceof Error ? error.message : "consulta não concluída");
  } finally {
    livePending = false;
  }
}
let processPending = false;
async function refreshProcesses() {
  if (processPending || (typeof document.hidden === "boolean" && document.hidden)) return;
  processPending = true;
  const target = document.getElementById("memory-processes");
  const status = document.getElementById("processes-updated");
  try {
    const data = await get("/workspace/system/processes");
    target.replaceChildren();
    if (data.available !== true || !Array.isArray(data.items)) {
      clear(target, "Não foi possível consultar os processos do Linux.");
    } else if (!data.items.length) {
      clear(target, "Nenhum processo visível nesta leitura.");
    } else {
      for (const item of data.items.slice(0, 8)) {
        if (typeof item.name !== "string" || typeof item.rss_mib !== "number" ||
            !Number.isFinite(item.rss_mib)) continue;
        const name = item.name.slice(0, 24);
        const amount = (item.rss_mib / 1024).toFixed(2) + " GiB RSS";
        target.append(card(name, amount));
      }
    }
    status.textContent = "Leitura: " + new Date().toLocaleTimeString("pt-BR") +
      ". RSS inclui páginas compartilhadas e não equivale ao consumo exclusivo.";
  } catch (error) {
    status.textContent = "Processos indisponíveis: " +
      (error instanceof Error ? error.message : "consulta não concluída");
  } finally {
    processPending = false;
  }
}
ui.refresh.addEventListener("click", () => { refresh(); refreshLive(); refreshProcesses(); refreshCycleLive(); });
refresh();
refreshLive();
refreshProcesses();
setInterval(refreshLive, 3000);
setInterval(refreshProcesses, 15000);

// ========== MONITOR DE CICLOS COGNITIVOS AO VIVO ==========
let lastLogCount = 0;
let cyclePending = false;

const cycleElements = {
  triggerBtn: document.getElementById("cycle-trigger-btn"),
  abortBtn: document.getElementById("cycle-abort-btn"),
  clearBtn: document.getElementById("clear-cycle-logs-btn"),
  viewReportBtn: document.getElementById("view-report-btn"),
  closeReportBtn: document.getElementById("close-report-btn"),
  badge: document.getElementById("cycle-badge"),
  phaseBadge: document.getElementById("cycle-phase-badge"),
  duration: document.getElementById("cycle-duration"),
  progressBar: document.getElementById("cycle-progress-bar"),
  currentAction: document.getElementById("cycle-current-action"),
  metricLearnings: document.getElementById("metric-learnings"),
  metricAnti: document.getElementById("metric-antipatterns"),
  metricCov: document.getElementById("metric-coverage"),
  metricGaps: document.getElementById("metric-gaps-detail"),
  metricScore: document.getElementById("metric-judge-score"),
  metricGold: document.getElementById("metric-gold-detail"),
  terminal: document.getElementById("cycle-terminal"),
  autoscrollChk: document.getElementById("autoscroll-chk"),
  reportModal: document.getElementById("report-modal"),
  reportMarkdownView: document.getElementById("report-markdown-view"),
};

async function refreshCycleLive() {
  if (cyclePending || (typeof document.hidden === "boolean" && document.hidden)) return;
  cyclePending = true;
  let data = null;
  try {
    data = await get("/api/study/live");
  } catch (liveErr) {
    // Fallback defensivo para instâncias onde o serviço FastAPI ainda não foi reiniciado
    try {
      const statusData = await get("/api/study/status");
      if (statusData && typeof statusData === "object") {
        const isStudying = statusData.is_studying === true;
        data = statusData.cycle_telemetry || {
          is_running: isStudying,
          current_phase: isStudying ? 2 : 0,
          progress_percent: isStudying ? 45 : 0,
          phase_desc: isStudying ? "Ciclo autônomo ativo em segundo plano (processando no Ollama)..." : "Aguardando próximo ciclo de estudo...",
          duration_seconds: isStudying ? Math.max(0, (statusData.idle_seconds || 0) - (statusData.idle_threshold || 1800)) : 0,
          metrics: {
            learnings_count: 0,
            anti_patterns_count: 0,
            coverage_percentage: "—",
            uncovered_gaps: 0,
            judge_score: "—",
            golden_example_created: false
          },
          logs: isStudying ? [
            { timestamp: new Date().toLocaleTimeString("pt-BR"), level: "step", message: "Ciclo autônomo em execução no servidor Ubuntu (Ollama)." }
          ] : []
        };
      }
    } catch (_) {}
  }
  try {
    if (!data || typeof data !== "object") return;

    // Status Badge & Ações
    const isRunning = data.is_running === true;
    if (cycleElements.badge) {
      cycleElements.badge.className = "state cycle-badge " +
        (isRunning ? "running" : data.interrupted ? "interrupted" : (data.current_phase === 5 || data.finished_at) ? "completed" : "idle");
      cycleElements.badge.textContent = isRunning ? "Em Execução (Ciclo Ativo)" :
        data.interrupted ? "Interrompido (Preempção)" :
        (data.current_phase === 5 || data.finished_at) ? "Concluído" : "Inativo (Aguardando Ociosidade)";
    }

    if (cycleElements.triggerBtn) {
      cycleElements.triggerBtn.disabled = isRunning;
      cycleElements.triggerBtn.textContent = isRunning ? "Executando Ciclo..." : "Disparar Ciclo Agora";
    }

    if (cycleElements.abortBtn) {
      if (isRunning) {
        cycleElements.abortBtn.classList.remove("hidden");
      } else {
        cycleElements.abortBtn.classList.add("hidden");
      }
    }

    if (cycleElements.phaseBadge) {
      cycleElements.phaseBadge.textContent = "Fase " + (data.current_phase || 0) + "/5";
    }

    if (cycleElements.duration) {
      cycleElements.duration.textContent = "Duração: " + (data.duration_seconds || 0) + "s";
    }

    if (cycleElements.progressBar) {
      cycleElements.progressBar.value = data.progress_percent || 0;
    }

    if (cycleElements.currentAction) {
      cycleElements.currentAction.textContent = data.phase_desc || "Aguardando início de novo ciclo...";
    }

    // Step labels
    for (let step = 1; step <= 5; step++) {
      const lbl = document.getElementById("step-lbl-" + step);
      if (lbl) {
        lbl.className = "step-lbl" +
          (step < data.current_phase ? " done" : step === data.current_phase ? " active" : "");
      }
    }

    // Métricas
    const m = data.metrics || {};
    if (cycleElements.metricLearnings) {
      cycleElements.metricLearnings.textContent = "+" + (m.learnings_count || 0);
    }
    if (cycleElements.metricAnti) {
      cycleElements.metricAnti.textContent = String(m.anti_patterns_count || 0);
    }
    if (cycleElements.metricCov) {
      cycleElements.metricCov.textContent = (typeof m.coverage_percentage === "number") ?
        m.coverage_percentage.toFixed(1) + "%" : String(m.coverage_percentage || "—");
    }
    if (cycleElements.metricGaps) {
      cycleElements.metricGaps.textContent = (m.uncovered_gaps || 0) + " gaps mapeados";
    }
    if (cycleElements.metricScore) {
      cycleElements.metricScore.textContent = (m.judge_score !== undefined && m.judge_score !== "N/A") ?
        m.judge_score + "/10" : "—";
    }
    if (cycleElements.metricGold) {
      cycleElements.metricGold.textContent = m.golden_example_created ?
        "Exemplo de Ouro gerado" : "Rubrica crítica de 0 a 10";
    }

    // Terminal Logs
    if (cycleElements.terminal && Array.isArray(data.logs)) {
      if (data.logs.length !== lastLogCount) {
        lastLogCount = data.logs.length;
        cycleElements.terminal.replaceChildren();
        if (!data.logs.length) {
          const emptyLine = el("div", "term-line info");
          emptyLine.append(el("span", "term-time", "[00:00:00] "), "Nenhum evento registrado ainda.");
          cycleElements.terminal.append(emptyLine);
        } else {
          for (const item of data.logs) {
            const line = el("div", "term-line " + (item.level || "info"));
            line.append(el("span", "term-time", "[" + (item.timestamp || "--:--:--") + "] "), item.message || "");
            cycleElements.terminal.append(line);
          }
        }
        if (cycleElements.autoscrollChk && cycleElements.autoscrollChk.checked) {
          cycleElements.terminal.scrollTop = cycleElements.terminal.scrollHeight;
        }
      }
    }
  } catch (err) {
    // Falha silenciosa de polling para não poluir tela
  } finally {
    cyclePending = false;
  }
}

if (cycleElements.triggerBtn) {
  cycleElements.triggerBtn.addEventListener("click", async () => {
    cycleElements.triggerBtn.disabled = true;
    cycleElements.triggerBtn.textContent = "Disparando...";
    try {
      const resp = await fetch("/api/study/trigger", {
        method: "POST",
        credentials: "same-origin",
      });
      const res = await resp.json();
      if (!res.success && res.message) {
        alert(res.message);
      }
    } catch (e) {
      alert("Falha ao disparar ciclo: " + (e.message || e));
    } finally {
      setTimeout(refreshCycleLive, 500);
    }
  });
}

if (cycleElements.abortBtn) {
  cycleElements.abortBtn.addEventListener("click", async () => {
    cycleElements.abortBtn.disabled = true;
    cycleElements.abortBtn.textContent = "Interrompendo...";
    try {
      await fetch("/api/study/abort", { method: "POST", credentials: "same-origin" });
    } finally {
      cycleElements.abortBtn.disabled = false;
      setTimeout(refreshCycleLive, 500);
    }
  });
}

if (cycleElements.clearBtn) {
  cycleElements.clearBtn.addEventListener("click", async () => {
    try {
      await fetch("/api/study/clear-logs", { method: "POST", credentials: "same-origin" });
      if (cycleElements.terminal) {
        cycleElements.terminal.replaceChildren();
        lastLogCount = 0;
      }
    } finally {
      setTimeout(refreshCycleLive, 400);
    }
  });
}

if (cycleElements.viewReportBtn && cycleElements.reportModal && cycleElements.reportMarkdownView) {
  cycleElements.viewReportBtn.addEventListener("click", async () => {
    cycleElements.reportMarkdownView.textContent = "Carregando último relatório consolidado...";
    cycleElements.reportModal.classList.remove("hidden");
    try {
      const rep = await get("/api/study/report");
      cycleElements.reportMarkdownView.textContent = rep.report_markdown ||
        "Nenhum relatório gerado ainda. Execute um ciclo para gerar o primeiro boletim.";
    } catch (err) {
      cycleElements.reportMarkdownView.textContent = "Erro ao carregar relatório: " + (err.message || err);
    }
  });
}

if (cycleElements.closeReportBtn && cycleElements.reportModal) {
  cycleElements.closeReportBtn.addEventListener("click", () => {
    cycleElements.reportModal.classList.add("hidden");
  });
}

refreshCycleLive();
setInterval(refreshCycleLive, 2000);
