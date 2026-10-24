# Ciclo universal de capacidades — Menor Assistant

Este documento amplia [PLANO_INTELLIGENCE_ENGINE.md](../PLANO_INTELLIGENCE_ENGINE.md)
e [PLANO.md](../PLANO.md). O objetivo não é programar frases para cada nicho,
mas separar raciocínio, instalação, execução e avaliação **para qualquer skill**.

## Incidente motivador

O usuário pediu um mago 32×32 com chapéu marrom e capa roxa. O Menor exibiu
uma imagem que parece uma textura e anunciou que o arquivo estava verificado.
Quando questionado, o modelo respondeu que não podia criar imagens, negando
a execução que o servidor acabara de registrar.

Causas identificadas:
1. O gerador trabalhava sempre em 512×512, sem aplicar o tamanho pedido.
2. O revisor só checava se o PNG existia, não seu conteúdo.
3. A conversa não carregava um recibo do resultado para turnos seguintes.
4. O catálogo tinha um único instalador; isso foi tratado como uma única opção
   possível, sem pesquisa ou comparação de famílias.
5. O modelo local SD1.5 não foi treinado especificamente para sprites, e prompts
   livres em português podiam não ser adequadamente interpretados.

## Procedimento universal desejado

1. **Entender** o resultado que o usuário quer, contexto, exemplos e restrições.
2. **Descobrir** capacidades existentes, versões, licenças, documentação e
   alternativas. Declarar explicitamente quais pesquisas foram feitas e suas fontes.
3. **Comparar** modelos/subagentes usando recursos do servidor, requisitos, tempo,
   qualidade e licenças. Um catálogo não substitui pesquisa recente e benchmark.
4. **Planejar** contrato de entrada/saída, testes de desempenho e critérios do
   briefing antes de instalar ou desenvolver.
5. **Autorizar** especificamente downloads, dependências e mudanças persistentes.
6. **Implementar** no ambiente isolado, registrar código/skill, testes e recibos.
7. **Avaliar** arquivo técnico, objetivo semântico e qualidade da tarefa de
   referência; usar segundo modelo quando houver revisão confiável disponível.
8. **Corrigir** erros em ciclo de tentativas com limite de CPU, duração e custo.
9. **Publicar** habilidade só após critério demonstrado. Não elevar qualidade
   desconhecida a habilidade comprovada; manter relatório de limitações.
10. **Aprender** com avaliações e feedback aprovado (RAG primeiro; LoRA/QLoRA
    somente depois de dataset curado, hardware e benchmark A/B).
11. **Retomar** o contexto de execução entre mensagens, reinícios e projetos.

## Incremento atual — PR #16

- Recibo de artefato no estado durável da conversa: entrada, URL privada,
  resolução, worker e limites de verificação. Perguntas posteriores usam
  esses dados, não a identidade imaginada do modelo de chat.
- Formatação de PNG no tamanho pedido (por exemplo, 32×32 real), com
  reamostragem e paleta discreta para sprites pequenos; isso **não garante
  um personagem reconhecível** se a composição original estiver errada.
- Adaptador local de prompt Ollama para modelos de imagens com briefing em
  português; preserva dimensões e intenção, sem API externa.
- Revisor distingue validade técnica e fidelidade visual. Um segundo modelo
  do Ollama pode atuar se MENOR_VISION_MODEL apontar para um modelo local
  multimodal já instalado; sem ele, qualidade do conteúdo fica "não avaliada".
- Até duas tentativas com feedback do revisor visual quando configurado.
  A avaliação por IA ainda é hipótese; requer comparação com humano.
- Comparação de candidatos com fontes oficiais e integradores explícitos.
  **Somente** o SD1.5 INT8 possui instalador revisado. Outros modelos não
  são baixados nem recebem status de "prontos".
- Interface preserva o resultado técnico no histórico, e imagens pequenas
  são exibidas com pixels nítidos.

## Próximas etapas ainda não implementadas

- Agente de pesquisa contínua que atualiza o catálogo pela internet sem
  compartilhar briefings/segredos privados com buscadores.
- Implementadores de famílias alternativas, LoRAs de pixel art ou um pipeline
  de sprites específico, todos testados no hardware Intel.
- Benchmark visual com conjunto de prompts inéditos e critérios reais de
  fidelidade, proporção, anatomia, paleta e grade 32×32.
- Missões de desenvolvimento de vários arquivos e vários dias em sandbox,
  com planejador, testes independentes, PR e retomada após interrupções.
- Ferramentas de música, design, automação de desktop e modelos de visão/áudio,
  cada uma sujeita ao mesmo ciclo sem hardcode de comandos do usuário.
- Dataset curado por feedback e treinamento local supervisionado, com
  comparativo A/B e rollback, **não aprendizagem automática por conversa**.

## Critério de sucesso

A ferramenta só merece o estado "domina pixel art" quando um conjunto
independente de sprites com briefs inéditos cumprir resolução, conteúdo e
qualidade mínima, em teste no servidor. "Arquivo gerado" é uma observação
técnica, não prova de especialização.

Fontes de modelos:
- https://huggingface.co/OpenVINO/stable-diffusion-v1-5-int8-ov
- https://huggingface.co/OpenVINO/stable-diffusion-v1-5-fp16-ov
- https://huggingface.co/stabilityai/sd-turbo
- https://huggingface.co/black-forest-labs/FLUX.1-schnell
