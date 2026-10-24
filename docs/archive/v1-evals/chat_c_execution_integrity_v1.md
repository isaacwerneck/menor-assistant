# Chat C — auditoria agregada de integridade V1

## Entrega

`ops.execution_integrity.audit_runs` agrega os contratos de transições e recuperação do Chat C. Recebe até 128 trilhas, com até 64 eventos cada, e devolve somente estado geral, códigos fixos e faixas de contagem (`0`, `1-9`, `10-49`, `50+`). Nenhum identificador, prompt, caminho, corpo de resposta, exceção ou token é incluído na saída.

Verifica continuidade de identidade (`mission_id`, `action_id`, `idempotency_key`), transições inválidas, chaves de idempotência reutilizadas em ações diferentes, interrupções sem reconciliação, aprovações pendentes e estados terminais declarados sem prova independente. O relatório é **estrutural**, não certifica execução real. Uma trilha com evento único nunca equivale a sucesso.

## Limites e integração

O auditor é puro, sem I/O, sem persistência, sem endpoints e sem execução de ferramentas. O sistema que o consumir deverá coletar evidência de fonte confiável, aplicar autorização antes da coleta, impor limites de tempo e tamanho e nunca aceitar eventos arbitrários do cliente como verdade. O auditor não bloqueia nem autoriza ações por si só.

A detecção de colisões pressupõe que a chave de idempotência seja única no domínio de comparação. O executor deve definir explicitamente esse domínio (usuário/tenant/provedor) e usar atomicidade no armazenamento; o módulo não resolve concorrência ou replay distribuído. Estados `executed` e `verified` continuam sem comprovação externa de efeito ou qualidade.

## Verificação e handoff

Executar `python -m unittest discover -s tests -p 'test_ops_execution_integrity.py' -v`, a suíte completa e o workflow obrigatório. Testar integração autenticada e recuperação real apenas em ambiente controlado e autorizado. Chat A/D: definir trilha persistida e política de transições; Chat E: eventual consumo privado de métricas agregadas, sem detalhes sensíveis. Não há deploy, restart, migração nem escrita em dados reais.
