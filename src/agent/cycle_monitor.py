"""Monitor e telemetria em tempo real dos ciclos cognitivos autônomos do Menor v2.

Mantém histórico em memória de logs, fases de execução (1 a 5), métricas de auto-evolução
(aprendizados, anti-padrões, cobertura AST e nota do juiz) para visualização ao vivo na web.
"""

from collections import deque
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, Optional


class CycleMonitor:
    """Rastreador thread-safe de estado e telemetria dos ciclos de estudo e auto-diagnóstico."""

    TOTAL_PHASES = 5
    PHASE_NAMES = {
        0: "Inativo",
        1: "Reflexão de Tarefas & Anti-Padrões",
        2: "Pesquisa & Assimilação Web",
        3: "Inspeção AST & Cobertura de Código",
        4: "Auto-Crítica & Self-Refinement (Reflexion)",
        5: "Consolidação do Relatório de Evolução",
    }

    def __init__(self, max_logs: int = 250):
        self._lock = threading.RLock()
        self._max_logs = max_logs
        self._logs: deque = deque(maxlen=max_logs)
        self._is_running = False
        self._start_time: Optional[float] = None
        self._current_phase = 0
        self._phase_name = self.PHASE_NAMES[0]
        self._phase_desc = "Aguardando próximo ciclo de estudo..."
        self._progress = 0
        self._started_at: Optional[str] = None
        self._finished_at: Optional[str] = None
        self._duration_seconds = 0.0
        self._interrupted = False
        self._error: Optional[str] = None

        self._metrics: Dict[str, Any] = {
            "learnings_count": 0,
            "anti_patterns_count": 0,
            "topics_studied": [],
            "coverage_percentage": "N/A",
            "uncovered_gaps": 0,
            "judge_score": "N/A",
            "golden_example_created": False,
        }
        self._last_report_summary: Dict[str, Any] = {}

    def start(self, initial_msg: str = "Ciclo cognitivo autônomo iniciado.") -> None:
        """Sinaliza início de um novo ciclo."""
        with self._lock:
            self._is_running = True
            self._start_time = time.time()
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._finished_at = None
            self._duration_seconds = 0.0
            self._current_phase = 1
            self._phase_name = self.PHASE_NAMES[1]
            self._phase_desc = "Iniciando reflexão sobre tarefas recentes..."
            self._progress = 10
            self._interrupted = False
            self._error = None

            self.log(initial_msg, level="info", phase=1)

    def set_phase(self, phase: int, desc: str = "") -> None:
        """Avança a fase atual do ciclo (1 a 5)."""
        with self._lock:
            self._current_phase = phase
            self._phase_name = self.PHASE_NAMES.get(phase, f"Fase {phase}")
            self._phase_desc = desc or self._phase_name
            # Calcula progresso aproximado proporcional às 5 fases
            self._progress = min(100, int((phase / self.TOTAL_PHASES) * 100))
            self.log(
                f"[{phase}/{self.TOTAL_PHASES}] {self._phase_name}: {self._phase_desc}",
                level="step",
                phase=phase,
            )

    def log(self, message: str, level: str = "info", phase: Optional[int] = None) -> None:
        """Registra mensagem de log no buffer circular."""
        with self._lock:
            now = datetime.now(timezone.utc)
            entry = {
                "timestamp": now.strftime("%H:%M:%S"),
                "iso": now.isoformat(),
                "phase": phase if phase is not None else self._current_phase,
                "level": level,  # info, step, ok, warn, error
                "message": message.strip(),
            }
            self._logs.append(entry)

    def update_metrics(self, **kwargs) -> None:
        """Atualiza indicadores e métricas acumuladas do ciclo."""
        with self._lock:
            for k, v in kwargs.items():
                if k in self._metrics:
                    self._metrics[k] = v

    def finish(
        self,
        report: Optional[Dict[str, Any]] = None,
        interrupted: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """Finaliza o ciclo com sucesso ou interrupção."""
        with self._lock:
            self._is_running = False
            now = datetime.now(timezone.utc)
            self._finished_at = now.isoformat()
            if self._start_time:
                self._duration_seconds = round(time.time() - self._start_time, 2)
            self._interrupted = interrupted
            self._error = error

            if error:
                self._current_phase = 0
                self._phase_name = "Erro"
                self._phase_desc = f"Ciclo finalizado com erro: {error}"
                self.log(f"Falha no ciclo: {error}", level="error")
            elif interrupted:
                self._phase_name = "Interrompido"
                self._phase_desc = "Ciclo interrompido por requisição prioritária do usuário."
                self.log("Ciclo interrompido (preempção imediata ativada).", level="warn")
            else:
                self._current_phase = 5
                self._progress = 100
                self._phase_name = "Concluído"
                self._phase_desc = "Ciclo executado com sucesso e aprendizados assimilados."
                self.log(f"Ciclo concluído em {self._duration_seconds}s.", level="ok", phase=5)

            if report:
                self._last_report_summary = {
                    "timestamp": self._finished_at,
                    "duration_seconds": self._duration_seconds,
                    "interrupted": self._interrupted,
                    "report_markdown": report.get("report_markdown", ""),
                    "metrics": dict(self._metrics),
                }

    def clear_logs(self) -> None:
        """Limpa histórico de logs em memória."""
        with self._lock:
            self._logs.clear()

    def snapshot(self) -> Dict[str, Any]:
        """Retorna fotografia serializável do estado atual da telemetria."""
        with self._lock:
            current_duration = (
                round(time.time() - self._start_time, 1)
                if (self._is_running and self._start_time)
                else self._duration_seconds
            )
            return {
                "is_running": self._is_running,
                "current_phase": self._current_phase,
                "total_phases": self.TOTAL_PHASES,
                "phase_name": self._phase_name,
                "phase_desc": self._phase_desc,
                "progress_percent": self._progress,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "duration_seconds": current_duration,
                "interrupted": self._interrupted,
                "error": self._error,
                "logs": list(self._logs),
                "metrics": dict(self._metrics),
                "last_report_summary": dict(self._last_report_summary),
            }


_GLOBAL_MONITOR: Optional[CycleMonitor] = None
_GLOBAL_LOCK = threading.Lock()


def get_cycle_monitor() -> CycleMonitor:
    """Acessa o monitor de ciclo singleton da aplicação."""
    global _GLOBAL_MONITOR
    with _GLOBAL_LOCK:
        if _GLOBAL_MONITOR is None:
            _GLOBAL_MONITOR = CycleMonitor()
        return _GLOBAL_MONITOR
