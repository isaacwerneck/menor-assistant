# Roadmap de Execução

## Fase 1: Sistema Operacional & Ambiente Base
- [x] Especificações definidas: i7-1185G7 (AVX-512) + 32 GB RAM.
- [x] Liberar partição no Windows (116 GB livres identificados).
- [x] Instalar Ubuntu Server 24.04 LTS (Dual Boot concluído).
- [x] SSH configurado e conectado com sucesso (`isaac@nakedrift`).
- [x] Configuração de suspensão desativada (notebook opera fechado 24/7).
- [x] Ferramentas essenciais instaladas (`git`, `curl`, `ffmpeg`, `python3-pip`, `python3-venv`).

## Fase 2: Runtime de Inferência & Modelo Hugging Face
- [x] Instalar Ollama com suporte AVX-512.
- [x] Baixar modelo local `qwen2.5-coder:7b` (inferência operando em CPU).
- [x] Primeiro teste de geração e chat validado via terminal.

## Fase 3: Servidor & Acesso Remoto
- [ ] Criar ambiente virtual Python (`.venv`) no repositório `~/menor-assistant`.
- [ ] Criar API base com FastAPI conectando diretamente ao Ollama.
- [ ] Configurar Tailscale no notebook, PC e celular para conexão segura fora de casa.
- [ ] Criar interface web/chat para testes pelo navegador.

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
