"""Blocos de operação compartilhados entre todos os canais.

Tudo aqui devolve `MutateOperation` com resource names TEMPORÁRIOS (ids
negativos), para que budget → campanha → ad groups → anúncios entrem numa
única transação. Se qualquer operação falhar, nada é criado — some a classe
inteira de falha "budget órfão porque o passo 6 quebrou".
"""

from __future__ import annotations

from datetime import datetime

from . import marcacao
from .brief import Brief

# ── ids temporários: a alocação de faixas ───────────────────────────────────
# Um id temporário é negativo e só precisa ser único DENTRO do mesmo mutate:
# o Google resolve a referência, devolve o resource name real e descarta o
# provisório. Enquanto havia UM ad group, três constantes bastavam. Agora duas
# famílias CRESCEM no mesmo grafo — ad groups (um por sub-intenção) e assets
# (um por sitelink, callout e snippet) — então as faixas são declaradas aqui,
# num lugar só, e a fronteira é verificada em código:
#
#   -1              orçamento
#   -2              campanha
#   -3   ..   -92   ad groups  (T_ADGROUP_BASE, descendo — teto de 90 grupos)
#   -93  ..   -99   VAZIO de propósito, o vão entre as faixas
#   -100 .. -199    assets de TEXTO   (T_ASSET_BASE, no pior caso 41:
#                                      20 sitelinks + 20 callouts + 1 snippet)
#   -200 .. -299    assets de IMAGEM  (T_IMAGEM_BASE — maior contrato atual:
#                                      Demand Gen, 20 marketing + 5 logos)
#
# ⚠️ Colisão de faixa é o defeito que não avisa. Se o 98º ad group recebesse
# -100, ou a referência do sitelink passaria a apontar para um ad group, ou a
# API recusaria o mutate inteiro com um erro sobre o ASSET — e o defeito está
# no ad group. Nos dois casos o diagnóstico é caro e o sintoma fica longe da
# causa. Por isso `temp_adgroup()` levanta antes de emitir o id.
#
# 90 é folga larga: o cluster medido do Pautador (opportunity_id 73) tem 4
# sub-intenções. O teto existe para a faixa não vazar, não para limitar o uso.
T_BUDGET, T_CAMPANHA = -1, -2
T_ADGROUP_BASE, T_ADGROUP_MAX = -3, 90
T_ASSET_BASE, T_ASSET_MAX = -100, 100

# ── a faixa de IMAGEM, e por que ela precisou nascer ────────────────────────
#
# Display recusava id temporário negativo para imagem, e a justificativa era
# interna: colidiria com a faixa de texto acima. A recusa estava CERTA e a
# conclusão estava errada — o que faltava era uma faixa, não uma proibição.
#
# O que ela destrava: `MutateOperation.asset_operation` existe, e um id
# temporário é único no request inteiro **mesmo entre tipos diferentes**. Então
# o Asset de imagem pode nascer no MESMO mutate atômico da campanha, com os
# bytes dentro (`ImageAsset.data` é mutate-only), e o anúncio o referencia pelo
# id provisório.
#
# Isso apaga uma classe inteira de problema em vez de resolvê-la: sem duas
# fases, não existe o estado "o asset subiu e a campanha não", não existe
# round-trip de `resource_name`, e não existe a pergunta "o upload deu timeout,
# criou?". A atomicidade do bulk mutate — tudo ou nada — passa a cobrir o
# criativo junto com a estrutura.
#
# 100 de folga para o maior teto real atual, 25 em Demand Gen (20 imagens de
# marketing combinadas + 5 logos). Display usa no máximo 20. A folga existe
# para a faixa não vazar, não para autorizar 100.
T_IMAGEM_BASE, T_IMAGEM_MAX = -200, 100


