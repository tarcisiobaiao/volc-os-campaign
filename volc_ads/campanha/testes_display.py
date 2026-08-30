"""Testes do construtor de Display — a primeira fatia vertical do canal.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/campanha/testes_display.py -q

**Nenhum teste aqui fala com o Google.** O cliente é montado sem credencial
(`_cliente_sem_rede`, o mesmo shim de `testes_search.py`) e injetado por
monkeypatch; o caminho do `validate_only` é exercitado contra um dublê que
registra o que receberia. O que se testa é o PAYLOAD e as RECUSAS — que é onde
moram os defeitos que este arquivo persegue.

Quatro grupos:

  GRAFO      a hierarquia campanha → ad group → responsive display ad → assets,
             com as faixas de id temporário de `comum.py` respeitadas e a faixa
             de asset INTOCADA.

  RECUSA     o que Search permite e Display não: `MANUAL_CPC`, `ai_max` e DKI.
             Cada uma some em silêncio se ninguém barrar — `comum.op_campanha`
             já ignora `estrategia_lance` no ramo DISPLAY.

  ASSET      imagem por papel, contagem, e o resource name que precisa ser real,
             desta conta e nunca temporário.

  PERFIL     o registro do engine e a vista de `subir.py` dizendo a mesma coisa,
             e o roteamento de opções por canal.
"""

from __future__ import annotations

import enum
import pathlib
import sys
from importlib import import_module

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

from volc_ads import subir as motor  # noqa: E402
from volc_ads.campanha import comum, conteudo, display, perfil  # noqa: E402
from volc_ads.campanha.brief import (  # noqa: E402
    Brief,
    Copy,
    ImagensDisplay,
    SubIntencao,
)

CID = "8017851692"


# ── cliente sem rede ────────────────────────────────────────────────────────


class _Enums:
    """`client.enums` sem credencial — ver `testes_search._Enums`."""

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
    monkeypatch.setattr(display, "cliente", lambda _login: _cliente_sem_rede())


# ── briefs de teste ─────────────────────────────────────────────────────────


def _imagens(**troca) -> ImagensDisplay:
    base = dict(
        marketing=[f"customers/{CID}/assets/111"],
        marketing_quadrada=[f"customers/{CID}/assets/222"],
        logo=[f"customers/{CID}/assets/333"],
    )
    base.update(troca)
    return ImagensDisplay(**base)


def _copy(**troca) -> Copy:
    base = dict(
        headlines=["Regras do Saque Anual", "Quem Tem Direito em 2026",
                   "Tabela Oficial por Faixa"],
        long_headlines=["Prazos, limites e quem tem direito ao saque anual"],
        descriptions=["Prazos, limites e quem tem direito, com fonte citada.",
                      "Portal informativo com a tabela legal por faixa etaria."],
        business_name="Credito Up",
    )
    base.update(troca)
    return Copy(**base)


def _brief(**troca) -> Brief:
    base = dict(
        nicho="Saque Anual",
        slug="saque-anual",
        url_final="https://creditoup.com.br/r/saque-anual/",
        keywords=["saque anual fgts"],
        copy=_copy(),
        # ⚠️ NÃO é o padrão do `Brief`. O padrão da casa é MANUAL_CPC, que
        # Display recusa — e é justamente por isso que o brief de teste declara
        # o outro: sem esta linha, TODO teste aqui morreria na mesma recusa e
        # nenhum deles provaria o que se propõe.
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        imagens_display=_imagens(),
    )
    base.update(troca)
    return Brief(**base)


def _por_tipo(ops, tipo: str):
    return [o for o in ops if o._pb.WhichOneof("operation") == tipo]


def _rda(ops):
    ad = _por_tipo(ops, "ad_group_ad_operation")[0]
    return ad.ad_group_ad_operation.create.ad.responsive_display_ad


def _erros(r) -> str:
    return "\n".join(f"{a.campo}: {a.motivo}" for a in r.erros)


def _avisos(r) -> str:
    return "\n".join(f"{a.campo}: {a.motivo}"
                     for a in r.achados if a.severidade == "aviso")


# ═══════════════════════════════════════════════════════════════════════════
# GRAFO
# ═══════════════════════════════════════════════════════════════════════════


def test_o_grafo_e_a_hierarquia_declarada_e_nada_mais():
    """campanha → ad group → responsive display ad, numa transação só."""
    ops, r = display.construir(CID, _brief(), login_customer_id="x")
    assert r.ok, _erros(r)

    tipos = [o._pb.WhichOneof("operation") for o in ops]
    assert tipos == [
        "campaign_budget_operation",
        "campaign_operation",
        "campaign_criterion_operation",   # geo
        "campaign_criterion_operation",   # idioma
        "ad_group_operation",
        "ad_group_ad_operation",
    ]


def test_a_campanha_nasce_no_canal_display_pausada_e_em_maxconv():
    ops, _ = display.construir(CID, _brief(), login_customer_id="x")
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create

    assert camp.advertising_channel_type.name == "DISPLAY"
    # Despausar é decisão explícita, nunca efeito colateral de criar.
    assert camp.status.name == "PAUSED"
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"
    # Rede de CONTEÚDO, e só ela: Display na busca não existe.
    assert camp.network_settings.target_content_network is True
    assert camp.network_settings.target_google_search is False


def test_o_tcpa_viaja_dentro_do_maxconv_e_nao_como_estrategia_avulsa():
    """⚠️ `TARGET_CPA` avulso NÃO aparece na tabela oficial de lances de Display.

    `matriz-api/display.md` §8: `MAXIMIZE_CONVERSIONS` é a única estratégia
    marcada `[alta]` para o canal. Emitir um esquema que a doc não declara é
    apostar em qual leitura está certa e descobrir no lote — o tCPA vive
    dentro do MaxConv, como em Search.
    """
    ops, _ = display.construir(CID, _brief(tcpa=3.5), login_customer_id="x")
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create

    assert camp._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"
    assert camp.maximize_conversions.target_cpa_micros == 3_500_000


