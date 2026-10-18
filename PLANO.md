# PLANO — Ecossistema Menor Assistant

> Documento de referência do projeto (**fonte de verdade para os próximos passos**).
> Plano complementar de estabilidade/autonomia: [PLANO_REFINAMENTO.md](PLANO_REFINAMENTO.md).
> Versão inicial: 1.0 — 18/10/2026. Repositório: `isaacwerneck/menor-assistant`.
> Status: **planejado**. Nenhuma fase abaixo está automaticamente concluída só por estar descrita aqui.

## 1. Visão

Transformar o **Menor** de um chat local com Ollama em um **assistente pessoal agêntico**, hospedado no servidor doméstico, que:

- mantém conhecimento duradouro sobre preferências, projetos e aprendizados;
- organiza seu trabalho em pastas e arquivos legíveis pelo usuário;
- consulta e aplica conhecimentos antes de responder ou executar tarefas;
- cria, acompanha e documenta projetos, decisões e tarefas;
- descobre e usa ferramentas especializadas (programação, arquivos, web, imagens, voz etc.);
- aprende com erros registrados e propõe melhorias verificáveis;
- futuramente **edita seu próprio código**, testa, faz commit e envia alterações em branches para revisão;
- mantém dados, memória e capacidades utilizáveis mesmo quando o modelo local for trocado.

**Princípio:** o Qwen gera e interpreta; o **Menor** organiza contexto, memória, permissões, ferramentas, tarefas, execução e versionamento. O aperfeiçoamento inicial será por software, ferramentas e memória, **não** por alteração autônoma dos pesos do modelo.

## 2. Ponto de partida (18/10/2026)

- Ubuntu Server doméstico; Ollama e `qwen2.5-coder:7b` funcionando localmente, conforme implantação relatada.
- `FastAPI` em `src/api/main.py`, interface em `src/api/templates/chat.html` e endpoints `/chat`, `/chat/stream`, `/health` e `/models`.
- Chat usa `/api/chat` do Ollama e envia histórico recente, limitado a 20 mensagens e 32.000 caracteres com a mensagem atual.
- Conversas são armazenadas no navegador, **ainda não em memória persistente do servidor**; a interface exporta Markdown.
- Scripts de deploy, units do `systemd`, timer e testes/CI estão no repositório. Instalação e funcionamento do deploy no servidor devem ser verificados separadamente.
- **Ainda não existe** executor de ferramentas, memória Markdown consultada automaticamente, projetos administrados pelo agente ou autonomia de programação.

## 3. Estrutura de diretórios

Separar **código versionado** de **dados mutáveis** para evitar que arquivos de memória bloqueiem `git pull` e o deploy. Caminhos-padrão no Ubuntu:

```text
/home/isaac/
├── menor-assistant/                # Código versionado no GitHub
│   ├── PLANO.md                    # Este documento
│   ├── src/
│   │   ├── api/                   # FastAPI + interface
│   │   ├── agent/                 # Orquestração e decisão de ferramentas
│   │   ├── memory/                # Persistência, recuperação e contexto
│   │   ├── projects/              # Projetos e acompanhamento
│   │   ├── tools/                 # Registro e execução de ferramentas
│   │   └── security/              # Autenticação e autorização
│   ├── tests/
│   ├── scripts/
│   └── deploy/
│
└── menor-data/                     # Persistente, fora do repositório
    └── cerebro/
        ├── identidade/
        │   ├── perfil_usuario.md
        │   └── preferencias.md
        ├── conhecimentos/
        │   ├── programacao/
        │   ├── game-design/
        │   ├── comunicacao/
        │   └── aprendizados_gerais.md
        ├── ferramentas/
        │   ├── catalogo.md
        │   ├── programacao/
        │   ├── imagens/
        │   └── web/
        ├── projetos/
        │   └── exemplo-de-projeto/
        │       ├── contexto.md
        │       ├── decisoes.md
        │       ├── tarefas.md
        │       ├── diario.md
        │       └── arquivos/
        ├── memoria/
        │   ├── eventos.jsonl
        │   └── indice.sqlite
        └── propostas/
            └── melhorias/
```

