# Hardware real, medições de inferência e diagnóstico da lentidão

**Observado no Ubuntu do proprietário em 20/10/2026.** Dados recebidos por fotos legíveis de terminal e JSON gerado por `python3 -m ops.ollama_hardware` e `python3 -m ops.model_latency --live --samples 3`. O GitHub não dispõe de SSH/shell no servidor do usuário, portanto números de telemetria ao vivo precisam ser verificados localmente na próxima sessão.

## Inventário do servidor

| Item | Medida ou constatação | Evidência/nota |
|---|---|---|
| Máquina | Notebook/servidor `nakedrift`, usuário local `isaac` | Prompt de shell `isaac@nakedrift:~/menor-assistant` |
| SO | Ubuntu Server 24.04 LTS (instalado previamente) | `docs/roadmap.md`; terminal mostra Python 3.12 do Ubuntu |
| CPU | **Intel Core i7-1185G7 @ 3,00 GHz**, 11ª geração, 4 núcleos/8 threads | `lscpu | grep 'Model name'` e `os.cpu_count() = 8` |
| RAM física | Comercialmente 32 GB; **31,06 GiB** reportados em `/proc/meminfo` | Medida em 20/10 |
| RAM disponível | **23,87 GiB** | Snapshot, não consumo fixo ou medida de benchmark |
| Swap | **8,00 GiB total e 8,00 GiB livres** | Sem pressão de swap no snapshot |
| GPU | **Intel TigerLake-LP GT2 [Iris Xe Graphics] (rev 01)**, integrada | `lspci`, `/dev/dri/card1` e `/dev/dri/renderD128` presentes |
| Memória GPU do modelo | **0,00 GiB reportados** (`size_vram=0`) | Resposta Ollama `/api/ps` |
| Ollama | **0.40.6** | `ollama --version` |
| Modelo | `qwen2.5-coder:7b` | `ollama ps` |
| Tamanho residente | `ollama ps`: **5,1 GB**; `/api/ps` pesos: **4,72 GiB** | Unidades/categorias não idênticas; overhead/cache explica diferença parcial |
| PROCESSOR | **100% CPU**, não GPU | `ollama ps`; significa colocação dos pesos, **não CPU a 100% de utilização constante** |
| Contexto reportado | **4096 tokens** | `ollama ps` |
| Keep alive | Modelo relatou ~23 horas até descarregar; default do Menor `OLLAMA_KEEP_ALIVE=24h` | Evita custo de recarregar pesos entre perguntas |
| Diagnóstico Vulkan | `command -v vulkaninfo` não retornou caminho | Na medição ainda não se demonstrou que `vulkaninfo`/driver Vulkan funcionam |
| Dispositivos gráficos | `/dev/dri/card1` grupo video; `renderD128` grupo render | Existência não prova acesso permissivo do processo Ollama nem uso de GPU |

**Não supor que `Intel Iris Xe` equivale a GPU dedicada.** É gráfica integrada e compartilha memória e largura de banda com o CPU; `0 GiB` de VRAM do Ollama é a prova operacional relevante de que **este modelo** não tinha offload naquele momento.

## Benchmark concluído, Ollama 7B em CPU

Comando real executado no checkout `~/menor-assistant`:

```bash
python3 -m ops.model_latency --live --samples 3
```

| Sonda | Tokens de saída | Tempo ponta a ponta | Velocidade de geração | Tempo de geração |
|---|---:|---:|---:|---:|
| 1 — algoritmo em uma frase | 28 | **2,774 s** | **10,51 tokens/s** | aprox. 2,664 s |
| 2 — lista vs. dicionário Python | 48 | **4,791 s** | **10,24 tokens/s** | aprox. 4,686 s |
| 3 — backup local em duas etapas | 80 | **9,495 s** | **8,52 tokens/s** | aprox. 9,388 s |

**Medianas:** 4,791 segundos para essas três perguntas breves; **10,24 tokens/segundo** gerados. Máximo da amostra: 9,495 s. O terceiro caso atingiu o limite `num_predict=80` do benchmark — pode truncar resposta; não transformar duração em prova de qualidade. `load_duration` reportado foi inferior a 1 ms nas sondas: o modelo **já estava aquecido**, e `prompt_eval_duration` girou em torno de 0,10 s para prompts de 40–46 tokens. A maior parte do tempo foi `eval_duration` (geração de saída).

