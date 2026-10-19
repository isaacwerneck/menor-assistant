# MENOR INTELLIGENCE ENGINE — Arquitetura e roadmap

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

