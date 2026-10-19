# Chat E E4 — Painel de sistema, modelos e ferramentas

## Escopo entregue
Rota privada `/workspace/system` com consulta exclusivamente GET a `/health`, `/models`, `/images/status`, `/agent/skills` e `/tools`. Visual Quiet Intelligence responsivo em PC e iPhone. Nenhum componente executa tarefas, modifica modelos ou emite comandos.

## Precisão dos estados
- API: status e versão **reportados pelo processo HTTP**, não confirmação da revisão implantada.
- Ollama: conectividade conforme `/health`, não benchmark de geração.
- Modelos: lista reportada por `/models` (não testa se carregam ou respondem adequadamente).
- Imagens: configuração e prontidão declaradas pelas rotas existentes (não prova semântica).
- Skills: `ready` do catálogo de capacidades, sem inventar resultados.
- Ferramentas: catálogo registrado, **não** declaração de execução nem disponibilidade comprovada.
- Deploy, CPU, RAM e systemd: explicitamente **sem telemetria** nesta entrega. Futuramente consumir contrato do Chat C com origem e data verificáveis.

## Segurança
Autenticação do proprietário no documento e nos assets, `Cache-Control: private, no-store`, CSP estrita sem scripts inline, sem recursos externos. `fetch` apenas `GET` mesmas origens, com expiração de sessão visível. Informações do backend rendem sempre `textContent` e nunca código ou HTML. Nada de credenciais, SSH público, terminal ou acesso administrativo.

## Próximo
Disponibilizar navegação a partir do chat sem duplicar links de E3; consolidar estilos compartilhados e rever acessibilidade. A futura ponte E5 exigirá canal remoto autenticado real e testes no notebook; o painel não equivale a conexão do ChatGPT com o servidor.
