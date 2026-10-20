# Chat A — avaliação reproduzível de interpretação e crítica de planos

Este incremento adiciona `src/agent/benchmark.py` para identificar regressões antes de habilitar revisão independente no notebook Intel. **Não** habilita `MENOR_PLAN_REVIEW_ENABLED`, não chama catálogo de ferramentas e não escreve em memórias, arquivos privados ou produção.

## Execução

```bash
python -m unittest discover -s tests -p 'test_chat_a_benchmark.py' -v
python -m src.agent.benchmark --live > benchmark_baseline.json
python -m src.agent.benchmark --live --compare-review > benchmark_review.json
```

A comparação justa dentro de uma mesma execução é a terceira chamada: avalia o mesmo plano inicialmente gerado com e sem crítica. O custo extra do revisor inclui uma inferência de crítica e, se necessário, **uma** reformulação. Nunca há segunda crítica. As duas chamadas anteriores são exemplos de execução simples; não se deve comparar resultados de rodadas separadas como se fossem a mesma amostra.

- `mode=ollama_inference` identifica tentativa com modelo real. Testes injetados retornam `mode=injected_decider`.
- `baseline` e `reviewed` relatam casos válidos, indisponíveis, acertos heurísticos e cobertura. `score=null` quando nenhuma inferência válida ocorreu (não converter indisponibilidade em zero de qualidade).
- `latency_ms.baseline_total`, `baseline_p50`, `review_extra_total` e `review_extra_p50` representam relógio de parede do processo, não `eval_duration` ou CPU/RAM do Ollama.
- `details` guarda apenas nome fixo de cenário, movimento, relação, indicadores e tempo; não salva prompts, memória privada, respostas ou problemas do revisor.
- O benchmark **não** mede veracidade factual, fidelidade semântica do plano, precisão de OCR, conclusão de tarefa, idempotência real, segurança de execução ou taxa de sucesso de ferramentas.

São 12 cenários fixos inéditos nesta suíte: linguagem coloquial, ambiguidade, documentos, visão, música, programação, ausência de comprovante, interrupção e troca/refinamento/retomada de objetivos. Os critérios intencionalmente aceitam mais de um movimento plausível em algumas tarefas; são um sinal de regressão, não uma métrica de inteligência geral. Não incorporar essas frases aos prompts de produção ou ao treinamento.

## Aceite no hardware

Executar no servidor autorizado com `MENOR_REASONING_MODEL`/`MENOR_PLAN_REVIEW_MODEL` apontando para modelos **já instalados** e dados privados isolados. Registrar SHA Git, versão do Qwen/Ollama, CPU/RAM, carga concorrente, aquecimento e pelo menos três execuções com ordem alternada. Inspecionar qualitativamente erros sem publicar dados privados. Habilitar crítica por padrão apenas se houver ganho útil e orçamento de latência aceitável, com decisão de configuração revisada separadamente.

**Estado da entrega original:** regressões de Python com mocks verificavam o instrumento;
a avaliação remota abaixo acrescenta observações reais, sem equivaler ao benchmark
controlado de inferência direta versus planejador.

## Avaliação integrada remota — 19/10/2026

### Escopo e referência

Revisão de referência: `7e357108da08b5d1f4c6f87e53e65a7bbda3d28f`.
Inventário de 52 Markdown versionados, planos, histórico de integração e alterações
desde `2b19ac7`: 170 arquivos, 17.461 linhas adicionadas e 150 removidas.
A análise do código concentrou-se nos fluxos de contexto, decisão, pesquisa,
memória, ferramentas, API, laboratório e deploy; não é auditoria linha a linha
de todos os executores ou certificação de segurança.

As mudanças integraram: objetivos e retomada; recuperação sem replay; crítica
opcional; leitores de documentos e OCR; visão; recibos e observabilidade;
painéis privados; cancelamento; anexo no chat; laboratório remoto.
Essas entregas ampliam o produto, mas quantidade de módulos e testes de contrato
não mede entendimento nem conclusão de tarefas. Muitos documentos preservam
estados históricos de PRs e listas antigas: os planos consolidados e o código
atual devem orientar a operação.

Direção de produto confirmada: assistente pessoal local inspirado no fluxo de
Codex/Jarvis, com memória, pesquisa, ferramentas e propostas de autoaperfeiçoamento.
Aprender notas não treina pesos; instalar mais ferramentas não melhora
automaticamente o raciocínio do modelo.

### Ambiente observado

Acesso pelo navegador autenticado ao servidor fornecido pelo proprietário.
Não publicar endereço temporário, senha, cookie ou conteúdo privado no relatório.

- `/health`: API 0.4.1, contrato 1, Ollama online,
  modelo padrão `qwen2.5-coder:7b`.
