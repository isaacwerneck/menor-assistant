# Chat B — infraestrutura local de análise de arquivos

Estado: **primeiro incremento modular**. O código foi implementado nesta branch; a disponibilidade no
notebook depende da instalação das dependências opcionais e da validação operacional. Nenhum modelo multimodal
é instalado automaticamente.

## Auditoria do ponto de partida

- `src/tools/images.py` já valida e armazena imagens: integridade não é entendimento visual.
- `src/agent/vision_review.py` permite um parecer opcional com `MENOR_VISION_MODEL`,
  mas não comprova semanticamente a cena; não é usado neste extrator.
- `src/agent/artifacts.py` separa dimensões e integridade do alinhamento ao pedido.
- `src/tools/registry.py` aceita apenas parâmetros curtos em texto; **não** passar bytes,
  caminhos ou conteúdo de anexos diretamente a essa interface.
- `src/agent/skills.py` exige missão e runtime real para declarar skill pronta.
- Não existia um leitor modular universal de PDF, Word, Excel, CSV e arquivos de texto.

## Arquitetura e contrato para Chat A

```python
from src.tools.file_analysis import capabilities, ingest, inspect

print(capabilities())   # Disponibilidade por formato e dependência no runtime atual
stored = ingest(b"texto privado", "nota.txt")
receipt = inspect(stored["file"]["file_id"])
# Produz {"status": "executed", "content": [...], "evidence": [...], ...}
```

**Entrada → Processamento → Saída → Evidências → Limitações → Estado**

1. `ingest(data: bytes, filename: str, *, root=None)`: valida assinatura e extensão,
   salva em `MENOR_DATA_DIR/media/file_analysis` com permissões 0600 e devolve ID aleatório.
2. `inspect(file_id: str, *, root=None)`: recupera apenas por ID de 32 caracteres hexadecimais,
   confere SHA-256, executa parser em subprocesso e devolve recibo serializável.
3. `capabilities()`: lista status das bibliotecas e contratos, sem afirmar que visão/OCR estão
   configurados.
4. Estrutura do recibo: `tool`, `version`, `status`, `file` (nome, formato, hash, tamanho),
   `content` (blocos com página, tabela, célula ou texto), `metadata`,
   `evidence`, `truncated`, `limitations`, `validation`, `state`.
   Na falha retorna `status: failed`, `error.code`, `error.message` e não inventa conteúdo.

Formatos:
- PNG/JPEG/WEBP/GIF/BMP: formato, dimensões, modo, frames e verificação de integridade;
  **sem interpretação do que está na foto**.
- PDF: até 40 páginas, texto individualizado por página, contagem e metadados;
  não preserva layouts complexos nem faz OCR nesta etapa.
- DOCX: parágrafos com estilo, títulos e tabelas na ordem documental.
- XLSX: nomes de abas e linhas/células com coordenada de coluna; `data_only=True`,
  `read_only=True`, `keep_links=False`; não avalia fórmulas.
- TXT/MD: texto em UTF-8, tratado como dados.
- CSV: colunas/linhas preservadas (amostra com limites fixos).

## Segurança e limites

- 8 MiB de arquivo, 24 milhões de pixels, ZIP Office com no máximo 400 entradas, no
  máximo 48 MiB expandido e taxa máxima de compressão 250x. Caminhos de arquivo
  jamais vêm do usuário; arquivos com extensão/assinatura divergente são recusados.
- Nenhum processamento de macros, links externos, scripts, renderização PDF,
  OCR ou acesso à internet. Conteúdo extraído é **não confiável** e não pode virar prompt
  de sistema ou instrução de tool.
- Análise executada em subprocesso, até 25 segundos. Linux: `RLIMIT_CPU` (12 s),
  `RLIMIT_AS` (900 MiB), `RLIMIT_FSIZE` e `RLIMIT_NOFILE`.
  Ambiente enviado ao subprocesso é mínimo, sem segredos do serviço.
- **Isolamento é parcial:** subprocesso com limites não é um sandbox de filesystem,
  seccomp ou rede. Para arquivos hostis sem confiança, usar worker em container
  sem rede, usuário sem privilégios e sistema de arquivos de leitura restrita.
