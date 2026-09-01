"""Testes do construtor de Search — as duas mudanças desta entrega.

Rodar da raiz do projeto:
    backend/.venv/bin/python -m pytest volc_ads/campanha/testes_search.py -q

**Nenhum teste aqui fala com o Google.** O cliente é montado sem credencial
(`_cliente_sem_rede`) e injetado por monkeypatch: o que se testa é o PAYLOAD,
que é onde moram os defeitos que este arquivo persegue — id temporário
colidindo, keyword no ad group errado, ad group sem anúncio, política que só
enxerga português. Quem julga se o payload é aceitável é o `validate_only`,
que roda contra a conta real e não cabe num teste unitário.

Dois grupos de teste, um por defeito corrigido:

  FAIXAS E GRUPOS  ids temporários não colidem, cada sub-intenção vira um ad
                   group com suas keywords, seu lance e seu RSA, e o brief sem
                   sub-intenção continua produzindo exatamente um ad group.

  POLÍTICA         `policy/spec.py` no lugar de `campanha/validacao.py`. O
                   teste que importa é o do espanhol: ele reproduz o buraco
                   antigo antes de provar que ele fechou.
"""

from __future__ import annotations

import dataclasses
import enum
import pathlib
import re
import sys
from importlib import import_module

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

from volc_ads.campanha import comum, conteudo, search, validacao  # noqa: E402
from volc_ads.campanha.brief import (  # noqa: E402
    REDE_LEGADA_SEARCH,
    RedeDePesquisa,
    SEM_SUB_INTENCAO,
    Brief,
    Copy,
    Sitelink,
    SubIntencao,
)

CID = "8017851692"


# ── cliente sem rede ────────────────────────────────────────────────────────


class _Enums:
    """`client.enums` sem credencial.

    O `_EnumGetter` do SDK recebe um `GoogleAdsClient` inteiro no construtor, e
    montar um exige refresh token válido — `load_from_dict` com credencial
    falsa levanta `RefreshError` na hora. Este shim faz o mesmo trabalho pelo
    módulo público de enums da v25: acha, dentro do wrapper `XEnum`, a classe
    que de fato é um enum.
    """

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
    """Nenhum teste deste arquivo carrega ~/google-ads.yaml."""
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


def _por_tipo(ops, tipo: str):
    return [o for o in ops if o._pb.WhichOneof("operation") == tipo]


def _adgroups(ops):
    return [o.ad_group_operation.create for o in _por_tipo(ops, "ad_group_operation")]


# ── faixas de id temporário ─────────────────────────────────────────────────


def test_faixa_de_adgroup_desce_a_partir_de_menos_3():
    """O primeiro grupo mantém -3: payload de um ad group fica idêntico."""
    assert comum.temp_adgroup(CID, 0) == f"customers/{CID}/adGroups/-3"
    assert comum.temp_adgroup(CID, 1) == f"customers/{CID}/adGroups/-4"
    assert comum.temp_adgroup(CID, 2) == f"customers/{CID}/adGroups/-5"


def test_faixa_de_adgroup_nunca_alcanca_a_de_asset():
    """A invariante que o teto de 90 existe para garantir.

    Se o último ad group chegasse a -100, a referência do primeiro sitelink e a
    do ad group apontariam para o mesmo resource name temporário — e o sintoma
    apareceria no asset, longe da causa.
    """
    ultimo = comum.T_ADGROUP_BASE - (comum.T_ADGROUP_MAX - 1)
    assert ultimo > comum.T_ASSET_BASE
    assert int(comum.temp_adgroup(CID, comum.T_ADGROUP_MAX - 1).rsplit("/", 1)[1]) == ultimo


def test_adgroup_fora_da_faixa_levanta_em_vez_de_colidir():
    with pytest.raises(ValueError, match="faixa"):
        comum.temp_adgroup(CID, comum.T_ADGROUP_MAX)
    with pytest.raises(ValueError):
        comum.temp_adgroup(CID, -1)


# ── contrato do brief ───────────────────────────────────────────────────────


def test_keywords_e_sub_intencoes_juntas_sao_recusadas():
    """Duas fontes de verdade descartariam keyword em silêncio."""
    with pytest.raises(ValueError, match="OU"):
        _brief(keywords=["a b"], sub_intencoes=[SubIntencao("ACESSO", ["c d"])])


