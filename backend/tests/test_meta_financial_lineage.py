"""Receita GAM pelo CONJUNTO, escopada, sem inventar moedas ou somar revisões.

⚠️ ESTE ARQUIVO MUDOU DE GRÃO EM 08/09/2026.

A versão anterior provava o join `utm_campaign_value = campaign_id` e, ao fazer
isso, CODIFICAVA COMO ESPERADO o defeito que a operação real desmentiu: os
anúncios que rodaram carregam `utm_campaign={{adset.id}}`, então a coluna do GAM
guarda um id de conjunto. Um teste verde sobre a chave errada é pior do que
nenhum teste — ele defende a regressão.

O que continua valendo, palavra por palavra, é tudo o que aquele arquivo
protegia e que NÃO dependia da chave: escopo de conta, vínculo de projeto,
unicidade de conta GAM, moeda e fuso confirmados nas duas pontas, ausência que
não vira zero, e receita sem prova que não apaga o gasto.
"""
import asyncio
import json
from datetime import date

import pytest

from app.trafego.meta.financeiro import ler_financeiro
from app.trafego.meta.read_model import RepositorioMetaReadModelSupabase
from test_meta_scoped_read_contract import SupabaseFalso, _base, REF_A, ATIVO_A

#: `c-a-1` (external_id 11) tem DOIS conjuntos: 31 e 32. Ter dois é o ponto —
#: com um só, "campanha = soma dos conjuntos" passaria por acidente.
CONJUNTO_1, CONJUNTO_2 = "31", "32"
DIA = "2026-09-06"


class Banco(SupabaseFalso):
    async def select(self, tabela, params):
        # Implementa exatamente os operadores emitidos; erros de filtro falham.
        simples = {k: v for k, v in params.items()
                   if k != 'and' and not str(v).startswith(('gte.', 'lte.', 'is.'))}
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


def _insight(conjunto, spend, **extra):
    base = {
        'meta_insight_daily_id': f'i-{conjunto}', 'ad_account_ativo_id': ATIVO_A,
        'provider': 'META_ADS', 'nivel': 'adset', 'objeto_externo': conjunto,
        'periodo_inicio': DIA, 'periodo_fim': DIA,
        'breakdown': 'none', 'time_increment': '1', 'action_report_time': 'impression',
        'janela_atribuicao': 'default', 'completo': True, 'currency': 'BRL',
        'account_timezone': 'America/Sao_Paulo', 'spend': spend, 'impressions': 100,
        'clicks': 5, 'observado_em': '2026-09-07T08:00:00Z'}
    base.update(extra)
    return base


def _receita(conjunto, valor, **extra):
    base = {'gam_accounts_id': 8, 'utm_campaign_value': conjunto, 'date': DIA,
            'revenue': valor, 'revenue_converted': valor,
            'updated_at': '2026-09-07T09:00:00Z'}
    base.update(extra)
    return base


def preparar(monkeypatch):
    dados = _base()
    # O segundo conjunto da campanha `c-a-1`.
    dados['trafego_meta_adset'].append({
        'meta_adset_id': 's-a-2', 'meta_campaign_id': 'c-a-1',
        'external_id': CONJUNTO_2, 'nome': 'Retomada',
        'observado_em': '2026-09-06T10:00:00Z'})
    dados['vw_trafego_meta_insight_latest'] = [
        _insight(CONJUNTO_1, '6'), _insight(CONJUNTO_2, '4')]
    dados['trafego_meta_project_binding'] = [
        {'ad_account_ativo_id': ATIVO_A, 'project_id': 7, 'desfeito_em': None}]
    dados['gam_accounts'] = [{'id': 8, 'project_id': 7}]
    dados['gam_metrics'] = [_receita(CONJUNTO_1, '15'), _receita(CONJUNTO_2, '10')]
    dados['campaigns'] = []
    monkeypatch.setenv('META_GAM_REPORTING_CONTRACT_JSON', json.dumps({
        '8': {'currency': 'BRL', 'timezone': 'America/Sao_Paulo',
              'revenue_column': 'revenue_converted'}}))
    return Banco(dados)


def ler(banco, ref='c-a-1', inicio=date(2026, 9, 6), fim=date(2026, 9, 6)):
    return asyncio.run(ler_financeiro(RepositorioMetaReadModelSupabase(banco), ref, REF_A, inicio, fim))


# ---------------------------------------------------------------------------
# O grão novo
# ---------------------------------------------------------------------------

