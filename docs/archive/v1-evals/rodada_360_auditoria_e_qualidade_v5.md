# Rodada v5 — auditoria de 360 execuções e melhorias verificáveis

**Data:** 20/10/2026. **Baseline da main:** `3687210b` (PR #96).
**Ambiente observado:** Ubuntu no i7-1185G7, 31,06 GiB RAM, Qwen 2.5 Coder 7B
carregado 100% em CPU, Intel Iris Xe sem offload demonstrado. Os relatórios
são de uma máquina privada; o GitHub permite examinar JSON já publicado, mas
não executar o modelo, instalar drivers ou medir resposta *depois* do deploy.

## Fonte e contagem sem duplicações indevidas

Consulta GitHub, ramo **privado** `lab-reports`, diretório
`lab/reports/full/`: **25 relatórios** no total, dos quais **15** com
prefixo de execução `20261020T162713Z`. Esses 15 acumulam:

| Indicador | Valor | Interpretação correta |
|---|---:|---|
| Execuções de caso | **360** | 192 da agregação + 14 lotes temáticos de 12 |
| Pares únicos pergunta/histórico | **204** | A agregação repete parte do conteúdo; não são 360 prompts únicos |
| Acertos automáticos | **142** | Apenas os critérios determinísticos configurados |
| Falhas automáticas | **36** | Algumas são falso negativo por formato; inspecionar |
| Sem nota automática | **182** | **Não** são erros; exigem revisão humana por rubrica |
| Falhas técnicas de inferência/contrato | **21** | Inclusive timeouts/JSON inválido; alguns já duplicados nas 360 execuções |
| Latência mediana de caso | **6,907 s** | Mistura curtas e longas, modos distintos |
| Prefill mediano reportado | **1,341 s** | Não incluem casos sem métricas válidas |
| Geração mediana reportada | **3,885 s** | Quando respondida; 84 gerações gastaram mais de 20 segundos |
| Limite de saída explicitamente reportado | **25 casos** | Outros com 256 tokens podem ter sido cortados sem marcação confiável |

**Não** tratar `142/360` como "precisão do Menor": 182 não têm nota
automática e os casos duplicados são correlacionados. Também não tratar
`142/(142+36)` como acerto geral, porque avalia apenas critérios automáticos.

Dos 25 relatórios completos, apenas 15 são identificáveis como parte dessa
publicação recente. Embora a interface tenha indicado uma seleção de 24
baterias, **a auditoria GitHub não comprova que 24 relatórios distintos foram
publicados nessa execução**. Conferir gaveta/histórico local antes de afirmar
que os nove restantes foram enviados. Relatórios já existentes podem coincidir
com parte da seleção.

## O que realmente falhou

- **Matemática:** `matematica-validacao-v2` marcou 7 acertos / 5 erros
  matemáticos genuínos: conversão de tempo, probabilidade, juros simples
  e média. Uma ferramenta `math.calculate` já existe para o agente, mas
  **não é usada no modo direct**. Orientar o modelo a verificar a fórmula
  não garante o acerto matemático.
- **Ferramentas/recibos:** `simular-vs-real` respondeu incorretamente
  que redigir comando equivale a executá-lo. O Lab `direct` usa uma baseline
  quase sem instruções e **não representa o executor supervisionado**.
  Verificar ação e recibo de fato separadamente no chat completo.
- **Injeção em dados:** casos de texto entre aspas, logs e notas com
  instruções falsas demonstraram confusão de limites de confiança.
  Em alguns houve timeout. Nunca promover texto recuperado a instrução
  de sistema ou prova de execução.
- **Interpretação de metadados:** o modelo respondeu que extensão `.pdf`
  garante conteúdo válido e que presença de GPU garante uso da GPU.
- **Contexto e gabarito:** `relatórios` vs `relatorios` e `sete` vs
  `7` são respostas potencialmente equivalentes rejeitadas por substring
  estrita. Preserve pontuação histórica; sugerir revisão humana, **não**
  marcar automaticamente como correto.
- **Naturalidade/latência:** muitas respostas extensas tocaram o orçamento
  de 256 tokens, com 35–50 s e algumas interrupções. O maior custo observado
  na massa é geração, não prefill. O chat real pode ter gargalos diferentes:
  anteriormente o Codex encontrou prefill ~25 s num fluxo com tools/contexto.
- **Planos:** `tarefas-multietapa` concluiu 12 decisões estruturalmente
  válidas, mas os 12 casos estavam sem avaliação qualitativa. Outro teste
  de planejamento teve timeout. **Plano JSON válido não prova execução,
  segurança ou qualidade**.

## Mudanças implementadas nesta branch v5

1. **Perfil opt-in `assistant` para o Lab direto**, com orientações
   genéricas de naturalidade, honestidade, análise de dados não confiáveis,
   aritmética e formatos estritos. **Baseline e natural históricos ficam
   intactos**; os relatórios antigos permanecem comparáveis entre si.
2. **Orçamento de saída proporcional ao formato pedido**: somente quando o
   usuário pede *só* SIM/NÃO, número, comando, campo ou poucas frases.
   Perfil assistant do Lab: limite pequeno para formato explícito, 176
   tokens para respostas normais, até 256 para demanda detalhada. Chat
   fallback: 56/96/256/512 tokens conforme formato. Isso visa eliminar
   saídas longas inúteis no Qwen da CPU sem cortar documentos complexos.
   **É um limite de geração, não prova de que o conteúdo estará correto.**
3. **Decodificação do planejador sem ações inexistentes:** quando o catálogo
   `tools=[]` é explicitamente vazio (como no laboratório planner), a
   estrutura JSON não oferece `act`, `tool` ou `arguments`. Não
   elimina gates reais nem remove ferramentas do chat principal.
4. **Auditoria privada offline:** `python3 -m ops.lab_batch_audit ~/menor-data/lab`
   informa contagens, repetição de perguntas, resultados, erros técnicos,
   p50/p95, prefill/geração e limites sem exibir perguntas, respostas ou
   históricos. Não envia dados à rede nem edita relatórios.
5. **Revisão de falsos negativos sem maquiar acertos:** `ops.lab_eval_analysis`
   identifica candidatos de equivalência de acento e números pequenos
   por extenso; apenas sinaliza `possible_format_mismatch`, sem alterar
   `automatic_pass` ou gabarito anterior.
6. **Teste real de ferramenta isolada:** regressões garantem que cálculo
   local retorna recibo e a conversa seguinte pode reconhecê-lo sem
   executar a ferramenta novamente. A ferramenta não comprova que
   interpretou a pergunta matemática de forma correta.
7. **Novo A/B de 46 casos idênticos:** `comparacao-qualidade-baseline-v1`
   e `comparacao-qualidade-assistente-v1` usam as mesmas perguntas
   originais de matemática, segurança de dados, recibos e lógica
   (46 casos diretos, dois perfis). A análise separa acertos, falhas,
   tempo, tokens e casos abertos; exige repetição e revisão humana.

### Cuidado na comparação A/B

O perfil `assistant` muda **orientações e orçamento de saída**.
Consequentemente, não é um experimento isolando somente o prompt;
o eventual ganho de velocidade pode vir do limite de tokens. Comparar
também número de tokens e erros de truncamento. Ambos preservam modelo,
temperatura e perguntas, desde que o operador não mude o Ollama entre rodadas.
Não tratar esses exemplos já publicados como benchmark cego independente.

## Aplicação e aceite no Ubuntu

Depois de CI verde, merge e deploy explícito pelo operador:

```bash
cd ~/menor-assistant
bash scripts/deploy.sh
python3 -m ops.lab_batch_audit ~/menor-data/lab
```

Abrir Menor Lab autenticado e executar **Controle — 46 perguntas anteriores**
e **Assistente — 46 perguntas idênticas** em sequência, sem benchmarks
concorrentes. Publicar os relatórios completos **manualmente após revisão
de privacidade**, pela UI do Lab. Repetir alternando ordem pelo menos três
vezes, revisar casos abertos, confrontar com o chat verdadeiro. No menu de
teste individual, selecionar perfil `Assistente aprimorado` para comparar
antes de lançar todos os casos.

Registrar para ambas: p50/p95 de resposta, tokens/s, prefills, tokens
gerados, limites, acertos sobre avaliados, falhas técnicas, casos sem nota,
qualidade humana de respostas e cumprimento de permissões. **Não afirmar
ganho de segundos ou pontos antes de executar a nova rodada.**

## Próximos problemas que nenhuma mudança de prompt resolve sozinha

- Evoluir a execução supervisionada de tools de acordo com recibos e
  evidência do estado final; simulações de planner não provam ferramentas.
- Reproduzir o prefill excepcional do chat real com histórico grande,
  catálogo e busca semântica, usando `agent_metrics` do PR #95.
- Se o Qwen permanecer em ~7–10 tokens/s na CPU, testar (com autorização)
  modelo de instrução quantizado menor ou backend suportado para Iris Xe;
  **não** assumir que 32 GB RAM ou detectar GPU garanta aceleração.
- Resgatar avaliação humana de 182 respostas abertas, incluindo
  planos e segurança. Não automatizar nota via LLM sem rubric e validação.

**Sem mudanças de drivers, unidades systemd, tokens, envio automático de
relatórios, autenticação, permissões ou modelo de produção nesta rodada.**
