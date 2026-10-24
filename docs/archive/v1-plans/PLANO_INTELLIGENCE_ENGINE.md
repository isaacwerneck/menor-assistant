# MENOR INTELLIGENCE ENGINE — Arquitetura e roadmap

> **Atualização de estado — 20/10/2026:** este plano inclui etapas e PRs históricos. Para o estado atual da frente A, evidência de testes e lacunas de autonomia consulte [handoff para Codex](docs/handoff/00_COMECE_AQUI_CODEX.md) e [frentes A–E](docs/handoff/03_FRENTES_A_B_C_D_E.md). Módulo presente no código não equivale a tarefa real validada no Ubuntu.

> **Direção consolidada em 19/10/2026:** [Plano integrado A–E](docs/plano_integrado_a_e.md).
> O Menor interpreta por modelo e contexto, não por palavras isoladas; aprendizado
> é supervisionado e nenhuma inferência concede permissão. A lista histórica
> abaixo preserva decisões e entregas anteriores, mas não é comprovação de 100%
> nem substitui critérios atuais de aceite e validação no Ubuntu.


## Objetivo

O Menor deve entender objetivos de qualquer área, manter contexto entre turnos,
planejar, delegar, verificar resultados e aproveitar experiências aprovadas.
Não é um sistema de palavras-chave, e não herda a inteligência do ChatGPT.

## I1 — Implementado neste PR

- src/agent/intelligence.py: interpretação contextual no Ollama/Qwen com
  movimentos genéricos answer, clarify, plan, act, research e continue.
- Histórico recente, objetivo pendente, capacidades disponíveis e conhecimento
  relacionado da memória são considerados dados, não autorização.
- src/agent/runner.py: compreensão universal antes do roteamento antigo;
  persiste objetivo, etapas, critérios e pergunta no estado SQLite privado.
- Quando uma ação é solicitada, executa apenas ferramentas existentes, sujeitas
  a contratos de validação, recibos e autorização para efeitos sensíveis.
- Em falha do modelo, fallback seguro para fluxo anterior. Configuração
  MENOR_INTELLIGENCE_ENABLED=0 desativa o núcleo novo para recuperação.
- src/agent/lab.py: cenários variados para avaliar decisões do modelo.
  A avaliação live usa Ollama local e não executa ferramentas.
- src/agent/feedback.py: dataset privado de exemplos aprovados pelo usuário,
  somente com consentimento explícito; não treina modelos automaticamente.
- Rotas autenticadas de feedback e estatísticas; não usa APIs externas de IA.

## Etapas necessárias para alcançar o objetivo integral

### I2 — Conhecimento semântico fundamentado

Embeddings locais com Ollama, índice incremental privado, busca em projetos
e documentos, fontes claras e testes de precisão de recuperação. Manter FTS5
como fallback, e não confundir fontes recuperadas com instruções executáveis.

### I3 — Missões longas e múltiplos objetivos

Dependências, prioridades, retomada após falhas, estado de vários dias,
agendamento autorizado e relatórios. Evitar duplicação de efeitos.

### I4 — Agente programador em sandbox

Worktree isolado, geração de testes independentes, lint, revisão, ciclo de
correção limitado e PR; revisão humana antes de merge e sem autopermissões.

### I5 — Percepção e interfaces

Modelos locais de visão, áudio, música e design, controle supervisionado de
interfaces gráficas, verificação de modelos/licenças e recursos no hardware.

### I6 — Fine-tuning com dados curados

Dataset consentido, amostras de treino/teste separadas, LoRA/QLoRA quando
houver GPU e RAM adequadas, avaliações A/B e rollback de modelos.
Não treinar com conversas não autorizadas ou respostas autogeradas incorretas.

### I7 — Autonomia proativa com limites

Scheduler de tarefas permitidas, orçamentos de CPU/RAM/tempo, logs mínimos,
backup/restauração, isolamento de ferramentas e recuperação do servidor.

## Critérios de aceite antes de declarar 100%

- Generalizar para tarefas desconhecidas sem codificar palavras-chave.
- Corrigir entendimento após novas informações e reconhecer ambiguidades.
- Verificar execução por recibos e testes independentes.
- Nenhuma alteração de segurança, instalação desconhecida ou deleção sem permissão.
- Teste real do Qwen e subagentes no notebook Intel, com tempo medido.
- Melhorar métricas de benchmark sem contaminação treino/teste.
- Nunca fingir que um plano significa execução concluída.

Limitação: Qwen 7B não se torna um modelo de ponta apenas por instruções.
CI testa contratos e mocks; hardware, qualidade e treinamento dependem
de entregas e validação adicionais.

## I2 parcial — Busca semântica local opcional

