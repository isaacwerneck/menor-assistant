# Gaveta de avaliações do Menor — comportamento atual (20/10/2026)

> Consulte também [catálogo das baterias](catalogo_baterias_v1.md),
> [resultados reais e erros](handoff/04_BATERIAS_E_DIAGNOSTICOS.md) e
> [comparativo v2](segundo_lote_qualidade_v2.md).
> Este laboratório **não executa ferramentas**, não treina pesos do Qwen e
> não demonstra, sozinho, autonomia de ponta a ponta.

## Execução autenticada

Na interface privada `/lab/view`, a **Gaveta de testes** permite listar as
baterias pré-instaladas (`lab/suites/*.json`), importar suítes privadas,
iniciar uma execução por vez, consultar progresso e baixar relatório completo.

- Bateria inicial: `lab/suites/diagnostico-inicial.json`.
- Baterias importadas: `~/menor-data/lab/suites/` (fora do Git).
- Relatório completo: `~/menor-data/lab/<run-id>.json`, apenas para proprietário autenticado.
- Resumo sem perguntas/respostas: `~/menor-data/lab/<run-id>.summary.json`.
- Máximo de 200 casos por bateria; execução em thread do processo FastAPI,
  sem fila persistente. **Reiniciar API interrompe uma bateria ativa**;
  não iniciar outra nem benchmark simultâneo.
- Cada caso usa `mode=direct` (Ollama cru, com `profile=baseline` por padrão
  ou `natural` para avaliação da voz) ou `mode=planner` (decisão JSON);
  nenhum dos dois executa ferramentas.
- `decision_validated` demonstra contrato/JSON válido, **não qualidade do plano**.

### Diagnóstico de inferência sem nova chamada ao modelo

O modo `planner` inclui `diagnostics.outcome`: `validated`, `timeout`,
`request_failed`, `invalid_json`, `invalid_response` ou `invalid_decision`
(estrutura/contrato rejeitado). `performance` preserva somente contagens e tempos
numéricos do Ollama, inclusive quando o texto JSON não pôde ser decodificado.
Timeout sem resposta não tem métricas inventadas.

`output_limited=true` indica `done_reason=length` reportado pelo Ollama;
`reply_truncated=true` indica o corte do trecho exibido no relatório. São
condições diferentes. A ausência de limite reportado não prova resposta completa.
O status continua compatível com relatórios anteriores; os sinalizadores devem
ser considerados na revisão humana.

O diagnóstico do planejador inclui hashes SHA-256 do prompt de sistema e schema,
limite de saída, temperatura e timeout efetivamente enviados. Esses hashes não
incluem a pergunta, histórico ou preferências e não substituem SHA do deploy,
digest do modelo, hardware e medição repetida. Nenhum texto bruto de exceção,
raciocínio ou credencial é copiado para o diagnóstico. Não há retry adicional.

### Avaliação automática, sem falsas notas

- `expected_contains`: todas as substrings devem ocorrer (teste sintático,
  não prova conteúdo correto).
- `expected_exact` com `grader=strict` (padrão): igualdade de texto sem
  diferenças de maiúsculas/espaços externos, **não** tolera ponto extra.
- `grader=boolean`: somente quando explicitamente marcado no JSON e o
  esperado é SIM ou NÃO. Aceita variação de acento/maiúscula/pontuação
  final simples, mas rejeita explicações e contradições.
- Sem critério automático: `automatic_pass=null` (revisar manualmente a
  `review_criteria`; **não** contabilizar como erro).
- `automatic_pass=false` pode indicar bug do avaliador e exige inspeção.
- A suite armazena `split` (`development/validation`) mas **nenhuma parte
  é cega** se os exemplos são usados para otimizar o modelo/prompt.

## Publicação opcional de resumo estatístico (sem prompts/respostas)

