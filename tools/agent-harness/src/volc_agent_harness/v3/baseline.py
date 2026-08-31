"""Baseline e ratchet de regressão.

A lane A3 mudou o comportamento de ``/subir`` para um canal fora do canário: o
baseline devolvia **403** e o candidato passou a devolver **409**, porque a
validação do selo passou a preemptar a recusa de canal. Isso regrediu o aceite 1
de P04-T09, que já estava provado e integrado.

Aceite previamente verde tem precedência sobre comportamento novo. Um aceite só
pode mudar de comportamento se a missão declarar explicitamente que o está
regredindo — e aí a mudança é o produto, não um efeito colateral.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .failures import FailureClass, HarnessFailure, classify_gate_exit


@dataclass
class BaselineRecord:
    gate_index: int
    argv: list[str]
    exit_code: int
    passed: int | None
    failed: int | None
    duration_s: float
    file_digests: dict[str, str] = field(default_factory=dict)
    observable: dict[str, Any] = field(default_factory=dict)
    #: Autoridade do resultado, propagada do `GateOutcome`. `exit_code` sozinho
    #: não distingue "o processo saiu 0" de "esta medição vale": um gate
    #: abandonado por perda de lease sai 0 e NÃO é prova de nada.
    status: str | None = None
    evidence_id: int | None = None
    execution_mode: str | None = None
    ok: bool | None = None

    @staticmethod
    def from_outcome(outcome: Any, **extra: Any) -> "BaselineRecord":
        """Constrói a partir do `GateOutcome`, sem perder nada pelo caminho."""

        return BaselineRecord(
            gate_index=outcome.gate_index,
            argv=list(outcome.argv),
            exit_code=outcome.exit_code,
            passed=extra.pop("passed", None),
            failed=extra.pop("failed", None),
            duration_s=outcome.duration_s,
            status=outcome.status,
            evidence_id=outcome.evidence_id,
            execution_mode=outcome.execution_mode,
            ok=outcome.ok,
            **extra,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_index": self.gate_index,
            "argv": self.argv,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "failed": self.failed,
            "duration_s": round(self.duration_s, 3),
            "file_digests": self.file_digests,
            "observable": self.observable,
            "status": self.status,
            "evidence_id": self.evidence_id,
            "execution_mode": self.execution_mode,
            "ok": self.ok,
        }


#: Mudanças que são regressão até prova em contrário. A chave é o que o aceite
#: observa; o valor é a explicação que vai no relatório.
DIMENSOES_OBSERVAVEIS = {
    "http_status": "código HTTP mudou",
    "typed_error": "erro tipado mudou",
    "validation_order": "ordem de validação mudou",
    "absence_semantics": "ausência virou zero (ou o inverso)",
    "header": "header observável mudou",
    "authentication": "exigência de autenticação mudou",
    "side_effect": "efeito lateral passou a ocorrer antes da recusa",
}


def digest_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _contagens(saida: str) -> tuple[int | None, int | None]:
    passou = falhou = None
    for linha in saida.splitlines():
        if " passed" in linha or " failed" in linha:
            tokens = linha.replace(",", " ").split()
            for i, t in enumerate(tokens):
                if t.startswith("passed") and i and tokens[i - 1].isdigit():
                    passou = int(tokens[i - 1])
                if t.startswith("failed") and i and tokens[i - 1].isdigit():
                    falhou = int(tokens[i - 1])
    return passou, falhou


def measure(*_args: Any, **_kwargs: Any) -> "BaselineRecord":
    """DESLIGADA. Medir o base é executar, e execução passa pelo ledger.

    Esta função criava o subprocesso direto. Enquanto ela existisse executável,
    o harness teria duas implementações de "rodar um gate" — e a segunda não
    reivindica, não mede digest e não deixa evidência. Manter as duas é como não
    ter migrado.

    O caminho vivo é ``run_gate_with_ledger`` com ``kind_prefix="baseline_gate"``,
    consumido por ``mission._run_implementation_mission``.
    """

    raise HarnessFailure(
        FailureClass.LEGACY_PATH_DISABLED,
        "baseline.measure foi desligada: baseline executa pelo ledger",
        detalhe="use run_gate_with_ledger(kind_prefix='baseline_gate')",
        reproducao="veja mission._run_implementation_mission",
    )


def assert_baseline_is_green(registros: Sequence[BaselineRecord]) -> None:
    """Uma tarefa não começa sobre baseline vermelho.

    Se o gate já falha antes do writer, qualquer veredito posterior é ruído: não
    dá para separar o que o candidato quebrou do que já estava quebrado.
    """

    vermelhos = [r for r in registros if r.exit_code != 0]
    if vermelhos:
        raise HarnessFailure(
            FailureClass.BASELINE_ERROR,
            "baseline vermelho antes do writer",
            detalhe=", ".join(
                f"gate {r.gate_index} exit={r.exit_code}" for r in vermelhos
            ),
            reproducao=" ".join(vermelhos[0].argv),
            evidencia={"gates_vermelhos": [r.gate_index for r in vermelhos]},
        )

    # `exit_code == 0` não basta. Um gate abandonado por perda de lease sai 0,
    # não tem evidência e não é autoridade sobre nada — aceitá-lo como baseline
    # verde era transformar ausência de prova em prova.
    sem_autoridade = [
        r for r in registros
        if r.ok is not None or r.status is not None or r.evidence_id is not None
        if not (r.ok and r.status == "green" and r.evidence_id is not None)
    ]
    if sem_autoridade:
        raise HarnessFailure(
            FailureClass.INFRASTRUCTURE_ERROR,
            "baseline sem autoridade: exit 0 não é prova sem evidência",
            detalhe=", ".join(
                f"gate {r.gate_index} status={r.status} mode={r.execution_mode} "
                f"evidence_id={r.evidence_id}" for r in sem_autoridade),
            reproducao="o gate saiu 0 mas o ledger não registrou conclusão válida",
            evidencia={"gates": [r.gate_index for r in sem_autoridade]},
        )


def compare(
    *,
    baseline: BaselineRecord,
    candidato: BaselineRecord,
    aceites_autorizados_a_regredir: Sequence[str] = (),
) -> dict[str, Any]:
    """Compara baseline e candidato e nomeia a regressão."""

    regressoes: list[dict[str, Any]] = []

    if baseline.exit_code == 0 and candidato.exit_code != 0:
        regressoes.append({
            "dimensao": "gate_exit",
            "antes": baseline.exit_code,
            "depois": candidato.exit_code,
            "explicacao": "gate era verde no baseline e ficou vermelho",
        })

    if (
        baseline.passed is not None
        and candidato.passed is not None
        and candidato.passed < baseline.passed
    ):
        regressoes.append({
            "dimensao": "test_count",
            "antes": baseline.passed,
            "depois": candidato.passed,
            "explicacao": "menos testes passando que no baseline",
        })

    for chave, explicacao in DIMENSOES_OBSERVAVEIS.items():
        antes = baseline.observable.get(chave)
        depois = candidato.observable.get(chave)
        if antes is None and depois is None:
            continue
        if antes != depois:
            regressoes.append({
                "dimensao": chave,
                "antes": antes,
                "depois": depois,
                "explicacao": explicacao,
            })

    autorizadas = set(aceites_autorizados_a_regredir)
    nao_autorizadas = [r for r in regressoes if r["dimensao"] not in autorizadas]

    return {
        "gate_index": baseline.gate_index,
        "regressoes": regressoes,
        "regressoes_nao_autorizadas": nao_autorizadas,
        "regrediu": bool(nao_autorizadas),
    }


def assert_no_regression(comparacoes: Sequence[dict[str, Any]]) -> None:
    """Regressão de aceite já provado não vai a reviewer — para antes."""

    quebrados = [c for c in comparacoes if c["regrediu"]]
    if not quebrados:
        return
    primeira = quebrados[0]["regressoes_nao_autorizadas"][0]
    raise HarnessFailure(
        FailureClass.BASELINE_ERROR,
        "candidato regrediu comportamento de aceite já provado",
        detalhe=(
            f"gate {quebrados[0]['gate_index']}: {primeira['dimensao']} "
            f"{primeira['antes']} -> {primeira['depois']} ({primeira['explicacao']})"
        ),
        reproducao="compare baseline e candidato no mesmo gate",
        evidencia={"comparacoes": quebrados},
    )
