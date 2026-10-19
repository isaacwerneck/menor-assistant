# Chat A — contexto de múltiplos objetivos

## Problema corrigido

Anteriormente, uma conversa guardava somente um campo \`goal\` ativo. Ao iniciar
outro assunto, o Menor podia substituir o plano anterior e misturar tarefas.
Uma pergunta incidental sobre outro tema também podia apagar a tarefa.
A aprovação de uma ferramenta podia remover o plano do estado.

## Contrato de estado (apenas Chat A)

O banco privado \`agent.sqlite\` continua sendo administrado por
\`src/agent/tasks.py\`, sem migração de esquema. O JSON da sessão pode conter:

- \`phase\`: idle, goal, approval ou estado existente no agente;
- \`goal_id\`: identificador aleatório do objetivo ativo;
- \`goal\`, \`steps\`, \`acceptance\`, \`question\`: plano atual;
- \`paused_goals\`: até 6 snapshots antigos com status paused/abandoned;
- \`goal_decisions\`: últimas 12 mudanças de objetivo (tipo, ID, resumo);
- \`return_goal\`: plano temporariamente guardado enquanto o usuário aprova
  uma operação já proposta;
- \`last_result\`: comprovante verificável de ação anterior, quando existir.

A versão anterior do JSON continua legível. Nenhum dado é enviado para APIs
comerciais de IA. A referência ao objetivo não concede autorização de execução.

## Contrato do modelo de interpretação

\`intelligence.decide\` continua aceitando os campos antigos. Agora pode receber
\`paused_goals\` e devolver opcionalmente:

- \`relation=start\`: uma tarefa nova;
- \`relation=refine\`: continuar uma tarefa;
- \`relation=switch\`: trocar de assunto, pausando a anterior;
- \`relation=resume\`: retomar exatamente o ID de uma tarefa pausada;
- \`resume_goal_id\`: ID autorizado apenas se estiver em \`paused_goals\`.

Referências inventadas são recusadas pelo validador e pela máquina de estado;
não são transformadas em ações ou instalações. Quando o Ollama não retorna
um contrato válido, a tarefa existente permanece intacta.

## Permissões e efeitos externos

Uma decisão \`plan/continue/clarify\` só salva plano; não executa ferramenta.
Uma decisão \`act\` entrega a solicitação e o objetivo ao catálogo autorizado,
cuja etapa de planejamento e aprovação continua no Python.
Após confirmar ou recusar uma ação, a tarefa de longo prazo permanece
disponível; isso não é permissão para repetir outras ações.

Nenhuma mudança no código de leitores, geração de imagem ou subagentes do Chat B.

## Critérios de avaliação

Testes de regressão medem: alternância música/documentos, retomada após
reinício, cancelamento seletivo, referências falsas, limitação de memória,
indisponibilidade do modelo, aprovação única com idempotência e pesquisa
incidental sem apagar contexto. O CI testa contratos com mocks; a
capacidade real do Qwen de escolher a relação certa entre assuntos ainda
precisa ser avaliada no notebook com o benchmark \`src/agent/lab.py --live\`.

## Limitações e próximos marcos

- Ainda não há agendamento de tarefas contínuas por horas/dias.
- O estado guarda 6 objetivos pausados; não é memória ilimitada.
- O modelo local pode errar ao classificar troca ou retomada; o código
  bloqueia IDs inexistentes, mas não prova a qualidade da interpretação.
- Planejamento não instala nem implementa automaticamente ferramentas novas.
- Futuras etapas: recuperação segura de interrupções, revisão independente de
  planos, armazenamento de decisões verificadas e avaliação do modelo real.
