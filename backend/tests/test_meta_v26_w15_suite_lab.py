"""Roda a suíte `tools/freedom-lab/db/suites/v26_w15.sh` com um stub FIEL do lab.sh.

No Mac, o `lab.sh` define P e PA como `docker exec -i ... psql`. O docker
repassa ao container o stdin inteiro de quem chamou, mesmo com `-c`. Uma
chamada a P/PA dentro de `while read ... done <<< "$lista"` engole as linhas
seguintes, e o loop roda uma vez só. O stub daqui reproduz isso com
`cat | psql`: P e PA consomem todo o stdin, leiam SQL dele ou não.

A base imita o `recriar-prod`: a v13_01 entra por dump schema-only, então
`cofre_gaveta` e `cofre_tipo` chegam vazias.

Prova num PostgreSQL DESCARTÁVEL (`VOLC_PG_DESCARTAVEL`, DSN de superusuário
em forma de palavras-chave). Sem a variável o teste é PULADO, e pulado não é
prova. A prova oficial continua sendo o `lab.sh recriar-prod` no Mac.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SUITE = RAIZ / "tools" / "freedom-lab" / "db" / "suites" / "v26_w15.sh"
V13 = RAIZ / "supabase" / "migrations" / "v13_01_cofre_de_ativos.sql"
DSN = os.environ.get("VOLC_PG_DESCARTAVEL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN or not all(shutil.which(b) for b in ("psql", "pg_dump", "bash")),
    reason="sem VOLC_PG_DESCARTAVEL/psql/pg_dump: suite do lab nao executada (lacuna, nao aprovacao)",
)

PAPEIS = (
    "DO $$BEGIN "
    "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF; "
    "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; "
    "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF; "
    "END$$; CREATE EXTENSION IF NOT EXISTS pgcrypto;"
)

# Helpers com a mesma interface do lab.sh. P e PA engolem o stdin como o
# `docker exec -i` do Mac.
STUB = r"""
set -u
OKS=0; NAOS=0
P()  { cat | psql "$W15_DSN" -X -q "$@"; }
PA() { cat | psql "$W15_DSN" -X -q "$@"; }
ok()  { OKS=$((OKS+1)); echo "  ok   $1"; }
nao() { NAOS=$((NAOS+1)); echo "  FALHOU $1"; }
eq()  { [ "$1" = "$2" ] && ok "$3" || nao "$3 (obtido: $1 | esperado: $2)"; }
"""


def _psql(dsn: str, *args: str, entrada: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["psql", dsn, "-X", "-q", "-v", "ON_ERROR_STOP=1", *args],
                          input=entrada, capture_output=True, text=True)


@pytest.fixture()
def base_schema_only(tmp_path):
    """Banco com a v13_01 vinda de dump schema-only, como no recriar-prod."""
    sufixo = uuid.uuid4().hex[:10]
    ref, alvo = f"w15_ref_{sufixo}", f"w15_lab_{sufixo}"
    admin = f"{DSN} dbname=postgres"
    for nome in (ref, alvo):
        p = _psql(admin, "-c", f"CREATE DATABASE {nome}")
        assert p.returncode == 0, p.stderr
    try:
        dsn_ref, dsn_alvo = f"{DSN} dbname={ref}", f"{DSN} dbname={alvo}"
        p = _psql(dsn_ref, "-c", PAPEIS, "-f", str(V13))
        assert p.returncode == 0, p.stderr[-2000:]
        dump = subprocess.run(["pg_dump", dsn_ref, "--schema-only"], capture_output=True, text=True)
        assert dump.returncode == 0, dump.stderr
        p = _psql(dsn_alvo, "-c", PAPEIS)
        assert p.returncode == 0, p.stderr
        p = _psql(dsn_alvo, entrada=dump.stdout)
        assert p.returncode == 0, p.stderr[-2000:]
        p = _psql(dsn_alvo, "-Atc", "SELECT (SELECT count(*) FROM public.cofre_gaveta) || '|' || "
                                    "(SELECT count(*) FROM public.cofre_tipo)")
        assert p.stdout.strip() == "0|0", "a base precisa chegar sem dados de referencia"
        yield dsn_alvo
    finally:
        for nome in (alvo, ref):
            _psql(admin, "-c", f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")


def _rodar_stub(corpo: str, dsn: str, tmp_path: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "stub.sh"
    script.write_text(STUB + corpo, encoding="utf-8")
    env = {**os.environ, "W15_DSN": dsn}
    return subprocess.run(["bash", str(script)], cwd=RAIZ, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=300)


def test_o_stub_engole_o_stdin_como_o_docker_exec(base_schema_only, tmp_path):
    # Sem isto, o teste abaixo passaria com uma suíte quebrada no Mac.
    p = _rodar_stub('n=0; while read -r x; do n=$((n+1)); P -Atc "select 1" >/dev/null; '
                    'done <<< "$(printf "a\\nb\\nc")"; echo "lidas=$n"\n',
                    base_schema_only, tmp_path)
    assert p.stdout.strip().endswith("lidas=1"), p.stdout + p.stderr


def test_suite_v26_w15_passa_no_stub_fiel(base_schema_only, tmp_path):
    corpo = (
        f'RAIZ="{RAIZ}"; RECIBOS="{tmp_path / "recibos"}"\n'
        "MIGRATION=supabase/migrations/v26_01_meta_insight_latest_completa.sql\n"
        "ROLLBACK=supabase/migrations/v26_01_rollback.sql\n"
        f'source "{SUITE}"\n'
        'echo "ok=$OKS falhou=$NAOS"\n'
    )
    p = _rodar_stub(corpo, base_schema_only, tmp_path)
    saida = p.stdout + p.stderr
    m = re.search(r"ok=(\d+) falhou=(\d+)\s*$", p.stdout)
    assert m, saida
    assert m.group(2) == "0", saida
    assert "os 6 arquivos foram percorridos" in saida, saida
    for fid in ("a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "d3"):
        assert f"semente w15-{fid}: 1 linha" in saida, saida
    assert int(m.group(1)) == 40, saida
