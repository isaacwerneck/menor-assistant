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
- [x] Criar ambiente virtual Python (`.venv`) no repositório `~/menor-assistant` (diretório confirmado via SSH).
- [x] Criar API base com FastAPI conectando diretamente ao Ollama.
- [ ] Configurar Tailscale no notebook, PC e celular para conexão segura fora de casa.
- [x] Criar interface web/chat para testes pelo navegador.
- [x] Enviar histórico recente ao modelo e validar mensagens/contexto.
- [x] Tratar indisponibilidade, timeout e falhas no streaming.
- [x] Adicionar status de conexão, exportação Markdown e refinamentos para celular/teclado.
- [x] Implementar deploy por consulta periódica à main, serviços systemd e testes no GitHub Actions.
- [ ] Ativar os serviços no servidor e habilitar linger; SSH deixou de responder antes da instalação.

A API e a interface foram verificadas localmente com Ollama simulado nos testes.
Inferência real, instalação dos serviços e continuidade após reboot ainda exigem
validação no servidor. Instruções em [guia do servidor](guia_servidor_domestico.md#deploy-automático-do-menor).

## Fase 4: Pipeline de Áudio (Voz Bidirecional)
- [ ] Integrar `faster-whisper` para transcrição de áudio do microfone.
- [ ] Integrar `piper-tts` para síntese de resposta em áudio.
- [ ] Implementar wake word local ("Jarvis").

## Fase 5: Gestor de Projetos & Memória Markdown
- [x] Exportar a conversa atual do navegador em Markdown (não é memória persistente no servidor).
- [ ] Implementar sistema de leitura e escrita de arquivos `.md`.
- [ ] Criar estrutura de pastas: `/memoria`, `/projetos`, `/logs`.
- [ ] Adicionar embeddings locais para busca semântica em notas e documentações.

## Fase 6: Agente & Execução de Ferramentas
- [ ] Conectar ferramentas de execução de código (Python sandbox / subprocess).
- [ ] Adicionar ferramentas de suporte a Game Dev (organização de assets, design docs).
- [ ] Sistema de auto-reflexão: salvar logs de aprendizado diário em Markdown.
