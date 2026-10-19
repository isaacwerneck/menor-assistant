# Chat B — OCR local de PDFs digitalizados (v1)

## Objetivo e escopo

Complementar a extração de texto por pypdf, que não consegue recuperar letras
de uma página que é apenas uma foto ou um scan. Esta entrega processa
**uma página por requisição**, **somente quando o usuário solicitar**,
usando Poppler (\`pdftoppm\`) para rasterizar e Tesseract para reconhecer texto.

Não executa scripts/macros em PDFs, não instala modelos ou dependências
automaticamente, não envia documentos para serviços externos, não adiciona
conteúdo ao cérebro do Menor e não faz OCR silenciosamente durante upload.

## Contratos públicos

\`\`\`python
from src.tools.file_analysis.ocr import status, ocr_page

print(status("por"))  # missing_dependency/missing_language/dependencies_detected
receipt = ocr_page(file_id, page=1, language="por")
\`\`\`

A API privada acrescenta:
- \`GET /files/ocr/status\`: apenas com sessão autenticada; inspeciona
  presença dos binários, idiomas e limites.
- \`POST /files/{file_id}/ocr\`: sessão do proprietário, JSON
  \`{"page": 1, "language": "por"}\`; uma página de 1 a 40. Idiomas
  permitidos: \`por\`, \`eng\`, \`por+eng\`. Sem acesso a caminhos do usuário.
- \`/files/view\`: campo de número da página e botão específico,
  **desativado** sem arquivo PDF ou sem dependências detectadas.

\`status: executed\` significa que Poppler/Tesseract executaram e devolveram
texto, **não** que o texto tenha sido conferido. O recibo contém hash do
arquivo, página, idioma, texto até 6 mil caracteres, truncamento, engine,
renderer, \`validation.ocr_quality_verified=false\` e limitações.

\`status: unavailable\` quando os componentes estão ausentes; \`failed\`
quando parser, execução ou tempo falharam. Uma página com texto reconhecido
vazio não equivale a imagem vazia.

## Dependências opcionais no notebook Ubuntu

O próprio dono deve avaliar licença, memória, espaço disponível e autorizar
a instalação. Exemplo para Ubuntu/Debian, **somente após autorização**:

\`\`\`bash
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
\`\`\`

Não há alteração em \`requirements.txt\`, inicialização de serviço ou
\`scripts/deploy.sh\`: o Menor não instala pacotes do sistema ao fazer deploy.
No GitHub Actions há instalação dessas ferramentas apenas no runner de CI
temporário, sem alterar o notebook.

O módulo limita CPU a 22 s, espaço de endereçamento Linux a 1,2 GiB, arquivo
intermediário a 20 MiB, processo a no máximo 40 s de parede e rasterização
a no máximo 1600 px no maior lado. O worker recebe PDF por stdin,
cria pasta temporária privada, usa comandos de argumentos fixos e nunca
inclui conteúdo do PDF na linha de comando.

**Fronteira de segurança:** limites de subprocesso não são sandbox
completo; o Poppler e o Tesseract ainda executam no SO e têm acesso à
rede/filesystem herdados conforme permissão do processo. Para receber
PDFs de origens hostis, instalar isolamento em container sem rede, usuário
sem privilégios e políticas de seccomp/AppArmor antes de confiar no pipeline.

## Critérios de qualidade / testes

- Arquivo privado é identificado por token opaco e SHA256 verificado;
  paths arbitrários, extensão diferente e páginas fora do intervalo falham.
- Estado ausente de binários ou pacote de idioma **não** simula execução.
- Execução com timeout, JSON inválido ou falha retorna erro verificável.
- OCR de PDF rasterizado novo com palavras de referência é testado no CI
  separado com binários reais instalados **apenas no runner**.
- Os testes gerais funcionam sem Tesseract e sem ReportLab no servidor.
- Mesmo com CI verde, qualidade OCR em português, documentos complexos,
  escrita manual, tabelas e latência no notebook exigem benchmark real.

## Etapas posteriores

1. Seleção OCR de páginas com prioridade por ausência de texto.
2. Inserção opcional e revisada de resultado OCR no recuperador
   \`files.context\`, preservando página, origem e confiança.
3. OCR de imagens PNG/JPEG via interface após avaliação de segurança.
4. Worker em container sem rede e teste de PDFs adversariais.
5. Benchmark reproduzível com 20 PDFs inéditos e cálculo de CER/WER
   sobre transcrições humanas, medindo CPU/RAM/tempo de ponta a ponta.

Fontes técnicas:
- https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
- https://manpages.debian.org/bookworm/poppler-utils/pdftoppm.1.en.html
