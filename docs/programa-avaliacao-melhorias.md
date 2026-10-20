# Programa de avaliação e evolução do Menor Assistant (v1)

## Norte do projeto

Construir um assistente pessoal local no Ubuntu, generalista, que compreende linguagem
natural, mantém contexto e memória sob controle do usuário, usa ferramentas de
forma autorizada, planeja e executa tarefas complexas, verifica artefatos e
melhora progressivamente. O objetivo é uma experiência próxima de um assistente
geral combinado a um agente de programação, **sem confundir plano com execução**.

**Uma bateria de testes NÃO treina automaticamente os pesos do Qwen.** Ela
identifica falhas e permite comparar mudanças em prompts, roteamento,
contratos, memória, ferramentas, modelos e infraestrutura. Fine-tuning local
somente se, depois de diagnóstico, houver dados de treinamento adequados,
hardware e um conjunto de avaliação independente.

## Fundamentação e fontes consultadas (outubro de 2026)

1. **OpenAI — Evaluation best practices:**
   https://developers.openai.com/api/docs/guides/evaluation-best-practices
   Recomenda avaliações específicas de tarefa, dados representativos,
   pontuação automatizada calibrada com julgamentos humanos e avaliações
   iterativas em vez de intuição.
2. **OpenAI Cookbook — Evaluation flywheel:**
   https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md
   Ciclo de analisar erros, quantificar em casos de avaliação e melhorar
   a aplicação após a medição.
3. **OpenAI — Model optimization:**
   https://developers.openai.com/api/docs/guides/model-optimization
   Separação entre avaliação, engenharia de prompt e fine-tuning.
4. **OpenAI — Graders:**
   https://developers.openai.com/api/docs/guides/graders
   Graders por checagem textual, similaridade, rubrica e outros mecanismos;
   combinar verificadores exige cuidado com falsos positivos.
5. **Stanford CRFM — HELM:**
   https://crfm.stanford.edu/2022/11/17/helm.html
   Medição multidimensional: precisão, calibração, robustez, vieses,
   toxicidade, justiça e eficiência, com cenários direcionados.
6. **GAIA — General AI Assistants:**
   https://arxiv.org/abs/2311.12983
   Tarefas reais com busca, raciocínio, multimodalidade e ferramentas.
7. **Tau-bench — Tool-Agent-User:**
   https://arxiv.org/abs/2406.12045
   Agentes interagindo com ferramentas e políticas; comparação do
   estado final e repetições para confiabilidade.
8. **OpenAI — SWE-bench Verified:**
   https://openai.com/index/introducing-swe-bench-verified/
   Testes FAIL_TO_PASS para a correção e PASS_TO_PASS para regressões.
9. **OpenAI — Contaminação de benchmarks:**
   https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
   Resultados inflados quando modelo e desenvolvedor conhecem as soluções.
10. **EleutherAI — lm-evaluation-harness:**
    https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md
    Configurações reprodutíveis de tarefas, métricas e versões.
11. **NIST — AI RMF (Measure):**
    https://airc.nist.gov/airmf-resources/airmf/5-sec-core/
    Medição contínua, documentação de incerteza e análise de riscos.
12. **Reuters (13/10/2026) — auditoria independente de IA:**
    https://www.reuters.com/world/behind-ai-industrys-call-independent-reviews-fight-over-what-gets-made-public-2026-10-13/
    Debate de transparência, independência de auditorias e dados privados.

Estas são **baterias originais, inspiradas nessas metodologias**. Não são
implementações oficiais de GAIA, HELM, tau-bench ou SWE-bench e não devem ter
suas notas comparadas diretamente aos leaderboards dessas instituições.

## Capacidades, conjuntos e critérios

Há **16 novas baterias com 12 casos cada (192 novos casos)** em `lab/suites/`,
mais o diagnóstico inicial existente. Cada bateria está dentro do formato
suportado por `src/api/lab_batches.py`: `id`, `title`, `cases`,
`mode`, `message`, histórico opcional e `expected_contains`.

- Linguagem e instruções: `instrucoes-ptbr`, `conversacao-robustez`.
- Raciocínio: `raciocinio-matematica`, `logica-restricoes`.
- Memória local simulada: `memoria-contexto-curto`.
- Limites e confiança: `honestidade-limites`, `pesquisa-verificacao`.
- Ação segura: `planejamento-supervisionado`, `ferramentas-recibos`,
  `permissoes-privacidade`, `injecao-dados-nao-instrucoes`.
