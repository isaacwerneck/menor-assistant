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