A raiz dos dados deve ser configurável (`MENOR_DATA_DIR`, padrão `~/menor-data`), com testes usando diretórios temporários. A estrutura de exemplo será criada pelo software no primeiro início, sem sobrescrever arquivos existentes. As pastas `ferramentas/` do cérebro guardam **descrições, catálogo, instruções e conhecimento**; os módulos **executáveis** de ferramentas ficam em `src/tools/`, sob controle de versão e testes. Não armazenar tokens, senhas, chaves ou credenciais em Markdown ou no Git.

## 4. Modelo de memória e conhecimento

### Tipos de memória

1. **Preferências e identidade:** como o usuário prefere conversar e trabalhar (ex.: respostas curtas/objetivas). Preferências explícitas têm prioridade sobre inferências.
2. **Conhecimentos por domínio:** programação, design de jogos, boas práticas, lições ensinadas e exemplos, registrando data, origem e grau de confiança quando aplicável.
3. **Memória episódica:** decisões, eventos e resultados de tarefas; histórico detalhado em JSONL, com resumos quando apropriado.
4. **Memória de projeto:** contexto, decisões, tarefas, entregáveis e diário específicos; não misturar projetos automaticamente.
5. **Catálogo de ferramentas:** o que cada ferramenta faz, parâmetros, limites, permissões e exemplos.

### Fluxo de conversa

1. Usuário envia mensagem pelo celular ou PC.
2. Orquestrador identifica intenção e projeto ativo, se houver.
3. Recuperador lê preferências e seleciona memórias pertinentes (filtros + busca textual SQLite/FTS; embeddings/RAG somente quando necessários).
4. Monta prompt para Ollama com sistema, contexto relevante, histórico recente e pedido atual, respeitando limites de tokens.
5. Modelo responde ou produz uma solicitação estruturada de ferramenta válida.
6. Executor verifica autorização, executa e registra resultado; modelo pode sintetizar resposta final.
7. Sistema propõe memórias para guardar; fatos importantes e preferências sensíveis não são gravados com base em suposições não confirmadas.

Memória durável deve sobreviver a reinício, troca de navegador, reinstalação de código e atualização do modelo. Prever visualização, correção, exclusão, exportação e backup das memórias; eventos auditáveis não devem se passar por fatos verificados. Minimizar conteúdo na janela de contexto: **mais memória em disco não significa enviar tudo a cada prompt**.

## 5. Projetos — regras esperadas

- Ao pedido explícito de “novo projeto”, criar `projetos/<slug-seguro>/` e os arquivos padrão; confirmar ambiguidades de nome ou escopo.
- Cada projeto registra objetivos, estado atual, decisões e razões, próximas tarefas, logs de atividades e entregáveis.
- Mudanças relevantes geram registro com data, autoria/origem e resumo; o assistente deve consultar o projeto ativo antes de trabalhar nele.
- Suportar consultar, listar, exportar, pausar, arquivar e excluir projetos mediante confirmação quando a ação for destrutiva.
- Impedir traversal (`../`), symlinks escapando da raiz e escrita fora do caminho autorizado; impor limites de arquivo/tamanho.

## 6. Sistema de ferramentas (skills)

- `src/tools/registry.py`: catálogo executável de ferramentas com nome, descrição, esquema de entradas/saídas e permissões.
- `src/tools/file_tools.py`: operações controladas de leitura, criação e edição em caminhos autorizados.
- `src/agent/orchestrator.py`: ciclo pedido → contexto → decisão → autorização → execução → resultado → resposta.
- `src/security/permissions.py`: política central de acesso e aprovação; padrões restritivos.
- Ferramentas futuras: programação, terminal isolado, pesquisas web, geração/edição de imagens, voz, integração com serviços, game dev.
- Resultados de ferramentas e conteúdo da web/arquivos são **dados não confiáveis**: não podem sobrescrever regras de sistema nem conceder permissões.
- Implementar logs por ação, timeouts, limites de recursos, simulação (`dry-run`) quando fizer sentido e mensagens de erro compreensíveis.

