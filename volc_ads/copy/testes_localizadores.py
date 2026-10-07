"""Palavra isolada não reprova: vira LOCALIZADOR entregue ao juiz de sentido (B6).

Base: inventário da frente A (`inventario-regras.json`, 30/09/2026) e diretriz do
operador (itens 2, 4 e 8). Decisões aplicadas aqui:

  ADS-07  `deturpacao.declaracoes_nao_confiaveis`  converter_em_aviso
  ADS-08  `financeiro.termo_em_portal_informativo` converter_em_aviso
  ADS-09  `deturpacao.clickbait`                   contextualizar: as frases que
          espelham os exemplos da política seguem barrando; palavra solta
          ('chocante', 'inacreditável') e fórmula ambígua ('veja o que
          aconteceu') viram localizador
  ADS-15  `editorial.repeticao.no_item`            converter_em_aviso
  ADS-05/06 TRAVA 0 do prompt (lista de `limites.yaml` + trava por conceito) remover

O que se prova, sem rede e sem token:

  · palavra antes proibida, em copy legítima, passa no portão do lançamento, na
    C10 da cascata e na cascata inteira — e continua VISÍVEL como aviso;
  · promessa falsa SEM palavra de lista é apontada pelo juiz e a copy não segue;
  · o juiz recebe fatos tipados, termos com estado, destino e os trechos
    marcados pelos localizadores;
  · o juiz é editor: só erro com procedência vira regeneração; estilo nunca é
    aplicado; a regeneração é por asset (os outros ficam intactos);
  · limites de campo, tracking e o texto exato do payload não mudaram.

Rodar:
    backend/.venv/bin/python -m pytest volc_ads/copy/testes_localizadores.py -q
"""
from __future__ import annotations

import copy as copia
import json
from types import SimpleNamespace

import pytest

from volc_ads.campanha import conteudo, search, validacao
from volc_ads.campanha.brief import Copy, Sitelink, Snippet
from volc_ads.campanha.testes_search import (
    CID,
    _brief,
    _cliente_sem_rede,
    _copy,
    _por_tipo,
)
from volc_ads.copy import juiz_semantico as js, render
from volc_ads.copy.ciclo import gerar
from volc_ads.copy.contrato import (
    Pedido,
    _c10_portao_do_lancamento,
    comprimento_efetivo,
    medir,
)
from volc_ads.copy.mock import ClienteMock, JuizMock, RoteiroEsgotado, copy_valida
from volc_ads.policy import spec as policy

LOCALIZADORES = {
    "deturpacao.declaracoes_nao_confiaveis": "ADS-07",
    "financeiro.termo_em_portal_informativo": "ADS-08",
    "deturpacao.clickbait.palavra_isolada": "ADS-09",
    "editorial.repeticao.no_item": "ADS-15",
}


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch):
    monkeypatch.setattr(search, "cliente", lambda _login: _cliente_sem_rede())


# ── o spec: o que virou localizador, com a decisão do inventário colada ─────


def _todas_as_regras(spec: dict) -> list[dict]:
    regras = list(spec["estruturais"])
    for lista in spec["semanticas"].values():
        regras += lista
    return regras


def test_as_regras_convertidas_sao_aviso_e_declaram_o_inventario():
    spec = policy.carregar()
    por_id: dict[str, list[dict]] = {}
    for r in _todas_as_regras(spec):
        por_id.setdefault(r["id"], []).append(r)
    for rid, inv in LOCALIZADORES.items():
        assert rid in por_id, f"{rid} sumiu do spec"
        for r in por_id[rid]:
            assert r["severidade"] == "aviso", (rid, r.get("idioma"))
            assert r.get("localizador") is True, rid
            assert inv in r.get("decisao_inventario", ""), rid


def test_clickbait_do_exemplo_da_politica_continua_erro():
    """ADS-09 é contextualizar, não remover: a frase que espelha o exemplo
    da política continua barrando; só a palavra solta sai."""
    pol = policy.Validador(vertical="informativo")
    r = validacao.Resultado()
    conteudo.politica(pol, ["Você Não Vai Acreditar Nisso"], "headline_rsa", r)
    assert any("15936667" in a.motivo for a in r.erros), r.resumo()

    r2 = validacao.Resultado()
    conteudo.politica(pol, ["Uma Mudança Inacreditável"], "headline_rsa", r2)
    assert r2.erros == [], r2.resumo()
    assert any("15936667" in a.motivo for a in r2.achados), r2.resumo()