**Opt-in separado**, executado automaticamente depois de finalizar a bateria
quando `MENOR_LAB_REPORTS_PUBLISH=1` estiver configurada pelo operador.
Envia métricas agregadas à branch privada `lab-reports`, caminho
`lab/reports/<run-id>.json`. Usa token no servidor com acesso apropriado.
Comportamento do resumo é diferente do botão de publicação completa.
Publicação de resumos duplicados pode falhar; o relatório local permanece salvo.

```ini
MENOR_LAB_REPORTS_PUBLISH=1
MENOR_LAB_GITHUB_TOKEN=<token restrito, armazenado somente no Ubuntu>
```

## Publicação MANUAL de relatório completo no GitHub

O botão **Enviar ao GitHub**, ao lado de cada relatório local salvo, faz
`POST /lab/reports/{run_id}/publish` autenticado. Envia **o JSON completo**
(perguntas, respostas, histórico sintético e pontuações) para a branch
`lab-reports`, pasta `lab/reports/full/`, **apenas por clique do dono**.
Não cria PR, não faz merge na `main`, não dispara deploy por alteração da
`lab-reports`.

```ini
MENOR_LAB_REPORTS_ALLOW_FULL_PUSH=1
MENOR_LAB_GITHUB_TOKEN=<fine-grained PAT, Contents: Read and write no repo>
```

Usar permissão **Contents: Read and write** somente no repositório privado.
Guardar essas configurações em arquivo `.env` fora do Git, por exemplo
`~/.config/menor/lab.env`, carregado por um `EnvironmentFile` privado do
`menor-api.service`. Permissões de filesystem restritas. Não compartilhar
PAT, snapshots de variáveis, cookies, conversas privadas nem arquivos de
configuração em mensagens ou commits. Se o token já apareceu em screenshot,
revogar e criar novo.

**Idempotência desde PR #83:** se já existe um relatório idêntico no mesmo
caminho da branch, a API devolve o link sem regravar; se já existe um conteúdo
**diferente**, retorna conflito `409` sem sobrescrever. O PR #82 distinguiu
falhas sanitizadas de `422` do GitHub (validação), `401/403` (token/permissões)
e problemas de rede. Não confiar em `422` como prova isolada de duplicação.

**Privacidade:** GitHub privado não significa anonimização. Quem tem acesso
à branch `lab-reports` pode ler as respostas completas. Não publicar relatórios
com senhas, credenciais, mensagens privadas ou dados sensíveis. Este chat pode
ler relatórios pelo **conector GitHub** após a publicação; não precisa importar
o JSON manualmente se ele já estiver acessível na branch.

## Resultados conhecidos e próximos testes

- `20261020T022255Z-4f73ee58` (`triagem-16-v1`): 16 casos, 7 acertos
  automáticos, 2 falhas automáticas, 7 sem nota, 0 erros de inferência.
- Duas falhas automáticas têm origens diferentes: confusão sobre execução real
  de comando (modelo) e `Não.` versus `NÃO` (avaliador antigo, corrigido no v2).
- `segundo-lote-base-v2` vs `segundo-lote-naturalidade-v2`:
  24 cenários iguais sob perfis A/B para medir naturalidade, contexto, segurança,
  latência e planos. Ambos foram executados no Qwen real na rodada Codex de
  20/10: baseline `20261020T040826Z-f0556cec` e natural
  `20261020T113158Z-217c3e5e`. Ambos os relatórios foram consultados: 5 acertos
  em 6 casos automáticos e 18 sem nota em cada lote; 2 falhas técnicas no baseline
  e 3 no natural. Medianas dos casos diretos: 12,072 s e 11,915 s. Uma rodada,
  executada em horários distantes, não comprova melhoria nem regressão causal.
- Medição independente do Qwen em CPU: **10,24 tokens/s** de mediana. Não
  usar apenas tempo bruto sem olhar quantidade de tokens de resposta.

Limites e plano de análise: [handoff de testes](handoff/04_BATERIAS_E_DIAGNOSTICOS.md)
e [programa de avaliação](pesquisa_metodologia_evals.md).
