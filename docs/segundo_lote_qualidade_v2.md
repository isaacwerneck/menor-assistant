# Segundo lote v2 — conversa natural, planos, confiabilidade e desempenho

Esta entrega integra quatro prioridades identificadas na triagem de 16 casos, além
da demanda do proprietário por linguagem natural e menor latência.

## Mudanças de comportamento

- **Voz conversacional unificada:** o chat comum, o raciocinador estruturado e
  o laboratório experimental compartilham orientações para conversar em português
  brasileiro natural, ajustar o nível de detalhe ao pedido e evitar jargão e
  estruturas artificiais. Isso **não** significa que o modelo foi retreinado.
- **Ações verificáveis:** a linguagem instrui explicitamente a distinguir
  sugestão, plano, simulação, execução e resultado verificado. O executor e
  seus gates continuam sendo a autoridade; texto do LLM nunca é recibo.
- **Planos preliminares:** verificações determinísticas, sem chamada adicional
  ao modelo, podem sinalizar etapas que contrariam restrições claras sobre
  preservação de arquivos ou omitiram um deploy explicitamente solicitado.
  Essas verificações são **heurísticas**, não provam completude e não autorizam
  ferramentas. Auditoria profunda de planejamento permanece opcional porque
  uma segunda inferência pode aumentar bastante a latência.
- **Avaliador binário:** `grader=boolean` aceita `NÃO`, `Não.` e `nao!`,
  mas rejeita respostas contraditórias como `sim, não`. Casos que exigem
  formato estrito continuam em `grader=strict` e não são relaxados.
- **Telemetria do laboratório:** salva só métricas numéricas do Ollama
  (tokens gerados, tempos de geração, carregamento etc.) e informa que
  `decision_validated` prova somente validade estrutural, não qualidade do plano.

## Como rodar um A/B justo

As baterias `segundo-lote-base-v2` e `segundo-lote-naturalidade-v2`
contêm **as mesmas 24 perguntas e rubricas**, diferindo apenas em
`profile=baseline` ou `profile=natural` para os testes diretos. Os
testes de planejamento usam o raciocinador estruturado compartilhado, portanto
**não são um A/B isolado de estilo de planejamento**.

1. Fazer deploy da versão aprovada. Confirmar a página do laboratório.
2. Executar **Segundo lote A — perfil antigo**. Não iniciar outra bateria
   enquanto a execução estiver ocorrendo.
3. Publicar o relatório **manualmente** no GitHub após revisar privacidade.
4. Executar **Segundo lote — linguagem, execução, planejamento e desempenho**,
   nas mesmas condições de temperatura/hardware e sem mudanças de modelo.
5. Publicar manualmente. Para maior confiança, repetir cada lote três vezes e
   alternar a ordem em rodadas futuras; uma execução isolada pode variar.
6. Comparar dois relatórios com `python -m ops.eval_compare ARQUIVO_ANTES ARQUIVO_DEPOIS`.
   O comparador exige mesmo grupo A/B e prompts, histórico, modo e critérios
   idênticos. Não equiparar automaticamente as notas das rubricas abertas a
   acertos/erros: revisar as respostas no relatório privado.

O grupo `linguagem-v2-24` não é benchmark cego: os prompts de avaliação
estão versionados no Git. É um **teste de desenvolvimento**, não uma medição
de capacidade geral definitiva.

## Métricas e limites

- Acertos automáticos, erros e casos sem nota são **três contagens separadas**.
- `latency_p50_seconds` e `latency_p95_seconds` consideram tempos medidos
  de ponta a ponta por caso. `generation_tokens_per_second_p50` usa
  apenas respostas do Ollama que forneceram métricas válidas.
- Edição real de arquivos, uso de navegador, GPU real, merge e autorização
  continuam fora do laboratório direto/planner. Esses cenários precisam de
  harness com ferramenta isolada, recibos e verificação do estado final.
- Não auto-ajustamos `num_ctx`, `num_thread`, `num_gpu`, overclock,
  permissões de sistema nem instalação de drivers por causa destes testes.
- Os dois perfis diretos têm o mesmo teto de 256 tokens no laboratório. O
  perfil natural muda a orientação e a temperatura de amostragem; os ganhos
  de tempo precisam ser conferidos com métricas de tokens por segundo e
  comprimento de resposta, não apenas com segundos brutos.

## Diagnóstico do hardware Ubuntu, sem alterações

Os seguintes comandos rodam no próprio servidor Ubuntu, não no ChatGPT.
Não exigem token de GitHub e não produzem nem enviam prompts:

```bash
cd ~/menor-assistant
python3 -m ops.ollama_hardware
ollama ps
python3 -m ops.model_latency --live --samples 3
```

O diagnóstico lê `/proc/meminfo`, consulta `/api/ps` na interface
**loopback** do Ollama e, se disponível, usa `lspci` para reconhecer o
tipo da GPU. Ele não altera configurações. O comando de benchmark
faz três inferências curtas com perguntas públicas fixas, **somente**
quando executado com `--live`.

### Interpretação correta

- **6 GB de RAM residente com sistema ocioso:** pode ser normal para pesos
  quantizados do Qwen carregados. O Menor usa `OLLAMA_KEEP_ALIVE=24h` por
  padrão para evitar recargas. RAM livre não implica potência desperdiçada.
- **32 GB de RAM:** dão espaço para modelos/contextos maiores e caching,
  mas não aceleram tokens automaticamente; CPU, largura de banda de memória,
  quantização e GPU podem ser os gargalos.
- **i7:** comparar taxa de tokens por segundo em condições sem carga concorrente;
  percentual de CPU sozinho é insuficiente, especialmente em CPU multithread.
- **GPU presente:** `lspci` comprova apenas dispositivo detectado. Verifique
  a coluna PROCESSOR de `ollama ps` ou `vram_gib` no diagnóstico para
  indícios de offload. Sem identificação da GPU/VRAM/driver não podemos
  concluir que aceleração de Qwen é suportada.
- **CPU constante em monitor:** investigar definição do gráfico, janela de
  amostragem e processos; não inferir inferência ativa por RAM residente.
- **Respostas longas/36s:** analisar tokens/s, tempo de avaliação do prompt,
  carga de modelo e tamanho da resposta. Evitar reduzir qualidade só para
  melhorar uma média de segundos.

## Próxima intervenção condicionada às medições

1. Obter snapshot de CPU/RAM/GPU/VRAM sem dados secretos.
2. Medir latência fria e aquecida, p50/p95 e geração tokens/s.
3. Se GPU suportada e não usada, validar driver/backend do Ollama;
   se não suportada, testar versões quantizadas/modelos de instrução
   compatíveis. Não instalar ou trocar modelo automaticamente.
4. Comparar, em A/B, modelo original e alternativa com **mesmo** prompt,
   contexto, hardware e limites de saída.
5. Só promover configuração nova se qualidade/segurança não regredirem.

Este documento orienta a fase inicial. A próxima fase precisa de testes
integrados de autonomia com ferramentas e avaliações de conclusão real.
