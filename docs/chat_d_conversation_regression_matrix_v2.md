# Chat D — Matriz de regressão conversacional (v2)

Baseline: `bf27a84188a7bdb364518eea7875412a8a24ea49` (PR #34 integrado). Este documento especifica critérios de aceite e handoffs; **não comprova** execução real nem altera o JavaScript de `src/api/templates/chat.html`, reservado ao Chat E.

## Invariantes de execução

1. **Aprovação vinculada**: `sim`, `bora`, `pode` ou `eu aprovo` só aprovam uma operação sensível quando existe proposta pendente, identificada por missão/ação/versão/escopo, mostrada ao usuário e ainda válida. Não usar aprovação genérica como permissão global ou para uma nova ação.
2. **Negação**: `não`, `cancela`, `deixa` encerram apenas a proposta atual; não excluem artefatos, histórico ou objetivos anteriores.
3. **Perguntas**: `que aprovação?`, `e agora?`, `quanto demora?` solicitam explicação/status e nunca executam operações pendentes.
4. **Retomada**: `continua`, `bora`, `volta naquela capa` selecionam o objetivo pertinente sem repetir efeitos colaterais. Quando há múltiplos objetivos compatíveis, perguntar qual.
5. **Mudança de assunto**: não usar a última imagem como referência para pedidos de código, memória ou documentos. A volta posterior deve preservar o identificador do objetivo e do artefato.
6. **Artefatos**: `cadê a imagem?` reexibe o último artefato acessível; `edita essa` requer referência resolvida (anexo atual ou artefato anterior acessível). Nunca inventar sucesso, URL ou qualidade visual verificada.
7. **Recibos**: distinguir `planned`, `awaiting_approval`, `queued`, `running`, `executed`, `failed`, `interrupted` e `verified`. Um resultado `executed` não implica qualidade `verified`.
8. **Recuperação**: retry após interrupção mantém `turn_id` e idempotência; operação de resultado incerto requer consulta/recuperação explícita, não replay automático.

## Cenários mínimos a automatizar

| ID | Contexto | Mensagem | Resultado esperado | Dono |
|---|---|---|---|---|
| D01 | Sem ação pendente | `sim` | Conversa/esclarecimento; zero efeitos | A/D |
| D02 | Plano sensível pendente | `que aprovação?` | Explica escopo; não aprova | A/D |
| D03 | Plano sensível pendente | `bora` | Aprova somente se escopo/identidade válidos | A/D |
| D04 | Plano sensível pendente | `não` | Recusa sem executar nem apagar histórico | A/D |
| D05 | Duas missões abertas | `continua` | Pergunta qual objetivo | A |
| D06 | Imagem gerada e guardada | `cadê a imagem?` | Reexibe arquivo existente, sem nova geração | B/D |
| D07 | Imagem existente | `edita essa, muda o fundo` | Reusa referência e produz novo recibo | B/D |
| D08 | Imagem seguida de bug no código | `corrige esse bug` | Não edita imagem; roteia para agente | A/D |
| D09 | Imagem, depois outro assunto | `volta naquela capa` | Recupera objetivo e confirma ambiguidade se houver | A/D |
| D10 | Operação interrompida | `sim, recupera` | Recuperação idempotente, sem repetir efeito | A/C/D |
| D11 | Execução apenas enfileirada | `já terminou?` | Consulta status; não declara conclusão | A/C/D |
| D12 | Imagem produzida sem validação visual | `ficou perfeito?` | Declara limite de verificação | B/C/D |
| D13 | Anexo inacessível | `edita essa` | Pede reanexo; não inventa artefato | B/D |
| D14 | Conversa em streaming | Troca de conversa | Não mistura resposta nem duplica envio | D/E |

## Critérios de aceite

- Executar testes JS e Python existentes; acrescentar regressões automatizadas para D01–D14 quando cada contrato estiver implementado.
- Para cada cenário, inspecionar requisições de rede, IDs de turno/missão, estados persistidos e recibos; não aceitar apenas texto da resposta como prova de execução.
- Testar no Safari iPhone e navegador desktop **após deploy autorizado**, com upload, aprovação, reconexão e troca de conversa. Registrar ambiente, SHA e evidências; testes mockados não substituem validação real.
- Nunca diminuir testes ou burlar proteção de branch para liberar merge.

## Handoffs

- **A**: identidade de aprovação sensível, desambiguação multiobjetivo, retomada, idempotência e estados do agente. Não conceder permissão por inferência do LLM.
- **B**: resolução de artefatos de imagem e anexos, acessibilidade, edição contextual, qualidade/recibos e falha explícita de recurso ausente.
- **C**: contratos de recibos e recuperação sem replay, telemetria de transições e smoke tests reais.
- **E**: feedback visual, acessibilidade, responsividade, erros e foco no Safari; D não modifica `src/api/templates/chat.html` durante o redesenho.

## Política de integração

Chat D audita conflitos, dependências e estado da main; **cada frente mantém a responsabilidade de seus PRs**, e o merge depende de escopo revisado, CI verde, ausência de regressão conhecida, branch atualizada e autorização. PR em draft não é mesclado. Merge de código não autoriza deploy, instalação de modelos nem reinício de serviços.
