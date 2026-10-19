# Chat B — ponte de delegação privada para o Chat A (v1)

Este incremento **não registra** ferramentas no Chat A e **não ativa** OCR. O Chat A
pode avaliar a integração após revisar a política de autorização. Não é um endpoint
HTTP novo, nem concede privilégios ao modelo.

## Interface para chamador confiável

```python
from src.tools.file_analysis.agent_bridge import capabilities, invoke

print(capabilities())
# Apenas após autenticação e autorização decididas por código confiável:
receipt = invoke(
    "files.context", {"file_id": token_privado, "question": "Qual é o prazo?"},
    authorized=True,
)
```

`authorized` e `root` são **keyword-only** e não pertencem ao JSON do modelo.
Um pedido do modelo para definir `authorized=true`, fornecer `root`, path,
comando, outro instrumento ou argumentos adicionais é rejeitado. O padrão
`authorized=False` nega toda execução. O `True` isoladamente não autentica
usuário; **o Chat A é responsável pela autenticação, decisão de permissão e
registro de aprovação** antes de construir a chamada. Não expor esta função
em rota pública nem alimentar `authorized` com dados produzidos pelo LLM.

## Contratos e estados

- Ferramentas fixas: `files.context` (recuperação lexical, até 6 trechos/4.000
  caracteres) e `vision.inspect` (parecer VLM já instalado, sem conferir cena).
- Argumentos obrigatórios e exclusivos: `file_id` hexadecimal privado de 32
  caracteres e `question` textual de 1 a 500 caracteres não vazios.
- Resultado: `tool`, `bridge_version`, `status`, `authorized_execution`,
  `untrusted_content`, `data` e `error.code` somente para falhas. Estados:
  `executed`, `denied`, `invalid_arguments`, `unsupported`, `no_text`,
  `unavailable`, `failed`.
- `authorized_execution=True` indica somente que a ferramenta retornou um
  recibo técnico de execução que passou no contrato. **Não** significa que a
  resposta esteja correta, nem que OCR, compreensão visual ou ação do usuário
  foram comprovadas. `untrusted_content=True` inclusive em casos de sucesso.
- Documentos: `data.file.file_id`, `sha256`, `format` e trechos com
  `citation`/`anchor`. Citação é localizador, não prova factual.
  `content_kind=extracted_text`, sem chamar OCR e sem elevar conteúdo a prompt
  de sistema. Resultados sem texto retornam `no_text`.
- Imagens: `data.assessment`, `dimensions`, `sha256` e
  `semantic_verified=False`. São hipóteses do modelo, não auditoria de arte.
- O contrato recusa recibos fora de formato e converte erros internos em
  códigos estáveis sem devolver caminhos privados nem stack traces.

`files.ocr` fica explicitamente fora do catálogo apesar do merge do PR #34. A inclusão requer revisão do novo contrato;
qualquer integração posterior exigirá origem `extracted_text` versus `ocr_text`,
idioma, página, hash e `ocr_quality_verified=False`, sem confiar em texto
reconhecido como instrução ou transcrição validada.

## Aceite e limites

Testes usam notas privadas reais em diretório temporário, PNG real, parecer
visual simulado, recibos adulterados, prompt injection como texto simples,
permissão negada, argumentos extras, campos de autorização forjados,
indisponibilidade e OCR não registrado. Não há download de modelos nem
chamadas ao Ollama real nos testes. CI não é benchmark no Intel.

O subprocesso dos parsers/OCR continua tendo isolamento **parcial**:
processamento de documentos não confiáveis requer avaliação de sandbox
forte (container sem rede, sem credenciais e com recursos controlados)
antes de ampliar a exposição pública. A ponte não altera esse isolamento.

Handoff ao Chat A: integrar ao roteador somente com autorização confiável,
logs auditáveis, limites de contexto e distinção entre conteúdo fornecido
pelo documento, inferências de modelo e instruções legítimas do usuário.