Primeira tentativa desse benchmark foi interrompida manualmente (`KeyboardInterrupt`), sem erro demonstrado do Ollama. A tentativa posterior de três amostras terminou normalmente. O script mede **inferência não streaming**, não tempo até o primeiro token, concorrência real ou tarefas agênticas completas.

### Efeito sobre o usuário

Na primeira triagem real de 16 casos, o tempo acumulado foi **172,244 s**; perguntas curtas em formato estrito saíram em ~0,6–1,8 s, mas certos pedidos abertos consumiram **26–37 s**. Os maiores tempos: backup coloquial **36,538 s**, explicação sobre dados de desenvolvimento/validação **36,140 s**, plano de site **27,664 s**, duplicados **26,914 s**. Os dois casos de planejamento somaram ~54,6 s. Há ainda overhead de decisão estruturada, contexto, possíveis revisões e tamanho de resposta. **Não atribuir toda a latência exclusivamente à CPU**, mas a geração de ~10 tokens/s é gargalo comprovado.

Na avaliação inicial, um pedido retornou `inference_failed` após ~50 s e um plano retornou `no_valid_decision` após ~40 s; distinguir timeout/parse de erro cognitivo.

## O que sabemos, o que suspeitamos e o que não sabemos

- **Comprovado:** RAM não estava pressionada; o modelo estava em CPU; a geração foi o maior componente do benchmark; manter 5,1 GB residentes ocioso é esperado com keep-alive.
- **Provável:** saídas extensas e duas etapas do raciocinador/planejador elevam latência; modelos menores/quantização apropriada podem reduzir tempo, mas podem perder qualidade.
- **Não comprovado:** driver e backend Vulkan instalados/compatíveis; capacidade da Iris Xe acelerar de fato o Qwen; nível atual de utilização por core, frequência térmica, limite de energia, taxa máxima de memória, API sob concorrência, ganho de `num_thread`, quantização ótima.
- **Engano a evitar:** `100% CPU` em `ollama ps` informa alocação do modelo, **não** que todos os núcleos ficam trabalhando continuamente; ocupar 32 GB de RAM não significa tornar respostas mais rápidas.

## Diagnóstico local seguro (sem mudanças)

```bash
cd ~/menor-assistant
ollama --version
ollama ps
python3 -m ops.ollama_hardware
python3 -m ops.model_latency --live --samples 3  # faz 3 inferências curtas, opt-in
lspci | grep -Ei 'vga|3d|display'
lscpu | grep 'Model name'
command -v vulkaninfo || true
ls -l /dev/dri
id -nG
```

`ops.ollama_hardware` não modifica serviços, configurações ou modelos. `model_latency` envia apenas três prompts públicos fixos ao endpoint Ollama loopback quando `--live` está presente. Fazer benchmark com Menor Lab ocioso; não rodar concorrência do navegador para comparar cenários.

## Plano de otimização, em ordem

1. **Capturar baseline reprodutível:** commit de `main`, `ollama --version`, modelo, opções, CPU/ram, GPU, throughput, tempos de carregamento/prompt/geração, número de tokens; três ou mais repetições com ordem alternada.
2. **Investigar o Vulkan/driver com cautela:** verificar `vulkaninfo --summary` se ferramenta disponível, dispositivo correto, grupos `render`/`video`, driver Mesa e versão do Ollama. Não instalar driver, não forçar flags, não reiniciar serviço ou expor GPU sem autorização; fazer prova em ambiente reversível. Compatibilidade e desempenho **não garantidos** para Iris Xe.
3. **Comparar CPU vs GPU somente se suportada:** mesma versão, mesmo modelo, mesmas perguntas/limites, carga semelhante. Usar `ollama ps` e `size_vram` para verificar uso real, além de medir tokens/s e qualidade. Se for mais lento/instável, voltar ao baseline.
4. **Avaliar modelos/quantizações menores** para conversa vs código, quando autorizado baixar modelos; deixar o 7B como controle, sem reduzir segurança/qualidade para buscar velocidade.
5. **Reduzir trabalho desnecessário:** prompts mais objetivos, evitar planos e revisão duplicados quando pergunta é simples, limitar respostas sem cortar tarefas complexas, cuidar da janela de contexto. Não aumentar `num_ctx` arbitrariamente.
6. **Proteger qualidade:** repetir segundo lote A/B e baterias de segurança/planejamento, comparar p50/p95, taxa de falha, tokens/s e revisão humana. Alterações rápidas devem ser rollbackáveis.

**Decisão até esta data:** nenhum ganho por GPU nem otimização de runtime foi implementado ou medido. A investigação ainda está em andamento.
