#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_script="$root/scripts/deploy.sh"
sandbox="$(mktemp -d)"
trap 'rm -rf -- "$sandbox"' EXIT
export HOME="$sandbox/home"
mkdir -p "$HOME"
# O deploy precisa estar ligado ao timer e instalado no servidor.
grep -q "^OnUnitInactiveSec=" "$root/deploy/systemd/menor-deploy.timer"
grep -q "systemctl --user enable --now menor-deploy.timer" "$root/scripts/install-services.sh"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.invalid
export GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.invalid

git init --bare -q "$sandbox/origin.git"
git clone -q "$sandbox/origin.git" "$sandbox/author"
cd "$sandbox/author"
git checkout -qb main
mkdir -p scripts tests
cp "$source_script" scripts/deploy.sh
cp "$root/scripts/menor" scripts/menor
printf '.venv/\n' > .gitignore
printf '# fixture\n' > requirements.txt
printf '#!/usr/bin/env bash\nexit 0\n' > tests/test_deploy.sh
cp tests/test_deploy.sh tests/test_control.sh
git add .
git commit -qm initial
git push -qu origin main
git clone -qb main "$sandbox/origin.git" "$sandbox/server"
cd "$sandbox/server"
mkdir -p .venv/bin "$sandbox/bin"
cat > .venv/bin/python <<'STUB'
#!/usr/bin/env bash
echo "python $*" >> .git/deploy-actions
exit "${FAIL_PYTHON:-0}"
STUB
cat > "$sandbox/bin/systemctl" <<'STUB'
#!/usr/bin/env bash
echo "systemctl $*" >> .git/deploy-actions
if [[ "$*" == *"restart menor-api.service"* && "${FAIL_RESTART:-0}" == 1 ]]; then
    exit 1
fi
STUB
cat > "$sandbox/bin/curl" <<'STUB'
#!/usr/bin/env bash
echo curl >> .git/deploy-actions
exit "${FAIL_HEALTH:-0}"
STUB
chmod +x .venv/bin/python "$sandbox/bin/"*
export PATH="$sandbox/bin:$PATH"

bash scripts/deploy.sh
test "$(cat .git/menor-deployed-revision)" = "$(git rev-parse HEAD)"
# Em revisão nova, usa o controle `menor reiniciar`, que reinicia a API e ativa timers.
grep -q "systemctl --user restart menor-api.service" .git/deploy-actions
grep -q "systemctl --user start menor-deploy.timer menor-missions.timer menor-review.timer" .git/deploy-actions
: > .git/deploy-actions
bash scripts/deploy.sh
if grep -q 'restart\|python' .git/deploy-actions; then
    echo "Deploy sem mudanças reiniciou o serviço." >&2
    exit 1
fi

echo dirty >> requirements.txt
if bash scripts/deploy.sh; then echo "Aceitou alterações locais." >&2; exit 1; fi
git restore requirements.txt
git checkout -qb feature
if bash scripts/deploy.sh; then echo "Aceitou outra branch." >&2; exit 1; fi
git checkout -q main

git -C "$sandbox/author" commit --allow-empty -qm update
git -C "$sandbox/author" push -q origin main
previous="$(cat .git/menor-deployed-revision)"
: > .git/deploy-actions
if FAIL_PYTHON=1 bash scripts/deploy.sh; then echo "Ignorou falha Python." >&2; exit 1; fi
test "$(cat .git/menor-deployed-revision)" = "$previous"
if grep -q "systemctl --user restart menor-api.service" .git/deploy-actions; then
    echo "Reiniciou API apesar de testes falharem." >&2
    exit 1
fi
if FAIL_RESTART=1 bash scripts/deploy.sh; then echo "Ignorou falha de restart." >&2; exit 1; fi
test "$(cat .git/menor-deployed-revision)" = "$previous"
if FAIL_HEALTH=1 bash scripts/deploy.sh; then echo "Ignorou falha de saúde." >&2; exit 1; fi
test "$(cat .git/menor-deployed-revision)" = "$previous"
bash scripts/deploy.sh
test "$(cat .git/menor-deployed-revision)" = "$(git rev-parse HEAD)"
test "$(git rev-parse HEAD)" != "$previous"

flock .git/menor-deploy.lock bash scripts/deploy.sh
git commit --allow-empty -qm unpublished
if bash scripts/deploy.sh; then echo "Aceitou commit não publicado." >&2; exit 1; fi
echo "Deploy: push, reinício do Menor, timer, no-op, bloqueios, falhas e retry OK."
