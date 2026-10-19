# Chat B — subagente local de compreensão visual (contrato v1)

Este módulo é **diferente** do gerador OpenVINO de imagens e do revisor
\`src/agent/vision_review.py\`. Ele responde perguntas sobre arquivos de imagem
**já armazenados** no cofre privado. É opt-in: nenhum modelo é instalado
ou baixado automaticamente.

## Contrato

\`\`\`python
from src.tools import vision

state = vision.status()
assessment = vision.inspect_image(
    "32_caracteres_hexadecimais_de_um_arquivo_privado",
    "Que objetos são realmente visíveis nesta foto?",
)
\`\`\`

- Entrada: \`file_id\` criado por \`src.tools.file_analysis.service.ingest\`,
  pergunta de 1 a 500 caracteres.
- Processamento: exige \`MENOR_VISION_MODEL\`, checa \`/api/tags\` do Ollama
  **na própria máquina** (\`localhost/127.0.0.1/::1\`), verifica previamente
  o arquivo no worker técnico isolado e envia a imagem em base64.
- Saída: \`tool\`, \`version\`, \`status\`, \`assessment\` com
  \`observations\`, \`inferences\`, \`answer\` e \`uncertainty\`.
- Evidência: hash SHA-256 e dimensões verificadas do arquivo.
- Limites: 8 MiB por imagem (contrato do arquivo), pergunta limitada,
  timeout de 90 segundos na inferência e saída JSON de até 5.000 caracteres.
- Estados: \`not_configured\`, \`missing_model\`, \`model_detected\`,
  \`unavailable\` e respostas \`executed\`/\`failed\`.
- **\`semantic_verified = False\`** em todos os resultados: um modelo que
  descreve uma imagem não prova que descreveu corretamente.

\`model_detected\` só confirma presença em \`/api/tags\`: não comprova
que o modelo é multimodal, que a CPU o executa rapidamente ou que descreve
com precisão. A tentativa real de inferência pode falhar.

O módulo não chama ferramentas, não modifica imagens, não instala modelos,
não interpreta instruções presentes nos pixels como autorização e não publica
conteúdo na internet. A URL Ollama é restrita a HTTP loopback.

## Comparação de opções locais (fontes Ollama)

| Modelo | Dados publicados pelo Ollama | Pontos de avaliação | Estado |
| --- | --- | --- | --- |
| [Qwen2.5-VL 3B](https://ollama.com/library/qwen2.5vl:3b) | Q4_K_M, ~3,2 GB, Apache-2.0; requer Ollama 0.7.0+ | OCR, símbolos, objetos, gráficos e respostas fundamentadas | candidato leve; ainda sem benchmark |
| [Gemma 3 4B](https://ollama.com/library/gemma3) | ~3,4 GB; modelo multimodal (4B+), Ollama 0.6+ | comparação de interpretação e português; confirmar termos da licença Gemma | não instalado |
| [MiniCPM-V 8B](https://ollama.com/library/minicpm-v) | ~5,5 GB e visão; Ollama 0.3.10+ | OCR e fidelidade com imagens maiores; checar licença por variante | não instalado |

As cifras acima são downloads aproximados publicados na biblioteca Ollama,
não RAM medida no notebook. O Intel i7-1185G7 com 32 GB pode sofrer latência
e competição de memória com o Qwen principal. A seleção definitiva depende
de benchmark presencial, consumo de RAM e licença. Não escolher um modelo
apenas porque o download é menor.

## Habilitação supervisionada no Ubuntu

1. Conferir versão do Ollama, espaço livre e disponibilidade de RAM.
2. Escolher e revisar a licença do modelo.
3. Só após autorização do proprietário, executar \`ollama pull <modelo>\`.
4. Configurar \`MENOR_VISION_MODEL\` (por exemplo, \`qwen2.5vl:3b\`) no arquivo
   de ambiente do serviço e reiniciar a API.
5. Validar \`vision.status()\`, depois inferência com imagens inéditas.
6. Medir tempo de resposta, pico de RAM e acertos/abstenções com gabaritos
   definidos antes do teste.

**Nada disso é realizado automaticamente neste PR.**

## Integração futura e fronteiras

O Chat A pode consumir o contrato independentemente da orquestração.
O endpoint e a interface de arquivos do PR #21 podem expor \`vision.inspect\`
após revisão, mas nunca devem tratar a resposta do modelo como fato
corroborado. Não inserir dados visuais como instrução de sistema.

Possível sequência adicional:
- Criar benchmark de perguntas com fotos inéditas e gabarito manual.
- Adicionar OCR local controlado e evidência por página para PDFs escaneados.
- Retornar observações com incerteza no chat e permitir pedir revisão.
- Criar revisor visual multi-critério para sprites e arte sem declarar
  correspondência sem auditoria independente.

Testes desta branch simulam respostas do Ollama e arquivos reais PNG.
Não fazem download de pesos e não provam latência ou qualidade no hardware.

Referências técnicas:
- [Ollama, Vision](https://github.com/ollama/ollama/blob/main/docs/capabilities/vision.mdx)
- [Qwen2.5-VL 3B](https://ollama.com/library/qwen2.5vl:3b)
- [Gemma 3](https://ollama.com/library/gemma3)
- [MiniCPM-V](https://ollama.com/library/minicpm-v)
