"""Política champion/challenger versionada. Promoção é proposta, nunca ação."""

from __future__ import annotations

from typing import Optional

from .constantes import (
    ALVO_REVENUE,
    ALVO_SPEND,
    JANELA_MINIMA_DIAS_PROMOCAO,
    MELHORIA_MINIMA_WAPE,
    N_MINIMO_PROMOCAO,
    POLITICA_CC,
    REGRESSAO_CRITICA_MAE_SPEND,
)
from .contratos import BacktestResult, ChampionChallengerDecision, SourceReceipt
from .excecoes import PopulacaoIncompativel
from .hashes import chave_idempotencia, hash_canonico, id_canonico
from .semantica import EstadoSemantico


def decidir_champion_challenger(
    *,
    champion: Optional[BacktestResult],
    challenger: BacktestResult,
    procedencia: SourceReceipt,
    observado_em: str,
    previous_champion_id: Optional[str] = None,
) -> ChampionChallengerDecision:
    explicacao: list[str] = []
    if (
        procedencia.dataset_kind != challenger.dataset_kind
        or procedencia.entra_em_contagens_reais != challenger.entra_em_contagens_reais
        or procedencia.hash_fonte != challenger.procedencia.hash_fonte
    ):
        raise PopulacaoIncompativel("procedência da decisão diverge do challenger")
    if champion is not None and (
        procedencia.dataset_kind != champion.dataset_kind
        or procedencia.entra_em_contagens_reais != champion.entra_em_contagens_reais
        or procedencia.hash_fonte != champion.procedencia.hash_fonte
    ):
        raise PopulacaoIncompativel("procedência da decisão diverge do champion")
    if champion is not None:
        campos_identidade = (
            "conta_id",
            "campanha_id",
            "janela_inicio",
            "janela_fim",
            "horizonte_dias",
            "dataset_kind",
            "entra_em_contagens_reais",
            "cenario",
            "population_hash",
        )
        divergentes = [
            campo
            for campo in campos_identidade
            if getattr(champion, campo) != getattr(challenger, campo)
        ]
        if divergentes:
            raise PopulacaoIncompativel(
                "champion/challenger com identidade ou janela distinta: "
                + ",".join(divergentes)
            )
        if dict(champion.pair_ids_por_alvo) != dict(challenger.pair_ids_por_alvo):
            raise PopulacaoIncompativel("champion/challenger não compartilham os mesmos pair_ids")
        if champion.n_total != challenger.n_total:
            raise PopulacaoIncompativel("champion/challenger têm populações de tamanhos diferentes")
        if champion.procedencia.hash_fonte != challenger.procedencia.hash_fonte:
            raise PopulacaoIncompativel("champion/challenger vieram de fontes diferentes")
    n = challenger.n_total
    janela_completa = challenger.janela.completa and (
        (parse_dias(challenger.janela.janela_fim) - parse_dias(challenger.janela.janela_inicio))
        >= JANELA_MINIMA_DIAS_PROMOCAO - 1
    )
    metricas = ("wape_revenue", "mae_spend")
    pair_ids_hash = hash_canonico(challenger.pair_ids_por_alvo)
    chave = chave_idempotencia(
        kind="cc",
        conta_id=challenger.conta_id,
        campanha_id=challenger.campanha_id,
        champ=champion.versao_modelo if champion else None,
        chal=challenger.versao_modelo,
        population_hash=challenger.population_hash,
        cenario=challenger.cenario,
        politica=POLITICA_CC,
    )

    def decision(veredito: str, promocao: str, extra: list[str]) -> ChampionChallengerDecision:
        return ChampionChallengerDecision(
            decision_id=id_canonico(
                "cc-decision",
                conta_id=challenger.conta_id,
                campanha_id=challenger.campanha_id,
                champion=champion.versao_modelo if champion else None,
                challenger=challenger.versao_modelo,
                population_hash=challenger.population_hash,
                politica=POLITICA_CC,
            ),
            campanha_id=challenger.campanha_id,
            conta_id=challenger.conta_id,
            observado_em=observado_em,
            janela_inicio=challenger.janela_inicio,
            janela_fim=challenger.janela_fim,
            horizonte_dias=1,
            versao_modelo=challenger.versao_modelo,
            hash_inputs=hash_canonico({
                "champ": champion.hash_inputs if champion else None,
                "chal": challenger.hash_inputs,
                "population_hash": challenger.population_hash,
                "pair_ids_hash": pair_ids_hash,
                "politica": POLITICA_CC,
            }),
            procedencia=procedencia,
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia=chave,
            champion_id=champion.versao_modelo if champion else None,
            challenger_id=challenger.versao_modelo,
            veredito=veredito,
            promocao=promocao,
            explicacao=tuple(explicacao + extra),
            metricas_consideradas=metricas,
            n_pares=n,
            janela_completa=janela_completa,
            previous_champion_id=previous_champion_id or (champion.versao_modelo if champion else None),
            politica_id=POLITICA_CC,
            mutacao_campanha=False,
            population_hash=challenger.population_hash,
            pair_ids_hash=pair_ids_hash,
            cenario=challenger.cenario,
        )

    if n < N_MINIMO_PROMOCAO:
        explicacao.append(f"n={n} < mínimo {N_MINIMO_PROMOCAO}")
        return decision("evidencia_insuficiente", "preservar", ["amostra pequena não promove"])
    if not janela_completa:
        explicacao.append("janela incompleta")
        return decision("evidencia_insuficiente", "preservar", ["janela incompleta não promove"])

    chal_rev = challenger.metricas_por_alvo.get(ALVO_REVENUE)
    chal_sp = challenger.metricas_por_alvo.get(ALVO_SPEND)
    if not chal_rev or not chal_sp or chal_rev.wape is None or chal_sp.mae is None:
        return decision("evidencia_insuficiente", "preservar", ["métricas ausentes"])
    if not chal_rev.evidencia_suficiente or not chal_sp.evidencia_suficiente:
        return decision("evidencia_insuficiente", "preservar", ["métrica sem evidência suficiente"])

    if champion is None:
        explicacao.append("não há champion; desafiante elegível a champion inicial")
        return decision("champion_inicial_proposto", "proposta", ["ainda é proposta, não auto-promoção"])

    champ_rev = champion.metricas_por_alvo.get(ALVO_REVENUE)
    champ_sp = champion.metricas_por_alvo.get(ALVO_SPEND)
    if not champ_rev or not champ_sp or champ_rev.wape is None or champ_sp.mae is None:
        return decision("evidencia_insuficiente", "preservar", ["champion sem métricas comparáveis"])

    if champ_sp.mae and chal_sp.mae > champ_sp.mae * (1.0 + REGRESSAO_CRITICA_MAE_SPEND):
        explicacao.append(
            f"regressão crítica MAE spend {chal_sp.mae:.4f} vs champion {champ_sp.mae:.4f}"
        )
        return decision("regressao_critica", "preservar", ["veto de regressão crítica"])

    if champ_rev.wape == 0:
        if chal_rev.wape == 0:
            melhoria = 0.0
        else:
            explicacao.append(
                f"champion tem WAPE zero; challenger positivo={chal_rev.wape:.4f} é regressão, não empate"
            )
            explicacao.append(f"MAE spend chal={chal_sp.mae:.4f} champ={champ_sp.mae:.4f}")
            return decision(
                "preservar_champion",
                "preservar",
                ["divisão por zero não transforma regressão em empate"],
            )
    else:
        melhoria = (champ_rev.wape - chal_rev.wape) / champ_rev.wape
    explicacao.append(f"ΔWAPE receita={melhoria:.4f} (mínimo {MELHORIA_MINIMA_WAPE})")
    explicacao.append(f"MAE spend chal={chal_sp.mae:.4f} champ={champ_sp.mae:.4f}")
    if melhoria > MELHORIA_MINIMA_WAPE and chal_sp.mae <= champ_sp.mae * (1.0 + REGRESSAO_CRITICA_MAE_SPEND):
        return decision("propor_promocao", "proposta", ["duas métricas; promoção proposta"])
    if abs(melhoria) <= 1e-6:
        return decision("empate", "preservar", ["empate preserva champion"])
    return decision("preservar_champion", "preservar", ["challenger não venceu o pacote de métricas"])


