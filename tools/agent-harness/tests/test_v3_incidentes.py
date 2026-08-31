"""Os incidentes reais da rodada anterior, virados regressão.

Cada teste aqui reproduz uma falha que custou tempo de writer. Se algum deles
ficar vermelho, o Harness V3 voltou a permitir o que já nos custou caro.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(RAIZ))

from volc_agent_harness.v3.adjudication import Forca, Parecer, adjudicar  # noqa: E402
from volc_agent_harness.v3.baseline import (  # noqa: E402
    BaselineRecord, assert_baseline_is_green, assert_no_regression, compare,
)
from volc_agent_harness.v3.compiler import compile_mission, load_acceptances  # noqa: E402
from volc_agent_harness.v3.failures import (  # noqa: E402
    FailureClass, HarnessFailure, classify_gate_exit, relanca_writer,
)
from volc_agent_harness.v3.gate_compiler import (  # noqa: E402
    ProducedPath, assert_pytest_collects, compile_gate,
)
from volc_agent_harness.v3.harvest import Harvest, requires_writer, resume_base  # noqa: E402
from volc_agent_harness.v3.ledger import EvidenceLedger, Status, digest_files  # noqa: E402
from volc_agent_harness.v3.registry import WorktreeRegistry  # noqa: E402


class _ChamadaDeModelo:
    """Sentinela: qualquer chamada aqui significa que gastamos um writer."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []

    def __call__(self, quem: str) -> None:
        self.chamadas.append(quem)


class CasoB3GateInexistente(unittest.TestCase):
    """B3 gastou 39 minutos de writer para descobrir um caminho inexistente."""

    def test_compiler_recusa_gate_com_caminho_inexistente_sem_chamar_writer(self):
        modelo = _ChamadaDeModelo()
        with TemporaryDirectory() as tmp:
            arvore = Path(tmp)
            (arvore / "backend" / "tests").mkdir(parents=True)
            (arvore / "backend" / "tests" / "test_existe.py").write_text("def test_ok(): pass\n")
            with self.assertRaises(HarnessFailure) as erro:
                compile_gate(
                    index=3,
                    argv=[sys.executable, "-m", "pytest",
                          "backend/tests/test_criativo_ownership_concorrente.py", "-q"],
                    timeout_seconds=600,
                    tree=arvore,
                )
            self.assertEqual(erro.exception.classe, FailureClass.SPEC_ERROR)
            self.assertIn("test_criativo_ownership_concorrente.py", erro.exception.detalhe)
        self.assertEqual(modelo.chamadas, [], "nenhum modelo pode ser chamado")
        self.assertFalse(relanca_writer(FailureClass.SPEC_ERROR))

    def test_caminho_declarado_em_produced_paths_compila(self):
        with TemporaryDirectory() as tmp:
            arvore = Path(tmp)
            (arvore / "backend" / "tests").mkdir(parents=True)
            gate = compile_gate(
                index=3,
                argv=[sys.executable, "-m", "pytest", "backend/tests/test_novo.py", "-q"],
                timeout_seconds=600,
                tree=arvore,
                produced=[ProducedPath("backend/tests/test_novo.py", required=True)],
            )
            self.assertFalse(gate.runnable_before_writer)
            self.assertEqual(gate.depends_on_produced, ["backend/tests/test_novo.py"])


class CasoExit4(unittest.TestCase):
    """Exit 4 do pytest é erro de uso. Nunca falha de mérito."""

    def test_exit_4_e_spec_error(self):
        self.assertEqual(
            classify_gate_exit(
                exit_code=4,
                argv=[sys.executable, "-m", "pytest", "x.py"],
                stderr="ERROR: file or directory not found: x.py",
            ),
            FailureClass.SPEC_ERROR,
        )

    def test_exit_5_nenhum_teste_coletado_e_spec_error(self):
        self.assertEqual(
            classify_gate_exit(exit_code=5, argv=["pytest"], stdout="no tests ran"),
            FailureClass.SPEC_ERROR,
        )

    def test_exit_1_continua_merit_failure(self):
        self.assertEqual(
            classify_gate_exit(exit_code=1, argv=["pytest"], stdout="1 failed, 49 passed"),
            FailureClass.MERIT_FAILURE,
        )

    def test_spec_error_nunca_relanca_writer(self):
        self.assertFalse(relanca_writer(FailureClass.SPEC_ERROR))
        self.assertFalse(relanca_writer(FailureClass.OWNERSHIP_ERROR))
        self.assertFalse(relanca_writer(FailureClass.AUTHORIZATION_BLOCK))
        self.assertTrue(relanca_writer(FailureClass.MERIT_FAILURE))

    def test_gate_que_coleta_zero_testes_e_spec_error(self):
        with TemporaryDirectory() as tmp:
            arvore = Path(tmp)
            (arvore / "vazio.py").write_text("# sem teste nenhum\n")
            gate = compile_gate(
                index=1, argv=[sys.executable, "-m", "pytest", "vazio.py", "-q"],
                timeout_seconds=120, tree=arvore,
            )
            with self.assertRaises(HarnessFailure) as erro:
                assert_pytest_collects(gate, tree=arvore)
            self.assertEqual(erro.exception.classe, FailureClass.SPEC_ERROR)


