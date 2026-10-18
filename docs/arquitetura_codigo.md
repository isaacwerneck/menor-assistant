# Arquitetura de Código & Organização do Menor

## Estado implementado

O runtime atual está em `src/api/main.py`, com FastAPI, Requests, Pydantic e
a interface HTML/JavaScript em `src/api/templates/chat.html`. As árvores e o
loop agêntico abaixo descrevem a arquitetura planejada, ainda não implementada.

### Chat com contexto

1. O navegador armazena conversas em `localStorage`. Ao enviar uma mensagem,
   seleciona até 20 mensagens anteriores, com orçamento conjunto de 32000
   caracteres incluindo a mensagem atual. Conteúdos anteriores maiores que
   8000 caracteres contribuem apenas com seus últimos 8000 caracteres.
2. Converte o papel visual `bot` em `assistant` e envia `message` e `history`
   ao `POST /chat/stream`. Clientes existentes podem continuar enviando somente
   `message` e, opcionalmente, `model`.
3. Pydantic rejeita mensagens vazias/brancas, mensagens acima de 8000 caracteres,
   histórico acima de 20 itens ou 32000 caracteres e papéis diferentes de
   `user`/`assistant`. O prompt de sistema é definido exclusivamente pela API.
4. A API chama [`POST /api/chat` do Ollama](https://docs.ollama.com/api/chat),
   enviando prompt de sistema, histórico e mensagem atual. Ambas as rotas usam
   o mesmo fluxo; `/chat` mantém a resposta JSON `reply`/`model` e
   `/chat/stream` mantém texto UTF-8 em streaming.
5. A conexão ao Ollama tem timeout de 5 segundos e a leitura de 120 segundos
   sem dados. Antes dos headers, falhas retornam 503 (conexão), 504 (timeout),
   404 (modelo ausente) ou 502 (falha/resposta inválida).
   Após iniciar o stream, falhas ou ausência de conclusão interrompem a
   transferência. O navegador mostra o erro e não salva uma resposta incompleta.

O histórico não vira memória global: não há sincronização entre navegadores
nem arquivos Markdown no servidor. O botão de exportar baixa a conversa atual
em `.md` usando recursos nativos do navegador.

### Interface e persistência

O status consulta `/health` ao abrir e a cada 30 segundos, exibindo o modelo
configurado e o estado do Ollama. A barra lateral fecha ao iniciar/abrir uma
conversa no celular; botões têm nomes acessíveis e foco visível, e animações
respeitam a preferência por movimento reduzido.

Durante uma resposta, iniciar, abrir ou excluir outra conversa fica bloqueado
para manter a resposta vinculada à conversa original. Uma nova conversa limpa
a área de mensagens anteriores. A decodificação preserva caracteres UTF-8
divididos entre chunks.

Falhas ao salvar aparecem em aviso separado do status de conexão. JSON inválido
ou estruturas/IDs inválidos no armazenamento não derrubam a página nem são
sobrescritos: novas conversas ficam apenas na memória e podem ser exportadas.

### Configuração e operação

Sem alterar código, o processo aceita `OLLAMA_URL` (padrão
`http://127.0.0.1:11434`), `OLLAMA_MODEL` (padrão `qwen2.5-coder:7b`) e
`OLLAMA_KEEP_ALIVE` (padrão `24h`). No systemd, podem ser definidos em
`~/.config/menor/environment`, fora do repositório, com uma atribuição por linha.
Depois, execute `systemctl --user restart menor-api.service`.

O deploy usa `scripts/deploy.sh` e os units em `deploy/systemd/`; veja o
[guia de operação e recuperação](guia_servidor_domestico.md#deploy-automático-do-menor).
Testes Python usam `unittest` e mocks do Ollama, sem exigir inferência real.
Testes da interface usam o test runner nativo do Node já disponível no ambiente
de desenvolvimento/CI, sem pacote npm nem dependência de Node no servidor.
Os testes Bash usam repositórios descartáveis, sem alterar a aplicação real.

## Arquitetura planejada

Como o código do Jarvis é estruturado, como o fluxo de dados acontece e como a IA interage com o sistema de arquivos.

---

## 📂 Estrutura de Pastas do Projeto

```text
menor/
├── docker-compose.yml           # Orquestração do banco, IA e túnel de rede
├── pyproject.toml / reqs.txt    # Dependências do Python
├── config/
│   └── settings.yaml            # Portas, caminhos de áudio e chaves
├── data/
│   ├── memoria/                 # Markdown com histórico e perfil do usuário
│   │   ├── usuario_perfil.md
│   │   └── aprendizados.md
│   ├── projetos/                # Pastas de projetos gerenciadas pela IA
│   └── vectordb/                # Banco vetorial para busca semântica (ChromaDB)
└── src/
    ├── api/                     # Servidor FastAPI e WebSockets
    │   ├── main.py              # Ponto de entrada da API
    │   └── rotas_chat.py
    ├── audio/                   # Pipeline de áudio bidirecional
    │   ├── stt_whisper.py       # Microfone -> Texto
    │   └── tts_piper.py         # Texto -> Alto-falante
    ├── brain/                   # Comunicação com o modelo de linguagem
    │   ├── client_llm.py        # Chamadas para Ollama / llama.cpp
    │   └── prompts.py           # System prompts e identidade do Jarvis
    ├── memory/                  # Gerenciador de memória e Markdown
    │   ├── markdown_manager.py  # Leitura e escrita de arquivos .md
    │   └── retriever.py         # Busca semântica de contexto anterior
    └── tools/                   # Habilidades executáveis do Jarvis
        ├── file_tools.py        # Criar, ler e editar arquivos
        ├── terminal_tools.py    # Executar comandos bash controlados
        └── code_sandbox.py      # Executar e testar scripts Python
```

---

## 🔄 Fluxo de Uma Interação (Loop Agêntico)

1. **Entrada**: Você fala no microfone do celular ou notebook.
2. **Transcrição (STT)**: O `faster-whisper` converte o áudio em texto em ~300ms.
3. **Injeção de Contexto (RAG)**: O gerenciador de memória busca notas relevantes em `data/memoria/` e anexa ao prompt.
4. **Raciocínio & Ferramentas**:
   * O LLM recebe a mensagem e decide se responde direto ou invoca uma ferramenta.
   * Se você pediu *"crie um documento do meu novo jogo"*, ele emite um comando estruturado JSON:
     ```json
     {
       "acao": "escrever_arquivo",
       "parametros": {
         "caminho": "data/projetos/jogo_rpg/game_design.md",
         "conteudo": "# Game Design Document\n..."
       }
     }
     ```
5. **Execução**: O módulo `file_tools.py` cria o arquivo no disco.
6. **Resposta Final**: O LLM confirma a ação e o `piper-tts` envia o áudio sintetizado para sua caixa de som.

---

## 🧬 Como Funciona o Auto-Aprimoramento (Self-Improvement)

A IA não recompila os próprios pesos da rede neural; em vez disso, ela utiliza o **Padrão de Reflexão (Agentic Reflection)**:

* **Detecção de Falha**: Ao rodar um script ou tentar executar uma tarefa que deu erro, ela captura o `stderr`.
* **Análise de Causa**: O modelo gera uma explicação do porquê o código falhou.
* **Persistência de Lições**: A IA grava a correção em `data/memoria/aprendizados.md` (ex: *"Quando rodar script X no Ubuntu, usar flag Y"*).
* **Criação de Novas Ferramentas**: Se a IA percebe que faz uma tarefa repetitiva, ela pode escrever um novo script Python dentro de `src/tools/` para expandir suas próprias capacidades.
