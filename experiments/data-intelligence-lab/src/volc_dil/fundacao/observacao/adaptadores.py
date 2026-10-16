"""Adaptadores puros das tabelas append-only que JÁ EXISTEM em produção para a `Observacao` canônica.

- `adaptar_google_ads_v21(linha)`: uma linha de `google_ads_observation` (v21) juntada com o lote
  (`google_ads_raw_batch`) e a execução (`google_ads_collection_run`) → uma `Observacao` por métrica.
- `adaptar_joinads_v2(linha)`: uma linha de `joinads_observation` (JoinAds v2) juntada com o lote
  (`joinads_raw_batch`) e a execução (`joinads_collection_run`) → uma `Observacao` por métrica.

A `linha` é um mapeamento plano (o resultado da consulta de junção documentada em
`02-CONTRATO-DE-DADOS.md` §9); nenhuma I/O aqui. Números chegam como `int`, `Decimal` ou `str`
(JSON lido com `parse_float=Decimal`); `float` é recusado como `invalid`.

Regras que as tabelas de origem não têm e o adaptador impõe:

1. **Relógios.** As tabelas só têm `collected_at` (relógio do n8n) e `created_at` (relógio do banco):
   `observed_at = collected_at`; `available_at = ingested_at = max(collected_at, created_at)` — o
   VOLC só "sabe" quando a linha existe no banco, e um relógio adiantado do n8n não antecipa nada.
2. **Janela.** `metric_date` (+ `metric_hour`) no `timezone` da execução (padrão `America/Sao_Paulo`);
   janela ainda aberta em `collected_at` → `partial` com cobertura DESCONHECIDA (nula, motivo
   `janela_aberta;cobertura_desconhecida`): a tabela não diz quanto da janela já foi contado (R1-F17).
3. **Zero sem linha de métrica.** O coletor v21 de campanha-dia sintetiza 0 (`basic()` no Code node)
   quando a API não devolveu linha de métrica para a campanha. Por isso, no v21, 0 só vira
   `zero_confirmed` com PROVA: o payload bruto do lote (`raw_source.metrics`) tem uma linha de
   métrica não vazia para a campanha. Sem a prova, 0 vira `missing` (`zero_sem_linha_de_metrica`
   ou `zero_sem_prova_de_linha`, se o payload não veio na junção). Valor ≠ 0 não é sintetizável.
4. **Chave substituída (JoinAds).** Se `request_meta.custom_key` (pedido) difere do `custom_key`
   devolvido, todas as métricas da linha viram `invalid` (`chave_substituida:<pedida>-><devolvida>`).
5. **Moeda só com prova (R1-F4).** A coluna `currency_code` não prova nada (v21 campanha-dia grava 'BRL'
   fixo; JoinAds v2 grava `cfg.CURRENCY || 'USD'` e a coluna tem DEFAULT 'USD'). Valor monetário só sai
   com moeda se o payload bruto do lote (`batch_payload`) declarar a mesma moeda ou o chamador passar
   `moeda_atestada`; senão `invalid` `moeda_nao_provada` (ou `moeda_divergente`).
6. **Chave JoinAds sem prova (R1-F15).** `custom_key` ausente num endpoint que pede chave → `invalid`
   `custom_key_ausente:<pedida>`; endpoints em que o normalizador a montante força `custom_key`
   (`key_value_country_adunit`, `pageviews_campaign_batch`) → `invalid` `custom_key_forcado_upstream`.
   Limite: linhas com chave substituída são DESCARTADAS a montante (`joinads_v2_normalize.js:169-173`,
   só um warning no recibo da execução); ausência de linha em `joinads_observation` não prova nada.
7. **Hash ausente.** Lote JoinAds com `payload_sha256` = 64 zeros (default da coluna sem o trigger)
   não prova conteúdo: as métricas viram `invalid` (`payload_sem_hash`).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from ...contracts.money import MICROS
from ...contracts.vocab import Metrica, ValueKind
from .modelo import COBERTURA_DESCONHECIDA, Coletor, EntidadeRef, Observacao, ObservacaoInvalida
from .vocab import StatusObservacao, Unidade

TZ_PADRAO = "America/Sao_Paulo"
HASH_ZERO = "0" * 64


class AdaptacaoImpossivel(ObservacaoInvalida):
    """A linha não tem identidade suficiente para virar observação (vai para dead_letter)."""


# --------------------------------------------------------------------------- utilidades
def _instante(v: Any, nome: str) -> datetime:
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError as exc:
            raise AdaptacaoImpossivel(f"{nome} inválido: {v!r}") from exc
    if not isinstance(v, datetime) or v.tzinfo is None:
        raise AdaptacaoImpossivel(f"{nome} precisa ser instante com timezone")
    return v


def _data(v: Any) -> date:
    if isinstance(v, datetime):
        raise AdaptacaoImpossivel("metric_date precisa ser data, não instante")
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError as exc:
        raise AdaptacaoImpossivel(f"metric_date inválida: {v!r}") from exc


def _janela(linha: Mapping[str, Any], tz: str) -> tuple[datetime, datetime]:
    if linha.get("metric_date") is None:
        raise AdaptacaoImpossivel("metric_date ausente: sem janela não há fato")
    d = _data(linha["metric_date"])
    zona = ZoneInfo(tz)
    hora = linha.get("metric_hour")
    if hora is None:
        ini = datetime(d.year, d.month, d.day, tzinfo=zona)
        prox = d + timedelta(days=1)
        return ini, datetime(prox.year, prox.month, prox.day, tzinfo=zona)
    ini = datetime(d.year, d.month, d.day, int(hora), tzinfo=zona)
    return ini, ini + timedelta(hours=1)


def _relogios(linha: Mapping[str, Any]) -> tuple[datetime, datetime]:
    coletado = _instante(linha.get("collected_at"), "collected_at")
    criado = _instante(linha.get("created_at"), "created_at") if linha.get("created_at") is not None else coletado
    return coletado, max(coletado, criado)


_CHAVES_MOEDA = frozenset({"currency_code", "currencyCode", "currency", "moeda"})


def _moedas_no_payload(payload: Any, profundidade: int = 0) -> set[str]:
    """Moedas que o payload BRUTO afirma (qualquer nível, até 8). Valor fixado pelo coletor não conta."""
    achadas: set[str] = set()
    if profundidade > 8:
        return achadas
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if k in _CHAVES_MOEDA and isinstance(v, str) and len(v.strip()) == 3 and v.strip().isalpha():
                achadas.add(v.strip().upper())
            else:
                achadas |= _moedas_no_payload(v, profundidade + 1)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            achadas |= _moedas_no_payload(v, profundidade + 1)
    return achadas


def _prova_de_moeda(moeda: Optional[str], payload: Any, atestada: Optional[str]) -> Optional[str]:
    """None se a moeda está provada; senão o motivo de invalidez (R1-F4).

    Prova: o payload bruto do lote declara exatamente essa moeda, ou o chamador passa `moeda_atestada`
    (moeda da conta lida com prova própria, ex.: `customer.currency_code` de outro lote) igual à coluna.
    A coluna sozinha não prova: o coletor v21 campanha-dia grava 'BRL' fixo e a JoinAds v2 grava
    `cfg.CURRENCY || 'USD'` (e a coluna tem DEFAULT 'USD').
    """
    if moeda is None:
        return "moeda_nao_declarada"
    no_payload = _moedas_no_payload(payload) if payload is not None else set()
    if no_payload and no_payload != {moeda}:
        return "moeda_divergente"
    if no_payload == {moeda} or (atestada is not None and atestada == moeda):
        return None
    if atestada is not None:
        return "moeda_divergente"
    return "moeda_nao_provada"


def _decimal(bruto: Any) -> tuple[Optional[Decimal], Optional[str]]:
    if isinstance(bruto, bool):
        return None, "valor_invalido"
    if isinstance(bruto, float):
        return None, "float_recusado"
    if isinstance(bruto, Decimal):
        dec = bruto
    elif isinstance(bruto, (int, str)):
        try:
            dec = Decimal(str(bruto).strip())
        except InvalidOperation:
            return None, "valor_invalido"
    else:
        return None, "valor_invalido"
    if not dec.is_finite():
        return None, "valor_invalido"
    return dec, None


def _inteiro(bruto: Any, nome: str, *, escala: int = 1) -> tuple[Optional[int], Optional[str]]:
    """Converte para inteiro (contagem ou micros). `escala=MICROS` para dinheiro em unidade da moeda."""
    dec, erro = _decimal(bruto)
    if erro:
        return None, f"{erro}:{nome}"
    assert dec is not None
    v = dec * escala
    if v != v.to_integral_value():
        return None, (f"precisao_acima_de_micros:{nome}" if escala == MICROS else f"valor_fracionario:{nome}")
    return int(v), None


def _texto(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class _Montador:
    """Fixa o que é comum às métricas de uma linha e emite uma Observacao por métrica."""

    def __init__(self, **comum: Any) -> None:
        self.comum = comum
        self.ini: datetime = comum["janela_inicio"]
        self.fim: datetime = comum["janela_fim"]
        self.obs_at: datetime = comum["observed_at"]

    def emitir(self, metrica: Metrica, unidade: Unidade, valor: Optional[int], *, moeda: Optional[str],
               value_kind: Optional[ValueKind] = None, status: Optional[StatusObservacao] = None,
               motivo: Optional[str] = None, dimensoes_extra: tuple = (),
               motivo_moeda: Optional[str] = None) -> Observacao:
        cobertura = None
        if status is None:  # derivar do valor e do relógio
            if self.obs_at < self.fim:
                # a tabela de origem não diz quanto da janela já foi contado: não se fabrica cobertura (R1-F17)
                status, motivo = StatusObservacao.PARTIAL, motivo or f"janela_aberta;{COBERTURA_DESCONHECIDA}"
            elif valor == 0:
                status = StatusObservacao.ZERO_CONFIRMED
            else:
                status = StatusObservacao.OBSERVED
        if status not in (StatusObservacao.OBSERVED, StatusObservacao.ZERO_CONFIRMED, StatusObservacao.PARTIAL):
            valor = None
        if unidade is Unidade.MICROS and motivo_moeda is not None:
            moeda = None  # moeda sem prova não é gravada nem em linha sem valor
            if valor is not None:
                status, valor, motivo, cobertura = StatusObservacao.INVALID, None, motivo_moeda, None
        dims = tuple(sorted(self.comum["dimensoes"] + tuple(dimensoes_extra)))
        kw = {k: v for k, v in self.comum.items() if k != "dimensoes"}
        return Observacao(metrica=metrica, unidade=unidade, valor=valor, moeda=moeda if unidade is Unidade.MICROS else None,
                          value_kind=value_kind, status=status, motivo=motivo, cobertura_ppm=cobertura,
                          dimensoes=dims, **kw)


# --------------------------------------------------------------------------- Google Ads v21
GRAO_V21: dict[str, tuple[str, tuple[str, ...]]] = {
    # grain v21 → (tipo de entidade, grão canônico). search_term não existe no vocabulário herdado de grão:
    # o termo é a entidade e o grão é ad_group×day (lacuna registrada no 02-CONTRATO §9).
    "campaign_day": ("campaign", ("campaign", "day")),
    "campaign_hour": ("campaign", ("campaign", "hour")),
    "ad_group_day": ("ad_group", ("ad_group", "day")),
    "keyword_day": ("keyword", ("keyword", "day")),
    "search_term_day": ("search_term", ("ad_group", "day")),
}

# métrica v21 (chave em `metrics`) → (métrica canônica, unidade, já em micros?)
METRICAS_V21: dict[str, tuple[Metrica, Unidade, bool]] = {
    "cost_micros": (Metrica.CUSTO, Unidade.MICROS, True),
    "impressions": (Metrica.IMPRESSOES, Unidade.CONTAGEM, False),
    "clicks": (Metrica.CLIQUES, Unidade.CONTAGEM, False),
    "conversions": (Metrica.CONVERSOES, Unidade.CONTAGEM, False),
}
# Não mapeadas de propósito (sem lugar no vocabulário herdado ou não aditivas): conversions_value,
# all_conversions*, interactions, ctr, average_cpc_micros, cost_per_conversion_micros, *_share,
# *_percentage. Ficam no payload bruto; razão não é observação somável.

# chave do metrics v21 → campo camelCase da linha bruta da API (prova de que a linha de métrica existe)
_CAMPO_API_V21 = {"cost_micros": "costMicros", "impressions": "impressions", "clicks": "clicks", "conversions": "conversions"}


def _prova_linha_metrica_v21(linha: Mapping[str, Any]) -> Optional[bool]:
    """True: o payload bruto tem linha de métrica; False: tem payload e a linha está vazia; None: sem payload."""
    payload = linha.get("batch_payload")
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        return False
    # raw_source = {campaign, metrics: <linha GAQL de métrica ou {}>, budget, goal}. Linha presente com
    # campos omitidos é zero da API (proto3 omite default); linha ausente ({}) é o zero sintetizado.
    m = payload.get("metrics")
    return isinstance(m, Mapping) and bool(m)


def adaptar_google_ads_v21(linha: Mapping[str, Any], *, moeda_atestada: Optional[str] = None) -> tuple[Observacao, ...]:
    """Linha de `google_ads_observation` ⋈ `google_ads_raw_batch` ⋈ `google_ads_collection_run` → observações.

    Campos esperados (nomes das colunas; os do lote/execução com prefixo explícito na junção):
    observation_id, run_id, batch_id, observation_key, customer_id, campaign_id, ad_group_id, criterion_id,
    resource_type, resource_id, grain, metric_date, metric_hour, currency_code, dimensions, metrics,
    collected_at, created_at, batch_payload_sha256, batch_request_id, batch_payload (opcional, prova de linha),
    run_collector, run_collector_version, run_api_version, run_timezone.
    """
    grain = _texto(linha.get("grain"))
    if grain not in GRAO_V21:
        raise AdaptacaoImpossivel(f"grain v21 sem mapeamento canônico: {grain!r}")
    tipo, grao = GRAO_V21[grain]
    conta = _texto(linha.get("customer_id"))
    if conta is None:
        raise AdaptacaoImpossivel("customer_id ausente")
    ids = {"campaign": linha.get("campaign_id"), "ad_group": linha.get("ad_group_id"), "keyword": linha.get("criterion_id"),
           "search_term": (linha.get("dimensions") or {}).get("search_term") or linha.get("resource_id")}
    ent_id = _texto(ids[tipo])
    if ent_id is None:
        raise AdaptacaoImpossivel(f"id da entidade {tipo} ausente na linha {linha.get('observation_key')!r}")
    dims: list[tuple[str, str]] = []
    if tipo in ("ad_group", "keyword", "search_term") and _texto(linha.get("campaign_id")):
        dims.append(("campaign_id", _texto(linha.get("campaign_id"))))  # type: ignore[arg-type]
    if tipo in ("keyword", "search_term") and _texto(linha.get("ad_group_id")):
        dims.append(("ad_group_id", _texto(linha.get("ad_group_id"))))  # type: ignore[arg-type]
    sha = _texto(linha.get("batch_payload_sha256"))
    if sha is None:
        raise AdaptacaoImpossivel("batch_payload_sha256 ausente: sem prova de conteúdo do lote")
    tz = _texto(linha.get("run_timezone")) or TZ_PADRAO
    ini, fim = _janela(linha, tz)
    coletado, disponivel = _relogios(linha)
    api = _texto(linha.get("run_api_version")) or "desconhecida"
    m = _Montador(
        fonte="google_ads", conta=conta, entidade=EntidadeRef(tipo, ent_id), grao=grao, dimensoes=tuple(dims),
        janela_inicio=ini, janela_fim=fim, timezone=tz, observed_at=coletado, available_at=disponivel,
        ingested_at=disponivel, run_id=str(linha["run_id"]), lote_id=str(linha["batch_id"]),
        request_id=_texto(linha.get("batch_request_id")), payload_sha256=sha,
        payload_ref=f"google_ads_raw_batch:{linha['batch_id']}:sha256:{sha}",
        schema_version=f"google_ads.v21.{linha.get('resource_type')}.{grain}.api_{api}",
        coletor=Coletor(_texto(linha.get("run_collector")) or "google_ads_v21", str(linha.get("run_collector_version") or "0")),
    )
    metricas = linha.get("metrics") or {}
    if not isinstance(metricas, Mapping):
        raise AdaptacaoImpossivel("metrics precisa ser objeto")
    moeda = _texto(linha.get("currency_code"))
    motivo_moeda = _prova_de_moeda(moeda, linha.get("batch_payload"), moeda_atestada)
    prova = _prova_linha_metrica_v21(linha) if grain == "campaign_day" else True
    saida = []
    for chave, (metrica, unidade, em_micros) in METRICAS_V21.items():
        if chave not in metricas:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, status=StatusObservacao.MISSING,
                                  motivo=f"metrica_ausente_no_registro:{chave}"))
            continue
        bruto = metricas[chave]
        if bruto is None:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, status=StatusObservacao.MISSING,
                                  motivo=f"valor_nulo_na_fonte:{chave}"))
            continue
        valor, erro = _inteiro(bruto, chave, escala=1 if (em_micros or unidade is Unidade.CONTAGEM) else MICROS)
        if erro is None and unidade is Unidade.CONTAGEM and valor is not None and valor < 0:
            erro = f"contagem_negativa:{chave}"
        if erro:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, status=StatusObservacao.INVALID, motivo=erro))
            continue
        if valor == 0 and prova is not True:
            motivo = "zero_sem_linha_de_metrica" if prova is False else "zero_sem_prova_de_linha"
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, status=StatusObservacao.MISSING, motivo=motivo))
            continue
        saida.append(m.emitir(metrica, unidade, valor, moeda=moeda, motivo_moeda=motivo_moeda))
    return tuple(saida)


# --------------------------------------------------------------------------- JoinAds v2
# coluna JoinAds → (métrica canônica, unidade, value_kind, dimensão que separa fatos de mesma métrica)
METRICAS_JOINADS_V2: dict[str, tuple[Metrica, Unidade, Optional[ValueKind], tuple]] = {
    "revenue_client": (Metrica.RECEITA, Unidade.MICROS, ValueKind.REPORTED_REVENUE, (("revenue_basis", "client"),)),
    "revenue_gross": (Metrica.RECEITA, Unidade.MICROS, ValueKind.REPORTED_REVENUE, (("revenue_basis", "gross"),)),
    "impressions": (Metrica.IMPRESSOES, Unidade.CONTAGEM, None, ()),
    "clicks": (Metrica.CLIQUES, Unidade.CONTAGEM, None, ()),
}
# Não mapeadas: requests_served, unfilled, pageviews, unique_views, first_views (sem métrica no vocabulário
# herdado — pageview NÃO é sessão), active_view, pmr, ctr, ecpm_* (razões). Ficam no payload bruto.

_STATUS_JOINADS = {"unavailable": StatusObservacao.UNAVAILABLE, "unsupported": StatusObservacao.UNSUPPORTED}


# chave de key-value que cada endpoint PEDE (joinads_v2_normalize.js:186-204). Nos endpoints de
# FORCADOS o normalizador a montante sobrescreve custom_key='utm_campaign' antes de conferir: a chave
# gravada não é evidência do que a API devolveu (R1-F15).
CHAVE_PEDIDA_JOINADS = {
    "key_value_campaign_adunit": "utm_campaign",
    "key_value_post": "id_post_wp",
    "key_value_land": "land_uri",
    "key_value_country_adunit": "utm_campaign",
    "pageviews_campaign_batch": "utm_campaign",
}
CHAVE_FORCADA_JOINADS = frozenset({"key_value_country_adunit", "pageviews_campaign_batch"})


def adaptar_joinads_v2(linha: Mapping[str, Any], *, moeda_atestada: Optional[str] = None) -> tuple[Observacao, ...]:
    """Linha de `joinads_observation` ⋈ `joinads_raw_batch` ⋈ `joinads_collection_run` → observações.

    Campos esperados: observation_key, run_key, batch_key, endpoint, grain, metric_date, metric_hour, domain,
    campaign_id, custom_key, custom_value, post_id, land_uri, ad_unit_name, country_iso, currency_code,
    revenue_client, revenue_gross, impressions, clicks, data_status, collected_at, created_at,
    batch_payload_sha256, batch_request_meta (opcional: custom_key pedido), run_collector,
    run_collector_version, run_timezone.
    """
    dominio = _texto(linha.get("domain"))
    if dominio is None:
        raise AdaptacaoImpossivel("domain ausente: a conta JoinAds é o domínio")
    endpoint, grain = _texto(linha.get("endpoint")), _texto(linha.get("grain"))
    if endpoint is None or grain is None:
        raise AdaptacaoImpossivel("endpoint/grain ausentes")
    camp, post, land = _texto(linha.get("campaign_id")), _texto(linha.get("post_id")), _texto(linha.get("land_uri"))
    if camp:
        entidade, grao_base = EntidadeRef("campaign", camp), {"campaign"}
    elif post:
        entidade, grao_base = EntidadeRef("post", post), {"url"}
    elif land:
        entidade, grao_base = EntidadeRef("land_uri", land), {"url"}
    elif _texto(linha.get("custom_key")) and _texto(linha.get("custom_value")):
        entidade, grao_base = EntidadeRef(f"kv:{_texto(linha.get('custom_key'))}", _texto(linha.get("custom_value"))), {"cell"}  # type: ignore[arg-type]
    else:
        entidade, grao_base = EntidadeRef("domain", dominio), {"account"}
    grao = grao_base | {"hour" if linha.get("metric_hour") is not None else "day"}
    dims: list[tuple[str, str]] = [("joinads_endpoint", endpoint), ("joinads_grain", grain)]
    fonte_da_entidade = {"post": ("post_id",), "land_uri": ("land_uri",)}.get(
        entidade.tipo, ("custom_key", "custom_value") if entidade.tipo.startswith("kv:") else ())
    for col in ("custom_key", "custom_value", "post_id", "land_uri", "ad_unit_name", "country_iso"):
        v = _texto(linha.get(col))
        if v is not None and col not in fonte_da_entidade:
            dims.append((col, v))
    if _texto(linha.get("ad_unit_name")):
        grao.add("ad_unit")
    if _texto(linha.get("country_iso")):
        grao.add("country")
    sha = _texto(linha.get("batch_payload_sha256"))
    if sha is None:
        raise AdaptacaoImpossivel("batch_payload_sha256 ausente")
    tz = _texto(linha.get("run_timezone")) or TZ_PADRAO
    ini, fim = _janela(linha, tz)
    coletado, disponivel = _relogios(linha)
    m = _Montador(
        fonte="joinads", conta=dominio, entidade=entidade, grao=tuple(sorted(grao)), dimensoes=tuple(dims),
        janela_inicio=ini, janela_fim=fim, timezone=tz, observed_at=coletado, available_at=disponivel,
        ingested_at=disponivel, run_id=str(linha["run_key"]), lote_id=str(linha["batch_key"]), request_id=None,
        payload_sha256=sha, payload_ref=f"joinads_raw_batch:{linha['batch_key']}:sha256:{sha}",
        schema_version=f"joinads.v2.{endpoint}.{grain}",
        coletor=Coletor(_texto(linha.get("run_collector")) or "n8n_joinads_v2", str(linha.get("run_collector_version") or "0")),
    )
    moeda = _texto(linha.get("currency_code"))
    # motivos que invalidam a linha inteira
    meta = linha.get("batch_request_meta")
    pedido = _texto(meta.get("custom_key")) if isinstance(meta, Mapping) else None
    pedido = pedido or CHAVE_PEDIDA_JOINADS.get(endpoint)
    devolvida = _texto(linha.get("custom_key"))
    motivo_linha = None
    if sha == HASH_ZERO:
        motivo_linha = "payload_sem_hash"
    elif endpoint in CHAVE_FORCADA_JOINADS:
        motivo_linha = "custom_key_forcado_upstream"  # chave reescrita pelo normalizador: identidade sem prova
    elif pedido and devolvida is None:
        motivo_linha = f"custom_key_ausente:{pedido}"  # o normalizador deixa passar linha sem chave
    elif pedido and devolvida != pedido:
        motivo_linha = f"chave_substituida:{pedido}->{devolvida}"
    motivo_moeda = _prova_de_moeda(moeda, linha.get("batch_payload"), moeda_atestada)
    data_status = _texto(linha.get("data_status")) or "observed"
    saida = []
    for col, (metrica, unidade, vk, extra) in METRICAS_JOINADS_V2.items():
        if motivo_linha:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, value_kind=vk, status=StatusObservacao.INVALID,
                                  motivo=motivo_linha, dimensoes_extra=extra))
            continue
        if data_status in _STATUS_JOINADS:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, value_kind=vk, status=_STATUS_JOINADS[data_status],
                                  motivo=f"joinads_data_status:{data_status}", dimensoes_extra=extra))
            continue
        bruto = linha.get(col)
        if bruto is None:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, value_kind=vk, status=StatusObservacao.MISSING,
                                  motivo=f"valor_nulo_na_fonte:{col}", dimensoes_extra=extra))
            continue
        valor, erro = _inteiro(bruto, col, escala=MICROS if unidade is Unidade.MICROS else 1)
        if erro is None and valor is not None and valor < 0:
            erro = f"valor_negativo:{col}"
        if erro is None and data_status == "zero_confirmed" and valor != 0:
            erro = f"zero_confirmed_com_valor:{col}"
        if erro:
            saida.append(m.emitir(metrica, unidade, None, moeda=moeda, motivo_moeda=motivo_moeda, value_kind=vk, status=StatusObservacao.INVALID,
                                  motivo=erro, dimensoes_extra=extra))
            continue
        # JoinAds devolve linha explícita: 0 numa linha que existe é zero afirmado pela fonte
        saida.append(m.emitir(metrica, unidade, valor, moeda=moeda, value_kind=vk, dimensoes_extra=extra,
                              motivo_moeda=motivo_moeda))
    return tuple(saida)
