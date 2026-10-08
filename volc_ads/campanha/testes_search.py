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


def test_o_construtor_novo_enxerga_o_mesmo_texto_em_espanhol():
    """⚠️ Alterado em 30/09/2026 (B6). Era `..._barra_o_mesmo_texto_...` e exigia
    ERRO. O inventário da frente A (ADS-08, classe C, converter_em_aviso) tirou o
    bloqueio por palavra: o risco é o sujeito (o site executa?), não o termo, e
    quem decide é o juiz de sentido. O que este teste protege continua: o
    validador NÃO é cego ao espanhol — o termo é localizado, como aviso."""
    b = _brief(
        pais="MX", idioma="es", vertical="informativo",
        copy=_copy(headlines=["Anticipo de tu dinero hoy", "Reglas del retiro",
                              "Quien tiene derecho", "La tabla oficial"]),
    )
    _, r = search.construir(CID, b, login_customer_id="x")
    assert r.ok, r.resumo()
    assert any("15188216" in a.motivo for a in r.achados), r.resumo()


def test_a_vertical_decide_qual_regra_marca_o_termo():
    """O critério que substituiu a blocklist: o PAPEL DO SITE, não a palavra.

    ⚠️ Alterado em 30/09/2026 (B6). Era `..._se_o_termo_e_erro_ou_aviso` e exigia
    que o informativo NÃO subisse. Pelo inventário da frente A (ADS-08) a palavra
    num portal informativo é LOCALIZADOR — marca "linguagem de prestador" para o
    juiz de sentido — e não reprova sozinha. A vertical continua decidindo QUAL
    regra marca: deturpação no portal que explica, divulgação obrigatória em
    quem empresta.
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
    assert informativo.ok, informativo.resumo()
    assert any("linguagem de prestador" in a.motivo for a in informativo.achados)
    assert not any("exigem divulga" in a.motivo for a in informativo.achados)
    assert financeiro.ok, financeiro.resumo()
    assert any("15188216" in a.motivo and "exigem divulga" in a.motivo
               for a in financeiro.achados)


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


def test_search_continua_nascendo_com_o_ad_group_ligado():
    """REGRESSÃO T03: parametrizar o status do ad group NÃO pode tocar Search.

    `comum.op_adgroup` ganhou um parâmetro `status` para que Display possa
    nascer PAUSED por objeto. O default é COMPATIBILIDADE: se ele mudasse, o
    payload provado do único canal com canário aceito mudaria junto, e o selo
    de tudo que já subiu deixaria de descrever o que sobe hoje.
    """
    ops, r = search.construir(CID, _brief(), login_customer_id="x")
    assert r.ok, _erros(r)
    grupos = _adgroups(ops)
    assert grupos, "Search precisa continuar montando ad group"
    for ag in grupos:
        assert ag.status.name == "ENABLED"


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DE SEARCH (v25.2) — 08/10/2026
# ═══════════════════════════════════════════════════════════════════════════
#
# `search_config.ConfiguracaoSearch` carrega o que o `Brief` ainda não tem:
# cinco estratégias, rede com Display expansion, AI Max inteira, fixação e
# path do RSA, programação, dispositivo, geo-tipo, datas e meta de conversão.
# Cada bloco abaixo prova o payload contra o proto real da v25 e prova que a
# combinação inválida morre ANTES do mutate.

from datetime import date, timedelta  # noqa: E402

from volc_ads.campanha import search_config as sc  # noqa: E402

REDE_SO_GOOGLE = sc.RedeSearch(google_search=True, parceiros=False,
                               display_expansion=False)
FUTURO = (date.today() + timedelta(days=30)).isoformat()
FUTURO_FIM = (date.today() + timedelta(days=90)).isoformat()


def _cfg(**troca) -> sc.ConfiguracaoSearch:
    base = dict(rede=REDE_SO_GOOGLE)
    base.update(troca)
    return sc.ConfiguracaoSearch(**base)


def _montar(brief=None, **kw):
    return search.construir(CID, brief or _brief(), login_customer_id="x", **kw)


def _camp(ops):
    return next(o.campaign_operation.create for o in ops
                if o._pb.WhichOneof("operation") == "campaign_operation")


def _criterios_de_campanha(ops, ramo: str):
    saida = []
    for o in _por_tipo(ops, "campaign_criterion_operation"):
        cc = o.campaign_criterion_operation.create
        if cc._pb.WhichOneof("criterion") == ramo:
            saida.append(cc)
    return saida


def _mensagens(r) -> str:
    return " | ".join(f"{a.campo}: {a.motivo}" for a in r.erros)


# ── o vocabulário fechado é o da API ────────────────────────────────────────


def _enum(nome: str) -> set[str]:
    return {v.name for v in getattr(_Enums(), nome)} - {"UNSPECIFIED", "UNKNOWN"}


@pytest.mark.parametrize("tupla, enum_v25", [
    (sc.LOCAIS_DE_IMPRESSAO, "TargetImpressionShareLocationEnum"),
    (sc.GEO_POSITIVO, "PositiveGeoTargetTypeEnum"),
    (sc.GEO_NEGATIVO, "NegativeGeoTargetTypeEnum"),
    (sc.DIAS, "DayOfWeekEnum"),
    (tuple(sc.MINUTOS.values()), "MinuteOfHourEnum"),
    (sc.DISPOSITIVOS, "DeviceEnum"),
    (sc.POSICOES_TITULO + sc.POSICOES_DESCRICAO, "ServedAssetFieldTypeEnum"),
    (sc.CATEGORIAS_DE_CONVERSAO, "ConversionActionCategoryEnum"),
    (sc.ORIGENS_DE_CONVERSAO, "ConversionOriginEnum"),
])
def test_cada_tupla_fechada_e_subconjunto_do_enum_v25(tupla, enum_v25):
    """`search_config` é stdlib pura; este teste é o que a amarra à API real."""
    assert set(tupla) <= _enum(enum_v25), set(tupla) - _enum(enum_v25)


def test_lances_permitidos_espelha_as_estrategias_do_contrato():
    assert search.LANCES_PERMITIDOS == sc.ESTRATEGIAS
    assert "configuracao" in search.OPCOES


# ── 1. LANCE ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lance, ramo, campos", [
    (sc.LanceSearch("MANUAL_CPC"), "manual_cpc", {}),
    (sc.LanceSearch("TARGET_SPEND"), "target_spend", {}),
    (sc.LanceSearch("TARGET_SPEND", teto_cpc=0.45), "target_spend",
     {"cpc_bid_ceiling_micros": 450_000}),
    (sc.LanceSearch("MAXIMIZE_CONVERSIONS"), "maximize_conversions",
     {"target_cpa_micros": 0}),
    (sc.LanceSearch("MAXIMIZE_CONVERSIONS", target_cpa=2.5), "maximize_conversions",
     {"target_cpa_micros": 2_500_000}),
    (sc.LanceSearch("MAXIMIZE_CONVERSION_VALUE"), "maximize_conversion_value",
     {"target_roas": 0.0}),
    (sc.LanceSearch("MAXIMIZE_CONVERSION_VALUE", target_roas=4.0),
     "maximize_conversion_value", {"target_roas": 4.0}),
    (sc.LanceSearch("TARGET_IMPRESSION_SHARE", teto_cpc=1.2,
                    local_impressao="TOP_OF_PAGE", fracao_impressao=0.65),
     "target_impression_share",
     {"location_fraction_micros": 650_000, "cpc_bid_ceiling_micros": 1_200_000}),
])
def test_cada_estrategia_vira_o_ramo_certo_do_oneof(lance, ramo, campos):
    b = _brief(match_type="PHRASE")
    ops, r = _montar(b, configuracao=_cfg(lance=lance))
    assert r.ok, _mensagens(r)
    camp = _camp(ops)
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == ramo
    for campo, valor in campos.items():
        assert getattr(getattr(camp, ramo), campo) == valor
    assert camp.status.name == "PAUSED"


def test_tis_leva_o_local_como_enum():
    lance = sc.LanceSearch("TARGET_IMPRESSION_SHARE", teto_cpc=1.0,
                           local_impressao="ABSOLUTE_TOP_OF_PAGE", fracao_impressao=1)
    ops, r = _montar(configuracao=_cfg(lance=lance))
    assert r.ok
    assert _camp(ops).target_impression_share.location.name == "ABSOLUTE_TOP_OF_PAGE"


def test_maxconv_sem_meta_e_o_ramo_vazio_e_nao_um_zero_escrito():
    """A semântica unificada com Demand Gen e PMax — e o selo antigo vale.

    `target_cpa_micros` é escalar proto3 sem presença: `= 0` e `SetInParent`
    serializam igual. A diferença é de CÓDIGO (ninguém "escolhe zero"), e o
    teste prova que unificar não mudou um byte do payload legado.
    """
    legado = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSIONS",
                                 carimbo_nome="20261008_120000")
    ops, _ = _montar(legado)
    camp = _camp(ops)
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"
    assert not camp.maximize_conversions._pb.ListFields()
    ref = comum.op_campanha(_cliente_sem_rede(), CID, legado,
                            conteudo.nome_da_campanha(legado, "20261008_120000"), "SEARCH")
    assert (camp._pb.SerializeToString(deterministic=True)
            == ref.campaign_operation.create._pb.SerializeToString(deterministic=True))


@pytest.mark.parametrize("kw", [
    {}, {"estrategia_lance": "MAXIMIZE_CONVERSIONS"},
    {"estrategia_lance": "MAXIMIZE_CONVERSIONS", "tcpa": 3.5}, {"tcpa": 2.0},
])
def test_sem_configuracao_a_campanha_e_byte_a_byte_a_de_comum(kw):
    """O selo de tudo que já subiu depende disto."""
    b = dataclasses.replace(_brief(), carimbo_nome="20261008_120000", **kw)
    ops, r = _montar(b)
    assert r.ok
    ref = comum.op_campanha(_cliente_sem_rede(), CID, b,
                            conteudo.nome_da_campanha(b, "20261008_120000"), "SEARCH")
    assert (_camp(ops)._pb.SerializeToString(deterministic=True)
            == ref.campaign_operation.create._pb.SerializeToString(deterministic=True))


def test_maximize_conversion_value_pelo_brief_agora_monta_em_search():
    b = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSION_VALUE",
                            target_roas=3.0)
    ops, r = _montar(b)
    assert r.ok, _mensagens(r)
    camp = _camp(ops)
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversion_value"
    assert camp.maximize_conversion_value.target_roas == 3.0
    assert any("valor" in a.motivo for a in r.achados if a.severidade == "aviso")


@pytest.mark.parametrize("kw, trecho", [
    ({"estrategia": "TARGET_CPA"}, "não existe"),
    ({"estrategia": "TARGET_SPEND", "target_cpa": 2.0}, "target_cpa só existe"),
    ({"estrategia": "MAXIMIZE_CONVERSIONS", "target_roas": 4.0}, "target_roas só existe"),
    ({"estrategia": "MAXIMIZE_CONVERSIONS", "teto_cpc": 1.0}, "portfólio"),
    ({"estrategia": "MAXIMIZE_CONVERSION_VALUE", "teto_cpc": 1.0}, "portfólio"),
    ({"estrategia": "MANUAL_CPC", "teto_cpc": 1.0}, "não se aplica"),
    ({"estrategia": "MAXIMIZE_CONVERSIONS", "target_cpa": 0}, "positivo"),
    ({"estrategia": "MAXIMIZE_CONVERSION_VALUE", "target_roas": 0}, "fora de"),
    ({"estrategia": "MAXIMIZE_CONVERSION_VALUE", "target_roas": 1500.0}, "fora de"),
    ({"estrategia": "TARGET_IMPRESSION_SHARE", "local_impressao": "TOP_OF_PAGE",
      "fracao_impressao": 0.5}, "exige teto_cpc"),
    ({"estrategia": "TARGET_IMPRESSION_SHARE", "teto_cpc": 1.0,
      "fracao_impressao": 0.5}, "local_impressao"),
    ({"estrategia": "TARGET_IMPRESSION_SHARE", "teto_cpc": 1.0,
      "local_impressao": "TOP_OF_PAGE"}, "fracao_impressao"),
    ({"estrategia": "TARGET_IMPRESSION_SHARE", "teto_cpc": 1.0,
      "local_impressao": "TOP_OF_PAGE", "fracao_impressao": 1.2}, "fracao_impressao"),
    ({"estrategia": "TARGET_SPEND", "local_impressao": "TOP_OF_PAGE"}, "só existem"),
])
def test_combinacao_invalida_de_lance_morre_na_forma(kw, trecho):
    with pytest.raises(ValueError, match=trecho):
        sc.LanceSearch(**kw)


def test_estrategia_do_brief_divergente_da_configuracao_e_erro():
    b = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSIONS")
    _, r = _montar(b, configuracao=_cfg(lance=sc.LanceSearch("TARGET_SPEND")))
    assert "lugar só" in _mensagens(r)


def test_tcpa_divergente_entre_brief_e_configuracao_e_erro():
    b = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSIONS", tcpa=3.0)
    lance = sc.LanceSearch("MAXIMIZE_CONVERSIONS", target_cpa=5.0)
    _, r = _montar(b, configuracao=_cfg(lance=lance))
    assert "divergem no tCPA" in _mensagens(r)


def test_tcpa_de_grupo_fora_de_maxconv_e_erro_e_nao_decoracao():
    subs = [SubIntencao("ACESSO", ["saque anual fgts"], tcpa=3.0),
            SubIntencao("VALOR", ["quanto recebo no saque anual"])]
    b = _brief(keywords=[], sub_intencoes=subs)
    _, r = _montar(b, configuracao=_cfg(lance=sc.LanceSearch("TARGET_SPEND")))
    assert "tCPA não existe em TARGET_SPEND" in _mensagens(r)


def test_campanha_nasce_pausada_em_toda_estrategia_da_configuracao():
    lances = [sc.LanceSearch("MANUAL_CPC"), sc.LanceSearch("TARGET_SPEND"),
              sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
              sc.LanceSearch("MAXIMIZE_CONVERSION_VALUE"),
              sc.LanceSearch("TARGET_IMPRESSION_SHARE", teto_cpc=1.0,
                             local_impressao="TOP_OF_PAGE", fracao_impressao=0.5)]
    for lance in lances:
        ops, r = _montar(configuracao=_cfg(lance=lance))
        assert r.ok, (lance, _mensagens(r))
        assert _camp(ops).status.name == "PAUSED", lance


# ── 2. REDE ─────────────────────────────────────────────────────────────────


def test_com_configuracao_a_rede_deixa_de_ter_default():
    """O legado com parceiros ligados não vale para quem declara configuração."""
    _, r = _montar(configuracao=sc.ConfiguracaoSearch())
    assert "rede é decisão obrigatória" in _mensagens(r)


def test_rede_do_brief_satisfaz_a_configuracao():
    b = _brief(rede=RedeDePesquisa(True, False, False))
    ops, r = _montar(b, configuracao=sc.ConfiguracaoSearch())
    assert r.ok, _mensagens(r)
    assert _camp(ops).network_settings.target_search_network is False


def test_rede_divergente_entre_brief_e_configuracao_e_erro():
    b = _brief(rede=RedeDePesquisa(True, True, False))
    _, r = _montar(b, configuracao=_cfg())
    assert "divergente" in " ".join(a.valor for a in r.erros)


def test_display_expansion_declarada_chega_ao_payload_com_aviso():
    rede = sc.RedeSearch(google_search=True, parceiros=True, display_expansion=True)
    ops, r = _montar(configuracao=_cfg(rede=rede))
    assert r.ok
    ns = _camp(ops).network_settings
    assert (ns.target_google_search, ns.target_search_network,
            ns.target_content_network) == (True, True, True)
    assert any(a.campo == "rede" for a in r.achados if a.severidade == "aviso")


def test_rede_search_sem_google_ou_sem_bool_morre_na_forma():
    with pytest.raises(ValueError, match="não é uma campanha Search"):
        sc.RedeSearch(google_search=False, parceiros=False, display_expansion=False)
    with pytest.raises(ValueError, match="bool declarado"):
        sc.RedeSearch(google_search=True, parceiros=None, display_expansion=False)


# ── 3. AI MAX ───────────────────────────────────────────────────────────────

LISTA_A = f"customers/{CID}/sharedSets/111"
LISTA_B = f"customers/{CID}/sharedSets/222"


def _aimax(**troca) -> sc.AiMaxSearch:
    base = dict(correspondencia_de_termos=True, personalizacao_de_texto=True,
                expansao_de_url_final=True)
    base.update(troca)
    return sc.AiMaxSearch(**base)


def _automacoes(camp) -> dict[str, str]:
    return {s.asset_automation_type.name: s.asset_automation_status.name
            for s in camp.asset_automation_settings}


def test_ai_max_completa_chega_inteira_ao_payload():
    subs = [SubIntencao("ACESSO", ["saque anual fgts"]),
            SubIntencao("MARCA", ["caixa saque anual"])]
    b = _brief(keywords=[], sub_intencoes=subs)
    aimax = _aimax(grupos_sem_correspondencia=("MARCA",),
                   exclusoes_de_url=("/blog/", "/contato"),
                   listas_de_marca_incluidas=(LISTA_A,),
                   listas_de_marca_excluidas=(LISTA_B,),
                   termos_excluidos=("garantido",),
                   restricoes_de_mensagem=("Nao prometa aprovacao de credito",))
    ops, r = _montar(b, configuracao=_cfg(
        lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"), ai_max=aimax))
    assert r.ok, _mensagens(r)
    camp = _camp(ops)
    assert camp.ai_max_setting.enable_ai_max is True
    assert _automacoes(camp) == {
        "TEXT_ASSET_AUTOMATION": "OPTED_IN",
        "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION": "OPTED_IN"}
    assert list(camp.text_guidelines.term_exclusions) == ["garantido"]
    rest = camp.text_guidelines.messaging_restrictions[0]
    assert rest.restriction_type.name == "RESTRICTION_BASED_EXCLUSION"
    grupos = {g.name.split("_")[0]: g.ai_max_ad_group_setting.disable_search_term_matching
              for g in _adgroups(ops)}
    assert grupos == {"ACESSO": False, "MARCA": True}
    paginas = _criterios_de_campanha(ops, "webpage")
    assert [p.webpage.conditions[0].argument for p in paginas] == ["/blog/", "/contato"]
    assert all(p.negative for p in paginas)
    assert all(p.webpage.conditions[0].operand.name == "URL" for p in paginas)
    marcas = {cc.brand_list.shared_set: cc.negative
              for cc in _criterios_de_campanha(ops, "brand_list")}
    assert marcas == {LISTA_A: False, LISTA_B: True}


def test_configuracao_sem_ai_max_desliga_tudo_em_voz_alta():
    """Default remoto não aparece no plano — e já mudou uma vez (ACA)."""
    ops, r = _montar(configuracao=_cfg())
    assert r.ok
    camp = _camp(ops)
    assert camp.ai_max_setting._pb.HasField("enable_ai_max")
    assert camp.ai_max_setting.enable_ai_max is False
    assert set(_automacoes(camp).values()) == {"OPTED_OUT"}
    assert all(not g.ai_max_ad_group_setting._pb.ListFields() for g in _adgroups(ops))


def test_flag_antiga_vira_ai_max_legado_explicito():
    b = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSIONS")
    ops, r = _montar(b, ai_max=True)
    assert r.ok, _mensagens(r)
    camp = _camp(ops)
    assert camp.ai_max_setting.enable_ai_max is True
    assert set(_automacoes(camp).values()) == {"OPTED_OUT"}
    assert [g.ai_max_ad_group_setting.disable_search_term_matching
            for g in _adgroups(ops)] == [False]


def test_brief_ai_max_deixou_de_ser_ignorado_em_search():
    """`brief.ai_max=True` era descartado em silêncio por este construtor."""
    b = dataclasses.replace(_brief(), estrategia_lance="MAXIMIZE_CONVERSIONS",
                            ai_max=True)
    ops, r = _montar(b)
    assert r.ok
    assert _camp(ops).ai_max_setting.enable_ai_max is True


def test_correspondencia_de_termos_com_lance_cego_e_erro():
    """AI Max trata toda keyword como broad: a doutrina do BROAD vale aqui."""
    _, r = _montar(ai_max=True)          # MANUAL_CPC, o padrão da casa
    assert "broad com lance cego" in _mensagens(r)
    _, r = _montar(configuracao=_cfg(lance=sc.LanceSearch("TARGET_SPEND"),
                                     ai_max=_aimax()))
    assert "broad com lance cego" in _mensagens(r)


def test_ai_max_so_com_texto_e_sem_correspondencia_aceita_lance_manual():
    aimax = sc.AiMaxSearch(correspondencia_de_termos=False,
                           personalizacao_de_texto=True, expansao_de_url_final=False)
    ops, r = _montar(configuracao=_cfg(ai_max=aimax))
    assert r.ok, _mensagens(r)
    assert [g.ai_max_ad_group_setting.disable_search_term_matching
            for g in _adgroups(ops)] == [True]


def test_flag_solta_com_configuracao_declarada_e_erro():
    _, r = _montar(ai_max=True, configuracao=_cfg(
        lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS")))
    assert "configuracao.ai_max" in _mensagens(r)


def test_grupo_sem_correspondencia_inexistente_e_erro():
    aimax = _aimax(grupos_sem_correspondencia=("FANTASMA",))
    _, r = _montar(configuracao=_cfg(lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
                                     ai_max=aimax))
    assert "grupo inexistente" in _mensagens(r)


def test_lista_de_marca_de_outra_conta_e_erro():
    aimax = _aimax(listas_de_marca_excluidas=("customers/999/sharedSets/1",))
    _, r = _montar(configuracao=_cfg(lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
                                     ai_max=aimax))
    assert "outra conta" in _mensagens(r)


@pytest.mark.parametrize("kw, trecho", [
    ({"personalizacao_de_texto": False}, "exige personalização"),
    ({"expansao_de_url_final": False, "exclusoes_de_url": ("/blog/",)},
     "não exclui nada"),
    ({"personalizacao_de_texto": False, "expansao_de_url_final": False,
      "termos_excluidos": ("x",)}, "só guiam texto"),
    ({"termos_excluidos": tuple(f"t{i}" for i in range(26))}, "no máximo 25"),
    ({"termos_excluidos": ("x" * 31,)}, "1 a 30"),
    ({"restricoes_de_mensagem": ("y" * 301,)}, "1 a 300"),
    ({"restricoes_de_mensagem": tuple(f"r{i}" for i in range(41))}, "no máximo 40"),
    ({"termos_excluidos": ("Gratis", "gratis")}, "repetido"),
    ({"exclusoes_de_url": ("/a b/",)}, "espaço"),
    ({"listas_de_marca_incluidas": ("sharedSets/1",)}, "resource name"),
    ({"listas_de_marca_incluidas": (LISTA_A,),
      "listas_de_marca_excluidas": (LISTA_A,)}, "incluída E excluída"),
    ({"correspondencia_de_termos": False, "grupos_sem_correspondencia": ("A",)},
     "só faz sentido"),
    ({"correspondencia_de_termos": None}, "bool declarado"),
])
def test_combinacao_invalida_de_ai_max_morre_na_forma(kw, trecho):
    with pytest.raises(ValueError, match=trecho):
        _aimax(**kw)


# ── 4. RSA ──────────────────────────────────────────────────────────────────


def test_fixacao_e_path_chegam_ao_rsa():
    anuncio = sc.AnuncioSearch(path1="saque-anual", path2="regras", fixacoes=(
        sc.Fixacao("Regras do Saque Anual", "HEADLINE_1"),
        sc.Fixacao("Prazos, limites e quem tem direito, com fonte citada.",
                   "DESCRIPTION_1"),
    ))
    ops, r = _montar(configuracao=_cfg(anuncio=anuncio))
    assert r.ok, _mensagens(r)
    rsa = _por_tipo(ops, "ad_group_ad_operation")[0].ad_group_ad_operation.create \
        .ad.responsive_search_ad
    assert (rsa.path1, rsa.path2) == ("saque-anual", "regras")
    pinos = {h.text: h.pinned_field.name for h in rsa.headlines}
    assert pinos["Regras do Saque Anual"] == "HEADLINE_1"
    assert pinos["Quem Tem Direito em 2026"] == "UNSPECIFIED"
    assert rsa.descriptions[0].pinned_field.name == "DESCRIPTION_1"
    assert any(a.campo == "anuncio.fixacoes" for a in r.achados
               if a.severidade == "aviso")


def test_fixacao_de_texto_que_nao_esta_na_copy_e_erro():
    anuncio = sc.AnuncioSearch(fixacoes=(sc.Fixacao("Titulo Inventado", "HEADLINE_1"),))
    _, r = _montar(configuracao=_cfg(anuncio=anuncio))
    assert "não está entre os títulos" in _mensagens(r)


def test_fixar_tudo_numa_posicao_deixa_a_segunda_vazia_e_e_erro():
    titulos = ["Regras do Saque Anual", "Quem Tem Direito em 2026",
               "Tabela Oficial por Faixa", "O Prazo de 90 Dias"]
    anuncio = sc.AnuncioSearch(fixacoes=tuple(sc.Fixacao(t, "HEADLINE_1") for t in titulos))
    _, r = _montar(configuracao=_cfg(anuncio=anuncio))
    assert "HEADLINE_2" in " ".join(a.valor for a in r.erros)


@pytest.mark.parametrize("kw, trecho", [
    ({"path2": "regras"}, "path2 exige path1"),
    ({"path1": "x" * 16}, "máximo 15"),
    ({"path1": "a/b"}, "sem barra"),
    ({"fixacoes": (sc.Fixacao("A", "HEADLINE_1"), sc.Fixacao("A", "HEADLINE_2"))},
     "repetido"),
])
def test_rsa_invalido_morre_na_forma(kw, trecho):
    with pytest.raises(ValueError, match=trecho):
        sc.AnuncioSearch(**kw)


def test_posicao_de_fixacao_inexistente_morre_na_forma():
    with pytest.raises(ValueError, match="posição"):
        sc.Fixacao("A", "HEADLINE_4")


# ── 5. PROGRAMAÇÃO E DISPOSITIVO ────────────────────────────────────────────


def test_programacao_e_dispositivo_chegam_como_criterios_de_campanha():
    cfg = _cfg(programacao=(
        sc.FaixaDeHorario("MONDAY", "08:00", "12:30"),
        sc.FaixaDeHorario("MONDAY", "14:00", "24:00", ajuste=1.2),
    ), dispositivos=(sc.AjusteDeDispositivo("TABLET", 0.5),
                     sc.AjusteDeDispositivo("DESKTOP", 0)))
    ops, r = _montar(configuracao=cfg)
    assert r.ok, _mensagens(r)
    faixas = _criterios_de_campanha(ops, "ad_schedule")
    a, b = (f.ad_schedule for f in faixas)
    assert (a.day_of_week.name, a.start_hour, a.start_minute.name,
            a.end_hour, a.end_minute.name) == ("MONDAY", 8, "ZERO", 12, "THIRTY")
    assert (b.start_hour, b.end_hour, b.end_minute.name) == (14, 24, "ZERO")
    assert faixas[1].bid_modifier == pytest.approx(1.2)
    disp = {d.device.type_.name: d.bid_modifier
            for d in _criterios_de_campanha(ops, "device")}
    assert disp == {"TABLET": 0.5, "DESKTOP": 0.0}


@pytest.mark.parametrize("faixas, trecho", [
    ([sc.FaixaDeHorario("MONDAY", f"{h:02d}:00", f"{h:02d}:30") for h in range(7)],
     "no máximo 6"),
    ([sc.FaixaDeHorario("MONDAY", "08:00", "12:00"),
      sc.FaixaDeHorario("MONDAY", "11:00", "13:00")], "se sobrepõem"),
])
def test_programacao_invalida_morre_na_forma(faixas, trecho):
    with pytest.raises(ValueError, match=trecho):
        sc.ConfiguracaoSearch(programacao=tuple(faixas))


@pytest.mark.parametrize("kw, trecho", [
    ({"dia": "MONDAY", "inicio": "08:10", "fim": "09:00"}, "minutos"),
    ({"dia": "MONDAY", "inicio": "08:00", "fim": "24:15"}, "24 só como 24:00"),
    ({"dia": "MONDAY", "inicio": "10:00", "fim": "09:00"}, "antes do fim"),
    ({"dia": "SEGUNDA", "inicio": "08:00", "fim": "09:00"}, "dia"),
    ({"dia": "MONDAY", "inicio": "08:00", "fim": "09:00", "ajuste": 11.0}, "fora de"),
    ({"dia": "MONDAY", "inicio": "8h", "fim": "09:00"}, "HH:MM"),
])
def test_faixa_invalida_morre_na_forma(kw, trecho):
    with pytest.raises(ValueError, match=trecho):
        sc.FaixaDeHorario(**kw)


def test_ajuste_de_lance_sob_smart_bidding_e_recusado():
    """Smart Bidding ignora ajuste manual: aceitar seria caixa que não faz nada."""
    lance = sc.LanceSearch("MAXIMIZE_CONVERSIONS")
    cfg = _cfg(lance=lance,
               programacao=(sc.FaixaDeHorario("MONDAY", "08:00", "12:00", ajuste=1.3),),
               dispositivos=(sc.AjusteDeDispositivo("MOBILE", 1.4),))
    _, r = _montar(configuracao=cfg)
    campos = {a.campo for a in r.erros}
    assert {"programacao.ajuste", "dispositivos"} <= campos


def test_exclusao_de_dispositivo_vale_mesmo_sob_smart_bidding():
    cfg = _cfg(lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
               programacao=(sc.FaixaDeHorario("MONDAY", "08:00", "12:00"),),
               dispositivos=(sc.AjusteDeDispositivo("TABLET", 0),))
    _, r = _montar(configuracao=cfg)
    assert r.ok, _mensagens(r)


def test_dispositivo_invalido_ou_todos_excluidos_morre_na_forma():
    with pytest.raises(ValueError, match="dispositivo"):
        sc.AjusteDeDispositivo("SMART_TV", 1.0)
    with pytest.raises(ValueError, match="fator"):
        sc.AjusteDeDispositivo("MOBILE", 0.05)
    with pytest.raises(ValueError, match="lugar nenhum"):
        sc.ConfiguracaoSearch(dispositivos=tuple(
            sc.AjusteDeDispositivo(d, 0) for d in sc.DISPOSITIVOS))
    with pytest.raises(ValueError, match="duas vezes"):
        sc.ConfiguracaoSearch(dispositivos=(sc.AjusteDeDispositivo("MOBILE", 1.1),
                                            sc.AjusteDeDispositivo("MOBILE", 0.9)))


# ── 6. GEO, IDIOMA E DATAS ──────────────────────────────────────────────────

SP_ESTADO, SP_CIDADE, RIO_ESTADO = 20106, 1001773, 20102


def test_geo_tipo_multiplos_locais_exclusao_e_idiomas_chegam_ao_payload():
    geo = sc.SegmentacaoGeo(tipo_positivo="PRESENCE", tipo_negativo="PRESENCE",
                            locais=(SP_ESTADO, RIO_ESTADO),
                            locais_excluidos=(SP_CIDADE,), idiomas=("pt", "es"))
    ops, r = _montar(configuracao=_cfg(geo=geo, inicio=FUTURO, fim=FUTURO_FIM))
    assert r.ok, _mensagens(r)
    camp = _camp(ops)
    assert camp.geo_target_type_setting.positive_geo_target_type.name == "PRESENCE"
    assert camp.geo_target_type_setting.negative_geo_target_type.name == "PRESENCE"
    assert camp.start_date_time == f"{FUTURO} 00:00:00"
    assert camp.end_date_time == f"{FUTURO_FIM} 23:59:59"
    locais = {(cc.location.geo_target_constant, cc.negative)
              for cc in _criterios_de_campanha(ops, "location")}
    assert locais == {(f"geoTargetConstants/{SP_ESTADO}", False),
                      (f"geoTargetConstants/{RIO_ESTADO}", False),
                      (f"geoTargetConstants/{SP_CIDADE}", True)}
    assert len(_criterios_de_campanha(ops, "language")) == 2


def test_geo_sem_locais_usa_o_pais_e_o_idioma_do_brief():
    geo = sc.SegmentacaoGeo(tipo_positivo="PRESENCE_OR_INTEREST", tipo_negativo="PRESENCE")
    ops, r = _montar(configuracao=_cfg(geo=geo))
    assert r.ok
    b = _brief()
    assert [cc.location.geo_target_constant
            for cc in _criterios_de_campanha(ops, "location")] == [
        f"geoTargetConstants/{b.geo_id}"]
    assert [cc.language.language_constant
            for cc in _criterios_de_campanha(ops, "language")] == [
        f"languageConstants/{b.idioma_id}"]


def test_local_de_outro_pais_e_erro_porque_o_portao_so_julgou_um():
    mexico = 2484
    geo = sc.SegmentacaoGeo(tipo_positivo="PRESENCE", tipo_negativo="PRESENCE",
                            locais=(mexico,))
    _, r = _montar(configuracao=_cfg(geo=geo))
    assert "portão país × vertical" in _mensagens(r)


def test_idiomas_sem_o_idioma_do_brief_e_erro():
    geo = sc.SegmentacaoGeo(tipo_positivo="PRESENCE", tipo_negativo="PRESENCE",
                            idiomas=("es",))
    _, r = _montar(configuracao=_cfg(geo=geo))
    assert "idioma do brief" in _mensagens(r)


def test_geo_invalido_morre_na_forma():
    with pytest.raises(ValueError, match="tipo_positivo"):
        sc.SegmentacaoGeo(tipo_positivo="LOCAL", tipo_negativo="PRESENCE")
    with pytest.raises(ValueError, match="tipo_negativo"):
        sc.SegmentacaoGeo(tipo_positivo="PRESENCE", tipo_negativo="SEARCH_INTEREST")
    with pytest.raises(ValueError, match="incluído E excluído"):
        sc.SegmentacaoGeo(tipo_positivo="PRESENCE", tipo_negativo="PRESENCE",
                          locais=(1,), locais_excluidos=(1,))


def test_datas_invalidas_sao_recusadas():
    with pytest.raises(ValueError, match="antes do início"):
        sc.ConfiguracaoSearch(inicio=FUTURO_FIM, fim=FUTURO)
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        sc.ConfiguracaoSearch(inicio="08/10/2026")
    _, r = _montar(configuracao=_cfg(inicio="2020-01-01"))
    assert "passado" in _mensagens(r)


# ── 7. META DE CONVERSÃO ────────────────────────────────────────────────────

ACAO = f"customers/{CID}/conversionActions/7467141090"
META = f"customers/{CID}/customConversionGoals/6456286881"


def _updates(ops, tipo):
    return [getattr(o, tipo) for o in _por_tipo(ops, tipo)]


def test_acao_especifica_cria_meta_personalizada_e_aponta_a_campanha_para_ela():
    meta = sc.MetaDeConversao(acoes_de_conversao=(ACAO,), categorias=(
        sc.MetaDeCategoria("PURCHASE", "WEBSITE", lance=False),))
    ops, r = _montar(configuracao=_cfg(lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
                                       meta_de_conversao=meta))
    assert r.ok, _mensagens(r)
    tipos = [o._pb.WhichOneof("operation") for o in ops]
    criada = _por_tipo(ops, "custom_conversion_goal_operation")[0] \
        .custom_conversion_goal_operation.create
    assert criada.resource_name == f"customers/{CID}/customConversionGoals/-400"
    assert list(criada.conversion_actions) == [ACAO]
    cfgop, = _updates(ops, "conversion_goal_campaign_config_operation")
    assert cfgop.update.resource_name == \
        f"customers/{CID}/conversionGoalCampaignConfigs/{comum.T_CAMPANHA}"
    assert cfgop.update.custom_conversion_goal == criada.resource_name
    assert list(cfgop.update_mask.paths) == ["custom_conversion_goal"]
    goal, = _updates(ops, "campaign_conversion_goal_operation")
    assert goal.update.resource_name.endswith(f"/{comum.T_CAMPANHA}~PURCHASE~WEBSITE")
    assert goal.update.biddable is False
    assert list(goal.update_mask.paths) == ["biddable"]
    # a meta nasce antes de ser referenciada, e tudo depois da campanha
    assert tipos.index("custom_conversion_goal_operation") < \
        tipos.index("conversion_goal_campaign_config_operation")
    assert tipos.index("campaign_operation") < tipos.index("custom_conversion_goal_operation")


def test_meta_personalizada_existente_nao_cria_outra():
    meta = sc.MetaDeConversao(meta_personalizada=META)
    ops, r = _montar(configuracao=_cfg(lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
                                       meta_de_conversao=meta))
    assert r.ok
    assert not _por_tipo(ops, "custom_conversion_goal_operation")
    cfgop, = _updates(ops, "conversion_goal_campaign_config_operation")
    assert cfgop.update.custom_conversion_goal == META
    # sem desligar as categorias herdadas, a meta SOMA — e isso é avisado
    assert any(a.campo == "meta_de_conversao" for a in r.achados
               if a.severidade == "aviso")


def test_meta_de_outra_conta_e_erro():
    meta = sc.MetaDeConversao(acoes_de_conversao=("customers/1/conversionActions/2",))
    _, r = _montar(configuracao=_cfg(lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS"),
                                     meta_de_conversao=meta))
    assert "conta de conversão" in _mensagens(r)


@pytest.mark.parametrize("kw, trecho", [
    ({}, "vazia"),
    ({"meta_personalizada": META, "acoes_de_conversao": (ACAO,)}, "OU"),
    ({"meta_personalizada": "6456286881"}, "CustomConversionGoal"),
    ({"acoes_de_conversao": ("conversionActions/1",)}, "ConversionAction"),
    ({"categorias": (sc.MetaDeCategoria("PURCHASE", "WEBSITE", True),
                     sc.MetaDeCategoria("PURCHASE", "WEBSITE", False))}, "repetido"),
])
def test_meta_invalida_morre_na_forma(kw, trecho):
    with pytest.raises(ValueError, match=trecho):
        sc.MetaDeConversao(**kw)


def test_categoria_ou_origem_inexistente_morre_na_forma():
    with pytest.raises(ValueError, match="categoria"):
        sc.MetaDeCategoria("VENDA", "WEBSITE", True)
    with pytest.raises(ValueError, match="origem"):
        sc.MetaDeCategoria("PURCHASE", "SITE", True)


# ── a integração com perfil, plano e selo ───────────────────────────────────


def test_perfil_montar_entrega_a_configuracao_ao_construtor():
    from volc_ads.campanha import perfil

    lance = sc.LanceSearch("TARGET_SPEND", teto_cpc=0.3)
    ops, r = perfil.montar("SEARCH", CID, _brief(), login_customer_id="x",
                           configuracao=_cfg(lance=lance))
    assert r.ok
    assert _camp(ops)._pb.WhichOneof("campaign_bidding_strategy") == "target_spend"


def test_planejar_aceita_o_payload_maximo_sem_quebrar_a_projecao():
    p = search.planejar(CID, _brief(), login_customer_id="x", configuracao=_cfg_maxima())
    assert p.prontidao.monta, p


def test_configuracao_diferente_muda_a_impressao_do_payload():
    from volc_ads import subir as sb

    a, _ = _montar(configuracao=_cfg(lance=sc.LanceSearch("TARGET_SPEND")))
    b, _ = _montar(configuracao=_cfg(lance=sc.LanceSearch("TARGET_SPEND", teto_cpc=0.5)))
    assert sb._impressao(a) != sb._impressao(b)


def _cfg_maxima() -> sc.ConfiguracaoSearch:
    """Todos os recursos novos juntos — o mesmo formato do `validate_only` máximo."""
    return sc.ConfiguracaoSearch(
        lance=sc.LanceSearch("MAXIMIZE_CONVERSIONS", target_cpa=4.0),
        rede=sc.RedeSearch(google_search=True, parceiros=False, display_expansion=True),
        ai_max=_aimax(exclusoes_de_url=("/blog/",), listas_de_marca_excluidas=(LISTA_B,),
                      termos_excluidos=("garantido",),
                      restricoes_de_mensagem=("Nao prometa aprovacao",)),
        anuncio=sc.AnuncioSearch(path1="saque", path2="regras", fixacoes=(
            sc.Fixacao("Regras do Saque Anual", "HEADLINE_1"),)),
        programacao=(sc.FaixaDeHorario("MONDAY", "08:00", "20:00"),),
        dispositivos=(sc.AjusteDeDispositivo("TABLET", 0),),
        geo=sc.SegmentacaoGeo(tipo_positivo="PRESENCE", tipo_negativo="PRESENCE",
                              locais=(SP_ESTADO,), idiomas=("pt",)),
        inicio=FUTURO, fim=FUTURO_FIM,
        meta_de_conversao=sc.MetaDeConversao(acoes_de_conversao=(ACAO,), categorias=(
            sc.MetaDeCategoria("PURCHASE", "WEBSITE", lance=False),)),
    )


def test_payload_maximo_monta_com_todos_os_recursos_juntos():
    ops, r = _montar(configuracao=_cfg_maxima())
    assert r.ok, _mensagens(r)
    tipos = {o._pb.WhichOneof("operation") for o in ops}
    assert {"custom_conversion_goal_operation",
            "conversion_goal_campaign_config_operation",
            "campaign_conversion_goal_operation"} <= tipos
    ramos = {o.campaign_criterion_operation.create._pb.WhichOneof("criterion")
             for o in _por_tipo(ops, "campaign_criterion_operation")}
    assert {"location", "language", "ad_schedule", "device", "webpage",
            "brand_list"} <= ramos
