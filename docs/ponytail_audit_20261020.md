# Ponytail — primeira varredura de segurança e redundâncias

Data: 20/10/2026. Fonte: [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail),
revisão `09c434ab73ca43761c5d8b0c5d341926c2fba710`. Escopo esperado: um proprietário,
FastAPI + Ollama local no Ubuntu, um processo de API e workers systemd.

## Método e alcance

Inventário recursivo da `main` com 337 entradas; leitura de README, AGENTS,
CI, requirements, núcleo FastAPI, autenticação, planejamento/runner,
ferramentas, sandbox, skills, geração supervisionada, armazenamento e
scripts operacionais, além da estrutura de testes. Não foi uma revisão
manual linha a linha de todos os 337 caminhos; nem foi acessado o Ubuntu.

## Achados confirmados (sem tocar nas áreas das demais frentes)

1. **Revisão de código sem critérios compartilhados**
   (`src/agent/self_edit.py:_propose_with_model` e
   `src/agent/tool_builder.py:_generate`):
   cada fluxo usa um prompt próprio e nenhum consumia uma política
   reutilizável de simplicidade, testes e validação. **Corrigido:** ambos
   recebem agora a seção de qualidade da skill versionada, somente ao gerar
   código; permissões, sandbox e revisão humana permanecem.

2. **Contagem imprecisa de prompts repetidos**
   (`ops/lab_batch_audit.py:inspect`):
   um caso sem campo `question` aumenta `cases_executed`, mas não participa
   de `prompts`; `total - len(prompts)` pode contar esse caso como repetido
   mesmo que exista apenas uma execução. **Pendente para a frente C:**
   calcular repetições apenas entre perguntas/históricos elegíveis, com teste
   de entrada incompleta. Não altera os relatórios privados.

3. **Latência não finita aceita pelo analisador**
   (`ops/lab_eval_analysis.py:summarize`):
   `elapsed_seconds=float("nan")` satisfaz `elapsed >= 0`? Não;
   porém `float("inf")` satisfaz e entra em medianas, produzindo números
   não JSON-portáveis. **Pendente para a frente C:** validar com
   `math.isfinite` e cobrir entradas malformadas.

4. **Validação heurística do patch proposto**
   (`src/agent/self_edit.py:_validate_patch`):
   o filtro de fragmentos de texto não é um validador de operações Python;
   equivalentes sintáticos podem contorná-lo. O código proposto
   atualmente não é executado automaticamente e exige PR rascunho +
   revisão; **pendente para a frente A/B:** validar contrato e comportamento
   com sandbox adequado, sem interpretar o filtro textual como garantia.

## Instalação e aceitação

- Skill original e licença MIT copiadas sob `.agents/skills/`; sem dependências
  novas ou hooks Node de terceiros.
- `AGENTS.md` orienta agentes de programação do repositório a usar Ponytail
  por padrão. O Menor lê suas regras somente nos dois geradores supervisionados,
  sem promover `programming` a capacidade pronta.
- Testes locais/CI verificam arquivos, prompts e contrato. Inferência efetiva
  do Qwen e desempenho no Ubuntu exigem teste quando o serviço voltar.

**Não verificado:** acesso real à máquina, benchmark de CPU/Ollama, segurança
de todos os fluxos e revisão de cada função do repositório.
