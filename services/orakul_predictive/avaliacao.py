"""Métricas derivadas do alvo de negócio: erro em dinheiro, não R² de conveniência."""

from __future__ import annotations

from typing import Optional, Sequence

from .constantes import CENARIO_OBSERVADO, DATASET_SINTETICO, DEFINICOES_ALVO
from .contratos import MetricasAvaliacao, ObservedOutcome, Prediction
from .excecoes import (
    ContratoInvalido,
    DefinicaoDeAlvoIncompativel,
    MoedaOuFusoIncompativel,
    PopulacaoIncompativel,
)
from .semantica import EstadoSemantico, valor_numerico_ou_nulo


def reconciliar(previsao: Prediction, outcome: ObservedOutcome) -> tuple[Optional[int], Optional[int]]:
    if previsao.alvo != outcome.alvo:
        raise DefinicaoDeAlvoIncompativel(f"{previsao.alvo} vs {outcome.alvo}")
    if previsao.target_date != outcome.target_date:
        raise DefinicaoDeAlvoIncompativel("target_date desalinhado — o legado comparava hoje com ontem")
    if previsao.campanha_id != outcome.campanha_id:
        raise DefinicaoDeAlvoIncompativel("campanha desalinhada")
    if previsao.conta_id != outcome.conta_id:
        raise PopulacaoIncompativel("conta desalinhada")
    if previsao.origin_date != outcome.origin_date:
        raise DefinicaoDeAlvoIncompativel("origin_date desalinhado")
    if previsao.horizonte_dias != 1 or outcome.horizonte_dias != 1:
        raise DefinicaoDeAlvoIncompativel("reconciliação aceita somente D+1")
    if previsao.target_definition != outcome.target_definition:
        raise DefinicaoDeAlvoIncompativel("definição de alvo desalinhada")
    if previsao.cenario != CENARIO_OBSERVADO or outcome.cenario != CENARIO_OBSERVADO:
        raise DefinicaoDeAlvoIncompativel("actual não avalia cenário hipotético")
    if previsao.pair_id != outcome.pair_id:
        raise PopulacaoIncompativel("pair_id desalinhado")
    if previsao.fuso != outcome.fuso or previsao.moeda != outcome.moeda:
        raise MoedaOuFusoIncompativel("fuso/moeda distintos na reconciliação")
    yhat = previsao.ponto_micros if previsao.disponivel else None
    y = valor_numerico_ou_nulo(outcome.estado_semantico, outcome.valor_micros)
    return yhat, y


def _mae(erros: Sequence[float]) -> Optional[float]:
    if not erros:
        return None
    return sum(abs(e) for e in erros) / len(erros)


def _rmse(erros: Sequence[float]) -> Optional[float]:
    if not erros:
        return None
    return (sum(e * e for e in erros) / len(erros)) ** 0.5


def _bias(erros: Sequence[float]) -> Optional[float]:
    if not erros:
        return None
    return sum(erros) / len(erros)


def _wape(y: Sequence[float], yhat: Sequence[float]) -> Optional[float]:
    denom = sum(abs(v) for v in y)
    if denom <= 0:
        return None
    return sum(abs(a - b) for a, b in zip(y, yhat)) / denom


def _winkler(y: float, lo: float, hi: float, alpha: float = 0.10) -> float:
    largura = hi - lo
    if y < lo:
        return largura + (2.0 / alpha) * (lo - y)
    if y > hi:
        return largura + (2.0 / alpha) * (y - hi)
    return largura


