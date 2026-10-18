"""Adapters de integração FUTURA — interfaces puras, sem chamadas externas.

Cada adapter transforma uma forma de dado já conhecida (ledger campanha×dia, linha GAQL de
`campaign_simulation`, Keyword Planner/DataForSEO, JoinAds, card do Pautador, pedido da Bia) em
`EntradaViabilidade` ou em partes dela. Nenhum adapter lê rede, banco ou arquivo: recebe dicts.

Regras do ledger campanha×dia (`de_ledger_campanha_dia`):
- custo e cliques somam TODOS os dias maduros com custo; a receita nunca filtra o custo;
- receita soma só dias maduros com `receita_status` em {observed, zero_confirmed} (zero confirmado ≠ ausente);
- nada vira zero por ausência: `cliques` ausente num dia com custo ⇒ cliques agregado UNKNOWN (o custo
  continua real e somável; a contagem não é) — decisão: rebaixar a evidência em vez de rejeitar a entrada,
  porque o kernel já diz "cliques_unknown" e o custo não deixa de existir;
- moedas heterogêneas dentro do custo ou dentro da receita ⇒ `ContratoViabilidadeViolado("moedas_heterogeneas")`;
- moeda NUNCA é assumida (sem BRL/USD por padrão): se nenhuma linha declara `custo_moeda` (ou `receita_moeda`
  onde há receita com valor), a medida vira valor=None, evidencia=UNKNOWN, moeda_evidencia=UNKNOWN, flag
  `moeda_ausente` — custo sem moeda não é somável (fail-closed); os dias e os cliques continuam contados.
  Linha COM valor e SEM moeda enquanto alguma linha do ledger declara a moeda ⇒
  `ContratoViabilidadeViolado("moeda_ausente_em_linha")` (ausência heterogênea, não é "a moeda das outras");
- o câmbio nunca inventa o par: `de`/`para` só entram quando ambas as moedas são conhecidas (do dict ou das
  linhas); caso contrário o câmbio é ABSENT com proveniencia "moeda_desconhecida" e `de`/`para` vazios — uma
  taxa sem par não converte nada, e o kernel dirá `cambio_ausente` se precisar converter;
- evidência agregada = a MAIS FRACA entre as linhas (FORCA); moeda_evidencia idem; flags = união;
  observado_em = o mais antigo; fonte = a declarada na chamada;
- datas duplicadas ⇒ fica a linha de maior `disponivel_em`, flag `datas_duplicadas=N`, dias_* contam datas distintas;
- câmbio/revshare/imposto entram VERSIONADOS (effective_at, disponivel_em, versao; hash calculado ou verificado);
- perda_maxima só entra como {valor, horizonte_dias, autorizacao}; `proveniencia` não substitui autorização.

A Bia pode PEDIR uma avaliação; nunca define tolerância do owner, câmbio, revshare, imposto, nem passa
uma autorização, nem transforma a recomendação em execução. A fronteira Pautador/Bia recebe uma
`Autorizacao` por referência, emitida do lado VOLC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from volc_dil.contracts import Dinheiro

from .contrato import (
    FORCA, Autorizacao, Cambio, ContratoViabilidadeViolado, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem,
    MedidaMonetaria, PerdaMaxima, PontoSimulacao, SimulacaoEntrada, Taxa,
)

_STATUS_COM_VALOR = {"observed", "zero_confirmed"}
_STATUS_PARA_EVIDENCIA = {"observed": Evidencia.OBSERVED, "zero_confirmed": Evidencia.OBSERVED, "partial": Evidencia.IMMATURE,
                          "missing": Evidencia.ABSENT, "late": Evidencia.UNKNOWN, "unavailable": Evidencia.UNKNOWN,
                          "unsupported": Evidencia.UNKNOWN, "invalid": Evidencia.INVALID, "projected": Evidencia.PROJECTED,
                          "estimated": Evidencia.ESTIMATED, "attested": Evidencia.ATTESTED, "reconciled": Evidencia.RECONCILED}
_PPM = 1_000_000


# --------------------------------------------------------------------------- parâmetros versionados
def _instante_de(d: Mapping[str, Any], chave: str, nome: str, obrigatorio: bool) -> Optional[datetime]:
    v = d.get(chave)
    if v is None:
        if obrigatorio:
            raise ContratoViabilidadeViolado(f"{nome}.{chave} é obrigatório (parâmetro versionado)")
        return None
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


MOEDA_DESCONHECIDA = ""  # `Cambio.de`/`Cambio.para` vazios: o par não é conhecido e nunca é inventado


def _cambio(d: Optional[Mapping[str, Any]], de: Optional[str], para: Optional[str]) -> Cambio:
    """`de`/`para` do chamador (moedas das linhas) só valem quando ambas são conhecidas; o dict pode declará-las
    explicitamente. Sem par conhecido o câmbio é ABSENT/"moeda_desconhecida" mesmo que o dict traga uma taxa:
    uma taxa sem par não converte nada (e o kernel dirá `cambio_ausente` quando precisar converter)."""
    d = d or {}
    # Uma taxa é uma afirmação sobre um par específico. As moedas observadas no
    # ledger podem dizer se uma conversão seria necessária, mas não podem
    # completar silenciosamente o contrato de uma cotação. Sem o par explícito,
    # descartamos a taxa e devolvemos câmbio ausente (fail-closed, preservando o
    # contrato público do adapter).
    if d.get("taxa") is not None and (not d.get("de") or not d.get("para")):
        return Cambio(taxa=None, de=MOEDA_DESCONHECIDA, para=MOEDA_DESCONHECIDA,
                      proveniencia="moeda_desconhecida", evidencia=Evidencia.ABSENT)
    de_ = str(d["de"]) if d.get("de") else de
    para_ = str(d["para"]) if d.get("para") else para
    if not de_ or not para_:
        return Cambio(taxa=None, de=MOEDA_DESCONHECIDA, para=MOEDA_DESCONHECIDA, proveniencia="moeda_desconhecida", evidencia=Evidencia.ABSENT)
    if d.get("taxa") is None:
        return Cambio(taxa=None, de=de_, para=para_, proveniencia=d.get("proveniencia", "ausente"), evidencia=Evidencia.ABSENT)
    return Cambio(taxa=Decimal(str(d["taxa"])), de=de_, para=para_, proveniencia=d.get("proveniencia", ""),
                  evidencia=Evidencia(d.get("evidencia", "estimated")), effective_at=_instante_de(d, "effective_at", "cambio", True),
                  disponivel_em=_instante_de(d, "disponivel_em", "cambio", True), versao=str(d.get("versao", "")), hash=str(d.get("hash", "")))


def _taxa(d: Optional[Mapping[str, Any]], nome: str) -> Taxa:
    if not d or d.get("valor") is None:
        return Taxa(valor=None, evidencia=Evidencia.UNKNOWN, proveniencia=(d or {}).get("proveniencia", "ausente"))
    return Taxa(valor=Decimal(str(d["valor"])), evidencia=Evidencia(d.get("evidencia", "attested")), proveniencia=d.get("proveniencia", ""),
                effective_at=_instante_de(d, "effective_at", nome, True), disponivel_em=_instante_de(d, "disponivel_em", nome, True),
                versao=str(d.get("versao", "")), hash=str(d.get("hash", "")))


def _perda(d: Optional[Mapping[str, Any]]) -> PerdaMaxima:
    if not d or (d.get("valor") is None and d.get("horizonte_dias") is None and d.get("autorizacao") is None):
        return PerdaMaxima(valor=None, horizonte_dias=None, autorizacao=None)
    if d.get("autorizacao") is None:
        raise ContratoViabilidadeViolado("perda_maxima sem autorização versionada (só entra como {valor, horizonte_dias, autorizacao})")
    return PerdaMaxima(valor=None if d.get("valor") is None else Dinheiro.de_json(d["valor"]), horizonte_dias=d.get("horizonte_dias"),
                       autorizacao=Autorizacao.de_json(d["autorizacao"]))


# --------------------------------------------------------------------------- agregação por linha
def _mais_fraca(evidencias: Iterable[Evidencia], vazio: Evidencia) -> Evidencia:
    evs = list(evidencias)
    return min(evs, key=lambda e: FORCA[e]) if evs else vazio


def _evidencia(l: Mapping[str, Any], chave: str, padrao: Evidencia) -> Evidencia:
    v = l.get(chave)
    if v is None:
        return padrao
    return _STATUS_PARA_EVIDENCIA[v] if v in _STATUS_PARA_EVIDENCIA else Evidencia(v)


def _moeda_unica(linhas: Sequence[Mapping[str, Any]], chave: str, medida: str) -> Optional[str]:
    """A única moeda declarada no ledger para a medida; None quando nenhuma linha declara (nunca um padrão)."""
    moedas = {l[chave] for l in linhas if l.get(chave)}
    if len(moedas) > 1:
        raise ContratoViabilidadeViolado(f"moedas_heterogeneas em {medida}: {sorted(moedas)}")
    return next(iter(moedas)) if moedas else None


def _moeda_somavel(com_valor: Sequence[Mapping[str, Any]], chave: str, medida: str, declarada: Optional[str]) -> Optional[str]:
    """Moeda com que as linhas COM valor podem ser somadas. Linha com valor sem moeda: se o ledger declara a moeda em
    alguma linha, é `moeda_ausente_em_linha` (erro de contrato); se nenhuma declara, devolve None (medida não somável)."""
    sem = [l["dia"] for l in com_valor if not l.get(chave)]
    if sem and declarada is not None:
        raise ContratoViabilidadeViolado(f"moeda_ausente_em_linha em {medida}: {len(sem)} de {len(com_valor)} linhas com valor sem {chave} ({', '.join(sem)})")
    return None if sem else declarada


def _dt(v: Any) -> Optional[datetime]:
    return None if v is None else (v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))


def _mais_antigo(linhas: Sequence[Mapping[str, Any]], chave: str) -> Optional[datetime]:
    ds = [_dt(l.get(chave)) for l in linhas if l.get(chave) is not None]
    return min(ds) if ds else None


def _flags_das_linhas(linhas: Sequence[Mapping[str, Any]]) -> set[str]:
    out: set[str] = set()
    for l in linhas:
        out.update(str(f) for f in (l.get("flags") or ()))
    return out


def _dedup_por_dia(linhas: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], int]:
    """Uma linha por `dia`: fica a de maior `disponivel_em` (empate: a última na sequência). Devolve (linhas, duplicadas removidas)."""
    por_dia: dict[str, Mapping[str, Any]] = {}
    for l in linhas:
        dia = l["dia"]
        if dia not in por_dia or _dt(l["disponivel_em"]) >= _dt(por_dia[dia]["disponivel_em"]):  # type: ignore[operator]
            por_dia[dia] = l
    return [por_dia[d] for d in sorted(por_dia)], len(linhas) - len(por_dia)


def de_ledger_campanha_dia(candidato_id: str, linhas: Sequence[Mapping[str, Any]], *, as_of: datetime, vertical: str = "", pais: str = "",
                           fonte_custo: str = "google_ads", fonte_receita: str = "joinads", cambio: Optional[Mapping[str, Any]] = None,
                           revshare: Optional[Mapping[str, Any]] = None, imposto: Optional[Mapping[str, Any]] = None,
                           perda_maxima: Optional[Mapping[str, Any]] = None, simulacao: Optional[SimulacaoEntrada] = None,
                           freshness_sla_dias: int = 7) -> EntradaViabilidade:
    """Agrega linhas campanha×dia do ledger econômico (ver regras no cabeçalho do módulo).

    Chaves por linha: dia, maduro, disponivel_em, custo_micros, custo_moeda, custo_moeda_evidencia, cliques,
    receita_micros, receita_moeda, receita_moeda_evidencia, receita_status; opcionais: status (evidência da linha
    no lado do custo: observed/projected/estimated…), custo_evidencia, cliques_evidencia, observado_em, flags."""
    linhas, duplicadas = _dedup_por_dia(linhas)
    maduras = [l for l in linhas if l.get("maduro")]
    imaturas = [l for l in linhas if not l.get("maduro")]
    com_custo = [l for l in maduras if l.get("custo_micros") is not None]
    com_receita = [l for l in maduras if l.get("receita_status") in _STATUS_COM_VALOR and l.get("receita_micros") is not None]
    dias_custo = {l["dia"] for l in com_custo}
    dias_receita = {l["dia"] for l in com_receita}
    sem_receita = sorted(dias_custo - dias_receita)
    disp = max((_dt(l["disponivel_em"]) for l in linhas), default=as_of)  # type: ignore[type-var]
    moeda_custo = _moeda_unica(linhas, "custo_moeda", "custo")
    moeda_rec = _moeda_unica(linhas, "receita_moeda", "receita")
    moeda_custo_somavel = _moeda_somavel(com_custo, "custo_moeda", "custo", moeda_custo)
    moeda_rec_somavel = _moeda_somavel(com_receita, "receita_moeda", "receita", moeda_rec)
    flags = _flags_das_linhas(maduras)
    if sem_receita:
        flags.add(f"dias_com_custo_sem_receita={len(sem_receita)}")
    if duplicadas:
        flags.add(f"datas_duplicadas={duplicadas}")
    sem_custo = [l for l in maduras if l.get("custo_micros") is None]
    if sem_custo:
        flags.add(f"dias_maduros_sem_custo={len(sem_custo)}")

    # custo e cliques: todos os dias maduros com custo
    if com_custo:
        ev_custo = _mais_fraca((_evidencia(l, "custo_evidencia", _evidencia(l, "status", Evidencia.OBSERVED)) for l in com_custo), Evidencia.OBSERVED)
        if moeda_custo_somavel is None:
            # custo sem moeda em nenhuma linha: não é somável (nunca BRL por padrão); dias e cliques continuam reais
            custo = MedidaMonetaria(None, Evidencia.UNKNOWN, Evidencia.UNKNOWN, disp, fonte_custo, observado_em=_mais_antigo(com_custo, "observado_em"),
                                    flags_qualidade=tuple(sorted(_flags_das_linhas(com_custo) | {"moeda_ausente"})))
            flags.add("moeda_ausente")
        else:
            custo = MedidaMonetaria(Dinheiro(sum(int(l["custo_micros"]) for l in com_custo), moeda_custo_somavel), ev_custo,
                                    _mais_fraca((_evidencia(l, "custo_moeda_evidencia", Evidencia.UNKNOWN) for l in com_custo), Evidencia.UNKNOWN),
                                    disp, fonte_custo, observado_em=_mais_antigo(com_custo, "observado_em"), flags_qualidade=tuple(_flags_das_linhas(com_custo)))
        sem_cliques = [l for l in com_custo if l.get("cliques") is None]
        if sem_cliques:
            cliques = MedidaContagem(None, Evidencia.UNKNOWN, disp, fonte_custo, observado_em=_mais_antigo(com_custo, "observado_em"),
                                     flags_qualidade=(f"cliques_ausentes_em_dias_com_custo={len(sem_cliques)}",))
            flags.add(f"cliques_ausentes_em_dias_com_custo={len(sem_cliques)}")
        else:
            ev_cliques = _mais_fraca((_evidencia(l, "cliques_evidencia", _evidencia(l, "custo_evidencia", _evidencia(l, "status", Evidencia.OBSERVED))) for l in com_custo), Evidencia.OBSERVED)
            cliques = MedidaContagem(sum(int(l["cliques"]) for l in com_custo), ev_cliques, disp, fonte_custo,
                                     observado_em=_mais_antigo(com_custo, "observado_em"), flags_qualidade=tuple(_flags_das_linhas(com_custo)))
    else:
        custo = MedidaMonetaria(None, Evidencia.ABSENT, Evidencia.UNKNOWN, disp, fonte_custo)
        cliques = MedidaContagem(None, Evidencia.ABSENT, disp, fonte_custo)

    # receita: só dias maduros com receita observada/zero confirmado; moeda_evidencia = a mais fraca das linhas com receita
    if com_receita and moeda_rec_somavel is None:
        # receita com valor mas sem moeda em nenhuma linha: não é somável (nunca USD por padrão)
        receita = MedidaMonetaria(None, Evidencia.UNKNOWN, Evidencia.UNKNOWN, disp, fonte_receita, observado_em=_mais_antigo(com_receita, "observado_em"),
                                  flags_qualidade=tuple(sorted(_flags_das_linhas(com_receita) | {"moeda_ausente"})))
        flags.add("moeda_ausente")
    elif com_receita:
        receita = MedidaMonetaria(Dinheiro(sum(int(l["receita_micros"]) for l in com_receita), moeda_rec_somavel),
                                  _mais_fraca((_evidencia(l, "receita_evidencia", Evidencia.RECONCILED) for l in com_receita), Evidencia.RECONCILED),
                                  _mais_fraca((_evidencia(l, "receita_moeda_evidencia", Evidencia.UNKNOWN) for l in com_receita), Evidencia.UNKNOWN),
                                  disp, fonte_receita, observado_em=_mais_antigo(com_receita, "observado_em"), flags_qualidade=tuple(_flags_das_linhas(com_receita)))
    else:
        moeda_rec_ev = _mais_fraca((_evidencia(l, "receita_moeda_evidencia", Evidencia.UNKNOWN) for l in maduras), Evidencia.UNKNOWN)
        ev = _mais_fraca((_evidencia(l, "receita_status", Evidencia.UNKNOWN) for l in maduras), Evidencia.ABSENT)
        receita = MedidaMonetaria(None, ev if ev in (Evidencia.ABSENT, Evidencia.UNKNOWN, Evidencia.INVALID) else Evidencia.ABSENT,
                                  moeda_rec_ev if moeda_rec_ev is not Evidencia.OBSERVED else Evidencia.UNKNOWN, disp, fonte_receita)

    dias = sorted(l["dia"] for l in linhas) or [as_of.date().isoformat()]
    janela = JanelaObservada(dias[0], dias[-1], dias_maduros=len(dias_custo), dias_imaturos=len({l["dia"] for l in imaturas}),
                             dias_custo_maduro=len(dias_custo), dias_receita_madura=len(dias_receita), dias_custo_sem_receita=len(sem_receita),
                             cobertura_receita_ppm=None if not dias_custo else (len(dias_receita) * _PPM) // len(dias_custo))
    return EntradaViabilidade(
        candidato_id=candidato_id, vertical=vertical, pais=pais, fonte_custo=fonte_custo, fonte_receita=fonte_receita, as_of=as_of,
        janela=janela, cliques=cliques, custo=custo, receita=receita, cambio=_cambio(cambio, moeda_rec, moeda_custo),
        revshare=_taxa(revshare, "revshare"), imposto=_taxa(imposto, "imposto"), perda_maxima=_perda(perda_maxima), simulacao=simulacao,
        flags_qualidade=tuple(sorted(flags)), freshness_sla_dias=freshness_sla_dias,
    )


def _int(v: Any) -> Optional[int]:
    return None if v is None else int(v)


def de_campaign_simulation_gaql(linha: Mapping[str, Any], *, moeda: str, disponivel_em: datetime, estrategia_lance: str = "", canal: str = "",
                                cambio: Optional[Cambio] = None) -> SimulacaoEntrada:
    """Mapeia uma linha GAQL de `campaign_simulation` (camelCase ou snake_case) para `SimulacaoEntrada`.
    Tipos sem lista de pontos interpretável devolvem pontos vazios (o kernel diz 'tipo_nao_suportado')."""
    cs = linha.get("campaign_simulation") or linha.get("campaignSimulation") or {}
    tipo = cs.get("type", "")
    lista = {"CPC_BID": ("cpc_bid_point_list", "cpcBidPointList", "cpc_bid_micros", "cpcBidMicros"),
             "BUDGET": ("budget_point_list", "budgetPointList", "budget_amount_micros", "budgetAmountMicros")}.get(tipo)
    pontos: list[PontoSimulacao] = []
    if lista:
        pl = cs.get(lista[0]) or cs.get(lista[1]) or {}
        for p in pl.get("points", []):
            mod = p.get(lista[2], p.get(lista[3]))
            conv = p.get("biddable_conversions", p.get("biddableConversions"))
            pontos.append(PontoSimulacao(
                modificacao_micros=int(mod), cliques=_int(p.get("clicks")), custo_micros=_int(p.get("cost_micros", p.get("costMicros"))),
                impressoes=_int(p.get("impressions")), conversoes=None if conv is None else Decimal(str(conv)),
            ))
    return SimulacaoEntrada(tipo=tipo, moeda=moeda, pontos=tuple(pontos), disponivel_em=disponivel_em, estrategia_lance=estrategia_lance, canal=canal, cambio=cambio)


def de_pesquisa_keyword_planner(d: Mapping[str, Any], *, moeda: str) -> Optional[tuple[Dinheiro, Dinheiro]]:
    """CPC de pesquisa (Keyword Planner / DataForSEO): intervalo [low, high] em micros. NUNCA autoriza verba."""
    lo, hi = d.get("low_top_of_page_bid_micros"), d.get("high_top_of_page_bid_micros")
    if lo is None or hi is None:
        return None
    return (Dinheiro(int(lo), moeda), Dinheiro(int(hi), moeda))


def de_joinads_campanha_dia(linhas: Sequence[Mapping[str, Any]], *, moeda: str, moeda_evidencia: str, disponivel_em: datetime) -> MedidaMonetaria:
    """Soma earnings JoinAds (micros) de dias com valor. Moeda vem ATESTADA por padrão (a API não declara)."""
    com_valor = [l for l in linhas if l.get("status") in _STATUS_COM_VALOR and l.get("earnings_micros") is not None]
    if not com_valor:
        return MedidaMonetaria(None, Evidencia.ABSENT, Evidencia(moeda_evidencia) if moeda_evidencia != "observed" else Evidencia.UNKNOWN, disponivel_em, "joinads")
    return MedidaMonetaria(Dinheiro(sum(int(l["earnings_micros"]) for l in com_valor), moeda), Evidencia.RECONCILED, Evidencia(moeda_evidencia), disponivel_em, "joinads")


def de_pautador_card(card: Mapping[str, Any], *, as_of: datetime, cpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None,
                     rpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None, autorizacao_ref: Optional[Autorizacao] = None,
                     perda_maxima_valor: Optional[Dinheiro] = None, perda_maxima_horizonte_dias: Optional[int] = None,
                     moeda: str) -> EntradaViabilidade:
    """Card sem histórico: só pesquisa e tolerância do owner. Custo/receita/cliques ficam AUSENTES.
    `moeda` é obrigatória (a moeda em que o card será operado; nunca BRL por padrão).
    A tolerância só existe com `autorizacao_ref` (emitida do lado VOLC); valor sem autorização é erro de contrato."""
    return EntradaViabilidade(
        candidato_id=str(card.get("id", "card")), vertical=card.get("vertical", ""), pais=card.get("pais", ""), fonte_custo="pesquisa", fonte_receita="pesquisa",
        as_of=as_of, janela=JanelaObservada(as_of.date().isoformat(), as_of.date().isoformat(), 0, 0, dias_custo_maduro=0, dias_receita_madura=0),
        cliques=MedidaContagem(None, Evidencia.ABSENT, as_of, "pautador"),
        custo=MedidaMonetaria(None, Evidencia.ABSENT, Evidencia.UNKNOWN, as_of, "pautador"),
        receita=MedidaMonetaria(None, Evidencia.ABSENT, Evidencia.UNKNOWN, as_of, "pautador"),
        cambio=Cambio(None, moeda, moeda, "nao_aplicavel", Evidencia.ABSENT), revshare=Taxa(None, Evidencia.UNKNOWN, "ausente"),
        imposto=Taxa(None, Evidencia.UNKNOWN, "ausente"),
        perda_maxima=PerdaMaxima(perda_maxima_valor, perda_maxima_horizonte_dias, autorizacao_ref), cpc_intervalo=cpc_intervalo, rpc_intervalo=rpc_intervalo,
    )


class BiaNaoPodeDefinirFinanceiro(PermissionError):
    """A Bia pediu para definir tolerância, câmbio, revshare, imposto, verba, lance — ou para passar uma autorização."""


_CAMPOS_FINANCEIROS = ("perda_maxima", "cambio", "revshare", "imposto", "tolerancia", "orcamento", "lance", "autorizacao")


@dataclass(frozen=True)
class RequisicaoBia:
    entrada: EntradaViabilidade
    motivo: str
    somente_leitura: bool = True
    pode_executar: bool = False


def requisicao_bia(entrada: EntradaViabilidade, pedido: Mapping[str, Any]) -> RequisicaoBia:
    """A Bia só pode pedir a avaliação de uma entrada já montada pelo lado VOLC. Qualquer campo financeiro
    (ou uma autorização) no pedido é recusado por construção; a resposta nunca carrega capacidade de execução."""
    proibidos = [k for k in pedido if k in _CAMPOS_FINANCEIROS]
    if proibidos:
        raise BiaNaoPodeDefinirFinanceiro(f"campos financeiros no pedido da Bia: {proibidos}")
    return RequisicaoBia(entrada=entrada, motivo=str(pedido.get("motivo", "")))
