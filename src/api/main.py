from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(
    title="Jarvis Local Assistant API",
    description="Servidor de orquestração do assistente Jarvis rodando em hardware doméstico.",
    version="0.1.0",
)

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
SYSTEM_PROMPT = (
    "Você é o Jarvis, o assistente pessoal de inteligência artificial criado e hospedado localmente pelo Isaac. "
    "Você é altamente competente em programação, planejamento de projetos, jogos e tarefas do dia a dia. "
    "Seja direto, prestativo, inteligente e responda em português brasileiro."
)


class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL
    stream: bool = False


class ChatResponse(BaseModel):
    reply: str
    model: str


@app.get("/")
def read_root():
    """Verifica a integridade do servidor e se o Ollama está online."""
    try:
        res = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        ollama_status = "online" if res.status_code == 200 else "degraded"
    except Exception:
        ollama_status = "offline"

    return {
        "status": "online",
        "service": "Jarvis API",
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


@app.post("/chat", response_model=ChatResponse)
def chat_with_jarvis(req: ChatRequest):
    """Envia uma mensagem para o Jarvis e retorna a resposta."""
    payload = {
        "model": req.model,
        "prompt": req.message,
        "system": SYSTEM_PROMPT,
        "stream": False,
    }

    try:
        res = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
        res.raise_for_status()
        data = res.json()
        return ChatResponse(reply=data.get("response", ""), model=req.model)
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Motor do Ollama não está rodando na porta 11434.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro durante a inferência: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
