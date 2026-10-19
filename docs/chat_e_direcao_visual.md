# Chat E — Direção visual única e contrato de interface

> Decisão do proprietário, 19/10/2026. Referência funcional: PRIMEIRA montagem de oito telas apresentada na conversa do projeto Menor AI. **Não** usar a segunda montagem de oito estilos como desenho final.

## Direção aprovada

**Menor AI · Quiet Intelligence**: arquitetura de produto completa da primeira montagem, com personalidade sóbria e pouco ruído.

- Base: cinza grafite/azul-noite, **roxo suave como acento opcional dominante** (não azul elétrico obrigatório); branco levemente quente e cinzas legíveis.
- Referências: o modelo de PC e celular da primeira montagem, **não** o layout futurista neon, brutalista, neon-noir, gradiente carnavalesco ou glass integral.
- Minimalismo funcional: sem excesso de emojis, badges, cards, gradientes, brilhos, sombras ou ícones; priorizar hierarquia de texto, espaçamento e conteúdo.
- Fluid glass **moderado**: transparência/blur apenas em barra superior, modais e superfícies flutuantes; não reduzir contraste de texto e nunca sobrecarregar a conversa.
- Componentes suaves: bordas discretas, cantos de 10–16px, largura de leitura controlada, tipografia de sistema, ícones simples e coerentes, controles de toque de no mínimo 44px.
- Responsivo: desktop com barra lateral e área central; celular com chat em primeiro plano, navegação compacta e margens seguras no Safari/iOS. Respeitar `prefers-reduced-motion`.

## Inventário exato da primeira montagem (todas as telas)

### 1. Desktop — Chat principal

- Marca Menor AI; barra lateral com Chat, Objetivos, Tarefas, Projetos, Arquivos, Ferramentas, Imagens, Subagentes, Sistema.
- Lista de conversas recentes e ações de abrir/criar conversa, acesso ao perfil.
- Barra superior com navegação e ações compactas.
- Mensagens de usuário e assistente, anexos, imagens geradas e respostas em texto/código.
- **Card de execução/objetivo**, com etapas, checks, estado real e lista de arquivos modificados; não simular tarefas nem arquivos.
- Campo de composição com anexos, enviar e, **quando houver suporte no backend**, seletor de modo/capacidade.
- Os itens de navegação dependentes de APIs ainda inexistentes devem ficar documentados, não virar links quebrados ou painéis com dados fictícios.

### 2. Desktop — Objetivos e Tarefas

- Filtros Todos / Em andamento / Concluídos / Planejados.
- Lista de objetivos com descrição, status real, progresso por etapas **apenas quando o backend expuser critérios e contagens confiáveis**.
- Checklist de marcos, prioridade e retomada. Percentual não deve ser inventado a partir do texto livre.
- Possibilidade de abrir um objetivo e consultar recibos; criação/edição submetida às permissões existentes.

### 3. Desktop — Projetos e Arquivos

- Navegação entre projetos reais, arquivos, imagens e documentos; filtros por tipo (documentos, código, imagens, planilhas).
- Cards de projetos, lista de arquivos recentes, detalhes da origem, tamanho/data quando fornecidos.
- Analisar, recuperar contexto, editar/excluir **apenas** mediante rotas já autenticadas e confirmações existentes.
- Acesso à interface atual `/files/view` e ao modal de projetos até existir navegação unificada.

### 4. Mobile — Chat

- Cabeçalho compacto Menor AI, histórico via menu, avatar discreto.
- Mensagens legíveis, anexos, saída de imagem, ações rápidas que executem funções reais.
- Compositor fixado de forma segura e navegação inferior compacta; sem duplicar ações da barra superior.
- Priorizar performance e evitar rolamento horizontal e teclado sobrepondo conteúdo.

### 5. Mobile — Objetivos

- Filtros e cards de planos com andamento verificado, etapas abertas/concluídas, detalhes e retomada.
- Não exibir porcentagens fictícias ou cronogramas simulados.

### 6. Mobile — Sistema

- Estado da API e Ollama, modelos instalados, timer de autodeploy, CPU, RAM, armazenamento, histórico de deploy e logs.
- Cada indicador deve ter origem explícita, hora de coleta e valor `indisponível` quando faltar telemetria.
- Status de GitHub Actions **não** comprova a revisão implantada no Ubuntu.

### 7. Mobile — Imagens

- Entrada para gerar/editar, histórico de resultados efetivamente emitidos, referência ao último resultado, estados de preparação/falha.
- Filtros e estilos só se houver suporte real. Não fingir que um modelo visual está instalado.
- Preservar as correções do Chat D para refinamentos naturais e ausência de confirmações redundantes.

### 8. Mobile — Ferramentas

