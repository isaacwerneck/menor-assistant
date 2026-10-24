# Direção integrada Menor Assistant — trilhas A → B → C → D → E

**Atualização pós-plano (20/10/2026):** este documento continua sendo a visão e separação de responsabilidades; seu status de 19/10 foi superado pelos PRs até #84 e por medições reais de latência. Consulte o [estado A–E atual](handoff/03_FRENTES_A_B_C_D_E.md), [hardware e gargalos](handoff/02_HARDWARE_E_LATENCIA.md) e [backlog do Codex](handoff/06_BACKLOG_PRIORIZADO.md), sem confundir integração no Git com validação end-to-end. 


Atualizado em 19/10/2026. Esta é a visão operacional consolidada do proprietário,
reconciliando `PLANO.md`, `PLANO_REFINAMENTO.md` e `PLANO_INTELLIGENCE_ENGINE.md`.
As regras de segurança nesses documentos continuam obrigatórias.

## Visão de produto

O Menor é um **assistente agêntico local**, não um menu de comandos ou um chatbot
de palavras-chave. Ele deve interpretar mensagens de qualquer domínio através
do modelo, combinar pergunta atual, histórico, objetivo, projeto e memórias
relevantes; decidir responder, esclarecer, planejar, pesquisar ou sugerir ações
por ferramentas disponíveis e **verificar os resultados efetivamente obtidos**.

Seguir o padrão de trabalho de assistentes como Codex significa orquestrar
objetivos, ferramentas reais, checkpoints, revisão de código, testes e evidência,
não copiar modelos proprietários nem prometer equivalência em raciocínio.

**Separação de autoridades:** o LLM interpreta e propõe; o código valida,
autoriza e executa; o usuário controla consentimentos, capacidades sensíveis,
instalações, publicação, exclusões e mudanças operacionais. Recuperação de texto
de arquivos, buscas e memórias nunca concede privilégios. A autorização para
o chat responsável integrar seu próprio PR após CI verde não transfere essas
permissões ao modelo rodando no servidor.

## Estado real confirmado vs. não confirmado

- PR #67 integrou interpretação contextual, exemplos aprovados, navegação e
  monitor de leitura. Os CI da `main` foram aprovados. A implantação e a
  qualidade do Qwen no servidor continuam **não confirmadas**.
- A já tem memória de vários objetivos por conversa, recuperação idempotente,
  interpretação JSON validada, ferramentas supervisionadas e crítica de plano
  opt-in. **Não possui** equivalência Codex, executor geral em sandbox e ciclo
  longo autônomo comprovado.
- B tem contratos de análise de arquivos, imagem e subagentes; capacidade só
  vale quando o runtime está instalado e demonstrado.
- C tem CI, diagnósticos e contratos operacionais; observabilidade real e
  recuperação ensaiada ainda precisam de hardware.
- D tem interface conversacional e isolamento de turnos; falta validar múltiplos
  navegadores e duração longa em hardware real.
- E tem painéis privados e diagnóstico read-only; experiência de interface e
  integração com servidor precisam de aceitação no PC/iPhone.

Nenhuma fase será considerada **100% concluída** apenas por passar mocks no CI.

## A — Motor de inteligência e autonomia contextual (primeiro)

1. **Contexto pertinente:** recuperar fatos antigos por relevância textual/semântica,
   preservar origem, ordem e contexto do projeto explícito, limitar tokens e
   impedir vazamento entre projetos. Sem criar um if/else para cada assunto.
2. **Memória controlável:** preferências explícitas, exemplos corrigidos
   consentidos, estado de objetivos, proveniência e revisão de conflitos.
   Não treinar automaticamente pesos com chats privados.
3. **Raciocínio universal:** movimentos `answer`, `clarify`, `plan`,
   `continue`, `research`, `act`, `inspect_result` tipados e validados;
   ferramentas e permissões não são inferidas por palavras ou modelo.
4. **Missões duráveis:** checkpoints, dependências, orçamento de recursos, pausa,
   retomada e reconciliação sem replay de efeitos incertos. Não autorizar
   operações por respostas soltas ou notas recuperadas.
5. **Programador supervisionado:** investigação, plano, worktree/sandbox isolado,
   testes independentes, patch, PR, revisão e implantação controlada; nunca
   escrever no checkout de produção nem expor credenciais.
