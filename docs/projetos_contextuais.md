# Projetos e memória por conversa — Fase 3 (incremento)

## Como funciona no celular

O Menor mantém projetos em `~/menor-data/cerebro/projetos/`, fora do Git.
Ao criar um projeto com nome definido, a estrutura real recebe
`contexto.md`, `decisoes.md`, `tarefas.md`, `diario.md` e `arquivos/`.

No chat, um usuário pode dizer:

> Tive uma ideia de uma ferramenta que ajuda a criar sprites.

Se ainda não for claro se deve guardar, o Menor pergunta **na conversa**:
"Quer que eu registre? Em conhecimentos, projetos ou ferramentas?"

O usuário responde naturalmente:
> Sim, coloca na pasta de ferramentas.

O Menor interpreta a resposta usando o modelo local, verifica o destino no
backend, salva somente o texto originalmente discutido e informa onde gravou.
Não há modal com opções grandes nem necessidade de decorar comandos.
"Não, deixa" cancela a anotação; se ainda houver dúvida, o Menor pergunta de novo.

## Trabalhando num projeto existente

O seletor compacto **Projetos**, no topo do chat, permite vincular a conversa
a um projeto existente. Esse vínculo é salvo com a conversa no navegador, de
modo que outras conversas não recebem contexto de projetos diferentes.

Também é possível dizer na conversa "Vamos continuar no projeto Cidade Noturna".
Quando o nome coincide com um projeto existente, o Menor o seleciona
automaticamente, sem exigir um botão. Se não encontrar, pergunta qual projeto
você deseja abrir.

Depois de selecionar um projeto, o Menor passa a recuperar, dentro de um
orçamento de contexto, o objetivo, decisões recentes, tarefas e diário.
As notas são apresentadas ao Qwen como **dados**, não como novas instruções
de sistema.

Exemplo:
> Já decidimos usar Godot. Registra isso no projeto.

Com projeto ativo e interpretação suficientemente clara, o backend adiciona
a decisão ao `decisoes.md` do projeto **selecionado**. O fluxo também aceita
registrar tarefas e notas de progresso. Se a intenção ou o destino forem
incertos, o Menor pergunta antes de escrever.

Para consulta e manutenção, o painel de projetos oferece leitura e
anotações manuais. Essa interface administrativa é complementar ao diálogo.

## Limites e segurança

- Toda gravação exige uma sessão autenticada.
- O Qwen sugere a intenção/destino, mas não recebe permissão para escolher
  caminhos arbitrários nem executar comandos do sistema.
- Uma resposta incerta nunca gera gravação automática.
- O diálogo pendente fica vinculado à conversa no navegador; ao trocar de
  conversa, não se perde a pergunta do Menor.
- O serviço não inventa ferramenta executável quando registra uma proposta.
- Não há acesso remoto à internet sem VPN/TLS nem execução de shell nesta etapa.
- Exportar, arquivar e consultar projetos em outros dispositivos ainda
  exigirão entregas posteriores.
- O modelo pode classificar incorretamente frases ambíguas; a atualização
  ainda requer validação funcional com Ollama rodando no servidor real.

## Verificação

Os testes automatizados cobrem separação de contextos, integridade dos caminhos,
anotações e interpretação de respostas após perguntas do Menor. O GitHub Actions
precisa ficar verde antes do merge. Nenhum `git pull` é necessário se o timer
de deploy estiver ativo no servidor.
