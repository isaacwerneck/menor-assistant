# PLANO DE ENGENHARIA E ARQUITETURA: MENOR ASSISTANT

> **Status em 21/10/2026: proposta em avaliação, sem implementação iniciada.**
> O texto recebido foi preservado abaixo. Antes de implementar, ler a revisão
> técnica e o controle de progresso nas seções 5 e 6; exemplos e estimativas
> deste documento não são comandos autorizados nem capacidades comprovadas.

**Destinatário**: Codex / Engenheiro de Implementação  
**Objetivo**: Transformar o "Menor Assistant" de um chatbot rígido/estático em um agente autônomo, conversacional, modular e extensível rodando em servidor local (CPU i7 11ª Gen + 32 GB RAM).

---

## 1. DIAGNÓSTICO: POR QUE O MODELO ATUAL ESTÁ "BURRO E DURO"?

### 1.1. Erro Conceitual: "Treinar" vs. "Engenharia de Agentes"
* **A Falha**: Tentar fazer Fine-Tuning ou Machine Learning tradicional para tornar um modelo mais "inteligente" em hardware local (CPU) não funciona e causa esquecimento catastrófico (*catastrophic forgetting*).
* **Como a OpenAI, Anthropic e DeepSeek fazem**: IAs assistentes não "aprendem" alterando seus pesos neurais em tempo de execução. A inteligência operacional vem de:
  1. **Prompt de Sistema Estruturado (System Instructions)** com templates de raciocínio.
  2. **Chamada de Ferramentas Estrita (Native Function Calling / Tool Calling)** com validação de esquema JSON.
  3. **Loop ReAct (Reasoning + Acting)** com auto-correção imediata após erros de execução.
  4. **Memória de Longo Prazo Externa** (RAG vetorial + arquivos Markdown estruturados).

### 1.2. Gargalos de Hardware e Seleção de Modelo
* **Hardware Disponível**: Intel Core i7 11ª Geração (8 núcleos / 16 threads), 32 GB RAM, 200 GB SSD NVMe, sem GPU dedicada de alto desempenho.
* **Diagnóstico do Modelo (Qwen 7B)**:
  * O **Qwen 2.5 7B Instruct** é uma das melhores bases compactas do mundo para raciocínio e function calling, mas rodá-lo como modelo base ou sem quantização adequada em CPU destrói a velocidade e a inteligência.
  * Em CPU com 32 GB de RAM, o **Qwen 2.5 14B Instruct (Quantização Q4_K_M)** roda consumindo ~9 a 10 GB de RAM a ~8-12 tokens/segundo, entregando um salto massivo de coerência lógica sobre a versão de 7B.
  * Formato obrigatório: **GGUF** rodando sobre engine otimizada com instruções vetoriais AVX-512 (llama.cpp / Ollama).

---

## 2. ARQUITETURA DO SISTEMA (MENOR AGENT CORE)

```
                       ┌─────────────────────────┐
                       │   Interface Usuário     │
                       │ (CLI / Web / Telegram)  │
                       └────────────┬────────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │  Orquestrador Principal │
                       │    (FastAPI / Python)   │
                       └──────┬────────────┬─────┘
                              │            │
            ┌─────────────────┴─┐        ┌─┴─────────────────┐
            ▼                   ▼        ▼                   ▼
    ┌───────────────┐   ┌────────────┐ ┌──────────────┐   ┌──────────────┐
    │ Motor Local   │   │ Ferramentas│ │ Memória &    │   │ Sub-Agentes  │
    │ Ollama / vLLM │   │ Dinâmicas  │ │ Conhecimento │   │ Especialistas│
    │ (Qwen 2.5 14B)│   │ (Registry) │ │ (ChromaDB/MD)│   │ (Coder, etc.)│
    └───────────────┘   └────────────┘ └──────────────┘   └──────────────┘
```

### 2.1. Componentes Principais
1. **Inference Engine**: Ollama local com `qwen2.5:14b-instruct-q4_K_M` (ou `qwen2.5:7b-instruct-q4_K_M` para respostas ultra-rápidas). Fallback opcional via API (Groq / OpenRouter) para tarefas analíticas pesadas.
2. **Agent Runtime**: Loop ReAct puro em Python (sem inchaço de frameworks pesados). Baseado em schemas Pydantic.
3. **Dynamic Tool Registry**: Sistema onde ferramentas são arquivos Python isolados carregados dinamicamente via `importlib`.
4. **Memory Layer**:
   * *Curto Prazo*: Histórico da sessão em buffer circular com resumo automático.
   * *Longo Prazo*: Base vetorial leve (ChromaDB local) + arquivos de notas `memory/*.md`.
