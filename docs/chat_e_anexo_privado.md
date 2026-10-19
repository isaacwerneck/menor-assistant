# Chat E — arquivos privados diretamente na conversa (PC e iPhone)

O Menor já possuía a tela autenticada `/files/view` e a frente B registrou
no agente os contratos read-only `files.context` e `vision.inspect`.
Esta entrega conecta esse fluxo à janela principal sem exigir que o usuário
copie manualmente IDs, preservar a direção visual *Quiet Intelligence*
previamente escolhida, e sem reestruturar o design aprovado.

## Como usar

1. Abra o chat no navegador, no PC ou no celular.
2. Toque em **Arquivo** ao lado da caixa de mensagem.
3. Escolha PDF, Word, Excel, CSV, TXT, Markdown ou uma imagem suportada.
4. Aguarde a confirmação de armazenamento privado. **Não é análise**.
5. Pergunte naturalmente: “Qual é o prazo deste documento?” ou
   “Resuma esta planilha e me diga os valores principais.”
6. O chat envia ao motor uma referência autenticada para o arquivo
   (ID privado gerado pelo servidor). A ferramenta só retorna trechos
   citados com proveniência, ou uma avaliação visual marcada não verificada.

## Contratos

- Upload envia `POST /files/upload?filename=...` com
  `Content-Type: application/octet-stream`, credenciais da sessão e
  **corpo binário**, não multipart. Não inventar API nova.
- Arquivo individual entre 1 byte e 8 MiB; nome até 120 caracteres,
  formatos reconhecidos, ID de exatamente 32 caracteres hexadecimais.
  O backend valida novamente magic bytes/extensão, limites e integridade;
  a validação do navegador não é fronteira de confiança.
- Mesmo após upload, nenhuma análise é executada até o usuário enviar
  a pergunta. Nunca colocar bytes, caminhos do PC ou URLs remotas no prompt.
- Referência no histórico explicita que o arquivo foi armazenado, porém
  **não inspecionado**. Ações e permissões seguem o catálogo confiável do
  servidor; texto extraído do documento nunca vira instrução de sistema.
- Ao alternar conversa, uma seleção pendente é abandonada; uploads ainda
  em andamento são cancelados no navegador quando possível e respostas
  atrasadas são ignoradas. O servidor pode ter armazenado os bytes antes
  de notar o cancelamento, portanto o usuário recebe orientação para verificar o armazenamento antes de
  reenviar quando houver incerteza. A tela `/files/view` só apaga o arquivo
  que foi carregado nela; o chat ainda não lista envios antigos para exclusão.
- Arquivos confirmados não são apagados ao desanexar. Exclusão exige
  `DELETE /files/{id}` com autorização. Sem limpeza silenciosa.
- Anexo de foto via botão **＋** continua sendo fluxo independente de
  edição de imagens; não mistura os dois anexos numa mesma operação.

## Qualidade

O CSS continua usando a paleta escura/violeta da interface aprovada,
com controles discretos e áreas de toque adequadas ao mobile. Nomes
de arquivos são mostrados via `textContent` (não HTML). Status de
upload utiliza `role=status` e `aria-live=polite`, com mensagens
de falha explícitas sem exibir credenciais.

Testes Node cobrem upload autenticado, bytes enviados corretamente,
limite de 8 MiB, nomes/formato/ID inválidos, isolamento entre chats,
ausência de interpretação prematura e bloqueio de envio concorrente.

## Limites de validação

Um teste de interface com mocks não comprova parsing correto de PDF,
qualidade da compreensão do Qwen ou comportamento do Safari com arquivos
do app Arquivos. Testar no Ubuntu real, inclusive timeout/retorno 401,
exclusão por ID e limites de armazenamento, depois de deploy aprovado.
Um arquivo armazenado pode permanecer até exclusão explícita;
a UX futura poderá incluir listagem e retenção automática auditável.
