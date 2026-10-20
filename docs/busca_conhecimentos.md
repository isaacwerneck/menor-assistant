# Busca e gestão de conhecimentos (Menor v0.4 — incremento da Fase 2)

O Menor mantém **Markdown como fonte de verdade** e usa um índice local
`SQLite FTS5` em `~/menor-data/cerebro/memoria/indice.sqlite`.
O banco é reconstruído automaticamente quando o arquivo de aprendizados muda.

## Fluxo na conversa

1. Você ensina uma informação e o Menor a registra em
   `conhecimentos/aprendizados_gerais.md` (pela função de memória já existente).
2. Quando um assunto voltar, o backend busca no índice textual os até
   **três** trechos mais pertinentes à mensagem atual.
3. Somente esses trechos, com indicação de arquivo e linha, são enviados
   como **dados não confiáveis** ao Qwen. Nunca devem ser tratados como
   instruções que sobrepõem as regras de segurança.
4. Se não houver resultado, a resposta segue como antes, sem contexto extra.

## Editar e excluir pelo celular

Abra o Menor no Wi-Fi privado e entre com a senha do proprietário.
Na barra superior, toque no ícone de **cérebro** para visualizar conhecimentos.

- **Pesquisar:** digite um termo e veja resultados do índice (somente leitura).
- **Mostrar todos:** lista até os 100 registros mais recentes.
- **Editar:** corrija uma anotação salva (não altera outras notas).
- **Excluir:** confirme a remoção de um conhecimento da lista.

A interface só permite alterar a nota de conhecimentos gerais.
Para evitar sobrescrever mudanças de outro navegador, cada item usa um ID
derivado da linha atual e seu conteúdo; caso ela tenha mudado, a operação
retorna conflito e solicita atualização da lista.

APIs (todas exigem sessão do dono):
`GET /memory/knowledge`,
`POST /memory/search`,
`POST /memory/knowledge/edit`,
`POST /memory/knowledge/delete`.

## Limitações honestas

- A busca **ainda é textual** (palavras/tokens com tolerância a acentos).
  Sinônimos sem termos em comum podem não ser encontrados;
  embeddings locais e recuperação semântica real ficam para outra etapa.
- O índice cobre **aprendizados gerais**, não todas as pastas de projetos,
  propostas de ferramentas ou histórico de conversas.
- A detecção de intenção pelo Ollama continua independente da busca de memória
  e tem sua própria latência. Nesta etapa a busca SQLite não requer outra
  inferência do modelo.
- Erros na pesquisa não devem derrubar o chat: ele prossegue sem contexto
  recuperado e registra o problema nos logs.
- O índice SQLite é um cache: mantenha backup **principalmente do Markdown**
  e demais dados de `menor-data/`. A versão atual ainda não tem rollback
  automático de deploy.
- Evite salvar segredos e informações sensíveis; o acesso continua destinado
  a uma rede doméstica confiável ou VPN.

## Pesquisa web e estudos por assunto

O núcleo e os endpoints de chat compartilham `src.agent.research`. Pedidos explícitos
de pesquisa/estudo são tratados antes da conversa comum. Com
`MENOR_AUTONOMY_ENABLED=1`, um passo adicional do Ollama decide se precisa consultar
a web; esta inferência pode errar e aumenta a latência. O modelo atual não foi
substituído ou treinado novamente.

Fluxo: consulta pública → até cinco resultados candidatos → até três páginas legíveis →
síntese de até três afirmações → verificação dos trechos e URLs →
resposta com fontes ou reconhecimento de insuficiência. Informações da internet
são dados não confiáveis e não autorizam comandos, escrita em produção ou código.

Um pedido explícito de `estude`/`aprenda`, classificado como estudo para registro,
salva a pesquisa em
`conhecimentos/programacao/estudo-<hash-da-consulta>.md` para assuntos de programação,
ou `conhecimentos/pesquisas/` nos demais casos. Uma nova pesquisa com a mesma consulta
atualiza essa nota. Fonte, consulta, trecho e limitações permanecem no Markdown.
O índice FTS inclui essas notas (até 200 fontes no total) e remove entradas quando
a nota é excluída do disco. A gestão pelo painel ainda edita somente aprendizados gerais.
As notas de estudo precisam ser geridas no disco; mantenha backup do cérebro.
A simples presença de “estude” em uma negação ou citação não basta para gravar:
o planejador também precisa declarar `study=true` como booleano. Uma proibição
de salvar deve produzir `study=false`. Essa classificação ainda pode errar;
não é garantia formal de interpretação da intenção.

A leitura aceita HTTPS público, porta 443, sem credenciais. Cada resolução DNS
é verificada e a conexão fixa o IP verificado, mantendo validação TLS do hostname.
Endereços privados, loopback e link-local são recusados; redirecionamentos também
são verificados. Há limites de resposta (1 MiB), texto (12000 caracteres) e tempo.

`web.browse` usa Playwright/Chromium opcional em contexto descartável. Não reutiliza
cookies do proprietário, não aceita downloads e bloqueia WebSockets/service workers.
O tráfego da página é intermediado pelo mesmo leitor público; páginas que dependem
de recursos não suportados podem falhar. Nenhum CAPTCHA é contornado.
A busca usa HTML público do DuckDuckGo e, em falha, o feed RSS público do Bing.
Ambos podem falhar por bloqueio ou mudança de formato.
Uma fonte recusada é registrada como falha parcial; a leitura tenta o próximo
candidato, até cinco candidatos e três páginas legíveis. Sem fontes legíveis, há abstenção.

### Contexto e diagnóstico da pesquisa (segunda avaliação, 19/10/2026)

O planejador de busca usa schema com `action`, `query` e `study`, com teto de
180 tokens de saída. A síntese mantém seu teto independente de 900 tokens.
Esse limite reduz geração desnecessária; não é medição de velocidade real.

`web.read(url, query=consulta)` seleciona trechos literais relevantes do texto
completo obtido, antes do antigo corte dos primeiros 12.000 caracteres.
Sem query, a interface anterior continua retornando o início da página.
A pesquisa envia no máximo 2.400 caracteres de texto por fonte, até 7.200
no total, inclusive se usar o navegador opcional. A seleção usa sobreposição
de termos, preserva a ordem dos trechos e marca omissões; pode perder sinônimos,
contexto ou fronteiras de frases. Uma citação precisa existir dentro de um
único trecho: o marcador de omissão não é evidência.

Falhas passam a distinguir `failure_stage=search` (buscadores), `read`
(páginas ilegíveis) e `synthesis` (resposta/citações não validadas). O texto
exibido informa a etapa sem devolver exceções ou dados privados. A ausência
de afirmações sustentadas continua sendo insuficiência de evidência, sem
salvar estudo ou inventar conteúdo. Nenhum novo provedor, dependência ou
modelo foi adicionado.

Limites: checar a existência da citação não prova que a frase sintetizada decorre
dela. A seleção de autoridade, confirmação entre fontes, revisão de versões e
busca iterativa ainda exigem evolução e avaliação real. Estudar não executa exemplos,
não instala ferramentas e não altera os pesos do modelo. Não há estudo agendado
ou infinito. A pesquisa envia a consulta ao buscador; não inclua segredos nos pedidos.

## Testes

O CI executa testes de busca, sincronização após edição direta do Markdown,
remoção, proteção contra caminhos indevidos, API autenticada e interface.
O aceite funcional final depende de testar o comportamento do modelo no servidor.
