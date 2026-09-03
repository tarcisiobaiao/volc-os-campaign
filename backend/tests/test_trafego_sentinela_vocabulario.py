"""Todo nome de enum da sentinela existe MESMO na Google Ads API.

## Por que este arquivo existe

Escrito em 03/09/2026, depois de a revisão factual encontrar QUATRO nomes de
enum inventados no primeiro corte da sentinela:

  · `AD_GROUP_CRITERION_LOW_QUALITY_SCORE` — o real é `..._LOW_QUALITY`;
  · `BELOW_FIRST_PAGE_BID` — o real é `AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID`;
  · `AD_GROUP_CRITERION_LOW_SEARCH_VOLUME` — não existe;
  · `AD_GROUP_CRITERION_POLICY_DISAPPROVED` — o real é `..._DISAPPROVED`.
  · e `REVIEWED_AND_PENDING` em `PolicyReviewStatusEnum`, que também não existe.

Um nome de enum inventado é o defeito mais silencioso possível: ele não quebra,
não avisa e não aparece em teste — ele simplesmente NUNCA casa. A causa que
dependia dele desaparece, e a tela mostra menos problema do que existe, que é
exatamente o falso verde que esta lane inteira existe para impedir.

## A fonte da verdade

O descriptor protobuf do pacote `google-ads` instalado — não a documentação,
não a memória de ninguém, não um modelo. Se o SDK subir de versão e um valor
sumir, este arquivo falha e alguém decide o que fazer, em vez de a causa
evaporar sem aviso.

⚠️ Estes testes são PULADOS quando o SDK não está no ambiente. Pular é honesto;
passar sem o SDK seria afirmar uma conferência que não aconteceu.
"""
from __future__ import annotations

import pytest

from app.trafego import diagnostico_persistido as dp
from app.trafego import sentinela as s

google_ads = pytest.importorskip(
    "google.ads.googleads.v25.enums.types.customer_status",
    reason="SDK google-ads ausente: a conferência de vocabulário não pode ser feita",
)


def valores(modulo: str, classe: str) -> set[str]:
    import importlib

    mod = importlib.import_module(f"google.ads.googleads.v25.enums.types.{modulo}")
    enum = getattr(mod, classe)
    interno = getattr(enum, classe.replace("Enum", ""), enum)
    return {v.name for v in interno}


# ── conta ───────────────────────────────────────────────────────────────────


def test_estados_bloqueantes_da_conta_existem():
    reais = valores("customer_status", "CustomerStatusEnum")
    assert s.CONTA_BLOQUEADA <= reais, s.CONTA_BLOQUEADA - reais
    assert s.CONTA_HABILITADA <= reais
    assert dp.CONTA_BLOQUEADA <= reais
    # E os dois módulos concordam: um vocabulário, não dois.
    assert s.CONTA_BLOQUEADA == dp.CONTA_BLOQUEADA


def test_a_conta_bloqueada_cobre_os_tres_estados_terminais():
    reais = valores("customer_status", "CustomerStatusEnum")
    terminais = reais - {"UNSPECIFIED", "UNKNOWN", "ENABLED"}
    # ⚠️ Se a API ganhar um quarto estado terminal, este teste falha e alguém
    # decide — em vez de o estado novo cair no ramo "não reconhecido" para
    # sempre, sem ninguém notar.
    assert s.CONTA_BLOQUEADA == terminais, (
        f"estados terminais não cobertos: {terminais - s.CONTA_BLOQUEADA}"
    )


# ── campanha ────────────────────────────────────────────────────────────────


def test_estados_da_campanha_existem_em_algum_dos_dois_enums():
    primary = valores("campaign_primary_status", "CampaignPrimaryStatusEnum")
    serving = valores("campaign_serving_status", "CampaignServingStatusEnum")
    status = valores("campaign_status", "CampaignStatusEnum")
    universo = primary | serving | status

    assert dp.ESTADOS_QUE_IMPEDEM <= universo, dp.ESTADOS_QUE_IMPEDEM - universo
    assert dp.ESTADOS_RECONHECIDOS_DA_CAMPANHA <= universo, (
        dp.ESTADOS_RECONHECIDOS_DA_CAMPANHA - universo
    )
    assert s.CAMPANHA_DESLIGADA <= universo


