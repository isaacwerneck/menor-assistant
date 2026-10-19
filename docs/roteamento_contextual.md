# Roteamento contextual e ações reais (prévia da Fase 2)

Esta entrega implementa um orquestrador pequeno e conservador em `src/agent/router.py`.
Ele usa o modelo local do Ollama para entender a intenção e as últimas 6 interações.
Pedidos diretos de imagem/ferramenta passam primeiro por regras compartilhadas com
o núcleo, para impedir que sejam confundidos com autorização de salvar memória.

## Decisões possíveis

- **chat**: pedido comum; envia ao modelo para responder. Não presume memória.
- **save**: registra automaticamente preferência ou aprendizado explícito e claro,
  somente quando a decisão é de alta confiança e o conteúdo é trecho literal da fala.
  A interface confirma o **caminho real** usado. Se houver dúvidas, pergunta.
- **ask**: pergunta onde guardar a ideia e apresenta categorias: preferência, conhecimento,
  projeto ou ferramenta. Nada é gravado antes da escolha.
- **create_project**: pedido claro para iniciar projeto nomeado cria de verdade
  `~/menor-data/cerebro/projetos/<nome-seguro>/` e arquivos `contexto.md`,
  `tarefas.md`, `decisoes.md`, `diario.md` e a pasta `arquivos/`.

## Exemplos

| Usuário | Comportamento |
| --- | --- |
| 'Prefiro respostas curtas e objetivas' | Pode registrar preferência clara |
| 'Tive uma ideia de jogo de corrida' | Pergunta se deve anotar e onde |
| 'Crie um projeto novo chamado Cidade Noturna' | Cria pasta e arquivos de projeto |
| 'Vamos criar uma ferramenta para gerar sprites' | Inicia missão, coleta requisitos e pede aprovação; não afirma que já construiu a skill |
| 'Crie uma imagem agora' | Trata como tarefa; se não existir ferramenta, explica a limitação |

## Correções de conversa em 18/10/2026 — versão 0.4.1

- Pixel art, pixel-art e sprites são reconhecidos como imagens. Pedir uma ferramenta
  de pixel art inicia uma missão de `images.generate`, com requisitos e aprovação.
- Um novo pedido atendido por `/agent/run` encerra a pergunta antiga de memória na
  interface, sem salvar a ideia. Se o agente não assumir o pedido, a resposta de
  memória continua disponível, incluindo confirmação e pasta explícitas.
- O classificador e o resolvedor também protegem pedidos de ação: criar uma imagem
  ou uma ferramenta não vira autorização de guardar uma nota.
- Perguntas durante `awaiting_approval` usam os dados do plano e o modelo local para
  explicar a proposta. `/agent/missions/{id}/question` atende conversas antigas;
  o núcleo usa a mesma implementação. Nenhuma dessas consultas altera aprovação,
  fila ou requisitos. Se a inferência falhar, informa a falha e apresenta os fatos.
- A explicação distingue reserva de 5 GB do tamanho do download. Não promete tempo
  de geração nem qualidade de pixel art sem teste. Somente sim/não no fluxo de
  aprovação muda a decisão. Não há nova biblioteca nem instalador nesta correção.

## Segurança, limites e próximo passo

- O Qwen apenas propõe uma ação estruturada. O backend valida tipo, destino,
  nome e limites; não executa shell, não escreve código e não usa caminhos
  arbitrários indicados pelo modelo.
- Todas as ações exigem a sessão autenticada que já existe.
- Escritas continuam exclusivamente em `MENOR_DATA_DIR` fora do Git.
- Se o classificador falhar, o chat continua **sem salvar nada**.
- Há uma chamada extra ao modelo antes de gerar a resposta normal, o que pode
  aumentar a latência no hardware local; medir durante os testes no notebook.
- Nem toda classificação será correta. O registro confirmado aparece no chat
  e deve poder ser revisado ou removido em versão posterior.
- Projetos criados automaticamente devem ter nome claro, derivado da fala; caso
  contrário, perguntar. Não sobrescreve projetos já existentes.
- A pasta `ferramentas/` recebe propostas; criar, testar, versionar e executar
  **ferramentas Python reais** requer o agente programador isolado da Fase 5.
- Índice SQLite/FTS e recuperação automática de conhecimentos seguem em
  desenvolvimento, em entrega separada; ainda não fazem parte desta branch.

## Testes

Executar o fluxo GitHub Actions deste PR; depois do merge, testar pelo celular
na rede local e observar os caminhos mostrados nas confirmações. Não é necessário
executar `git pull` manual se o timer de deploy estiver funcionando.
