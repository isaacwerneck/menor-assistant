# Menor - Assistente Pessoal de IA

Assistente pessoal local com FastAPI, interface web para PC/iPhone, Ollama,
memória/projetos, ferramentas supervisionadas, trabalhos em progresso e Menor Lab.
O modelo medido em outubro de 2026 é o `qwen2.5-coder:7b` na CPU; voz
bidirecional plena, autonomia longa e agente programador end-to-end ainda não
foram comprovados. As implementações existentes não equivalem a capacidade
completa em produção.

**Migrando o projeto para Codex?** Comece em
[`AGENTS.md`](AGENTS.md) e no
[`handoff de 20/10/2026`](docs/handoff/00_COMECE_AQUI_CODEX.md).
Lá estão status A–E, progresso estimado, relatórios reais, hardware,
latência, limites e próximos marcos. O [roadmap histórico](docs/roadmap.md)
não deve ser lido como checklist integral do estado atual.

O [checkpoint de continuidade](docs/handoff/00_COMECE_AQUI_CODEX.md#checkpoint-de-continuidade--20102026)
registra a revisão integrada e a proposta em avaliação para exigir, já na geração
JSON, os campos obrigatórios de planos e esclarecimentos. As sondagens reais e
falhas de qualidade ainda abertas estão documentadas; contrato válido não prova
plano correto.

## Acesso remoto e laboratório de inteligência (opcional)

É possível acessar o Menor por **Cloudflare Tunnel com Access protegido**,
mantendo FastAPI, Ollama, sessões e arquivos no Ubuntu. O modo remoto exige a
variável de ambiente `MENOR_PUBLIC_ORIGIN=https://menor.seudominio.com`
e a configuração manual do túnel e do DNS; nenhuma instalação é automática.
O laboratório autenticado `/lab/view` compara Qwen direto com o
raciocinador JSON, sem executar ferramentas nem salvar históricos. Os relatórios
distinguem timeout, JSON/contrato inválido, categoria do campo rejeitado e limite de saída, com métricas
numéricas de inferência, também visíveis nos cartões dos testes individuais;
veja o [contrato do laboratório](docs/laboratorio_baterias.md).

Relatórios completos novos registram o checkout Git observado na importação do
laboratório e no início/fim da bateria, com indicação de revisão diferente ou
alterações rastreadas. Versão desconhecida fica explícita; esse registro não
atesta todo o código carregado nem altera a pontuação ou publicação automática.

O Netlify oferece somente uma **página estática de entrada** neste estágio.
Não coloque `/chat/stream` atrás de proxy Netlify: o timeout da camada
de proxy não é apropriado para inferências de 40+ segundos. Configuração,
limites e procedimentos completos em
[acesso remoto Cloudflare + Netlify](docs/acesso_remoto_cloudflare_netlify.md).

## Executar

O chat permite exportar tempos técnicos por turno, sem mensagens, pelo botão
de relógio. Medidas ausentes permanecem ausentes; a coleta e seus limites estão
no [diagnóstico de desempenho](docs/diagnostico_desempenho_e10.md).

Requer Python 3.10+ e Ollama com o modelo instalado:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Abra `http://IP_DO_SERVIDOR:8000`. A API oferece `/health`, `/models`,
`/chat`, `/chat/stream` e a documentação interativa em `/docs`.
O proprietário configura autenticação no primeiro acesso. Mantenha o serviço na rede privada/VPN; HTTPS não é integrado.

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

A ferramenta `math.calculate` calcula expressões com decimais sem convertê-los
primeiro para ponto flutuante binário. O agente recebe orientação para conferir
fórmula e unidades e preferir essa ferramenta na aritmética; o recibo comprova
a expressão calculada, não a interpretação da pergunta. O Lab direto não executa
essa ferramenta. Veja [contrato e limites](docs/rodada_inferencia_contexto_e_ferramentas_v4.md).

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

## Núcleo de execução local

O chat consulta o núcleo autenticado em `/agent/run`: capacidades reais,
planejamento, aprovação persistente e ferramentas limitadas ao catálogo.
O modelo pode consultar ferramentas de leitura em até quatro passos; uma escrita
mostra a operação e seus parâmetros antes de pedir autorização. O mesmo turno
repetido recupera o recibo salvo. Não existe terminal arbitrário nesta versão.
Pedidos de pixel art e sprites seguem para imagens ou criação de ferramenta,
mesmo com pergunta antiga de memória pendente. Durante a aprovação, dúvidas sobre
o modelo e a CPU recebem explicação do plano; perguntar não autoriza instalação.

A comparação com as arquiteturas públicas de Codex, Claude, ChatGPT e
Antigravity, o que já foi entregue e as próximas fases estão no
[plano de refinamento, seção R11](PLANO_REFINAMENTO.md).

## Pesquisa, estudos e criação supervisionada de ferramentas

Pedidos como `Pesquise a documentação oficial de funções Python` consultam páginas
públicas e só retornam fatos com citações encontradas no material. `Estude programação
Python sobre funções` também salva fonte, data e limitações em conhecimentos por
assunto; essas notas entram na busca textual do cérebro. Citação válida não garante
que a interpretação esteja correta: o Menor deve reconhecer dúvidas.

Para classificar automaticamente dúvidas e buscar antes de responder, configure
`MENOR_AUTONOMY_ENABLED=1` no ambiente do serviço. Sem essa opção, pedidos explícitos
de pesquisa/estudo continuam disponíveis. A busca HTML, com fallback para RSS público
do Bing, não exige chave paga, mas pode encontrar CAPTCHA ou mudanças nos buscadores.

O navegador é opcional, instalado separadamente no ambiente virtual do Menor:

```bash
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install --with-deps chromium
```

Ative `MENOR_BROWSER_ENABLED=1` em `~/.config/menor/environment` e reinicie a API.
A ferramenta `web.browse` fica no catálogo para navegação sob demanda; o leitor
simples é usado primeiro para reduzir custo e memória.

`developer.build` propõe ferramentas puras de texto com código, testes e documentação,
testa em Docker sem rede e abre uma branch `codex/` com PR rascunho.
Exige Docker e a imagem preparada com `docker pull python:3.12-alpine`,
além do opt-in `MENOR_AUTODEV_ENABLED=1` e da integração GitHub já existente.
Não coloque tokens no chat ou no repositório. Depois de CI, revisão, merge e
reinício, a nova ferramenta aparece como `custom.<nome>`.
Sem sandbox funcional, nenhuma branch da ferramenta nova é criada.
A autoedição legada `developer.propose` ainda depende do CI para os testes de comportamento.

A visão completa, a proposta anterior preservada e os marcos pendentes estão em
[PLANO_REFINAMENTO.md, R12](PLANO_REFINAMENTO.md#r12--assistente-autônomo-de-pesquisa-estudo-construção-e-autoevolução).
A pesquisa limita os trechos enviados ao modelo e distingue falha de busca,
leitura e validação da síntese. Estudo negado não deve ser gravado apenas pela
presença da palavra. Veja [fluxo, limites e operação](docs/busca_conhecimentos.md#pesquisa-web-e-estudos-por-assunto).

## Comandos curtos no servidor

Instalados automaticamente pelo deploy em `~/.local/bin/menor`:

```bash
menor start
menor stop
menor restart
menor status
```

Também aceita `iniciar`, `parar` e `reiniciar`. Se o terminal já estava aberto
antes da instalação, execute `source ~/.profile` uma vez para atualizar o PATH.
`stop` para API, timers e workers do Menor; o serviço Ollama e o computador
continuam ligados. `restart` reinicia a API e retoma timers, preservando workers
que já estejam ativos. Operações em curso interrompidas por stop exigem revisão.

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
python -m flake8 src ops tests --max-line-length=119
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

### Preparação segura do subagente de imagens (PR #9)

O OpenVINO roda em um ambiente virtual isolado do chat, instalado somente após
autorização da missão. Download e inferência ocorrem em subprocessos com
limites de duração. O chat mostra preparo, download, teste e bloqueio por
espaço em disco; o modelo fica fora do Git. Consulte
[a documentação do subagente local](docs/arquitetura_multiagente.md).

A validação efetiva no notebook continua pendente.

### Correções de aprovação e segurança (PR #11)

No chat, frases naturais de autorização como `eu aprovo` e `bora lá`
são aceitas quando já existe uma missão aguardando consentimento.
Perguntas como `que aprovação?` explicam exatamente o que será instalado
sem executar downloads; o estado é salvo e consultável depois do aceite.

Ferramentas geradas passam a executar dentro de containers Docker restritos
na utilização, não apenas durante os testes. Sem Docker disponível,
a execução é recusada. Pesquisas externas recebem filtragem preventiva de
dados privados; não envie senhas ou tokens em consultas.
## Avaliação integrada de contexto e latência

O raciocinador organiza catálogos de ferramentas/skills antes dos campos variáveis
do contexto para favorecer reaproveitamento de prefixo. O ganho no Ubuntu ainda
exige [medição controlada](docs/chat_a_benchmark_real.md); isso não evita partida
fria nem torna perguntas simples instantâneas.

O [relatório de 19/10/2026](docs/chat_a_benchmark_real.md#avaliação-integrada-remota--19102026)
registra testes reais no navegador, problemas encontrados e limites de medição.
O planejador preserva o pedido completo, recebe preferências, usa resposta JSON
mínima para perguntas simples e valida a saída por schema. O fallback compartilha
o orçamento de histórico; correções finais e fatos do usuário têm prioridade.
A pesquisa reutiliza a consulta pública do raciocinador quando disponível,
evitando uma segunda classificação no Ollama; pedidos de estudo ainda validam
o registro separadamente. Sem consulta contextual, mantém o fluxo anterior.
Pesquisa respeita a decisão de não buscar, e trocar o modelo de embeddings
reconstrói o cache. A melhoria no servidor precisa ser medida após deploy.

## Menor Intelligence Engine — em evolução

O agente interpreta objetivos com o Qwen/Ollama local e gera movimentos gerais:
responder, esclarecer, planejar, pesquisar, continuar ou encaminhar execução.
A execução é sempre validada pelo registro de ferramentas existente. Ações e
pesquisas curtas não precisam gerar campos de plano desnecessários para serem
aceitas; ferramentas e aprovações continuam sob validação do executor. O estado
de planejamento continua na SQLite por conversa; informações do cérebro entram
como dados contextualizados, sem conceder permissões. Recibos de consultas e
escritas aprovadas são preservados por conversa para consulta posterior, sem
reexecutar ferramentas; execução confirmada não garante a qualidade do conteúdo.
Veja o [fluxo de continuidade](docs/chat_a_objetivos_contextuais.md).

O módulo de laboratório mede decisões em cenários diversos. O feedback aprovado
é guardado localmente mediante consentimento explícito, sem treinamento
automático ou upload externo. Para recuperação, MENOR_INTELLIGENCE_ENABLED=0
desativa a nova camada; o padrão é habilitado.

[Roadmap e critérios de aceite](PLANO_INTELLIGENCE_ENGINE.md).

### Busca semântica local (opcional)

Se o Ollama tiver um modelo de embeddings local e MENOR_EMBED_MODEL estiver
configurado com seu nome, o Menor poderá consultar notas por significado,
além da busca FTS5. O índice fica no cérebro privado. Sem esse modelo, a
funcionalidade é ignorada e o chat continua funcionando normalmente.
Veja [plano de evolução](PLANO_INTELLIGENCE_ENGINE.md).

### Recibos de artefatos e qualidade de imagens — PR #16

O Menor agora registra a última saída de imagem na conversa, incluindo tamanho,
modelo e limitações, para responder perguntas sobre o que realmente executou.
O subagente aplica dimensões solicitadas (por exemplo, PNG 32×32 real) e
adapta prompts em português com Ollama local. Uma revisão visual opcional
requer configurar MENOR_VISION_MODEL com modelo multimodal local instalado;
sem isso, a qualidade do conteúdo não é considerada verificada. Compare
alternativas e limites em [ciclo de capacidades](docs/ciclo_capacidades.md).

### Revisão independente de planos (opcional)

O Chat A pode avaliar planos complexos usando uma segunda chamada ao modelo
local do Ollama, que verifica correspondência com o pedido, etapas específicas
e critérios de aceite. Ativa-se com `MENOR_PLAN_REVIEW_ENABLED=1` e pode usar
um modelo já instalado configurado por `MENOR_PLAN_REVIEW_MODEL`.

Por padrão fica desligada até medirmos desempenho na CPU. Ela nunca concede
permissões e pode devolver uma pergunta, uma reformulação única ou um plano
marcado como preliminar. Veja [detalhes](docs/chat_a_revisao_de_planos.md).
