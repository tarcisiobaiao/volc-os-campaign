"""Performance Max — contrato próprio, e jamais o de Search.

## O que torna este canal diferente dos outros três

PMax é o **único canal sem `AdGroup`, sem `Ad` e sem keyword positiva**. O
degrau intermediário dele é o `AssetGroup`, e o anúncio não existe como
recurso: o Google monta as combinações a partir dos assets soltos. Consultar
`ad_group`, `ad_group_ad` ou `keyword_view` numa campanha PMax **não retorna
nada** (`matriz-api/performance-max.md` §1, `[alta]`).

Isso não é uma curiosidade de esquema. Reaproveitar o caminho de Search aqui
— `op_adgroup`, `ad_group_ad_operation`, `keyword` positiva — produziria um
payload que a API recusa inteiro, com o erro apontando para o asset group e a
causa morando no contrato. Por isso este módulo **não chama** `comum.op_adgroup`
e não tem nenhum ramo compartilhado com `search.py`.

## O grafo, numa transação só — e por que ela precisa ser uma só

A matriz §2 é literal: em PMax não-retail, o `AssetGroup` e todos os
`AssetGroupAsset` que satisfazem os mínimos **têm de nascer no mesmo bulk
mutate**, porque `AssetGroupService` sozinho não consegue satisfazer o mínimo.
E **`partial_failure` não é suportado**. Ou seja, a atomicidade aqui não é uma
preferência de desenho deste projeto: é a única forma que a API aceita.

    CampaignBudget (DAILY, não compartilhado)
    └── Campaign (PERFORMANCE_MAX, PAUSED, brand_guidelines IMUTÁVEL)
        ├── CampaignCriterion   geo, idioma, keyword NEGATIVA
        ├── CampaignAsset       BUSINESS_NAME + LOGO  ← só com brand guidelines LIGADO
        └── AssetGroup (PAUSED)
            ├── AssetGroupAsset  HEADLINE, LONG_HEADLINE, DESCRIPTION,
            │                    [BUSINESS_NAME, LOGO ← só com brand guidelines DESLIGADO],
            │                    MARKETING_IMAGE, SQUARE_MARKETING_IMAGE,
            │                    PORTRAIT_MARKETING_IMAGE, LANDSCAPE_LOGO, YOUTUBE_VIDEO
            └── AssetGroupSignal  audience | search_theme

## As contagens obrigatórias NÃO são declaradas aqui

Elas já existiam, medidas e testadas, em
`volc_ads/observabilidade_pmax/coverage.py::PMAX_FIELD_REQUIREMENTS`, junto com
`evaluate_asset_group_coverage`. Este módulo **importa** aquela tabela e
**reusa** aquele avaliador para decidir se o plano cumpre o mínimo.

A consequência boa é que o portão de criação e o observador da conta usam a
mesma régua: o que o construtor recusa montar é exatamente o que o observador
apontaria como `GAPS` depois de criado. Uma segunda tabela aqui divergiria no
primeiro ajuste, e a divergência apareceria como "o VOLC deixou subir uma
campanha que o VOLC classifica como incompleta".

## Mensuração é portão de criação, não enfeite de relatório

PMax otimiza por conversão — as duas únicas estratégias de lance suportadas são
`MAXIMIZE_CONVERSIONS` e `MAXIMIZE_CONVERSION_VALUE` (§7). Uma campanha PMax
sem ação de conversão válida não é uma campanha ruim: é uma campanha que gasta
sem sinal para otimizar, em todas as redes do Google ao mesmo tempo e sem
controle de rede (§13).

Por isso `brief.pmax.mensuracao` é um **recibo de leitura da conta**
(`ReciboDeMensuracao`), emitido só por `ler_mensuracao()`, e a ausência dele é
bloqueio. Um `bool` no brief seria preenchido pela mesma parte interessada em
subir a campanha — foi esse o defeito de *linhagem autoatestável* que a revisão
de Demand Gen encontrou.

## O que este módulo NÃO faz, e é declarado

- **Não cria nada.** `perfil.PERFORMANCE_MAX.construtor` continua `None` de
  propósito, então `subir.py` não tem por onde encaminhar PMax ao mutate.
  Promovê-lo mudaria `perfil.canais_que_provam()` e a guarda de import de
  `subir.py:133-148` derrubaria a rota HTTP dos QUATRO canais.
- **Não roda `validate_only` sozinho.** `validar()` existe e é chamável, mas
  `planejar()` marca `pode_provar=False` com código próprio enquanto o canal
  estiver fora do executor. Ver `plano.PMAX_FORA_DO_EXECUTOR`.
- **Não monta retail** (`ShoppingSetting`, `AssetGroupListingGroupFilter`),
  nem `CampaignConversionGoal`, nem `text_guidelines`, nem `TRAVEL_GOALS`.
  A automação de expansão de URL final é a exceção deliberada: nasce com
  `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION` em `OPTED_OUT`, porque PMax só é
  elegível se o clique permanecer na LP declarada. Cada ausência restante é
  declarada em `NAO_OPERADO`, e chega ao plano — ausência declarada, não lacuna.
"""

from __future__ import annotations

import enum
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module

import yaml

from ..gads.client import VERSAO_API, buscar, cliente, validar_mutacoes
from ..observabilidade_pmax import (
    PMAX_FIELD_REQUIREMENTS,
    CoverageVerdict,
    ObservedValue,
    PMaxAssetDTO,
    PMaxAssetFieldType,
    PMaxAssetGroupAssetDTO,
    PMaxAssetGroupDTO,
    PMaxAssetGroupStatus,
    evaluate_asset_group_coverage,
)
from ..observabilidade_pmax.types import PMaxAdStrength, PMaxAssetGroupPrimaryStatus
from . import comum, conteudo, plano, taxonomia, validacao
from .brief import (
    PAPEIS_DE_ASSET_PMAX,
    AcaoDeConversao,
    AssetRemotoAprovado,
    Brief,
    ImagemParaSubir,
    ImagensPMax,
    ReciboDeMensuracao,
    _emitir_recibo_de_mensuracao,
    conferir_asset_aprovado,
)

CANAL = "PERFORMANCE_MAX"

#: As duas ÚNICAS estratégias que PMax suporta (§7, `[alta]`, ref [X2]): "The
#: only supported bidding strategies for Performance Max campaigns are…".
#: Estratégias de portfólio são explicitamente proibidas e não têm caminho aqui.
LANCES_PERMITIDOS: tuple[str, ...] = (
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
)

#: Nenhuma opção de construção além do brief. `ai_max` é de Search.
OPCOES: frozenset[str] = frozenset()

_LIM = yaml.safe_load(
    (pathlib.Path(__file__).parent / "limites.yaml").read_text(encoding="utf-8")
)

_RESOURCE_ASSET = re.compile(r"^customers/(\d+)/assets/(\d+)$")

