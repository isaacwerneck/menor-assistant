# E19 — Catálogo permanente de avaliação das capacidades do Menor

## Princípio

**14 baterias fixas, cada uma com uma finalidade verificável.**
Baterias antigas (E8, E15, regressões avulsas) continuam disponíveis,
mas não são contadas como capacidades adicionais. Novas hipóteses
criadas em uma investigação entram primeiro como casos exploratórios;
se relevantes, passam a uma das 14 baterias permanentes.

| Nº | Capacidade | Fase técnica | O que medir agora |
| --- | --- | --- | --- |
| 01 | Conversação natural | D | Linguagem humana, esclarecimentos úteis, naturalidade |
| 02 | Intenção semântica | A | Desejo vs. pedido explícito, paráfrases, sem palavras-chave |
| 03 | Memória e correções | A | Decisão mais recente, retomada, não inventar fatos |
| 04 | Planejamento | A | Decomposição, critérios, restrições, dependências |
| 05 | Projetos persistentes | A | Continuidade e atualização das escolhas do workspace |
| 06 | Documentos | B | Estrutura/índice, lacunas, rascunho vs. arquivo real |
| 07 | Programação | B | Especificação, depuração, código do usuário vs. do Menor |
| 08 | Ferramentas | B | Quando propor chamadas, recibos, limites e erros |
| 09 | Segurança | C | Aprovação, escopo, prompt injection, privacidade |
| 10 | Pesquisa | B | Evidência verificável, frescor, fontes, incerteza |
| 11 | Multimodal | B | Imagem/voz/música/anexos, não alegar geração sem prova |
| 12 | Delegação | A | Programador/designer/pesquisador, papéis e dependências |
| 13 | Autoaperfeiçoamento | C | Diagnóstico, correção isolada, CI, autorização, sem auto-merge |
| 14 | Desempenho | C | Erros, latência, respostas curtas, cache e truncamento |

O trabalho de **interface, desktop, mobile e implantação (frente E)**
precisa ser coberto também por testes Node, integração, segurança e
browser reais: uma resposta textual jamais prova que um botão, uma
tela ou o deploy funcionaram. Do mesmo modo, cada função real de
imagem/PDF/código necessita teste **end-to-end com artefato inspecionado**.

## Formato e custo inicial

Cada bateria principal contém duas conversas de quatro mensagens:
uma **âncora invariável** e uma conversa de variação. São
**112 mensagens por modelo** quando as 14 baterias são selecionadas
(224 com dois modelos). O Lab permanece sequencial por padrão na CPU,
sem ativar novos modelos ou executar ferramentas.

A cada nova rodada, a conversa de variação alterna entre três
formulações completas (`cycle % 3`), sempre com o mesmo objetivo,
restrições e critérios. A âncora fixa evita que uma nota melhore
apenas porque o teste ficou mais fácil.

O número da rodada é determinado pelo maior `core_cycle` salvo nos
resumos locais, mais um. Todas as baterias e **ambos os modelos da mesma
fila usam a mesma rodada**, preservada no relatório completo e no
resumo, com o índice efetivo de variante por cenário. A comparação
entre revisões deve usar a mesma âncora e, quando possível, a mesma
variação/rodada. Não misturar referências geradas em commits
diferentes sem explicitá-lo.

## Três camadas de evidência

1. **Modelo (esta atualização):** resposta/decisão real em chat ou
   roteador, com histórico composto das respostas anteriores.
   Mede latência, completude, escolhas seguras e critérios objetivos
   que tenham sido codificados. Naturalidade e correção semântica
   exigem leitura humana, não ganham nota automática por JSON válido.
2. **Contrato/CI (já existe e deve crescer):** validação Python/Node
   de argumentos, autorização, revogação, memória, persistência,
   sandbox e falhas. Pode usar mocks e não comprova o desempenho
   do 7B/14B no Ubuntu.
3. **Entrega real (próxima fase):** executor supervisionado trabalha
   em workspace de teste isolado, cria artefato, executa testes,
   verifica resultado, tenta corrigir e registra evidências.
   Manutenção do próprio Menor só em escopo separado, branch,
   diff, CI e revisão. Jamais executar a etapa 3 ao selecionar
   uma bateria de modelo sem consentimento específico.

## Como usar no Lab

- Abra **Menor Lab > Suas baterias > 14 capacidades fixas**.
- Clique em **Selecionar as 14 capacidades** para avaliação geral.
  Se estiver corrigindo só o registro de escolhas, marque
  **Memória**, **Projetos** e **Segurança**, por exemplo.
- Escolha o 7B ou dois modelos: cada modelo recebe os mesmos
  exemplos de uma dada rodada, um depois do outro.
- A cada ciclo, compare tempo, decisões inválidas, violações,
  trajetórias concluídas e casos com revisão humana pendente.
- Para um experimento causal, preserve código, contexto de
  hardware, orçamento, versão do catálogo, modelo e rodada;
  depois altere **uma variável de cada vez**. A comparação
  pareada de modelos no mesmo ciclo ajuda, mas não prova
  causalidade sem replicações.

## Regressões e inclusão de novos casos

- Toda correção de software deve acrescentar teste CI que reproduza
  a falha original, pelo menos uma paráfrase semanticamente
  equivalente quando o problema envolver linguagem, e outro
  caso adjacente para evitar sobreajuste de palavras.
- Os IDs `core-...` e as 14 finalidades são estáveis. Mudanças
  em enunciados, critérios ou ordem devem atualizar a
  `core_catalog_version`, documentar o motivo e preservar
  relatórios antigos para comparação.
- Contagem de casos aprovados **não representa** capacidade
  real de criar documentos, imagens, ferramentas ou apps.
  Baterias virtuais de modelo não exercem shell nem alteram
  dados privados.

Implementação: `lab/core/capabilities.json`,
`src/api/lab_core.py`, `src/api/lab_batches.py`,
`src/api/templates/remote_lab.html`.
