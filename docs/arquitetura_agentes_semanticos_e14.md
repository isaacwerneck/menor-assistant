# E14 — Entendimento semântico, agente e ferramentas (21/10/2026)

## Problema observado
Usuário: "tô querendo fazer um jogo 2D que rode na web".
Resposta incorreta do Menor: aprovação de `developer.propose` para alterar
seu próprio código num PR. Nenhuma criação de jogo foi solicitada naquele
turno; a intenção era discutir o projeto. O catálogo misturava ferramentas
de projetos pessoais e de manutenção do assistente. Além disso, expressões
regulares em `runner._advance` decidiam sobre colaboração e geração de
jogos antes da inferência do modelo, produzindo comportamento por palavras
em lugar de interpretação contextual.

## Pesquisa em documentação pública

- Codex Agent Loop, OpenAI:
  https://openai.com/pt-BR/index/unrolling-the-codex-agent-loop/
  O modelo emite resposta ou chamada de ferramenta; o harness executa,
  devolve observação, repete até resposta final. Contexto e ambiente de
  trabalho são gerenciados fora da inferência. Não é um dicionário de gatilhos.
- OpenAI, function calling:
  https://developers.openai.com/api/docs/guides/function-calling
  Ferramentas possuem esquemas. O modelo propõe argumentos; aplicativo executa
  e devolve resultado; executor mantém autorização e validação.
- Gemini:
  https://ai.google.dev/gemini-api/docs/function-calling
  Funções declaradas, execução pela aplicação, chamadas sequenciais e
  paralelas. O modelo não executa a chamada sozinho.
- Google ADK:
  https://adk.dev/agents/routing/
  Roteamento de modelos/agentes pode considerar contexto, capacidade e
  resultados. Delegação hierárquica não requer lista de palavras-chave.
- DeepSeek:
  https://api-docs.deepseek.com/guides/thinking_mode/
  Pensamento e tool calling em múltiplos passos; uso correto de contexto
  e outputs requer orquestração. Não supor detalhes internos não publicados.
- Anthropic:
  https://www.anthropic.com/engineering/building-effective-agents
  Distingue fluxos pré-definidos de agentes que direcionam ferramentas;
  recomenda composição simples antes de camadas desnecessárias.

Essas fontes descrevem padrões públicos, não permitem afirmar que os
pesos ou sistemas privados desses fornecedores funcionem identicamente.

## Decisões arquiteturais

1. **Uma inferência semântica central** com o modelo disponível escolhe
   entre `answer`, `clarify`, `plan`, `act`, `research` e demais movimentos
   já existentes. O roteamento padrão não intercepta `jogo`, `cria`,
   `site` ou qualquer palavra específica antes da inferência.
2. **Catálogo por escopo do produto, não por palavras do pedido.**
   O chat pessoal não apresenta `developer.propose` ou `developer.build`
   ao modelo. `MENOR_AGENT_SCOPE=maintenance`, configurável somente no
   servidor, expõe manutenção supervisionada. As ferramentas continuam
   registradas para execução administrativa explícita pelo dono.
3. **Autorizações e riscos continuam determinísticos.** O modelo pode
   solicitar uma ferramenta, mas não pode fabricar permissão. A mesma
   validação do catálogo e da aprovação é reaplicada antes da execução.
   Um modelo que alucine ferramenta de outro escopo é recusado.
4. **Estado conversacional é contexto, não regra de ação.** Objetivos
   e decisões anteriores entram como dados; uma inferência pode pedir
   esclarecimento, responder ou continuar o plano. Em falha de inferência,
   o caminho degradado conversa, sem simular ação.
5. **Baixo custo de latência.** Reutilizar a chamada de `intelligence.decide`
   atual, em vez de empilhar novos classificadores LLM na CPU. Evitar
   enumerar funções de manutenção no prompt do chat cotidiano.

## Estado atual versus próximos incrementos

Implementação E14:
- Remove a decisão primária por expressões regulares no `runner`;
  mantém ramo legado quando inteligência for desabilitada explicitamente.
- Atualiza prompt semântico e conversacional, escopo de catálogo e loop
  de ferramentas; adiciona regressões para ideias de diferentes domínios,
  seleção de ferramenta por modelo e proposta indevida de autoedição.
- Não altera o modelo Ollama nem o hardware; não concede acesso irrestrito
  ao servidor; não instala subagentes.

Fase A seguinte:
- Avaliar modelo real em conversas longas e parafrases de intenções; medir
  escolha de `move`, pergunta útil, precisão e repetição com revisão humana.
- Diferenciar *discutir*, *registrar decisões*, *executar*, *revisar* e
  *modificar o Menor* em avaliação independente do vocabulário.
- Projetos pessoais devem ter um workspace privado persistente com anotações
  proativas de baixo risco e recibos visíveis; arquivos externos ao workspace
  e operações destrutivas exigem aprovação contextual.
- Ferramentas devem ser descobertas conforme permissões e tarefa, sem colocar
  dezenas de contratos no prompt de cada turno.

Fase B–D:
- Agent loop durável (checkpoints, compensação, retomada segura,
  dependências, verificação de resultados).
- Execução isolada de aplicações para testar e corrigir, não apenas
  `node --check` e criação de arquivos.
- Delegação para subagentes especializados por capacidade comprovada,
  inclusive modelos distintos, com limites de CPU/RAM e consentimento.
- Autoedição do Menor sempre em escopo separado, com CI e revisão.

## Teste de aceitação real

Testar em ambiente com Ollama instalado após deploy:
1. Expressões diferentes da mesma intenção não causam ferramentas diferentes.
2. Ideias nas áreas de jogos, agenda, finanças e design iniciam conversa
   contextual; não geram PRs nem criam arquivos inadvertidamente.
3. Pedidos explícitos de executar em projeto pessoal solicitam a ferramenta
   correta e uma aprovação proporcionada; o recibo reflete o resultado real.
4. Apenas escopo explícito de manutenção permite propor alterar o Menor.
5. Comparar latência de roteamento em uma chamada com caminho antigo;
   não aceitar regressões silenciosas de qualidade.

CI com mocks valida os contratos, não demonstra compreensão correta do 7B
numa conversa real. Ampliar avaliações com exemplos novos e adversariais.