- Tarefas especializadas: `programacao-debug`, `dados-extracao`,
  `pedidos-multimodais`, `tarefas-multietapa`.
- Consciência de qualidade: `avaliacao-evolucao`.

Os casos incluem metadados de `review_criteria` para revisão manual e
`split` como rótulo exploratório (9 development / 3 holdout por bateria).
**A interface atual NÃO filtra por split:** executa os 12 casos, portanto
esse `holdout` NÃO é um conjunto cego independente. Não use esses 48 casos
como comprovação de generalização após consultar suas respostas. Para
validação final rigorosa, gere conjuntos adicionais novos, ainda não
vistos pelo desenvolvedor ou modelo, e não os utilize no ajuste.

`expected_contains` verifica **somente inclusão textual**. Exemplo: uma
resposta pode incluir "não" mas contradizer a pergunta; a nota automática
pode ser enganosa. Não há avaliador semântico calibrado nesta versão.
Os casos com `expected_contains: []` continuam **sem nota**, e NÃO
devem ser contados como falhas nem como acertos. As rubricas humanas
são metadados para análise, não execução automática.

## Quatro níveis de avaliação (não confundir)

1. **L0 — Código/infraestrutura:** pytest/unittest, CI, sintaxe de frontend,
   segurança de rotas, banco, fluxos simulados, deploy e rollback.
   Esses testes verificam *código*, não raciocínio da IA.
2. **L1 — Menor Lab atual:** inferência `direct` ou `planner`, histórico
   efêmero, SEM ferramentas, arquivos reais ou memória persistente.
   As 192 novas perguntas funcionam aqui.
3. **L2 — Agente em sandbox (a construir):** ferramentas simuladas ou
   ambientes descartáveis, snapshots de sistema/arquivos, políticas,
   decisões supervisionadas e avaliação **do estado final**. Inspirado em
   GAIA, tau-bench e SWE-bench. Necessário para comprovar capacidades
   de criar/editar documentos, navegar, pesquisar ou programar.
4. **L3 — Fluxo real supervisionado (futuro):** ensaio autorizado em
   ambiente controlado, recibos verificáveis, qualidade do artefato,
   rollback e aprovação humana para ações destrutivas/publicações.

Uma resposta "vou gerar arquivo" em L1 não prova que foi gerado em L2.

## Como executar no Menor Lab

1. Faça deploy da `main` após merge e abra `/lab/view` autenticado.
2. Clique em **Atualizar gaveta**: aparecem as baterias novas.
3. Rode **uma bateria por vez**. A inferência local é serial e algumas
   perguntas de `planner` podem levar dezenas de segundos. Evite
   iniciar 192 de uma só vez; aqueça o modelo antes da primeira medição.
4. Faça primeiro `instrucoes-ptbr`, `honestidade-limites` e
   `planejamento-supervisionado`. Depois cubra demais categorias.
5. Para cada bateria, registre modelo, hardware, commit de código,
   temperatura/configurações de inferência, latência e falhas;
   compare ambientes equivalentes. A versão v1 **não registra todos
   esses metadados**, portanto faça nota externa se necessário.
6. Publique **manualmente** os relatórios completos (apenas repositório
   privado, depois de conferir se não contêm segredos) na branch
   `lab-reports`. A publicação não dá merge na main.
7. Envie à revisão humana os casos marcados **sem nota**. Para campos
   de alto risco, exija validação humana antes de aprovar a mudança.

Os prompts de L1 não enviam arquivos nem executam comandos. Não inclua
senhas nem documentos privados em baterias de avaliação.

## Leitura estruturada dos resultados

Exemplo de análise local sem enviar ou imprimir texto privado:

```bash
python -m ops.lab_eval_analysis ~/menor-data/lab/<run_id>.json
python -m ops.lab_eval_analysis ~/menor-data/lab/<run_antigo>.json ~/menor-data/lab/<run_novo>.json
```

O comando imprime JSON com categorias, contagens, latência mediana,
classificação de falhas, sugestões e mudanças entre duas execuções
da mesma bateria. Não imprime pergunta nem resposta e não realiza
chamadas de rede. Também não faz uma avaliação semântica automática.

