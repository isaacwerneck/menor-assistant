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
