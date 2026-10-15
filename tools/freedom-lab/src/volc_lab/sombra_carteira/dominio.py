"""Regra do motor shadow da carteira: reconcilia custo × receita no grão
campanha × dia e devolve uma direção que NÃO é executada.

É a regra da prova Senac (`volc_lab/prova_vertical.py`) com duas trocas que a
prova não podia fazer:

1. a receita chega já em BRL pelo câmbio versionado do W12; não há câmbio fixo
   aqui. Dia cuja cotação está `defasada` ou `sem_cotacao` não tem receita em
   BRL: fica sem dado, nunca zero;
2. a atribuição segue a v17_04: só a linha de custo não segmentada; GAM sem o
   roteador de atribuição não reconcilia; GAM e JoinAds no mesmo dia são
   sobreposição (a mesma impressão contada duas vezes), não soma.

Puro: sem I/O, sem relógio, sem rede. Mesma entrada, mesma saída.
Os limiares são PARÂMETROS DO LABORATÓRIO, não a política do dono.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Optional, Sequence

from volc_lab.brokers.valor_operacional import RecomendacaoShadow
from volc_lab.sombra_carteira.portas import ContratoQuebrado, CustoDia, ReceitaObservada

PARAMETROS_PADRAO: dict[str, float] = {
    "janela_dias": 30,               # dias de custo considerados até o as_of
    "dias_imaturos": 3,              # conector D-1 reescreve 3 dias
    "janela_recente_dias": 5,        # recorte recente dentro da janela madura
    "min_cliques_maduros": 200,
    "estresse_receita": 2.0,         # e se a receita madura dobrar
    "estresse_cambio": 1.5,          # e se o câmbio estiver 50% subestimado
    "roas_equilibrio": 1.0,
    "roas_aumentar": 1.5,
    "max_custo_sem_receita": 0.10,   # fração do custo maduro sem receita que ainda permite decidir
    "max_dias_sem_custo": 0.10,      # fração dos dias maduros com custo não lido (NULL) que ainda permite decidir
}

# Estados do dia. Só `reconciliado` entra em ROAS; o resto é ausência nomeada.
RECONCILIADO = "reconciliado"
ESTADOS_DIA = (
    RECONCILIADO,
    "sem_custo",                 # há receita e não há linha de custo
    "custo_ausente",             # linha de custo com custo_micros nulo
    "moeda_custo_nao_brl",       # custo em outra moeda: não é comparável com receita em BRL
    "janela_aberta",             # o Google ainda pode reescrever o custo do dia
    "receita_ausente",           # nenhuma receita observada para a campanha no dia
    "receita_parcial",           # algum componente (domínio) sem valor
    "sem_cotacao",               # câmbio inexistente para o dia (W12)
    "cambio_defasado",           # câmbio mais velho que o limite do resolvedor (W12)
    "gam_sem_atribuicao",        # GAM sem o roteador: pode ser adset Meta
    "sobreposicao_gam_joinads",  # duas fontes no mesmo dia: soma contaria duas vezes
)

# estado_dado do resultado: o que a tela mostra antes da direção.
COMPLETO = "completo"
SEM_DADO = "sem_dado"
AMOSTRA_INSUFICIENTE = "amostra_insuficiente"


@dataclass(frozen=True)
class DiaReconciliado:
    data: date
    custo_brl: Optional[float]
    cliques: Optional[int]
    receita_brl: Optional[float]
    receita_moeda_origem: Optional[float]
    cambio_modos: tuple[str, ...]
    fontes_receita: tuple[str, ...]
    valor_conversao_google: Optional[float]
    custo_origem: Optional[str]      # origem_janela do fato: D0, D-1 ou backfill (recoleta)
    maduro: bool
    estado: str


@dataclass(frozen=True)
class Avaliacao:
    campanha: str
    as_of: date
    corte_maturidade: date
    dias: tuple[DiaReconciliado, ...]
    janela_madura: dict[str, Any]
    janela_madura_recente: dict[str, Any]
    fracao_custo_maduro_sem_receita: Optional[float]
    custo_maduro_por_estado: dict[str, float]
    estado_dado: str
    motivo_estado_dado: Optional[str]
    roas_sob_estresse: Optional[float]
    recomendacao: RecomendacaoShadow
    valor_conversao_google_total: Optional[float]
    parametros: dict[str, float] = field(default_factory=dict)


def _soma(valores: Iterable[Optional[float]]) -> Optional[float]:
    """Soma que respeita ausência: se algum é None, o total é None."""
    total = 0.0
    for v in valores:
        if v is None:
            return None
        total += v
    return total


def _estado_receita(receitas: Sequence[ReceitaObservada]) -> tuple[str, Optional[float], Optional[float]]:
    """Estado da receita de UM dia de UMA campanha: (estado, brl, moeda_origem)."""
    if not receitas:
        return "receita_ausente", None, None
    fontes = {r.fonte for r in receitas}
    if fontes == {"gam", "joinads"}:
        return "sobreposicao_gam_joinads", None, None
    if fontes == {"gam"}:
        return "gam_sem_atribuicao", None, None
    modos = {r.cambio_modo for r in receitas}
    if "sem_cotacao" in modos:
        return "sem_cotacao", None, _soma(r.receita for r in receitas)
    if "defasada" in modos:
        return "cambio_defasado", None, _soma(r.receita for r in receitas)
    com_valor = [r for r in receitas if r.receita is not None]
    if not com_valor:
        return "receita_ausente", None, None
    if len(com_valor) < len(receitas):
        return "receita_parcial", None, None
    brl = _soma(r.receita_brl for r in receitas)
    if brl is None:  # o contrato garante BRL nos modos válidos; defesa
        return "sem_cotacao", None, _soma(r.receita for r in receitas)
    return RECONCILIADO, brl, _soma(r.receita for r in receitas)


def reconciliar(
    campanha: str,
    custos: Sequence[CustoDia],
    receitas: Sequence[ReceitaObservada],
    as_of: date,
    parametros: Optional[dict[str, float]] = None,
) -> tuple[list[DiaReconciliado], date]:
    """Junta custo e receita da campanha por dia, dentro da janela até `as_of`."""
    p = {**PARAMETROS_PADRAO, **(parametros or {})}
    inicio = as_of - timedelta(days=int(p["janela_dias"]))
    corte = as_of - timedelta(days=int(p["dias_imaturos"]))

    por_dia_custo: dict[date, CustoDia] = {}
    for c in custos:
        if c.campaign_id != campanha:
            raise ContratoQuebrado(f"custo da campanha {c.campaign_id} entregue para {campanha}")
        if c.segmentado or not (inicio <= c.metric_date <= as_of):
            continue
        if c.metric_date in por_dia_custo:
            # A chave do fato é (conta, campanha, data, segments_hash); duas
            # linhas não segmentadas no mesmo dia somariam o custo duas vezes.
            raise ContratoQuebrado(f"custo repetido para {campanha} em {c.metric_date}")
        por_dia_custo[c.metric_date] = c

    por_dia_receita: dict[date, list[ReceitaObservada]] = {}
    vistas: set[tuple[str, date, str]] = set()
    for r in receitas:
        if r.campanha != campanha:
            raise ContratoQuebrado(f"receita da campanha {r.campanha} entregue para {campanha}")
        # A leitura vigente tem UMA linha por chave (fonte, dia, componente). Duas
        # são versões do diário ou página deslocada, e somá-las contaria a mesma
        # receita duas vezes (a guarda que a prova Senac tinha).
        chave = (r.fonte, r.data_referencia, r.componente)
        if chave in vistas:
            raise ContratoQuebrado(f"receita repetida para {campanha} em {r.data_referencia} ({r.fonte}/{r.componente})")
        vistas.add(chave)
        if not (inicio <= r.data_referencia <= as_of):
            continue
        por_dia_receita.setdefault(r.data_referencia, []).append(r)

    dias: list[DiaReconciliado] = []
    for d in sorted(set(por_dia_custo) | set(por_dia_receita)):
        custo = por_dia_custo.get(d)
        rec = sorted(por_dia_receita.get(d, []), key=lambda r: (r.fonte, r.componente))
        estado_rec, brl, origem = _estado_receita(rec)
        if custo is None:
            estado = "sem_custo"
        elif custo.custo_micros is None:
            estado = "custo_ausente"
        elif custo.currency_code != "BRL":
            estado = "moeda_custo_nao_brl"
        elif not custo.janela_fechada:
            estado = "janela_aberta"
        else:
            estado = estado_rec
        # Maturidade é do CALENDÁRIO. Um dia antigo que só tem D0 (janela aberta,
        # D-1 falhou) é maduro e entra na conta como custo sem receita
        # reconciliada; tirá-lo da maturidade o faria sumir da guarda de fração.
        maduro = d < corte
        dias.append(DiaReconciliado(
            data=d,
            custo_brl=None if custo is None or custo.custo_micros is None
            else round(custo.custo_micros / 1e6, 2),
            cliques=None if custo is None else custo.cliques,
            # Receita em BRL só sai quando o dia inteiro reconcilia.
            # Sem arredondar aqui: a janela soma o valor cheio, como a prova Senac.
            receita_brl=brl,
            receita_moeda_origem=origem,
            cambio_modos=tuple(sorted({r.cambio_modo for r in rec})),
            fontes_receita=tuple(sorted({r.fonte for r in rec})),
            valor_conversao_google=None if custo is None else custo.valor_conversoes,
            custo_origem=None if custo is None else custo.origem_janela,
            maduro=maduro,
            estado=estado,
        ))
    return dias, corte


def janela(dias: Sequence[DiaReconciliado], inicio: Optional[date] = None) -> dict[str, Any]:
    m = [d for d in dias if d.maduro and d.estado == RECONCILIADO and (inicio is None or d.data >= inicio)]
    if not m:  # janela sem dia reconciliado: ausência, não zero
        return {"dias": 0, "custo_brl": None, "receita_brl": None, "cliques": None, "roas": None,
                "cpc": None, "rpc": None, "contribuicao_bruta": None}
    custo = sum(d.custo_brl or 0.0 for d in m)
    receita = sum(d.receita_brl or 0.0 for d in m)
    cliques_lidos = [d.cliques for d in m]
    cliques = None if any(c is None for c in cliques_lidos) else sum(cliques_lidos)
    return {"dias": len(m), "custo_brl": round(custo, 2), "receita_brl": round(receita, 2),
            "cliques": cliques, "roas": round(receita / custo, 4) if custo else None,
            "cpc": round(custo / cliques, 4) if cliques else None,
            "rpc": round(receita / cliques, 4) if cliques else None,
            "contribuicao_bruta": round(receita - custo, 2)}


def avaliar(
    campanha: str,
    custos: Sequence[CustoDia],
    receitas: Sequence[ReceitaObservada],
    as_of: date,
    parametros: Optional[dict[str, float]] = None,
    lacunas_fixas: Sequence[str] = (),
) -> Avaliacao:
    p = {**PARAMETROS_PADRAO, **(parametros or {})}
    dias, corte = reconciliar(campanha, custos, receitas, as_of, p)
    madura = janela(dias)
    recente = janela(dias, inicio=corte - timedelta(days=int(p["janela_recente_dias"])))

    maduros = [d for d in dias if d.maduro]
    custo_maduro = sum(d.custo_brl or 0.0 for d in maduros)
    por_estado: dict[str, float] = {}
    for d in maduros:
        if d.estado != RECONCILIADO and (d.custo_brl or 0.0) > 0:
            por_estado[d.estado] = round(por_estado.get(d.estado, 0.0) + (d.custo_brl or 0.0), 2)
    sem_receita = sum(por_estado.values())
    fracao = round(sem_receita / custo_maduro, 4) if custo_maduro else None

    lacunas = list(lacunas_fixas)
    contagem: dict[str, list[str]] = {}
    for d in maduros:
        if d.estado != RECONCILIADO:
            contagem.setdefault(d.estado, []).append(d.data.isoformat())
    for estado in sorted(contagem):
        datas = contagem[estado]
        lacunas.append(f"dias maduros em {estado} (ausentes, não zero): {len(datas)} "
                       f"({datas[0]} a {datas[-1]})")
    valor_google = [d.valor_conversao_google for d in dias if d.valor_conversao_google is not None]

    # Custo NULL não pesa na fração (não se sabe quanto foi): conta-se por dia.
    dias_com_custo = [d for d in maduros if d.estado != "sem_custo"]
    sem_custo_lido = [d for d in dias_com_custo if d.custo_brl is None]
    fracao_dias_sem_custo = (len(sem_custo_lido) / len(dias_com_custo)) if dias_com_custo else None

    estresse: Optional[float] = None
    if fracao_dias_sem_custo is not None and fracao_dias_sem_custo > p["max_dias_sem_custo"]:
        estado_dado = SEM_DADO
        motivo = (f"{len(sem_custo_lido)} de {len(dias_com_custo)} dias maduros sem custo lido "
                  f"(limite {p['max_dias_sem_custo']:.0%})")
    elif not custo_maduro:
        estado_dado = SEM_DADO
        motivo = "sem custo maduro na janela: não há o que reconciliar"
    elif fracao is not None and fracao > p["max_custo_sem_receita"]:
        estado_dado = SEM_DADO
        piores = ", ".join(f"{e} R$ {v:.2f}" for e, v in sorted(por_estado.items(), key=lambda x: -x[1]))
        motivo = (f"{fracao:.0%} do custo maduro não tem receita reconciliada em BRL "
                  f"(limite {p['max_custo_sem_receita']:.0%}): {piores}")
    elif madura["roas"] is None:
        estado_dado = SEM_DADO
        motivo = "nenhum dia maduro reconciliado com custo positivo"
    elif madura["cliques"] is None:
        estado_dado = SEM_DADO
        motivo = "cliques não lidos em dia maduro reconciliado"
    elif madura["cliques"] < p["min_cliques_maduros"]:
        estado_dado = AMOSTRA_INSUFICIENTE
        motivo = f"cliques maduros {madura['cliques']} < {int(p['min_cliques_maduros'])}"
    else:
        estado_dado = COMPLETO
        motivo = None

    if estado_dado != COMPLETO:
        rec = RecomendacaoShadow(campanha, "evidencia_insuficiente", (motivo or "sem dado",), None, tuple(lacunas))
    else:
        roas = madura["roas"]
        estresse = round(roas * p["estresse_receita"] * p["estresse_cambio"], 4)
        motivos = [f"ROAS maduro {roas:.3f} em {madura['cliques']} cliques e {madura['dias']} dias",
                   f"ROAS sob estresse (receita ×{p['estresse_receita']}, câmbio ×{p['estresse_cambio']}) = {estresse:.3f}"]
        if estresse < p["roas_equilibrio"]:
            direcao = "pausar"
            motivos.append("mesmo no estresse a campanha não paga o próprio custo")
        elif roas < p["roas_equilibrio"]:
            direcao = "reduzir"
        elif roas >= p["roas_aumentar"]:
            direcao = "aumentar"
        else:
            direcao = "manter"
        # Nenhum valor monetário sugerido: o motor não calcula verba nem lance.
        rec = RecomendacaoShadow(campanha, direcao, tuple(motivos), None, tuple(lacunas))

    return Avaliacao(
        campanha=campanha, as_of=as_of, corte_maturidade=corte, dias=tuple(dias),
        janela_madura=madura, janela_madura_recente=recente,
        fracao_custo_maduro_sem_receita=fracao, custo_maduro_por_estado=por_estado,
        estado_dado=estado_dado, motivo_estado_dado=motivo, roas_sob_estresse=estresse,
        recomendacao=rec,
        valor_conversao_google_total=round(sum(valor_google), 2) if valor_google else None,
        parametros=p,
    )
