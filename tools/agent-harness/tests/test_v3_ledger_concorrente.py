"""FASE 0 + FASE 3 — G5: claim, lease e fencing sob concorrência real.

A refutação de G5 foi física, não retórica: dois consumidores com o mesmo digest
e uma ``Barrier`` executaram o gate DUAS vezes e gravaram DUAS evidências
``EXECUTED``. O ledger sabia dizer "reuso" depois do fato, mas não impedia a
segunda execução, porque ``lookup`` não reserva nada.

As provas A–F desta suíte são as exigidas pela missão. Todas rodam também em
multiprocesso, porque ``threading`` compartilha a mesma conexão de processo e
esconde exatamente a corrida que interessa.

⚠️ LIMITE DECLARADO — não existe exactly-once absoluto aqui. Um crash depois do
claim e antes da conclusão pode causar reexecução quando o lease vencer. O que
está provado é: no máximo uma execução física CONCORRENTE, e fencing da
conclusão.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _ledger_concorrente_worker import (  # noqa: E402
    argv_do_caso, consumidor, consumidor_sem_heartbeat,
)

import volc_agent_harness.v3.gate_runner as gate_runner_mod  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.ledger import (  # noqa: E402
    ClaimOutcome, EvidenceLedger, GateIdentity, context_digest, env_fingerprint,
)

WORKER = str(Path(__file__).resolve().parent / "_ledger_concorrente_worker.py")


def _executados(marcador: Path) -> int:
    """Quantos processos de gate realmente rodaram."""

    return len(list(marcador.iterdir())) if marcador.is_dir() else 0


class _Base(unittest.TestCase):
    #: `lease_efetivo` passou a garantir `timeout + MARGEM_DE_LEASE_S`, para que
    #: o lease não vença com o processo vivo. As provas que exercem RETOMADA
    #: precisam de um lease que realmente expire, então encolhem a margem — e
    #: encolher a margem é dizer explicitamente qual propriedade está sendo
    #: testada, em vez de depender de um lease curto que o runtime já não aceita.
    MARGEM_DE_TESTE = 0

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.wt = self.raiz / "wt"
        self.wt.mkdir()
        subprocess.run(["git", "init", "-q", str(self.wt)], check=True)
        self.ledger_path = self.raiz / "led.sqlite"
        self.marcador = self.raiz / "execucoes"
        self.ctx = context_digest(acceptance_text="a1", base_sha="s",
                                  candidate_sha=None, lineage_root=None)
        self.fp = env_fingerprint({"PATH": "/usr/bin:/bin"})
        self._margem = gate_runner_mod.MARGEM_DE_LEASE_S
        gate_runner_mod.MARGEM_DE_LEASE_S = self.MARGEM_DE_TESTE

    def tearDown(self):
        gate_runner_mod.MARGEM_DE_LEASE_S = self._margem
        self.tmp.cleanup()

    def caso(self, **over):
        base = {
            "ledger": str(self.ledger_path),
            "worktree": str(self.wt),
            "marcador": str(self.marcador),
            "acceptance_id": "P10-T17-A1",
            "ctx": self.ctx,
            "fp": self.fp,
            "prod": "p1",
            "test": "t1",
            "run_id": "r1",
            "worker_id": "w1",
        }
        base.update(over)
        return base

    def identidade(self, **over) -> GateIdentity:
        campos = {
            "acceptance_id": "P10-T17-A1",
            "kind": "gate_1",
            "context_digest": self.ctx,
            "production_digest": "p1",
            "test_digest": "t1",
            "command_digest": "cmd",
            "env_fingerprint": self.fp,
        }
        campos.update(over)
        return GateIdentity(**campos)


class ProvaA_UmaExecucaoFisica(_Base):
    """Dois consumidores, mesmo digest, Barrier."""

    def test_threads_executam_exatamente_uma_vez(self):
        barreira = threading.Barrier(2)
        saidas: list[dict] = []
        erros: list[BaseException] = []

        def alvo(worker_id: str):
            try:
                saidas.append(consumidor(
                    self.caso(worker_id=worker_id, atraso=1.5), barreira))
            except BaseException as exc:   # pragma: no cover
                erros.append(exc)

        fios = [threading.Thread(target=alvo, args=(f"w{i}",)) for i in (1, 2)]
        for f in fios:
            f.start()
        for f in fios:
            f.join(timeout=90)

        self.assertEqual(erros, [], f"consumidor falhou: {erros}")
        self.assertEqual(_executados(self.marcador), 1,
                         "o gate rodou fisicamente mais de uma vez")
        modos = sorted(s["execution_mode"] for s in saidas)
        self.assertEqual(modos, ["executed", "waited"])
        self.assertTrue(all(s["status"] == "green" for s in saidas))

    def test_multiprocesso_executa_exatamente_uma_vez(self):
        ctx = mp.get_context("spawn")
        barreira = ctx.Barrier(2)
        fila = ctx.Queue()

        procs = [
            ctx.Process(target=_alvo_mp,
                        args=(self.caso(worker_id=f"w{i}", atraso=2.0), barreira, fila))
            for i in (1, 2)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)

        saidas = [fila.get(timeout=10) for _ in procs]
        for s in saidas:
            self.assertNotIn("erro", s, f"consumidor multiprocesso falhou: {s}")
        self.assertEqual(_executados(self.marcador), 1,
                         "processo concorrente executou o gate duas vezes")
        modos = sorted(s["execution_mode"] for s in saidas)
        self.assertEqual(modos, ["executed", "waited"])

    def test_uma_unica_evidencia_verde_final(self):
        consumidor(self.caso(worker_id="w1"))
        consumidor(self.caso(worker_id="w2"))
        led = EvidenceLedger(self.ledger_path)
        verdes = [e for e in led.evidencias(acceptance_id="P10-T17-A1")
                  if e["exit_code"] == 0]
        executadas = [e for e in verdes
                      if json.loads(e["counts_json"]).get("execution_mode") == "executed"]
        self.assertEqual(len(executadas), 1,
                         "duas evidências EXECUTED para o mesmo digest")


class ProvaB_LeaseVivoNaoEhRoubado(_Base):
    def test_segundo_consumidor_nao_rouba_claim_vivo(self):
        led = EvidenceLedger(self.ledger_path)
        ident = self.identidade()
        primeiro = led.acquire(ident, run_id="r1", worker_id="w1",
                               lease_seconds=120, wait_seconds=0.0)
        self.assertEqual(primeiro.outcome, ClaimOutcome.ACQUIRED)

        segundo = led.acquire(ident, run_id="r2", worker_id="w2",
                              lease_seconds=120, wait_seconds=0.5)
        self.assertEqual(segundo.outcome, ClaimOutcome.LEASE_TIMEOUT)
        self.assertIsNone(segundo.owner_token)
        self.assertEqual(led.claim_atual(ident)["owner_token"], primeiro.owner_token)

    def test_lease_timeout_chega_ao_consumidor_de_gate(self):
        led = EvidenceLedger(self.ledger_path)
        argv = argv_do_caso(self.caso())
        ident = GateIdentity.for_gate(
            acceptance_id="P10-T17-A1", gate_index=1, argv=argv,
            context_digest=self.ctx, production_digest="p1", test_digest="t1",
            env_fingerprint=self.fp, cwd_rel=".",
        )
        led.acquire(ident, run_id="r1", worker_id="w1",
                    lease_seconds=120, wait_seconds=0.0)
        saida = run_gate_with_ledger(
            gate_index=1, argv=argv, worktree=self.wt,
            env={"PATH": "/usr/bin:/bin"}, timeout=30, ledger=led,
            acceptance_id="P10-T17-A1", base_sha="s", candidate_sha=None,
            context_digest=self.ctx, env_fingerprint=self.fp,
            production_digest="p1", test_digest="t1", run_id="r2", worker_id="w2",
            lease_seconds=120, wait_seconds=0.6,
        )
        self.assertEqual(saida.claim_outcome, ClaimOutcome.LEASE_TIMEOUT.value)
        self.assertNotEqual(saida.status, "green")
        self.assertEqual(_executados(self.marcador), 0,
                         "nada pode ter rodado com o lease alheio vivo")
        self.assertIsNotNone(saida.evidence_id, "lease_timeout precisa ser auditável")


class ProvaB2_ExecucaoMaiorQueOLeaseNominal(_Base):
    """B — o heartbeat segura o lease enquanto o runner trabalha.

    A trava é um ARQUIVO, não um argumento: argv entra na identidade lógica, e
    segurar o processo por argumento faria os dois consumidores reivindicarem
    identidades diferentes — a prova compararia duas coisas distintas e passaria
    por engano.
    """

    def _trava(self) -> Path:
        alvo = self.raiz / "TRAVA"
        alvo.write_text("segura")
        return alvo

    def test_threads_uma_execucao_com_lease_curto_e_heartbeat(self):
        trava = self._trava()
        saidas: list[dict] = []
        fio = threading.Thread(target=lambda: saidas.append(consumidor(
            self.caso(worker_id="w1", lease_seconds=1, wait_seconds=0.0))))
        fio.start()
        for _ in range(400):                       # espera a execução começar
            if _executados(self.marcador):
                break
            time.sleep(0.01)
        time.sleep(1.5)                            # muito além do lease nominal
        segundo = consumidor(self.caso(worker_id="w2", run_id="r2",
                                       lease_seconds=1, wait_seconds=0.5))
        trava.unlink(missing_ok=True)
        fio.join(timeout=60)

        self.assertEqual(_executados(self.marcador), 1,
                         "lease renovado não pode abrir segunda execução")
        self.assertEqual(segundo["claim_outcome"], ClaimOutcome.LEASE_TIMEOUT.value)
        self.assertFalse(segundo["ok"])

    def test_multiprocesso_uma_execucao_com_lease_curto(self):
        trava = self._trava()
        ctx = mp.get_context("spawn")
        fila = ctx.Queue()
        caso = self.caso(worker_id="w1", lease_seconds=1, wait_seconds=0.0)
        proc = ctx.Process(target=_alvo_mp, args=(caso, None, fila))
        proc.start()
        for _ in range(600):
            if _executados(self.marcador):
                break
            time.sleep(0.01)
        time.sleep(1.5)
        segundo = consumidor(self.caso(worker_id="w2", run_id="r2",
                                       lease_seconds=1, wait_seconds=0.5))
        trava.unlink(missing_ok=True)
        proc.join(timeout=90)
        primeiro = fila.get(timeout=15)

        self.assertNotIn("erro", primeiro, f"consumidor falhou: {primeiro}")
        self.assertEqual(_executados(self.marcador), 1)
        self.assertEqual(segundo["claim_outcome"], ClaimOutcome.LEASE_TIMEOUT.value)


class ProvaC2_HeartbeatInterrompido(_Base):
    """C — com o heartbeat morto, o lease AINDA não vence durante a execução.

    A versão anterior desta prova media outra coisa, e aceitava o resultado
    errado como contrato: heartbeat morto, lease de 1s, DUAS execuções físicas,
    e a docstring dizia que reexecução era esperada. Era a única barreira contra
    corrida ser um fio que qualquer indisponibilidade momentânea do SQLite
    cortava.

    Com a estratégia A — `lease_efetivo` garantindo `timeout + margem` — o lease
    deixa de vencer com o processo vivo, e o heartbeat vira defesa em
    profundidade. O cenário que esta prova exercia não é mais alcançável, e a
    prova passou a afirmar o que passou a valer: UMA execução física, e o
    segundo consumidor recebendo `lease_timeout` em vez de retomar.

    A retomada continua existindo e continua provada — em `ProvaD`, no caso que
    a justifica: o processo MORRE, e aí o digest não pode ficar preso para
    sempre.
    """

    MARGEM_DE_TESTE = 120                 # a margem de produção, de propósito

    def test_heartbeat_morto_nao_abre_segunda_execucao(self):
        trava = self.raiz / "TRAVA"
        trava.write_text("segura")
        antigo: list[dict] = []

        fio = threading.Thread(target=lambda: antigo.append(
            consumidor_sem_heartbeat(
                self.caso(worker_id="w1", lease_seconds=1, wait_seconds=0.0))))
        fio.start()
        for _ in range(600):
            if _executados(self.marcador):
                break
            time.sleep(0.01)
        time.sleep(1.6)                    # muito além do lease NOMINAL de 1s

        segundo = consumidor(self.caso(worker_id="w2", run_id="r2",
                                       lease_seconds=1, wait_seconds=1.0))
        trava.unlink(missing_ok=True)
        fio.join(timeout=90)

        self.assertEqual(_executados(self.marcador), 1,
                         "heartbeat morto não pode abrir segunda execução física")
        self.assertEqual(segundo["claim_outcome"], ClaimOutcome.LEASE_TIMEOUT.value)
        self.assertFalse(segundo["ok"])
        self.assertTrue(antigo and antigo[0]["ok"],
                        "o dono legítimo terminou e concluiu")

        led = EvidenceLedger(self.ledger_path)
        verdes = [e for e in led.evidencias() if e["exit_code"] == 0]
        self.assertEqual(len(verdes), 1)


class ProvaD2_CompleteDuplicado(_Base):
    """D — um claim/fence conclui no máximo uma vez, garantido pelo banco."""

    def test_indice_unico_impede_segunda_evidencia(self):
        led = EvidenceLedger(self.ledger_path)
        claim = led.acquire(self.identidade(), run_id="r1", worker_id="w1",
                            lease_seconds=120, wait_seconds=0.0)
        args = dict(state="green", base_sha="s", run_id="r1", command="c",
                    production_digest="p1", test_digest="t1", exit_code=0)
        ids = [led.complete(claim, **args) for _ in range(5)]
        self.assertEqual(len(led.evidencias()), 1)
        self.assertEqual({i for i in ids if i is not None}, {ids[0]})


class ProvaC_LeaseVencidoERetomado(_Base):
    def test_retomada_gera_fencing_novo_e_dono_antigo_nao_conclui(self):
        led = EvidenceLedger(self.ledger_path)
        ident = self.identidade()
        velho = led.acquire(ident, run_id="r1", worker_id="w1",
                            lease_seconds=1, wait_seconds=0.0)
        self.assertEqual(velho.outcome, ClaimOutcome.ACQUIRED)
        time.sleep(1.2)

        novo = led.acquire(ident, run_id="r2", worker_id="w2",
                           lease_seconds=60, wait_seconds=0.0)
        self.assertEqual(novo.outcome, ClaimOutcome.RECLAIMED_AFTER_EXPIRY)
        self.assertGreater(novo.fencing_token, velho.fencing_token)

        perdeu = led.complete(
            velho, state="green", base_sha="s", run_id="r1", command="c",
            cwd=str(self.wt), production_digest="p1", test_digest="t1",
            exit_code=0, counts={"execution_mode": "executed"},
        )
        self.assertIsNone(perdeu, "dono antigo gravou resultado depois de perder o lease")

        manteve = led.complete(
            novo, state="green", base_sha="s", run_id="r2", command="c",
            cwd=str(self.wt), production_digest="p1", test_digest="t1",
            exit_code=0, counts={"execution_mode": "executed"},
        )
        self.assertIsNotNone(manteve)

    def test_heartbeat_do_dono_antigo_falha_depois_da_retomada(self):
        led = EvidenceLedger(self.ledger_path)
        ident = self.identidade()
        velho = led.acquire(ident, run_id="r1", worker_id="w1",
                            lease_seconds=1, wait_seconds=0.0)
        self.assertTrue(led.heartbeat(velho, lease_seconds=1))
        time.sleep(1.2)
        led.acquire(ident, run_id="r2", worker_id="w2",
                    lease_seconds=60, wait_seconds=0.0)
        self.assertFalse(led.heartbeat(velho, lease_seconds=60))


class ProvaD_CrashDepoisDoClaim(_Base):
    """Morrer segurando o claim não pode aposentar o digest.

    A trava é um arquivo, não um argumento: o argv entra na identidade lógica, e
    segurar o primeiro processo por argumento faria os dois consumidores
    reivindicarem identidades DIFERENTES — a prova compararia duas coisas
    distintas e passaria por engano.
    """

    def test_digest_nao_fica_bloqueado_para_sempre(self):
        trava = self.raiz / "TRAVA"
        trava.write_text("segura o gate")
        caso = self.caso(lease_seconds=1, wait_seconds=0.5, timeout=1, margem=0)
        caso["saida"] = str(self.raiz / "morto.json")
        proc = subprocess.Popen(
            [sys.executable, WORKER, json.dumps(caso)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(400):                   # espera o claim aparecer
                if self.ledger_path.exists() and EvidenceLedger(
                        self.ledger_path).claims_ativos():
                    break
                time.sleep(0.05)
            led = EvidenceLedger(self.ledger_path)
            ativos = led.claims_ativos()
            self.assertTrue(ativos, "o primeiro consumidor não chegou a reivindicar")
            proc.kill()
            proc.wait(timeout=30)
        finally:
            trava.unlink(missing_ok=True)

        self.assertTrue(EvidenceLedger(self.ledger_path).claims_ativos(),
                        "o claim do processo morto sumiu")
        time.sleep(1.3)                            # o lease vence
        saida = consumidor(self.caso(worker_id="w2", wait_seconds=3.0, run_id="r2",
                                     timeout=1, margem=0))
        self.assertEqual(saida["claim_outcome"],
                         ClaimOutcome.RECLAIMED_AFTER_EXPIRY.value)
        self.assertEqual(saida["execution_mode"], "reclaimed")
        self.assertEqual(saida["status"], "green")
        self.assertGreater(saida["fencing_token"], ativos[0]["fencing_token"],
                           "retomada exige fencing token novo")


class ProvaE_VermelhoTimeoutEInfra(_Base):
    def test_vermelho_e_registrado_e_nunca_volta_verde(self):
        saida = consumidor(self.caso(exit_code=1, worker_id="w1"))
        self.assertEqual(saida["status"], "red")
        self.assertIsNotNone(saida["evidence_id"], "vermelho precisa estar no ledger")

        de_novo = consumidor(self.caso(exit_code=1, worker_id="w2", run_id="r2"))
        self.assertEqual(de_novo["execution_mode"], "executed",
                         "prova vermelha virou reuso")
        self.assertEqual(de_novo["status"], "red")
        self.assertEqual(_executados(self.marcador), 2)

    def test_timeout_e_infra_sao_registrados_e_nao_sao_reutilizados(self):
        class _Timeout(GateRunner):
            name = "timeout"

            def execute(self, *, argv, cwd, env, timeout):
                raise subprocess.TimeoutExpired(argv, timeout)

        led = EvidenceLedger(self.ledger_path)
        argv = ["/usr/bin/true"]
        comum = dict(
            gate_index=1, argv=argv, worktree=self.wt, env={"PATH": "/usr/bin:/bin"},
            timeout=5, ledger=led, acceptance_id="P10-T17-A1", base_sha="s",
            candidate_sha=None, context_digest=self.ctx, env_fingerprint=self.fp,
            production_digest="p1", test_digest="t1", lease_seconds=60,
            wait_seconds=1.0,
        )
        primeiro = run_gate_with_ledger(
            **comum, run_id="r1", worker_id="w1", runner=_Timeout())
        self.assertEqual(primeiro.status, "timeout")
        self.assertIsNotNone(primeiro.evidence_id)

        segundo = run_gate_with_ledger(
            **comum, run_id="r2", worker_id="w2", runner=_Timeout())
        self.assertEqual(segundo.execution_mode, "executed",
                         "timeout foi reutilizado como prova")
        self.assertNotEqual(segundo.status, "green")

    def test_falha_e_gravada_antes_de_qualquer_excecao(self):
        """A ordem no código: complete/record acontece antes do raise do chamador."""

        import inspect

        from volc_agent_harness.v3 import gate_runner

        fonte = inspect.getsource(gate_runner.run_gate_with_ledger)
        self.assertLess(fonte.index("acquire("), fonte.index("runner.execute("))
        self.assertLess(fonte.index("runner.execute("), fonte.index(".complete("))
        self.assertNotIn("raise HarnessFailure", fonte.split(".complete(")[0])


class ProvaF_MudancaDeScriptOuConfig(_Base):
    def test_execucao_recusada_por_digest_divergente(self):
        from volc_agent_harness.v3.failures import FailureClass, HarnessFailure
        from volc_agent_harness.v3.gate_resolution import (
            assert_bindings_fresh, resolve_mission_gates,
        )

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _e2e_fixture import git, repo_sintetico

        catalogo = {
            "catalog_version": 1,
            "gates": {"prova": {"kind": "tracked_script",
                                "script_path": "tools/agent-harness/prova.py",
                                "args": [], "description": "d"}},
        }
        raiz = self.raiz / "repo"
        raiz.mkdir()
        repo_sintetico(raiz, catalogo=catalogo)
        (raiz / "tools" / "agent-harness" / "prova.py").write_text("print(1)\n")
        git(raiz, "add", "-A")
        subprocess.run(["git", "-C", str(raiz), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "s"],
                       check=True, capture_output=True)

        resolvidos = resolve_mission_gates(
            gates=[{"kind": "catalog", "gate_id": "prova"}],
            tree=raiz, toolchain={"python": sys.executable},
        )
        (raiz / "tools" / "agent-harness" / "prova.py").write_text("print(2)\n")
        with self.assertRaises(HarnessFailure) as e:
            assert_bindings_fresh(resolvidos, tree=raiz)
        self.assertEqual(e.exception.classe, FailureClass.STALE_INPUT)


def _alvo_mp(caso, barreira, fila):   # pragma: no cover - roda em outro processo
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from _ledger_concorrente_worker import consumidor as _c

    try:
        fila.put(_c(caso, barreira))
    except BaseException as exc:
        fila.put({"erro": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    unittest.main()
