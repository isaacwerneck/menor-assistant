# Gaveta de avaliações do Menor

Acesse `/lab/view` autenticado como proprietário. A seção **Gaveta de testes** lista baterias pré-instaladas, permite importar JSON, iniciar a execução em segundo plano e baixar relatórios completos.

- Bateria inicial: `lab/suites/diagnostico-inicial.json`.
- Baterias importadas: `~/menor-data/lab/suites/` (fora do checkout).
- Relatórios completos: `~/menor-data/lab/<run-id>.json`, disponíveis apenas na sessão autenticada.
- Resumos sem perguntas ou respostas: `~/menor-data/lab/<run-id>.summary.json`.
- Limite: 200 casos por bateria; uma execução por vez. O executor reutiliza os modos `direct` e `planner` do laboratório e **não executa ferramentas**.
- `automatic_pass` é calculado apenas com critérios determinísticos: `expected_contains`,
  `expected_exact` estrito ou `grader=boolean` para `SIM`/`NÃO` (com pontuação final
  opcional); casos com apenas `review_criteria` permanecem **sem nota automática**.
- Há 16 baterias de 12 casos, triagem de 16, agregação de 192 e duas suítes
  pareadas A/B de 24 casos. Consulte [catálogo](catalogo_baterias_v1.md) e
  [relatórios/diagnóstico de 20/10](handoff/04_BATERIAS_E_DIAGNOSTICOS.md).

## Publicação automática opcional no GitHub

Apenas métricas agregadas, nunca prompts, histórico ou respostas, são publicadas na branch `lab-reports`, pasta `lab/reports/`. Configure no ambiente do serviço:

```ini
MENOR_LAB_REPORTS_PUBLISH=1
MENOR_LAB_GITHUB_TOKEN=<token de escrita restrito ao repositório>
```

O token deve ficar **somente no Ubuntu**, fora do Git e de conversas. O servidor precisa ter acesso de saída a `api.github.com`. A publicação ocorre ao concluir a bateria; se falhar, o relatório local permanece disponível e a interface mostra `publish_status=failed:...`. O GitHub recebe somente estatísticas agregadas e identificadores, mas esses metadados são visíveis caso o repositório seja público.

**Importante:** a branch `lab-reports` é separada da `main` para não disparar
um deploy a cada avaliação. Relatório apenas salvo no Ubuntu **não fica automaticamente
acessível por ChatGPT**; com conexão GitHub autorizada e publicação manual
aprovada, os relatórios completos já publicados na branch privada podem ser
consultados sem necessidade de anexar o JSON ao chat. Nunca exponha respostas
ou tokens em repositório público.

Para importar baterias, use o esquema JSON do exemplo inicial. A interface exige sessão do proprietário. Esta é uma primeira versão sem filas persistentes: reiniciar a API interrompe uma bateria em andamento.


## Enviar relatório completo ao GitHub manualmente

O botão **Enviar ao GitHub** aparece ao lado de cada relatório salvo. Ele envia o JSON
completo para a branch `lab-reports`, pasta `lab/reports/full/`, somente depois
da confirmação do proprietário. A publicação exige no ambiente privado do Ubuntu:

```ini
MENOR_LAB_REPORTS_ALLOW_FULL_PUSH=1
MENOR_LAB_GITHUB_TOKEN=<token GitHub restrito a este repositório>
```

O token precisa de permissão de escrita em Contents. Não o coloque no Git ou no chat.
**Confirme que o repositório é privado antes de ativar a publicação completa.**
O servidor não verifica a visibilidade do repositório automaticamente. Mesmo num
repositório privado, quem tiver acesso ao GitHub poderá ler os relatórios completos.
Não use essa opção para baterias que contenham credenciais ou dados sensíveis.
A função não abre PR nem faz merge na `main`. Desde o PR #83, o envio é
**idempotente**: conteúdo idêntico já publicado retorna o link; conteúdo
diferente no mesmo caminho gera conflito e não é sobrescrito. Falhas de API
mantêm o arquivo local disponível. O PAT exige **Contents: Read and write**.
