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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

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


@dataclass(frozen=True)
class Coluna:
    """Forma material de uma coluna. Nome não basta para saber se ela serve."""

    nome: str
    affinity: str
    notnull: bool
    default: str | None
    pk: int

    @property
    def exige_valor(self) -> bool:
        """NOT NULL sem default e fora da PK: todo INSERT precisa preenchê-la."""

        return self.notnull and self.default is None and self.pk == 0


def estrutura(conn: sqlite3.Connection, tabela: str) -> dict[str, Coluna]:
    """``PRAGMA table_info`` completo, não só os nomes.

    Validar nome deixava passar o pior caso: a coluna existe, o boot fica verde
    e o primeiro ``INSERT`` estoura com ``NOT NULL constraint failed``. Falha
    adiada é pior que falha na inicialização, porque acontece longe da causa.
    """

    achadas: dict[str, Coluna] = {}
    for _cid, nome, tipo, notnull, default, pk in conn.execute(
            f"PRAGMA table_info({tabela})"):
        achadas[nome] = Coluna(
            nome=nome, affinity=_affinity(tipo or ""), notnull=bool(notnull),
            default=default, pk=int(pk))
    return achadas


def _affinity(tipo: str) -> str:
    """Regra de afinidade do SQLite, não igualdade de string.

    O SQLite normaliza tipos: ``VARCHAR(80)``, ``TEXT`` e ``CHARACTER(20)`` têm
    a mesma afinidade. Comparar a string crua recusaria bancos legítimos.
    """

    t = tipo.upper()
    if "INT" in t:
        return "INTEGER"
    if any(m in t for m in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in t or not t:
        return "BLOB"
    if any(m in t for m in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def chave_primaria(conn: sqlite3.Connection, tabela: str) -> tuple[str, ...]:
    return tuple(
        c.nome for c in sorted(
            (c for c in estrutura(conn, tabela).values() if c.pk), key=lambda c: c.pk)
    )


def indices_unicos(conn: sqlite3.Connection, tabela: str) -> set[tuple[str, ...]]:
    """Conjuntos de colunas com unicidade material declarada."""

    saida: set[tuple[str, ...]] = set()
    for linha in conn.execute(f"PRAGMA index_list({tabela})"):
        nome, unico = linha[1], bool(linha[2])
        if not unico:
            continue
        cols = tuple(l[2] for l in conn.execute(f"PRAGMA index_info({nome})") if l[2])
        if cols:
            saida.add(cols)
    return saida


def indices(conn: sqlite3.Connection) -> set[str]:
    return {linha[0] for linha in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}


@dataclass(frozen=True)
class ColunaEsperada:
    """Contrato de UMA coluna. Nome sozinho não diz se ela serve.

    `id TEXT PRIMARY KEY` tem o nome certo e destrói o runtime: `lastrowid`
    devolve o rowid, a PK material fica NULL, e a evidência deixa de ser
    endereçável — com `ok=True` e baseline verde.
    """

    nome: str
    affinity: str
    notnull: bool
    tem_default: bool
    pk: int = 0

    def divergencia(self, real: "Coluna") -> str | None:
        if real.affinity != self.affinity:
            return f"affinity {real.affinity} ≠ {self.affinity}"
        if real.pk != self.pk:
            return f"posição de PK {real.pk} ≠ {self.pk}"
        if real.notnull and not self.notnull and real.default is None:
            return "declarada NOT NULL sem default, mas o harness grava NULL nela"
        if self.notnull and not real.notnull:
            return "aceita NULL onde o contrato exige valor"
        if self.notnull and not self.tem_default and real.default is None \
                and real.pk == 0:
            return None                  # exigida e sempre preenchida por nós
        return None


@dataclass(frozen=True)
class IndiceEsperado:
    """Índice conferido por DEFINIÇÃO, nunca por nome.

    Um índice não-único chamado `idx_evidence_claim_unico` sobre a coluna errada
    passava: o nome existia, a criação do índice correto era pulada, e a
    unicidade material — que é o que torna `complete()` idempotente no banco —
    simplesmente não existia.
    """

    nome: str
    colunas: tuple[str, ...]
    unico: bool


def indices_detalhados(conn: sqlite3.Connection, tabela: str) -> dict[str, tuple]:
    """``(colunas em ordem, é único)`` por nome de índice."""

    saida: dict[str, tuple] = {}
    for linha in conn.execute(f"PRAGMA index_list({tabela})"):
        nome, unico = linha[1], bool(linha[2])
        cols = tuple(l[2] for l in conn.execute(f"PRAGMA index_info({nome})")
                     if l[2] is not None)
        saida[nome] = (cols, unico)
    return saida


def _recusar(conn: sqlite3.Connection, tabela: str, motivo: str,
             evidencia: dict) -> None:
    """Recusa tipada, com o banco INTACTO. Nunca DROP, nunca recreate."""

    if conn.in_transaction:
        conn.execute("ROLLBACK")
    raise HarnessFailure(
        FailureClass.INFRASTRUCTURE_ERROR,
        "schema local incompatível e não migrável automaticamente",
        detalhe=f"{tabela}: {motivo} — {evidencia}",
        reproducao=("inspecione o banco e migre à mão; o harness não apaga nem "
                    "recria banco para 'consertar' schema"),
        evidencia={"tabela": tabela, "motivo": motivo, **evidencia},
    )


def migrar(
    conn: sqlite3.Connection,
    *,
    tabelas_novas: Sequence[tuple[str, str]] = (),
    colunas_novas: Sequence[tuple[str, str, str]] = (),
    indices_novos: Sequence[tuple[str, str, str, Sequence[str]]] = (),
    obrigatorias: Sequence[tuple[str, Iterable[str]]] = (),
    chaves_primarias: Sequence[tuple[str, Sequence[str]]] = (),
    unicidades: Sequence[tuple[str, Sequence[str]]] = (),
    estrutura_esperada: Sequence[tuple[str, Sequence["ColunaEsperada"]]] = (),
    indices_esperados: Sequence[tuple[str, Sequence["IndiceEsperado"]]] = (),
    prova_de_uso: Any = None,
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
                         e NUNCA apagamos o banco. A checagem também recusa
                         coluna NOT NULL sem default que o harness não preenche.
    ``chaves_primarias`` — ``(tabela, colunas da PK)`` esperadas. PK divergente é
                         schema de outro sistema, não versão antiga do nosso.
    ``unicidades``     — ``(tabela, colunas)`` com unicidade material exigida.

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
            atual = estrutura(conn, tabela)
            faltando = sorted(set(exigidas) - set(atual))
            if faltando:
                _recusar(conn, tabela, "colunas ausentes e não migráveis",
                         {"colunas_faltando": faltando})

            # Coluna NOT NULL sem default que NÓS não conhecemos: todo INSERT
            # nosso vai omiti-la e estourar. Era exatamente o "boot verde,
            # primeiro INSERT vermelho".
            intrusas = sorted(
                nome for nome, col in atual.items()
                if col.exige_valor and nome not in set(exigidas)
            )
            if intrusas:
                _recusar(conn, tabela, "coluna NOT NULL sem default que o harness "
                         "não preenche", {"colunas": intrusas})

        for tabela, esperadas in estrutura_esperada:
            if tabela not in existentes:
                continue
            real = estrutura(conn, tabela)
            for coluna in esperadas:
                atual_col = real.get(coluna.nome)
                if atual_col is None:
                    continue          # ausência já é tratada por `obrigatorias`
                divergencia = coluna.divergencia(atual_col)
                if divergencia:
                    _recusar(conn, tabela, f"coluna {coluna.nome}: {divergencia}",
                             {"coluna": coluna.nome, "divergencia": divergencia})

        for tabela, esperados in indices_esperados:
            if tabela not in existentes:
                continue
            reais = indices_detalhados(conn, tabela)
            for indice in esperados:
                if indice.nome not in reais:
                    continue          # ainda vai ser criado pelo laço de índices
                cols, unico = reais[indice.nome]
                if cols != indice.colunas or unico != indice.unico:
                    _recusar(conn, tabela,
                             f"índice {indice.nome} com definição divergente",
                             {"esperado": {"colunas": list(indice.colunas),
                                           "unico": indice.unico},
                              "encontrado": {"colunas": list(cols), "unico": unico}})

        for tabela, pk_esperada in chaves_primarias:
            if tabela not in existentes:
                continue
            atual_pk = chave_primaria(conn, tabela)
            if atual_pk != tuple(pk_esperada):
                _recusar(conn, tabela, "chave primária divergente",
                         {"esperada": list(pk_esperada), "encontrada": list(atual_pk)})

        for tabela, cols_unicas in unicidades:
            if tabela not in existentes:
                continue
            if tuple(cols_unicas) in indices_unicos(conn, tabela):
                continue
            if set(cols_unicas) - set(colunas(conn, tabela)):
                continue                    # sem as colunas, o índice nasce depois
            # As colunas existem e a unicidade não: dá para criar, e o laço de
            # índices logo abaixo faz isso. Nada a recusar aqui.

        ja_existem = indices(conn)
        for nome, tabela, ddl, exigidas in indices_novos:
            if nome in ja_existem or tabela not in existentes:
                continue
            if set(exigidas) - colunas(conn, tabela):
                continue                     # colunas ainda não existem: adia
            conn.execute(ddl)
            aplicadas.append(f"indice:{nome}")

        conn.execute("COMMIT")

        # Prova de PRIMEIRO USO, dentro de SAVEPOINT: o boot só é verde se as
        # operações reais funcionarem sobre a estrutura real. Comparar
        # propriedade a propriedade cobre o que sabemos declarar; a sonda cobre
        # o que esquecemos. Nada dela sobrevive ao rollback.
        if prova_de_uso is not None:
            conn.execute("SAVEPOINT prova_de_uso")
            try:
                prova_de_uso(conn)
            except HarnessFailure:
                conn.execute("ROLLBACK TO prova_de_uso")
                conn.execute("RELEASE prova_de_uso")
                raise
            except Exception as erro:
                conn.execute("ROLLBACK TO prova_de_uso")
                conn.execute("RELEASE prova_de_uso")
                raise HarnessFailure(
                    FailureClass.INFRASTRUCTURE_ERROR,
                    "boot verde não sobrevive ao primeiro uso",
                    detalhe=f"{type(erro).__name__}: {str(erro)[:160]}",
                    reproducao="a estrutura passou na conferência e falhou ao ser usada",
                ) from erro
            conn.execute("ROLLBACK TO prova_de_uso")
            conn.execute("RELEASE prova_de_uso")

        return aplicadas
    except HarnessFailure:
        raise
    except BaseException:
        conn.execute("ROLLBACK")
        raise
