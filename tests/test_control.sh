#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
export CONTROL_LOG="$scratch/calls"
mkdir -p "$scratch/bin"
cat > "$scratch/bin/systemctl" <<'STUB'
#!/usr/bin/env bash
if [[ "$*" == *" cat "* ]]; then
    [[ "$*" != *"menor-review.timer"* ]]
    exit $?
fi
printf '%s\n' "$*" >> "$CONTROL_LOG"
STUB
chmod +x "$scratch/bin/systemctl"
export PATH="$scratch/bin:$PATH"

bash "$root/scripts/menor" start
bash "$root/scripts/menor" stop
bash "$root/scripts/menor" restart
bash "$root/scripts/menor" status
if bash "$root/scripts/menor" invalid; then exit 1; fi
grep -q -- '--user start menor-api.service menor-deploy.timer menor-missions.timer' "$CONTROL_LOG"
grep -q -- '--user stop menor-deploy.timer menor-missions.timer menor-deploy.service menor-missions.service' "$CONTROL_LOG"
grep -q -- '--user stop menor-api.service' "$CONTROL_LOG"
grep -q -- '--user restart menor-api.service' "$CONTROL_LOG"
echo "Controle: start, stop com timers, restart e status OK."
