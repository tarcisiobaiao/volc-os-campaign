"""Provas do contrato tipado de keyword — o que o payload preserva e o que recusa.

Rodar da raiz do projeto:
    backend/.venv/bin/python -m pytest volc_ads/campanha/testes_criterio.py -q

**Nenhum teste aqui fala com o Google.** O cliente é montado sem credencial e
injetado por monkeypatch, exatamente como em `testes_search.py`: o que se prova
é o PAYLOAD, porque é lá que moram os defeitos que este contrato persegue —
match type trocado por BROAD fixo, negativa no nível errado, negativa de um
grupo vazando para outro e erro de negativa descartado em silêncio.

Cada teste responde a uma pergunta que alguém vai fazer olhando uma campanha
que não entrega: "a negativa que eu escrevi está lá, com o alcance que eu
escrevi, e no grupo em que eu escrevi?"
"""

from __future__ import annotations

import dataclasses
import enum
import pathlib
import sys
from datetime import date
from importlib import import_module

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

from volc_ads.campanha import search, validacao  # noqa: E402
from volc_ads.campanha.brief import Brief, Copy, Sitelink, SubIntencao  # noqa: E402
from volc_ads.campanha.criterio import (  # noqa: E402
    Criterio,
    chave,
    Evidencia,
    conflitos,
    de_lista,
    deduplicar,
)

CID = "8017851692"


# ── cliente sem rede (mesmo shim de testes_search) ───────────────────────────


class _Enums:
    def __getattr__(self, nome: str):
        wrapper = getattr(import_module("google.ads.googleads.v25.enums"), nome)
        for attr in dir(wrapper):
            valor = getattr(wrapper, attr)
            if isinstance(valor, enum.EnumMeta):
                return valor
        raise AttributeError(nome)


def _cliente_sem_rede():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    c.enums = _Enums()
    return c


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch):
    monkeypatch.setattr(search, "cliente", lambda _login: _cliente_sem_rede())


# ── briefs de teste ─────────────────────────────────────────────────────────


def _copy(**troca) -> Copy:
    base = dict(
        headlines=["Regras do Saque Anual", "Quem Tem Direito em 2026",
                   "Tabela Oficial por Faixa", "O Prazo de 90 Dias"],
        descriptions=["Prazos, limites e quem tem direito, com fonte citada.",
                      "Portal informativo com a tabela legal por faixa etaria."],
        sitelinks=[Sitelink("Regras de 2026", "O que vale hoje", "E o que muda"),
                   Sitelink("Quem tem direito", "As condicoes", "Em linguagem simples")],
        callouts=["Conteudo informativo", "Fontes oficiais"],
    )
    base.update(troca)
    return Copy(**base)


def _brief(**troca) -> Brief:
    base = dict(
        nicho="Saque Anual",
        slug="saque-anual",
        url_final="https://creditoup.com.br/r/saque-anual/",
        keywords=["saque anual fgts", "regras do saque anual"],
        copy=_copy(),
        cpc_inicial=0.20,
    )
    base.update(troca)
    return Brief(**base)


def _ops(brief: Brief):
    ops, r = search.construir(CID, brief, login_customer_id=CID)
    return ops, r


def _por_tipo(ops, tipo: str):
    return [o for o in ops if o._pb.WhichOneof("operation") == tipo]


def _keywords(ops, *, negativa: bool):
    """(texto, match type, ad group) de cada AdGroupCriterion de keyword."""
    saida = []
    for o in _por_tipo(ops, "ad_group_criterion_operation"):
        c = o.ad_group_criterion_operation.create
        if bool(c.negative) is negativa:
            saida.append((c.keyword.text, c.keyword.match_type.name, c.ad_group))
    return saida


def _negativas_de_campanha(ops):
    """Só os CampaignCriterion que são KEYWORD — geo e idioma também vivem lá."""
    saida = []
    for o in _por_tipo(ops, "campaign_criterion_operation"):
        c = o.campaign_criterion_operation.create
        if c._pb.WhichOneof("criterion") == "keyword":
            saida.append((c.keyword.text, c.keyword.match_type.name, bool(c.negative)))
    return saida


