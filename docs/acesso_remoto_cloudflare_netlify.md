# Menor remoto: Cloudflare Tunnel + Netlify + laboratório real

**Objetivo:** conversar com o Menor fora de casa e permitir testes
interativos no navegador do ChatGPT Work, mantendo o Qwen, o FastAPI,
o armazenamento privado e o processamento **no Ubuntu do proprietário**.

> Este PR **não ativa** um túnel, registra domínios nem configura provedores
> externos. Tudo isso exige aprovação e ações explícitas nas contas Cloudflare,
> Netlify, DNS e SSH. Não coloque senhas, tokens, UUIDs de credenciais ou
> cookies em issues, screenshots, GitHub ou mensagens do chat.

## Arquitetura recomendada

```text
PC/iPhone/ChatGPT Work
          |
          | HTTPS + Cloudflare Access (e-mail do dono)
          v
https://menor.seudominio.com  (Cloudflare DNS)
          |
       Cloudflare Tunnel  (conexões SAINDO do Ubuntu)
          |
          v
127.0.0.1:8000 -> FastAPI -> Ollama 127.0.0.1:11434
          |                   |
          +-- /              +-- Qwen / modelo realmente instalado
          +-- /lab/view
          +-- /chat/stream
          +-- /agent/run
          +-- arquivos privados

https://menor-entrada.netlify.app (opcional)
          |
          +-- página estática de acesso -> https://menor.seudominio.com
```

**Por que não um frontend completo no Netlify agora?** O chat contém
dependência de cookies autenticados, caminhos relativos de API e streaming
de modelo lento (40+ segundos). Segundo a documentação do Netlify,
proxy rewrites têm timeout de **26 s**, portanto redirecionar
`/chat/stream` e `/agent/run` por Netlify pode quebrar justamente as
respostas que você pretende medir. A página pública do Netlify será só um
launcher, sem dados nem chamadas à API. Separar a UI completa do backend
exigiria arquitetura BFF/async, controles de sessão e testes de streaming
antes de torná-la equivalente ao app atual.

## 1. Antes de publicar: confirmar autenticação local

No Ubuntu, por SSH (sem modificar nada):

```bash
cd ~/menor-assistant
git rev-parse --short HEAD
curl -fsS http://127.0.0.1:8000/auth/status
```

Confirme `"configured": true`. Se for `false`, primeiro configure a
senha do proprietário **na rede doméstica, antes de ativar o domínio
público**. `MENOR_PUBLIC_ORIGIN` bloqueia de propósito `/auth/setup`,
inclusive quando o túnel chega pela interface loopback; isso impede
sequestro da conta na primeira publicação.

Revisar firewall: NÃO abrir 8000 ou 11434 no roteador/Internet. A saída
do `cloudflared` é pelo lado do Ubuntu. Use `ufw status verbose` ou
regras equivalentes para confirmar o estado; não altere regras sem conferir
acesso SSH e recuperação.

## 2. Registrar domínio DNS na Cloudflare

Você pode comprar o domínio no registrador de sua preferência (inclusive
via um serviço que ofereça registro integrado) e delegar **o DNS** do
domínio à Cloudflare. Um `netlify.app` sozinho não fornece a zona DNS
Cloudflare necessária para o hostname estável do Tunnel.

No painel Cloudflare:
1. Adicione sua zona `seudominio.com` e conclua os nameservers.
2. Em **Zero Trust / Access > Applications**, crie uma aplicação
   *Self-hosted* para **`menor.seudominio.com`**.
3. Configure uma política **Allow** apenas para o endereço de e-mail do
   proprietário (OTP ou identidade aprovada). Exija login.
4. Verifique que a política é **deny by default**, incluindo
   `/lab/view`, `/docs`, `/auth`, `/agent` e `/files`.
5. Só então configure DNS/túnel. O login próprio do Menor permanece como
   **segunda barreira**, não é substituído pela Cloudflare.

Referências oficiais:
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/

## 3. Cloudflare Tunnel no Ubuntu (ações manuais supervisionadas)

Instale `cloudflared` pelo guia **oficial** adequado à arquitetura do
Ubuntu. Verifique o binário: `cloudflared --version`.

Os comandos abaixo exigem login no navegador e **são executados por você**:

```bash
cloudflared tunnel login
cloudflared tunnel create menor-assistant
cloudflared tunnel list
```

A criação retorna um UUID e cria o arquivo privado
`~/.cloudflared/<UUID>.json`. **Não envie esse JSON para ninguém**.

Prepare localmente o YAML com o UUID real, após atualizar o repositório:

```bash
cd ~/menor-assistant
git pull --ff-only
python3 -m ops.remote_access \
  --hostname menor.seudominio.com \
  --tunnel-id SEU_UUID_REAL > ~/.cloudflared/config.yml
chmod 600 ~/.cloudflared/config.yml
cloudflared tunnel --config ~/.cloudflared/config.yml ingress validate
```

O gerador só imprime configuração: `ingress` aceita **exatamente**
`menor.seudominio.com -> http://127.0.0.1:8000` e termina com
`http_status:404`. Não cria portas nem publica DNS sozinho.

Configure a URL de origem pública canônica no arquivo de ambiente
**já utilizado pelo serviço systemd**:
`~/.config/menor/environment` (chmod 600).

Adicione uma linha:

