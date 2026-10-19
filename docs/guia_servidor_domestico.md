# Guia do Servidor Doméstico (Home Server)

Como transformar o notebook em uma central de serviços para IA, bancos de dados, APIs e jogos.

---

## ⚙️ Como Funciona um Servidor Doméstico

Um servidor nada mais é do que um computador comum executando serviços em segundo plano que escutam portas de rede (ex: `:8000` para a IA, `:5432` para banco de dados) e respondem a requisições de outros dispositivos.

```mermaid
graph TD
    subgraph Rede Externa / Dispositivos
        Phone[Celular via 4G/5G]
        PC[PC Principal / Jogos]
    end

    subgraph Acesso Seguro
        Tunnel[Tailscale / Cloudflare Tunnel]
    end

    Phone --> Tunnel
    PC --> Tunnel

    subgraph Notebook Servidor (Ubuntu Server + 32GB RAM)
        Tunnel --> ReverseProxy[Reverse Proxy - Nginx / Caddy]
        
        ReverseProxy --> ServiceAI[Container: Jarvis IA + Whisper]
        ReverseProxy --> ServiceDB[Container: PostgreSQL / Redis]
        ReverseProxy --> ServiceGame[Container: Servidor de Jogos]
        ReverseProxy --> ServiceWeb[Container: Sites / APIs]
    end
```

---

## 🐳 O Segredo da Multi-Hospedagem: Docker

Para rodar dezenas de coisas diferentes no mesmo notebook sem que uma quebre a outra, tudo deve ser empacotado em **containers Docker**:

* **Isolamento total**: Uma API em Python 3.10 não interfere em um site em Node 20 ou no banco de dados.
* **Reinicialização automática**: Se a máquina reiniciar ou um app travar, o Docker sobe tudo de volta sozinho (`restart: always`).
* **Deploy em um comando**: Um único arquivo `docker-compose.yml` sobe todos os bancos, sites e serviços de uma vez.

---

## 🚀 O que Você Pode Rodar Neste Notebook (32 GB RAM)

1. **Inteligência Artificial (Jarvis)**:
   - LLM local (Qwen / Llama) consumindo ~8 a 10 GB de RAM.
   - Vector Database (ChromaDB / Qdrant) para memória de longo prazo da IA.
   - Microserviço de transcrição de voz (Whisper).
2. **Bancos de Dados**:
   - **PostgreSQL**: Banco relacional para seus apps e projetos.
   - **Redis**: Cache ultrarrápido para sessões e mensagens em tempo real.
3. **Backends & APIs**:
   - Seus backends em FastAPI, Express, NestJS, Go, etc.
4. **Servidores de Jogos**:
   - Dedicated servers para testes de jogos multiplayer (Godot, Unity, Unreal) via WebSocket/UDP.
   - Servidores locais para jogos (Minecraft, Terraria, Valheim).
5. **Automação & Bots**:
   - Bots de Discord ou Telegram que interagem com a sua IA.
   - Rotinas de backup automático para a nuvem.

---

## 🔒 Acesso Remoto Seguro (Fora de Casa)

* **Sem abrir portas no roteador (CGNAT safe)**: Uso do **Tailscale**. Ele cria uma VPN mesh criptografada entre seu notebook, PC e celular em menos de 2 minutos.
* **Publicação pública (se quiser colocar um site na internet)**: Uso de **Cloudflare Tunnels**, que expõe seu domínio seguro (`https://seusite.com`) direto do notebook sem riscos de invasão na rede doméstica.

## Deploy automático do Menor

A implementação atual usa o Python e o systemd existentes no Ubuntu; os containers
acima são a arquitetura futura. Não requer instalar Docker ou runners do GitHub.

### Instalação inicial

Repositório limpo na branch `main`, em `~/menor-assistant`, com acesso de leitura
ao GitHub e os pacotes `python3-venv`, `git`, `curl` e `util-linux` disponíveis:

```bash
cd ~/menor-assistant
git pull --ff-only
bash scripts/install-services.sh
sudo loginctl enable-linger "$USER"
systemctl --user status menor-api.service menor-deploy.timer
```

A instalação cria links dos três units em `~/.config/systemd/user/`, prepara o
`.venv`, executa o primeiro deploy e habilita a API e o timer. O `enable-linger`
permite que os serviços do usuário iniciem no boot e continuem após sair do SSH.
Se a API já estiver aberta manualmente na porta 8000, encerre esse processo antes.

### Fluxo após cada push

O deploy automático acontece quando o commit é **publicado na `main`** (por push direto
ou merge de um PR revisado). Um commit apenas local ou em branch de trabalho não
atualiza a produção. Não é necessário rodar `git pull` ou reiniciar a API
manualmente a cada versão.

1. `menor-deploy.timer` consulta o GitHub cerca de 30 segundos após cada execução.
2. `scripts/deploy.sh` trava execuções concorrentes e recusa branch diferente de
   `main`, alterações locais (inclusive arquivos não ignorados) ou commits locais
   não publicados. Não usa reset, stash nem descarta dados.
3. Faz fetch e merge somente fast-forward da `main`. É o equivalente seguro de
   um pull sem criar commits de merge.
4. Havendo uma revisão ainda não aplicada, instala `requirements.txt` no `.venv`,
   executa os testes Python e os cenários de deploy isolados, recarrega os units
   e executa `bash scripts/menor reiniciar` (o mesmo efeito de `menor reiniciar`),
   reiniciando a API e garantindo que os timers disponíveis estão ativos.
5. Confere `/health` e o serviço ativo antes de gravar a revisão aplicada em
   `.git/menor-deployed-revision`. Sem mudanças, não reinstala nem reinicia.
   Se os testes, o reinício ou a verificação falharem, não marca a revisão como
   implantada; registra o erro no journal e tenta novamente no próximo ciclo.

Os testes do deploy criam repositórios temporários e simulam instalação/restart;
não alteram o serviço real. O GitHub Actions roda Flake8 e os mesmos testes em
pushes na `main` e pull requests. O timer não depende do Actions e não aguarda
esse resultado. Não é um webhook instantâneo: o intervalo e o tempo dos testes
determinam o atraso entre push e aplicação.

### Operação e recuperação

```bash
journalctl --user -u menor-deploy.service -n 80 --no-pager
journalctl --user -u menor-api.service -n 80 --no-pager
systemctl --user list-timers menor-deploy.timer
systemctl --user start menor-deploy.service   # conferir mudanças agora
menor reiniciar                             # reiniciar API manualmente, se necessário
systemctl --user stop menor-deploy.timer     # pausar atualizações
systemctl --user start menor-deploy.timer    # retomar
```

A API fica disponível na porta 8000 na rede privada. O `/health` responde mesmo
com Ollama offline; confira também `ollama_status` para diagnosticar inferência.
O deploy não exige que o modelo esteja carregado para subir a API.

Limite: o checkout e o ambiente virtual são atualizados no próprio diretório.
Uma falha de dependências/testes impede o restart, mas não reverte arquivos ou
pacotes já atualizados. Uma falha depois do restart pode deixar a API indisponível.
Não há rollback automático: pause o timer, publique um `git revert` da alteração
problemática na `main` e retome o timer. Não edite arquivos versionados no servidor.

Referências: [timers do systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
e [gatilhos do GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
