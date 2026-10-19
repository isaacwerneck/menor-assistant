# Chat D — continuidade da conversa com imagens (v1)

## Sintomas reproduzidos

Prints de outubro/2026: pedido natural de imagem desviava para aprovação de
`images.generate`, resposta livre ao consentimento era tratada como não aprovação
e, depois do comprovante de geração, a conversa genérica negava conseguir
produzir imagens. Uma correção de atributos do cachorro era replanejada como
outra imagem, sem reaproveitar o resultado anterior.

## Escopo isolado

- Somente `src/api/templates/chat.html`, `tests/test_ui.js` e este documento.
- Não modifica `src/agent/runner.py`, `src/agent/intelligence.py`,
  `src/agent/approval.py`, `src/tools/`, `ops/` nem `src/api/main.py`.
- Chat A continua responsável por decisões gerais, permissões e memória;
  Chat B pelas implementações de geração/edição e processamento especializado;
  Chat C por testes de operação e segurança da API.
- Nenhum bypass de permissão de instalação, Git, exclusão ou outros recursos:
  somente a API de imagem já disponibilizada recebe pedido direto de imagem.

## Fluxo

1. O navegador reconhece **pedido explícito de imagem** (inclusive "img") e
   consulta `/images/intent` antes do agente geral. A rota da API continua a
   validar o pedido, a autenticação e a disponibilidade.
2. A geração usa `/images/generate`, com `session_id`, sem passar por
   `images.generate` como escrita genérica que exige dupla confirmação.
3. Uma solicitação para **mostrar novamente** a imagem exibe o URL da última
   imagem realmente entregue pelo servidor nessa conversa, sem chamar o modelo
   genérico nem fabricar comprovante.
4. Uma solicitação de **corrigir ou ajustar** a imagem recente reutiliza o PNG
   pela rota autenticada `GET /images/files/<id>`, enviando-o como upload
   para `POST /images/edit`. Nunca carrega endereços arbitrários fornecidos
   pelo usuário, um modelo ou páginas externas.
5. Pedidos de desenvolver *ferramenta* de imagens e ações que exigem autorização
   continuam sob o fluxo do agente geral.

## Limitações e responsabilidade

- O roteamento de imagens é um primeiro estágio heurístico na interface;
  não substitui o planejamento semântico do Chat A.
- A correspondência visual do cachorro (patas, idade, cores) não foi provada:
  a geração e edição precisam de revisão visual humana ou de modelo específico.
- A melhoria é por conversa no navegador; a sincronização durável de artefatos
  entre aparelhos e a política abrangente de confirmação pertencem a outras
  etapas de arquitetura.
- A imagem anterior só é reutilizada se o navegador a reconhece como URL
  `/images/files/<uuid-hex>` armazenada na própria conversa.
- Se o arquivo anterior não estiver acessível, a edição falha sem alterar a
  imagem original, e a interface solicita que o usuário o anexe.
- O backend permanece responsável por autenticação e validação; o cliente
  não adiciona privilégios.

## Verificação

```sh
node --test tests/test_ui.js
python3 -m unittest discover -s tests
```

Regressões: "img" com linguagem informal, reexibir o resultado gerado, edição
contextual de imagem recente, não sequestrar criação de ferramentas e não
confundir um "eu aprovo" isolado com pedido de edição.

Aprovação humana e CI são exigidas antes do merge em `main`.
