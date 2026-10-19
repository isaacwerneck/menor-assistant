# Chat C — monitoramento seguro do Ubuntu e benchmark voluntário do Qwen

A versão anterior implementou `menor monitor` (CPU, RAM, swap, processos,
disco e rede) em modo passivo. Este incremento acrescenta:

- carga Linux de 1/5/15 minutos;
- alertas apenas informativos quando CPU excede 90%, RAM disponível cai
  abaixo de 10% ou o espaço livre na home cai abaixo de 5 GiB;
- `--services` **opcional**, que consulta `systemctl --user is-active
  menor-api.service` e `ollama ps` com comandos fixos, sem shell e sem
  autenticação, instalação ou reinício;
- `menor benchmark --live --samples 2` para duas inferências controladas no
  Qwen/Ollama local com prompts públicos fixos, sem registrar respostas
  privadas, textos de memória ou históricos de conversa.

## Utilização depois de deploy aprovado

```bash
menor monitor
menor monitor --once --json --services
menor monitor --interval 1 --services
menor benchmark
menor benchmark --live --samples 2
```

O primeiro comando tem amostras passivas. `--services` gera probes locais
adicionais, apenas quando explicitamente fornecido. `benchmark` sozinho não
roda o modelo. `--live` autoriza 1–3 inferências limitadas a 80 tokens em
`http://127.0.0.1:11434` (ou outro endpoint **HTTP loopback válido**). A
execução não faz download, não altera configurações ou reinicia serviço.

## Evidências e privacidade

O benchmark retorna tempos em segundos, contagem de tokens e taxa de geração
**somente quando esses metadados são fornecidos pelo Ollama**. Não grava o
texto da resposta. Nenhum URL externo é permitido. Resultados não equivalem
a latência até o primeiro token, velocidade da internet ou qualidade da IA:
a inferência é `stream:false` e usa perguntas fixas muito curtas.

O estado `responsive` de `ollama ps` apenas confirma que o comando devolveu
informação, não que o modelo tem capacidade ou qualidade suficientes. Nomes
de modelos têm limite e filtro de caracteres; nenhuma linha de comando de
processo com credenciais entra na interface.

## Critérios de aceite e limitações

- Simular CPU/RAM baixa, sobrecarga e disco crítico sem mudar o servidor.
- Validar que `--services` é opt-in e só chama executáveis predefinidos.
- Validar ausência de probes de inferência sem `--live`.
- Recusar endpoints remotos, credenciais em URLs, nomes de modelo inseguros
  e quantidade excessiva de amostras.
- Testar os comandos no Ubuntu real após deployment, incluindo parser da
  versão instalada de `ollama ps`, permissões `systemd --user` e uso CPU.

Esses testes simulados não provam a velocidade real do Qwen, nem substituem
teste de latência ponta a ponta entre Safari/PC, API e modelo.
