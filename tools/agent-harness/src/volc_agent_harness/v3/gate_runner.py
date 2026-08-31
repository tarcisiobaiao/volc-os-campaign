"""GateRunner: onde o gate roda, e o ledger que reserva antes de executar.

Duas refutações moram aqui.

**G1** — análise de argv não contém código. O que contém é o LUGAR: worktree
descartável registrada, cwd fixo nela, ambiente sanitizado, e diff depois. Esta
abstração existe para que um backend de sandbox real possa entrar depois sem
reescrever o pipeline. Enquanto ele não existir e não for provado, ``LocalRunner``
NÃO afirma proteção do filesystem externo — apenas reduz superfície e detecta.

**G5** — a primeira correção trocou a ordem (``lookup`` antes de executar) e
achou que bastava. Não bastava: ``lookup`` responde, não reserva. Dois
consumidores simultâneos recebiam ambos ``NEW_EVIDENCE`` e ambos executavam. A
ordem agora é **identidade → claim transacional → (reuso | execução) →
conclusão fenced**, e não existe caminho que pule o claim.
"""

from __future__ import annotations

import hashlib
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .failures import FailureClass, HarnessFailure, classify_gate_exit
from .ledger import ClaimOutcome, GateIdentity, canonical_cwd


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


#: Estado do gate → estado terminal do claim. Um mapa explícito, porque
#: "infrastructure" e "infra" divergirem em silêncio custaria uma prova perdida.
_ESTADO_DO_CLAIM = {
    "green": "green",
    "red": "red",
    "timeout": "timeout",
    "infrastructure": "infra",
}

#: E o caminho de volta, para relatar o que outro consumidor observou.
_STATUS_DO_ESTADO = {
    "green": "green",
    "red": "red",
    "timeout": "timeout",
    "infra": "infrastructure",
    "abandoned": "infrastructure",
}


