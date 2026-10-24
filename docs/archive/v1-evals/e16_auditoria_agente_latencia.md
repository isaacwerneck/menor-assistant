# E16 — Auditoria do harness, diagnóstico por fase e inferências redundantes

Data: 21/10/2026. Baseline: `82944fb9` / E15 com 272 mensagens reais
executadas pelo operador no Ubuntu. Este documento descreve as
melhorias preparadas **em branch separada** durante a execução das baterias.

## Achados de maior impacto

| Prioridade | Evidência no código | Correção E16 | Evidência necessária |
| --- | --- | --- | --- |
| Alta | `runner._understand` pode tentar outra chamada `conversation.reply` quando `intelligence.decide` falha após um timeout de 40s | Sem segunda inferência por padrão; comportamento anterior opt-in | Comparar número de chamadas/modelo e latência fim a fim, sem simular respostas |
| Alta | `_understand` pode fazer segunda chamada para resposta "Sim/OK" sem informação | Fallback transparente, mantém contexto e não alega execução | Repetir casos de respostas pobres nos dois modelos e revisar qualidade |
| Alta | `_advance` executava aprovação salva mesmo se `MENOR_AGENT_SCOPE` fosse alterado desde a proposta | Revalidar escopo e argumentos tipados ANTES de efeito | Testar escopo revogado, estado corrompido e aprovação legítima |
| Alta | Latência de contexto agrupada escondia busca semântica do Ollama e leitura FTS5 | Métricas separadas (semantic/lexical/project/review) | Diagnóstico real por modelo em horários comparáveis |
| Média | `_model_step` não enviava `keep_alive` explicitamente, diferindo do planejador | Respeitar mesmo `OLLAMA_KEEP_ALIVE` opt-in já usado no roteador | Medir recargas e RSS; não manter 14B desnecessariamente |
| Média | `conversation.reply` decidia orçamento por palavras de linguagem de programação | Aplicar `response_budget.output_budget(chat=True)` por extensão pedida | A/B de completude, tokens/s e truncamento |

## Por que isso importa no i7

- Em E12, 7B demorou ~7 t/s em planejamentos longos e até ~17 s
  para o prefill de 509 tokens sem cache. Uma consulta extra pode custar
  dezenas de segundos. **Não alegar ganho em tempo sem benchmark real**.
- A opção de revisão independente de plano permanece opt-in
  (`MENOR_PLAN_REVIEW_ENABLED=1`). Se ativada, adiciona outra chamada
  até 25 s e, se necessário, uma terceira para refazer o plano.
- A consulta semântica opcional `MENOR_EMBED_MODEL` pode disparar `/api/embed`,
  alterar residência dos modelos e consumir recursos. Contexto FTS local
  não precisa de outro modelo, mas também pode custar tempo de I/O.
- Retenção `OLLAMA_KEEP_ALIVE` reduz tempo de carregamento quando há
  memória suficiente, porém manter 7B + 14B simultaneamente consome RAM.
  Não confundir memória livre com throughput; medir carga e temperatura.

## Estrutura dos recibos: nenhuma mensagem privada

`agent_metrics` de resposta contém apenas:
- `semantic_retrieval_ms`, `lexical_retrieval_ms`, `project_context_ms`;
- `context_retrieval_ms`, `reasoner_wall_ms`, `review_wall_ms`;
- `review_status`, `fallback_reason`, `secondary_model_calls` quando aplicável;
- `tool_model_calls`, `tool_model_wall_ms` se houver loop de ferramentas;
- contadores/tokens/latência Ollama já existentes, sem dados brutos de mensagens.

O código da CI não invoca Ollama: valida simulações, escopos e
os formatos de saída. Os resultados E15 da CPU precisam ser
medidos separadamente. Essa instrumentação não cria tarefas ou modelo
novo e não altera a quantização.

## Três blocos de trabalho

1. **Auditar:** mapear `runner`, `intelligence`, `conversation`,
   `plan_review`, contexto, aprovações, tarefas, Lab, repositório.
   Consultar padrões públicos de harness, cache e agentes.