def test_o_nome_da_campanha_marca_o_canal_e_search_continua_sem_marcador():
    """O defeito nº 1 da nomenclatura dos primos: canal implícito no nome.

    Quatro campanhas de Demand Gen deles dizem "Display". Com dois canais no
    ar, o nome precisa dizer qual é — e o de Search não pode mudar, senão o
    `analisar()` de tudo que já subiu para de casar.
    """
    ops, _ = display.construir(CID, _brief(), login_customer_id="x")
    nome = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create.name

    assert nome.endswith(" [Display]")
    assert nome.startswith("BR - ")
    assert not conteudo.nome_da_campanha(
        _brief(), "20260826_120000").endswith("]")


def test_o_ad_group_e_display_standard_e_fica_no_id_temporario_menos_3():
    ops, _ = display.construir(CID, _brief(), login_customer_id="x")
    ag = _por_tipo(ops, "ad_group_operation")[0].ad_group_operation.create

    assert ag.type_.name == "DISPLAY_STANDARD"
    assert ag.resource_name == comum.temp_adgroup(CID, 0)
    assert ag.campaign == comum.temp(CID, "campaigns", comum.T_CAMPANHA)


def test_display_nao_toca_na_faixa_de_asset_reservada_para_search():
    """A faixa `-100 para baixo` continua sendo só de Search.

    Display não CRIA asset: imagem e vídeo chegam como resource name de Asset
    já existente. Se algum id temporário desta faixa aparecesse no payload, a
    referência apontaria para um recurso que este mutate não cria.
    """
    ops, _ = display.construir(CID, _brief(), login_customer_id="x")
    texto = "\n".join(str(o) for o in ops)

    assert f"/assets/{comum.T_ASSET_BASE}" not in texto
    assert "/assets/-" not in texto


def test_o_anuncio_leva_a_url_limpa_e_a_marcacao_vive_no_sufixo_da_campanha():
    ops, _ = display.construir(CID, _brief(), login_customer_id="x")
    ad = _por_tipo(ops, "ad_group_ad_operation")[0].ad_group_ad_operation.create
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create

    assert list(ad.ad.final_urls) == ["https://creditoup.com.br/r/saque-anual/"]
    assert "?" not in ad.ad.final_urls[0]
    # ⚠️ O contrato de DISPLAY não carrega `{keyword}` nem `{matchtype}`: neste
    # canal eles chegam vazios e só poluiriam a coluna do relatório.
    assert "utm_campaign={campaignid}" in camp.final_url_suffix
    assert "{keyword}" not in camp.final_url_suffix


def test_o_rda_carrega_texto_imagem_e_video_nos_campos_certos():
    ops, _ = display.construir(
        CID,
        _brief(videos=[f"customers/{CID}/assets/444"]),
        login_customer_id="x",
    )
    rda = _rda(ops)

    assert [h.text for h in rda.headlines] == [
        "Regras do Saque Anual", "Quem Tem Direito em 2026",
        "Tabela Oficial por Faixa"]
    # `long_headline` é campo SINGULAR no proto, não uma lista de um item.
    assert rda.long_headline.text == "Prazos, limites e quem tem direito ao saque anual"
    assert len(rda.descriptions) == 2
    assert rda.business_name == "Credito Up"
    assert [i.asset for i in rda.marketing_images] == [f"customers/{CID}/assets/111"]
    assert [i.asset for i in rda.square_marketing_images] == [f"customers/{CID}/assets/222"]
    assert [i.asset for i in rda.logo_images] == [f"customers/{CID}/assets/333"]
    assert [v.asset for v in rda.youtube_videos] == [f"customers/{CID}/assets/444"]


def test_o_teto_de_5_titulos_do_rda_corta_o_excesso_do_brief_de_search():
    """O RSA aceita 15 títulos e o RDA aceita 5.

    O brief é multicanal e traz a lista que a copy escreveu; herdar o limite de
    Search subiria um payload que a API recusa inteiro.
    """
    ops, r = display.construir(
        CID,
        _brief(copy=_copy(headlines=[f"Titulo numero {i}" for i in range(9)])),
        login_customer_id="x",
    )
    assert r.ok, _erros(r)
    assert len(_rda(ops).headlines) == 5


# ═══════════════════════════════════════════════════════════════════════════
# RECUSA — o que Search permite e Display não
# ═══════════════════════════════════════════════════════════════════════════


def test_o_padrao_da_casa_manual_cpc_e_recusado_com_o_caminho_de_volta():
    """⚠️ O brief nasce em `MANUAL_CPC`. Este é o caso REAL, não o exótico.

    `comum.op_campanha()` já não lê `estrategia_lance` no ramo DISPLAY: sem
    esta recusa, a campanha subiria em tCPA e o operador seguiria achando que
    declarou o lance. É o mesmo defeito que o `MANUAL_CPC` de Search existe
    para não ter — número digitado que vira decoração.
    """
    ops, r = display.construir(
        CID, _brief(estrategia_lance="MANUAL_CPC"), login_customer_id="x")

    assert not r.ok
    assert ops == []
    motivo = _erros(r)
    assert "estrategia_lance" in motivo
    assert "MAXIMIZE_CONVERSIONS" in motivo, "a recusa precisa dizer o que fazer"


def test_ai_max_e_recusado_porque_o_campo_e_de_search():
    _, r = display.construir(CID, _brief(ai_max=True), login_customer_id="x")

    assert not r.ok
    assert "ai_max" in _erros(r)


def test_dki_e_recusado_e_a_recusa_explica_por_que():
    """Display não casa keyword: a tag renderiza SEMPRE o fallback."""
    _, r = display.construir(
        CID,
        _brief(copy=_copy(headlines=["{KeyWord:Saque Anual} 2026", "Outro", "Terceiro"])),
        login_customer_id="x",
    )

    assert not r.ok
    motivo = _erros(r)
    assert "DKI" in motivo
    assert "fallback" in motivo


def test_o_titulo_longo_e_obrigatorio_e_a_recusa_diz_onde_preencher():
    _, r = display.construir(
        CID, _brief(copy=_copy(long_headlines=[])), login_customer_id="x")

    assert not r.ok
    assert "copy.long_headlines" in _erros(r)


def test_o_nome_do_negocio_e_obrigatorio():
    _, r = display.construir(
        CID, _brief(copy=_copy(business_name="")), login_customer_id="x")

    assert not r.ok
    assert "copy.business_name" in _erros(r)


def test_titulo_acima_de_30_chars_e_recusado_antes_da_api():
    _, r = display.construir(
        CID,
        _brief(copy=_copy(headlines=["Um titulo bem maior do que trinta caracteres"])),
        login_customer_id="x",
    )

    assert not r.ok
    assert "headline_display" in _erros(r)