def test_misconfigured_e_suspended_impedem():
    """Os dois valores que caíam no `else` com um impedimento falso."""
    assert "MISCONFIGURED" in dp.ESTADOS_QUE_IMPEDEM
    assert "SUSPENDED" in dp.ESTADOS_QUE_IMPEDEM
    assert "MISCONFIGURED" in valores(
        "campaign_primary_status", "CampaignPrimaryStatusEnum"
    )
    assert "SUSPENDED" in valores(
        "campaign_serving_status", "CampaignServingStatusEnum"
    )


# ── keywords ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nome,conjunto",
    [
        ("KW_ABAIXO_DA_PRIMEIRA_PAGINA", s.KW_ABAIXO_DA_PRIMEIRA_PAGINA),
        ("KW_RARAMENTE_SERVIDA", s.KW_RARAMENTE_SERVIDA),
        ("KW_REPROVADA", s.KW_REPROVADA),
        ("KW_BAIXA_QUALIDADE", s.KW_BAIXA_QUALIDADE),
        ("KW_EM_REVISAO", s.KW_EM_REVISAO),
        ("KW_RESTRITA", s.KW_RESTRITA),
    ],
)
def test_todo_motivo_de_keyword_existe_no_enum(nome, conjunto):
    reais = valores(
        "ad_group_criterion_primary_status_reason",
        "AdGroupCriterionPrimaryStatusReasonEnum",
    )
    inventados = conjunto - reais
    assert not inventados, (
        f"{nome} carrega nome(s) que a API não tem: {sorted(inventados)}. "
        "Um nome inventado nunca casa, e a causa some em silêncio."
    )


def test_os_conjuntos_de_keyword_nao_se_sobrepoem():
    """Um motivo em dois baldes contaria a mesma keyword duas vezes."""
    baldes = {
        "abaixo": s.KW_ABAIXO_DA_PRIMEIRA_PAGINA,
        "rara": s.KW_RARAMENTE_SERVIDA,
        "reprovada": s.KW_REPROVADA,
        "qualidade": s.KW_BAIXA_QUALIDADE,
        "revisao": s.KW_EM_REVISAO,
        "restrita": s.KW_RESTRITA,
    }
    nomes = list(baldes)
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            comum = baldes[a] & baldes[b]
            assert not comum, f"{a} e {b} compartilham {sorted(comum)}"


def test_o_status_habilitado_da_keyword_e_o_do_enum():
    reais = valores(
        "ad_group_criterion_primary_status", "AdGroupCriterionPrimaryStatusEnum"
    )
    assert "ELIGIBLE" in reais
    assert "ELIGIBLE" in s.KW_HABILITADA
    # ⚠️ `ENABLED` NÃO está no enum de primary_status; ele viaja na lista como
    # tolerância a um servidor que mande `ad_group_criterion.status`. O teste
    # registra isso como decisão, para que ninguém o "corrija" achando que é
    # um valor de primary_status.
    assert "ENABLED" not in reais
    assert "ENABLED" in s.KW_HABILITADA


# ── anúncios ────────────────────────────────────────────────────────────────


def test_estados_de_politica_do_anuncio_existem():
    aprovacao = valores("policy_approval_status", "PolicyApprovalStatusEnum")
    revisao = valores("policy_review_status", "PolicyReviewStatusEnum")

    for nome, conjunto, reais in (
        ("ANUNCIO_REPROVADO", s.ANUNCIO_REPROVADO, aprovacao),
        ("ANUNCIO_APROVADO", s.ANUNCIO_APROVADO, aprovacao),
        ("dp.ANUNCIO_REPROVADO", dp.ANUNCIO_REPROVADO, aprovacao),
        ("dp.ANUNCIO_LIMITADO", dp.ANUNCIO_LIMITADO, aprovacao),
        ("ANUNCIO_EM_REVISAO", s.ANUNCIO_EM_REVISAO, revisao),
        ("dp.ANUNCIO_EM_REVISAO", dp.ANUNCIO_EM_REVISAO, revisao),
    ):
        inventados = conjunto - reais
        assert not inventados, f"{nome} carrega {sorted(inventados)}"