#: Papel do brief → `AssetFieldType` da API. A ORDEM mora em
#: `brief.PAPEIS_DE_ASSET_PMAX`, porque quem percorre os assets fora deste
#: módulo (o recibo, via `linhagens()`) precisa da mesma sequência.
CAMPO_DE_ASSET: dict[str, PMaxAssetFieldType] = {
    papel: PMaxAssetFieldType(campo) for papel, campo in PAPEIS_DE_ASSET_PMAX
}

_EXPLICACAO_DKI = (
    "Performance Max não casa keyword positiva — {KeyWord:…} não tem intenção "
    "de busca para resolver, e o Google monta a combinação sozinho. Escreva o "
    "texto final"
)

#: Janela em que um recibo de mensuração ainda é considerado fresco. Não é um
#: limite da API: é a distância a partir da qual "a conta tinha conversão" vira
#: uma afirmação sobre o passado. Fora dela o plano AVISA — não bloqueia, porque
#: uma leitura antiga continua sendo uma leitura, e tratá-la como ausência
#: colapsaria dois estados que este projeto separa em todo lugar.
IDADE_MAXIMA_DA_MENSURACAO = timedelta(hours=24)

#: Ausências DECLARADAS. Cada linha é uma resposta ("PMax do VOLC não faz isso,
#: e este é o motivo"), nunca uma lacuna esquecida. Elas viajam no plano.
NAO_OPERADO: tuple[str, ...] = (
    "retail: `ShoppingSetting` e `AssetGroupListingGroupFilter` não são "
    "montados. PMax retail tem um estado a mais (asset group vazio OU completo, "
    "§2) e uma árvore de listing group com profundidade máxima própria; montar "
    "por analogia subiria um asset group que a API aceita e que não veicula.",
    "CampaignConversionGoal: a campanha usa os `CustomerConversionGoal` da "
    "conta, que é o default da API (§7). Restringir por campanha exige copiar "
    "cada goal e ajustar `biddable`, e é uma decisão de negócio que o brief "
    "ainda não expressa — herdar a conta é o comportamento previsível.",
    "text_guidelines (`term_exclusions`, `messaging_restrictions`): campos "
    "reais do proto (§9), sem campo correspondente no brief. Inventá-los aqui "
    "seria decidir a política editorial do cliente pelo cliente.",
    "TRAVEL_GOALS: é `advertising_channel_sub_type`, imutável, e muda os "
    "requisitos do canal inteiro. A campanha padrão sai SEM sub_type (§0).",
    "Local Services PMax: exige ao menos um sinal por asset group e ao menos "
    "um critério de localização positivo (§8). O builder padrão não garante "
    "nenhuma das duas, e prometer o subtipo sem elas seria prometer errado.",
    "`brand`, `webpage`, `ad_schedule`, `device`, `age_range` e "
    "`location_group` como critério de campanha: suportados pela API (§8) e "
    "sem campo no brief. Keyword e brand, quando entrarem, só podem entrar "
    "como NEGATIVOS — em PMax o positivo não existe para os dois.",
    "múltiplos asset groups: a API aceita 1..100 por campanha (§10) e este "
    "builder emite exatamente 1. Cada asset group tem público e criativo "
    "próprios; emitir N cópias do mesmo conteúdo repartiria a verba por "
    "sorteio, que é o mesmo motivo pelo qual Display monta um ad group só.",
)


# ═══════════════════════════════════════════════════════════════════════════
# A SONDA DOS PROTOS v25
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SuporteProtoV25:
    """Resultado da prova local do namespace/campos que ESTE builder emite."""

    disponivel: bool
    motivo: str
    objetos_serializados: tuple[str, ...] = ()


def _classe_enum(modulo, nome: str):
    wrapper = getattr(modulo, nome)
    for atributo in dir(wrapper):
        valor = getattr(wrapper, atributo)
        if isinstance(valor, enum.EnumMeta):
            return valor
    raise AttributeError(f"{nome} não contém enum concreto")


def _exigir_campos(classe, *campos: str) -> None:
    existentes = {campo.name for campo in classe.pb().DESCRIPTOR.fields}
    faltantes = sorted(set(campos) - existentes)
    if faltantes:
        raise AttributeError(
            f"{classe.__module__}.{classe.__name__} sem campos {faltantes}"
        )


def _serializar_proto(objeto) -> bytes:
    alvo = getattr(objeto, "_pb", objeto)
    return alvo.SerializeToString(deterministic=True)


