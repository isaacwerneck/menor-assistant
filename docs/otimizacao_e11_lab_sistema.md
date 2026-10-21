# E11 — Um commit, nove etapas: Menor Lab, desempenho e Menor Systems

Data: 21/10/2026. Trabalho incremental na arquitetura atual; **7B permanece padrão**.
O 14B pode ser escolhido apenas no Lab. Não instalar modelos, alterar configuração
do Ollama, usar credenciais GitHub fora dos endpoints existentes ou iniciar benchmark
no Ubuntu sem decisão explícita do operador.

## Plano executado no código (uma etapa por vez)

1. **Inventário e contratos** — examinar a fila `lab_batches`, o histórico local,
   o mecanismo de publicação idempotente, o Lab e o painel Systems. Preservar API antiga.
2. **Identificação confiável de publicação** — comparar a árvore Git de `lab-reports`
   e os blobs SHA-1 canônicos dos arquivos completos. Mostrar `sent`, `not_sent`,
   `conflict`, `invalid`; se a consulta falhar, marcar `unknown`, nunca `not_sent`.
3. **Publicação supervisionada em lote** — permitir selecionar não enviados,
   confirmar explicitamente o conteúdo completo e iniciar uma fila separada;
   um envio por relatório, sem sobrescrita, com resultado e falhas por item.
4. **Histórico utilizável** — busca por bateria/ID/modelo, filtros, agrupamento,
   paginação incremental de 15 registros e seleção em lote além da página visível.
5. **Seleção de modelos na bateria** — caixas no próprio fluxo de execução;
   de um a dois modelos instalados, validação de identificadores, filas por bateria
   e por modelo, relatórios separados com proveniência. Sem mudança no chat.
6. **Evidência de velocidade e novas baterias** — preservar métricas Ollama,
   adicionar `--thread-sweep` voluntário, criar os 12 casos E11 e exigir
   comparações repetidas com mesmas condições e revisão humana.
7. **Pesquisa técnica contra o código existente** — identificar causas prováveis
   de lentidão e descartar recomendações não confirmadas; ver tabela abaixo.
8. **Simplificação de navegação** — deixar ações principais na barra do chat e
   recolher links/exports secundários em "Mais"; capacidades avançadas no
   Systems ficam em seção expansível sem ocultar acesso.
9. **Monitoramento no Systems** — endpoint privado de leitura com CPU amostrada,
   RAM disponível/consumida, uso de GPU apenas se o driver reportar, e modelos
   carregados em `/api/ps`; atualizar a cada três segundos só com página visível.

## Pesquisa técnica: recomendações oficiais × Menor

| Evidência técnica | Estado encontrado no código | Mudança / teste que discrimina causa |
|---|---|---|
| `/api/chat` fornece `load_duration`, `prompt_eval_duration`, `eval_duration`, `eval_count` | `ops.model_latency.numeric_summary` e métricas E10 já separam fases | Preservado. Comparar geração, prefill e residual; não deduzir ausências como zero |
| `ollama ps` e `/api/ps` informam colocação CPU/GPU e pesos carregados | Hardware anterior: 7B alocado 100% CPU; Iris Xe sem offload comprovado | Systems passa a expor modelos realmente residentes e `size_vram` como memória, não como % de uso |
| CPU LLM pode saturar largura de banda de memória; mais threads nem sempre ajudam | i7-1185G7: **4 núcleos físicos/8 threads lógicas**; não há curva 1/2/4/6/8 no Ubuntu | `--thread-sweep` alterna a ordem de 5 valores, com prompts públicos fixos e tokens/s por perfil |
| Modelos maiores Q4 exigem mais leitura de pesos a cada token | 14B falhou em 16/27 decisões do planejador sob limite de 40 s; 7B não falhou | Manter 7B como padrão e comparar 7B × 14B por execução, sob mesma fila e controle de carga |
| Cache, prefixos e histórico alteram prefill; `keep_alive` só evita carregar os pesos | E10 já mede prefill e tem keep_alive longo, mas caminhos de chat e Lab divergem | Comparar frio/quente, histórico 0/4/8 turnos e pedidos com/sem catálogo, sem criar prompt gigante |
| Concorrência aumenta custo agregado de memória e pode competir pela CPU | Laboratório possui semáforo global de inferência; dois modelos podem ficar residentes sem produzir tokens juntos | **Sequência por padrão**. Paralelismo só após medição separada de p95, CPU e throughput agregado |
| Streaming reduz tempo de espera percebido até primeiro token, sem aumentar necessariamente tokens/s | `/agent/run` continua síncrono; E10 não tem TTFT nesse fluxo | Item futuro: streaming com recibos/idempotência; não misturar com experimento de threads |
| GPU integrada Intel Xe compartilha RAM do sistema; driver e backend devem ser comprovados | Sem prova de offload no servidor; detectar GPU não significa usá-la | Exibir "indisponível" se o driver não expuser `gpu_busy_percent`; não instalar driver por suposição |

