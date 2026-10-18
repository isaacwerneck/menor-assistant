# Menor - Assistente Pessoal de IA

Assistente local com FastAPI, interface web com streaming e inferência pelo Ollama
(`qwen2.5-coder:7b`). Voz, memória Markdown e ferramentas agênticas estão no
[roadmap](docs/roadmap.md).

## Executar

Requer Python 3.10+ e Ollama com o modelo instalado:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Abra `http://IP_DO_SERVIDOR:8000`. A API oferece `/health`, `/models`,
`/chat`, `/chat/stream` e a documentação interativa em `/docs`.
O serviço ainda não possui autenticação: mantenha-o na rede privada/VPN.

O chat envia o histórico recente ao modelo (até 20 mensagens e 32000 caracteres
junto com a mensagem atual). As conversas ficam no navegador e podem ser
exportadas pelo botão ↓ em Markdown. Mensagens novas aceitam até 8000 caracteres.
O rodapé mostra a conexão com Ollama; falhas de armazenamento aparecem em aviso
separado. Histórico corrompido é preservado sem sobrescrita.

Configuração opcional: `OLLAMA_URL`, `OLLAMA_MODEL` e `OLLAMA_KEEP_ALIVE`.
Detalhes de contexto, erros e configuração em
[organização do código](docs/arquitetura_codigo.md#estado-implementado).

## Cérebro persistente e preferências pelo chat (v0.3)

Na primeira visita, a interface permite criar uma senha do proprietário
(com pelo menos 12 caracteres), sem usar comandos do terminal. Configure-a
somente na sua rede privada. Depois, envie uma mensagem como
`Menor, lembre disso: Prefiro respostas objetivas` e escolha se será
preferência ou conhecimento. O conteúdo é salvo em
`~/menor-data/cerebro/`, fora do repositório.

**Aviso:** ainda não há HTTPS integrado nem recuperação automática de senha.
A configuração inicial pode ser reivindicada por outro dispositivo da
mesma rede privada antes do dono configurá-la. Não publique a porta 8000
na Internet e não use Wi-Fi público. Prefira VPN e HTTPS.

Veja [como usar o cérebro com segurança](docs/memoria_v03.md) e o
[PLANO.md](PLANO.md) para as próximas fases.

## Busca e revisão de conhecimentos (v0.4)

A cada pergunta, o Menor busca no cérebro apenas conhecimentos gerais
relacionados ao assunto, usando SQLite FTS5 local. Na interface, o ícone
de **cérebro** permite consultar, pesquisar, corrigir e apagar anotações
sem usar terminal. Consulte [o guia da busca](docs/busca_conhecimentos.md).

## Projetos contextuais e diálogo natural (Fase 3)

O Menor pergunta na própria conversa se você quer guardar uma ideia e
onde, sem abrir um modal com botões grandes. Responda normalmente:
"Sim, nos projetos" ou "Não, deixa".

O painel compacto **Projetos** permite vincular uma conversa a um projeto
existente; as decisões, tarefas e o diário desse projeto entram no contexto,
sem misturar projetos diferentes. Veja [o guia da Fase 3](docs/projetos_contextuais.md).

## Robustez de decisões e ferramentas (v0.5 em desenvolvimento)

O projeto mantém um [plano extra de refinamento](PLANO_REFINAMENTO.md).
Respostas curtas a perguntas de memória ("sim", "simm", "ferramentas",
"não") são resolvidas sem depender de nova inferência do Qwen.

Também existe um catálogo inicial de ferramentas reais com endpoint
autenticado `GET /tools` e execução controlada em
`POST /tools/execute`. A execução usa **dry-run por padrão** e registra
metadados locais de auditoria. O Menor ainda não cria/instala
autonomamente ferramentas Python nem controla Git.

## Imagens e revisões de código (v0.6 — em revisão)

O chat identifica pedidos de gerar/editar imagem, faz perguntas curtas
quando falta informação, aceita anexo de foto e mostra o resultado
quando um motor externo de imagens está configurado.

A opção de corrigir código gera um **PR rascunho**, em branch separada,
somente se o proprietário ativar explicitamente a integração GitHub.
O monitor diário de falhas roda localmente, sem auto-merge e sem
executar patches na máquina.

Veja [configuração, custos, privacidade e limites](docs/imagens_autoedicao_v06.md).
O motor de imagens e as credenciais não são configurados automaticamente.

## Orquestrador e subagentes locais (incremento do PR #8)

O Menor pode iniciar uma missão para construir uma capacidade que falta,
perguntar requisitos, propor um modelo local e pedir autorização. A missão
fica salva no cérebro e um worker systemd executa tarefas autorizadas.
O primeiro subagente é de geração de imagens OpenVINO CPU, sem API de IA
externa por padrão. O download inicial exige internet, alguns GB livres
e o teste de desempenho no notebook.

Veja [a arquitetura multiagente](docs/arquitetura_multiagente.md).

## Deploy automático

No Ubuntu, com o repositório em `~/menor-assistant`:

```bash
cd ~/menor-assistant
git pull --ff-only
bash scripts/install-services.sh
sudo loginctl enable-linger "$USER"
```

Depois da instalação, o servidor consulta a `main` no GitHub aproximadamente a
cada 30 segundos, atualiza sem criar merges, instala dependências, executa os
testes e reinicia a API. Não precisa manter o PC ligado nem expor o SSH à internet.
O GitHub Actions também executa lint e testes em pushes e pull requests.
O deploy usa os testes locais; não espera o resultado do Actions.

Instalação, fluxo, limites e recuperação:
[guia do servidor](docs/guia_servidor_domestico.md#deploy-automático-do-menor).

## Verificar

```bash
python -m unittest discover -s tests -v
node --test tests/test_ui.js  # apenas desenvolvimento/CI, sem dependências npm
# Flake8 é uma ferramenta de desenvolvimento, fora das dependências da API.
python -m pip install flake8
python -m flake8 src tests --max-line-length=119
bash -n scripts/deploy.sh scripts/install-services.sh tests/test_deploy.sh
bash tests/test_deploy.sh
```

## Documentação

- [Arquitetura](docs/arquitetura.md)
- [Organização do código](docs/arquitetura_codigo.md)
- [Roadmap](docs/roadmap.md)
- [Hardware](docs/hardware_requisitos.md)
- [Setup Linux](docs/setup_linux.md)
- [Servidor doméstico e deploy](docs/guia_servidor_domestico.md)

### Planejador e registro de skills

O Menor agora pode organizar requisitos em etapas e critérios usando o Qwen
local. `GET /agent/skills` mostra o estado verificado dos subagentes;
pedidos de imagens só executam o worker local se missão e runtime estiverem
aprovados e disponíveis. O resultado é tecnicamente revisado antes de
ser exibido. A skill testada documenta seu uso no cérebro.

Esta arquitetura ainda não substitui um sandbox programador nem prova
qualidade artística. [Arquitetura e limites](docs/arquitetura_multiagente.md).

