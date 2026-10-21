# E10 — Diagnóstico de latência, continuidade e fluxos completos

**Situação:** as capturas mostraram repetições da pergunta Canvas/Raylib,
falsos exemplos de CDN e espera longa mesmo para "tenta dnv". A correção
E10 remove a segunda geração para resposta fraca, preserva a escolha técnica
e adiciona instrumentação. **Não equivale a acelerar fisicamente a CPU**.

## O que já é medido por turno

A API autenticada `/agent/run` retorna `agent_metrics` sem o conteúdo
da mensagem. O botão **Tempos técnicos (JSON)** no topo do chat exporta
somente as métricas coletadas nas respostas atendidas pelo agente nesta
conversa, armazenadas localmente no navegador. Outros caminhos, como
streaming de chat legado, ainda não incluem toda essa coleta.

- `browser_request_wall_ms`: tempo entre iniciar a requisição da UI e
  receber a resposta; inclui rede, fila e servidor.
- `agent_wall_ms`: tempo no processador da requisição do agente, sem
  incluir toda a persistência de estado.
- `chat_wall_ms` / `reasoner_wall_ms`: duração de chamadas ao Ollama.
- `ollama.model_load_ms`: carregamento do modelo.
- `ollama.prompt_processing_ms`: prefill do prompt.
- `ollama.token_generation_ms`: geração dos tokens da saída.
- `ollama.eval_count` e `ollama.generation_tokens_per_second`: contagem
  e taxa observada de tokens na resposta.
- `ollama.other_model_ms`: outras durações internas contabilizadas
  pelo Ollama (somente quando campos são suficientes).
- `chat_attempts`: chamadas realizadas no caminho de conversa;
  agora deve ser **1** por turno.
- `quality_guard`: resposta genérica, repetição de decisão já resolvida
  ou alegação de execução não comprovada; o texto do usuário não é exportado.

Os campos só aparecem quando disponíveis; ausência de um campo **não é
zero**. Valores de um modelo não podem ser comparados diretamente aos de
outro com prompt, hardware, quantização ou condições diferentes.

## Diagnóstico seguro no Ubuntu (somente leitura)

Sem instalar ou alterar configuração do servidor, execute quando o Menor
estiver ligado:

```bash
ollama --version
ollama ps
ollama list
free -h
lscpu
python -m ops.model_latency --live --samples 3
```

O último comando é um benchmark intencional com prompts públicos fixos
no Ollama local, não captura chats privados, e consome inferência. Faça
primeiro sem outros jobs do Lab concorrendo com o modelo.

`ollama ps` indica quanto está na CPU versus GPU. Não é possível inferir
a existência de GPU dedicada sem a inspeção real. Quando existir GPU
NVIDIA compatível, `nvidia-smi` pode acrescentar evidência. Não altere
drivers ou sistema baseado apenas em recomendações genéricas.

## Plano de investigação baseado em documentação

1. **Comparar frio e quente:** `load_duration` alto no primeiro pedido
   versus pedidos posteriores indica carregamento. Use
   `OLLAMA_KEEP_ALIVE` / `keep_alive` para manter o modelo carregado
   enquanto couber na memória; evite manter modelos demais.
2. **Decodificação lenta:** `eval_count / eval_duration` baixo indica
   limite do modelo/quantização/hardware ou contenção. Avalie 1) GPU
   disponível e efetivamente usada, 2) modelo menor/quantização comparada
   na mesma tarefa, 3) uso da CPU e RAM, 4) ajuste experimental do número
   de threads, evitando oversubscription.
3. **Prefill lento:** `prompt_eval_duration` alto pede reduzir histórico
   irrelevante e definições de ferramenta repetidas, sem apagar decisões
   importantes. Cache de prefixo depende de modelo/versão e estabilidade
   de contexto.
4. **Fila/contenda:** se `browser_request_wall_ms` excede muito o
   `agent_wall_ms`, verifique rede e filas. Ollama documenta que
   paralelismo aumenta o consumo de memória proporcional ao contexto.
5. **Flash Attention/cache KV:** Ollama pode ativar Flash Attention
   automaticamente quando disponível; quantizar cache KV com `q8_0`
   reduz memória, mas pode alterar a qualidade — especialmente em
   arquiteturas Qwen2. Faça A/B e jamais mude tudo ao mesmo tempo.
6. **Streaming:** ajuda a mostrar tokens assim que são gerados, mas
   não aumenta por si só a taxa física de tokens por segundo. O
   caminho `/agent/run` permanece síncrono nesta etapa; implementar
   streaming exige preservar aprovações, deduplicação e idempotência.
7. **Treinamento:** supervisionar exemplos humanos corretos (SFT/LoRA)
   pode melhorar estilo e tarefas específicas, mas não conserta falta
   de ferramentas, continuidade, hardware lento ou APIs de execução.
   Só treinar após curadoria de dados e avaliação de regressão separada.

### Critério objetivo para o próximo experimento

- Mesmo modelo, versão, quantização, prompt, hardware e estado do servidor.
- Duas rodadas completas em ordem diferente, sem jobs concorrentes.
- Comparar p50/p95 da latência total e do primeiro token quando streaming
  estiver instrumentado; taxa de saída e qualidade devem constar no mesmo
  registro. Menos tokens *não significa* mais tokens/s.
- Contar repetições de pergunta já respondida, alegações falsas de arquivo
  e execuções duplicadas como **bloqueadores**; não ocultar esses resultados
  atrás de médias de latência.

## Aceitação real (não é a suíte `direct` do Lab)

`lab/scenarios/e10-e2e-workflows.json` contém **8 fluxos/40 mensagens**:
jogo de plataforma Raylib/JS; Snake; imagem e revisão; música; pesquisa e PDF
de 3 páginas; PDF privado e prompt injection; depuração; publicação GitHub.

O operador deve executar **um cenário por conversa nova** no chat autenticado,
sem executar ações perigosas ou destrutivas. Cada turno contém uma rubrica
humanamente verificável. Salve o JSON técnico de tempos e registre avaliação
0/1/2, com recibos reais dos efeitos. Ferramentas ausentes devem produzir
limites claros, não relatórios de "sucesso".

**Não executar automaticamente:** testes de criação de música, imagem,
PDF e publicação GitHub exigem ferramentas/revisão/autorizações específicas.
O arquivo JSON é um protocolo para o operador, não uma fila de ferramentas.

## Referências verificadas

- Ollama, [API chat](https://docs.ollama.com/api/chat): durações,
  tokens processados e gerados, cache do prompt e controle de keep_alive.
- Ollama, [FAQ](https://docs.ollama.com/faq): `ollama ps`, retenção,
  paralelismo, Flash Attention, cache KV e uso de memória.
- Ollama, [streaming](https://docs.ollama.com/capabilities/streaming).
- llama.cpp, [dicas de desempenho](https://github.com/ggml-org/llama.cpp/blob/master/docs/development/token_generation_performance_tips.md):
  GPU offload e custo excessivo de threads CPU.
- Hugging Face, [SFT Trainer](https://huggingface.co/docs/trl/main/sft_trainer):
  pós-treinamento por dados conversacionais e adapters PEFT/LoRA.
