"""Coleta de câmbio versionado (W12): PTAX do BCB → versões em exchange_rate_history.

Hermético: a resposta do PTAX é um corpo gravado no formato do OData (valores
sintéticos), o HTTP é injetado e o repositório é dublê. Nada sai para a rede.
A regra de resolução (exata/anterior/defasada) é do banco e é provada pela
suíte tools/freedom-lab/db/suites/v23_w12.sh, não aqui.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.monetizacao.cambio.application import ColetaRecusada, coletar_cotacoes
from app.monetizacao.cambio.domain import Cotacao, CotacaoInvalida
from app.monetizacao.cambio.infrastructure import ptax_bcb
from app.monetizacao.cambio.infrastructure.ptax_bcb import FontePtaxBcb, interpretar, montar_url
from app.monetizacao.cambio.infrastructure.repositorio_postgrest import CONFLITO, RepositorioCotacaoPostgrest

# Formato do recurso CotacaoDolarPeriodo; valores SINTÉTICOS (não são a PTAX real).
# 10 e 11/10/2026 são sábado e domingo: a fonte não publica e a coleta não inventa.
CORPO = json.dumps({"@odata.context": "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata$metadata",
                    "value": [
                        {"cotacaoCompra": 5.4012, "cotacaoVenda": 5.4018, "dataHoraCotacao": "2026-10-09 13:09:27.113"},
                        {"cotacaoCompra": 5.4100, "cotacaoVenda": 5.4106, "dataHoraCotacao": "2026-10-12 13:04:11.501"},
                        {"cotacaoCompra": 5.3950, "cotacaoVenda": 5.3956, "dataHoraCotacao": "2026-10-13 13:11:02.090"},
                    ]}).encode()
AGORA = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)


class RepoDuble:
    def __init__(self):
        self.linhas = {}

    async def gravar(self, cotacoes):
        novas = 0
        for c in cotacoes:
            k = (c.par, c.data_referencia, c.fonte, c.as_of)
            if k not in self.linhas:
                self.linhas[k] = c
                novas += 1
        return novas


def _fonte(corpo=CORPO, urls=None):
    def obter(url):
        if urls is not None:
            urls.append(url)
        return corpo
    return FontePtaxBcb(obter)


def _coletar(fonte, repo, inicio=date(2026, 10, 9), fim=date(2026, 10, 13)):
    return asyncio.run(coletar_cotacoes(fonte, repo, inicio, fim, relogio=lambda: AGORA))


def test_url_documentada_com_datas_no_formato_do_olinda():
    url = montar_url(date(2026, 10, 9), date(2026, 10, 13))
    assert url.startswith("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarPeriodo(")
    assert "@dataInicial='10-09-2026'" in url and "@dataFinalCotacao='10-13-2026'" in url


def test_ptax_vira_versao_com_as_of_da_fonte_no_fuso_de_brasilia():
    c = interpretar(CORPO, "u")[0]
    assert (c.par, c.fonte, c.data_referencia, c.taxa) == ("USD/BRL", "bcb_ptax", date(2026, 10, 9), Decimal("5.4018"))
    assert c.as_of.utcoffset().total_seconds() == -3 * 3600
    assert c.proveniencia["campo"] == "cotacaoVenda" and c.proveniencia["cotacao_compra"] == "5.4012"
    assert len(c.proveniencia["resposta_sha256"]) == 64


def test_linha_nao_leva_coletado_em_nem_float():
    linha = interpretar(CORPO, "u")[0].como_linha()
    assert "coletado_em" not in linha            # quem carimba é o banco
    assert linha["rate"] == "5.4018" and linha["as_of"].endswith("+00:00")
    assert linha["effective_date"] == "2026-10-09"


def test_coleta_grava_so_dias_publicados_e_e_idempotente():
    repo, urls = RepoDuble(), []
    r = _coletar(_fonte(urls=urls), repo)
    assert (r.recebidas, r.gravadas) == (3, 3)
    assert r.dias_com_cotacao == ("2026-10-09", "2026-10-12", "2026-10-13")   # sem fim de semana inventado
    assert len(urls) == 1
    assert _coletar(_fonte(), repo).gravadas == 0


@pytest.mark.parametrize("registro, trecho", [
    ({"cotacaoVenda": 0, "dataHoraCotacao": "2026-10-13 13:00:00"}, "taxa"),
    ({"cotacaoVenda": "NaN", "dataHoraCotacao": "2026-10-13 13:00:00"}, "taxa"),
    ({"cotacaoVenda": 5.4, "dataHoraCotacao": "ontem"}, "ilegível"),
    ({"dataHoraCotacao": "2026-10-13 13:00:00"}, "ilegível"),
])
def test_registro_ruim_recusa_a_janela_inteira(registro, trecho):
    corpo = json.dumps({"value": [json.loads(CORPO)["value"][0], registro]}).encode()
    repo = RepoDuble()
    with pytest.raises(ColetaRecusada) as e:
        _coletar(_fonte(corpo), repo)
    assert trecho in " ".join(e.value.motivos)
    assert repo.linhas == {}


def test_resposta_sem_value_e_recusada():
    with pytest.raises(ColetaRecusada):
        _coletar(_fonte(b'{"erro": 1}'), RepoDuble())


def test_cotacao_fora_da_janela_ou_repetida_nao_grava_nada():
    repo = RepoDuble()
    with pytest.raises(ColetaRecusada) as e:
        _coletar(_fonte(), repo, inicio=date(2026, 10, 12))
    assert any("fora da janela" in m for m in e.value.motivos) and repo.linhas == {}
    dobrado = json.dumps({"value": json.loads(CORPO)["value"] * 2}).encode()
    with pytest.raises(ColetaRecusada) as e:
        _coletar(_fonte(dobrado), repo)
    assert any("repetida" in m for m in e.value.motivos) and repo.linhas == {}


def test_as_of_no_futuro_e_janela_futura_sao_recusados():
    futuro = json.dumps({"value": [{"cotacaoVenda": 5.4, "dataHoraCotacao": "2026-10-15 23:00:00"}]}).encode()
    with pytest.raises(ColetaRecusada) as e:
        _coletar(_fonte(futuro), RepoDuble(), fim=date(2026, 10, 15))
    assert any("futuro" in m for m in e.value.motivos)
    with pytest.raises(ColetaRecusada):
        _coletar(_fonte(), RepoDuble(), fim=date(2026, 10, 16))
    with pytest.raises(ColetaRecusada):
        _coletar(_fonte(), RepoDuble(), inicio=date(2026, 10, 13), fim=date(2026, 10, 9))


def test_janela_sem_publicacao_nao_vira_zero():
    r = _coletar(_fonte(b'{"value": []}'), RepoDuble(), inicio=date(2026, 10, 10), fim=date(2026, 10, 11))
    assert (r.recebidas, r.gravadas, r.dias_com_cotacao) == (0, 0, ())


@pytest.mark.parametrize("campos, trecho", [
    ({"par": "USDBRL"}, "par"),
    ({"fonte": "legado_manual"}, "fonte"),
    ({"fonte": "manual"}, "fonte"),       # o banco trocaria o as_of da fonte pelo do servidor
    ({"taxa": 5.4}, "Decimal"),
    ({"as_of": datetime(2026, 10, 13, 13, 0)}, "fuso"),
    ({"data_referencia": datetime(2026, 10, 13, 13, 0)}, "date"),
])
def test_invariantes_da_cotacao_espelham_os_checks_do_banco(campos, trecho):
    base = dict(par="USD/BRL", data_referencia=date(2026, 10, 13), taxa=Decimal("5.4"), fonte="bcb_ptax",
                as_of=datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc))
    with pytest.raises(CotacaoInvalida) as e:
        Cotacao(**{**base, **campos})
    assert trecho in str(e.value)


def test_fonte_padrao_nao_toca_a_rede_no_import():
    assert ptax_bcb.FontePtaxBcb()._obter is ptax_bcb._obter_http


def test_repositorio_postgrest_usa_on_conflict_do_indice_da_v23_01():
    chamadas = []

    class ClienteDuble:
        def _headers(self, prefer=None):
            return {"Prefer": prefer}

        async def _req(self, metodo, alvo, **kw):
            chamadas.append((metodo, alvo, kw))
            return [{"id": 1}]

    cotacoes = interpretar(CORPO, "u")
    n = asyncio.run(RepositorioCotacaoPostgrest(ClienteDuble()).gravar(cotacoes))
    metodo, alvo, kw = chamadas[0]
    assert (n, metodo, alvo) == (1, "POST", "exchange_rate_history")
    assert kw["params"] == {"on_conflict": CONFLITO} and CONFLITO == "par,effective_date,fonte,as_of"
    assert kw["headers"]["Prefer"] == "resolution=ignore-duplicates,return=representation"
    assert [l["effective_date"] for l in kw["json"]] == ["2026-10-09", "2026-10-12", "2026-10-13"]
    assert asyncio.run(RepositorioCotacaoPostgrest(ClienteDuble()).gravar([])) == 0 and len(chamadas) == 1