def test_approved_limited_nunca_conta_como_aprovado():
    """A API separa os dois porque a veiculação é menor. Nós também separamos."""
    assert "APPROVED_LIMITED" in valores(
        "policy_approval_status", "PolicyApprovalStatusEnum"
    )
    assert "APPROVED_LIMITED" not in dp.ANUNCIO_REPROVADO
    assert "APPROVED_LIMITED" in dp.ANUNCIO_LIMITADO
    # ⚠️ `ANUNCIO_APROVADO` da sentinela É tolerante e inclui os dois — ela usa
    # a contagem de `aptos`, que a ponte calcula EXCLUINDO os limitados.
    assert dp.ANUNCIO_LIMITADO.isdisjoint(dp.ANUNCIO_REPROVADO)


# ── estratégias de lance ────────────────────────────────────────────────────


def test_estrategias_dependentes_de_conversao_existem():
    reais = valores("bidding_strategy_type", "BiddingStrategyTypeEnum")
    inventadas = s.ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO - reais
    assert not inventadas, sorted(inventadas)


def test_target_impression_share_existe_e_fica_de_fora():
    """⚠️ TIS é lance automático e NÃO otimiza contra conversão.

    O valor existe no enum — não é engano de nome, é engano de significado. Ele
    otimiza participação e posição de impressão. Incluí-lo na lista fazia uma
    campanha em TIS sem meta de conversão ser acusada de
    `MEASUREMENT_NOT_READY` por fazer exatamente o que foi mandada fazer.
    """
    reais = valores("bidding_strategy_type", "BiddingStrategyTypeEnum")
    assert "TARGET_IMPRESSION_SHARE" in reais
    assert "TARGET_IMPRESSION_SHARE" not in s.ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO
    # E as quatro que de fato dependem continuam dentro.
    assert s.ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO == {
        "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE",
        "TARGET_CPA", "TARGET_ROAS",
    }


# ── campos, não só valores ──────────────────────────────────────────────────


def test_os_campos_que_a_allowlist_promete_existem_no_proto():
    """A allowlist de `CAMINHOS_ITEM` aponta para campos reais do proto.

    Um caminho que não existe devolve `None` silenciosamente em `_caminho`, e o
    degrau vira `nao_apurado` sem que ninguém saiba que o pedido estava errado.
    """
    from google.ads.googleads.v25.resources.types.ad_group_criterion import (
        AdGroupCriterion,
    )
    from google.ads.googleads.v25.resources.types.customer import Customer
    from google.ads.googleads.v25.resources.types.customer_conversion_goal import (
        CustomerConversionGoal,
    )

    campos_conta = set(Customer.meta.fields)
    for caminho in dp.CAMINHOS_ITEM["account"]:
        campo = caminho.split(".", 1)[1]
        assert campo in campos_conta, f"customer.{campo} não existe no proto"

    campos_meta = set(CustomerConversionGoal.meta.fields)
    for caminho in dp.CAMINHOS_ITEM["conversion_goal"]:
        campo = caminho.split(".", 1)[1]
        assert campo in campos_meta, f"customer_conversion_goal.{campo} não existe"

    assert "first_page_cpc_micros" in AdGroupCriterion.PositionEstimates.meta.fields
    assert "top_of_page_cpc_micros" in AdGroupCriterion.PositionEstimates.meta.fields
    assert "quality_score" in AdGroupCriterion.QualityInfo.meta.fields


def test_as_metricas_da_allowlist_existem():
    from google.ads.googleads.v25.common.types.metrics import Metrics

    campos = set(Metrics.meta.fields)
    # As da allowlist que são métricas de verdade (as demais são derivadas
    # nossas: keyword_count, first_page_cpc_median_micros, daily_budget_micros).
    derivadas = {
        "keyword_count", "first_page_cpc_median_micros", "daily_budget_micros",
    }
    for nome in dp.METRICAS_PERMITIDAS - derivadas:
        assert nome in campos, f"metrics.{nome} não existe no proto v25"
