# Menor Assistant — Plano A–E, com aceite por tarefas reais

Data: 21/10/2026. Base de avaliação: main d37bf271 (E12).
Objetivo: trocar métricas de infraestrutura isoladas por capacidades verificadas
na experiência do usuário. Um modelo 7B em CPU não é equivalente a um modelo
avançado; preservar um caminho híbrido opcional e consentido sem o tornar requisito.

## Métrica norte: tarefa concluída, não JSON válido

Uma tarefa só é considerada concluída se o pedido foi interpretado, efeitos
necessários foram autorizados, ferramentas executaram e o artefato foi verificado
com critérios previamente definidos. Resultado "decisão validada" ou teste
mockado não equivale a conclusão do trabalho. Registrar a causa de cada bloqueio:
modelo, intenção, catálogo, autorização, sandbox, aplicação ou avaliação.

Cinco provas de aceite, em sessões reais, repetidas em ao menos duas rodadas:
1. Conversar sobre um projeto por 8 turnos, sem re-perguntar escolhas ou inventar ações.
2. Criar e recuperar um projeto e três tarefas aprovadas, mantendo contexto.
3. Pesquisar uma questão pública, citar fontes e distinguir incertezas.
4. Criar um miniaplicativo de arquivos reais, verificar sintaxe e abrir/inspecionar
   em navegador isolado; corrigir defeito e revalidar antes de chamar concluído.
5. Propor uma ferramenta de texto, validá-la em Docker sem rede e abrir PR rascunho;
   não instalá-la antes de revisão e CI.

O ensaio atual de Lab compara apenas resposta direta e planejador, sem ferramentas.
Criar um ensaio completo separado com recibos privados para testar os cinco fluxos.
Não armazenar conversas privadas em arquivos enviados ao GitHub sem confirmação.

## Fase A — Conversa e inteligência

- Inventariar caminhos de conversa, colaboração, raciocínio e fallback em runner,
  intelligence, conversation, voice, context_engine e goal_context.
- Corrigir roteamento onde pedidos de execução explícitos entram no caminho que
  somente conversa: não executar sem aprovação e contexto de projeto.
- Evitar prompt/contexto gigantes quando desnecessário; não comprometer memória.
- Comparar 7B Coder com 7B Instruct em tarefas reais, com contexto, modelo,
  versão, quantização, tempos e avaliação humana do conteúdo.
- Aceite: pelo menos 7/8 turnos de conversa coerentes e ações explicitamente
  solicitadas chegando ao fluxo de autorização adequado.

## Fase B — Executor com continuidade

- Unificar decisões, chamadas de ferramenta, observações, recibos e continuidade.
  O loop de leitura passa a suportar 6 ações (ainda com parada por repetição).
- Cada escrita exige aprovação precisa e escopo; não permitir comandos arbitrários.
- Persistir estado de operação longa e permitir retomar após reinício, sem
  duplicar efeitos; política de retry limitada e idempotência verificável.
- Aceite: sequência de 3 ferramentas de leitura concluída e resumida com evidência;
  sequência com escrita retoma autorização sem alegar execução antecipada.
- Ainda pendente: checkpoint persistente de todo o ciclo do modelo e auto-reparo.

## Fase C — Programação real

- CodeWorkspace permanece com um arquivo seguro e sem sobrescrita; valida JS
  com Node --check quando disponível, sem executar o JS.
- Novo primeiro degrau: webapp Canvas offline (index.html, style.css, game.js),
  um pedido por projeto já selecionado, aprovação, fontes sem rede nem segredos,
  sintaxe verificada, recibos de hash e revisão no navegador explicitamente pendente.
- Próximos incrementos: gerar múltiplos arquivos arbitrários em workspace isolado,
  executar testes em container sem rede, observar erros, corrigir até limite,
  evidenciar rodagem real em navegador e preservar rollback.
- Aceite desta fatia: três arquivos gravados exclusivamente, nenhuma gravação
  quando sintaxe falha ou aprovação é recusada. Aceite da fase completa:
  aplicativo com teste funcional real, correção automática limitada e recibo.
- Não declarar app pronto apenas por passar no parser de JS.