# ── 1. o match type da positiva sobrevive ───────────────────────────────────


def test_positiva_exact_permanece_exact_ate_o_payload():
    """EXACT declarado é EXACT enviado — não o `match_type` do brief.

    A versão anterior lia `brief.match_type` dentro do laço por grupo, então o
    match type de uma keyword era, na prática, o de todas.
    """
    b = _brief(
        match_type="PHRASE",  # o default do brief é outro DE PROPÓSITO
        criterios=[
            Criterio("saque anual fgts", "EXACT"),
            Criterio("regras do saque anual", "BROAD"),
        ],
        estrategia_lance="MAXIMIZE_CONVERSIONS",  # BROAD exige lance automático
    )
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    achado = {t: m for t, m, _ in _keywords(ops, negativa=False)}
    assert achado == {
        "saque anual fgts": "EXACT",
        "regras do saque anual": "BROAD",
    }


# ── 2. os três match types de negativa são distintos ────────────────────────


def test_negativas_exact_phrase_e_broad_permanecem_distintas():
    """Três negativas, três match types. Antes as três saíam BROAD."""
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("simulador", "EXACT", negativa=True),
        Criterio("como funciona", "PHRASE", negativa=True),
        Criterio("gratis download", "BROAD", negativa=True),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    achado = {t: m for t, m, _ in _keywords(ops, negativa=True)}
    assert achado == {
        "simulador": "EXACT",
        "como funciona": "PHRASE",
        "gratis download": "BROAD",
    }


# ── 3 e 4. cada nível no seu recurso ────────────────────────────────────────


