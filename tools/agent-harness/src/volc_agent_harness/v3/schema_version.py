"""Versionamento do schema de missão e caminho de migração.

Uma missão do V2 não pode atravessar o compilador V3 em silêncio: ela não declara
``acceptance_ids``, não declara ``ownership_envelope`` e não declara
``produced_paths``. Sem esses campos o compilador não tem como recusar um gate
quebrado nem reconciliar ownership — ou seja, o V3 daria uma falsa sensação de
proteção.

Ela falha com código explícito e instrução de migração.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .failures import FailureClass, HarnessFailure

SCHEMA_VERSION_ATUAL = 3
CAMPO = "mission_schema_version"

#: O que a v3 exige e a v2 não tinha.
CAMPOS_V3_OBRIGATORIOS = ("acceptance_ids", "ownership_envelope")


@dataclass(frozen=True)
class MigrationHint:
    campo: str
    porque: str
    exemplo: str

    def as_dict(self) -> dict[str, Any]:
        return {"campo": self.campo, "porque": self.porque, "exemplo": self.exemplo}


DICAS = {
    "acceptance_ids": MigrationHint(
        "acceptance_ids",
        "sem aceite atômico o compilador não sabe o que a missão fecha nem o que "
        "precisa continuar verde como regressão",
        '"acceptance_ids": ["P04-T09-A2", "P04-T09-A3"]',
    ),
    "ownership_envelope": MigrationHint(
        "ownership_envelope",
        "o envelope é a fronteira entre 'esqueci um arquivo' e 'estou ampliando "
        "escopo'; sem ele a descoberta de ownership não tem contra o que comparar",
        '"ownership_envelope": ["volc_ads", "backend/app/trafego"]',
    ),
    "produced_paths": MigrationHint(
        "produced_paths",
        "gate que cita arquivo ainda inexistente só é legítimo se a missão "
        "declarar que vai produzi-lo",
        '"produced_paths": [{"path": "backend/tests/test_novo.py", "required": true}]',
    ),
}


def detect_version(mission: Mapping[str, Any]) -> int:
    return int(mission.get(CAMPO, 2))


def assert_compilable(mission: Mapping[str, Any]) -> int:
    """Recusa missão que o compilador V3 não consegue proteger de verdade."""

    versao = detect_version(mission)
    if versao > SCHEMA_VERSION_ATUAL:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            f"missão declara schema {versao}, mais novo que o suportado ({SCHEMA_VERSION_ATUAL})",
            detalhe=str(mission.get("mission_id", "?")),
        )
    if versao == SCHEMA_VERSION_ATUAL:
        faltando = [c for c in CAMPOS_V3_OBRIGATORIOS if not mission.get(c)]
        if faltando:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                "missão declara schema 3 mas não traz os campos que o schema 3 exige",
                detalhe=", ".join(faltando),
                reproducao="; ".join(DICAS[c].exemplo for c in faltando if c in DICAS),
                evidencia={"migration_hints": [DICAS[c].as_dict() for c in faltando if c in DICAS]},
            )
        return versao

    # Schema 2: legado. Não passa pelo compilador em silêncio.
    faltando = [c for c in CAMPOS_V3_OBRIGATORIOS if not mission.get(c)]
    raise HarnessFailure(
        FailureClass.SPEC_ERROR,
        f"missão no schema {versao} não pode usar o compilador V3 sem migração",
        detalhe=(
            f"{mission.get('mission_id', '?')} precisa declarar: " + ", ".join(faltando)
        ),
        reproducao=(
            f'adicione "{CAMPO}": {SCHEMA_VERSION_ATUAL} e os campos exigidos; '
            "ou execute pelo caminho legado, que não oferece as guardas do V3"
        ),
        evidencia={
            "schema_atual": versao,
            "schema_alvo": SCHEMA_VERSION_ATUAL,
            "migration_hints": [DICAS[c].as_dict() for c in faltando if c in DICAS],
        },
    )


def migration_report(missions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Plano de migração das missões existentes."""

    pronto, precisa = [], []
    for nome, m in missions.items():
        try:
            assert_compilable(m)
            pronto.append(nome)
        except HarnessFailure as exc:
            precisa.append({
                "mission": nome,
                "schema": detect_version(m),
                "faltando": exc.detalhe,
                "como_migrar": exc.reproducao,
            })
    return {
        "schema_alvo": SCHEMA_VERSION_ATUAL,
        "prontas": sorted(pronto),
        "precisam_migrar": precisa,
        "total": len(missions),
    }
