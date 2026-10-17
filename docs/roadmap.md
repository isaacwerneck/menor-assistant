# Roadmap de Execução

## Fase 1: Sistema Operacional & Ambiente Base
- [x] Especificações definidas: i7-1185G7 (AVX-512) + 32 GB RAM.
- [ ] Liberar partição de 60-100 GB no Windows.
- [ ] Instalar Ubuntu Server 24.04 LTS (Dual Boot).
- [ ] Configurar `/etc/systemd/logind.conf` para notebook operar com tampa fechada.
- [ ] Ativar SSH e Tailscale para controle remoto a partir do PC principal e celular.

## Fase 2: Runtime de Inferência & Modelo Hugging Face
- [ ] Instalar Ollama / llama.cpp compilado com suporte AVX-512.
- [ ] Baixar modelo quantizado GGUF (recomendado: `Qwen 2.5 Coder 14B Q4_K_M` ou `7B`).
- [ ] Testar benchmark de geração de tokens/segundo em CPU.

## Fase 3: Servidor & Acesso Remoto
- [ ] Criar API base com FastAPI (endpoint `/chat` e `/health`).
- [ ] Configurar Tailscale no notebook, PC e celular para conexão segura.
- [ ] Criar interface web minimalista (Streamlit ou HTML/JS leve) para testes.

## Fase 4: Pipeline de Áudio (Voz Bidirecional)
- [ ] Integrar `faster-whisper` para transcrição de áudio do microfone.
- [ ] Integrar `piper-tts` para síntese de resposta em áudio.
- [ ] Implementar wake word local ("Jarvis").

## Fase 5: Gestor de Projetos & Memória Markdown
- [ ] Implementar sistema de leitura e escrita de arquivos `.md`.
- [ ] Criar estrutura de pastas: `/memoria`, `/projetos`, `/logs`.
- [ ] Adicionar embeddings locais para busca semântica em notas e documentações.

## Fase 6: Agente & Execução de Ferramentas
- [ ] Conectar ferramentas de execução de código (Python sandbox / subprocess).
- [ ] Adicionar ferramentas de suporte a Game Dev (organização de assets, design docs).
- [ ] Sistema de auto-reflexão: salvar logs de aprendizado diário em Markdown.
