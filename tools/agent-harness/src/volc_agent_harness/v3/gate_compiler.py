"""Compilação de gates: um gate só existe se for executável.

A lane B3 gastou 39 minutos de writer para descobrir que o gate 3 apontava para
``backend/tests/test_criativo_ownership_concorrente.py`` — arquivo que nunca
existiu, porque o nome foi inventado na missão e depois abandonado. O pytest
respondeu ``exit 4`` (erro de uso) e o harness leu como falha genérica.

Aqui um gate é compilado ANTES do writer. Se ele cita um caminho que não existe
no ``base_ref`` nem está declarado em ``produced_paths``, a missão não compila.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from .failures import FailureClass, HarnessFailure


@dataclass(frozen=True)
class ProducedPath:
    """Caminho que a missão promete criar. Só ele justifica um gate sobre arquivo ausente."""

    path: str
    required: bool = True


@dataclass
class CompiledGate:
    index: int
    argv: list[str]
    timeout_seconds: int
    executable: str
    resolved_executable: str | None
    referenced_paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)
    depends_on_produced: list[str] = field(default_factory=list)
    runnable_before_writer: bool = True
    kind: str = "generic"
    collect_only_argv: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "argv": self.argv,
            "timeout_seconds": self.timeout_seconds,
            "executable": self.executable,
            "resolved_executable": self.resolved_executable,
            "referenced_paths": self.referenced_paths,
            "depends_on_produced": self.depends_on_produced,
            "runnable_before_writer": self.runnable_before_writer,
            "kind": self.kind,
            "collect_only_argv": self.collect_only_argv,
        }


_IGNORAR_COMO_CAMINHO = {
    "-q", "-v", "-x", "--tb", "-p", "-k", "-m", "run", "build", "--noEmit",
    "--skipLibCheck", "--stdout", "--check", "--write", "-h", "--help",
}


def _parece_caminho(token: str) -> bool:
    if token.startswith("-") or token in _IGNORAR_COMO_CAMINHO:
        return False
    if "=" in token and not token.startswith("/"):
        return False
    return "/" in token or token.endswith((".py", ".ts", ".tsx", ".json", ".js"))


def _indice_do_comando(argv: Sequence[str]) -> int:
    if not argv:
        raise HarnessFailure(FailureClass.SPEC_ERROR, "gate sem argv")
    if Path(argv[0]).name != "env":
        return 0
    i = 1
    while i < len(argv) and "=" in argv[i] and not argv[i].startswith("="):
        i += 1
    if i >= len(argv):
        raise HarnessFailure(FailureClass.SPEC_ERROR, "gate com env, mas sem comando")
    return i


def compile_gate(
    *,
    index: int,
    argv: Sequence[str],
    timeout_seconds: int,
    tree: Path,
    produced: Iterable[ProducedPath] = (),
) -> CompiledGate:
    """Compila um gate contra a árvore do ``base_ref``.

    Levanta ``HarnessFailure(SPEC_ERROR)`` se o gate for inexecutável, e
    ``INFRASTRUCTURE_ERROR`` se o executável existir na especificação mas não no
    ambiente.
    """

    argv = list(argv)
    if not argv:
        raise HarnessFailure(FailureClass.SPEC_ERROR, f"gate {index} sem argv")
    if any(not item for item in argv):
        raise HarnessFailure(FailureClass.SPEC_ERROR, f"gate {index} tem item vazio no argv")

    cmd_i = _indice_do_comando(argv)
    executavel = argv[cmd_i]
    caminho_exec = Path(executavel)

    if caminho_exec.is_absolute():
        if not caminho_exec.is_file() or not os.access(caminho_exec, os.X_OK):
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                f"gate {index}: executável absoluto ausente ou não executável",
                detalhe=executavel,
                reproducao=f"test -x {executavel}",
            )
        resolvido = str(caminho_exec)
    elif "/" not in executavel:
        resolvido = shutil.which(executavel)
        if resolvido is None:
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                f"gate {index}: executável não encontrado no PATH",
                detalhe=executavel,
            )
    else:
        local = (tree / caminho_exec).absolute()
        if not local.is_file():
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                f"gate {index}: executável relativo ausente na árvore",
                detalhe=executavel,
            )
        resolvido = str(local)

    nomes_produzidos = {p.path for p in produced}
    referenciados: list[str] = []
    ausentes: list[str] = []
    depende_de_produzido: list[str] = []

    for token in argv[cmd_i + 1:]:
        if not _parece_caminho(token):
            continue
        if PurePosixPath(token).is_absolute():
            continue
        referenciados.append(token)
        if (tree / token).exists():
            continue
        if token in nomes_produzidos:
            depende_de_produzido.append(token)
        else:
            ausentes.append(token)

    if ausentes:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            f"gate {index} cita caminho inexistente e não declarado em produced_paths",
            detalhe=", ".join(ausentes),
            reproducao=f"ls {ausentes[0]}  # dentro de {tree}",
            evidencia={"gate_index": index, "missing": ausentes, "argv": argv},
        )

    texto_argv = " ".join(argv)
    kind = "generic"
    collect_argv: list[str] | None = None
    if "pytest" in texto_argv:
        kind = "pytest"
        collect_argv = argv[: cmd_i + 1] + [
            t for t in argv[cmd_i + 1:] if t not in {"-q"}
        ] + ["--collect-only", "-q"]
    elif "vitest" in texto_argv:
        kind = "vitest"
    elif "tsc" in texto_argv:
        kind = "tsc"
    elif "vite" in texto_argv:
        kind = "vite"

    return CompiledGate(
        index=index,
        argv=argv,
        timeout_seconds=timeout_seconds,
        executable=executavel,
        resolved_executable=resolvido,
        referenced_paths=referenciados,
        missing_paths=[],
        depends_on_produced=depende_de_produzido,
        runnable_before_writer=not depende_de_produzido,
        kind=kind,
        collect_only_argv=collect_argv,
    )


@dataclass(frozen=True)
class ColetaContexto:
    """Contexto material da coleta. Ela é execução, e execução se reivindica."""

    ledger: Any
    acceptance_id: str
    base_sha: str
    context_digest: str
    env_fingerprint: str
    production_digest: str
    test_digest: str
    run_id: str
    worker_id: str
    candidate_sha: str | None = None
    runner: Any = None
    lease_seconds: int = 600
    wait_seconds: float = 60.0
    cwd_rel: str = "."


def _coletados(saida: str) -> int:
    for linha in saida.splitlines():
        if "test" in linha and "collected" in linha:
            for palavra in linha.split():
                if palavra.isdigit():
                    return int(palavra)
    return 0


def assert_pytest_collects(
    gate: Any, *, tree: Path, ctx: ColetaContexto, env: dict[str, str] | None = None
) -> int:
    """Roda ``--collect-only`` PELO LEDGER. Zero testes coletados é falha de spec.

    Um gate que coleta zero testes é um gate que sempre passa — o pior tipo de
    gate, porque parece verde sem provar nada.

    E a coleta passou a ser reivindicada. O argumento anterior — "ela não emite
    veredito de mérito, então pode ficar fora do ledger" — respondia à pergunta
    errada. Coleta de pytest IMPORTA ``conftest.py``, plugins e todos os módulos
    de teste: é código do repositório executando. Não contabilizar isso deixava
    um caminho produtivo transitivo
    (``mission → postwriter_compile → assert_pytest_collects → subprocess.run``)
    criando processo sem claim, sem digest e sem evidência.

    ⚠️ Isto NÃO contém a coleta. Ela continua rodando com os privilégios do
    harness e alcançando o filesystem inteiro. G1b segue aberta; o que muda é
    que agora existe registro de que rodou, com que identidade e com que
    resultado.
    """

    from .gate_runner import run_gate_with_ledger

    if getattr(gate, "kind", "") != "pytest" or not getattr(
            gate, "collect_only_argv", None):
        return -1

    vinculo = getattr(gate, "binding", None)
    resultado = run_gate_with_ledger(
        gate_index=gate.index,
        argv=gate.collect_only_argv,
        worktree=tree,
        env=env if env is not None else {},
        timeout=180,
        ledger=ctx.ledger,
        acceptance_id=ctx.acceptance_id,
        base_sha=ctx.base_sha,
        candidate_sha=ctx.candidate_sha,
        context_digest=ctx.context_digest,
        env_fingerprint=ctx.env_fingerprint,
        production_digest=ctx.production_digest,
        test_digest=ctx.test_digest,
        run_id=ctx.run_id,
        worker_id=ctx.worker_id,
        runner=ctx.runner,
        binding_digest=vinculo.digest() if vinculo is not None else "",
        lease_seconds=ctx.lease_seconds,
        wait_seconds=ctx.wait_seconds,
        kind_prefix="collect_gate",
        cwd_rel=ctx.cwd_rel,
        enrich_counts=lambda code, out, err: {"collected": _coletados(out)},
    )

    if resultado.evidence_id is None:
        # Sem evidência não há prova de que a coleta aconteceu sob esta
        # identidade — e uma coleta que não se pode provar não autoriza seguir.
        raise HarnessFailure(
            FailureClass.INFRASTRUCTURE_ERROR,
            f"gate {gate.index}: coleta sem evidência no ledger",
            detalhe=f"claim_outcome={resultado.claim_outcome}",
            reproducao=" ".join(gate.collect_only_argv),
            evidencia={"gate_index": gate.index,
                       "claim_outcome": resultado.claim_outcome},
        )

    saida = f"{resultado.stdout}\n{resultado.stderr}"
    if resultado.exit_code in {4, 5} or "no tests ran" in saida.lower():
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            f"gate {gate.index}: pytest não coletou nenhum teste",
            detalhe=saida.strip().splitlines()[-1] if saida.strip() else "",
            reproducao=" ".join(gate.collect_only_argv),
            evidencia={"gate_index": gate.index, "exit": resultado.exit_code},
        )
    if resultado.exit_code != 0:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            f"gate {gate.index}: --collect-only falhou com exit={resultado.exit_code}",
            detalhe=saida.strip()[-400:],
            reproducao=" ".join(gate.collect_only_argv),
        )
    # No REUSO o stdout é vazio de propósito: a contagem vem do registro.
    return int(resultado.counts.get("collected", _coletados(resultado.stdout)))


def compile_gate_plan(
    *,
    gates: Sequence[Any],
    tree: Path,
    produced: Iterable[ProducedPath] = (),
) -> dict[str, Any]:
    """Compila todos os gates e devolve o ``gate-plan.json``."""

    produced = list(produced)
    compilados = [
        compile_gate(
            index=i,
            argv=g.argv if hasattr(g, "argv") else g["argv"],
            timeout_seconds=(
                g.timeout_seconds if hasattr(g, "timeout_seconds") else g.get("timeout_seconds", 600)
            ),
            tree=tree,
            produced=produced,
        )
        for i, g in enumerate(gates, start=1)
    ]
    return {
        "total": len(compilados),
        "runnable_before_writer": [g.index for g in compilados if g.runnable_before_writer],
        "depends_on_produced": [g.index for g in compilados if not g.runnable_before_writer],
        "produced_paths": [{"path": p.path, "required": p.required} for p in produced],
        "gates": [g.as_dict() for g in compilados],
    }
