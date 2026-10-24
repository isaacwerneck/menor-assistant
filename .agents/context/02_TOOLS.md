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
