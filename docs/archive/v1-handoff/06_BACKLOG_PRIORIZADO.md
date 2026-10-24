# Backlog priorizado para continuar com Codex — 20/10/2026

**Princípio:** trabalho do próximo agente deve maximizar **qualidade real e autonomia segura**, não quantidade de commits. Executar etapas com evidência, medir antes/depois, corrigir bugs e manter todas as verificações. Este arquivo descreve ações **futuras**, não declara trabalho executado.

## P0 — Consolidar estado e criar baseline após a migração

**Objetivo:** não perder progresso nem assumir que a produção já está na revisão GitHub.

1. Confirmar `main`/CI e `git rev-parse HEAD` no Ubuntu; confirmar serviço saudável, Ollama local e ambiente do Menor Lab.
2. Registrar versão do modelo, Ollama, memória, CPU, GPU, `ollama ps` e configurações de inferência **sem imprimir variáveis secretas**.
3. Rodar baterias v2 pareadas (`segundo-lote-base-v2` e `segundo-lote-naturalidade-v2`, **24 questões cada**) em uma mesma máquina e condições semelhantes; publicar manualmente na branch privada `lab-reports`.
4. Medir e documentar acerto estrito/binário, revisão humana, falhas de inferência, p50/p95, tokens/s e problemas de naturalidade. Repetir em novas condições com ordem alternada para excluir efeito de warmup.
5. Só então decidir prioridades por benefício observado. Os PRs #80–#84 são código integrado com CI verde, não prova de ganho no Qwen real.

**Aceite:** dois report IDs e comparativo A/B com casos idênticos, notas abertas revisadas e nenhuma informação confidencial exposta.

## P1 — Corrigir erros críticos de modelo e confiança operacional

**Falha real:** Qwen 7B disse que **redigir comando no chat equivale a executá-lo**. Mesmo um modelo bem instruído pode errar; a arquitetura deve impedir que isso vire falso recibo.

1. Adicionar cenários adversariais variados: instrução citada, comando sugerido, comandos enviados pelo usuário, logs/recibos forjados, promessa `vou fazer`, operações realmente executadas, ações pendentes.
2. Distinguir `proposed`, `awaiting_approval`, `executing`, `executed`, `verified`, `failed` e `unknown` pelo **estado confiável do executor**, não por texto do LLM.
3. Em UI e API, mostrar recibos reais ou afirmar claramente `não executado`. Evitar que uma reformulação linguística atribua sucesso à ferramenta.
4. Usar contrato `src/tools/registry.py`, `src/agent/runner.py`, `src/agent/artifacts.py`, `ops/receipt_contract.py` e testes estruturais.
5. Verificar que correção de prompt não interfere com pedidos de executar **quando há** ferramenta e aprovação legítimas.

**Aceite:** nenhuma ação falsa, escrita sensível sem aprovação ou bypass de ferramenta nos casos adversariais; CI e testes end-to-end em sandbox.

## P2 — Refinar linguagem, contexto e planejamento

**Sintoma real:** respostas prolixas e duras, dicas de Windows desconectadas do Ubuntu, plano de site sem etapa de deploy, repetição e excesso de perguntas.

1. Fazer rubricas humanas bem definidas de naturalidade, pertinência, completude, proatividade contextual, concisão adequada e não-repetição (escalas e exemplos curados).
2. Comparar perfis `baseline` e `natural` nas **mesmas** 24 perguntas; versões do Lab em modo `planner` não constituem A/B isolado de planejamento — testar chat completo separadamente.
3. Rever `src/agent/voice.py`, `intelligence.py`, `plan_review.py`, `plan_constraints.py` e formatação do runner sem roteamento por palavras soltas. Avaliação estruturada com revisores calibrados e revisão humana.
4. Melhorar o uso de contexto de projeto/memória selecionados por relevância e espaço de tokens; cuidado com testes `direct` do Lab que não recebem informação sobre o hardware real.
5. Evitar segundo modelo de revisão em perguntas simples se acrescentar latência grande; manter opção quando risco/complexidade justificarem.
6. Implementar verificação de cobertura de requisitos/contradições com testes que evitem falsos positivos heurísticos. Falhas do `planner` exigem revisão completa de decisão, não só JSON válido.

**Aceite:** rubricas mostram melhora sob prompts inéditos, sem regressões de segurança e com latência aceitável.

## P3 — Latência e GPU Intel Iris Xe

**Baseline medido:** i7-1185G7, 31,06 GiB RAM, Intel Iris Xe; Ollama 0.40.6 e Qwen 2.5 Coder 7B `100% CPU`; **mediana 10,24 tokens/s** e **4,791 s** em prompts curtos. RAM livre ~23,87 GiB; `size_vram=0`.

