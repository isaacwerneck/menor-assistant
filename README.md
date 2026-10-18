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
