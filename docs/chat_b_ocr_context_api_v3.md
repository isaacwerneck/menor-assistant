# Chat B — Consulta documental com OCR explícito via API

Endpoint autenticado existente: `POST /files/{file_id}/context`.

Corpo padrão (não executa OCR):
```json
{"question":"Qual é o prazo?"}
```

Corpo com OCR solicitado pelo proprietário:
```json
{"question":"Qual é o prazo?","ocr_page":1,"ocr_language":"por"}
```

- Autenticação do proprietário e validação de origem continuam obrigatórias, antes da análise.
- `ocr_page` é opcional, inteiro estrito (booleanos e strings rejeitados), entre 1 e MAX_PAGES. A página precisa existir no PDF. Idiomas: por, eng, por+eng.
- OCR roda somente na página informada, não em lote. A rota chama o executor local supervisionado; não instala dependências e não habilita ferramenta no orquestrador.
- O recibo valida ID, SHA-256, formato PDF, evidência e página. Trechos OCR recebem `source: "ocr"`, âncora e citação distinta; `ocr_quality_verified: false`.
- Dependência OCR ausente/falha: HTTP 503, `grounded: false`, sem inventar transcrição. Payload inválido: HTTP 422.
- Texto do documento/OCR permanece não confiável; nenhuma instrução embutida ganha autoridade.
- Não há reconhecimento automático em uploads, arquivos não PDF, nem na ponte de ferramentas do agente.
- Cobertura: ASGI autenticado, CSRF/origem, opt-in, limites e tipos, indisponibilidade, além dos testes anteriores de proveniência e integridade.
