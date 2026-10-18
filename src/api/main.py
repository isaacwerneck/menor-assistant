import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import requests

app = FastAPI(
    title="Menor - Assistente de IA Pessoal",
    description="Servidor de orquestração do Menor, assistente pessoal rodando em hardware doméstico.",
    version="0.1.0",
)

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
SYSTEM_PROMPT = (
    "Você é o Menor, o assistente pessoal de inteligência artificial criado e hospedado localmente pelo Isaac. "
    "Você é altamente competente em programação, desenvolvimento de jogos, planejamento de projetos e tarefas do dia a dia. "
    "Seu tom é parceiro, inteligente, direto e prestativo. Responda sempre em português brasileiro."
)


class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL


class ChatResponse(BaseModel):
    reply: str
    model: str


@app.get("/", response_class=HTMLResponse)
def serve_chat_ui():
    """Interface visual com streaming em tempo real token-a-token."""
    return """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Menor - Assistente IA</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f8fafc; height: 100vh; display: flex; flex-direction: column; }
        header { padding: 16px 24px; background: #111827; border-bottom: 1px solid #1f2937; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 1.25rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
        .status { font-size: 0.85rem; padding: 4px 10px; border-radius: 999px; background: #064e3b; color: #34d399; font-weight: 600; }
        #chat-box { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
        .msg { max-width: 85%; padding: 14px 18px; border-radius: 12px; line-height: 1.6; font-size: 0.95rem; white-space: pre-wrap; word-break: break-word; }
        .msg.user { align-self: flex-end; background: #2563eb; color: #fff; border-bottom-right-radius: 2px; }
        .msg.bot { align-self: flex-start; background: #1f2937; border: 1px solid #374151; color: #e2e8f0; border-bottom-left-radius: 2px; }
        .msg.cursor::after { content: '▋'; display: inline-block; animation: blink 1s infinite; color: #38bdf8; margin-left: 2px; }
        @keyframes blink { 0%, 50% { opacity: 1; } 50.1%, 100% { opacity: 0; } }
        footer { padding: 16px 24px; background: #111827; border-top: 1px solid #1f2937; display: flex; gap: 12px; }
        input { flex: 1; padding: 14px 18px; border-radius: 8px; border: 1px solid #374151; background: #0b0f19; color: #f8fafc; font-size: 1rem; outline: none; }
        input:focus { border-color: #38bdf8; }
        button { padding: 14px 24px; border-radius: 8px; border: none; background: #38bdf8; color: #0b0f19; font-weight: 700; cursor: pointer; transition: 0.2s; }
        button:hover { background: #0284c7; color: #fff; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
    </style>
</head>
<body>
    <header>
        <div class="logo">⚡ Menor Local Assistant</div>
        <div class="status">● RAM Fixa (24h) | Streaming Ativo</div>
    </header>
    <div id="chat-box">
        <div class="msg bot">Opa Isaac! Sou o Menor, seu assistente local. O que vamos programar ou planejar hoje?</div>
    </div>
    <footer>
        <input type="text" id="userInput" placeholder="Mande uma mensagem para o Menor..." autofocus onkeydown="if(event.key==='Enter' && !isGenerating) sendMsg()">
        <button id="sendBtn" onclick="sendMsg()">Enviar</button>
    </footer>

    <script>
        let isGenerating = false;

        async function sendMsg() {
            if (isGenerating) return;
            const input = document.getElementById('userInput');
            const sendBtn = document.getElementById('sendBtn');
            const chatBox = document.getElementById('chat-box');
            const msg = input.value.trim();
            if (!msg) return;

            isGenerating = true;
            sendBtn.disabled = true;

            const userDiv = document.createElement('div');
            userDiv.className = 'msg user';
            userDiv.textContent = msg;
            chatBox.appendChild(userDiv);
            input.value = '';

            const botDiv = document.createElement('div');
            botDiv.className = 'msg bot cursor';
            botDiv.textContent = '';
            chatBox.appendChild(botDiv);
            chatBox.scrollTop = chatBox.scrollHeight;

            try {
                const response = await fetch('/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg })
                });

                if (!response.ok) throw new Error('Falha no servidor');

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    botDiv.textContent += decoder.decode(value, { stream: true });
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            } catch (err) {
                botDiv.textContent = 'Erro ao se comunicar com o Menor: ' + err.message;
            } finally {
                botDiv.classList.remove('cursor');
                isGenerating = false;
                sendBtn.disabled = false;
                input.focus();
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        }
    </script>
</body>
</html>
"""


def stream_ollama_generator(message: str, model: str):
    """Gera tokens sob demanda do Ollama com modelo fixado na memória RAM."""
    payload = {
        "model": model,
        "prompt": message,
        "system": SYSTEM_PROMPT,
        "stream": True,
        "keep_alive": "24h",  # Mantém o modelo sempre carregado na RAM (sem recargas de disco)
    }

    try:
        with requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=120) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
    except Exception as e:
        yield f"\n[Erro de conexão: {str(e)}]"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Endpoint de streaming em tempo real token-a-token."""
    return StreamingResponse(
        stream_ollama_generator(req.message, req.model),
        media_type="text/plain",
    )


@app.post("/chat", response_model=ChatResponse)
def chat_sync(req: ChatRequest):
    """Endpoint tradicional síncrono para scripts e chamadas de API."""
    payload = {
        "model": req.model,
        "prompt": req.message,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "keep_alive": "24h",
    }

    try:
        res = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=90)
        res.raise_for_status()
        data = res.json()
        return ChatResponse(reply=data.get("response", ""), model=req.model)
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Motor do Ollama não está rodando na porta 11434.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro durante a inferência: {str(e)}")


@app.get("/health")
def health_check():
    """Verifica a integridade do servidor e se o Ollama está online."""
    try:
        res = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        ollama_status = "online" if res.status_code == 200 else "degraded"
    except Exception:
        ollama_status = "offline"

    return {
        "status": "online",
        "service": "Menor API",
        "ollama_status": ollama_status,
        "default_model": DEFAULT_MODEL,
    }


@app.get("/models")
def list_models():
    """Retorna os modelos instalados no Ollama."""
    try:
        res = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao conectar com Ollama: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
