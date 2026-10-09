"""Família `campanha_dia`: fato canônico campanha-dia pela RPC da v12_04.

Mesma semântica do normalizador do workflow n8n v12
(`n8n/gerar_flows_gads_ledger_v12.py`, JS_NORMALIZAR + JS_VALIDAR): segmentos
`{}`, moeda da conta, ausência vira None, taxa 0..1 como a API manda, e a
recusa local vira motivo do lote em vez de sumir. A diferença é
`metricas_extras`, que agora leva `invalid_clicks` e `invalid_click_rate`
(a `vw_gads_campanha_dia` lê exatamente essas chaves).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .. import executor
from ..contrato import Contexto, enum_nome, medida

# coluna do fato → (campo em `metrics`, tipo)
METRICAS: dict[str, tuple[str, type]] = {
    "impressoes": ("impressions", int),
    "cliques": ("clicks", int),
    "interacoes": ("interactions", int),
    "custo_micros": ("cost_micros", int),
    "conversoes": ("conversions", float),
    "todas_conversoes": ("all_conversions", float),
    "valor_conversoes": ("conversions_value", float),
    "valor_todas_conversoes": ("all_conversions_value", float),
    "ctr": ("ctr", float),
    "cpc_medio_micros": ("average_cpc", float),
    "custo_por_conversao_micros": ("cost_per_conversion", float),
    "search_impression_share": ("search_impression_share", float),
    "search_budget_lost_impression_share": ("search_budget_lost_impression_share", float),
    "search_rank_lost_impression_share": ("search_rank_lost_impression_share", float),
    "search_top_impression_share": ("search_top_impression_share", float),
    "search_absolute_top_impression_share": ("search_absolute_top_impression_share", float),
    "search_click_share": ("search_click_share", float),
    "search_exact_match_impression_share": ("search_exact_match_impression_share", float),
    "top_impression_percentage": ("top_impression_percentage", float),
    "absolute_top_impression_percentage": ("absolute_top_impression_percentage", float),
}

EXTRAS: dict[str, tuple[str, type]] = {
    "invalid_clicks": ("invalid_clicks", int),
    "invalid_click_rate": ("invalid_click_rate", float),
}

TAXAS = (
    "ctr", "search_impression_share", "search_budget_lost_impression_share",
    "search_rank_lost_impression_share", "search_top_impression_share",
    "search_absolute_top_impression_share", "search_click_share",
    "search_exact_match_impression_share", "top_impression_percentage",
    "absolute_top_impression_percentage",
)
NAO_NEGATIVAS = tuple(c for c in METRICAS if c not in TAXAS)

CAMPOS = (
    "customer.id",
    "campaign.id",
    "campaign.name",
    "campaign.status",
    "campaign.advertising_channel_type",
    "segments.date",
    *(f"metrics.{campo}" for campo, _ in METRICAS.values()),
    *(f"metrics.{campo}" for campo, _ in EXTRAS.values()),
)

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validar(linha: dict, ctx: Contexto) -> str | None:
    """A mesma rede do JS_VALIDAR. Uma taxa fora de 0..1 não é rejeição de
    linha no banco: estoura a CHECK da tabela e derruba o lote inteiro."""
    if not re.fullmatch(r"[0-9]{6,12}", linha["customer_id"] or ""):
        return "CUSTOMER_ID_INVALIDO"
    if not re.fullmatch(r"[0-9]{1,20}", linha["campaign_id"] or ""):
        return "CAMPAIGN_ID_INVALIDO"
    if not _DATA.match(linha["metric_date"] or ""):
        return "DATA_AUSENTE"
    if not (ctx.data_inicio.isoformat() <= linha["metric_date"] <= ctx.data_fim.isoformat()):
        return "DATA_FORA_DA_JANELA"
    if not re.fullmatch(r"[A-Z]{3}", linha["currency_code"] or ""):
        return "MOEDA_AUSENTE_OU_INVALIDA"
    for campo in TAXAS:
        v = linha[campo]
        if v is not None and not 0 <= v <= 1:
            return f"TAXA_FORA_DE_0_1:{campo}"
    for campo in NAO_NEGATIVAS:
        v = linha[campo]
        if v is not None and v < 0:
            return f"VALOR_NEGATIVO_OU_NAO_NUMERICO:{campo}"
    return None


class _CampanhaDia:
    nome = "campanha_dia"
    rpc = "volc_registrar_gads_campanha_dia"
    # O workflow n8n v12 pede a projeção legada explicitamente; o default da
    # RPC é fechado.
    projetar_compat = True

    def gaql(self, ctx: Contexto) -> str:
        return (f"SELECT {', '.join(CAMPOS)} FROM campaign "
                f"WHERE {ctx.janela_gaql} ORDER BY campaign.id")

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        devolvida = str(row.customer.id) if row.customer.id else None
        if devolvida is not None and devolvida != str(ctx.customer_id):
            raise ValueError(f"IDENTIDADE_DIVERGENTE: pedi {ctx.customer_id} e a resposta "
                             f"trouxe {devolvida}")
        m = row.metrics
        linha = {
            "customer_id": str(ctx.customer_id),
            "campaign_id": str(row.campaign.id) if row.campaign.id else None,
            "metric_date": row.segments.date or None,
            "volc_campaign_id": None,
            "campaign_name": row.campaign.name or None,
            "campaign_status": enum_nome(row.campaign.status),
            "advertising_channel_type": enum_nome(row.campaign.advertising_channel_type),
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            "segmentos": {},
        }
        # O ON CONFLICT da RPC sobrescreve o vínculo: sem o mapa, um run
        # posterior ao n8n apagaria o volc_campaign_id que ele gravou.
        if linha["campaign_id"] is not None:
            linha["volc_campaign_id"] = ctx.mapa_volc.get(linha["campaign_id"])
        for coluna, (campo, tipo) in METRICAS.items():
            linha[coluna] = medida(m, campo, tipo)
        linha["metricas_extras"] = {
            chave: valor for chave, (campo, tipo) in EXTRAS.items()
            if (valor := medida(m, campo, tipo)) is not None
        }
        return linha

    def documento(self, ctx: Contexto, linhas: list[dict], *, lote: int,
                  execucao_chave: str, iniciada: datetime) -> dict:
        boas: list[dict] = []
        recusas: list[dict] = []
        chaves: set[tuple] = set()
        for i, linha in enumerate(linhas, start=1):
            motivo = _validar(linha, ctx)
            chave = (linha["customer_id"], linha["campaign_id"], linha["metric_date"])
            if motivo is None and chave in chaves:
                motivo = "LINHA_DUPLICADA_NA_PAGINA"
            if motivo is None:
                chaves.add(chave)
                boas.append(linha)
            else:
                recusas.append({"ordinal": i, "campaign_id": linha["campaign_id"], "motivo": motivo})

        doc = self._cabecalho(ctx, execucao_chave, iniciada)
        doc.update({
            "chave_idempotencia": f"{execucao_chave}:lote{lote}",
            "tipo_lote": "contas",
            "lote_ordinal": lote,
            "resultado": "parcial" if recusas else "ok",
            "motivo": (f"{len(recusas)} de {len(linhas)} linhas recusadas na validacao local: "
                       + "; ".join(f"{r['campaign_id']}:{r['motivo']}" for r in recusas[:10])
                       if recusas else None),
            "escopo": f"conta {ctx.customer_id} lote {lote}",
            "contas_aceitas": [str(ctx.customer_id)],
            "projetar_compat": self.projetar_compat,
            "linhas": boas,
        })
        return doc

    def fechamento(self, ctx: Contexto, *, execucao_chave: str, lotes: list[dict],
                   iniciada: datetime) -> dict:
        """Ordinal 0: declara a soma dos recibos dos lotes para a RPC reconciliar
        contra o que ela mesma persistiu."""
        def soma(chave: str) -> int:
            return sum(int(r.get(chave) or 0) for r in lotes)

        aceitas, preteridas, rejeitadas = (soma("linhas_aceitas"), soma("linhas_preteridas"),
                                           soma("linhas_rejeitadas"))
        estados = {r.get("projecao_estado") or "nao_solicitada" for r in lotes} or {"nao_solicitada"}
        # A CHECK exige código de erro para 'falhou', e o fechamento não carrega
        # código: estado misto ou com falha vira 'parcial' (o detalhe fica no lote).
        projecao = estados.pop() if len(estados) == 1 and "falhou" not in estados else "parcial"
        resultados = {r.get("resultado") for r in lotes}
        if resultados <= {"ok"}:
            resultado, motivo = "ok", None
        elif aceitas + preteridas > 0:
            resultado = "parcial"
            motivo = f"lotes nao-ok: {sorted(str(x) for x in resultados - {'ok'})}"
        else:
            resultado, motivo = "falhou", "nenhum lote aproveitavel"

        doc = self._cabecalho(ctx, execucao_chave, iniciada)
        doc.update({
            "chave_idempotencia": f"{execucao_chave}:fechamento",
            "tipo_lote": "fechamento",
            "lote_ordinal": 0,
            "resultado": resultado,
            "motivo": motivo,
            "escopo": f"conta {ctx.customer_id} fechamento de {len(lotes)} lote(s)",
            "contas_aceitas": [str(ctx.customer_id)] if aceitas + preteridas > 0 else [],
            "linhas_aceitas": aceitas,
            "linhas_preteridas": preteridas,
            "linhas_rejeitadas": rejeitadas,
            "projecao_estado": projecao,
            "projecao_linhas": soma("projecao_linhas"),
            "linhas": [],
        })
        return doc

    def _cabecalho(self, ctx: Contexto, execucao_chave: str, iniciada: datetime) -> dict:
        agora = datetime.now(timezone.utc)
        return {
            "execucao_chave": execucao_chave,
            "fonte": "python_oneshot",
            "job": f"gads_{self.nome}",
            "disparo": ctx.disparo,
            "workflow_id": None,
            "execucao_externa_id": None,
            "api_versao": ctx.api_versao,
            "contrato_versao": executor.CONTRATO_VERSAO,
            "contrato_sha256": executor.contrato_sha256(),
            "origem_janela": ctx.origem_janela,
            "janela_inicio": ctx.data_inicio.isoformat(),
            "janela_fim": ctx.data_fim.isoformat(),
            "iniciada_em": iniciada.isoformat(),
            "encerrada_em": agora.isoformat(),
            "duracao_ms": max(0, int((agora - iniciada).total_seconds() * 1000)),
            "batimento_em": agora.isoformat(),
            "contas_tentadas": [str(ctx.customer_id)],
            "contas_recusadas": [],
        }


FAMILIA = _CampanhaDia()
