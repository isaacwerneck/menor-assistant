import json
from pathlib import Path
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

TEMPLATES_DIR = Path(__file__).parent / "templates"


class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL


class ChatResponse(BaseModel):
    reply: str
    model: str


@app.get("/", response_class=HTMLResponse)
def serve_chat_ui():
    """Interface visual estilo ChatGPT para conversar com o Menor."""
    html_file = TEMPLATES_DIR / "chat.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


def stream_ollama_generator(message: str, model: str):
    """Gera tokens sob demanda do Ollama com modelo fixado na memória RAM."""
    payload = {
        "model": model,
        "prompt": message,
        "system": SYSTEM_PROMPT,
        "stream": True,
        "keep_alive": "24h",
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