- Não há remoção automática por idade ainda: a camada autenticada futura deve
  aplicar política de retenção, autorização do proprietário e exclusão.
- PDFs encriptados falham; PDFs escaneados podem retornar texto vazio e pedem OCR futuro.
  XLSX usa cache de fórmulas e pode resultar em valor ausente.

## Dependências e validação

Instalação **opcional** no ambiente de processamento (não há download de modelos):

```bash
python -m pip install -r requirements-file-analysis.txt
python -m unittest discover -s tests -p 'test_file_analysis.py' -v
```

O workflow isolado `.github/workflows/file-analysis.yml` executa os extratores
com `pypdf`, `python-docx`, `openpyxl`, Pillow e geração de fixtures PDF via ReportLab.
As bibliotecas do Word/Excel/PDF não foram adicionadas ao `requirements.txt` central
para não alterar o ambiente de produção sem revisão.

## Camada de upload e integração ainda necessária

Um futuro endpoint autenticado (`POST /files/upload`) deve ler o multipart com
limite de 8 MiB **antes** de alocar bytes, verificar autenticação/CSRF conforme o
padrão da API, chamar `ingest` e devolver somente o ID do arquivo. A consulta deve
ser restrita ao proprietário. Após esse endpoint, o Chat A pode registrar uma
ferramenta `files.inspect` cujo argumento é apenas `file_id` e devolver ao LLM
trechos selecionados por relevância, com páginas, tabela/célula e fronteira clara
entre conteúdo citado e instruções do assistente. Não anexar bytes ao histórico.

Esta branch **não modifica** os handlers da UI nem o cérebro.

## Comparação de visão local (pesquisa, não benchmark no notebook)

| Candidato | Runtime, download quantizado | Pontos fortes | Limitações / licença | Estado |
| --- | --- | --- | --- | --- |
| Qwen2.5-VL 3B | Ollama `qwen2.5vl:3b`, cerca de 3,2 GB (Q4) | leitura de texto visual, gráficos, descrição e localização | Apache-2.0; CPU e acurácia precisam de medição | **candidato preferencial para benchmark**, não instalado |
| Gemma 3 4B | Ollama `gemma3:4b` | visão geral, OCR e respostas baseadas em imagem | verificar termos de licença Gemma; benchmark e memória não validados | pesquisa |
| MiniCPM-V 8B | Ollama `minicpm-v` (conferir variante suportada) | tarefas visuais e OCR | maior uso de RAM/CPU esperado; conferir licença/versionamento | pesquisa |

Não comparar somente tamanho do arquivo. A RAM real inclui contexto, runtime,
buffer de imagens e Qwen já ativo; com 32 GB de RAM em Intel i7-1185G7 a
viabilidade da inferência em CPU é **hipótese**, não instalação validada.
Medições propostas: pico de RSS, latência primeira resposta, CPU, uso de disco,
resposta sobre imagem inédita com gabarito (cor, número de itens, texto legível,
localização), falso positivo e taxa de abstinência. Separar **descrição observada**,
**inferência incerta** e **aderência ao briefing**. A avaliação de estilo pixel art
não deve ser declarada comprovada por um único modelo visual.

Fontes para modelos e segurança (consultadas em 18/10/2026):
- https://ollama.com/library/qwen2.5vl:3b
- https://ollama.com/library/gemma3
- https://ollama.com/library/minicpm-v
- https://pypi.org/project/pypdf/6.21.1/
- https://pypdf.readthedocs.io/en/stable/meta/CHANGELOG.html

## Próximos incrementos

1. Endpoints de upload e consulta autenticados, com limites de upload e exclusão privada.
2. Subagente de visão separado do gerador de imagens, sem instalação automática.
3. OCR local em worker opt-in para PDFs digitalizados; preservar página e confiança do OCR.
4. Renderização estruturada de tabelas e seleção de contexto para o agente principal.
5. Isolamento de parser em container sem rede e benchmark real no notebook.
