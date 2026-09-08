"""O golden do grão conjunto/dia, contra a operação real sanitizada.

64 linhas campanha/dia: 62 com receita atribuída via conjunto e 2 sem UTM de
conjunto no GAM, ambas sem entrega. R$ 1.029,41 investidos, R$ 1.140,73 de
receita, ROAS agregado ~1,108.

O que este arquivo prova, e que a suíte anterior não podia provar porque
codificava o join errado como comportamento esperado:

- a receita chega pelo CONJUNTO (`utm_campaign_value = adset_id`);
- a campanha é a SOMA dos conjuntos, com igualdade exata em Decimal;
- somar campaign-level com adset-level é RECUSADO, não tolerado;
- ausência não vira zero, e zero medido não vira ausência;
- o mesmo grão duas vezes é recusado antes de virar total;
- nenhum caminho resolve nada por nome.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.trafego.meta.atribuicao import (
    ATRIBUIDO_VIA_ADSET,
    ESCOPO_CAMPANHA,
    ESCOPO_CONJUNTO,
    SEM_LEITURA_GAM,
    SEM_UTM_ADSET_NO_GAM,
    AtribuicaoMetaInvalida,
    LinhaAtribuicao,
    agregar_campanha_dia,
    agregar_campanha_periodo,
    agregar_conjunto_periodo,
    id_meta_valido,
    linha_de_conjunto_dia,
    reconciliar_com_campaign_level,
    totalizar,
)

GOLDEN = Path(__file__).parent / "goldens" / "atribuicao-meta-adset-v1.json"

#: Ids SINTÉTICOS para as fixtures escritas à mão.
#:
#: ⚠️ Eles não vêm da operação real e não têm correspondência com nada. Usar um
#: id real aqui — mesmo "só num teste" — devolveria ao repositório a identidade
#: que o gerador do golden tirou de propósito.
CAMPANHA_SINTETICA = "900000000000001"
CONJUNTO_SINTETICO = "900000000000002"
CAMPANHA_SINTETICA_2 = "900000000000003"
CONJUNTO_SINTETICO_2 = "900000000000004"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _linhas(golden: dict) -> list[LinhaAtribuicao]:
    """Converte o golden nas linhas do contrato.

    As duas linhas sem conjunto NÃO viram `LinhaAtribuicao`: o grão exige
    `adset_id`, e é exatamente por isso que elas continuam distinguíveis — elas
    não são um conjunto com receita zero, são uma campanha sem conjunto
    conhecido. Elas são conferidas à parte, em
    `test_campanha_sem_utm_nao_vira_conjunto_com_receita_zero`.
    """
    saida = []
    for r in golden["linhas"]:
        if r["adset_id"] is None:
            continue
        saida.append(LinhaAtribuicao(
            account_ref=r["account_ref"],
            campaign_id=r["campaign_id"],
            adset_id=r["adset_id"],
            date=date.fromisoformat(r["date"]),
            project_id=r["project_id"],
            spend=Decimal(r["spend"]),
            impressions=r["impressions"],
            clicks=r["clicks"],
            gam_revenue_original=Decimal(r["gam_revenue_original"]),
            gam_revenue_brl=Decimal(r["gam_revenue_brl"]),
            gam_impressions=r["gam_impressions"],
            gam_clicks=r["gam_clicks"],
            attribution_method="GAM.utm_campaign_value = adset_id",
            mapping_status=ATRIBUIDO_VIA_ADSET,
            currency="BRL",
            timezone="America/Sao_Paulo",
        ))
    return saida


# ---------------------------------------------------------------------------
# O golden: os números da operação real
# ---------------------------------------------------------------------------

def test_o_golden_carrega_a_forma_da_operacao_real(golden):
    inv = golden["invariantes"]
    assert inv["linhas_campanha_dia"] == 64
    assert inv["campanha_dia_atribuidas"] == 62
    assert inv["campanha_dia_sem_utm"] == 2
    assert inv["total_spend"] == "1029.410000"
    assert inv["total_revenue_brl"] == "1140.73"
    # Sanitização, provada pela FORMA e não por comparação com id real.
    #
    # ⚠️ A primeira versão listava três ids reais aqui para afirmar que eles
    # NÃO estavam no golden. Achado do revisor adversarial: isso versionava
    # justamente o que a sanitização removeu — com o sal público do gerador,
    # os literais permitiam reconstruir a ligação com as linhas do golden. Um
    # teste de sanitização não pode carregar o dado que sanitiza.
    #
    # A prova estrutural é mais forte e não vaza nada: TODO id do golden tem a
    # forma sintética (prefixo '9', 15 dígitos), e nenhum tem a forma de id
    # real da Meta desta operação (17 dígitos terminados em '361').
    for r in golden["linhas"]:
        for campo in ("campaign_id", "adset_id", "account_ref"):
            valor = r[campo]
            if valor is None:
                continue
            assert valor.isdigit() and len(valor) == 15 and valor[0] == "9", (
                f"{campo}={valor!r} não tem a forma sintética do gerador")
            assert not (len(valor) == 17 and valor.endswith("361"))


def test_totais_do_periodo_batem_com_o_csv_real(golden):
    total = totalizar(_linhas(golden))
    assert total.spend == Decimal("1029.410000")
    assert total.revenue_brl == Decimal("1140.73")
    assert total.currency == "BRL" and total.timezone == "America/Sao_Paulo"
    # ROAS = receita / gasto. Nunca purchase_roas da Meta.
    assert total.roas_ratio == Decimal("1140.73") / Decimal("1029.410000")
    assert round(total.roas_ratio, 3) == Decimal("1.108")
    # Lucro bruto = receita - gasto, e retorno excedente é OUTRA leitura.
    assert total.profit_gross == Decimal("1140.73") - Decimal("1029.410000")
    assert total.retorno_excedente_pct == (
        Decimal("1140.73") / Decimal("1029.410000") - 1) * 100


def test_impressoes_e_cliques_das_duas_fontes_nao_se_confundem(golden):
    inv, total = golden["invariantes"], totalizar(_linhas(golden))
    assert total.impressions == inv["total_impressions_meta"] == 234333
    assert total.clicks == inv["total_clicks_meta"] == 18961
    assert total.gam_impressions == inv["total_impressions_gam"] == 11734
    assert total.gam_clicks == inv["total_clicks_gam"] == 5424


def test_alcance_nunca_soma(golden):
    """Alcance é gente; a mesma pessoa aparece em dois dias."""
    linhas = _linhas(golden)
    com_alcance = [
        LinhaAtribuicao(**{**l.__dict__, "reach": 100}) for l in linhas[:3]]
    assert totalizar(com_alcance).reach is None
    assert totalizar(com_alcance).publico()["reach"] is None


# ---------------------------------------------------------------------------
# O rollup: campanha = soma dos conjuntos, exata
# ---------------------------------------------------------------------------

def test_campanha_e_exatamente_a_soma_dos_conjuntos(golden):
    linhas = _linhas(golden)
    por_campanha = agregar_campanha_periodo(linhas)
    soma_das_campanhas = sum(
        (t.spend for t in por_campanha.values()), Decimal(0))
    receita_das_campanhas = sum(
        (t.revenue_brl for t in por_campanha.values()), Decimal(0))
    total = totalizar(linhas)
    assert soma_das_campanhas == total.spend
    assert receita_das_campanhas == total.revenue_brl
    # E a soma por conjunto tem de dar a mesma coisa, pelo outro caminho.
    por_conjunto = agregar_conjunto_periodo(linhas)
    assert sum((t.spend for t in por_conjunto.values()), Decimal(0)) == total.spend
    assert sum((t.revenue_brl for t in por_conjunto.values()), Decimal(0)) == total.revenue_brl


def test_campanha_dia_e_a_soma_dos_conjuntos_daquele_dia(golden):
    linhas = _linhas(golden)
    por_dia = agregar_campanha_dia(linhas)
    for (campanha, dia), total in por_dia.items():
        filhos = [l for l in linhas if l.campaign_id == campanha and l.date == dia]
        assert total.spend == sum((l.spend for l in filhos), Decimal(0))
        assert total.revenue_brl == sum((l.gam_revenue_brl for l in filhos), Decimal(0))
        assert total.razao.conjuntos == len({l.adset_id for l in filhos})


def test_a_campanha_abo_tem_varios_conjuntos_e_soma_todos(golden):
    """A campanha ABO real chegou a ter 6 conjuntos no mesmo dia."""
    linhas = _linhas(golden)
    por_dia = agregar_campanha_dia(linhas)
    maior = max(t.razao.conjuntos for t in por_dia.values())
    assert maior == 6
    assert any(t.razao.conjuntos > 1 for t in por_dia.values())


def test_o_mesmo_conjunto_em_datas_diferentes_nao_colide(golden):
    linhas = _linhas(golden)
    conjunto = linhas[0].adset_id
    dias = {l.date for l in linhas if l.adset_id == conjunto}
    assert len(dias) > 1, "o golden precisa ter o mesmo conjunto em vários dias"
    total = totalizar([l for l in linhas if l.adset_id == conjunto])
    assert total.razao.dias == len(dias)
    assert total.razao.conjuntos == 1


# ---------------------------------------------------------------------------
# As recusas: o que NÃO pode virar total
# ---------------------------------------------------------------------------

def test_somar_campaign_level_com_adset_level_e_recusado(golden):
    """A trava contra o double count.

    A leitura campaign-level e as leituras adset-level medem a MESMA despesa.
    Somá-las dobra o gasto — e é o erro mais fácil de cometer, porque as duas
    linhas parecem apenas "mais dados".
    """
    linhas = _linhas(golden)[:3]
    campanha = LinhaAtribuicao(
        account_ref=linhas[0].account_ref, campaign_id=linhas[0].campaign_id,
        adset_id=linhas[0].adset_id, date=linhas[0].date,
        metric_scope=ESCOPO_CAMPANHA, spend=Decimal("999"),
        currency="BRL", timezone="America/Sao_Paulo")
    with pytest.raises(AtribuicaoMetaInvalida) as erro:
        totalizar([*linhas, campanha])
    assert erro.value.codigo == "META_ESCOPOS_MISTURADOS"
    with pytest.raises(AtribuicaoMetaInvalida) as erro:
        agregar_campanha_dia([*linhas, campanha])
    assert erro.value.codigo == "META_AGREGACAO_EXIGE_ESCOPO_CONJUNTO"


def test_grao_duplicado_e_recusado_antes_de_virar_total(golden):
    linha = _linhas(golden)[0]
    with pytest.raises(AtribuicaoMetaInvalida) as erro:
        totalizar([linha, linha])
    assert erro.value.codigo == "META_GRAO_DUPLICADO"


@pytest.mark.parametrize("campo,valor,codigo", [
    ("currency", "USD", "META_MOEDAS_MISTURADAS"),
    ("timezone", "UTC", "META_FUSOS_MISTURADOS"),
    ("metric_version", "outra", "META_VERSOES_MISTURADAS"),
])
def test_moeda_fuso_e_versao_diferentes_nao_somam(golden, campo, valor, codigo):
    a, b = _linhas(golden)[0], _linhas(golden)[1]
    b = LinhaAtribuicao(**{**b.__dict__, campo: valor})
    with pytest.raises(AtribuicaoMetaInvalida) as erro:
        totalizar([a, b])
    assert erro.value.codigo == codigo


@pytest.mark.parametrize("bruto", [
    "abc", "", "/", "https://exemplo.com", "camp-123", None, 123,
    "1234567890123456789012345678901234567890x",
])
def test_a_chave_de_atribuicao_recusa_o_que_nao_e_id_de_objeto(bruto):
    """A gramática de id que faltava.

    A JoinAds já devolveu `land_uri` no lugar de `utm_campaign` em dado real, e
    o valor `/` chegou a entrar na coluna de atribuição como se fosse
    identidade. Sem esta recusa, uma URL vira chave de conjunto.
    """
    assert not id_meta_valido(bruto)
    with pytest.raises(AtribuicaoMetaInvalida):
        LinhaAtribuicao(account_ref="1", campaign_id="120", adset_id=bruto,  # type: ignore[arg-type]
                        date=date(2026, 8, 10))


def test_nenhum_caminho_do_contrato_conhece_nome(golden):
    """Nenhum nome de campanha ou conjunto participa da identidade."""
    linha = _linhas(golden)[0]
    assert "nome" not in linha.__dict__ and "name" not in linha.__dict__
    assert all(not isinstance(p, str) or p.isdigit() or "-" in p or ":" in p or "/" in p
               for p in linha.chave[:3])


# ---------------------------------------------------------------------------
# Ausência versus zero
# ---------------------------------------------------------------------------

def test_campanha_sem_utm_nao_vira_conjunto_com_receita_zero(golden):
    """As 2 linhas sem UTM: estado explícito, não zero inventado."""
    sem_conjunto = [r for r in golden["linhas"] if r["adset_id"] is None]
    assert len(sem_conjunto) == 2
    for r in sem_conjunto:
        assert r["status_origem"] == "SEM_UTM_ADSET_NO_GAM"
        assert r["gam_revenue_brl"] is None, "receita desconhecida não é R$ 0,00"
        assert Decimal(r["spend"]) == 0 and r["impressions"] == 0


def test_gam_lido_sem_a_chave_e_diferente_de_gam_nao_lido():
    comum = dict(account_ref="1", campaign_id=CAMPANHA_SINTETICA,
                 adset_id=CONJUNTO_SINTETICO, date=date(2026, 8, 25),
                 insight={"spend": "2.15", "impressions": 331, "clicks": 14},
                 currency="BRL", timezone="America/Sao_Paulo")
    lido = linha_de_conjunto_dia(**comum, receita_gam=None, gam_disponivel=True)
    nao_lido = linha_de_conjunto_dia(**comum, receita_gam=None, gam_disponivel=False)
    assert lido.mapping_status == SEM_UTM_ADSET_NO_GAM
    assert nao_lido.mapping_status == SEM_LEITURA_GAM
    # Os dois têm receita None — mas por razões diferentes, e o produto precisa
    # das duas frases. O gasto sobrevive aos dois casos.
    assert lido.gam_revenue_brl is None and nao_lido.gam_revenue_brl is None
    assert lido.spend == nao_lido.spend == Decimal("2.15")
    assert lido.attribution_method is None


def test_entrega_medida_com_receita_zero_e_zero_de_verdade():
    linha = linha_de_conjunto_dia(
        account_ref="1", campaign_id=CAMPANHA_SINTETICA,
        adset_id=CONJUNTO_SINTETICO, date=date(2026, 8, 25),
        insight={"spend": "2.15", "impressions": 331, "clicks": 14},
        receita_gam={"revenue": "0", "revenue_converted": "0", "updated_at": "2026-08-26T00:00:00Z"},
        gam_disponivel=True, currency="BRL", timezone="America/Sao_Paulo")
    assert linha.mapping_status == ATRIBUIDO_VIA_ADSET
    assert linha.gam_revenue_brl == Decimal(0)
    total = totalizar([linha])
    assert total.revenue_brl == Decimal(0) and total.profit_gross == Decimal("-2.15")
    assert total.roas_ratio == Decimal(0)


def test_receita_com_zero_de_entrega_continua_visivel():
    """O caso real de 18/08: R$ 0,10 de receita num dia sem gasto nem impressão.

    Ele existe no CSV e não pode ser apagado por parecer estranho: é receita
    medida chegando num dia em que a Meta não reportou entrega.
    """
    linha = linha_de_conjunto_dia(
        account_ref="1", campaign_id=CAMPANHA_SINTETICA_2,
        adset_id=CONJUNTO_SINTETICO_2, date=date(2026, 8, 18),
        insight={"spend": "0", "impressions": 0, "clicks": 0},
        receita_gam={"revenue": "0.02", "revenue_converted": "0.10"},
        gam_disponivel=True, currency="BRL", timezone="America/Sao_Paulo")
    assert not linha.tem_entrega
    assert linha.gam_revenue_brl == Decimal("0.10")
    total = totalizar([linha])
    assert total.razao.linhas_sem_entrega == 1
    # Sem gasto não há ROAS: divisão por zero é ausência, não infinito.
    assert total.roas_ratio is None and total.profit_gross == Decimal("0.10")


def test_um_gasto_desconhecido_torna_o_total_desconhecido(golden):
    linhas = _linhas(golden)[:4]
    linhas[2] = LinhaAtribuicao(**{**linhas[2].__dict__, "spend": None})
    total = totalizar(linhas)
    assert total.spend is None and total.profit_gross is None and total.roas_ratio is None
    assert total.razao.spend_completo is False
    # A receita medida continua visível: ela não some porque o gasto sumiu.
    assert total.revenue_brl is not None


def test_leitura_parcial_nao_parece_total_completo(golden):
    linhas = _linhas(golden)[:4]
    linhas[0] = LinhaAtribuicao(**{**linhas[0].__dict__, "completo": False})
    total = totalizar(linhas)
    assert total.razao.spend_completo is False and total.razao.revenue_completo is False
    assert total.spend is not None  # o número existe; a razão diz que é parcial


def test_conjunto_sem_utm_no_meio_da_campanha_aparece_na_razao(golden):
    linhas = _linhas(golden)[:4]
    linhas[1] = LinhaAtribuicao(**{
        **linhas[1].__dict__, "gam_revenue_brl": None, "gam_revenue_original": None,
        "gam_impressions": None, "gam_clicks": None,
        "mapping_status": SEM_UTM_ADSET_NO_GAM, "attribution_method": None})
    total = totalizar(linhas)
    assert total.razao.linhas_sem_utm == 1
    assert total.razao.linhas == 4 and total.razao.linhas_atribuidas == 3
    assert total.razao.revenue_completo is False
    # O total continua sendo a soma do que FOI atribuído — com a razão ao lado.
    assert total.revenue_brl == sum(
        (l.gam_revenue_brl for l in linhas if l.gam_revenue_brl is not None), Decimal(0))


# ---------------------------------------------------------------------------
# Reconciliação: diagnóstico, nunca parcela
# ---------------------------------------------------------------------------

def test_campaign_level_reconcilia_mas_nao_entra_na_soma(golden):
    linhas = [l for l in _linhas(golden) if l.date == date(2026, 8, 25)]
    total = totalizar(linhas)
    igual = reconciliar_com_campaign_level(total, {"spend": str(total.spend)})
    assert igual["reconciliado"] is True and igual["diferenca"] == Decimal(0)
    divergente = reconciliar_com_campaign_level(total, {"spend": "999"})
    assert divergente["reconciliado"] is False
    assert divergente["motivo"] == "DIVERGENCIA_ENTRE_NIVEIS"
    # E o total não mudou por causa da reconciliação.
    assert totalizar(linhas).spend == total.spend


def test_sem_leitura_campaign_level_a_reconciliacao_e_desconhecida(golden):
    total = totalizar(_linhas(golden)[:2])
    r = reconciliar_com_campaign_level(total, None)
    assert r["reconciliado"] is None and r["motivo"] == "SEM_LEITURA_CAMPAIGN_LEVEL"


def test_receita_nao_desce_para_anuncio_ou_criativo(golden):
    """O contrato não tem grão de anúncio, e isso é a garantia.

    Se um dia houver receita por `ad_id`, ela nasce em `ESCOPO_ANUNCIO` e o
    `_exigir_homogeneidade` impede que ela seja somada às linhas de conjunto —
    que é exatamente como a duplicação seria introduzida.
    """
    linha = _linhas(golden)[0]
    anuncio = LinhaAtribuicao(**{**linha.__dict__, "metric_scope": "ad"})
    with pytest.raises(AtribuicaoMetaInvalida) as erro:
        totalizar([linha, anuncio])
    assert erro.value.codigo == "META_ESCOPOS_MISTURADOS"


def test_a_chave_do_grao_e_o_que_torna_a_gravacao_idempotente(golden):
    linhas = _linhas(golden)
    chaves = [l.chave for l in linhas]
    assert len(set(chaves)) == len(chaves), "o golden não pode ter grão repetido"
    exemplo = linhas[0]
    assert exemplo.chave == (
        exemplo.account_ref, exemplo.campaign_id, exemplo.adset_id,
        exemplo.date.isoformat(), ESCOPO_CONJUNTO, "meta-atribuicao-adset-v1")
