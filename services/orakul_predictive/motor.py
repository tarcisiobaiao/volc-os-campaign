"""Motor de previsão. Emite Prediction; nunca muta campanha, Google Ads ou n8n."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional, Sequence

from .constantes import (
    ALVO_REVENUE,
    ALVO_ROAS,
    ALVO_SPEND,
    CENARIO_PLANNED_SPEND,
    DEFINICOES_ALVO,
    HORIZONTE_PADRAO_DIAS,
    MODELO_LAGGED_LINEAR,
    MODELO_NAIVE_PERSISTENCE,
    MODELO_NAIVE_WEEKDAY,
)
from .contratos import Prediction, PredictionRequest
from .excecoes import ContratoInvalido, DefinicaoDeAlvoIncompativel, IsolamentoViolado
from .features import ObservacaoDiaria, montar_snapshot
from .hashes import chave_idempotencia, hash_canonico, id_canonico, pair_id_d1
from .isolamento import recusar_mutacao_externa
from .incerteza import intervalo_de_ponto, margem_quantil
from .modelos import ArtefatoLinear, brl_para_micros, naive_persistence, naive_weekday, prever_linear
from .relogio import iso_civil, parse_civil
from .semantica import EstadoSemantico


def codigo_hash_motor() -> str:
    from pathlib import Path

    from .hashes import hash_codigo_pacote

    pasta = Path(__file__).resolve().parent
    textos = {p.name: p.read_text(encoding="utf-8") for p in sorted(pasta.glob("*.py"))}
    return hash_codigo_pacote(textos)


def prever(
    request: PredictionRequest,
    serie: Sequence[ObservacaoDiaria],
    *,
    artefatos: Optional[dict[str, ArtefatoLinear]] = None,
    residuos_oof: Optional[dict[str, tuple[float, ...]]] = None,
) -> tuple[Prediction, ...]:
    recusar_mutacao_externa(request.mutacao_campanha)
    if request.horizonte_dias != HORIZONTE_PADRAO_DIAS:
        raise DefinicaoDeAlvoIncompativel("Core V1 só prevê horizonte D+1")
    origin = request.janela_fim
    origin_d = parse_civil(origin)
    target_date = iso_civil(origin_d + timedelta(days=request.horizonte_dias))
    code_hash = codigo_hash_motor()
    saida: list[Prediction] = []
    for alvo in request.alvos:
        if alvo == ALVO_ROAS:
            continue
        snap = montar_snapshot(
            serie,
            campanha_id=request.campanha_id,
            origin=origin,
            horizonte_dias=request.horizonte_dias,
            versao_modelo=request.versao_modelo,
            procedencia=request.procedencia,
            codigo_hash=code_hash,
            alvo=alvo,
            planned_spend_micros=request.planned_spend_micros,
            conta_id=request.conta_id,
            observado_em=request.observado_em,
            cutoff_em=request.cutoff_em,
            cenario=request.cenario,
        )
        ponto: Optional[int]
        bruto: Optional[int]
        target_definition = DEFINICOES_ALVO[alvo]
        pair_id = pair_id_d1(
            conta_id=str(request.conta_id),
            campanha_id=request.campanha_id,
            origin_date=origin,
            target_date=target_date,
            alvo=alvo,
            cenario=request.cenario,
            target_definition=target_definition,
        )
        motivo_indisponivel: Optional[str] = None
        estado_forcado: Optional[EstadoSemantico] = None

        if request.cenario == CENARIO_PLANNED_SPEND and alvo == ALVO_SPEND:
            ponto = request.planned_spend_micros
            bruto = ponto
            estado_forcado = EstadoSemantico.HIPOTESE
            artifact_hash = hash_canonico({
                "kind": "planned_spend_assumption/v1",
                "target_definition": target_definition,
                "code_hash": code_hash,
                "identificacao": request.identificacao_cenario,
            })
        elif request.cenario == CENARIO_PLANNED_SPEND and alvo == ALVO_REVENUE:
            ponto = None
            bruto = None
            estado_forcado = EstadoSemantico.NAO_APLICAVEL
            motivo_indisponivel = "efeito_causal_de_planned_spend_nao_identificado"
            artifact_hash = hash_canonico({
                "kind": "planned_spend_response_unavailable/v1",
                "target_definition": target_definition,
                "code_hash": code_hash,
                "identificacao": request.identificacao_cenario,
            })
        elif request.versao_modelo == MODELO_NAIVE_WEEKDAY:
            ponto = naive_weekday(serie, snap, alvo)
            bruto = ponto
            artifact_hash = hash_canonico({
                "kind": MODELO_NAIVE_WEEKDAY,
                "target_definition": target_definition,
                "feature_set_id": snap.feature_set_id,
                "code_hash": code_hash,
            })
        elif request.versao_modelo == MODELO_LAGGED_LINEAR:
            if not artefatos or alvo not in artefatos:
                raise ContratoInvalido(f"artefato Ridge ausente para alvo {alvo}")
            artefato = artefatos[alvo]
            if artefato.alvo != alvo or artefato.modelo_id != request.versao_modelo:
                raise DefinicaoDeAlvoIncompativel("artefato associado à chave/alvo incorretos")
            if artefato.code_hash != code_hash:
                raise ContratoInvalido("artefato foi produzido por outro código")
            y_brl = prever_linear(artefato, snap)
            bruto = None if y_brl is None else int(round(y_brl * 1_000_000))
            ponto = brl_para_micros(y_brl)
            artifact_hash = artefato.artifact_hash
        elif request.versao_modelo == MODELO_NAIVE_PERSISTENCE:
            ponto = naive_persistence(snap, alvo)
            bruto = ponto
            artifact_hash = hash_canonico({
                "kind": MODELO_NAIVE_PERSISTENCE,
                "target_definition": target_definition,
                "feature_set_id": snap.feature_set_id,
                "code_hash": code_hash,
            })
        else:
            raise ContratoInvalido(f"versão de modelo desconhecida: {request.versao_modelo}")

        disponivel = ponto is not None
        if estado_forcado is not None:
            estado = estado_forcado
        elif not disponivel:
            estado = (
                snap.estado_semantico
                if snap.estado_semantico
                in (EstadoSemantico.FALHA, EstadoSemantico.ANTIGO, EstadoSemantico.NAO_APLICAVEL)
                else EstadoSemantico.AUSENTE
            )
            motivo_indisponivel = motivo_indisponivel or f"feature_origem_{estado.value}"
        elif ponto == 0 and (bruto is None or bruto == 0):
            estado = EstadoSemantico.ZERO_MEDIDO
        else:
            estado = EstadoSemantico.MEDIDO
        identidade = {
            "conta_id": request.conta_id,
            "campanha_id": request.campanha_id,
            "target_date": target_date,
            "alvo": alvo,
            "cenario": request.cenario,
            "versao_modelo": request.versao_modelo,
        }
        previsao_id = id_canonico("pred", **identidade)
        chave = chave_idempotencia(
            kind="prediction",
            **identidade,
        )
        prediction_hash = hash_canonico({
            "request_hash": request.hash_inputs,
            "snapshot_hash": snap.hash_inputs,
            "artifact_hash": artifact_hash,
            "pair_id": pair_id,
            "target_definition": target_definition,
            "planned_spend_micros": request.planned_spend_micros,
            "identificacao_cenario": request.identificacao_cenario,
        })
        residuos = () if request.cenario == CENARIO_PLANNED_SPEND else (
            (residuos_oof or {}).get(alvo)
            or (artefatos[alvo].residuos_abs if artefatos and alvo in artefatos else ())
        )
        fora = bool(residuos_oof and alvo in residuos_oof)
        margem = margem_quantil(residuos) if residuos and fora else None
        intervalo = intervalo_de_ponto(
            previsao_id=previsao_id,
            campanha_id=request.campanha_id,
            alvo=alvo,
            ponto_micros=ponto,
            margem_brl=margem,
            observado_em=request.observado_em,
            janela_inicio=request.janela_inicio,
            janela_fim=request.janela_fim,
            horizonte_dias=request.horizonte_dias,
            versao_modelo=request.versao_modelo,
            hash_inputs=prediction_hash,
            procedencia=request.procedencia,
            n_calibracao=len(residuos),
            fora_da_amostra=fora,
            conta_id=request.conta_id,
            pair_id=pair_id,
            cenario=request.cenario,
            artifact_hash=artifact_hash,
        )
        saida.append(
            Prediction(
                previsao_id=previsao_id,
                campanha_id=request.campanha_id,
                conta_id=request.conta_id,
                observado_em=request.observado_em,
                janela_inicio=request.janela_inicio,
                janela_fim=request.janela_fim,
                horizonte_dias=request.horizonte_dias,
                versao_modelo=request.versao_modelo,
                hash_inputs=prediction_hash,
                procedencia=request.procedencia,
                estado_semantico=estado,
                chave_idempotencia=chave,
                alvo=alvo,
                target_date=target_date,
                ponto_micros=ponto,
                ponto_bruto_micros=bruto,
                intervalo=intervalo,
                confianca=None,
                snapshot_id=snap.snapshot_id,
                cenario=request.cenario,
                pair_id=pair_id,
                origin_date=origin,
                target_definition=target_definition,
                artifact_hash=artifact_hash,
                mutacao_campanha=False,
                disponivel=disponivel,
                motivo_indisponivel=motivo_indisponivel,
            )
        )
    if ALVO_ROAS in request.alvos:
        spend = next((p for p in saida if p.alvo == ALVO_SPEND), None)
        rev = next((p for p in saida if p.alvo == ALVO_REVENUE), None)
        saida.append(_roas_derivado(request, spend, rev, target_date))
    return tuple(saida)


def _roas_derivado(
    request: PredictionRequest,
    spend: Optional[Prediction],
    rev: Optional[Prediction],
    target_date: str,
) -> Prediction:
    disponivel = (
        spend is not None
        and rev is not None
        and spend.ponto_micros not in (None, 0)
        and rev.ponto_micros is not None
    )
    ponto = None
    if disponivel and spend and rev and spend.ponto_micros:
        # ROAS * 1e6 para caber no campo micros com unidade "fracao_x_1e6"
        ponto = int(round((rev.ponto_micros / spend.ponto_micros) * 1_000_000))
    target_definition = DEFINICOES_ALVO[ALVO_ROAS]
    pair_id = pair_id_d1(
        conta_id=str(request.conta_id),
        campanha_id=request.campanha_id,
        origin_date=request.janela_fim,
        target_date=target_date,
        alvo=ALVO_ROAS,
        cenario=request.cenario,
        target_definition=target_definition,
    )
    artifact_hash = hash_canonico({
        "kind": "roas_derived/v1",
        "spend_artifact": spend.artifact_hash if spend else None,
        "revenue_artifact": rev.artifact_hash if rev else None,
        "target_definition": target_definition,
    })
    identidade = {
        "conta_id": request.conta_id,
        "campanha_id": request.campanha_id,
        "target_date": target_date,
        "alvo": ALVO_ROAS,
        "cenario": request.cenario,
        "versao_modelo": request.versao_modelo,
    }
    estados_componentes = {p.estado_semantico for p in (spend, rev) if p is not None}
    if disponivel:
        estado = EstadoSemantico.MEDIDO
    elif EstadoSemantico.FALHA in estados_componentes:
        estado = EstadoSemantico.FALHA
    elif EstadoSemantico.ANTIGO in estados_componentes:
        estado = EstadoSemantico.ANTIGO
    else:
        estado = EstadoSemantico.NAO_APLICAVEL
    return Prediction(
        previsao_id=id_canonico("pred", **identidade),
        campanha_id=request.campanha_id,
        conta_id=request.conta_id,
        observado_em=request.observado_em,
        janela_inicio=request.janela_inicio,
        janela_fim=request.janela_fim,
        horizonte_dias=request.horizonte_dias,
        versao_modelo=request.versao_modelo,
        hash_inputs=hash_canonico({
            "request_hash": request.hash_inputs,
            "spend": spend.hash_inputs if spend else None,
            "rev": rev.hash_inputs if rev else None,
            "artifact_hash": artifact_hash,
            "pair_id": pair_id,
        }),
        procedencia=request.procedencia,
        estado_semantico=estado,
        chave_idempotencia=chave_idempotencia(kind="prediction", **identidade),
        alvo=ALVO_ROAS,
        target_date=target_date,
        ponto_micros=ponto,
        ponto_bruto_micros=ponto,
        intervalo=None,
        confianca=None,
        snapshot_id=(
            spend.snapshot_id
            if spend
            else id_canonico(
                "derived-snapshot",
                conta_id=request.conta_id,
                campanha_id=request.campanha_id,
                origin_date=request.janela_fim,
                target_date=target_date,
                alvo=ALVO_ROAS,
                cenario=request.cenario,
            )
        ),
        cenario=request.cenario,
        pair_id=pair_id,
        origin_date=request.janela_fim,
        target_definition=target_definition,
        artifact_hash=artifact_hash,
        mutacao_campanha=False,
        unidade="fracao_x_1e6",
        disponivel=bool(disponivel),
        motivo_indisponivel=None if disponivel else "roas_exige_spend_e_receita",
    )


def recusar_executor(*_a, **_k) -> None:
    raise IsolamentoViolado("núcleo preditivo não possui executor de campanha")