def test_brief_sem_keyword_nenhuma_e_recusado():
    with pytest.raises(ValueError, match="sem keyword"):
        _brief(keywords=[])


def test_sub_intencao_duplicada_e_recusada():
    with pytest.raises(ValueError, match="duas vezes"):
        _brief(keywords=[], sub_intencoes=[SubIntencao("Acesso", ["a b"]),
                                           SubIntencao("ACESSO", ["c d"])])


def test_sub_intencao_vazia_ou_sem_nome_e_recusada():
    with pytest.raises(ValueError, match="sem keyword"):
        _brief(keywords=[], sub_intencoes=[SubIntencao("ACESSO", [])])
    with pytest.raises(ValueError, match="sem nome"):
        SubIntencao("  ", ["a b"])


def test_grupos_sinaliza_a_ausencia_de_sub_intencao():
    g = _brief().grupos()
    assert len(g) == 1
    assert g[0].nome == SEM_SUB_INTENCAO
    assert g[0].keywords == ["saque anual fgts", "regras do saque anual"]


# ── compatibilidade: brief sem sub-intenção ─────────────────────────────────


def test_sem_sub_intencao_continua_um_ad_group_so():
    ops, r = search.construir(CID, _brief(), login_customer_id="x")
    assert r.ok, r.resumo()
    grupos = _adgroups(ops)
    assert len(grupos) == 1
    assert grupos[0].name.startswith("AdGroup_")
    assert grupos[0].cpc_bid_micros == 200_000          # o cpc_inicial do brief
    assert grupos[0].resource_name == comum.temp_adgroup(CID, 0)
    assert len(_por_tipo(ops, "ad_group_ad_operation")) == 1


# ── N ad groups ─────────────────────────────────────────────────────────────


def _brief_4_grupos(**troca) -> Brief:
    subs = [
        SubIntencao("ACESSO", ["saque anual fgts", "app do fgts"], cpc_inicial=0.74),
        SubIntencao("ELEGIBILIDADE", ["quem tem direito ao saque anual"],
                    cpc_inicial=1.09, negativas=["advogado"]),
        SubIntencao("VALOR", ["quanto recebo no saque anual"], cpc_inicial=1.50),
        SubIntencao("OUTROS", ["saque anual ou rescisao"]),
    ]
    return _brief(keywords=[], sub_intencoes=subs,
                  negativas_adgroup=["concurso"], **troca)


def test_cada_sub_intencao_vira_um_ad_group_com_lance_proprio():
    """O spread de 9× do cluster medido tem onde morar no payload."""
    ops, r = search.construir(CID, _brief_4_grupos(), login_customer_id="x")
    assert r.ok, r.resumo()
    grupos = _adgroups(ops)
    assert [g.name.split("_")[0] for g in grupos] == [
        "ACESSO", "ELEGIBILIDADE", "VALOR", "OUTROS"]
    assert [g.cpc_bid_micros for g in grupos] == [740_000, 1_090_000, 1_500_000, 200_000]
    # ids temporários distintos — a condição de o mutate ser interpretável
    assert len({g.resource_name for g in grupos}) == 4


def test_keywords_negativas_e_rsa_ficam_cada_uma_no_seu_grupo():
    ops, _ = search.construir(CID, _brief_4_grupos(), login_customer_id="x")
    kw: dict[str, list[str]] = {}
    neg: dict[str, list[str]] = {}
    rsa: dict[str, int] = {}
    for o in _por_tipo(ops, "ad_group_criterion_operation"):
        k = o.ad_group_criterion_operation.create
        (neg if k.negative else kw).setdefault(k.ad_group, []).append(k.keyword.text)
    for o in _por_tipo(ops, "ad_group_ad_operation"):
        rsa[o.ad_group_ad_operation.create.ad_group] = 1

    g = [comum.temp_adgroup(CID, i) for i in range(4)]
    assert kw[g[0]] == ["saque anual fgts", "app do fgts"]
    assert kw[g[2]] == ["quanto recebo no saque anual"]
    # negativa do brief em TODOS; a do grupo, só no dele
    assert all("concurso" in neg[x] for x in g)
    assert neg[g[1]] == ["concurso", "advogado"]
    # ad group sem anúncio não veicula: o RSA é replicado, não compartilhado
    assert set(rsa) == set(g)


