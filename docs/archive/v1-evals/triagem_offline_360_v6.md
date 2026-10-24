# Incremento de triagem offline — 20/10/2026

Esta rodada acrescenta observabilidade **sem servidor ligado, sem inferência e sem publicar
dados privados**. Nenhum relatório original é editado. A implementação é apenas
diagnóstica: não modifica o modelo, o roteamento de ferramentas, aprovações,
autenticação nem parâmetros operacionais.

## Evidência que motivou a mudança

A rodada completa de 20/10 registrada na branch privada `lab-reports` totaliza
360 **execuções** em 15 relatórios finais: 142 aprovações automáticas, 36 reprovações
automáticas, 182 sem nota e 21 falhas técnicas (estas podem sobrepor as notas).
Inclui uma bateria de 192 casos reaproveitados em lotes temáticos; não contabilizar
360 como perguntas inéditas. Os resultados são históricos, não baseline novo após PR.

- `matematica-validacao-v2`: 5/12 falhas automáticas com resultados matemáticos
  realmente incorretos; conferir contas separadamente de formato.
- `injecao-dados-nao-instrucoes`: 3/12 falhas automáticas e 2 técnicas; textos
  citados foram confundidos com instruções de autoridade.
- `diagnostico-geral-192-v1`: 16 falhas técnicas no lote composto;
  seus exemplos aparecem também em baterias temáticas.
- 182 execuções sem nota automática exigem rubrica humana e não são 182 erros.

## Uso

```bash
python3 -m ops.lab_batch_audit ~/menor-data/lab --limit 100
```

O relatório agrega `repeated_prompt_executions`, `technical_graded_failures`,
`completed_graded_failures`, `validation_issues` (categorias conhecidas),
`priority_suites`, limites de saída e latência mediana por bateria.

**Interpretação:** repetição é igualdade de pergunta + histórico, independentemente
do perfil de estilo. Portanto não use a deduplicação como taxa de acerto de um
experimento A/B. `priority_suites` prioriza falhas técnicas, falhas automáticas
em respostas completas e saídas limitadas; não avalia qualidade de  respostas
abertas. As métricas usam apenas relatórios disponíveis no Ubuntu.

## Próximo teste quando o servidor iniciar

1. Confirmar SHA de deploy e saúde Ollama; executar auditoria offline acima.
2. No Lab, executar as baterias A/B `comparacao-qualidade-baseline-v1` e
   `comparacao-qualidade-assistente-v1`, 46 casos cada, com mesma máquina e
   sem concorrência. Alternar ordem em repetições.
3. Rodar `matematica-validacao-v2` e `injecao-dados-nao-instrucoes` novamente
   para detectar regressões e revisão humana de falso recibo/autoridade citada.
4. Medir falhas técnicas, respostas de 256 tokens, p50/p95, tempo de geração,
   acerto no conjunto corrigível e qualidade de respostas abertas.
5. Sem novo baseline real, não afirmar aceleração ou ganho de inteligência.

Mudanças futuras de cálculo supervisionado, prompt ou gates precisam de ensaio
de chat completo e recibos reais: o `Lab direct` não executa ferramentas.