def sondar_proto_v25() -> SuporteProtoV25:
    """Instancia e serializa, sem credencial e sem rede, os protos desta onda.

    Importar `google-ads` não prova que a versão nem os campos existem —
    `brand_guidelines_enabled` nasceu na v21, `AssetGroupSignal.search_theme`
    é mais novo que o resto, e um SDK antigo aceitaria o import e faltaria o
    campo na hora do mutate. Esta sonda monta um objeto de cada tipo que o
    builder emite, a partir dos namespaces gerados de v25, e serializa.

    Qualquer ausência **rebaixa a capacidade**: não há fallback para outra
    versão nem dublê que finja o campo.
    """
    try:
        servicos = import_module(
            f"google.ads.googleads.{VERSAO_API}.services.types.google_ads_service")
        campanhas = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.campaign")
        budgets = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.campaign_budget")
        criterios = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.campaign_criterion")
        campaign_assets = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.campaign_asset")
        grupos = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.asset_group")
        grupo_assets = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.asset_group_asset")
        sinais = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.asset_group_signal")
        assets = import_module(
            f"google.ads.googleads.{VERSAO_API}.resources.types.asset")
        criteria = import_module(
            f"google.ads.googleads.{VERSAO_API}.common.types.criteria")
        enums = import_module(f"google.ads.googleads.{VERSAO_API}.enums")

        MutateOperation = getattr(servicos, "MutateOperation")
        Campaign = getattr(campanhas, "Campaign")
        CampaignBudget = getattr(budgets, "CampaignBudget")
        CampaignCriterion = getattr(criterios, "CampaignCriterion")
        CampaignAsset = getattr(campaign_assets, "CampaignAsset")
        AssetGroup = getattr(grupos, "AssetGroup")
        AssetGroupAsset = getattr(grupo_assets, "AssetGroupAsset")
        AssetGroupSignal = getattr(sinais, "AssetGroupSignal")
        Asset = getattr(assets, "Asset")
        SearchThemeInfo = getattr(criteria, "SearchThemeInfo")
        AudienceInfo = getattr(criteria, "AudienceInfo")

        # Os campos que ESTE builder escreve. Um campo a menos aqui é um mutate
        # que falha em produção com a causa a três arquivos de distância.
        _exigir_campos(
            Campaign, "advertising_channel_type", "brand_guidelines_enabled",
            "maximize_conversions", "maximize_conversion_value",
            "contains_eu_political_advertising", "final_url_suffix",
            "campaign_budget", "status", "name")
        _exigir_campos(CampaignBudget, "amount_micros", "explicitly_shared",
                       "period", "delivery_method", "name")
        _exigir_campos(AssetGroup, "name", "campaign", "final_urls", "status")
        _exigir_campos(AssetGroupAsset, "asset", "asset_group", "field_type")
        _exigir_campos(AssetGroupSignal, "asset_group", "audience",
                       "search_theme")
        _exigir_campos(CampaignAsset, "asset", "campaign", "field_type")
        _exigir_campos(Asset, "name", "type_", "text_asset", "image_asset")
        _exigir_campos(SearchThemeInfo, "text")

        canal_enum = _classe_enum(enums, "AdvertisingChannelTypeEnum")
        if not hasattr(canal_enum, "PERFORMANCE_MAX"):
            raise AttributeError("AdvertisingChannelTypeEnum sem PERFORMANCE_MAX")
        campo_enum = _classe_enum(enums, "AssetFieldTypeEnum")
        for exigido in ("HEADLINE", "LONG_HEADLINE", "DESCRIPTION",
                        "BUSINESS_NAME", "MARKETING_IMAGE",
                        "SQUARE_MARKETING_IMAGE", "PORTRAIT_MARKETING_IMAGE",
                        "LOGO", "LANDSCAPE_LOGO", "YOUTUBE_VIDEO"):
            if not hasattr(campo_enum, exigido):
                raise AttributeError(f"AssetFieldTypeEnum sem {exigido}")
        grupo_enum = _classe_enum(enums, "AssetGroupStatusEnum")
        if not hasattr(grupo_enum, "PAUSED"):
            raise AttributeError("AssetGroupStatusEnum sem PAUSED")
        periodo_enum = _classe_enum(enums, "BudgetPeriodEnum")
        if not hasattr(periodo_enum, "DAILY"):
            raise AttributeError("BudgetPeriodEnum sem DAILY")

        campanha = Campaign(
            name="sonda",
            advertising_channel_type=canal_enum.PERFORMANCE_MAX,
            brand_guidelines_enabled=True,
        )
        campanha.maximize_conversion_value.target_roas = 4.0

        grupo = AssetGroup(name="sonda", final_urls=["https://exemplo/"],
                           status=grupo_enum.PAUSED)
        vinculo = AssetGroupAsset(field_type=campo_enum.HEADLINE)
        sinal = AssetGroupSignal()
        sinal.search_theme = SearchThemeInfo(text="sonda")
        sinal_audiencia = AssetGroupSignal()
        sinal_audiencia.audience = AudienceInfo(
            audience="customers/1/audiences/2")
        asset_texto = Asset(name="sonda")
        asset_texto.text_asset.text = "sonda"
        asset_imagem = Asset(name="sonda")
        asset_imagem.image_asset.data = b"\x89PNG"
        campanha_asset = CampaignAsset(field_type=campo_enum.BUSINESS_NAME)
        orcamento = CampaignBudget(amount_micros=1, explicitly_shared=False,
                                   period=periodo_enum.DAILY)
        criterio = CampaignCriterion(negative=True)
        criterio.keyword.text = "sonda"

        # E as OPERAÇÕES: o proto que de fato viaja, não só as folhas.
        op_campanha = MutateOperation()
        op_campanha.campaign_operation.create = campanha
        op_grupo = MutateOperation()
        op_grupo.asset_group_operation.create = grupo
        op_vinculo = MutateOperation()
        op_vinculo.asset_group_asset_operation.create = vinculo
        op_sinal = MutateOperation()
        op_sinal.asset_group_signal_operation.create = sinal
        op_campanha_asset = MutateOperation()
        op_campanha_asset.campaign_asset_operation.create = campanha_asset

        serializados: list[str] = []
        for nome, objeto in (
            ("Campaign", campanha), ("CampaignBudget", orcamento),
            ("CampaignCriterion", criterio), ("CampaignAsset", campanha_asset),
            ("AssetGroup", grupo), ("AssetGroupAsset", vinculo),
            ("AssetGroupSignal.search_theme", sinal),
            ("AssetGroupSignal.audience", sinal_audiencia),
            ("Asset.text", asset_texto), ("Asset.image", asset_imagem),
            ("MutateOperation.campaign", op_campanha),
            ("MutateOperation.asset_group", op_grupo),
            ("MutateOperation.asset_group_asset", op_vinculo),
            ("MutateOperation.asset_group_signal", op_sinal),
            ("MutateOperation.campaign_asset", op_campanha_asset),
        ):
            if not _serializar_proto(objeto):
                raise ValueError(f"{nome} serializou vazio")
            serializados.append(nome)

        return SuporteProtoV25(
            True,
            f"protos {VERSAO_API} instanciados e serializados",
            tuple(serializados),
        )
    except Exception as exc:  # noqa: BLE001 — ausência/mudança de SDK é capacidade
        return SuporteProtoV25(
            False,
            f"SDK Google Ads {VERSAO_API} incompatível: "
            f"{type(exc).__name__}: {exc}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# A LEITURA DE MENSURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

CONSULTA_DE_MENSURACAO = """
SELECT
  conversion_action.resource_name,
  conversion_action.name,
  conversion_action.type,
  conversion_action.category,
  conversion_action.status,
  conversion_action.primary_for_goal,
  conversion_action.include_in_conversions_metric,
  conversion_action.value_settings.default_value,
  conversion_action.value_settings.always_use_default_value
FROM conversion_action
WHERE conversion_action.status != 'REMOVED'
""".strip()


def ler_mensuracao(cid: str, *, login_customer_id: str) -> ReciboDeMensuracao:
    """Lê as ações de conversão da conta e emite o recibo. **Só leitura.**

    Usa `gads.client.buscar`, que é `search_stream` — não há caminho daqui para
    `mutar()`. O recibo emitido é a única forma de `brief.pmax.mensuracao`
    nascer válido: `ReciboDeMensuracao` tem construtor privado e checa a
    própria impressão, então um recibo montado à mão pelo chamador responde
    `integro=False` e o builder o recusa.

    ⚠️ Esta função **não** popula `conversoes_ultimos_30d`. O volume vem de
    `metrics` sobre `conversion_action`, que é outra consulta com outro
    `segments.date`; enquanto ela não existir, o campo fica `None` — que é
    "ninguém mediu", e nunca "mediu e deu zero".
    """
    linhas = buscar(str(cid), CONSULTA_DE_MENSURACAO,
                    login_customer_id=str(login_customer_id))
    acoes: list[AcaoDeConversao] = []
    for linha in linhas:
        ca = linha.conversion_action
        valores = getattr(ca, "value_settings", None)
        acoes.append(AcaoDeConversao(
            resource_name=str(ca.resource_name),
            nome=str(ca.name),
            tipo=getattr(ca.type_, "name", str(ca.type_)),
            categoria=getattr(ca.category, "name", str(ca.category)),
            status=getattr(ca.status, "name", str(ca.status)),
            primaria_para_meta=bool(ca.primary_for_goal),
            inclui_em_conversoes=bool(ca.include_in_conversions_metric),
            # "Carrega valor" é ter valor por conversão: ou o padrão é
            # diferente de zero, ou a ação foi configurada para sempre usar o
            # padrão. Sem uma das duas, MaximizeConversionValue otimizaria por
            # um valor que não existe.
            carrega_valor=bool(
                valores is not None
                and (float(getattr(valores, "default_value", 0.0) or 0.0) > 0.0
                     or bool(getattr(valores, "always_use_default_value", False)))
            ),
            conversoes_ultimos_30d=None,
        ))
    return _emitir_recibo_de_mensuracao(
        customer_id=str(cid),
        login_customer_id=str(login_customer_id),
        lido_em=datetime.now(timezone.utc).isoformat(),
        consulta=CONSULTA_DE_MENSURACAO,
        coletor=f"volc_ads.campanha.pmax.ler_mensuracao ({VERSAO_API})",
        acoes=tuple(acoes),
    )


# ═══════════════════════════════════════════════════════════════════════════
# AS RECUSAS
# ═══════════════════════════════════════════════════════════════════════════


def _recusar_o_que_nao_e_de_pmax(brief: Brief, r: validacao.Resultado) -> None:
    """Campos do brief multicanal que PMax não pode honrar. Recusa, não descarte.

    Cada linha aqui existe porque o campo tem consumidor em OUTRO canal e
    chegaria até este builder sem ninguém notar. Ignorar em silêncio faria o
    operador declarar uma coisa e receber outra — que é o defeito que este
    projeto persegue em todos os canais.
    """
    if brief.estrategia_lance not in LANCES_PERMITIDOS:
        r.erro("estrategia_lance", brief.estrategia_lance,
               f"Performance Max aceita somente {', '.join(LANCES_PERMITIDOS)} "
               f"— a matriz §7 registra a frase oficial 'The only supported "
               f"bidding strategies for Performance Max campaigns are…'. "
               f"Estratégia de portfólio é proibida no canal",
               plano.LANCE_NAO_PERMITIDO)

    if brief.ai_max:
        r.erro("ai_max", True,
               "`campaign.ai_max_setting` é campo de Search. Em PMax a "
               "expansão é o comportamento padrão do canal e não se liga por "
               "flag — pedir ai_max aqui é pedir uma caixa que não existe",
               plano.CAMPO_NAO_OPERADO)

    if brief.sub_intencoes:
        r.erro("sub_intencoes", f"{len(brief.sub_intencoes)} grupos",
               "PMax NÃO TEM ad group (matriz §1) — `sub_intencoes` particiona "
               "keywords em grupos e não há grupo para receber. A partição "
               "equivalente aqui é um asset group por público/criativo, que "
               "esta onda ainda não monta",
               plano.CAMPO_NAO_OPERADO)

    positivas = [c for c in brief.criterios if not c.negativa]
    if positivas:
        r.erro("keywords", f"{len(positivas)} positivas",
               "keyword em PMax só pode ser NEGATIVA (matriz §8: 'brand e "
               "keyword só podem ser negativos'). Targeting positivo por termo "
               "não existe no canal — o substituto é `pmax.sinais` "
               "(AssetGroupSignal)",
               plano.CAMPO_NAO_OPERADO)

    if brief.copy.sitelinks or brief.copy.callouts or brief.copy.snippet:
        r.erro("copy.extensoes",
               f"{len(brief.copy.sitelinks)} sitelinks, "
               f"{len(brief.copy.callouts)} callouts, "
               f"snippet={'sim' if brief.copy.snippet else 'não'}",
               "sitelink, callout e structured snippet são assets de Search. "
               "Em PMax o asset group tem tabela própria de field_type "
               "(matriz §4) e nenhum deles aparece nela — montá-los por "
               "analogia subiria asset que não veicula",
               plano.CAMPO_NAO_OPERADO)

    if brief.imagens_display is not None:
        r.erro("imagens_display", "preenchido",
               "PMax usa `imagens_pmax`: os papéis não coincidem "
               "(`LANDSCAPE_LOGO` não existe em Display) e Display aceita "
               "resource name sem bytes, que PMax recusa",
               plano.CAMPO_NAO_OPERADO)
    if brief.imagens_demand_gen is not None:
        r.erro("imagens_demand_gen", "preenchido",
               "PMax usa `imagens_pmax`: Demand Gen tem retrato alto 9:16 e "
               "só logo quadrado; PMax tem logo 1:1 e logo paisagem 4:1",
               plano.CAMPO_NAO_OPERADO)
    if brief.demand_gen is not None:
        r.erro("demand_gen", "preenchido",
               "`upgraded_targeting` e channel controls são de Demand Gen. "
               "PMax não tem controle de rede nenhum (matriz §13)",
               plano.CAMPO_NAO_OPERADO)

    if brief.imagens or brief.videos:
        r.erro("imagens/videos",
               f"{len(brief.imagens)} imagens, {len(brief.videos)} vídeos",
               "as listas chapadas `imagens`/`videos` não carregam papel, e em "
               "PMax o papel É o contrato (`AssetFieldType`). Use "
               "`imagens_pmax`, que separa por papel e leva vídeo em "
               "`videos_youtube`",
               plano.CAMPO_NAO_OPERADO)


def _checar_contrato(brief: Brief, r: validacao.Resultado):
    """A configuração de PMax existe e tomou as decisões que não têm default."""
    cfg = brief.pmax
    if cfg is None:
        r.erro("pmax", "ausente",
               "Performance Max exige `brief.pmax` explícito: brand "
               "guidelines (imutável), sinais, negativas e o recibo de "
               "mensuração. Nenhum deles tem default seguro",
               plano.CONFIGURACAO_AUSENTE)
        return None

    if cfg.brand_guidelines_enabled is None:
        r.erro("pmax.brand_guidelines_enabled", "ausente",
               "campo IMUTÁVEL na criação (matriz §5/§6): ligado, "
               "BUSINESS_NAME e LOGO viram CampaignAsset; desligado, ficam no "
               "AssetGroupAsset. Desde a v21 a API liga por default, e herdar "
               "esse default move o asset de nível sem ninguém decidir — não "
               "há update normal que desfaça",
               plano.CONFIGURACAO_AUSENTE)

    if cfg.sinais is None:
        r.erro("pmax.sinais", "ausente",
               "declare a tupla de AssetGroupSignal, ainda que vazia. PMax "
               "padrão funciona sem sinal (matriz §8) — mas '()' é a escolha "
               "de não dar dica, e None é ninguém ter escolhido",
               plano.CONFIGURACAO_AUSENTE)
    if cfg.negativas is None:
        r.erro("pmax.negativas", "ausente",
               "declare a tupla de keywords negativas, ainda que vazia. Em "
               "PMax a negativa é o único controle de termo que existe, e "
               "deixá-la indefinida é deixar o canal comprar qualquer consulta",
               plano.CONFIGURACAO_AUSENTE)

    teto = _LIM["pmax_limites"]["negativas_por_campanha_max"]
    if cfg.negativas is not None and len(cfg.negativas) > teto:
        r.erro("pmax.negativas", f"{len(cfg.negativas)} termos",
               f"o teto por campanha PMax é {teto} (matriz §10). Acima disso a "
               f"API responde ResourceCountLimitExceededError",
               plano.ASSET_ACIMA_DO_TETO)

    limite_nome = _LIM["pmax_limites"]["nome_asset_group_max_chars"]
    if cfg.nome_do_asset_group and len(cfg.nome_do_asset_group) > limite_nome:
        r.erro("pmax.nome_do_asset_group", cfg.nome_do_asset_group,
               f"`AssetGroup.name` aceita 1..{limite_nome} caracteres",
               plano.CONFIGURACAO_AUSENTE)

    return cfg


def _checar_mensuracao(cid: str, brief: Brief, cfg, r: validacao.Resultado,
                       *, login_customer_id: str) -> None:
    """O portão que separa "monta o payload" de "pode existir gastando".

    Este portão é INDEPENDENTE de o canal estar fora do executor. Hoje PMax
    está bloqueado por dois motivos empilhados — não há construtor no perfil, e
    a mensuração pode ser inadequada — e só o segundo é uma regra de negócio.
    Se o primeiro sumisse amanhã (alguém habilita o canal), este continuaria de
    pé; provar isso é o objetivo de
    `testes_pmax.py::test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado`.
    """
    if cfg is None:
        return

    recibo = cfg.mensuracao
    if recibo is None:
        r.erro("pmax.mensuracao", "ausente",
               "Performance Max otimiza por conversão e serve em todas as "
               "redes do Google sem controle de rede (matriz §7/§13). Sem "
               "leitura da mensuração da conta, não há como afirmar que existe "
               "sinal para otimizar — e uma campanha sem sinal gasta em todo "
               "lugar ao mesmo tempo. Rode `pmax.ler_mensuracao(cid, "
               "login_customer_id=…)` e traga o recibo",
               plano.MENSURACAO_INADEQUADA)
        return

    if not isinstance(recibo, ReciboDeMensuracao):
        r.erro("pmax.mensuracao", type(recibo).__name__,
               "`pmax.mensuracao` exige ReciboDeMensuracao tipado",
               plano.MENSURACAO_INADEQUADA)
        return

    if not recibo.integro:
        r.erro("pmax.mensuracao", "não íntegro",
               "o recibo não foi emitido por `ler_mensuracao()` nesta execução "
               "ou foi alterado depois. Um objeto que declara a própria "
               "procedência não é prova de leitura nenhuma",
               plano.MENSURACAO_INADEQUADA)
        return

    if recibo.customer_id != str(cid):
        r.erro("pmax.mensuracao", recibo.customer_id,
               f"a mensuração foi lida da conta {recibo.customer_id} e o plano "
               f"é da conta {cid}. Conversão não atravessa conta",
               plano.MENSURACAO_INADEQUADA)
    if recibo.login_customer_id != str(login_customer_id):
        r.erro("pmax.mensuracao", recibo.login_customer_id,
               f"a mensuração foi lida sob o MCC {recibo.login_customer_id} e "
               f"o plano roda sob {login_customer_id}",
               plano.MENSURACAO_INADEQUADA)

    validas = recibo.acoes_validas
    if not validas:
        r.erro("pmax.mensuracao", f"{len(recibo.acoes)} ações lidas, 0 válidas",
               "nenhuma ação de conversão está ENABLED, primária da meta e "
               "incluída na métrica de conversões ao mesmo tempo. As três "
               "condições são da API, não de gosto: pausada não recebe, fora "
               "de include_in_conversions_metric não entra na métrica que o "
               "lance otimiza, e não-primária não participa do objetivo. "
               "Criação e ativação de PMax ficam BLOQUEADAS",
               plano.MENSURACAO_INADEQUADA)

    if brief.estrategia_lance == "MAXIMIZE_CONVERSION_VALUE" and not recibo.acoes_com_valor:
        r.erro("pmax.mensuracao", "nenhuma ação carrega valor",
               "MAXIMIZE_CONVERSION_VALUE otimiza VALOR de conversão, e "
               "nenhuma das ações válidas tem `value_settings` com valor "
               "padrão positivo ou `always_use_default_value`. Otimizar valor "
               "sobre conversões sem valor é otimizar por zero — use "
               "MAXIMIZE_CONVERSIONS ou configure o valor das ações",
               plano.MENSURACAO_INADEQUADA)

    volume = recibo.volume_30d
    if volume is None:
        r.aviso("pmax.mensuracao", "volume não medido",
                "`conversoes_ultimos_30d` é None em todas as ações válidas: "
                "ninguém mediu o volume. Isso NÃO é zero conversões — é a "
                "ausência da medida, e o plano diz isso em voz alta em vez de "
                "escolher uma das duas leituras",
                plano.MENSURACAO_INADEQUADA)
    elif volume == 0.0:
        r.aviso("pmax.mensuracao", "0 conversões em 30 dias",
                "a tag está válida e o volume medido é zero. A API cria a "
                "campanha assim; o Smart Bidding, porém, não tem histórico "
                "para aprender. É aviso e não bloqueio porque barrar aqui "
                "recusaria localmente um payload que a API aceita",
                plano.MENSURACAO_INADEQUADA)

    _avisar_recibo_velho(recibo, r)


def _avisar_recibo_velho(recibo: ReciboDeMensuracao,
                         r: validacao.Resultado) -> None:
    try:
        lido = datetime.fromisoformat(recibo.lido_em)
    except ValueError:
        r.erro("pmax.mensuracao", recibo.lido_em,
               "`lido_em` não é um instante ISO-8601 — um recibo sem data "
               "legível não permite dizer se a leitura ainda vale",
               plano.MENSURACAO_INADEQUADA)
        return
    if lido.tzinfo is None:
        r.erro("pmax.mensuracao", recibo.lido_em,
               "`lido_em` sem fuso horário: 'agora' sem fuso é ambíguo por até "
               "26 horas, que é maior que a janela de frescor",
               plano.MENSURACAO_INADEQUADA)
        return
    idade = datetime.now(timezone.utc) - lido
    if idade > IDADE_MAXIMA_DA_MENSURACAO:
        r.aviso("pmax.mensuracao", f"lida há {idade}",
                f"a leitura tem mais de {IDADE_MAXIMA_DA_MENSURACAO} — ela "
                f"continua sendo uma leitura, e por isso é aviso, mas descreve "
                f"a conta de ontem. Releia antes de autorizar gasto",
                plano.MENSURACAO_INADEQUADA)


def _checar_assets(cid: str, brief: Brief, cfg,
                   r: validacao.Resultado) -> ImagensPMax:
    """Recibo tipado por asset, papel a papel, e o peso de arquivo.

    A CONTAGEM não é conferida aqui: quem a confere é
    `evaluate_asset_group_coverage`, sobre o plano projetado, com a mesma
    `PMAX_FIELD_REQUIREMENTS` que o observador da conta usa. Conferir duas
    vezes com duas tabelas é como as duas tabelas divergem.
    """
    imagens = brief.imagens_pmax
    if imagens is None:
        r.erro("imagens_pmax", "ausente",
               "Performance Max exige assets visuais: MARKETING_IMAGE e "
               "SQUARE_MARKETING_IMAGE são obrigatórios em todo asset group "
               "(matriz §4), e LOGO também quando brand guidelines está "
               "desligado. Um plano de PMax sem asset não é um plano de PMax",
               plano.ASSET_OBRIGATORIO_AUSENTE)
        return ImagensPMax()

    peso_max = _LIM["pmax_asset"]["peso_maximo_bytes"]
    for papel in ImagensPMax.PAPEIS:
        for item in getattr(imagens, papel):
            if isinstance(item, str):
                r.erro(f"imagens_pmax.{papel}", item,
                       "PMax NÃO aceita resource name solto. A tabela oficial "
                       "de requisitos (§4) impõe proporção, dimensão mínima e "
                       "peso por papel, e sem os bytes nada disso pode ser "
                       "reconferido antes do validate_only. Traga "
                       "`ImagemParaSubir` ou `AssetRemotoAprovado`",
                       plano.ASSET_SEM_RECIBO)
                continue
            if not isinstance(item, (ImagemParaSubir, AssetRemotoAprovado)):
                r.erro(f"imagens_pmax.{papel}", type(item).__name__,
                       "forma de asset não suportada em PMax",
                       plano.ASSET_SEM_RECIBO)
                continue

            for erro in conferir_asset_aprovado(
                item, papel=papel, customer_id=str(cid), canal=CANAL
            ):
                r.erro(f"imagens_pmax.{papel}", getattr(item, "nome", "?"), erro)

            dados = getattr(item, "dados", b"")
            if len(dados) > peso_max:
                r.erro(f"imagens_pmax.{papel}", getattr(item, "nome", "?"),
                       f"{len(dados)} bytes acima do máximo {peso_max} "
                       f"(5120 KB, matriz §4) — a API responde "
                       f"MediaUploadError e recusa o mutate inteiro",
                       plano.ASSET_ACIMA_DO_TETO)

            if isinstance(item, AssetRemotoAprovado):
                if not _RESOURCE_ASSET.fullmatch(item.resource_name):
                    r.erro(f"imagens_pmax.{papel}", item.resource_name,
                           "resource name fora da forma canônica "
                           "`customers/<cid>/assets/<id>`; id negativo é "
                           "temporário e invadiria a faixa de outro canal",
                           plano.RESOURCE_NAME_INVALIDO)

    for rn in imagens.videos_youtube:
        if not isinstance(rn, str) or not _RESOURCE_ASSET.fullmatch(rn):
            r.erro("imagens_pmax.videos_youtube", str(rn),
                   "vídeo entra por resource name de Asset já criado, na forma "
                   "`customers/<cid>/assets/<id>` — `YouTubeVideoAsset` não "
                   "carrega bytes para conferir aqui",
                   plano.RESOURCE_NAME_INVALIDO)
            continue
        if _RESOURCE_ASSET.fullmatch(rn).group(1) != str(cid):
            r.erro("imagens_pmax.videos_youtube", rn,
                   f"o vídeo não está na conta {cid}",
                   plano.RESOURCE_NAME_INVALIDO)

    return imagens


# ═══════════════════════════════════════════════════════════════════════════
# O CONSTRUTOR
# ═══════════════════════════════════════════════════════════════════════════


def construir(cid: str, brief: Brief, *, login_customer_id: str):
    """Monta o grafo de Performance Max sem executar chamada externa.

    Devolve `(operacoes, resultado)`. Mesma forma dos outros três canais — e
    conteúdo completamente diferente, porque a hierarquia é outra.
    """
    r = validacao.Resultado()

    suporte = sondar_proto_v25()
    if not suporte.disponivel:
        r.erro("sdk.google_ads.v25", "indisponível",
               suporte.motivo + "; capacidade Performance Max rebaixada, sem "
               "fallback para outra versão",
               plano.SDK_V25_INDISPONIVEL)
        return [], r

    _recusar_o_que_nao_e_de_pmax(brief, r)
    cfg = _checar_contrato(brief, r)
    _checar_mensuracao(cid, brief, cfg, r, login_customer_id=login_customer_id)

    pol = conteudo.abrir_portao(brief, r)

    headlines = conteudo.forma(brief.copy.headlines, "headline_pmax", r,
                               explicacao_dki=_EXPLICACAO_DKI)
    longas = conteudo.forma(brief.copy.long_headlines, "long_headline_pmax", r,
                            explicacao_dki=_EXPLICACAO_DKI)
    descriptions = conteudo.forma(brief.copy.descriptions, "description_pmax", r,
                                  explicacao_dki=_EXPLICACAO_DKI)
    nomes = conteudo.forma([brief.copy.business_name], "business_name", r)
    if not brief.copy.business_name.strip():
        r.erro("business_name", "",
               "o asset group exige BUSINESS_NAME (exatamente 1, ≤25 de "
               "largura) — como AssetGroupAsset com brand guidelines "
               "desligado, ou como CampaignAsset com ele ligado. Nos dois "
               "casos, obrigatório",
               plano.ASSET_OBRIGATORIO_AUSENTE)

    conteudo.politica(pol, headlines, "headline_pmax", r)
    conteudo.politica(pol, longas, "long_headline_pmax", r)
    conteudo.politica(pol, descriptions, "description_pmax", r)
    conteudo.politica(pol, nomes, "business_name", r)

    imagens = _checar_assets(cid, brief, cfg, r)

    if not r.ok or cfg is None:
        return [], r

    ts = brief.carimbo_nome or comum.carimbo()
    base = conteudo.nome_da_campanha(
        brief, ts, marcador=taxonomia.MODIFICADOR[CANAL])

    # A autenticação é dependência de MONTAGEM, não de validação local. Antes
    # deste portão, um brief já inválido renovaria OAuth e "Google fora do ar"
    # viraria "contrato incompleto" — a mesma razão documentada em display.py.
    c = cliente(login_customer_id)

    ops = [
        comum.op_budget(c, cid, brief, f"Budget_{ts}", periodo="DAILY"),
        comum.op_campanha(c, cid, brief, base, CANAL),
        comum.op_geo(c, cid, brief),
        comum.op_idioma(c, cid, brief),
    ]

    for termo in cfg.negativas or ():
        ops.append(_op_keyword_negativa(c, cid, termo))

    grupo_rn = comum.temp_asset_group(cid, 0)
    nome_grupo = cfg.nome_do_asset_group or f"AssetGroup_{ts}"
    url = comum.url_destino(brief)

    # ⚠️ ORDEM. A API resolve id temporário só DEPOIS de ele ser definido, e
    # `AssetGroupAsset` referencia o asset E o grupo. Por isso: assets primeiro,
    # grupo depois, vínculos por último. Inserir os vínculos antes faria a API
    # recusar o mutate inteiro com um erro sobre o VÍNCULO — e o defeito
    # estaria na ordem da lista.
    ops_de_asset: list = []
    vinculos: list[tuple[str, PMaxAssetFieldType]] = []
    contador_texto = 0
    contador_imagem = 0

    def _texto(valor: str, campo: PMaxAssetFieldType) -> None:
        nonlocal contador_texto
        rn = comum.temp_asset(cid, contador_texto)
        contador_texto += 1
        o = c.get_type("MutateOperation")
        cria = o.asset_operation.create
        cria.resource_name = rn
        cria.name = f"{campo.value}_{ts}_{contador_texto}"
        cria.text_asset.text = valor
        ops_de_asset.append(o)
        vinculos.append((rn, campo))

    for t in headlines:
        _texto(t, PMaxAssetFieldType.HEADLINE)
    for t in longas:
        _texto(t, PMaxAssetFieldType.LONG_HEADLINE)
    for t in descriptions:
        _texto(t, PMaxAssetFieldType.DESCRIPTION)

    # BUSINESS_NAME e LOGO mudam de NÍVEL conforme brand guidelines (§5). Não é
    # uma variação cosmética: com ele ligado, deixá-los no asset group responde
    # `AssetLinkError.BRAND_ASSETS_NOT_LINKED_AT_CAMPAIGN_LEVEL`; com ele
    # desligado, deixá-los na campanha responde
    # `CampaignError.REQUIRED_BUSINESS_NAME_ASSET_NOT_LINKED`.
    marca: list[tuple[str, PMaxAssetFieldType]] = []
    rn_nome = comum.temp_asset(cid, contador_texto)
    contador_texto += 1
    o_nome = c.get_type("MutateOperation")
    cria_nome = o_nome.asset_operation.create
    cria_nome.resource_name = rn_nome
    cria_nome.name = f"BUSINESS_NAME_{ts}"
    cria_nome.text_asset.text = nomes[0]
    ops_de_asset.append(o_nome)
    marca.append((rn_nome, PMaxAssetFieldType.BUSINESS_NAME))

    for papel in ImagensPMax.PAPEIS:
        campo = CAMPO_DE_ASSET[papel]
        for item in getattr(imagens, papel):
            if isinstance(item, AssetRemotoAprovado):
                rn = item.resource_name
            else:
                rn = comum.temp_imagem(cid, contador_imagem)
                contador_imagem += 1
                o = c.get_type("MutateOperation")
                cria = o.asset_operation.create
                cria.resource_name = rn
                cria.name = item.nome
                cria.type_ = c.enums.AssetTypeEnum.IMAGE
                cria.image_asset.data = item.dados
                ops_de_asset.append(o)
            if campo is PMaxAssetFieldType.LOGO:
                marca.append((rn, campo))
            else:
                vinculos.append((rn, campo))

    for rn in imagens.videos_youtube:
        vinculos.append((rn, PMaxAssetFieldType.YOUTUBE_VIDEO))

    ops.extend(ops_de_asset)

    if cfg.brand_guidelines_enabled:
        for rn, campo in marca:
            ops.append(_op_campaign_asset(c, cid, rn, campo))
    else:
        vinculos.extend(marca)

    ops.append(_op_asset_group(c, cid, grupo_rn, nome_grupo, url))
    for rn, campo in vinculos:
        ops.append(_op_asset_group_asset(c, grupo_rn, rn, campo))
    for sinal in cfg.sinais or ():
        ops.append(_op_sinal(c, grupo_rn, sinal))

    return ops, r


def _op_keyword_negativa(c, cid: str, termo: str):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    cr.negative = True
    cr.keyword.text = termo
    # BROAD como negativa é o alcance mais largo, e é o que Search já usa para
    # negativa de campanha. Em PMax não há match type positivo com que comparar.
    cr.keyword.match_type = c.enums.KeywordMatchTypeEnum.BROAD
    return o


def _op_asset_group(c, cid: str, rn: str, nome: str, url: str):
    o = c.get_type("MutateOperation")
    ag = o.asset_group_operation.create
    ag.resource_name = rn
    ag.name = nome
    ag.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    ag.final_urls.append(url)
    # PAUSED como a campanha. Um asset group ENABLED numa campanha PAUSED não
    # veicula, mas despausar a campanha o acordaria junto — e a decisão de
    # veicular tem de ser um ato só, explícito.
    ag.status = c.enums.AssetGroupStatusEnum.PAUSED
    return o


def _op_asset_group_asset(c, grupo_rn: str, asset_rn: str,
                          campo: PMaxAssetFieldType):
    o = c.get_type("MutateOperation")
    v = o.asset_group_asset_operation.create
    v.asset_group = grupo_rn
    v.asset = asset_rn
    v.field_type = getattr(c.enums.AssetFieldTypeEnum, campo.value)
    return o


def _op_campaign_asset(c, cid: str, asset_rn: str, campo: PMaxAssetFieldType):
    o = c.get_type("MutateOperation")
    ca = o.campaign_asset_operation.create
    ca.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    ca.asset = asset_rn
    ca.field_type = getattr(c.enums.AssetFieldTypeEnum, campo.value)
    return o


def _op_sinal(c, grupo_rn: str, sinal):
    o = c.get_type("MutateOperation")
    s = o.asset_group_signal_operation.create
    s.asset_group = grupo_rn
    if sinal.tipo == "audience":
        s.audience.audience = sinal.valor
    else:
        s.search_theme.text = sinal.valor
    return o


# ═══════════════════════════════════════════════════════════════════════════
# O PLANO — e o portão de cobertura que reusa o observador
# ═══════════════════════════════════════════════════════════════════════════


def _dto_do_plano(p: plano.PlanoDeCanal, cfg) -> PMaxAssetGroupDTO:
    """Projeta o plano num `PMaxAssetGroupDTO` para reusar o avaliador real.

    Não é um dublê: é o mesmo tipo que `observabilidade_pmax` monta ao LER uma
    conta. Rodar `evaluate_asset_group_coverage` sobre ele faz o portão de
    criação usar exatamente a régua com que o observador julgará a campanha
    depois de criada — o que é criado passa a não poder ser reprovado pelo
    próprio sistema no dia seguinte.
    """
    unidade = next((u for u in p.unidades if u.tipo == "asset_group"), None)
    vinculos: list[PMaxAssetGroupAssetDTO] = []
    itens = list(unidade.assets) if unidade else []
    itens.extend(p.assets_de_campanha)
    for i, a in enumerate(itens):
        try:
            campo = PMaxAssetFieldType(a.papel)
        except ValueError:
            campo = PMaxAssetFieldType.UNKNOWN
        vinculos.append(PMaxAssetGroupAssetDTO(
            resource_name=f"planejado/assetGroupAssets/{i}",
            asset_group_id="planejado",
            asset_id=a.identidade,
            field_type=campo,
            status="ENABLED",
            primary_status=ObservedValue.not_collected("plano"),
            primary_status_reasons=(),
            primary_status_details=(),
            source=ObservedValue.present("PLANEJADO"),
            policy_approval_status=ObservedValue.not_collected("plano"),
            policy_summary_reasons=(),
            asset_details=PMaxAssetDTO(
                resource_name=a.identidade,
                id=a.identidade,
                name=ObservedValue.present(a.identidade),
                asset_type="TEXT" if a.origem == "texto" else "IMAGE",
                # O texto do asset é o que decide a regra "ao menos uma
                # DESCRIPTION ≤ 60". `identidade` carrega o texto quando a
                # origem é texto; nos outros papéis o campo é `not_collected`,
                # e o avaliador trata isso como INDETERMINATE em vez de
                # inventar um comprimento.
                text_content=(ObservedValue.present(a.identidade)
                              if a.origem == "texto"
                              else ObservedValue.not_applicable("plano")),
                youtube_video_id=ObservedValue.not_applicable("plano"),
                youtube_video_title=ObservedValue.not_applicable("plano"),
                image_url=ObservedValue.not_applicable("plano"),
                policy_approval_status=ObservedValue.not_collected("plano"),
                policy_topic_entries=(),
            ),
        ))
    return PMaxAssetGroupDTO(
        resource_name="planejado/assetGroups/0",
        id="planejado",
        campaign_id="planejado",
        name=unidade.nome if unidade else "",
        status=PMaxAssetGroupStatus.PAUSED,
        primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.PAUSED),
        primary_status_reasons=(),
        ad_strength=ObservedValue.not_applicable("plano: nada foi criado"),
        asset_coverage=ObservedValue.not_applicable("plano: nada foi criado"),
        final_urls=unidade.urls_finais if unidade else (),
        final_mobile_urls=(),
        # `path1`/`path2` são o caminho de exibição da URL. Este builder não os
        # emite, e `not_applicable` diz isso — não `""`, que afirmaria um
        # caminho vazio escolhido.
        path1=ObservedValue.not_applicable("plano: builder não emite path"),
        path2=ObservedValue.not_applicable("plano: builder não emite path"),
        assets=tuple(vinculos),
        signals=(),
    )