def test_o_portao_pais_vertical_vale_em_display_igual_a_search():
    """Display não tem desconto de política.

    `financeiro` no BR exige certificação declarada; sem ela o portão barra o
    mutate em vez de torcer para passar.
    """
    _, sem = display.construir(
        CID, _brief(vertical="financeiro"), login_customer_id="x")
    _, com = display.construir(
        CID,
        _brief(vertical="financeiro",
               certificacoes={"verificacao_servicos_financeiros"}),
        login_customer_id="x",
    )

    assert not sem.ok
    assert com.ok, _erros(com)


# ═══════════════════════════════════════════════════════════════════════════
# ASSET
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_imagens_display_a_recusa_ensina_o_que_preencher():
    _, r = display.construir(
        CID, _brief(imagens_display=None, imagens=["customers/1/assets/9"]),
        login_customer_id="x")

    assert not r.ok
    motivo = _erros(r)
    assert "imagens_display" in motivo
    assert "600x314" in motivo and "300x300" in motivo
    # a lista chapada que veio no brief não some sem explicação
    assert "imagens" in _avisos(r)


@pytest.mark.parametrize(
    ("troca", "campo"),
    [
        ({"marketing": []}, "imagens_display.marketing"),
        ({"marketing_quadrada": []}, "imagens_display.marketing_quadrada"),
    ],
)
def test_as_duas_familias_de_imagem_de_marketing_sao_obrigatorias(troca, campo):
    """O proto do RDA diz "at least one … is required" para as duas."""
    _, r = display.construir(
        CID, _brief(imagens_display=_imagens(**troca)), login_customer_id="x")

    assert not r.ok
    assert campo in _erros(r)


def test_sem_logo_e_aviso_e_nao_erro():
    """⚠️ A diferença é medida, não opinião.

    O proto escreve "is required" para as duas famílias de marketing e NÃO
    escreve para logo. Barrar aqui recusaria localmente um payload que a API
    aceita — e portão que dá falso positivo é portão que alguém desliga.
    """
    ops, r = display.construir(
        CID, _brief(imagens_display=_imagens(logo=[])), login_customer_id="x")

    assert r.ok, _erros(r)
    assert ops
    assert "imagens_display.logo" in _avisos(r)


def test_o_teto_combinado_de_15_imagens_de_marketing_e_barrado():
    im = _imagens(
        marketing=[f"customers/{CID}/assets/{i}" for i in range(1, 10)],
        marketing_quadrada=[f"customers/{CID}/assets/{i}" for i in range(20, 28)],
    )
    _, r = display.construir(CID, _brief(imagens_display=im), login_customer_id="x")

    assert not r.ok
    assert "15" in _erros(r)


def test_o_teto_de_5_logos_e_barrado():
    im = _imagens(
        logo=[f"customers/{CID}/assets/{i}" for i in range(40, 44)],
        logo_quadrado=[f"customers/{CID}/assets/{i}" for i in range(50, 53)],
    )
    _, r = display.construir(CID, _brief(imagens_display=im), login_customer_id="x")

    assert not r.ok
    assert "`logo` e `logo_quadrado`" in _erros(r)


def test_mais_de_5_videos_e_barrado():
    _, r = display.construir(
        CID,
        _brief(videos=[f"customers/{CID}/assets/{i}" for i in range(60, 67)]),
        login_customer_id="x",
    )

    assert not r.ok
    assert "videos" in _erros(r)


def test_asset_de_outra_conta_e_recusado_aqui_e_nao_no_google():
    """`RESOURCE_NOT_FOUND` do outro lado nomeia a conta ERRADA para procurar."""
    _, r = display.construir(
        CID,
        _brief(imagens_display=_imagens(marketing=["customers/9999/assets/111"])),
        login_customer_id="x",
    )

    assert not r.ok
    assert "9999" in _erros(r)


def test_resource_name_torto_e_recusado_com_o_formato_certo_na_mensagem():
    _, r = display.construir(
        CID, _brief(imagens_display=_imagens(marketing=["assets/111"])),
        login_customer_id="x")

    assert not r.ok
    assert f"customers/{CID}/assets/" in _erros(r)


def test_id_temporario_de_asset_e_recusado_porque_invadiria_a_faixa():
    """A colisão que não avisa, barrada onde ela é barata.

    Um `assets/-100` no payload de Display apontaria para o vão que `comum.py`
    reserva a Search — e o sintoma apareceria em outro recurso do mesmo mutate.
    """
    _, r = display.construir(
        CID,
        _brief(imagens_display=_imagens(
            marketing=[f"customers/{CID}/assets/{comum.T_ASSET_BASE}"])),
        login_customer_id="x",
    )

    assert not r.ok
    motivo = _erros(r)
    assert "TEMPOR" in motivo.upper()
    assert str(comum.T_ASSET_BASE) in motivo


# ═══════════════════════════════════════════════════════════════════════════
# O QUE A FATIA AINDA NÃO MONTA — declarado, nunca descartado em silêncio
# ═══════════════════════════════════════════════════════════════════════════


def test_as_keywords_do_brief_nao_viram_criterio_e_o_operador_ouve_isso():
    ops, r = display.construir(CID, _brief(), login_customer_id="x")

    assert r.ok, _erros(r)
    assert not _por_tipo(ops, "ad_group_criterion_operation")
    assert "keywords" in _avisos(r)


def test_sub_intencoes_viram_um_ad_group_so_com_aviso():
    """Sem segmentação por grupo, N grupos repartiriam a verba por sorteio."""
    b = _brief(keywords=[], sub_intencoes=[
        SubIntencao("ACESSO", ["saque anual fgts"]),
        SubIntencao("VALOR", ["valor do saque anual"]),
    ])
    ops, r = display.construir(CID, b, login_customer_id="x")

    assert r.ok, _erros(r)
    assert len(_por_tipo(ops, "ad_group_operation")) == 1
    assert "sub_intencoes" in _avisos(r)


def test_as_negativas_do_brief_ficam_de_fora_com_aviso():
    ops, r = display.construir(
        CID, _brief(negativas_campanha=["gratis"]), login_customer_id="x")

    assert r.ok, _erros(r)
    assert len(_por_tipo(ops, "campaign_criterion_operation")) == 2  # geo + idioma
    assert "negativas" in _avisos(r)


