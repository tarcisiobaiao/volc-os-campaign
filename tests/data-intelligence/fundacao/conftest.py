"""Fixtures da fundação (thread A): fábrica de observações e PostgreSQL 16 descartável.

O PostgreSQL sobe num diretório temporário próprio, só por socket unix (`listen_addresses=''`),
porta alta aleatória, `fsync=off`, e é derrubado no teardown. Nada de rede, nada de produção.
Se os binários não existirem ou o servidor não subir, os testes que dependem dele são
marcados como SKIP com o motivo (nunca passam em silêncio).

Armadilha medida: no macOS o postmaster aborta com "postmaster became multithreaded during
startup" se `LC_ALL` não estiver definido; por isso todo subprocesso roda com `LC_ALL=C`.
"""
from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

from volc_dil.fundacao.observacao import Coletor, EntidadeRef, Observacao

RAIZ = Path(__file__).resolve().parents[3]
MIGRACOES = RAIZ / "experiments" / "data-intelligence-lab" / "migrations_candidatas"
BINARIOS_PG = Path(os.environ.get("DIL_PG_BIN", "/opt/homebrew/bin"))

BRT = timezone(timedelta(hours=-3))
DIA = datetime(2026, 10, 14, tzinfo=BRT)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def nova_obs(**kw) -> Observacao:
    """Observação válida (custo Google Ads, campanha-dia, BRL) com sobrescritas pontuais.

    `payload=b"..."` recalcula `payload_sha256`/`payload_ref`; `entidade_id=` troca só o id.
    """
    payload = kw.pop("payload", b'{"cost_micros": 5000000}')
    ent_id = kw.pop("entidade_id", "111")
    base = dict(
        fonte="google_ads",
        conta="1234567890",
        entidade=EntidadeRef("campaign", ent_id),
        grao=("campaign", "day"),
        metrica="cost",
        valor=5_000_000,
        unidade="micros",
        moeda="BRL",
        janela_inicio=DIA,
        janela_fim=DIA + timedelta(days=1),
        timezone="America/Sao_Paulo",
        observed_at=DIA + timedelta(days=1, hours=4),
        available_at=DIA + timedelta(days=1, hours=4, minutes=5),
        ingested_at=DIA + timedelta(days=1, hours=4, minutes=6),
        run_id="run-1",
        lote_id="lote-1",
        payload_sha256=sha(payload),
        payload_ref=f"sha256:{sha(payload)}",
        schema_version="google_ads.gaql.campaign_day.v1",
        coletor=Coletor("coleta_canonica_google_ads", "1.0.0"),
        status="observed",
    )
    base.update(kw)
    return Observacao(**base)


@pytest.fixture
def obs():
    return nova_obs


# --------------------------------------------------------------------------- PostgreSQL
class ErroPsql(RuntimeError):
    def __init__(self, rc: int, saida: str, erro: str) -> None:
        super().__init__(f"psql rc={rc}: {erro.strip()}")
        self.rc, self.saida, self.erro = rc, saida, erro