def temp_asset(cid: str, indice: int) -> str:
    """Resource name temporário do asset de TEXTO nº `indice` (0-based)."""
    if not 0 <= indice < T_ASSET_MAX:
        raise ValueError(
            f"asset de texto nº {indice} fora da faixa reservada "
            f"({T_ASSET_MAX} assets, ids {T_ASSET_BASE} a "
            f"{T_ASSET_BASE - T_ASSET_MAX + 1}). O próximo id invadiria a faixa "
            f"de imagem ({T_IMAGEM_BASE} para baixo) e a referência do anúncio "
            f"passaria a apontar para o asset errado — sem erro de API, porque "
            f"os dois ids são válidos.")
    return temp(cid, "assets", T_ASSET_BASE - indice)


def temp_imagem(cid: str, indice: int) -> str:
    """Resource name temporário do asset de IMAGEM nº `indice` (0-based)."""
    if not 0 <= indice < T_IMAGEM_MAX:
        raise ValueError(
            f"asset de imagem nº {indice} fora da faixa reservada "
            f"({T_IMAGEM_MAX} imagens, ids {T_IMAGEM_BASE} a "
            f"{T_IMAGEM_BASE - T_IMAGEM_MAX + 1}). O maior teto real atual é "
            f"25 em Demand Gen (20 marketing + 5 logos); chegar aqui "
            f"significa que a contagem por papel não foi conferida antes.")
    return temp(cid, "assets", T_IMAGEM_BASE - indice)


def temp(cid: str, colecao: str, n: int) -> str:
    return f"customers/{cid}/{colecao}/{n}"


def temp_adgroup(cid: str, indice: int) -> str:
    """Resource name temporário do ad group nº `indice` (0-based).

    Único ponto que traduz índice de sub-intenção em id temporário — para que
    keywords, negativas e RSA do grupo apontem todos para o mesmo lugar sem
    ninguém recalcular a aritmética por conta própria.
    """
    if not 0 <= indice < T_ADGROUP_MAX:
        raise ValueError(
            f"ad group nº {indice} fora da faixa reservada "
            f"({T_ADGROUP_MAX} grupos, ids {T_ADGROUP_BASE} a "
            f"{T_ADGROUP_BASE - T_ADGROUP_MAX + 1}). O próximo id invadiria a "
            f"faixa de assets ({T_ASSET_BASE} para baixo) e a referência "
            f"cruzada do mutate passaria a apontar para o recurso errado."
        )
    return temp(cid, "adGroups", T_ADGROUP_BASE - indice)


def carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def op_budget(c, cid: str, brief: Brief, nome: str):
    o = c.get_type("MutateOperation")
    b = o.campaign_budget_operation.create
    b.resource_name = temp(cid, "campaignBudgets", T_BUDGET)
    b.name = nome
    b.amount_micros = brief.micros(brief.budget_diario)
    b.delivery_method = c.enums.BudgetDeliveryMethodEnum.STANDARD
    # nunca compartilhado: budget compartilhado impede ajuste por campanha,
    # que é justamente a alavanca principal do motor de decisão.
    b.explicitly_shared = False
    return o


