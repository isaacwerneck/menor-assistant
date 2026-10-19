# Chat E E5 — Diagnóstico operacional privado, sem shell

## Escopo efetivo
A rota `GET /ops/diagnostics` agrega probes de `ops.doctor.run_checks` já existentes usando **somente** `ops.observability.build_snapshot` do Chat C. É leitura e não oferece nenhum endpoint de comando, execução de código, reinício de systemd, criação de tarefa, instalação de modelo, reset ou leitura arbitrária de arquivos.

**Não confundir com conexão direta deste ChatGPT ao servidor.** O aplicativo não está automaticamente acessível ao ChatGPT na mesma rede Wi-Fi. Para uso remoto futuro, será preciso um transporte e identidade confiáveis (VPN/reverse proxy com autenticação adicional, integração explicitamente autorizada e credenciais fora do repositório). Nenhum token é criado ou armazenado aqui.

## Proteções
1. `auth.require_owner(request)` é executado antes de chamar o diagnóstico.
2. O navegador não controla `port`, `timeout`, comandos nem alvos. Probes locais do doctor possuem seus próprios timeouts.
3. `asyncio.to_thread` evita bloquear o event loop, com espera máxima de 9 s e no máximo dois probes concorrentes por processo.
4. A saída é convertida para um envelope de campos permitidos: statuses `api, ollama, service, disk, memory`, evidências fixas e `collected_at`. **Detalhes brutos do doctor, nomes de arquivo, logs e paths jamais são incluídos**.
5. `Cache-Control: private, no-store` e `X-Content-Type-Options: nosniff`, sem CORS público.
6. Erros são tratados com código 503 genérico, sem mostrar exceções ou dados operacionais privados.

## Limites de verificação
- `api`: GET /health em loopback, não prova que a revisão corresponde ao GitHub.
- `ollama`: informado pelo /health da API, não comprova que o modelo gerou resposta correta.
- `service`: status de `menor-api.service` no systemd do usuário.
- `disk`, `memory`: faixas críticas de capacidade, não expõem caminhos ou valores privados.
- Revisão implantada, deploy timer, restart recente, CPU, precisão das ferramentas, logs e benchmarks de inferência: **não monitorados** por esta rota; não apresentar status verde sem evidências.
- O coletor de `ops.doctor` ainda precisa ser validado no Ubuntu real. A execução da CI usa simulações e não instala nenhum serviço.

## Próximas fases após revisão
1. Consumir o envelope em `/workspace/system` com selo de horário/origem e estados `unknown`.
2. Teste manual de autenticação e desempenho na instalação Ubuntu.
3. Planejar integração externa autenticada do ChatGPT ou Codex, com aprovação e auditoria de risco, somente após configurar o canal remoto seguro.
4. Adicionar probes sintéticos de inferência com consentimento explícito, orçamento de recursos e resultados rastreáveis, sem reutilizar conversas privadas.
