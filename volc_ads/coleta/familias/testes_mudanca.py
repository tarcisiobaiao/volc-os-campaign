from __future__ import annotations

import json
from datetime import date, datetime, timezone

from google.ads.googleads.v25.enums.types.change_client_type import ChangeClientTypeEnum
from google.ads.googleads.v25.enums.types.change_event_resource_type import ChangeEventResourceTypeEnum
from google.ads.googleads.v25.enums.types.resource_change_operation import ResourceChangeOperationEnum
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta import executor
from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias.mudanca import FAMILIA, LIMITE
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL",
               colhida_em=datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc))
TIPO = ChangeEventResourceTypeEnum.ChangeEventResourceType
OP = ResourceChangeOperationEnum.ResourceChangeOperation
CLIENTE = ChangeClientTypeEnum.ChangeClientType
CHAVES = {"change_event_rn", "ocorrido_em", "tipo_recurso", "recurso_alterado", "operacao",
          "campaign_id", "ad_group_id", "cliente", "usuario", "campos_alterados", "antes",
          "depois", "colhida_em"}


def _lance() -> GoogleAdsRow:
    """O evento real lido na Crédito Up em 07/10/2026 (teto de CPC 0,60 → 1,00)."""
    r = GoogleAdsRow()
    ev = r.change_event
    ev.resource_name = "customers/5478096539/changeEvents/1791369761210026~0~0"
    ev.change_date_time = "2026-10-07 07:42:41.210026"
    ev.change_resource_type = TIPO.CAMPAIGN
    ev.change_resource_name = "customers/5478096539/campaigns/24278665189"
    ev.resource_change_operation = OP.UPDATE
    ev.client_type = CLIENTE.GOOGLE_ADS_WEB_CLIENT
    ev.user_email = "tarcisio@agenciavolc.com.br"
    ev.changed_fields.paths.append("target_spend.cpc_bid_ceiling_micros")
    ev.old_resource.campaign.target_spend.cpc_bid_ceiling_micros = 600_000
    ev.new_resource.campaign.target_spend.cpc_bid_ceiling_micros = 1_000_000
    ev.campaign = "customers/5478096539/campaigns/24278665189"
    return r


def teste_familia_registrada_com_nome_e_rpc():
    assert todas()["mudanca"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_gaql_tem_janela_do_dia_inteiro_e_limit():
    gaql = FAMILIA.gaql(CTX)
    assert catalogo.invalidos(gaql) == ()
    assert "FROM change_event" in gaql and "segments.date" not in gaql
    assert "change_event.change_date_time >= '2026-10-07 00:00:00'" in gaql
    assert "change_event.change_date_time <= '2026-10-07 23:59:59'" in gaql
    assert gaql.rstrip().endswith(f"LIMIT {LIMITE}") and LIMITE == 10000
    assert FAMILIA.limite == LIMITE


def teste_executor_marca_truncado_quando_bate_no_limit():
    rec = executor.coletar(FAMILIA, CTX, buscar=lambda cid, g: [_lance()] * LIMITE,
                           registrar=lambda rpc, doc: {})
    assert rec.truncado is True
    rec = executor.coletar(FAMILIA, CTX, buscar=lambda cid, g: [_lance()],
                           registrar=lambda rpc, doc: {})
    assert rec.truncado is False


def teste_evento_real_normalizado():
    l = FAMILIA.normalizar(_lance(), CTX)
    assert set(l) == CHAVES
    assert l["ocorrido_em"] == "2026-10-07T07:42:41.210026-03:00"
    assert (l["tipo_recurso"], l["operacao"], l["cliente"]) == ("CAMPAIGN", "UPDATE", "GOOGLE_ADS_WEB_CLIENT")
    assert (l["campaign_id"], l["ad_group_id"]) == ("24278665189", None)
    assert l["campos_alterados"] == ["target_spend.cpc_bid_ceiling_micros"]
    assert l["antes"] == {"target_spend": {"cpc_bid_ceiling_micros": "600000"}}
    assert l["depois"] == {"target_spend": {"cpc_bid_ceiling_micros": "1000000"}}
    assert l["colhida_em"] == CTX.colhida_iso
    assert json.loads(json.dumps(l)) == l


def teste_tipos_sao_texto_lista_ou_dict():
    l = FAMILIA.normalizar(_lance(), CTX)
    for k in CHAVES - {"campos_alterados", "antes", "depois"}:
        assert l[k] is None or isinstance(l[k], str), k
    assert isinstance(l["campos_alterados"], list)
    datetime.fromisoformat(l["ocorrido_em"])


def teste_create_sem_antes_e_ausentes_viram_none():
    r = GoogleAdsRow()
    ev = r.change_event
    ev.resource_name = "customers/5478096539/changeEvents/1~0~0"
    ev.change_date_time = "2026-10-07 23:59:59"
    ev.change_resource_type = TIPO.AD_GROUP_CRITERION
    ev.change_resource_name = "customers/5478096539/adGroupCriteria/193210441352~2432033692024"
    ev.resource_change_operation = OP.CREATE
    ev.new_resource.ad_group_criterion.status = 2
    l = FAMILIA.normalizar(r, CTX)
    assert l["antes"] is None and isinstance(l["depois"], dict)
    assert l["ocorrido_em"] == "2026-10-07T23:59:59-03:00"
    assert l["usuario"] is None and l["campaign_id"] is None and l["campos_alterados"] == []
    # sem `change_event.ad_group`, o grupo sai do id composto do critério
    assert l["ad_group_id"] == "193210441352"


def teste_operacao_fora_do_check_vira_unknown():
    r = _lance()
    r.change_event.resource_change_operation = OP.UNSPECIFIED
    assert FAMILIA.normalizar(r, CTX)["operacao"] == "UNKNOWN"
    r.change_event.resource_change_operation = OP.REMOVE
    assert FAMILIA.normalizar(r, CTX)["operacao"] == "REMOVE"


def teste_documento_padrao_da_familia():
    docs = []
    executor.coletar(FAMILIA, CTX, buscar=lambda cid, g: [_lance()],
                     registrar=lambda rpc, doc: docs.append((rpc, doc)) or {})
    rpc, doc = docs[0]
    assert rpc == "volc_registrar_gads_fatos" and doc["familia"] == "mudanca"
    assert len(doc["linhas"]) == 1 and json.loads(json.dumps(doc)) == doc
