# Rodada v5 — auditoria de 360 respostas e qualidade/latência do Menor

**Referência auditada:** branch privada `lab-reports`, relatórios com prefixo
`20261020T162713Z` (15 relatórios; contém bateria agregada de 192 casos).
**Base de código:** `main` em `3687210b` (PR #96).
**Ambiente esperado:** Ubuntu, i7-1185G7, 32 GB RAM, Intel Iris Xe;
Qwen 2.5 Coder 7B com inferência CPU. Não houve acesso remoto ao notebook
nem alteração em modelos/drivers/tokens nesta rodada.

## Resultado reproduzível antes das mudanças

- **15 relatórios, 360 execuções**, **204 pares pergunta/histórico distintos**.
  A bateria agregada de 192 casos reproduz questões das baterias temáticas.
  Portanto **não são 360 exemplos independentes**.
- **142 passes**, **36 falhas automáticas**, **182 sem nota**. Os passes
  automáticos são testes de gabarito/formato, não abrangem qualidade de todos
  os planos. Os 182 requerem revisão manual, não são acertos nem erros.
- **339 respostas com status completado** (`answered` ou `decision_validated`)
  e **21 falhas técnicas** (14 `inference_failed`, 7 `no_valid_decision`).
- Das **301 execuções em modo direct**, mediana total **3,13 s**,
  mediana prefill **1,24 s**, geração **1,48 s**. Em 48 casos o tempo foi
  acima de 30 s, normalmente por respostas extensas.
- Das **59 execuções em modo planner**, mediana total **28,51 s**,
  prefill **1,79 s**, geração **25,46 s**; 24 casos acima de 30 s.
  A mediana de cada subcomponente usa apenas casos com métrica disponível;
  não deve ser somada para estimar a mediana total.
- **25 respostas foram marcadas `output_limited`** naqueles relatórios.
  Timeouts do Ollama e decisões com JSON inválido também demandam investigação.
- A bateria de matemática `matematica-validacao-v2` registrou **7/12**
  acertos e 5 erros reais: duração, probabilidade, juros (2), média.
  Não confundir esses erros com as rejeições estritas de formato em
  `memoria-contexto-curto` (`relatórios`/ `relatorios`, sete/7).
- Segurança preocupante no modelo direto: obedeceu instruções citadas como
  dados, interpretou log manipulado como prova, confundiu a escrita de um
  comando com execução. Algumas respostas incorretas sobre GPU e CPU
  mostraram que o modelo não deve tirar conclusões apenas de `lspci`,
  `ollama ps` ou um percentual isolado.

**Conclusão operacional:** o custo de geração domina o modo planner nesse
lote. Reduzir somente o prefill não elimina a lentidão. É preciso comparar
**p50/p95, geração, tokens e acertos simultaneamente**. O Qwen pode ficar
mais rápido às custas de qualidade; não aceitar tal regressão.

## Implementações propostas

1. `src/agent/response_budget.py`: limite de tokens proporcional a
   **restrições de formato explicitadas no pedido atual**. Se o pedido pede
   uma palavra, número ou sim/não, reservar poucos tokens; em resposta
   detalhada, manter orçamento maior. `src/api/main.py` adota esse limite
   no fallback conversacional, inclusive streaming. *Não* modifica executor,
   permissões nem configuração do modelo.
2. `src/agent/voice.py`: `LAB_ASSISTANT_VOICE`, estilo mais direto, com
   distinção de dados não confiáveis, recibos, evidências e cautela em
   operações matemáticas. É um **perfil experimental**, não uma prova de
   que o modelo aprendeu ou de que recusará todas as injeções de prompt.
3. `src/api/remote_lab.py`: novo `profile=assistant` com teto de geração
   adaptativo e métricas do orçamento. **`baseline` e `natural` antigos
   continuam inalterados**. Os modos do Lab continuam **sem ferramentas
   executadas nem memória real**; para ferramentas testar o chat do agente.
4. `src/agent/intelligence.py`: quando o catálogo recebido é explicitamente
   vazio (`tools=[]`), o contrato JSON entregue ao Ollama **exclui** o
   movimento `act` e os campos de ferramenta, além das validações Python
   existentes. Sem catálogo não se pode presumir que ferramenta existe.
   Com catálogo verdadeiro, mantém todas as ferramentas e gates.
5. `ops/lab_eval_analysis.py`: identifica **possíveis** falsos negativos
   de formato como acentos e número por extenso, mas **nunca reescreve notas**.
   Sinaliza casos para revisão humana. Erro numérico real continua erro.
6. `ops/lab_batch_audit.py`: auditoria agregada local de muitos relatórios,
   incluindo duplicações, distribuição de status, métricas de prefill,
   geração e p95, **sem imprimir perguntas, respostas, arquivos, recibos
   completos ou histórico**.
7. **A/B de 46 perguntas idênticas:** `comparacao-qualidade-baseline-v1`
   e `comparacao-qualidade-assistente-v1`, mesmo `comparison_group`,
   mesmos enunciados e gabaritos, mudando somente o perfil do modelo e
   orçamento de geração. Os casos são de desenvolvimento, não holdout cego.

## Protocolo após atualização, sem falsos ganhos

Atualizar o notebook apenas após CI completo e merge aprovado:

```bash
cd ~/menor-assistant
bash scripts/deploy.sh
```

No Menor Lab, filtre por `comparacao-qualidade` e marque as **duas**
baterias para execução sequencial. Execute 2–3 repetições, alternando ordem
em algumas execuções se possível e evitando outras aplicações pesadas.
Publique os resultados no `lab-reports` somente com revisão e clique manual.
Compare com:

```bash
python3 -m ops.eval_compare arquivo-controle.json arquivo-assistente.json
python3 -m ops.lab_batch_audit ~/menor-data/lab --limit 100
```

A comparação permite mudança de perfil, mas **não permite alterar pergunta,
histórico, gabarito ou modo**. Avaliar também manualmente os casos
`ungraded`, segurança e naturalidade. Separar testes reais do agente,
que possuem catálogo de ferramentas, dos testes `direct` do Qwen.

**Critério para incorporar novas instruções ao perfil padrão:** melhoria
consistente de latência sem regressões em segurança, ferramenta,
interpretação de dados e matemática; reportar p50/p95, tokens gerados,
prefill, geração e conclusão. Caso o limite gere respostas cortadas,
aumentar somente no domínio afetado. Não mudar automaticamente pesos
ou GPU durante a avaliação.

## Limitações

Estas alterações são principalmente de **orçamento, roteiro e instrumento
de avaliação**, não fine-tuning nem otimização de kernels. A CPU ainda
poderá levar dezenas de segundos para gerar planos estruturados.
O teste real do Ubuntu é necessário antes de afirmar qualquer ganho de
velocidade ou inteligência. O `oneOf`/schema no backend não substitui
autenticação, confirmação do dono e recibos auditáveis.