5. **Skill Factory & Self-Evolution**: Capacidade do agente de escrever código de novas ferramentas, executar em sandbox de teste e adicioná-las ao seu próprio catálogo.

---

## 3. ESPECIFICAÇÃO DE IMPLEMENTAÇÃO (PASSO A PASSO PARA O CODEX)

### Fase 1: Setup da Infraestrutura de Inferência
1. Instalar o **Ollama** no servidor Linux/Windows:
   ```bash
   ollama pull qwen2.5:7b-instruct-q4_K_M
   ollama pull qwen2.5:14b-instruct-q4_K_M
   ```
2. Configurar variáveis de ambiente de CPU para uso máximo de threads (`OLLAMA_NUM_PARALLEL=1`, `OMP_NUM_THREADS=8`).

### Fase 2: Estrutura do Repositório do Projeto
O Codex deve estruturar o projeto com o seguinte layout limpo:

```
menor_assistant/
├── config/
│   ├── settings.py           # Configurações de modelo, paths e chaves
│   └── system_prompt.txt     # Persona, regras e diretrizes operacionais
├── core/
│   ├── agent.py              # Loop ReAct (pensamento -> ação -> observação)
│   ├── llm_client.py         # Cliente Ollama / OpenAI API format
│   └── memory.py             # RAG local e histórico persistente
├── tools/
│   ├── __init__.py
│   ├── base.py               # Classe base abstrata e decorator @tool
│   ├── file_system.py        # Criação de pastas, leitura/escrita
│   ├── git_tools.py          # Git init, commit, push, integração GitHub
│   ├── terminal.py           # Execução de comandos bash/powershell
│   ├── web_search.py         # Pesquisa web (DuckDuckGo Search)
│   └── dynamic_tools/        # Pasta de ferramentas criadas pela própria IA
├── subagents/
│   ├── coder.py              # Agente focado exclusivamente em programar
│   └── researcher.py         # Agente de busca e síntese de conhecimento
├── memory/
│   ├── daily_logs/           # Logs de conversas e aprendizados
│   └── knowledge/            # Artigos e resumos criados pelo auto-estudo
├── main.py                   # Ponto de entrada (CLI ou API)
└── requirements.txt
```

### Fase 3: System Prompt Fundamental
O prompt de sistema deve eliminar respostas de "chatbot de FAQ" e forçar o comportamento direto e acionável:

```text
Você é o "Menor Assistant", uma IA assistente autônoma, direta, técnica e resolutiva.
REGRAS FUNDAMENTAIS:
1. NUNCA dê respostas evasivas, burocráticas ou filosóficas vazias.
2. Seja conciso. Quando receber um comando, execute a ação usando suas ferramentas.
3. Se um comando falhar, analise o traceback, ajuste os parâmetros e tente novamente antes de responder ao usuário.
4. Idioma padrão: Português coloquial, natural, sem formalismos desnecessários.
5. Sempre que precisar realizar alterações no sistema operacional, delegue ou chame a ferramenta adequada.
```

### Fase 4: Mecanismo de Tool Calling e Criação Dinâmica de Ferramentas
O Codex deve implementar o registro dinâmico via decorator e a ferramenta `create_new_tool`:

```python
# tools/base.py
import inspect
from typing import Callable, Dict, Any
from pydantic import BaseModel

TOOLS_REGISTRY: Dict[str, Any] = {}

def tool(name: str, description: str):
    def decorator(func: Callable):
        TOOLS_REGISTRY[name] = {
            "name": name,
            "description": description,
            "func": func,
            "parameters": inspect.signature(func)
        }
        return func
    return decorator
```

```python
# tools/dynamic_tools_manager.py
import os
from tools.base import tool, TOOLS_REGISTRY

@tool(
    name="create_new_tool",
    description="Cria uma nova ferramenta em Python para expandir suas próprias capacidades."
)
def create_new_tool(tool_name: str, python_code: str) -> str:
    file_path = f"tools/dynamic_tools/{tool_name}.py"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(python_code)
    
    # Validação sintática antes de carregar
    try:
        compiled = compile(python_code, file_path, "exec")
        module_ns = {}
        exec(compiled, module_ns)
        return f"Ferramenta {tool_name} criada e validada com sucesso."
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return f"Falha ao validar a ferramenta {tool_name}: {str(e)}"
```

