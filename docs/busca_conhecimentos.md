# Busca e gestão de conhecimentos (Menor v0.4 — incremento da Fase 2)

O Menor mantém **Markdown como fonte de verdade** e usa um índice local
`SQLite FTS5` em `~/menor-data/cerebro/memoria/indice.sqlite`.
O banco é reconstruído automaticamente quando o arquivo de aprendizados muda.

## Fluxo na conversa

1. Você ensina uma informação e o Menor a registra em
   `conhecimentos/aprendizados_gerais.md` (pela função de memória já existente).
2. Quando um assunto voltar, o backend busca no índice textual os até
   **três** trechos mais pertinentes à mensagem atual.
3. Somente esses trechos, com indicação de arquivo e linha, são enviados
   como **dados não confiáveis** ao Qwen. Nunca devem ser tratados como
   instruções que sobrepõem as regras de segurança.
4. Se não houver resultado, a resposta segue como antes, sem contexto extra.

## Editar e excluir pelo celular

Abra o Menor no Wi-Fi privado e entre com a senha do proprietário.
Na barra superior, toque no ícone de **cérebro** para visualizar conhecimentos.

- **Pesquisar:** digite um termo e veja resultados do índice (somente leitura).
- **Mostrar todos:** lista até os 100 registros mais recentes.
- **Editar:** corrija uma anotação salva (não altera outras notas).
- **Excluir:** confirme a remoção de um conhecimento da lista.

A interface só permite alterar a nota de conhecimentos gerais.
Para evitar sobrescrever mudanças de outro navegador, cada item usa um ID
derivado da linha atual e seu conteúdo; caso ela tenha mudado, a operação
retorna conflito e solicita atualização da lista.

APIs (todas exigem sessão do dono):
`GET /memory/knowledge`,
`POST /memory/search`,
`POST /memory/knowledge/edit`,
`POST /memory/knowledge/delete`.

## Limitações honestas

- A busca **ainda é textual** (palavras/tokens com tolerância a acentos).
  Sinônimos sem termos em comum podem não ser encontrados;
  embeddings locais e recuperação semântica real ficam para outra etapa.
- O índice cobre **aprendizados gerais**, não todas as pastas de projetos,
  propostas de ferramentas ou histórico de conversas.
- A detecção de intenção pelo Ollama continua independente da busca de memória
  e tem sua própria latência. Nesta etapa a busca SQLite não requer outra
  inferência do modelo.
- Erros na pesquisa não devem derrubar o chat: ele prossegue sem contexto
  recuperado e registra o problema nos logs.
- O índice SQLite é um cache: mantenha backup **principalmente do Markdown**
  e demais dados de `menor-data/`. A versão atual ainda não tem rollback
  automático de deploy.
- Evite salvar segredos e informações sensíveis; o acesso continua destinado
  a uma rede doméstica confiável ou VPN.

## Testes

O CI executa testes de busca, sincronização após edição direta do Markdown,
remoção, proteção contra caminhos indevidos, API autenticada e interface.
O aceite funcional final depende de testar o comportamento do modelo no servidor.
