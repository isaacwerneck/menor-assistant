# Chat C — observabilidade read-only V1

`ops.observability.build_snapshot` é um contrato puro, sem I/O ou endpoint. Recebe relatórios de `ops.doctor`, `ops.smoke`, verificações estruturais de recibos e contagens agregadas opcionais. Devolve apenas estados `ok`, `warning`, `critical` ou `unknown`, faixas de contagem e evidências categóricas. Ausência de evidência é `unknown`, nunca sucesso. O estado do Ollama vem da declaração de `/health`, não comprova inferência. Recibos estruturais não comprovam execução real.

## Handoff para Chat E

Integrar somente em endpoint privado com `auth.require_owner(request)` antes de coletar informações, `Cache-Control: no-store`, limitação de frequência e timeout. Responder 401/403 sem diagnóstico quando anônimo. Nunca publicar em `/health` ou renderizar dados de logs, prompts, IDs, paths, exceções ou tokens. O Chat E é dono do endpoint; este PR não altera `src/api` nem HTML. Contadores opcionais devem vir de coletores confiáveis; sem coleta o painel mostra `unknown`. `BoundedHistory` armazena só data UTC e estado em memória (máximo 24 registros), sem persistência.

## Verificação

`python3 -m unittest discover -s tests -p 'test_ops_observability.py' -v`

`python3 -m unittest discover -s tests -v`

`python3 -m flake8 ops tests --max-line-length=119`

Testes simulados não medem Ollama, Ubuntu/Intel ou segurança completa. O CI atual verifica `src tests` com flake8, mas não `ops`; lint local de `ops` é necessário. Não há deploy, restart, recuperação nem escrita em dados reais.