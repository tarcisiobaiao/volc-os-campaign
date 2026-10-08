"""A conta do Google Ads vista pelo motor `volc_ads.gestao`. Implementa `portas.ContaGoogle`.

Nenhuma regra mora aqui. As leituras do "antes" são as do motor
(`estado.ler`), o ensaio e a escrita são as do lote (`lote.validar`,
`lote.aplicar`, `lote.aplicar_recomendacoes`) — e a escrita real passa pela
trava de dois fatores DENTRO do lote (`modo.destravar(motivo)` +
FORGE_PERMITIR_ESCRITA=1). Este adaptador não abre trava nenhuma.

As três GAQLs próprias (métricas da evidência, campanha a importar,
recomendações) têm o SELECT literal, para `catalogo.varrer_gaqls` conferi-las
contra o servidor v25 sem rede; a interpolação mora só no WHERE.

⚠️ `login_customer_id` é o MCC da casa (`escopo.MCC_DA_CASA`) por padrão — o
mesmo portão de `escopo.exigir_escopo`: a chamada viaja sob o manager da casa,
e é isso que faz o próprio Google recusar conta de terceiro.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.trafego import escopo

from ..application.erros import Indisponivel

_RAIZ = pathlib.Path(__file__).resolve().parents[5]


def garantir_volc_ads() -> None:
    """Põe a raiz do repositório no `sys.path` e confirma que o motor importa.

    O backend roda com `cwd=backend`, e o `volc_ads` mora um nível acima — o
    mesmo ajuste de `routers/trafego._ponte`, com a mesma distinção de causa:
    SDK ausente e pacote fora do caminho pedem consertos diferentes.
    """
    if str(_RAIZ) not in sys.path:
        sys.path.insert(0, str(_RAIZ))
    try:
        import volc_ads.gestao.lote  # noqa: F401,PLC0415
    except ImportError as exc:
        faltando = (getattr(exc, "name", "") or "").split(".")[0]
        if faltando in ("google", "grpc", "proto"):
            raise Indisponivel(f"o SDK do Google Ads não está instalado ({exc})",
                               codigo="sdk_ausente") from exc
        raise Indisponivel(f"o motor `volc_ads` não foi encontrado a partir de {_RAIZ} ({exc})",
                           codigo="motor_ausente") from exc


_GAQL_METRICAS = {
    "conta": ("SELECT customer.id, customer.currency_code, metrics.impressions, "
              "metrics.clicks, metrics.cost_micros, metrics.conversions, "
              "metrics.conversions_value FROM customer "
              "WHERE segments.date BETWEEN '{inicio}' AND '{fim}'"),
    "campanha": ("SELECT campaign.id, customer.currency_code, metrics.impressions, "
                 "metrics.clicks, metrics.cost_micros, metrics.conversions, "
                 "metrics.conversions_value FROM campaign "
                 "WHERE campaign.id = {alvo} AND segments.date BETWEEN '{inicio}' AND '{fim}'"),
    "grupo": ("SELECT ad_group.id, customer.currency_code, metrics.impressions, "
              "metrics.clicks, metrics.cost_micros, metrics.conversions, "
              "metrics.conversions_value FROM ad_group "
              "WHERE ad_group.id = {alvo} AND segments.date BETWEEN '{inicio}' AND '{fim}'"),
    "anuncio": ("SELECT ad_group_ad.ad.id, customer.currency_code, metrics.impressions, "
                "metrics.clicks, metrics.cost_micros, metrics.conversions, "
                "metrics.conversions_value FROM ad_group_ad "
                "WHERE ad_group.id = {grupo} AND ad_group_ad.ad.id = {anuncio} "
                "AND segments.date BETWEEN '{inicio}' AND '{fim}'"),
    "asset_group": ("SELECT asset_group.id, customer.currency_code, metrics.impressions, "
                    "metrics.clicks, metrics.cost_micros, metrics.conversions, "
                    "metrics.conversions_value FROM asset_group "
                    "WHERE asset_group.id = {alvo} "
                    "AND segments.date BETWEEN '{inicio}' AND '{fim}'"),
}

GAQL_CAMPANHA = ("SELECT campaign.id, campaign.name, campaign.status, "
                 "campaign.advertising_channel_type, customer.currency_code FROM campaign "
                 "WHERE campaign.id = {campanha}")

GAQL_RECOMENDACOES = ("SELECT recommendation.resource_name, recommendation.type, "
                      "recommendation.campaign, recommendation.campaign_budget, "
                      "recommendation.ad_group, recommendation.dismissed, "
                      "recommendation.impact FROM recommendation "
                      "WHERE recommendation.dismissed = FALSE")


def _enum(v: Any) -> str:
    return getattr(v, "name", None) or str(v)


def somar_metricas(linhas: Sequence[Any]) -> Dict[str, Any]:
    """Soma as linhas da GAQL. Pura (testável com dublês de linha).

    ⚠️ Zero linhas NÃO é ausência: a consulta rodou e a API não devolve linha
    para quem não teve entrega na janela. É "medi e não houve" — 0 — e fica
    marcado em `sem_linhas` para a evidência dizer de onde veio o zero.
    A moeda vem da conta; sem linha, ela fica `None`, e o custo zero sem moeda
    seria recusado pela CHECK — então o chamador a completa pela conta.
    """
    total = {"impressoes": 0, "cliques": 0, "custo_micros": 0, "conversoes": 0.0,
             "valor_conversao_micros": 0, "moeda": None, "sem_linhas": not linhas}
    for r in linhas:
        m = r.metrics
        total["impressoes"] += int(m.impressions)
        total["cliques"] += int(m.clicks)
        total["custo_micros"] += int(m.cost_micros)
        total["conversoes"] += float(m.conversions)
        total["valor_conversao_micros"] += int(round(float(m.conversions_value) * 1_000_000))
        total["moeda"] = total["moeda"] or r.customer.currency_code or None
    total["conversoes"] = round(total["conversoes"], 2)
    return total


class ContaGoogleAds:
    """O adaptador real. Síncrono; os casos de uso o chamam por `to_thread`."""

    def __init__(self, login_customer_id: str = escopo.MCC_DA_CASA) -> None:
        self.login = str(login_customer_id)

    def _buscar(self, customer_id: str, gaql: str) -> List[Any]:
        from volc_ads.gads import catalogo  # noqa: PLC0415
        from volc_ads.gads.client import buscar  # noqa: PLC0415

        return list(buscar(str(customer_id), catalogo.exigir_valida(gaql),
                           login_customer_id=self.login))

    def ler_antes(self, customer_id: str, acao: Any, *, conferir: bool) -> Any:
        from volc_ads.gestao import estado  # noqa: PLC0415

        return estado.ler(customer_id, acao, login_customer_id=self.login, conferir=conferir)

    def ler_metricas(self, customer_id: str, nivel: str, alvo_id: str,
                     inicio: str, fim: str) -> Dict[str, Any]:
        if nivel == "anuncio":
            grupo, anuncio = str(alvo_id).split("~")
            gaql = _GAQL_METRICAS[nivel].format(grupo=int(grupo), anuncio=int(anuncio),
                                                inicio=inicio, fim=fim)
        else:
            gaql = _GAQL_METRICAS[nivel].format(alvo=int(alvo_id) if alvo_id else 0,
                                                inicio=inicio, fim=fim)
        total = somar_metricas(self._buscar(customer_id, gaql))
        if total["moeda"] is None:
            conta = self._buscar(customer_id, "SELECT customer.id, customer.currency_code "
                                              "FROM customer")
            total["moeda"] = conta[0].customer.currency_code if conta else None
        return total

    def ler_campanha(self, customer_id: str, campaign_id: str) -> Optional[Dict[str, Any]]:
        for r in self._buscar(customer_id, GAQL_CAMPANHA.format(campanha=int(campaign_id))):
            c = r.campaign
            return {"campaign_id": str(c.id), "nome": c.name, "status": _enum(c.status),
                    "canal": _enum(c.advertising_channel_type),
                    "moeda": r.customer.currency_code}
        return None

    def validar(self, customer_id: str, acoes: Sequence[Any]) -> Any:
        from volc_ads.gestao import lote  # noqa: PLC0415

        return lote.validar(customer_id, list(acoes), login_customer_id=self.login)

    def aplicar(self, customer_id: str, acoes: Sequence[Any], motivo: str) -> Tuple[Any, Any]:
        from volc_ads.gestao import lote  # noqa: PLC0415

        return lote.aplicar(customer_id, list(acoes), login_customer_id=self.login,
                            motivo=motivo)

    def aplicar_recomendacoes(self, customer_id: str, acoes: Sequence[Any],
                              motivo: str) -> Dict[str, Any]:
        from volc_ads.gestao import lote  # noqa: PLC0415

        return lote.aplicar_recomendacoes(customer_id, list(acoes),
                                          login_customer_id=self.login, motivo=motivo)

    def recomendacoes(self, customer_id: str) -> List[Dict[str, Any]]:
        saida = []
        for r in self._buscar(customer_id, GAQL_RECOMENDACOES):
            rec = r.recommendation
            base = rec.impact.base_metrics
            pot = rec.impact.potential_metrics
            saida.append({
                "recurso": rec.resource_name, "tipo": _enum(rec.type_),
                "campanha": rec.campaign or None, "orcamento": rec.campaign_budget or None,
                "grupo": rec.ad_group or None, "dispensada": bool(rec.dismissed),
                "impacto": {
                    "base": {"impressoes": base.impressions, "cliques": base.clicks,
                             "custo_micros": base.cost_micros,
                             "conversoes": base.conversions},
                    "potencial": {"impressoes": pot.impressions, "cliques": pot.clicks,
                                  "custo_micros": pot.cost_micros,
                                  "conversoes": pot.conversions},
                },
                # A ação tipada que a tela manda de volta em POST /propostas.
                "acoes": [{"tipo": "recomendacao.aplicar", "recurso": rec.resource_name},
                          {"tipo": "recomendacao.dispensar", "recurso": rec.resource_name}],
            })
        return saida