# ── palavra antes proibida, em copy legítima, passa e continua visível ──────

LEGITIMOS = [
    # (chave do limite, texto) — cada um é exemplo_legitimo_que_bloqueia do inventário
    ("description_rsa", "O acesso gratuito não é garantido a todos: depende da renda."),
    ("headline_rsa", "Procura Curso no Senac?"),
    ("headline_rsa", "Curso de Curativos no Senac"),
    ("headline_rsa", "Antecipação da Matrícula?"),
    ("description_rsa", "Cursos gratuitos e cursos pagos do Senac: os requisitos mudam."),
    ("headline_rsa", "Veja o que Aconteceu no PSG"),
]


@pytest.mark.parametrize("chave,texto", LEGITIMOS)
def test_palavra_antes_proibida_em_copy_legitima_nao_barra_mas_fica_visivel(chave, texto):
    pol = policy.Validador(vertical="informativo")
    r = validacao.Resultado()
    conteudo.politica(pol, [texto], chave, r)
    assert r.erros == [], r.resumo()
    assert r.achados, "o localizador sumiu: o trecho tem de continuar visível"


def test_o_construtor_aceita_a_copy_legitima_e_o_payload_e_o_texto_aprovado():
    """Nenhuma reescrita silenciosa: o que vai ao validate_only é exatamente o
    texto aprovado — inclusive o que o localizador marcou."""
    hl = ["Procura Curso no Senac?", "Curso de Curativos no Senac",
          "Regras de 2026", "Quem Tem Direito"]
    ds = ["O acesso gratuito não é garantido a todos: depende da renda.",
          "Portal informativo com a tabela legal por faixa etaria."]
    sl = [Sitelink("Regras de 2026", "O que vale hoje", "E o que muda"),
          Sitelink("Quem tem direito", "As condicoes", "Em linguagem simples")]
    co = ["Conteudo informativo", "Fontes oficiais"]
    b = _brief(copy=_copy(headlines=hl, descriptions=ds, sitelinks=sl, callouts=co))
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()
    rsa = _por_tipo(ops, "ad_group_ad_operation")[0].ad_group_ad_operation.create.ad
    assert [h.text for h in rsa.responsive_search_ad.headlines] == hl
    assert [d.text for d in rsa.responsive_search_ad.descriptions] == ds
    assets = [o.asset_operation.create for o in _por_tipo(ops, "asset_operation")]
    textos_sitelink = [a.sitelink_asset.link_text for a in assets if a.sitelink_asset.link_text]
    assert textos_sitelink == [s.texto for s in sl]
    textos_callout = [a.callout_asset.callout_text for a in assets
                      if a.callout_asset.callout_text]
    assert textos_callout == co


def test_tracking_fica_intacto_com_ou_sem_localizador():
    """`final_url_suffix` (UTMs/vc_*) e a URL final não dependem do texto."""
    def _camp(ops):
        return _por_tipo(ops, "campaign_operation")[0].campaign_operation.create

    limpo, r1 = search.construir(CID, _brief(), login_customer_id="x")
    marcado, r2 = search.construir(
        CID, _brief(copy=_copy(headlines=["Procura Curso no Senac?", "Regras de 2026",
                                          "Quem Tem Direito", "A Tabela Oficial"])),
        login_customer_id="x")
    assert r1.ok and r2.ok, (r1.resumo(), r2.resumo())
    assert _camp(limpo).final_url_suffix == _camp(marcado).final_url_suffix
    assert _camp(marcado).final_url_suffix, "sufixo de marcação sumiu"
    rsa = _por_tipo(marcado, "ad_group_ad_operation")[0].ad_group_ad_operation.create.ad
    assert list(rsa.final_urls) == [_brief().url_final]


# ── limites reais de campo: continuam bloqueando ────────────────────────────


