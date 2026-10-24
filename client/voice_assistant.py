"""Assistente de Voz Local para o PC (Windows com GPU).

Ouve comandos de voz e texto, responde em alta velocidade usando o modelo local na GPU
e despacha tarefas de código, arquivos e ferramentas reais para o Servidor Ubuntu do Menor v2.
"""
import argparse
import os
import re
from typing import Any, Dict, List, Optional
import requests

SERVER_URL = os.environ.get("MENOR_SERVER_URL", "http://192.168.0.10:8000")
PASSWORD = os.environ.get("MENOR_PASSWORD", "01020203isaaC!")
LOCAL_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LOCAL_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")

LOCAL_SYSTEM_PROMPT = (
    "Você é a interface de voz ultrarrápida do Menor v2 no PC do Isaac, "
    "conectada em tempo real ao Servidor Hub Central.\n"
    "Diretrizes OBRIGATÓRIAS:\n"
    "1. Responda SEMPRE em português brasileiro, de forma direta, natural e concisa (no máximo 1 a 3 frases curtas).\n"
    "2. NUNCA finja que criou arquivos ou sites quando não executou ferramentas reais. "
    "NUNCA diga 'Pronto, o site foi criado' sem que a ferramenta fs_write tenha sido executada de verdade.\n"
    "3. Se o Isaac pedir para criar, programar, fazer um site, salvar arquivos ou executar comandos, confirme:\n"
    "'Entendido, mano! Já estou enviando essa tarefa para o Servidor Hub executar e salvar os arquivos agora mesmo.'\n"
    "4. Você TEM total capacidade e ferramentas através do Servidor Hub (fs_write, fs_read, terminal_run). "
    "NUNCA diga que é apenas um assistente de voz ou que não pode enviar/manipular arquivos.\n"
    "5. Sem enrolação, sem divagações filosóficas e sem blocos de raciocínio interno em inglês."
)

ACTION_PATTERNS = (
    r"\b(crie|criar|cria|faça|fazer|faz|monte|montar|programa|programar|desenvolva|desenvolver)\b",
    r"\b(site|landing page|app|aplicativo|código|codigo|script|arquivo|pasta|diretório)\b",
    r"\b(html|css|js|python|fastapi|index\.html)\b",
    r"\b(salve|salvar|leia|ler|mostra|mostrar|mande|mandar|envie|enviar|conteúdo|conteudo)\b",
    r"\b(terminal|comando|bash|rodar|rode|execute|executar|npm|pytest|git)\b",
    r"\b(inspecione|inspeção|gaps?|auditoria|estudo|relatório|relatorio|aprimorar)\b",
    r"\b(plano|planeje|planejar|webhook)\b",
)


def speak_text(text: str):
    """Sintetiza voz localmente ou imprime na tela."""
    print(f"\n[Menor Voz]: {text}\n")
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
    except Exception:
        pass