def op_campanha(c, cid: str, brief: Brief, nome: str, canal: str, *, ai_max: bool = False):
    """Campanha base. `canal` ∈ SEARCH | DISPLAY | DEMAND_GEN."""
    o = c.get_type("MutateOperation")
    camp = o.campaign_operation.create
    camp.resource_name = temp(cid, "campaigns", T_CAMPANHA)
    camp.name = nome
    camp.campaign_budget = temp(cid, "campaignBudgets", T_BUDGET)
    camp.advertising_channel_type = getattr(c.enums.AdvertisingChannelTypeEnum, canal)
    # SEMPRE nasce pausada. Despausar é decisão explícita, nunca efeito colateral.
    camp.status = c.enums.CampaignStatusEnum.PAUSED

    # Obrigatório desde a v25 — não existia na v21 e quebra todo payload antigo.
    camp.contains_eu_political_advertising = (
        c.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    # Estratégia de lance condicionada ao canal — medido no comportamento real:
    # Search varia por brief; Display aceita tCPA dentro de MaxConv; a primeira
    # onda Demand Gen usa MaxConv sem meta numérica.
    if canal == "SEARCH":
        # ⚠️ Sob `maximize_conversions` a API ACEITA `cpc_bid_micros` no ad group
        # e o ignora na veiculação — o lance do operador vira decoração. Sob
        # `manual_cpc` ele passa a morder. Por isso a escolha é do brief e não
        # do canal: ela decide se o número que o operador digitou vale alguma
        # coisa. Ver `op_ad_group()` logo abaixo.
        if brief.estrategia_lance == "MANUAL_CPC":
            # `enhanced_cpc_enabled` fica FALSE de propósito: eCPC é lance
            # automático disfarçado, e quem escolheu manual quer o controle.
            # É o mesmo que o gerador legado fazia (`manualCpc` com
            # `enhancedCpcEnabled: false`).
            camp.manual_cpc.enhanced_cpc_enabled = False
        elif brief.tcpa:
            camp.maximize_conversions.target_cpa_micros = brief.micros(brief.tcpa)
        else:
            camp.maximize_conversions.target_cpa_micros = 0
        camp.network_settings.target_google_search = True
        camp.network_settings.target_search_network = True
        camp.network_settings.target_content_network = False
        if ai_max:
            camp.ai_max_setting.enable_ai_max = True
    elif canal == "DISPLAY":
        # ⚠️ `maximize_conversions` SEMPRE, com o tCPA dentro — e não a
        # estratégia `target_cpa` avulsa, que era o que estava aqui.
        #
        # `docs/growth-engine/matriz-api/display.md` §8 mediu a tabela oficial
        # de estratégias (`campaigns/bidding/strategy-types`, 26/08/2026) e
        # `MAXIMIZE_CONVERSIONS` é a ÚNICA marcada `[alta]` para Display —
        # "as a standard strategy, it can be used with Search, Display, Video
        # and App campaigns". `TARGET_CPA` avulso não aparece em lista nenhuma
        # da página, nem como suportado nem como aposentado.
        #
        # Emitir um esquema de lance que a doc não declara para o canal é
        # apostar em qual das leituras está certa e descobrir no lote. O tCPA
        # não se perde: ele vive DENTRO do MaxConv, que é exatamente como
        # Search já o expressa três linhas acima.
        camp.maximize_conversions.target_cpa_micros = (
            brief.micros(brief.tcpa) if brief.tcpa else 0
        )
        camp.network_settings.target_google_search = False
        camp.network_settings.target_search_network = False
        camp.network_settings.target_content_network = True
    elif canal == "DEMAND_GEN":
        cfg = brief.demand_gen
        if cfg is None or cfg.upgraded_targeting is None:
            raise ValueError(
                "Demand Gen exige `demand_gen.upgraded_targeting` explícito: "
                "é imutável e o default remoto não pode decidir onde a "
                "segmentação será gravada"
            )
        camp.demand_gen_campaign_settings.upgraded_targeting = (
            cfg.upgraded_targeting
        )
        # A primeira onda escolhe somente Maximize Conversions sem meta
        # numérica. O oneof precisa ser selecionado, mas ausência de tCPA deve
        # continuar ausência — escrever `target_cpa_micros = 0` colapsaria as
        # duas coisas. `SetInParent` marca a mensagem vazia no protobuf.
        maxconv = camp.maximize_conversions
        pb = getattr(maxconv, "_pb", maxconv)
        selecionar = getattr(pb, "SetInParent", None)
        if selecionar is None:
            raise TypeError(
                "o SDK local não expõe SetInParent em MaximizeConversions; "
                "não há forma comprovada de selecionar o lance sem inventar "
                "target_cpa_micros=0"
            )
        selecionar()
    else:
        raise ValueError(f"canal desconhecido: {canal}")

    # Marcação NATIVA. Declarada uma vez aqui e aplicada pelo Google a toda URL
    # final servida pela campanha — anúncio, sitelink, asset. É o que fecha o
    # join custo × receita, e é por isso que `url_destino()` devolve a URL limpa.
    # A validação local é obrigatória: a API aceita macro inexistente sem erro.
    sufixo = marcacao.montar(canal, incluir_gclid=brief.marcacao_gclid,
                             extras=brief.marcacao_extra)
    r = marcacao.validar(sufixo, canal=canal, url_final=brief.url_final,
                         auto_tagging=not brief.marcacao_gclid)
    if not r.ok:
        raise ValueError(f"final_url_suffix inválido para {canal}:\n{r.resumo()}")
    camp.final_url_suffix = sufixo

    return o


def op_geo(c, cid: str, brief: Brief):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = temp(cid, "campaigns", T_CAMPANHA)
    cr.location.geo_target_constant = f"geoTargetConstants/{brief.geo_id}"
    return o


def op_idioma(c, cid: str, brief: Brief):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = temp(cid, "campaigns", T_CAMPANHA)
    cr.language.language_constant = f"languageConstants/{brief.idioma_id}"
    return o


def op_adgroup(
    c,
    cid: str,
    brief: Brief,
    nome: str,
    tipo: str | None = None,
    *,
    indice: int = 0,
    cpc_inicial: float | None = None,
    tcpa: float | None = None,
):
    """Um ad group. `indice` escolhe o id temporário dentro da faixa reservada.

    `cpc_inicial` e `tcpa` sobrescrevem os do brief quando vêm preenchidos —
    é o que permite a cada sub-intenção ter lance próprio. Sem eles, o grupo
    herda o brief e o payload é idêntico ao de quando existia um ad group só.

    ⚠️ O lance por grupo só morde de fato com lance manual. Sob
    MaximizeConversions a API aceita `cpc_bid_micros` e o ignora na veiculação;
    medido no brief do FGTS, que declara `cpc_inicial=0.20` como rede de
    proteção justamente por isso. O que separa os grupos sob MaxConv é o
    `target_cpa_micros` e a própria segmentação (termo de busca, relevância e
    negativa por grupo).

    Com `brief.estrategia_lance == "MANUAL_CPC"` — o padrão da casa desde
    18/08/2026 — esse `cpc_bid_micros` passa a ser o lance de verdade, e o
    número que o operador digitou no cockpit vira a régua do leilão.
    """
    o = c.get_type("MutateOperation")
    ag = o.ad_group_operation.create
    ag.resource_name = temp_adgroup(cid, indice)
    ag.name = nome
    ag.campaign = temp(cid, "campaigns", T_CAMPANHA)
    ag.status = c.enums.AdGroupStatusEnum.ENABLED
    if tipo:
        ag.type_ = getattr(c.enums.AdGroupTypeEnum, tipo)
    ag.cpc_bid_micros = brief.micros(
        cpc_inicial if cpc_inicial is not None else brief.cpc_inicial
    )
    # tCPA vive no ad group: é onde 90% do ajuste fino acontece (9,4:1 vs campanha)
    alvo = tcpa if tcpa is not None else brief.tcpa
    if alvo:
        ag.target_cpa_micros = brief.micros(alvo)
    return o


def url_destino(brief: Brief) -> str:
    """A URL final, LIMPA. A marcação não mora aqui.

    Era `url_com_marcacao()`, e concatenava `utm_source=gads&utm_campaign=…`
    direto na URL. Três motivos para ter saído daqui, todos em `marcacao.py`:
    a concatenação quebra quando a URL já tem query string, não alcança
    sitelink nem asset, e o parâmetro passa a fazer parte do destino que a
    política compara com a página.

    Quem carrega a marcação agora é `campaign.final_url_suffix`, montado em
    `op_campanha()` e aplicado pelo Google no clique, a todas as URLs da
    campanha de uma vez.
    """
    return brief.url_final
