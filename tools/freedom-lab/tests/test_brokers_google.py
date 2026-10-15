"""Brokers Google sem rede: capacidades, métodos HTTP, escopos, ausência ≠ zero, sanitização."""
import ast
import itertools
import json
from pathlib import Path

import pytest

from volc_lab.brokers import ga4, gtm, recibos
from volc_lab.brokers.google_credencial import (
    CredencialIndisponivel, conferir_escopos, verificar_arquivo)
from volc_lab.brokers.valor_operacional import (
    ORIGENS, RecomendacaoShadow, ValorMonetario, ValorSemAutoridade)

BROKERS = Path(__file__).resolve().parents[1] / "src" / "volc_lab" / "brokers"
C = gtm.CapacidadeGTM


class _Resp:
    def __init__(self, status=200, corpo=None):
        self.status_code, self._c = status, corpo or {}
        self.ok = status == 200

    def json(self):
        return self._c

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.status_code)


class SessaoFake:
    def __init__(self, rotas):
        self.rotas, self.chamadas = rotas, []
        self.escopos_efetivos = frozenset()

    def get(self, url, **kw):
        self.chamadas.append(("GET", url))
        for sufixo, corpo in self.rotas.items():
            if url.endswith(sufixo):
                return _Resp(200, corpo)
        return _Resp(404)

    def post(self, url, **kw):
        self.chamadas.append(("POST", url))
        return _Resp(200, self.rotas.get("runReport", {}))


# ---------- GTM: capacidades sem hierarquia ----------

def test_leitura_nao_implica_publicar():
    c = gtm.ConcessaoGTM(frozenset({C.LEITURA}), "inventário do laboratório")
    for cap in (C.EDITAR, C.CRIAR_VERSAO, C.PUBLICAR):
        with pytest.raises(gtm.CapacidadeNegada):
            c.exigir(cap)


@pytest.mark.parametrize("caps", [frozenset(s) for n in range(1, 4)
                                  for s in itertools.combinations([C.EDITAR, C.CRIAR_VERSAO, C.PUBLICAR], n)])
def test_teto_do_lab_recusa_tudo_alem_de_leitura(caps):
    with pytest.raises(gtm.CapacidadeNegada):
        gtm.ConcessaoGTM(caps | {C.LEITURA}, "tentativa de ampliar o teto")


def test_teto_do_lab_e_so_leitura():
    assert gtm.TETO_DO_LAB == frozenset({C.LEITURA})


def test_cliente_gtm_nao_tem_verbo_de_escrita():
    nomes = {n for n in dir(gtm.ClienteGTMLeitura) if not n.startswith("__")}
    assert not {n for n in nomes if any(v in n.lower() for v in
                                        ("publi", "versao", "version", "criar", "atualiz", "update", "delete"))}


def test_gtm_so_faz_get_e_conta_tudo():
    rotas = {
        "/accounts": {"account": [{"path": "accounts/1"}]},
        "accounts/1/containers": {"container": [{"path": "accounts/1/containers/2"}]},
        "containers/2/workspaces": {"workspace": [{"path": "w/3"}, {"path": "w/4"}]},
        "/tags": {"tag": [{}, {}]}, "/triggers": {"trigger": [{}]}, "/variables": {"variable": [{}]},
    }
    fake = SessaoFake(rotas)
    cli = gtm.ClienteGTMLeitura(gtm.ConcessaoGTM(frozenset({C.LEITURA}), "inventário do laboratório"),
                                fabrica_sessao=lambda esc: fake, pausa_s=0)
    inv = cli.inventariar()
    assert {m for m, _ in fake.chamadas} == {"GET"}
    assert all(u.startswith(gtm.BASE) for _, u in fake.chamadas)
    assert (inv.accounts, inv.containers, inv.workspaces, inv.tags, inv.triggers, inv.variables) == (1, 1, 2, 4, 2, 2)


# ---------- GA4 ----------

def test_ga4_ausencia_nao_vira_zero_e_so_runreport_e_post():
    fake = SessaoFake({"accountSummaries": {"accountSummaries": [
        {"propertySummaries": [{"property": "properties/123"}]}]},
        "/dataStreams": {"dataStreams": [{}]}, "runReport": {}})
    cli = ga4.ClienteGA4Leitura(fabrica_sessao=lambda esc: fake)
    assert cli.agregado("properties/123") == {"tem_linha": False, "valores": None}
    inv = cli.inventariar()
    assert (inv.contas, inv.properties, inv.streams, inv.erros_http) == (1, 1, 1, 0)
    for metodo, url in fake.chamadas:
        if metodo == "POST":
            assert ga4._RUNREPORT.match(url)
        else:
            assert metodo == "GET"


def test_ga4_recusa_metrica_fora_da_lista_e_property_forjada():
    fake = SessaoFake({})
    cli = ga4.ClienteGA4Leitura(fabrica_sessao=lambda esc: fake)
    with pytest.raises(ValueError):
        cli.agregado("properties/1", ("userId",))
    with pytest.raises(ValueError):
        cli.agregado("properties/1/../../x")


# ---------- credencial ----------

