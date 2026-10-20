# Menor Assistant — ponto de entrada para o Codex

**Snapshot:** 20/10/2026 (horário de Brasília). **Repositório:** `isaacwerneck/menor-assistant` (**privado**). **Branch de integração:** `main`. **Baseline confirmado antes deste handoff:** `826b3b5c17a69f3c7ebb25ddfaa1d63bc1d4bccf` (PR #84). O SHA da `main` pode avançar; confirme novamente no início de cada sessão.

> Este diretório contém o estado **atual** para a migração de conversas para Codex. Planos antigos continuam preservados no repositório como histórico e visão de produto. Não interprete um checklist histórico como descrição completa do software hoje. A documentação aqui registra evidência e pendências — não certifica autonomia plena do Menor.

## Leia nesta ordem

1. [01 — Objetivo e status geral](01_OBJETIVO_E_PROGRESSO.md): o produto sonhado, definição de pronto, estimativa de progresso e grandes lacunas.
2. [02 — Hardware e causa da lentidão](02_HARDWARE_E_LATENCIA.md): especificações reais, medições locais, gargalos, GPU e próximos testes.
3. [03 — Plano e estado das frentes A–E](03_FRENTES_A_B_C_D_E.md): entregas, PRs, arquivos, responsáveis lógicos e pendências.
4. [04 — Laboratório e resultados](04_BATERIAS_E_DIAGNOSTICOS.md): incidentes reais, scores corretos, evidências, como melhorar e reproduzir.
5. [05 — Operação, acesso e segurança](05_OPERACAO_E_SEGURANCA.md): Ubuntu, GitHub, deploy, Cloudflare, ambientes e limitações de autoridade.
6. [06 — Próximas implementações](06_BACKLOG_PRIORIZADO.md): plano de continuidade com tarefas e critérios verificáveis.
7. [07 — Auditoria documental](07_AUDITORIA_DOCUMENTAL.md): documentos originais revisados, divergências históricas e links canônicos.

**Instruções para o agente de código:** [`AGENTS.md`](../../AGENTS.md). Outras referências:
[`PLANO.md`](../../PLANO.md), [`PLANO_REFINAMENTO.md`](../../PLANO_REFINAMENTO.md),
[`PLANO_INTELLIGENCE_ENGINE.md`](../../PLANO_INTELLIGENCE_ENGINE.md),
[`docs/plano_integrado_a_e.md`](../plano_integrado_a_e.md) e
[`docs/segundo_lote_qualidade_v2.md`](../segundo_lote_qualidade_v2.md).

## A missão em uma frase

Construir um **assistente pessoal local, geral e inteligente**, com experiência conversacional natural e habilidades semelhantes, em escopo, à combinação ChatGPT/Codex: memória confiável, interpretação, pesquisa, arquivos/multimídia, criação, código, planejamento, ferramentas verificadas e autonomia **supervisionada**. Nunca confundir o funcionamento do Qwen com o produto inteiro.

## Estado auditável na transição

- Infraestrutura real: servidor Ubuntu, FastAPI, Ollama, UI privada, autenticação, Cloudflare Tunnel temporário usado pelo proprietário, deploy systemd e testes GitHub CI.
- Fluxo de avaliação: Menor Lab autenticado, gaveta de baterias, armazenamento de relatórios e publicação **manual** na branch `lab-reports` do GitHub privado. A conexão GitHub aqui conseguiu ler três relatórios completos.
- Primeira triagem real `triagem-16-v1`: 7 aprovações automáticas, 2 falhas automáticas, 7 sem nota automática, 0 falhas de inferência. Uma falha automática é falso negativo (`Não.`), outra é erro conceitual sobre executar comandos.
- Código mais recente: PR #84 unificou voz natural, avaliação binária mais justa, avisos de planejamento, métricas e dois lotes A/B de 24 casos; CI verde em **611 testes Python** (7 skipped) e JS/Bash. **Não foi demonstrado** que o modelo melhorou empiricamente, pois os dois lotes v2 ainda não foram publicados/testados no servidor nesta conversa.
- Hardware: i7-1185G7, 32 GB de RAM, Intel Iris Xe integrada; Qwen 7B efetivamente em CPU, mediana **10,24 tokens/s**. Sem benchmark Vulkan/offload concluído.
- Sem reivindicar fine-tuning, voz completa, agente geral estável por horas/dias, GPU acelerada ou equivalência ao Codex.

## Procedimento para começar no Codex

```bash
cd ~/menor-assistant
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin main
python3 -m unittest discover -s tests -v
```

Esses comandos são uma **sugestão para execução no Ubuntu**, não foram executados por este handoff. Ao iniciar uma tarefa, leia os contratos e testes pertinentes, verifique a revisão real, reproduza o problema, trabalhe em **branch própria**, rode CI e abra PR. **Nunca dê merge se faltar verificação obrigatória.** Não modificar `main` diretamente por conveniência, credenciais, dados privados, instalação de modelo, GPU ou serviços do Ubuntu sem aprovação apropriada.

## O que não migrar para o Git

Nenhuma senha, token PAT, arquivo `~/.config/menor/*`, dados de `~/menor-data/`, histórico privado, cookies, arquivos Cloudflare, prints com credenciais ou URLs temporárias de túnel. Os relatórios completos já publicados vivem em `lab-reports`, não na `main`, e podem conter perguntas/respostas privadas; verificar privacidade antes de publicações futuras.