## 7. Autoaprimoramento e programação do próprio Menor

Meta de longo prazo: o Menor criar melhorias e novas skills com supervisão, **sem alterar diretamente o processo em execução nem enviar código não revisado à `main`**.

Fluxo desejado:

1. Identifica oportunidade ou recebe pedido de melhoria.
2. Produz especificação, avaliação de risco, arquivos afetados e testes esperados.
3. Cria branch de trabalho em checkout isolado (não edita o diretório de produção).
4. Implementa código e testes; executa lint, testes e validações em sandbox sem segredos e com recursos limitados.
5. Analisa falhas e tenta correções limitadas, registrando o aprendizado.
6. Faz commit/push **somente da branch de trabalho** e abre Pull Request.
7. Usuário revisa e aprova; após merge, deploy controlado aplica a nova versão.
8. Monitora saúde após instalação; possuir procedimento de recuperação/rollback testado.

A execução de comandos arbitrários, acesso a segredos, alterações do deploy, permissões, firewall, credenciais, instalações de dependências e operações destrutivas precisam de controle especial ou confirmação explícita. Auto-reflexão significa melhorar **memória, instruções, ferramentas e código**: não é treinamento automático dos pesos do Qwen. Fine-tuning pode ser avaliado depois, à parte, conforme dados e hardware disponíveis.

## 8. Roadmap aprovado

### Fase 1 — Fundação do cérebro (**primeira entrega: Menor v0.3**)

- [ ] Criar `src/memory/store.py` e inicialização idempotente do cérebro em `MENOR_DATA_DIR`.
- [ ] Criar Markdown de identidade, preferências, conhecimentos e projeto de exemplo de forma segura.
- [ ] Implementar leitura e escrita atômica de Markdown, com validação de caminhos e limites.
- [ ] Implementar busca simples e carregamento de preferências antes da chamada ao Ollama.
- [ ] Adicionar instrução “lembre disso” com operação explícita e verificável.
- [ ] Adicionar testes para persistência, reinício, diretórios proibidos e compatibilidade do chat atual.
- [ ] Garantir que os dados sejam preservados em atualizações de código.

**Aceite:** dizer “prefiro respostas objetivas”, salvar a preferência, reiniciar a API e receber respostas com essa preferência recuperada, sem precisar repetir a instrução. Nenhuma gravação fora do diretório autorizado. O chat antigo continua funcionando.

### Fase 2 — Gerenciador de conhecimentos e memória

- [ ] Implementar registro, revisão, atualização, busca e exclusão de conhecimento com fontes.
- [x] Usar SQLite (FTS5) para indexação e pesquisa textual dos conhecimentos gerais.
- [ ] Separar memória episódica de preferências e fatos consolidados.
- [ ] Estabelecer política de relevância, deduplicação e conflito entre informações.
- [ ] Opcional posterior: embeddings locais e busca semântica/RAG.

**Aceite:** conhecimentos ensinados reaparecem em conversas posteriores quando relevantes, sem invadir assuntos não relacionados; usuário consegue ler/corrigir/apagar as entradas.

**Incremento entregue em PR #4:** recuperação textual contextual de conhecimentos gerais,
consulta, correção e exclusão autenticadas pela interface, com índice FTS5.
Busca semântica/embeddings, reconciliação de conflitos e recuperação dos
conhecimentos específicos de projetos permanecem pendentes. O aceite completo
da Fase 2 depende de validação no servidor com o modelo real.

### Fase 3 — Gestor de projetos

- [x] Criar e listar projetos com nomes normalizados, pastas e templates Markdown.
- [ ] Registrar contexto, decisões, tarefas, diário e arquivos com referências de origem.
- [x] Selecionar projeto ativo por conversa e recuperar contexto antes de trabalhar.
- [ ] Exportar e arquivar projetos com segurança.

**Aceite:** pedido de novo projeto cria pasta e documentos; retomada após reinício preserva decisões e próximo passo.

