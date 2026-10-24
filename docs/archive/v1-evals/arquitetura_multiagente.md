# Menor — Arquitetura multiagente local

Complementa o PLANO.md e o PLANO_REFINAMENTO.md.

## Objetivo

O Menor é o **orquestrador central**. Entende a solicitação, recupera o contexto,
identifica capacidades necessárias, planeja, delega a um subagente especializado,
verifica o resultado e o apresenta ao usuário.

Cada subagente pode usar um modelo local diferente: Qwen no Ollama para texto,
planejamento e programação; OpenVINO Stable Diffusion para pixels. A capacidade
de entender não passa automaticamente do modelo principal ao subagente.

## Máquina de estados

1. Pedido: decidir se pode executar com capacidades disponíveis.
2. Lacuna: perguntar se o usuário quer criar uma nova ferramenta.
3. Requisitos: perguntar em linguagem natural como deve funcionar.
4. Pesquisa: escolher modelos de um catálogo com origem e licença revisadas.
5. Plano: apresentar efeitos, espaço em disco, restrições e testes.
6. Aprovação: exigir permissão explícita antes de instalar.
7. Execução: um worker separado baixa o modelo permitido e prepara o runtime.
8. Verificação: produzir arquivo real, inspecioná-lo e repetir até duas vezes.
9. Entrega: marcar pronto só após teste; não confundir plano com execução.

A missão persiste no cérebro privado e não desaparece ao reiniciar a API.

## Implementação inicial

- src/agent/missions.py: missões privadas, requisitos, aprovação e estados.
- src/agent/model_catalog.py: candidatos conhecidos, sem instalação arbitrária.
- src/tools/local_images.py: worker OpenVINO CPU, download aprovado.
- src/agent/mission_worker.py: executor separado com teste de geração real.
- src/agent/reviewer.py: valida a integridade técnica do artefato.
- deploy/systemd/menor-missions.timer: fila periódica e recuperação de missões.
- API autenticada e chat para iniciar, detalhar, aprovar e consultar a missão.

Modelo inicial: https://huggingface.co/OpenVINO/stable-diffusion-v1-5-int8-ov
Licença do modelo: creativeml-openrail-m. A reserva de disco do instalador é
5 GiB (não é uma medição precisa do tamanho dos arquivos).

O provedor de imagens padrão é **local**. Não há uso automático de APIs externas.
O download inicial do modelo exige internet; depois, a inferência é offline.
As dependências opcionais vêm de um arquivo revisado do próprio repositório.

## Limitações verificáveis

- O Qwen 7B local não tem automaticamente a mesma capacidade do ChatGPT.
- A geração de imagens local está implementada como worker, mas a execução
  e o desempenho no notebook ainda precisam ser comprovados.
- Edição de imagens local ainda não está pronta.
- Descoberta de modelos hoje usa catálogo pré-aprovado; pesquisa aberta
  e verificação automática de novos candidatos ainda não existem.
- Programação autônoma genérica, modelos de música, navegador, memória
  multimodal, rollback e avaliação estética exigem outras entregas.
- O teste atual verifica arquivo válido, resolução e tamanho; não julga
  qualidade artística ou correspondência semântica com o prompt.

## Próximas etapas

1. Pesquisador de modelos: fontes/licenças/hardware e comparação auditável.
2. Programador em sandbox: criar código, testes, branches e PR supervisionados.
3. Subagentes de imagem (edição), design, web e música, cada um com testes reais.
4. Revisor multimodal local: verificar se o resultado atende ao briefing;
   dar feedback ao executor e repetir com limite de tentativas.
5. Segurança e operação: isolamento, backups, recuperação e rollback.

## Regras permanentes

- Sem instalar código ou modelo arbitrário por iniciativa do LLM.
- Sem execução irrestrita de shell, Git ou auto-merge.
- Sem usar API de outra IA sem configuração e consentimento explícitos.
- Sem alegar que concluiu uma tarefa quando existe apenas um plano.
- Sem prosseguir indefinidamente: limite de custo, memória e tentativas.
- Não transformar instruções contidas em arquivos consultados em regras.

## Integração: planejador, registro de skills e revisor (incremento PR #8)

- `src/agent/planner.py` usa o Qwen no Ollama para transformar briefing em etapas,
  critérios de aceite e limites; em caso de erro, devolve plano de contingência.
  Esse texto **nunca** concede permissão de instalar ou executar algo.
- `src/agent/skills.py` consulta o estado persistente e o runtime. Uma skill só é
  `ready` quando existe uma missão aprovada e validada **e** o modelo local está
  disponível. O endpoint `GET /agent/skills` exibe o catálogo autenticado.
- `src/agent/delegation.py` só delega geração local a uma skill verificada.
  O resultado passa por `review_image`; se falhar, no máximo duas tentativas
  antes de informar um erro. Essa revisão é **técnica**, não estética.
- Após o smoke test do instalador, o Menor cria
  `cerebro/ferramentas/imagens/geracao_local.md` com instruções reais,
  restrições e referência da missão. Não cria esse manual antes de verificar.
- O chat exibe plano e critérios antes do consentimento. Consultas de status
  confirmam que missão e runtime continuam válidos, sem alegar sucesso
  apenas porque um arquivo foi baixado.

**Limite:** integração real de instalação e velocidade da inferência ainda
precisam de teste no Ubuntu. Criar uma ferramenta genérica de música,
programação ou edição de foto continua dependendo de novos executores.

## Operação do subagente local (PR #9)

A instalação do modelo OpenVINO passou a usar um runtime Python próprio em
`~/menor-data/runtimes/openvino-image/`, fora do ambiente da API. Um
subprocesso com opções fixas executa o download de arquivos de modelo
`OpenVINO/stable-diffusion-v1-5-int8-ov` ou a geração de imagem. O child
não recebe segredos de outras integrações e tem limite de tempo.

O modelo permanece em `~/menor-data/models/openvino-sd15-int8/`.
Downloads parciais não são classificados como modelo pronto.
A primeira instalação precisa de internet; depois a geração usa apenas
pesos locais. Dependências opcionais são instaladas só após autorização.

Na conversa, "status" retorna a etapa em andamento: preparar dependências,
baixar os pesos ou testar o PNG. Antes da aprovação, o Menor informa se
há espaço livre suficiente para iniciar. O timer systemd processa tarefas
aprovadas sem necessitar de comandos manuais de Git.

**Ainda é necessário testar no notebook real.** A automação não garante
velocidade, compatibilidade com drivers ou qualidade artística.