# ═══════════════════════════════════════════════════════════════════════════
# validate_only — implementado, provado com dublê, nunca contra a conta real
# ═══════════════════════════════════════════════════════════════════════════


def test_validar_manda_o_grafo_ao_validate_only_e_nao_escreve(monkeypatch):
    vistos = {}

    def _dublê(cid, ops, *, login_customer_id):
        vistos["cid"] = cid
        vistos["n"] = len(ops)
        vistos["mcc"] = login_customer_id
        return None

    monkeypatch.setattr(display, "validar_mutacoes", _dublê)
    r, falha, n = display.validar(CID, _brief(), login_customer_id="x")

    assert r.ok and falha is None
    assert n == 6 and vistos == {"cid": CID, "n": 6, "mcc": "x"}


def test_validar_nao_gasta_chamada_quando_a_validacao_local_ja_reprovou(monkeypatch):
    """A camada mais barata primeiro. `validate_only` custa rede."""
    monkeypatch.setattr(
        display, "validar_mutacoes",
        lambda *_a, **_k: pytest.fail("chamou a API com payload reprovado localmente"))

    r, falha, n = display.validar(
        CID, _brief(estrategia_lance="MANUAL_CPC"), login_customer_id="x")

    assert not r.ok and falha is None and n == 0


# ═══════════════════════════════════════════════════════════════════════════
# PERFIL — uma verdade, duas leituras
# ═══════════════════════════════════════════════════════════════════════════


def test_o_registro_de_subir_e_uma_vista_do_perfil_e_nao_uma_segunda_lista():
    assert set(motor.CONSTRUTORES_POR_CANAL) == set(perfil.canais_que_criam())
    assert motor.CONSTRUTORES_POR_CANAL["DISPLAY"] is display.construir
    assert perfil.DISPLAY.construtor is display.construir
    assert perfil.DISPLAY.validador is display.validar
    assert set(motor.PROVADORES_POR_CANAL) == set(perfil.canais_que_provam())
    assert "DEMAND_GEN" in motor.PROVADORES_POR_CANAL
    assert "DEMAND_GEN" not in motor.CONSTRUTORES_POR_CANAL


def test_o_perfil_referencia_o_canal_em_vez_de_copiar_os_fatos_dele():
    """`is`, e não `==`: cópia é o que diverge no primeiro ajuste."""
    assert perfil.DISPLAY.lances_permitidos is display.LANCES_PERMITIDOS
    assert perfil.DISPLAY.opcoes is display.OPCOES
    assert perfil.SEARCH.lances_permitidos is not perfil.DISPLAY.lances_permitidos


def test_resolver_construtor_aceita_display_e_canoniza_a_entrada():
    canal, construtor = motor.resolver_construtor("  display ")

    assert canal == "DISPLAY"
    assert construtor is display.construir


def test_montar_recusa_a_opcao_que_o_canal_nao_tem_em_vez_de_ignorar():
    """Marcar uma caixa que não faz nada é pior que não poder marcá-la."""
    with pytest.raises(perfil.OpcaoIndisponivel, match="ai_max"):
        perfil.montar("DISPLAY", CID, _brief(),
                      login_customer_id="x", ai_max=True)


def test_montar_deixa_passar_a_opcao_desligada_sem_reclamar(monkeypatch):
    """`ai_max=False` é o default de `preparar()` e vale para todo canal."""
    monkeypatch.setattr(display, "cliente", lambda _l: _cliente_sem_rede())
    ops, r = perfil.montar("DISPLAY", CID, _brief(),
                           login_customer_id="x", ai_max=False)

    assert r.ok, _erros(r)
    assert len(ops) == 6


def test_display_nao_autocorrige_keyword_porque_nao_opera_keyword():
    """A poda remontaria um payload IDÊNTICO e o diário afirmaria uma decisão."""
    assert perfil.SEARCH.autocorrige_keywords is True
    assert perfil.DISPLAY.autocorrige_keywords is False


def test_todo_canal_que_cria_declara_validador_prova_e_lance():
    """A guarda do `__post_init__` é a prova; aqui ela é exercida no registro."""
    for p in perfil.PERFIS.values():
        if not p.sabe_criar:
            continue
        assert p.validador is not None
        assert p.lances_permitidos
        assert "selo" in p.provas_obrigatorias
        assert p.coletor, f"{p.canal} cria e ninguém declara quem lê de volta"


def test_o_canal_que_nao_cria_declara_a_ausencia_em_vez_de_ficar_vazio():
    for canal in ("DEMAND_GEN", "PERFORMANCE_MAX"):
        p = perfil.PERFIS[canal]
        assert not p.sabe_criar
        assert p.acoes_indisponiveis, f"{canal} não explica por que não cria"
    assert perfil.DEMAND_GEN.sabe_provar is True
    assert perfil.PERFORMANCE_MAX.sabe_provar is False


def test_a_fatia_nao_emite_criterio_de_segmentacao_nenhum():
    """A contraprova da decisão sobre placement: nada além de geo e idioma.

    ⚠️ Se alguém acrescentar segmentação positiva por placement sem a prova de
    `validate_only` que resolve a contradição das duas fontes oficiais, este
    teste derruba — e é para derrubar mesmo. A contradição não some porque
    alguém escolheu um dos lados.
    """
    ops, r = display.construir(CID, _brief(), login_customer_id="x")
    assert r.ok, _erros(r)

    criterios = _por_tipo(ops, "campaign_criterion_operation")
    campos = {c.campaign_criterion_operation.create._pb.WhichOneof("criterion")
              for c in criterios}
    assert campos == {"location", "language"}
    assert not _por_tipo(ops, "ad_group_criterion_operation")


def test_o_perfil_explica_por_que_placement_positivo_ficou_de_fora():
    texto = " ".join(perfil.DISPLAY.acoes_indisponiveis)

    assert "placement" in texto
    assert "NÃO CONFIRMADO" in texto
    assert "validate_only" in texto


# ═══════════════════════════════════════════════════════════════════════════
# REGRESSÃO · achado da auditoria adversarial de 26/08/2026
# ═══════════════════════════════════════════════════════════════════════════


