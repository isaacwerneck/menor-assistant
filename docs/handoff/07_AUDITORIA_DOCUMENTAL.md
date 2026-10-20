# Auditoria dos documentos — snapshot da migração para Codex

**Data:** 20/10/2026. **Base auditada:** `main` em `826b3b5` antes deste PR. Foram inventariados e lidos, ao menos por seções, **58 arquivos Markdown versionados**; nenhum foi excluído ou movido. Esta auditoria distingue documentação histórica de instruções operacionais atuais.

## Achados: inconsistências e decisão

| Documento | Problema de atualidade observado | Tratamento neste handoff |
|---|---|---|
| `README.md` | A abertura descrevia memória/ferramentas como apenas roadmap apesar de módulos já integrados | Atualizar abertura e apontar o índice do Codex; preservar orientação histórica útil |
| `docs/roadmap.md` | Checklist datado descrevia escrita/leitura de Markdown e pastas de memória como não implementadas | Atualizar status das partes comprovadas no código e indicar validações pendentes |
| `docs/hardware_requisitos.md` | Listava só modelos candidatos; faltavam CPU/GPU/Ollama medidos e resultados de velocidade | Adicionar referência canônica ao diagnóstico quantitativo real |
| `docs/laboratorio_baterias.md` | Dizia que só `expected_contains` recebia nota; afirmava que duplicação era sempre rejeitada e orientava baixar JSON para este chat | Corrigir contrato `expected_exact`/`boolean`, publicação manual idempotente e conector GitHub |
| `docs/catalogo_baterias_v1.md` | Não listava o segundo lote A/B v2 de 24 casos | Acrescentar os dois IDs e política de comparação |
| `docs/arquitetura_codigo.md` | Cabeçalho dizia que loop agêntico inteiro era planejado, apesar do `runner` atual | Qualificar: desenho antigo é visão evolutiva; apontar módulos implementados |
| `docs/integracao_documental_chat_b.md` | Texto antigo afirmava que não havia anexos documentais na interface principal | Acrescentar observação de substituição funcional no PR #72 |
| `docs/plano_integrado_a_e.md` e planos da raiz | Snapshot de 19/10 ainda dizia validação de inferência no notebook totalmente ausente | Preservar como histórico; apontar o relatório/medições de 20/10 sem sobrepor a visão |
| `docs/guia_servidor_domestico.md` / `docs/arquitetura.md` | Diagramas ilustram Docker/Nginx/Whisper/TTS e até nome Jarvis como desenho desejado, não necessariamente deploy real | Anotar explicitamente que a operação comprovada é Ubuntu + systemd + Ollama; não renomear projeto |
| `docs/contrato_delegacao_chat_b.md` e contratos de C | Documentos são do estado **do seu próprio incremento** e alguns dizem que integração ainda não ocorreu | **Manter históricos**; leitor deve consultar `03_FRENTES_A_B_C_D_E.md` e código atual |
| `docs/chat_d_conversation_regression_matrix_v2.md` | Baseline `792529c9` é antigo | Preservar como matriz histórica de regressões, não SHA atual de produção |
| `docs/chat_e_diagnosticos.md` | Documento anterior fala de transporte remoto como futuro | Preservar contexto do PR; uso de túnel temporário em 20/10 documentado à parte, sem afirmar Access permanente |
| `docs/pesquisa_metodologia_evals.md` e `docs/programa-avaliacao-melhorias.md` | Sobreposição de metodologia de avaliação | Preservar ambas como estudos, tornar [04](04_BATERIAS_E_DIAGNOSTICOS.md) índice operacional atual |
| `PLANO.md` e `PLANO_REFINAMENTO.md` | Seções numeradas antigas e fases planejadas convivem com entregas posteriores; fonte histórica não é checklist de release | Manter integralmente decisões; colocar indicação de handoff atual no topo |

**Não foi identificada razão para apagar documentos históricos** — informações de segurança, decisões visuais e contratos ainda são úteis. Erros datados devem ser rotulados com contexto, não apagados para fabricar progresso. A auditoria é editorial; não prova que cada contrato descrito ainda corresponde perfeitamente ao código sem testes específicos.