```text
MENOR_PUBLIC_ORIGIN=https://menor.seudominio.com
```

Se o arquivo já tem outras variáveis, **mantenha todas** e adicione ou
edite somente essa linha, sem duplicação. Depois confira
`systemctl --user cat menor-api.service` e reinicie o serviço
quando estiver pronto para ativar, usando `menor restart`. A
configuração não instala nem inicia a aplicação automaticamente.

Atribua o DNS ao túnel:

```bash
cloudflared tunnel route dns menor-assistant menor.seudominio.com
cloudflared tunnel --config ~/.cloudflared/config.yml ingress rule https://menor.seudominio.com/
cloudflared tunnel --config ~/.cloudflared/config.yml run menor-assistant
```

Teste HTTPS no celular com Wi-Fi desligado. Primeiro você deve ver o
login do Cloudflare Access, **depois** o login do Menor. Inspecione
`/auth/status`, e só então abra `/lab/view`.

Depois de confirmar, o serviço persistente do cloudflared pode ser
instalado mediante sua autorização por:

```bash
sudo cloudflared --config "$HOME/.cloudflared/config.yml" service install
sudo systemctl status cloudflared --no-pager
```

O `sudo` acima altera o sistema; nunca executá-lo antes de você
confirmar a configuração. A documentação oficial alerta para o
diretório HOME mudar ao usar sudo; por isso passamos o `--config`
**com caminho absoluto**.

## 4. Netlify (opcional, landing page estática)

A raiz do repositório contém `netlify.toml` e
`scripts/build_netlify_site.py`. Conecte o GitHub ao Netlify,
sem publicar `~/.config/menor` nem arquivos de dados.

No painel Netlify, configure:
- Build command: `python3 scripts/build_netlify_site.py`
- Publish directory: `dist`
- Environment: `MENOR_PUBLIC_ORIGIN=https://menor.seudominio.com`

O build falha se faltar a URL válida. O resultado é uma única página
estática com link HTTPS para o Menor, sem conversas, cookies, funções
ou proxy para a API. A URL Netlify é **pública mas não processa chats**.

## 5. Comparar Qwen e Menor de verdade

Após fazer login no Menor, abra:

```text
https://menor.seudominio.com/lab/view
```

Digite "E aí, Menor" e execute os dois modos (um por vez):

- **Modelo direto:** chamada HTTP real à instância do Ollama, sem roteador
  JSON e sem ferramentas; baseline de qualidade/tempo.
- **Raciocinador:** usa `intelligence.decide` de verdade, com estrutura
  JSON validada e seus limites; coleta movimento, texto e segundos.

O laboratório evita usar os conhecimentos pessoais, feedbacks ou
ferramentas, e não salva mensagens; é um teste **comparativo isolado**.
Está limitado a 10 inferências por 5 minutos por processo para não
sobrecarregar a CPU. O chat real `/` continua sendo o lugar para
testar memória, projetos, ferramentas e a experiência completa.

**Diferença importante:** o laboratório **não executa a mesma máquina
de estados completa de `/agent/run`**. Ele isola o modelo e o
raciocinador justamente para identificar se o problema já existe no
Qwen cru ou se aparece após a orquestração. Para diagnosticar o
pipeline inteiro, reproduza o mesmo texto no chat principal.

## 6. Como testar com ChatGPT

Quando o endereço estiver acessível, você poderá iniciar uma tarefa
no **ChatGPT Work** solicitando abrir o domínio no navegador remoto,
autenticar-se no Cloudflare e no Menor, conversar e registrar problemas.
A permissão do Work, a autenticação e eventuais restrições da proteção
Cloudflare dependem da sessão. A ferramenta GitHub deste chat **não tem
acesso SSH ao Ubuntu**, e enviar um link nesta conversa não estabelece
uma conexão remota POST autenticada de forma automática.

Não compartilhe senha, cookie, token Cloudflare ou credenciais comigo no
texto. Utilize os fluxos oficiais de login do navegador conectado.
Não desative Cloudflare Access somente para facilitar a navegação.

## 7. Aceite/rollback

Antes de considerar o acesso externo habilitado:
- Seu hostname exibe a tela Access quando usuário não autenticado.
- Uma requisição `POST` com `Origin` externo tem 403.
- Login no Menor por HTTPS define cookie `Secure; HttpOnly; SameSite=Strict`.
- Criação inicial de proprietário pelo hostname público tem 403.
- Teste `/lab/view` sem login retorna 401 (ou 403 do Access).
- `/chat/stream` mantém conexão além de 40 segundos, sem proxy Netlify.
- CPU/RAM continuam compatíveis; nenhum dado pessoal aparece em logs
  ou no site Netlify.
- Testar em rede móvel e revogar acesso no Cloudflare se necessário.

Rollback: desligar o serviço `cloudflared` ou remover a rota DNS,
retirar `MENOR_PUBLIC_ORIGIN` do ambiente, reiniciar a API no horário
escolhido; manter credenciais privadas e não apagar arquivos nem senhas
sem plano. Reverter publicação externa é diferente de reverter a
versão do Menor na `main`.

**Nenhuma etapa de Cloudflare, Netlify ou servidor está feita pelo
merge deste PR**. Necessitam conta, zona DNS, OAuth/OTP, SSH e confirmação
expressa do operador.
