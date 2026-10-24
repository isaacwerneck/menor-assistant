# Chat A — recuperação segura de turnos interrompidos

## Problema

Antes deste incremento, uma queda da API entre o início e o fim de uma
operação podia deixar a conversa na fase running indefinidamente. Reiniciar
a ação diretamente seria perigoso: um arquivo, PR ou projeto poderia já ter
sido criado, mesmo que o Menor não tivesse recebido o comprovante final.

## Alterações

- Um lock Linux por conversa acompanha o processamento completo do agente.
  Outra execução ou tentativa de recuperação encontra esse lock e é
  bloqueada, inclusive se ocorrer em outro processo do servidor.
- O SQLite privado do agente registra snapshot do estado anterior ao turno.
  Ao terminar corretamente, o snapshot temporário é eliminado.
- Em caso de interrupção, uma recuperação explícita encerra o turno sem
  reexecutá-lo; a resposta antiga passa a indicar resultado incerto.
- Se existia um plano, ele fica pausado, nunca volta automaticamente para
  um estado de autorização. O usuário pode examiná-lo e retomá-lo depois.
- O endpoint autenticado POST /agent/runs/{session_id}/recover só funciona
  com confirmed=true. A versão GET do estado permanece estritamente leitura.
- Quando o chat recebe conflito de execução, explica o risco e pergunta
  naturalmente se o proprietário quer liberar o estado. Responder não não
  muda nada; responder sim exige que o lock antigo já tenha sido liberado.

## Segurança

A recuperação **não** é rollback: não desfaz efeitos externos e não prova
que nada aconteceu. O usuário deve conferir o último resultado antes de
pedir a mesma operação novamente.

O sistema não fornece acesso a shell, instalação de modelos, auto-merge ou
permissões adicionais. Não recupera a execução de workers assíncronos de
subagentes, que possuem seus próprios estados.

Os arquivos de lock e snapshots ficam em diretórios privados de memória.
Não contêm logs de comandos a serem executados novamente. A API verifica
sessão autenticada e exige uma confirmação separada.

## Critérios de testes

- Recuperação de um turno interrompido não duplica execução.
- Repetição com o mesmo ID retorna recibo terminal de interrupção.
- Lock de processo ativo recusa a recuperação.
- Aprovação antiga não reaparece após recuperação.
- Plano pode ser localizado no histórico pausado.
- Sessão concluída não é modificada.
- Endpoint não autenticado, ou sem consentimento, é recusado.
- Chat oferece pergunta de consentimento e permite recusa sem efeitos.

## Limites

Se houver perda física do arquivo SQLite, este mecanismo não substitui
backups. Operações externas realizadas fora do processo do agente podem
ter andamento próprio. Recuperação de objetivos longos com múltiplas
etapas e checkpoint detalhado permanece uma etapa futura do plano.
