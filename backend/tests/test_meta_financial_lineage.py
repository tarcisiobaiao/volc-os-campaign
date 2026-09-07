"""GAM por campaign_id, escopado, sem inventar moedas ou somar revisões."""
import asyncio
import json
from datetime import date

import pytest

from app.trafego.meta.financeiro import ler_financeiro
from app.trafego.meta.read_model import RepositorioMetaReadModelSupabase
from test_meta_scoped_read_contract import SupabaseFalso, _base, REF_A, ATIVO_A


class Banco(SupabaseFalso):
    async def select(self, tabela, params):
        # Implementa exatamente os operadores emitidos; erros de filtro falham.
        simples = {k: v for k, v in params.items() if k != 'and' and not str(v).startswith(('gte.', 'lte.', 'is.'))}
        simples.pop('limit', None)
        rows = await super().select(tabela, simples)
        filtros = [(k, str(v)) for k, v in params.items() if str(v).startswith(('gte.', 'lte.', 'is.'))]
        if 'and' in params:
            filtros.extend(tuple(x.split('.', 1)) for x in params['and'][1:-1].split(','))
        for campo, filtro in filtros:
            op, alvo = filtro.split('.', 1)
            if op == 'gte':
                rows = [r for r in rows if str(r.get(campo)) >= alvo]
            elif op == 'lte':
                rows = [r for r in rows if str(r.get(campo)) <= alvo]
            elif filtro == 'is.null':
                rows = [r for r in rows if r.get(campo) is None]
            else:
                raise AssertionError(filtro)
        self.consultas[-1] = (tabela, params)
        return rows[:int(params.get('limit', len(rows)))]


def preparar(monkeypatch):
    dados = _base()
    dados['vw_trafego_meta_insight_latest'] = [
        {'meta_insight_daily_id': 'i-1', 'ad_account_ativo_id': ATIVO_A,
         'provider': 'META_ADS', 'nivel': 'campaign', 'objeto_externo': '11',
         'periodo_inicio': '2026-09-06', 'periodo_fim': '2026-09-06',
         'breakdown': 'none', 'time_increment': '1', 'action_report_time': 'impression',
         'janela_atribuicao': 'default', 'completo': True, 'currency': 'BRL',
         'account_timezone': 'America/Sao_Paulo', 'spend': '10', 'impressions': 100,
         'clicks': 5, 'observado_em': '2026-09-07T08:00:00Z'}]
    dados['trafego_meta_project_binding'] = [{'ad_account_ativo_id': ATIVO_A, 'project_id': 7, 'desfeito_em': None}]
    dados['gam_accounts'] = [{'id': 8, 'project_id': 7}]
    dados['gam_metrics'] = [{'gam_accounts_id': 8, 'utm_campaign_value': '11',
                            'date': '2026-09-06', 'revenue_converted': '25', 'updated_at': '2026-09-07T09:00:00Z'}]
    dados['campaigns'] = []
    monkeypatch.setenv('META_GAM_REPORTING_CONTRACT_JSON', json.dumps({
        '8': {'currency': 'BRL', 'timezone': 'America/Sao_Paulo', 'revenue_column': 'revenue_converted'}}))
    return Banco(dados)


def ler(banco, ref='c-a-1', inicio=date(2026, 9, 6), fim=date(2026, 9, 6)):
    return asyncio.run(ler_financeiro(RepositorioMetaReadModelSupabase(banco), ref, REF_A, inicio, fim))


def test_financeiro_real_por_campaign_id_na_conta_e_projeto(monkeypatch):
    banco = preparar(monkeypatch)
    r = ler(banco)
    assert (r['spend'], r['revenue'], r['profit_gross'], r['roas_ratio'], r['retorno_excedente_pct']) == (10, 25, 15, 2.5, 150)
    assert r['ctr'] == 5 and r['cpc'] == 2
    assert r['impedimentos'] == []
    gam = next(p for t, p in banco.consultas if t == 'gam_metrics')
    assert gam['utm_campaign_value'] == 'eq.11' and gam['gam_accounts_id'] == 'eq.8'
    assert 'external_id' not in json.dumps(r, default=str)


def test_outra_campanha_conta_janela_e_nivel_nao_somam(monkeypatch):
    banco = preparar(monkeypatch)
    row = banco.tabelas['vw_trafego_meta_insight_latest'][0]
    for alteracao in ({'objeto_externo': '12'}, {'ad_account_ativo_id': 'outra'},
                      {'nivel': 'ad'}, {'janela_atribuicao': '7d_click'}, {'periodo_inicio': '2026-09-05'}):
        banco.tabelas['vw_trafego_meta_insight_latest'].append({**row, **alteracao, 'spend': '999'})
    banco.tabelas['gam_metrics'].extend([
        {**banco.tabelas['gam_metrics'][0], 'gam_accounts_id': 99, 'revenue_converted': 1000},
        {**banco.tabelas['gam_metrics'][0], 'utm_campaign_value': '12', 'revenue_converted': 1000}])
    assert ler(banco)['spend'] == 10
    assert ler(banco)['revenue'] == 25
    assert ler(banco, 'c-b-1')['spend'] is None
    assert ler(banco, 'c-a-2')['spend'] == 999  # valor próprio, não o gasto da campanha 11


