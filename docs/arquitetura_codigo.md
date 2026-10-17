# Arquitetura de Código & Organização do Jarvis

Como o código do Jarvis é estruturado, como o fluxo de dados acontece e como a IA interage com o sistema de arquivos.

---

## 📂 Estrutura de Pastas do Projeto

```text
menor/
├── docker-compose.yml           # Orquestração do banco, IA e túnel de rede
├── pyproject.toml / reqs.txt    # Dependências do Python
├── config/
│   └── settings.yaml            # Portas, caminhos de áudio e chaves
├── data/
│   ├── memoria/                 # Markdown com histórico e perfil do usuário
│   │   ├── usuario_perfil.md
│   │   └── aprendizados.md
│   ├── projetos/                # Pastas de projetos gerenciadas pela IA
│   └── vectordb/                # Banco vetorial para busca semântica (ChromaDB)
└── src/
    ├── api/                     # Servidor FastAPI e WebSockets
    │   ├── main.py              # Ponto de entrada da API
    │   └── rotas_chat.py
    ├── audio/                   # Pipeline de áudio bidirecional
    │   ├── stt_whisper.py       # Microfone -> Texto
    │   └── tts_piper.py         # Texto -> Alto-falante
    ├── brain/                   # Comunicação com o modelo de linguagem
    │   ├── client_llm.py        # Chamadas para Ollama / llama.cpp
    │   └── prompts.py           # System prompts e identidade do Jarvis
    ├── memory/                  # Gerenciador de memória e Markdown
    │   ├── markdown_manager.py  # Leitura e escrita de arquivos .md
    │   └── retriever.py         # Busca semântica de contexto anterior
    └── tools/                   # Habilidades executáveis do Jarvis
        ├── file_tools.py        # Criar, ler e editar arquivos
        ├── terminal_tools.py    # Executar comandos bash controlados
        └── code_sandbox.py      # Executar e testar scripts Python
```

---

## 🔄 Fluxo de Uma Interação (Loop Agêntico)

1. **Entrada**: Você fala no microfone do celular ou notebook.
2. **Transcrição (STT)**: O `faster-whisper` converte o áudio em texto em ~300ms.
3. **Injeção de Contexto (RAG)**: O gerenciador de memória busca notas relevantes em `data/memoria/` e anexa ao prompt.
4. **Raciocínio & Ferramentas**:
   * O LLM recebe a mensagem e decide se responde direto ou invoca uma ferramenta.
   * Se você pediu *"crie um documento do meu novo jogo"*, ele emite um comando estruturado JSON:
     ```json
     {
       "acao": "escrever_arquivo",
       "parametros": {
         "caminho": "data/projetos/jogo_rpg/game_design.md",
         "conteudo": "# Game Design Document\n..."
       }
     }
     ```
5. **Execução**: O módulo `file_tools.py` cria o arquivo no disco.
6. **Resposta Final**: O LLM confirma a ação e o `piper-tts` envia o áudio sintetizado para sua caixa de som.

---

## 🧬 Como Funciona o Auto-Aprimoramento (Self-Improvement)

A IA não recompila os próprios pesos da rede neural; em vez disso, ela utiliza o **Padrão de Reflexão (Agentic Reflection)**:

* **Detecção de Falha**: Ao rodar um script ou tentar executar uma tarefa que deu erro, ela captura o `stderr`.
* **Análise de Causa**: O modelo gera uma explicação do porquê o código falhou.
* **Persistência de Lições**: A IA grava a correção em `data/memoria/aprendizados.md` (ex: *"Quando rodar script X no Ubuntu, usar flag Y"*).
* **Criação de Novas Ferramentas**: Se a IA percebe que faz uma tarefa repetitiva, ela pode escrever um novo script Python dentro de `src/tools/` para expandir suas próprias capacidades.
