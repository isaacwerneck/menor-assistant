# Chat A — Crítica independente de planejamento (PR #29)

O Menor já usa um planejador contextual e memória de múltiplos objetivos.
A melhoria introduz **revisão opcional de planos**, não apenas mais palavras-chave
sobre pixel art, música ou PDFs.

## Ciclo

1. O modelo de interpretação decide se responde, esclarece, planeja ou utiliza
   ferramentas existentes. Nunca recebe novas permissões por isso.
2. Quando propõe **plan** ou **continue**, e o recurso está ativado, um segundo
   pedido ao Ollama avalia se o plano responde ao objetivo atual, usa etapas
   verificáveis, evita misturar assuntos e não inventa ações concluídas.
3. Parecer `ok`: manter proposta (não significa que está correta).
4. Parecer `clarify`: fazer uma pergunta essencial, sem executar nada.
5. Parecer `revise`: devolver problemas concretos ao planejador e permitir
   **uma** nova tentativa. O novo plano é marcado como ainda não revisado
   independentemente. Pareceres não autorizam execução.
6. Modelo indisponível/timeout/JSON inválido: mostrar plano **preliminar**,
   mantendo a conversa utilizável, e sinalizar que a revisão não ocorreu.

## Privacidade, limites e ativação

- Nenhum serviço externo de IA é consultado; utiliza Ollama local.
- Revisão consulta somente a mensagem atual e resumo do plano, não arquivos
  privados brutos nem todo o histórico.
- O parecer é dados não confiáveis e não pode alterar IDs, aprovações ou
  ferramentas. O modelo revisor nunca executa operações.
- `MENOR_PLAN_REVIEW_ENABLED=1` ativa a etapa adicional. O padrão é **0**,
  pois cada plano pode exigir até duas inferências adicionais em CPU.
- `MENOR_PLAN_REVIEW_MODEL` permite escolher um modelo **já instalado** no
  Ollama; se ausente, usa `MENOR_REASONING_MODEL` ou `OLLAMA_MODEL`.
- Não instala nem treina modelo algum. São necessários testes reais de
  latência e qualidade do Qwen no notebook antes de habilitar por padrão.

## Aceite e limitação

A suíte automatizada avalia contratos, indisponibilidade e tentativas limitadas,
não a qualidade do julgamento em linguagem natural. Os testes de benchmark
`src/agent/lab.py` ainda precisam ser executados **com o Ollama real** e casos
inéditos, comparando o fluxo com e sem revisão antes de afirmar melhorias.

O plano de autonomia posterior continua incluindo execução de tarefas longas,
autoedição em sandbox, revisão externa, treinamento com exemplos curados e rollback.
