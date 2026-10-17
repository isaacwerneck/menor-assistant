# Guia de Escolha de Distro & Setup Linux

## 🐧 Escolha da Distribuição Linux

| Distribuição | Interface Gráfica | Consumo de RAM em Idle | Recomendação |
| :--- | :--- | :--- | :--- |
| **Ubuntu Server 24.04 LTS** | Não (Headless / Terminal) | ~300 MB | **Melhor Opção** para servidor 24/7. Máximo desempenho e estabilidade. |
| **Ubuntu Desktop 24.04 LTS** | Sim (GNOME) | ~1.8 GB | Boa se preferir tela gráfica no próprio notebook. |
| **Debian 12 Bookworm** | Opcional | ~250 MB | Ultraleve e estável, mas requer mais passos de configuração manual. |

> **Veredito**: Se o notebook for ficar fechado/dedicado, use **Ubuntu Server 24.04 LTS**. O controle é feito remotamente via SSH do PC principal.

---

## 🛠️ Passo a Passo do Dual Boot

1. **Liberar Espaço no Windows**:
   - Abrir `Gerenciamento de Disco` (`diskmgmt.msc`).
   - Clicar com botão direito na partição `C:` > `Diminuir Volume`.
   - Liberar no mínimo **60 GB a 100 GB** de espaço não alocado (para modelos e datasets).
2. **Gravar Pendrive Bootável**:
   - Baixar a ISO do Ubuntu Server 24.04 LTS.
   - Usar [Rufus](https://rufus.ie/) ou [Ventoy] para gravar no pendrive.
3. **BIOS / UEFI**:
   - Desativar `Fast Startup` no Windows (Painel de Controle > Opções de Energia).
   - Acessar a BIOS e garantir que o boot UEFI está ativo.
   - Dar boot pelo pendrive e instalar o Ubuntu no espaço não alocado.
4. **Comportamento da Tampa (Notebook Fechado)**:
   - Configurar o Linux para não suspender ao fechar a tampa:
     ```bash
     sudo nano /etc/systemd/logind.conf
     # Descomentar e alterar:
     HandleLidSwitch=ignore
     HandleLidSwitchExternalPower=ignore
     # Aplicar:
     sudo systemctl restart systemd-logind
     ```

---

## 📦 Pós-Instalação: Ambiente Base

```bash
# Atualização inicial
sudo apt update && sudo apt upgrade -y

# Ferramentas essenciais e Python
sudo apt install -y build-essential git curl ffmpeg python3-pip python3-venv

# Acesso remoto (SSH)
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```