def test_keyword_repetida_entre_grupos_fica_so_no_primeiro():
    """Duplicata entre ad groups faz a campanha competir consigo mesma."""
    b = _brief(keywords=[], sub_intencoes=[
        SubIntencao("ACESSO", ["saque anual fgts"]),
        SubIntencao("VALOR", ["saque anual fgts", "quanto recebo"]),
    ])
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()
    textos = [o.ad_group_criterion_operation.create.keyword.text
              for o in _por_tipo(ops, "ad_group_criterion_operation")
              if not o.ad_group_criterion_operation.create.negative]
    assert textos.count("saque anual fgts") == 1
    assert any("já está em 'ACESSO'" in a.motivo for a in r.achados)


def test_toda_referencia_a_ad_group_existe_no_mesmo_mutate():
    """A atomicidade em forma verificável: nada aponta para fora do grafo."""
    ops, _ = search.construir(CID, _brief_4_grupos(), login_customer_id="x")
    criados = {g.resource_name for g in _adgroups(ops)}
    referencias = {
        o.ad_group_criterion_operation.create.ad_group
        for o in _por_tipo(ops, "ad_group_criterion_operation")
    } | {
        o.ad_group_ad_operation.create.ad_group
        for o in _por_tipo(ops, "ad_group_ad_operation")
    }
    assert referencias <= criados
    # e os assets continuam na faixa deles, longe da dos ad groups
    ids_asset = [int(o.asset_operation.create.resource_name.rsplit("/", 1)[1])
                 for o in _por_tipo(ops, "asset_operation")]
    assert ids_asset and max(ids_asset) <= comum.T_ASSET_BASE


def test_nome_longo_preserva_o_carimbo_em_vez_do_rotulo():
    """Truncar pelo fim comeria o carimbo, que é o que desempata entre rodadas."""
    b = _brief(keywords=[], sub_intencoes=[SubIntencao("A" * 400, ["kw uma"])])
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()
    nome = _adgroups(ops)[0].name
    assert len(nome) == 255
    assert re.fullmatch(r"A+_\d{8}_\d{6}", nome)


def test_nomes_que_colidem_depois_da_truncagem_viram_erro():
    """Um rótulo comprido não pode derrubar um mutate atômico inteiro."""
    b = _brief(keywords=[], sub_intencoes=[
        SubIntencao("X" * 239 + "UM", ["kw uma"]),
        SubIntencao("X" * 239 + "DOIS", ["kw duas"]),
    ])
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert not r.ok
    assert any("DUPLICATE_ADGROUP_NAME" in a.motivo for a in r.erros), r.resumo()
    assert ops == []


def test_mais_grupos_que_a_faixa_comporta_e_erro_e_nao_payload():
    subs = [SubIntencao(f"G{i}", [f"kw numero {i}"])
            for i in range(comum.T_ADGROUP_MAX + 1)]
    ops, r = search.construir(CID, _brief(keywords=[], sub_intencoes=subs),
                              login_customer_id="x")
    assert not r.ok
    assert ops == []


# ── política: o buraco do pt-BR, reproduzido e fechado ──────────────────────


def test_o_validador_antigo_deixava_o_espanhol_passar():
    """Reproduz o defeito ANTES de provar que ele fechou.

    `checar_politica` de `validacao.py` compara com uma lista pt-BR. O análogo
    exato em espanhol de um termo proibido não está nela — então a copy passa
    com zero achados e o runner diz "ok". É por isso que este teste existe:
    sem ele, o teste seguinte não prova nada.
    """
    r = validacao.Resultado()
    validacao.checar_politica("Anticipo de tu dinero hoy", "headline_rsa", r)
    assert r.achados == []


def test_o_construtor_novo_barra_o_mesmo_texto_em_espanhol():
    b = _brief(
        pais="MX", idioma="es", vertical="informativo",
        copy=_copy(headlines=["Anticipo de tu dinero hoy", "Reglas del retiro",
                              "Quien tiene derecho", "La tabla oficial"]),
    )
    _, r = search.construir(CID, b, login_customer_id="x")
    assert not r.ok
    assert any("15188216" in a.motivo for a in r.erros), r.resumo()