def avaliar_pares(
    pares: Sequence[tuple[Prediction, ObservedOutcome]],
    *,
    dataset_kind: str = DATASET_SINTETICO,
    entra_em_contagens_reais: bool = False,
    n_minimo: int = 14,
) -> MetricasAvaliacao:
    ys: list[float] = []
    yhats: list[float] = []
    erros: list[float] = []
    coberturas: list[bool] = []
    larguras: list[float] = []
    winklers: list[float] = []
    pair_ids: list[str] = []
    vistos: set[str] = set()
    identidade_populacao: set[tuple[object, ...]] = set()
    for pred, out in sorted(pares, key=lambda par: par[0].pair_id):
        if pred.procedencia.dataset_kind != dataset_kind or out.procedencia.dataset_kind != dataset_kind:
            raise PopulacaoIncompativel("dataset_kind do par diverge da avaliação")
        if pred.pair_id in vistos:
            raise PopulacaoIncompativel(f"pair_id duplicado: {pred.pair_id}")
        vistos.add(pred.pair_id)
        identidade_populacao.add(
            (
                pred.conta_id,
                pred.campanha_id,
                pred.alvo,
                pred.target_definition,
                pred.cenario,
                pred.horizonte_dias,
            )
        )
        if len(identidade_populacao) > 1:
            raise PopulacaoIncompativel("avaliar_pares mistura identidades/alvos")
        yhat, y = reconciliar(pred, out)
        if yhat is None or y is None:
            continue
        pair_ids.append(pred.pair_id)
        ys.append(y / 1_000_000.0)
        yhats.append(yhat / 1_000_000.0)
        erros.append((yhat - y) / 1_000_000.0)
        if pred.intervalo and pred.intervalo.lower_micros is not None and pred.intervalo.upper_micros is not None:
            lo = pred.intervalo.lower_micros / 1_000_000.0
            hi = pred.intervalo.upper_micros / 1_000_000.0
            y_brl = y / 1_000_000.0
            coberturas.append(lo <= y_brl <= hi)
            larguras.append(hi - lo)
            winklers.append(
                _winkler(y_brl, lo, hi, alpha=1.0 - pred.intervalo.nominal)
            )
    n = len(erros)
    if dataset_kind != DATASET_SINTETICO and entra_em_contagens_reais:
        if any(
            not pred.procedencia.entra_em_contagens_reais
            or not out.procedencia.entra_em_contagens_reais
            for pred, out in pares
        ):
            raise PopulacaoIncompativel("métrica real contém par inelegível para contagem real")
    suficiente = n >= n_minimo
    return MetricasAvaliacao(
        n=n,
        mae=_mae(erros),
        wape=_wape(ys, yhats),
        rmse=_rmse(erros),
        bias=_bias(erros),
        cobertura=(sum(coberturas) / len(coberturas)) if coberturas else None,
        largura_media=(sum(larguras) / len(larguras)) if larguras else None,
        winkler=(sum(winklers) / len(winklers)) if winklers else None,
        evidencia_suficiente=suficiente,
        dataset_kind=dataset_kind,
        entra_em_contagens_reais=False if dataset_kind == DATASET_SINTETICO else entra_em_contagens_reais,
        pair_ids=tuple(pair_ids),
        n_intervalos=len(coberturas),
    )


def outcome_de_observacao(
    *,
    campanha_id: str,
    target_date: str,
    alvo: str,
    micros: Optional[int],
    estado: EstadoSemantico,
    procedencia,
    observado_em: str,
    previsao_id: Optional[str] = None,
    conta_id: Optional[str] = None,
    versao_modelo: str = "",
    origin_date: Optional[str] = None,
    cenario: str = CENARIO_OBSERVADO,
    watermark_fechado_ate: Optional[str] = None,
) -> ObservedOutcome:
    from datetime import timedelta

    from .hashes import chave_idempotencia, hash_canonico, id_canonico, pair_id_d1
    from .relogio import iso_civil, parse_civil

    if not conta_id:
        raise ContratoInvalido("outcome exige conta_id")
    origin = origin_date or iso_civil(parse_civil(target_date) - timedelta(days=1))
    target_definition = DEFINICOES_ALVO.get(alvo)
    if target_definition is None:
        raise DefinicaoDeAlvoIncompativel(f"alvo inválido: {alvo}")
    if cenario != CENARIO_OBSERVADO:
        raise ContratoInvalido("outcome só pode representar cenário observado")
    pair_id = pair_id_d1(
        conta_id=conta_id,
        campanha_id=campanha_id,
        origin_date=origin,
        target_date=target_date,
        alvo=alvo,
        cenario=cenario,
        target_definition=target_definition,
    )
    identidade = {
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "pair_id": pair_id,
        "alvo": alvo,
        "target_date": target_date,
        "cenario": cenario,
    }

    return ObservedOutcome(
        outcome_id=id_canonico("outcome", **identidade),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=target_date,
        janela_fim=target_date,
        horizonte_dias=1,
        versao_modelo=versao_modelo,
        hash_inputs=hash_canonico({
            **identidade,
            "origin_date": origin,
            "target_definition": target_definition,
            "valor_micros": micros,
            "estado": estado.value,
            "procedencia_hash": procedencia.hash_fonte,
            "watermark_fechado_ate": watermark_fechado_ate,
        }),
        procedencia=procedencia,
        estado_semantico=estado,
        chave_idempotencia=chave_idempotencia(kind="outcome", **identidade),
        alvo=alvo,
        target_date=target_date,
        valor_micros=micros,
        pair_id=pair_id,
        origin_date=origin,
        target_definition=target_definition,
        cenario=cenario,
        previsao_id=previsao_id,
        watermark_fechado_ate=watermark_fechado_ate,
    )
