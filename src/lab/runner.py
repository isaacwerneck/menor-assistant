"""Executor assíncrono de baterias de teste com suporte a Human-in-the-Loop."""
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from src.agent.orchestrator import Orchestrator
from src.lab.eval_engine import CANONICAL_PROBES, DualTierVerifier, LabSession
from src.memory.store import BrainStore

logger = logging.getLogger(__name__)


class LabRunner:
    """Executa sessões de teste no Laboratório em thread separada."""

    def __init__(self, session: LabSession, store: Optional[BrainStore] = None):
        self.session = session
        self.store = store or BrainStore()
        self.orchestrator = Orchestrator(store=self.store)
        self._thread: Optional[threading.Thread] = None

    def start_async(self, categories: Optional[List[str]] = None):
        """Inicia a execução da bateria em segundo plano."""
        self._thread = threading.Thread(
            target=self._run_battery,
            args=(categories,),
            daemon=True,
            name=f"lab-runner-{self.session.session_id}",
        )
        self._thread.start()

    def _select_probes(self, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Filtra as sondas de teste canônicas e sintéticas pelas categorias selecionadas."""
        if not categories:
            return list(CANONICAL_PROBES)
        return [p for p in CANONICAL_PROBES if p.get("category") in categories]

    def _run_battery(self, categories: Optional[List[str]] = None):
        """Loop principal de execução de cada passo da bateria."""
        session = self.session
        probes = self._select_probes(categories)
        session.total_steps = len(probes)
        session.status = "running"
        session.logs.append(f"[INÍCIO] Bateria iniciada com {len(probes)} passos no modelo {session.model}.")

        for idx, probe in enumerate(probes, start=1):
            if session._abort_requested:
                session.logs.append("[ABORT] Execução interrompida prematuramente.")
                session.status = "aborted"
                return

            # Tratamento de pausa solicitado pelo usuário
            session._pause_event.wait()

            session.current_step = idx
            session.active_probe = probe
            session.logs.append(f"[{idx}/{session.total_steps}] Executando: {probe['name']}...")

            # 1. Execução da sonda através do orquestrador
            start_t = time.time()
            messages = [{"role": "user", "content": probe["prompt"]}]
            is_comm_error = False
            try:
                turn_res = self.orchestrator.run_turn(
                    messages=messages,
                    model=session.model,
                    enable_tools=True,
                )
                reply = turn_res.get("reply", "")
                if not turn_res.get("success", True) or "erro de comunicação com o modelo" in reply.lower():
                    is_comm_error = True
                elapsed = time.time() - start_t
            except Exception as exc:
                logger.error("Erro na execução da sonda %s: %s", probe['id'], exc)
                reply = f"[ERRO]: {exc}"
                is_comm_error = True
                elapsed = time.time() - start_t

            # 2. Verificações Dual-Tier
            t1 = DualTierVerifier.verify_tier1(probe, reply)
            t2 = DualTierVerifier.verify_tier2_qualitative(
                probe, reply, session.objective_md, tier1_checks=t1["tier1_checks"]
            )
            combined_score = 0.0 if is_comm_error else round((t1["tier1_score"] + t2["tier2_score"]) / 10.0, 1)

            # 3. Reflexion / Auto-Aprimoramento se a nota inicial for insuficiente (apenas se não for erro de conexão)
            initial_score = combined_score
            if not is_comm_error and combined_score < 7.0 and not session._abort_requested:
                fail_points = [c["detail"] for c in t1.get("tier1_checks", []) if c.get("status") == "FAIL"]
                critique_note = (
                    "; ".join(fail_points) if fail_points else t2.get("critique", "Critérios não atingidos.")
                )
                session.logs.append(
                    f"[REFLEXION] Nota preliminar {combined_score}/10 insuficiente. Auto-crítica: {critique_note}"
                )

                reflexion_prompt = (
                    f"Sua resposta anterior não atingiu a pontuação mínima (nota {combined_score}/10).\n"
                    f"Falhas detectadas na verificação técnica:\n- {critique_note}\n\n"
                    f"Por favor, atenda ao pedido com rigor máximo gerando a solução completa, "
                    f"código limpo e executável sem frases robóticas:\n{probe['prompt']}"
                )
                try:
                    ref_messages = [
                        {"role": "user", "content": probe["prompt"]},
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content": reflexion_prompt},
                    ]
                    ref_res = self.orchestrator.run_turn(
                        messages=ref_messages,
                        model=session.model,
                        enable_tools=True,
                    )
                    ref_reply = ref_res.get("reply", "")
                    if ref_reply and not ref_reply.startswith("[ERRO"):
                        ref_t1 = DualTierVerifier.verify_tier1(probe, ref_reply)
                        ref_t2 = DualTierVerifier.verify_tier2_qualitative(
                            probe, ref_reply, session.objective_md, tier1_checks=ref_t1["tier1_checks"]
                        )
                        new_score = round((ref_t1["tier1_score"] + ref_t2["tier2_score"]) / 10.0, 1)
                        if new_score > combined_score:
                            session.logs.append(
                                f"[EVOLUÇÃO] Reflexion aumentou a nota de {combined_score}/10 "
                                f"para {new_score}/10 (+{round(new_score - combined_score, 1)} pts)!"
                            )
                            combined_score = new_score
                            reply = ref_reply
                            t1 = ref_t1
                            t2 = ref_t2
                except Exception as ref_exc:
                    logger.debug("Reflexion pass falhou: %s", ref_exc)

            evol_note = (
                f" (Auto-aprimorado de {initial_score} para {combined_score}/10 via Reflexion)"
                if combined_score > initial_score else ""
            )

            result_card = {
                "step": idx,
                "probe_id": probe["id"],
                "category": probe.get("category", "geral"),
                "probe_name": probe["name"],
                "question": probe["prompt"],
                "reply": reply,
                "elapsed": round(elapsed, 2),
                "tier1_checks": t1["tier1_checks"],
                "tier1_score": t1["tier1_score"],
                "tier2_critique": t2["critique"],
                "tier2_score": t2["tier2_score"],
                "final_score": combined_score,
                "initial_score": initial_score,
                "learning": t2["learning_extracted"] + evol_note,
                "target_file": f"conhecimentos/{probe.get('category', 'geral')}/{probe['id']}.md",
                "proposed_diff": (
                    f"+ # Aprendizado: {probe['name']}\n"
                    f"+ {t2['learning_extracted']}{evol_note}\n"
                    f"+ Verificado com nota final {combined_score}/10."
                ),
            }

            session.active_result = result_card
            session.scores.append(combined_score)
            session.history.append(result_card)

            status_str = "PASS" if combined_score >= 7.0 else "FAIL"
            session.logs.append(
                f"[{status_str}] Nota: {combined_score}/10 em {round(elapsed, 1)}s. "
                f"Aprendizado gerado para {probe['name']}."
            )

            # 3. Human-in-the-Loop (Modo Manual)
            if session.mode == "manual":
                session.status = "waiting_approval"
                session.logs.append("[AGUARDANDO] Aprovação humana necessária para persistir o aprendizado.")
                # Aguarda até o usuário aprovar, avançar passo ou abortar
                session._step_event.wait(timeout=300)
                session._step_event.clear()

                if session._abort_requested:
                    session.status = "aborted"
                    return
                session.status = "running"
            else:
                # Piloto automático: persiste automaticamente no cérebro
                self._persist_learning(result_card)
                time.sleep(0.5)

        session.status = "completed"
        avg_score = round(sum(session.scores) / len(session.scores), 1) if session.scores else 0.0
        session.logs.append(
            f"[CONCLUÍDO] Bateria finalizada! Nota Média: {avg_score}/10 em {session.total_steps} passos."
        )

    def _persist_learning(self, result_card: Dict[str, Any]):
        """Grava a nota de aprendizado verificada na memória permanente do cérebro."""
        try:
            rel = result_card["target_file"]
            content = (
                f"# Aprendizado Consolidado pelo Laboratório\n\n"
                f"**Data:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**Domínio:** {result_card['category']}\n"
                f"**Nota de Avaliação:** {result_card['final_score']}/10\n\n"
                f"## Pergunta Testada\n{result_card['question']}\n\n"
                f"## Lição Aprendida\n{result_card['learning']}\n\n"
                f"## Crítica Qualitativa\n{result_card['tier2_critique']}\n"
            )
            self.store.write_note(rel, content)
            self.session.logs.append(f"[PERSISTIDO] Aprendizado gravado com sucesso em {rel}.")
        except Exception as exc:
            logger.error("Erro ao persistir nota de aprendizado: %s", exc)