def test_receita_vem_pelo_conjunto_e_a_campanha_soma_os_conjuntos(monkeypatch):
    banco = preparar(monkeypatch)
    r = ler(banco)
    assert r['grao'] == 'adset'
    assert (r['spend'], r['revenue'], r['profit_gross'], r['roas_ratio'],
            r['retorno_excedente_pct']) == (10, 25, 15, 2.5, 150)
    # 2 conjuntos x 100 impressões e 5 cliques: CTR 10/200 = 5%, CPC 10/10 = 1.
    assert r['ctr'] == 5 and r['cpc'] == 1
    assert r['impedimentos'] == []
    # A consulta ao GAM usa os IDS DOS CONJUNTOS, nunca o da campanha.
    gam = next(p for t, p in banco.consultas if t == 'gam_metrics')
    assert gam['utm_campaign_value'] == f'in.({CONJUNTO_1},{CONJUNTO_2})'
    assert gam['gam_accounts_id'] == 'eq.8'
    # E o gasto vem do nível adset.
    insight = next(p for t, p in banco.consultas
                   if t == 'vw_trafego_meta_insight_latest' and p.get('nivel') == 'eq.adset')
    assert insight['objeto_externo'] == f'in.({CONJUNTO_1},{CONJUNTO_2})'
    assert 'external_id' not in json.dumps(r, default=str)


def test_o_total_prova_matematicamente_a_soma_dos_conjuntos(monkeypatch):
    r = ler(preparar(monkeypatch))
    assert len(r['conjuntos']) == 2
    assert sum(c['spend'] for c in r['conjuntos']) == r['spend']
    assert sum(c['revenue_brl'] for c in r['conjuntos']) == r['revenue']
    assert r['razao']['conjuntos'] == 2 and r['razao']['linhas'] == 2
    assert r['razao']['linhas_atribuidas'] == 2
    assert r['razao']['spend_completo'] and r['razao']['revenue_completo']
    # O conjunto viaja mascarado e por referência opaca, nunca pelo id bruto.
    for c in r['conjuntos']:
        assert c['adset_ref'].startswith('metaobj_')
        assert CONJUNTO_1 not in str(c['adset_ref'])


def test_a_leitura_campaign_level_reconcilia_e_nao_entra_na_soma(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'].append(
        _insight('11', '10', nivel='campaign', meta_insight_daily_id='i-camp'))
    r = ler(banco)
    # 6 + 4 = 10, e a leitura de campanha também diz 10: reconciliado.
    assert r['spend'] == 10, 'somar campaign-level dobraria o gasto para 20'
    assert r['reconciliacao']['reconciliado'] is True
    assert r['reconciliacao']['diferenca'] == 0


def test_divergencia_entre_niveis_e_reportada_sem_corrigir_o_total(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'].append(
        _insight('11', '99', nivel='campaign', meta_insight_daily_id='i-camp'))
    r = ler(banco)
    assert r['spend'] == 10
    assert r['reconciliacao']['reconciliado'] is False
    assert r['reconciliacao']['motivo'] == 'DIVERGENCIA_ENTRE_NIVEIS'
    assert r['reconciliacao']['diferenca'] == -89