def test_copy_cortada_por_teto_aparece_como_achado():
    """⚠️ O corte era silencioso, e o que se perde é trabalho pago.

    O RSA aceita 15 títulos e o RDA aceita 5. Um brief escrito para Search e
    reaproveitado em Display perdia 10 títulos sem um achado — e esses textos vêm
    do ciclo de copy, que passa por juiz semântico. O operador precisa saber que
    o que ele leu não é o que subiu.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import Brief, Copy, ImagensDisplay

    CID = "8017851692"
    b = Brief(
        nicho="Consórcio", slug="consorcio",
        url_final="https://creditoup.com.br/r/consorcio/",
        keywords=["consorcio"], estrategia_lance="MAXIMIZE_CONVERSIONS",
        copy=Copy(
            headlines=[f"Título número {n}" for n in range(1, 13)],
            descriptions=["Simule agora e veja a parcela."],
            long_headlines=["Consórcio de imóvel com parcela que cabe no bolso"],
            business_name="Crédito Up"),
        imagens_display=ImagensDisplay(
            marketing=[f"customers/{CID}/assets/1"],
            marketing_quadrada=[f"customers/{CID}/assets/2"]))

    _, r = display.construir(CID, b, login_customer_id="6016739364")
    cortes = [a for a in r.achados
              if "não sobem" in str(getattr(a, "motivo", ""))]
    assert cortes, "12 títulos entraram para um teto de 5 e nenhum achado avisou"
    assert "7" in str(cortes[0].motivo), cortes[0].motivo


# ═══════════════════════════════════════════════════════════════════════════
# P04-T05a · O ASSET DE IMAGEM NASCE NO MESMO MUTATE
# ═══════════════════════════════════════════════════════════════════════════
#
# A fatia que o revisor adversarial propôs no lugar da ponte de upload: em vez
# de subir o asset, esperar o `resource_name` e montar o payload depois — que é
# improvável sem abrir a trava de escrita —, o asset entra como
# `asset_operation` na mesma requisição atômica, referenciado por id temporário.
#
# Isso apaga uma classe de problema em vez de resolvê-la: sem duas fases não
# existe "o asset subiu e a campanha não", nem "o upload deu timeout, criou?".


def _brief_display(cid="8017851692", **imagens):
    from volc_ads.campanha.brief import Brief, Copy, ImagensDisplay
    return Brief(
        nicho="Consórcio", slug="consorcio",
        url_final="https://creditoup.com.br/r/consorcio/",
        keywords=["consorcio"], estrategia_lance="MAXIMIZE_CONVERSIONS",
        copy=Copy(headlines=["Consórcio de imóvel"],
                  descriptions=["Simule agora e veja a parcela."],
                  long_headlines=["Consórcio de imóvel com parcela que cabe"],
                  business_name="Crédito Up"),
        imagens_display=ImagensDisplay(**imagens))


def _png(n=64):
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * n


def test_imagem_nova_vira_asset_operation_no_mesmo_mutate():
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir
    CID = "8017851692"
    b = _brief_display(
        marketing=[ImagemParaSubir(nome="banner", dados=_png(), mime="image/png")],
        marketing_quadrada=[ImagemParaSubir(nome="quadrado", dados=_png(), mime="image/png")])
    ops, r = display.construir(CID, b, login_customer_id="6016739364")
    assert r.ok, [str(a) for a in r.achados]

    de_asset = [o for o in ops if o._pb.WhichOneof("operation") == "asset_operation"]
    assert len(de_asset) == 2, f"esperava 2 asset_operation, veio {len(de_asset)}"
    for o in de_asset:
        cria = o.asset_operation.create
        assert cria.resource_name.startswith(f"customers/{CID}/assets/-2")
        assert cria.image_asset.data, "asset sem bytes"
        assert cria.name


def test_o_asset_entra_ANTES_do_anuncio_que_o_referencia():
    """A API resolve id temporário só depois de ele ser definido.

    Se o anúncio viesse primeiro, a API recusaria o mutate inteiro com um erro
    sobre o ANÚNCIO — e o defeito estaria na ordem da lista.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir
    b = _brief_display(
        marketing=[ImagemParaSubir(nome="banner", dados=_png())],
        marketing_quadrada=[ImagemParaSubir(nome="quadrado", dados=_png())])
    ops, r = display.construir("8017851692", b, login_customer_id="6016739364")
    tipos = [o._pb.WhichOneof("operation") for o in ops]
    i_ultimo_asset = max(i for i, t in enumerate(tipos) if t == "asset_operation")
    i_anuncio = tipos.index("ad_group_ad_operation")
    assert i_ultimo_asset < i_anuncio, f"ordem errada: {tipos}"


def test_o_anuncio_referencia_exatamente_os_ids_emitidos():
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir
    b = _brief_display(
        marketing=[ImagemParaSubir(nome="banner", dados=_png())],
        marketing_quadrada=[ImagemParaSubir(nome="quadrado", dados=_png())])
    ops, _ = display.construir("8017851692", b, login_customer_id="6016739364")
    # ⚠️ LISTA, e não conjunto. A primeira versão deste teste comparava
    # `set == set`, e por isso passaria se as duas imagens recebessem o MESMO
    # id temporário: `{-200} == {-200}`. Colisão de id é exatamente o defeito
    # que a faixa existe para evitar, e o teste que a guardava não a via.
    emitidos = [o.asset_operation.create.resource_name for o in ops
                if o._pb.WhichOneof("operation") == "asset_operation"]
    assert len(emitidos) == len(set(emitidos)), f"ids repetidos: {emitidos}"
    rda = [o for o in ops if o._pb.WhichOneof("operation") == "ad_group_ad_operation"
           ][0].ad_group_ad_operation.create.ad.responsive_display_ad
    referenciados = [i.asset for i in rda.marketing_images] + \
                    [i.asset for i in rda.square_marketing_images]
    assert len(referenciados) == len(set(referenciados)), \
        f"o anúncio referencia o mesmo id duas vezes: {referenciados}"
    assert sorted(referenciados) == sorted(emitidos), f"{referenciados} != {emitidos}"


