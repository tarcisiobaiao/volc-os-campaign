"""Provas do contrato V2: paridade com o V1, união de orçamento e público.

A prova central é a PRIMEIRA: para a mesma campanha, o compilador V2 emite os
mesmos payloads que o V1. Sem ela, "versionar o contrato" seria só uma forma
elegante de escrever um segundo compilador que diverge em silêncio — e o preço
apareceria numa conta real, não aqui.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.trafego.meta_execucao import contrato_v2 as c2
from app.trafego.meta_execucao import receitas
from app.trafego.meta_execucao.compilador import (
    compilar_plano_pausado,
    compilar_plano_v2,
)
from app.trafego.meta_execucao.contrato import (
    ErroDeNascimentoMeta,
    ManifestoSupplyMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
    VariacaoEstaticaMeta,
)


INICIO = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
ASSET = "metaasset_0123456789ab"
CONTA = "metaacct_0123456789ab"
PAGINA = "metapage_0123456789ab"
URL = "https://focogenial.com/"


def _manifesto(asset_ref: str = ASSET) -> ManifestoSupplyMeta:
    return ManifestoSupplyMeta(
        asset_ref=asset_ref,
        content_sha256="a" * 64,
        item_sha256="b" * 64,
        supply_sha256="c" * 64,
        policy_receipt_ref="metapolicy_" + "0" * 24,
        policy_state="CLEAR",
        policy_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        lifecycle="READY_FOR_PAID_MEDIA",
        provider_image_hash="hash_da_peca_01",
        mime_type="image/jpeg",
        width=1080,
        height=1080,
        byte_size=123456,
    )


def _referencias(asset_refs: tuple[str, ...] = (ASSET,)) -> ReferenciasMetaResolvidas:
    return ReferenciasMetaResolvidas(
        account_id="1234567890",
        page_id="9876543210",
        image_hash="hash_da_peca_01",
        image_hashes_by_ref={ref: "hash_da_peca_01" for ref in asset_refs},
        page_permission_proven=True,
        placement_identity_mode="FACEBOOK_ONLY_PAGE_PROVEN",
        asset_supply_manifests={ref: _manifesto(ref) for ref in asset_refs},
    )


def _variacao(chave: str = "v1") -> VariacaoEstaticaMeta:
    return VariacaoEstaticaMeta(
        variation_key=chave,
        creative_name=f"Criativo {chave}",
        ad_name=f"Anuncio {chave}",
        asset_ref=ASSET,
        message="mensagem do anuncio",
        headline="titulo",
        description="descricao",
    )


def _plano_v1() -> PlanoMetaPausado:
    return PlanoMetaPausado(
        account_ref=CONTA,
        campaign_name="VOLC · Meta · Trafego",
        adset_name="Brasil · Amplo",
        creative_name="Criativo v1",
        ad_name="Anuncio v1",
        destination_url=URL,
        page_ref=PAGINA,
        asset_ref=ASSET,
        message="mensagem do anuncio",
        headline="titulo",
        description="descricao",
        daily_budget_minor=1000,
        start_time=INICIO,
        special_ad_categories=(),
        special_categories_confirmed=True,
        is_adset_budget_sharing_enabled=False,
        variacoes_estaticas=(_variacao(),),
    )


#: Sentinela para distinguir "não passei orçamento" de "passei None de
#: propósito, porque este conjunto é CBO e não pode ter verba".
SEM_ORCAMENTO = object()


def _conjunto(
    chave: str = "principal",
    *,
    orcamento: object = SEM_ORCAMENTO,
    publico: c2.PublicoMeta | None = None,
    mensuracao: c2.MensuracaoMeta | None = None,
    fim: datetime | None = None,
    nome: str | None = None,
) -> c2.ConjuntoMeta:
    return c2.ConjuntoMeta(
        adset_key=chave,
        nome=nome or "Brasil · Amplo",
        programacao=c2.ProgramacaoMeta(start_time=INICIO, end_time=fim),
        publico=publico or c2.PublicoMeta(
            modo=c2.PUBLICO_AMPLO, geografia=c2.GeografiaMeta(countries=("BR",))),
        mensuracao=mensuracao or c2.MensuracaoMeta(),
        orcamento=c2.OrcamentoMeta(
            nivel=receitas.ORCAMENTO_NO_CONJUNTO,
            periodo=receitas.PERIODO_DIARIO,
            amount_minor=1000,
        ) if orcamento is SEM_ORCAMENTO else orcamento,
    )


def _plano_v2(**troca) -> c2.PlanoMetaV2:
    base = dict(
        recipe_id=receitas.RECEITA_PADRAO,
        account_ref=CONTA,
        page_ref=PAGINA,
        campaign_name="VOLC · Meta · Trafego",
        destination_url=URL,
        conjuntos=(_conjunto(),),
        anuncios=(c2.AnuncioMeta(variacao=_variacao(), adset_key="principal"),),
        special_categories_confirmed=True,
    )
    base.update(troca)
    return c2.PlanoMetaV2(**base)


# ── Paridade V1 ↔ V2 ────────────────────────────────────────────────────────


def test_v2_emite_os_mesmos_payloads_que_o_v1_para_a_mesma_campanha() -> None:
    """A prova que autoriza as duas versões a coexistirem."""
    referencias = _referencias()
    antigo = compilar_plano_pausado(_plano_v1(), referencias)
    novo = compilar_plano_v2(_plano_v2(), referencias)

    por_tipo_v1 = {op.tipo_objeto: op for op in antigo.operacoes}
    por_tipo_v2 = {op.tipo_objeto: op for op in novo.operacoes}
    assert set(por_tipo_v1) == set(por_tipo_v2) == {"campaign", "adset", "creative", "ad"}

    assert por_tipo_v2["campaign"].payload == por_tipo_v1["campaign"].payload
    assert por_tipo_v2["creative"].payload == por_tipo_v1["creative"].payload
    # O AdSet difere apenas no que a identidade estável exige: o V1 não tem
    # `adset_key`, então o Ad dele aponta para `$adset.id` e o V2 para
    # `$adset:principal.id`. Todo o resto — verba, lance, targeting, horário —
    # tem de ser idêntico, e é isso que a comparação abaixo cobra.
    assert por_tipo_v2["adset"].payload == por_tipo_v1["adset"].payload
    assert por_tipo_v2["ad"].payload["name"] == por_tipo_v1["ad"].payload["name"]
    assert por_tipo_v2["ad"].payload["status"] == "PAUSED"


def test_v1_continua_compilando_sem_tocar_no_v2() -> None:
    """O caminho legado não passou a depender do módulo novo."""
    compilado = compilar_plano_pausado(_plano_v1(), _referencias())
    assert [op.chave for op in compilado.operacoes] == [
        "campaign", "adset", "creative:v1", "ad:v1"]


# ── F04/F06: a união discriminada de orçamento ──────────────────────────────


def test_abo_emite_verba_no_conjunto_e_nunca_na_campanha() -> None:
    compilado = compilar_plano_v2(_plano_v2(), _referencias())
    campanha = next(op for op in compilado.operacoes if op.tipo_objeto == "campaign")
    conjunto = next(op for op in compilado.operacoes if op.tipo_objeto == "adset")
    assert "daily_budget" not in campanha.payload
    assert "lifetime_budget" not in campanha.payload
    assert "bid_strategy" not in campanha.payload
    assert conjunto.payload["daily_budget"] == 1000
    assert conjunto.payload["bid_strategy"] == "LOWEST_COST_WITHOUT_CAP"


def test_cbo_emite_verba_e_lance_na_campanha_e_nenhum_no_conjunto() -> None:
    plano = _plano_v2(
        conjuntos=(_conjunto(orcamento=None),),
        orcamento_campanha=c2.OrcamentoMeta(
            nivel=receitas.ORCAMENTO_NA_CAMPANHA,
            periodo=receitas.PERIODO_DIARIO,
            amount_minor=5000,
        ),
    )
    compilado = compilar_plano_v2(plano, _referencias())
    campanha = next(op for op in compilado.operacoes if op.tipo_objeto == "campaign")
    conjunto = next(op for op in compilado.operacoes if op.tipo_objeto == "adset")
    assert campanha.payload["daily_budget"] == 5000
    assert campanha.payload["bid_strategy"] == "LOWEST_COST_WITHOUT_CAP"
    assert "daily_budget" not in conjunto.payload
    assert "lifetime_budget" not in conjunto.payload
    assert "bid_strategy" not in conjunto.payload


def test_orcamento_nos_dois_niveis_e_recusado_antes_de_compilar() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(
            orcamento_campanha=c2.OrcamentoMeta(
                nivel=receitas.ORCAMENTO_NA_CAMPANHA,
                periodo=receitas.PERIODO_DIARIO,
                amount_minor=5000,
            ),
        )
    assert erro.value.codigo == "META_BUDGET_DUPLICATED"


def test_abo_sem_verba_em_um_dos_conjuntos_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(conjuntos=(_conjunto(orcamento=None),))
    assert erro.value.codigo == "META_BUDGET_REQUIRED"


def test_lifetime_exige_data_de_termino() -> None:
    total = c2.OrcamentoMeta(
        nivel=receitas.ORCAMENTO_NO_CONJUNTO,
        periodo=receitas.PERIODO_TOTAL,
        amount_minor=50000,
    )
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _conjunto(orcamento=total)
    assert erro.value.codigo == "META_SCHEDULE_END_REQUIRED"

    conjunto = _conjunto(orcamento=total, fim=INICIO + timedelta(days=7))
    compilado = compilar_plano_v2(_plano_v2(conjuntos=(conjunto,)), _referencias())
    adset = next(op for op in compilado.operacoes if op.tipo_objeto == "adset")
    assert adset.payload["lifetime_budget"] == 50000
    assert adset.payload["end_time"].startswith("2026-09-17")


def test_fim_antes_do_inicio_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.ProgramacaoMeta(start_time=INICIO, end_time=INICIO - timedelta(hours=1))
    assert erro.value.codigo == "META_SCHEDULE_INVALID"


def test_start_sem_fuso_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.ProgramacaoMeta(start_time=datetime(2026, 9, 10, 12, 0))
    assert erro.value.codigo == "META_SCHEDULE_INVALID"


def test_valor_em_reais_como_float_nao_atravessa() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.OrcamentoMeta(
            nivel=receitas.ORCAMENTO_NO_CONJUNTO,
            periodo=receitas.PERIODO_DIARIO,
            amount_minor=10.0,  # type: ignore[arg-type]
        )
    assert erro.value.codigo == "META_BUDGET_INVALID"


# ── F10/F34: identidade estável e mapa anúncio→conjunto ─────────────────────


def test_multiplos_conjuntos_mantem_chave_apos_reordenar() -> None:
    a = _conjunto("alpha", nome="Alpha")
    b = _conjunto("beta", nome="Beta")
    anuncios = (
        c2.AnuncioMeta(variacao=_variacao("v1"), adset_key="alpha"),
        c2.AnuncioMeta(variacao=_variacao("v2"), adset_key="beta"),
    )
    direto = compilar_plano_v2(
        _plano_v2(conjuntos=(a, b), anuncios=anuncios), _referencias())
    invertido = compilar_plano_v2(
        _plano_v2(conjuntos=(b, a), anuncios=tuple(reversed(anuncios))), _referencias())

    def mapa(compilado):
        return {
            op.chave: op.payload.get("adset_id")
            for op in compilado.operacoes if op.tipo_objeto == "ad"
        }

    assert mapa(direto) == mapa(invertido) == {
        "ad:v1": "$adset:alpha.id", "ad:v2": "$adset:beta.id"}
    # Reordenar muda a ordem das operações — mas não a identidade de nenhuma.
    assert {op.chave for op in direto.operacoes} == {op.chave for op in invertido.operacoes}


def test_anuncio_apontando_para_conjunto_inexistente_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(anuncios=(c2.AnuncioMeta(variacao=_variacao(), adset_key="fantasma"),))
    assert erro.value.codigo == "META_AD_ADSET_UNKNOWN"


def test_conjunto_sem_anuncio_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(
            conjuntos=(_conjunto("alpha", nome="Alpha"), _conjunto("beta", nome="Beta")),
            anuncios=(c2.AnuncioMeta(variacao=_variacao(), adset_key="alpha"),),
        )
    assert erro.value.codigo == "META_ADSET_WITHOUT_AD"


def test_dependencias_do_anuncio_citam_o_conjunto_certo() -> None:
    a = _conjunto("alpha", nome="Alpha")
    b = _conjunto("beta", nome="Beta")
    compilado = compilar_plano_v2(
        _plano_v2(
            conjuntos=(a, b),
            anuncios=(
                c2.AnuncioMeta(variacao=_variacao("v1"), adset_key="alpha"),
                c2.AnuncioMeta(variacao=_variacao("v2"), adset_key="beta"),
            ),
        ),
        _referencias(),
    )
    dependencias = {op.chave: op.depende_de for op in compilado.operacoes}
    assert dependencias["ad:v1"] == ("adset:alpha", "creative:v1")
    assert dependencias["ad:v2"] == ("adset:beta", "creative:v2")
    assert dependencias["adset:alpha"] == ("campaign",)


def test_todo_objeto_nasce_pausado() -> None:
    compilado = compilar_plano_v2(_plano_v2(), _referencias())
    for op in compilado.operacoes:
        if op.tipo_objeto == "creative":
            # AdCreative é entidade de biblioteca: PAUSED nunca foi esperado.
            assert "status" not in op.payload
        else:
            assert op.payload["status"] == "PAUSED"


# ── F12..F20: público ───────────────────────────────────────────────────────


def test_publicos_incluidos_e_excluidos_chegam_ao_payload_resolvidos() -> None:
    publico = c2.PublicoMeta(
        modo=c2.PUBLICO_PERSONALIZADO,
        geografia=c2.GeografiaMeta(countries=("BR",)),
        incluir_custom_refs=("metaaud_incluido01",),
        excluir_custom_refs=("metaaud_excluido1",),
    )
    resolvidos = c2.ReferenciasDePublicoResolvidas(
        custom_audience_ids={"metaaud_incluido01": "111", "metaaud_excluido1": "222"})
    compilado = compilar_plano_v2(
        _plano_v2(conjuntos=(_conjunto(publico=publico),)), _referencias(), resolvidos)
    alvo = next(op for op in compilado.operacoes if op.tipo_objeto == "adset").payload["targeting"]
    assert alvo["custom_audiences"] == [{"id": "111"}]
    assert alvo["excluded_custom_audiences"] == [{"id": "222"}]


def test_publico_nao_resolvido_recusa_antes_de_emitir() -> None:
    publico = c2.PublicoMeta(
        modo=c2.PUBLICO_PERSONALIZADO,
        geografia=c2.GeografiaMeta(countries=("BR",)),
        incluir_custom_refs=("metaaud_deoutraconta",),
    )
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        compilar_plano_v2(
            _plano_v2(conjuntos=(_conjunto(publico=publico),)), _referencias())
    assert erro.value.codigo == "META_AUDIENCE_REFERENCE_UNRESOLVED"


def test_mesmo_publico_incluido_e_excluido_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.PublicoMeta(
            modo=c2.PUBLICO_PERSONALIZADO,
            geografia=c2.GeografiaMeta(countries=("BR",)),
            incluir_custom_refs=("metaaud_mesmo0001",),
            excluir_custom_refs=("metaaud_mesmo0001",),
        )
    assert erro.value.codigo == "META_AUDIENCE_INCLUDE_EXCLUDE_CONFLICT"


def test_exclusao_geografica_chega_ao_payload() -> None:
    geo = c2.GeografiaMeta(countries=("BR",), excluded_city_keys=("264443",))
    publico = c2.PublicoMeta(modo=c2.PUBLICO_AMPLO, geografia=geo)
    compilado = compilar_plano_v2(
        _plano_v2(conjuntos=(_conjunto(publico=publico),)), _referencias())
    alvo = next(op for op in compilado.operacoes if op.tipo_objeto == "adset").payload["targeting"]
    assert alvo["excluded_geo_locations"] == {"cities": [{"key": "264443"}]}


def test_texto_livre_nao_vira_chave_de_geografia() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.GeografiaMeta(countries=("BR",), city_keys=("São Paulo",))
    assert erro.value.codigo == "META_GEO_KEY_INVALID"


def test_geografia_sem_nenhuma_inclusao_e_recusada() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.GeografiaMeta()
    assert erro.value.codigo == "META_GEO_INCLUDE_REQUIRED"


@pytest.mark.parametrize(
    "argumentos",
    [
        {"latitude": 999.0, "longitude": 0.0, "radius": 10},
        {"latitude": float("nan"), "longitude": 0.0, "radius": 10},
        {"latitude": 0.0, "longitude": 0.0, "radius": 0},
        {"latitude": 0.0, "longitude": 0.0, "radius": 10, "distance_unit": "parsec"},
    ],
)
def test_raio_invalido_e_recusado(argumentos) -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.LocalizacaoPorRaio(**argumentos)
    assert erro.value.codigo == "META_GEO_RADIUS_INVALID"


def test_raio_valido_chega_ao_payload() -> None:
    geo = c2.GeografiaMeta(custom_locations=(
        c2.LocalizacaoPorRaio(latitude=-23.55, longitude=-46.63, radius=15),))
    publico = c2.PublicoMeta(modo=c2.PUBLICO_MANUAL, geografia=geo)
    compilado = compilar_plano_v2(
        _plano_v2(conjuntos=(_conjunto(publico=publico),)), _referencias())
    alvo = next(op for op in compilado.operacoes if op.tipo_objeto == "adset").payload["targeting"]
    assert alvo["geo_locations"]["custom_locations"] == [
        {"latitude": -23.55, "longitude": -46.63, "radius": 15, "distance_unit": "kilometer"}]


def test_expansao_advantage_viaja_sempre_explicita() -> None:
    for ligado in (True, False):
        publico = c2.PublicoMeta(
            modo=c2.PUBLICO_AMPLO,
            geografia=c2.GeografiaMeta(countries=("BR",)),
            expansao_advantage=ligado,
        )
        compilado = compilar_plano_v2(
            _plano_v2(conjuntos=(_conjunto(publico=publico),)), _referencias())
        alvo = next(
            op for op in compilado.operacoes if op.tipo_objeto == "adset").payload["targeting"]
        assert alvo["targeting_automation"] == {"advantage_audience": 1 if ligado else 0}


def test_expansao_ligada_derruba_a_promessa_de_alcance_exclusivo() -> None:
    """`A16`: a tela não pode prometer o que o provedor não garante."""
    base = dict(
        modo=c2.PUBLICO_PERSONALIZADO,
        geografia=c2.GeografiaMeta(countries=("BR",)),
        incluir_custom_refs=("metaaud_incluido01",),
    )
    assert c2.PublicoMeta(**base, expansao_advantage=False).promete_alcance_exclusivo is True
    assert c2.PublicoMeta(**base, expansao_advantage=True).promete_alcance_exclusivo is False


def test_publico_amplo_nao_aceita_publico_personalizado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.PublicoMeta(
            modo=c2.PUBLICO_AMPLO,
            geografia=c2.GeografiaMeta(countries=("BR",)),
            incluir_custom_refs=("metaaud_incluido01",),
        )
    assert erro.value.codigo == "META_AUDIENCE_MODE_CONFLICT"


def test_faixa_etaria_fora_do_produto_e_recusada() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.PublicoMeta(
            modo=c2.PUBLICO_AMPLO,
            geografia=c2.GeografiaMeta(countries=("BR",)),
            idade_min=13,
        )
    assert erro.value.codigo == "META_TARGETING_INVALID"


# ── F21: posicionamentos ────────────────────────────────────────────────────


def test_facebook_only_nao_se_amplia_sozinho() -> None:
    compilado = compilar_plano_v2(_plano_v2(), _referencias())
    alvo = next(op for op in compilado.operacoes if op.tipo_objeto == "adset").payload["targeting"]
    assert alvo["publisher_platforms"] == ["facebook"]


def test_instagram_sem_identidade_bloqueia_o_plano() -> None:
    conjunto = c2.ConjuntoMeta(
        adset_key="principal",
        nome="Com Instagram",
        programacao=c2.ProgramacaoMeta(start_time=INICIO),
        publico=c2.PublicoMeta(
            modo=c2.PUBLICO_AMPLO, geografia=c2.GeografiaMeta(countries=("BR",))),
        posicionamentos=c2.PosicionamentosMeta(
            modo=c2.POSICIONAMENTO_MANUAL, plataformas=("facebook", "instagram")),
        orcamento=c2.OrcamentoMeta(
            nivel=receitas.ORCAMENTO_NO_CONJUNTO,
            periodo=receitas.PERIODO_DIARIO,
            amount_minor=1000,
        ),
    )
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(conjuntos=(conjunto,))
    assert erro.value.codigo == "META_INSTAGRAM_IDENTITY_REQUIRED"


def test_plataforma_fora_do_vocabulario_e_recusada() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.PosicionamentosMeta(modo=c2.POSICIONAMENTO_MANUAL, plataformas=("orkut",))
    assert erro.value.codigo == "META_PLACEMENT_PLATFORM_UNKNOWN"


# ── F22..F25: mensuração ────────────────────────────────────────────────────


def test_relatar_conversao_nao_muda_o_payload_do_conjunto() -> None:
    """`A19`: escolher um KPI para VER não pode mudar o que a campanha otimiza."""
    sem = compilar_plano_v2(_plano_v2(), _referencias())
    com = compilar_plano_v2(
        _plano_v2(conjuntos=(_conjunto(mensuracao=c2.MensuracaoMeta(
            proposito=receitas.MENSURACAO_RELATORIO,
            source_kind=c2.FONTE_PIXEL,
            source_ref="metapixel_0123456789",
        )),)),
        _referencias(),
    )
    alvo_sem = next(op for op in sem.operacoes if op.tipo_objeto == "adset").payload
    alvo_com = next(op for op in com.operacoes if op.tipo_objeto == "adset").payload
    assert "promoted_object" not in alvo_com
    assert alvo_sem == alvo_com


def test_traffic_nao_admite_otimizar_por_conversao() -> None:
    medida = c2.MensuracaoMeta(
        proposito=receitas.MENSURACAO_OTIMIZACAO,
        source_kind=c2.FONTE_PIXEL,
        source_ref="metapixel_0123456789",
        standard_event="PURCHASE",
    )
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(conjuntos=(_conjunto(mensuracao=medida),))
    assert erro.value.codigo == "META_MEASUREMENT_PURPOSE_NOT_IN_RECIPE"


def test_receita_de_conversao_emite_promoted_object_resolvido() -> None:
    medida = c2.MensuracaoMeta(
        proposito=receitas.MENSURACAO_OTIMIZACAO,
        source_kind=c2.FONTE_PIXEL,
        source_ref="metapixel_0123456789",
        standard_event="PURCHASE",
    )
    plano = _plano_v2(
        recipe_id="WEB_SALES_CONVERSION", conjuntos=(_conjunto(mensuracao=medida),))
    resolvidos = c2.ReferenciasDePublicoResolvidas(
        measurement_source_ids={"metapixel_0123456789": "555"})
    compilado = compilar_plano_v2(plano, _referencias(), resolvidos)
    adset = next(op for op in compilado.operacoes if op.tipo_objeto == "adset").payload
    campanha = next(op for op in compilado.operacoes if op.tipo_objeto == "campaign").payload
    assert adset["promoted_object"] == {"pixel_id": "555", "custom_event_type": "PURCHASE"}
    assert adset["optimization_goal"] == "OFFSITE_CONVERSIONS"
    assert campanha["objective"] == "OUTCOME_SALES"


def test_conversao_personalizada_e_evento_padrao_juntos_sao_recusados() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.MensuracaoMeta(
            proposito=receitas.MENSURACAO_OTIMIZACAO,
            source_kind=c2.FONTE_PIXEL,
            source_ref="metapixel_0123456789",
            standard_event="PURCHASE",
            custom_conversion_ref="metacc_0123456789",
        )
    assert erro.value.codigo == "META_MEASUREMENT_EVENT_AMBIGUOUS"


def test_otimizar_sem_fonte_e_recusado() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        c2.MensuracaoMeta(proposito=receitas.MENSURACAO_OTIMIZACAO)
    assert erro.value.codigo == "META_MEASUREMENT_SOURCE_REQUIRED"


def test_receita_de_conversao_exige_otimizacao_declarada() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(recipe_id="WEB_LEADS_CONVERSION")
    assert erro.value.codigo == "META_MEASUREMENT_REQUIRED_BY_RECIPE"


def test_conversao_personalizada_emite_o_par_correto() -> None:
    medida = c2.MensuracaoMeta(
        proposito=receitas.MENSURACAO_OTIMIZACAO,
        source_kind=c2.FONTE_PIXEL,
        source_ref="metapixel_0123456789",
        custom_conversion_ref="metacc_0123456789ab",
    )
    plano = _plano_v2(
        recipe_id="WEB_SALES_CONVERSION", conjuntos=(_conjunto(mensuracao=medida),))
    resolvidos = c2.ReferenciasDePublicoResolvidas(
        measurement_source_ids={"metapixel_0123456789": "555"},
        custom_conversion_ids={"metacc_0123456789ab": "777"},
    )
    adset = next(
        op for op in compilar_plano_v2(plano, _referencias(), resolvidos).operacoes
        if op.tipo_objeto == "adset").payload
    assert adset["promoted_object"] == {"pixel_id": "555", "custom_conversion_id": "777"}


# ── Receitas e bloqueios honestos ───────────────────────────────────────────


def test_receita_desconhecida_e_recusada_antes_de_qualquer_rede() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(recipe_id="RECEITA_INVENTADA")
    assert erro.value.codigo == "META_RECIPE_UNKNOWN"


def test_receita_sem_prova_remota_bloqueia_criar_mas_nao_compilar() -> None:
    medida = c2.MensuracaoMeta(
        proposito=receitas.MENSURACAO_OTIMIZACAO,
        source_kind=c2.FONTE_PIXEL,
        source_ref="metapixel_0123456789",
        standard_event="LEAD",
    )
    plano = _plano_v2(
        recipe_id="WEB_LEADS_CONVERSION", conjuntos=(_conjunto(mensuracao=medida),))
    resolvidos = c2.ReferenciasDePublicoResolvidas(
        measurement_source_ids={"metapixel_0123456789": "555"})
    assert compilar_plano_v2(plano, _referencias(), resolvidos).operacoes
    bloqueios = plano.bloqueios_para_criar()
    assert bloqueios and "elegibilidade" in bloqueios[0]


def test_cbo_bloqueia_criar_enquanto_nao_houver_prova_da_conta() -> None:
    plano = _plano_v2(
        conjuntos=(_conjunto(orcamento=None),),
        orcamento_campanha=c2.OrcamentoMeta(
            nivel=receitas.ORCAMENTO_NA_CAMPANHA,
            periodo=receitas.PERIODO_DIARIO,
            amount_minor=5000,
        ),
    )
    assert plano.bloqueios_para_criar()
    assert not _plano_v2().bloqueios_para_criar()


def test_compartilhamento_de_verba_nao_e_ligado_pelo_cbo() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(is_adset_budget_sharing_enabled=True)
    assert erro.value.codigo == "META_BUDGET_SHARING_REQUIRES_PROVEN_RECIPE"


def test_limites_operacionais_do_produto() -> None:
    conjuntos = tuple(
        _conjunto(f"c{i}", nome=f"Conjunto {i}") for i in range(c2.MAX_CONJUNTOS + 1))
    anuncios = tuple(
        c2.AnuncioMeta(variacao=_variacao(f"v{i}"), adset_key=f"c{i}")
        for i in range(c2.MAX_CONJUNTOS + 1))
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano_v2(conjuntos=conjuntos, anuncios=anuncios)
    assert erro.value.codigo == "META_ADSET_LIMIT_EXCEEDED"
