# ARQUITETURA MENOR

## Hub Ubuntu

O Hub Ubuntu é um servidor Linux que serve como uma base de dados e ponto de conexão para os clientes Windows. Ele executa serviços essenciais, como o banco de dados SQLite e a API FastAPI.

### Serviços Executados pelo Hub Ubuntu:

- **SQLite Database**: O banco de dados SQLite é usado para armazenar informações importantes do sistema.
- **FastAPI Server**: Um servidor FastAPI que atende solicitações de clientes Windows. Ele pode ser configurado para lidar com consultas ao banco de dados e outras operações necessárias.

## PC Cliente Windows

O cliente Windows (PC Cliente) é um computador que interage diretamente com o usuário e também faz chamadas para o Hub Ubuntu.

### Funcionalidades do PC Cliente:

- **Interfaz Gráfica**: O sistema tem uma interface gráfica onde os usuários podem interagir, visualizar dados e realizar operações.
- **Conexão com Hub Ubuntu**: O cliente Windows estabelece uma conexão com o servidor Linux (Hub Ubuntu) para acessar informações do banco de dados e executar consultas.

### Exemplo de Comando no Cliente Windows: