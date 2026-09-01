"""A leitura da meta efetiva, exercida OFFLINE contra os protos reais da v25.

## Por que os protos reais, e não dublês de conveniência

`contas.py` não tem um único teste offline: ele importa `buscar` dentro do corpo
de cada função, e a única forma de exercitá-lo sem rede seria monkeypatchar o
módulo do engine — coisa que nenhum teste da casa faz. O resultado é que a
leitura de metas nunca foi provada; ela só foi USADA.

Aqui a função de busca entra por parâmetro, e as linhas devolvidas são
`GoogleAdsRow`-like montadas com os **tipos reais** do SDK v25. Isso importa por
um motivo concreto: `conversion_action.primary_for_goal` tem *presence*, e é a
presença que separa "o Google trata como primária" de "a API declarou não
primária". Um `SimpleNamespace` responderia qualquer coisa a `HasField` e a
prova mediria o dublê, não o contrato.

⚠️ Nenhum teste daqui abre socket. A prova de que a leitura funciona não pode
depender da conta de um cliente responder hoje o mesmo que ontem.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.trafego import metas_efetivas as mef  # noqa: E402
from app.trafego import plano_mensuracao as pm  # noqa: E402

pytest.importorskip("google.ads.googleads")

from google.ads.googleads.v25.resources.types import (  # noqa: E402
    campaign_conversion_goal as cpg,
)
from google.ads.googleads.v25.resources.types import (  # noqa: E402
    conversion_action as ca,
)
from google.ads.googleads.v25.resources.types import (  # noqa: E402
    conversion_goal_campaign_config as cgcc,
)
from google.ads.googleads.v25.resources.types import (  # noqa: E402
    customer as cust,
)
from google.ads.googleads.v25.resources.types import (  # noqa: E402
    customer_conversion_goal as ccg,
)

CONTA = "5478096539"
MCC = "6016739364"
CAMPANHA = "24195821946"


# ═══════════════════════════════════════════════════════════════════════════
# Linhas reais da v25
# ═══════════════════════════════════════════════════════════════════════════


def _linha_meta_da_conta(categoria, origem, biddable):
    m = ccg.CustomerConversionGoal()
    m.category = categoria
    m.origin = origem
    m.biddable = biddable
    return SimpleNamespace(customer_conversion_goal=m)


def _linha_meta_da_campanha(categoria, origem, biddable):
    m = cpg.CampaignConversionGoal()
    m.campaign = f"customers/{CONTA}/campaigns/{CAMPANHA}"
    m.category = categoria
    m.origin = origem
    m.biddable = biddable
    return SimpleNamespace(campaign_conversion_goal=m)


def _linha_nivel(nivel, custom=""):
    c = cgcc.ConversionGoalCampaignConfig()
    c.campaign = f"customers/{CONTA}/campaigns/{CAMPANHA}"
    c.goal_config_level = nivel
    if custom:
        c.custom_conversion_goal = custom
    return SimpleNamespace(conversion_goal_campaign_config=c)


def _linha_acao(*, id=7466919994, nome="Compra no site", categoria="PURCHASE",
                origem="WEBSITE", tipo="WEBPAGE", status="ENABLED",
                primaria=True, owner=CONTA):
    a = ca.ConversionAction()
    a.id = id
    a.name = nome
    a.resource_name = f"customers/{owner}/conversionActions/{id}"
    if owner:
        a.owner_customer = f"customers/{owner}"
    a.category = categoria
    a.origin = origem
    a.type_ = tipo
    a.status = status
    # ⚠️ `primaria=None` deixa o campo AUSENTE de propósito. É o caso em que a
    # doc manda tratar como `true`, e é o que o dublê de conveniência não sabe
    # reproduzir.
    if primaria is not None:
        a.primary_for_goal = primaria
    return SimpleNamespace(conversion_action=a)


def _linha_frescor(id=7466919994, data="2026-08-30"):
    a = ca.ConversionAction()
    a.id = id
    metrics = SimpleNamespace(conversion_last_conversion_date=data)
    return SimpleNamespace(conversion_action=a, metrics=metrics)


def _linha_conta(*, auto_tagging=True, tracking_id="17862729897",
                 dono=CONTA, status="CONVERSION_TRACKING_MANAGED_BY_SELF",
                 termos=True):
    c = cust.Customer()
    c.id = int(CONTA)
    c.auto_tagging_enabled = auto_tagging
    c.conversion_tracking_setting.conversion_tracking_id = int(tracking_id)
    c.conversion_tracking_setting.google_ads_conversion_customer = (
        f"customers/{dono}")
    c.conversion_tracking_setting.conversion_tracking_status = status
    c.conversion_tracking_setting.accepted_customer_data_terms = termos
    return SimpleNamespace(customer=c)


def _buscar(mapa):
    """Um `buscar` que responde por CONSULTA — e falha se pedirem outra coisa.

    ⚠️ Casar pelo texto da consulta, e não pela ordem das chamadas. Um dublê que
    responde na ordem passa a mentir no dia em que alguém reordenar as leituras,
    e mente devolvendo dado plausível — que é o pior jeito de mentir.
    """
    def fn(customer_id, query, *, login_customer_id, **_kw):
        assert customer_id == CONTA
        assert login_customer_id == MCC
        for marca, resposta in mapa.items():
            if marca in query:
                if isinstance(resposta, Exception):
                    raise resposta
                return list(resposta)
        raise AssertionError(f"consulta inesperada: {query.strip()[:80]}")
    return fn


# ═══════════════════════════════════════════════════════════════════════════
# 1. As três leituras que decidem a meta efetiva
# ═══════════════════════════════════════════════════════════════════════════


def test_le_as_tres_e_o_nivel_governa():
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("PURCHASE", "WEBSITE", True),
            _linha_meta_da_conta("DOWNLOAD", "APP", False),
        ],
        "FROM conversion_goal_campaign_config": [_linha_nivel("CUSTOMER")],
        "FROM campaign_conversion_goal": [
            _linha_meta_da_campanha("SIGNUP", "WEBSITE", True)],
    })
    m = mef.ler_meta_efetiva(CONTA, login_customer_id=MCC,
                             campaign_id=CAMPANHA, buscar=buscar)
    assert m.nivel == "CUSTOMER"
    assert m.nivel_decidido is True
    # ⚠️ A meta de campanha EXISTE no recurso e NÃO decide. Foi exatamente este
    # o caso medido na 24195821946.
    biddable = m.metas_biddable
    assert biddable is not None
    assert [x.semantica for x in biddable] == ["PURCHASE/WEBSITE"]


def test_com_nivel_campaign_a_campanha_decide():
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("PURCHASE", "WEBSITE", True)],
        "FROM conversion_goal_campaign_config": [_linha_nivel("CAMPAIGN")],
        "FROM campaign_conversion_goal": [
            _linha_meta_da_campanha("DOWNLOAD", "APP", True)],
    })
    m = mef.ler_meta_efetiva(CONTA, login_customer_id=MCC,
                             campaign_id=CAMPANHA, buscar=buscar)
    assert [x.semantica for x in (m.metas_biddable or ())] == ["DOWNLOAD/APP"]


def test_o_filtro_da_campanha_e_por_resource_name():
    """`conversion_goal_campaign_config.campaign` é RESOURCE_NAME, filtrável.

    ⚠️ Filtrar por `campaign.id` funcionaria por atribuição, e depender disso
    seria depender de um caminho que a página do recurso não promete.
    """
    vistas = []

    def fn(customer_id, query, *, login_customer_id, **_kw):
        vistas.append(query)
        return []

    mef.ler_nivel(CONTA, CAMPANHA, login_customer_id=MCC, buscar=fn)
    assert f"customers/{CONTA}/campaigns/{CAMPANHA}" in vistas[0]
    assert "conversion_goal_campaign_config.campaign =" in vistas[0]


def test_antes_do_nascimento_a_meta_da_campanha_e_inelegivel_e_nao_vazia():
    """⚠️ `vazio_confirmado` afirmaria que a campanha existe e não tem meta."""
    estado, metas, causa = mef.ler_metas_da_campanha(
        CONTA, None, login_customer_id=MCC, buscar=_buscar({}))
    assert estado == pm.INELEGIVEL
    assert metas == ()
    assert "ainda não existe" in (causa or "")


def test_antes_do_nascimento_o_nivel_herdado_e_dito_em_voz_alta():
    """A herança documentada é APLICADA, e a resposta diz que foi inferida."""
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("PURCHASE", "WEBSITE", True)],
    })
    m = mef.ler_meta_efetiva(CONTA, login_customer_id=MCC, campaign_id=None,
                             buscar=buscar)
    assert m.nivel == pm.NIVEL_CUSTOMER
    assert m.nivel_decidido is True
    assert "ainda não nasceu" in (m.causa or ""), m.causa
    assert m.metas_da_campanha_estado == pm.INELEGIVEL


def test_nivel_fora_do_enum_vira_nao_suportado_e_nao_desconhecido():
    """Um valor fora do enum é um contrato que mudou embaixo de nós."""
    c = cgcc.ConversionGoalCampaignConfig()
    c.campaign = f"customers/{CONTA}/campaigns/{CAMPANHA}"
    linha = SimpleNamespace(
        conversion_goal_campaign_config=SimpleNamespace(
            goal_config_level=SimpleNamespace(name="CONTA"),
            custom_conversion_goal=""))
    estado, nivel, custom, causa = mef.ler_nivel(
        CONTA, CAMPANHA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_goal_campaign_config": [linha]}))
    assert estado == pm.NAO_SUPORTADO
    assert nivel is None
    assert "CONTA" in (causa or "")


def test_custom_conversion_goal_vazio_nao_vira_meta_customizada():
    """⚠️ Um resource name não setado chega como STRING VAZIA, não como `None`.

    Sem o `or None`, `""` viajaria como "há meta customizada" e travaria toda
    campanha normal com um bloqueio inventado.
    """
    estado, nivel, custom, _ = mef.ler_nivel(
        CONTA, CAMPANHA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_goal_campaign_config":
                        [_linha_nivel("CUSTOMER")]}))
    assert estado == pm.COM_DADOS
    assert custom is None


def test_custom_conversion_goal_preenchido_atravessa_ate_o_plano():
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("PURCHASE", "WEBSITE", True)],
        "FROM conversion_goal_campaign_config": [
            _linha_nivel("CAMPAIGN",
                         custom=f"customers/{CONTA}/customConversionGoals/9")],
        "FROM campaign_conversion_goal": [],
    })
    m = mef.ler_meta_efetiva(CONTA, login_customer_id=MCC,
                             campaign_id=CAMPANHA, buscar=buscar)
    assert m.usa_meta_customizada is True
    assert m.metas_que_mandam is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Falha de uma leitura NÃO apaga as outras
# ═══════════════════════════════════════════════════════════════════════════


def test_uma_consulta_que_explode_nao_derruba_as_outras():
    """O defeito do router, que colapsava tudo num `metas = None`.

    Uma falha na consulta nova apagaria a leitura antiga que tinha funcionado —
    tudo-ou-nada, em que uma leitura parcialmente bem-sucedida vira ignorância
    total.
    """
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("PURCHASE", "WEBSITE", True)],
        "FROM conversion_goal_campaign_config": RuntimeError("a API recusou"),
        "FROM campaign_conversion_goal": [],
    })
    m = mef.ler_meta_efetiva(CONTA, login_customer_id=MCC,
                             campaign_id=CAMPANHA, buscar=buscar)
    assert m.metas_da_conta_estado == pm.COM_DADOS
    assert len(m.metas_da_conta) == 1, "a leitura boa foi apagada pela ruim"
    assert m.nivel_estado == pm.FALHOU
    assert "não completou" in (m.causa or "")


def test_falha_e_vazio_confirmado_sao_estados_diferentes():
    vazio, metas_v, causa_v = mef.ler_metas_da_conta(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM customer_conversion_goal": []}))
    falhou, metas_f, causa_f = mef.ler_metas_da_conta(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM customer_conversion_goal": RuntimeError("boom")}))
    assert vazio == pm.VAZIO_CONFIRMADO and causa_v is None
    assert falhou == pm.FALHOU and causa_f
    assert metas_v == metas_f == ()
    assert vazio != falhou, (
        "uma conta sem meta e uma rede instável viraram a mesma coisa")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Ações: dono, id numérico e o tri-estado de `primary_for_goal`
# ═══════════════════════════════════════════════════════════════════════════


def test_primary_for_goal_ausente_no_proto_real_chega_como_none():
    """⚠️ Contra o descritor REAL. É esta prova que impede alguém de "otimizar"
    a leitura para `bool(a.primary_for_goal)`, que devolveria `False` para uma
    ação que o Google trata como primária."""
    estado, acoes, _ = mef.ler_acoes(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_action":
                        [_linha_acao(primaria=None)]}))
    assert estado == pm.COM_DADOS
    assert acoes[0].primaria is None
    assert acoes[0].primaria_efetiva is True


def test_primary_for_goal_declarado_falso_chega_como_falso():
    _, acoes, _ = mef.ler_acoes(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_action":
                        [_linha_acao(primaria=False)]}))
    assert acoes[0].primaria is False
    assert acoes[0].primaria_efetiva is False


def test_o_dono_e_extraido_do_resource_name_do_owner_customer():
    _, acoes, _ = mef.ler_acoes(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_action":
                        [_linha_acao(owner="1234567890")]}))
    assert acoes[0].owner_customer_id == "1234567890"


def test_acao_definida_pelo_sistema_chega_sem_dono_e_nao_com_dono_errado():
    """> "or null if this is a system-defined conversion action"

    ⚠️ Cair para o `customer_id` da consulta seria o palpite confortável — e
    mandaria a conversão offline para a conta errada, em silêncio.
    """
    _, acoes, _ = mef.ler_acoes(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_action": [_linha_acao(owner="")]}))
    assert acoes[0].owner_customer_id is None
    assert pm.resolver_destino(acoes[0]).resolvido is False


def test_os_enums_chegam_pelo_NOME_e_nunca_pelo_numero():
    """⚠️ Um `2` no lugar de `PURCHASE` casaria com nada na semântica e
    produziria "nenhuma ação corresponde" — um veredito errado com cara de
    leitura correta."""
    _, acoes, _ = mef.ler_acoes(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_action": [_linha_acao()]}))
    a = acoes[0]
    assert a.categoria == "PURCHASE"
    assert a.origem == "WEBSITE"
    assert a.tipo == "WEBPAGE"
    assert a.status == "ENABLED"
    assert a.semantica == "PURCHASE/WEBSITE"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Frescor — o campo oficial, e os três desfechos que não se confundem
# ═══════════════════════════════════════════════════════════════════════════


def test_frescor_com_data_conta_os_dias_a_partir_de_hoje_injetado():
    """⚠️ `hoje` entra por parâmetro. Sem ele, um teste que fixasse a data da
    conversão passaria hoje e falharia amanhã."""
    acao = pm.AcaoDeConversao(
        id="7466919994",
        resource_name=f"customers/{CONTA}/conversionActions/7466919994",
        owner_customer_id=CONTA, nome="x", categoria="PURCHASE",
        origem="WEBSITE", tipo="WEBPAGE", status="ENABLED", primaria=True)
    f = mef.ler_frescor(
        CONTA, acao, login_customer_id=MCC, hoje="2026-09-01",
        buscar=_buscar({"metrics.conversion_last_conversion_date":
                        [_linha_frescor(data="2026-08-30")]}))
    assert f.estado == pm.COM_DADOS
    assert f.ultima_conversao_em == "2026-08-30"
    assert f.dias_desde_a_ultima == 2
    assert f.comprovado is True


def test_frescor_sem_hoje_nao_inventa_a_distancia():
    acao = pm.AcaoDeConversao(
        id="7466919994", resource_name="customers/1/conversionActions/7466919994",
        owner_customer_id=CONTA, nome="x", categoria="PURCHASE",
        origem="WEBSITE", tipo="WEBPAGE", status="ENABLED", primaria=True)
    f = mef.ler_frescor(
        CONTA, acao, login_customer_id=MCC,
        buscar=_buscar({"metrics.conversion_last_conversion_date":
                        [_linha_frescor()]}))
    assert f.dias_desde_a_ultima is None, (
        "inventou uma distância sem saber a partir de quando contar")


def test_campo_de_frescor_vazio_e_zero_MEDIDO_e_nao_ignorancia():
    """A API diz "nunca houve conversão para esta ação", e isso é conclusão."""
    acao = pm.AcaoDeConversao(
        id="7466919994", resource_name="customers/1/conversionActions/7466919994",
        owner_customer_id=CONTA, nome="x", categoria="PURCHASE",
        origem="WEBSITE", tipo="WEBPAGE", status="ENABLED", primaria=True)
    f = mef.ler_frescor(
        CONTA, acao, login_customer_id=MCC, hoje="2026-09-01",
        buscar=_buscar({"metrics.conversion_last_conversion_date":
                        [_linha_frescor(data="")]}))
    assert f.estado == pm.VAZIO_CONFIRMADO
    assert f.conversoes_na_janela == 0.0
    assert f.comprovado is False


def test_acao_ausente_do_relatorio_e_inelegivel_e_nao_zero():
    """⚠️ Não aparecer no relatório é diferente de ter recebido zero."""
    acao = pm.AcaoDeConversao(
        id="999", resource_name="customers/1/conversionActions/999",
        owner_customer_id=CONTA, nome="x", categoria="PURCHASE",
        origem="WEBSITE", tipo="WEBPAGE", status="ENABLED", primaria=True)
    f = mef.ler_frescor(
        CONTA, acao, login_customer_id=MCC, hoje="2026-09-01",
        buscar=_buscar({"metrics.conversion_last_conversion_date":
                        [_linha_frescor(id=111)]}))
    assert f.estado == pm.INELEGIVEL
    assert f.conversoes_na_janela is None


def test_sem_acao_eleita_o_frescor_e_inelegivel_e_diz_por_que():
    f = mef.ler_frescor(CONTA, None, login_customer_id=MCC,
                        buscar=_buscar({}))
    assert f.estado == pm.INELEGIVEL
    assert "sem sujeito" in (f.causa or "")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Marcação — o dono do tracking e as fontes derivadas de leitura
# ═══════════════════════════════════════════════════════════════════════════


def test_le_o_dono_do_tracking_e_nao_presume_a_conta_da_campanha():
    inv = mef.ler_marcacao(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM customer": [_linha_conta(dono="1234567890")]}))
    assert inv.estado == pm.COM_DADOS
    assert inv.conversion_tracking_owner_id == "1234567890"
    assert inv.auto_tagging is True
    assert inv.aceitou_termos_de_dados is True


def test_marcacao_nao_deriva_fontes_de_uma_lista_que_ninguem_leu():
    """⚠️ `()` aqui seria lido como "esta conta não tem tag nem GA4" — uma
    afirmação sobre o mundo a partir do que não se olhou."""
    inv = mef.ler_marcacao(
        CONTA, login_customer_id=MCC, acoes=(), acoes_estado=pm.NAO_COLETADO,
        buscar=_buscar({"FROM customer": [_linha_conta()]}))
    assert inv.acoes_com_tag == ()
    assert inv.acoes_de_ga4 == ()


def test_com_as_acoes_lidas_a_tag_e_o_ga4_sao_inventariados():
    _, acoes, _ = mef.ler_acoes(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM conversion_action": [
            _linha_acao(id=1, tipo="WEBPAGE"),
            _linha_acao(id=2, tipo="GOOGLE_ANALYTICS_4_PURCHASE"),
            _linha_acao(id=3, tipo="UPLOAD_CLICKS"),
        ]}))
    inv = mef.ler_marcacao(
        CONTA, login_customer_id=MCC, acoes=acoes, acoes_estado=pm.COM_DADOS,
        buscar=_buscar({"FROM customer": [_linha_conta()]}))
    assert inv.acoes_com_tag == ("1",)
    assert inv.acoes_de_ga4 == ("2",)


def test_marcacao_que_falha_nao_vira_conta_sem_auto_tagging():
    inv = mef.ler_marcacao(
        CONTA, login_customer_id=MCC,
        buscar=_buscar({"FROM customer": RuntimeError("boom")}))
    assert inv.estado == pm.FALHOU
    assert inv.auto_tagging is None, (
        "uma falha de leitura virou 'esta conta não usa auto-tagging'")


# ═══════════════════════════════════════════════════════════════════════════
# 6. O plano inteiro, de ponta a ponta e offline
# ═══════════════════════════════════════════════════════════════════════════


def test_ler_plano_monta_o_caso_completo_sem_tocar_a_rede():
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("PURCHASE", "WEBSITE", True)],
        "FROM conversion_goal_campaign_config": [_linha_nivel("CUSTOMER")],
        "FROM campaign_conversion_goal": [
            _linha_meta_da_campanha("PURCHASE", "WEBSITE", True)],
        "FROM conversion_action\n    WHERE conversion_action.status !=":
            [_linha_acao()],
        "metrics.conversion_last_conversion_date": [_linha_frescor()],
        "FROM customer": [_linha_conta()],
    })
    p = mef.ler_plano(CONTA, login_customer_id=MCC, campaign_id=CAMPANHA,
                      hoje="2026-09-01", buscar=buscar)
    assert p.completo is True, p.bloqueadores
    assert p.acao_alvo is not None and p.acao_alvo.id == "7466919994"
    assert p.destino.resolvido is True
    assert p.destino.operating_account_id == CONTA
    assert p.destino.product_destination_id == "7466919994"
    assert p.bloqueadores == ()


def test_ler_plano_reproduz_o_caso_medido_na_conta_real():
    """A conta em que o objetivo existe e nenhuma ação primária o mede.

    Medido ao vivo em 01/09/2026 na Portal Mundo Mais: `goal_config_level =
    CUSTOMER`, única meta biddable DOWNLOAD/APP, e a única ação dessa semântica
    com `primary_for_goal = false` declarado.
    """
    buscar = _buscar({
        "FROM customer_conversion_goal": [
            _linha_meta_da_conta("DOWNLOAD", "APP", True),
            _linha_meta_da_conta("PURCHASE", "WEBSITE", False),
        ],
        "FROM conversion_goal_campaign_config": [_linha_nivel("CUSTOMER")],
        "FROM campaign_conversion_goal": [],
        "FROM conversion_action\n    WHERE conversion_action.status !=": [
            _linha_acao(id=7498530235, categoria="DOWNLOAD", origem="APP",
                        tipo="ANDROID_INSTALLS_ALL_OTHER_APPS",
                        primaria=False),
            _linha_acao(id=7466919994, primaria=True),
        ],
        "metrics.conversion_last_conversion_date": [],
        "FROM customer": [_linha_conta()],
    })
    p = mef.ler_plano(CONTA, login_customer_id=MCC, campaign_id=CAMPANHA,
                      hoje="2026-09-01", buscar=buscar)
    assert p.meta_efetiva.resolvida is True, "havia meta biddable"
    assert p.acao_alvo is None, (
        "elegeu a ação não-primária — o lance não pode persegui-la")
    assert "DOWNLOAD/APP" in (p.acao_alvo_causa or "")
    assert p.completo is False
    assert p.destino.resolvido is False
