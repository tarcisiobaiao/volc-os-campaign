"""Contrato de alertas: definição + função pura que decide. NENHUM envio real.

`decidir_alertas` é pura: recebe achados, o instante e o estado do último envio por chave, e
devolve (alertas, novo_estado). `despachar` só chama um `sink` injetado pelo chamador — não há
sink padrão, nem import de rede (Slack, e-mail, webhook) neste pacote; os testes usam um sink falso.
O canal real fica "a_decidir" pelo dono (ver doc 09, seção de alertas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Iterable, Mapping

from .modelo import Achado, Severidade


@dataclass(frozen=True)
class PoliticaAlerta:
    nome: str
    severidade_minima: Severidade
    quem_acorda: str
    canal: str = "a_decidir"
    silencio: timedelta = timedelta(hours=4)
    regras: frozenset[str] | None = None  # None = todas as regras

    def aceita(self, a: Achado) -> bool:
        if a.severidade.nivel < self.severidade_minima.nivel:
            return False
        return self.regras is None or a.regra in self.regras


POLITICAS_PADRAO: tuple[PoliticaAlerta, ...] = (
    PoliticaAlerta("imediato", Severidade.CRITICO,
                   "responsável de dados do VOLC (hoje: Tarcisio) — a qualquer hora", silencio=timedelta(hours=1)),
    PoliticaAlerta("horario_comercial", Severidade.ALTO,
                   "responsável de dados — dentro do horário comercial", silencio=timedelta(hours=4)),
    PoliticaAlerta("digest_diario", Severidade.AVISO,
                   "ninguém acorda — vai no resumo diário", silencio=timedelta(hours=24)),
)


@dataclass(frozen=True)
class Alerta:
    politica: str
    canal: str
    quem_acorda: str
    achado: Achado
    chave: tuple = field(compare=False)

    def como_dict(self) -> dict:
        return {"politica": self.politica, "canal": self.canal, "quem_acorda": self.quem_acorda,
                "regra": self.achado.regra, "severidade": self.achado.severidade.value,
                "fonte": self.achado.fonte, "chave": self.achado.chave, "mensagem": self.achado.mensagem}


def decidir_alertas(
    achados: Iterable[Achado],
    agora: datetime,
    politicas: tuple[PoliticaAlerta, ...] = POLITICAS_PADRAO,
    ultimo_envio: Mapping[tuple, datetime] | None = None,
) -> tuple[list[Alerta], dict[tuple, datetime]]:
    """Cada achado vai para a PRIMEIRA política que o aceita (ordem = mais severa primeiro).
    `info` nunca alerta. Mesma chave dentro da janela de silêncio é suprimida; duplicatas no mesmo
    lote de achados também. O estado devolvido é novo (a entrada não é mutada)."""
    estado = dict(ultimo_envio or {})
    alertas: list[Alerta] = []
    vistos: set[tuple] = set()
    for a in achados:
        if a.severidade is Severidade.INFO:
            continue
        pol = next((p for p in politicas if p.aceita(a)), None)
        if pol is None:
            continue
        chave = (pol.nome, *a.chave_dedupe())
        if chave in vistos:
            continue
        vistos.add(chave)
        anterior = estado.get(chave)
        if anterior is not None and agora < anterior + pol.silencio:
            continue
        estado[chave] = agora
        alertas.append(Alerta(pol.nome, pol.canal, pol.quem_acorda, a, chave))
    return alertas, estado


def despachar(alertas: Iterable[Alerta], sink: Callable[[Alerta], None]) -> int:
    """Entrega cada alerta ao `sink` injetado. Sem sink, não há envio (o parâmetro é obrigatório)."""
    n = 0
    for al in alertas:
        sink(al)
        n += 1
    return n
