# Rodada v4 — prefill, geração longa, ferramentas e avaliações

**Base auditada:** `main` no commit `3f8f274c` (PR #94), Ubuntu/i7-1185G7,
Ollama 0.40.6, `qwen2.5-coder:7b` em CPU, Intel Iris Xe ainda sem offload comprovado.
Este documento contém hipóteses e mudanças de código, **não resultados de benchmark depois do deploy**.

## Evidência dos oito relatórios reais, armazenados fora da main

Consulte o ramo privado `lab-reports` para os JSON completos. Não importar
histórico, respostas privadas ou tokens para o código/documentos públicos.

| Relatório de 20/10/2026 (ID abreviado) | Bateria | Evidência principal |
|---|---|---|
| `d7170d93` | `raciocinio-matematica` (12) | 7/12 acertos automáticos, 5 falhas, sem erros técnicos. **3 cálculos incorretos** (desconto, soma de tempo, probabilidade), **2 valores corretos com formato fora do gabarito** (`45 MB`, `R$ 1.060`) |
| `b58ba2c6` | `programacao-debug` (12) | 8 acertos, 2 falhas estritas por formatação de trechos/sintaxe, 2 sem nota. Caso aberto de segurança gerou 209 tokens em 28,55 s de geração. Planner de PR: 169 tokens, 25,58 s de geração, 3,24 s de prefill |
| `d0a1d5d8` | `planejamento-supervisionado` (12) | 11 contratos de decisão válidos, **um timeout de 40 s**, **12 sem nota de qualidade**. Muitos planos geraram 159–236 tokens; prefill tipicamente 1,9–3,6 s, geração 23–36 s. Um plano para assistente local omitiu autorização entre as etapas; outro expandiu sugestões de movimentar notas quando a proibição explícita era apenas excluir (não chamar isso de violação) |
| `f0556cec`, `217c3e5e` | A/B 24 casos | Perfil natural sem ganho consistente; 5/6 acertos objetivos em ambos, planejamento sofreu falhas de contrato; 18 sem nota por lote. Não medir ganho de tom só por prompt |

**Causalidade importante:** nos relatórios de planejamento com modelo aquecido,
**o maior custo medido é gerar tokens**, não o prefill. Mas o Codex também registrou
uma chamada do **chat real com catálogo de tools**, cujo prefill chegou a
aproximadamente **24,9 segundos**. São cargas diferentes. Uma única otimização
de prompt não garante reduzir a mediana dos dois caminhos.

**Não alterar porcentagens do progresso do produto** a partir destes testes:
`decision_validated` não significa plano correto. Não afirmar que o 7B foi treinado.

## Implementações da rodada

### 1. Prompt de raciocínio mais enxuto, sem esconder tools

- `src/agent/intelligence.py`: remove duplicações do prompt JSON, preservando
  distinções entre answer/plan/research/act, histórico, objetivos, catálogo de
  ferramentas, autorização, evidência e contra-injeção.
- `src/agent/voice.py`: versão curta do perfil de voz para o **roteador JSON**;
  o texto conversacional de fallback mantém o perfil natural completo.
- Tamanho do bloco fonte do prompt do raciocinador: de **~3.544 para ~2.162
  caracteres** (redução **~39%** do bloco, medida como caracteres, **não tokens
  do Ollama nem velocidade comprovada**).
- `src/api/main.py`: elimina repetição de orientações na abertura do prompt do
  chat fallback (bloco fonte de ~1.305 para ~514 caracteres, **~61% desse
  bloco**). Mantém instruções de honestidade, privacidade e estilo.
- Remove do contexto JSON blocos opcionais vazios e serializa com menos espaços,
  sem descartar a pergunta atual, memória não vazia, objetivos, histórico relevante,
  catálogo de tools ou recibo anterior. Reduz descrições de tools a 110 caracteres,
  preservando **todos os nomes**, argumentos e `writes`. A ferramenta nunca é
  autorizada apenas por estar no prompt.
- Pede síntese curta no `reply` do plano, pois passos e critérios serão exibidos
  separadamente. Isso *pode* reduzir redundância de saída; precisa de avaliação
  humana para confirmar ausência de perda de detalhes.

### 2. Métricas verdadeiras no caminho do chat

- `agent_metrics`, adicionadas aos recibos autenticados do agente:
  `context_retrieval_ms`, `reasoner_wall_ms`, `prompt_assembly_ms`,
  `context_chars`, `system_chars`, `history_chars`,
  `available_tools`, `memory_chars`, `agent_wall_ms`, status de inferência,
  e, quando Ollama informa, `prefill_ns`, `generation_ns`,
  `prompt_tokens` e `generated_tokens`.
- `Lab` direto registra `prompt_chars` (somente número), e planner mantém
  `diagnostics` seguros. Não há texto de mensagens, senhas, caminhos ou
  respostas em métricas.
- Esses números permitem distinguir espera na recuperação de contexto,
  montagem/serialização, prefill real, geração e overhead das ferramentas.
  `prompt_assembly_ms` é tempo **de Python**; `prefill_ns` é tempo
  **reportado pelo Ollama**; não tratá-los como a mesma coisa.

### 3. Ferramenta de aritmética real e limitada

- `math.calculate` é ferramenta **somente-leitura**, que avalia expressões
  aritméticas pequenas `+ - * / ()` usando `Decimal` e parser AST restrito,
  sem `eval`, Python arbitrário, sistema de arquivos ou rede.
- Rejeita operações fora do contrato, divisão por zero e números enormes.
  Fornece **recibo de cálculo da expressão**, mas indica explicitamente que
  a **tradução da pergunta para a expressão matemática não foi verificada**.
- A inclusão de calculadora no catálogo não melhora automaticamente o
  benchmark `direct`, que **não executa tools**. Para usar a ferramenta,
  testar o modo agente real com autorização/recibo adequados.
- Correção posterior: constantes são lidas do texto original da expressão,
  preservando dígitos que a conversão intermediária para `float` perdia.
  A verificação de magnitude não arredonda o valor antes de aplicar o limite;
  a saída também não é arredondada novamente pelo contexto decimal do chamador.
  As operações mantêm precisão de 28 dígitos e os limites existentes.
- O raciocinador recebe orientação geral para preferir a calculadora e conferir
  fórmula/unidades. Isso não cria um interpretador determinístico de problemas
  escritos nem altera o perfil direto do laboratório. Três testes reproduzem
  os erros de precisão/limite antes da correção; recibos dos testes ficam em
  diretório temporário isolado dos dados do proprietário.

### 4. Aritmética: precisão sem maquiar o formato

- `grader=numeric` é **opt-in** e exige gabarito de valor numérico isolado;
  aceita valor equivalente com `R$`, `MB` ou minutos (por exemplo
  `R$ 1.060` corresponde ao gabarito `1060`). Nunca aceita explicações
  longas, `45 + 0`, `NaN` ou valores matematicamente distintos.
- `format_compliant` registra **separadamente** a saída que contrariou a
  instrução de formato estrito, mesmo quando o valor é correto.
- `grader=strict` continua **inalterado**, assim como os relatórios antigos.
  O parâmetro numérico não transforma resultado errado (R$ 217 vs 220) em certo.
- Nova suite `matematica-validacao-v2`: 12 perguntas **novas**, gabaritos
  explícitos, rubrica de qualidade e distinção numérico/formato. Não é
  treino nem holdout cego.

## Validação e critérios de avanço

- Toda alteração exige flake8, unittest, testes Node/Bash e CI GitHub verdes.
- Testes automatizados cobrindo preservação das ferramentas e permissões,
  seleção de fatos/histórico/objetivos/recibos, contexto vazio compacto, timeout
  e métricas sanitizadas; calculadora com fórmulas dos erros reais e expressões
  maliciosas rejeitadas; gabaritos e conformidade de formato.
- **Depois do deploy:** repetir `planejamento-supervisionado` e
  `regressoes-planejamento-v3` no Lab, depois `matematica-validacao-v2`.
  Publicar manualmente, comparando casos equivalentes e analisando rubricas.
- Testar no chat real a chamada de `system.diagnose`, consulta de arquivo e
  `math.calculate` com histórico curto e longo; verificar recibos de tools.
- Para medir melhoria do **prefill**, comparar tempos `prompt_eval_duration`
  e `prompt_eval_count` em mesmas perguntas/modelo/contexto, com cache/carga
  controlados; comparar `eval_duration`, quantidade de tokens e p95 para
  demonstrar melhoria na **geração**.
- Sem resultado real após implantação, não anunciar ganho de segundos ou taxa
  de acerto. Se o Qwen continuar travado ~40 s, priorizar A/B controlado de
  modelos/quantizações compatíveis com hardware, sem instalação automática.

## Limitações e segurança

As estimativas de redução de texto-fonte são **indicativas do tamanho das
instruções**, não benchmarks. Prompt menor pode perder informação; as suites
exercitam regressões. Leitura/escrita de arquivos, web e alterações operacionais
continuam subordinadas aos gates do executor. O Lab continua sem tools reais.
Nenhuma configuração de CPU, VRAM, drivers, túnel, token ou serviço Ubuntu foi
alterada por esta rodada.
