"""Provas das rotas V2: fronteira HTTP fechada, resumo honesto e zero criação.

O que estas provas cobram é a FRONTEIRA, não o compilador — a aritmética de
orçamento e público está provada em `test_meta_contrato_v2.py`. Aqui a pergunta
é outra: o que o navegador consegue mandar, o que ele recebe de volta, e o que
a rota se recusa a fazer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import meta_local, trafego_meta_validacao
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta_execucao import contrato_v2 as c2
from app.trafego.meta_execucao import publicos as mod_publicos
from app.trafego.meta_execucao import receitas
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta


INICIO = "2027-01-01T12:00:00Z"


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(trafego_meta_validacao.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub="operador-meta", email="admin@volc", papel="ADMIN", origem="sessao")
    return TestClient(app, headers={"host": "localhost"})


def _corpo(**troca: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "recipe_id": "TRAFFIC_WEBSITE_LPV_STATIC",
        "account_ref": "metaacct_exemplo",
        "page_ref": "metapage_exemplo",
        "campaign_name": "Campanha",
        "destination_url": "https://example.com/",
        "special_ad_categories": [],
        "special_categories_confirmed": True,
        "adsets": [
            {
                "adset_key": "principal",
                "name": "Conjunto principal",
                "start_time": INICIO,
                "audience": {
                    "mode": "BROAD",
                    "geo": {"countries": ["BR"]},
                    "expansion": False,
                },
                "budget": {"nivel": "ADSET", "periodo": "DAILY", "amount_minor": 1000},
            },
        ],
        "ads": [
            {
                "variation_key": "v1",
                "adset_key": "principal",
                "asset_ref": "metaasset_exemplo",
                "creative_name": "Criativo 1",
                "ad_name": "Anuncio 1",
                "message": "Mensagem",
                "headline": "Titulo",
                "description": "Descricao",
            },
        ],
    }
    base.update(troca)
    return base


# ── A fronteira HTTP fecha ───────────────────────────────────────────────────


def test_campo_desconhecido_vira_422_com_o_nome_do_campo() -> None:
    """`extra=forbid` também no V2: um campo que o servidor não conhece é 422.

    Sem isto, uma tela que passasse a enviar `objective` ou `bid_strategy`
    receberia 200 e o operador acreditaria ter escolhido algo que nunca saiu do
    navegador.
    """
    with pytest.raises(Exception):
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(
            _corpo(objective="OUTCOME_SALES"))


def test_expansao_advantage_e_obrigatoria_no_dto() -> None:
    """Omitir `expansion` não pode significar "não liguei": na Meta significa o oposto."""
    corpo = _corpo()
    del corpo["adsets"][0]["audience"]["expansion"]
    with pytest.raises(Exception):
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo)


def test_dto_traduz_para_o_contrato_puro_sem_perder_campo() -> None:
    pedido = trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(_corpo())
    plano = trafego_meta_validacao._plano_v2_do_pedido(pedido)
    assert plano.recipe_id == "TRAFFIC_WEBSITE_LPV_STATIC"
    assert plano.nivel_de_orcamento == receitas.ORCAMENTO_NO_CONJUNTO
    assert plano.conjuntos[0].adset_key == "principal"
    assert plano.conjuntos[0].publico.expansao_advantage is False
    assert plano.anuncios[0].adset_key == "principal"


def test_cbo_atravessa_o_dto_ate_o_contrato() -> None:
    corpo = _corpo(
        campaign_budget={"nivel": "CAMPAIGN", "periodo": "DAILY", "amount_minor": 5000})
    corpo["adsets"][0].pop("budget")
    pedido = trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo)
    plano = trafego_meta_validacao._plano_v2_do_pedido(pedido)
    assert plano.orcamento_e_da_campanha is True
    assert plano.nivel_de_orcamento == receitas.ORCAMENTO_NA_CAMPANHA


def test_orcamento_nos_dois_niveis_e_409_e_nao_500() -> None:
    """Erro de contrato é 409 com código, nunca um 500 sem nome."""
    corpo = _corpo(
        campaign_budget={"nivel": "CAMPAIGN", "periodo": "DAILY", "amount_minor": 5000})
    pedido = trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo)
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        trafego_meta_validacao._plano_v2_do_pedido(pedido)
    assert erro.value.codigo == "META_BUDGET_DUPLICATED"
    assert trafego_meta_validacao._erro(erro.value).status_code == 409


# ── Autoridade: nenhuma rota nova abre criação ou ativação ──────────────────


def test_o_v2_nao_acrescentou_rota_de_criacao_aprovacao_ou_ativacao() -> None:
    """`A45`: leitura/validação/upload não podem abrir criar/ativar."""
    paths = {route.path for route in trafego_meta_validacao.router.routes}
    assert "/api/trafego/meta/local/criacao/v2/compilar" in paths
    assert "/api/trafego/meta/local/criacao/v2/validar" in paths
    assert all("criar" not in path.rsplit("/", 1)[-1] for path in paths)
    assert all("aprovar" not in path for path in paths)
    assert all("ativar" not in path for path in paths)
    assert all("enable" not in path for path in paths)


def test_validate_only_v2_fechado_recusa_antes_de_ler_token(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.delenv("META_VALIDATE_ONLY_ENABLED", raising=False)
    monkeypatch.setattr(
        trafego_meta_validacao, "_credencial_salva",
        lambda *_: pytest.fail("nao deveria ler token"))
    resposta = _cliente().post("/api/trafego/meta/local/criacao/v2/validar", json={
        "confirmar_validate_only": True, "plano": _corpo()})
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_VALIDATE_ONLY_BLOCKED"


def test_validate_only_v2_sem_confirmacao_recusa(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_VALIDATE_ONLY_ENABLED", "1")
    monkeypatch.setattr(
        trafego_meta_validacao, "_credencial_salva",
        lambda *_: pytest.fail("nao deveria ler token"))
    resposta = _cliente().post("/api/trafego/meta/local/criacao/v2/validar", json={
        "confirmar_validate_only": False, "plano": _corpo()})
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_VALIDATE_ONLY_NOT_CONFIRMED"


# ── O catálogo de receitas diz a verdade sobre a prova ───────────────────────


def test_catalogo_de_receitas_expoe_o_nivel_de_prova(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    corpo = _cliente().get("/api/trafego/meta/local/criacao/v2/receitas").json()
    assert corpo["receita_padrao"] == "TRAFFIC_WEBSITE_LPV_STATIC"
    por_id = {item["id"]: item for item in corpo["receitas"]}
    assert por_id["TRAFFIC_WEBSITE_LPV_STATIC"]["criar_liberado"] is True
    # As receitas de conversão existem no catálogo E declaram que criar está
    # fechado, com o motivo. Uma receita apresentada como disponível e recusada
    # pela rota é pior do que uma receita ausente.
    for identificador in ("WEB_SALES_CONVERSION", "WEB_LEADS_CONVERSION"):
        assert por_id[identificador]["criar_liberado"] is False
        assert por_id[identificador]["motivo_sem_prova"]
    # Modos de orçamento carregam prova PRÓPRIA: o ABO diário foi aceito, os
    # outros três não.
    modos = {m["id"]: m for m in por_id["TRAFFIC_WEBSITE_LPV_STATIC"]["modos_de_orcamento"]}
    assert modos["ADSET_DAILY"]["criar_liberado"] is True
    assert modos["CAMPAIGN_DAILY"]["criar_liberado"] is False


def test_catalogo_nao_promete_limite_da_meta_como_se_fosse_oficial(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    corpo = _cliente().get("/api/trafego/meta/local/criacao/v2/receitas").json()
    assert "produto" in corpo["limites"]["classificacao"]
    assert "produto" in corpo["idade"]["motivo"]


# ── O resumo é derivado do contrato, não do rascunho ────────────────────────


def _plano(**troca: Any) -> c2.PlanoMetaV2:
    return trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(_corpo(**troca)))


def test_resumo_diz_onde_a_verba_mora() -> None:
    resumo = trafego_meta_validacao._resumo_v2(_plano())
    assert resumo["orcamento"]["onde_a_verba_mora"] == "em cada conjunto (ABO)"
    corpo = _corpo(
        campaign_budget={"nivel": "CAMPAIGN", "periodo": "DAILY", "amount_minor": 5000})
    corpo["adsets"][0].pop("budget")
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    assert trafego_meta_validacao._resumo_v2(plano)["orcamento"][
        "onde_a_verba_mora"] == "na campanha (CBO)"


def test_resumo_nao_promete_alcance_exclusivo_com_expansao_ligada() -> None:
    """`A16`: com Advantage+ a seleção é sugestão, e a tela não pode dizer o contrário."""
    corpo = _corpo()
    corpo["adsets"][0]["audience"] = {
        "mode": "EXISTING_CUSTOM",
        "geo": {"countries": ["BR"]},
        "include_custom_refs": ["metaobj_aaaaaaaaaaaaaaaaaaaaaaaa"],
        "expansion": True,
    }
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    conjunto = trafego_meta_validacao._resumo_v2(plano)["conjuntos"][0]
    assert conjunto["expansao_advantage"] is True
    assert conjunto["promete_alcance_exclusivo"] is False

    corpo["adsets"][0]["audience"]["expansion"] = False
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    assert trafego_meta_validacao._resumo_v2(plano)["conjuntos"][0][
        "promete_alcance_exclusivo"] is True


def test_resumo_lista_o_mapa_anuncio_para_conjunto() -> None:
    corpo = _corpo()
    corpo["adsets"].append({
        "adset_key": "secundario", "name": "Conjunto secundario", "start_time": INICIO,
        "audience": {"mode": "BROAD", "geo": {"countries": ["BR"]}, "expansion": False},
        "budget": {"nivel": "ADSET", "periodo": "DAILY", "amount_minor": 2000},
    })
    corpo["ads"].append({
        "variation_key": "v2", "adset_key": "secundario",
        "asset_ref": "metaasset_exemplo", "creative_name": "Criativo 2",
        "ad_name": "Anuncio 2", "message": "Mensagem 2", "headline": "Titulo 2",
        "description": "Descricao 2",
    })
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    conjuntos = trafego_meta_validacao._resumo_v2(plano)["conjuntos"]
    assert {c["adset_key"]: c["anuncios"] for c in conjuntos} == {
        "principal": ["v1"], "secundario": ["v2"]}


def test_resumo_declara_os_bloqueios_para_criar() -> None:
    corpo = _corpo(
        campaign_budget={"nivel": "CAMPAIGN", "periodo": "DAILY", "amount_minor": 5000})
    corpo["adsets"][0].pop("budget")
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    assert trafego_meta_validacao._resumo_v2(plano)["bloqueios_para_criar"]
    assert not trafego_meta_validacao._resumo_v2(_plano())["bloqueios_para_criar"]


# ── Resolução de referências: barata quando nada foi escolhido ──────────────


class _CatalogoQueContaChamadas:
    def __init__(self, mapa: dict[tuple[str, str], str] | None = None) -> None:
        self.chamadas = 0
        self._mapa = mapa or {}

    async def descobrir_contas(self, segredo: Any) -> tuple[Any, ...]:
        class _Conta:
            referencia_opaca = "metaacct_exemplo"
            id_externo = "123456789"
        return (_Conta(),)

    async def resolver_ids_por_referencia(
        self, conta_externa: str, tipo: str, referencias: list[str], segredo: Any,
    ) -> dict[str, str]:
        self.chamadas += 1
        return {
            ref: self._mapa[(tipo, ref)]
            for ref in referencias if (tipo, ref) in self._mapa
        }


@pytest.mark.anyio
async def test_publico_amplo_nao_custa_nenhuma_leitura_de_catalogo() -> None:
    """Compilar sem seleção continua sendo um ato local e barato."""
    catalogo = _CatalogoQueContaChamadas()
    resolvidas = await mod_publicos.resolver_referencias_de_publico(
        None, plano=_plano(), account_ref="metaacct_exemplo",
        segredo=None, catalogo=catalogo)
    assert catalogo.chamadas == 0
    assert resolvidas.custom_audience_ids == {}


@pytest.mark.anyio
async def test_publico_de_outra_conta_nao_resolve() -> None:
    """`A13`: o isolamento vem de a lista ser da conta certa, não de um `if`."""
    corpo = _corpo()
    corpo["adsets"][0]["audience"] = {
        "mode": "EXISTING_CUSTOM", "geo": {"countries": ["BR"]},
        "include_custom_refs": ["metaobj_deoutracontaxxxxxxxx"], "expansion": False,
    }
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    catalogo = _CatalogoQueContaChamadas(mapa={})
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await mod_publicos.resolver_referencias_de_publico(
            None, plano=plano, account_ref="metaacct_exemplo",
            segredo=None, catalogo=catalogo)
    assert erro.value.codigo == "META_AUDIENCE_REFERENCE_UNRESOLVED"


@pytest.mark.anyio
async def test_publico_da_conta_resolve_para_o_id_do_provedor() -> None:
    corpo = _corpo()
    corpo["adsets"][0]["audience"] = {
        "mode": "EXISTING_CUSTOM", "geo": {"countries": ["BR"]},
        "include_custom_refs": ["metaobj_aaaaaaaaaaaaaaaaaaaaaaaa"], "expansion": False,
    }
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    catalogo = _CatalogoQueContaChamadas(
        mapa={("custom_audience", "metaobj_aaaaaaaaaaaaaaaaaaaaaaaa"): "778899"})
    resolvidas = await mod_publicos.resolver_referencias_de_publico(
        None, plano=plano, account_ref="metaacct_exemplo",
        segredo=None, catalogo=catalogo)
    assert resolvidas.publico("metaobj_aaaaaaaaaaaaaaaaaaaaaaaa") == "778899"


@pytest.mark.anyio
async def test_conta_fora_da_credencial_nao_resolve() -> None:
    corpo = _corpo()
    corpo["adsets"][0]["audience"] = {
        "mode": "EXISTING_CUSTOM", "geo": {"countries": ["BR"]},
        "include_custom_refs": ["metaobj_aaaaaaaaaaaaaaaaaaaaaaaa"], "expansion": False,
    }
    corpo["account_ref"] = "metaacct_deoutroator"
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await mod_publicos.resolver_referencias_de_publico(
            None, plano=plano, account_ref="metaacct_deoutroator",
            segredo=None, catalogo=_CatalogoQueContaChamadas())
    assert erro.value.codigo == "META_ACCOUNT_REFERENCE_UNRESOLVED"


@pytest.mark.anyio
async def test_conversao_apenas_para_relatorio_nao_custa_leitura() -> None:
    """Uma fonte escolhida para VER não vira `promoted_object` — nem leitura."""
    corpo = _corpo()
    corpo["adsets"][0]["measurement"] = {
        "purpose": "REPORT_ONLY", "source_kind": "PIXEL",
        "source_ref": "metaobj_pixelaaaaaaaaaaaaaaaa",
    }
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    catalogo = _CatalogoQueContaChamadas()
    await mod_publicos.resolver_referencias_de_publico(
        None, plano=plano, account_ref="metaacct_exemplo",
        segredo=None, catalogo=catalogo)
    assert catalogo.chamadas == 0


@pytest.mark.anyio
async def test_segmentacao_detalhada_e_idioma_sao_lacuna_nomeada() -> None:
    """Sem catálogo provado, a recusa é explícita — não um id adivinhado."""
    corpo = _corpo()
    corpo["adsets"][0]["audience"] = {
        "mode": "MANUAL", "geo": {"countries": ["BR"]},
        "interest_refs": ["metaobj_interesseaaaaaaaaa"], "expansion": False,
    }
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await mod_publicos.resolver_referencias_de_publico(
            None, plano=plano, account_ref="metaacct_exemplo",
            segredo=None, catalogo=_CatalogoQueContaChamadas())
    assert erro.value.codigo == "META_AUDIENCE_CATALOG_NOT_PROVEN"


@pytest.mark.anyio
async def test_catalogo_sem_o_leitor_diz_isso_em_vez_de_dizer_nao_encontrado() -> None:
    """"não sei ler" e "não é seu" são causas opostas e mensagens diferentes."""
    corpo = _corpo()
    corpo["adsets"][0]["audience"] = {
        "mode": "EXISTING_CUSTOM", "geo": {"countries": ["BR"]},
        "include_custom_refs": ["metaobj_aaaaaaaaaaaaaaaaaaaaaaaa"], "expansion": False,
    }
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))

    class _SemLeitor:
        async def descobrir_contas(self, segredo: Any) -> tuple[Any, ...]:
            class _Conta:
                referencia_opaca = "metaacct_exemplo"
                id_externo = "123456789"
            return (_Conta(),)

    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await mod_publicos.resolver_referencias_de_publico(
            None, plano=plano, account_ref="metaacct_exemplo",
            segredo=None, catalogo=_SemLeitor())
    assert erro.value.codigo == "META_CATALOG_READER_UNAVAILABLE"


# ── T12: a ficha do canário ─────────────────────────────────────────────────


def _compilado_falso(sha: str = "f" * 64):
    class _Op:
        tipo_objeto = "creative"
        payload = {"url_tags": (
            "utm_source=meta&utm_medium=paid_social"
            "&utm_campaign={{campaign.id}}&campaign_id={{campaign.id}}")}

    class _Compilado:
        plano_sha256 = sha
        operacoes = (_Op(),)

    return _Compilado()


def test_ficha_declara_que_nada_foi_criado_ao_gera_la() -> None:
    ficha = c2.ficha_de_canario(_plano(), _compilado_falso())
    assert ficha["estado"] == "CANARY_AUTHORIZATION_REQUIRED"
    assert ficha["efeito_desta_ficha"] == "NENHUM"
    assert ficha["objetos_criados"] == 0
    assert ficha["autorizado"] is False


def test_ficha_nao_carrega_identificador_real_do_provedor() -> None:
    """Uma ficha é feita para ser copiada para um chat ou ticket."""
    import json

    texto = json.dumps(c2.ficha_de_canario(_plano(), _compilado_falso()))
    assert "act_" not in texto
    # As referências que viajam são as opacas que o navegador já tinha.
    assert "metaacct_exemplo" in texto


def test_sem_recibo_de_validacao_a_ficha_lista_a_lacuna() -> None:
    ficha = c2.ficha_de_canario(_plano(), _compilado_falso(), prova_de_validacao=None)
    assert any("recibo durável" in item for item in ficha["provas_faltantes"])

    ficha_com = c2.ficha_de_canario(
        _plano(), _compilado_falso(), prova_de_validacao={"registrada": True})
    assert not any("recibo durável" in item for item in ficha_com["provas_faltantes"])


def test_plano_maior_que_o_canario_e_apontado_como_lacuna() -> None:
    """Um plano de dois conjuntos não é inválido — ele só não é o canário."""
    corpo = _corpo()
    corpo["adsets"].append({
        "adset_key": "segundo", "name": "Segundo", "start_time": INICIO,
        "audience": {"mode": "BROAD", "geo": {"countries": ["BR"]}, "expansion": False},
        "budget": {"nivel": "ADSET", "periodo": "DAILY", "amount_minor": 2000},
    })
    corpo["ads"].append({
        "variation_key": "v2", "adset_key": "segundo", "asset_ref": "metaasset_exemplo",
        "creative_name": "C2", "ad_name": "A2", "message": "m", "headline": "h",
        "description": "d",
    })
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    ficha = c2.ficha_de_canario(
        plano, _compilado_falso(), prova_de_validacao={"registrada": True})
    assert any("primeiro canário" in item for item in ficha["provas_faltantes"])


def test_as_quatro_camadas_de_prova_ficam_separadas() -> None:
    """`A44`: roots não prova dependentes, nem expansão, nem receita."""
    ficha = c2.ficha_de_canario(_plano(), _compilado_falso())
    camadas = {item["id"]: item for item in ficha["tracking"]["camadas"]}
    assert set(camadas) == {
        "COMPILADO_LOCAL", "ROOTS_REMOTO", "EXPANSAO_REAL", "RECEITA_NO_GAM"}
    assert "conjunto" in camadas["ROOTS_REMOTO"]["nao_prova"]
    assert "macro" in camadas["ROOTS_REMOTO"]["nao_prova"]
    assert "receita" in camadas["ROOTS_REMOTO"]["nao_prova"]
    # As duas últimas dependem de entrega real, e a ficha diz isso.
    assert "autorização separada" in camadas["EXPANSAO_REAL"]["exige"]
    assert "autorização separada" in camadas["RECEITA_NO_GAM"]["exige"]


def test_a_ficha_pede_o_hash_exato_do_plano() -> None:
    ficha = c2.ficha_de_canario(_plano(), _compilado_falso(sha="a" * 64))
    assert ficha["pedido"]["plano_sha256"] == "a" * 64
    assert ficha["pedido"]["estado_ao_nascer"] == "PAUSED"


def test_a_rota_da_ficha_nao_cria_nem_valida_remotamente() -> None:
    paths = {rota.path for rota in trafego_meta_validacao.router.routes}
    assert "/api/trafego/meta/local/criacao/v2/canario/ficha" in paths
    # A ficha é um documento; ela não ganhou uma rota de execução irmã.
    assert all("canario/criar" not in path for path in paths)
    assert all("canario/executar" not in path for path in paths)


def test_ficha_em_abo_nao_mostra_o_orcamento_de_um_conjunto_como_o_do_pedido() -> None:
    """A ficha é o documento sobre o qual alguém assina — o número tem de ser o certo.

    ⚠️ Antes, `conjuntos[0].orcamento` fazia a ficha pedir autorização para o
    orçamento do PRIMEIRO conjunto enquanto o plano autorizava a soma de todos.
    """
    corpo = _corpo()
    corpo["adsets"].append({
        "adset_key": "segundo", "name": "Segundo", "start_time": INICIO,
        "audience": {"mode": "BROAD", "geo": {"countries": ["BR"]}, "expansion": False},
        "budget": {"nivel": "ADSET", "periodo": "DAILY", "amount_minor": 2000},
    })
    corpo["ads"].append({
        "variation_key": "v2", "adset_key": "segundo", "asset_ref": "metaasset_exemplo",
        "creative_name": "C2", "ad_name": "A2", "message": "m", "headline": "h",
        "description": "d",
    })
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    orcamento = c2.ficha_de_canario(plano, _compilado_falso())["pedido"]["orcamento"]
    assert orcamento["escopo"] == "CONJUNTOS_ABO"
    assert orcamento["total_minor"] == 3000  # 1000 + 2000, não 1000
    assert len(orcamento["por_conjunto"]) == 2
    assert "soma de 2 conjunto" in orcamento["rotulo_do_total"]


def test_ficha_em_cbo_rotula_o_escopo_da_verba() -> None:
    corpo = _corpo(
        campaign_budget={"nivel": "CAMPAIGN", "periodo": "DAILY", "amount_minor": 5000})
    corpo["adsets"][0].pop("budget")
    plano = trafego_meta_validacao._plano_v2_do_pedido(
        trafego_meta_validacao.PedidoPlanoMetaV2.model_validate(corpo))
    orcamento = c2.ficha_de_canario(plano, _compilado_falso())["pedido"]["orcamento"]
    assert orcamento["escopo"] == "CAMPANHA_CBO"
    assert orcamento["amount_minor"] == 5000
