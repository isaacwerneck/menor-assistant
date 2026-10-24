# 02 — Catálogo de Ferramentas Reais do Sistema

As ferramentas estão implementadas em `src/tools/core.py`. Elas utilizam APIs nativas do Python e do sistema operacional.

## 1. `fs_read(filepath, max_bytes=262144)`
* **Objetivo:** Lê o conteúdo de qualquer arquivo no disco.
* **Retorno:**
  ```json
  {
    "success": true,
    "filepath": "/caminho/completo/arquivo.ext",
    "content": "conteúdo textual...",
    "truncated": false,
    "size_bytes": 1024
  }
  ```

## 2. `fs_write(filepath, content)`
* **Objetivo:** Cria ou atualiza arquivos no disco. Garante a criação de diretórios pais automaticamente.
* **Retorno:**
  ```json
  {
    "success": true,
    "filepath": "/caminho/completo/arquivo.ext",
    "bytes_written": 1024
  }
  ```

## 3. `fs_list(dirpath=".")`
* **Objetivo:** Lista arquivos e diretórios com metadados (tamanho e tipo).

## 4. `terminal_run(command, cwd=".", timeout_seconds=45)`
* **Objetivo:** Executa comandos no shell do sistema operacional (ex: `pytest`, `npm test`, `git status`).
* **Retorno:**
  ```json
  {
    "success": true,
    "exit_code": 0,
    "stdout": "...",
    "stderr": "...",
    "cwd": "/diretorio/de/execucao"
  }
  ```

## 5. `save_plan(project_slug, markdown_content)`
* **Objetivo:** Salva ou atualiza a especificação de engenharia e lista de tarefas (`PLANO.md`) do projeto no cérebro permanente.

## 6. `web_search(query)`
* **Objetivo:** Pesquisa na internet termos públicos via DuckDuckGo/Bing e retorna títulos e URLs relevantes sem precisar de chaves pagas.
* **Retorno:**
  ```json
  {
    "success": true,
    "query": "qwen 2.5 14b",
    "results": [{"title": "...", "url": "https://..."}],
    "provider": "bing-rss"
  }
  ```

## 7. `web_read(url, query=None)`
* **Objetivo:** Acessa uma página web pública (HTTPS) e extrai o texto limpo para o agente ler documentações ou notícias.

## 8. `create_new_tool(name, code, test_command, description, parameters_schema)`
* **Objetivo:** Meta-ferramenta de autoevolução. Permite que a IA crie dinamicamente uma nova ferramenta Python em `src/tools/dynamic/`, valide sua sintaxe, execute seus testes no terminal com `terminal_run`, e registre a nova função em tempo de execução no `TOOL_DISPATCHER` e no `CORE_TOOLS_SCHEMA`.
