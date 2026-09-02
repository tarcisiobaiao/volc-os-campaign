"""A porta unica do deposito de trabalhos.

## Por que uma porta, e nao dois depositos

O P17-T04 pede "uma unica porta escolhe o deposito por ambiente; o mesmo
contrato de claim, lease, heartbeat, idempotencia, transicao e recibo passa nos
dois adapters sem dupla verdade".

"Sem dupla verdade" e a parte dificil. Ate aqui existiam DUAS maquinas de estado:
a fila SQLite, escrita em Python, e a v11_03, escrita em gatilhos PL/pgSQL. As
duas foram provadas — separadamente — e divergiam em quatro pontos que a
correcao anterior fechou (lease vencido nao avanca, `rendered` exige recibo COM
artefato, mensagem sem caminho, trilha append-only). Uma porta sem uma suite de
contrato compartilhada apenas esconderia a proxima divergencia atras de um
`Protocol`.

Por isso este modulo define o `Protocol` E aponta para quem o prova:
`backend/tests/test_criativo_deposito_contrato.py` roda as MESMAS assercoes
contra os dois adapters, e o adapter Postgres nasce contra um cluster
descartavel — nunca contra `database.agenciavolc.com.br`.

## Escolha por ambiente, e a recusa explicita

`escolher_deposito()` le `CRIATIVO_DEPOSITO`. Ausencia significa `sqlite`, que e
o unico que funciona sem infraestrutura. Pedir `postgres` sem DSN NAO cai
silenciosamente para SQLite: levanta. Fallback silencioso entre depositos e como
um trabalho reivindicado num banco termina no outro.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from .contrato import Encomenda, EstadoDoTrabalho
from .deposito import Trabalho


@runtime_checkable
class Deposito(Protocol):
    """O contrato que os dois adapters cumprem, com as mesmas garantias.

    As garantias que a suite de contrato exerce nos dois:

    - **claim** e exclusivo: dois operarios concorrentes nunca pegam o mesmo
      trabalho (`BEGIN IMMEDIATE` no SQLite, `for update skip locked` no
      Postgres);
    - **lease** tem prazo e vencer devolve para a fila, sem marcar falha;
    - **batimento** so renova lease que AINDA VALE e so para o dono;
    - **avanco** para `running`/`validating` exige lease vivo;
    - **idempotencia** e por conteudo, com o tenant dentro da chave;
    - **transicao** obedece ao mapa e escreve trilha append-only;
    - **recibo** e obrigatorio em `rendered` e precisa ter artefato;
    - **terminalidade** e carimbada e nao volta.
    """

    def enfileirar(
        self,
        encomenda: Encomenda,
        *,
        max_tentativas: int = 3,
        chave: str | None = None,
        retoma_de: str | None = None,
        retomada_n: int = 0,
    ) -> tuple[Trabalho, bool]: ...

    def reivindicar(self, operario: str, *, lease_s: int = 60) -> Trabalho | None: ...

    def reivindicar_este(
        self, trabalho_id: str, operario: str, *, lease_s: int = 60
    ) -> Trabalho | None: ...

    def retomar(
        self, trabalho_id: str, *, tenant_id: str, max_tentativas: int = 3
    ) -> tuple[Trabalho, bool]: ...

    def cancelar(
        self, trabalho_id: str, *, tenant_id: str, por: str, motivo: str
    ) -> Trabalho: ...

    def bater(
        self, trabalho_id: str, *, lease_s: int = 60, operario: str | None = None
    ) -> bool: ...

    def transicionar(
        self,
        trabalho_id: str,
        para: EstadoDoTrabalho,
        *,
        falha: dict[str, Any] | None = None,
        recibo: dict[str, Any] | None = None,
        exigir_operario: str | None = None,
        exigir_tentativa: int | None = None,
    ) -> Trabalho: ...

    def devolver_vencidos(self) -> int: ...

    def por_id(
        self, trabalho_id: str, *, tenant_id: str | None = None
    ) -> Trabalho | None: ...

    def listar(self, *, tenant_id: str, limite: int = 50) -> list[Trabalho]: ...

    def por_chave(self, chave: str, *, tenant_id: str | None = None) -> Trabalho | None: ...

    def linhagem(self, trabalho_id: str, *, tenant_id: str) -> list[Trabalho]: ...

    def trilha(
        self, trabalho_id: str, *, tenant_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def contar_por_estado(self) -> dict[str, int]: ...


class DepositoIndisponivel(RuntimeError):
    """Pediram um deposito que esta maquina nao consegue montar.

    Levanta em vez de cair para outro adapter. Um trabalho reivindicado num
    deposito e concluido em outro nao e degradacao: e perda de linhagem.
    """


def escolher_deposito(
    *,
    caminho_sqlite: Any = None,
    dsn: str | None = None,
    ambiente: str | None = None,
) -> Deposito:
    """Monta o deposito do ambiente. `CRIATIVO_DEPOSITO` manda; ausencia e sqlite.

    ⚠️ Ausencia de `CRIATIVO_DEPOSITO` significa `sqlite` porque e o unico que
    sobe sem infraestrutura — e nao porque "sqlite e o padrao de producao". Quem
    quer Postgres pede Postgres, e se o DSN nao estiver la, ouve isso.
    """
    escolha = (ambiente or os.environ.get("CRIATIVO_DEPOSITO") or "sqlite").strip().lower()

    if escolha == "sqlite":
        from .deposito import DepositoDeTrabalhos  # noqa: PLC0415

        if caminho_sqlite is None:
            from .servico import raiz_da_bancada  # noqa: PLC0415

            caminho_sqlite = raiz_da_bancada() / "fila.db"
        return DepositoDeTrabalhos(caminho_sqlite)

    if escolha == "postgres":
        alvo = dsn or os.environ.get("CRIATIVO_DEPOSITO_DSN") or ""
        if not alvo:
            raise DepositoIndisponivel(
                "CRIATIVO_DEPOSITO=postgres exige CRIATIVO_DEPOSITO_DSN; "
                "nao ha queda silenciosa para sqlite"
            )
        from .deposito_postgres import DepositoPostgres  # noqa: PLC0415

        return DepositoPostgres(alvo)

    raise DepositoIndisponivel(
        f"CRIATIVO_DEPOSITO={escolha!r} nao e um deposito conhecido "
        "(esperado: sqlite | postgres)"
    )