def test_campanha_sem_conjuntos_conhecidos_continua_distinguivel(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['trafego_meta_adset'] = [
        c for c in banco.tabelas['trafego_meta_adset'] if c['meta_campaign_id'] != 'c-a-1']
    r = ler(banco)
    assert r['estado'] == 'SEM_CONJUNTOS_NO_READ_MODEL'
    assert 'CAMPANHA_SEM_CONJUNTOS_CONHECIDOS' in r['impedimentos']
    # E ela NÃO é uma campanha com gasto zero.
    assert r['spend'] is None and r['revenue'] is None


# ---------------------------------------------------------------------------
# Escopo: o que não pode entrar na conta
# ---------------------------------------------------------------------------

def test_outra_campanha_conta_janela_e_nivel_nao_somam(monkeypatch):
    banco = preparar(monkeypatch)
    row = banco.tabelas['vw_trafego_meta_insight_latest'][0]
    for i, alteracao in enumerate((
            {'objeto_externo': '41'}, {'ad_account_ativo_id': 'outra'},
            {'nivel': 'ad'}, {'janela_atribuicao': '7d_click'},
            {'periodo_inicio': '2026-09-05', 'periodo_fim': '2026-09-05'})):
        banco.tabelas['vw_trafego_meta_insight_latest'].append(
            {**row, **alteracao, 'spend': '999', 'meta_insight_daily_id': f'ruido-{i}'})
    banco.tabelas['gam_metrics'].extend([
        {**banco.tabelas['gam_metrics'][0], 'gam_accounts_id': 99, 'revenue_converted': 1000},
        {**banco.tabelas['gam_metrics'][0], 'utm_campaign_value': '41', 'revenue_converted': 1000}])
    assert ler(banco)['spend'] == 10
    assert ler(banco)['revenue'] == 25
    assert ler(banco, 'c-b-1')['spend'] is None  # conta B, fora do escopo


def test_conjunto_de_outra_campanha_nao_entra_no_total(monkeypatch):
    """O conjunto `41` é da campanha `c-b-1`, na conta B."""
    banco = preparar(monkeypatch)
    r = ler(banco)
    conjuntos_lidos = next(
        p for t, p in banco.consultas if t == 'trafego_meta_adset')
    assert conjuntos_lidos['meta_campaign_id'] == 'eq.c-a-1'
    assert '41' not in str(r['conjuntos'])


@pytest.mark.parametrize('mudanca', [
    {'completo': False}, {'currency': 'USD'}, {'account_timezone': 'UTC'},
])
def test_gasto_incompleto_ou_incomparavel_nao_vira_total(monkeypatch, mudanca):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'][0].update(mudanca)
    r = ler(banco)
    assert r['razao']['spend_completo'] is False
    assert 'INSIGHTS_DIARIOS_AUSENTES_PARCIAIS_OU_INCOMPATIVEIS' in r['impedimentos']


def test_um_dia_sem_linha_de_insight_nao_vira_gasto_zero(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'] = [_insight(CONJUNTO_1, '6')]
    r = ler(banco)
    # O conjunto 32 não tem linha: o gasto do período fica DESCONHECIDO.
    assert r['spend'] is None and r['profit_gross'] is None
    assert r['razao']['spend_completo'] is False
    # E a receita medida continua visível.
    assert r['revenue'] == 25


def test_insight_duplicado_no_mesmo_grao_e_recusado(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['vw_trafego_meta_insight_latest'].append(
        _insight(CONJUNTO_1, '6', meta_insight_daily_id='i-clone'))
    r = ler(banco)
    assert 'INSIGHT_DUPLICADO_NO_MESMO_GRAO' in r['impedimentos']
    assert r['spend'] is None


def test_zero_e_zero_divisao_nao_e_zero(monkeypatch):
    banco = preparar(monkeypatch)
    for linha in banco.tabelas['vw_trafego_meta_insight_latest']:
        linha['spend'] = '0'
    for linha in banco.tabelas['gam_metrics']:
        linha['revenue'] = linha['revenue_converted'] = '0'
    r = ler(banco)
    assert r['spend'] == 0 and r['revenue'] == 0 and r['profit_gross'] == 0
    assert r['roas_ratio'] is None and r['retorno_excedente_pct'] is None


# ---------------------------------------------------------------------------
# Receita sem prova não apaga o gasto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('caso', [
    'sem_contrato', 'sem_projeto', 'colisao_google', 'duplicado_gam', 'fuso_gam'])
def test_receita_sem_prova_nao_apaga_spend(monkeypatch, caso):
    banco = preparar(monkeypatch)
    if caso == 'sem_contrato':
        monkeypatch.delenv('META_GAM_REPORTING_CONTRACT_JSON')
    if caso == 'sem_projeto':
        banco.tabelas['trafego_meta_project_binding'] = []
    if caso == 'colisao_google':
        banco.tabelas['campaigns'] = [{'id': 3, 'google_ads_campaign_id': CONJUNTO_1}]
    if caso == 'duplicado_gam':
        banco.tabelas['gam_metrics'] *= 2
    if caso == 'fuso_gam':
        monkeypatch.setenv('META_GAM_REPORTING_CONTRACT_JSON',
                           '{"8":{"currency":"BRL","timezone":"UTC","revenue_column":"revenue_converted"}}')
    r = ler(banco)
    assert r['spend'] == 10, 'o gasto sobrevive à falta de prova de receita'
    assert r['revenue'] is None and r['profit_gross'] is None
    assert r['impedimentos']
    assert r['razao']['linhas_sem_leitura_gam'] == 2


def test_conjunto_sem_utm_no_gam_e_diferente_de_gam_nao_lido(monkeypatch):
    """O GAM foi lido e não conhece o conjunto 32: associação DESCONHECIDA."""
    banco = preparar(monkeypatch)
    banco.tabelas['gam_metrics'] = [_receita(CONJUNTO_1, '15')]
    r = ler(banco)
    assert r['revenue'] == 15, 'soma o que foi atribuído'
    assert r['razao']['linhas_sem_utm'] == 1
    assert r['razao']['revenue_completo'] is False, 'e diz que não está completo'
    assert r['spend'] == 10
    por_conjunto = {c['adset_ref']: c for c in r['conjuntos']}
    sem = [c for c in por_conjunto.values() if c['revenue_brl'] is None]
    assert len(sem) == 1 and sem[0]['razao']['linhas_sem_utm'] == 1


def test_receita_nula_no_gam_nao_vira_receita_zero(monkeypatch):
    banco = preparar(monkeypatch)
    banco.tabelas['gam_metrics'][0]['revenue_converted'] = None
    r = ler(banco)
    # A linha existe no GAM (associação conhecida) mas o valor é nulo: o total
    # do que foi medido continua sendo o do outro conjunto, e a razão avisa.
    assert r['revenue'] == 10
    assert r['razao']['revenue_completo'] is True
    assert any(c['revenue_brl'] is None for c in r['conjuntos'])


def test_colisao_de_namespace_e_verificada_nos_conjuntos(monkeypatch):
    """O id que o GAM usa agora é o do CONJUNTO — é ele que pode colidir."""
    banco = preparar(monkeypatch)
    banco.tabelas['campaigns'] = [{'id': 3, 'google_ads_campaign_id': CONJUNTO_2}]
    r = ler(banco)
    assert 'ADSET_ID_GAM_COM_NAMESPACE_NAO_UNIVOCO' in r['impedimentos']
    assert r['revenue'] is None and r['spend'] == 10


def test_dias_faltantes_nao_viram_semana_completa(monkeypatch):
    r = ler(preparar(monkeypatch), inicio=date(2026, 9, 1))
    assert r['spend'] is None and r['razao']['spend_completo'] is False


def test_periodo_invertido_recusa_antes_de_ler_fatos(monkeypatch):
    banco = preparar(monkeypatch)
    with pytest.raises(ValueError):
        ler(banco, inicio=date(2026, 9, 6), fim=date(2026, 9, 5))
    assert not any(t in {'gam_metrics', 'vw_trafego_meta_insight_latest'}
                   for t, _ in banco.consultas)


# ---------------------------------------------------------------------------
# O endpoint
# ---------------------------------------------------------------------------

def test_endpoint_financeiro_serializa_valores_sem_keychain_ou_meta(monkeypatch):
    from app.routers import meta_local
    from test_meta_sync_operacional import cliente_app

    banco = preparar(monkeypatch)
    monkeypatch.setattr(meta_local, '_repositorio_read_model',
                        lambda: RepositorioMetaReadModelSupabase(banco))
    monkeypatch.setattr(meta_local, '_chaveiro',
                        lambda: pytest.fail('financeiro tentou resolver token Meta'))
    cliente = cliente_app()
    r = cliente.get('/api/trafego/meta/local/financeiro/c-a-1', params={
        'conta_ref': REF_A, 'inicio': '2026-09-06', 'fim': '2026-09-06'})
    assert r.status_code == 200
    # FastAPI/Pydantic preserva Decimal como string no contrato JSON.
    assert r.json()['profit_gross'] == '15' and r.json()['revenue'] == '25'
    assert r.json()['grao'] == 'adset'
    assert cliente.get('/api/trafego/meta/local/financeiro/c-a-1').status_code == 422
    assert cliente.get('/api/trafego/meta/local/financeiro/c-a-1', params={
        'conta_ref': REF_A, 'inicio': 'nao-e-data'}).status_code == 422


def test_endpoint_financeiro_exige_identidade_antes_do_banco(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.config import get_settings
    from app.routers import meta_local

    monkeypatch.setattr(meta_local, '_repositorio_read_model',
                        lambda: pytest.fail('banco antes de autenticar'))
    app = FastAPI()
    app.include_router(meta_local.router)
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        supabase_url='https://banco.exemplo.invalid', supabase_service_role_key='fixture-sem-segredo')
    assert TestClient(app, headers={'host': 'localhost'}).get(
        '/api/trafego/meta/local/financeiro/c-a-1', params={'conta_ref': REF_A}).status_code == 401
