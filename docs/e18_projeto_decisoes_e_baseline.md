# E18 — Escolhas persistentes em projetos e comparação E17 (22/10/2026)

## Quatro relatórios novos encontrados

Todos os arquivos foram enviados para a branch privada `lab-reports`:
`20261022T150728Z-{c8ed0548,8bdcb187,3884bb16,3d54bcfe}.json`.
São duas baterias por modelo (32 posições de turno por bateria).
Os quatro apontam para o mesmo código E17: `49fb4f14`.

| Modelo e bateria | E15 pré-E17 | E17 | Mudança |
| --- | ---: | ---: | ---: |
| 7B intenção | 5/8 conversas completas | 3/8 | -2 |
| 7B segurança | 6/8 | 3/8 | -3 |
| 14B intenção | 0/8 | 0/8 | sem recuperação |
| 14B segurança | 0/8 | 0/8 | sem recuperação |

7B E17: **36 de 64 posições** com decisões válidas (18+20 menos
duas decisões bloqueadas? Não: o número de decisões válidas é
**38 de 64**, contando as conversões de ações reprovadas, que não
passam na nota automática). **34/64 checks aprovadas**, 30 reprovadas.
Foram 10 decisões inválidas ou timeouts (5 por suíte), seguidos de
16 turnos pulados. 14B: 6/64 decisões validadas, demais turnos
interrompidos ou pulados.

No 7B, o filtro `action_quote` rejeitou várias propostas de ação que
não correspondiam a um pedido direto, incluindo solicitação hipotética de
salvar projeto e frase negativa sobre criar PDF. Essa proteção é
importante, mas **não é uma melhoria de inteligência**: a proposta
errada é contada como falha, mesmo que o executor a recuse.
O menor número de conversas concluídas constitui uma regressão
observada. Não existe evidência suficiente para atribuir a piora
exclusivamente ao prompt compacto ou ao orçamento de tokens.
Não desativar barreiras de segurança só para aumentar a nota.

## Implementação E18: decisões atuais

Ferramenta: `projects.set_decision`, com `slug`, `topic` e `value`.
Só é apresentada em sessões pessoais com escopo, nunca usada para
modificar o código do assistente. Só grava em **projeto privado existente**
depois de apresentar a aprovação do proprietário.

Comportamento:
- Cria uma decisão vigente por tema em `decisoes.md`;
- Uma correção no mesmo tema substitui a decisão vigente anterior
  (comparação case-insensitive do tema);
- Notas históricas feitas por `append` ficam preservadas;
- Uma gravação idêntica é idempotente;
- O contexto recuperado no projeto prioriza **decisões atuais**
  mesmo com limite de 1050 caracteres;
- Não escreve em projetos inexistentes, diretórios arbitrários,
  links simbólicos ou arquivos fora do cérebro;
- `perform(..., dry_run=True)` valida projeto e parâmetros sem gravar;
  a execução real volta a validar o estado e devolve recibo.

Exemplo de conversa-alvo: no projeto `aurora-notes` já selecionado,
o usuário solicita explicitamente "Registra nossa decisão:
armazenamento local, sem nuvem". O agente poderá preparar a ferramenta
e solicitar aprovação, e então salvar a decisão. Se depois solicitar
"Troca a decisão de armazenamento para arquivos locais com backups",
a decisão vigente será atualizada no mesmo arquivo.

**Limites**: a ferramenta não transcreve automaticamente toda a
conversa nem decide sozinha o que registrar. Ainda não existe executor
completo criar→testar→corrigir aplicativos, nem cache semântico de
decisões por projeto. Segurança dos argumentos e aprovação continuam
determinísticas.

## Próxima validação útil

- Depois de integrar o PR e fazer deploy, **não repetir 272 turnos**:
  compare algumas conversas completas com 7B e 14B e inspecione
  `action_rejected`, `validation_issue`, `done_reason`, prefill e
  tempo de geração.
- Faça um teste real de escolha/correção de projeto e confirme que
  `decisoes.md` mostra apenas a escolha vigente dentro do bloco
  ativo; notas anteriores fora do bloco continuam preservadas.
- A melhoria seguinte do plano é executor de projeto supervisionado
  e verificação real de arquivos, não apenas classificações de texto.
