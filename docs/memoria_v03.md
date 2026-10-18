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

## Salvar pela interface web (próxima entrega)

Depois da aprovação e merge desta alteração, abra o Menor no navegador.
No **primeiro acesso**, crie uma senha de pelo menos 12 caracteres. Isso
habilita um cookie de sessão por 7 dias, com autenticação para chat e escrita.
O cadastro inicial só é aceito de endereço de rede privada/loopback; **qualquer
pessoa na mesma rede privada poderia reivindicar a instalação antes do dono**.
Por isso, faça a configuração imediatamente ao instalar e não use Wi-Fi público.

Envie no chat:

```text
Menor, lembre disso: Prefiro respostas diretas.
```

Também são aceitas frases naturais como `lembre se de sempre ser objetivo`,
`lembre-se de...`, `anota aí: ...` e `guarda na memória: ...`.
Se uma frase não for reconhecida, use **Guardar memória** junto à mensagem.
O modelo não deve afirmar que uma memória foi gravada sem a confirmação
visível do aplicativo.

O Menor abre uma confirmação. Escolha:

- **Preferência**: o texto é gravado em `identidade/preferencias.md` e incluído
  no contexto das próximas respostas.
- **Conhecimento**: é registrado em `conhecimentos/aprendizados_gerais.md`.
  A recuperação automática de conhecimento virá numa etapa posterior.

O chat não pede comandos de terminal. O novo registro fica em Markdown fora do
GitHub, inclusive após reboot. Gravações exigem uma sessão autenticada e
confirmação explícita; pedidos comuns não acionam gravação automaticamente.

A senha não é armazenada em texto legível: fica um hash derivado de scrypt em
`~/menor-data/owner.json`, com permissão privada. As sessões usam cookies
HttpOnly e SameSite Strict, com Secure quando servidas sobre HTTPS.

**Limites atuais de segurança:** numa rede HTTP sem TLS, senha e cookie trafegam
sem criptografia de aplicação. Use rede doméstica confiável; para acesso externo
configure HTTPS/VPN. O logout apaga o cookie do navegador, mas não revoga um
cookie copiado previamente — rotação de sessões virá depois. Não há mecanismo
de recuperação de senha nesta entrega: guarde-a em gerenciador confiável.
Sem a senha, não há procedimento automático de recuperação pela web.

## Limites de segurança

- A gravação pela API exige senha de proprietário e confirmação no navegador.
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
A próxima etapa acrescentará busca e recuperação de conhecimentos gerais e gerenciamento de projetos.
