# Chat C — Contratos operacionais da API (v2)

Este incremento adiciona **testes de leitura**, sem alterar rotas ou ferramentas do Menor.
Trabalha somente com arquivos `ops/`, `tests/test_ops_*` e este documento.

## Testes no servidor

Na raiz do checkout atualizado do Menor, usando Python 3.10+:

```bash
python3 -m ops.smoke
python3 -m ops.smoke --json
python3 -m ops.smoke --port 8000 --timeout 2
```

A ferramenta consulta exclusivamente `127.0.0.1` e nunca usa cookies,
tokens, login ou headers de autenticação. Todos os pedidos são **GET**.
Não há upload, upload de artefato, download de modelos, reinício, alteração
de configuração nem execução de tarefas.

1. Valida os campos essenciais de `/health`, incluindo versão do contrato,
   versão do software e status declarado do Ollama. `offline` é permitido:
   é o `ops.doctor` que distingue a saúde operacional do Ollama.
2. Confere se endpoints privados retornam **401 ou 403** para uma chamada
   sem sessão, incluindo ferramentas, feedback, missões, tarefas, imagens,
   arquivos e memória.
3. Nunca lê o corpo das respostas de endpoints privados. A resposta pública
   de `/health` é limitada a 8 KiB, sem seguir redirects HTTP.
4. Oculta mensagens de exceções e corpos HTTP no relatório. JSON exibe apenas
   nome, estado e descrição estática do check, sem informações pessoais.

O código de saída é 0 para sucesso e 2 para falha crítica. Se `/health`
falhar, as demais verificações são marcadas `skipped` para evitar chamar
outras rotas quando a identidade/contrato da API é desconhecido. A saída
`ok` significa somente que as verificações **sem autenticação** passaram.
Não significa que as ferramentas funcionam, que o modelo está instalado,
que a IA gera respostas ou que não existem outras rotas vulneráveis.

## Testes automatizados

```bash
python3 -m unittest discover -s tests -p 'test_ops_smoke*.py' -v
python3 -m flake8 ops tests --max-line-length=119
```

- `tests/test_ops_smoke.py`: requests locais simulados, 401/403, rotas
  acidentalmente públicas, redirect/404/500, respostas malformadas,
  timeouts, privacidade, argumentos do CLI e ausência de leitura de corpos privados.
- `tests/test_ops_smoke_contract.py`: invoca a app FastAPI real em ASGI,
  com dados temporários e rede do Ollama simulada; garante que a API
  realmente preserve o contrato e a barreira de autenticação, sem subir servidor.

O GitHub Actions já executa `python -m unittest discover -s tests -v` em PRs.
Nenhuma modificação de CI, `src/api`, `src/agent`, `src/tools` ou deploy
é necessária.

## Limites e segurança

- A ferramenta de diagnóstico opera **somente no próprio notebook Menor**.
- Não a exponha como endpoint público e não a execute com credenciais:
  seu propósito é detectar acessos indevidos **anônimos**.
- O check não comprova a inexistência de outros vazamentos de autorização.
- Não há recuperação automática de falhas; não há testes de escrita
  nem comandos que alterem o ambiente de produção.
- Qualquer ampliação com ações ou dados privados exige plano de isolamento
  e revisão técnica antes da implementação.

**Integração:** PR exclusivo do Chat C, revisão e CI antes de qualquer merge.
