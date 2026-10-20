# Chat B — integração fundamentada de arquivos com o agente principal

> **Atualização posterior (20/10/2026):** a afirmação histórica abaixo de
> que a interface principal ainda não oferece anexos está superada pelo
> [PR #72](https://github.com/isaacwerneck/menor-assistant/pull/72),
> que adicionou anexos privados ao chat PC/iPhone. Contratos, sandbox e
> instalação opcional ainda requerem validação; ver
> [estado da frente B](handoff/03_FRENTES_A_B_C_D_E.md).

Esta entrega registra dois contratos já existentes no catálogo confiável do
agente: `files.context` e `vision.inspect`. Não instala modelos, não altera
arquivos privados e não habilita OCR sem pedido explícito do proprietário.

## O que passa a ser utilizável

O usuário envia um arquivo autenticado pela interface `/files/view`. O
armazenamento devolve um `file_id` opaco. Ao indicar esse identificador e uma
pergunta, o agente principal pode selecionar `files.context` ou
`vision.inspect` e receber apenas evidências com limites estritos.

Por exemplo, um pedido em linguagem natural pode ser:
“Leia o PDF com ID `<id recebido no upload>` e encontre o prazo da entrega.”

- `files.context(file_id, question)`: PDF/DOCX/XLSX/CSV/TXT/MD. Seleção
  limitada de trechos, citação de origem e endereço de página/linha/aba.
  Sem OCR implícito, sem avaliação de veracidade.
- `vision.inspect(file_id, question)`: pergunta sobre imagem armazenada.
  Depende de modelo de visão **já configurado e instalado**. A saída do
  modelo é opinião não verificada, com `semantic_verified=false`.
- Somente ferramentas no registro fechado são executadas. A chamada
  `invoke(..., authorized=True)` ocorre dentro do executor confiável, após
  autenticação do proprietário pela API do Menor; o LLM **não recebe**
  argumento `authorized`, `root` ou caminhos privados.
- O id é validado antes do parse; `dry_run` jamais lê o arquivo.
- Falhas e retornos sem texto não resultam em mensagens “verificado” ou
  “executado”. O ciclo de ferramentas é encerrado, com status `failed`
  e uma orientação explícita de verificar o runtime/arquivo.
- Texto extraído pode conter prompt injection: não vira instrução de sistema,
  não concede permissão, não cria novas ferramentas. É dado não confiável.

## Limites e próximo aceite

**Nota posterior (20/10/2026):** a interface principal recebeu seletor de
anexos privados no PR #72; o parágrafo original descrevia a limitação
**na época deste incremento**, não o estado da `main` atual. O fluxo
novo ainda precisa de aceitação end-to-end com documentos reais no Ubuntu;
veja [handoff A–E](handoff/03_FRENTES_A_B_C_D_E.md).

O parser em subprocesso ainda não é container com seccomp/rede bloqueada.
Arquivos hostis devem ser processados em isolamento mais forte antes de uso
público. `semantic_verified=false` não significa que a frase está errada,
mas que o modelo não forneceu verificação externa independente.

Validações de OCR português, imagem inédita, performance CPU/RAM e
cancelamento de workers exigem testes no Ubuntu real. Nunca afirmar
qualidade visual, texto fiel do OCR ou extração perfeita apenas pelo CI.
