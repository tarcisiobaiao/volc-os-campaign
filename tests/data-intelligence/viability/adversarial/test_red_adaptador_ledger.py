"""RED — adapter `de_ledger_campanha_dia`: custo filtrado, datas duplicadas, moedas heterogêneas, proveniência inventada.

Achados 1, 9, 11 (via adapter) e 12 da missão V2. Nenhum teste aqui precisa de `perda_maxima`
para chegar ao veredito, de propósito: `already_profitable` na V1 não exige teto, então a
falha fica puramente no lado econômico.
"""
from __future__ import annotations

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.adaptadores import de_ledger_campanha_dia
from volc_dil.viability.contrato import ContratoViabilidadeViolado
from volc_dil.viability.gate import Veredito, avaliar

from _entradas import AS_OF


def _linha(dia: str, custo: int, cliques: int, receita, *, status: str = "observed", maduro: bool = True, custo_moeda: str = "BRL") -> dict:
    return {"dia": dia, "custo_micros": custo, "custo_moeda": custo_moeda, "custo_moeda_evidencia": "observed", "cliques": cliques,
            "receita_micros": receita, "receita_moeda": "BRL", "receita_moeda_evidencia": "observed", "receita_status": status,
            "maduro": maduro, "disponivel_em": AS_OF.isoformat()}


def test_red01_dia_maduro_com_custo_alto_e_receita_ausente_nao_pode_virar_already_profitable():
    """Achado 1. Três dias maduros lucrativos (custo 100, receita 150, 200 cliques cada) e um
    quarto dia maduro com custo 600 e receita AUSENTE (status `missing`).

    V1 está errada porque `com_ambos` só soma custo dos dias que TAMBÉM têm receita: o custo do
    4º dia (600 BRL, 2/3 do gasto real) some da economia e o kernel declara `already_profitable`
    com contribuição +150 — a campanha de verdade perdeu 450 BRL. Ausência de receita virou
    ausência de custo, que é pior do que virar zero.

    V2 deve somar o custo de TODOS os dias maduros (900 BRL), tratar a cobertura de receita
    (3/4) como lacuna própria e nunca devolver `already_profitable`.
    """
    linhas = [_linha("2026-10-01", 100_000_000, 200, 150_000_000), _linha("2026-10-02", 100_000_000, 200, 150_000_000),
              _linha("2026-10-03", 100_000_000, 200, 150_000_000), _linha("2026-10-04", 600_000_000, 200, None, status="missing")]
    e = de_ledger_campanha_dia("cand-red-01", linhas, as_of=AS_OF, vertical="v", pais="BR")
    r = avaliar(e)
    assert r.verdict is not Veredito.ALREADY_PROFITABLE, f"V1 ignora o custo do dia sem receita: {r.verdict.value}, contribuição {r.contribution_observed}"
    assert e.custo.valor == Dinheiro(900_000_000, "BRL"), "custo maduro precisa somar os 4 dias"
    assert r.contribution_observed is None or r.contribution_observed.micros < 0


def test_red09_datas_duplicadas_no_ledger_nao_inflam_dias_maduros_nem_custo():
    """Achado 9. A mesma linha (dia 2026-10-01) aparece duas vezes, mais dois dias distintos.

    V1 está errada porque conta `dias_maduros = len(com_ambos)` = 4 e soma custo/receita/cliques
    em dobro: uma releitura duplicada do coletor dobra o volume e passa o limiar de maturidade
    sem nenhum dia novo.

    V2 deve deduplicar por data (3 dias maduros, custo 300 BRL) e registrar flag de qualidade
    mencionando a duplicata.
    """
    base = _linha("2026-10-01", 100_000_000, 300, 150_000_000)
    linhas = [dict(base), dict(base), _linha("2026-10-02", 100_000_000, 300, 150_000_000), _linha("2026-10-03", 100_000_000, 300, 150_000_000)]
    e = de_ledger_campanha_dia("cand-red-09", linhas, as_of=AS_OF)
    assert e.janela.dias_maduros == 3, f"V1 conta a data duplicada: dias_maduros={e.janela.dias_maduros}"
    assert e.custo.valor == Dinheiro(300_000_000, "BRL") and e.cliques.valor == 900
    assert any("duplic" in f for f in e.flags_qualidade), e.flags_qualidade


def test_red12_moedas_heterogeneas_no_custo_sao_recusadas():
    """Achado 12. Dia 1 com custo em BRL, dia 2 com custo em USD.

    V1 está errada porque `moeda_custo = next(...)` pega a primeira moeda e soma micros de USD
    como se fossem BRL — conversão implícita 1:1, que o contrato de `Dinheiro` proíbe.

    V2 deve recusar (ContratoViabilidadeViolado) linhas com moedas heterogêneas.
    """
    linhas = [_linha("2026-10-01", 100_000_000, 300, 150_000_000), _linha("2026-10-02", 100_000_000, 300, 150_000_000, custo_moeda="USD"),
              _linha("2026-10-03", 100_000_000, 300, 150_000_000)]
    with pytest.raises(ValueError):  # ContratoViabilidadeViolado é ValueError
        de_ledger_campanha_dia("cand-red-12", linhas, as_of=AS_OF)


@pytest.mark.parametrize("perda", [
    {"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14, "proveniencia": "owner"},
    {"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14, "proveniencia": "bia"},
    {"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14},
], ids=["proveniencia_owner", "proveniencia_bia", "sem_proveniencia_vira_owner"])
def test_red11_adapter_nao_aceita_perda_maxima_sem_autorizacao(perda):
    """Achado 11 (lado do adapter). `perda_maxima` chega como dict com valor e só uma string de
    proveniência ("owner", "bia") — ou sem proveniência nenhuma.

    V1 está errada porque `_perda` aceita qualquer texto e, sem texto, INVENTA `"owner"`: a
    tolerância do dono — a única autoridade de gasto do kernel — pode ser fabricada por quem
    monta o dict (inclusive a Bia por outro caminho).

    V2 deve aceitar `perda_maxima` somente com um dict `autorizacao` verificável (id, versão,
    hash, emissor identificado, vigência) e recusar o resto com ContratoViabilidadeViolado.
    """
    linhas = [_linha("2026-10-01", 100_000_000, 300, 150_000_000)]
    with pytest.raises(ContratoViabilidadeViolado):
        de_ledger_campanha_dia("cand-red-11", linhas, as_of=AS_OF, perda_maxima=perda)
