"""Um cluster Postgres descartavel para a suite de contrato do deposito.

## Por que um cluster proprio, e nunca o Supabase oficial

`database.agenciavolc.com.br` e a autoridade operacional. Uma suite que
reivindica, vence lease e cancela trabalho nao pode tocar nele, e "cuidado ao
rodar" nao e um controle. O cluster nasce em `mktemp -d`, escuta so num socket
unix dentro dele, e morre no fim da sessao.

## Fail-closed

`VOLC_EXIGIR_POSTGRES=1` transforma "nao consegui subir o cluster" em FALHA, e
nao em `skip`. Sem essa variavel o skip aparece — mas ele e um skip VISIVEL, com
motivo, e nunca um teste verde. O gate oficial define a variavel; a maquina de
quem nao tem `initdb` continua conseguindo rodar o resto da suite.

⚠️ `LC_ALL=C` nao e enfeite: sem ela o Postgres 16 do Homebrew no macOS morre no
arranque com "postmaster became multithreaded during startup". O script
`scripts/provar-ciclo-v11_03.sh` ja carregava essa cicatriz.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "supabase" / "migrations" / "v11_03_execucao_criativa.sql"

#: Motivo textual quando o cluster nao pode nascer. Nunca `None` silencioso.
_MOTIVO: str | None = None


def _exigido() -> bool:
    return os.environ.get("VOLC_EXIGIR_POSTGRES", "").strip() in {"1", "true", "sim"}


def _faltando() -> str | None:
    for b in ("initdb", "pg_ctl", "psql"):
        if shutil.which(b) is None:
            return f"binario `{b}` ausente no PATH"
    try:
        import psycopg  # noqa: F401, PLC0415
    except ImportError:
        return "driver `psycopg` ausente neste interpretador"
    if not MIGRATION.is_file():
        return f"migration ausente em {MIGRATION.name}"
    return None


@pytest.fixture(scope="session")
def dsn_postgres() -> str:
    """DSN de um cluster que nasce e morre nesta sessao, com a v11_03 aplicada."""
    global _MOTIVO
    _MOTIVO = _faltando()
    if _MOTIVO:
        if _exigido():
            pytest.fail(
                f"VOLC_EXIGIR_POSTGRES esta ligado e o cluster nao pode nascer: {_MOTIVO}"
            )
        pytest.skip(f"sem Postgres descartavel: {_MOTIVO}")

    base = Path(tempfile.mkdtemp(prefix="volc-deposito-pg."))
    dados, socket = base / "d", base / "s"
    socket.mkdir(parents=True, exist_ok=True)
    ambiente = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def rodar(*args: str, **kw) -> subprocess.CompletedProcess:
        return subprocess.run(args, env=ambiente, capture_output=True, text=True, **kw)

    try:
        r = rodar("initdb", "-D", str(dados), "-U", "postgres",
                  "--encoding=UTF8", "--locale=C")
        if r.returncode != 0:
            raise RuntimeError(f"initdb falhou: {r.stderr[-400:]}")
        r = rodar("pg_ctl", "-D", str(dados), "-l", str(base / "pg.log"),
                  "-o", f"-k {socket} -h ''", "-w", "start")
        if r.returncode != 0:
            raise RuntimeError(f"pg_ctl start falhou: {r.stderr[-400:]}")

        psql_env = {**ambiente, "PGHOST": str(socket), "PGUSER": "postgres",
                    "PGDATABASE": "postgres"}
        # Papeis que a migration referencia em GRANT/RLS. Nascem aqui porque num
        # cluster virgem eles nao existem — no Supabase, existem.
        r = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-c",
             "create role anon nologin; create role authenticated nologin;"
             " create role service_role nologin bypassrls;"],
            env=psql_env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"papeis: {r.stderr[-400:]}")
        r = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f", str(MIGRATION)],
            env=psql_env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"v11_03: {r.stderr[-800:]}")

        yield f"host={socket} user=postgres dbname=postgres"
    finally:
        subprocess.run(["pg_ctl", "-D", str(dados), "-m", "immediate", "stop"],
                       env=ambiente, capture_output=True)
        shutil.rmtree(base, ignore_errors=True)