**Indicadores separados:**
- Taxa de acerto dos casos *automaticamente graduados*, denominador
  explícito; proporção sem nota à parte.
- Taxa de decisão válida do planner (`decision_validated`), timeout,
  ocupação da fila e erro de inferência, separadamente.
- Mediana e distribuição de latência por modo, não apenas média global.
- Cumprimento de restrições, qualidade e segurança via rubrica humana.
- Repetições de cada caso em dias diferentes (taxa de sucesso e variação).
- Em L2, sucesso do estado final, chamadas permitidas/bloqueadas, recibos,
  artefatos reais e regressões; L1 não permite essas métricas.

## Diagnóstico -> hipótese -> correção -> reavaliação

| Sintoma | Possível origem | Hipótese de melhoria e teste |
| --- | --- | --- |
| Conta incorreta ou texto ignora formato | prompt/modelo/parsing | melhorar instrução de saída, determinismo, comparação por categoria; considerar modelo especializado |
| `no_valid_decision` | roteador JSON/planner/schema | reproduzir em `intelligence.decide`, verificar contrato, limites, retries e validação sem inferir autorização |
| `ReadTimeout`/ocupado | Ollama/carga/CPU/RAM/filas | registrar duração, carga, número de tokens, warmup e limitação de concorrência |
| Resposta inventa arquivo ou navegação | instruções/recibos/contrato | exigir evidência real antes de afirmar ação; caso de regressão |
| Plano contém exclusão não solicitada | restrições/planner/autorização | codificar invariantes e testar em L2 que nenhum arquivo foi alterado |
| Recuperação errada do contexto | histórico/resumo/memória | comparar curtas vs longas janelas, retrieval, isolamento entre projetos |
| Não usa ferramenta disponível | roteamento/capabilities/subagente | comparar intenção, decisão, args, execução e recibo; não alterar só prompt |
| Acerto instável entre rodadas | amostragem/contexto/carga | medir success@1 e consistência em repetições; variar paráfrases |
| Melhoria num teste causa erro antigo | regressão | manter `FAIL_TO_PASS` e `PASS_TO_PASS` de software, mais casos IA anteriores |

Priorize causas **observáveis**. Por exemplo, timeout não prova falta de
inteligência; resposta incorreta não prova que fine-tuning seja necessário.

## Ciclo de trabalho com PRs

1. Baseline das baterias, sem mudar código, e revisão dos exemplos falhos.
2. Classificar cada falha: `prompt`, `planner`, `modelo`, `memoria`,
   `roteamento`, `tool`, `infra`, `permissao`, `dados`, `grader`.
3. Criar problema reprodutível, com comportamento esperado e
   **teste de regressão** que falha antes da correção.
4. Implementar patch mínimo no componente causador; não tentar
   “acertar” apenas a formulação da bateria conhecida.
5. Exigir CI verde e revisão da autorização; sem merge destrutivo.
6. Repetir as baterias relevantes, comparar métricas e inspecionar
   resultados abertos manualmente; **não prometer melhoria global por
   elevar uma única nota**.
7. Medir num conjunto **novo/cego** antes da conclusão e monitorar
   regressões após deploy. Manter sempre os relatórios de baseline.

Futuramente, se decidirmos ajustar pesos com LoRA/fine-tuning, gerar
**outro conjunto de treino** a partir de casos revisados, sem segredos;
separar treino, validação e teste final independente. Não treinar em
respostas não verificadas e evitar vazamento de dados de teste no treino.

## Limitações e trabalhos futuros

- Faltam graders formais com notas por rubrica/humano, severidade,
  formatos estritos e verificação semântica independente.
- Os 48 casos rotulados `holdout` não são cegos, conforme explicado.
- Não há medição de ferramentas reais, estado final, custo energético,
  multimodalidade verdadeira ou memória persistente em L1.
- Faltam casos longos/multiturno dinâmicos com usuários simulados,
  repetição automatizada e controle de versões do modelo.
- Uma avaliação em repositório privado continua exigindo revisão de
  confidencialidade antes do push.

O próximo marco recomendado é um executor L2 com fixtures descartáveis,
políticas de autorização verificáveis e validadores determinísticos
de artefatos: criar CSV, editar documento, reparar pequeno bug,
consultar ferramenta mock, e **verificar efeitos reais** sem
acessar produção ou dados pessoais.