## Hierarquia de fontes (evita contradição)

1. **Comportamento real**: execução/recibos/verificação no Ubuntu, testes e relatórios versionados.
2. **Código da `main` atualizada**, testes e contratos ativos.
3. **Este handoff 20/10/2026**: agregação de estado, diagnóstico e prioridades.
4. **Roadmaps e documentos antigos**: histórico de intenção e decisões, com ressalvas.
5. **Exemplos/simulações**: não comprovam execução ou qualidade no servidor.

Documentos criados neste PR vão em `docs/handoff/` e **não foram incluídos** nos 58 já auditados. O repositório pode ganhar novos documentos após a migração; atualizar manifesto quando isso acontecer.

## Índice completo dos 58 Markdown existentes na baseline

### Raiz — objetivos/planos legados (4)

- [`PLANO.md`](../../PLANO.md)
- [`PLANO_INTELLIGENCE_ENGINE.md`](../../PLANO_INTELLIGENCE_ENGINE.md)
- [`PLANO_REFINAMENTO.md`](../../PLANO_REFINAMENTO.md)
- [`README.md`](../../README.md)

### Planejamento e arquitetura (10)

- [`docs/arquitetura.md`](../../docs/arquitetura.md)
- [`docs/arquitetura_codigo.md`](../../docs/arquitetura_codigo.md)
- [`docs/arquitetura_multiagente.md`](../../docs/arquitetura_multiagente.md)
- [`docs/ciclo_capacidades.md`](../../docs/ciclo_capacidades.md)
- [`docs/guia_servidor_domestico.md`](../../docs/guia_servidor_domestico.md)
- [`docs/hardware_requisitos.md`](../../docs/hardware_requisitos.md)
- [`docs/plano_integrado_a_e.md`](../../docs/plano_integrado_a_e.md)
- [`docs/roadmap.md`](../../docs/roadmap.md)
- [`docs/setup_linux.md`](../../docs/setup_linux.md)
- [`docs/upgrade_cognitivo_v2.md`](../../docs/upgrade_cognitivo_v2.md)

### Frente A — inteligência, memória e contexto (8)

- [`docs/busca_conhecimentos.md`](../../docs/busca_conhecimentos.md)
- [`docs/chat_a_benchmark_real.md`](../../docs/chat_a_benchmark_real.md)
- [`docs/chat_a_objetivos_contextuais.md`](../../docs/chat_a_objetivos_contextuais.md)
- [`docs/chat_a_recuperacao_segura.md`](../../docs/chat_a_recuperacao_segura.md)
- [`docs/chat_a_revisao_de_planos.md`](../../docs/chat_a_revisao_de_planos.md)
- [`docs/memoria_v03.md`](../../docs/memoria_v03.md)
- [`docs/projetos_contextuais.md`](../../docs/projetos_contextuais.md)
- [`docs/roteamento_contextual.md`](../../docs/roteamento_contextual.md)

### Frente B — ferramentas e percepção (10)

- [`docs/analise_arquivos_chat_b.md`](../../docs/analise_arquivos_chat_b.md)
- [`docs/auditoria_sprites_chat_b.md`](../../docs/auditoria_sprites_chat_b.md)
- [`docs/chat_b_ocr_context_api_v3.md`](../../docs/chat_b_ocr_context_api_v3.md)
- [`docs/chat_b_ocr_context_security_v2.md`](../../docs/chat_b_ocr_context_security_v2.md)
- [`docs/contexto_arquivos_chat_b.md`](../../docs/contexto_arquivos_chat_b.md)
- [`docs/contrato_delegacao_chat_b.md`](../../docs/contrato_delegacao_chat_b.md)
- [`docs/imagens_autoedicao_v06.md`](../../docs/imagens_autoedicao_v06.md)
- [`docs/integracao_documental_chat_b.md`](../../docs/integracao_documental_chat_b.md)
- [`docs/ocr_local_chat_b.md`](../../docs/ocr_local_chat_b.md)
- [`docs/subagente_visao_chat_b.md`](../../docs/subagente_visao_chat_b.md)

