# Objetivo principal, progresso e definição de concluído

**Data da avaliação:** 20/10/2026. **Fonte:** roadmap A–E, código/CI do repositório e três relatórios reais do Menor Lab; avaliação humana do proprietário.

## Objetivo principal do proprietário

Transformar o Menor, atualmente um sistema de IA rodando localmente no notebook Ubuntu, num **assistente pessoal geral com comportamento natural, memória robusta, ferramentas reais e progressiva autonomia supervisionada**, próximo em **experiência pretendida** a um ChatGPT com capacidades de construção, programação e execução tipo Codex.

Não é um chatbot com comandos fixos ou respostas protocolares. O sistema deve:

- Interpretar qualquer solicitação em português natural, inclusive informal, acompanhar o contexto entre mensagens/projetos e lembrar informações relevantes sem confundir assuntos ou inventar memórias.
- Conversar de forma fluida, inteligente, assertiva e ajustada à complexidade; aprofundar quando faz sentido, sem enrolar ou soar como um formulário.
- Pesquisar, verificar fontes, estudar, interpretar arquivos (PDF/Office/imagens/áudio), criar documentos, artes, ferramentas e código, sem declarar capacidades ausentes como concluídas.
- Planejar tarefas e **executar somente quando houver ferramenta disponível, permissão válida e contrato seguro**, guardando recibos e verificando o resultado real; falhas e interrupções não podem gerar replay perigoso.
- Resolver problemas de ponta a ponta: investigar → planejar → obter aprovação → executar em ambiente isolado → testar → apresentar evidências → revisar; produzir PRs e melhorias supervisionadas no próprio Menor.
- Operar no hardware doméstico, com CPU, RAM e GPU aproveitados de modo eficiente e medido, acessível por PC/iPhone via interface privada.
- Melhorar progressivamente **por avaliação reproduzível e feedback aprovado**; fine-tuning é eventual, não automático nem sinônimo de testes.

### Limites e escolhas que não podem ser perdidos

O LLM **sugere/entende**, o Python confiável **valida/autorizada/executa** e o usuário **controla permissões sensíveis**. Texto de documento, histórico, página web ou saída do modelo não é autorização. Nunca tratar `planned`, `decision_validated`, geração de texto ou HTTP 202 como comprovação de ação final. Não alegar visualização de imagem sem visão real. Evitar roteamento por listas de palavras como substituto para entendimento contextual. Manter o desenho **Quiet Intelligence**, grafite + roxo suave, escolhido pelo proprietário; não reiniciar seleção visual. Preferência por incrementos substanciais, CI completa e rastros auditáveis.

## Quanto falta?

**Estimativa de progresso global da visão integral: aproximadamente 60%, com confiança baixa.** É uma **estimativa gerencial subjetiva**, não uma métrica de benchmark ou medição quantitativa de capacidade. Versões anteriores citaram ~48% em 19/10 antes dos PRs #67–#84. O salto indica novas peças técnicas, **não** que 60% das tarefas reais já funcionem de ponta a ponta.

| Frente | Maturidade *indicativa* no escopo da frente | Evidências / principais faltas |
|---|---:|---|
| A — interpretação/contexto/memória/autonomia | ~60% | Motor contextual JSON, metas e revisão; faltam autonomia durável, memória demonstrada e agente programador robusto |
| B — ferramentas e subagentes | ~55% | Contratos PDF/Office/visão/OCR e ponte; faltam runtimes, ferramentas ponta a ponta e multimodalidades validadas |
| C — confiabilidade, avaliações e operações | ~65% | CI, recibos estruturais, diagnósticos, 192+24 cenários; faltam rollback ensaiado, telemetria e harness real |
| D — conversa/UX operacional | ~60% | Cancelamento/isolamento/recibos e voz textual v2; falta prova de qualidade de conversas longas e consistência |
| E — experiência PC/iPhone/integrações | ~70% | UI, workspaces, anexos, diagnósticos, Cloudflare/Lab; falta teste de aceitação amplo, robustez mobile/acesso |

**Não somar essas porcentagens para certificar conclusão.** Os esforços têm pesos e dependências diferentes, e há áreas de risco (segurança/execução) cuja ausência impede declarar o sistema concluído, independentemente de média.

## Marcos já entregues e verificados como código

- Fundamentos: FastAPI, Ollama, interface web, autenticação, runtime de projetos/memória, sistema de ferramentas tipadas, estados de objetivos e aprovação.
- Frente A: `src/agent/intelligence.py`, `runner.py`, `context_engine.py`, `goal_context.py`, `plan_review.py`, `plan_constraints.py`, `voice.py`, `feedback.py`, `tasks.py`.
- Frente B: serviços de análise de arquivos, contexto fundamentado, OCR opt-in, ponte de visão; artefatos de imagem com recibos e verificação limitada.
- Frente C: `ops/doctor.py`, `ops/monitor.py`, `ops/model_latency.py`, `ops/ollama_hardware.py`, `ops/eval_compare.py`, contratos de evidência e CI.
- Frente D: cancelamento de UI, isolamento de chats, recuperações supervisionadas e respostas com melhor orientação conversacional.
- Frente E: identidade visual Quiet Intelligence, interfaces de arquivos/objetivos/sistema e Menor Lab privado.
- Laboratório: 16 baterias temáticas com 12 casos cada (192 casos originais), triagem de 16, execução agregada de 192, dois lotes A/B de 24 **mesmos** casos (mais 24 prompts únicos); relatórios privados com publicação manual para GitHub.

**Entrega no repositório não equivale a teste real no Ubuntu.** Alguns componentes opcionais podem não estar instalados ou configurados.

## O que precisa acontecer para afirmar 100%

1. **Qualidade conversacional comprovada** por avaliação humana + inédita, sem falhas graves de contexto, alucinação operacional e respostas robóticas.
2. **Memória e projetos recuperados realmente** em conversas e reinícios isolados, com privacidade e proveniência.
3. **Ferramentas end-to-end** para tarefas úteis de arquivo, visão, documentos, programação, pesquisa e criação, em sandbox, com entradas reais, qualidade e recibos; áudio/voz bidirecional implementados quando aprovados.
4. **Agente programador supervisionado** que reproduz issues, produz patches em worktree, testa, revisa e prepara PR com segurança; sem merges ou deploys arbitrários.
5. **Missões longas/reinício/concorrência** com retomada segura e sem efeitos duplicados, dados privados e permissões isoladas.
6. **Confiabilidade operacional** com recuperação após falha, backup/restore testado, observabilidade, latência/p95 aceitável e métricas de CPU/GPU medidas em ambiente real.
7. **Validação independente**: benchmarks isolados e testes de conclusão real, suites protegidas contra contaminação, repetição A/B e regressão integral verde.
8. **Experiência completa** aprovada no PC e iPhone, acesso remoto protegido, sem vazamento de segredos e sem afirmações falsas de execução.

Se um desses itens críticos não estiver comprovado, o progresso continua parcial.

## Critério de decisão para melhorias

Sem confundir prompt com capacidade: primeiro medir, classificar falhas (prompt/contexto, modelo, parser, ferramenta, autorização, CPU, rede, armazenamento, UI), formular hipótese, implementar mudança isolada, rodar CI e repetir em conjunto de desenvolvimento e validação separado. **Uma bateria não treina os pesos do Qwen.**
