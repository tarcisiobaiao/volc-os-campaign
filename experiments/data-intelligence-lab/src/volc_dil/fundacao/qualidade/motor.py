"""Motor: roda todas as checagens sobre um `ConjuntoSaude` e devolve achados ordenados."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from .adaptadores import cobertura_de_raw_events, observacoes_de_tabelas, runs_de_tabelas
from .agenda import LIMIARES_PADRAO, SLA, SLA_PADRAO
from .deriva import checar_deriva
from .integridade import checar_cobertura_atribuicao, checar_deriva_esquema, checar_substituicao_fonte
from .leituras import checar_duplicacao, checar_zero_sintetizado
from .modelo import Achado, CoberturaSensorDia, ObservacaoDQ, RunDQ, ordenar_achados
from .reconciliacao import (
    LinhaReceitaDia,
    agregar_receita_joinads,
    checar_reconciliacao_custo,
    checar_reconciliacao_receita,
)
from .runs import checar_completude_slots, checar_falha_silenciosa, checar_frescor, checar_runs_orfaos

# regra (prefixo) -> view candidata equivalente (None = só Python)
MAPA_REGRA_VIEW: Mapping[str, str | None] = {
    "frescor_": "dq_freshness",
    "completude_slots": "dq_completude_hora",
    "completude_": None,
    "run_orfao": "dq_runs_orfaos",
    "falha_silenciosa_run_vazio": "dq_falha_silenciosa",
    "duplicacao_": "dq_duplicacao",
    "zero_sintetizado": "dq_zero_sintetizado",
    "reconciliacao_receita_": "dq_reconciliacao_joinads",
    "reconciliacao_custo_": "dq_reconciliacao_custo_d0_d1",
    "deriva_distribuicao": None,
    "esquema_": "dq_esquema_joinads",
    "substituicao_": "dq_substituicao_fonte",
    "atribuicao_sensor_": "dq_cobertura_atribuicao_sensor",
    "latencia_": "dq_obs_latencia_ingestao",
    "dead_letter_taxa": "dq_obs_dead_letter",
}


@dataclass
class ConjuntoSaude:
    runs: list[RunDQ]
    observacoes: list[ObservacaoDQ]
    cobertura_sensor: list[CoberturaSensorDia] = field(default_factory=list)
    receita_dias: list[LinhaReceitaDia] | None = None  # None: derivada das observações JoinAds
    series_deriva: dict[str, list[float | None]] = field(default_factory=dict)
    contrato_esquema: dict | None = None
    moeda_esperada: dict[str, str] | None = None

    @classmethod
    def de_tabelas(cls, tabelas: Mapping[str, list[dict]], agora: datetime, **extra: Any) -> "ConjuntoSaude":
        """Linhas exportadas das tabelas reais (mesmos nomes de coluna) -> conjunto."""
        return cls(runs=runs_de_tabelas(tabelas), observacoes=observacoes_de_tabelas(tabelas),
                   cobertura_sensor=cobertura_de_raw_events(tabelas.get("raw_events", []), agora), **extra)

    @classmethod
    def de_dict(cls, d: Mapping[str, Any], agora: datetime) -> "ConjuntoSaude":
        """`{"formato": "tabelas", "tabelas": {...}}` ou `{"formato": "protocolo", "runs": [...], ...}`."""
        extra = {"series_deriva": d.get("series_deriva") or {}, "moeda_esperada": d.get("moeda_esperada")}
        if d.get("formato", "protocolo") == "tabelas":
            conj = cls.de_tabelas(d["tabelas"], agora, **extra)
            if d.get("cobertura_sensor") is not None:  # export agregado (sem raw_events linha a linha)
                conj.cobertura_sensor = [CoberturaSensorDia.de_dict(c) for c in d["cobertura_sensor"]]
            return conj
        return cls(
            runs=[RunDQ.de_dict(r) for r in d.get("runs", [])],
            observacoes=[ObservacaoDQ.de_dict(o) for o in d.get("observacoes", [])],
            cobertura_sensor=[CoberturaSensorDia.de_dict(c) for c in d.get("cobertura_sensor", [])],
            receita_dias=None if d.get("receita_dias") is None
            else [LinhaReceitaDia.de_dict(x) for x in d["receita_dias"]],
            **extra,
        )

    def como_dict(self) -> dict:
        return {
            "formato": "protocolo",
            "runs": [r.como_dict() for r in self.runs],
            "observacoes": [o.como_dict() for o in self.observacoes],
            "cobertura_sensor": [c.como_dict() for c in self.cobertura_sensor],
            "receita_dias": None if self.receita_dias is None else [x.como_dict() for x in self.receita_dias],
            "series_deriva": self.series_deriva,
            "moeda_esperada": self.moeda_esperada,
        }


def avaliar_saude(
    conjunto: ConjuntoSaude,
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    c = conjunto
    receita = c.receita_dias if c.receita_dias is not None else agregar_receita_joinads(c.observacoes, c.runs, agora, limiares)
    achados: list[Achado] = []
    achados += checar_frescor(c.runs, agora, slas, limiares)
    achados += checar_completude_slots(c.runs, agora, slas)
    achados += checar_runs_orfaos(c.runs, agora, slas)
    achados += checar_falha_silenciosa(c.runs, agora, slas)
    achados += checar_duplicacao(c.observacoes, agora, limiares)
    achados += checar_zero_sintetizado(c.observacoes, agora, limiares=limiares)
    achados += checar_reconciliacao_receita(receita, limiares)
    achados += checar_reconciliacao_custo(c.observacoes, c.runs, agora, limiares)
    achados += checar_deriva(c.series_deriva) if c.series_deriva else []
    achados += checar_deriva_esquema(c.observacoes, c.contrato_esquema)
    achados += checar_substituicao_fonte(c.observacoes, c.runs, c.moeda_esperada)
    achados += checar_cobertura_atribuicao(c.cobertura_sensor, limiares)
    return ordenar_achados(achados)


def view_da_regra(regra: str) -> str | None:
    for prefixo, view in MAPA_REGRA_VIEW.items():
        if regra.startswith(prefixo):
            return view
    return None
