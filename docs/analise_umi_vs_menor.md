# Estudo Comparativo e Benchmark: Menor v2 vs. Arquitetura Umi (2 Anos de Evolução)

Este documento registra a análise técnica detalhada da documentação da **Umi** (assistente local distribuído em Debian/Windows desenvolvido e refinado ao longo de 2 anos) e estabelece o diagnóstico crítico de engenharia: **onde o Menor v2 está errando, o que a Umi resolveu com excelência e como consertar nossa arquitetura.**

---

## 1. Tabela Comparativa: Menor v2 vs. Umi

| Dimensão | Menor v2 (Atual / Onde estamos errando) | Umi (Produção de 2 Anos / O que faz certo) |
| :--- | :--- | :--- |
| **Arquitetura Geral** | Monolito de orquestração (`src/agent/orchestrator.py`) misturando regras de negócio, prompts, schemas de ferramentas e chamadas HTTP. | Separação rígida: **Núcleo** (identidade, memória canônica), **Mente** (motores LLM plugáveis), **Corpo** (hardware/áudio/telas), **Gateways** e **Extensões**. |
| **System Prompt & Comportamento** | **Tapa-buracos negativos (Band-aids):** 20 regras em CAPS no prompt proibindo simulações, menções e siglas ("NUNCA isso", "NUNCA aquilo"). Causa *Attention Sink* no Qwen. | **Identidade canônica e positiva:** `SOUL.md` (essência durável), `SELF.md` (autopercepção em 1ª pessoa). O comportamento é garantido pelo pipeline, não por broncas no prompt. |
| **Gerenciamento de Contexto** | Poda crua por caracteres (`MAX_HISTORY_CHARS = 4400`) e bifurcação heurística frágil (`FastPath` vs `HeavyPath` via `_needs_tools()`). | **Context Budget v2 em Tokens:** Camadas protegidas (identidade/pessoa) + Camadas consultivas sob demanda (cartões ranqueados por BM25/Ori). Prompt casual < 300 tokens naturalmente. |
| **Consolidação de Memória** | `ReflectionWorker` tentando gerar "Golden Examples" sintéticos. Projetos hardcoded no código (`DEFAULT_BLOCKS` em `core_memory.py`). | **Rotina de Dream Diário (`umi.dream.daily` às 21h):** Varre os transcripts reais do dia, extrai fatos verificáveis, grava em diário append-only (`.jsonl`) e atualiza resumos de projetos. |
| **Observabilidade e Debug** | Logs soltos de terminal. Quando o modelo alucina ou demora 130s, precisa-se adivinhar o que foi enviado ao Ollama. | **Prompt Trace v2 & Context Trace:** A cada chamada ao LLM, grava o payload exato, tokens consumidos, camadas e a proveniência de cada trecho em timeline tipada. |
| **Taxonomia Operacional** | Tarefas, lembretes, metas e jobs de sistema misturados em filas genéricas do SQLite. | **Taxonomia Estrita:** Tarefa (humana pontual), Lembrete (alerta horário), Agendamento (recorrente humano) e Rotina Intrínseca (manutenção da máquina). Zero mistura. |
| **Entrega de Mensagens & Erros** | **Brochure-Dumping:** Erros de sistema e nomes de ferramentas internas vazam para a conversa do usuário. | **Decisão Autoral de Entrega:** Fatos técnicos vão para log/chat do sistema; para o humano (Voz/Discord/Web), a IA gera apenas um aviso curto, natural e contextual. |
| **Pipeline de Áudio / Voz** | Gravação de WAVs temporários em disco, dependência de nomes voláteis de dispositivos do Windows. | Wake Word local leve via ONNX (`umi.onnx`), streaming de PCM em RAM, amarração de microfone/saída por hardware UID estável e modo *fail-closed*. |
| **Integração com Agentes de Código** | Tentativa de fazer o assistente ser o próprio executor de diffs ou tarefas complexas na mesma janela de contexto. | **Extensão de Agentes (Codex / Antigravity):** Espaços isolados para agentes de código; o assistente recebe apenas o manifesto incremental e recibos, sem poluir a memória pessoal. |

---

## 2. Diagnóstico Crítico: Os 5 Maiores Erros do Menor v2

### Erro 1: "Prompt Band-Aids" e Paradoxo do Elefante Rosa
No arquivo `src/agent/orchestrator.py`, acumulamos restrições negativas:
```text
- NUNCA use web_read nem web_search para pedidos de criar ou programar sites/arquivos locais.
- NUNCA invente siglas corporativas como "Grupo Nacional de Tecnologia".
- NUNCA invente reuniões, compromissos ou presuma a rotina pessoal do Isaac.
```
* **A Falha:** Modelos locais de 7B e 14B sofrem de *Inverse Attention*. Ao colocar "NUNCA invente Grupo Nacional de Tecnologia", a probabilidade do token "Grupo Nacional de Tecnologia" ser ativado no espaço latente aumenta exponencialmente. O modelo alucina exatamente aquilo que foi proibido.
* **A Solução da Umi:** Retirar todas as proibições. Escrever apenas instruções positivas sobre quem a IA é e qual o contrato das ferramentas disponíveis. O controle de fluxo deve ser feito por schemas de tool-calling e permissões do backend.

