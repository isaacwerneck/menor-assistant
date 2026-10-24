"""Assistente de Voz Local para o PC (Windows com GPU).

Ouve comandos de voz, responde em alta velocidade usando o modelo 7B na GPU
e despacha tarefas complexas para o Servidor Ubuntu do Menor v2.
"""
import argparse
import json
import os
import sys
import requests

SERVER_URL = os.environ.get("MENOR_SERVER_URL", "http://192.168.1.100:8000")
LOCAL_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LOCAL_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def speak_text(text: str):
    """Sintetiza voz localmente ou imprime na tela."""
    print(f"\n[Menor Voz]: {text}\n")
    # Tenta usar win32com SAPI nativo do Windows ou Kokoro se instalado
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
    except Exception:
        pass


def chat_local(prompt: str, history: list) -> str:
    """Conversa rápida na GPU local (25-30 tokens/s)."""
    messages = [
        {"role": "system", "content": "Você é a interface de voz do Menor v2 no PC. Seja direto, conciso e natural."},
        *history,
        {"role": "user", "content": prompt},
    ]
    try:
        resp = requests.post(
            f"{LOCAL_OLLAMA_URL}/api/chat",
            json={"model": LOCAL_MODEL, "messages": messages, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as exc:
        return f"Erro ao acessar IA local no PC: {exc}"


def dispatch_to_server(goal: str, project_slug: str = None) -> dict:
    """Envia uma demanda de projeto para a esteira do Servidor Ubuntu."""
    try:
        resp = requests.post(
            f"{SERVER_URL.rstrip('/')}/api/tasks/enqueue",
            json={"goal": goal, "project_slug": project_slug},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Cliente de Voz do Menor v2")
    parser.add_argument("--server", default=SERVER_URL, help="URL da API do Servidor Menor")
    parser.add_argument("--model", default=LOCAL_MODEL, help="Modelo Ollama no PC local")
    args = parser.parse_args()

    print("=" * 60)
    print("Menor v2 - Terminal Interativo de Voz e Comandos (PC Local)")
    print(f"Nó Local (GPU): {LOCAL_OLLAMA_URL} ({args.model})")
    print(f"Hub Servidor:   {args.server}")
    print("=" * 60)
    print("Digite sua mensagem ou digite 'sair' para encerrar.\n")

    history = []
    while True:
        try:
            user_input = input("Você: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("sair", "exit", "quit"):
                break

            # Se for pedido de execução/projeto, avisa e despacha ao servidor
            if any(term in user_input.lower() for term in ("crie o projeto", "inicie o projeto", "monte um app", "faça um plano")):
                speak_text("Entendido! Despachando a estruturação do projeto para o servidor...")
                res = dispatch_to_server(user_input)
                if "task_id" in res:
                    speak_text(f"Tarefa #{res['task_id']} enfileirada no servidor com sucesso.")
                else:
                    speak_text(f"Aviso do servidor: {res.get('error', 'Sem resposta')}")
                continue

            # Conversa rápida normal no PC
            reply = chat_local(user_input, history)
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