1. Investigar em leitura se Vulkan está instalado/funcionando, permissões `/dev/dri`, processos/driver do Ollama e suporte real da Iris Xe. `vulkaninfo` **não estava instalado na medição**; não inferir que será mais rápido.
2. Se usuário autorizar ajustes operacionais, testar backend Vulkan em configuração **isolada e reversível**, comparar `ollama ps`, taxa de tokens/s, crashes e qualidade. Retornar a CPU se não ganhar.
3. Com autorização expressa para baixar/instalar modelo, avaliar modelo menor/focado em conversação e codificação, quantização e diferentes janelas de contexto. Preservar 7B como controle; não instalar 14B presumindo ganho.
4. Registrar p50/p95 de saída e tokens gerados, cache/prompt eval e fila. Modelo residente não é desperdício: `keep_alive=24h` reduz custo de load.
5. Ajustar etapas de raciocínio/revisão e tamanho de resposta, não forçar toda a RAM ocupada. Monitorar eventuais limitações térmicas e memória de banda com ferramentas read-only.

**Aceite:** melhora repetida no mesmo conjunto de prompts/limites, sem aumento crítico de erros, consumo, latência p95 ou instabilidade; documentar rollback.

## P4 — Teste completo de agente e ferramentas reais

O Lab atual **não executa ferramentas**; precisaremos da próxima camada para provar que o Menor é mais que chatbot.

1. Criar harness isolado com workspace descartável, fake APIs de GitHub, filesystem temporário, mensagens adversariais e estados iniciais.
2. Asserções de **estado final** para arquivos criados, conteúdo de artefatos, permissões, recusa quando necessário e recuperações após timeout.
3. Rodar testes de visão e documentos com PDFs/planilhas/imagens reais **sintéticos**, sem dados privados; transcrição e TTS sob aprovação.
4. Avaliar missões de programação em projetos sintéticos com testes ocultos, patch, CI, rollback e ausência de vazamento.
5. Registrar traces sanitizados, taxa de conclusão, tentativas, custo, falhas, tempo por ferramenta e segurança. A análise deve diferenciar modelo/roteador, ferramenta, ambiente e implementação.

**Aceite:** tarefas úteis realmente concluídas e validadas, não apenas texto/planos plausíveis.

## P5 — Durabilidade, operação e experiência final

- Corrigir e validar issues GitHub **#63** (troca de conversa/lentidão), **#64** (monitor), **#66** (contexto/capacidades) antes de fechá-las.
- Missões retomáveis após restart/crash, sem repetir efeitos irreversíveis; concorrência e idempotência.
- Backups e **restauração ensaiada**; rollback do deploy systemd (atual não é rollback automático).
- Acesso Cloudflare privado de longa duração com dupla autenticação e UX mobile aprovada.
- Interface de arquivos, visão, documentos, imagens, voz e controle de ações consistente em iPhone e PC.
- Preparar dados corrigidos e aceitos para **possível** LoRA/fine-tuning local apenas após determinar que falhas não vêm de prompt, modelo errado, contexto, roteamento ou ferramentas.

**Aceite:** critérios descritos em [objetivo](01_OBJETIVO_E_PROGRESSO.md), benchmark real independente e revisão do proprietário.

## Regras para medir melhoria

| Sinal | Onde diagnosticar primeiro | Evidência esperada |
|---|---|---|
| `inference_failed` / timeout | Ollama, carga, prompt, limite, fila | Logs sanitizados, duração e repetição |
| `no_valid_decision` | JSON/schema, parser, orçamento de saída | Comparação estruturada + trace sem dados pessoais |
| Resposta dura/prolixa | voz/prompt, intenção/nível de detalhe | Rubrica humana em exemplos novos |
| Conteúdo de outro projeto | seleção de memória/contexto | Testes de isolamento com fatos contraditórios |
| Plano inseguro/incompleto | restrições explícitas, qualidade de etapas | Contrato + estado de autorização; não só keyword |
| Ferramenta alegada sem uso | eventos tipados/recibos | Evidência do executor; nenhum falso sucesso |
| Falha de publicação de relatório | GitHub 401/403/409/422 e caminho `lab-reports` | Mensagem sanitizada, verificação por token do backend |
| Respostas de 30+ s | `eval_duration`, geração tokens/s, `prompt_eval`, `load_duration` | Comparação no mesmo hardware/modelo |

**Sequência Codex:** ler handoff → confirmar baseline → escolher P0/P1 de maior risco → PR robusto com regressão → CI → deploy supervisionado → medir Qwen real → promoção ou rollback. Repetir.