6. **Avaliação antes de declarar ganho de inteligência:** diálogos inéditos,
   perguntas factuais de retomada, troca de assunto, resistência a prompt
   injection, taxa de compreensão, custo de inferência e tempo no Qwen real.
7. **Otimização responsável:** modelos distintos opcionalmente por tarefa,
   orçamento de contexto e revisão opt-in quando CPU exigir. Não baixar ou
   habilitar modelos automaticamente.
8. **Limites que impedem chamar 100%:** benchmarks reais do hardware,
   recuperação multipasso, sandbox programador validado e segurança sob
   interrupção, tarefas de horas/dias e isolamento.

### Aceite mínimo de cada incremento A

- “Qual sistema operacional do meu servidor?” depois de assunto não relacionado
  responde o fato anterior se estiver presente, sem repetir o resumo inteiro.
- “Planeje melhorar a interface” elabora plano, não ativa autocorreção.
- “Corrija” propõe ação supervisionada conforme contratos e autorizações.
- Correções aprovadas relevantes orientam novas mensagens; correções de outros
  assuntos não contaminam a resposta.
- Duas conversas/projetos não vazam dados uma para outra.
- Nenhuma falha ou duplicação gera execução automática de ferramenta.
- CI Python/Node/Bash verde, avaliação Qwen real separada e resultados registrados.

## B — Ferramentas e subagentes (após a base A)

Integrar arquivo e visão ao agente com proveniência e seleção de evidências,
suportar imagem gerar/editar mediante runtime disponível, OCR opt-in,
transcrição/voz e pesquisa controlada; incluir limites de dados, licenças,
custo de CPU/RAM, sandbox e recibos. Ferramentas não instaladas não aparecem
como operacionais.

## C — Confiabilidade e avaliação independente

Telemetria privada e sanitizada, desempenho, alertas, auditoria, monitor SSH,
backups/restauração com testes, rollback, análise de regressões, benchmarks
entre versões. Corrigir erros de PR antes de merge e nunca mascarar falhas
reduzindo a cobertura. Monitor passivo não equivale a speed test externo.

## D — Conversa e execução supervisionada

Mensagens naturais, renderização de evidências, estado visual das ações e
aprovações explícitas. Navegação entre chats durante geração, cancelamento
do cliente sem falsa promessa de cancelar efeito do servidor, edição contextual,
progresso real e isolamento de respostas tardias. Não competir com o redesign E
pelos mesmos arquivos sem coordenação.

## E — Experiência PC/iPhone e integração privada

Manter o visual escolhido pelo usuário como referência (não reiniciar seleção
de oito layouts). Redesign mobile-first e desktop consistente, performance,
acessibilidade, exibição de projetos, arquivos e saúde do modelo, conexão
segura ao Ubuntu com autenticação e privilégio mínimo. Nenhum shell remoto
exposto na web só para conveniência.

## Forma de entrega

Cada frente tem pacote de mudanças coeso e PR verificável; o usuário prefere
entregas substanciais, não commits decorativos. Revisar diff, conflitos,
credenciais, regressões e CI. **Somente fazer merge após todos os checks
necessários passarem**, e conferir SHA da `main` depois. Deploy do Ubuntu é
separado e exige checagem operacional. Não afirmar tarefas futuras como já
feitas, e não prometer execução em segundo plano sem um serviço real.

## Dependências

A fornece interpretação/orquestração → B fornece ferramentas reais → C prova
confiabilidade → D expõe diálogo e autorizações → E apresenta experiência final.
Os contratos A/B/C devem poder evoluir em paralelo quando arquivos não conflitam.

## Achievements do GitHub: contribuições genuínas

Os merges reais de PRs **podem** contar para Pull Shark e, dependendo de
atribuição/autoria e revisão, outras conquistas. O GitHub decide o crédito
de cada conta; jamais reivindicar badge apenas pela API ter criado um PR.
Co-autoria só com um colaborador verdadeiro; nunca forjar trailers Git.
Issues/reviews são registrados porque resolvem problemas, não para manipular
Quickdraw ou YOLO. Galaxy Brain requer respostas genuinamente aceitas;
Starstruck depende de terceiros; Public Sponsor envolve pagamento e
autorização própria. Não criar repositórios, stars falsas ou despesas por badges.
