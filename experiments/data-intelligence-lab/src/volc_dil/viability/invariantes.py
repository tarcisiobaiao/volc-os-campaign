"""Verificador de invariantes em tempo de execução (exit code 4 na CLI).

Confere o RESULTADO contra a ENTRADA: nada aqui recalcula a economia; só verifica que o
resultado não viola regras que o kernel promete. Serve de rede contra mutantes e regressões.

V2 (integrador): além das regras V1, governa evidência de CUSTO e CLIQUES, freshness (SLA),
flags de qualidade `invalid*`, cobertura de receita, evidência da moeda do custo, e a separação
entre max_loss, spend_cap e contribuição.
"""
from __future__ import annotations

from datetime import timedelta

from .contrato import REALIZADA, SEM_VALOR, EntradaViabilidade, Evidencia, hash_entrada
from .gate import Confianca, ResultadoViabilidade, Veredito, _hash_resultado

POSITIVOS = (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
NAO_DECISIVA = (Evidencia.PROJECTED, Evidencia.ESTIMATED, Evidencia.IMMATURE)


class InvarianteViolada(AssertionError):
    pass


def _medidas(e: EntradaViabilidade):
    out = [("cliques", e.cliques), ("custo", e.custo), ("receita", e.receita)]
    if e.visitas is not None:
        out.append(("visitas", e.visitas))
    return out


def _stale(e: EntradaViabilidade) -> list[str]:
    sla = timedelta(days=int(getattr(e, "freshness_sla_dias", 7)))
    return [n for n, m in _medidas(e) if getattr(m, "observado_em", None) is not None and m.observado_em < e.as_of - sla]


def _invalid_flags(e: EntradaViabilidade) -> list[str]:
    out = []
    for n, m in _medidas(e):
        for f in getattr(m, "flags_qualidade", ()) or ():
            if str(f).startswith("invalid"):
                out.append(f"{n}:{f}")
    for f in getattr(e, "flags_qualidade", ()) or ():
        if str(f).startswith("invalid"):
            out.append(f"entrada:{f}")
    return out


def verificar_invariantes(e: EntradaViabilidade, r: ResultadoViabilidade) -> None:
    falhas: list[str] = []
    if r.input_hash != hash_entrada(e):
        falhas.append("input_hash não corresponde à entrada")
    if r.result_hash != _hash_resultado(r.para_json(com_hash=False)):
        falhas.append("result_hash não corresponde ao resultado")
    j = r.para_json()
    if j["external_actions"] != 0:
        falhas.append("resultado declara ação externa")
    # ausência ≠ zero
    if e.receita.evidencia in SEM_VALOR and r.contribution_observed is not None:
        falhas.append("receita ausente mas contribuição calculada (ausência virou zero)")
    if e.custo.evidencia in SEM_VALOR and r.observed_cpc is not None:
        falhas.append("custo ausente mas CPC calculado")
    if e.cliques.evidencia in SEM_VALOR and r.observed_cpc is not None:
        falhas.append("cliques ausentes mas CPC calculado")
    # projeção/imaturo/estimado nunca realizado — para receita, custo e cliques
    for nome, m in (("receita", e.receita), ("custo", e.custo), ("cliques", e.cliques)):
        if m.evidencia in NAO_DECISIVA and r.verdict in POSITIVOS:
            falhas.append(f"{nome} {m.evidencia.value} produziu veredito {r.verdict.value}")
        if m.evidencia in NAO_DECISIVA and r.confidence_class is Confianca.HIGH:
            falhas.append(f"{nome} {m.evidencia.value} com confiança high")
    if e.receita.evidencia is Evidencia.IMMATURE and r.verdict is not Veredito.INSUFFICIENT_EVIDENCE:
        falhas.append("receita imatura decidiu viabilidade")
    if e.receita.evidencia not in REALIZADA and r.verdict in POSITIVOS:
        falhas.append(f"receita {e.receita.evidencia.value} (não realizada) produziu veredito positivo")
    # freshness e qualidade
    stale = _stale(e)
    if stale and (r.verdict in POSITIVOS or r.confidence_class is Confianca.HIGH):
        falhas.append(f"medida(s) stale {stale} com veredito/confiança positivos")
    inval = _invalid_flags(e)
    if inval and (r.verdict in POSITIVOS or r.confidence_class is Confianca.HIGH):
        falhas.append(f"flag(s) invalid {inval} com veredito/confiança positivos")
    # cobertura de receita
    cob = getattr(e.janela, "cobertura_receita_ppm", None)
    if r.verdict in POSITIVOS and (cob is None or cob < 1_000_000):
        falhas.append(f"veredito positivo com cobertura de receita {cob!r}")
    # moeda/câmbio não provados nunca viram viable/already (receita E custo)
    moeda_ok = e.receita.moeda_evidencia is Evidencia.OBSERVED and e.custo.moeda_evidencia is Evidencia.OBSERVED
    precisa_cambio = e.receita.valor is not None and e.custo.valor is not None and e.receita.valor.moeda != e.custo.valor.moeda
    cambio_ok = (not precisa_cambio) or e.cambio.evidencia is Evidencia.OBSERVED
    if r.verdict in POSITIVOS and not (moeda_ok and cambio_ok):
        falhas.append("veredito permissivo com moeda/câmbio não provados")
    if e.receita.moeda_evidencia is Evidencia.INVALID and r.verdict is not Veredito.INSUFFICIENT_EVIDENCE:
        falhas.append("moeda inválida decidiu viabilidade")
    # teto só com tolerância do owner (autorizada)
    if not e.perda_maxima.informada() and (r.max_experiment_spend is not None or r.max_experiment_clicks is not None):
        falhas.append("teto calculado sem perda_maxima autorizada do owner")
    # max_loss, spend_cap e contribuição são campos separados e coerentes
    max_loss = getattr(r, "max_loss", None)
    if max_loss is not None and e.perda_maxima.valor is not None and max_loss != e.perda_maxima.valor:
        falhas.append("max_loss difere da perda_maxima do owner")
    if r.max_experiment_spend is not None and e.perda_maxima.valor is not None and r.max_experiment_spend.moeda != e.perda_maxima.valor.moeda:
        falhas.append("spend_cap em moeda diferente da perda_maxima")
    # inviável nunca propõe gasto
    if r.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS and r.max_experiment_spend is not None:
        falhas.append("inviável com teto de gasto")
    if falhas:
        raise InvarianteViolada("; ".join(falhas))
