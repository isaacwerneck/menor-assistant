# 04 — Armazenamento, Estado e Persistência

O Menor v2 separa estritamente o código do repositório dos dados do usuário.

## 1. Diretório de Dados Privados (`~/menor-data/`)

Todo dado mutável reside em `~/menor-data/` (ou caminho definido em `MENOR_DATA_DIR`):

```text
~/menor-data/
├── auth.json                  # Senha e segredo de sessão do proprietário
├── tasks_v2.db                # Fila de tarefas autônomas em segundo plano
└── cerebro/                   # Armazenamento Markdown com índice SQLite FTS5
    ├── indice.db              # Banco SQLite com busca full-text FTS5
    ├── preferencias/          # Notas de preferências do usuário (.md)
    ├── conhecimentos/         # Anotações e fatos gerais (.md)
    └── projetos/              # Diretórios de projetos do desenvolvedor
        └── <slug>/
            ├── PLANO.md       # Roteiro, arquitetura e tarefas do projeto
            ├── contexto.md    # Visão geral
            ├── decisoes.md    # Log de decisões tomadas
            └── arquivos/      # Código-fonte gerado para o projeto
```

## 2. Busca e Indexação (SQLite FTS5)
* O arquivo `indice.db` mantém um índice FTS5 sincronizado com os arquivos Markdown.
* Toda vez que uma nota é gravada com `BrainStore.write_note()`, o índice é atualizado automaticamente.
* Consultas textuais rápidas usam `KnowledgeIndex().search(query)`.
