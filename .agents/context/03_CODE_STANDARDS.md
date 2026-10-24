# 03 — Padrões de Código e Diretrizes de Engenharia

Para manter o Menor v2 robusto, previsível e sustentável:

## 1. Princípio Ponytail (YAGNI & Menor Caminho)
* Prefira sempre a biblioteca padrão do Python (`pathlib`, `subprocess`, `sqlite3`, `re`, `json`) antes de instalar novas dependências.
* Não crie abstrações especulativas (camadas extras de mediação, parsers sintéticos de intenção, modelos de classificação intermediários) a menos que haja um caso de uso concreto que exija.

## 2. Tipagem e Validação
* Use `pydantic` (v2) para validar payloads da API.
* Use type hints em todas as assinaturas de funções (`def fn(param: str) -> Dict[str, Any]:`).

## 3. Tratamento de Erros e Resiliência
* A indisponibilidade de um serviço externo (ex: Ollama offline) não deve derrubar o servidor FastAPI; deve retornar HTTP 503 com mensagem clara e amigável.
* Nunca engula exceções silenciosamente; registre com `logger.warning` ou `logger.error`.

## 4. Testabilidade
* Todo código novo deve ser coberto por testes unitários em `tests/`.
* Testes não devem depender de chamadas de rede para a internet ou da presença obrigatória de uma GPU; use mocks quando necessário.
