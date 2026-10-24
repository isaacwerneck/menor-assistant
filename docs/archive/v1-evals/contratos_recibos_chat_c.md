# Chat C — Contratos e regressões de recibos (v3)

O Menor distingue plano, execução e verificação. Este incremento protege o
**contrato dos resultados**, não modifica a inteligência ou os executores.

## Como validar

Na raiz do repositório, com as dependências normais instaladas:

```bash
python3 -m unittest discover -s tests -p 'test_ops_receipt_contract.py' -v
python3 -m flake8 ops tests --max-line-length=119
```

O GitHub Actions existente também executa a suíte de testes completa em cada PR.
Todos os dados criados para os testes usam diretórios temporários fora do cérebro
real; o teste de imagem usa um PNG temporário gerado no próprio teste.

## Regras observadas

O módulo puro `ops.receipt_contract` produz objetos `Check` com estados
`ok`, `warning` ou `critical`. Há três verificadores:

- `tool_receipt`: `planned` exige `writes` booleano e lista de nomes
  de parâmetros, **sem resultado**. `executed` precisa conter campo
  `result`. A validação apenas confere o formato, não prova execução.
- `agent_result`: respostas tratadas exigem `reply` e fase válidos;
  eventos que afirmam execução não podem conter status `planned`.
  Uma URL de imagem precisa corresponder ao recibo estruturado.
- `image_receipt`: ID hexadecimal de 32 caracteres, URL privada local,
  dimensões válidas, status de integridade e conteúdo separados, declaração
  explícita de limites e ausência de contradições entre evidências. Diferença
  entre tamanho solicitado e produzido vira aviso, não sucesso silencioso.

`summarize` reduz os checks a um resumo estruturado adequado para um futuro
painel local. Ele nunca retorna dados dos recibos, apenas códigos estáticos.
Campos adicionais são permitidos para compatibilidade com extensões futuras.

## O que os testes integrados cobrem

- Pré-validação real da ferramenta `projects.list`, em modo dry-run,
  sem executar a listagem ou operações com dados privados.
- Criação real de uma resposta simples pelo agente, sem chamar o Ollama.
- Produção de recibo de artefato a partir de um PNG temporário, com path simulado,
  sem gerar imagens, instalar modelos ou acessar recursos externos.
- Persistência do último recibo com `TaskStore` em banco temporário isolado,
  nunca no `MENOR_DATA_DIR` de produção.
- Erros e regressões: claim de conteúdo incompatível com integridade, ausência
  de evidência, ID ou URL falsificados, imagem sem recibo, tamanhos inválidos,
  resposta tratada sem texto, eventos planejados falsamente executados.

## Limitações

Este é um mecanismo **de observação e regressão**, não uma certificação de que
a ferramenta realizou a ação, que o arquivo ainda existe ou que uma imagem
representa o conteúdo solicitado. Testar recibos pode identificar alegações
incoerentes, mas não substitui inspeção, autorização e validação dos artefatos.

Não há chamada a endpoints em produção, leitura de prompts reais, escrita em
pastas do usuário, mudanças de deploy ou recuperação automática. PR próprio,
integração somente após CI e revisão. Não altera arquivos dos Chats A, B ou D.
