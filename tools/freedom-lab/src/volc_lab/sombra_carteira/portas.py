"""Contratos de entrada do motor da carteira, consumidos por interface.

O motor não copia código do W11 nem do W12. Ele declara aqui a FORMA das linhas
que lê e a porta por onde elas chegam; qualquer adaptador (snapshot JSON,
PostgREST, banco descartável) que entregue essa forma serve.

- Custo: o fato canônico `google_ads_campanha_dia` (v12_04), que a coleta e a
  recoleta do W11 alimentam (último valor por dia, recoleta incluída). Só a
  linha NÃO segmentada (`segmentos = {}`) é o total da campanha no dia, a mesma
  regra da v17_04. NUNCA `daily_campaign_metrics`: lá fica o D-1 projetado
  para painel e comissão, e a recoleta do W11 não projeta nele.
- Receita: `receita_as_of(conhecido_ate)` / `vw_receita_vigente` (v23_01, W12).
  Cada linha já traz `receita_brl` convertida pelo `cambio_resolver` e o
  `cambio_modo` usado. `defasada` e `sem_cotacao` chegam com `receita_brl`
  NULL: o motor nunca converte por conta própria e nunca usa câmbio fixo.

Campo obrigatório ausente na linha é `ContratoQuebrado`, nunca valor padrão:
uma coluna renomeada do outro lado não pode virar zero aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional, Protocol, Sequence


class ContratoQuebrado(ValueError):
    """A linha lida não tem a forma do contrato de origem."""


MODOS_CAMBIO = ("exata", "anterior", "defasada", "sem_cotacao", "moeda_local", "sem_receita")
FONTES_RECEITA = ("joinads", "gam")


def _exigir(linha: Mapping[str, Any], campos: Sequence[str], origem: str) -> None:
    faltam = [c for c in campos if c not in linha]
    if faltam:
        raise ContratoQuebrado(f"{origem}: linha sem {', '.join(faltam)}")


def _data(valor: Any, origem: str) -> date:
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError as exc:
        raise ContratoQuebrado(f"{origem}: data ilegível {valor!r}") from exc


def _inteiro(valor: Any, campo: str, origem: str) -> Optional[int]:
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise ContratoQuebrado(f"{origem}: {campo} não é inteiro ({valor!r})") from exc


def _numero(valor: Any, campo: str, origem: str) -> Optional[float]:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
        raise ContratoQuebrado(f"{origem}: {campo} não é número ({valor!r})") from exc


@dataclass(frozen=True)
class CustoDia:
    """Uma linha de `google_ads_campanha_dia` (v12_04)."""

    customer_id: str
    campaign_id: str
    metric_date: date
    segmentado: bool
    custo_micros: Optional[int]   # None = custo não lido, nunca zero
    cliques: Optional[int]
    currency_code: str
    janela_fechada: bool
    campaign_name: Optional[str]
    campaign_status: Optional[str]
    valor_conversoes: Optional[float]   # valor estático do Google; nunca decide
    colhida_em: str
    origem_janela: str            # D0, D-1 ou backfill: quem gravou o último valor

    CAMPOS = ("customer_id", "campaign_id", "metric_date", "segmentos", "custo_micros",
              "cliques", "currency_code", "janela_fechada", "campaign_name",
              "campaign_status", "valor_conversoes", "colhida_em", "origem_janela")

    @classmethod
    def da_linha(cls, linha: Mapping[str, Any]) -> "CustoDia":
        origem = "google_ads_campanha_dia"
        _exigir(linha, cls.CAMPOS, origem)
        segmentos = linha["segmentos"]
        if not isinstance(segmentos, dict):
            raise ContratoQuebrado(f"{origem}: segmentos não é objeto ({segmentos!r})")
        if not isinstance(linha["janela_fechada"], bool):
            raise ContratoQuebrado(f"{origem}: janela_fechada não é booleano")
        return cls(
            customer_id=str(linha["customer_id"]),
            campaign_id=str(linha["campaign_id"]),
            metric_date=_data(linha["metric_date"], origem),
            segmentado=bool(segmentos),
            custo_micros=_inteiro(linha["custo_micros"], "custo_micros", origem),
            cliques=_inteiro(linha["cliques"], "cliques", origem),
            currency_code=str(linha["currency_code"] or ""),
            janela_fechada=linha["janela_fechada"],
            campaign_name=None if linha["campaign_name"] is None else str(linha["campaign_name"]),
            campaign_status=None if linha["campaign_status"] is None else str(linha["campaign_status"]),
            valor_conversoes=_numero(linha["valor_conversoes"], "valor_conversoes", origem),
            colhida_em=str(linha["colhida_em"]),
            origem_janela=str(linha["origem_janela"]),
        )


@dataclass(frozen=True)
class ReceitaObservada:
    """Uma linha de `receita_as_of()` / `vw_receita_vigente` (v23_01)."""

    fonte: str
    campanha: str            # chave.utm_campaign_value
    componente: str          # joinads_domain (JoinAds) ou gam_accounts_id (GAM)
    data_referencia: date
    moeda: str
    receita: Optional[float]       # moeda de origem; None = ausente
    receita_brl: Optional[float]   # None quando o câmbio não resolveu
    cambio_modo: str
    cambio_taxa: Optional[float]
    cambio_defasagem_dias: Optional[int]
    coletado_em: str

    CAMPOS = ("fonte", "chave", "data_referencia", "moeda", "receita", "receita_brl",
              "cambio_modo", "cambio_taxa", "cambio_defasagem_dias", "coletado_em", "removida")

    @classmethod
    def da_linha(cls, linha: Mapping[str, Any]) -> "ReceitaObservada":
        origem = "receita_as_of"
        _exigir(linha, cls.CAMPOS, origem)
        fonte = str(linha["fonte"])
        if fonte not in FONTES_RECEITA:
            raise ContratoQuebrado(f"{origem}: fonte fora do contrato ({fonte!r})")
        if linha["removida"] is not False:
            # receita_as_of e vw_receita_vigente já excluem removidas; se uma
            # chegou, a fonte não é a que o contrato diz.
            raise ContratoQuebrado(f"{origem}: linha removida na leitura vigente")
        chave = linha["chave"]
        if not isinstance(chave, dict) or "utm_campaign_value" not in chave:
            raise ContratoQuebrado(f"{origem}: chave sem utm_campaign_value")
        modo = str(linha["cambio_modo"])
        if modo not in MODOS_CAMBIO:
            raise ContratoQuebrado(f"{origem}: cambio_modo fora do contrato ({modo!r})")
        if linha["data_referencia"] is None:
            raise ContratoQuebrado(f"{origem}: data_referencia nula")
        componente = chave.get("joinads_domain", chave.get("gam_accounts_id"))
        receita_brl = _numero(linha["receita_brl"], "receita_brl", origem)
        if receita_brl is not None and modo not in ("exata", "anterior", "moeda_local"):
            # O CHECK receita_observacao_brl_ck da v23_01 proíbe isso; se chegou,
            # não é a fonte do contrato.
            raise ContratoQuebrado(f"{origem}: receita_brl com cambio_modo {modo}")
        return cls(
            fonte=fonte,
            campanha=str(chave["utm_campaign_value"]),
            componente=str(componente),
            data_referencia=_data(linha["data_referencia"], origem),
            moeda=str(linha["moeda"]),
            receita=_numero(linha["receita"], "receita", origem),
            receita_brl=receita_brl,
            cambio_modo=modo,
            cambio_taxa=_numero(linha["cambio_taxa"], "cambio_taxa", origem),
            cambio_defasagem_dias=_inteiro(linha["cambio_defasagem_dias"], "cambio_defasagem_dias", origem),
            coletado_em=str(linha["coletado_em"]),
        )


@dataclass(frozen=True)
class Leitura:
    """O que uma porta devolveu, com o instante da leitura."""

    linhas: tuple[Mapping[str, Any], ...]
    lido_em: str          # ISO-8601 UTC
    fonte: str            # descrição legível de onde veio


class FonteCusto(Protocol):
    def custo_campanha_dia(self, conta: str, inicio: date, fim: date) -> Leitura: ...


class FonteReceita(Protocol):
    def receita_vigente(self, inicio: date, fim: date) -> Leitura: ...
