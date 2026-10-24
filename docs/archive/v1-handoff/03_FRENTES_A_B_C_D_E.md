# Estado das cinco frentes de trabalho A, B, C, D e E

**Consolidado em 20/10/2026.** Frentes são responsabilidades históricas de trabalho paralelo, **não cinco subagentes comprovadamente autônomos e ativos no servidor**. O projeto usa um só repositório privado, `main` e PRs de branches independentes; evitar que o Codex reimplemente recursos já integrados.

## Mapa executivo

| Frente | Missão | Código/artefatos relevantes | Status honesto |
|---|---|---|---|
| **A** | Cérebro: interpretar objetivos, contexto, memória, metas, planejamento e agente programador supervisionado | `src/agent/intelligence.py`, `runner.py`, `goal_context.py`, `context_engine.py`, `plan_review.py`, `self_edit.py` | Núcleo integrado e testado por CI; execução agêntica geral, memória longa e autocorreção confiáveis **ainda incompletas** |
| **B** | Ferramentas e subagentes: documentos, visão, imagens, áudio, pesquisa e artefatos | `src/tools/`, `src/tools/file_analysis/`, `src/agent/delegation.py` | Contratos e integrações parciais; runtimes opcionais e fidelidade multimodal precisam validação real |
| **C** | Confiabilidade: diagnósticos, CI, recibos, auditoria, benchmark e recuperação | `ops/`, `tests/test_ops_*`, `src/api/private_diagnostics.py` | Boa base de testes e monitoração; evidência de operação real e recuperação/rollback end-to-end incompletas |
| **D** | Diálogo/execução supervisionada: continuidade, aprovações, cancelamento, isolamento e UX operacional | `src/agent/runner.py`, `src/api/templates/chat.html`, testes conversacionais | Casos/regressões implementados; precisa prova em conversas reais longas e navegação sob carga |
| **E** | Experiência PC/iPhone: design Quiet Intelligence, anexos, projetos, estado do servidor e acesso privado | `src/api/templates/`, `src/api/workspace*.py`, `src/api/system_*`, `remote_lab.py` | Várias páginas e endpoints integrados; aceitar mobile/desktop e endurecer operação remota |

## A — Arquiteto de inteligência

**Integrado, com evidência de PR:** #29 (revisor opcional de planos), #31 (recuperação conservadora), #38 (bench de raciocínio), #43 (validação de ferramentas), #51/#55 (evidência/artefatos), #67 (interpretação contextual), #68 (contexto de projeto e memória), #74 (ajustes pós-avaliação), #84 (voz natural e restrições básicas).

**O que existe:** `intelligence.decide` gera JSON tipado com `answer/clarify/plan/act/research/continue/inspect_result`; histórico e memória relevantes entram com limite; `runner` integra estados de objetivos, catálogo de tools e gate de permissão. Plano não é execução e ação de escrita exige autorização adequada; revisão adicional de plano permanece opt-in para conter latência. Preferências/exemplos aprovados orientam o comportamento sem retreinar pesos.

**Faltando:** comprovar compreensão/correções do proprietário em cenários novos e conversas de longa duração; objetivos duráveis e recuperação sob perda real; agente programador completo, seguro, autônomo sob supervisão e capaz de testar trabalho real; memória semântica fundamentada e isolamento cruzado auditado no servidor; consistência do planejamento. A triagem real revelou erro conceitual grave sobre redigir vs executar comando.

## B — Ferramentas, multimodalidade e subagentes

**PRs de referência:** #26 (extratores PDF/Word/Excel), #27 (consultas documentais UI), #34/#44/#50/#57 (OCR opt-in e proveniência), #39 (ponte `files.context`/`vision.inspect`), #69 (contratos de ferramentas documentais/visuais no agente).

**O que existe:** `src/tools/file_analysis/` com parsers, contexto/citações e API privada; OCR de PDF digitalizado explicitamente solicitado, com Poppler/Tesseract quando instalados; contrato de visão opt-in; geração de imagens com runner e recibos sob capacidade e autorização. Ferramenta registrada/código presente **não garante** modelo de visão, OpenVINO ou transcrição instalados/funcionando.

**Faltando:** teste real de PDFs grandes e digitalizados, DOCX/XLSX variados, qualidade de visão sem inventar cena, edição fiel de imagem/sprites, transcrição/voz bidirecional e pesquisa web com evidência; sandbox robusto de arquivos/rede e subagentes especializados com revisão de resultado. Não confundir Gerador de imagem com Leitor de imagem.

## C — Confiabilidade, segurança operacional e avaliação

**PRs de referência:** #24 (doctor), #30/#33 (smoke/contratos), #37 (observabilidade read-only), #45/#47/#52/#58 (recuperação/evidência estrutural), #70 (monitor e benchmark), #75–#84 (Lab API, baterias, publicação e avaliação/latência).

