"""Chaves determinísticas da observação, reproduzíveis byte a byte em PostgreSQL.

A serialização NÃO é JSON: o `jsonb::text` do Postgres ordena chaves e espaça diferente
do `json.dumps` do Python, e a chave precisa ser recalculada pelo banco (o escritor não
escolhe a própria chave). Por isso o texto canônico é uma lista de campos separados por
caracteres de controle ASCII que o contrato proíbe dentro dos campos:

- US (0x1F) separa campos;
- RS (0x1E) separa pares de dimensão;
- GS (0x1D) separa nome e valor de uma dimensão;
- grão: elementos ordenados por ponto de código, unidos por vírgula (vocabulário fechado, sem vírgula);
- instantes: UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ` (microssegundos, como o `timestamptz`).

Espelho SQL: `dil_obs._chave_natural`, `dil_obs._chave_base`, `dil_obs._chave_reafirmacao`
em `migrations_candidatas/dil_obs_0001_schema_observacao.sql`. O teste
`test_schema_pg_observacao.py::test_chaves_python_iguais_as_do_postgres` prova a igualdade.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable, Optional

US = "\x1f"
RS = "\x1e"
GS = "\x1d"

PREFIXO_NATURAL = "dil_obs.chave_natural.v1"
PREFIXO_BASE = "dil_obs.chave_idempotencia.v1"
PREFIXO_REAFIRMACAO = "dil_obs.reafirmacao.v1"


def sha256_texto(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def instante_canonico(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def tem_controle(s: str) -> bool:
    """Caracteres proibidos em campos de identidade (espelho SQL: `~ '[\\x01-\\x1f\\x7f]'`)."""
    return any(ord(c) < 32 or ord(c) == 127 for c in s)


def chave_natural(
    *,
    fonte: str,
    conta: str,
    entidade_tipo: str,
    entidade_id: str,
    grao: Iterable[str],
    dimensoes: Iterable[tuple[str, str]],
    metrica: str,
    value_kind: Optional[str],
    janela_inicio: datetime,
    janela_fim: datetime,
    timezone_nome: str,
) -> str:
    """Identifica 'o mesmo fato' entre versões. Valor, status, moeda e relógios de conhecimento ficam fora."""
    grao_txt = ",".join(sorted(set(grao)))
    dims_txt = RS.join(f"{k}{GS}{v}" for k, v in sorted(dimensoes))
    campos = [
        PREFIXO_NATURAL,
        fonte,
        conta,
        entidade_tipo,
        entidade_id,
        grao_txt,
        dims_txt,
        metrica,
        value_kind or "",
        instante_canonico(janela_inicio),
        instante_canonico(janela_fim),
        timezone_nome,
    ]
    return sha256_texto(US.join(campos))


def chave_base(
    *, chave_natural_hex: str, payload_sha256: str, schema_version: str, coletor_nome: str, coletor_versao: str
) -> str:
    """Chave de idempotência de uma LEITURA: o mesmo fato, lido do mesmo payload pelo mesmo coletor.

    Repetir a leitura (retry, cron que relê o mesmo dado) dá a mesma chave → no-op.
    Payload diferente para a mesma janela → outra chave → nova versão (restatement).
    Reprocessar o mesmo payload com outra versão do coletor/esquema → outra chave → nova versão.
    """
    return sha256_texto(US.join([PREFIXO_BASE, chave_natural_hex, payload_sha256, schema_version, coletor_nome, coletor_versao]))


def chave_reafirmacao(*, chave_base_hex: str, available_at: datetime) -> str:
    """Chave de uma reafirmação: uma leitura antiga volta a ser verdade depois de outra versão (A→B→A)."""
    return sha256_texto(US.join([PREFIXO_REAFIRMACAO, chave_base_hex, instante_canonico(available_at)]))