def test_as_duas_formas_convivem_na_mesma_campanha():
    """Reaproveitar o que já existe e subir o que falta, no mesmo anúncio."""
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir
    CID = "8017851692"
    b = _brief_display(
        marketing=[f"customers/{CID}/assets/777"],
        marketing_quadrada=[ImagemParaSubir(nome="quadrado", dados=_png())])
    ops, r = display.construir(CID, b, login_customer_id="6016739364")
    assert r.ok, [str(a) for a in r.achados]
    assert sum(1 for o in ops if o._pb.WhichOneof("operation") == "asset_operation") == 1
    rda = [o for o in ops if o._pb.WhichOneof("operation") == "ad_group_ad_operation"
           ][0].ad_group_ad_operation.create.ad.responsive_display_ad
    assert rda.marketing_images[0].asset == f"customers/{CID}/assets/777"
    assert rda.square_marketing_images[0].asset.endswith("/-200")


def test_a_faixa_de_imagem_nao_invade_a_de_texto():
    """⚠️ Colisão de faixa é o defeito que não avisa.

    Os dois ids seriam válidos para a API; a referência apontaria para o asset
    errado e o erro, se viesse, falaria de outro recurso.
    """
    from volc_ads.campanha import comum
    ultimo_texto = comum.T_ASSET_BASE - comum.T_ASSET_MAX + 1
    assert ultimo_texto > comum.T_IMAGEM_BASE, "as faixas se tocam"
    with pytest.raises(ValueError, match="fora da faixa"):
        comum.temp_imagem("123", comum.T_IMAGEM_MAX)
    with pytest.raises(ValueError, match="fora da faixa"):
        comum.temp_asset("123", comum.T_ASSET_MAX)


def test_imagem_sem_bytes_e_sem_nome_e_recusada_na_construcao():
    from volc_ads.campanha.brief import ImagemParaSubir
    with pytest.raises(ValueError, match="sem bytes"):
        ImagemParaSubir(nome="x", dados=b"")
    with pytest.raises(ValueError, match="sem nome"):
        ImagemParaSubir(nome="   ", dados=b"x")


def test_medida_zero_e_recusada_dos_DOIS_lados_da_fronteira():
    """A invariante de `criativo.Asset` passa a valer também aqui.

    Até 27/08/2026 `Asset` recusava `largura=0` e `ImagemParaSubir` aceitava.
    Essa assimetria era o buraco por onde um medidor que devolvesse `0,0` em
    vez de `None,None` faria "não medi" virar "medi e deu zero" ao cruzar.
    """
    from volc_ads.campanha.brief import ImagemParaSubir, Linhagem
    for campo in ("largura", "altura"):
        with pytest.raises(ValueError, match="ausente é None, nunca 0"):
            ImagemParaSubir(nome="x", dados=b"x", **{campo: 0})
    # E do lado da linhagem, incluindo o peso.
    for campo in ("largura", "altura", "bytes_totais"):
        with pytest.raises(ValueError, match="ausente é None, nunca 0"):
            Linhagem(nome="x", papel="marketing", **{campo: 0})
    # `None` continua sendo aceito: é a resposta certa para "não medi".
    assert ImagemParaSubir(nome="x", dados=b"x").largura is None


def test_linhagem_recusa_datetime_em_quando():
    """GUARDA DE REGRESSÃO do recibo, e ela é específica de propósito.

    `Recibo.para_json()` é `asdict` e `_gravar` chama `json.dumps` SEM
    `default=`. Um `datetime` cru só estouraria na gravação do recibo — que
    acontece DENTRO do `with destravar(...)`, com a trava aberta e a requisição
    prestes a sair. Falhar aqui é falhar barato.

    ⚠️ O teste exige `TypeError` e confere a mensagem: um `except Exception`
    ficaria verde se a classe passasse a rejeitar por qualquer outro motivo.
    """
    from datetime import datetime
    from volc_ads.campanha.brief import Linhagem
    with pytest.raises(TypeError, match="precisa ser str ISO-8601"):
        Linhagem(nome="x", papel="marketing", quando=datetime(2026, 8, 27))
    # E a prova de que a guarda não é só cosmética: com `str`, serializa.
    import json
    ln = Linhagem(nome="x", papel="marketing", quando="2026-08-27T12:00:00+00:00")
    assert json.loads(json.dumps(ln.para_json()))["quando"].startswith("2026-08-27")


def test_linhagem_recusa_hash_sem_algoritmo_declarado():
    from volc_ads.campanha.brief import Linhagem
    with pytest.raises(ValueError, match="sem algoritmo declarado"):
        Linhagem(nome="x", papel="marketing", conteudo_hash="a" * 64)


def test_confirmada_e_derivada_e_viaja_no_json():
    """`confirmada` não é campo gravável — e `asdict` sozinho a perderia."""
    from volc_ads.campanha.brief import Linhagem
    magra = Linhagem.desconhecida("x", "marketing")
    assert magra.confirmada is False
    assert magra.para_json()["confirmada"] is False
    # Nenhum caminho permite gravar `confirmada=True` numa linhagem vazia.
    with pytest.raises(TypeError):
        Linhagem(nome="x", papel="marketing", confirmada=True)  # type: ignore[call-arg]

    cheia = Linhagem(
        nome="x", papel="marketing", identidade="cri_1",
        conteudo_hash="sha256:" + "f" * 64, motor="m", insumo="i",
        quando="2026-08-27T12:00:00+00:00", mime="image/png",
        largura=600, altura=314)
    assert cheia.confirmada is True
    assert cheia.para_json()["confirmada"] is True


def test_custo_ausente_e_None_e_nunca_zero():
    """`0.0` afirma que a imagem foi de graça; `None` diz que ninguém reportou."""
    from volc_ads.campanha.brief import Linhagem
    assert Linhagem.desconhecida("x", "marketing").custo_usd is None
    # Zero é uma medida legítima (um motor local realmente custa 0) e passa;
    # o que não passa é negativo, que não é ausência nem medida.
    assert Linhagem(nome="x", papel="marketing", custo_usd=0.0).custo_usd == 0.0
    with pytest.raises(ValueError, match="custo negativo"):
        Linhagem(nome="x", papel="marketing", custo_usd=-1.0)