@pytest.mark.parametrize("troca,limite", [
    (dict(headlines=["X" * 31, "Regras de 2026", "Quem tem direito", "A tabela"]), 30),
    (dict(descriptions=["Y" * 91, "Portal informativo com a tabela legal."]), 90),
    (dict(callouts=["Z" * 26, "Fontes oficiais"]), 25),
    (dict(sitelinks=[Sitelink("W" * 26, "O que vale hoje", "E o que muda"),
                     Sitelink("Quem tem direito", "As condicoes", "Em linguagem")]), 25),
    (dict(snippet=Snippet("Cursos", ["V" * 26, "Tecnico", "Livre"])), 25),
])
def test_limite_de_campo_continua_bloqueando(troca, limite):
    _, r = search.construir(CID, _brief(copy=_copy(**troca)), login_customer_id="x")
    assert any(f"chars > limite {limite}" in a.motivo for a in r.erros), r.resumo()


# ── a cascata: C10 espelha o portão; o juiz decide o sentido ────────────────


def _pedido(**troca) -> Pedido:
    base = dict(n_headlines=15, n_descriptions=4, n_sitelinks=4, n_callouts=4,
                n_snippet=4, idioma="pt", fatos=("F1", "F2", "F3", "F4", "F5"),
                headers_snippet=("Tipos",), max_dki=1)
    base.update(troca)
    return Pedido(**base)


def _sincronizar(d: dict) -> None:
    for i, h in enumerate(d["headlines"]):
        d["ancoragem"]["headlines"][i]["chars"] = comprimento_efetivo(h)
    for i, t in enumerate(d["descriptions"]):
        d["ancoragem"]["descriptions"][i]["chars"] = len(t)
    c = medir(d["headlines"])
    c["mecanicas_distintas"] = len({e["mecanica"] for e in d["ancoragem"]["headlines"]})
    c["max_titulos_por_fato"] = 2
    d["auditoria"]["contagem_final"] = c


def _com_palavras_antes_proibidas() -> dict:
    d = copia.deepcopy(copy_valida())
    d["headlines"][3] = "Procura a Tabela por Faixa?"
    d["ancoragem"]["headlines"][3]["mecanica"] = "M8"
    d["descriptions"][1] = ("Portal informativo: o valor não é garantido a todos; "
                            "veja a tabela legal por faixa.")
    _sincronizar(d)
    return d


def test_c10_nao_transforma_localizador_em_achado():
    assert _c10_portao_do_lancamento(_com_palavras_antes_proibidas(), _pedido()) == []


def test_copy_legitima_com_palavra_antes_proibida_e_aceita_sem_reescrita():
    d = _com_palavras_antes_proibidas()
    original = copia.deepcopy(d)
    r = gerar(cliente=ClienteMock([copia.deepcopy(d)]), juiz=JuizMock(),
              pedido=_pedido(), prompt_usuario="<p>",
              juiz_semantico=lambda dados: [])
    assert r.ok, r.relatorio()
    assert r.dados["headlines"] == original["headlines"]
    assert r.dados["descriptions"] == original["descriptions"]


class _JuizLLM:
    """Dublê do LLM juiz: aponta erro em todo recurso que contém `alvo`."""

    def __init__(self, alvo: str, *, severidade: str = "erro", regra: str = "promessa"):
        self.alvo, self.severidade, self.regra = alvo, severidade, regra
        self.usuarios: list[str] = []

    def gerar(self, sistema: str, usuario: str) -> str:
        self.usuarios.append(usuario)
        obs = []
        for linha in usuario.splitlines():
            linha = linha.strip()
            if ":" in linha and self.alvo in linha and linha.split(":")[0].count("[") == 1:
                campo = linha.split(":")[0]
                if campo.startswith(("headline[", "description[", "callout[")):
                    obs.append({"campo": campo, "regra": self.regra,
                                "severidade": self.severidade,
                                "motivo": "promete o que nenhum fato sustenta",
                                "trecho": self.alvo, "conserto": "tirar a garantia"})
        return json.dumps({"observacoes": obs}, ensure_ascii=False)


def _promessa_falsa() -> dict:
    d = copia.deepcopy(copy_valida())
    d["headlines"][3] = "Saque Assegurado na Hora"
    _sincronizar(d)
    return d


