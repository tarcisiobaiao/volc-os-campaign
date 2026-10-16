"""Controles NEGATIVOS: políticas que trapaceiam de propósito, para provar que os gates as pegam.

`PoliticaTrapaceira` captura o fluxo inteiro no construtor (como faria um código que contorna o
isolamento por tipo — p.ex. lendo uma variável global ou o banco direto) e decide com a versão
FINAL de cada fato, ignorando o corte. O motor não tem como impedir esse código de existir; o que
o pega é `motor.detectar_vazamento`: injetar observações com `available_at` posterior a alguns
cortes muda as decisões dela ANTES desse instante, e não muda as de nenhuma política honesta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from volc_dil.contracts.vocab import Metrica

from ..observacao.asof import as_of
from ..observacao.modelo import Observacao
from .politicas import exigir_snapshot, propor
from .snapshot import SnapshotShadow
from .tipos import BPS, Acao, Confianca, DecisaoShadow

_FIM_DOS_TEMPOS = datetime(9999, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class PoliticaTrapaceira:
    fluxo: tuple[Observacao, ...]
    janela_dias: int = 7
    nome: str = "controle_trapaceira"
    versao: str = "controle_trapaceira@1(le_fluxo_futuro)"

    def decidir(self, snapshot: SnapshotShadow) -> DecisaoShadow:
        snap = exigir_snapshot(snapshot)
        final = as_of(self.fluxo, _FIM_DOS_TEMPOS)  # TRAPAÇA: ignora snap.as_of
        dias = {snap.dia_corte - timedelta(days=k) for k in range(1, self.janela_dias + 1)}
        receita: dict[str, int] = {}
        custo: dict[str, int] = {}
        for o in final.values():
            if o.valor is None or o.metrica not in (Metrica.CUSTO, Metrica.RECEITA):
                continue
            d = o.janela_inicio.astimezone(o.janela_inicio.tzinfo).date()
            if d not in dias:
                continue
            if o.metrica is Metrica.CUSTO and o.fonte == "google_ads":
                custo[o.entidade.id] = custo.get(o.entidade.id, 0) + o.valor
            elif o.metrica is Metrica.RECEITA and dict(o.dimensoes).get("revenue_basis") == "client" and o.entidade.tipo == "campaign":
                receita[o.entidade.id] = receita.get(o.entidade.id, 0) + o.valor * 5
        propostas = []
        for e in snap.campanhas:
            c, r = custo.get(e.campaign_id, 0), receita.get(e.campaign_id, 0)
            if c and r < c:
                propostas.append(propor(snap, self, e, Acao.PAUSAR, 0, Confianca.ALTA, "usa versão final (trapaça)"))
            else:
                propostas.append(propor(snap, self, e, Acao.MANTER, BPS, Confianca.ALTA, "usa versão final (trapaça)"))
        return DecisaoShadow(tuple(propostas))


def cortar_por_observed_at(fluxo: Sequence[Observacao], t: datetime) -> tuple[Observacao, ...]:
    """Corte ERRADO (por `observed_at`), para a contraprova do retrodatado: só existe para comparação."""
    return tuple(o for o in fluxo if o.observed_at <= t)
