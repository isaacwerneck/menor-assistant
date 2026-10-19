"use strict";
const input = document.querySelector("#file");
const upload = document.querySelector("#upload");
const remove = document.querySelector("#delete");
const message = document.querySelector("#message");
const result = document.querySelector("#result");
const info = document.querySelector("#file-info");
const question = document.querySelector("#question");
const context = document.querySelector("#context");
const visual = document.querySelector("#vision");
const visionState = document.querySelector("#vision-state");
let fileId = null;
let fileFormat = null;
let visionAvailable = false;

function enableActions() {
  const present = Boolean(fileId);
  context.disabled = !present || ["png", "jpeg", "gif", "bmp", "webp"].includes(fileFormat);
  visual.disabled = !present || !visionAvailable ||
    !["png", "jpeg", "gif", "bmp", "webp"].includes(fileFormat);
}

async function refreshVision() {
  try {
    const state = await api("/files/vision/status");
    visionAvailable = Boolean(state.installed);
    visionState.textContent = visionAvailable ?
      "Modelo local detectado (qualidade ainda não validada)." : state.reason;
  } catch (error) {
    visionAvailable = false;
    visionState.textContent = "Não consegui consultar a disponibilidade de visão local.";
  }
  enableActions();
}

async function ask(mode) {
  if (!fileId || !question.value.trim()) {
    message.textContent = "Informe uma pergunta e envie um arquivo primeiro.";
    return;
  }
  context.disabled = true;
  visual.disabled = true;
  message.textContent = mode === "vision" ? "Analisando imagem com modelo local..." :
    "Localizando trechos e referências no documento...";
  try {
    const output = await api("/files/" + fileId + "/" + mode, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: question.value.trim()}),
    });
    result.textContent = JSON.stringify(output, null, 2);
    message.textContent = mode === "vision" ?
      "Parecer visual gerado; conteúdo NÃO verificado independentemente." :
      "Trechos e origens localizados; nenhuma resposta inventada.";
  } catch (error) {
    result.textContent = "A consulta não foi concluída.";
    message.textContent = "Falha: " + error.message;
  } finally {
    enableActions();
  }
}

context.addEventListener("click", () => ask("context"));
visual.addEventListener("click", () => ask("vision"));
refreshVision();

async function api(path, options = {}) {
  const response = await fetch(path, {credentials: "same-origin", cache: "no-store", ...options});
  const payload = await response.json();
  if (!response.ok || payload.status === "failed") {
    throw new Error(payload.detail || payload.error?.message || payload.reason ||
      payload.model_state?.reason || "Ação indisponível.");
  }
  return payload;
}

upload.addEventListener("click", async () => {
  const file = input.files?.[0];
  if (!file) {
    message.textContent = "Selecione um arquivo.";
    return;
  }
  if (file.size > 8 * 1024 * 1024 || file.size === 0) {
    message.textContent = "O arquivo deve ter de 1 byte a 8 MB.";
    return;
  }
  upload.disabled = true;
  message.textContent = "Lendo e analisando o arquivo...";
  result.textContent = "";
  fileId = null;
  fileFormat = null;
  enableActions();
  remove.disabled = true;
  try {
    const stored = await api("/files/upload?filename=" + encodeURIComponent(file.name), {
      method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: file,
    });
    fileId = stored.file.file_id;
    fileFormat = stored.file.format;
    enableActions();
    remove.disabled = false;
    const receipt = await api("/files/" + fileId);
    info.textContent = stored.file.filename + " — " + receipt.file.format;
    result.textContent = JSON.stringify({
      metadata: receipt.metadata,
      content: receipt.content,
      evidence: receipt.evidence,
      truncated: receipt.truncated,
      limitations: receipt.limitations,
      semantic_verified: receipt.validation.semantic_verified,
    }, null, 2);
    message.textContent = "Extração concluída. Avalie as limitações do resultado.";
  } catch (error) {
    message.textContent = "Falha: " + error.message;
    result.textContent = "Não foi possível concluir a análise.";
  } finally {
    upload.disabled = false;
  }
});

remove.addEventListener("click", async () => {
  if (!fileId || !window.confirm("Excluir permanentemente este arquivo do servidor?")) return;
  remove.disabled = true;
  try {
    await api("/files/" + fileId, {method: "DELETE"});
    fileId = null;
    fileFormat = null;
    enableActions();
    info.textContent = "";
    result.textContent = "Arquivo excluído.";
    message.textContent = "Arquivo removido do armazenamento privado.";
  } catch (error) {
    message.textContent = "Falha na exclusão: " + error.message;
    remove.disabled = false;
  }
});
