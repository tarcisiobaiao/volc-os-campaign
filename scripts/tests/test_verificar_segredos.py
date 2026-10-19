from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verificar_segredos", ROOT / "scripts" / "verificar_segredos.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_service_role_literal_longo_continua_bloqueado() -> None:
    padrao = MODULE.PATTERNS["hardcoded-service-role"]
    amostra = (
        b"SUPABASE_"
        + b'SERVICE_ROLE_KEY="'
        + b"valor-literal-muito-longo-que-nao-pode-entrar"
        + b'"'
    )
    assert padrao.search(amostra)


def test_expansao_de_ambiente_nao_e_redigida_como_segredo() -> None:
    padrao = MODULE.PATTERNS["hardcoded-service-role"]
    assert not padrao.search(
        b'SUPABASE_SERVICE_ROLE_KEY="${SERVICE_ROLE_KEY:?SERVICE_ROLE_KEY ausente no ambiente}"'
    )

