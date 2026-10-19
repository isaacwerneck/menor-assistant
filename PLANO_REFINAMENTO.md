# PLANO DE REFINAMENTO — Qualidade, autonomia e autoaperfeiçoamento do Menor

Status: plano mestre complementar ao [PLANO.md](PLANO.md), 18/10/2026.
**Regra:** não considerar uma capacidade concluída por estar documentada; cada marco exige testes, evidência e validação no servidor.

## 1. Problemas reais encontrados (regressões obrigatórias)

- 18:57: "bora fazer essa ferramenta de criar imagens?" → modelo perguntou "Tem certeza?" em vez de iniciar planejamento da ferramenta; "simm" → erro de interpretação.
- 18:58: "vamos criar uma ferramenta nova de criar imagens?" → Menor tratou o pedido **de execução** como mera intenção de **anotação**; respondeu "em qual pasta?"; "ferramentas" → erro.
- Layout do iPhone: transbordamento horizontal, avatar e texto cortados, rolagem lateral.
- Antes: assistente afirmou que lembrava sem registrar em arquivo; comandos naturais e contexto anterior ignorados.
- Problemas futuros previstos: timeouts no Ollama, respostas JSON malformadas, memórias conflitantes, ações repetidas, alterações concorrentes, falta de backup e deploy sem rollback.

## 2. Máquina de estados e decisão explícita

Cada conversa e tarefa tem estados persistentes e auditáveis:
`observada -> interpretada -> planejada -> aguardando esclarecimento/aprovação -> executando
-> verificada -> concluída|falhou|cancelada`.
Uma resposta como "sim", "simm" ou "ferramentas" é interpretada **no estado pendente**
e não reprocessada como uma ordem isolada. Registros de memórias não substituem
pedidos de execução: "crie a ferramenta" é uma tarefa; anotar a ideia é efeito
secundário, não o objetivo final.

O modelo propõe intenção estruturada, mas **somente código Python valida
objetivos, permissões, arquivos, consequências, destinatários e efeitos**.
Pedidos claros de baixo risco podem agir; ambiguidades exigem pergunta curta
sem botões invasivos. Em caso de dúvida/falha, não inventar sucesso.
Eventos repetidos devem ter chaves de idempotência para evitar duplicações.

## 3. Contratos de ferramentas (Fase 4)

- Registro de tools versionadas com schema JSON, custo, risco, side effects e testes.
- Executor com funções permitidas por nome, entrada tipada, timeout, registro da
  execução e resultados verificados. Sem `eval`, shell arbitrário ou paths externos.
- Ferramentas iniciais: listar projetos, ler notas, registrar tarefa/decisão,
  inspecionar estado do cérebro, criar propostas de melhoria.
- Ferramentas futuras: buscas web, imagem (motor não disponível ainda), voz, Git.
- Toda tool executada deve produzir recibo `executed|failed|needs_approval`.
- Auditar somente metadados mínimos, sem expor dados sensíveis.

## 4. Autoedição e correção (Fase 5)

Prioridade: **propor mudanças**, não sobrescrever código em produção.

1. Observar falha com trace sanitizado, categoria e passos reproduzíveis.
2. Gerar hipótese, arquivos afetados, patch e testes de regressão.
3. Criar worktree isolada sob diretório de desenvolvimento, sem credenciais
   de produção nem acesso arbitrário ao cérebro.
4. Aplicar patch somente em arquivos permitidos, com limites de tamanho.
5. Rodar formatter/lint/testes/validações, com timeout e cotas de execução.
6. Corrigir até um número limitado de tentativas; desistir se não verificável.
7. Fazer commit e push **somente em branch**, abrir PR com relatório.
8. Esperar revisão humana para merge; monitorar deploy e reverter com backup
   se o serviço falhar. Não permitir autoelevação de permissões.
9. Guardar lição no conhecimento do Menor quando o resultado for confirmado.

## 5. Diagnóstico proativo e decisões verificáveis

