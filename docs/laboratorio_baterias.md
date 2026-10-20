# Gaveta de avaliações do Menor

Acesse `/lab/view` autenticado como proprietário. A seção **Gaveta de testes** lista baterias pré-instaladas, permite importar JSON, iniciar a execução em segundo plano e baixar relatórios completos.

- Bateria inicial: `lab/suites/diagnostico-inicial.json`.
- Baterias importadas: `~/menor-data/lab/suites/` (fora do checkout).
- Relatórios completos: `~/menor-data/lab/<run-id>.json`, disponíveis apenas na sessão autenticada.
- Resumos sem perguntas ou respostas: `~/menor-data/lab/<run-id>.summary.json`.
- Limite: 200 casos por bateria; uma execução por vez. O executor reutiliza os modos `direct` e `planner` do laboratório e **não executa ferramentas**.
- `automatic_pass` só é calculado para casos com `expected_contains`; respostas abertas permanecem sem nota automática.

## Publicação automática opcional no GitHub

Apenas métricas agregadas, nunca prompts, histórico ou respostas, são publicadas na branch `lab-reports`, pasta `lab/reports/`. Configure no ambiente do serviço:

```ini
MENOR_LAB_REPORTS_PUBLISH=1
MENOR_LAB_GITHUB_TOKEN=<token de escrita restrito ao repositório>
```

O token deve ficar **somente no Ubuntu**, fora do Git e de conversas. O servidor precisa ter acesso de saída a `api.github.com`. A publicação ocorre ao concluir a bateria; se falhar, o relatório local permanece disponível e a interface mostra `publish_status=failed:...`. O GitHub recebe somente estatísticas agregadas e identificadores, mas esses metadados são visíveis caso o repositório seja público.

**Importante:** a branch de relatórios é separada da `main` para não disparar deploys a cada avaliação. Um relatório salvo no Ubuntu **não fica automaticamente acessível a este chat**; com a publicação habilitada, é possível consultar os resumos pelo conector GitHub. Para avaliar a qualidade das respostas completas, baixe o JSON privado e anexe à conversa.

Para importar baterias, use o esquema JSON do exemplo inicial. A interface exige sessão do proprietário. Esta é uma primeira versão sem filas persistentes: reiniciar a API interrompe uma bateria em andamento.
