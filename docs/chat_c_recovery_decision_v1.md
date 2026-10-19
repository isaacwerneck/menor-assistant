# Chat C — decisão de recuperação segura V1

O módulo `ops.recovery_decision.recovery_decision` é uma função pura e conservadora. Não lê filas, banco, arquivos ou rede, não executa ferramentas e **nunca** retorna autorização para repetir efeitos. É um contrato de decisão, não um mecanismo de recuperação.

Entradas: registro com `status`, `mission_id`, `action_id`, `idempotency_key` (strings de 1 a 128 caracteres) e, opcionalmente, estado `persisted` de fonte confiável. O consumidor deve conferir vínculo com usuário e autorização antes de qualquer consulta ou ação. Não aceitar registros fornecidos pelo cliente como evidência persistida.

Saídas fixas: `decision`, `reason`, `safe_to_retry: false`. Estados `running` e `interrupted` requerem `reconcile`; `executed` e `verified` exigem `do_not_replay`; `queued` exige consulta à fila; `awaiting_approval` exige aprovação vinculada; `failed` exige classificação humana ou política explícita. Divergência de identidade falha em `manual_review`. Nenhum campo de entrada é devolvido.

Para uma futura implementação de reconciliação, Chat A/C/D devem definir prova persistente, atomicidade e idempotência de cada ferramenta. Não executar replay apenas com base neste resultado. O estado `planned` devolve somente `plan_only`, sem autorização. Testes são simulados; não demonstram recuperação real, ausência de duplicação em processos concorrentes ou durabilidade de banco.

Verificação: `python -m unittest discover -s tests -p 'test_ops_recovery_decision.py' -v`; suíte completa e CI antes do merge. Sem deploy, migração, restart ou acesso a dados privados.
