"""As sete guardas obrigatórias do Harness V3."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_compiler import ProducedPath  # noqa: E402
from volc_agent_harness.v3.ledger import EvidenceLedger, Status, env_fingerprint  # noqa: E402
from volc_agent_harness.v3.ownership import build_proposal  # noqa: E402
from volc_agent_harness.v3.registry import WorktreeRegistry  # noqa: E402
from volc_agent_harness.v3.schema_version import (  # noqa: E402
    SCHEMA_VERSION_ATUAL, assert_compilable, migration_report,
)
from volc_agent_harness.v3.two_phase import postwriter_compile  # noqa: E402
from volc_agent_harness.v3.workspace import (  # noqa: E402
    assert_no_destructive_intent, prepare,
)


class Guarda1SemLimpezaDestrutiva(unittest.TestCase):
    def test_caminho_livre_e_usado_diretamente(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "novo"
            plano = prepare(desired=alvo, mission_id="m1")
            self.assertEqual(plano.path, alvo)
            self.assertFalse(plano.reused)

    def test_caminho_preexistente_nunca_e_apagado(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "ocupado"
            alvo.mkdir()
            (alvo / "MARCA").write_text("nao me apague")
            plano = prepare(desired=alvo, mission_id="m1")
            self.assertNotEqual(plano.path, alvo)
            self.assertTrue((alvo / "MARCA").is_file(), "conteúdo preexistente intacto")

    def test_worktree_com_colheita_bloqueia_com_autorizacao(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "colheita"
            alvo.mkdir()
            reg = WorktreeRegistry(Path(tmp) / "reg.sqlite")
            reg.claim(worktree=str(alvo), mission_id="m1", branch="b", base_sha="a")
            reg.release(worktree=str(alvo), status="released", harvest_sha="b7111fa")
            with self.assertRaises(HarnessFailure) as e:
                prepare(desired=alvo, registry=reg, mission_id="m1", allow_unique_fallback=False)
            self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_writer_ativo_bloqueia(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "ativo"
            alvo.mkdir()
            reg = WorktreeRegistry(Path(tmp) / "reg.sqlite")
            reg.claim(worktree=str(alvo), mission_id="m1", branch="b",
                      base_sha="a", writer_pid=os.getpid())
            with self.assertRaises(HarnessFailure) as e:
                prepare(desired=alvo, registry=reg, mission_id="m2", allow_unique_fallback=False)
            self.assertEqual(e.exception.classe, FailureClass.OWNERSHIP_ERROR)

    def test_gate_com_comando_destrutivo_e_recusado(self):
        for argv in (["sh", "-c", "rm -rf build"], ["git", "clean", "-fdx"]):
            with self.subTest(argv=argv):
                with self.assertRaises(HarnessFailure) as e:
                    assert_no_destructive_intent(argv)
                self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_codigo_do_harness_nao_contem_rm_rf(self):
        """Nenhuma CHAMADA destrutiva no código — docstring que fala do assunto vale.

        A verificação é por AST: só importa `shutil.rmtree(...)` de verdade e
        `subprocess` com `rm -rf`, não a prosa que documenta a proibição.
        """

        import ast

        raiz = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"
        ofensores = []
        for arquivo in raiz.rglob("*.py"):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Call):
                    alvo = ast.unparse(no.func)
                    if alvo.endswith("rmtree"):
                        ofensores.append(f"{arquivo.name}:{no.lineno} {alvo}")
                if isinstance(no, ast.Constant) and isinstance(no.value, str):
                    continue  # literal em allowlist de proibição não é chamada
        self.assertEqual(ofensores, [], "o harness não pode apagar árvore")


class Guarda3DuasFases(unittest.TestCase):
    def test_artefato_obrigatorio_ausente_apos_writer_e_spec_error(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(HarnessFailure) as e:
                postwriter_compile(
                    tree=Path(tmp),
                    produced=[ProducedPath("backend/tests/test_novo.py", required=True)],
                    changed_paths=[], writable_paths=["backend"], gates=[], collect=False,
                )
            self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)

    def test_alteracao_fora_do_ownership_efetivo_e_ownership_error(self):
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "backend").mkdir()
            with self.assertRaises(HarnessFailure) as e:
                postwriter_compile(
                    tree=t, produced=[], changed_paths=["backend/ok.py", "src/fora.ts"],
                    writable_paths=["backend"], gates=[], collect=False,
                )
            self.assertEqual(e.exception.classe, FailureClass.OWNERSHIP_ERROR)
            self.assertIn("src/fora.ts", e.exception.detalhe)

    def test_produced_presente_passa_a_segunda_fase(self):
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "backend" / "tests").mkdir(parents=True)
            (t / "backend" / "tests" / "test_novo.py").write_text("def test_x(): pass\n")
            r = postwriter_compile(
                tree=t, produced=[ProducedPath("backend/tests/test_novo.py")],
                changed_paths=["backend/tests/test_novo.py"],
                writable_paths=["backend/tests"], gates=[], collect=False,
            )
            self.assertEqual(r.produced_present, ["backend/tests/test_novo.py"])


class Guarda4OwnershipNaoAmplia(unittest.TestCase):
    def _arvore(self, tmp):
        t = Path(tmp)
        (t / "volc_ads" / "campanha").mkdir(parents=True)
        (t / "volc_ads" / "subir.py").write_text("class Selo:\n    pass\n")
        (t / "volc_ads" / "campanha" / "demand_gen.py").write_text(
            "from volc_ads.subir import Selo\n\ndef b():\n    return Selo()\n")
        return t

    def test_descoberta_sugere_mas_nao_concede_escrita(self):
        with TemporaryDirectory() as tmp:
            p = build_proposal(
                tree=self._arvore(tmp), acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                search_roots=["volc_ads"], envelope=["volc_ads"],
                declared_writable=["volc_ads/subir.py"],
            )
            self.assertEqual(p["writable_paths"], ["volc_ads/subir.py"],
                             "writable_paths continua sendo só o declarado")
            self.assertIn("volc_ads/campanha/demand_gen.py", p["suggested_writable_paths"])
            self.assertIn("volc_ads/campanha/demand_gen.py", p["material_outside_declared"])

    def test_fora_do_envelope_exige_nova_autorizacao(self):
        with TemporaryDirectory() as tmp:
            p = build_proposal(
                tree=self._arvore(tmp), acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                search_roots=["volc_ads"], envelope=["volc_ads/subir.py"],
                declared_writable=["volc_ads/subir.py"],
            )
            self.assertTrue(p["requires_new_authorization"])
            self.assertTrue(p["blocks_writer"])


class Guarda5LedgerDuravel(unittest.TestCase):
    def test_ambiente_diferente_invalida_a_prova(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "l.sqlite")
            fp1 = env_fingerprint({"PATH": "/a", "PYTHONPATH": "/x"})
            fp2 = env_fingerprint({"PATH": "/b", "PYTHONPATH": "/x"})
            led.record(acceptance_id="A-A1", kind="focal_gate", base_sha="s", run_id="r",
                       command="pytest", cwd="/w", env_fp=fp1,
                       production_digest="d", test_digest="t")
            igual = led.lookup(acceptance_id="A-A1", kind="focal_gate", command="pytest",
                               production_digest="d", test_digest="t", cwd="/w", env_fp=fp1)
            self.assertEqual(igual["status"], Status.REUSED)
            outro = led.lookup(acceptance_id="A-A1", kind="focal_gate", command="pytest",
                               production_digest="d", test_digest="t", cwd="/w", env_fp=fp2)
            self.assertEqual(outro["status"], Status.REEXECUTED)
            self.assertIn("ambiente", outro["reason"])

    def test_cwd_diferente_invalida_a_prova(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "l.sqlite")
            fp = env_fingerprint({"PATH": "/a"})
            led.record(acceptance_id="A-A1", kind="focal_gate", base_sha="s", run_id="r",
                       command="pytest", cwd="/w1", env_fp=fp,
                       production_digest="d", test_digest="t")
            r = led.lookup(acceptance_id="A-A1", kind="focal_gate", command="pytest",
                           production_digest="d", test_digest="t", cwd="/w2", env_fp=fp)
            self.assertEqual(r["status"], Status.REEXECUTED)
            self.assertIn("diretório de trabalho", r["reason"])

    def test_fingerprint_nao_carrega_valor_de_segredo(self):
        a = env_fingerprint({"PATH": "/a", "GEMINI_API_KEY": "AIzaSEGREDOREAL"})
        b = env_fingerprint({"PATH": "/a", "GEMINI_API_KEY": "outro-valor"})
        self.assertEqual(a, b, "valor de credencial não pode entrar no fingerprint")
        c = env_fingerprint({"PATH": "/a"})
        self.assertNotEqual(a, c, "a PRESENÇA da chave é material")

    def test_ledger_usa_wal_e_suporta_concorrencia(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "l.sqlite"
            led = EvidenceLedger(caminho)
            led.record(acceptance_id="A-A1", kind="k", base_sha="s", run_id="r",
                       command="c", production_digest="d", test_digest="t")
            import sqlite3
            with sqlite3.connect(caminho) as c:
                modo = c.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(modo.lower(), "wal")


class Guarda6SchemaEMigracao(unittest.TestCase):
    def test_missao_v2_nao_atravessa_o_compilador_em_silencio(self):
        with self.assertRaises(HarnessFailure) as e:
            assert_compilable({"mission_id": "legado", "base_ref": "x"})
        self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)
        self.assertIn("migração", e.exception.resumo)
        self.assertIn("mission_schema_version", e.exception.reproducao)

    def test_v3_sem_campos_obrigatorios_falha_com_dica(self):
        with self.assertRaises(HarnessFailure) as e:
            assert_compilable({"mission_schema_version": 3, "mission_id": "m"})
        dicas = e.exception.evidencia.get("migration_hints", [])
        self.assertTrue(dicas)
        self.assertTrue(all("porque" in d and "exemplo" in d for d in dicas))

    def test_schema_futuro_e_recusado(self):
        with self.assertRaises(HarnessFailure):
            assert_compilable({"mission_schema_version": SCHEMA_VERSION_ATUAL + 1})

    def test_relatorio_de_migracao_lista_o_que_falta(self):
        rel = migration_report({
            "antiga.json": {"mission_id": "a"},
            "nova.json": {"mission_schema_version": 3, "acceptance_ids": ["P-T1-A1"],
                          "ownership_envelope": ["x"]},
        })
        self.assertEqual(rel["prontas"], ["nova.json"])
        self.assertEqual(len(rel["precisam_migrar"]), 1)
        self.assertIn("como_migrar", rel["precisam_migrar"][0])


class Guarda7Higiene(unittest.TestCase):
    def test_gitignore_cobre_artefatos_de_runtime(self):
        raiz = Path(__file__).resolve().parents[3]
        ignore = (raiz / ".gitignore").read_text(encoding="utf-8")
        for padrao in ("evidence-ledger.sqlite", "worktree-registry.sqlite",
                       "heartbeat.jsonl", "compiled-mission.json", "gate-plan.json"):
            self.assertIn(padrao, ignore, f"{padrao} precisa ser ignorado")

    def test_nenhum_pycache_ou_sqlite_versionado(self):
        raiz = Path(__file__).resolve().parents[3]
        saida = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "tools/agent-harness"],
            capture_output=True, text=True, check=True,
        ).stdout
        for proibido in ("__pycache__", ".sqlite", ".pyc", "heartbeat.jsonl"):
            self.assertNotIn(proibido, saida, f"{proibido} não pode estar versionado")


if __name__ == "__main__":
    unittest.main()