@dataclass
class ClusterPG:
    raiz: Path
    porta: int

    @property
    def socket(self) -> str:
        return str(self.raiz)

    @staticmethod
    def env() -> dict:
        e = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        e.update(LC_ALL="C", LANG="C", PGCONNECT_TIMEOUT="5")
        return e

    def psql(self, sql: str, *, db: str = "postgres", papel: Optional[str] = None, check: bool = True) -> str:
        """Roda SQL (via stdin, ON_ERROR_STOP) como superusuário `postgres` ou, com `papel`, após SET ROLE."""
        corpo = (f"SET ROLE {papel};\n" if papel else "") + sql
        p = subprocess.run(
            [str(BINARIOS_PG / "psql"), "-h", self.socket, "-p", str(self.porta), "-U", "postgres", "-d", db,
             "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
            input=corpo, capture_output=True, text=True, env=self.env(), timeout=120,
        )
        if check and p.returncode != 0:
            raise ErroPsql(p.returncode, p.stdout, p.stderr)
        return p.stdout.strip() if p.returncode == 0 else ""

    def falha(self, sql: str, *, db: str = "postgres", papel: Optional[str] = None) -> str:
        """Roda SQL que DEVE falhar; devolve a mensagem de erro (falha o teste se passar)."""
        try:
            self.psql(sql, db=db, papel=papel)
        except ErroPsql as e:
            return e.erro
        raise AssertionError(f"SQL deveria falhar e passou: {sql[:200]}")

    def aplicar(self, arquivo: str, *, db: str) -> None:
        self.psql((MIGRACOES / arquivo).read_text(encoding="utf-8"), db=db)

    def novo_banco(self, nome: str) -> str:
        self.psql(f"DROP DATABASE IF EXISTS {nome}; CREATE DATABASE {nome} TEMPLATE template0;")
        return nome

    def parar(self) -> None:
        subprocess.run([str(BINARIOS_PG / "pg_ctl"), "-D", str(self.raiz / "data"), "-m", "immediate", "stop"],
                       capture_output=True, env=self.env(), timeout=60)
        shutil.rmtree(self.raiz, ignore_errors=True)


def subir_cluster() -> ClusterPG:
    """Sobe um cluster descartável ou levanta pytest.skip com o motivo exato."""
    for b in ("initdb", "pg_ctl", "psql", "postgres"):
        if not (BINARIOS_PG / b).exists():
            pytest.skip(f"PostgreSQL descartável indisponível: binário {BINARIOS_PG / b} não existe")
    # caminho curto: o socket unix do macOS tem limite de ~103 bytes
    raiz = Path(tempfile.mkdtemp(prefix="dilpg", dir="/tmp" if Path("/tmp").is_dir() else None))
    env = ClusterPG.env()
    r = subprocess.run([str(BINARIOS_PG / "initdb"), "-D", str(raiz / "data"), "-U", "postgres", "-A", "trust",
                        "--no-locale", "-E", "UTF8"], capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        shutil.rmtree(raiz, ignore_errors=True)
        pytest.skip(f"PostgreSQL descartável indisponível: initdb falhou: {r.stderr.strip()[:300]}")
    porta = random.SystemRandom().randint(40000, 60000)
    opcoes = f"-k {raiz} -c listen_addresses= -p {porta} -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
    r = subprocess.run([str(BINARIOS_PG / "pg_ctl"), "-D", str(raiz / "data"), "-o", opcoes, "-l", str(raiz / "log"),
                        "-w", "-t", "60", "start"], capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        log = (raiz / "log").read_text(errors="replace")[-500:] if (raiz / "log").exists() else ""
        subprocess.run([str(BINARIOS_PG / "pg_ctl"), "-D", str(raiz / "data"), "-m", "immediate", "stop"],
                       capture_output=True, env=env)
        shutil.rmtree(raiz, ignore_errors=True)
        pytest.skip(f"PostgreSQL descartável não subiu: {log.strip()}")
    c = ClusterPG(raiz, porta)
    # papéis que o Supabase traz prontos; aqui são simulados, com o default ACL perigoso que o
    # Supabase usa (v8_01 M3): tudo que `postgres` criar nasce aberto para anon/authenticated.
    c.psql(
        "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS;"
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT ALL ON TABLES TO anon, authenticated;"
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT ALL ON FUNCTIONS TO anon, authenticated;"
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT ALL ON SEQUENCES TO anon, authenticated;"
    )
    return c


@pytest.fixture(scope="session")
def cluster_pg():
    c = subir_cluster()
    try:
        yield c
    finally:
        c.parar()


@pytest.fixture(scope="session")
def banco_obs(cluster_pg):
    """Banco com a migration 0001 aplicada uma vez para a sessão (testes não destrutivos)."""
    db = cluster_pg.novo_banco("dil_sessao")
    cluster_pg.aplicar("dil_obs_0001_schema_observacao.sql", db=db)
    return db
