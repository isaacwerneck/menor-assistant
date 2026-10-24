#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Deploy falhou na linha $LINENO. Consulte journalctl --user -u menor-deploy.service." >&2' ERR

# Instala os timers opcionais uma vez, sem reconfigurar cada ciclo de deploy.
ensure_optional_timers() {
    local units="$HOME/.config/systemd/user"
    local name changed=0
    mkdir -p "$units"
    if [[ -f scripts/menor ]]; then
        mkdir -p "$HOME/.local/bin"
        ln -sfn "$PWD/scripts/menor" "$HOME/.local/bin/menor"
    fi
    for name in menor-review menor-missions; do
        if [[ ! -f "deploy/systemd/$name.timer" ]]; then
            continue
        fi
        if systemctl --user is-enabled --quiet "$name.timer"; then
            continue
        fi
        ln -sfn "$PWD/deploy/systemd/$name.service" "$units/$name.service"
        ln -sfn "$PWD/deploy/systemd/$name.timer" "$units/$name.timer"
        changed=1
    done
    if [[ "$changed" == 1 ]]; then
        systemctl --user daemon-reload
        for name in menor-review menor-missions; do
            if [[ -e "$units/$name.timer" ]]; then
                systemctl --user enable --now "$name.timer"
            fi
        done
    fi
}

# O Bash lê a função inteira antes do pull que pode atualizar este arquivo.
main() {
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    command -v flock >/dev/null
    exec 9>.git/menor-deploy.lock
    if ! flock -n 9; then
        echo "Outro deploy está em execução."
        return 0
    fi
    if [[ "$(git branch --show-current)" != main ]]; then
        echo "Deploy requer a branch main." >&2
        return 1
    fi
    if [[ -n "$(git status --porcelain -uno)" ]]; then
        echo "Deploy bloqueado: há alterações locais em arquivos rastreados. Salve-as antes de atualizar." >&2
        return 1
    fi

    export GIT_TERMINAL_PROMPT=0
    git fetch --no-tags origin main
    local target
    target="$(git rev-parse FETCH_HEAD)"
    if ! git merge-base --is-ancestor HEAD "$target"; then
        echo "Deploy bloqueado: main local divergiu ou contém commits não publicados." >&2
        return 1
    fi
    git merge --ff-only "$target"
    if [[ -f .git/menor-deployed-revision ]] &&
        [[ "$(cat .git/menor-deployed-revision)" == "$target" ]] &&
        systemctl --user is-active --quiet menor-api.service; then
        ensure_optional_timers
        echo "Sem mudanças: $target"
        return 0
    fi

    if [[ ! -x .venv/bin/python ]]; then
        python3 -m venv .venv
    fi
    .venv/bin/python -m pip install -r requirements.txt
    (
        test_data="$(mktemp -d)"
        trap 'rm -rf -- "$test_data"' EXIT
        # Testes não podem ler o cérebro real nem disputar a CPU do Ollama de produção.
        MENOR_DATA_DIR="$test_data/data" OLLAMA_URL=http://127.0.0.1:9 \
            .venv/bin/python -m unittest discover -s tests -v
    )
    bash tests/test_deploy.sh
    bash tests/test_control.sh
    systemctl --user daemon-reload
    # Mesmo caminho do comando `menor reiniciar`: recarrega a API e mantém os timers ativos.
    bash scripts/menor reiniciar
    curl --fail --silent --show-error --retry 10 --retry-connrefused \
        --retry-delay 2 --max-time 5 http://127.0.0.1:8000/health
    systemctl --user is-active --quiet menor-api.service
    ensure_optional_timers
    printf '%s\n' "$target" > .git/menor-deployed-revision
    echo "Deploy concluído: $target"
}

main "$@"
