"""Regressões do monitor local: dados simulados, nenhuma rede ou alteração no host."""
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops import monitor


class MonitorTests(unittest.TestCase):
    def test_cpu_deltas_and_core_percentages(self):
        before = monitor.cpu_times(["cpu 100 0 100 800 0", "cpu0 40 0 10 450 0"])
        after = monitor.cpu_times(["cpu 150 0 150 900 0", "cpu0 50 0 20 480 0"])
        percent = monitor.cpu_percent(before, after)
        self.assertAlmostEqual(percent["cpu"], 50)
        self.assertAlmostEqual(percent["cpu0"], 40)
        self.assertEqual(monitor.cpu_percent(after, after), {})

    def test_memory_and_network_are_local_counters(self):
        mem = monitor.meminfo(["MemTotal: 8192000 kB", "MemAvailable: 4096000 kB",
                               "SwapTotal: 2048000 kB", "SwapFree: 1024000 kB"])
        self.assertEqual(mem["MemTotal"], 8192000 * 1024)
        net = monitor.network_bytes([
            "Inter-| Receive | Transmit", " face |bytes packets etc",
            " eth0: 1048576 1 0 0 0 0 0 0 2097152 1 0 0 0 0 0 0",
            " lo: 100 0 0 0 0 0 0 0 200 0 0 0 0 0 0 0",
        ])
        self.assertEqual(net["eth0"], (1048576, 2097152))
        before = {"cpu": {"cpu": (10, 5)}, "network": {"eth0": (0, 0)},
                  "processes": {}, "memory": mem, "disk": {}}
        after = {**before, "cpu": {"cpu": (30, 15)}, "network": net}
        result = monitor.sample(before, after, 2.0)
        self.assertEqual(result["ram_mib"]["total"], 8000)
        self.assertEqual(result["ram_mib"]["used"], 4000)
        self.assertEqual(result["swap_mib"]["used"], 1000)
        self.assertEqual(result["network"]["eth0"]["rx_mib_s"], 0.5)
        self.assertNotIn("lo", result["network"])
        self.assertEqual(result["source"], "local_procfs")

    def test_proc_parser_ignores_sensitive_arguments_and_handles_parentheses(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            process = root / "321"
            process.mkdir()
            # Depois do último ')' seguem state, ppid, ... utime/stime.
            fields = ["S"] + ["0"] * 10 + ["120", "60"] + ["0"] * 11
            (process / "stat").write_text("321 (nome (teste)) " + " ".join(fields))
            (process / "status").write_text("Name: nome\nVmRSS:\t2048 kB\n")
            (process / "comm").write_text("ollama\n")
            (root / "abc").mkdir()
            out = monitor.process_snapshot(root)
        self.assertEqual(out[321], ("ollama", 180, 2048 * 1024))
        ranking = monitor.process_ranking(
            {321: ("ollama", 80, 5000)}, out, 2.0
        )
        self.assertEqual(ranking["ram"][0]["pid"], 321)
        self.assertNotIn("command", str(ranking))

    def test_active_test_is_explicit_and_has_no_implicit_network(self):
        with patch("ops.monitor.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                monitor.active_speed_test()
        with patch("ops.monitor.capture") as capture, patch("ops.monitor.time.sleep"):
            first = {"cpu": {"cpu": (50, 25)}, "memory": {"MemTotal": 1024},
                     "network": {}, "processes": {}, "disk": {}}
            capture.return_value = first
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(monitor.main(["--once", "--json"]), 0)
            data = json.loads(output.getvalue())
            self.assertIn("cpu_pct", data)
            self.assertIn("source", data)
        with patch("ops.monitor.subprocess.run") as run:
            with patch("ops.monitor.shutil.which", return_value="/usr/bin/speedtest-cli"):
                run.return_value = subprocess.CompletedProcess(
                    [], 0, stdout='{"download":50000000,"upload":10000000}')
                result = monitor.active_speed_test()
                self.assertEqual(result["download_mbps"], 50)
                run.assert_called_once()

    def test_invalid_interval_fails_before_collecting_any_data(self):
        with patch("ops.monitor.capture") as capture:
            with self.assertRaises(SystemExit):
                monitor.main(["--interval", "0", "--once"])
            capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
