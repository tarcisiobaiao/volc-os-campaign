"""Verificador de invariantes em tempo de execução (exit code 4 na CLI).

Confere o RESULTADO contra a ENTRADA: nada aqui recalcula a economia; só verifica que o
resultado não viola regras que o kernel promete. Serve de rede contra mutantes e regressões.
"""
from __future__ import annotations

from .contrato import REALIZADA, SEM_VALOR, EntradaViabilidade, Evidencia, hash_entrada
from .gate import ResultadoViabilidade, Veredito, _hash_resultado


class InvarianteViolada(AssertionError):
    pass


def verificar_invariantes(e: EntradaViabilidade, r: ResultadoViabilidade) -> None:
    falhas: list[str] = []
    if r.input_hash != hash_entrada(e):
        falhas.append("input_hash não corresponde à entrada")
    if r.result_hash != _hash_resultado(r.para_json(com_hash=False)):
        falhas.append("result_hash não corresponde ao resultado")
    if r.para_json()["external_actions"] != 0:
        falhas.append("resultado declara ação externa")
    # ausência ≠ zero
    if e.receita.evidencia in SEM_VALOR and r.contribution_observed is not None:
        falhas.append("receita ausente mas contribuição calculada (ausência virou zero)")
    if e.custo.evidencia in SEM_VALOR and r.observed_cpc is not None:
        falhas.append("custo ausente mas CPC calculado")
    # projeção/imaturo/estimado nunca realizado
    if e.receita.evidencia not in REALIZADA and r.verdict in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE):
        falhas.append(f"receita {e.receita.evidencia.value} produziu veredito {r.verdict.value}")
    if e.receita.evidencia is Evidencia.IMMATURE and r.verdict is not Veredito.INSUFFICIENT_EVIDENCE:
        falhas.append("receita imatura decidiu viabilidade")
    # moeda/câmbio não provados nunca viram viable/already
    moeda_ok = e.receita.moeda_evidencia is Evidencia.OBSERVED
    precisa_cambio = e.receita.valor is not None and e.custo.valor is not None and e.receita.valor.moeda != e.custo.valor.moeda
    cambio_ok = (not precisa_cambio) or e.cambio.evidencia is Evidencia.OBSERVED
    if r.verdict in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE) and not (moeda_ok and cambio_ok):
        falhas.append("veredito permissivo com moeda/câmbio não provados")
    if e.receita.moeda_evidencia is Evidencia.INVALID and r.verdict is not Veredito.INSUFFICIENT_EVIDENCE:
        falhas.append("moeda inválida decidiu viabilidade")
    # teto só com tolerância do owner
    if not e.perda_maxima.informada() and (r.max_experiment_spend is not None or r.max_experiment_clicks is not None):
        falhas.append("teto calculado sem perda_maxima do owner")
    if r.max_experiment_spend is not None and e.perda_maxima.valor is not None and r.max_experiment_clicks is not None:
        pass  # a relação perda esperada <= tolerância é verificada nos testes do teto
    # inviável nunca propõe gasto
    if r.verdict is Veredito.STRUCTURALLY_UNVIABLE and r.max_experiment_spend is not None:
        falhas.append("inviável com teto de gasto")
    if falhas:
        raise InvarianteViolada("; ".join(falhas))
