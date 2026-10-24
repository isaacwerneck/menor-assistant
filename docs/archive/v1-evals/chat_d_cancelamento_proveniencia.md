# Chat D — cancelamento e proveniência de execução na interface

Esta entrega fecha corridas de estado que podem aparecer quando o usuário
muda de conversa durante uma operação prolongada. A versão anterior já
oferecia `Parar` e isolava a resposta básica de texto; agora estende as
garantias a quatro caminhos de operação.

## Fronteiras corrigidas

- Recuperação de tarefa interrompida (`/agent/runs/{id}/recover`) usa o
  sinal de cancelamento da geração e só altera `pendingRunRecovery` após
  verificar que a resposta pertence à conversa ainda ativa.
- Consultas de missão e disponibilidade de skill também usam o sinal,
  conferindo novamente o turno antes de atualizar o estado. Assim uma
  resposta tardia não marca o modelo como pronto em outro chat.
- Leitura de streaming é cancelada no navegador ao trocar ou parar,
  sem alegar reversão de operações já iniciadas no servidor. Recibos
  de status incerto permanecem sujeitos à reconciliação específica.
- Mensagens de eventos não usam sinal de sucesso para `planned`, `failed`
  ou estado desconhecido. Apenas `executed` recebe ✓; eventos são
  renderizados como texto puro, com limite de itens e tamanho de campos.

## Segurança

Uma operação já iniciada pode continuar no backend após o cancelamento
do navegador. O usuário não deve repetir automaticamente uma escrita
cujo recibo tenha ficado incerto. As autorizações são ligadas à sessão,
ao turno e às políticas do executor Python, nunca a uma frase solta
capturada em outra conversa.

## Validação

Testes Node reproduzem:
- retorno atrasado de recuperação com navegação entre chats;
- skill retornando pronta depois do cancelamento;
- stream bloqueado e `reader.cancel()` no navegador;
- distinção de executado, planejado e falho no recibo.

CI e testes simulados não substituem Safari/iPhone, encerramento real de
conexão nem monitoramento do Qwen. Após deploy verificar no navegador
e pelo monitor SSH antes de afirmar que o bug está totalmente eliminado.
