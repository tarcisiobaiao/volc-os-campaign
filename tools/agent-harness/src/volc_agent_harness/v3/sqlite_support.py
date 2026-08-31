"""Conexão e evolução de schema SQLite, compartilhadas pelo harness.

Dois bancos locais são escritos por lanes concorrentes — o registry de worktrees
e o evidence ledger — e ambos já erraram do mesmo jeito.

**WAL imposto.** ``PRAGMA journal_mode=WAL`` pede lock exclusivo, e o busy
handler do SQLite não é acionado em todos os caminhos dessa troca. Impor o
pragma a cada conexão fazia duas inicializações simultâneas colidirem com
``OperationalError: database is locked`` — era isso que deixava a prova de
inicialização concorrente do registry falhar em ~40% das execuções. Aqui o modo
é CONSULTADO e só trocado quando difere, com repetição limitada.

**``CREATE TABLE IF NOT EXISTS`` como migração.** Ele não faz nada quando a
tabela já existe — inclusive quando existe com o schema errado. Um banco criado
antes de uma coluna nova continuava velho e quebrava no primeiro ``INSERT``. A
evolução aqui é por INSPEÇÃO explícita (``PRAGMA table_info``), nunca por
``try/except OperationalError``: capturar a exceção esconde a diferença entre
"a coluna já existe" e "o banco está corrompido".

Este módulo é API interna PÚBLICA. O registry importava ``_conectar`` privado do
ledger; acoplamento a nome privado entre módulos é dívida que ninguém vê até
alguém renomear.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence

from .failures import FailureClass, HarnessFailure

#: Tentativas de negociar o WAL antes de seguir sem ele.
_TENTATIVAS_WAL = 12


def conectar(path: Path, *, timeout: float = 30.0) -> sqlite3.Connection:
    """Conexão com transação manual, busy_timeout e WAL negociado.

    ``isolation_level=None`` porque quem controla a transação é o chamador: o
    BEGIN implícito do ``sqlite3`` só dispara no primeiro DML, e um SELECT de
    verificação viria ANTES dele — deixando uma janela real entre checar e
    reivindicar. Quem precisa de exclusão escreve ``BEGIN IMMEDIATE`` à mão.
    """

    conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    atual = (conn.execute("PRAGMA journal_mode").fetchone()[0] or "").lower()
    if atual != "wal":
        for tentativa in range(_TENTATIVAS_WAL):
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError:
                time.sleep(0.05 * (tentativa + 1))
        # WAL indisponível não é fatal: o busy_timeout ainda serializa.
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def tabelas(conn: sqlite3.Connection) -> set[str]:
    return {linha[0] for linha in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def colunas(conn: sqlite3.Connection, tabela: str) -> set[str]:
    return {linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")}


def indices(conn: sqlite3.Connection) -> set[str]:
    return {linha[0] for linha in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}


def migrar(
    conn: sqlite3.Connection,
    *,
    tabelas_novas: Sequence[tuple[str, str]] = (),
    colunas_novas: Sequence[tuple[str, str, str]] = (),
    indices_novos: Sequence[tuple[str, str, str, Sequence[str]]] = (),
    obrigatorias: Sequence[tuple[str, Iterable[str]]] = (),
) -> list[str]:
    """Evolui o banco de forma idempotente, preservando linhas.

    ``tabelas_novas``  — ``(nome, DDL)``, criadas só quando ausentes.
    ``colunas_novas``  — ``(tabela, coluna, tipo)``, por ``ALTER TABLE``.
    ``indices_novos``  — ``(nome, tabela, DDL, colunas exigidas)``; o índice só
                         nasce DEPOIS que as colunas dele existem, senão a
                         criação derruba a inicialização inteira.
    ``obrigatorias``   — ``(tabela, colunas)`` que precisam existir para o banco
                         ser considerado migrável. Se faltarem e não estiverem em
                         ``colunas_novas``, o schema é incompatível: falha tipada,
                         e NUNCA apagamos o banco.

    Devolve a lista do que foi aplicado. Segunda chamada devolve ``[]``.
    """

    conn.execute("BEGIN IMMEDIATE")
    try:
        aplicadas: list[str] = []
        existentes = tabelas(conn)

        for nome, ddl in tabelas_novas:
            if nome not in existentes:
                conn.execute(ddl)
                aplicadas.append(f"tabela:{nome}")
                existentes.add(nome)

        for tabela, coluna, tipo in colunas_novas:
            if tabela not in existentes:
                continue
            if coluna not in colunas(conn, tabela):
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
                aplicadas.append(f"coluna:{tabela}.{coluna}")

        for tabela, exigidas in obrigatorias:
            if tabela not in existentes:
                continue
            faltando = sorted(set(exigidas) - colunas(conn, tabela))
            if faltando:
                conn.execute("ROLLBACK")
                raise HarnessFailure(
                    FailureClass.INFRASTRUCTURE_ERROR,
                    "schema local incompatível e não migrável automaticamente",
                    detalhe=f"{tabela} sem: {', '.join(faltando)}",
                    reproducao=(
                        "inspecione o banco e migre à mão; o harness não apaga "
                        "banco para 'consertar' schema"),
                    evidencia={"tabela": tabela, "colunas_faltando": faltando},
                )

        ja_existem = indices(conn)
        for nome, tabela, ddl, exigidas in indices_novos:
            if nome in ja_existem or tabela not in existentes:
                continue
            if set(exigidas) - colunas(conn, tabela):
                continue                     # colunas ainda não existem: adia
            conn.execute(ddl)
            aplicadas.append(f"indice:{nome}")

        conn.execute("COMMIT")
        return aplicadas
    except HarnessFailure:
        raise
    except BaseException:
        conn.execute("ROLLBACK")
        raise