2. **Corrigir:** eliminar inferências de reparo automáticas por padrão,
   instrumentar buscas/contexto/revisões, revalidar ações aprovadas,
   alinhar keep-alive e orçamento de chat à intenção de extensão.
3. **Validar:** testes herméticos de falha, latência, escopo antigo,
   entradas corrompidas, operação permitida e orçamentos; CI completa,
   PR isolado. **Não fazer merge durante a bateria E15 em andamento.**

## Configurações

- `MENOR_SECONDARY_INFERENCE_ENABLED=0` (**padrão E16**): evita consulta
  secundária se o raciocinador já falhou, escolheu ferramenta inválida
  ou respondeu algo sem informação. Devolve resposta honesta e mantém
  o objetivo; não executa operação nem finge conclusão.
- `MENOR_SECONDARY_INFERENCE_ENABLED=1`: reativa tentativas antigas,
  explicitamente, para teste A/B caso a qualidade piore.
- `OLLAMA_KEEP_ALIVE`: mesmo valor para roteador, chat e loop; cuidado
  com RSS dos dois modelos residentes.
- `MENOR_PLAN_REVIEW_ENABLED=1`: controle anterior, independente desta
  atualização; revisão extra pode piorar latência mas corrigir planos.

## Próxima medição depois da E15

A E15 em andamento representa baseline inalterado em produção.
Conclua e preserve os relatórios antes do deploy de E16. Depois:
1. Selecione as mesmas 32 conversas de descoberta/organização no 7B.
2. Compare `reasoner_wall_ms`, buscas, números de inferências e qualidade
   humana; inclua turnos em que o modelo demora até timeout.
3. Repita com o 14B em execução sequencial, nunca simultânea na CPU.
4. Meça também tempo até resposta, p95, fração de cache, respostas
   insuficientes e falhas por cenário; não aceite velocidade com
   perda de contexto nem ferramentas falsas.

## Fontes primárias pesquisadas

- OpenAI Codex harness (19/08/2026):
  https://developers.openai.com/blog/codex-as-a-platform
- Codex agent loop e cache:
  https://openai.com/index/unrolling-the-codex-agent-loop/
- OpenAI, trace → eval → melhoria:
  https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop
- Anthropic, fluxos de agentes (05/03/2026):
  https://claude.com/resources/articles/common-workflow-patterns-for-ai-agents-and-when-to-use-them
- Ollama chat e keep_alive:
  https://github.com/ollama/ollama/blob/main/docs/api.md

## O que continua pendente no plano A–E

A redução de latência não torna 7B equivalente a um agente Codex.
Próximas fases exigem workspace de tarefas persistente, execução real
em sandbox, testes e correções com evidência, e avaliação de sucesso
end-to-end. Nenhuma afirmação de "aplicativo funcional" sem execução
real. Não usar regras por palavras para decidir intenção.

## Análise E15 offline depois dos testes

A ferramenta nova `ops/e15_report_analysis.py` lê os JSONs completos
**somente no diretório privado local**, escolhe o relatório mais recente
por bateria e modelo e imprime apenas contadores e tempos, sem perguntas,
respostas nem históricos. Não consulta Ollama, GitHub ou rede, nem edita
os relatórios.

```bash
cd ~/menor-assistant
python3 -m ops.e15_report_analysis
```

Para diretório alternativo:

```bash
python3 -m ops.e15_report_analysis --lab-dir /caminho/privado/do/lab
```

Saída: número de conversas estruturalmente completas por modelo,
turnos válidos/invalidos, verificações automáticas, mediana e p95 de
tempo, prefill e geração, tokens/s e comparação entre os dois modelos
para os mesmos turnos. Não classifica uma conversa como boa apenas por
ter gerado texto nem afirma ter executado uma ferramenta.

Se nenhum relatório E15 estiver pronto, retorna
`status: no_e15_reports`. Filtros por versão ainda são uma limitação:
se os dois modelos tiverem sido testados em revisões diferentes,
`revision_changed`/proveniência devem ser conferidos no relatório
original antes de fazer afirmações comparativas.
