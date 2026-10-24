# Chat E — Workspace de arquivos (E2)

## Objetivo

Unificar a interface privada `/files/view` com a identidade **Quiet Intelligence** do Menor AI, usando a estrutura aprovada para desktop e iPhone. Esta entrega é **somente visual**: não cria novos endpoints, arquivos fictícios, capacidades de visão ou status de modelos.

## Telas e comportamento entregues

- Identidade grafite com acentos roxos suaves, contornos discretos e glass moderado apenas na barra superior.
- Desktop: navegação lateral real (Conversas e Arquivos), topo contextual, composição em painel principal e coluna de informações.
- Mobile: navegação inferior leve, compositor de consulta e painéis adaptáveis, áreas seguras do Safari, controles touch, foco de teclado.
- Sequência de trabalho preservada: 01 Enviar arquivo; 02 Consultar conteúdo; 03 Resultado.
- Todos os IDs de `assets.js` foram preservados; análise, upload, exclusão, OCR e visão seguem ligados aos mesmos endpoints autenticados.
- Nenhum valor inventado de disponibilidade da CPU, Ollama ou resultado dos parsers; os estados continuam preenchidos pelo JavaScript original e retornos reais da API.
- A tela continua sob a política CSP original `default-src 'none'`, `style-src 'self'`, `script-src 'self'`, `connect-src 'self'`, sem CSS remoto nem scripts inline.

## Arquivos modificados

- `src/tools/file_analysis/templates/files.html`
- `src/tools/file_analysis/templates/assets.css`
- `tests/test_chat_e_file_workspace.py`

Não modificar `src/tools/file_analysis/templates/assets.js` nem `src/tools/file_analysis/api.py`; ambos pertencem ao Chat B. Não modificar o orquestrador do Chat A, observabilidade do Chat C ou interpretação de mensagens do Chat D.

## Testes e aceite

- CI executa Python, JavaScript, Flake8 e scripts de deploy em ambiente isolado.
- Teste do Chat E verifica IDs, acessibilidade, CSP compatível, comportamento de desabilitar controles e ausência de serviços externos.
- Testes existentes do Chat B verificam autenticação da página, CSS e JavaScript e APIs de upload/análise/visão/OCR.
- Aceite visual em Safari iPhone e navegador desktop no servidor ainda depende de inspeção manual; passar CI não confirma responsividade com teclado real.

## Próximas entregas

- E3: painel de objetivos e tarefas com estados verdadeiros via API.
- E4: estados reais de sistema, imagens e ferramentas.
- E5: ponte de diagnóstico estritamente autorizada, dependente de setup operacional e testes no Ubuntu.
- E6: auditoria de acessibilidade e aparência real em dispositivos.