def test_escopo_a_mais_e_recusado():
    with pytest.raises(CredencialIndisponivel):
        conferir_escopos(frozenset({gtm.ESCOPO[C.LEITURA], "https://www.googleapis.com/auth/adwords"}),
                         frozenset({gtm.ESCOPO[C.LEITURA]}))
    with pytest.raises(CredencialIndisponivel):
        conferir_escopos(frozenset(), frozenset({gtm.ESCOPO[C.LEITURA]}))


def test_arquivo_com_permissao_aberta_e_recusado(tmp_path):
    f = tmp_path / "google-oauth.json"
    f.write_text("{}")
    f.chmod(0o644)
    with pytest.raises(CredencialIndisponivel):
        verificar_arquivo(f)
    f.chmod(0o600)
    assert verificar_arquivo(f) == f


# ---------- recibos ----------

@pytest.mark.parametrize("vazamento", [
    "ya29.a0AfH6SMBabcdef", "1//0gABCDEFGHIJKLMNOPQRSTUV", "GOCSPX-abc",
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x", '"refresh_token": "x"'])
def test_recibo_com_segredo_nao_e_gravado(tmp_path, vazamento):
    destino = tmp_path / "r.jsonl"
    with pytest.raises(recibos.ReciboInseguro):
        recibos.gravar({"campo": vazamento}, destino)
    assert not destino.exists()


def test_mascara():
    assert recibos.mascarar("123-456-7890") == "123****890"
    assert "456" not in recibos.mascarar("1234567890")


# ---------- Google Ads: o broker não alcança escrita ----------

PROIBIDOS_ADS = {"mutar", "destravar", "aplicar", "aplicar_recomendacoes", "enviar",
                 "mutate", "get_service", "cliente", "GoogleAdsClient", "lote", "gestao"}


def nomes_alcancados(fonte: str) -> set[str]:
    """Atributos, nomes, e tudo o que entra por import (nome original E alias)."""
    nomes = set()
    for n in ast.walk(ast.parse(fonte)):
        if isinstance(n, ast.Attribute):
            nomes.add(n.attr)
        elif isinstance(n, ast.Name):
            nomes.add(n.id)
        elif isinstance(n, ast.alias):
            nomes.update(n.name.split("."))
            if n.asname:
                nomes.add(n.asname)
        elif isinstance(n, ast.ImportFrom) and n.module:
            nomes.update(n.module.split("."))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            nomes.add(n.value)  # getattr(x, "mutar")
    return nomes


def test_broker_ads_nao_alcanca_escrita():
    assert not nomes_alcancados((BROKERS / "google_ads.py").read_text(encoding="utf-8")) & PROIBIDOS_ADS


@pytest.mark.parametrize("trecho", [
    "from volc_ads.gads.client import mutar as _m",
    "from volc_ads.gads import client as c\nf = c.mutar",
    "import volc_ads.gestao.lote as l",
    "from volc_ads.gads.modo import destravar as abre",
    "x = getattr(obj, 'mutar')",
])
def test_contraprova_alias_e_import_sao_pegos(trecho):
    fonte = (BROKERS / "google_ads.py").read_text(encoding="utf-8") + "\n" + trecho + "\n"
    assert nomes_alcancados(fonte) & PROIBIDOS_ADS


# ---------- valor operacional ----------

@pytest.mark.parametrize("origem", sorted(ORIGENS - {"operador", "medido_na_conta"}))
def test_cpc_externo_nunca_autoriza(origem):
    with pytest.raises(ValorSemAutoridade):
        ValorMonetario(1_500_000, origem, "serp:x").autoriza()


def test_medido_na_conta_exige_gaql_e_ausencia_nao_autoriza():
    with pytest.raises(ValorSemAutoridade):
        ValorMonetario(1, "medido_na_conta", "planilha")
    with pytest.raises(ValorSemAutoridade):
        ValorMonetario(None, "operador", "operador:tarcisio").autoriza()
    assert ValorMonetario(5, "medido_na_conta", "gaql:SELECT metrics.cost_micros").autoriza() == 5


def test_shadow_nao_executa():
    with pytest.raises(ValueError):
        RecomendacaoShadow("c", "manter", ("x",), executada=True)
    with pytest.raises(ValueError):
        RecomendacaoShadow("c", "dobrar", ("x",))


def test_gtm_recua_em_429_e_nao_perde_a_lista():
    class Sessao429(SessaoFake):
        def __init__(self, rotas):
            super().__init__(rotas)
            self.vezes = 0

        def get(self, url, **kw):
            if url.endswith("/accounts") and self.vezes < 2:
                self.vezes += 1
                self.chamadas.append(("GET", url))
                return _Resp(429)
            return super().get(url, **kw)

    fake = Sessao429({"/accounts": {"account": []}})
    cli = gtm.ClienteGTMLeitura(gtm.ConcessaoGTM(frozenset({C.LEITURA}), "inventário do laboratório"),
                                fabrica_sessao=lambda esc: fake, pausa_s=0)
    inv = cli.inventariar()
    assert inv.recuos_429 == 2 and inv.erros_http == {}
