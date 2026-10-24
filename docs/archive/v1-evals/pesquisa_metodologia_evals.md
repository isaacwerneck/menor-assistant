# Programa de avaliação e melhoria do Menor Assistant — v1 (20/10/2026)

## Missão

Transformar o Menor, instalado no Ubuntu, em um assistente pessoal geral semelhante, em
experiência e capacidade de execução supervisionada, a um ChatGPT com ferramentas tipo Codex:
entender intenção natural, sustentar contexto e memória, pesquisar com evidências, trabalhar
com arquivos/imagens/áudio, planejar, usar ferramentas reais com autorização, verificar artefatos,
diagnosticar falhas e melhorar progressivamente. **Avaliar não equivale a treinar pesos.**

## Fontes e o que foi aprendido

1. [OpenAI — Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices):
   critérios vinculados ao uso real, graders determinísticos/humanos/modelo e comparação de mudanças.
2. [OpenAI — Optimizing LLM Accuracy](https://developers.openai.com/api/docs/guides/optimizing-llm-accuracy):
   a decisão entre prompt, contexto/RAG e fine-tuning depende do **tipo de falha**, não de moda.
3. [OpenAI — Model optimization](https://developers.openai.com/api/docs/guides/model-optimization):
   ciclo avaliação → hipótese → alteração → nova avaliação.
4. [OpenAI Evals, código aberto](https://github.com/openai/evals): conjuntos de dados,
   graders, métricas e registro dos resultados; não há dependência da API da OpenAI neste projeto.
5. [Stanford HELM](https://crfm.stanford.edu/helm/index.html):
   medir diversas dimensões (precisão, segurança, robustez, eficiência), não uma só pontuação.
6. [GAIA](https://arxiv.org/abs/2311.12983): tarefas de assistente que demandam
   pesquisa, ferramentas e, algumas vezes, multimodalidade.
7. [τ-bench](https://arxiv.org/abs/2406.12045): avaliar **estado final** e
   consistência do agente em várias tentativas, com políticas e ferramentas.
8. [SWE-bench](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md):
   correções de código avaliadas em ambiente reproduzível, aplicando patches e rodando testes.
9. [OpenAI — limitações do SWE-bench Verified (2026)](
   https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/):
   contaminação do benchmark e critérios falhos podem fabricar desempenho aparente.
10. [Anthropic — Demystifying evals for AI agents (2026)](
    https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents):
    tarefa, tentativa, grader, trace, estado final, repetição e avaliação manual.
11. [NIST AI RMF GenAI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence):
    gestão contínua de riscos, confiança e testes de sistemas com IA.
12. [Hugging Face — TRL SFT](https://huggingface.co/docs/trl/sft_trainer):
    exemplos supervisionados aprovados e adaptadores PEFT para eventual ajuste de pesos.

Os 192 casos desta coleção são **originais e adaptados ao Menor**, não cópias oficiais ou
pontuações comparáveis às leaderboards dessas referências.

## O que os testes atuais realmente medem

O Menor Lab possui dois modos: `direct` (Qwen sem agente) e `planner`
(raciocinador que produz decisões estruturadas). Nenhum deles executa ferramentas.
Essas baterias **não validam** memória persistente, navegador real, arquivos reais,
edição de repositório, geração de imagens/áudio, envio de e-mail nem autonomia
end-to-end. Podem medir se o modelo entende e formula uma proposta sobre essas
capacidades. Avaliação real exigirá harness com ferramentas simuladas ou sandbox,
traces, permissões, estado inicial conhecido e asserções de estado final.

`lab/suites/` oferece 16 baterias específicas de 12 casos cada, além de duas agregações:
`triagem-16-v1` (16 casos) e `diagnostico-geral-192-v1` (192 casos, execução longa).
As agregações repetem exemplos das suítes específicas; **não são novos casos independentes**. Cada caso pode carregar:
- `id`, `mode`, `message`, `history` e `category` (contrato do laboratório);
- `expected_exact` (comparação exata, ignorando espaços externos e caixa);
- `expected_contains` (todos os marcadores devem aparecer; **heurística fraca**);
- `review_criteria` (rubrica para revisão humana, não uma nota automática);
- `split` = `development` ou `validation` (48 casos de validação em 16 suítes: 3 por suíte);
- `methodology_version` na raiz da bateria.

**Cuidado:** o campo `validation` não constitui um holdout verdadeiramente cego:
estes arquivos estão versionados no Git, podem ser lidos e os prompts podem acabar
conhecidos por desenvolvedores/modelos. Um benchmark cego de promoção deve ficar
isolado do repositório de desenvolvimento, com acesso restrito e sem vazamento
de exemplos para ajuste de prompt ou treinamento.

### Graders e métricas

- `automatic_pass=true/false`: só quando há asserção determinística.
- `automatic_pass=null`: **não avaliado**, jamais contabilizar como erro/acerto.
- `status`: separa sucesso de inferência, timeout, `busy`, parse inválido etc.
- `inference_failures`: falhas de execução separadas dos erros de conteúdo.
- Revisão humana: para cada rubrica dar `pass`, `fail` ou `unclear`, com motivo;
  não confundir saída plausível com execução verificada.
- Robustez: repetir cada bateria crítica pelo menos 3 vezes em condições iguais;
  medir variação, não escolher apenas a melhor execução.
- Latência: p50, p95, máximo, timeout, por modo e por categoria.
- Segurança: critério de bloqueio absoluto para ações destrutivas/sem permissão,
  vazamento de credenciais ou afirmação falsa de execução; uma média alta não compensa.

Um grader baseado em texto pode errar: por exemplo, encontrar "não" dentro de
"sim, não tenho certeza" não valida uma resposta binária. Para respostas objetivas,
prefira `expected_exact`. Para planos, verifique restrições e qualidade da sequência
por rubrica, nunca apenas pela presença de palavras.

## Ciclo de melhoria (iterar sem autoengano)

1. **Baseline congelada:** registrar commit da `main`, versão do modelo, quantização,
   hardware, `OLLAMA_MODEL`, `MENOR_REASONING_MODEL`, configurações e timestamp.
2. **Executar por categoria:** começar com 12 casos; só depois aumentar para 48 ou 192.
   Registrar erros sem modificar as perguntas usadas como referência.
3. **Publicar relatório completo manualmente** na branch privada `lab-reports`;
   não anexar tokens, documentos sensíveis ou dados pessoais. Confirmar repositório privado.
4. **Análise da falha:** identificar se foi erro de raciocínio, instrução, contexto,
   recuperação, roteamento, permissão, formato, ferramenta, timeout ou infraestrutura.
5. **Hipótese específica:** escolher **uma alteração** e explicar o que deveria mudar.
   Ex.: parse JSON falha → reduzir ambiguidade do esquema e adicionar validação/retry.
6. **Patch isolado + teste de regressão:** implementar em PR próprio, CI completo,
   sem remover testes que falharam; aprovar apenas após revisar diffs e permissões.
7. **Reexecutar a mesma bateria** na mesma configuração, repetir, comparar taxas e tempos.
   Medir no conjunto de validação e proteger um conjunto cego posterior.
8. **Promover ou reverter**: melhorar métrica-alvo sem piorar segurança, confiabilidade,
   latência ou casos anteriormente bons. Arquivar relatório de decisão.
9. **Alimentar suíte de regressão** com novas falhas reais, sem incluir informações privadas.

### Diagnóstico → intervenção

| Sinal nos resultados | Investigar primeiro | Hipótese de melhoria |
|---|---|---|
| `ReadTimeout`, `busy`, latência extrema | Ollama/CPU/RAM, fila, payload, modelo | timeout adequado, fila persistente, modelo leve |
| `no_valid_decision` | parser JSON, esquema, prompt e tentativas | validação estruturada e reparo com limite |
| Formato errado/ignora restrição | prompt de sistema, exemplos e grader | prompt mais preciso, exemplos demonstrativos |
| Resposta ignora histórico fornecido | construção de contexto e truncamento | memória curta, seleção de contexto |
| Dados privados/atuais não encontrados | índice RAG, recuperador, origem | melhorar busca, grounding, citações |
| Ação alegada sem recibo | roteamento, contrato da ferramenta | recibos verificáveis de execução |
| Plano quer apagar/mover sem autorização | política, guardrails, etapas | portão de aprovação + dry-run/rollback |
| Erro em tarefas com arquivos | ferramenta, parser, sandbox | fixtures, contrato, asserções de artefato |
| Erro aparece só após deploy | ambiente, migração, cache, CI | testes de integração e smoke tests |
| Erro persiste após corrigir contexto e roteamento | capacidade do modelo | comparar modelos, considerar SFT/LoRA |

### Quando treinar pesos de verdade

Somente depois de identificar que o problema é **comportamento aprendido**, e não
a ausência de contexto/ferramenta ou um bug. Preparar exemplos aprovados (instrução,
contexto fornecido, resposta corrigida), remover dados sensíveis e manter splits de
treino/validação/teste isolados. Considerar SFT/LoRA/QLoRA local com modelo-base
compatível e hardware medido; não assumir que o Qwen via Ollama suporta treino direto.
Fazer comparação antes/depois em tarefas **não usadas** no ajuste. Treinar com
respostas erradas ou com o mesmo gabarito de avaliação causa sobreajuste. DPO ou
outros métodos por preferência exigem pares revisados e infraestrutura adicional:
não são o primeiro passo para este projeto.

## Executar a comparação local (opcional)

```bash
python3 -m ops.eval_compare ~/menor-data/lab/<run_id_antes>.json
python3 -m ops.eval_compare ~/menor-data/lab/<run_id_antes>.json ~/menor-data/lab/<run_id_depois>.json
```

O script produz apenas métricas, IDs de casos que regrediram e recomendações; **não**
imprime respostas ou perguntas. Verifique que os relatórios sejam da mesma bateria.
O relatório do GitHub continua sendo a fonte para revisão qualitativa neste chat.

## Princípios de qualidade da medição

- **Não usar nota global = acertos / todos os casos**: casos sem rubricagem não têm nota.
- **Não chamar este laboratório de teste de agente completo**: são duas modalidades sem ferramentas.
- **Não promover apenas por melhora pontual**: olhar repetição, variação e categorias críticas.
- **Não remover teste por estar difícil**: primeiro auditar ambiguidade e gabarito.
- **Não otimizar em cima de gabaritos escondidos**: separar desenvolvimento de teste final.
- **Não confundir autorização declarada com ferramenta executada**: exigir recibo e estado final.

## Próximas camadas (ainda não implementadas)

1. Harness offline de agentes com repositório descartável, Git simulado, FS temporário,
   fake APIs e transcrições completas; assertivo para permissão e resultado.
2. Testes de recuperação de memória persistente isolada, RAG e citações verificáveis.
3. Benchmarks de PDFs, planilhas, imagens e áudio com artefatos reais e gabaritos.
4. Arena A/B de prompts/modelos, evals cegas privadas, execução repetida e painel de regressões.
5. Instrumentação de execução completa e autoaperfeiçoamento supervisionado,
   com rollback, auditoria e CI como critérios obrigatórios.
