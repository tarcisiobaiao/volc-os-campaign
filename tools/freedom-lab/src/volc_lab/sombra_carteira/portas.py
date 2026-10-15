"""Contratos de entrada do motor da carteira, consumidos por interface.

O motor não copia código do W11 nem do W12. Ele declara aqui a FORMA das linhas
que lê e a porta por onde elas chegam; qualquer adaptador (snapshot JSON,
PostgREST, banco descartável) que entregue essa forma serve.

- Custo: o fato canônico `google_ads_campanha_dia` (v12_04), que a coleta e a
  recoleta do W11 alimentam (último valor por dia, recoleta incluída). Só a
  linha NÃO segmentada (`segmentos = {}`) é o total da campanha no dia, a mesma
  regra da v17_04. NUNCA `daily_campaign_metrics`: lá fica o D-1 projetado
  para painel e comissão, e a recoleta do W11 não projeta nele.
- Receita: `receita_as_of(conhecido_ate)` / `vw_receita_vigente` (v23_01, W12),
  na moeda de origem (`receita`, `moeda`).
- Câmbio: `cambio_resolver(data, par, max_defasagem, conhecido_ate)` (v23_01),
  resolvido NA LEITURA (ciclo corretivo 2). O `receita_brl` que o W12 grava é
  o câmbio do instante da ingestão e nunca é re-resolvido: um dia ingerido
  antes da PTAX ficaria `defasada` para sempre. Por isso o motor usa a
  `receita` de origem × a cotação que o resolvedor devolve agora, com o mesmo
  corte `conhecido_ate` da leitura de receita. O motor nunca usa câmbio fixo
  nem `revenue_converted`.

Campo obrigatório ausente na linha é `ContratoQuebrado`, nunca valor padrão:
uma coluna renomeada do outro lado não pode virar zero aqui.
"""
from __future__ import annotations

import math
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


def _nao_negativo(valor: Optional[float], campo: str, origem: str) -> Optional[float]:
    # Estorno não está no contrato de nenhuma das fontes; negativo é recusado,
    # não subtraído em silêncio.
    if valor is not None and valor < 0:
        raise ContratoQuebrado(f"{origem}: {campo} negativo ({valor!r})")
    return valor


def _inteiro(valor: Any, campo: str, origem: str) -> Optional[int]:
    if valor is None:
        return None
    if isinstance(valor, bool) or (isinstance(valor, float) and not valor.is_integer()):
        raise ContratoQuebrado(f"{origem}: {campo} não é inteiro ({valor!r})")
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise ContratoQuebrado(f"{origem}: {campo} não é inteiro ({valor!r})") from exc


def _numero(valor: Any, campo: str, origem: str) -> Optional[float]:
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ContratoQuebrado(f"{origem}: {campo} é booleano, não número")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ContratoQuebrado(f"{origem}: {campo} não é número ({valor!r})") from exc
    if not math.isfinite(numero):
        # numeric NaN do Postgres chega como "NaN"; não é medição nem ausência.
        raise ContratoQuebrado(f"{origem}: {campo} não é finito ({valor!r})")
    return numero


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
            custo_micros=_nao_negativo(_inteiro(linha["custo_micros"], "custo_micros", origem),
                                       "custo_micros", origem),
            cliques=_nao_negativo(_inteiro(linha["cliques"], "cliques", origem), "cliques", origem),
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
        # A chave de upsert da v23_01: date + utm_campaign_value + o componente.
        campo_componente = "joinads_domain" if fonte == "joinads" else "gam_accounts_id"
        if campo_componente not in chave:
            raise ContratoQuebrado(f"{origem}: chave {fonte} sem {campo_componente}")
        componente = chave[campo_componente]
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
            receita=_nao_negativo(_numero(linha["receita"], "receita", origem), "receita", origem),
            receita_brl=receita_brl,
            cambio_modo=modo,
            cambio_taxa=_numero(linha["cambio_taxa"], "cambio_taxa", origem),
            cambio_defasagem_dias=_inteiro(linha["cambio_defasagem_dias"], "cambio_defasagem_dias", origem),
            coletado_em=str(linha["coletado_em"]),
        )


@dataclass(frozen=True)
class Cotacao:
    """Uma resposta de `cambio_resolver` (v23_01) para (par, data) pedidos."""

    par: str
    data: date                     # o dia PEDIDO (o da receita)
    modo: str                      # exata | anterior | defasada | sem_cotacao
    taxa: Optional[float]          # None quando defasada/sem_cotacao
    data_cotacao: Optional[date]
    defasagem_dias: Optional[int]
    cotacao_id: Optional[int]
    fonte: Optional[str]

    CAMPOS = ("par", "data", "modo", "taxa", "data_cotacao", "defasagem_dias", "cotacao_id", "fonte")
    MODOS = ("exata", "anterior", "defasada", "sem_cotacao")

    @classmethod
    def da_linha(cls, linha: Mapping[str, Any]) -> "Cotacao":
        origem = "cambio_resolver"
        _exigir(linha, cls.CAMPOS, origem)
        modo = str(linha["modo"])
        if modo not in cls.MODOS:
            raise ContratoQuebrado(f"{origem}: modo fora do contrato ({modo!r})")
        taxa = _numero(linha["taxa"], "taxa", origem)
        if modo in ("exata", "anterior") and (taxa is None or taxa <= 0 or linha["cotacao_id"] is None):
            raise ContratoQuebrado(f"{origem}: modo {modo} sem taxa positiva e cotação")
        if modo in ("defasada", "sem_cotacao") and taxa is not None:
            raise ContratoQuebrado(f"{origem}: modo {modo} com taxa")
        return cls(
            par=str(linha["par"]),
            data=_data(linha["data"], origem),
            modo=modo,
            taxa=taxa,
            data_cotacao=None if linha["data_cotacao"] is None else _data(linha["data_cotacao"], origem),
            defasagem_dias=_inteiro(linha["defasagem_dias"], "defasagem_dias", origem),
            cotacao_id=_inteiro(linha["cotacao_id"], "cotacao_id", origem),
            fonte=None if linha["fonte"] is None else str(linha["fonte"]),
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


class FonteCambio(Protocol):
    def cotacoes(self, pedidos: Sequence[tuple[str, date]], conhecido_ate: str,
                 max_defasagem_dias: int) -> Leitura: ...