- Catálogo por capacidade real: análise de documentos, visão local, pesquisa web, código supervisionado, gerenciamento de arquivos, subagentes.
- Estados disponível / precisa configurar / indisponível obtidos de contratos existentes; pedidos sensíveis continuam exigindo autorização.
- Não habilitar ações que o backend não execute nem expor terminal irrestrito.

## Inventário transversal de componentes

1. Marca tipográfica, cores e tokens semânticos; estados de foco/hover/disabled/error/success.
2. Sidebar com conversas e navegação (links apenas para funcionalidades reais).
3. Barra superior: título contextual, acesso a projeto, memória, exportação e estado do modelo.
4. Chat: mensagens, avatars discretos, code/pre, imagens, indicadores de streaming e erros.
5. Compositor: textarea flexível, anexos, botão enviar, informações de conexão.
6. Cards de objetivos, tarefas e recibos; filtros; vazios e estados de carregamento.
7. Projetos/arquivos: cards, listas, tags por formato, preview e confirmação de exclusão.
8. Sistema: indicadores temporais, status sem falso verde, logs e revisão implantada.
9. Painéis/modais de login, conhecimento, projeto; responsivos e acessíveis.
10. Navegação móvel, áreas seguras, controles com rótulos, teclado e movimento reduzido.

## Fronteiras entre chats

- **A**: interpretação, objetivos, memória, agente e planejamento; E consome APIs, não altera decisão.
- **B**: modelos, vision, arquivos e ferramentas; E consome rotas, não muda parsers/workers.
- **C**: deploy, observabilidade, smoke/doctor e segurança; E apenas apresenta telemetria disponibilizada.
- **D**: lógica de conversas, aprovação e imagens; E não substitui `sendMsg`, agentes ou fluxos de refinamento.
- **E**: tokens, layout, responsividade, interação de navegação e integração visual.
- Sempre desenvolver em branch `feat/chat-e-*`, testar e abrir PR. Por autorização posterior do proprietário, o Chat E pode mesclar **somente seus próprios PRs** após revisão de escopo, CI obrigatório aprovado, branch atualizada, ausência de conflitos e regressões conhecidas. Não executar deploy, restart, instalação de modelos nem alterações destrutivas; nunca escrever diretamente na `main`. O Chat D continua coordenando conflitos entre frentes.

## Ponte futura de diagnóstico remoto (escopo E, não implementada por este documento)

Objetivo: tornar o Ubuntu, Ollama e a API **inspecionáveis mediante autorização** a partir de uma interface/integração visível neste chat. O ChatGPT no celular não herda acesso ao Wi-Fi; SSH direto e execução autônoma prolongada continuam fora do escopo.

Arquitetura de aceite em fases:

1. Diagnósticos **somente leitura**, com comandos predeterminados (`ops.doctor`, `ops.smoke`, revisão implantada, versões de API/Ollama, testes sintéticos com dados descartáveis), timeouts, limites de CPU e sanitização.
2. Transporte autenticado de solicitações e recibos com expiração, identidade verificada, nonce contra replay e canal de retorno auditável. Não confiar em textos livres de issues/PR como comandos. Não embutir chaves no browser ou Git.
3. Aprovação explícita do proprietário para testes que usem CPU intensivamente ou modifiquem estado. Sem shell arbitrário ou alterações de produção. Logs limitados e sem dados privados.
4. Painel de diagnósticos com diferença entre `código presente`, `revisão instalada`, `serviço ativo` e `comportamento testado`.
5. Testes de ameaças (autorização, replay, payload adulterado, isolamento e vazamento), CI e validação **real** no notebook antes de declarar a ponte disponível.

O canal de transporte definitivo requer configurar a conexão do servidor e autorizar credenciais com escopo mínimo; até lá, sem alegação de conexão remota funcional.

## Entregas graduais e critérios de aceite

- **E1**: tema visual único, marca, cabeçalho, sidebar e mobile, mantendo todos os testes atuais.
- **E2**: navegação integrada para recursos existentes e componentes compartilhados com a tela de arquivos.
- **E3**: objetivos/tarefas e estados com contratos de API reais, sem dados falsos.
- **E4**: projetos, imagens, ferramentas e sistema com fontes verificadas.
- **E5**: ponte restrita de diagnóstico, testes de segurança e instalação comprovada no Ubuntu.
- **E6**: revisão de acessibilidade, iPhone/Safari, desktop, CI, regressões do Chat D, rollback e aceite visual.

**100% só quando** todas as telas estiverem implementadas, conectadas a capacidades verdadeiras, testadas em desktop e iPhone, sem falhas regressivas, e a ponte responder a diagnósticos reais autorizados no servidor. Este PR inicial entrega **somente E1**.