def test_a_vertical_decide_se_o_termo_e_erro_ou_aviso():
    """O critério que substituiu a blocklist: o PAPEL DO SITE, não a palavra.

    A mesma palavra é deturpação num portal que só explica e produto REGULADO
    em quem de fato empresta. `limites.yaml` não sabia dessa diferença: proibia
    "antecipação" nos dois casos.
    """
    hl = ["Antecipacao do saque anual", "Regras de 2026", "Quem tem direito",
          "A tabela oficial por faixa"]
    _, informativo = search.construir(
        CID, _brief(vertical="informativo", copy=_copy(headlines=hl)),
        login_customer_id="x")
    _, financeiro = search.construir(
        CID, _brief(vertical="financeiro", copy=_copy(headlines=hl),
                    certificacoes={"verificacao_servicos_financeiros"}),
        login_customer_id="x")
    assert not informativo.ok
    assert financeiro.ok, financeiro.resumo()
    assert any("15188216" in a.motivo for a in financeiro.achados)


def test_habilitacao_barra_vertical_financeira_sem_certificacao():
    """Portão binário: sem certificação declarada, não sobe. Sem escotilha."""
    _, sem = search.construir(CID, _brief(pais="MX", idioma="es",
                                          vertical="financeiro"),
                              login_customer_id="x")
    assert not sem.ok
    assert any(a.campo == "conta" for a in sem.erros), sem.resumo()

    _, com = search.construir(
        CID, _brief(pais="MX", idioma="es", vertical="financeiro",
                    certificacoes={"verificacao_servicos_financeiros"}),
        login_customer_id="x")
    assert com.ok, com.resumo()


def test_idioma_sem_regra_semantica_avisa_que_esta_cego():
    """Falso negativo silencioso é pior que reprovar."""
    _, r = search.construir(CID, _brief(pais="DK", idioma="da"),
                            login_customer_id="x")
    assert any(a.campo == "politica" and "NÃO são verificados" in a.motivo
               for a in r.achados), r.resumo()