### Frente C — confiabilidade e observabilidade (10)

- [`docs/chat_c_execution_evidence_v2.md`](../../docs/chat_c_execution_evidence_v2.md)
- [`docs/chat_c_execution_integrity_v1.md`](../../docs/chat_c_execution_integrity_v1.md)
- [`docs/chat_c_execution_transitions_v1.md`](../../docs/chat_c_execution_transitions_v1.md)
- [`docs/chat_c_monitor_latencia.md`](../../docs/chat_c_monitor_latencia.md)
- [`docs/chat_c_recovery_decision_v1.md`](../../docs/chat_c_recovery_decision_v1.md)
- [`docs/contrato_observabilidade_chat_c.md`](../../docs/contrato_observabilidade_chat_c.md)
- [`docs/contratos_api_chat_c.md`](../../docs/contratos_api_chat_c.md)
- [`docs/contratos_recibos_chat_c.md`](../../docs/contratos_recibos_chat_c.md)
- [`docs/diagnostico_operacional_chat_c.md`](../../docs/diagnostico_operacional_chat_c.md)
- [`docs/observabilidade_chat_c.md`](../../docs/observabilidade_chat_c.md)

### Frente D — conversa e autorização (3)

- [`docs/chat_d_cancelamento_proveniencia.md`](../../docs/chat_d_cancelamento_proveniencia.md)
- [`docs/chat_d_conversation_regression_matrix_v2.md`](../../docs/chat_d_conversation_regression_matrix_v2.md)
- [`docs/conversa_imagens_chat_d.md`](../../docs/conversa_imagens_chat_d.md)

### Frente E — interface (6)

- [`docs/chat_e_anexo_privado.md`](../../docs/chat_e_anexo_privado.md)
- [`docs/chat_e_arquivos.md`](../../docs/chat_e_arquivos.md)
- [`docs/chat_e_diagnosticos.md`](../../docs/chat_e_diagnosticos.md)
- [`docs/chat_e_direcao_visual.md`](../../docs/chat_e_direcao_visual.md)
- [`docs/chat_e_objetivos.md`](../../docs/chat_e_objetivos.md)
- [`docs/chat_e_sistema.md`](../../docs/chat_e_sistema.md)

### Laboratório, remoto e metodologia (7)

- [`docs/acesso_remoto_cloudflare_netlify.md`](../../docs/acesso_remoto_cloudflare_netlify.md)
- [`docs/api_avaliacao_remota.md`](../../docs/api_avaliacao_remota.md)
- [`docs/catalogo_baterias_v1.md`](../../docs/catalogo_baterias_v1.md)
- [`docs/laboratorio_baterias.md`](../../docs/laboratorio_baterias.md)
- [`docs/pesquisa_metodologia_evals.md`](../../docs/pesquisa_metodologia_evals.md)
- [`docs/programa-avaliacao-melhorias.md`](../../docs/programa-avaliacao-melhorias.md)
- [`docs/segundo_lote_qualidade_v2.md`](../../docs/segundo_lote_qualidade_v2.md)

**Total enumerado:** 58 documentos; grupos são mutuamente exclusivos neste inventário, não um organograma rígido de responsabilidade.

## Rotina para manter a documentação confiável

- Cada PR que mudar contrato, endpoint ou estado de implantação deve atualizar **o documento operacional correspondente**, sem afirmar o trabalho futuro como pronto.
- Preservar data e SHA do baseline nos relatórios; não deixar textos `neste PR` sem contexto passarem como data atual.
- Links para `docs/handoff/*` e `AGENTS.md` devem continuar acessíveis; se renomear arquivo, ajustar índices.
- Não versionar artefatos pessoais, logs, tokens, modelos baixados, relatórios completos ou evidências sensíveis na `main`.
- Codex deve reauditar **código + CI + configuração do Ubuntu** antes de fechar marcos e atualizar porcentagem global.
