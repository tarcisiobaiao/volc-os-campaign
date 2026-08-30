"""Walk-forward temporal. Nunca embaralha o tempo."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional, Sequence

from .avaliacao import avaliar_pares, outcome_de_observacao
from .constantes import (
    ALVO_REVENUE,
    ALVO_SPEND,
    DATASET_SINTETICO,
    CENARIO_OBSERVADO,
    HORIZONTE_PADRAO_DIAS,
    MODELO_LAGGED_LINEAR,
    MODELO_NAIVE_PERSISTENCE,
    N_MINIMO_TREINO,
)
from .contratos import BacktestResult, EvaluationWindow, PredictionRequest, SourceReceipt
from .excecoes import ContratoInvalido, DatasetInsuficiente, VazamentoDeFuturo
from .features import ObservacaoDiaria, montar_snapshot, serie_sem_futuro
from .hashes import chave_idempotencia, hash_canonico, id_canonico
from .modelos import ArtefatoLinear, treinar_linear
from .motor import codigo_hash_motor, prever
from .relogio import cutoff_utc, civil_de_instante, iso_civil, iso_instante, parse_civil, parse_instante
from .semantica import EstadoSemantico, valor_numerico_ou_nulo


def origens_possiveis(
    serie: Sequence[ObservacaoDiaria],
    campanha_id: str,
    horizonte: int,
    *,
    conta_id: Optional[str] = None,
    cutoff_em: Optional[str] = None,
) -> tuple[str, ...]:
    if horizonte != HORIZONTE_PADRAO_DIAS:
        raise ContratoInvalido("replay V1 só admite origens D+1")
    candidatas = [o for o in serie if o.campanha_id == campanha_id]
    contas = {o.conta_id for o in candidatas}
    if conta_id is None:
        if len(contas) != 1:
            raise ContratoInvalido("origens ambíguas entre contas")
        conta_id = next(iter(contas))
    elegiveis = [o for o in candidatas if o.conta_id == conta_id]
    if cutoff_em is not None:
        limite_instante = parse_instante(cutoff_em)
        limite_civil = civil_de_instante(cutoff_em)
        elegiveis = [
            o for o in elegiveis
            if parse_instante(o.lido_em) <= limite_instante and parse_civil(o.civil_date) <= limite_civil
        ]
    dias_set = {parse_civil(o.civil_date) for o in elegiveis}
    if len(dias_set) < horizonte + 2:
        return ()
    # Uma lacuna civil não pode transformar D+2 em D+1.
    return tuple(
        iso_civil(dia)
        for dia in sorted(dias_set)
        if dia + timedelta(days=HORIZONTE_PADRAO_DIAS) in dias_set
    )


def _y_de(
    serie: Sequence[ObservacaoDiaria],
    campanha_id: str,
    conta_id: str,
    target: str,
    alvo: str,
    cutoff_em: str,
) -> tuple[Optional[int], EstadoSemantico]:
    fechamento = cutoff_utc(target)
    limite = parse_instante(cutoff_em)
    vintages = sorted(
        (
            obs
            for obs in serie
            if obs.conta_id == conta_id
            and obs.campanha_id == campanha_id
            and obs.civil_date == target
            and fechamento < parse_instante(obs.lido_em) <= limite
        ),
        key=lambda obs: parse_instante(obs.lido_em),
    )
    if vintages:
        # Actual científico é a primeira vintage fechada. Uma correção tardia
        # fica auditável na série, mas não reescreve o replay já conciliado.
        obs = vintages[0]
        primeira_vintage = parse_instante(obs.lido_em)
        if any(
            parse_instante(outro.lido_em) == primeira_vintage and outro != obs
            for outro in vintages[1:]
        ):
            raise ContratoInvalido(
                f"actual com vintages contraditórias no mesmo instante: {conta_id}/{campanha_id}/{target}"
            )
        if alvo == ALVO_SPEND:
            return valor_numerico_ou_nulo(obs.spend_estado, obs.spend_micros), obs.spend_estado
        return valor_numerico_ou_nulo(obs.revenue_estado, obs.revenue_micros), obs.revenue_estado
    return None, EstadoSemantico.AUSENTE


def walk_forward(
    serie: Sequence[ObservacaoDiaria],
    *,
    campanha_id: str,
    procedencia: SourceReceipt,
    observado_em: str,
    versao_modelo: str = MODELO_LAGGED_LINEAR,
    n_minimo_treino: int = N_MINIMO_TREINO,
    conta_id: Optional[str] = None,
    split_aleatorio: bool = False,
) -> BacktestResult:
    if split_aleatorio:
        raise VazamentoDeFuturo("split aleatório recusado em série temporal")
    if procedencia.dataset_kind == DATASET_SINTETICO and procedencia.entra_em_contagens_reais:
        raise VazamentoDeFuturo("sintético marcado como real")

    candidatas = [o for o in serie if o.campanha_id == campanha_id]
    contas = {o.conta_id for o in candidatas}
    if conta_id is None:
        if len(contas) != 1:
            raise ContratoInvalido("walk-forward exige conta_id sem ambiguidade")
        conta_id = next(iter(contas))
    if not conta_id:
        raise ContratoInvalido("walk-forward sem conta_id")
    serie_conta = tuple(o for o in candidatas if o.conta_id == conta_id)
    kinds = {o.dataset_kind for o in serie_conta}
    if kinds != {procedencia.dataset_kind}:
        raise ContratoInvalido(
            f"fixture/dataset {sorted(kinds)} não pode se declarar {procedencia.dataset_kind}"
        )

    origens = origens_possiveis(
        serie_conta,
        campanha_id,
        HORIZONTE_PADRAO_DIAS,
        conta_id=conta_id,
        cutoff_em=observado_em,
    )
    falhas: list[dict[str, str]] = []
    pares_modelo: dict[str, list] = {ALVO_SPEND: [], ALVO_REVENUE: []}
    pares_naive: dict[str, list] = {ALVO_SPEND: [], ALVO_REVENUE: []}
    residuos_oof: dict[str, list[float]] = {ALVO_SPEND: [], ALVO_REVENUE: []}
    origens_avaliadas: set[str] = set()

    for i, origin in enumerate(origens):
        origin_d = parse_civil(origin)
        origin_cutoff = iso_instante(cutoff_utc(origin))
        as_of_serie = serie_sem_futuro(serie_conta, origin, origin_cutoff)
        treino_origens = origens[:i]
        if len(treino_origens) < n_minimo_treino:
            continue
        pares_treino: dict[str, list[tuple]] = {ALVO_SPEND: [], ALVO_REVENUE: []}
        for t_origin in treino_origens:
            t_d = parse_civil(t_origin)
            t_target = iso_civil(t_d + timedelta(days=HORIZONTE_PADRAO_DIAS))
            if parse_civil(t_target) > origin_d:
                raise VazamentoDeFuturo("par de treino com target posterior ao as-of")
            if parse_civil(t_target) == origin_d:
                # O actual do próprio dia ainda não fechou no cutoff da origem.
                continue
            t_cutoff = iso_instante(cutoff_utc(t_origin))
            for alvo in (ALVO_SPEND, ALVO_REVENUE):
                try:
                    snap = montar_snapshot(
                        serie_conta,
                        campanha_id=campanha_id,
                        origin=t_origin,
                        horizonte_dias=HORIZONTE_PADRAO_DIAS,
                        versao_modelo=versao_modelo,
                        procedencia=procedencia,
                        codigo_hash=codigo_hash_motor(),
                        alvo=alvo,
                        conta_id=conta_id,
                        observado_em=observado_em,
                        cutoff_em=t_cutoff,
                    )
                except VazamentoDeFuturo:
                    raise
                except Exception as exc:  # noqa: BLE001 — falha parcial auditável, nunca leakage
                    falhas.append({"origin": t_origin, "alvo": alvo, "erro": type(exc).__name__})
                    continue
                y, estado = _y_de(
                    serie_conta,
                    campanha_id,
                    conta_id,
                    t_target,
                    alvo,
                    origin_cutoff,
                )
                if y is None:
                    continue
                pares_treino[alvo].append((snap, y))
        artefatos: dict[str, ArtefatoLinear] = {}
        try:
            for alvo in (ALVO_SPEND, ALVO_REVENUE):
                artefatos[alvo] = treinar_linear(pares_treino[alvo], alvo, n_minimo=n_minimo_treino)
        except DatasetInsuficiente as exc:
            falhas.append({"origin": origin, "alvo": "*", "erro": str(exc)})
            continue

        janela_inicio = min(o.civil_date for o in as_of_serie if o.campanha_id == campanha_id)
        req_payload = {
            "kind": "walk_forward_request/v2",
            "conta_id": conta_id,
            "campanha_id": campanha_id,
            "origin": origin,
            "treino_origens": treino_origens,
            "cutoff_em": origin_cutoff,
            "versao_modelo": versao_modelo,
            "procedencia_hash": procedencia.hash_fonte,
        }
        req = PredictionRequest(
            request_id=id_canonico("wf-request", conta_id=conta_id, campanha_id=campanha_id, origin=origin, versao=versao_modelo),
            campanha_id=campanha_id,
            conta_id=conta_id,
            observado_em=observado_em,
            janela_inicio=janela_inicio,
            janela_fim=origin,
            horizonte_dias=HORIZONTE_PADRAO_DIAS,
            versao_modelo=versao_modelo,
            hash_inputs=hash_canonico(req_payload),
            procedencia=procedencia,
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia=chave_idempotencia(kind="wf", conta_id=conta_id, c=campanha_id, o=origin, v=versao_modelo, cenario=CENARIO_OBSERVADO),
            alvos=(ALVO_SPEND, ALVO_REVENUE),
            mutacao_campanha=False,
            cenario=CENARIO_OBSERVADO,
            cutoff_em=origin_cutoff,
        )
        preds = prever(
            req,
            serie,
            artefatos=artefatos,
            residuos_oof={k: tuple(v) for k, v in residuos_oof.items() if v},
        )
        naive_req = PredictionRequest(
            request_id=id_canonico("wf-request", conta_id=conta_id, campanha_id=campanha_id, origin=origin, versao=MODELO_NAIVE_PERSISTENCE),
            campanha_id=campanha_id,
            conta_id=conta_id,
            observado_em=observado_em,
            janela_inicio=janela_inicio,
            janela_fim=origin,
            horizonte_dias=HORIZONTE_PADRAO_DIAS,
            versao_modelo=MODELO_NAIVE_PERSISTENCE,
            hash_inputs=req.hash_inputs,
            procedencia=procedencia,
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia=chave_idempotencia(kind="wf-naive", conta_id=conta_id, c=campanha_id, o=origin, cenario=CENARIO_OBSERVADO),
            alvos=(ALVO_SPEND, ALVO_REVENUE),
            cenario=CENARIO_OBSERVADO,
            cutoff_em=origin_cutoff,
        )
        naive_preds = prever(naive_req, serie)
        target = iso_civil(origin_d + timedelta(days=HORIZONTE_PADRAO_DIAS))
        por_alvo = {pred.alvo: pred for pred in preds}
        naive_por_alvo_pred = {pred.alvo: pred for pred in naive_preds}
        for alvo in (ALVO_SPEND, ALVO_REVENUE):
            pred = por_alvo.get(alvo)
            pred_naive = naive_por_alvo_pred.get(alvo)
            y, estado = _y_de(
                serie_conta,
                campanha_id,
                conta_id,
                target,
                alvo,
                observado_em,
            )
            if (
                pred is None
                or pred_naive is None
                or pred.ponto_micros is None
                or pred_naive.ponto_micros is None
                or y is None
            ):
                continue
            if pred.pair_id != pred_naive.pair_id:
                raise VazamentoDeFuturo("candidato e baseline produziram pair_ids diferentes")
            out = outcome_de_observacao(
                campanha_id=campanha_id,
                target_date=target,
                origin_date=origin,
                alvo=alvo,
                micros=y,
                estado=estado,
                procedencia=procedencia,
                observado_em=observado_em,
                conta_id=conta_id,
                cenario=CENARIO_OBSERVADO,
            )
            if out.pair_id != pred.pair_id:
                raise VazamentoDeFuturo("actual D+1 não pertence ao pair_id previsto")
            pares_modelo[alvo].append((pred, out))
            pares_naive[alvo].append((pred_naive, out))
            residuos_oof[alvo].append(abs(pred.ponto_micros - y) / 1_000_000.0)
            origens_avaliadas.add(origin)

    metricas_por_alvo = {
        alvo: avaliar_pares(
            pares,
            dataset_kind=procedencia.dataset_kind,
            entra_em_contagens_reais=procedencia.entra_em_contagens_reais,
        )
        for alvo, pares in pares_modelo.items()
    }
    naive_por_alvo = {
        alvo: avaliar_pares(
            pares_naive[alvo],
            dataset_kind=procedencia.dataset_kind,
            entra_em_contagens_reais=procedencia.entra_em_contagens_reais,
        )
        for alvo in (ALVO_SPEND, ALVO_REVENUE)
    }
    pair_ids_por_alvo = {
        alvo: metricas_por_alvo[alvo].pair_ids
        for alvo in (ALVO_SPEND, ALVO_REVENUE)
    }
    n_total = min((len(ids) for ids in pair_ids_por_alvo.values()), default=0)
    if not origens or n_total == 0 or not origens_avaliadas:
        raise DatasetInsuficiente(
            f"série insuficiente para walk-forward (origens={len(origens)}, pares_pareados={n_total})"
        )

    inicio_avaliacao = min(origens_avaliadas, key=parse_civil)
    fim_avaliacao = max(origens_avaliadas, key=parse_civil)
    population_hash = hash_canonico({
        "schema": "orakul-evaluation-population/v2",
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "cenario": CENARIO_OBSERVADO,
        "horizonte_dias": HORIZONTE_PADRAO_DIAS,
        "janela_inicio": inicio_avaliacao,
        "janela_fim": fim_avaliacao,
        "pair_ids_por_alvo": pair_ids_por_alvo,
        "dataset_kind": procedencia.dataset_kind,
        "source_hash": procedencia.hash_fonte,
    })
    janela_completa = n_total >= 21 and (
        parse_civil(fim_avaliacao) - parse_civil(inicio_avaliacao)
    ).days >= 20
    janela = EvaluationWindow(
        window_id=id_canonico("evaluation-window", conta_id=conta_id, campanha_id=campanha_id, modelo=versao_modelo, population_hash=population_hash),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=inicio_avaliacao,
        janela_fim=fim_avaliacao,
        horizonte_dias=HORIZONTE_PADRAO_DIAS,
        versao_modelo=versao_modelo,
        hash_inputs=hash_canonico({"population_hash": population_hash, "modelo": versao_modelo}),
        procedencia=procedencia,
        estado_semantico=EstadoSemantico.MEDIDO,
        chave_idempotencia=chave_idempotencia(kind="window", conta_id=conta_id, c=campanha_id, v=versao_modelo, population_hash=population_hash),
        n_pares=n_total,
        completa=janela_completa,
        split="walk_forward_temporal",
        cenario=CENARIO_OBSERVADO,
        population_hash=population_hash,
    )
    estado = EstadoSemantico.MEDIDO if n_total >= n_minimo_treino else EstadoSemantico.AUSENTE
    resultado_hash = hash_canonico({
        "population_hash": population_hash,
        "modelo": versao_modelo,
        "prediction_hashes": {
            alvo: [pred.hash_inputs for pred, _ in pares_modelo[alvo]]
            for alvo in (ALVO_SPEND, ALVO_REVENUE)
        },
        "metricas": {alvo: m.serializar() for alvo, m in metricas_por_alvo.items()},
        "naive": {alvo: m.serializar() for alvo, m in naive_por_alvo.items()},
    })
    return BacktestResult(
        result_id=id_canonico("backtest", conta_id=conta_id, campanha_id=campanha_id, modelo=versao_modelo, population_hash=population_hash),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=janela.janela_inicio,
        janela_fim=janela.janela_fim,
        horizonte_dias=HORIZONTE_PADRAO_DIAS,
        versao_modelo=versao_modelo,
        hash_inputs=resultado_hash,
        procedencia=procedencia,
        estado_semantico=estado,
        chave_idempotencia=chave_idempotencia(kind="backtest", conta_id=conta_id, c=campanha_id, v=versao_modelo, population_hash=population_hash),
        janela=janela,
        metricas_por_alvo=metricas_por_alvo,
        naive_por_alvo=naive_por_alvo,
        falhas_parciais=tuple(falhas),
        # Completar o backtest implica fail-closed: VazamentoDeFuturo aborta antes.
        leakage_detectado=False,
        dataset_kind=procedencia.dataset_kind,
        entra_em_contagens_reais=procedencia.entra_em_contagens_reais,
        n_total=n_total,
        pair_ids_por_alvo=pair_ids_por_alvo,
        population_hash=population_hash,
        cenario=CENARIO_OBSERVADO,
    )