class CasoA3Regressao(unittest.TestCase):
    """A3 trocou 403 por 409 num aceite já provado."""

    def test_mudanca_de_http_status_e_regressao_e_reviewer_nao_e_chamado(self):
        reviewer = _ChamadaDeModelo()
        base = BaselineRecord(1, ["pytest"], 0, 50, 0, 1.0, observable={"http_status": 403})
        cand = BaselineRecord(1, ["pytest"], 1, 49, 1, 1.0, observable={"http_status": 409})
        resultado = compare(baseline=base, candidato=cand)
        self.assertTrue(resultado["regrediu"])
        dimensoes = {r["dimensao"] for r in resultado["regressoes"]}
        self.assertIn("http_status", dimensoes)
        with self.assertRaises(HarnessFailure) as erro:
            assert_no_regression([resultado])
        self.assertEqual(erro.exception.classe, FailureClass.BASELINE_ERROR)
        self.assertEqual(reviewer.chamadas, [], "reviewer não é chamado sobre regressão")

    def test_regressao_declarada_e_autorizada(self):
        base = BaselineRecord(1, ["pytest"], 0, 50, 0, 1.0, observable={"http_status": 403})
        cand = BaselineRecord(1, ["pytest"], 0, 50, 0, 1.0, observable={"http_status": 409})
        r = compare(baseline=base, candidato=cand,
                    aceites_autorizados_a_regredir=["http_status"])
        self.assertFalse(r["regrediu"])

    def test_baseline_vermelho_impede_inicio(self):
        with self.assertRaises(HarnessFailure) as erro:
            assert_baseline_is_green([BaselineRecord(1, ["pytest"], 1, 0, 1, 1.0)])
        self.assertEqual(erro.exception.classe, FailureClass.BASELINE_ERROR)


class CasoA1A2Ownership(unittest.TestCase):
    """A1/A2: call site material fora do writable declarado."""

    def _arvore(self, tmp: str) -> Path:
        arvore = Path(tmp)
        (arvore / "volc_ads" / "campanha").mkdir(parents=True)
        (arvore / "volc_ads" / "subir.py").write_text("class Selo:\n    pass\n")
        (arvore / "volc_ads" / "campanha" / "demand_gen.py").write_text(
            "from volc_ads.subir import Selo\n\ndef build():\n    return Selo()\n"
        )
        return arvore

    def test_call_site_dentro_do_envelope_e_compilado_sem_confirmacao(self):
        from volc_agent_harness.v3.ownership import build_proposal

        with TemporaryDirectory() as tmp:
            arvore = self._arvore(tmp)
            p = build_proposal(
                tree=arvore, acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                search_roots=["volc_ads"], envelope=["volc_ads"],
                declared_writable=["volc_ads/subir.py"],
            )
            self.assertIn("volc_ads/campanha/demand_gen.py", p["writable_paths"])
            self.assertIn("volc_ads/campanha/demand_gen.py", p["missing_from_declaration"])
            self.assertFalse(p["blocks_writer"], "dentro do envelope não bloqueia")

    def test_call_site_fora_do_envelope_bloqueia_antes_do_writer(self):
        from volc_agent_harness.v3.ownership import build_proposal

        with TemporaryDirectory() as tmp:
            arvore = self._arvore(tmp)
            p = build_proposal(
                tree=arvore, acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                search_roots=["volc_ads"], envelope=["volc_ads/subir.py"],
                declared_writable=["volc_ads/subir.py"],
            )
            self.assertIn("volc_ads/campanha/demand_gen.py", p["outside_envelope"])
            self.assertTrue(p["blocks_writer"])


