# Chat C — auditoria estrutural de transições V1

`ops.execution_transitions` valida sequências de eventos de execução sem I/O, banco, rede, replay ou mutação. Aceita estados `planned`, `awaiting_approval`, `queued`, `running`, `executed`, `failed`, `interrupted`, `verified`. Vincula transições a `mission_id`, `action_id` e `idempotency_key`, recusando mudanças de identidade.

Transições terminais não podem voltar a `running`; duplicações retornam `warning`. Eventos sem evidência suficiente são `unknown`. Saídas contêm apenas códigos fixos e número de transições inspecionadas, nunca campos privados.

Este é um contrato conservador para trilhas de execução futuras. Não garante que a sequência persistida seja autêntica, que a execução ocorreu ou que um evento `verified` represente validação real. A integração com o executor, política de cancelamento e reconciliação de interrupções requer contrato coordenado com Chat A/D. Não usar a auditoria como autorização de execução.

Verificação: `python -m unittest discover -s tests -p 'test_ops_execution_transitions.py' -v`, suíte completa e CI. Sem deploy ou migração.