def test_caixa_alta_e_aviso_porque_sigla_nao_se_distingue_de_grito():
    """`CCFGTS` é sigla legítima e o `validate_only` aceita a mesma descrição."""
    b = _brief(copy=_copy(descriptions=[
        "Conteudo apoiado na Lei 8.036/90 e na Resolucao CCFGTS 1.130/2025.",
        "Portal informativo com a tabela legal por faixa etaria.",
    ]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()
    assert any("14848295" in a.motivo for a in r.achados)


def test_a_lista_de_palavras_morta_nao_voltou():
    """"crédito" aparece 54× nos 6.651 aprovados e em nenhum punido."""
    b = _brief(copy=_copy(headlines=["Credito do trabalhador", "Regras de 2026",
                                     "Quem tem direito", "A tabela oficial"]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()


# ── forma: os limites numéricos que sobreviveram ────────────────────────────


def test_limite_de_caractere_continua_valendo():
    b = _brief(copy=_copy(headlines=["Este headline tem trinta e um c",
                                     "Regras de 2026", "Quem tem direito",
                                     "A tabela oficial"]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert any("chars > limite 30" in a.motivo for a in r.erros), r.resumo()


def test_dki_conta_pelo_fallback_como_o_google_conta():
    """'{KeyWord:Saque Anual} 2026' são 16 caracteres, não 36."""
    b = _brief(copy=_copy(headlines=["{KeyWord:Saque Anual} 2026", "Regras de 2026",
                                     "Quem tem direito", "A tabela oficial"]))
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()
    rsa = _por_tipo(ops, "ad_group_ad_operation")[0].ad_group_ad_operation.create
    assert rsa.ad.responsive_search_ad.headlines[0].text == "{KeyWord:Saque Anual} 2026"


def test_dki_truncado_continua_sendo_erro():
    b = _brief(copy=_copy(headlines=["{KeyWord:Saque", "Regras de 2026",
                                     "Quem tem direito", "A tabela oficial"]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert any("DKI truncada" in a.motivo for a in r.erros)


def test_dki_e_recusado_fora_do_headline():
    b = _brief(copy=_copy(callouts=["{KeyWord:Saque Anual}", "Fontes oficiais"]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert any("DKI não é permitido" in a.motivo for a in r.erros)


def test_header_de_snippet_fora_do_pt_avisa_em_vez_de_chutar():
    """`limites.yaml` só tem a linha pt-BR da tabela oficial de headers."""
    from volc_ads.campanha.brief import Snippet
    b = _brief(pais="MX", idioma="es",
               copy=_copy(snippet=Snippet("Tipos", ["Uno", "Dos", "Tres"])))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert any(a.campo == "snippet_header" and "structured_snippets.md" in a.motivo
               for a in r.achados)
    assert not any(a.campo == "snippet_header" for a in r.erros)


def test_replace_no_brief_continua_funcionando():
    """`copy/provar.py` monta o brief com `dataclasses.replace` — não quebre."""
    b = dataclasses.replace(_brief(), copy=_copy(callouts=["Um callout", "Outro"]))
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok and ops


# ── COMO A CAMPANHA NASCE ───────────────────────────────────────────────────
#
# A estratégia de lance deixou de ser decisão implícita do engine e virou
# escolha do operador (docs/SPEC-FRONT-CAMPANHAS.md §1). O que estes testes
# protegem é a consequência prática: sob `maximize_conversions` a API aceita o
# `cpc_bid_micros` do ad group e o IGNORA na veiculação; sob `manual_cpc` ele é
# o lance de verdade. Trocar um pelo outro faz o operador gastar achando que
# controla o leilão.

def _estrategia_do_payload(ops):
    """Qual `oneof` de lance a campanha declarou no payload."""
    for o in ops:
        if o._pb.WhichOneof("operation") == "campaign_operation":
            camp = o.campaign_operation.create
            return camp._pb.WhichOneof("campaign_bidding_strategy")
    raise AssertionError("nenhuma operação de campanha no payload")


def test_nasce_em_manual_cpc_por_padrao():
    """O padrão da casa: quem não escolhe, nasce manual."""
    ops, r = search.construir(CID, _brief(), login_customer_id="x")
    assert r.ok
    assert _estrategia_do_payload(ops) == "manual_cpc"


def test_manual_cpc_desliga_o_ecpc():
    """eCPC é lance automático disfarçado — quem pediu manual quer o controle."""
    ops, _ = search.construir(CID, _brief(), login_customer_id="x")
    camp = next(o.campaign_operation.create for o in ops
                if o._pb.WhichOneof("operation") == "campaign_operation")
    assert camp.manual_cpc.enhanced_cpc_enabled is False


def test_maximize_conversions_continua_disponivel():
    """A graduação precisa do outro lado, e ele não pode ter sumido."""
    b = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSIONS")
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok
    assert _estrategia_do_payload(ops) == "maximize_conversions"


def test_o_lance_do_operador_chega_ao_ad_group_em_micros():
    """Sob manual, o número digitado no cockpit É a régua do leilão."""
    b = dataclasses.replace(_brief(), cpc_inicial=0.38)
    ops, _ = search.construir(CID, b, login_customer_id="x")
    ag = next(o.ad_group_operation.create for o in ops
              if o._pb.WhichOneof("operation") == "ad_group_operation")
    assert ag.cpc_bid_micros == 380_000


def test_broad_com_manual_cpc_e_recusado():
    """Broad sem Smart Bidding não tem sinal de leilão que filtre a consulta.

    Recusar no `Brief` é de graça; descobrir isso pela fatura não é.
    """
    with pytest.raises(ValueError, match="BROAD"):
        dataclasses.replace(_brief(), match_type="BROAD")


def test_broad_e_liberado_na_graduacao():
    """O que a doutrina promete: broad é recompensa da graduação."""
    b = dataclasses.replace(_brief(), match_type="BROAD",
                            estrategia_lance="MAXIMIZE_CONVERSIONS")
    ops, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok
    assert _estrategia_do_payload(ops) == "maximize_conversions"


def test_estrategia_desconhecida_e_recusada():
    with pytest.raises(ValueError, match="estrategia_lance"):
        dataclasses.replace(_brief(), estrategia_lance="TURBO")


def test_campanha_continua_nascendo_pausada_nas_duas_estrategias():
    """A trava mais importante do engine não pode depender da estratégia."""
    for est in ("MANUAL_CPC", "MAXIMIZE_CONVERSIONS"):
        b = dataclasses.replace(_brief(), estrategia_lance=est)
        ops, _ = search.construir(CID, b, login_customer_id="x")
        camp = next(o.campaign_operation.create for o in ops
                    if o._pb.WhichOneof("operation") == "campaign_operation")
        assert camp.status.name == "PAUSED", est


# ── caixa alternada: marca não é grito ──────────────────────────────────────
#
# A regra contava TRANSIÇÕES de caixa e disparava com `>= 2`. Um único capital
# interno já produz duas (entra e sai), então toda palavra CamelCase reprovava.
# Medido no card 74 em 19/08/2026: `PagBank`, `InfiniteSmart`, `Point Pro 3` e
# `T3 Smart` barravam a campanha — 11 achados, todos falso positivo. A política
# 14848295 mira grito gráfico, que tem VÁRIOS blocos de maiúscula.

@pytest.mark.parametrize("marca", [
    "PagBank ou Ton: Como Escolher?",
    "InfiniteSmart e a Menor Taxa",
    "Compare a Point Pro 3 hoje",
    "Taxa da T3 Smart por venda",
    "Use o iPhone para vender",
    "Consulte o CadUnico atualizado",
])
def test_marca_camelcase_nao_e_caixa_alternada(marca):
    """Um bloco de maiúscula no miolo é marca. Reprovar isso barra o anúncio."""
    b = _brief(copy=_copy(headlines=[marca, "Segunda linha comum", "Terceira comum"]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert not any("14848295" in a.motivo for a in r.erros), \
        f"{marca!r} reprovado como caixa alternada: {r.resumo()}"


@pytest.mark.parametrize("grito", [
    "CoMpRe AgOrA mesmo",
    "FrEeMoNeY para todos",
    "OfErTa ImPeRdIvEl hoje",
])
def test_grito_grafico_continua_reprovado(grito):
    """Dois ou mais blocos de maiúscula é gimmick — a política tem que morder."""
    b = _brief(copy=_copy(headlines=[grito, "Segunda linha comum", "Terceira comum"]))
    _, r = search.construir(CID, b, login_customer_id="x")
    assert any("14848295" in a.motivo for a in r.achados), \
        f"{grito!r} passou como texto normal"


# ── a taxonomia do nome da campanha ─────────────────────────────────────────
#
# `BR - {carimbo} / {termo} / {URL}` é o formato que a operação já usava no
# flow n8n que criou as campanhas de fevereiro. Cada barra separa uma pergunta
# que se faz olhando a lista: ONDE compro, O QUE compro, PARA ONDE mando.
#
# O engine montava `FORGE BR 20260819_123824 Maquininha de Cartão` — quatro
# campos com espaço e sem a URL. Espaço não separa: não dá para saber onde o
# carimbo termina e o termo começa.

def test_nome_segue_a_taxonomia_da_casa():

    b = dataclasses.replace(_brief(), nicho="Maquininha de Cartão",
                            url_final="https://creditoup.com.br/r/maquininha/")
    nome = conteudo.nome_da_campanha(b, "20260819_123824")
    assert nome == ("BR - 20260819_123824 / Maquininha de Cartão / "
                    "https://creditoup.com.br/r/maquininha/"), nome


def test_o_prefixo_padrao_nao_polui_o_nome():
    """`FORGE` existia por falta de formato, não por decisão."""

    assert not conteudo.nome_da_campanha(_brief(), "20260819_123824").startswith("FORGE")


def test_prefixo_declarado_pelo_operador_entra_na_frente():
    """Quem quer marcar um lote de teste não perde o recurso."""

    b = dataclasses.replace(_brief(), prefixo_nome="CANARIO")
    assert conteudo.nome_da_campanha(b, "20260819_123824").startswith("CANARIO BR - ")


def test_o_nome_chega_ao_payload():
    """Não basta a função certa: o que vale é o que vai para a API."""
    ops, _ = search.construir(CID, _brief(), login_customer_id="x")
    camp = next(o.campaign_operation.create for o in ops
                if o._pb.WhichOneof("operation") == "campaign_operation")
    assert camp.name.startswith("BR - ")
    assert " / " in camp.name


def test_mesmo_carimbo_reconstroi_o_mesmo_nome_e_grafo():
    """Provar e subir podem montar em instantes diferentes sem mudar o plano."""
    carimbo = "20260828_120000"
    brief = dataclasses.replace(_brief(), carimbo_nome=carimbo)

    ops_prova, resultado_prova = search.construir(
        CID, brief, login_customer_id="x",
    )
    ops_subida, resultado_subida = search.construir(
        CID, brief, login_customer_id="x",
    )

    assert resultado_prova.ok and resultado_subida.ok
    identidade_prova = tuple(
        op._pb.SerializeToString(deterministic=True) for op in ops_prova
    )
    identidade_subida = tuple(
        op._pb.SerializeToString(deterministic=True) for op in ops_subida
    )
    assert identidade_subida == identidade_prova

    nomes = [
        op.campaign_operation.create.name
        for op in ops_prova
        if op._pb.WhichOneof("operation") == "campaign_operation"
    ]
    assert nomes == [
        "BR - 20260828_120000 / Saque Anual / "
        "https://creditoup.com.br/r/saque-anual/"
    ]


# ═══════════════════════════════════════════════════════════════════════════
# A REDE DE PESQUISA É DECISÃO, NÃO DEFAULT — 01/09/2026
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ `comum.py:169` ligava `target_search_network = True` como literal. Search
# Partners é um inventário DIFERENTE do Google Search: outros sites, outro
# comportamento de consulta, outro CPC. Ele estava ligado em toda campanha
# Search da casa sem o operador escolher, sem aparecer no plano aprovado e sem
# entrar em nenhuma tela. A matriz de cobertura v25 já registrava isso como
# "efeito invisível".
#
# O defeito não é o valor `True` — é ele não ser uma decisão de ninguém.


def teste_rede_declarada_chega_ao_payload() -> None:
    b = _brief(rede=RedeDePesquisa(google_search=True, search_partners=False,
                                   display_expansion=False))
    ops, _ = search.construir(CID, b, login_customer_id="x")
    camp = next(o.campaign_operation.create for o in ops
                if o._pb.WhichOneof("operation") == "campaign_operation")
    assert camp.network_settings.target_google_search is True
    assert camp.network_settings.target_search_network is False
    assert camp.network_settings.target_content_network is False


def teste_parceiros_ligados_exige_declaracao() -> None:
    """Ligar parceiros continua possível — mas agora alguém precisa ter dito."""
    b = _brief(rede=RedeDePesquisa(google_search=True, search_partners=True,
                                   display_expansion=False))
    ops, _ = search.construir(CID, b, login_customer_id="x")
    camp = next(o.campaign_operation.create for o in ops
                if o._pb.WhichOneof("operation") == "campaign_operation")
    assert camp.network_settings.target_search_network is True


def teste_rede_ausente_usa_o_legado_nomeado_e_nao_um_literal_solto() -> None:
    """Compatibilidade preservada, e com nome: `REDE_LEGADA_SEARCH`.

    Campanhas antigas não podem mudar de comportamento em silêncio. O que muda
    é que o estado legado deixou de ser um literal perdido no builder e passou
    a ser uma constante que se pode citar, testar e aposentar.
    """
    b = _brief()
    assert b.rede is None
    ops, _ = search.construir(CID, b, login_customer_id="x")
    camp = next(o.campaign_operation.create for o in ops
                if o._pb.WhichOneof("operation") == "campaign_operation")
    assert camp.network_settings.target_google_search is REDE_LEGADA_SEARCH.google_search
    assert camp.network_settings.target_search_network is REDE_LEGADA_SEARCH.search_partners
    assert REDE_LEGADA_SEARCH.search_partners is True, (
        "o legado tinha parceiros ON; mudar isso aqui alteraria campanhas "
        "antigas em silêncio, que é o oposto do conserto")


def teste_google_search_desligado_e_recusado_em_search() -> None:
    """Uma campanha Search sem Google Search não é uma campanha Search."""
    with pytest.raises(ValueError):
        RedeDePesquisa(google_search=False, search_partners=True,
                       display_expansion=False)


def teste_mudar_a_rede_muda_a_impressao_do_payload() -> None:
    """⚠️ O selo tem de invalidar: rede diferente é plano diferente.

    Sem isto, um plano aprovado com parceiros OFF poderia subir com eles ON e o
    selo continuaria conferindo — a autorização humana passaria a cobrir algo
    que o humano não viu.
    """
    from volc_ads import subir as sb

    sem, _ = search.construir(CID, _brief(rede=RedeDePesquisa(True, False, False)),
                              login_customer_id="x")
    com, _ = search.construir(CID, _brief(rede=RedeDePesquisa(True, True, False)),
                              login_customer_id="x")
    assert sb._impressao(sem) != sb._impressao(com)