def parse_dias(iso: str) -> int:
    from datetime import date

    d = date.fromisoformat(iso)
    return d.toordinal()


def propor_rollback(
    *,
    champion_atual: str,
    champion_anterior: str,
    motivo: str,
    procedencia: SourceReceipt,
    observado_em: str,
    campanha_id: Optional[str] = None,
    conta_id: Optional[str] = None,
) -> ChampionChallengerDecision:
    if not campanha_id or not conta_id:
        raise PopulacaoIncompativel("rollback exige conta_id e campanha_id")
    population_hash = hash_canonico({
        "kind": "rollback_sem_populacao_de_metricas",
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "champion_atual": champion_atual,
        "champion_anterior": champion_anterior,
    })
    return ChampionChallengerDecision(
        decision_id=id_canonico(
            "cc-rollback",
            conta_id=conta_id,
            campanha_id=campanha_id,
            champion_atual=champion_atual,
            champion_anterior=champion_anterior,
        ),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=observado_em[:10],
        janela_fim=observado_em[:10],
        horizonte_dias=1,
        versao_modelo=champion_anterior,
        hash_inputs=hash_canonico({"from": champion_atual, "to": champion_anterior, "motivo": motivo}),
        procedencia=procedencia,
        estado_semantico=EstadoSemantico.MEDIDO,
        chave_idempotencia=chave_idempotencia(
            kind="rollback",
            conta_id=conta_id,
            campanha_id=campanha_id,
            a=champion_atual,
            b=champion_anterior,
        ),
        champion_id=champion_atual,
        challenger_id=champion_anterior,
        veredito="propor_rollback",
        promocao="rollback_proposto",
        explicacao=(motivo, "rollback é proposta; não executa campanha"),
        metricas_consideradas=("wape_revenue", "mae_spend"),
        n_pares=0,
        janela_completa=False,
        previous_champion_id=champion_anterior,
        politica_id=POLITICA_CC,
        mutacao_campanha=False,
        population_hash=population_hash,
        pair_ids_hash=hash_canonico(()),
    )
