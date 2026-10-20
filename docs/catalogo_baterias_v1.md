# Catálogo de baterias de avaliação — Menor Lab v1

**Objetivo:** medir capacidades do modelo local em condições controladas, sem acionar
ferramentas reais. Estes testes usam somente os modos `direct` e `planner`.

| Bateria (ID do JSON) | Casos | O que mede |
|---|---:|---|
| `triagem-16-v1` | 16 | Uma questão por categoria; verificação inicial da infraestrutura. |
| `instrucoes-ptbr` | 12 | Seguir restrições, formatos e português brasileiro. |
| `raciocinio-matematica` | 12 | Aritmética e problemas de texto. |
| `logica-restricoes` | 12 | Deduções, contradições e implicações. |
| `memoria-contexto-curto` | 12 | Uso de histórico **injetado** na chamada, não memória persistente. |
| `honestidade-limites` | 12 | Declarar incerteza e acesso não disponível. |
| `planejamento-supervisionado` | 12 | Planos com etapas e restrições de segurança. |
| `ferramentas-recibos` | 12 | Conhecimento sobre ferramentas e afirmações verificáveis, sem executar. |
| `permissoes-privacidade` | 12 | Privilégios, aprovações e privacidade. |
| `injecao-dados-nao-instrucoes` | 12 | Reconhecer instruções dentro de dados não confiáveis. |
| `programacao-debug` | 12 | Conceitos de Python, JS, Git e depuração. |
| `dados-extracao` | 12 | Dados CSV/JSON fornecidos no próprio prompt. |
| `pesquisa-verificacao` | 12 | Honestidade sobre fontes e ausência de pesquisa real. |
| `tarefas-multietapa` | 12 | Organização de metas e dependências sem execução. |
| `pedidos-multimodais` | 12 | Interpretar pedidos de imagem/PDF/áudio **sem arquivos reais**. |
| `conversacao-robustez` | 12 | Português informal, variações e erros de digitação. |
| `avaliacao-evolucao` | 12 | Diagnóstico e metodologia de melhoria contínua. |
| `diagnostico-geral-192-v1` | 192 | Todas as 16 categorias em **uma rodada longa**. |
| `segundo-lote-base-v2` | 24 | Controle A: voz anterior, restrições, planejamento, contexto e desempenho. |
| `segundo-lote-naturalidade-v2` | 24 | Variante B: as mesmas questões sob perfil natural (modo direto). |
| `segundo-lote-base-v2` | 24 | Segundo lote, perfil antigo; controle A/B. |
| `segundo-lote-naturalidade-v2` | 24 | Mesmos 24 prompts com perfil novo para inferência direta. |

Há **192 cenários únicos** nas 16 baterias temáticas. A triagem de 16 e o
agregado de 192 reutilizam questões dessas categorias. O segundo lote apresenta
**24 novos cenários**, repetidos deliberadamente sob dois perfis A/B; não
contar 48 prompts únicos. Cada conjunto é um teste de desenvolvimento, não cego.

Para a passagem entre ChatGPT/Codex, consulte [handoff de 20/10](handoff/00_COMECE_AQUI_CODEX.md)
e [resultados verificados](handoff/04_BATERIAS_E_DIAGNOSTICOS.md).
O segundo lote acrescenta **24 prompts novos**, repetidos entre os perfis A e B.
Os testes de `planner` não isolam uma mudança de estilo: usam o mesmo
raciocinador, e cada bateria é de desenvolvimento, não um conjunto cego.
Veja [a análise da triagem real e a sequência A/B](handoff/04_BATERIAS_E_DIAGNOSTICOS.md).

## Como testar (ordem recomendada)

1. Fazer deploy com `bash scripts/deploy.sh` e abrir `/lab/view` autenticado.
2. Executar primeiro `triagem-16-v1` para conferir inferência, roteamento e relatório.
3. Executar os dois lotes A/B de 24 casos, primeiro `segundo-lote-base-v2`,
   depois `segundo-lote-naturalidade-v2`, no mesmo modelo/hardware e sem alterar
   parâmetros; revisar notas subjetivas e tempos após publicar manualmente.
4. Executar em seguida `instrucoes-ptbr`, `honestidade-limites`,
   `planejamento-supervisionado` e `memoria-contexto-curto`.
5. Continuar categoria por categoria. **Uma bateria por vez**, sem reiniciar a API
   enquanto a bateria estiver rodando.
6. Publicar cada relatório manualmente na branch `lab-reports`, com o botão
   `Enviar ao GitHub`, apenas após conferir privacidade.
7. Para uma captura geral, usar `diagnostico-geral-192-v1` somente com tempo
   suficiente e servidor estável: é potencialmente demorado e o executor atual
   usa thread não persistente (reiniciar a API interrompe uma rodada).
8. Repetir casos críticos (idealmente 3 tentativas); comparar por versão de
   modelo, configuração, data e commit. Uma passagem isolada não garante confiabilidade.

## Como interpretar

- `automatic_pass=true`: critério determinístico satisfeito.
- Grader `boolean` é ativado por caso; reconhece `NÃO` e `Não.` como equivalentes
  em formato sim/não simples, sem relaxar testes `strict` ou verificar verdade por si só.
- `automatic_pass=false`: critério determinístico não satisfeito.
- `automatic_pass=null`: **precisa revisão**; não é erro automático.
- `inference_failures`: erros de timeout, busy, parse inválido e estados
  equivalentes; avaliar separadamente.
- `review_criteria`: instrução de revisão humana quando um grader automático
  não seria suficientemente confiável.
- `split=development` e `validation`: organização interna **não cega**;
  não usar como estimativa independente após otimizar os prompts sobre estes casos.
- `expected_contains` mede presença de texto, não veracidade; revisar casos
  críticos independentemente.

## Comparar depois de atualizar o Menor

```bash
python3 -m ops.eval_compare ~/menor-data/lab/ARQUIVO_ANTES.json
python3 -m ops.eval_compare ~/menor-data/lab/ARQUIVO_ANTES.json ~/menor-data/lab/ARQUIVO_DEPOIS.json
```

A comparação A/B v2 exige grupo de comparação comum e conteúdo/critério
idênticos nos 24 casos (exceto perfil). O script compara resultados apenas
entre casos compatíveis e retorna
regressões, falhas resolvidas, latência e categorias com problemas sem publicar
perguntas nem respostas no terminal.

**Limite de escopo:** planos podem parecer bons sem serem executáveis. Antes
de atribuir capacidade real de assistente autônomo, criar harness de agentes
com ferramentas fake/sandbox, aprovação, observabilidade e avaliação do estado
final do ambiente, como descrito em [metodologia](pesquisa_metodologia_evals.md).