**Incremento do PR #5:** contexto de projeto por conversa, listagem,
decisões/tarefas/diário no Markdown e perguntas de memória respondidas
em linguagem natural, sem menu de categorias. Permanecem pendentes:
desambiguação de nomes de projetos, exportação/arquivamento
seguro, registro de arquivos com metadados e testes com o modelo real.

**Incremento v0.5 em PR #6:** catálogo de ferramentas com validação,
`dry-run`, autenticação de API, comprovante da execução e trilha de
auditoria privada. O agente ainda não invoca automaticamente ferramentas
arbitrárias, e o agente programador/integração Git/sandbox ficam pendentes.
Também corrige regressões observadas nos prints do iPhone (confirmações
curtas e overflow). Veja [PLANO_REFINAMENTO.md](PLANO_REFINAMENTO.md).

### Fase 4 — Ferramentas e execução agêntica

- [ ] Criar registro de ferramentas, esquemas e permissões por ferramenta.
- [ ] Integrar chamada estruturada de ferramentas do modelo ao orquestrador.
- [ ] Implementar ferramentas básicas de arquivos e gerenciamento de projeto.
- [ ] Adicionar aprovação do usuário para escrita sensível e isolamento para execução de código.
- [ ] Adicionar auditoria, timeouts, limites e testes de prompt injection.

**Aceite:** o Menor usa ferramentas reais para criar/atualizar um projeto autorizado e relata exatamente o que executou; recusa operações fora de escopo.

### Fase 5 — Agente programador e evolução do próprio código

- [ ] Permitir inspeção do repositório e planejamento de mudanças.
- [ ] Implementar escrita em checkout/branch isolada com testes e lint.
- [ ] Integrar git commit, push e abertura de Pull Request com credenciais de escopo mínimo.
- [ ] Exigir revisão antes de merge/deploy e criar recuperação testada.
- [ ] Registrar erros e lições úteis como propostas de melhoria.

**Aceite:** cria uma ferramenta pequena em branch de teste, valida os testes, publica PR e aguarda aprovação; não altera produção autonomamente.

### Fase 6 — Expansão de capacidades

- [ ] Web/navegação com permissões e tratamento de conteúdo não confiável.
- [ ] Geração e edição de imagem por motor adequado.
- [ ] Voz: STT (Faster-Whisper), TTS (Piper), wake word se desejado.
- [ ] Ferramentas de programação/game dev e integrações externas.
- [ ] Avaliar desempenho local e eventual fine-tuning, sem presumir viabilidade.

**Aceite:** cada nova skill tem contrato de ferramenta, testes, permissões, documentação e exemplo de uso; memórias continuam compatíveis.

## 9. Engenharia, segurança e implantação

- **Não quebrar o chat atual**: endpoints existentes e streaming continuam compatíveis; migrar por etapas.
- Proteger acesso remoto: sem expor API sem autenticação à internet; preferir VPN privada (ex.: Tailscale) e introduzir autenticação antes de ferramentas capazes de escrever/executar.
- Não guardar credenciais em Markdown, logs ou commits. Minimizar permissões da conta que executa a API.
- Dados fora do Git e **backup periódico restaurável** de `menor-data/`, incluindo SQLite/Markdown; definir política de retenção.
- Dev/testes devem usar dados temporários, não diretórios reais do cérebro; impedir escrita fora da raiz.
- Validar CI antes do merge; script do deploy atual não possui rollback automático. Implementar recuperação segura antes do agente desenvolvedor.
- Controlar consumo de RAM/CPU (i7-1185G7, 32 GB) e latência. Preferir abordagem incremental e mensurável a serviços adicionais desnecessários.
- Toda fase deve ter documentação, teste automatizado, cenários de falha e verificação manual no servidor quando necessária.

## 10. Ordem de trabalho imediata

