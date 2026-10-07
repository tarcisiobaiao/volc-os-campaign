"""Termos de busca REAIS na copy Search, em três estados — nunca inventados.

`presente` · consulta feita na janela, com termos.
`vazio_confirmado` · consulta feita na janela, zero termos (é informação).
`ausente` · ninguém coletou. NUNCA vira lista — nem vazia.

Antes desta reforma a encomenda fixava `termos_de_busca=()` e o prompt dizia
"(vazia — nenhum termo de busca colhido ainda nesta campanha)": uma ausência
apresentada como medição. O formato é o do contrato entre as trilhas (o mesmo
JSON que o motor valida em `funnelforge.domain.models.TermosDeBusca`).

Tudo aqui é hermético: o "export do integrador" é um fixture SINTÉTICO escrito
num diretório temporário, e o cliente GAQL é um dublê que só devolve dicts.

Rodar:
    backend/.venv/bin/python -m pytest volc_ads/copy/testes_termos_de_busca.py -q
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from volc_ads.copy import render
from volc_ads.copy.render import Encomenda, ErroDeRender, valores
from volc_ads.inteligencia_google import coletor
from volc_ads.inteligencia_google.modelo import (
    JanelaDeTermos,
    TermoDeBusca,
    TermosDeBusca,
    tem_dado_pessoal,
    termos_ausentes,
)

JANELA = JanelaDeTermos(date(2026, 9, 21), date(2026, 9, 30))
CHAVES_DO_CONTRATO = {"estado", "janela", "coletado_em", "fonte", "termos",
                      "motivo_ausencia"}


def _linha(termo: str, dia: str, imp: int, cli: int, custo_micros: int | None = 0):
    m = {"impressions": str(imp), "clicks": str(cli), "conversions": 0.0}
    if custo_micros is not None:
        m["cost_micros"] = str(custo_micros)
    return {"search_term_view": {"resource_name": "customers/1/searchTermViews/2~3~x",
                                 "search_term": termo, "status": "NONE"},
            "segments": {"date": dia, "search_term_match_type": "PHRASE"},
            "metrics": m}


LINHAS = [
    _linha("cursos senac gratuitos", "2026-09-21", 40, 3, 1_500_000),
    _linha("cursos senac gratuitos", "2026-09-22", 60, 2, 1_000_000),
    _linha("senac cursos", "2026-09-22", 30, 4, 2_000_000),
    _linha("senac ead gratis", "2026-09-30", 10, 0, 0),
    _linha("meu cpf 123.456.789-09 senac", "2026-09-23", 5, 1, 500_000),
    _linha("contato fulano@exemplo.com senac", "2026-09-24", 5, 0, 0),
    _linha("senac 11987654321", "2026-09-25", 3, 0, 0),
]


def _arquivo(tmp_path, linhas=LINHAS):
    caminho = tmp_path / "search_terms.json"
    caminho.write_text(json.dumps(linhas, ensure_ascii=False), encoding="utf-8")
    return caminho


# ── o modelo: três estados, validados na construção ─────────────────────────

def test_ausente_nunca_carrega_termos():
    with pytest.raises(ValueError):
        TermosDeBusca(estado="ausente", termos=(TermoDeBusca("x", 1, 0),),
                      motivo_ausencia="m")
    a = termos_ausentes("campanha sem id")
    assert a.termos == () and a.motivo_ausencia == "campanha sem id"
    assert a.para_json()["termos"] == []


def test_ausente_exige_motivo():
    with pytest.raises(ValueError):
        TermosDeBusca(estado="ausente")


def test_vazio_confirmado_nao_tem_termos_e_exige_janela_e_fonte():
    with pytest.raises(ValueError):
        TermosDeBusca(estado="vazio_confirmado", janela=JANELA,
                      coletado_em="2026-09-30T10:00:00+00:00", fonte="search_term_view",
                      termos=(TermoDeBusca("x", 1, 0),))
    with pytest.raises(ValueError):
        TermosDeBusca(estado="vazio_confirmado", coletado_em="2026-09-30T10:00:00+00:00",
                      fonte="search_term_view")


def test_presente_exige_termos_janela_coleta_e_fonte_valida():
    with pytest.raises(ValueError):
        TermosDeBusca(estado="presente", janela=JANELA,
                      coletado_em="2026-09-30T10:00:00+00:00", fonte="search_term_view")
    with pytest.raises(ValueError):
        TermosDeBusca(estado="presente", janela=JANELA,
                      coletado_em="2026-09-30T10:00:00+00:00", fonte="planilha",
                      termos=(TermoDeBusca("x", 1, 0),))


def test_janela_invertida_e_recusada():
    with pytest.raises(ValueError):
        JanelaDeTermos(date(2026, 9, 30), date(2026, 9, 21))


def test_json_tem_exatamente_as_chaves_do_contrato_e_volta_igual():
    t = TermosDeBusca(estado="presente", janela=JANELA,
                      coletado_em="2026-09-30T10:00:00+00:00", fonte="search_term_view",
                      termos=(TermoDeBusca("senac cursos", 30, 4, 2.0),))
    j = t.para_json()
    assert set(j) == CHAVES_DO_CONTRATO
    assert j["janela"] == {"inicio": "2026-09-21", "fim": "2026-09-30",
                           "fuso": "America/Sao_Paulo"}
    assert j["termos"] == [{"termo": "senac cursos", "impressoes": 30, "cliques": 4,
                            "custo": 2.0}]
    assert TermosDeBusca.de_json(json.loads(json.dumps(j))) == t


def test_filtro_de_dado_pessoal():
    for termo in ("meu cpf 123.456.789-09", "cpf 12345678909", "fulano@exemplo.com",
                  "11987654321", "cnpj 03.709.814/0001-98"):
        assert tem_dado_pessoal(termo), termo
    for termo in ("cursos senac 2026", "senac ead gratis", "decreto 6.633"):
        assert not tem_dado_pessoal(termo), termo


# ── o export do integrador (arquivo) ────────────────────────────────────────

def test_arquivo_agrega_por_termo_filtra_pii_e_guarda_o_sha(tmp_path):
    caminho = _arquivo(tmp_path)
    t = coletor.carregar_termos_de_arquivo(caminho)
    assert t.estado == "presente"
    assert t.fonte == "arquivo:" + hashlib.sha256(caminho.read_bytes()).hexdigest()
    por_termo = {x.termo: x for x in t.termos}
    # 2 linhas (dias diferentes) do mesmo termo viram UM termo, somado.
    assert por_termo["cursos senac gratuitos"] == TermoDeBusca(
        "cursos senac gratuitos", 100, 5, 2.5)
    # Nenhum termo com cara de dado pessoal chega ao prompt.
    assert not [x for x in t.termos if tem_dado_pessoal(x.termo)]
    assert t.descartados_por_dado_pessoal == 3
    assert t.total_na_fonte == 6          # termos distintos no arquivo
    # Ordem: mais cliques, depois mais impressões.
    assert [x.termo for x in t.termos] == ["cursos senac gratuitos", "senac cursos",
                                           "senac ead gratis"]


def test_termos_enviados_sao_subconjunto_da_fonte(tmp_path):
    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path))
    da_fonte = {linha["search_term_view"]["search_term"] for linha in LINHAS}
    assert {x.termo for x in t.termos} <= da_fonte


def test_arquivo_sem_janela_declarada_usa_as_datas_das_linhas(tmp_path):
    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path))
    assert t.janela == JanelaDeTermos(date(2026, 9, 21), date(2026, 9, 30))


def test_janela_declarada_filtra_as_linhas(tmp_path):
    t = coletor.carregar_termos_de_arquivo(
        _arquivo(tmp_path), janela=JanelaDeTermos(date(2026, 9, 21), date(2026, 9, 21)))
    assert [(x.termo, x.impressoes) for x in t.termos] == [("cursos senac gratuitos", 40)]
    assert t.janela.inicio == t.janela.fim == date(2026, 9, 21)


def test_top_n_e_declarado(tmp_path):
    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path), limite=2)
    assert len(t.termos) == 2 and t.limite == 2 and t.total_na_fonte == 6


def test_arquivo_vazio_com_janela_e_vazio_confirmado(tmp_path):
    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path, []), janela=JANELA)
    assert t.estado == "vazio_confirmado" and t.termos == ()


def test_arquivo_vazio_sem_janela_nao_confirma_nada(tmp_path):
    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path, []))
    assert t.estado == "ausente" and t.termos == ()
    assert "janela" in t.motivo_ausencia


def test_so_dado_pessoal_nao_vira_lista_nem_vazio(tmp_path):
    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path, LINHAS[4:]))
    assert t.estado == "ausente" and t.termos == ()
    assert "pessoal" in t.motivo_ausencia


def test_arquivo_ilegivel_falha_alto(tmp_path):
    caminho = tmp_path / "x.json"
    caminho.write_text("{isto não é json", encoding="utf-8")
    with pytest.raises(ValueError):
        coletor.carregar_termos_de_arquivo(caminho)


# ── a coleta ao vivo, com cliente GAQL falso ────────────────────────────────

class _ClienteFalso:
    """Executor de GAQL de mentira: grava a consulta e devolve o que mandarem."""

    def __init__(self, linhas=None, erro: Exception | None = None):
        self.linhas = linhas or []
        self.erro = erro
        self.consultas: list[tuple[str, str]] = []

    def __call__(self, customer_id: str, gaql: str):
        self.consultas.append((customer_id, gaql))
        if self.erro:
            raise self.erro
        return list(self.linhas)


AGORA = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)


def test_coleta_faz_uma_gaql_somente_leitura_no_search_term_view():
    c = _ClienteFalso(LINHAS)
    t = coletor.coletar_termos_de_busca(c, "547-809-6539", "24278665189", JANELA,
                                        agora=AGORA)
    assert len(c.consultas) == 1
    cid, gaql = c.consultas[0]
    assert cid == "5478096539"
    normal = " ".join(gaql.split())
    assert normal.startswith("SELECT ")
    assert "FROM search_term_view" in normal
    for campo in ("search_term_view.search_term", "segments.date",
                  "metrics.impressions", "metrics.clicks", "metrics.cost_micros"):
        assert campo in normal
    assert "campaign.id = 24278665189" in normal
    assert "segments.date BETWEEN '2026-09-21' AND '2026-09-30'" in normal
    for proibido in ("mutate", "INSERT", "UPDATE", "DELETE", "REMOVE"):
        assert proibido.lower() not in normal.lower()
    assert t.estado == "presente" and t.fonte == "search_term_view"
    assert t.coletado_em == AGORA.isoformat()
    assert t.janela == JANELA and t.janela.fuso == "America/Sao_Paulo"


def test_coleta_sem_linhas_e_vazio_confirmado_nao_ausente():
    t = coletor.coletar_termos_de_busca(_ClienteFalso([]), "5478096539", "24278665189",
                                        JANELA, agora=AGORA)
    assert t.estado == "vazio_confirmado" and t.termos == ()
    assert t.janela == JANELA and t.fonte == "search_term_view"


def test_coleta_que_falha_e_ausente_sem_vazar_a_mensagem():
    erro = RuntimeError("401 token=abc123 Authorization: Bearer xyz")
    t = coletor.coletar_termos_de_busca(_ClienteFalso(erro=erro), "5478096539",
                                        "24278665189", JANELA, agora=AGORA)
    assert t.estado == "ausente" and t.termos == ()
    assert "RuntimeError" in t.motivo_ausencia
    assert "abc123" not in t.motivo_ausencia and "xyz" not in t.motivo_ausencia


@pytest.mark.parametrize("customer_id,campaign_id", [
    ("", "24278665189"), ("5478096539", ""), ("5478096539", "1 OR 1=1"),
    ("54780x96539", "24278665189"),
])
def test_ids_invalidos_nao_consultam_e_viram_ausente(customer_id, campaign_id):
    c = _ClienteFalso(LINHAS)
    t = coletor.coletar_termos_de_busca(c, customer_id, campaign_id, JANELA, agora=AGORA)
    assert c.consultas == []
    assert t.estado == "ausente" and t.motivo_ausencia


def test_coleta_aceita_o_coletor_real_pelo_query():
    """Em produção o executor é `ColetorGoogleInteligencia._query` (só SELECT,
    trava de escrita conferida no construtor). Aqui sem construir o real."""
    real = coletor.ColetorGoogleInteligencia.__new__(coletor.ColetorGoogleInteligencia)
    falso = _ClienteFalso(LINHAS)
    real._query = falso
    t = coletor.coletar_termos_de_busca(real, "5478096539", "24278665189", JANELA,
                                        agora=AGORA)
    assert t.estado == "presente" and len(falso.consultas) == 1


# ── o prompt: três estados, três textos ─────────────────────────────────────

def _enc(**troca) -> Encomenda:
    base = dict(nicho="Cursos Senac", url="https://exemplo.com.br/r/senac/",
                keywords=("cursos senac", "senac cursos gratuitos"), ano=2026)
    base.update(troca)
    return Encomenda(**base)


def _presente():
    return TermosDeBusca(estado="presente", janela=JANELA,
                         coletado_em="2026-09-30T10:00:00+00:00", fonte="search_term_view",
                         termos=(TermoDeBusca("cursos senac gratuitos", 100, 5, 2.5),
                                 TermoDeBusca("senac cursos", 30, 4, 2.0)),
                         total_na_fonte=1303, limite=25)


def _vazio():
    return TermosDeBusca(estado="vazio_confirmado", janela=JANELA,
                         coletado_em="2026-09-30T10:00:00+00:00", fonte="search_term_view")


def test_os_tres_estados_renderizam_textos_distintos():
    textos = {nome: valores(_enc(termos_de_busca=t))["{termos_de_busca}"]
              for nome, t in (("presente", _presente()), ("vazio", _vazio()),
                              ("ausente", termos_ausentes("campanha sem id")))}
    assert len(set(textos.values())) == 3
    assert "cursos senac gratuitos" in textos["presente"]
    assert "2026-09-21" in textos["presente"] and "1303" in textos["presente"]
    assert "0 termos" in textos["vazio"] and "2026-09-21" in textos["vazio"]


def test_ausente_diz_nao_coletado_com_motivo_e_nunca_vira_lista():
    txt = valores(_enc(termos_de_busca=termos_ausentes("campanha sem id")))[
        "{termos_de_busca}"]
    assert "NÃO COLETADO (campanha sem id)" in txt
    assert "  - " not in txt, "ausente virou lista"
    assert "vazia" not in txt.lower(), "ausência apresentada como lista vazia"


def test_encomenda_sem_termos_e_ausente_explicito():
    txt = valores(_enc())["{termos_de_busca}"]
    assert "NÃO COLETADO" in txt and "  - " not in txt


def test_lista_crua_de_termos_e_recusada():
    """Uma tupla de strings não diz janela, fonte nem estado — é o defeito."""
    with pytest.raises(ErroDeRender):
        _enc(termos_de_busca=("cursos senac",))


def test_dado_pessoal_nao_chega_ao_prompt_nem_se_o_objeto_vier_sujo():
    sujo = SimpleNamespace(estado="presente", janela=JANELA, fonte="search_term_view",
                           coletado_em="2026-09-30T10:00:00+00:00", motivo_ausencia=None,
                           termos=(TermoDeBusca("senac cpf 12345678909", 9, 9, None),
                                   TermoDeBusca("senac cursos", 30, 4, 2.0)),
                           total_na_fonte=2, limite=None, descartados_por_dado_pessoal=0)
    txt = valores(_enc(termos_de_busca=sujo))["{termos_de_busca}"]
    assert "12345678909" not in txt and "senac cursos" in txt


def test_prompt_inteiro_monta_nos_tres_estados():
    for t in (_presente(), _vazio(), termos_ausentes("x"), None):
        prompt = render.montar(_enc(termos_de_busca=t))
        assert not render.RX_PLACEHOLDER.findall(prompt)


# ── a encomenda deixa de fixar () ───────────────────────────────────────────

def _cockpit():
    origem = SimpleNamespace(nicho="Cursos Senac", url_final="https://exemplo.com.br/r/x/",
                             pais="BR", idioma="pt", vertical="informativo", fatos=())
    return SimpleNamespace(origem=origem)


def test_encomendar_sem_termos_declara_ausencia():
    from volc_ads.copy import encomendar as em

    enc, _ = em.encomendar(_cockpit(), keywords=["cursos senac"])
    assert enc.termos_de_busca.estado == "ausente"
    assert enc.termos_de_busca.motivo_ausencia


def test_encomendar_repassa_os_termos_coletados(tmp_path):
    from volc_ads.copy import encomendar as em

    t = coletor.carregar_termos_de_arquivo(_arquivo(tmp_path))
    enc, _ = em.encomendar(_cockpit(), keywords=["cursos senac"], termos_de_busca=t)
    assert enc.termos_de_busca is t
    assert "cursos senac gratuitos" in render.montar(enc)


def test_escrever_aceita_termos_como_encomendar():
    """A lição de `vertical`: parâmetro só em `encomendar()` estoura a rota."""
    import inspect

    from volc_ads.copy import encomendar as em

    assert "termos_de_busca" in inspect.signature(em.escrever).parameters
    assert "termos_de_busca" in inspect.signature(em.encomendar).parameters
