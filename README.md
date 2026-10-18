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