### Fase 5: Módulo de Auto-Estudo e Pesquisa Contínua
Para a IA "aprender" sem quebrar o modelo:
1. O usuário comanda: *"Menor, estude sobre arquiteturas de microsserviços em Go"*.
2. O agente ativa o sub-agente `researcher`:
   * Dispara buscas via DuckDuckGo API / Scraper.
   * Extrai o conteúdo dos 3 melhores artigos técnicos.
   * Resume as lições chave e gera um arquivo Markdown estruturado em `memory/knowledge/microservicos_go.md`.
   * Registra embeddings do arquivo no ChromaDB local.
3. Nas próximas conversas, a busca vetorial injeta esse conhecimento no contexto quando o assunto surgir.

### Fase 6: Orquestração e Delegação Multi-Agente
O `Menor Assistant` atua como **Gerente de Projeto (Orquestrador)**:
* Recebe a demanda: *"Crie um projeto de API em FastAPI, com testes e repositório Git"*.
* Etapa 1: Chama `file_system.create_directory("meu_projeto")`.
* Etapa 2: Invoca o `coder_agent` passando o escopo técnico.
* Etapa 3: O `coder_agent` gera os arquivos de código e executa `pytest`.
* Etapa 4: O orquestrador aciona `git_tools.init_and_push("meu_projeto")`.
* Etapa 5: Responde ao usuário apenas com o sumário do que foi concluído e o link/path.

---

## 4. CHECKLIST DE VERIFICAÇÃO PARA O CODEX
- [ ] Configurar Ollama com `qwen2.5:14b-instruct-q4_K_M` e testar latência de inferência em CPU.
- [ ] Implementar o loop ReAct com suporte estrito a Function Calling (schemas JSON nativos).
- [ ] Criar as ferramentas essenciais: `file_ops`, `terminal_exec`, `git_ops`, `web_search`.
- [ ] Implementar a pasta `tools/dynamic_tools` com carregamento em tempo de execução via `importlib`.
- [ ] Configurar ChromaDB local embutido para persistência de conhecimento pesquisado.
- [ ] Adicionar auto-correção: capturar `stderr` de comandos do terminal e reenviar ao modelo para correção autônoma.
- [ ] Testar fluxo ponta a ponta: "Criar repositório, escrever script de teste, executar e comitar".

---

## 5. REVISÃO TÉCNICA ANTES DA IMPLEMENTAÇÃO — 21/10/2026

Base conferida: `main` em `7d3f32dc075f1099c2fa3b4edbe3c807df7e8754`.
Esta revisão registra uma proposta de execução, não aprovação de dependências,
downloads, serviços externos, mudanças de sistema ou execução dos exemplos.

### Direção recomendada

O objetivo de um agente conversacional com ferramentas, memória e correção de
erros está alinhado à visão do Menor. A evolução deve aproveitar a arquitetura
existente, preservar conversas e projetos e avaliar pedidos inéditos. Não
substituir compreensão por respostas prontas ou por rotas específicas para jogos.

### Correções e decisões necessárias

1. **Hardware e desempenho:** o inventário anterior identifica i7-1185G7,
   com **4 núcleos/8 threads**, não 8/16. Confirmar se continua sendo o mesmo
   servidor. Os 8–12 tokens/s do 14B são hipótese, não benchmark deste Ubuntu.
   Peso do arquivo, RAM total e velocidade são medidas diferentes. Comparar
   candidatos no hardware real antes de escolher o modelo padrão; 14B pode
   piorar a latência. AVX-512 não é requisito universal do produto.
2. **Modelo e treinamento:** o modelo observado era `qwen2.5-coder:7b`, não
   necessariamente o Qwen geral citado no plano. Fine-tuning não causa
   inevitavelmente esquecimento catastrófico; é uma técnica distinta, com
   custos e riscos próprios. RAG ajuda a fornecer evidência, mas não altera
   pesos nem garante raciocínio correto. Não há garantia de equivalência ao Codex.