def test_promessa_falsa_sem_palavra_proibida_passa_no_codigo():
    """Nenhuma lista enxerga: é por isso que o sentido é do juiz."""
    d = _promessa_falsa()
    pol = policy.Validador(vertical="informativo")
    assert pol.checar_texto(d["headlines"][3], "headline") == []
    assert js.localizar(d, pais="BR", idioma="pt", vertical="informativo") == []


def test_promessa_falsa_sem_palavra_proibida_e_apontada_e_nao_segue():
    d = _promessa_falsa()
    llm = _JuizLLM("Assegurado")
    juiz = js.montar_juiz(llm, fatos_texto="  F1 [data] 31/10/2026", nicho="FGTS",
                          termos_texto="  NÃO COLETADO (teste)",
                          destino="  anúncio → https://exemplo.com.br/r/fgts/",
                          pais="BR", idioma="pt", vertical="informativo")
    achados = juiz(d)
    assert [a.codigo for a in achados] == ["JS.promessa"]
    assert str(achados[0].alvo) == "headline[3]"

    # O modelo insiste na promessa: a copy não segue.
    insiste = {"texto": "Saque Assegurado na Hora", "mecanica": "M1", "fato": "-"}
    r = gerar(cliente=ClienteMock([d, dict(insiste), dict(insiste), dict(insiste)]),
              juiz=JuizMock(), pedido=_pedido(), prompt_usuario="<p>",
              juiz_semantico=juiz)
    assert r.ok is False, "promessa falsa aceita"
    assert any(a.codigo == "JS.promessa" for a in r.pendentes), r.pendentes


def test_conserto_do_juiz_e_por_asset_e_preserva_o_resto():
    d = _promessa_falsa()
    original = copia.deepcopy(d)
    juiz = js.montar_juiz(_JuizLLM("Assegurado"), fatos_texto="", nicho="FGTS",
                          pais="BR", idioma="pt", vertical="informativo")
    r = gerar(cliente=ClienteMock([d, {"texto": "Tabela Oficial por Faixa",
                                       "mecanica": "M1", "fato": "-"}]),
              juiz=JuizMock(), pedido=_pedido(), prompt_usuario="<p>",
              juiz_semantico=juiz)
    assert r.ok, r.relatorio()
    assert r.dados["headlines"][3] == "Tabela Oficial por Faixa"
    for i, h in enumerate(original["headlines"]):
        if i != 3:
            assert r.dados["headlines"][i] == h, i
    assert r.dados["descriptions"] == original["descriptions"]


@pytest.mark.parametrize("severidade,regra", [("aviso", "promessa"), ("erro", "estilo")])
def test_sugestao_de_estilo_nunca_e_aplicada(severidade, regra):
    """Aviso, ou 'erro' sem procedência (regra que não existe), não regenera."""
    d = _com_palavras_antes_proibidas()
    original = copia.deepcopy(d)
    juiz = js.montar_juiz(_JuizLLM("Procura", severidade=severidade, regra=regra),
                          fatos_texto="", nicho="FGTS",
                          pais="BR", idioma="pt", vertical="informativo")
    r = gerar(cliente=ClienteMock([copia.deepcopy(d)]), juiz=JuizMock(),
              pedido=_pedido(), prompt_usuario="<p>", juiz_semantico=juiz)
    assert r.ok, r.relatorio()
    assert r.dados["headlines"] == original["headlines"]


# ── o que o juiz recebe ─────────────────────────────────────────────────────


def test_localizar_marca_o_trecho_com_a_regra():
    d = _com_palavras_antes_proibidas()
    marcas = js.localizar(d, pais="BR", idioma="pt", vertical="informativo")
    assert any("headline[3]" in m and "deturpacao.declaracoes_nao_confiaveis" in m
               for m in marcas), marcas
    assert any("description[1]" in m and "garantido" in m for m in marcas), marcas