- `/workspace/system`: somente esse modelo foi listado como instalado;
  ferramentas registradas e skills não prontas aparecem separadamente.
- `/lab/view`: retornou 404, embora exista na revisão de referência.
  Portanto, não foi possível comparar Qwen direto e planejador pelo laboratório
  naquele processo. A revisão efetivamente carregada não foi comprovada.
- CI da referência passou nos dois workflows; isso não comprova deploy.
- Não houve SSH, instalação de modelos, treino de pesos ou restart manual.

### Conversas reais com dados sintéticos

| Caso | Resultado observado |
| --- | --- |
| Inventário de capacidades, sem executar | Resposta longa e pouco focal; ainda gerando após 128 s, interrompida pelo botão Parar. |
| Cancelar essa resposta | Interface reconheceu a interrupção e avisou que o servidor pode continuar. Encerramento real do Ollama não comprovado. |
| “2 + 2”, somente número | Acertou 4, mas respondeu “2 + 2 é igual a 4.”: falhou no formato. Espera de mais de 24 s observada. |
| Informar Farol / Ubuntu 24.04 sem memória durável | Respondeu “Entendido.”; não exibiu recibo de gravação. |
| Recuperar esses dois fatos | Respondeu corretamente em uma linha. Resultado estava concluído na observação aos 42 s; esse valor é limite superior, não latência exata. |
| Corrigir para Aurora / Ubuntu 22.04 | Aplicou os valores novos sem repetir os antigos. |
| Nova conversa, perguntar nome não informado | Respondeu “Não informado.”; não trouxe Farol/Aurora da conversa anterior. |
| Analisar média de lista vazia, sem executar | Identificou ZeroDivisionError e sugeriu tratar a entrada vazia; respeitou limite de três frases, sem recibo de execução. |
| Dois projetos, referência ambígua | Fez uma única pergunta distinguindo música e jardinagem. |
| Conteúdo de arquivo nunca anexado, “não procure” | Não inventou conteúdo, mas respondeu sobre fontes disponíveis e ignorou o formato pedido. Ainda processava aos 68 s. |
| Plano de estudo, três etapas e nenhuma execução | Entregou três etapas sobre sintaxe, exercícios e pequenos projetos, sem alegar execução. |
| Pesquisa oficial de funções Python, com fonte e sem estudo | Retornou pesquisa indisponível/evidências inválidas, sem URL ou exemplo. Falha funcional de pesquisa; não é sucesso por ter se abstido. |

São observações qualitativas de uma amostra pequena e sequencial, na versão
então disponível. Não calcular taxa de inteligência ou ganho de velocidade a
partir dessa tabela. O tempo entre observações inclui outras atividades e
não deve ser apresentado como duração exata do modelo. Ausência de recibo na
UI não prova ausência de qualquer efeito persistido; não inspecionamos dados
privados para verificar isso.

### Causas demonstráveis e correções

1. **Pedido atual cortado em 1.800 caracteres:** a API aceitava 8.000, mas o
   planejador perdia instruções finais. Agora envia o pedido aceito completo.
2. **Memória cortada duas vezes:** 1.850 caracteres montados viravam 1.200 no
   planejador. O orçamento montado agora é preservado.
3. **Preferências ausentes no caminho principal:** agora chegam ao planejador,
   limitadas a 2.000 caracteres e sem conceder permissões. O laboratório passa
   preferências explicitamente vazias para continuar isolado.
4. **Histórico longo perdia correções finais:** a seleção preserva início/fim,
   sinaliza omissão e prioriza fatos do usuário após o último par recente.
   A ordem cronológica dos trechos escolhidos permanece intacta.
5. **Fallback enviava até 32.000 caracteres de histórico:** agora reutiliza
   a seleção de até 4.400 caracteres; a mensagem atual permanece completa.
6. **Prompt e resposta estruturada excessivos:** instruções redundantes foram
   condensadas; respostas simples pedem apenas move/reply. O schema do Ollama
   restringe movimentos, tipos e tamanhos. Validação e autorização continuam
   no Python. Uma única chamada basta quando a resposta é válida.
7. **Explicações válidas acima de 900 caracteres eram descartadas:** limite
   compatível de 4.000 evita esse fallback desnecessário, mantendo o teto de
   geração existente. Respostas vazias, inválidas ou maiores continuam recusadas.
8. **Convite genérico em todo plano:** removido; perguntas essenciais explícitas
   e etapas continuam sendo exibidas.
9. **Pesquisa forçada por palavra, inclusive negada:** decisão chat do
   classificador agora é respeitada também quando há palavra de pesquisa.
   O prompt distingue negação, citação, arquivo privado e evidência pública.
   Isso reduz o desvio demonstrado; o classificador ainda pode errar.
