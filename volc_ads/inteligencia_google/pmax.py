"""Observabilidade read-only de Performance Max no contrato canonico.

Camada de dominio e aplicacao: monta as consultas, projeta as linhas em
``DocumentoColeta`` e decide o que o ledger v12_01 consegue guardar. Nao abre
socket, nao instancia cliente Google, nao fala com o Supabase e nao tem relogio
proprio — quem executa e ``coletor.ColetorGoogleInteligencia``.

## O que esta coleta responde, e o que ela nunca faz

Ela le uma campanha Performance Max ja existente: a campanha, seus grupos de
recursos, os assets vinculados a cada grupo, os sinais do grupo, o desempenho
por grupo numa janela declarada e a segunda opiniao oficial do Google sobre a
forca do anuncio. Ela NAO cria, nao altera, nao ativa, nao pausa, nao remove,
nao aplica recomendacao, nao baixa midia e nao julga qualidade visual.

## Sete familias, e por que sao sete

Uma familia e a pergunta que a leitura respondeu. Elas sao separadas porque
falham separadamente: se os sinais cairem, a estrutura lida continua valida, e
um recibo unico transformaria uma queda parcial num retrato inteiro suspeito.
A dependencia que existe e declarada, nao implicita — ``PMAX_ASSETS`` so sabe
quais assets pedir depois de ``PMAX_ASSET_GROUP_ASSETS``, e quando o
prerequisito nao foi lido a familia FALHA em vez de fingir vazio.

## O que a primeira leitura real corrigiu

Em 01/09/2026 estas perguntas foram feitas a v25 REAL (evidencia sanitizada em
``docs/closure/hermes-p04-t07-pmax-real-read-v1/REAL-READ-SUMMARY.json``). Nove
campos que os descriptors do SDK descrevem voltaram como
``query_error: UNRECOGNIZED_FIELD``: descriptor de proto NAO e contrato de
selecao GAQL, e so a leitura real separou os dois. Eles sairam da projecao sem
substituto — ``CAMPOS_RECUSADOS_PELA_API_V25`` nomeia cada um e o que a coleta
deixou de enxergar, e essa perda viaja no recibo em vez de sumir.

A mesma leitura expos um erro de contrato pior que um campo faltando: com
``PMAX_ASSET_GROUPS`` e ``PMAX_ASSET_GROUP_ASSETS`` caidos, as familias que
dependem delas foram registradas como ``vazio_confirmado`` — "nao ha assets"
afirmado por quem nunca conseguiu perguntar. Hoje isso e impossivel por
construcao: sem prerequisito lido a familia sai ``falhou`` com a causa
estruturada ``DEPENDENCIA_FALHOU:<familia>``, e a decisao mora na projecao
(``documento_assets``, ``documento_sinais``), nao so no coletor que a chama.

## ⚠️ A lacuna que esta coleta nao pode fechar sozinha

O ledger v12_01 fecha ``tipo_sinal`` num CHECK de seis valores
(``trafego_google_coleta_tipo``). Das sete familias, apenas
``PMAX_RECOMENDACOES_FORCA`` cabe — ela E uma leitura de ``recommendation``, e
por ser de escopo de campanha nao colide com a varredura de conta. As outras
seis nao tem lugar no vocabulario, e reaproveitar ``DIAGNOSTICO_ENTREGA`` para
elas seria pior que nao gravar: ``backend/app/trafego/diagnostico_persistido``
le a coleta MAIS RECENTE desse tipo por campanha, entao um recibo PMax passaria
a responder pelo diagnostico Search da mesma campanha.

Entao a persistencia dessas seis PARA — nomeada, com a migration exata que a
destravaria — e o resto da coleta e preservado. O vocabulario aceito e
injetavel (``tipos_sinal_do_ledger``) justamente para que a prova de que o
bloqueio mora no banco, e nao aqui, seja executavel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from volc_ads.observabilidade_pmax import (
    assert_read_only_gaql,
    build_pmax_asset_group_assets_query,
    build_pmax_asset_group_signals_query,
    build_pmax_asset_groups_query,
    build_pmax_assets_query,
    validate_identifier,
)

from .modelo import (
    DocumentoColeta, EstadoColeta, EstadoValor, Item, Metrica, metrica_de_dict,
)

CANAL_PMAX = "PERFORMANCE_MAX"
FONTE_GOOGLE_ADS = "google_ads_api"

FAMILIA_CAMPANHA = "PMAX_CAMPANHA"
FAMILIA_ASSET_GROUPS = "PMAX_ASSET_GROUPS"
FAMILIA_ASSET_GROUP_ASSETS = "PMAX_ASSET_GROUP_ASSETS"
FAMILIA_ASSETS = "PMAX_ASSETS"
FAMILIA_DESEMPENHO = "PMAX_DESEMPENHO_ASSET_GROUP"
FAMILIA_SINAIS = "PMAX_SINAIS"
FAMILIA_RECOMENDACOES = "PMAX_RECOMENDACOES_FORCA"

#: Ordem de execucao. A estrutura vem antes do desempenho porque e ela que diz
#: quais grupos existem — e sem essa lista nao da para distinguir "grupo sem
#: linha na janela" de "grupo que ninguem enumerou".
FAMILIAS_PMAX = (
    FAMILIA_CAMPANHA,
    FAMILIA_ASSET_GROUPS,
    FAMILIA_ASSET_GROUP_ASSETS,
    FAMILIA_ASSETS,
    FAMILIA_DESEMPENHO,
    FAMILIA_SINAIS,
    FAMILIA_RECOMENDACOES,
)

#: Sob qual `tipo_sinal` cada familia pediria para ser gravada. Quando nao ha um
#: valor honesto no vocabulario, a familia pede o proprio nome — e e recusada.
TIPO_SINAL_POR_FAMILIA: dict[str, str] = {
    FAMILIA_CAMPANHA: FAMILIA_CAMPANHA,
    FAMILIA_ASSET_GROUPS: FAMILIA_ASSET_GROUPS,
    FAMILIA_ASSET_GROUP_ASSETS: FAMILIA_ASSET_GROUP_ASSETS,
    FAMILIA_ASSETS: FAMILIA_ASSETS,
    FAMILIA_DESEMPENHO: FAMILIA_DESEMPENHO,
    FAMILIA_SINAIS: FAMILIA_SINAIS,
    # `IMPROVE_PERFORMANCE_MAX_AD_STRENGTH` sai de `FROM recommendation`: e
    # literalmente uma recomendacao armazenada. Escopo de campanha, entao a
    # chave nao colide com a leitura de conta da varredura continua.
    FAMILIA_RECOMENDACOES: "RECOMENDACOES_ARMAZENADAS",
}

#: Espelho EXATO do CHECK `trafego_google_coleta_tipo` da v12_01 aplicada.
#: `test_vocabulario_do_ledger_e_o_da_migration_aplicada` compara os dois; se
#: alguem ampliar o CHECK no banco sem tocar aqui, o teste cai.
TIPOS_SINAL_ACEITOS_PELO_LEDGER = frozenset({
    "DIAGNOSTICO_ENTREGA",
    "RECOMENDACOES_ARMAZENADAS",
    "RECOMENDACOES_GERADAS",
    "SIMULACOES_CAMPANHA",
    "FORECAST_KEYWORDS",
    "EXPERIMENTOS",
})

MIGRATION_NECESSARIA = (
    "v12_03: ALTER TABLE public.trafego_google_inteligencia_coleta "
    "DROP CONSTRAINT trafego_google_coleta_tipo, ADD CONSTRAINT "
    "trafego_google_coleta_tipo CHECK (tipo_sinal IN (<os seis atuais>, "
    "'PMAX_CAMPANHA', 'PMAX_ASSET_GROUPS', 'PMAX_ASSET_GROUP_ASSETS', "
    "'PMAX_ASSETS', 'PMAX_DESEMPENHO_ASSET_GROUP', 'PMAX_SINAIS'))"
)

#: Campos que a doutrina pede e a v25 instalada NAO expoe. Provado contra os
#: descriptors do SDK em `test_h_campo_nao_suportado_e_fato_do_sdk_instalado`.
#: Nomear o buraco e o oposto de preenche-lo com zero.
CAMPOS_NAO_SUPORTADOS_V25: dict[str, str] = {
    "asset_group_asset.performance_label": (
        "a v25 nao expoe rotulo de desempenho por asset em asset_group_asset; "
        "o campo existe apenas em ad_group_ad_asset_view, que e de Search"
    ),
}

#: Campos que EXISTEM na v25 e esta coleta deliberadamente nao pede, para nao
#: alterar consultas de propriedade de outra lane. Declarados para que ninguem
#: leia a ausencia deles no recibo como "o Google nao devolveu".
CAMPOS_NAO_COLETADOS: dict[str, str] = {
    "asset_group_signal.approval_status": (
        "a consulta de sinais e a de volc_ads/observabilidade_pmax/queries.py, "
        "fora do ownership desta entrega; o campo existe na v25 e continua por "
        "coletar"
    ),
    "asset_group_signal.disapproval_reasons": (
        "mesma consulta, mesma razao"
    ),
}

#: Campos que a v25 REAL recusou com `query_error: UNRECOGNIZED_FIELD` na
#: leitura de 01/09/2026, por familia. Todos EXISTEM nos descriptors do SDK
#: instalado — `assert_v25_descriptor_contract` passa com eles — e mesmo assim o
#: endpoint os rejeita. Nenhum ganhou substituto: nada equivalente foi
#: comprovado na v25 real, e inventar um fallback semantico seria pior que o
#: buraco. Cada valor diz o que a coleta DEIXOU DE ENXERGAR.
CAMPOS_RECUSADOS_POR_FAMILIA: dict[str, dict[str, str]] = {
    FAMILIA_ASSET_GROUPS: {
        "asset_group.asset_coverage.ad_strength_action_items.action_item_type": (
            "perde-se QUAL acao o Google sugere para subir a forca do grupo; "
            "`asset_group.ad_strength` continua legivel, mas so como nota, sem "
            "o que fazer a respeito"
        ),
        "asset_group.asset_coverage.ad_strength_action_items.add_asset_details.asset_field_type": (
            "perde-se QUAL tipo de asset falta (titulo, imagem, video)"
        ),
        "asset_group.asset_coverage.ad_strength_action_items.add_asset_details.asset_count": (
            "perde-se QUANTOS assets faltam para a acao sugerida"
        ),
        "asset_group.asset_coverage.ad_strength_action_items.add_asset_details.video_aspect_ratio_requirement": (
            "perde-se a proporcao de video exigida quando a acao e adicionar video"
        ),
    },
    FAMILIA_ASSET_GROUP_ASSETS: {
        "asset_group_asset.primary_status_details.status": (
            "perde-se o detalhe por tras do status do vinculo; "
            "`asset_group_asset.primary_status` e `primary_status_reasons` "
            "continuam sendo lidos, entao resta o motivo grosso, sem o fino"
        ),
        "asset_group_asset.primary_status_details.reason": (
            "perde-se a razao detalhada do status do vinculo"
        ),
        "asset_group_asset.primary_status_details.asset_disapproved.offline_evaluation_error_reasons": (
            "perde-se POR QUE um asset reprovado foi reprovado; "
            "`asset_group_asset.policy_summary` continua trazendo a aprovacao e "
            "os topicos de politica, que e outra pergunta"
        ),
    },
    FAMILIA_RECOMENDACOES: {
        "recommendation.improve_performance_max_ad_strength_recommendation.asset_group": (
            "perde-se A QUAL grupo de recursos a recomendacao se refere; a "
            "recomendacao continua identificada por `resource_name` e ligada a "
            "campanha, mas nao ao grupo dentro dela"
        ),
        "recommendation.improve_performance_max_ad_strength_recommendation.ad_strength": (
            "perde-se a forca que a recomendacao reporta; a de "
            "`asset_group.ad_strength` NAO e substituta — sao duas leituras "
            "diferentes, e trocar uma pela outra seria fallback inventado"
        ),
    },
}

#: A mesma lista, achatada: e ela que a consulta consulta.
CAMPOS_RECUSADOS_PELA_API_V25: dict[str, str] = {
    campo: perda
    for campos in CAMPOS_RECUSADOS_POR_FAMILIA.values()
    for campo, perda in campos.items()
}

#: Quem depende de quem. Declarado aqui, e nao so no coletor, porque quem
#: precisa saber que "sem prerequisito" nao e "vazio" e a projecao.
DEPENDENCIA_POR_FAMILIA: dict[str, str] = {
    FAMILIA_ASSETS: FAMILIA_ASSET_GROUP_ASSETS,
    FAMILIA_SINAIS: FAMILIA_ASSET_GROUPS,
}

CODIGO_DEPENDENCIA_FALHOU = "DEPENDENCIA_FALHOU"
CLASSE_PREREQUISITO = "DependenciaDeLeitura"


def causa_de_dependencia(familia_prerequisito: str) -> str:
    """``DEPENDENCIA_FALHOU:<familia>`` — causa estruturada, legivel por maquina.

    O codigo antigo (``PREREQUISITO_NAO_LIDO``) dizia que faltou prerequisito
    sem dizer QUAL, e quem lesse o ledger tinha de adivinhar pelo payload.
    """

    return f"{CODIGO_DEPENDENCIA_FALHOU}:{familia_prerequisito}"

TIPO_RECOMENDACAO_FORCA = "IMPROVE_PERFORMANCE_MAX_AD_STRENGTH"

#: Uma fotografia diaria mais a folga de uma reexecucao. Acima disso o retrato
#: descreve um passado que ninguem confirmou continuar valendo.
FRESCOR_MAXIMO_SEGUNDOS = 26 * 3600

METRICAS_DE_ASSET_GROUP = (
    ("impressions", None, None),
    ("clicks", None, None),
    ("cost_micros", "micros", "BRL"),
    ("conversions", None, None),
    ("conversions_value", None, "BRL"),
)


class ErroCanalNaoPMax(RuntimeError):
    """O alvo existe e a identidade fecha, mas o canal nao e Performance Max."""


class ErroCampoRecusadoNaConsulta(RuntimeError):
    """Uma consulta desta coleta pediu campo que a v25 real ja recusou."""


def exigir_canal_pmax(canal: str) -> str:
    """Fail-closed ANTES da primeira consulta especifica de PMax.

    Coletar asset groups de uma campanha Search nao devolveria erro: devolveria
    vazio. E um vazio de pergunta errada e indistinguivel de um vazio observado.
    """

    normalizado = str(canal or "").strip().upper()
    if normalizado != CANAL_PMAX:
        raise ErroCanalNaoPMax(
            f"canal {normalizado or 'ausente'} nao e {CANAL_PMAX}: a coleta "
            f"PMax e recusada antes de qualquer consulta"
        )
    return normalizado


# --- ledger: o que cabe no v12_01, e o que nao cabe -------------------------


@dataclass(frozen=True)
class RecusaDePersistencia:
    """A leitura aconteceu; o ledger e que nao tem onde guarda-la."""

    familia: str
    tipo_sinal: str
    motivo: str
    migration_necessaria: str

    def serializar(self) -> dict[str, str]:
        return {
            "familia": self.familia,
            "tipo_sinal": self.tipo_sinal,
            "motivo": self.motivo,
            "migration_necessaria": self.migration_necessaria,
        }


def recusa_de_persistencia(
    familia: str, *, tipos_aceitos: frozenset[str] | None = None,
) -> RecusaDePersistencia | None:
    aceitos = TIPOS_SINAL_ACEITOS_PELO_LEDGER if tipos_aceitos is None else tipos_aceitos
    tipo = TIPO_SINAL_POR_FAMILIA[familia]
    if tipo in aceitos:
        return None
    return RecusaDePersistencia(
        familia=familia,
        tipo_sinal=tipo,
        motivo=(
            f"o CHECK trafego_google_coleta_tipo da v12_01 nao admite "
            f"'{tipo}'; gravar sob um dos seis valores existentes faria este "
            f"recibo responder por outra pergunta"
        ),
        migration_necessaria=MIGRATION_NECESSARIA,
    )


# --- consultas: somente SELECT, todas conferidas na construcao --------------


def _id_seguro(valor: Any, campo: str) -> str:
    return validate_identifier(str(valor), campo)


def campos_projetados(gaql: str) -> list[str]:
    """A lista do SELECT, campo a campo — sem o FROM e sem o WHERE.

    Comparar por campo, e nao por substring, e o que impede
    ``asset_group.ad_strength`` de ser confundido com
    ``...add_asset_details.asset_field_type`` na hora de podar.
    """

    normalizado = " ".join(gaql.split())
    fim = normalizado.upper().find(" FROM ")
    if not normalizado.upper().startswith("SELECT ") or fim < 0:
        raise ValueError("consulta sem projecao legivel: nao da para conferir campos")
    return [c.strip() for c in normalizado[len("SELECT "):fim].split(",") if c.strip()]


def assert_sem_campos_recusados(gaql: str) -> None:
    """Fail-closed contra reintroduzir um campo que a v25 REAL ja recusou.

    Este e o unico ponto por onde as sete consultas passam, entao o erro que
    derrubou tres familias na primeira leitura real nao volta em silencio — nem
    por edicao aqui, nem por um builder de outra lane mudando debaixo.
    """

    recusados = [
        campo for campo in campos_projetados(gaql)
        if campo in CAMPOS_RECUSADOS_PELA_API_V25
    ]
    if recusados:
        raise ErroCampoRecusadoNaConsulta(
            f"a v25 real recusou {sorted(recusados)} com UNRECOGNIZED_FIELD; "
            f"remova o campo e declare a perda de cobertura — nao troque por "
            f"outro campo sem prova de equivalencia"
        )


def sem_campos_recusados(gaql: str) -> str:
    """Devolve a consulta sem os campos que a v25 real recusou.

    Poda, nunca substitui. Existe porque os builders de
    ``volc_ads/observabilidade_pmax/queries.py`` sao de outra lane e continuam
    projetando os campos que os descriptors do SDK descrevem — mexer neles aqui
    trocaria uma correcao por uma mudanca fora do escopo desta entrega.
    """

    normalizado = " ".join(gaql.split())
    mantidos = [
        campo for campo in campos_projetados(normalizado)
        if campo not in CAMPOS_RECUSADOS_PELA_API_V25
    ]
    if not mantidos:
        raise ErroCampoRecusadoNaConsulta(
            "a poda deixaria a consulta sem projecao alguma"
        )
    return f"SELECT {', '.join(mantidos)}{normalizado[normalizado.upper().find(' FROM '):]}"


def _select(gaql: str) -> str:
    """Toda consulta desta coleta passa por aqui antes de existir."""

    normalizado = " ".join(gaql.split())
    assert_read_only_gaql(normalizado)
    assert_sem_campos_recusados(normalizado)
    return normalizado


def query_campanha(campaign_id: str) -> str:
    """Identidade e estado da campanha. Sem metrica, de proposito.

    Metrica sem ``segments.date`` seria metrica de janela nao declarada — e a
    janela desta coleta mora na familia de desempenho, onde ela e explicita.
    """

    return _select(f"""
      SELECT campaign.id, campaign.resource_name, campaign.name,
             campaign.status, campaign.primary_status,
             campaign.primary_status_reasons, campaign.serving_status,
             campaign.advertising_channel_type,
             campaign.bidding_strategy_type, campaign.start_date_time,
             campaign.brand_guidelines_enabled,
             campaign_budget.amount_micros
      FROM campaign
      WHERE campaign.id = {_id_seguro(campaign_id, "campaign_id")}
        AND campaign.advertising_channel_type = '{CANAL_PMAX}'
    """)


def query_asset_groups(campaign_id: str) -> str:
    """Estrutura do grupo, menos os quatro campos de ``asset_coverage``.

    A v25 real recusou os quatro juntos e derrubou a familia inteira: um campo
    impossivel de selecionar nao custa um campo, custa a consulta.
    """

    return _select(sem_campos_recusados(
        build_pmax_asset_groups_query(campaign_ids=[campaign_id])
    ))


def query_asset_group_assets(customer_id: str, campaign_id: str) -> str:
    """Vinculos do grupo, menos os tres campos de ``primary_status_details``."""

    return _select(sem_campos_recusados(build_pmax_asset_group_assets_query(
        customer_id, campaign_ids=[campaign_id],
    )))


def query_assets(asset_ids: Sequence[str]) -> str:
    if not asset_ids:
        raise ValueError("consulta de assets exige ids; sem eles ela leria a conta inteira")
    return _select(build_pmax_assets_query(asset_ids=list(asset_ids)))


def query_sinais(customer_id: str, asset_group_ids: Sequence[str]) -> str:
    if not asset_group_ids:
        raise ValueError("consulta de sinais exige grupos; sem eles ela leria a conta inteira")
    return _select(build_pmax_asset_group_signals_query(
        customer_id, asset_group_ids=list(asset_group_ids),
    ))


def query_desempenho(campaign_id: str, inicio: date, fim: date) -> str:
    """Desempenho por asset group, na janela declarada.

    Doutrina oficial lida em 01/09/2026 (asset-group-reporting): ``FROM
    asset_group`` com ``metrics.*`` e ``segments.date``.
    """

    return _select(f"""
      SELECT asset_group.id, asset_group.resource_name, asset_group.name,
             asset_group.primary_status, campaign.id,
             metrics.impressions, metrics.clicks, metrics.cost_micros,
             metrics.conversions, metrics.conversions_value
      FROM asset_group
      WHERE campaign.id = {_id_seguro(campaign_id, "campaign_id")}
        AND segments.date BETWEEN '{inicio.isoformat()}' AND '{fim.isoformat()}'
    """)


def query_desempenho_por_canal(campaign_id: str, inicio: date, fim: date) -> str:
    """Mesma janela, segmentada por rede — a "performance by channel" oficial."""

    return _select(f"""
      SELECT asset_group.id, asset_group.name, segments.ad_network_type,
             metrics.impressions, metrics.clicks, metrics.conversions,
             metrics.cost_micros
      FROM asset_group
      WHERE campaign.id = {_id_seguro(campaign_id, "campaign_id")}
        AND segments.date BETWEEN '{inicio.isoformat()}' AND '{fim.isoformat()}'
    """)


def query_recomendacoes_forca() -> str:
    """Recomendacoes de forca de PMax da conta.

    ⚠️ Sem ``WHERE recommendation.campaign = ...``. A doutrina oficial so
    demonstra filtro por ``recommendation.type``; assumir que o campo de
    campanha e filtravel arriscaria um erro de consulta que apagaria a familia
    inteira. O recorte por campanha e feito LOCALMENTE, e o recibo diz isso.

    ⚠️ Sem o detalhe ``improve_performance_max_ad_strength_recommendation.*``:
    a v25 real recusou os dois campos e a familia caiu inteira. Resta a
    existencia da recomendacao e a campanha dela — nao o grupo nem a forca.
    """

    return _select(f"""
      SELECT recommendation.resource_name, recommendation.type,
             recommendation.campaign, recommendation.dismissed
      FROM recommendation
      WHERE recommendation.type = '{TIPO_RECOMENDACAO_FORCA}'
    """)


# --- projecao: linhas cruas -> documento canonico ---------------------------


def id_do_recurso(nome: Any) -> str | None:
    """``customers/123/assetGroups/2001`` -> ``2001``. Sem palpite."""

    if not isinstance(nome, str) or "/" not in nome:
        return None
    ultimo = nome.rsplit("/", 1)[1].strip()
    return ultimo or None


def _base(
    familia: str, *, campanha: Any, login_customer_id: str, bucket: str,
) -> dict[str, Any]:
    """A identidade que TODO recibo desta coleta carrega, sem excecao.

    Conta, MCC, identidade interna e ID externo juntos: e o par interno/externo
    que impede duas contas com o mesmo `campaign_id` de virarem a mesma coisa.
    """

    return {
        "tipo_sinal": TIPO_SINAL_POR_FAMILIA[familia],
        "familia": familia,
        "customer_id": campanha.customer_id,
        "login_customer_id": login_customer_id,
        "bucket": bucket,
        "volc_campaign_id": campanha.volc_campaign_id,
        "campaign_id": campanha.campaign_id,
    }


def _payload(
    *, janela: tuple[date, date], **extra: Any,
) -> dict[str, Any]:
    """Todo recibo desta coleta carrega procedencia, leitura e janela."""

    return {
        "somente_leitura": True,
        "fonte": FONTE_GOOGLE_ADS,
        "canal": CANAL_PMAX,
        # A janela da EXECUCAO, presente em toda familia. So a familia de
        # desempenho a aplica como recorte de metrica — as estruturais leem o
        # estado corrente, sem segmentacao por data, e dizer o contrario
        # inventaria um recorte que a consulta nao tem.
        "janela_da_execucao": [janela[0].isoformat(), janela[1].isoformat()],
        **extra,
    }


def documento_campanha(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]],
) -> DocumentoColeta:
    """A campanha PMax como a API a enxerga — em qualquer estado externo."""

    observada = dict(linhas[0]) if linhas else {}
    campo = observada.get("campaign", {})
    return DocumentoColeta.agora(
        estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
        quantidade=len(linhas),  # preenchido pelo coletor
        payload=_payload(
            janela=janela,
            status_observado=campo.get("status"),
            primary_status_observado=campo.get("primary_status"),
            serving_status_observado=campo.get("serving_status"),
            brand_guidelines_enabled=campo.get("brand_guidelines_enabled"),
            # Zero linha aqui e "a API nao devolveu campanha PMax com esse id".
            # Isso NAO e "campanha removida" e NAO e "campanha inexistente":
            # sao tres coisas, e so uma delas foi observada.
            motivo=None if linhas else "nenhuma campanha PMax com este id na resposta",
        ),
        itens=[Item("campaign", dict(linha), campanha.campaign_id) for linha in linhas],
        **_base(FAMILIA_CAMPANHA, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_asset_groups(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]],
) -> DocumentoColeta:
    itens: list[Item] = []
    metricas: list[Metrica] = []
    for linha in linhas:
        grupo = linha.get("asset_group", {})
        identificador = str(grupo.get("id") or id_do_recurso(grupo.get("resource_name")) or "")
        itens.append(Item("asset_group", dict(linha), grupo.get("resource_name")))
        if not identificador:
            continue
        for nome in ("ad_strength", "primary_status", "status"):
            metricas.append(metrica_de_dict(
                linha, ("asset_group", nome), recurso_tipo="asset_group",
                recurso_externo=identificador, nome=nome,
            ))
        # `asset_coverage_action_items` SAIU: a v25 real recusa os campos, entao
        # a consulta nao os pede mais. Emitir a metrica como `ausente` diria "o
        # Google nao devolveu" sobre algo que ninguem chegou a perguntar — e
        # esse e o mesmo erro que esta correcao existe para desfazer. A perda
        # esta declarada no payload, onde tem nome e causa.
    return DocumentoColeta.agora(
        estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
        quantidade=len(linhas),
        payload=_payload(
            janela=janela, sem_filtro_de_status=True,
            campos_recusados_pela_api=dict(
                CAMPOS_RECUSADOS_POR_FAMILIA[FAMILIA_ASSET_GROUPS]
            ),
        ),
        itens=itens, metricas=metricas,
        **_base(FAMILIA_ASSET_GROUPS, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_asset_group_assets(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]],
) -> DocumentoColeta:
    itens = [
        Item(
            "asset_group_asset", dict(linha),
            linha.get("asset_group_asset", {}).get("resource_name"),
        )
        for linha in linhas
    ]
    return DocumentoColeta.agora(
        estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
        quantidade=len(linhas),
        payload=_payload(
            janela=janela,
            # Duas listas, duas causas diferentes, deliberadamente separadas: o
            # SDK v25 nao tem `performance_label` (adjudicado por
            # GoogleAdsFieldService), e a v25 real recusa campos que o SDK TEM.
            campos_nao_suportados=dict(CAMPOS_NAO_SUPORTADOS_V25),
            campos_recusados_pela_api=dict(
                CAMPOS_RECUSADOS_POR_FAMILIA[FAMILIA_ASSET_GROUP_ASSETS]
            ),
        ),
        itens=itens,
        **_base(FAMILIA_ASSET_GROUP_ASSETS, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_assets(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]], pedidos: Sequence[str] | None,
) -> DocumentoColeta:
    """Metadados dos assets pedidos. Nenhum byte de midia atravessa daqui.

    ``pedidos=None`` quer dizer que ``PMAX_ASSET_GROUP_ASSETS`` nao concluiu —
    nao existe lista de assets a pedir, e nao existe "nenhum asset" observado.
    ``pedidos=[]`` e outra coisa: os vinculos FORAM lidos e nao tinham asset.
    Achatar as duas em ``vazio_confirmado`` foi exatamente o que a primeira
    leitura real fez, e e por isso que a distincao mora aqui e nao no chamador.
    """

    if pedidos is None:
        if linhas:
            raise ValueError(
                "assets sem prerequisito lido nao podem trazer linhas: de onde "
                "elas viriam, se ninguem soube quais assets pedir?"
            )
        return documento_prerequisito(
            FAMILIA_ASSETS, campanha=campanha,
            login_customer_id=login_customer_id, bucket=bucket, janela=janela,
            dependia_de=DEPENDENCIA_POR_FAMILIA[FAMILIA_ASSETS],
        )

    itens = [
        Item("asset", dict(linha), linha.get("asset", {}).get("resource_name"))
        for linha in linhas
    ]
    devolvidos = {
        str(linha.get("asset", {}).get("id") or "") for linha in linhas
    }
    return DocumentoColeta.agora(
        estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
        quantidade=len(linhas),
        payload=_payload(
            janela=janela,
            assets_pedidos=len(pedidos),
            # Pedido sem resposta e um fato: o vinculo aponta para um asset que
            # a consulta de assets nao devolveu.
            assets_pedidos_sem_resposta=sorted(set(pedidos) - devolvidos),
            midia_baixada=False,
        ),
        itens=itens,
        **_base(FAMILIA_ASSETS, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_desempenho(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]],
    grupos_conhecidos: Sequence[str] | None,
    por_canal: Sequence[Mapping[str, Any]] | None,
    falha_por_canal: Mapping[str, str] | None,
) -> DocumentoColeta:
    """Metricas por grupo na janela. Zero medido e ausencia de linha diferem.

    ``grupos_conhecidos`` vem da familia de estrutura. Quando ela nao foi lida,
    o argumento chega ``None`` — e ai NAO se emite ausencia para grupo nenhum:
    afirmar que o grupo X nao teve linha exige antes saber que o grupo X existe.
    """

    por_grupo: dict[str, Mapping[str, Any]] = {}
    for linha in linhas:
        grupo = linha.get("asset_group", {})
        identificador = str(grupo.get("id") or id_do_recurso(grupo.get("resource_name")) or "")
        if identificador:
            por_grupo[identificador] = linha

    if grupos_conhecidos is None:
        alvos = list(por_grupo)
        sem_linha: list[str] | None = None
    else:
        alvos = sorted(set(grupos_conhecidos) | set(por_grupo))
        sem_linha = sorted(set(grupos_conhecidos) - set(por_grupo))

    metricas: list[Metrica] = []
    for identificador in alvos:
        linha = por_grupo.get(identificador)
        for nome, unidade, moeda in METRICAS_DE_ASSET_GROUP:
            if linha is None:
                # Sem linha na janela: nao ha valor observado. Emitir zero aqui
                # seria a afirmacao mais barata e mais errada desta coleta.
                metricas.append(Metrica(
                    "asset_group", identificador, nome, EstadoValor.AUSENTE,
                    unidade=unidade, moeda=moeda,
                ))
                continue
            metricas.append(metrica_de_dict(
                linha, ("metrics", nome), recurso_tipo="asset_group",
                recurso_externo=identificador, nome=nome,
                unidade=unidade, moeda=moeda,
            ))

    itens = [
        Item(
            "asset_group_desempenho", dict(linha),
            linha.get("asset_group", {}).get("resource_name"),
        )
        for linha in linhas
    ]
    segmentacao: dict[str, Any]
    if falha_por_canal is not None:
        segmentacao = {"estado": "falhou", **falha_por_canal}
    elif por_canal is None:
        segmentacao = {"estado": "nao_consultada"}
    else:
        segmentacao = {"estado": "medida", "linhas": len(por_canal)}
        itens.extend(
            Item("asset_group_desempenho_por_canal", dict(linha))
            for linha in por_canal
        )

    estado = EstadoColeta.COM_DADOS if itens else EstadoColeta.VAZIO_CONFIRMADO
    if falha_por_canal is not None:
        # Parte respondeu, parte nao: parcial e o unico estado honesto. Nao e
        # falha (a agregada esta ali) e nao e com_dados (falta um pedaco).
        estado = EstadoColeta.PARCIAL
    return DocumentoColeta.agora(
        estado=estado, quantidade=len(itens),
        janela_inicio=janela[0], janela_fim=janela[1],
        payload=_payload(
            janela=janela,
            grupos_conhecidos=None if grupos_conhecidos is None else sorted(grupos_conhecidos),
            grupos_sem_linha=sem_linha,
            grupos_com_linha=sorted(por_grupo),
            segmentacao_por_canal=segmentacao,
        ),
        itens=itens, metricas=metricas,
        **_base(FAMILIA_DESEMPENHO, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_sinais(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]], grupos_conhecidos: Sequence[str] | None,
) -> DocumentoColeta:
    """Sinais dos grupos lidos — e so dos grupos que alguem chegou a ler.

    ``grupos_conhecidos=None`` e ``PMAX_ASSET_GROUPS`` que nao concluiu: sem a
    lista, "nenhum sinal" seria uma afirmacao sobre grupos que ninguem
    enumerou. ``[]`` continua sendo vazio observado.
    """

    if grupos_conhecidos is None:
        if linhas:
            raise ValueError(
                "sinais sem grupos lidos nao podem trazer linhas: a consulta "
                "precisa dos grupos para existir com recorte"
            )
        return documento_prerequisito(
            FAMILIA_SINAIS, campanha=campanha,
            login_customer_id=login_customer_id, bucket=bucket, janela=janela,
            dependia_de=DEPENDENCIA_POR_FAMILIA[FAMILIA_SINAIS],
        )

    itens = [
        Item(
            "asset_group_signal", dict(linha),
            linha.get("asset_group_signal", {}).get("resource_name"),
        )
        for linha in linhas
    ]
    return DocumentoColeta.agora(
        estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
        quantidade=len(linhas),
        payload=_payload(
            janela=janela,
            grupos_consultados=sorted(grupos_conhecidos),
            campos_nao_coletados=dict(CAMPOS_NAO_COLETADOS),
        ),
        itens=itens,
        **_base(FAMILIA_SINAIS, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_recomendacoes(
    *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date],
    linhas: Sequence[Mapping[str, Any]], campanha_observada: bool | None,
) -> DocumentoColeta:
    """Segunda opiniao oficial sobre forca do anuncio. Nunca uma ordem.

    ``campanha_observada=False`` quer dizer que a leitura da campanha VOLTOU e
    nao trouxe campanha PMax alguma com esse id — ai a pergunta nao se aplica.
    ``None`` quer dizer que a leitura da campanha nao concluiu: nesse caso a
    familia e consultada assim mesmo, porque ignorancia nao e inelegibilidade.
    """

    if campanha_observada is False:
        return DocumentoColeta.agora(
            estado=EstadoColeta.INELEGIVEL, quantidade=None,
            payload=_payload(
                janela=janela,
                motivo=(
                    "nenhuma campanha Performance Max com este id foi observada; "
                    "nao existe recomendacao de forca para campanha que a leitura "
                    "nao encontrou"
                ),
                natureza="segunda_opiniao", aplicada=False,
            ),
            **_base(FAMILIA_RECOMENDACOES, campanha=campanha,
                    login_customer_id=login_customer_id, bucket=bucket),
        )

    alvo = f"customers/{campanha.customer_id}/campaigns/{campanha.campaign_id}"
    desta = [
        linha for linha in linhas
        if str(linha.get("recommendation", {}).get("campaign") or "") == alvo
    ]
    return DocumentoColeta.agora(
        estado=EstadoColeta.COM_DADOS if desta else EstadoColeta.VAZIO_CONFIRMADO,
        quantidade=len(desta),
        payload=_payload(
            janela=janela,
            tipo_solicitado=TIPO_RECOMENDACAO_FORCA,
            linhas_na_conta=len(linhas),
            filtro_por_campanha="local",
            motivo_do_filtro_local=(
                "a doutrina oficial so demonstra filtro por recommendation.type; "
                "filtrar por recommendation.campaign no GAQL nao foi provado"
            ),
            campos_recusados_pela_api=dict(
                CAMPOS_RECUSADOS_POR_FAMILIA[FAMILIA_RECOMENDACOES]
            ),
            natureza="segunda_opiniao", aplicada=False,
        ),
        itens=[
            Item("recommendation", dict(linha),
                 linha.get("recommendation", {}).get("resource_name"))
            for linha in desta
        ],
        **_base(FAMILIA_RECOMENDACOES, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


def documento_prerequisito(
    familia: str, *, campanha: Any, login_customer_id: str, bucket: str,
    janela: tuple[date, date], dependia_de: str,
) -> DocumentoColeta:
    """A familia nao foi lida porque a leitura de que ela depende caiu.

    Estado ``falhou``, e nao ``parcial``: parcial e o que a familia de
    desempenho usa quando UMA PARTE respondeu (a agregada chegou, a segmentacao
    por canal caiu). Aqui nada respondeu — nem uma linha, nem um zero — e
    chamar isso de parcial afirmaria uma leitura que nao houve. O que a
    correcao acrescenta e a causa ESTRUTURADA: ``DEPENDENCIA_FALHOU:<familia>``
    no proprio ``erro_codigo``, para que a distincao entre "esta familia caiu" e
    "a familia de que ela depende caiu" sobreviva a ida ao ledger.
    """

    causa = causa_de_dependencia(dependia_de)
    return DocumentoColeta.agora(
        estado=EstadoColeta.FALHOU, quantidade=None,
        payload=_payload(janela=janela, dependia_de=dependia_de, causa=causa),
        erro_codigo=causa, erro_classe=CLASSE_PREREQUISITO,
        erro_detalhe=(
            f"{familia} depende de {dependia_de}, que nao concluiu; sem ela nao "
            f"ha o que perguntar, e perguntar sem recorte leria a conta inteira"
        ),
        **_base(familia, campanha=campanha,
                login_customer_id=login_customer_id, bucket=bucket),
    )


# --- prontidao: o que uma fotografia precisa ter para valer como prova ------


ESTADOS_QUE_OBSERVARAM = frozenset({"com_dados", "vazio_confirmado"})


#: Linhagem de uma fotografia. Um veredito calculado sobre o resultado da
#: propria execucao vale menos que um calculado sobre recibos RELIDOS do ledger:
#: no primeiro caso quem afirma que gravou e quem gravou. Os dois usam a mesma
#: funcao — o que muda e a etiqueta, e ela viaja junto para que ninguem promova
#: um pelo outro por engano.
LINHAGEM_EXECUCAO = "execucao_local"
LINHAGEM_RELEITURA = "releitura_do_ledger"


@dataclass(frozen=True)
class ProntidaoPMax:
    """O veredito de observabilidade — deliberadamente dificil de ficar verde."""

    provada: bool
    faltando: tuple[str, ...]
    motivos: tuple[str, ...]
    linhagem: str = LINHAGEM_EXECUCAO

    def serializar(self) -> dict[str, Any]:
        return {
            "provada": self.provada,
            "faltando": list(self.faltando),
            "motivos": list(self.motivos),
            "linhagem": self.linhagem,
            "autoatestada": self.linhagem == LINHAGEM_EXECUCAO,
        }


def avaliar_prontidao_pmax(
    resultado: Mapping[str, Any], *, agora: datetime,
    frescor_maximo_segundos: int = FRESCOR_MAXIMO_SEGUNDOS,
    linhagem: str = LINHAGEM_EXECUCAO,
) -> ProntidaoPMax:
    """Uma campanha existir nao prova observabilidade. Impressions tampouco.

    So evolui com fotografia COMPLETA — as sete familias — cada uma tendo
    observado de fato, cada uma gravada com recibo, e todas recentes. Falta
    qualquer um dos quatro e o veredito continua fechado, com o motivo dito.

    ⚠️ Funciona igual sobre o resultado de uma execucao e sobre recibos relidos
    do ledger, e e por isso que ``linhagem`` existe: quem for promover o
    bloqueador ``pmax_observabilidade_nao_provada`` precisa de
    ``LINHAGEM_RELEITURA``. Um veredito autoatestado descreve o que este
    processo ACHA que gravou.
    """

    coletas = {c.get("familia"): c for c in resultado.get("coletas", [])}
    faltando: list[str] = []
    motivos: list[str] = []

    for familia in FAMILIAS_PMAX:
        coleta = coletas.get(familia)
        if coleta is None:
            faltando.append(familia)
            motivos.append(f"{familia}: ausente da fotografia")
            continue
        estado = coleta.get("estado")
        if estado not in ESTADOS_QUE_OBSERVARAM:
            faltando.append(familia)
            motivos.append(f"{familia}: estado {estado} nao e leitura concluida")
            continue
        if not coleta.get("persistido"):
            faltando.append(familia)
            motivos.append(f"{familia}: lida mas nao persistida, sem recibo no ledger")
            continue
        instante = _instante(coleta.get("coletada_em"))
        if instante is None:
            faltando.append(familia)
            motivos.append(f"{familia}: sem instante de leitura legivel")
            continue
        idade = (agora - instante).total_seconds()
        if idade < 0 or idade > frescor_maximo_segundos:
            faltando.append(familia)
            motivos.append(
                f"{familia}: frescor fora da janela ({int(idade)}s)"
            )

    provada = not faltando
    if provada:
        motivos.append("as sete familias observaram, foram gravadas e estao recentes")
    return ProntidaoPMax(
        provada=provada, faltando=tuple(faltando), motivos=tuple(motivos),
        linhagem=linhagem,
    )


def _instante(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str):
        return None
    try:
        lido = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


# --- saida para humano: resumo sem payload, sem item, sem metrica -----------


CAMPOS_DO_RESUMO = (
    "familia", "tipo_sinal", "estado", "quantidade", "persistido",
    "coleta_id", "erro_codigo", "erro_classe", "janela_inicio", "janela_fim",
    "coletada_em", "recusa_de_persistencia",
)


def resumo_sanitizado(resultado: Mapping[str, Any]) -> dict[str, Any]:
    """O que pode ser impresso: estado, contagem e recibo. Nunca conteudo.

    Itens e metricas carregam texto de anuncio, URL final e nome de campanha —
    dado do cliente. Eles ficam no banco, atras da service_role, e nao no
    terminal nem no log de um job.

    ``cobertura_perdida`` viaja junto porque a fotografia so e legivel com o que
    ela NAO enxerga do lado: sem isso, quem le o resumo confunde campo que a
    v25 recusou com informacao que a campanha nao tem.
    """

    return {
        "modo": resultado.get("modo"),
        "bucket": resultado.get("bucket"),
        "origem": resultado.get("origem"),
        "canal": resultado.get("canal"),
        "customer_id": resultado.get("customer_id"),
        "campaign_id": resultado.get("campaign_id"),
        "volc_campaign_id": resultado.get("volc_campaign_id"),
        "estado_externo": resultado.get("estado_externo"),
        "janela": resultado.get("janela"),
        "total": resultado.get("total"),
        "coletas": [
            {campo: coleta.get(campo) for campo in CAMPOS_DO_RESUMO}
            for coleta in resultado.get("coletas", [])
        ],
        "lacunas": resultado.get("lacunas", []),
        "cobertura_perdida": dict(CAMPOS_RECUSADOS_PELA_API_V25),
        "prontidao_desta_execucao": resultado.get("prontidao_desta_execucao"),
    }
