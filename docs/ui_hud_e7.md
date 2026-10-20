# Revisão E7 — HUD e interações (20/10/2026)

O design **Quiet Intelligence** é mantido; não há mudanças em inferência,
tokens, autenticação, armazenamento ou autorização do agente.

## Entrega

- Chat: topbar em grupos, atalhos e menu contextual, sidebar organizada por
  trabalho/personalização e com acesso a Sistema. No celular, a sidebar tem
  fechamento por clique fora ou Escape, e a navegação inferior usa cinco opções.
- Compositor: botões com 44px de área tocável, estados de conexão com origem
  da API, informações de anexo e processamento agrupadas, envio e parada
  sem competição por espaço durante uma geração.
- Ações destrutivas: excluir conversa do navegador requer confirmação explícita.
- Lab: navegação entre seções, dois resultados lado a lado no desktop,
  cartões de baterias alinhados, pesquisa rotulada, barra de seleção e
  execução sequencial destacada; IDs de ações e APIs preservados.
- Workspaces de objetivos, arquivos e sistema: navegação cruzada e
  consistência de targets/foco/feedback, sem criar rotas novas.

## Validação

CI Python/Node/shell e testes sintéticos verificam compatibilidade estrutural e
funcional. Ao religar o Ubuntu, conferir visualmente no iPhone Safari e no
desktop: teclado e safe areas, foco/Escape, modal sobre menu, listas extensas,
seleção de testes, streaming, anexos e estados de falha. O CI sozinho
não comprova a qualidade do layout renderizado em dispositivos reais.