def test_negativa_de_campanha_vira_campaign_criterion():
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("emprestimo", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert _negativas_de_campanha(ops) == [("emprestimo", "PHRASE", True)]
    # e não vazou para o ad group
    assert _keywords(ops, negativa=True) == []


def test_negativa_de_grupo_vira_ad_group_criterion():
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("emprestimo", "PHRASE", negativa=True, nivel="AD_GROUP"),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert [(t, m) for t, m, _ in _keywords(ops, negativa=True)] == [
        ("emprestimo", "PHRASE")
    ]
    assert _negativas_de_campanha(ops) == []


def test_negativa_de_grupo_nao_migra_para_campanha_em_silencio():
    """O nível declarado é o nível enviado, nos dois sentidos."""
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("um", "EXACT", negativa=True, nivel="AD_GROUP"),
        Criterio("dois", "EXACT", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, _ = _ops(b)
    assert [t for t, _, _ in _keywords(ops, negativa=True)] == ["um"]
    assert [t for t, _, _ in _negativas_de_campanha(ops)] == ["dois"]


# ── 5. a negativa de um grupo não vaza para outro ───────────────────────────


def test_negativa_de_um_grupo_nao_vaza_para_outro():
    """O defeito que a separação por sub-intenção existe para permitir evitar.

    `ACESSO` nega `simulador`; `VALOR` não. Se a negativa vazasse, o grupo
    `VALOR` perderia tráfego que ninguém mandou bloquear — e o relatório não
    diria por quê.
    """
    b = _brief(
        keywords=[],
        sub_intencoes=[
            SubIntencao(nome="ACESSO", keywords=["saque anual fgts"]),
            SubIntencao(nome="VALOR", keywords=["valor do saque anual"]),
        ],
        criterios=[
            Criterio("saque anual fgts", "PHRASE", grupo="ACESSO"),
            Criterio("valor do saque anual", "PHRASE", grupo="VALOR"),
            Criterio("simulador", "PHRASE", negativa=True, grupo="ACESSO"),
        ],
    )
    ops, r = _ops(b)
    assert r.ok, r.resumo()

    negativas = _keywords(ops, negativa=True)
    assert len(negativas) == 1, "a negativa de ACESSO apareceu em mais de um grupo"
    _texto, _mt, ag_da_negativa = negativas[0]

    # o ad group da negativa é o MESMO da keyword de ACESSO, e não o de VALOR
    positivas = {t: ag for t, _m, ag in _keywords(ops, negativa=False)}
    assert ag_da_negativa == positivas["saque anual fgts"]
    assert ag_da_negativa != positivas["valor do saque anual"]


def test_negativa_sem_grupo_vale_em_todos_os_grupos():
    """A semântica histórica de `negativas_adgroup`, preservada."""
    b = _brief(
        keywords=[],
        sub_intencoes=[
            SubIntencao(nome="ACESSO", keywords=["saque anual fgts"]),
            SubIntencao(nome="VALOR", keywords=["valor do saque anual"]),
        ],
        criterios=[
            Criterio("saque anual fgts", "PHRASE", grupo="ACESSO"),
            Criterio("valor do saque anual", "PHRASE", grupo="VALOR"),
            Criterio("simulador", "PHRASE", negativa=True),  # sem grupo
        ],
    )
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    ags = {ag for _t, _m, ag in _keywords(ops, negativa=True)}
    assert len(ags) == 2, "a negativa sem grupo tem de entrar nos DOIS ad groups"


def test_grupo_inexistente_e_recusado_na_construcao():
    """Rótulo com erro de digitação viraria negativa que some do payload."""
    with pytest.raises(ValueError, match="não existe neste brief"):
        _brief(
            keywords=[],
            sub_intencoes=[SubIntencao(nome="ACESSO", keywords=["saque anual fgts"])],
            criterios=[
                Criterio("saque anual fgts", "PHRASE", grupo="ACESSO"),
                Criterio("x", "PHRASE", negativa=True, grupo="ACESO"),  # typo
            ],
        )


# ── 7. erro de negativa é visível ───────────────────────────────────────────


def test_negativa_longa_demais_produz_erro_visivel():
    """Antes ela sumia: o `Resultado()` que a julgava era descartado."""
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("x" * 200, "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, r = _ops(b)
    assert not r.ok, "negativa com 200 chars tinha de barrar a construção"
    achados = [a for a in r.erros if a.campo == "negativa_campanha"]
    assert achados, f"nenhum achado apontou a negativa: {r.resumo()}"
    assert "chars" in achados[0].motivo


def test_negativa_com_palavras_demais_produz_erro_visivel():
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio(" ".join(["p"] * 30), "PHRASE", negativa=True),
    ])
    _ops_, r = _ops(b)
    assert not r.ok
    assert any("palavras" in a.motivo for a in r.erros), r.resumo()


def test_lista_de_negativas_vazia_nao_inventa_erro():
    """O erro fantasma que obrigava o `Resultado()` descartável a existir.

    `checar_keywords` emite "nenhuma keyword válida" numa lista vazia — certo
    para as positivas, errado para as negativas. Se a correção tivesse sido
    apenas ligar o resultado descartável ao principal, TODA campanha sem
    negativa passaria a falhar.
    """
    b = _brief()  # nenhuma negativa declarada
    _ops_, r = _ops(b)
    assert r.ok, r.resumo()
    assert not [a for a in r.achados if "nenhuma keyword" in a.motivo]


# ── 8. duplicata normalizada não vira duas operações ────────────────────────


def test_duplicata_normalizada_nao_cria_duas_operacoes():
    """Acento, caixa e espaço duplo são a MESMA keyword para o Google.

    Duas operações para o mesmo critério fazem a API recusar a segunda — e num
    mutate atômico isso derruba a campanha inteira.
    """
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("simulador grátis", "PHRASE", negativa=True, nivel="CAMPAIGN"),
        Criterio("SIMULADOR  GRÁTIS", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert len(_negativas_de_campanha(ops)) == 1
    assert any("duplicata" in a.motivo for a in r.achados), \
        "a duplicata foi removida mas ninguém foi avisado"


def test_mesmo_texto_com_match_types_diferentes_sao_dois_criterios():
    """`"curso"` EXACT e `"curso"` PHRASE coexistem na API — e devem coexistir aqui.

    Deduplicar por texto, como um `set()` faria, apagaria um dos dois.
    """
    unicos, descartados = deduplicar([
        Criterio("curso", "EXACT", negativa=True),
        Criterio("curso", "PHRASE", negativa=True),
    ])
    assert len(unicos) == 2
    assert descartados == []


def test_dedup_preserva_a_ordem_e_o_primeiro_declarado_vence():
    """Determinismo: a mesma entrada tem de produzir o mesmo payload.

    Ordenar por "qualidade" faria o selo do payload deixar de significar algo.
    """
    a = Criterio("um", "EXACT", negativa=True, motivo="primeiro")
    b = Criterio("um", "EXACT", negativa=True, motivo="segundo")
    unicos, descartados = deduplicar([a, b])
    assert [c.motivo for c in unicos] == ["primeiro"]
    assert descartados[0][0].motivo == "segundo"
    assert descartados[0][1].motivo == "primeiro"


# ── 9. conflito positiva × negativa ─────────────────────────────────────────


def test_conflito_positiva_negativa_e_detectado_no_resultado():
    """A keyword entra no payload e nunca serve uma consulta. Isso tem de aparecer."""
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("saque", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    _ops_, r = _ops(b)
    conflito = [a for a in r.achados if a.campo == "conflito"]
    assert conflito, f"conflito não detectado: {r.resumo()}"
    assert "anula" in conflito[0].motivo


def test_conflito_respeita_o_escopo_do_grupo():
    """Negativa de `VALOR` não conflita com keyword de `ACESSO` — não a alcança."""
    pos = Criterio("saque anual", "PHRASE", grupo="ACESSO")
    neg_mesmo = Criterio("saque", "PHRASE", negativa=True, grupo="ACESSO")
    neg_outro = Criterio("saque", "PHRASE", negativa=True, grupo="VALOR")
    assert len(conflitos([pos, neg_mesmo])) == 1
    assert conflitos([pos, neg_outro]) == []


def test_semantica_de_bloqueio_segue_a_da_api():
    """EXACT só a consulta idêntica; PHRASE contígua na ordem; BROAD todos os tokens."""
    consulta = "curso de ingles gratis"
    assert not Criterio("curso gratis", "EXACT", negativa=True).bloqueia(consulta)
    assert Criterio("curso de ingles gratis", "EXACT", negativa=True).bloqueia(consulta)
    assert Criterio("de ingles", "PHRASE", negativa=True).bloqueia(consulta)
    assert not Criterio("curso gratis", "PHRASE", negativa=True).bloqueia(consulta)
    assert Criterio("curso gratis", "BROAD", negativa=True).bloqueia(consulta)
    # positiva nunca "bloqueia"
    assert not Criterio("curso gratis", "BROAD").bloqueia(consulta)


# ── 10. o cliente antigo continua funcionando ───────────────────────────────


def test_cliente_antigo_com_list_de_str_continua_funcionando():
    """Compatibilidade COMPORTAMENTAL, não só de assinatura.

    O brief antigo não declara `criterios`. O payload que sai tem de ser o
    mesmo de antes: positivas no `match_type` do brief, negativas em BROAD.
    """
    b = _brief(
        match_type="EXACT",
        negativas_campanha=["emprestimo"],
        negativas_adgroup=["simulador"],
    )
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert {m for _t, m, _ag in _keywords(ops, negativa=False)} == {"EXACT"}
    assert _negativas_de_campanha(ops) == [("emprestimo", "BROAD", True)]
    assert [(t, m) for t, m, _ in _keywords(ops, negativa=True)] == [
        ("simulador", "BROAD")
    ]


def test_sub_intencao_negativas_legado_continua_no_seu_grupo():
    b = _brief(
        keywords=[],
        sub_intencoes=[
            SubIntencao(nome="ACESSO", keywords=["saque anual fgts"],
                        negativas=["simulador"]),
            SubIntencao(nome="VALOR", keywords=["valor do saque anual"]),
        ],
    )
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert len(_keywords(ops, negativa=True)) == 1


def test_declarar_negativa_nos_dois_contratos_e_recusado():
    """Precedência silenciosa é como uma das listas some do payload."""
    with pytest.raises(ValueError, match="nos dois contratos"):
        _brief(
            criterios=[
                Criterio("saque anual fgts", "PHRASE"),
                Criterio("regras do saque anual", "PHRASE"),
                Criterio("x", "PHRASE", negativa=True),
            ],
            negativas_campanha=["y"],
        )


def test_positiva_tipada_tem_de_cobrir_a_estrutura():
    """Keyword fora do contrato tipado seria descartada em silêncio."""
    with pytest.raises(ValueError, match="não cobre"):
        _brief(criterios=[Criterio("saque anual fgts", "EXACT")])  # falta a 2ª


def test_adaptador_de_lista_descarta_so_ruido_de_serializacao():
    saida = de_lista(["a", "", "  ", "b"], match_type="EXACT", negativa=True)
    assert [c.texto for c in saida] == ["a", "b"]
    assert {c.origem for c in saida} == {"LEGADO"}
    assert {c.match_type for c in saida} == {"EXACT"}


# ── a regra da ausência e da procedência ────────────────────────────────────


def test_ausencia_continua_ausencia():
    c = Criterio("x", "EXACT")
    assert c.motivo is None
    assert c.evidencia is None
    assert c.observado_em is None
    assert c.aprovado_por is None
    assert c.medido is False


def test_search_term_sem_medicao_e_recusado():
    """Hipótese com crachá de fato é o defeito que a doutrina proíbe."""
    with pytest.raises(ValueError, match="SEARCH_TERM"):
        Criterio("x", negativa=True, origem="SEARCH_TERM")
    with pytest.raises(ValueError, match="SEARCH_TERM"):
        Criterio("x", negativa=True, origem="SEARCH_TERM",
                 evidencia=Evidencia("HIPOTESE", fonte="modelo"))


def test_evidencia_medida_exige_janela_e_metricas():
    with pytest.raises(ValueError, match="janela"):
        Evidencia("MEDIDO", fonte="search_term_view", metricas={"impressoes": 1})
    with pytest.raises(ValueError, match="métricas"):
        Evidencia("MEDIDO", fonte="search_term_view",
                  janela_inicio=date(2026, 8, 1), janela_fim=date(2026, 8, 27))
    ok = Evidencia("MEDIDO", fonte="search_term_view",
                   janela_inicio=date(2026, 8, 1), janela_fim=date(2026, 8, 27),
                   metricas={"impressoes": 312, "cliques": 0})
    assert ok.medida


def test_keyword_positiva_de_campanha_e_recusada():
    """A API só aceita `CampaignCriterion.keyword` com `negative=True`."""
    with pytest.raises(ValueError, match="positiva não existe em nível de campanha"):
        Criterio("x", nivel="CAMPAIGN")


def test_criterio_de_campanha_nao_declara_grupo():
    with pytest.raises(ValueError, match="não pode declarar grupo"):
        Criterio("x", negativa=True, nivel="CAMPAIGN", grupo="ACESSO")


# ── 11. o selo é do payload: mudar a negativa muda a impressão ──────────────


def test_mudar_o_match_type_da_negativa_muda_a_impressao_do_payload():
    """O selo é do payload exato. Se o alcance da negativa muda, o selo cai.

    Sem isto, provar com `PHRASE` e subir com `BROAD` passaria pelo portão —
    o operador teria aprovado um alcance e a conta receberia outro.
    """
    from volc_ads import subir as sb

    def _mk(mt: str):
        b = _brief(criterios=[
            Criterio("saque anual fgts", "PHRASE"),
            Criterio("regras do saque anual", "PHRASE"),
            Criterio("simulador", mt, negativa=True, nivel="CAMPAIGN"),
        ])
        ops, r = _ops(b)
        assert r.ok, r.resumo()
        return sb._impressao(ops)

    assert _mk("PHRASE") != _mk("BROAD"), \
        "trocar o match type da negativa não mudou a impressão — o selo não protege nada"


def test_mudar_o_nivel_da_negativa_muda_a_impressao_do_payload():
    from volc_ads import subir as sb

    def _mk(nivel: str):
        b = _brief(criterios=[
            Criterio("saque anual fgts", "PHRASE"),
            Criterio("regras do saque anual", "PHRASE"),
            Criterio("simulador", "EXACT", negativa=True, nivel=nivel),
        ])
        ops, r = _ops(b)
        assert r.ok, r.resumo()
        return sb._impressao(ops)

    assert _mk("CAMPAIGN") != _mk("AD_GROUP")


def test_a_mesma_entrada_produz_a_mesma_impressao():
    """Determinismo — sem ele o selo não vale nada."""
    from volc_ads import subir as sb

    def _mk():
        b = _brief(criterios=[
            Criterio("saque anual fgts", "PHRASE"),
            Criterio("regras do saque anual", "PHRASE"),
            Criterio("simulador", "EXACT", negativa=True, nivel="CAMPAIGN"),
        ])
        ops, r = _ops(b)
        return sb._impressao(ops)

    assert _mk() == _mk()


# ── 12, 18 e 19. nada é criado, e a campanha nasce pausada ──────────────────


def test_construir_nao_fala_com_a_rede_e_nao_cria_nada():
    """`construir()` só monta operações. Quem escreve é `mutar()`, atrás da trava."""
    b = _brief(criterios=[
        Criterio("saque anual fgts", "EXACT"),
        Criterio("regras do saque anual", "EXACT"),
        Criterio("simulador", "PHRASE", negativa=True),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    # toda operação é um `create` — nenhum `remove`, nenhum `update`
    assert ops, "nenhuma operação montada"
    for o in ops:
        nome = o._pb.WhichOneof("operation")
        sub = getattr(o, nome)
        assert sub._pb.WhichOneof("operation") == "create", \
            f"{nome} não é create — esta missão não altera nada existente"


def test_campanha_continua_nascendo_pausada_com_criterios_tipados():
    b = _brief(criterios=[
        Criterio("saque anual fgts", "EXACT"),
        Criterio("regras do saque anual", "EXACT"),
        Criterio("simulador", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, _ = _ops(b)
    camp = [o.campaign_operation.create for o in _por_tipo(ops, "campaign_operation")]
    assert len(camp) == 1
    assert camp[0].status.name == "PAUSED"


def test_a_trava_de_escrita_continua_fechada():
    """Prova de que esta missão não pode mutar: a trava é de dois fatores."""
    from volc_ads.gads import modo

    with pytest.raises(modo.EscritaBloqueada):
        modo.exigir_leitura_apenas("teste do contrato tipado")


# ── achados carregam o rótulo de onde vieram ────────────────────────────────


def test_achado_de_negativa_diz_de_que_grupo_veio():
    """"80 chars > 80" num brief de quatro grupos não diz onde procurar."""
    b = _brief(
        keywords=[],
        sub_intencoes=[
            SubIntencao(nome="ACESSO", keywords=["saque anual fgts"]),
            SubIntencao(nome="VALOR", keywords=["valor do saque anual"]),
        ],
        criterios=[
            Criterio("saque anual fgts", "PHRASE", grupo="ACESSO"),
            Criterio("valor do saque anual", "PHRASE", grupo="VALOR"),
            Criterio("x" * 200, "PHRASE", negativa=True, grupo="VALOR"),
        ],
    )
    _ops_, r = _ops(b)
    assert not r.ok
    assert any(a.campo == "negativa[VALOR]" for a in r.erros), r.resumo()


def test_checar_criterios_nao_exige_item_por_padrao():
    r = validacao.Resultado()
    assert validacao.checar_criterios([], r) == []
    assert r.ok, "lista vazia de negativa não pode virar erro"

    r2 = validacao.Resultado()
    validacao.checar_criterios([], r2, exigir_pelo_menos_um=True)
    assert not r2.ok, "para as positivas, lista vazia CONTINUA sendo erro"


def test_positiva_broad_individual_nao_burla_a_doutrina_do_leilao():
    """O portão do BROAD × MANUAL_CPC vale POR KEYWORD, não só pelo default.

    Antes desta checagem, `match_type="PHRASE"` no brief e uma positiva BROAD
    declarada individualmente entravam juntos: o portão olhava só o default e a
    keyword larga passava pela porta dos fundos, comprando consulta larga com
    lance cego.
    """
    with pytest.raises(ValueError, match="BROAD com MANUAL_CPC"):
        _brief(
            match_type="PHRASE",
            estrategia_lance="MANUAL_CPC",
            criterios=[
                Criterio("saque anual fgts", "BROAD"),
                Criterio("regras do saque anual", "PHRASE"),
            ],
        )


def test_negativa_broad_continua_permitida_com_lance_manual():
    """Negativa BROAD não compra consulta nenhuma — ela bloqueia."""
    b = _brief(
        estrategia_lance="MANUAL_CPC",
        criterios=[
            Criterio("saque anual fgts", "PHRASE"),
            Criterio("regras do saque anual", "PHRASE"),
            Criterio("simulador gratis", "BROAD", negativa=True, nivel="CAMPAIGN"),
        ],
    )
    _ops_, r = _ops(b)
    assert r.ok, r.resumo()


def test_positiva_tipada_que_nao_esta_na_estrutura_e_recusada():
    """A recíproca da cobertura, e a mais perigosa das duas.

    `Escolha.keywords_fora` — o que o operador DESMARCOU — filtra
    `cockpit.grupos` na montagem do brief, mas não filtra `criterios`. Sem esta
    checagem, uma keyword desmarcada voltaria pelo contrato tipado; e como um
    critério sem grupo vale em TODOS os grupos, ela entraria em todos eles. A
    campanha compraria um termo que o operador tirou.
    """
    with pytest.raises(ValueError, match="não estão na estrutura"):
        _brief(criterios=[
            Criterio("saque anual fgts", "PHRASE"),
            Criterio("regras do saque anual", "PHRASE"),
            Criterio("keyword que o operador desmarcou", "PHRASE"),
        ])


def test_a_cobertura_exata_e_aceita():
    """Nem sobra nem falta: o contrato tipado descreve a estrutura declarada."""
    b = _brief(criterios=[
        Criterio("saque anual fgts", "EXACT"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("simulador", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert {t for t, _m, _ag in _keywords(ops, negativa=False)} == {
        "saque anual fgts", "regras do saque anual"}


# ── o aviso sobrevive ao CAMINHO FELIZ ──────────────────────────────────────


def test_aviso_de_conflito_sobrevive_a_prova_que_passa(monkeypatch):
    """O caminho feliz é o caminho em que o operador aprova e gasta.

    ⚠️ A versão anterior deste teste NÃO PROVAVA NADA: ela montava a tupla de
    avisos com as próprias mãos, duplicando a expressão de `subir.py`, e depois
    só conferia que o dataclass tinha o campo. Apagar as três linhas
    `avisos_locais=avisos_locais` de `preparar()` deixava o teste VERDE — a
    prova aceitava exatamente o erro que existia para pegar.

    Agora chama `preparar()` de verdade, com o `validate_only` dublado (nenhuma
    rede), e lê o que a projeção HTTP entrega. Sabotar a propagação faz falhar.
    """
    from backend.app.trafego import projecao
    from volc_ads import subir as sb

    # `validate_only` dublado: sem rede, e ACEITANDO — é o caminho feliz que
    # este teste persegue. Retornar `None` é o contrato de "sem falha".
    monkeypatch.setattr(sb, "validar_mutacoes", lambda *a, **k: None)

    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        # anula AS DUAS positivas, mas é AVISO — a construção passa
        Criterio("saque", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    preparo = sb.preparar(CID, b, login_customer_id=CID, canal="SEARCH")

    assert preparo.selo is not None, "a prova tinha de PASSAR neste teste"
    assert preparo.recusa_local == "", "nada podia barrar"

    # e mesmo tendo passado, os avisos chegaram
    assert preparo.avisos_locais, "o aviso morreu no caminho feliz"
    assert any("conflito" in a for a in preparo.avisos_locais), preparo.avisos_locais

    # até a projeção que a tela consome
    visto = projecao.preparo(preparo)
    assert visto["aprovado"] is True
    assert any("conflito" in a for a in visto["avisos_locais"]), visto["avisos_locais"]


# ── os achados da revisão adversarial ───────────────────────────────────────


def test_negativa_declarada_nos_dois_escopos_emite_UMA_operacao():
    """C1 — `grupo=None` e `grupo="VALOR"` resolvem para o MESMO ad group.

    `Criterio.identidade` os trata como declarações diferentes, e está certo:
    "vale em todos" e "vale só no VALOR" são coisas diferentes de se dizer. Mas
    depois de resolvido quem vale neste grupo, as duas viram a MESMA operação —
    e a API recusa a segunda, derrubando o mutate atômico inteiro.

    Este é o contrato ANTIGO, que produz o caso sozinho — a versão anterior
    desta entrega emitia duas operações onde `f4cf128` emitia uma.
    """
    b = _brief(
        keywords=[],
        sub_intencoes=[
            SubIntencao("VALOR", ["mensalidade do curso"], negativas=["gratis"]),
        ],
        negativas_adgroup=["gratis"],
    )
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert len(_keywords(ops, negativa=True)) == 1, "duas operações idênticas no mesmo ad group"
    assert any("duplicata" in a.motivo for a in r.achados), r.resumo()


def test_acento_nao_e_deduplicado_em_negativa():
    """C8 — apagar `"gratis"` porque `"grátis"` existe perde um bloqueio.

    Negativa não expande para variantes próximas. Se as duas grafias forem
    coisas diferentes para o Google, deduplicá-las apaga o que o operador
    declarou; se forem a mesma, mandar as duas custa uma operação que a API
    aceita. Mandar as duas nunca é pior.
    """
    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("grátis", "PHRASE", negativa=True, nivel="CAMPAIGN"),
        Criterio("gratis", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    ops, r = _ops(b)
    assert r.ok, r.resumo()
    assert {t for t, _m, _n in _negativas_de_campanha(ops)} == {"grátis", "gratis"}
    # e caixa/espaço CONTINUAM colapsando
    assert chave("  SIMULADOR   Grátis ") == chave("simulador grátis")


def test_evidencia_com_janela_no_futuro_e_recusada():
    """C10 — observação que começa amanhã não é observação."""
    from datetime import timedelta

    with pytest.raises(ValueError, match="futuro"):
        Evidencia("MEDIDO", fonte="search_term_view",
                  janela_inicio=date.today() + timedelta(days=1),
                  janela_fim=date.today() + timedelta(days=30),
                  metricas={"impressoes": 1})


def test_display_avisa_sobre_negativa_tipada():
    """C5 — a guarda do Display lia só os campos antigos.

    Com o contrato tipado, `negativas_campanha`/`negativas_adgroup` chegam
    VAZIAS e tudo vive em `criterios`. A guarda parava de disparar, e um pedido
    de Display com exclusões declaradas voltava aprovado, sem operação de
    exclusão e sem uma linha dizendo por quê.
    """
    from volc_ads.campanha import display

    b = _brief(criterios=[
        Criterio("saque anual fgts", "PHRASE"),
        Criterio("regras do saque anual", "PHRASE"),
        Criterio("simulador", "PHRASE", negativa=True, nivel="CAMPAIGN"),
    ])
    r = validacao.Resultado()
    display._avisos_de_escopo(b, r) if hasattr(display, "_avisos_de_escopo") else None
    # o caminho público: montar e procurar o aviso
    achados = []
    try:
        _ops_, rr = display.construir(CID, b, login_customer_id=CID)
        achados = rr.achados
    except Exception:  # noqa: BLE001 — Display pode recusar por outro motivo
        pass
    alvo = [a for a in achados if a.campo == "negativas"]
    assert alvo, f"Display não avisou sobre negativa tipada: {[a.campo for a in achados]}"