@pytest.mark.parametrize('mudanca', [
    {'completo': False}, {'spend': None}, {'currency': 'USD'}, {'account_timezone': 'UTC'},
])
def test_gasto_incompleto_ou_incomparavel_nao_vira_total(monkeypatch, mudanca):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'][0].update(mudanca)
    r = ler(banco)
    assert r['spend'] is None and r['profit_gross'] is None


def test_zero_e_zero_divisao_nao_e_zero(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'][0]['spend'] = '0'
    banco.tabelas['gam_metrics'][0]['revenue_converted'] = '0'
    r = ler(banco)
    assert r['spend'] == 0 and r['revenue'] == 0 and r['profit_gross'] == 0
    assert r['roas_ratio'] is None and r['retorno_excedente_pct'] is None


@pytest.mark.parametrize('caso', ['sem_contrato', 'sem_projeto', 'colisao_google', 'colisao_meta', 'duplicado_gam', 'nulo_gam', 'dia_faltante', 'fuso_gam'])
def test_receita_sem_prova_nao_apaga_spend(monkeypatch, caso):
    banco = preparar(monkeypatch)
    if caso == 'sem_contrato': monkeypatch.delenv('META_GAM_REPORTING_CONTRACT_JSON')
    if caso == 'sem_projeto': banco.tabelas['trafego_meta_project_binding'] = []
    if caso == 'colisao_google': banco.tabelas['campaigns'] = [{'id': 3, 'google_ads_campaign_id': '11'}]
    if caso == 'colisao_meta': banco.tabelas['trafego_meta_campaign'].append({**banco.tabelas['trafego_meta_campaign'][0], 'meta_campaign_id': 'outro'})
    if caso == 'duplicado_gam': banco.tabelas['gam_metrics'] *= 2
    if caso == 'nulo_gam': banco.tabelas['gam_metrics'][0]['revenue_converted'] = None
    if caso == 'dia_faltante': banco.tabelas['gam_metrics'] = []
    if caso == 'fuso_gam': monkeypatch.setenv('META_GAM_REPORTING_CONTRACT_JSON', '{"8":{"currency":"BRL","timezone":"UTC","revenue_column":"revenue_converted"}}')
    r = ler(banco)
    assert r['spend'] == 10 and r['revenue'] is None and r['profit_gross'] is None and r['impedimentos']


def test_dias_faltantes_nao_viram_semana_completa(monkeypatch):
    r = ler(preparar(monkeypatch), inicio=date(2026, 9, 1))
    assert r['spend'] is None and r['revenue'] is None


def test_periodo_invertido_recusa_antes_de_ler_fatos(monkeypatch):
    banco = preparar(monkeypatch)
    with pytest.raises(ValueError):
        ler(banco, inicio=date(2026, 9, 6), fim=date(2026, 9, 5))
    assert not any(t in {'gam_metrics', 'vw_trafego_meta_insight_latest'} for t, _ in banco.consultas)


def test_endpoint_financeiro_serializa_valores_sem_keychain_ou_meta(monkeypatch):
    from app.routers import meta_local
    from test_meta_sync_operacional import cliente_app

    banco = preparar(monkeypatch)
    monkeypatch.setattr(meta_local, '_repositorio_read_model', lambda: RepositorioMetaReadModelSupabase(banco))
    monkeypatch.setattr(meta_local, '_chaveiro', lambda: pytest.fail('financeiro tentou resolver token Meta'))
    cliente = cliente_app()
    r = cliente.get('/api/trafego/meta/local/financeiro/c-a-1', params={
        'conta_ref': REF_A, 'inicio': '2026-09-06', 'fim': '2026-09-06'})
    assert r.status_code == 200
    # FastAPI/Pydantic preserva Decimal como string no contrato JSON.
    assert r.json()['profit_gross'] == '15' and r.json()['revenue'] == '25'
    assert cliente.get('/api/trafego/meta/local/financeiro/c-a-1').status_code == 422
    assert cliente.get('/api/trafego/meta/local/financeiro/c-a-1', params={
        'conta_ref': REF_A, 'inicio': 'nao-e-data'}).status_code == 422


def test_endpoint_financeiro_exige_identidade_antes_do_banco(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.config import get_settings
    from app.routers import meta_local

    monkeypatch.setattr(meta_local, '_repositorio_read_model', lambda: pytest.fail('banco antes de autenticar'))
    app = FastAPI()
    app.include_router(meta_local.router)
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        supabase_url='https://banco.exemplo.invalid', supabase_service_role_key='fixture-sem-segredo')
    assert TestClient(app, headers={'host': 'localhost'}).get(
        '/api/trafego/meta/local/financeiro/c-a-1', params={'conta_ref': REF_A}).status_code == 401