1. Salvar e versionar **este `PLANO.md`** no repositório `isaacwerneck/menor-assistant`.
2. Corrigir a autorização do GitHub App para permitir escrita no repositório; idealmente trabalhar em branch + PR.
3. Confirmar o funcionamento do serviço `menor-api` e do timer de deploy no Ubuntu; não presumir instalação pela mera presença dos arquivos.
4. Implementar **Fase 1** em PR pequeno, sem incluir alterações invasivas na interface nem executar código arbitrário.
5. Executar testes + validar no navegador e no servidor; documentar conclusão real antes de marcar checkboxes.

## 11. Governança deste plano

- `PLANO.md` é o documento-base acordado. Ajustes futuros devem ser explícitos, versionados em commits e justificados.
- O `docs/roadmap.md` pode funcionar como resumo de execução e apontar para este arquivo, sem substituir as definições arquiteturais.
- Não marcar fases como concluídas antes de verificar critérios de aceite.
- Decisões de segurança e isolamento não devem ser removidas sem revisão consciente.

---

## 12. Decisão de produto — iniciativa contextual (18/10/2026)

O Menor **não dependerá de palavras-chave fixas ou comandos decorados**. Antes de
responder, interpretará a intenção e o histórico recente para escolher entre:
conversar, registrar memória clara, pedir esclarecimento e executar uma ação
suportada (por exemplo, criar de verdade um projeto e seus arquivos).

- Intenções inequívocas e de baixo risco poderão gerar memória sem confirmação
  adicional, **sempre com registro visível do que foi salvo e onde**.
- Quando intenção, informação ou categoria forem incertas, o Menor fará
  pergunta objetiva para escolher entre conhecimentos, projetos, ferramentas etc.
- Pedidos explícitos de criar um projeto devem resultar em pastas e documentos
  reais, não apenas em uma anotação da frase "criar projeto".
- Pedidos de criação de ferramentas devem virar planejamento e, quando houver
  executor agêntico isolado, implementação testada em branch e Pull Request;
  **não afirmar que a ferramenta existe se foi apenas registrada como ideia**.
- Ferramentas, código, shell, Git e ações destrutivas precisam das permissões e
  revisões já definidas neste documento. Autonomia não equivale a acesso irrestrito.
- O classificador baseado em modelo nunca decide sozinho caminhos arbitrários;
  o sistema valida entradas, nomes, locais permitidos, consequências e limites.
- Falhas na interpretação não devem resultar em gravação silenciosa nem em
  promessas falsas. A conversa deve continuar ou pedir esclarecimento.

Implementação incremental: [roteamento contextual](docs/roteamento_contextual.md).

---

## 13. Entrega integrada de imagens e autoedição supervisionada — PR #7

- [x] Roteamento independente de imagens (criar/editar/pedir detalhes).
- [x] Estado de imagem pendente por conversa e anexo discreto no celular.
- [x] Provedor externo opcional de imagem, protegido por autenticação; sem chaves, nenhum sucesso inventado.
- [x] Motor de proposta de correção restrito a arquivos permitidos, com branch e PR rascunho após opt-in.
- [ ] Provedor local sem dependência de nuvem; execução autônoma de programação em sandbox.
- [ ] Web/voz e observabilidade proativa, backups, rollback e testes reais no notebook.

Ver [guia de imagens/autoedição](docs/imagens_autoedicao_v06.md).

---

**Direção acordada:** *Você ensina → Menor registra → Menor recupera → Menor aplica → Menor avalia → Menor propõe melhorias.*

## 14. Sistema multiagente local — incremento PR #8

- [x] Orquestrador de missões persistentes com requisitos e aprovação.
- [x] Catálogo auditável de candidatos locais; sem downloads arbitrários.
- [x] Worker OpenVINO de imagem em CPU e prova técnica de geração real.
- [x] Provider padrão local sem API externa nem chave de terceiros.
- [x] Worker agendado por systemd para instalações aprovadas.
- [ ] Pesquisa aberta e auditoria de novos modelos locais.
- [ ] Edição de imagens local, áudio, design, navegação e visão multimodal.
- [ ] Programador autônomo em sandbox com testes de regressão e PR.
- [ ] Avaliação semântica dos artefatos, correção iterativa e limites de recursos.

Consultar [arquitetura multiagente](docs/arquitetura_multiagente.md).
