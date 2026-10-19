"""Monitoramento local, contínuo e somente leitura do Ubuntu Server.

Sem serviços externos ou credenciais. Um teste ativo de banda exige --speed-test.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


PROC = Path("/proc")
MIB = 1024 * 1024


def cpu_times(source=None):
    """Total e tempo ocioso da CPU total e de cada núcleo (/proc/stat)."""
    lines = source if source is not None else (PROC / "stat").read_text().splitlines()
    result = {}
    for line in lines:
        words = line.split()
        if not words or not words[0].startswith("cpu"):
            continue
        try:
            values = [int(x) for x in words[1:]]
            if len(values) < 4:
                continue
            result[words[0]] = (sum(values), values[3] + (values[4] if len(values) > 4 else 0))
        except ValueError:
            continue
    return result


def cpu_percent(previous, current):
    usage = {}
    for name, (total, idle) in current.items():
        if name not in previous:
            continue
        old_total, old_idle = previous[name]
        elapsed = total - old_total
        if elapsed > 0:
            usage[name] = max(0.0, min(100.0, 100.0 * (elapsed - (idle - old_idle)) / elapsed))
    return usage


def meminfo(source=None):
    data = {}
    lines = source if source is not None else (PROC / "meminfo").read_text().splitlines()
    for line in lines:
        if ":" not in line:
            continue
        name, _, value = line.partition(":")
        try:
            data[name] = int(value.split()[0]) * 1024
        except (IndexError, ValueError):
            continue
    return data


def network_bytes(source=None):
    """Bytes por interface; não equivale à velocidade contratada da internet."""
    lines = source if source is not None else (PROC / "net/dev").read_text().splitlines()
    result = {}
    for line in lines[2:]:
        if ":" not in line:
            continue
        name, _, fields = line.partition(":")
        values = fields.split()
        if len(values) < 16:
            continue
        try:
            result[name.strip()] = (int(values[0]), int(values[8]))
        except ValueError:
            continue
    return result


def process_snapshot(root=PROC):
    """Usa somente nome curto do processo: nunca imprime argumentos ou segredos."""
    result = {}
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            # /proc/PID/stat permite parênteses no nome; split simples é incorreto.
            closing = stat.rfind(")")
            if closing < 0:
                continue
            fields = stat[closing + 2:].split()
            ticks = int(fields[11]) + int(fields[12])
            status = (entry / "status").read_text().splitlines()
            rss = next((int(row.split()[1]) * 1024 for row in status
                        if row.startswith("VmRSS:")), 0)
            name = (entry / "comm").read_text().strip().replace("\x1b", "")[:24]
            result[int(entry.name)] = (name, ticks, rss)
        except (OSError, ValueError, IndexError, StopIteration):
            continue
    return result


def process_ranking(before, after, elapsed, limit=6):
    ticks_per_sec = os.sysconf("SC_CLK_TCK")
    ranked = []
    for pid, (name, ticks, rss) in after.items():
        previous = before.get(pid)
        delta = max(0, ticks - previous[1]) if previous and previous[0] == name else 0
        pct = 100.0 * delta / (ticks_per_sec * elapsed) if elapsed > 0 else 0.0
        ranked.append({"pid": pid, "name": name, "cpu_pct": round(pct, 1),
                       "ram_mib": round(rss / MIB, 1)})
    return {"cpu": sorted(ranked, key=lambda x: (-x["cpu_pct"], x["pid"]))[:limit],
            "ram": sorted(ranked, key=lambda x: (-x["ram_mib"], x["pid"]))[:limit]}


def sample(previous, current, elapsed):
    """Produz métricas normalizadas com fonte e unidade explícitas."""
    memory = current["memory"]
    total = memory.get("MemTotal", 0)
    available = memory.get("MemAvailable", memory.get("MemFree", 0))
    swap = memory.get("SwapTotal", 0)
    used = max(0, total - available)
    speed = {}
    for name, (rx, tx) in current["network"].items():
        if name == "lo":
            continue
        old_rx, old_tx = previous["network"].get(name, (rx, tx))
        speed[name] = {"rx_mib_s": round(max(0, rx - old_rx) / MIB / elapsed, 3),
                       "tx_mib_s": round(max(0, tx - old_tx) / MIB / elapsed, 3),
                       "rx_total_mib": round(rx / MIB, 1),
                       "tx_total_mib": round(tx / MIB, 1)}
    return {
        "cpu_pct": cpu_percent(previous["cpu"], current["cpu"]),
        "ram_mib": {"total": round(total / MIB, 1), "used": round(used / MIB, 1),
                    "available": round(available / MIB, 1)},
        "swap_mib": {"total": round(swap / MIB, 1),
                     "used": round(max(0, swap - memory.get("SwapFree", 0)) / MIB, 1)},
        "network": speed,
        "processes": process_ranking(previous["processes"], current["processes"], elapsed),
        "disk": current["disk"],
        "source": "local_procfs",
    }


def capture():
    try:
        usage = shutil.disk_usage(Path.home())
        disk = {"total_gib": round(usage.total / MIB / 1024, 1),
                "free_gib": round(usage.free / MIB / 1024, 1)}
    except OSError:
        disk = {}
    return {"cpu": cpu_times(), "memory": meminfo(), "network": network_bytes(),
            "processes": process_snapshot(), "disk": disk}


def render(metrics):
    cpu = metrics["cpu_pct"]
    mem = metrics["ram_mib"]
    swap = metrics["swap_mib"]
    head = ["MENOR | Monitor local (somente leitura) | Ctrl+C para sair",
            f"CPU total: {cpu.get('cpu', 0):.1f}%  "
            + "  ".join(f"{k} {v:.0f}%" for k, v in list(cpu.items())[1:9]),
            f"RAM: {mem['used']:.0f}/{mem['total']:.0f} MiB  "
            f"disponível: {mem['available']:.0f} MiB  "
            f"swap: {swap['used']:.0f}/{swap['total']:.0f} MiB",
            "Disco (home): " + json.dumps(metrics["disk"], ensure_ascii=False),
            "Rede (tráfego local; não é teste de velocidade da internet):"]
    for name, rates in sorted(metrics["network"].items()):
        head.append(f"  {name}: ↓ {rates['rx_mib_s']:.3f} MiB/s "
                    f"↑ {rates['tx_mib_s']:.3f} MiB/s")
    for key, title in (("cpu", "Processos por CPU"), ("ram", "Processos por RAM")):
        head.append(title + " | PID | nome | CPU% | RAM MiB")
        for item in metrics["processes"][key]:
            head.append(f"  {item['pid']:>7}  {item['name']:<24} "
                        f"{item['cpu_pct']:>6.1f}  {item['ram_mib']:>8.1f}")
    return "\n".join(head)


def active_speed_test():
    """Somente mediante --speed-test. Não é parte da monitoração passiva."""
    binary = shutil.which("speedtest") or shutil.which("speedtest-cli")
    if not binary:
        raise RuntimeError("Instale um cliente speedtest manualmente para teste ativo. "
                           "Nenhum download ou teste foi executado.")
    command = [binary, "--format=json"] if Path(binary).name == "speedtest" else [binary, "--json"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=70, check=False)
    if result.returncode:
        raise RuntimeError("Teste ativo não concluiu; verifique o cliente instalado.")
    try:
        payload = json.loads(result.stdout[:50000])
        if "download" in payload and isinstance(payload["download"], dict):
            return {"download_mbps": round(payload["download"]["bandwidth"] * 8 / 1000000, 2),
                    "upload_mbps": round(payload["upload"]["bandwidth"] * 8 / 1000000, 2)}
        return {"download_mbps": round(payload["download"] / 1000000, 2),
                "upload_mbps": round(payload["upload"] / 1000000, 2)}
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Cliente de velocidade retornou dados incompatíveis.") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description="Monitoramento local e passivo do Menor.")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Intervalo em segundos (0.5–60).")
    parser.add_argument("--once", action="store_true", help="Uma única amostra.")
    parser.add_argument("--json", action="store_true", help="Amostras JSON sem dados privados.")
    parser.add_argument("--speed-test", action="store_true",
                        help="Executa teste EXTERNO ativo (consome dados e internet); não é automático.")
    args = parser.parse_args(argv)
    if not 0.5 <= args.interval <= 60:
        parser.error("Intervalo precisa estar entre 0.5 e 60 segundos.")
    if args.speed_test:
        try:
            print(json.dumps(active_speed_test(), ensure_ascii=False))
            return 0
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            print(str(error), file=sys.stderr)
            return 1
    try:
        previous = capture()
        while True:
            start = time.monotonic()
            time.sleep(args.interval)
            current = capture()
            elapsed = max(time.monotonic() - start, 0.001)
            data = sample(previous, current, elapsed)
            if args.json:
                print(json.dumps(data, ensure_ascii=False), flush=True)
            else:
                if sys.stdout.isatty():
                    print("\033[2J\033[H", end="")
                print(render(data), flush=True)
            previous = current
            if args.once:
                break
    except (KeyboardInterrupt, BrokenPipeError):
        return 0
    except (OSError, ValueError) as error:
        print("Monitor indisponível: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
