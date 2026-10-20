# Roadmap de Execução

> **Checklist de instalação inicial (histórico 18–19/10/2026).**
> Para o estado corrente, progresso ~60% estimado da missão total, frentes
> A–E e evidências reais, consulte [handoff para Codex](handoff/00_COMECE_AQUI_CODEX.md).
> Este checklist não substitui o plano integrado nem comprova entrega completa.

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
- [x] Ativar os serviços no servidor e habilitar linger; confirmados via SSH em 18/10/2026.

A suíte Python foi validada no Ubuntu com dados isolados e Ollama indisponível;
a interface passou nos testes Node e no fluxo real de missão pelo navegador.
Serviços habilitados e linger foram confirmados. Desempenho de inferência real e
continuidade após reboot ainda exigem validação no servidor. Instruções em [guia do servidor](guia_servidor_domestico.md#deploy-automático-do-menor).

## Fase 4: Pipeline de Áudio (Voz Bidirecional)
- [ ] Integrar `faster-whisper` para transcrição de áudio do microfone.
- [ ] Integrar `piper-tts` para síntese de resposta em áudio.
- [ ] Implementar wake word local ("Jarvis").

## Fase 5: Gestor de Projetos & Memória Markdown
- [x] Exportar a conversa atual do navegador em Markdown (não é memória persistente no servidor).
- [x] Implementar componentes de leitura/escrita de memória Markdown (base integrada; validar uso real).
- [x] Criar estrutura privada de memória/projetos/logs fora do Git (veja `src/memory/store.py`).
- [ ] Confirmar em produção o funcionamento da busca semântica/embeddings **opcionais** já previstos no código.

## Fase 6: Agente & Execução de Ferramentas
- [x] Integrar catálogo tipado, aprovação e recibos para ferramentas supervisionadas (escopo parcial).
- [ ] Conectar ferramentas de execução de código (Python sandbox / subprocess).
- [ ] Adicionar ferramentas de suporte a Game Dev (organização de assets, design docs).
- [ ] Sistema de auto-reflexão: salvar logs de aprendizado diário em Markdown.
