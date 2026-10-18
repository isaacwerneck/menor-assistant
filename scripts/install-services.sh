#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Instalação falhou na linha $LINENO." >&2' ERR
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ "$PWD" != "$HOME/menor-assistant" ]]; then
    echo "Instale o repositório em ~/menor-assistant antes de continuar." >&2
    exit 1
fi
for tool in git python3 flock curl systemctl; do
    command -v "$tool" >/dev/null
done
mkdir -p "$HOME/.config/systemd/user"
for unit in deploy/systemd/*; do
    ln -sfn "$PWD/$unit" "$HOME/.config/systemd/user/${unit##*/}"
done
systemctl --user daemon-reload
bash scripts/deploy.sh
systemctl --user enable menor-api.service
systemctl --user enable --now menor-deploy.timer
echo "Serviços instalados. Para iniciar sem login: sudo loginctl enable-linger $USER"
