# Rodada v3 — planos que respeitam restrições e diagnóstico orientado a falhas

**Data:** 20/10/2026. Esta atualização parte da `main` em `18fc8659` (PR #93). Escopo: segurança de planejamento e diagnóstico de respostas; **nenhum ajuste de hardware ou treino de pesos**.

## Motivação — falhas reais

- Na triagem de 16, o Menor confundiu **redigir um comando** com **executá-lo**, e produziu um plano que omitia o deploy como etapa.
- Na comparação A/B de 24 casos, o planejador devolveu decisões inválidas e ainda houve um plano que tolerava CI vermelho.
- O Codex encontrou planos de migração que não incluíam autorização e sugestões de mover arquivos originais quando o pedido exigia preservá-los.
- A investigação mostrou tempos de **prefill** de até aproximadamente 24,9 s em uma chamada; na GPU Iris Xe não foi provado offload. Velocidade não será inferida de uma mudança no código de qualidade.

## Mudanças efetivas nesta rodada

1. **Conflitos explícitos bloqueiam persistência de plano:** no fluxo do chat, quando `src/agent/plan_constraints.py` identifica que a proposta contém ação proibida ou omite uma etapa explicitamente solicitada, `runner._understand` devolve justificativa breve sem registrar/ativar o plano. O objetivo anterior, quando existe, permanece intacto.
2. **Revisor opcional não contorna restrições:** se o segundo julgamento reformular um plano e introduzir um conflito detectável, a proposta também é bloqueada antes de persistir. Não é realizada chamada adicional ao modelo para checar regras determinísticas.
3. **Cobertura de proibições frequentes:** apagar, mover, substituir, alterar, renomear e enviar/publicar, com reconhecimento limitado de negações e listas. Regras de aprovação condicional não são tratadas como proibição absoluta de publicar. Para planos com backup, testes, rollback, autorização, deploy ou acessibilidade exigidos, essas etapas devem aparecer entre os passos, não apenas nos critérios finais.
4. **Triage segura de relatórios:** `python3 -m ops.lab_eval_analysis` agora classifica incidentes de restrição, diagnóstico de schema, geração limitada, truncamento de exibição, prefill elevado e geração longa. Imprime **somente categorias conhecidas e números**, nunca conteúdo de resposta, prompt, mensagens brutas de exceção, token nem aviso produzido pelo LLM. Preserva métricas antigas.
5. **Nova bateria:** `lab/suites/regressoes-planejamento-v3.json`, 24 perguntas **de desenvolvimento**, sendo 15 sobre planejamento e 9 de resposta direta. Inclui arquivos intactos, autorização, CI, rollback, tarefas sem deploy, pesquisa sem registro e honestidade sobre GPU e execução. Não há prova de sucesso até executá-la no Ubuntu.

## Limitações de segurança

Este é um **filtro heurístico de planos**, não verificador formal de autorização nem compreensão semântica perfeita. Pode deixar passar paráfrases novas, negar erroneamente uma proposta válida ou não captar referências a restrições antigas se elas não aparecerem no turno atual. O executor continua responsável por autenticação, aprovação de operações com efeito, sandbox e recibos reais. Planos nunca são prova de execução.

O método não marca planos sem aviso como `verificados`. A saída `decision_validated` do Lab valida contrato/estrutura, não correção semântica. Não treinar o Qwen no corpus de avaliação e depois tratá-lo como teste cego.

## Como avaliar depois do deploy

1. Atualizar via `scripts/deploy.sh` somente depois do PR aprovado.
2. Primeiro, testar no **chat real** um pedido de análise de arquivos sem mover/apagar nada. Se surgir plano inadequado, ele deve ser devolvido como não consolidado, **sem substituir objetivo salvo nem executar tools**.
3. No Lab, rodar `regressoes-planejamento-v3` (24 casos) isoladamente e salvar relatório. Publicação completa no GitHub continua **manual**.
4. Examinar qualitativamente os 15 planejamentos. Registrar se todos passos exigidos e restrições foram cumpridos. Não contabilizar as respostas sem gabarito como erros ou acertos.
5. Diagnosticar localmente: `python3 -m ops.lab_eval_analysis ~/menor-data/lab/ARQUIVO.json`; comparar depois de correções e repetir pelo menos 3 vezes.
6. Para desempenho, usar p50/p95, `prompt_eval_duration`, `eval_duration` e tokens/s. Nenhum ganho no i7/Qwen foi medido por esta alteração.

### Próximas frentes técnicas

- Ampliar teste de autorização no executor real, com sandbox para alterações em arquivos/PR e verificação de estado final.
- Corrigir falhas de entendimento em conversa natural sem depender de gatilhos por palavras.
- Medir o prefill do raciocinador com histórico, tamanho do manifesto de ferramentas e cache em ambiente controlado; reduzir latência **sem perder ferramentas ou informações necessárias**.
- Só testar aceleração Vulkan na Intel Iris Xe com suporte e permissão confirmados; manter CPU como referência se GPU não melhorar.
