# Chat B — auditoria técnica de sprites e pixel art

## Incidente original

O Menor recebeu o pedido de um mago em pixel art de 32×32, com chapéu
marrom e capa roxa. O motor local retornou uma textura: o arquivo existia,
mas não mostrava o personagem. Dimensões corretas e PNG válido não bastam
para validar a cena.

## Ferramenta independente

\`\`\`python
from src.tools import sprite_audit
receipt = sprite_audit.audit(file_id, expected_size=(32, 32))
\`\`\`

O \`file_id\` precisa existir no armazenamento privado de arquivos;
não são aceitos caminhos fornecidos pelo usuário.

Saída estruturada:
- \`status\`: \`executed\`, \`unsupported\` ou \`failed\`.
- \`technical_verified\`: arquivo decodificável e obtido de recibo privado.
- \`size_matches\`: comparação exata de largura/altura.
- \`metrics.unique_rgba_colors\`: quantidade de cores RGBA únicas, ou \`null\`
  quando houver mais de 256.
- \`metrics.fully_transparent_pixels\`: pixels com alfa zero.
- \`metrics.partially_transparent_pixels\`: pixels com alfa entre 1 e 254.
- \`metrics.nontransparent_bounds\`: limites visíveis, quando há transparência.
- \`semantic_checks\`: personagem reconhecível, cores e acessórios solicitados,
  estilo pixel art: **todos \`not_evaluated\`** sem avaliador externo confiável.
- \`content_verified = False\`: métricas não podem certificar a intenção do usuário.

A contagem de cores é calculada exclusivamente pelo worker de leitura
já isolado por subprocesso, somente para imagens de um frame de até
256×256. Imagens maiores retornam \`metrics = null\` e continuam
com informação técnica de resolução. Não é necessário instalar modelos.

## Benchmark reprodutível de aceitação

Propostas de prompts inéditos (revisar antes de usar):

| Caso | Briefing | Critérios objetivos | Avaliação manual necessária |
| --- | --- | --- | --- |
| Mago | 32×32, chapéu marrom, capa roxa | PNG 32×32 e métricas de paleta | Reconhecer mago, chapéu e capa nas cores |
| Guerreiro | 48×48, escudo redondo, espada curta | 48×48 e integridade | Silhueta, acessórios, proporções |
| Gato | 32×32, gato preto sentado, fundo transparente | 32×32, alfa e limites visíveis | Reconhecer gato e pose |
| Árvore | 64×64, copa verde e tronco marrom | 64×64, paleta medida | Reconhecer árvore, tons e forma |

Não usar estes exemplos apenas no ajuste de prompt e depois
apresentar o mesmo conjunto como teste independente. Separar amostras
de desenvolvimento e avaliação desconhecidas do gerador.

### Aceite do subagente de sprites (ainda pendente)

1. Repetir a geração no servidor Intel com o motor instalado e modelo aprovado.
2. Medir latência, RAM e taxa de falha sob carga.
3. Conferir formato, pixels reais, paleta, alfa, tamanho e armazenamento privado.
4. Fazer inspeção humana cega dos briefings inéditos com rubrica de 0 a 5.
5. Usar avaliador VLM apenas como segunda opinião e medir divergências.
6. Sem atingir critérios predefinidos, manter skill em \`needs_improvement\`,
   não \`ready_for_pixel_art\`. A geração geral de imagens e a especialização
   em pixel art são habilidades diferentes.

**Este incremento entrega auditoria técnica, não gerador especializado,
edição de imagens, OCR, benchmark real nem resultado artístico garantido.**
