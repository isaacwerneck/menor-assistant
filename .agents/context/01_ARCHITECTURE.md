# 01 — Arquitetura e Comunicação entre Nós

O Menor v2 foi desenhado para maximizar a performance combinando o melhor do hardware do desenvolvedor:

```mermaid
flowchart TD
    User["Desenvolvedor (Voz / Web UI)"] <--> PC["PC Principal (Windows)"]
    
    subgraph PC_Sub ["Nó Cliente (PC / GTX 1650 4GB)"]
        Browser["Navegador Web (chat.html)"]
        VoiceApp["client/voice_assistant.py (Microfone/TTS)"]
        OllamaLocal["Ollama Local: qwen2.5:7b (GPU)\n~25-30 tokens/s"]
    end

    subgraph Server_Sub ["Nó Servidor (Notebook Ubuntu / 32GB RAM)"]
        FastAPIServer["FastAPI Hub (:8000)\nsrc/api/main.py"]
        OllamaServer["Ollama Servidor: qwen2.5:14b (CPU)\n~5-6 tokens/s"]
        SQLiteBrain["Cérebro SQLite FTS5\n~/menor-data/cerebro/"]
        TaskQueueDB["Fila de Tarefas\n~/menor-data/tasks_v2.db"]
        OSTools["Ferramentas Reais do SO\nsrc/tools/core.py"]
    end

    Browser -- "HTTP / SSE (:8000)" --> FastAPIServer
    VoiceApp -- "POST /api/tasks/enqueue" --> FastAPIServer
    VoiceApp -- "Chat Local (:11434)" --> OllamaLocal
    FastAPIServer -- "Orquestração (:11434)" --> OllamaServer
    FastAPIServer --> OSTools
    FastAPIServer --> SQLiteBrain
    FastAPIServer --> TaskQueueDB
```

## Divisão de Responsabilidades

1. **Nó Servidor (Notebook Ubuntu):**
   * Roda ininterruptamente via systemd (`menor-api.service`).
   * Mantém o estado da memória e projetos em disco.
   * Executa comandos e scripts de terminal solicitados pelos agentes.
   * Utiliza `qwen2.5:14b` para raciocínio profundo, quebra de tarefas e documentação.

2. **Nó Cliente (PC Windows):**
   * Interface de uso imediato: o usuário acessa `http://<IP-DO-NOTEBOOK>:8000` pelo navegador do PC.
   * Pode alternar instantaneamente entre a inferência pesada no notebook ou a inferência ultra-rápida na GPU local usando o seletor da UI.
