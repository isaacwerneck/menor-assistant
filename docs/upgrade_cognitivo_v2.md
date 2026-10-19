# Menor — upgrade cognitivo orientado a objetivos (issues #63–#66)

> A implementação melhora os mecanismos de entendimento e interação; não prova equivalência
> com ChatGPT/Codex nem desempenho no servidor sem medições reais.

## 1. Interpretação antes de rotas por palavras

Fluxo principal:
1. O chat compõe a solicitação atual, o histórico breve e o projeto selecionado.
2. `/agent/run` consulta o planejador geral, que recebe objetivos em andamento,
   experiências confirmadas pelo usuário, ferramentas registradas e estado de skills.
3. O modelo propõe `answer`, `clarify`, `plan`, `continue`, `inspect_result`,
   `research` ou `act`. A saída JSON é validada pelo Python.
4. Planejamento nunca executa ações. O catálogo e a camada de autorização continuam
   sendo a única origem de permissões para operar em arquivos/servidor.
5. Modelos podem falhar e o fallback conversacional permanece disponível.
   Regras de segurança não são removidas para melhorar a experiência.

Perguntas simples não precisam inventar um objetivo. Perguntas de retomada são
respondidas com o contexto pertinente em vez de repetir todo o último resumo.
Recursos do servidor são relatados com base nos estados disponíveis: possuir
um contrato de API **não** prova que um modelo ou executável está instalado.

### Exemplo importante

Pedido: “Quero melhorar a interface do Menor. Crie um objetivo em três etapas
e me mostre o plano antes de fazer alterações.”

Esperado: proposta de plano, critérios verificáveis e nenhuma escrita. Não
se deve iniciar autoedição apenas porque as palavras “melhorar” e “Menor”
apareceram juntas. O comando deliberado `/corrigir …` continua sujeito às
autorizações e bloqueios do servidor. Pedidos naturais de alteração passam pelo
planejador e catálogo supervisionado.

## 2. Adaptação com correções aprovadas

Na interface: **Ensinar uma resposta** → conferir o pedido original → digitar a
resposta desejada → marcar autorização explícita → salvar.

O backend persiste até 500 exemplos por proprietário no armazenamento privado,
conforme a política de `/agent/feedback`. Nas decisões seguintes, o planejador
pode receber os cinco exemplos aprovados mais recentes, truncados por limites
de tamanho. Esses exemplos são **dados de referência**, não ordens, nem permissões.
Nenhuma conversa é automaticamente enviada para treinamento; nenhuma alteração
nos pesos do Qwen é reivindicada.

Correções e preferências explícitas podem aproximar o estilo do usuário, mas
o aprendizado não é contínuo por gradientes; é contexto/personalização local.
Para avaliação real, rode testes com exemplos não vistos, diferentes domínios,
perguntas relacionadas e alternância de assuntos.

## 3. Sessões e cancelamento da interface

O botão **Parar** e a troca de conversas interrompem a espera do navegador,
registrando a interrupção no histórico atual. O uso de `AbortController` cancela
a requisição do cliente quando suportado.

**Importante:** não é possível garantir que uma ação já iniciada no backend
tenha sido revertida. O histórico informa que a execução anterior pode continuar
e nunca repete automaticamente efeitos incertos. Regressões devem confirmar
que a resposta tardia não entre em outro chat nem contamine autorização de outro
objetivo.

O indicador do chat mostra tempo decorrido e, no modo de streaming, tempo até
a primeira parcela de texto. Não confunda esse valor com o tempo de execução do
modelo ou de uma operação no backend: medições detalhadas exigem instrumentação
dos componentes envolvidos.

## 4. Monitoramento SSH local

Depois de aplicar o PR ao Ubuntu com deploy aprovado:

```bash
menor monitor
menor monitor --once
menor monitor --interval 1 --json
menor monitor --speed-test
```

`menor monitor` mede CPU por núcleo, RAM, swap, processos mais ativos,
armazenamento do diretório home e tráfego nas interfaces do Linux. Pode sair
a qualquer instante por Ctrl+C. Processos são identificados por PID/nome curto,
**sem argumentos de linha de comando** que poderiam conter credenciais.

O monitor é somente de leitura, não exige root e não abre portas.
Tráfego passivo (MiB/s) **não é** a velocidade contratada da internet.
`--speed-test` é opcional e executa um cliente previamente instalado; consome
banda e utiliza um serviço externo. Nunca é acionado pelo monitor passivo.

## 5. Validação e limitações

CI deve passar flake8, Python, Node, contratos de API e scripts de controle.
Validações locais recomendadas:
- Uma pergunta simples de histórico (servidor Ubuntu), depois novo assunto e retomada.
- Um pedido de plano que mencione “melhorar”, sem acionar autoedição.
- Listar capacidades com provider de imagens indisponível sem inventar uso.
- Trocar chat durante geração longa; confirmar ausência de contaminação e ausência
  de reexecução automática; conferir processos residuais via monitor.
- Corrigir uma resposta, salvar com consentimento e observar a adaptação.
- Medir tempo até primeira resposta e CPU/RAM por processo enquanto Ollama executa.

**Pendências externas ao CI:** desempenho no CPU/32 GB real, qualidade factual
em novas tarefas, cancelamento no runtime Ollama, instalação do modelo visual,
latência com sessões longas, medição de velocidade real, experiência Safari.
O merge não equivale a deploy nem garante esses resultados.