class HubClient:
    """Cliente HTTP autenticado com o Servidor Hub Menor v2."""

    def __init__(self, server_url: str = SERVER_URL, password: str = PASSWORD):
        self.server_url = server_url.rstrip("/")
        self.password = password
        self.session = requests.Session()
        self.authenticated = False

    def login(self) -> bool:
        """Autentica na API do Servidor Hub como proprietário."""
        try:
            resp = self.session.post(
                f"{self.server_url}/auth/login",
                json={"password": self.password},
                headers={"Origin": self.server_url},
                timeout=5,
            )
            if resp.status_code == 200:
                self.authenticated = True
                return True
        except Exception:
            pass
        return False

    def ensure_auth(self):
        if not self.authenticated:
            self.login()

    def run_agent_turn(self, message: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Executa turno com ferramentas reais no Servidor Hub."""
        self.ensure_auth()
        payload = {
            "message": message,
            "history": history[-6:] if history else [],
            "node": "server",
        }
        try:
            resp = self.session.post(
                f"{self.server_url}/agent/run",
                json=payload,
                headers={"Origin": self.server_url},
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            return {"error": str(exc), "reply": f"Erro de conexão com o Hub Servidor: {exc}"}
        return {"error": "Falha na resposta do Hub", "reply": "Não consegui obter resposta do Hub Central."}

    def enqueue_background_task(self, goal: str, project_slug: Optional[str] = None) -> Dict[str, Any]:
        """Envia tarefa para execução autônoma em segundo plano no Hub."""
        self.ensure_auth()
        try:
            resp = self.session.post(
                f"{self.server_url}/api/tasks/enqueue",
                json={"goal": goal, "project_slug": project_slug, "auto_start": True},
                headers={"Origin": self.server_url},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            return {"error": str(exc)}
        return {"error": "Falha ao enfileirar tarefa no Hub"}

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        self.ensure_auth()
        try:
            resp = self.session.get(f"{self.server_url}/api/tasks/{task_id}", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None


def is_action_request(text: str) -> bool:
    """Classifica se o prompt exige ferramentas reais ou criação de arquivos no Hub."""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    matches = sum(1 for pat in ACTION_PATTERNS if re.search(pat, lower))
    return matches >= 1


def clean_local_reply(raw: str) -> str:
    """Remove tags <think> e raciocínio interno do modelo local."""
    cleaned = re.sub(r"<(?:think|thought)>.*?</(?:think|thought)>", "", raw, flags=re.DOTALL)
    cleaned = re.sub(r"<(?:think|thought)>.*", "", cleaned, flags=re.DOTALL)
    parts = re.split(r"\n\s*(?:Resposta|Response|Final Answer|Assistant|Menor):\s*", cleaned, flags=re.IGNORECASE)
    if len(parts) > 1 and parts[-1].strip():
        cleaned = parts[-1].strip()
    return cleaned.strip() or raw.strip()


def chat_local(prompt: str, history: list, model: str = LOCAL_MODEL) -> str:
    """Conversa rápida na GPU local (25-30 tokens/s)."""
    messages = [
        {"role": "system", "content": LOCAL_SYSTEM_PROMPT},
        *history[-6:],
        {"role": "user", "content": prompt},
    ]
    try:
        resp = requests.post(
            f"{LOCAL_OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_predict": 180,
                    "stop": ["\nThinking Process:", "Thinking Process:", "<think>", "Okay, let's"],
                },
            },
            timeout=20,
        )
        if resp.status_code == 200:
            raw = resp.json().get("message", {}).get("content", "")
            return clean_local_reply(raw)
    except Exception as exc:
        return f"Aviso do nó local: {exc}"
    return "Tô na escuta, Isaac! Pode falar."


def main():
    parser = argparse.ArgumentParser(description="Cliente de Voz do Menor v2 (Dual-Brain)")
    parser.add_argument("--server", default=SERVER_URL, help="URL da API do Servidor Menor")
    parser.add_argument("--password", default=PASSWORD, help="Senha do proprietário Menor")
    parser.add_argument("--model", default=LOCAL_MODEL, help="Modelo Ollama no PC local")
    args = parser.parse_args()

    hub = HubClient(server_url=args.server, password=args.password)
    hub_ok = hub.login()

    print("=" * 65)
    print("Menor v2 - Terminal de Voz e Comandos Inteligentes (Dual-Brain)")
    print(f"Nó Local (GPU PC): {LOCAL_OLLAMA_URL} ({args.model})")
    print(f"Hub Central Servidor: {args.server} [{'ONLINE' if hub_ok else 'OFFLINE'}]")
    print("=" * 65)
    print("Digite sua mensagem ou digite 'sair' para encerrar.\n")

    history = []
    while True:
        try:
            user_input = input("Você: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("sair", "exit", "quit"):
                break

            # Dual-Brain: se exigir ferramentas reais (site, código, arquivos, terminal), despacha ao Hub
            if is_action_request(user_input):
                print("\n[Dual-Brain] Ação técnica detectada -> Roteando para ferramentas reais no Hub Central...")
                hub_res = hub.run_agent_turn(user_input, history)
                reply = hub_res.get("reply", "Operação concluída no Hub.")
                tools_used = hub_res.get("tools_executed", [])
                if tools_used:
                    tool_names = [t.get("tool") if isinstance(t, dict) else str(t) for t in tools_used]
                    print(f"[Hub Tools Executadas]: {', '.join(tool_names)}")

                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": reply})
                if len(history) > 10:
                    history = history[-10:]

                speak_text(reply)
                continue

            # Conversa rápida e direta no PC local via GPU
            reply = chat_local(user_input, history, model=args.model)
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})
            if len(history) > 10:
                history = history[-10:]

            speak_text(reply)

        except (KeyboardInterrupt, EOFError):
            print("\nEncerrando Menor v2.")
            break


if __name__ == "__main__":
    main()
