"use strict";
const input = document.querySelector("#file");
const upload = document.querySelector("#upload");
const remove = document.querySelector("#delete");
const message = document.querySelector("#message");
const result = document.querySelector("#result");
const info = document.querySelector("#file-info");
let fileId = null;

async function api(path, options = {}) {
  const response = await fetch(path, {credentials: "same-origin", cache: "no-store", ...options});
  const payload = await response.json();
  if (!response.ok || payload.status === "failed") {
    throw new Error(payload.detail || payload.error?.message || "Ação indisponível.");
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
  remove.disabled = true;
  try {
    const stored = await api("/files/upload?filename=" + encodeURIComponent(file.name), {
      method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: file,
    });
    fileId = stored.file.file_id;
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
    info.textContent = "";
    result.textContent = "Arquivo excluído.";
    message.textContent = "Arquivo removido do armazenamento privado.";
  } catch (error) {
    message.textContent = "Falha na exclusão: " + error.message;
    remove.disabled = false;
  }
});
