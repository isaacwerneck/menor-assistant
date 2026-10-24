# PLANO DE REFINAMENTO — Qualidade, autonomia e autoaperfeiçoamento do Menor

**Atualização de status — 20/10/2026:** preserve as hipóteses e contratos abaixo, mas priorize as falhas reais e medições do [handoff de Codex](docs/handoff/00_COMECE_AQUI_CODEX.md). As melhorias de linguagem, avaliação e segurança do PR #84 estão integradas no código; ainda aguardam comparação experimental A/B no Ubuntu. 


> **Direção consolidada em 19/10/2026:** [Plano integrado A–E](docs/plano_integrado_a_e.md).
> O Menor interpreta por modelo e contexto, não por palavras isoladas; aprendizado
> é supervisionado e nenhuma inferência concede permissão. A lista histórica
> abaixo preserva decisões e entregas anteriores, mas não é comprovação de 100%
> nem substitui critérios atuais de aceite e validação no Ubuntu.


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
| [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling) e [structured outputs](https://docs.ollama.com/capabilities/structured-outputs) | Chamadas estruturadas e schema de saída imposto pelo runtime | Schema JSON restringe ação, nome da ferramenta e formato dos argumentos; validação adicional no backend |

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

O teste com o Qwen real revelou que JSON genérico podia copiar literalmente
`tool|answer` e retornar argumentos como lista. O planejador agora envia schema
JSON ao Ollama com ações e argumentos restritos ao catálogo, além de exemplos
válidos no prompt. A validação do backend permanece obrigatória.

Validação em 18/10/2026: 148 testes Python no Ubuntu, 26 testes de interface
no Node, cenários Bash de deploy/controle e Flake8 com limite de 119 caracteres.
A conversa do print foi reproduzida no navegador com dados isolados: oferta de
capacidade, missão, coleta de requisitos e plano antes da aprovação; sem instalar
modelo nem consultar o cérebro de produção. Com o Qwen real, “Liste meus projetos”
executou `projects.list` em dados temporários e concluiu usando o recibo observado.
Start/stop/restart foram exercitados no servidor; API 0.4.0 e timers voltaram ativos.

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


## R12 — Assistente autônomo de pesquisa, estudo, construção e autoevolução

Pedido do proprietário em 18/10/2026: aproximar o fluxo do Menor ao de um
assistente de desenvolvimento como Codex. Receber um objetivo, investigar como
cumpri-lo, apresentar fatos e alternativas, criar recursos que faltam, reutilizar
esses recursos e propor melhorias do próprio sistema. O proprietário revisa
a branch e aprova a incorporação. A inspiração é o fluxo de trabalho; não é
promessa de equivalência de inteligência, desempenho ou acesso a ferramentas.

### Proposta anterior, preservada integralmente por solicitação do proprietário

O texto abaixo registra a mensagem da conversa antes da implementação.
A frase sobre não ter alterado código descreve aquele momento, não o estado atual.

**Sim, menor: dá para criar uma ferramenta própria que abre um navegador no servidor, pesquisa e lê os sites.** Minha pergunta anterior limitou demais as opções.

Podemos seguir estes caminhos, inclusive combinando alguns:

| Caminho | Como funciona | Principal limite |
|---|---|---|
| **Navegador próprio** | O menor controla Chromium com Playwright: escreve pesquisas, abre resultados, segue links e lê páginas. Funciona sem uma janela visível no servidor. | Exige instalar navegador e automação. [Playwright](https://playwright.dev/python/docs/library) |
| **SearXNG no servidor** | Um serviço gratuito reúne resultados de outros buscadores e os entrega ao menor. | Precisa manter outro serviço; continua dependendo dos buscadores consultados. [SearXNG](https://docs.searxng.org/) |
| **API de pesquisa** | Um serviço entrega resultados estruturados, sem precisar controlar a página de um buscador. | Depende das condições, credenciais e limites do fornecedor. O próprio Ollama oferece pesquisa e leitura de páginas com conta e chave. [Ollama](https://docs.ollama.com/capabilities/web-search) |
| **Leitor de documentação** | A ferramenta acessa fontes conhecidas diretamente, como a documentação de uma linguagem. | Ajuda a estudar essas fontes, mas precisamos de busca para descobrir outras. |

No navegador, **não precisaríamos contratar uma API de busca**, mas isso não garante acesso ilimitado: o Google, por exemplo, pode apresentar CAPTCHA ao detectar consultas automatizadas. [Explicação do Google](https://support.google.com/websearch/answer/86640?hl=pt-BR)

Sobre um “modelo de pesquisa”: podemos usar um modelo para decidir **o que pesquisar, quais páginas ler e quando buscar mais evidências**. Ele ainda precisa de uma ferramenta que acesse a internet. O Ollama suporta esse fluxo de chamadas de ferramentas. [Documentação](https://docs.ollama.com/capabilities/tool-calling)

**Para o menor, eu começaria com leitor de páginas + navegador sob demanda**, aproveitando o modelo local. Minha proposta de funcionamento seria:

1. Você pede algo; ele consulta a memória e identifica o que precisa confirmar.
2. Pesquisa, abre as fontes e prioriza documentação oficial.
3. Responde com referências e admite quando a evidência é insuficiente ou contraditória.
4. Quando você pedir para estudar, organiza o material em `conhecimentos/programacao/`, com fonte, data, versão e limitações.
5. Ao desenvolver uma ferramenta, cria o código e verifica seu funcionamento antes de registrá-la como disponível.

Esse “aprendizado” inicialmente seria **memória persistente consultada nas próximas tarefas**. Treinar os pesos do modelo seria outro processo. E salvar uma explicação sobre programação não provaria que ele já consegue executar corretamente qualquer programa.

Ainda não alterei código nem instalei dependências. Certeza absoluta não é garantível; o objetivo é exigir evidências e reconhecer o que não foi confirmado.

### Fluxo completo desejado

1. **Entender e contextualizar:** recuperar preferências, projeto selecionado,
   capacidades instaladas e conhecimentos pertinentes; manter dados privados locais.
2. **Avaliar lacunas:** distinguir conversa/criação livre de dúvidas factuais;
   pesquisar informações atuais, APIs, versões e qualquer ponto sem evidência.
   A confiança declarada pelo modelo não é prova.
3. **Investigar:** formular consultas, descobrir fontes, abrir páginas completas,
   seguir referências e reformular a busca quando faltar informação. Priorizar
   documentação oficial para programação; fóruns e exemplos são complementares.
4. **Conferir:** confrontar afirmações com trechos reais, versões e datas;
   registrar contradições e falhas de acesso. Nunca converter ausência de fonte
   em resposta inventada. Citação existente não prova interpretação correta.
5. **Responder:** separar fatos sustentados, inferências e lacunas. Apresentar
   fontes consultadas e explicar como executar a solução. Admitir impossibilidade
   de confirmação quando necessário; nenhuma promessa de certeza absoluta.
6. **Estudar:** a pedido, organizar conceitos, documentação, exemplos e exercícios
   em conhecimentos por assunto, com origem, data, versão e limitações.
   Retomar o material em tarefas futuras e revalidar informações que envelhecem.
7. **Construir:** identificar capacidade ausente, definir contrato, gerar código,
   testes e documentação. Executar apenas em ambiente isolado; falha de teste
   impede tratar a ferramenta como pronta.
8. **Revisar e incorporar:** preparar branch `codex/`, testes, diff e PR rascunho.
   O proprietário revisa e decide o merge. Somente código incorporado e validado
   passa a compor o catálogo executável após reinício.
9. **Usar e aprender com a execução:** resolver novas tarefas com recursos
   aprovados; registrar falhas sem segredos e converter problemas reproduzíveis
   em testes e propostas de melhoria.
10. **Autoanalisar:** observar recorrência de falhas, propor causas e correções
    mensuráveis, testar e abrir nova branch. Não elevar as próprias permissões,
    alterar produção, fazer merge ou treinar os próprios pesos automaticamente.

### Incremento implementado no checkout

- `web.search`: HTML público do DuckDuckGo com fallback para feed RSS público do Bing,
  sem chave ou API paga. Integrações públicas podem mudar ou encontrar bloqueios/CAPTCHA.
- `web.read`: texto de HTTPS público com limites de tamanho, protocolos e
  redirecionamentos; DNS é validado e a conexão usa o IP validado com TLS no hostname.
- `web.browse`: Chromium opcional com Playwright, contexto descartável, sem
  sessão do proprietário, downloads ou WebSockets; requisições passam pelo leitor
  de endereços públicos. Não é um navegador com login ou controle irrestrito.
- Pesquisa explícita no núcleo e nos endpoints de chat. A classificação automática
  de dúvidas usa `MENOR_AUTONOMY_ENABLED=1`; desligada por padrão para implantação
  controlada e compatibilidade. Falha de pesquisa/validação resulta em incerteza.
- Estudo explícito com `estude`/`aprenda` salva notas em
  `conhecimentos/programacao/estudo-<hash>.md` ou `conhecimentos/pesquisas/`.
  Fonte, data e limitações são preservadas; o índice textual passa a incluir essas notas.
- No máximo cinco resultados e leitura das três primeiras fontes por pesquisa.
  Síntese de até três fatos, com checagem de existência literal das citações.
  Não há garantia automática de verdade, autoridade da fonte ou implicação semântica.
- `developer.build`: proposta de ferramenta pura `run(text) -> str`, testes unittest,
  documentação e catálogo em draft PR. Testes em container sem rede, sem credenciais,
  sistema de arquivos de leitura e cotas de CPU, memória, processos e tempo,
  antes de qualquer mutação no GitHub. Docker/imagem ausentes bloqueiam a proposta.
- Catálogo `custom.<nome>` carregado somente do código local revisado e incorporado;
  a ferramenta nova não é importada durante sua geração nem diretamente do cérebro.
- Autoanálise no chat pode consultar `system.diagnose` e propor `developer.propose`.
  O autoeditor existente permanece restrito aos arquivos permitidos; fixa a revisão
  de origem antes de gerar a branch e declara testes comportamentais pendentes de CI.
- Conteúdos privados do cérebro não são anexados automaticamente ao código/PR.
  O objetivo solicitado e o código proposto são enviados à integração GitHub autorizada.

### Próximos marcos e critérios de aceite

- **Pesquisa iterativa:** reformular consultas e seguir links por orçamento de
  páginas, tempo e tokens. Aceite: resolver pergunta que a primeira busca não cobre.
- **Qualidade das fontes:** identificar documentação oficial, versões conflitantes
  e informação desatualizada. Aceite: não misturar APIs de versões diferentes.
- **Estudo progressivo:** currículo por assunto, exemplos, exercícios executados
  em sandbox e revisão de erros. Aceite: retomar estudo e distinguir material lido
  de habilidade demonstrada por teste.
- **Programador geral:** snapshot/worktree do projeto, dependências aprovadas,
  edição de múltiplos arquivos, lint e testes do projeto em sandbox completo.
  Aceite: implementar uma feature real sem tocar produção ou expor credenciais.
- **Autoeditor com testes completos:** reproduzir a falha e executar a suíte do
  snapshot antes de commit/PR, além de CI. O autoeditor legado ainda não faz isso.
- **Autonomia persistente:** fila, cancelamento, eventos, retomada segura e cotas
  entre turnos; estudo agendado apenas com objetivo e autorização definidos.
  O incremento atual não inicia estudo infinito ou rotina em segundo plano.
- **Avaliação do modelo:** medir acerto, abstenção, citações inválidas, ferramentas
  escolhidas, latência e RAM no servidor real. Comparar modelos compatíveis com o
  hardware antes de escolher mudanças. Mais memória não substitui um modelo melhor.
- **Liberação:** revisão humana, CI, backup, deploy, teste de saúde e rollback
  verificado. Nunca usar o texto de uma página como autorização operacional.

Os procedimentos de ativação ficam no README e em
[busca de conhecimentos](docs/busca_conhecimentos.md). A validação no servidor,
com Qwen, Chromium e Docker reais, é um aceite separado dos testes com mocks.

### Evidências desta implementação no ambiente de desenvolvimento

- Leitura real da documentação Python e busca pública foram exercitadas.
  A busca HTML recebeu HTTP 202; o fallback Bing RSS devolveu resultados.
- Testes locais cobrem rede privada/DNS, IP fixado com TLS, citações inválidas,
  memória, índice, endpoints de chat, catálogo, branch atômica, recusa de execução
  sem opt-in, falha e timeout do sandbox.
- Flake8 e testes de interface são executados separadamente.
- A suíte Python existente depende de permissões POSIX e falha neste Windows
  por `os.fchmod`, modos e privilégios de symlink; precisa rodar no Linux/CI.
- O Docker real foi bloqueado pela allowlist da ferramenta de shell deste ambiente.
  O navegador Chromium e o Qwen reais ainda precisam de aceite no servidor.

## R11 — Incidente de autorização (regressão dos prints)

Cenário: usuário informa requisitos de imagem pixel art, faz perguntas sobre
CPU/modelo e depois autoriza explicitamente. O sistema não pode responder
que nenhuma aprovação existe quando uma missão ainda aguarda autorização.

Critérios automáticos:

1. Perguntar `que aprovação?` explica o download e deixa a missão inalterada.
2. Dizer `eu aprovo` ou `pode instalar` transforma
   `awaiting_approval` em `queued` uma única vez, sem alegar instalação.
3. Consultar `conseguimos fazer?` após o aceite retorna estado persistido,
   não uma promessa do modelo de texto.
4. Skill gerada só roda em Docker isolado, sem rede, sem chaves, sem permissões
   de escrita no host. Sem Docker a execução não ocorre.
5. Logs falsos de testes não são comprovante de aprovação de um patch.
6. Dados privados detectáveis bloqueiam a pesquisa externa, inclusive quando
   sugeridos por um LLM; assumir que o filtro não cobre todos os segredos.

Ainda é necessário medir comportamento no notebook real após merge.
## R12 — Entendimento universal e avaliação

Cobrir mensagens de gêneros inéditos, mudança de assunto, correções de objetivo,
perguntas incompletas, modelo lento/offline e tentativas de executar algo sem
permissão. O cérebro não deve inventar execução nem salvar automaticamente
exemplos para treinamento. Separar score de intenção de sucesso real da tarefa.
Comparar versões do Qwen com desafios inéditos e evitar otimização apenas dos
prints fornecidos pelo usuário.

## R14 — Incidente: textura em vez de mago 32×32 e perda de contexto

Regressões independentes do assunto: (1) pedir artefato com resolução explícita;
(2) garantir dimensões reais e recibo de arquivo; (3) perguntar em linguagem
natural pelo último resultado após reiniciar o servidor; (4) não negar ter
executado ferramenta com comprovante persistido; (5) nunca confundir
integridade do arquivo com fidelidade visual; (6) comparar várias alternativas
antes de tratar catálogo fixo como universo de modelos; (7) nunca instalar
candidato sem integrador auditado e autorização.

A cobertura de CI usa mocks; a qualidade de personagens e sprites ainda
precisa de imagem real e avaliador visual confiável no hardware.


## R19 — Regressões de planejamento em vários assuntos

Verificar transições entre documentos, música, robótica e dúvidas incidentais,
sem prefixos de comando. Testar retomada com IDs reais e recusar IDs falsos.
Confirmar que uma pergunta paralela não apaga o plano, que o modelo offline
não cria estado incorreto e que uma aprovação de escrita não executa antes
do consentimento. Verificar duplicação de turnos e logs sem segredos.

Métricas de falhas são observabilidade, não prova de melhoria cognitiva;
a avaliação qualitativa real do Ollama segue pendente no hardware.

## R21 — Revisor de plano independente, sem confiança cega

A revisão com segundo modelo local é um parecer, não uma garantia. A saída é
validada por contrato estruturado e não pode selecionar ferramenta ou liberar
aprovação. Na divergência, permite UMA reformulação sem efeitos colaterais;
se persistir dúvida, a proposta é identificada como preliminar.

Próximos testes: criar benchmarks inéditos de mudança de domínio, qualidade
factual, latência no i7, consumo de RAM e risco de crítico superconfiante.
Manter revisão desabilitada por padrão até essa validação real.