def _prontidao(cfg, r: validacao.Resultado, ops) -> plano.Prontidao:
    monta = bool(ops) and r.ok
    return plano.Prontidao(
        monta=monta,
        pode_provar=monta,
        pode_criar=monta,
        motivo_nao_monta=("" if monta else
                          "o brief não passou na validação local; veja bloqueios"),
        motivo_nao_prova=("" if monta else
                          "sem payload local aprovado não há validate_only seguro"),
        motivo_nao_cria=("" if monta else
                         "sem payload local aprovado e selado não há criação PAUSED segura"),
    )


def planejar(cid: str, brief: Brief, *, login_customer_id: str) -> plano.PlanoDeCanal:
    """Monta offline e devolve o plano serializável. **Nunca fala com o Google.**

    O que este canal acrescenta aos outros três: depois de projetar, o plano é
    passado por `evaluate_asset_group_coverage` — o mesmo avaliador que
    `observabilidade_pmax` usa para julgar uma campanha já criada — e cada
    lacuna estrutural vira um bloqueio com código.
    """
    ops, r = construir(cid, brief, login_customer_id=login_customer_id)
    cfg = brief.pmax
    p = plano.projetar(
        canal=CANAL,
        customer_id=cid,
        login_customer_id=login_customer_id,
        operacoes=ops,
        resultado=r,
        prontidao=_prontidao(cfg, r, ops),
        nao_operado=NAO_OPERADO,
        aberto_por_ausencia=(
            "audiência: PMax não tem targeting positivo por audiência. O "
            "substituto é o AssetGroupSignal, que é DICA e não restrição — o "
            "Google pode servir fora do sinal.",
            "rede: PMax serve em Search, Display, YouTube, Discover, Gmail e "
            "Maps sem opt-out (matriz §13). Não existe controle de rede.",
        ),
        nivel_geo_idioma="campanha",
    )

    bloqueios = list(p.bloqueios)

    if ops:
        relatorio = evaluate_asset_group_coverage(
            _dto_do_plano(p, cfg),
            brand_guidelines_enabled=(
                cfg.brand_guidelines_enabled if cfg is not None else None),
        )
        for lacuna in relatorio.structural_gaps:
            bloqueios.append(plano.Achado(
                codigo=plano.ASSET_OBRIGATORIO_AUSENTE
                if "minimum required" in lacuna or "60 characters" in lacuna
                else plano.ASSET_ACIMA_DO_TETO,
                campo="asset_group.cobertura",
                causa=f"{lacuna} [PMAX_FIELD_REQUIREMENTS, "
                      f"veredito {relatorio.verdict.value}]",
                valor=relatorio.asset_group_name,
            ))
        avisos = list(p.avisos)
        for a in relatorio.warnings:
            avisos.append(plano.Achado(
                codigo=plano.BLOQUEIO_NAO_CLASSIFICADO,
                campo="asset_group.cobertura", causa=a,
                valor=relatorio.verdict.value))
        if relatorio.verdict is CoverageVerdict.INDETERMINATE:
            avisos.append(plano.Achado(
                codigo=plano.BLOQUEIO_NAO_CLASSIFICADO,
                campo="asset_group.cobertura",
                causa="a cobertura ficou INDETERMINADA — falta evidência para "
                      "afirmar completude, e isso não é o mesmo que faltar "
                      "asset",
                valor=relatorio.verdict.value))
        p = _com(p, bloqueios=tuple(bloqueios), avisos=tuple(avisos))
    else:
        p = _com(p, bloqueios=tuple(bloqueios))
    return p


def _com(p: plano.PlanoDeCanal, **troca) -> plano.PlanoDeCanal:
    import dataclasses
    return dataclasses.replace(p, **troca)


def validar(cid: str, brief: Brief, *, login_customer_id: str):
    """Validação local + `validate_only`. **Nunca cria recurso.**

    Existe e é chamável, e `planejar()` marca `pode_provar=False` enquanto o
    canal estiver fora do executor — a fronteira externa é decisão de
    autorização, não do builder. Quem chamar isto está declarando que tem a
    autorização.
    """
    ops, r = construir(cid, brief, login_customer_id=login_customer_id)
    if not r.ok:
        return r, None, 0
    falha = validar_mutacoes(cid, ops, login_customer_id=login_customer_id)
    return r, falha, len(ops)