10. **Cache de embeddings reutilizado após troca de modelo:** identifica o
    modelo e reconstrói vetores incompatíveis; o Markdown não é alterado.
11. **Inventário JSON cortado e quebra de linha literal:** preservados JSON
    completo e separação real do prompt. Registro continua distinto de prontidão.
12. **Lint operacional fora do CI:** incluído ops no Flake8 e removidos dois
    imports sem uso. Documentação de hardware deixou de prometer velocidade
    de 14B e folga de RAM não medidas.

A API de schema utilizada é documentada pelo
[Ollama](https://docs.ollama.com/capabilities/structured-outputs).
Nenhuma biblioteca nova ou troca de modelo foi necessária.

### Verificação e próximos aceites

Regressões cobrem pedido longo, fim de memória, preferências e isolamento do
laboratório, explicação longa sem segunda chamada, limites, orçamento/histórico,
troca de embeddings e negação de pesquisa. Flake8 inclui src/ops/tests.
Testes de interface existentes cobrem recibos, anexos, cancelamento e isolamento.

O Windows local não executa integralmente a suíte POSIX: há dependências de
fcntl, fchmod, permissões e symlinks; não remover essas proteções para obter
resultado verde. O aceite de integração deve usar os workflows Ubuntu,
incluindo Python completo, documentos/OCR, Node e scripts Bash.

Depois de confirmar a revisão carregada no servidor:
1. Repetir casos equivalentes e inéditos em ordem alternada, três vezes.
2. Comparar Qwen direto, planejador e chat completo; coletar prompt_eval_count,
   eval_count, load_duration, eval_duration, tempo até primeiro token e total.
3. Medir CPU/RAM/carga concorrente; testar um modelo alternativo somente após
   escolha e instalação autorizadas, sem presumir ganho por número de parâmetros.
4. Testar leitura de documento sintético, pesquisa com fonte oficial, estudo
   consentido e uso de ferramenta com recibo. Não confundir abstenção com sucesso.
5. Validar cancelamento no Ollama e recuperar resultado incerto sem replay.
6. Só depois ampliar o programador e o estudo persistente supervisionados.

Este incremento corrige perdas e desvios reproduzíveis da orquestração.
Ganho de latência e qualidade no notebook após deploy exige nova medição;
CI verde sozinho não comprova esse ganho.

## Segunda rodada — pesquisa com contexto limitado

Referência inicial: main em `f4c3a70`, PR #74 incorporado. O laboratório remoto
continuou respondendo 404 nesta rodada; não atribuir resultados ao código novo
sem conferir o processo carregado.

Observações adicionais no chat real:
- Pergunta inédita “17 menos 9, somente número”: respondeu exatamente “8”.
- Documento nunca anexado: respondeu em uma frase que não tem acesso ao conteúdo.
- Esses resultados não incluem duração exata; não provam ganho de desempenho.

Problemas reproduzidos com fontes sintéticas e correções:
- O leitor cortava os primeiros 12.000 caracteres antes de procurar informação;
  texto pertinente no fim de uma documentação longa desaparecia. A leitura com
  consulta agora seleciona trechos literais do texto obtido antes desse corte.
- Até 36.000 caracteres de páginas podiam ser enviados à síntese. Agora há limite
  de 2.400 por fonte e três fontes, inclusive no fallback de navegador.
- Três primeiros resultados ilegíveis encerravam a tentativa mesmo se o quarto
  fosse acessível. Agora examina até cinco candidatos para obter três legíveis.
- A classificação tinha teto de 900 tokens como a síntese. Recebe schema menor
  e teto de 180; a síntese conserva seu orçamento independente.
- A palavra “estude” negada podia disparar registro. Agora também exige uma
  decisão booleana de estudo; o modelo ainda pode interpretar intenção mal.
- Busca, leitura e síntese inválida tinham mensagem quase indistinguível. Agora
  retornam etapas de falha específicas, sem divulgar exceções e sem salvar estudo.
- Marcadores de omissão são separados dos trechos citáveis; não contam como fonte.

Validação web real no computador de desenvolvimento, sem Ollama:
a leitura HTTPS da documentação oficial de Python com seleção de trechos e a
busca pública passaram. O HTML do DuckDuckGo falhou e o fallback Bing RSS
retornou resultados. Foram dois testes opt-in em cerca de um segundo nessa
execução; isso não mede o Ubuntu nem qualidade da resposta do modelo.
Testes de regressão cobrem orçamento, texto no fim da página, fontes falhas,
navegador, decisão de não salvar, formatos de classificação e erros por etapa.

Limites: seleção lexical não garante relevância, autoridade ou implicação
semântica da citação. Não há nova biblioteca, provedor ou modelo. Os controles
HTTPS/DNS e a recusa de fontes privadas continuam no leitor existente.