class CasoB4ValidacaoSemWriter(unittest.TestCase):
    """B4: a colheita já existia; faltava só rodar o gate corrigido."""

    def test_colheita_com_spec_error_nao_abre_writer(self):
        h = Harvest("b7111fa", "candidate/p17", ["a.py"], True, [1, 2], 3, "SPEC_ERROR")
        self.assertFalse(requires_writer("SPEC_ERROR", harvest=h))
        self.assertFalse(requires_writer("INFRASTRUCTURE_ERROR", harvest=h))

    def test_merit_failure_com_colheita_retoma_da_colheita(self):
        h = Harvest("b7111fa", "candidate/p17", ["a.py"], True, [1], 2, "MERIT_FAILURE")
        self.assertTrue(requires_writer("MERIT_FAILURE", harvest=h))
        self.assertEqual(resume_base(h, "297757a"), "b7111fa")

    def test_sem_colheita_parte_do_base(self):
        self.assertEqual(resume_base(None, "297757a"), "297757a")


class CasoDivergenciaRevisores(unittest.TestCase):
    """Gemini aprova por checklist, Sol traz contraprova executável."""

    def test_contraprova_executavel_vence_checklist(self):
        r = adjudicar([
            Parecer("gemini", "gemini", "accept", Forca.CHECKLIST, "tudo certo"),
            Parecer("sol", "codex", "changes_requested", Forca.CONTRAPROVA_EXECUTAVEL,
                    "lease vencido transiciona", "pytest -k lease"),
        ])
        self.assertEqual(r["veredito"], "CORRIGIR")
        self.assertEqual(r["forca_decisiva"], "CONTRAPROVA_EXECUTAVEL")
        self.assertEqual(r["reproducao"], "pytest -k lease")

    def test_todos_aceitam_resulta_aceitar(self):
        r = adjudicar([
            Parecer("gemini", "gemini", "accept", Forca.EVIDENCIA_FILE_LINE),
            Parecer("sol", "codex", "accept", Forca.CONTRAPROVA_EXECUTAVEL),
        ])
        self.assertEqual(r["veredito"], "ACEITAR")

    def test_empate_de_forca_prevalece_a_recusa(self):
        r = adjudicar([
            Parecer("gemini", "gemini", "accept", Forca.TESTE_DE_PROPRIEDADE),
            Parecer("sol", "codex", "changes_requested", Forca.TESTE_DE_PROPRIEDADE),
        ])
        self.assertEqual(r["veredito"], "CORRIGIR")