### Erro 2: Prompt Bloat e a Falácia do FastPath
Tentamos resolver latências de 139 segundos criando um classificador artificial `_needs_tools()` que bifurca entre `Casual` e `Heavy`.
* **A Falha:** Heurísticas de texto ("se tiver 'quero', 'ajuda', etc.") falham constantemente em conversas reais, gerando comportamento bipolar (ora uma casca vazia, ora um dump de 2500 tokens).
* **A Solução da Umi:** Orçamento dinâmico de tokens com camadas protegidas vs. consultivas. O prompt base (Identidade + Pessoa) tem apenas ~250 tokens. Cartões de contexto (projetos, notas) só recebem cota de tokens se o ranqueador semântico/BM25 pontuar relevância com a mensagem do usuário. Uma saudação ("opa eai") tem score zero para projetos, resultando naturalmente em um prompt de 250 tokens que responde em < 1 segundo no CPU sem nenhum `if/else` no código.

### Erro 3: Invenção de "Golden Examples" Sintéticos vs. Consolidação Real
O plano em `docs/PLANO_BLINDAGEM_COGNITIVA_E_AUTO_AVALIACAO.md` previa um Juiz Sintético gerando conversas falsas para avaliar a IA em offline.
* **A Falha:** Dados sintéticos desconectados da rotina real geram overfitting e regras artificiais que quebram quando o usuário fala gírias ou muda de assunto.
* **A Solução da Umi (Dream Diário):** O sono da IA deve operar sobre **dados reais**. Toda noite, o processo em background lê as conversas que realmente aconteceram no dia, extrai fatos verificáveis ("Isaac prefere backend em FastAPI", "Isaac pausou o projeto X") e grava em formato append-only (`diario/YYYY/MM.jsonl`), atualizando o SQLite FTS5 de forma atômica.

### Erro 4: Falta de Rastreabilidade (O "Mistério da Alucinação")
Hoje no Menor v2, quando a IA diz algo estranho, não sabemos exatamente o que o modelo leu no instante da geração.
* **A Falha:** Debug reativo através de `print()` ou logs genéricos.
* **A Solução da Umi (Prompt Trace v2):** Gravar em tabela do SQLite um snapshot imutável antes de cada dispatch ao Ollama:
  1. Lista de arquivos e hashes carregados no turno.
  2. Proveniência de cada bloco de texto (de onde veio e quantos tokens custou).
  3. Payload bruto exato sanitizado.
  4. Resposta do modelo, chamadas de ferramenta e tempos de execução.

### Erro 5: Ausência de Identidade Canônica Desacoplada do LLM
No Menor v2, o assistente é quase um reflexo direto do modelo que estiver no Ollama.
* **A Falha:** Se você mudar de `qwen2.5:14b` para `deepseek-coder` ou `llama3`, o assistente perde tom de voz, memória relacional e consistência.
* **A Solução da Umi:** A identidade pertence ao **Núcleo**, não à Mente:
  * `SOUL.md`: Princípios imutáveis, valores, tom de voz durável.
  * `SELF.md`: Autobiografia viva e autopercepção em 1ª pessoa que evolui com o tempo.
  * O LLM é apenas um processador cognitivo substituível (como uma CPU executando um sistema operacional).

---

## 3. Plano de Ação para o Menor v2

1. **Fase 1: Limpeza Radical de Prompts e Arquitetura de Identidade**
   * Criar `data/identidade/SOUL.md` e `data/identidade/SELF.md`.
   * Purgar as 20 restrições negativas em CAPS de `src/agent/orchestrator.py`.
   * Substituir o dicionário estático `DEFAULT_BLOCKS` por leitura dinâmica das camadas canônicas.

2. **Fase 2: Motor de Orçamento de Contexto (Context Budget v2)**
   * Implementar contagem de tokens real (`tiktoken` ou estimativa por modelo).
   * Estabelecer Camadas Protegidas (< 350 tokens) e Cartões Consultivos sob demanda.
   * Eliminar o hack `_needs_tools()` e o FastPath forçado, deixando o orçamento selecionar o contexto.

3. **Fase 3: O Motor de "Dream" (Sono e Consolidação)**
   * Configurar a rotina noturna no `menor-missions.timer` (ex: 22h).
   * Ler os chats do dia, extrair fatos com recibos de evidência e persistir no SQLite FTS5.
   * Compactar turnos históricos quando a sessão ultrapassar 80% da janela de contexto.

4. **Fase 4: Observabilidade com Prompt Trace**
   * Criar a tabela `prompt_traces` no SQLite para auditoria imediata de latência e alucinações.

5. **Fase 5: Modernização do Cliente de Voz**
   * Integrar wake word local ONNX no `client/voice_assistant.py`.
   * Manter o stream de áudio em buffer de RAM, eliminando arquivos WAV intermediários em disco.
