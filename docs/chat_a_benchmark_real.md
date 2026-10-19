# Chat A — avaliação reproduzível de interpretação e crítica de planos

Este incremento adiciona `src/agent/benchmark.py` para identificar regressões antes de habilitar revisão independente no notebook Intel. **Não** habilita `MENOR_PLAN_REVIEW_ENABLED`, não chama catálogo de ferramentas e não escreve em memórias, arquivos privados ou produção.

## Execução

```bash
python -m unittest tests.test_chat_a_benchmark -v
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

**Estado da entrega:** regressões de Python com mocks verificam o instrumento; inferência Qwen e tempo no Intel continuam pendentes até acesso autorizado ao servidor. Nenhuma porcentagem de progresso é inferida dos testes sintéticos.