class CasoInfraestrutura(unittest.TestCase):
    """Overlay ausente é infraestrutura, não mérito. Writer não reinicia."""

    def test_err_module_not_found_e_infraestrutura(self):
        self.assertEqual(
            classify_gate_exit(
                exit_code=1, argv=["vitest", "run"],
                stderr="Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'vitest'",
            ),
            FailureClass.INFRASTRUCTURE_ERROR,
        )
        self.assertFalse(relanca_writer(FailureClass.INFRASTRUCTURE_ERROR))

    def test_executavel_absoluto_ausente_e_infraestrutura(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(HarnessFailure) as erro:
                compile_gate(index=1, argv=["/nao/existe/bin/tsc", "--noEmit"],
                             timeout_seconds=60, tree=Path(tmp))
            self.assertEqual(erro.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)


class CasoReusoDeEvidencia(unittest.TestCase):
    """Digest igual reutiliza; digest diferente reexecuta."""

    def test_mesmo_digest_reutiliza(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "led.sqlite")
            led.record(acceptance_id="P17-T09-A3", kind="reviewer", base_sha="297757a",
                       run_id="r1", command="review", production_digest="d1", test_digest="t1",
                       reviewer="sol")
            r = led.lookup(acceptance_id="P17-T09-A3", kind="reviewer", command="review",
                           production_digest="d1", test_digest="t1")
            self.assertEqual(r["status"], Status.REUSED)

    def test_digest_alterado_reexecuta_e_diz_o_que_mudou(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "led.sqlite")
            led.record(acceptance_id="P17-T09-A3", kind="reviewer", base_sha="297757a",
                       run_id="r1", command="review", production_digest="d1", test_digest="t1")
            r = led.lookup(acceptance_id="P17-T09-A3", kind="reviewer", command="review",
                           production_digest="d2", test_digest="t1")
            self.assertEqual(r["status"], Status.REEXECUTED)
            self.assertIn("código de produção", r["reason"])

    def test_provas_do_estado_do_mundo_nunca_sao_reutilizadas(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "led.sqlite")
            for kind in ("secret_scan", "diff_check", "final_build", "clean_tree",
                         "integration_gate", "material_equivalence"):
                led.record(acceptance_id="X-A1", kind=kind, base_sha="a", run_id="r",
                           command="c", production_digest="d", test_digest="t")
                r = led.lookup(acceptance_id="X-A1", kind=kind, command="c",
                               production_digest="d", test_digest="t")
                self.assertEqual(r["status"], Status.NEW, f"{kind} não pode ser reutilizada")

    def test_invalidacao_forca_nova_execucao(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "led.sqlite")
            led.record(acceptance_id="P17-T09-A3", kind="focal_gate", base_sha="a", run_id="r",
                       command="pytest", production_digest="d1", test_digest="t1")
            self.assertEqual(led.invalidate(acceptance_id="P17-T09-A3", reason="base mudou"), 1)
            r = led.lookup(acceptance_id="P17-T09-A3", kind="focal_gate", command="pytest",
                           production_digest="d1", test_digest="t1")
            self.assertNotEqual(r["status"], Status.REUSED)


class CasoSingleWriter(unittest.TestCase):
    """Dois writers não ocupam a mesma worktree."""

    def test_segundo_claim_na_mesma_worktree_e_recusado(self):
        with TemporaryDirectory() as tmp:
            reg = WorktreeRegistry(Path(tmp) / "reg.sqlite")
            reg.claim(worktree="/wt/a", mission_id="m1", branch="b1",
                      base_sha="297757a", writer_pid=os.getpid())
            with self.assertRaises(HarnessFailure) as erro:
                reg.claim(worktree="/wt/a", mission_id="m2", branch="b2",
                          base_sha="297757a", writer_pid=os.getpid())
            self.assertEqual(erro.exception.classe, FailureClass.OWNERSHIP_ERROR)

    def test_worktree_liberada_aceita_novo_claim(self):
        with TemporaryDirectory() as tmp:
            reg = WorktreeRegistry(Path(tmp) / "reg.sqlite")
            reg.claim(worktree="/wt/a", mission_id="m1", branch="b1",
                      base_sha="297757a", writer_pid=os.getpid())
            reg.release(worktree="/wt/a", status="released")
            reg.claim(worktree="/wt/a", mission_id="m2", branch="b2", base_sha="297757a")

    def test_gc_nunca_marca_candidato_nao_integrado(self):
        with TemporaryDirectory() as tmp:
            reg = WorktreeRegistry(Path(tmp) / "reg.sqlite")
            reg.claim(worktree="/wt/a", mission_id="m1", branch="b1", base_sha="297757a")
            reg.release(worktree="/wt/a", status="released", harvest_sha="b7111fa")
            plano = reg.gc_plan()
            self.assertFalse(plano[0]["cleanup_eligible"])
            self.assertIn("candidato não integrado", plano[0]["motivo"])


class CasoAcceptanceIds(unittest.TestCase):
    ROADMAP = {"initiatives": [{"id": "P04-T09", "acceptance": ["a1", "a2", "a3", "a4", "a5"]}]}

    def test_aceite_inexistente_recusa(self):
        with self.assertRaises(HarnessFailure) as e:
            load_acceptances(self.ROADMAP, ["P04-T09-A9"])
        self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)

    def test_tarefa_inexistente_recusa(self):
        with self.assertRaises(HarnessFailure) as e:
            load_acceptances(self.ROADMAP, ["P99-T01-A1"])
        self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)

    def test_formato_invalido_recusa(self):
        with self.assertRaises(HarnessFailure):
            load_acceptances(self.ROADMAP, ["P04-T09"])

    def test_aceite_ja_provado_vira_regressao_obrigatoria(self):
        refs = load_acceptances(self.ROADMAP, ["P04-T09-A1"], proven=["P04-T09-A1"])
        self.assertTrue(refs[0].already_proven)


class CasoHeartbeat(unittest.TestCase):
    def test_resumo_humano_so_muda_de_fase_ou_a_cada_intervalo(self):
        from volc_agent_harness.v3.heartbeat import HeartbeatEvent, HeartbeatSink

        with TemporaryDirectory() as tmp:
            sink = HeartbeatSink(Path(tmp) / "hb.jsonl", resumo_a_cada_segundos=900)
            e1 = HeartbeatEvent("P04-T09", "writer", "active", 20, 4)
            self.assertIsNotNone(sink.emit(e1), "mudança de fase emite resumo")
            e2 = HeartbeatEvent("P04-T09", "writer", "active", 40, 4)
            self.assertIsNone(sink.emit(e2), "mesma fase e antes do intervalo não emite")
            e3 = HeartbeatEvent("P04-T09", "writer", "active", 1000, 4)
            self.assertIsNotNone(sink.emit(e3), "vencido o intervalo, emite")
            linhas = (Path(tmp) / "hb.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(linhas), 3, "artefato guarda tudo")

    def test_alive_without_output_nao_e_falha(self):
        from volc_agent_harness.v3.heartbeat import alive_without_output_e_falha

        self.assertFalse(alive_without_output_e_falha(seconds_since_event=600, limite=300))


if __name__ == "__main__":
    unittest.main()