Criar coletores semânticos de eventos (erro de interface, erro de validação,
latência do router, falha do Ollama, falha de ferramenta, saúde do sistema).
Executar checagens agendadas de maneira **local e controlada**, sem inundar
o modelo nem iniciar tarefas irrestritas. Agrupar erros semelhantes por hash.
Ação automática permitida: sugerir teste, registrar problema, diagnosticar
módulo isolado e produzir proposta de PR. Ações sensíveis exigem aprovação.

Os cenários das capturas do iPhone viram testes permanentes de regressão.
Fases de refinamento:
- R1: respostas curtas, roteamento robusto e interface mobile sem overflow.
- R2: trilha de decisões, recibos de execução e gerenciamento de falhas.
- R3: ferramentas reais com permissões, limites e dry-run.
- R4: plano/patch/teste/PR em sandbox, com revisão humana.
- R5: backup/restore testado, rollback de deploy, monitoramento e alertas.
- R6: métricas de qualidade no Ollama real e testes adversariais em ambiente local.

## 6. Critérios de qualidade e aceite

- "ferramentas" como resposta a "em qual pasta?" salva apenas se a ação
  pendente for realmente uma anotação, com confirmação do caminho salvo.
- "sim"/"simm" confirma quando o destino é inequívoco; caso contrário,
  o Menor pergunta especificamente **onde** ou **o que executar**.
- "vamos criar ferramenta de imagens" inicia análise dos requisitos e informa
  objetivamente se falta um motor; **não** afirma que criou ferramentas.
- Não executar ações duplicadas ao reabrir conversa/recarregar.
- Nenhum vazamento de paths/dados; nenhuma tool fora do catálogo.
- Tela mobile sem rolagem horizontal em larguras 320/375/390px.
- Testes unitários + integração API + UI + GitHub CI, e validação humana no
  servidor local antes de declarar finalizadas as fases.

## 7. Riscos, restrições e ponto de controle

Qwen 7B local pode demorar, errar JSON e confundir intenções. Usar decisões
determinísticas para respostas curtas e modelo só para interpretação aberta.
Sem acesso à execução no notebook neste ambiente de GitHub, só é possível
confirmar CI remoto e revisão estática; validação de desempenho/segurança
no hardware fica pendente até evidência real do servidor.
Memórias do usuário ficam fora do Git; backups devem ser gerados e testados
com o mínimo de permissões, sem publicá-los como artefatos de CI.

## R7 — Fluxo de imagem e autoedição (PR #7)

Recebimento de pedido de imagem deve acionar geração/edição, pedir detalhes da cena
ou indicar provedor ausente, sem resposta genérica do Qwen. O estado pertence à conversa
no navegador; anexo discreto e resultado privado. Em desenvolvimento de código,
o Qwen pode sugerir patch em arquivos permitidos, mas o GitHub só recebe branch
com PR em rascunho após opt-in, e revisão humana continua obrigatória.

**Não concluído:** sandbox de execução autônoma, cron de diagnóstico,
rollback transacional e provedor local de imagens.

## R8 — Missões e subagentes locais

Testar aprovação antes de download, persistência após restart, isolamento dos
arquivos, verificação da imagem antes de declarar pronto e uso sem API externa.
A qualidade artística não é verificada pelo teste de integridade de pixels.
Implantar e medir desempenho no hardware Intel real antes de aceitar a fase.

## R9 — Critérios de aceite de skills e prevenção de falsos sucessos

- Quando a missão diz `ready` mas o runtime foi removido, a skill não pode
  ser oferecida como disponível.
- Critérios gerados pelo Qwen precisam aparecer no diálogo **antes** do aceite,
  sem transformar o plano em execução implícita.
- Se a geração retornar arquivo inválido, tentar novamente no máximo uma vez;
  depois reportar falha, não um resultado inventado.
- Salvar manual da skill apenas após prova real de teste; manter dados fora Git.
- Testes automatizados cobrem estas invariantes com modelos simulados.
- O modelo precisa ser testado no Ubuntu com Intel para aceite operacional.

## R10 — Subagente local isolado e recuperável