**O que existe:** suite Python/Node/Bash em Actions, auditoria estrutural de recibos/transições e replays conservadores, `menor monitor`, `ops/model_latency.py`, `ops/ollama_hardware.py`, diagnóstico privado e Menor Lab de inferência. PR #84 teve **611 testes Python** aprovados (7 skipped); não é certificação de qualidade real.

**Faltando:** harness end-to-end com ferramenta simulada/real isolada, avaliação cega, repetição e A/B no hardware, backup+restore validado, análise de crashes/temperatura/concurrency, observabilidade persistente privada e rollback testado. CPU Qwen medido a 10,24 tokens/s; GPU integrada ainda não comprovada em uso.

## D — Conversa, autorização e ações visíveis

**PRs de referência:** #32 (continuidade do fluxo de imagens), #40/#41/#42 (regressões de conversa/recusa), #49/#53/#56 (isolamento e autorização), #71 (cancelamento e proveniência); #84 melhora orientação de voz textual.

**O que existe:** estado de tarefas/conversas separado, cancelamento de apresentação sem falsamente cancelar efeito já realizado, aprovações tipadas, recibos e etapas em UI. Há matriz de testes `docs/chat_d_conversation_regression_matrix_v2.md`.

**Faltando:** validar com usuário duas sessões/navegadores e conversas longas, concorrência, regeneração, respostas tardias, retomada e consistência de tom. Não concluir que a IA fala naturalmente apenas porque recebeu um prompt novo.

## E — UX PC/iPhone, Cloudflare e interface privada

**PRs de referência:** #35 (direção Quiet Intelligence, 8 telas), #46/#54/#60/#61 (workspaces de arquivos/objetivos/sistema e diagnósticos), #72 (anexos privados no chat principal), #73 (Cloudflare + Lab), #76/#77 (baterias e publicação).

**O que existe:** chat principal mobile/desktop, seleção/anexo de arquivos, páginas `/files/view`, `/workspace/objectives`, `/workspace/system`, `/lab/view`; acesso remoto com Cloudflare Tunnel foi usado pelo proprietário, e a API fica no Ubuntu. Netlify é **opcional** e somente página estática, não proxy de chat.

**Faltando:** teste formal de acessibilidade, mobile/desktop em dispositivos reais, autenticação de borda/estabilidade do túnel, upload e gestão de arquivos entre conversas, progresso de ferramentas com evidências e validação contínua da experiência. Não registrar a URL `trycloudflare.com` temporária como endpoint estável.

## Fronteiras entre frentes e próximas entregas

- **A↔B:** A interpreta intenção e escolhe *contratos de ferramentas*; B implementa leitores/geradores, provenance e status. LLM não pode inventar permissão de B.
- **B↔C:** todos artefatos e tools precisam de recibos verificáveis; verificação estrutural C não é prova semântica do conteúdo B.
- **A↔C:** medir raciocinador em hardware Qwen real, timeouts e impacto de segundo julgamento; não multiplicar chamadas sem medir.
- **D↔E:** E detém visual e arquivos HTML/CSS; D detém coerência de turnos, provas de ação e cancelamento. Coordenação reduz conflitos.
- **Todas:** branch isolada, revisão de escopo, CI obrigatória verde, PR e sem alteração destrutiva/sensível não autorizada.

## Status de issues GitHub em 20/10/2026

- [#63](https://github.com/isaacwerneck/menor-assistant/issues/63): **aberta**, troca de conversa durante geração e lentidão no Ubuntu. Há código relacionado integrado, mas issue não encerrada/teste de aceite incompleto.
- [#64](https://github.com/isaacwerneck/menor-assistant/issues/64): **aberta**, CLI/monitoramento; `menor monitor` foi integrado, porém o aceite completo da issue ainda não foi reconciliado.
- [#66](https://github.com/isaacwerneck/menor-assistant/issues/66): **aberta**, repetição de contexto e capacidades não verificadas. Melhorias parciais existem; validar em casos reais.
- [#65](https://github.com/isaacwerneck/menor-assistant/issues/65): **fechada**, planejar melhoria não deve ativar autoedição.
- Antes de alterar status, conferir critérios e evidências; **não fechar issues automaticamente** só porque um PR menciona o assunto.

## PRs de integração mais recentes

`#67` → evolução cognitiva; `#68–#72` → entregas A–E; `#73–#74` → remoto e correções de contexto; `#75–#79` → API/Lab/baterias e correções; `#80–#81` → 192 avaliações e metodologia; `#82–#83` → erros 422, publicação idempotente sem sobrescrita; `#84` → voz natural, avaliadores, diagnósticos e segundo lote. Todos constavam **merged** na consulta ao GitHub em 20/10/2026. Na primeira migração, reconsultar estados reais.
