"""Coletar cotações de uma fonte e gravá-las como versões.

Tudo ou nada: se UMA cotação da janela é inválida (fora da janela, par
errado, duplicada, as_of no futuro), nada é gravado. Uma janela pela metade
faria o resolvedor cair em "anterior" num dia que a fonte publicou, e isso
não aparece em lugar nenhum.

Ausência não é zero: dia sem cotação na fonte (fim de semana, feriado) não
vira linha. O resolvedor do banco decide o que vale para esse dia e diz que
usou a anterior.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, List, Optional, Protocol, Sequence, Tuple

from ..domain import Cotacao, CotacaoInvalida


class ColetaRecusada(RuntimeError):
    """A janela não pode ser gravada; o recibo de falha vai em `motivos`."""

    def __init__(self, mensagem: str, motivos: Sequence[str]) -> None:
        super().__init__(mensagem)
        self.motivos = tuple(motivos)


class FonteDeCotacao(Protocol):
    nome: str
    par: str

    def buscar(self, inicio: date, fim: date) -> List[Cotacao]: ...


class RepositorioDeCotacao(Protocol):
    async def gravar(self, cotacoes: Sequence[Cotacao]) -> int:
        """Grava as versões; repetidas (mesmo par, dia, fonte e as_of) são ignoradas.
        Devolve quantas eram novas."""
        ...


@dataclass(frozen=True)
class ReciboDeColeta:
    fonte: str
    par: str
    janela: Tuple[str, str]
    recebidas: int
    gravadas: int
    dias_com_cotacao: Tuple[str, ...]


def _validar(cotacoes: Sequence[Cotacao], fonte: FonteDeCotacao, inicio: date, fim: date,
             agora: datetime) -> List[str]:
    motivos: List[str] = []
    vistas = set()
    for c in cotacoes:
        if c.fonte != fonte.nome or c.par != fonte.par:
            motivos.append(f"{c.data_referencia}: {c.fonte}/{c.par} não é {fonte.nome}/{fonte.par}")
        if not inicio <= c.data_referencia <= fim:
            motivos.append(f"{c.data_referencia}: fora da janela {inicio}..{fim}")
        chave = (c.par, c.data_referencia, c.as_of)
        if chave in vistas:
            motivos.append(f"{c.data_referencia}: versão repetida na mesma resposta")
        vistas.add(chave)
        try:
            c.validar_contra(agora)
        except CotacaoInvalida as e:
            motivos.append(f"{c.data_referencia}: {e}")
    return motivos


async def coletar_cotacoes(fonte: FonteDeCotacao, repositorio: RepositorioDeCotacao,
                           inicio: date, fim: date, *,
                           relogio: Optional[Callable[[], datetime]] = None) -> ReciboDeColeta:
    if fim < inicio:
        raise ColetaRecusada("janela invertida", [f"{inicio} > {fim}"])
    agora = (relogio or (lambda: datetime.now(timezone.utc)))()
    if fim > agora.date():
        raise ColetaRecusada("janela termina no futuro", [f"fim {fim} > hoje {agora.date()}"])
    try:
        cotacoes = fonte.buscar(inicio, fim)
    except CotacaoInvalida as e:
        raise ColetaRecusada(f"{fonte.nome} devolveu cotação inválida", [str(e)]) from e
    motivos = _validar(cotacoes, fonte, inicio, fim, agora)
    if motivos:
        raise ColetaRecusada(f"{fonte.nome}: {len(motivos)} problema(s); nada gravado", motivos)
    gravadas = await repositorio.gravar(cotacoes) if cotacoes else 0
    return ReciboDeColeta(
        fonte=fonte.nome, par=fonte.par, janela=(inicio.isoformat(), fim.isoformat()),
        recebidas=len(cotacoes), gravadas=gravadas,
        dias_com_cotacao=tuple(sorted({c.data_referencia.isoformat() for c in cotacoes})))
