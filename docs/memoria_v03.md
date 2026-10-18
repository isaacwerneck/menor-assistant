# Memória persistente (Menor v0.3 — primeira etapa)

Esta entrega cria um cérebro privado em Markdown, conforme o [PLANO.md](../PLANO.md).

## Localização e inicialização

Os dados ficam em `~/menor-data/cerebro/`, **fora** do repositório `~/menor-assistant/`.
Isso impede que notas mutáveis bloqueiem o deploy via Git. O FastAPI cria os diretórios ao iniciar.
A instalação é idempotente: não sobrescreve notas preexistentes.

```bash
cd ~/menor-assistant
.venv/bin/python -m src.memory.store init
```

São criadas as pastas identidade, conhecimentos, ferramentas, projetos, memoria e propostas,
com modelos Markdown de preferências, conhecimento e projeto demonstrativo.
É possível alterar a raiz usando `MENOR_DATA_DIR` no ambiente do serviço.

## Registrar preferências explicitamente

Por enquanto, só o operador local pode alterar preferências. Digite no terminal do servidor:

```bash
cd ~/menor-assistant
.venv/bin/python -m src.memory.store remember "Responda sempre de forma curta e objetiva"
.venv/bin/python -m src.memory.store show
cat ~/menor-data/cerebro/identidade/preferencias.md
```

As preferências são lidas em cada nova requisição ao Ollama; não exigem reinício da API.
Os dados persistem após reboot, atualização do código ou troca de navegador.
Também é possível editar o Markdown manualmente: cada preferência deve começar com `- `.

## Limites de segurança

- A API **não** oferece gravação de memória nessa etapa: falta autenticação.
- Escrita atômica, bloqueio de caminhos absolutos/traversal/symlinks e tamanho máximo de 64 KiB por nota.
- Diretórios do cérebro com permissões 0700; novas notas com 0600.
- Não coloque senhas, tokens ou credenciais em Markdown.
- Não exponha a porta 8000 publicamente: use rede local privada ou VPN.
- Esta etapa ainda não implementa ferramentas executáveis, novos projetos pelo chat ou busca semântica.

## Testar

```bash
cd ~/menor-assistant
.venv/bin/python -m unittest discover -s tests -v
curl http://127.0.0.1:8000/health
```

Após registrar uma preferência, converse com o Menor para observar o contexto aplicado.
A próxima etapa acrescentará autenticação e operação `lembre disso` no chat, com confirmação.
