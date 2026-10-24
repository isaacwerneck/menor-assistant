# API remota de avaliação (opt-in)

Esta API permite um cliente HTTP autorizado testar a inferência **sem sessão web**.
Não fornece shell, arquivos, ferramentas, memória, execução de tarefas ou acesso
administrativo. Reutiliza o limite do laboratório: 10 chamadas/5 minutos e uma
inferência simultânea. Não mede CPU/RAM; mede apenas latência de resposta.

## Configuração no Ubuntu

No ambiente privado do serviço, gere um token aleatório de pelo menos 32
caracteres e defina `MENOR_LAB_API_TOKEN` e
`MENOR_LAB_REMOTE_ENABLED=1`. **Nunca** envie o token pelo chat,
GitHub, screenshots, query strings ou logs. Reinicie a API após configurar.
Não habilite o endpoint sem HTTPS, autenticação na borda do Cloudflare e
política de acesso apropriada para cliente automatizado (service token).

Exemplo de chamada de uma máquina autorizada:

```bash
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $MENOR_LAB_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"mode":"direct","message":"Ola, Menor"}' \
  "https://SEU_DOMINIO/lab/api/compare"
```

A resposta contém `reply`, `status`, `model`, `move`,
`elapsed_seconds`, `tools_executed=0` e `history_saved=false`.
Use `mode=planner` para a decisão estruturada.

**Limitação essencial:** implementar a API não concede automaticamente a
esta conversa ChatGPT uma ferramenta HTTP capaz de enviar POST com
credenciais. É necessário conectar um cliente/integração que suporte essa
operação. O endpoint também não equivale ao pipeline completo do chat.
O aceite final requer chamada externa autenticada e medição real no Ubuntu.
