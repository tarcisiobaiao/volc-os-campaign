"""O coletor de snapshots lê três grãos sem multiplicar orçamento de páginas."""
import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.routers import meta_local as router
from app.trafego.meta.adaptador import ErroDeLeituraMeta
from app.trafego.meta import dominio as dom
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta.read_model import montar_snapshot_canonico
from test_meta_real_read_model import ClienteGraphFake, pagina, TOKEN


def executar(monkeypatch, *, paginas=1, parcial=None, erro=None):
    pedidos, limites = [], []

    class Adaptador:
        def __init__(self, cliente, *, limite_por_pagina, max_paginas_por_edge):
            assert limite_por_pagina == 100
            self.limite = max_paginas_por_edge
            limites.append(self.limite)

        async def ler_insights(self, pedido, segredo):
            pedidos.append(pedido)
            if pedido.nivel == erro:
                raise ErroDeLeituraMeta('HTTP_FAIL', 'Erro seguro')
            quantidade = self.limite if paginas == 'teto' else paginas
            return SimpleNamespace(insights=(pedido.nivel,), paginas_lidas=quantidade,
                                   completo=pedido.nivel != parcial)

    monkeypatch.setattr(router, 'AdaptadorMetaSomenteLeitura', Adaptador)
    result = asyncio.run(router._ler_insights_dos_niveis(None,
        SimpleNamespace(id_externo='123', fuso='America/Sao_Paulo'), None,
        date(2026, 9, 9), 7))
    return result, pedidos, limites


def test_coleta_tres_niveis_mesmo_periodo_sem_misturar(monkeypatch):
    (rows, completo, motivo), pedidos, limites = executar(monkeypatch)
    assert rows == ('campaign', 'adset', 'ad') and completo and motivo is None
    assert all(p.periodo_inicio == date(2026, 9, 3) and p.periodo_fim == date(2026, 9, 9)
               and p.fuso_da_conta == 'America/Sao_Paulo' and p.conta_externa == '123'
               and p.time_increment == '1' for p in pedidos)


def test_teto_100_total_em_vez_100_por_nivel(monkeypatch):
    (_, completo, _), pedidos, limites = executar(monkeypatch, paginas='teto', parcial='ad')
    assert len(pedidos) == 3 and sum(limites) == 100
    assert not completo


def test_parcialidade_persiste_no_recibo(monkeypatch):
    (_, completo, motivo), _, _ = executar(monkeypatch, parcial='adset')
    assert not completo and motivo == 'INSIGHTS_ADSET_LEITURA_INCOMPLETA'


def test_erro_um_nivel_preserva_outros_mas_nunca_completo(monkeypatch):
    (rows, completo, motivo), _, _ = executar(monkeypatch, erro='adset')
    assert rows == ('campaign', 'ad') and not completo
    assert motivo == 'INSIGHTS_ADSET_LEITURA_INDISPONIVEL'


def test_deadline_total_corta_antes_outro_request(monkeypatch):
    ticks = iter([100, 101, 191])
    # Replace router's namespace, not global monotonic used by asyncio.
    monkeypatch.setattr(router, 'time', SimpleNamespace(monotonic=lambda: next(ticks, 191)))
    (rows, completo, motivo), pedidos, _ = executar(monkeypatch)
    assert rows == ('campaign',) and len(pedidos) == 1 and not completo
    assert motivo == 'INSIGHTS_TEMPO_TOTAL_EXCEDIDO'


def test_adaptador_real_transporta_tres_niveis_ate_payload_de_persistencia():
    async def cenario():
        conta = dom.ContaMetaDescoberta('123', 'Conta fixture', '1', 'BRL', 'America/Sao_Paulo')
        base = {'account_id': '123', 'date_start': '2026-09-09', 'date_stop': '2026-09-09',
                'spend': '5.25', 'impressions': '100', 'clicks': '3'}
        cliente = ClienteGraphFake({'insights': [
            pagina([{**base, 'campaign_id': '11'}]),
            pagina([{**base, 'campaign_id': '11', 'adset_id': '31'}]),
            pagina([{**base, 'campaign_id': '11', 'adset_id': '31', 'ad_id': '51'}]),
        ]})
        rows, completo, motivo = await router._ler_insights_dos_niveis(
            cliente, conta, SegredoEfemero(TOKEN), date(2026, 9, 9), 1)
        assert [i.nivel for i in rows] == ['campaign', 'adset', 'ad']
        snapshot = montar_snapshot_canonico(conta,
            dom.LeituraDaHierarquia('123', (), (), (), (), 4), rows, {}, 'fixture',
            datetime.now(timezone.utc), insights_completos=completo, motivo_incompleto=motivo)
        gravaveis = snapshot.linhas['trafego_meta_insight_daily']
        assert {r['nivel'] for r in gravaveis} == {'campaign', 'adset', 'ad'}
        assert all(r['completo'] and r['currency'] == 'BRL' and r['account_timezone'] == conta.fuso
                   for r in gravaveis)
        assert len(cliente.chamadas) == 3
    asyncio.run(cenario())
