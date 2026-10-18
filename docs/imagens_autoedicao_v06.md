# Menor v0.6 — Imagens e autoedição supervisionada

Entrega integrada do [PLANO.md](../PLANO.md) e [PLANO_REFINAMENTO.md](../PLANO_REFINAMENTO.md).

## Pedidos de imagem pelo chat

O Menor reconhece 'quero q vc crie uma imagem pra mim' e pergunta a cena e o estilo.
A resposta seguinte continua a mesma tarefa. Se já houver detalhes, inicia geração.
Para editar, o botão pequeno ＋ do chat permite anexar PNG, JPEG ou WebP.
Imagens válidas geradas ficam em `~/menor-data/media/images/` e só são exibidas
com sessão autenticada. O Menor não declara sucesso sem imagem confirmada.

## Motor real e custos

O código inclui integração real com a API de imagens da OpenAI.
Para ativar, o dono precisa configurar a variável de ambiente de serviço
`MENOR_IMAGE_API_KEY` com uma chave de API própria, com créditos e cobrança aplicável.
`MENOR_IMAGE_MODEL=gpt-image-1` é opcional e esse modelo é o padrão.
O Qwen de texto do Ollama não gera pixels por si só.
Quando o provedor está configurado, prompts e fotos enviados para gerar ou editar
são transmitidos ao serviço externo. Sem configuração, o Menor explica
que o motor não está disponível, sem fingir geração e sem transmitir a foto.
Não salve chaves no Git, Markdown ou no chat em HTTP; use ambiente protegido do serviço.

Rotas autenticadas: `POST /images/intent`, `GET /images/status`,
`POST /images/generate`, `POST /images/edit` e `GET /images/files/{id}`.
Upload limitado a 12 MiB; arquivos com IDs aleatórios e permissões privadas.

## Ferramentas e execução

Catálogo inclui `images.generate`, `images.edit` e `developer.propose`.
Execução por `/tools/execute` exige login e tem `dry_run=true` por padrão.
Falhas de execução produzem eventos na auditoria sem o conteúdo dos prompts.

## Autoedição em branch com Pull Request

`POST /agent/improve` aceita a descrição do problema. Por padrão, apenas
simula a preparação. Para publicar correção, o proprietário precisa ativar
`MENOR_AUTODEV_ENABLED=1` e configurar `MENOR_GITHUB_TOKEN` com permissões
restritas de Contents Write e Pull Requests Write no repositório do Menor.
Sem isso, o serviço não cria PRs automaticamente.
O fluxo lê um dos arquivos previamente autorizados na main, pede sugestão ao
Qwen, valida tamanho/sintaxe e cria branch com commit e PR **rascunho**.
Não executa o patch no servidor, não altera a main nem faz auto-merge.
A validação estática é parcial e NÃO substitui revisão humana e CI.
`GET /agent/improve/status` mostra se o opt-in está ativo sem revelar segredos.

## Pendências explícitas do plano completo

- Motor local de imagens e reconhecimento visual da foto pelo modelo.
- Ferramentas completas de web, voz, sandbox de código e operações Git mais amplas.
- Backup/restauração e rollback transacional de deploy.
- Monitoramento proativo agendado e redução de duplicações em ações externas.
- Validação do comportamento e desempenho do Qwen no notebook real.