Fontes primárias consultadas:
- Ollama: https://docs.ollama.com/api/chat
- Ollama: https://docs.ollama.com/api/ps
- Ollama: https://docs.ollama.com/faq
- Ollama hardware: https://docs.ollama.com/gpu
- llama.cpp: https://github.com/ggml-org/llama.cpp/blob/master/docs/development/token_generation_performance_tips.md

## Campanha operacional recomendada (não executada por esta alteração)

Pré-condição: servidor em revisão nova, Ollama ocioso, sem outro teste/geração
concomitante, modelos previamente instalados. Registrar `ollama --version`,
`ollama ps`, CPU/RAM/swap, digest, contexto, quantização e modelo escolhido.
A fila Lab consome inferência; relatórios completos contêm texto e somente são
publicados após autorização explícita e verificação de privacidade.

### 1. Curva de threads (opt-in)

```bash
cd ~/menor-assistant
python3 -m ops.model_latency --live --samples 2 --model qwen2.5-coder:7b --thread-sweep
```

São **10 inferências públicas de teste** (1, 2, 4, 6 e 8 threads, duas
rodadas alternadas). A ferramenta não grava opções globais de Ollama. Comparar
mediana tokens/s e prefill por valor de threads e estabilidade, **não escolher
o valor maior pelo número de threads**. Rodar novamente só com recursos térmicos
estáveis. Não mudar `OMP_NUM_THREADS`, unidades systemd, drivers ou quantização
junto desse experimento.

### 2. Testar qualidade × latência (um ou dois modelos)

No Lab selecionar `E11 — modelos, latência, confiança e ferramentas`.
Marcar 7B, 14B ou ambos e confirmar. Executar também
`matematica-validacao-v2`, `programacao-debug`,
`planejamento-supervisionado` e `regressoes-planejamento-v3`.
Repetir em ordem invertida (três rodadas idealmente) depois de estabilizar
carga/caches; comparar relatórios completos por modelo, p50/p95, tokens/s,
timeouts, precisão factual, formato e passos da tarefa. Os 12 casos E11 têm
avaliação automática parcial; planos abertos exigem revisão independente.

### 3. Ensaios que faltam para saber **por que** está lento

- Início frio vs. modelo carregado (duração de carregamento) e RSS/swap.
- Prompt curto vs. grande, com `prompt_eval_count` e prefill medidos.
- Gerar 16/64/128 tokens na mesma pergunta pública para distinguir custo
  por token, limite de saída e overhead fixo.
- Testar 7B isolado e depois com 14B residente, sem inferir simultaneidade
  apenas pela presença dos dois em `ollama ps`.
- Verificar frequência térmica/limite de energia e carga por processo no
  Ubuntu, sem mudanças automáticas e sem publicar dados sensíveis.
- Repetir casos E10 ponta a ponta no chat, medindo tempo de requisição e
  primeiro token **quando houver streaming autenticado com recibos**.

**Critério de aceite:** reduzir p50/p95 sem aumentar respostas falsas,
timeouts, descumprimento de formato, violação de escopo ou regressões. Uma
melhoria de testes unitários não prova aumento de tokens/s no hardware.

## Limites e privacidade

- A sincronização GitHub requer token existente e branch `lab-reports`.
  Não altera `main`; consulta indisponível não transforma arquivos em pendentes.
- Uma fila de publicação é em memória. Se a API reiniciar, conferir a branch
  de novo antes de repetir; a publicação individual é idempotente por conteúdo.
- A fila de baterias também é em memória; artefatos já concluídos sobrevivem.
- A consulta do Systems usa somente procfs e `/api/ps` local, sem terminal,
  comandos de usuário, contas externas ou divulgação de endereço/credenciais.
- CPU é porcentagem **entre duas coletas**; RAM usa `MemAvailable`.
  `size_vram` representa memória reportada, não atividade da GPU.
- A primeira leitura ou métricas ausentes são exibidas como indisponíveis,
  não zero; polling ocorre somente com página visível.
- Novos testes simulados/CI não substituem execução real 7B/14B no Ubuntu.

## Verificação do incremento

Rodar em CI Linux todos os testes existentes e os novos contratos:
`tests/test_lab_multi_sync_live.py`, `tests/test_lab_ui.js`,
`tests/test_model_latency.py`, `tests/test_lab_queue.py`,
`tests/test_lab_publish.py`, `tests/test_chat_e_system_workspace.py`.
Revisar comportamento no iPhone e PC; verificar que a opção de 14B não muda o
modelo de chat configurado no servidor.
