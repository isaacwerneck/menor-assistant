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
