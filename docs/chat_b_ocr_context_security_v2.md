# Chat B — OCR contextual: contrato de segurança v2

- OCR é opt-in por chamada `retrieve(..., ocr_page=N)`; a ponte do agente não habilita OCR automaticamente.
- `ocr_page` e idioma são validados antes da inspeção. Limites e idiomas são compartilhados com o executor.
- Recibo OCR precisa declarar ferramenta `files.ocr`, PDF, mesmo ID e SHA-256, página, idioma, verificação do arquivo, qualidade não verificada e exatamente uma evidência `ocr_pdf_page` compatível.
- Recibos inconsistentes ou malformados falham sem devolver texto como evidência; falha de OCR não é substituída silenciosamente por extração textual.
- Citações OCR usam `file:<id>:ocr:page:<n>:<offset>`, separadas das citações PDF extraídas.
- `ocr_source_truncated` identifica truncamento na origem OCR; `source_truncated` continua representando a extração do documento.
- O conteúdo OCR é dado não confiável. Nenhuma instrução nele pode alterar autorizações, executar comandos ou conceder privilégios.
- A ponte do agente exige autorização externa e rejeita fonte OCR com âncora/citação divergentes; continua sem oferecer OCR ao modelo.
- Os testes com mocks cobrem divergência de SHA, página, evidência, recibo malformado, idioma, truncamento e opt-in. Eles não medem qualidade OCR real nem segurança completa de Poppler/Tesseract.
