# Chat C — Contrato privado de observabilidade V1 (19/10/2026)

## Entrega e limites

Este incremento propõe `ops/observability.py`, puramente **read-only** e
sem operações de I/O: uma função de serialização minimizada e histórico
limitado exclusivamente em memória. Não cria endpoint, cron, serviço, registro
persistente nem integração na interface. Não modifica `src/**`,
`src/api/templates/chat.html`, deploy ou workflows compartilhados.

A revisão de base confirmou `main` no commit
`58aeece42a65b641d6c63ea36ba954d2bbf7ee51`;
`ops.doctor`, `ops.smoke` e `ops.receipt_contract` existem e oferecem
observações incompletas, que **não provam funcionamento real do Ollama,
segurança geral da API ou execução de ferramentas**.

## Uso pelo backend (somente código confiável)

```python
from ops.observability import BoundedHistory, build_snapshot

history = BoundedHistory(max_entries=12)
snapshot = build_snapshot(
    doctor_report=None,   # eventual saída de ops.doctor.run_checks()
    smoke_report=None,    # eventual saída de ops.smoke.run_smoke()
    receipt_checks=(),    # lista de ops.doctor.Check, sem dados de recibo
    aggregates=None,      # opcional: contagens obtidas de fonte confiável
    history=history,
)
history.add(snapshot)
# Entregar APENAS snapshot a cliente autenticado, sob revisão do Chat E.
```

O modelo de dados JSON possui:
- `contract: "menor.ops.observability"`, `contract_version: 1`,
  `collected_at` UTC, `read_only: true` e `assurance:
  "partial_structural_observation"`.
- `status: ok|warning|critical|unknown`; qualquer coleta ausente ou
  pulada impede o agregado de aparecer como totalmente `ok`, salvo
  quando já existe uma falha/aviso mais grave.
- `components.api`, `ollama`, `service`, `disk`, `memory`,
  `api_contract`, `private_routes`, `receipts`, `queues`, `tasks`
  e `errors`. Cada componente tem `status` e `evidence` fixos.
- `history` lista no máximo 24 registros `{at, status}` em memória,
  sem IDs, mensagens, paths, recibos ou persistência.

As verificações do `doctor` têm nomes fixos. Os checks de rotas no `smoke`
são aceitos somente de relatório explicitamente anônimo (campo
`authenticated: false`), de leitura e completo para as rotas privadas
conhecidas. O agregado `private_routes=ok` NÃO significa que *todas*
as rotas da API são seguras. O status do Ollama deriva de `/health` e não
de uma geração real. Recibos são validados por formato, não por evidência
física de execução.

## Fontes agregadas opcionais e minimização

Apenas o backend confiável pode fornecer um dicionário com as seções:

```python
{
    "queues": {"pending": 0, "active": 0},
    "tasks": {"running": 0, "blocked": 0, "failed": 0},
    "errors": {"recent": 0},
}
```

O coletor desses contadores **não faz parte desta entrega**. Sem coletor
confiável os campos ficam `unknown`; **não** confundir ausência de telemetria
com fila vazia. Números aceitos são inteiros não negativos até 1 bilhão e
aparecem para o navegador apenas como faixas `0`, `1-9`, `10-49` e
`50+`, sem identificadores. Configuração atual de aviso:
`queues.pending >= 50`, `tasks.blocked > 0`, `tasks.failed > 0`,
`errors.recent > 0`. São heurísticas, não SLOs nem alarmes operacionais.

O contrato **nunca** replica `detail` de checks, parâmetros de tarefas,
`result` de recibos, nomes de arquivos, sessões, prompts, caminhos locais,
tokens, stack traces ou mensagens de exceção; novas chaves recebidas são
ignoradas. O histórico não armazena a entrada, apenas horário próprio e
status sanitizado. Evitar enviar snapshots para analytics, logs públicos
ou SaaS.

## Handoff explícito ao Chat E — SEM integração ainda

Para disponibilizar o painel, E deve combinar com C um endpoint privado
(por exemplo `GET /ops/observability`) **somente após revisão de código
em `src/api/**`**. A ordem da verificação tem de ser:

1. `auth.require_owner(request)` antes de qualquer probe, consulta a dados
   ou montagem do resultado. Testar ausência de cookie, cookie inválido e
   sessão válida em ASGI.
2. Ler apenas coletores internos predefinidos, com timeout e limites; nunca
   aceitar o `aggregates`, `doctor_report` ou `smoke_report` do navegador.
   Manter saída não pública e `Cache-Control: no-store`; evitar CORS aberto
   e incluir o endpoint na lista de rotas privadas monitoradas **em PR
   coordenado**. Não retornar erros brutos ao navegador.
3. Renderizar `unknown` como **não verificado** e não chamar o Ollama de
   produção para pintar indicador verde. Não criar controles de restart,
   rollback, escrita ou recuperação nessa tela.
4. Efetuar auditoria de privacidade de logs/proxies, endpoints e autenticação.
   Interface apenas consome snapshot; não recebe detalhamento de bancos.

Um simples import do módulo **não** protege endpoint: autenticação é obrigação
da camada API. `read_only=true` é uma descrição de contrato, não defesa
contra execução se um integrador violar o desenho.

## Testes e validações

```bash
python3 -m unittest discover -s tests -p 'test_ops_observability.py' -v
python3 -m unittest discover -s tests -v
python3 -m flake8 ops tests --max-line-length=119
```

`tests/test_ops_observability.py` cobre: dados ausentes, Ollama offline,
falha de rota privada, relatórios incompletos/duplicados, uso indevido de
sessão autenticada como prova de teste anônimo, dados e contagens malformadas,
injeção de segredos/caminhos em mensagens e campos extras, recibos planejados,
histórico limitado e ausência de leitura de dados no construtor.

CI é evidência de testes em simulação. Este PR **não mede** uptime,
latência, qualidade de geração, conflitos concorrentes, logs reais,
funcionamento no notebook Ubuntu/Intel, rollback, recuperação ou segurança
completa de rotas não listadas. Essas são etapas seguintes, com validação
isolada e aprovação para ações que tenham efeitos operacionais.

## Checklist de aceite

- [ ] Testes locais de privacidade e lint aprovados.
- [ ] CI completo do PR verde e merge-base atualizado em relação a `main`.
- [ ] Revisão de diff e conflitos; não alterar arquivos de outras frentes.
- [ ] Handoff ao Chat D após merge e ao Chat E antes de integração visual.
- [ ] Testar no notebook autorizado separadamente (não executado neste PR).