- A instalação de OpenVINO não modifica o .venv do chat.
- A geração só ocorre depois de missão aprovada, modelo completo e teste.
- Com download incompleto, o Menor informa a falha e pode retomar a preparação
  em uma missão autorizada, sem marcar a capacidade como pronta.
- Espaço insuficiente bloqueia o download; erros/timeouts geram falha explícita.
- O processo filho não herda tokens GitHub, chaves da API de imagens ou variáveis
  de conexão do Qwen. Somente instruções JSON aceitas são executadas.
- Testar inferência real de 512x512 no notebook antes de declarar operação pronta.

## R11 — Arquitetura pública dos agentes e implementação local (18/10/2026)

Esta análise usa documentação pública consultada nesta data. Os pesos, treinamento
e detalhes privados dos produtos não foram inspecionados. A implementação abaixo
reproduz padrões de orquestração, sem adicionar SDK externo ou trocar o Qwen.

| Referência oficial | Mecanismo documentado | Aplicação no Menor |
| --- | --- | --- |
| [Codex harness](https://developers.openai.com/blog/codex-as-a-platform) e [App Server](https://learn.chatgpt.com/docs/app-server) | Estado de conversa/turnos, ferramentas, aprovações e atividade exposta pelo servidor | O backend passa a possuir estado e recibos; a UI apresenta o resultado |
| [Claude tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) e [loops](https://claude.com/resources/articles/getting-started-with-loops) | Modelo pede ação, aplicação executa, resultado volta ao modelo; condições de parada | Loop local de até quatro passos, catálogo fechado e bloqueio de repetição |
| [Antigravity Artifacts](https://antigravity.google/docs/artifacts) | Planos, diffs e arquivos como entregas revisáveis | Plano da missão e critérios apresentados antes da autorização; arquivo só após verificação |
| [ChatGPT imagens](https://learn.chatgpt.com/docs/image-generation) | Ferramenta de geração/edição disponível na experiência de conversa | Capacidade do produto vem de executores reais, não de o modelo textual saber produzir pixels |
| [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling) | Chamadas estruturadas e resultados de ferramentas | Nesta etapa usa JSON validado, compatível com o runtime já adotado; não presume suporte nativo de qualquer modelo |

### Diagnóstico confirmado do print

O servidor respondia versão 0.3.0 e sua especificação OpenAPI não continha
`/agent/resolve`, imagens ou missões, apesar do checkout na revisão atual.
O processo mantinha módulos antigos em memória. O deploy executava testes que
podiam consultar o Ollama de produção antes de chegar ao restart.

O 404 tem evidência de incompatibilidade interface/API. A captura, isoladamente,
não revela o corpo exato de todas as chamadas. Não se atribui o erro a uma
suposta incapacidade dos pesos do Qwen.

### Incremento implementado

- `POST /agent/run`: autenticado, recebe conversa, identificador do turno,
  mensagem e histórico limitado. Mantém as rotas anteriores compatíveis.
- `GET /agent/runs/{session_id}`: consulta autenticada do estado da conversa.
- `src/agent/tasks.py`: estado e recibos no SQLite privado em
  `cerebro/memoria/agent.sqlite`. Transações serializam o início de cada conversa.
  Mesmo turno e conteúdo retornam o recibo anterior; ID reutilizado com conteúdo
  diferente é recusado. Aprovação pendente sobrevive à recriação do processo.
- `src/agent/runner.py`: inspeção de capacidade, coleta de requisitos, plano,
  autorização, execução e resultado. Leituras podem alimentar outro passo do
  modelo; escritas sempre mostram ferramenta e parâmetros antes de pedir aceite.
  Somente nomes e argumentos do registry são aceitos. Não aceita shell arbitrário.
- Limites: quatro passos, uma ação por passo, timeout de leitura de 45 segundos
  por inferência do planejador e bloqueio de chamadas repetidas no mesmo ciclo.
- Pedidos de imagens consultam a capacidade real. Sem runtime, oferecem planejar
  sua construção. Pedir software inicia missão; não grava uma ideia como substituto
  da execução. Um “sim” responde ao estado persistido, não cria permissão genérica.
- A interface chama o núcleo antes dos handlers anteriores para tarefas novas.
  Memória, anexos e missões antigas conservam seus fluxos durante a migração.
  Falha do núcleo não vira silenciosamente conversa genérica.
- `/health` publica `api_contract: 1`; a UI detecta API antiga e explica o problema.
  O HTML é servido sem cache. Isso identifica contrato, não revisão Git completa.
- Deploy usa diretório de dados temporário e Ollama indisponível nos testes:
  não consulta memórias reais nem disputa inferência com conversas de produção.
- Correções operacionais: edição externa de imagem sai do loop assíncrono;
  a fila filtra estados antes do limite e processa mais antigos primeiro;
  nova missão não apaga a instalação previamente verificada do catálogo.
- Controle instalado em `~/.local/bin/menor`: start, stop, restart, status.
  Stop pausa timers e workers; restart recarrega a API sem matar workers ativos.

### Critérios de aceite desta entrega

1. A frase “eai mano, conseguimos fazer uma imagem?” recebe capacidade real e
   pergunta objetiva; não cai em negação genérica do modelo.
2. “não conseguimos fazer uma ferramenta?” inicia missão; autorização de
   instalação só ocorre depois de requisitos e plano.
3. Repetir o mesmo turno confirmado não repete a ferramenta.
4. Recusar a proposta não executa escrita; ferramenta fora do catálogo é recusada.
5. Testes Python completos no Ubuntu, interface no Node e cenários Bash passam.
6. API reiniciada publica o novo contrato; o git pull sozinho não é aceite.

Validação em 18/10/2026: 147 testes Python no Ubuntu, 26 testes de interface
no Node, cenários Bash de deploy/controle e Flake8 com limite de 119 caracteres.
A conversa do print foi reproduzida no navegador com dados isolados: oferta de
capacidade, missão, coleta de requisitos e plano antes da aprovação; sem instalar
modelo nem consultar o cérebro de produção.

### Próximas entregas, por ordem e com limites claros

1. **Recuperação operacional:** guardar lease/heartbeat da execução e reconciliar
   tarefas interrompidas com artefatos antes de permitir nova tentativa.
   Aceite: encerrar processo após ação e antes do recibo não duplica efeitos.
2. **Executor programador:** worktree por tarefa, leitura/pesquisa/diff, comandos
   permitidos e testes em sandbox real, sem credenciais nem cérebro de produção.
   Aceite: tarefa pequena produz patch e teste verificável, sem tocar a main.
   O autoeditor atual continua limitado a draft PR com opt-in; não é esse sandbox.
3. **Eventos e revisão:** persistir eventos por ferramenta, transmitir progresso
   real e exibir plano, diff e evidências. Aceite: reconectar no meio da tarefa
   reconstrói o progresso sem chamar a ferramenta novamente.
4. **Contexto:** resumo por tarefa e orçamento de tokens medido no Ollama,
   separado de memória durável. Aceite: retomar projeto sem vazar outro contexto
   e sem perder decisões ao compactar.
5. **Confiabilidade:** backup/restore ensaiado, revisão de aprovação por risco e
   rollback de release. Aceite: restauração preserva notas, tarefas e autorizações.
6. **Hardware e avaliação:** medir latência, RAM e taxa de acerto das frases reais
   no Qwen/Intel antes de expandir ferramentas ou paralelismo.

Limites atuais: um processo interrompido durante uma ferramenta fica bloqueado,
sem replay automático; recibos não equivalem a transação distribuída com GitHub
ou APIs externas. Missões têm worker próprio; o loop de ferramentas é limitado
ao turno HTTP. Ainda não há terminal programador, browsing autônomo, sandbox
completo, retomada automática de execução interrompida ou equivalência de
inteligência com modelos proprietários. O banco de tarefas contém argumentos
necessários à aprovação e resultados; incluí-lo no backup privado, nunca no Git.