## Fase D — Ferramentas autoexpansíveis supervisionadas

- ToolBuilder mantém Docker isolado sem rede e PR rascunho obrigatório.
- Uma tentativa adicional de gerar proposta apenas se sintaxe/teste falhar;
  indisponibilidade do Docker nunca é mascarada por novo pedido ao modelo.
- Futuro: catálogo de contratos tipados para capacidades além de run(text),
  sandbox com permissões finas e validação humana/CI antes de incorporar.
- Aceite completo: ferramenta real executa em ambiente controlado após revisão;
  registro e usuário conseguem comprovar capacidade sem elevação de privilégios.

## Fase E — Laboratório e avaliação

- Arquivar todo histórico existente por decisão explícita, com índice privado
  persistente. JSON e resumos nunca são apagados nem enviados automaticamente.
- Separar Atual de Arquivados, permitir reativação; seleção Git por hash continua
  usando os mesmos relatórios originais.
- Testes herméticos em CI provam contratos e não substituem execução com Ollama.
- Avaliar cinco provas reais: pass/fail com evidência, nível de qualidade humana,
  tempo, modelo, chamadas/retries, custos de CPU/RAM e origem de falha.
- Critério de saída do ciclo: 3/5 casos reais completos em duas rodadas,
  depois 4/5, depois 5/5, sem perder limites de segurança.

## Auditoria Ponytail — aplicação prática

A skill versionada `.agents/skills/ponytail/SKILL.md` é uma regra de
engenharia, não uma ferramenta que executa varredura sozinho. Aplica:
menor alteração completa, reutilizar contratos existentes, revisar chamadores,
sem sobre-engenharia, com teste para cada ramificação de risco.

Mapa de responsabilidades inspecionado nesta rodada:
- runner/conversation/intelligence: classificação, escolha, continuidade,
  fallback; interceptação textual indevida em pedidos de projeto.
- code_workspace/workspace/manager: isolamento dos projetos e escrita única.
- tool_builder/ponytail/code_sandbox/custom_runtime/registry: geração,
  sandbox, contratos e autorização; builder limitado a ferramentas textuais.
- lab_batches/lab_batches_routes/lab_report_sync/lab_publish: resultados
  completos, fila e publicação, com histórico poluído sem arquivo persistente.
- ops/model_latency: inferência CPU e benchmark.
- quality_metrics/benchmark/plan_review/context_engine: avaliações e
  limites de interpretação; alta cobertura de mocks, pouca prova de tarefas.

Isto não certifica revisão linha a linha de *todos* os módulos Python.
A auditoria integral continuará por grupos de dependências e testes de
integração; não esconder lacunas sob a expressão "varredura completa".

## Evidência CPU fornecida pelo operador

7B Qwen Coder, duas amostras por variante de thread:
1=2,99 t/s; 2=5,21; 4=7,71; 6=7,62; 8=8,39.
Troca de configuração apresentou carregamentos entre ~5 e 40 segundos
em parte das chamadas. Na matriz, prompt longo sem cache processou cerca de
509 tokens em 12–17 s, enquanto respostas longas ficaram em torno de
7 tokens/s. São dados influenciados por recarga, cache e atividade da CPU.
Não escolher oito threads nem alterar padrão com base em duas medições.

Próximo experimento: modelo único residente, pares de configs em ordem
alternada, tempos de carregamento excluídos da comparação de geração,
com CPU/temperatura e quantização fixadas. Só implementar override depois
de melhoria repetida e sem perda nas cinco provas de aceite.

## Lançamento incremental

**Fatia E13** (esta atualização): roteamento de pedido explícito com projeto,
webapp Canvas de três arquivos, validação estática JS, reparo limitado do
ToolBuilder, limite de seis ações de leitura e arquivo lógico do Lab.
Essa fatia não conclui as fases A–E. Não inclui app testado no navegador,
ferramenta irrestrita, modelo novo instalado ou inferência real na CI.

**Fatia seguinte**: harness de projeto com execução de testes isolados,
recibo de falha, uma correção automática e inspeção em navegador local.
Depois: persistência de tarefas longas e avaliação end-to-end, antes de
novos botões e componentes cosméticos.