A busca por significado já está disponível em src/memory/semantic.py,
com armazenamento SQLite reconstruível e embeddings gerados localmente
pelo Ollama. Para ativar, é necessário ter um modelo de embeddings
instalado no Ollama e configurar MENOR_EMBED_MODEL com seu nome. Nenhum
modelo é baixado automaticamente; sem configuração, a busca FTS5 anterior
continua ativa. O índice atual cobre aprendizados gerais e estudos,
com um limite conservador de 150 trechos. Busca semântica de projetos,
re-ranking e avaliação de precisão ainda ficam para I2 completa.

A primeira sincronização pode ser lenta em CPU; fazer benchmark no notebook.


## Separação dos modelos locais

Opcionalmente, MENOR_REASONING_MODEL escolhe um modelo do Ollama já
instalado para interpretar objetivos e conversas. Se não estiver definido,
o motor usa OLLAMA_ROUTER_MODEL ou OLLAMA_MODEL. Isso permite comparar modelos
instruct sem substituir o Qwen Coder utilizado para código. Não baixa nem
treina modelos automaticamente; benchmarks reais continuam necessários.

## I2/I4/I5 — Critério novo de capacidades demonstradas

A evolução tipo Codex usa [ciclo universal de capacidades](docs/ciclo_capacidades.md).
O estado deve manter resultados concretos e permitir perguntas sobre
executado anteriormente. Habilidades especializadas só contam quando passam
benchmarks do objetivo; instalação de pesos e saída PNG válida não garantem
compreensão de pixel art. Integradores alternativos e treinamento exigem
avaliação separada, em vez de inferência automática baseada na existência do modelo.


## I3 parcial — vários objetivos, execução tipada e observabilidade

- [x] Memória de trabalho limitada a seis objetivos pausados por conversa,
  com IDs verificáveis e retomada depois de reinício do servidor.
- [x] Modelo pode propor começar, refinar, trocar ou retomar objetivo.
  Python valida a referência antes de alterar estado.
- [x] Resposta incidental e pesquisa não apagam o plano principal.
- [x] Aprovação de uma ferramenta não apaga o objetivo que a originou.
- [x] Decisão de ação pode selecionar ferramenta e argumentos do catálogo
  real; código valida contrato e exige permissão para escrita.
- [x] Benchmark de continuidade e métricas agregadas privadas, com sinais
  de regressão e retenção limitada a 5.000 eventos.
- [ ] Avaliar o Qwen real em centenas de diálogos inéditos e medir falsos
  positivos de troca/retomada no notebook.
- [ ] Tarefas de várias horas/dias e recuperação segura após interrupções.
- [ ] Autoedição com propostas, testes independentes, PR, revisão e rollback,
  sem liberar alterações automáticas irrestritas.

Detalhes: docs/chat_a_objetivos_contextuais.md.

## I3 — Revisão independente de planos (Chat A, PR #29)

- [x] Um segundo julgamento Ollama, opcional, compara pedido atual com objetivo,
  etapas e critérios, sem classificação rígida por gênero.
- [x] Divergência produz no máximo uma reformulação. Ausência de informações
  essenciais produz pergunta; modelo indisponível preserva resposta preliminar.
- [x] Parecer nunca concede permissão de ferramenta, instalação ou publicação.
- [x] Testes isolados para erro de domínio, resposta inválida, indisponibilidade
  e impossibilidade de executar operações pela crítica.
- [ ] Medir tempo e qualidade do segundo julgamento no servidor i7 antes de
  ativá-lo para todos os pedidos. Por padrão fica desligado por custo de CPU.

Detalhes: [revisão de planos](docs/chat_a_revisao_de_planos.md).

## Prioridade operacional — contexto e latência (19/10/2026)

A avaliação remota encontrou espera elevada, perda de instruções finais,
preferências ausentes no planejador e pesquisa disparada por palavra negada.
As correções e observações estão no
[relatório integrado](docs/chat_a_benchmark_real.md#avaliação-integrada-remota--19102026).

- [x] Preservar pedido atual, fim dos turnos longos e memória já selecionada.
- [x] Aplicar preferências no planejador e manter laboratório sem dados privados.
- [x] Reduzir instruções redundantes, exigir JSON tipado e permitir resposta mínima.
- [x] Compartilhar orçamento de histórico com o fallback e remover convite repetitivo.
- [x] Respeitar decisão de não pesquisar; invalidar embeddings após troca de modelo.
- [x] Ampliar lint para módulos operacionais e regressões dos caminhos corrigidos.
- [ ] Confirmar revisão efetivamente carregada: laboratório retornou 404 no servidor.
- [ ] Comparar modelo direto, planejador e chat completo após deploy, com casos inéditos.
- [ ] Medir ganho real de latência/qualidade e consumo de recursos antes de trocar modelo.
- [ ] Validar tarefa completa com pesquisa, arquivo sintético e ferramenta com recibo.

Prioridade: estabilizar e medir o núcleo antes de expandir modelos, integrações
ou autoedição. O objetivo Jarvis pessoal permanece; ganho cognitivo não é
declarado a partir da quantidade de features ou de testes com mocks.