def test_o_grafo_com_asset_inline_serializa_inteiro():
    """Prova de que o payload é enviável — sem enviá-lo."""
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir
    # ⚠️ NÃO importar `cliente` de `gads.client`: isso dribla a fixture
    # `_sem_credencial` deste arquivo e dispara um refresh de token OAuth
    # CONTRA A CONTA REAL a cada execução da suíte. Medido com socket
    # bloqueado: era o ÚNICO teste do repositório que alcançava a rede.
    # O shim local monta o mesmo proto, sem credencial nenhuma.
    cliente = lambda _login: _cliente_sem_rede()  # noqa: E731
    b = _brief_display(
        marketing=[ImagemParaSubir(nome="banner", dados=_png(200))],
        marketing_quadrada=[ImagemParaSubir(nome="quadrado", dados=_png(200))])
    ops, r = display.construir("8017851692", b, login_customer_id="6016739364")
    assert r.ok
    c = cliente("6016739364")
    req = c.get_type("MutateGoogleAdsRequest")
    req.customer_id = "8017851692"
    req.mutate_operations.extend(ops)
    req.validate_only = True
    assert type(req).pb(req).SerializeToString()


def test_search_no_pior_caso_declarado_nao_alcanca_a_faixa_de_imagem():
    """⚠️ Provar que a FUNÇÃO levanta não prova que a FAIXA é respeitada.

    A auditoria adversarial apontou: `test_a_faixa_de_imagem_nao_invade_a_de_texto`
    prova que `temp_asset()` recusa fora da faixa — e não que quem emite passa
    por ela. Se alguém subisse `sitelink_texto.max_itens` de 20 para 120 em
    `limites.yaml`, o construtor de Search emitiria `-220` e o teste continuaria
    verde.

    Este teste fecha o buraco pelo outro lado: pega os tetos REAIS declarados no
    YAML, soma o pior caso, e confirma que ele cabe na faixa de texto. Se um teto
    subir, esta prova cai — que é o comportamento que se quer.
    """
    from volc_ads.campanha import comum, conteudo
    t = conteudo.LIM["texto"]
    # Um asset por sitelink, um por callout, e UM só para o snippet — o snippet
    # é um asset com N valores dentro, não N assets. Ver `search.py`.
    pior = t["sitelink_texto"]["max_itens"] + t["callout"]["max_itens"] + 1
    assert pior <= comum.T_ASSET_MAX, (
        f"o pior caso de assets de texto é {pior} e a faixa comporta "
        f"{comum.T_ASSET_MAX}. O id {comum.T_ASSET_BASE - pior + 1} invadiria a "
        f"faixa de imagem ({comum.T_IMAGEM_BASE}) — e os dois ids são válidos "
        f"para a API, então a referência apontaria para o asset errado sem erro")
    ultimo = comum.temp_asset("123", pior - 1)
    assert int(ultimo.rsplit("/", 1)[1]) > comum.T_IMAGEM_BASE


def test_search_emite_asset_pela_guarda_e_nao_por_aritmetica_solta():
    """O produtor real tem de PASSAR pela guarda, não tê-la disponível."""
    import inspect
    from volc_ads.campanha import search
    fonte = inspect.getsource(search)
    assert "comum.temp_asset(" in fonte, (
        "search.py não usa comum.temp_asset() — a disciplina de faixa estaria "
        "escrita duas vezes e comparada nunca")
    assert 'comum.temp(cid, "assets"' not in fonte, (
        "search.py ainda emite id de asset por aritmética solta, contornando a "
        "guarda")


def test_imagem_sem_linhagem_avisa_e_nao_passa_calada():
    """Não ter passado pela ponte aparece no diário — nem erro, nem silêncio.

    ⚠️ Este teste perguntava "alguém mediu?" até 27/08/2026, e a pergunta
    envelheceu junto com a razão dela: `criativo/validacao.py` não tinha
    chamador de produção, então medida ausente era o único sinal disponível.
    Agora a ponte existe, e medida PRESENTE sem linhagem é o caso perigoso —
    alguém preencheu `largura`/`altura` à mão e nenhuma régua as julgou. Por
    isso a imagem que dispara o aviso aqui está *medida*.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir, Linhagem
    b = _brief_display(
        marketing=[ImagemParaSubir(
            nome="banner-a-mao", dados=_png(),
            mime="image/png", largura=600, altura=314)],
        marketing_quadrada=[ImagemParaSubir(
            nome="quadrado-da-ponte", dados=_png(),
            mime="image/png", largura=300, altura=300,
            linhagem=Linhagem(
                nome="quadrado-da-ponte", papel="marketing_quadrada",
                identidade="cri_abc", conteudo_hash="sha256:" + "a" * 64,
                motor="motor-de-teste", insumo="um prompt",
                quando="2026-08-27T12:00:00+00:00",
                mime="image/png", largura=300, altura=300))])
    _, r = display.construir("8017851692", b, login_customer_id="6016739364")
    assert r.ok, "não passar pela ponte é aviso, não erro"
    avisos = [a for a in r.achados if "sem linhagem" in str(getattr(a, "motivo", ""))]
    assert len(avisos) == 1, f"esperava 1 aviso, veio {len(avisos)}"
    assert "banner-a-mao" in str(avisos[0].valor)


def test_linhagem_incompleta_nao_se_faz_passar_por_confirmada():
    """Ter vindo da ponte não basta: procedência pela metade é dita pela metade."""
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir, Linhagem
    # Veio da ponte (linhagem existe) mas sem motor e sem insumo: não dá para
    # responder "o que produziu o criativo que performou?".
    manca = Linhagem(nome="banner-manco", papel="marketing",
                     identidade="cri_xyz", conteudo_hash="sha256:" + "b" * 64,
                     mime="image/png", largura=600, altura=314)
    assert not manca.confirmada
    b = _brief_display(
        marketing=[ImagemParaSubir(nome="banner-manco", dados=_png(),
                                   mime="image/png", largura=600, altura=314,
                                   linhagem=manca)],
        marketing_quadrada=[ImagemParaSubir(nome="q", dados=_png())])
    _, r = display.construir("8017851692", b, login_customer_id="6016739364")
    assert r.ok, "procedência incompleta é aviso, não erro"
    incompletas = [a for a in r.achados
                   if "linhagem incompleta" in str(getattr(a, "motivo", ""))]
    assert len(incompletas) == 1, f"esperava 1 aviso, veio {len(incompletas)}"


def test_a_ordem_das_linhagens_e_a_ordem_das_asset_operations():
    """A lista de linhagem casa 1:1, POSIÇÃO A POSIÇÃO, com o que sai no mutate.

    Este é o teste que impede o defeito mais caro desta fatia: a procedência
    deslocada. Se `linhagens()` e o construtor discordassem em uma posição, o
    recibo atribuiria o prompt da logo ao banner — e um rastro errado parece um
    rastro, então ninguém iria conferir.

    ⚠️ LISTA, não conjunto, e não `sorted`. Conjunto passaria com as posições
    trocadas; `sorted` passaria com qualquer permutação. Só a igualdade de
    listas prova ordem.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir, Linhagem

    def _img(nome, papel):
        return ImagemParaSubir(
            nome=nome, dados=_png(), mime="image/png", largura=600, altura=314,
            linhagem=Linhagem(nome=nome, papel=papel,
                              conteudo_hash="sha256:" + "c" * 64))

    b = _brief_display(
        marketing=[_img("m1", "marketing"), _img("m2", "marketing")],
        marketing_quadrada=[_img("q1", "marketing_quadrada")])
    b.imagens_display.logo = [_img("l1", "logo")]
    b.imagens_display.logo_quadrado = [_img("lq1", "logo_quadrado")]

    ops, r = display.construir("8017851692", b, login_customer_id="6016739364")
    assert r.ok, [str(a) for a in r.achados]

    nomes_no_payload = [
        o.asset_operation.create.name for o in ops
        if o._pb.WhichOneof("operation") == "asset_operation"
    ]
    nomes_na_linhagem = [ln.nome for ln in b.imagens_display.linhagens()]
    assert nomes_no_payload == nomes_na_linhagem, (
        f"ordem divergente:\n  payload  {nomes_no_payload}\n"
        f"  linhagem {nomes_na_linhagem}")
    # E a ordem é exatamente a canônica declarada em UM lugar só.
    assert nomes_no_payload == ["m1", "m2", "q1", "l1", "lq1"]


