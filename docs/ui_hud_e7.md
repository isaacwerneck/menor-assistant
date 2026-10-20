# E7 — UX do chat, HUD e workspaces

Atualização visual **Quiet Intelligence**, sem mudanças de inferência ou
permissões, preparada para avaliação mesmo quando o Ollama está desligado.

## Melhorias implementadas
- Cabeçalho com nome da conversa e ações separadas; áreas de toque de 44px.
- Menu lateral com separação entre espaços de trabalho e personalização,
  rota de Sistema, controle de abertura e fechamento no celular por overlay,
  Escape ou navegação; controle `aria-expanded` e menu `inert` ao fechar.
- Compositor compacto com anexos, enviar/parar e estado de conexão organizado.
- Confirmação antes de apagar uma conversa do histórico do navegador.
- Lab com navegação por seções, resultados em colunas responsivas,
  baterias em grade, busca e barra de seleção/execução legível.
- Links entre Conversas, Objetivos, Arquivos, Laboratório e Sistema
  consistentes em desktop e mobile; botões com foco e feedback visual.

## Validação
Verificações sintéticas no GitHub Actions de Python, Node e shell. Testes Node
específicos para navegação inicialmente fechada no mobile, confirmação de
exclusão e preservação dos controles. Não equivale a comprovação de layout
visual no Safari/desktop reais.

## Aceite operacional quando o Ubuntu ligar
1. Confirmar deploy do SHA integrado e abrir em iPhone + PC.
2. Testar menu com botão, fundo, Escape e mudança de tela.
3. Enviar mensagem e anexar arquivo; confirmar ausência de sobreposição
   entre `Enviar` e `Parar`, inclusive com teclado virtual aberto.
4. Confirmar teste individual e fila de baterias, histórico, foco e scroll.
5. Corrigir eventuais diferenças de viewport antes de encerrar a entrega.

Nenhum endpoint ou ferramenta adicional é implicitamente habilitado.
