# Chat C — diagnóstico e confiabilidade operacional

Esta frente trabalha separadamente do cérebro do **Chat A** (`src/agent/`) e dos
executores/analisadores do **Chat B** (`src/tools/`, `src/api/`). Não modifica a
API existente, banco de dados, modelos, credenciais, serviços nem deploy.

## Primeiro incremento: `ops.doctor`

Pré-requisito: Python 3.10+. Executar no notebook do Menor a partir da raiz do
repositório, sem instalar pacotes extras:

```bash
python3 -m ops.doctor
python3 -m ops.doctor --json
python3 -m unittest discover -s tests -p 'test_ops_doctor.py' -v
```

O comando realiza somente leituras:

- `GET http://127.0.0.1:8000/health`, sem redirects e com limite de resposta.
- Estado informado do Ollama, **separado** do estado da API (HTTP 200 não
  significa que o modelo esteja funcionando).
- `systemctl --user is-active menor-api.service` (sem reiniciar nada).
- Espaço livre do volume de `MENOR_DATA_DIR` ou `~/menor-data` (sem listar dados).
- `MemAvailable` do Linux (sem consultar processos).

Todos os comandos têm timeout. O diagnóstico não lê tokens, não escreve arquivos,
não faz chamadas externas e não mostra caminhos locais. O resultado JSON é
adequado à futura interface de status; não o exponha numa rota pública sem
controle de acesso. As classificações são `ok`, `warning`, `critical` e
`skipped`. O status final é o mais grave (avisos não são escondidos por
checks saudáveis). Código de saída: 0 = ok, 1 = warning, 2 = critical.

As marcas de atenção do volume (<2 GiB) e memória (<1 GiB) são heurísticas,
não requisitos do modelo. Mesmo com a API ativa e recursos disponíveis, não há
prova de qualidade da inferência, de modelos baixados ou de uma operação real.

### Limites da primeira versão

- Executar no mesmo notebook da API: o acesso é **somente loopback**.
- A disponibilidade do Ollama é a reportada por `/health`, não um teste de
  geração de texto.
- Systemd e `/proc/meminfo` são opcionais fora do Linux; `skipped` não é falha.
- `ops.doctor` não executa recuperação automática, não faz restart nem altera
  a branch `main`.

## Próximos incrementos reservados ao Chat C

1. Testes de contrato (API/health/recibos) entre versões, sem dependência de
   modelos grandes ou execução de tarefas do usuário.
2. Painel privado de saúde operacional e detecção de regressões (em módulos
   novos, coordenando imports em `src/api/main.py` somente após revisão).
3. Simulações de indisponibilidade e auditoria de rollback do deploy, sem
   modificar o deploy automático sem acordo explícito.

**Regra de integração:** branch/PR próprios, CI verde, revisão antes do merge;
sem alterar arquivos do Chat A ou B e sem publicar diagnósticos privados.
