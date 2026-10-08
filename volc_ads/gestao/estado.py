"""O "antes" de cada ação, lido da conta no momento em que importa.

Duas leituras, dois papéis no ledger v10_02, e as duas passam por aqui:

  · na PROPOSTA  → `trafego_proposta.valor_atual` + `valor_atual_lido_em`
    (o gatilho recusa um "antes" mais velho que o frescor da regra);
  · no ENVIO     → `trafego_aplicacao.valor_anterior`, capturado logo antes
    do mutate — é DELE que o reverso sai, não do da proposta, porque entre a
    aprovação e o envio alguém pode ter mexido na campanha.

Toda GAQL passa por `catalogo.exigir_valida` antes de sair: um campo que o
servidor v25 não aceita no SELECT derruba a consulta inteira, e um "antes" que
não foi lido não pode virar "antes vazio" — vazio autorizaria qualquer diff.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Sequence

from volc_ads.gads import catalogo

from .acoes import Acao

Buscar = Callable[[str, str], Iterable[Any]]


@dataclass(frozen=True)
class Antes:
    """O estado lido para UMA ação, com o carimbo de quando foi lido."""

    acao: Acao
    dados: dict
    lido_em: datetime
    consultas: tuple[str, ...]


def _buscar_padrao(login_customer_id: str) -> Buscar:
    from volc_ads.gads.client import buscar  # noqa: PLC0415 — sem rede no import

    return lambda cid, q: buscar(cid, q, login_customer_id=login_customer_id)


def consultas_conferidas(acao: Acao, customer_id: str) -> tuple[str, ...]:
    """As GAQLs da ação, cada uma conferida pelo catálogo do servidor."""
    return tuple(catalogo.exigir_valida(q) for q in acao.consultas_antes(str(customer_id)))


def ler(
    customer_id: str,
    acao: Acao,
    *,
    login_customer_id: str = "",
    buscar: Buscar | None = None,
    conferir: bool = True,
    agora: Callable[[], datetime] | None = None,
) -> Antes:
    """Lê o "antes" de `acao`. Com `conferir=True`, levanta AcaoRecusada se o
    estado não permite a ação (estratégia mudou, orçamento compartilhado…).

    O carimbo é tirado ANTES da leitura: se a leitura demorar, o "antes" é
    tratado como um pouco mais velho do que é — o erro seguro para frescor.
    """
    cid = str(customer_id)
    consultas = consultas_conferidas(acao, cid)
    lido_em = (agora or (lambda: datetime.now(timezone.utc)))()
    b = buscar or _buscar_padrao(login_customer_id)
    linhas = tuple(list(b(cid, q)) for q in consultas)
    dados = acao.interpretar_antes(linhas) if consultas else {}
    if conferir:
        acao.conferir(dados)
    return Antes(acao=acao, dados=dados, lido_em=lido_em, consultas=consultas)


def ler_todos(
    customer_id: str,
    acoes: Sequence[Acao],
    *,
    login_customer_id: str = "",
    buscar: Buscar | None = None,
    conferir: bool = True,
) -> tuple[Antes, ...]:
    """Um `Antes` por ação, na ordem. Recusa na primeira ação incompatível."""
    return tuple(ler(customer_id, a, login_customer_id=login_customer_id,
                     buscar=buscar, conferir=conferir) for a in acoes)