def test_o_juiz_recebe_fatos_tipados_termos_destino_e_localizadores():
    d = _com_palavras_antes_proibidas()
    llm = _JuizLLM("nada-casa-isto")
    juiz = js.montar_juiz(
        llm, fatos_texto="  f1 [contexto] 27 Departamentos Regionais (fonte: senac.br)",
        nicho="Cursos Senac",
        termos_texto=render._bloco_termos(None),
        destino="  anúncio → https://exemplo.com.br/r/senac/\n"
                "  sitelink[0] → https://exemplo.com.br/r/senac/",
        pais="BR", idioma="pt", vertical="informativo")
    assert juiz(d) == []
    u = llm.usuarios[0]
    assert "f1 [contexto] 27 Departamentos Regionais" in u
    assert "NÃO COLETADO" in u
    assert "https://exemplo.com.br/r/senac/" in u and "sitelink[0]" in u
    assert "deturpacao.declaracoes_nao_confiaveis" in u
    assert "não reprova" in u.lower()


def test_o_sistema_do_juiz_e_editor_e_nao_neutralizador():
    s = js.SISTEMA.lower()
    for trecho in ("destino", "cta", "preserve o ângulo", "menor ajuste",
                   "estilo", "identidade", "qualificador"):
        assert trecho in s, trecho
    assert "aviso de independência em todo recurso" in s


def _cockpit():
    fatos = tuple(SimpleNamespace(id=i, tipo=t, texto=x, fonte="lei.gov.br")
                  for i, t, x in (("F1", "data", "31/10/2026"), ("F2", "numero", "90 dias"),
                                  ("F3", "mudanca", "regra nova"),
                                  ("F4", "fonte_legal", "Lei 8.036/90"),
                                  ("F5", "prazo", "após aderir")))
    origem = SimpleNamespace(nicho="Saque-Aniversário FGTS",
                             url_final="https://exemplo.com.br/r/fgts/",
                             pais="BR", idioma="pt", vertical="informativo", fatos=fatos)
    return SimpleNamespace(origem=origem)


def test_escrever_liga_o_juiz_com_fatos_termos_e_destino():
    """A porta que o backend chama: o juiz de verdade recebe tudo."""
    from volc_ads.copy import encomendar as em

    c = ClienteMock([_com_palavras_antes_proibidas(), '{"observacoes": []}'])
    try:
        em.escrever(_cockpit(), keywords=["saque aniversario fgts"], cliente=c)
    except RoteiroEsgotado:
        pass  # só a primeira rodada interessa aqui
    juizes = [u for s, u in c.chamadas if s == js.SISTEMA]
    assert juizes, [s[:40] for s, _ in c.chamadas]
    u = juizes[0]
    assert "F2 [numero] 90 dias" in u
    assert "NÃO COLETADO" in u
    assert "https://exemplo.com.br/r/fgts/" in u
    assert "deturpacao.declaracoes_nao_confiaveis" in u


# ── o prompt do redator: a TRAVA 0 saiu (ADS-05/06) ─────────────────────────


def test_prompt_do_redator_nao_ensina_mais_trava_por_palavra():
    corpo = render.corpo()
    assert "{termos_travados}" not in corpo
    assert "TRAVA 0" not in corpo
    assert "FATO INESCREVÍVEL" not in corpo
    assert "DÚVIDA RESOLVE CONTRA O TEXTO" not in corpo


def test_prompt_do_redator_diz_que_localizador_nao_reprova():
    enc = render.Encomenda(nicho="Cursos Senac", url="https://exemplo.com.br/r/senac/",
                           keywords=("cursos senac",), ano=2026)
    p = render.montar(enc)
    assert not render.RX_PLACEHOLDER.findall(p)
    assert "LOCALIZADOR" in p
    # Declarações não confiáveis não aparecem mais como PROIBIDO.
    proibido = p[p.index("PROIBIDO —"):p.index("REGULADO —")]
    assert "Declarações não confiáveis" not in proibido
    assert "Portal informativo usando linguagem de prestador" not in proibido


def test_oficial_qualificando_o_canal_do_orgao_e_permitido_no_prompt():
    """ADS-47: o veto é à afiliação implícita do ANUNCIANTE, não à palavra."""
    corpo = render.corpo()
    assert "PROIBIDAS em qualquer recurso" not in corpo
    assert "canal oficial" in corpo
