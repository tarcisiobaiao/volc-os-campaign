"""Adaptador: ``RegistroObservacao`` simulado → ``volc_dil.contracts.Observacao`` herdado.

Prova que o registro do simulador cabe no contrato econômico da 1ª execução (que o replay
v0 herdado consome) sem tradução com perda escondida. O contrato novo do worker A
(``volc_dil.fundacao.observacao``) não é importado; o integrador liga os dois.

Perdas declaradas (o contrato herdado não tem campo para):
- ``pageviews`` não tem ``Metrica`` → devolve ``None`` (sem mapeamento);
- ``ingested_at``, ``payload_sha256``, ``late``/``available_previsto`` e ``custom_key_*`` não têm
  campo próprio: viram ``coleta_id`` (run + leitura) e ``motivo``;
- ``partial`` vira ``MEDIDO`` + ``Cobertura.PARCIAL`` + ``Maturidade.PRELIMINAR``;
- receita intradiária vira ``ESTIMATED_REVENUE`` (não entra em lucro pelo contrato herdado).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from volc_dil.contracts import (
    ChaveUnidade,
    Cobertura,
    Dinheiro,
    EstadoMedida,
    Maturidade,
    Metrica,
    MetodoAtribuicao,
    Observacao,
    ValueKind,
)

from .registro import RegistroObservacao

LINHAGEM = ("simulador-fundacao",)  # opaca de propósito (lição F1-01: nada de seed/cenário na linhagem)

_METRICA = {"cost": Metrica.CUSTO, "revenue": Metrica.RECEITA, "clicks": Metrica.CLIQUES,
            "impressions": Metrica.IMPRESSOES, "sessions": Metrica.SESSOES, "destino": Metrica.CONVERSOES}
_ESTADO = {"observed": EstadoMedida.MEDIDO, "late": EstadoMedida.MEDIDO, "partial": EstadoMedida.MEDIDO,
           "zero_confirmed": EstadoMedida.ZERO_CONFIRMADO, "missing": EstadoMedida.AUSENTE,
           "unavailable": EstadoMedida.FALHA, "invalid": EstadoMedida.FALHA,
           "unsupported": EstadoMedida.NAO_APLICAVEL}


def para_observacao_contrato(r: RegistroObservacao, versao_fonte: str = "sim-fundacao") -> Optional[Observacao]:
    metrica = _METRICA.get(r.metrica)
    if metrica is None:
        return None
    estado = _ESTADO[r.status]
    if r.valor is None:
        valor = None
    elif r.unidade == "micros":
        valor = Dinheiro(r.valor, r.moeda)  # type: ignore[arg-type]
    else:
        valor = r.valor
    if r.status == "partial":
        cobertura, maturidade = Cobertura.PARCIAL, Maturidade.PRELIMINAR
    elif r.valor is None:
        cobertura, maturidade = Cobertura.DESCONHECIDA, Maturidade.PRELIMINAR
    else:
        cobertura = Cobertura.COMPLETA
        maturidade = {"final": Maturidade.REVISADA if r.fonte == "joinads" else Maturidade.MADURA}.get(
            r.maturidade, Maturidade.PRELIMINAR)
    value_kind = None
    metodo = MetodoAtribuicao.NAO_APLICAVEL
    if metrica is Metrica.RECEITA:
        value_kind = ValueKind.ESTIMATED_REVENUE if r.maturidade == "intradiaria" else ValueKind.REPORTED_REVENUE
        metodo = MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE
    motivo = r.motivo
    extras = []
    if r.status == "late":
        extras.append(f"late: previsto {r.available_previsto}")
    if r.custom_key_efetiva != r.custom_key_solicitada:
        extras.append(f"custom_key efetiva {r.custom_key_efetiva} ≠ solicitada {r.custom_key_solicitada}")
    if extras:
        motivo = "; ".join(([motivo] if motivo else []) + extras)
    unidade = ChaveUnidade(r.conta, r.entidade_tipo, r.entidade, tuple(r.grao), tuple(sorted(r.dimensoes)))
    return Observacao(
        unidade=unidade, metrica=metrica, valor=valor, estado=estado,
        janela_inicio=datetime.fromisoformat(r.janela_inicio), janela_fim=datetime.fromisoformat(r.janela_fim),
        timezone=r.timezone, observado_em=datetime.fromisoformat(r.observed_at),
        disponivel_em=datetime.fromisoformat(r.available_at), fonte=r.fonte, versao_fonte=versao_fonte,
        coleta_id=f"{r.run_id}:{r.leitura_id}", cobertura=cobertura, maturidade=maturidade, metodo=metodo,
        value_kind=value_kind, motivo=motivo, linhagem=LINHAGEM)
