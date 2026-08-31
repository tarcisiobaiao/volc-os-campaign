"""Classificação tipada de falhas.

O harness V2 levantava ``RuntimeError(f"gate {i} falhou com exit={code}")`` para
tudo. Um ``exit 4`` do pytest — que significa *erro de uso*, arquivo inexistente —
era indistinguível de um teste vermelho. Foi assim que a lane B3 consumiu 39
minutos de writer para descobrir que o gate apontava para um arquivo que nunca
existiu, e que a falha foi lida como defeito do candidato.

Cada classe aqui tem um destino próprio e uma regra de retry própria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FailureClass(str, Enum):
    """Nove classes. O destino e a política de retry derivam da classe."""

    SPEC_ERROR = "SPEC_ERROR"
    OWNERSHIP_ERROR = "OWNERSHIP_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    BASELINE_ERROR = "BASELINE_ERROR"
    MERIT_FAILURE = "MERIT_FAILURE"
    REVIEW_FINDING = "REVIEW_FINDING"
    TIMEOUT = "TIMEOUT"
    AUTHORIZATION_BLOCK = "AUTHORIZATION_BLOCK"
    TRANSIENT_PROVIDER_ERROR = "TRANSIENT_PROVIDER_ERROR"


#: Para onde a falha volta. ``None`` significa decisão humana.
DESTINO: Mapping[FailureClass, str | None] = {
    FailureClass.SPEC_ERROR: "mission_compiler",
    FailureClass.OWNERSHIP_ERROR: "ownership_discovery",
    FailureClass.INFRASTRUCTURE_ERROR: "gatekeeper",
    FailureClass.BASELINE_ERROR: "baseline_reconciliation",
    FailureClass.MERIT_FAILURE: "writer_or_harvest",
    FailureClass.REVIEW_FINDING: "counterproof_then_writer",
    FailureClass.TIMEOUT: "process_inspection",
    FailureClass.AUTHORIZATION_BLOCK: None,
    FailureClass.TRANSIENT_PROVIDER_ERROR: "retry_once",
}

#: Quantas vezes o harness pode relançar um writer para esta classe.
MAX_RETRIES: Mapping[FailureClass, int] = {
    FailureClass.SPEC_ERROR: 0,
    FailureClass.OWNERSHIP_ERROR: 0,
    FailureClass.INFRASTRUCTURE_ERROR: 0,
    FailureClass.BASELINE_ERROR: 0,
    FailureClass.MERIT_FAILURE: 2,
    FailureClass.REVIEW_FINDING: 2,
    FailureClass.TIMEOUT: 1,
    FailureClass.AUTHORIZATION_BLOCK: 0,
    FailureClass.TRANSIENT_PROVIDER_ERROR: 1,
}


def relanca_writer(classe: FailureClass) -> bool:
    """Um novo writer nunca conserta um gate inexistente."""

    return MAX_RETRIES[classe] > 0


@dataclass
class HarnessFailure(Exception):
    """Falha com classe, destino e reprodução.

    NÃO é frozen: uma exceção precisa aceitar ``__traceback__``, e o unittest
    (entre outros) escreve nesse atributo ao coletar o erro. Congelar a classe
    fazia `raise` funcionar e `assertRaises` explodir com FrozenInstanceError.
    """

    classe: FailureClass
    resumo: str
    detalhe: str = ""
    reproducao: str = ""
    evidencia: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - representação
        return f"[{self.classe.value}] {self.resumo}"

    @property
    def destino(self) -> str | None:
        return DESTINO[self.classe]

    @property
    def permite_retry(self) -> bool:
        return relanca_writer(self.classe)

    def as_dict(self) -> dict[str, Any]:
        return {
            "classe": self.classe.value,
            "resumo": self.resumo,
            "detalhe": self.detalhe,
            "reproducao": self.reproducao,
            "destino": self.destino,
            "permite_retry": self.permite_retry,
            "max_retries": MAX_RETRIES[self.classe],
            "evidencia": self.evidencia,
        }


# --- pytest -----------------------------------------------------------------
# https://docs.pytest.org/en/stable/reference/exit-codes.html
#   0 tudo passou · 1 teste falhou · 2 interrompido · 3 erro interno
#   4 ERRO DE USO (argumento/caminho inválido) · 5 nenhum teste coletado
_PYTEST_SPEC_EXITS = {4, 5}
_PYTEST_MERIT_EXITS = {1}
_PYTEST_INFRA_EXITS = {2, 3}


def classify_gate_exit(
    *,
    exit_code: int,
    argv: list[str] | tuple[str, ...] = (),
    stdout: str = "",
    stderr: str = "",
) -> FailureClass:
    """Traduz o exit de um gate na classe correta.

    A regra mais importante: ``exit 4`` e ``exit 5`` do pytest são falhas de
    ESPECIFICAÇÃO. O arquivo não existe, ou nenhum teste foi coletado — em
    ambos os casos quem errou foi quem escreveu a missão, não o candidato.
    """

    if exit_code == 0:
        raise ValueError("exit 0 não é falha")
    texto = f"{stdout}\n{stderr}".lower()
    argv_texto = " ".join(argv)
    e_pytest = "pytest" in argv_texto

    # A SEMÂNTICA DO RUNNER VEM PRIMEIRO. Marcadores de texto só refinam o que o
    # exit code deixou ambíguo.
    #
    # Um teste que falha imprimindo "expected usage: volc [...]" no diff é um
    # teste vermelho legítimo — MERIT_FAILURE. Deixar o texto decidir antes do
    # exit transformava a saída do candidato em veredito sobre a missão.
    if e_pytest:
        if exit_code in _PYTEST_SPEC_EXITS:
            return FailureClass.SPEC_ERROR
        if exit_code in _PYTEST_INFRA_EXITS:
            return FailureClass.INFRASTRUCTURE_ERROR
        if exit_code in _PYTEST_MERIT_EXITS:
            # Exit 1 é teste vermelho. Só um erro de coleta — que o pytest
            # reporta como ERROR, não FAILED — muda isso.
            if "error collecting" in texto or "errors during collection" in texto:
                return FailureClass.SPEC_ERROR
            return FailureClass.MERIT_FAILURE

    # Runner sem semântica conhecida: aí sim o texto ajuda.
    marcadores_infra = (
        "err_module_not_found", "cannot find package", "command not found",
        "no such file or directory: '/",
    )
    if any(m in texto for m in marcadores_infra):
        return FailureClass.INFRASTRUCTURE_ERROR
    marcadores_spec = (
        "file or directory not found", "no tests ran",
        "error: unrecognized arguments", "unrecognized option",
    )
    if any(m in texto for m in marcadores_spec):
        return FailureClass.SPEC_ERROR
    return FailureClass.MERIT_FAILURE


_TRANSIENTES = (
    "503",
    "unavailable",
    "rate limit",
    "429",
    "temporarily",
    "connection reset",
    "timed out reading",
)


def classify_exception(exc: BaseException) -> FailureClass:
    """Classifica erro de provider ou de execução."""

    if isinstance(exc, HarnessFailure):
        return exc.classe
    texto = str(exc).lower()
    if isinstance(exc, TimeoutError) or "excedeu" in texto or "timeout" in texto:
        return FailureClass.TIMEOUT
    if "permissionerror" in texto or "fora do escopo autorizado" in texto:
        return FailureClass.OWNERSHIP_ERROR
    if "saiu do ownership" in texto:
        return FailureClass.OWNERSHIP_ERROR
    if any(marcador in texto for marcador in _TRANSIENTES):
        return FailureClass.TRANSIENT_PROVIDER_ERROR
    return FailureClass.MERIT_FAILURE
