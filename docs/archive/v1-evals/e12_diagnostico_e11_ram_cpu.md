# E12 — Diagnóstico após os testes E11, 21/10/2026

## RAM e processo residente

Na captura do Menor Systems: 16,6/31,1 GiB (53,4%) em uso; 7B carregado
com 4,7 GiB em pesos e buffers e 0 GiB em GPU. Esse consumo não prova
vazamento de memória, e a RAM restante não deve ser atribuída ao Menor
sem processo e contexto. O Linux informa MemAvailable como estimativa
de memória disponível, descontando cache recuperável.

Systems agora consulta um endpoint privado, somente leitura, que mostra
os 8 maiores processos por RSS a cada 15 segundos enquanto a página
estiver visível. RSS pode incluir memória compartilhada: não somar valores
nem confundir cada processo com consumo exclusivo. O endpoint não mostra
comandos de terminal, parâmetros, credenciais, usuários ou PIDs.

## Baterias E11 reais: dois relatórios publicados

- lab/reports/full/20261021T160526Z-0f5759f4.json: Qwen 2.5 Coder 7B.
- lab/reports/full/20261021T160526Z-1e32fdee.json: Qwen 2.5 Instruct 14B Q4.

Mesmo commit 967a09de e 12 casos cada. Acertos automáticos: 5/8 (7B)
e 6/8 (14B); 4 questões abertas por modelo exigem revisão humana.
Planejador: 4/4 decisões válidas no 7B, apenas 1/4 no 14B (3 timeouts).
Medianas: 1,952s (7B) e 5,244s (14B); p95: 31,394s e 40,042s.
Uma rodada é insuficiente para extrapolar p95 para todas as tarefas.

Erros factuais: ambos disseram "ollama list" no lugar de "ollama ps"
para modelos residentes. Ambos erraram 2h35 + 1h25 = 240 minutos
(7B respondeu 160, 14B respondeu 180). O 7B disse SIM à alegação de
que RAM livre garante maior throughput, que é falsa.

Gargalo identificado: 7B levou 23,43s para gerar 166 tokens (7,08 t/s),
contra 1,66s de prefill, em uma tarefa de planejamento. Outra levou
28,74s para gerar 198 tokens (6,89 t/s). O carregamento de pesos foi
menor que alguns milissegundos nessas chamadas. Portanto a fase de
geração domina o tempo dos planos longos.

No primeiro caso do 14B, prefill demorou 27,49s para 402 tokens,
com apenas 3 reportados como cacheados. Chamadas seguintes reutilizaram
~365 tokens e reduziram prefill, mas geração permaneceu entre ~3,45
e 5,59 tokens/s, com três timeouts de planejamento. São dois gargalos:
cache/prefill frio e geração sustentada no 14B.

## Mudanças instrumentais

1. A telemetria calcula também tokens de prompt estimados como não
   cacheados e proporção do cache, quando há ambos os contadores.
   Taxas brutas de prompt com prefixo cacheado não devem ser tratadas
   como tokens novos por segundo.
2. Nova flag opt-in --diagnose em ops.model_latency: quatro combinações
   de prompt público curto/longo e limites de 16/96 tokens, repetidas
   1 a 3 vezes, sem alterar configuração ou descarregar pesos.
3. Configuração opcional MENOR_OLLAMA_NUM_THREAD aceita 1/2/4/6/8.
   Ausente preserva a configuração atual. Aplicar somente se o
   experimento com variações de threads comprovar melhoria consistente.
4. Testes isolados cobrem autenticação, falha de leitura, sanitização,
   cache, CPU e limites do benchmark sem rede no CI.

## Ensaios opt-in no Ubuntu, após deploy atualizado

No diretório do Menor, com Ollama ocioso, executar sequencialmente:

    python3 -m ops.model_latency --live --samples 2 --model qwen2.5-coder:7b --diagnose
    python3 -m ops.model_latency --live --samples 2 --model qwen2.5-coder:7b --thread-sweep

São oito e dez inferências, respectivamente. Comparar geração,
prefill, cache, tamanho real das saídas, carga por processo e temperatura.
Registrar versão/digest, estado carregado e quantização, repetir em
horários/ordens alternados. Não assumir ganho na produção antes dos
testes de qualidade e latência de conversas reais.

## Referências técnicas

- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/ps
- https://docs.ollama.com/faq
- https://github.com/ggml-org/llama.cpp/blob/master/docs/development/token_generation_performance_tips.md

A orientação do llama.cpp é testar diferentes valores de threads
incluindo a contagem de núcleos físicos: 4 no i7-1185G7, em contraste
com 8 threads lógicas. A escolha efetiva depende do resultado local.
