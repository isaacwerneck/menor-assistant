# E17 — Resultados reais da E15 e correção do contrato de ações

## Evidências do GitHub — 22/10/2026

Os oito relatórios completos foram publicados em `lab-reports` sob
`lab/reports/full/20261022T000631Z-*.json`, avaliados na revisão
`82944fb9b74b86117562218963f7dc02ac88bb65`, sem troca de commit
entre as execuções. Foram 32 cenários de 4–5 mensagens, **136 turnos por
modelo e 272 posições de turno no total**, incluindo turnos que não
foram executados após falha inicial.

| Bateria | 7B conclusão | 14B conclusão | Sintomas |
| --- | ---: | ---: | --- |
| Descoberta (8x4) | 7/8 | 0/8 | 1 versus 8 timeouts de chat |
| Continuidade (8x5) | 4/8 | 0/8 | 4 versus 8 timeouts de chat |
| Intenção semântica (8x4) | 5/8 | 0/8 | 3 versus 8 timeouts de decisão |
| Segurança (8x4) | 6/8 | 0/8 | 2 versus 8 timeouts de decisão |
| **Total de 32 conversas** | **22/32** | **0/32** | Piora do 14B atribuível majoritariamente a timeout |

Turnos tecnicamente respondidos ou validados: **119/136 no 7B** e
**25/136 no 14B**. Os demais são falhas diretas ou turnos
`skipped_after_failure`. Não interpretar os 136 como 136 respostas
efetivamente produzidas por modelo.

**Observação direta:** no 14B os oito `no_answer` de descoberta e
oito de continuidade registraram `ReadTimeout`, normalmente após
42s (ou 58s em pedidos longos). Os roteadores 14B
registraram 16 timeouts em 40s. No 7B, houve cinco timeouts de
chat (1+4) e cinco do roteador (3+2). O 14B pode até produzir
respostas úteis quando termina, mas NÃO está viável como padrão
no ciclo observado. O limite fixo e CPU/prefill explicam muito da
falha: isso não prova incapacidade semântica da arquitetura 14B.

**Falhas semânticas que realmente apareceram no 7B:** alguns cenários
de conversa tiveram propostas prematuras de `images.generate`,
`files.context`, `projects.create` e `web.search`, apesar de o
usuário querer apenas discutir possibilidades ou adiar execução.
A E14 já impede a ferramenta de autoedição no escopo pessoal,
mas não evita todas as sugestões indevidas de ferramentas pessoais.

Todos os testes E15 com `engine=chat` são não classificados
(`ungraded`) quando tecnicamente bem-sucedidos; não extrapolar
qualidade, continuidade correta ou naturalidade de uma resposta válida.
O E15 não executa ferramentas; tampouco comprova funcionalidades reais.

## Mudanças E17 (sobre a E16 já integrada)

1. **Contrato de decisão compacto:** uma única estrutura JSON
   (`type:object`) sem o `oneOf` triplicado. A validação condicional
   continua no Python, inclusive campos obrigatórios de plano/pergunta,
   esquemas das ferramentas e referência de objetivos. O modelo recebe
   as mesmas capacidades, sem reescrita de roteamento por palavras.
2. **Prompt semântico menos redundante:** mesmo objetivo universal,
   reduzido aproximadamente de 3.736 para ~2.300 caracteres
   de instrução (medir no código); inclui distinção explícita de
   ideia, hipótese, plano e pedido de operação.
3. **Orçamento** do roteador de 480 para 360 tokens máximos. A redução
   é um experimento: medir `done_reason=length`, truncamentos e
   falhas em planos longos antes de concluir que é ganho líquido.
4. **Evidência da intenção:** ações propostas pelo roteador devem
   apresentar `action_quote`, trecho literal do **pedido atual** que
   pede efetivamente uma operação. O executor somente considera act
   com ferramenta válida, argumentos exatos e prova atual não vazia.
   A ausência de prova converte a decisão em esclarecimento,
   sem ação de leitura, escrita ou proposta de PR.
5. **Métricas honestas:** o Lab registra `action_rejected`; mesmo
   quando a proteção impede um efeito, a nota automática de decisão
   indica **falha do modelo**, não acerto semântico. Isso mede melhoria
   no roteador separadamente do sucesso da barreira de segurança.
6. **Conversa e memória de trabalho:** a revisão manual de trajetórias
   7B encontrou horários inventados em um planejamento semanal e a
   inversão de uma dependência explicitamente corrigida pelo usuário.
   O chat agora conserva até cinco pares recentes; prioriza texto do
   usuário (440 caracteres) sobre respostas antigas do assistente
   (240 caracteres) e instrui que correções recentes substituem
   fatos anteriores. Não promete corrigir toda alucinação apenas
   por alterar o prompt.

**Importante:** evidência textual por si só não é um classificador
perfeito de intenção. Uma frase negativa ou trecho citado pode
conter palavras de ação. A decisão semântica segue do modelo e a
aprovação de escrita segue do executor; qualquer falha aqui exigirá
mais dados reais. Não alegar segurança perfeita ou paridade com Codex.

## Verificação e experimento A/B

A CI Python/Node do GitHub valida determinismo e limites.
Sem acesso ao Ollama do usuário, não é correto afirmar que
o novo prompt/schema ficou mais rápido em produção.

Após deploy, repetir **primeiro** a bateria
`e15-intencao-sem-antigos-gatilhos` (32 turnos) somente no 7B e
comparar com a referência `20261022T000631Z-2b12085d`:
- `dialogue_completed`, `validation_issue`, `action_rejected`;
- propostas indevidas de ação e perguntas realmente pertinentes;
- tempo total/p50/p95, `prompt_processing_ms`,
  `token_generation_ms`, geração de tokens/s;
- `done_reason=length` e falhas por timeout;
- se um pedido explícito realmente escolhe a ferramenta certa
  e preserva a aprovação do proprietário.

Depois executar `e15-seguranca-e-autorizacao` (32 turnos);
comparar com `20261022T000631Z-1acc7afe`. Revisão humana é
obrigatória para naturalidade, utilidade e falsa execução.
Não realizar teste 14B simultâneo sem necessidade comprovada.

## Melhorias posteriores fora do escopo

O próximo salto na inteligência funcional depende de
**workspace privado de projeto + registro durável das decisões +
executor isolado de código + loop executar→testar→corrigir**.
Os testes E15 medem decisões e conversas, não concluem esses passos.

## Fontes externas de contrato e temporização

- Ollama, OpenAPI (schema, `num_predict`, timings e keep_alive):
  https://github.com/ollama/ollama/blob/main/docs/openapi.yaml
- Ollama, structured outputs:
  https://ollama.com/blog/structured-outputs
