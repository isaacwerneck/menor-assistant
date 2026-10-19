# Chat E — E3: objetivos e missões com dados reais

## Entrega
- Página privada `/workspace/objectives` para desktop e celular, consistente com Quiet Intelligence.
- Objetivos de até oito conversas salvas no **navegador atual**, consultados por `GET /agent/runs/{session_id}`; estados `idle` não são apresentados como metas reais.
- Missões recentes do backend, consultadas por `GET /agent/missions`, com filtros de estado e passos presentes no plano.
- Sem porcentagens inventadas, datas calculadas, resultados artificiais, monitoramento em background ou endpoints de escrita.
- Erros e falta de autenticação aparecem explicitamente; respostas são renderizadas com `textContent`, nunca HTML vindo da API.

## Privacidade e segurança
As páginas e assets exigem sessão do proprietário antes de devolver qualquer recurso. CSP restringe scripts, estilos e chamadas à própria origem. A página não solicita credenciais, não chama SSH, não inicia missões e não altera aprovações.

## Limitações e próximos passos
Não existe endpoint de lista global de objetivos conversacionais no servidor. A página usa os identificadores válidos das conversas que o browser mantém; pode não encontrar estados de outros dispositivos. A disponibilidade de missão é um estado declarado, não prova de desempenho no hardware.

E4 adicionará navegação de sistema, imagens e ferramentas com estados reais; E5 será ponte de diagnóstico controlada. Aceite visual real no Ubuntu e Safari depende de teste no ambiente do usuário.
