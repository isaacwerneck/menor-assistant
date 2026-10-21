# Programação colaborativa no Menor — E9

A conversa de programação **não executa código por si só**. Quando a pessoa pede
para criar um jogo ou aplicativo, o Menor pode discutir requisitos e escrever
trechos no chat sem inventar uma chamada de ferramenta.

## Gerar arquivo real dentro de projeto existente

1. Primeiro crie um projeto no Menor com a ferramenta `projects.create`
   (exige aprovação). Isso cria um projeto e a pasta privada `arquivos/`.
2. Solicite **um arquivo específico** no projeto (nome válido como `index.html`,
   `game.js`, `style.css`, `main.py`), com uma descrição de 12–280 caracteres.
3. O modelo pode selecionar `projects.code.create`; o backend valida
   `slug`, `filename`, projeto existente e ausência de arquivo no destino
   antes de oferecer **Aprovar / Explicar / Cancelar**.
4. A geração e escrita ocorrem **somente após a aprovação específica**.
   O conteúdo é salvo em `MENOR_DATA_DIR/cerebro/projetos/<slug>/arquivos/<filename>`.
   O recibo retorna caminho, bytes e SHA-256, além de `tested=false` e
   `executed=false`. O código não é executado nem apresentado como testado.
5. Para HTML/JS/CSS, revise os arquivos antes de abri-los no navegador; eles
   podem conter código inseguro ou erro do modelo. Não é servido preview
   automático nem permitido sobrescrever um arquivo existente.

### Limites de segurança e produto

- Sem caminhos absolutos, subdiretórios, links simbólicos ou extensão executável
  arbitrária; permitido somente `.html`, `.js`, `.css`, `.py` e `.md`.
- O modelo só fornece o **conteúdo**; não escolhe o caminho real de escrita.
- Nenhuma ferramenta de shell, execução Python/Node, deploy ou instalação foi
  liberada por essa implementação.
- Arquivo no disco não prova qualidade, segurança ou funcionamento. O usuário
  ainda precisa revisar, testar em ambiente seguro e solicitar alterações em
  novos arquivos sem sobrescrever. A edição de código existente, testes de
  aplicativos inteiros e execução de projetos ficam para uma fase supervisionada
  posterior com sandbox e proteção de dados.
- No exemplo Snake em JavaScript com Raylib, confirmar a integração/runtime
  antes de gerar dependências. Para browser sem dependências, Canvas é uma
  alternativa, mas não deve ser substituído sem escolha do usuário.

### Verificação

`python -m unittest tests.test_code_workspace tests.test_conversation_flow`
(ou `discover -s tests`), Flake8, Node UI, shell e deploy checks no CI.

Testes de CI usam Ollama simulado e diretório temporário. O comportamento
e a qualidade do código gerado ainda precisam ser testados no Ubuntu com o
modelo instalado; não existe execução remota comprovada.
