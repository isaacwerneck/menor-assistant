# Chat C — endurecimento e evidência estrutural V2

## Mudanças

- Corrige `audit_runs([])`: sem trilhas, estado `unknown`, nunca `ok`.
- Rejeita evento intermediário inválido mesmo quando os extremos são válidos.
- Valida o tipo de `status` antes de testar pertencimento a estados permitidos, evitando exceções com listas ou objetos não hasháveis.
- Adiciona `ops.execution_evidence.verify_evidence` para conferir sequência monotônica contígua, identidade, transições e fingerprint SHA-256 do último evento.
- Adiciona `verify_json_envelope` com limite de 64 KiB, envelope estrito e falha segura.
- Acrescenta 12 testes de regressão sobre evidência, privacidade, limites e correções.

## Garantias e limites

As funções não fazem I/O, não abrem banco, não recuperam tarefas, não executam ações e nunca autorizam replay. `trusted: false` é deliberado: hash SHA-256 **não é assinatura**, não prova autenticidade, autoria, integridade histórica ou persistência. O digest pode servir como verificação de consistência em canal confiável, mas não deve ser exposto em endpoint público por possibilitar correlação. Dados fornecidos por clientes não são evidência confiável.

A trilha real requer: armazenamento transacional append-only ou equivalente; identidade de usuário/tenant vinculada no servidor; versionamento atômico; regras de deduplicação no executor; autorização explícita para operações sensíveis; provas externas de efeitos; reconciliação de resultado incerto sem replay. Esse trabalho depende de coordenação com Chat A/D e dos contratos reais de persistência. Nenhuma dessas garantias é reivindicada por este PR.

## Verificação

`python -m unittest discover -s tests -p 'test_ops_execution_evidence.py' -v`

`python -m unittest discover -s tests -v`

`python -m flake8 ops tests --max-line-length=119`

CI não substitui testes de concorrência e recuperação em ambiente controlado. Sem deploy, restart, migração ou escrita em dados reais.
