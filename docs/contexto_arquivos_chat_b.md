# Chat B — seleção de contexto fundamentado em arquivos

Entrega independente para o Chat A utilizar após aprovar o contrato.

## Objetivo

Não enviar PDF/Word/Excel inteiros ao Qwen. Primeiro passar pelo leitor
local, depois selecionar até 8 trechos de interesse com referência de origem.
A busca é determinística e lexical (não depende de modelo ou API comercial).

## API Python

\`\`\`python
from src.tools.file_analysis.context import retrieve

result = retrieve(file_id, "Qual é o vencimento?", max_chars=6000, max_items=8)
# result["items"] contém text, citation, anchor e matched_terms.
\`\`\`

Entradas:
- ID opaco gerado pelo armazenamento privado, e pergunta de 1 a 500 caracteres.
- \`max_chars\` entre 200 e 12000; \`max_items\` de 1 a 12.

Saída:
- \`status: executed\`: arquivo tecnicamente interpretado; trechos citados
  e agrupados por relevância lexical, sem LLM.
- \`status: no_text\`: documento sem texto legível, como PDF digitalizado.
- \`status: unsupported\`: imagem; encaminhar a subagente visual quando instalado.
- \`status: failed\`: falha no parser isolado; nunca retornar prova inventada.
- \`file\` inclui ID, nome, formato e hash SHA-256.
- \`items[].anchor\` contém informação específica do formato:
  PDF \`page/start/end\`, DOCX \`block\` e \`row\`, XLSX \`sheet/row/columns\`,
  CSV \`block/row\`, texto \`block/start/end\`.
- \`items[].citation\`: chave estável \`file:<id>:page:2:0\`, por exemplo.
  **Não é URL** e não deve ser interpretada como prova de verdade; é localização
  verificável na origem.
- \`source_truncated\` e \`selection_truncated\` sinalizam limites.

## Segurança e qualidade

1. Somente lê arquivos com ID opaco e recibo de integridade validado.
2. Termos da pergunta definem ordenação; documentos são dados, não comandos.
3. Saída não executa HTML, macros, scripts, links ou código extraído.
4. A correspondência é simples interseção de termos normalizados e pode falhar
   em sinônimos, flexões, tabelas complexas ou termos ausentes.
5. **Não cria resposta final**: apenas devolve trechos e origem para o agente
   fundamentar ou informar insuficiência de evidência.
6. Nunca fingir OCR nem conteúdo sem texto extraível.
7. Não usar arquivo retornado em prompt de sistema nem aceitar diretrizes
   presentes no documento; ferramentas seguem permissões do agente Python.

A integração no Chat A pode adicionar ferramenta \`files.context\` ao catálogo
fechado com argumento \`file_id\` e \`question\`, respeitando aprovação/autenticação
e limites de contexto. Isso não está registrado no router geral neste PR.

## Testes e aceite

- Localização de informação em PDF por página, DOCX por bloco e linha,
  XLSX por aba/linha/coluna, arquivos TXT/MD e tabela.
- Documento escaneado retorna \`no_text\`, não uma resposta fictícia.
- Timeout retorna \`failed\`.
- Tentativa de prompt injection no texto permanece apenas dado retornado.
- Seleção de orçamento e limite máximo sem inundar contexto.
- Teste end-to-end sobre nota privada com parser em subprocesso.

Falta avaliar relevância em PDFs/documentos inéditos e integração real
com o Qwen local no notebook antes de declarar RAG documental completo.