3. **Reutilização:** já existem FastAPI/Ollama, catálogo validado, loop limitado,
   memória Markdown/SQLite/FTS5, embeddings opcionais, pesquisa com citações,
   criação supervisionada de um arquivo de projeto e proposta de tools por PR.
   Não reorganizar todo o repositório nem introduzir ChromaDB, vLLM ou APIs
   comerciais sem demonstrar a lacuna e decidir a dependência com o proprietário.
4. **Ferramentas dinâmicas:** o exemplo de `create_new_tool` NÃO é implementação
   adequada: grava antes de validar, não limita o nome/caminho e executa código
   gerado no processo atual. `compile` verifica sintaxe; `exec` executa com as
   permissões do servidor. `inspect.signature` também não é um JSON Schema.
   Reutilizar `tool_builder.py`, `code_sandbox.py` e `custom_runtime.py` para
   evoluir o ciclo proposta → testes isolados → CI/revisão → registro → execução.
   O executor existente é limitado a ferramentas puras de texto, não agente geral.
5. **Autocorreção e autonomia:** não repetir cegamente comandos com efeitos.
   Usar observação sanitizada, limites de tentativas/tempo, estado persistente,
   idempotência e autorização por escopo. Separar explicação, plano, ação,
   recibo e verificação do resultado. Subagentes compartilham o orçamento da CPU;
   delegação lógica não implica inferência paralela mais rápida.

Fontes primárias consultadas em 21/10/2026:

- [Intel: especificações do i7-1185G7](https://www.intel.com/content/www/us/en/products/sku/208664/intel-core-i71185g7-processor-12m-cache-up-to-4-80-ghz-with-ipu/specifications.html).
- [Ollama: variante Qwen 14B Q4_K_M](https://ollama.com/library/qwen2.5:14b-instruct-q4_K_M) — existência do modelo não demonstra desempenho local.
- [Qwen: documentação do 14B Instruct](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct).
- [Hugging Face: LoRA](https://huggingface.co/docs/peft/main/en/conceptual_guides/lora).
- [Inventário e medições anteriores do projeto](docs/handoff/02_HARDWARE_E_LATENCIA.md).

## 6. CONTROLE DE PROGRESSO E EVIDÊNCIAS

Marcar `[x]` somente após entrega demonstrada. Em cada atualização registrar
PR/commit, testes e resultado observado. Código/CI aprovados e comportamento
comprovado no Ubuntu são estados diferentes. Itens parciais continuam `[ ]`.

- [x] Receber e revisar tecnicamente o plano; registrar sua referência no Git.
- [ ] Validar hardware atual e comparar modelos/quantizações com qualidade,
  p50/p95 e memória; escolher o padrão por resultado, sem promessa de velocidade.
- [ ] Consolidar conversa geral e interpretação contextual sem respostas fixas;
  avaliar compreensão, continuidade e naturalidade em conversas inéditas.
- [ ] Completar o ciclo geral de ferramentas tipadas com autorização, execução,
  observação e verificação. **Parcial:** `src/tools/registry.py` e
  `src/agent/runner.py`; JSON de decisão não prova native tool calling completo.
- [ ] Completar programação em workspace isolado com vários arquivos, testes e
  Git/PR. **Parcial:** `src/projects/code_workspace.py` cria um arquivo;
  isso não prova executar/testar um projeto ou publicá-lo.
- [ ] Completar criação/incorporação de skills com testes e revisão.
  **Parcial:** `src/agent/tool_builder.py` e `src/agent/custom_runtime.py`.
  Sem importar código recém-gerado no servidor nem instalar a versão do exemplo.
- [ ] Validar estudo e recuperação de conhecimento com fonte/data/versão,
  atualização e isolamento. **Parcial:** `src/agent/research.py`,
  `src/memory/search.py` e `src/memory/semantic.py`; não exige ChromaDB por si só.
- [ ] Completar autocorreção limitada com falhas sanitizadas, retomada e proteção
  contra efeitos duplicados; comprovar estado final em sandbox.
- [ ] Passar o fluxo final com tarefa inédita: criar projeto, gerar arquivos,
  executar testes e preparar commit/PR; registrar efeitos reais e limites.

**Ordem proposta para decidir antes de implementar:** baseline/modelo → conversa
e contexto → ciclo de execução → programação/Git → skills e conhecimento →
autonomia prolongada. Os subagentes entram quando uma tarefa comprovadamente
precisar deles; não são condição para começar. Os sete itens da seção 4 seguem
pendentes; as tecnologias específicas dessa lista ainda precisam ser avaliadas.
