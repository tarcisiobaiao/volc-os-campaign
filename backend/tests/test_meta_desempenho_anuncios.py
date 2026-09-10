"""Métricas de anúncios independentes de receita e protegidas pela hierarquia."""
import asyncio
from datetime import date

import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta import desempenho_anuncios as modulo
from app.trafego.meta.read_model import RepositorioMetaReadModelSupabase
from test_meta_financial_lineage import Banco, _insight, preparar, ler
from test_meta_scoped_read_contract import _base, ATIVO_A, ATIVO_B, CONTA_A

DIA = date(2026, 9, 6)
CONTEXTO = {"ativo_id": ATIVO_A, "conta_externa": CONTA_A,
            "moeda": "BRL", "fuso": "America/Sao_Paulo"}


class BancoPaginado(Banco):
    async def select(self, tabela, params):
        offset = int(params.get("offset", 0))
        tudo = {k: v for k, v in params.items() if k not in {"offset", "limit"}}
        rows = await super().select(tabela, tudo)
        return rows[offset:offset + int(params.get("limit", len(rows)))]


def fixture():
    dados = _base()
    dados['vw_trafego_meta_insight_latest'] = [_insight('51', '4.5', nivel='ad')]
    return dados


def consultar(dados=None, *, fim=DIA, banco=None):
    banco = banco or BancoPaginado(dados or fixture())
    return asyncio.run(modulo.ler_desempenho_anuncios(
        RepositorioMetaReadModelSupabase(banco), CONTEXTO, 'c-a-1', DIA, fim))


def test_metricas_reais_sem_receita_nem_ids_brutos():
    dados = fixture()
    dados['vw_trafego_meta_insight_latest'] += [
        _insight('61', '999', nivel='ad', ad_account_ativo_id=ATIVO_B),
        _insight('31', '999', nivel='adset'),
        _insight('51', '999', nivel='ad', periodo_inicio='2026-09-05', periodo_fim='2026-09-05'),
    ]
    resposta = consultar(dados)
    assert resposta['anuncios_completo'] is True
    assert resposta['anuncios_impedimentos'] == []
    ad, = resposta['anuncios']
    assert ad['spend'] == '4.5'
    assert ad['ctr'] == '5.00' and ad['cpc'] == '0.9' and ad['cpm'] == '45.000'
    assert ad['ad_ref'] == dom.referencia_opaca_objeto(CONTA_A, 'ad', '51')
    assert ad['adset_ref'] == dom.referencia_opaca_objeto(CONTA_A, 'adset', '31')
    assert not {'revenue', 'roas', 'external_id', 'meta_ad_id'} & set(ad)


def test_agrega_dias_calcula_taxas_nao_media_e_usa_frescor_mais_antigo():
    dados = fixture()
    dados['vw_trafego_meta_insight_latest'].append(_insight(
        '51', '5.5', nivel='ad', periodo_inicio='2026-09-07', periodo_fim='2026-09-07',
        impressions=400, clicks=15, observado_em='2026-09-08T08:00:00Z'))
    ad, = consultar(dados, fim=date(2026, 9, 7))['anuncios']
    assert ad['spend'] == '10.0' and ad['impressions'] == 500 and ad['clicks'] == 20
    assert ad['ctr'] == '4.00' and ad['cpc'] == '0.5' and ad['cpm'] == '20.00'
    assert ad['source_freshness'] == '2026-09-07T08:00:00+00:00'


def test_dia_ausente_nao_virar_zero_nem_total_parcial():
    result = consultar(fim=date(2026, 9, 7))
    assert not result['anuncios_completo']
    assert result['anuncios'][0]['spend'] is None
    assert result['anuncios'][0]['impressions'] is None


@pytest.mark.parametrize('campo,valor', [
    ('currency', 'USD'), ('account_timezone', 'UTC'), ('completo', False),
    ('spend', None), ('spend', '-1'), ('spend', 'NaN'), ('spend', 'Infinity'),
    ('impressions', 0.2), ('clicks', True), ('observado_em', '2026-09-07T08:00:00'),
])
def test_campos_incompativeis_sem_estimativa(campo, valor):
    dados = fixture()
    dados['vw_trafego_meta_insight_latest'][0][campo] = valor
    result = consultar(dados)
    assert not result['anuncios_completo']
    assert result['anuncios'][0]['spend'] is None


def test_zero_medido_nao_vira_ausencia():
    dados = fixture()
    dados['vw_trafego_meta_insight_latest'][0].update(spend='0', impressions=0, clicks=0)
    ad, = consultar(dados)['anuncios']
    assert ad['completo'] and ad['spend'] == '0' and ad['impressions'] == 0
    assert ad['ctr'] is None and ad['cpc'] is None and ad['cpm'] is None


def test_duplicate_grain_fail_without_double_count():
    dados = fixture()
    dados['vw_trafego_meta_insight_latest'] *= 2
    assert consultar(dados)['anuncios_impedimentos'] == ['ANUNCIOS_INSIGHT_DUPLICADO']


def test_paginacao_todas_as_paginas_e_teto_explicito(monkeypatch):
    monkeypatch.setattr(modulo, '_PAGINA', 1)
    assert consultar()['anuncios_completo'] is True  # second empty page proves exhaustion
    monkeypatch.setattr(modulo, '_MAX_PAGINAS', 1)
    result = consultar()
    assert 'ANUNCIOS_INSIGHTS_TRUNCADOS' in result['anuncios_impedimentos']
    assert result['anuncios'][0]['spend'] is None


@pytest.mark.parametrize('campo,valor', [('objeto_externo', '61'), ('ad_account_ativo_id', ATIVO_B),
    ('nivel', 'campaign'), ('periodo_inicio', '2026-09-05'), ('periodo_fim', '2026-09-07'),
    ('janela_atribuicao', '7d_click')])
def test_view_que_ignora_filtro_nao_vaza_escopo(campo, valor):
    class BancoCorrompido(BancoPaginado):
        async def select(self, tabela, params):
            rows = await super().select(tabela, params)
            if tabela == 'vw_trafego_meta_insight_latest' and rows:
                rows[0][campo] = valor
            return rows
    assert consultar(banco=BancoCorrompido(fixture()))['anuncios_impedimentos'] == ['ANUNCIOS_GRAO_FORA_DO_ESCOPO']


def test_parentesco_ambiguo_bloqueia():
    dados = fixture()
    dados['trafego_meta_ad'].append({**dados['trafego_meta_ad'][0], 'meta_ad_id': 'outro'})
    assert consultar(dados)['anuncios_impedimentos'] == ['ANUNCIOS_PARENTESCO_INVALIDO']


def test_falha_ads_nao_derruba_financeiro_existente(monkeypatch):
    banco = preparar(monkeypatch)
    # fixture does not carry ad-level insight but financial campaign stays valid
    result = ler(banco)
    assert result['spend'] is not None and result['revenue'] is not None
    assert not result['anuncios_completo'] and result['anuncios_impedimentos']
    assert not any(i.startswith('ANUNCIOS_') for i in result['impedimentos'])


def test_erro_da_fonte_secundaria_nao_derruba_receita_e_total(monkeypatch):
    from app.trafego.meta import financeiro
    async def falhar(*args, **kwargs):
        raise RuntimeError('backend indisponível')
    monkeypatch.setattr(financeiro, 'ler_desempenho_anuncios', falhar)
    result = ler(preparar(monkeypatch))
    assert result['spend'] == 10 and result['revenue'] == 25
    assert result['impedimentos'] == []
    assert result['anuncios_impedimentos'] == ['ANUNCIOS_LEITURA_INDISPONIVEL']
