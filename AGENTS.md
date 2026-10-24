# AGENTS.md — Instruções Canônicas para Agentes de IA

Bem-vindo ao repositório do **Menor v2**. Este documento é a porta de entrada obrigatória para qualquer modelo ou agente de inteligência artificial (Cursor, Claude Code, Antigravity, Aider, Codex, Copilot) que for ler, manter ou expandir este projeto.

---

## 1. O que é o Menor v2?

O **Menor v2** é um assistente pessoal e executivo de software distribuído e local:
* **Hub Central (Notebook Ubuntu / 32 GB RAM):** Executa o servidor FastAPI, gerencia o cérebro permanente (SQLite FTS5), hospeda a interface web e orquestra ferramentas reais do sistema operacional com o modelo `qwen2.5:14b` via Ollama.
* **Cliente Interativo (PC Windows / GPU GTX 1650):** Onde o usuário programa e fala por voz com o modelo `qwen2.5:7b` em altíssima velocidade (~25 tokens/s), despachando tarefas pesadas ao servidor.

---

## 2. Regras de Ouro e Diretrizes Inegociáveis

1. **Ferramentas Reais, Nunca Simulações:**
   * Qualquer tarefa que precise criar arquivos, inspecionar código ou rodar testes DEVE usar ferramentas reais do sistema (`src/tools/core.py`: `fs_read`, `fs_write`, `terminal_run`, `save_plan`).
   * Nunca crie classificadores sintéticos com gramáticas JSON rígidas de dezenas de campos, nem tente inventar regexes de sim/não para mensagens do usuário.
2. **Native Tool Calling:**
   * A inferência do modelo usa o padrão de ferramentas nativas do Ollama/OpenAI (`tools=[...]`).
   * Não execute cascata de 3 chamadas por turno (`router -> intelligence -> review`). Uma única chamada resolve o turno.
3. **Preservação de Integridade:**
   * Dados mutáveis (memória, notas, sessões, logs) são salvos fora do repositório Git em `~/menor-data/`.
   * Mantenha os testes em `tests/` sempre 100% verdes antes de qualquer commit, pois o deploy no servidor Ubuntu (`scripts/deploy.sh`) aborta o reinício da API se os testes falharem.

---

## 3. Mapa de Contexto Detalhado

Antes de realizar alterações complexas, consulte os guias na pasta [`.agents/context/`](.agents/context/):
* [01 — Arquitetura e Rede](.agents/context/01_ARCHITECTURE.md): Comunicação entre nós, portas de rede e fluxo de dados.
* [02 — Catálogo de Ferramentas](.agents/context/02_TOOLS.md): Especificação das ferramentas do sistema operacional.
* [03 — Padrões de Código](.agents/context/03_CODE_STANDARDS.md): Estilo Python, tipagem e convenções do FastAPI.
* [04 — Armazenamento e Estado](.agents/context/04_STORAGE_AND_STATE.md): Estrutura do SQLite FTS5 e workspace de projetos.

---

## 4. Comandos Essenciais

```bash
# Rodar todos os testes unitários (obrigatório antes de commits)
python3 -m unittest discover -s tests -v

# Iniciar o servidor localmente para desenvolvimento
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Executar cliente de voz interativo (no PC)
python3 client/voice_assistant.py
```