@dataclass
class GateOutcome:
    gate_index: int
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    execution_mode: str          # executed | reused | waited | reclaimed | lease_timeout
    status: str                  # green | red | timeout | infrastructure
    evidence_id: int | None = None
    source_evidence_id: int | None = None
    claim_outcome: str = ""
    fencing_token: int = 0
    waited_seconds: float = 0.0
    started_at: str = ""
    completed_at: str = ""
    tree_delta: list[str] = field(default_factory=list)
    #: Contagens do registro — inclusive quando a prova foi REUTILIZADA, para
    #: que quem depende de um número (testes coletados) não precise reexecutar.
    counts: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Verde SEM evidência não é verde.

        O dono que perdia o lease durante a execução devolvia
        ``status="green"`` e ``ok=True`` com ``evidence_id=None``, e o runtime
        decidia por ``ok``. Um gate sem linha no ledger virava commit de
        candidato: prova que não existe autorizando colheita.
        """

        return self.status == "green" and self.evidence_id is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_index": self.gate_index,
            "argv": self.argv,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "execution_mode": self.execution_mode,
            "status": self.status,
            "claim_outcome": self.claim_outcome,
            "fencing_token": self.fencing_token,
            "waited_seconds": round(self.waited_seconds, 3),
            "ok": self.ok,
            "counts": self.counts,
            "evidence_id": self.evidence_id,
            "source_evidence_id": self.source_evidence_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stdout_digest": _digest(self.stdout),
            "stderr_digest": _digest(self.stderr),
            "tree_delta": self.tree_delta,
        }


class GateRunner(ABC):
    """Backend de execução. Local hoje; sandbox/container amanhã.

    As três capacidades abaixo são DECLARAÇÃO FACTUAL, não aspiração. Elas
    decidem em que modo o harness pode operar, e é por isso que existem: um
    backend que não contém não pode rodar sozinho, e dizer que contém quando não
    contém é a única forma de errar que não tem conserto depois.
    """

    #: Escrita fora da worktree é impedida pelo backend.
    contains_filesystem: bool = False
    #: Descendentes não escapam do cancelamento — inclusive quem chama `setsid()`.
    contains_process_tree: bool = False
    #: Insumos ficam congelados durante a execução (snapshot, CoW, overlay RO).
    immutable_inputs: bool = False
    name: str = "abstract"

    @classmethod
    def capabilities(cls) -> dict[str, bool]:
        return {
            "contains_filesystem": cls.contains_filesystem,
            "contains_process_tree": cls.contains_process_tree,
            "immutable_inputs": cls.immutable_inputs,
        }

    @classmethod
    def modes_supported(cls) -> tuple[str, ...]:
        """`autonomous_contained` exige as TRÊS. Derivado, nunca declarado à mão.

        Deixar o modo ser escrito à mão permitiria a um backend afirmar
        contenção que ele não tem — exatamente o que este contrato existe para
        impedir.
        """

        if all(cls.capabilities().values()):
            return ("supervised_local", "autonomous_contained")
        return ("supervised_local",)

    @abstractmethod
    def execute(
        self, *, argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout: int
    ) -> tuple[int, str, str]:
        ...

    def cancel(self) -> None:
        """Encerra a execução em curso. Backend que não sabe cancelar não faz nada.

        Sinalizar "perdi o lease" sem encerrar o processo deixa dois gates rodando
        ao mesmo tempo — o contrário do que o claim promete.
        """


class LocalRunner(GateRunner):
    """Subprocesso local em worktree descartável.

    NÃO contém o filesystem externo: um teste pode escrever fora da worktree.
    O que fazemos é reduzir superfície (gates tipados), fixar o cwd, sanitizar o
    ambiente e DETECTAR alteração inesperada pelo diff posterior.
    """

    contains_filesystem = False
    #: Provado por contraprova: um filho que chama `setsid()` sai do grupo criado
    #: por `start_new_session` e sobrevive ao `killpg` — ele escreveu depois do
    #: `cancel()`. Fechar isso exige cgroup, subreaper ou container.
    contains_process_tree = False
    #: Nada congela a árvore durante a execução; ver G1b.
    immutable_inputs = False
    name = "local"

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._trava = threading.Lock()

    def execute(self, *, argv, cwd, env, timeout):
        # `Popen` em vez de `run`: sem a referência ao processo não há como
        # cancelá-lo quando o lease é perdido.
        with self._trava:
            self._proc = subprocess.Popen(
                list(argv), cwd=cwd, env=dict(env), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
        proc = self._proc
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.cancel()
            proc.communicate()
            raise
        finally:
            with self._trava:
                self._proc = None
        return proc.returncode, out, err

    def cancel(self) -> None:
        """Mata o grupo do processo. `start_new_session` garante que filhos vão junto."""

        import os
        import signal

        with self._trava:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):     # pragma: no cover
            proc.kill()


class _Heartbeat:
    """Renova o lease enquanto o runner executa, e ENCERRA quem perde autoridade.

    A primeira versão tratava qualquer exceção como lease perdido e morria:
    uma indisponibilidade momentânea do SQLite bastava para outro consumidor
    retomar com o primeiro ainda executando — duas execuções físicas.

    Duas correções, combinadas (estratégias A + C do contrato):

    * o lease já nasce cobrindo ``timeout + margem`` (:func:`lease_efetivo`), e
      a renovação só precisa cobrir o resto;
    * a tolerância a falha é limitada pelo TEMPO RESTANTE do lease, não por um
      N arbitrário. Enquanto sobrar folga, insiste; quando a folga entra na
      margem de segurança, desiste — e desistir significa MATAR o subprocesso,
      não apenas sinalizar. Um processo que perdeu autoridade e continua
      rodando é exatamente a corrida que o claim existe para impedir.
    """

    #: Fração do lease abaixo da qual não dá mais para garantir renovação.
    MARGEM_DE_SEGURANCA = 0.25

    def __init__(self, ledger: Any, claim: Any, lease_seconds: int,
                 runner: "GateRunner | None" = None,
                 intervalo: float | None = None):
        self.ledger = ledger
        self.claim = claim
        self.runner = runner
        self.lease_seconds = max(1, int(lease_seconds))
        # `intervalo` existe para TESTE. Sem ele, uma prova de tolerância a
        # falha do heartbeat sobre um gate curto nunca chega a invocar o
        # heartbeat: com lease de 126s o primeiro tique cai aos 31,5s, e o
        # runner já terminou. A prova passava sem exercitar a função sob teste.
        # O default de produção é imutável e continua sendo lease/4.
        self.intervalo = (max(0.01, float(intervalo)) if intervalo is not None
                          else max(0.05, self.lease_seconds / 4.0))
        self.perdeu = threading.Event()
        self.cancelou = threading.Event()
        self._parar = threading.Event()
        self._fio: threading.Thread | None = None
        self._ultimo_ok = time.monotonic()

    def __enter__(self) -> "_Heartbeat":
        if self.claim.owner_token is None:
            return self
        self._fio = threading.Thread(target=self._laco, daemon=True,
                                     name="volc-heartbeat")
        self._fio.start()
        return self

    @property
    def _folga(self) -> float:
        """Segundos restantes do lease desde a última renovação bem-sucedida."""

        return self.lease_seconds - (time.monotonic() - self._ultimo_ok)

    def _laco(self) -> None:
        while not self._parar.wait(self.intervalo):
            try:
                vivo = self.ledger.heartbeat(
                    self.claim, lease_seconds=self.lease_seconds)
            except Exception:
                # Falha TRANSITÓRIA: enquanto houver folga no lease, insiste.
                # Matar a renovação na primeira exceção entregava o claim a
                # outro consumidor sem necessidade nenhuma.
                if self._folga > self.lease_seconds * self.MARGEM_DE_SEGURANCA:
                    continue
                self._desistir()
                return
            if vivo:
                self._ultimo_ok = time.monotonic()
                continue
            self._desistir()          # o claim é de outro: não há o que insistir
            return

    def _desistir(self) -> None:
        """Perdeu autoridade: sinaliza E encerra o processo."""

        self.perdeu.set()
        if self.runner is not None:
            try:
                self.runner.cancel()
                self.cancelou.set()
            except Exception:         # pragma: no cover - cancelar é best-effort
                pass

    def __exit__(self, *_excecao) -> None:
        self._parar.set()
        if self._fio is not None:
            # AGUARDA de verdade: um fio que continua renovando depois do
            # resultado manteria vivo um lease sem dono ativo.
            prazo = self.intervalo * 4 + 1.0
            self._fio.join(timeout=prazo)
            if self._fio.is_alive():   # pragma: no cover - só sob banco travado
                self._fio.join(timeout=prazo)


#: Margem entre o timeout do gate e o lease. Com ela, o lease só vence se o
#: processo já deveria ter sido morto pelo timeout — o heartbeat vira defesa em
#: profundidade, não a única barreira contra retomada indevida.
MARGEM_DE_LEASE_S = 120


MODOS = ("supervised_local", "autonomous_contained")


def _assert_modo_suportado(runner: "GateRunner", modo: str) -> None:
    """Fail-closed. Um runner sem contenção NUNCA vira autônomo em silêncio."""

    if modo not in MODOS:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR, "runner_safety_mode desconhecido",
            detalhe=f"{modo!r} não está em {list(MODOS)}")
    if modo in runner.modes_supported():
        return
    faltando = sorted(k for k, v in runner.capabilities().items() if not v)
    raise HarnessFailure(
        FailureClass.AUTHORIZATION_BLOCK,
        f"runner não contido para o modo {modo}",
        detalhe=f"{runner.name} não garante: {', '.join(faltando)}",
        reproducao=("use runner_safety_mode=supervised_local, ou forneça um "
                    "backend que contenha filesystem, árvore de processos e "
                    "insumos"),
        evidencia={"runner": runner.name, "modo_pedido": modo,
                   "capacidades": runner.capabilities(),
                   "modos_suportados": list(runner.modes_supported())},
    )


def lease_efetivo(*, lease_seconds: int, timeout: int) -> int:
    """Estratégia A: o lease cobre o timeout máximo do gate mais a margem.

    Confiar só no heartbeat era frágil: uma indisponibilidade momentânea do
    SQLite matava a renovação e outro consumidor retomava com o primeiro ainda
    executando. Com o lease dimensionado assim, a expiração durante execução
    normal deixa de ser possível, e o heartbeat cobre o resto.
    """

    return max(int(lease_seconds), int(timeout) + MARGEM_DE_LEASE_S)


def _cwd_efetivo(worktree: Path, cwd_rel: str) -> Path:
    """`worktree / cwd_rel`, contido e existente — conferido ANTES de executar.

    `cwd_rel` entrava na identidade e a execução usava sempre a raiz: a evidência
    afirmava um diretório e o processo rodava em outro. Evidência que mente é
    pior que evidência ausente.
    """

    alvo = (worktree / cwd_rel).resolve() if cwd_rel != "." else worktree.resolve()
    raiz = worktree.resolve()
    if alvo != raiz and raiz not in alvo.parents:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "cwd do gate escapa da worktree",
            detalhe=f"{cwd_rel} -> {alvo}")
    if not alvo.is_dir():
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "cwd do gate não existe na worktree",
            detalhe=cwd_rel, reproducao=f"ls {alvo}")
    return alvo


#: Onde a revalidação acontece. É a lista que a evidência publica — quem lê a
#: prova precisa saber ONDE ela foi conferida, não só que foi.
PONTOS_DE_REVALIDACAO = (
    "antes do claim", "depois da espera pelo claim",
    "antes de reutilizar", "antes de executar",
)


def _evidencia_honesta(gate: Any, runner: "GateRunner", modo: str,
                       revalidacoes: list[str]) -> dict[str, Any]:
    """O que a prova afirma, e o que ela NÃO afirma.

    Um ledger que só grava "verde" convida a leitura errada. Estes campos dizem
    sobre qual impressão de insumos o verde foi medido, em que pontos ele foi
    reconferido, e — explicitamente — que NÃO houve snapshot atômico: entre a
    última medição e o `execve`, e entre o `execve` e cada leitura do processo,
    sobra janela. Esse é o risco residual G1b, e ele fica visível em vez de
    implícito.
    """

    vinculo = getattr(gate, "binding", None)
    return {
        "input_fingerprint": (vinculo.tree_digest if vinculo is not None else ""),
        "binding_digest": (vinculo.digest() if vinculo is not None else ""),
        "revalidated_at": _agora(),
        "revalidation_points": revalidacoes,
        "atomic_snapshot": runner.immutable_inputs,
        "residual_risk": "G1b",
        "runner_safety_mode": modo,
        **runner.capabilities(),
    }


def _revalidador(gate: Any, worktree: Path):
    """Fecha a revalidação sobre o gate. Sem gate, não há o que revalidar."""

    # Sem vínculo ou sem tipo não há o que revalidar. Explodir aqui trocaria
    # uma guarda ausente por um AttributeError, que é pior: some a informação.
    if gate is None or getattr(gate, "binding", None) is None \
            or getattr(gate, "typed", None) is None:
        return lambda _momento: None

    from .gate_resolution import assert_bindings_fresh

    def revalidar(momento: str) -> None:
        try:
            assert_bindings_fresh([gate], tree=worktree)
        except HarnessFailure as falha:
            falha.detalhe = f"{falha.detalhe} [{momento}]".strip()
            raise

    return revalidar


def redact_texto(erro: BaseException) -> str:
    """Mensagem de exceção sanitizada. Traceback carrega variável de ambiente."""

    from ..security import redact

    return redact(f"{type(erro).__name__}: {erro}")[:2000]


def _counts_de(evidencia: Mapping[str, Any]) -> dict[str, Any]:
    """Contagens gravadas, para que o reuso não perca o número medido."""

    import json

    bruto = evidencia.get("counts_json") if evidencia else None
    if not bruto:
        return {}
    try:
        return dict(json.loads(bruto))
    except (TypeError, ValueError):
        return {}


def _snapshot(worktree: Path) -> set[str]:
    r = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    return {l[3:].strip() for l in r.stdout.splitlines() if l.strip()}


def run_gate_with_ledger(
    *,
    gate_index: int,
    argv: Sequence[str],
    worktree: Path,
    env: Mapping[str, str],
    timeout: int,
    ledger: Any,
    acceptance_id: str,
    base_sha: str,
    candidate_sha: str | None,
    context_digest: str,
    env_fingerprint: str,
    production_digest: str,
    test_digest: str,
    run_id: str,
    worker_id: str,
    runner: GateRunner | None = None,
    allow_reuse: bool = True,
    binding_digest: str = "",
    lease_seconds: int = 900,
    wait_seconds: float = 30.0,
    kind_prefix: str = "gate",
    cwd_rel: str = ".",
    enrich_counts: Any = None,
    gate: Any = None,
    heartbeat_interval_seconds: float | None = None,
    runner_safety_mode: str = "supervised_local",
) -> GateOutcome:
    """revalida → claim → revalida → (reuso | execução) → conclusão fenced.

    ``gate`` é o ``ResolvedGate`` VERIFICÁVEL, não um digest solto. A assinatura
    anterior recebia só ``binding_digest`` como string, sem origem: revalidar
    depois da espera não era uma chamada esquecida, era impossível.
    """

    runner = runner or LocalRunner()
    _assert_modo_suportado(runner, runner_safety_mode)
    revalidacoes: list[str] = []
    _bruto = _revalidador(gate, worktree)

    def revalidar(momento: str) -> None:
        _bruto(momento)
        revalidacoes.append(momento)
    if getattr(gate, "binding", None) is not None and not binding_digest:
        # O gate verificável É a origem do digest. Aceitar os dois e deixar o
        # chamador sincronizá-los à mão criaria identidades divergentes entre
        # quem passa a string e quem passa o objeto — dois consumidores do mesmo
        # experimento deixariam de se reconhecer.
        binding_digest = gate.binding.digest()

    # 1. ANTES do acquire. O mundo pode ter mudado desde a compilação.
    revalidar("antes do claim")
    comando = " ".join(argv)
    identidade = GateIdentity.for_gate(
        acceptance_id=acceptance_id, gate_index=gate_index, argv=argv,
        context_digest=context_digest, production_digest=production_digest,
        test_digest=test_digest, env_fingerprint=env_fingerprint,
        binding_digest=binding_digest, kind_prefix=kind_prefix,
        cwd_rel=canonical_cwd(cwd_rel),
    )

    # 1. CLAIM ANTES. `lookup` responde uma pergunta; só o claim reserva.
    lease = lease_efetivo(lease_seconds=lease_seconds, timeout=timeout)
    claim = ledger.acquire(
        identidade, run_id=run_id, worker_id=worker_id,
        lease_seconds=lease, wait_seconds=wait_seconds,
        allow_reuse=allow_reuse,
    )

    # 2. DEPOIS de qualquer espera. `acquire` bloqueia até `wait_seconds`; se a
    #    árvore mudou nessa janela, nem o reuso nem a execução valem sob a
    #    identidade antiga. O claim já adquirido é abandonado, não deixado vivo.
    if claim.aguardou or claim.waited_seconds > 0.05:
        try:
            revalidar("depois da espera pelo claim")
        except BaseException:
            if claim.owner_token is not None:
                ledger.abandon(claim)
            raise
    inicio = _agora()
    comum = dict(
        gate_index=gate_index, argv=list(argv), claim_outcome=claim.outcome.value,
        fencing_token=claim.fencing_token, waited_seconds=claim.waited_seconds,
        started_at=inicio,
    )

    if claim.outcome is ClaimOutcome.REUSED_GREEN:
        # 3a. IMEDIATAMENTE antes de reutilizar.
        revalidar("antes de reutilizar")
        anterior = claim.evidence or {}
        return GateOutcome(
            exit_code=0, stdout="", stderr="", duration_s=0.0,
            execution_mode="waited" if claim.aguardou else "reused",
            status="green", source_evidence_id=anterior.get("id"),
            evidence_id=anterior.get("id"), completed_at=_agora(),
            counts=_counts_de(anterior), **comum,
        )

    if claim.outcome is ClaimOutcome.OBSERVED_NON_GREEN:
        # 2b. Outro consumidor rodou o MESMO experimento e ele não ficou verde.
        #     Repetir não muda o resultado, e não-verde nunca vira verde.
        anterior = claim.evidence or {}
        return GateOutcome(
            exit_code=int(anterior.get("exit_code") or 1), stdout="", stderr="",
            duration_s=0.0, execution_mode="waited",
            status=_STATUS_DO_ESTADO.get(claim.previous_state or "red", "red"),
            source_evidence_id=anterior.get("id"),
            evidence_id=anterior.get("id"), completed_at=_agora(),
            counts=_counts_de(anterior), **comum,
        )

    if claim.outcome is ClaimOutcome.LEASE_TIMEOUT:
        # 2c. Alguém vivo segura o claim. Não roubamos e não executamos — mas a
        #     espera esgotada é fato auditável, então vira evidência não-verde.
        evidencia = ledger.record(
            acceptance_id=acceptance_id, kind=identidade.kind, base_sha=base_sha,
            candidate_sha=candidate_sha, run_id=run_id, command=comando,
            cwd=str(worktree), env_fp=env_fingerprint, ctx_digest=context_digest,
            production_digest=production_digest, test_digest=test_digest,
            exit_code=None,
            counts={"execution_mode": "lease_timeout", "status": "infrastructure",
                    "claim_outcome": claim.outcome.value, "worker_id": worker_id,
                    "waited_seconds": round(claim.waited_seconds, 3)},
            identity=identidade,
        )
        return GateOutcome(
            exit_code=75, stdout="", stderr="lease de outro consumidor ainda vivo",
            duration_s=claim.waited_seconds, execution_mode="lease_timeout",
            status="infrastructure", evidence_id=evidencia, completed_at=_agora(),
            **comum,
        )

    # 3b em diante roda sob UMA fronteira de abandono. Antes, só a falha da
    # revalidação chamava `abandon`: erro de cwd, de snapshot, na entrada do
    # heartbeat, no enriquecimento de contagens ou no próprio ledger escapava e
    # deixava o claim `running` até o lease vencer — prendendo a identidade por
    # um motivo já conhecido no instante da exceção.
    #
    # `concluido` é o corte: quando `complete` devolveu evidência, o resultado é
    # terminal e VÁLIDO, e nenhum abandono pode sobrescrevê-lo. Por isso o
    # abandono mora no `except`, não no `finally`.
    concluido = False
    try:
        revalidar("antes de executar")
        cwd_efetivo = _cwd_efetivo(worktree, identidade.cwd_rel)
        antes = _snapshot(worktree)
        t0 = time.monotonic()
        exit_code, out, err, status = 1, "", "", None
        with _Heartbeat(ledger, claim, lease, runner=runner,
                        intervalo=heartbeat_interval_seconds) as batida:
            try:
                exit_code, out, err = runner.execute(
                    argv=argv, cwd=cwd_efetivo, env=env, timeout=timeout)
                status = "green" if exit_code == 0 else None
            except subprocess.TimeoutExpired:
                exit_code, out, err, status = 124, "", "timeout", "timeout"
            except OSError as erro:
                # Falha de spawn — binário some, fd esgotado, permissão. Só
                # `TimeoutExpired` era capturado, e um OSError escapava ANTES de
                # `complete`: o claim ficava `running` até o lease vencer e INFRA
                # nunca era registrada, apesar de o contrato dizer "sempre".
                exit_code, out, err, status = 71, "", redact_texto(erro), "infrastructure"
            except Exception as erro:                      # noqa: BLE001
                exit_code, out, err, status = 70, "", redact_texto(erro), "infrastructure"
        dur = time.monotonic() - t0

        if status is None:
            classe = classify_gate_exit(
                exit_code=exit_code, argv=list(argv), stdout=out, stderr=err)
            status = ("infrastructure"
                      if classe is FailureClass.INFRASTRUCTURE_ERROR else "red")
        if batida.perdeu.is_set() and status == "green":
            # O lease caiu no meio da execução. O resultado existe, mas não é
            # autoridade: quem retomou o claim responde por esta identidade.
            status = "infrastructure"
            err = (err + "\nlease perdido durante a execução").strip()
        depois = _snapshot(worktree)

        modo = ("reclaimed" if claim.outcome is ClaimOutcome.RECLAIMED_AFTER_EXPIRY
                else "executed")
        contagens: dict[str, Any] = {
            "execution_mode": modo,
            "status": status,
            "claim_outcome": claim.outcome.value,
            "fencing_token": claim.fencing_token,
            "worker_id": worker_id,
            "stdout_digest": _digest(out),
            "stderr_digest": _digest(err),
            "started_at": inicio,
            "runner": runner.name,
            "contains_filesystem": runner.contains_filesystem,
            "lease_perdido": batida.perdeu.is_set(),
            "cwd_rel": identidade.cwd_rel,
            "cwd_efetivo": str(cwd_efetivo),
            **_evidencia_honesta(gate, runner, runner_safety_mode, revalidacoes),
        }
        if enrich_counts is not None:
            contagens.update(enrich_counts(exit_code, out, err) or {})

        resultado = GateOutcome(
            exit_code=exit_code, stdout=out, stderr=err, duration_s=dur,
            execution_mode=modo, status=status, completed_at=_agora(),
            tree_delta=sorted(depois - antes), counts=contagens, **comum,
        )

        # 4. CONCLUSÃO FENCED, sempre — verde, vermelho, timeout e infraestrutura —
        #    ANTES de qualquer raise do chamador. Gravar evidência e fechar o claim
        #    acontecem na mesma transação: quem perdeu o lease não escreve, e um
        #    claim/fence conclui no máximo uma vez (índice único no banco).
        contagens["completed_at"] = resultado.completed_at
        resultado.evidence_id = ledger.complete(
            claim, state=_ESTADO_DO_CLAIM[status], base_sha=base_sha,
            candidate_sha=candidate_sha, run_id=run_id, command=comando,
            cwd=identidade.cwd_rel, production_digest=production_digest,
            test_digest=test_digest, exit_code=resultado.exit_code,
            counts=contagens,
        )
        concluido = resultado.evidence_id is not None
    except BaseException:
        # Efeito colateral, nunca tratamento: o erro ORIGINAL sempre sobe. E a
        # falha do próprio abandono não pode mascará-lo — quem investiga precisa
        # ver o que quebrou, não o que falhou ao registrar que quebrou.
        if not concluido and claim.owner_token is not None:
            try:
                ledger.abandon(claim)
            except BaseException:
                pass
        raise

    if resultado.evidence_id is None:
        # Sem evidência não há autoridade — e `ok` já sabe disso.
        resultado.execution_mode = "abandoned"
        if resultado.status == "green":
            resultado.status = "infrastructure"
    return resultado