def test_resource_name_reaproveitado_nao_entra_na_linhagem():
    """`str` é asset que já existe: ele não nasce agora e não tem linhagem aqui.

    A subsequência importa: com forma mista, a linhagem tem de casar com as
    `asset_operation` na ordem, pulando os reaproveitados sem se desalinhar.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir, Linhagem
    CID = "8017851692"
    nova = ImagemParaSubir(
        nome="banner-novo", dados=_png(), mime="image/png",
        largura=600, altura=314,
        linhagem=Linhagem(nome="banner-novo", papel="marketing",
                          conteudo_hash="sha256:" + "d" * 64))
    b = _brief_display(
        marketing=[f"customers/{CID}/assets/999111", nova],
        marketing_quadrada=[ImagemParaSubir(
            nome="quadrado-novo", dados=_png(), mime="image/png",
            largura=300, altura=300,
            linhagem=Linhagem(nome="quadrado-novo", papel="marketing_quadrada",
                              conteudo_hash="sha256:" + "e" * 64))])
    ops, r = display.construir(CID, b, login_customer_id="6016739364")
    assert r.ok, [str(a) for a in r.achados]

    nomes_no_payload = [
        o.asset_operation.create.name for o in ops
        if o._pb.WhichOneof("operation") == "asset_operation"
    ]
    assert nomes_no_payload == ["banner-novo", "quadrado-novo"]
    assert [ln.nome for ln in b.imagens_display.linhagens()] == nomes_no_payload


def test_imagem_a_mao_no_meio_nao_desloca_a_linhagem_seguinte():
    """Sem linhagem entra como `desconhecida`, e a lista NÃO encurta.

    Pular a imagem sem linhagem faria a procedência da imagem seguinte deslizar
    para a posição dela. Este teste prova que a posição 0 continua sendo a
    imagem 0 — mesmo quando não se sabe nada sobre ela.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagemParaSubir, Linhagem
    b = _brief_display(
        marketing=[
            ImagemParaSubir(nome="anonima", dados=_png()),
            ImagemParaSubir(
                nome="rastreada", dados=_png(),
                linhagem=Linhagem(nome="rastreada", papel="marketing",
                                  motor="motor-de-teste")),
        ],
        marketing_quadrada=[ImagemParaSubir(nome="q", dados=_png())])
    ops, r = display.construir("8017851692", b, login_customer_id="6016739364")
    assert r.ok

    linhagens = b.imagens_display.linhagens()
    nomes_no_payload = [
        o.asset_operation.create.name for o in ops
        if o._pb.WhichOneof("operation") == "asset_operation"
    ]
    assert len(linhagens) == len(nomes_no_payload) == 3
    assert [ln.nome for ln in linhagens] == nomes_no_payload
    assert linhagens[0].motor is None and not linhagens[0].confirmada
    assert linhagens[1].motor == "motor-de-teste"


def test_a_ordem_canonica_dos_papeis_tem_um_dono_so():
    """`display` traduz papel→proto; quem declara a ORDEM é `ImagensDisplay`.

    ⚠️ A primeira versão deste teste comparava `PAPEIS_DE_IMAGEM` com
    `ImagensDisplay.PAPEIS` — e `PAPEIS_DE_IMAGEM` é CONSTRUÍDO a partir de
    `PAPEIS` (`display.py`), então a igualdade era verdadeira por construção e
    não podia falhar. A revisão adversarial de 27/08/2026 provou por mutação:
    reordenar `PAPEIS` derruba 6 testes, e este não estava entre eles.

    Agora a ordem é ancorada num LITERAL. Ele é a declaração independente
    contra a qual a fonte é conferida — sem ela, "as duas concordam" só diz
    que uma foi copiada da outra.
    """
    from volc_ads.campanha import display
    from volc_ads.campanha.brief import ImagensDisplay

    # A ordem do proto do `ResponsiveDisplayAdInfo`, escrita à mão de propósito.
    esperada = ["marketing", "marketing_quadrada", "logo", "logo_quadrado"]
    assert list(ImagensDisplay.PAPEIS) == esperada
    assert [p for p, _ in display.PAPEIS_DE_IMAGEM] == esperada
    # E a tradução cobre exatamente os papéis declarados — nem a mais, nem a menos.
    assert set(display._CAMPO_DO_PROTO) == set(ImagensDisplay.PAPEIS)
    assert [c for _, c in display.PAPEIS_DE_IMAGEM] == [
        "marketing_images", "square_marketing_images",
        "logo_images", "square_logo_images"]
