# E15 — Conversas simuladas com o Ollama real, sem repetição manual

## O problema

O Lab antigo testava mensagens independentes ou um histórico escrito no JSON.
Era possível aprovar dezenas de respostas sem observar o Menor acompanhando
uma conversa. Além disso, testes de "planner" sem ferramentas não representam
o chat real, nem a execução de ferramentas da arquitetura A–E.

## O que foi implementado

Quatro baterias instaladas em `lab/suites/e15-*.json`, totalizando **32 cenários
e 136 mensagens de usuário por modelo** (32 + 40 + 32 + 32).
Um cenário recebe entre dois e oito turnos e roda até o fim. Em cada turno,
o próximo histórico contém **a resposta produzida de verdade pelo modelo no
turno anterior**. Se houver timeout ou resposta inválida, o restante do
cenário vira `skipped_after_failure`: nada é inventado para mascarar a falha.

- **Descoberta e organização:** 8 conversas, 32 mensagens, backend `chat`.
- **Continuidade e escolhas:** 8 conversas, 40 mensagens, backend `chat`.
- **Decisões semânticas:** 8 conversas, 32 mensagens, backend `semantic`.
- **Segurança e permissões:** 8 conversas, 32 mensagens, backend `semantic`.

`chat` usa `conversation.reply`, o prompt conversacional real do Menor,
com o modelo escolhido no Lab. `semantic` usa `intelligence.decide` e
as ferramentas **pessoais** reais do catálogo, mas faz somente proposta:
a ferramenta **nunca é executada**; não cria projetos, não publica PRs,
não acessa shell e não altera os dados do servidor. O estado de objetivo
e o histórico da simulação são temporários em memória, isolados entre
cenários e modelos.

## Execução supervisionada e carga

No **Menor Lab → Suas baterias → Selecionar conversas E15**.
Selecione um modelo ou dois e confirme. A fila existente executa uma
bateria de cada vez, sequencialmente, salva um JSON completo com histórico
real de cada turno e um resumo sem mensagens. Não troca o modelo padrão
do chat. Não executa sem o clique explícito do proprietário autenticado.

Cada bateria pode ser executada separadamente. Para começar sem aguardar
136 inferências, marque apenas **E15 · Conversas reais: ideias e organização**
(32 inferências por modelo). Um modelo 7B e um 14B fazem 272 inferências
se todas as E15 forem marcadas; a CPU pode levar bastante tempo, sobretudo
no roteador de 14B com timeout. Não rodar junto com benchmarks de threads,
que alteram aquecimento e interferem na medição.

A fila é armazenada em memória: após reinício da API pode perder o
progresso não concluído, mas os relatórios anteriores sobrevivem. Não
iniciar várias filas simultâneas. Os relatórios completos permanecem
privados; publicação no GitHub exige revisão e confirmação separadas.

## Como ler os resultados

Cada `case` do JSON de relatório corresponde a **um turno real**
e inclui `conversation_id`, `turn_index`, pergunta, histórico produzido,
resposta ou decisão, métricas, critério humano e resultado automático.
O relatório também informa qual modelo gerou cada resposta, checkout e
eventuais timeouts.

- `automatic_pass: true` em testes de decisões significa APENAS que
  checagens estruturadas foram satisfeitas: não executou uma ferramenta
  indevida, move esperado, escopo correto etc.
- `automatic_pass: false` revela violação verificável ou falha de inferência.
- `automatic_pass: null` significa que a qualidade depende de
  **avaliação humana**, não que acertou ou errou.
- Em conversa natural, a checagem automática só detecta se foi obtida
  resposta válida. Naturalidade, perguntas pertinentes, retenção real,
  utilidade, afirmações de execução e qualidade são avaliadas pelo
  critério `review_criteria`; nenhum avaliador determinístico por substring
  recebe autoridade de julgar capacidade de IA.

## Comparação de modelos e próximos avanços

Primeiro, rodar o 7B sozinho e analisar: quantos cenários chegaram ao
último turno, tempos por etapa, falhas, decisões prematuras, trocas
indevidas de objetivo e recomendações de manutenção do próprio Menor.
Depois repetir os mesmos cenários no 14B (se desejado) e comparar
qualidade do diálogo, p50/p95, tempo de prefill, geração e tempo total
sem confundir qualidade com JSON válido.

**Limite claro:** esta atualização simula conversa e escolha de ferramenta,
mas **não executa o Menor completo** com `runner.run`, persistência
de projeto nem ferramentas de escrita. Um teste integrado de tarefas
reais exigirá workspace de teste isolado, aprovações simuladas,
evidências de arquivos, execução de testes em sandbox e recibos.
Assim evitamos simular um sucesso que ainda não aconteceu.

## Contratos e segurança

- Até 8 mensagens por conversa e 4200 caracteres por cenário.
- Mensagem de 3 a 800 caracteres; critério humano obrigatório por turno.
- Ferramentas pessoais listadas apenas como opções sem execução.
- Modelos selecionados no Lab, no máximo dois, processados em série.
- Toda falha interrompe a conversa daquele cenário para não montar um
  histórico fictício. A bateria continua com o próximo cenário.
- Resultado sem nota humana permanece explicitamente `ungraded`.

Referência de implementação:
`src/api/lab_dialogues.py`, `src/api/lab_batches.py`,
`lab/suites/e15-*.json`, `tests/test_lab_dialogues.py`.
