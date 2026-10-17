"""Custo marginal sobre pontos de `campaign_simulation` do Google Ads — offline, sem API.

Interpreta CPC_BID e BUDGET (ambos têm cliques e custo por ponto). Entre pontos adjacentes
calcula custo incremental, cliques incrementais, CPC marginal, conversões incrementais (se
houver) e contribuição marginal sob um RPC conservador. Nunca interpola fora da faixa
observada; nunca confunde CPC médio com marginal; curva não monotônica é recusada, ou
normalizada SÓ com `normalizar_nao_monotonica=True` e recibo dos pontos removidos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Optional, Union

from .contrato import COM_VALOR, PontoSimulacao, SimulacaoEntrada
from .economia import micros_de_fracao

TIPOS_SUPORTADOS = frozenset({"CPC_BID", "BUDGET"})


@dataclass(frozen=True)
class CurvaIndisponivel:
    motivo: str
    detalhe: str = ""

    def para_json(self) -> dict:
        return {"disponivel": False, "motivo": self.motivo, "detalhe": self.detalhe}


@dataclass(frozen=True)
class PontoAvaliado:
    modificacao_micros: int
    cliques: int
    custo_micros: int
    cpc_medio: Fraction
    contribuicao_media_micros: int  # cliques × rpc_cons − custo (visão "média", que engana)
    conversoes: Optional[Decimal]


@dataclass(frozen=True)
class Segmento:
    de_micros: int
    para_micros: int
    cliques_incrementais: int
    custo_incremental_micros: int
    cpc_marginal: Fraction
    contribuicao_marginal_micros: int
    conversoes_incrementais: Optional[Decimal]
    sustentavel: bool


@dataclass(frozen=True)
class Normalizacao:
    pontos_removidos: tuple[int, ...]
    motivo: str


@dataclass(frozen=True)
class FronteiraMarginal:
    tipo: str
    moeda: str
    rpc_conservador: Fraction
    pontos: tuple[PontoAvaliado, ...]
    segmentos: tuple[Segmento, ...]
    ultimo_ponto_sustentavel: Optional[PontoAvaliado]
    primeiro_ponto_destrutivo: Optional[PontoAvaliado]
    expansao_aceitavel_ate_modificacao: Optional[int]
    faixa_observada: tuple[int, int]
    extrapolacao_permitida: bool
    normalizacao: Optional[Normalizacao]
    moeda_original: Optional[str] = None   # moeda em que a simulação foi reportada (== moeda quando não houve conversão)
    conversao: Optional[dict] = None       # recibo da conversão explícita do custo (None = nenhuma)

    def para_json(self) -> dict:
        return {
            "disponivel": True, "tipo": self.tipo, "moeda": self.moeda, "moeda_original": self.moeda_original or self.moeda,
            "conversao": self.conversao, "rpc_conservador_micros": str(self.rpc_conservador),
            "pontos": [{"modificacao_micros": p.modificacao_micros, "cliques": p.cliques, "custo_micros": p.custo_micros,
                        "cpc_medio_micros": str(p.cpc_medio), "contribuicao_media_micros": p.contribuicao_media_micros,
                        "conversoes": None if p.conversoes is None else str(p.conversoes)} for p in self.pontos],
            "segmentos": [{"de_micros": s.de_micros, "para_micros": s.para_micros, "cliques_incrementais": s.cliques_incrementais,
                           "custo_incremental_micros": s.custo_incremental_micros, "cpc_marginal_micros": str(s.cpc_marginal),
                           "contribuicao_marginal_micros": s.contribuicao_marginal_micros,
                           "conversoes_incrementais": None if s.conversoes_incrementais is None else str(s.conversoes_incrementais),
                           "sustentavel": s.sustentavel} for s in self.segmentos],
            "ultimo_ponto_sustentavel_micros": None if self.ultimo_ponto_sustentavel is None else self.ultimo_ponto_sustentavel.modificacao_micros,
            "primeiro_ponto_destrutivo_micros": None if self.primeiro_ponto_destrutivo is None else self.primeiro_ponto_destrutivo.modificacao_micros,
            "expansao_aceitavel_ate_modificacao": self.expansao_aceitavel_ate_modificacao,
            "faixa_observada": list(self.faixa_observada), "extrapolacao_permitida": self.extrapolacao_permitida,
            "normalizacao": None if self.normalizacao is None else {"pontos_removidos": list(self.normalizacao.pontos_removidos), "motivo": self.normalizacao.motivo},
        }


def _validar(s: SimulacaoEntrada) -> Union[list[PontoSimulacao], CurvaIndisponivel]:
    if s.tipo not in TIPOS_SUPORTADOS:
        return CurvaIndisponivel("tipo_nao_suportado", f"tipo={s.tipo} estrategia={s.estrategia_lance}: sem curva clique×custo interpretável")
    faltando = [p.modificacao_micros for p in s.pontos if p.cliques is None or p.custo_micros is None]
    if faltando:
        return CurvaIndisponivel("campos_ausentes", f"pontos sem cliques/custo: {faltando}")
    for p in s.pontos:
        for nome in ("modificacao_micros", "cliques", "custo_micros"):
            v = getattr(p, nome)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                return CurvaIndisponivel("unidade_invalida", f"{nome}={v!r} precisa ser int >= 0 (micros/contagem)")
    pontos = sorted(s.pontos, key=lambda p: p.modificacao_micros)
    mods = [p.modificacao_micros for p in pontos]
    if len(set(mods)) != len(mods):
        dup = sorted({m for m in mods if mods.count(m) > 1})
        return CurvaIndisponivel("pontos_duplicados", f"modificação repetida: {dup}")
    if len(pontos) < 2:
        return CurvaIndisponivel("curva_insuficiente", f"{len(pontos)} ponto(s); são necessários >= 2")
    return pontos


def _nao_monotonicos(pontos: list[PontoSimulacao]) -> list[int]:
    """Pontos cujos cliques OU custo caem em relação ao ponto anterior aceito."""
    ruins: list[int] = []
    ultimo = pontos[0]
    for p in pontos[1:]:
        if p.cliques < ultimo.cliques or p.custo_micros < ultimo.custo_micros:  # type: ignore[operator]
            ruins.append(p.modificacao_micros)
        else:
            ultimo = p
    return ruins


def _converter_moeda(s: SimulacaoEntrada, pontos: list[PontoSimulacao], moeda: Optional[str]
                     ) -> Union[tuple[list[PontoSimulacao], str, Optional[dict]], CurvaIndisponivel]:
    """`moeda` é a moeda do RPC conservador (a do custo observado). Simulação em outra moeda só entra com
    `simulacao.cambio` (de=moeda da simulação, para=moeda) e a conversão do custo fica registrada; o lance
    (`modificacao_micros`) permanece na moeda da conta porque é a alavanca, não um valor comparado."""
    if moeda is None or s.moeda == moeda:
        return pontos, s.moeda, None
    c = getattr(s, "cambio", None)
    if c is None or c.taxa is None or c.evidencia not in COM_VALOR:
        return CurvaIndisponivel("moeda_incompativel", f"simulação em {s.moeda}, custo em {moeda}, sem câmbio na simulação")
    if c.de != s.moeda or c.para != moeda:
        return CurvaIndisponivel("moeda_incompativel", f"câmbio {c.de}->{c.para} não cobre {s.moeda}->{moeda}")
    taxa = Fraction(c.taxa)
    convertidos = [PontoSimulacao(p.modificacao_micros, p.cliques, micros_de_fracao(Fraction(p.custo_micros) * taxa), p.impressoes, p.conversoes)  # type: ignore[arg-type]
                   for p in pontos]
    recibo = {"de": s.moeda, "para": moeda, "taxa": str(c.taxa), "proveniencia": c.proveniencia, "evidencia": c.evidencia.value, "campos": ["custo_micros"]}
    return convertidos, moeda, recibo


def analisar_simulacao(s: Optional[SimulacaoEntrada], rpc_conservador: Fraction, *, normalizar_nao_monotonica: bool = False,
                       moeda: Optional[str] = None) -> Union[FronteiraMarginal, CurvaIndisponivel]:
    if s is None:
        return CurvaIndisponivel("simulacao_ausente", "nenhum ponto de campaign_simulation informado")
    v = _validar(s)
    if isinstance(v, CurvaIndisponivel):
        return v
    conv = _converter_moeda(s, v, moeda)
    if isinstance(conv, CurvaIndisponivel):
        return conv
    pontos, moeda_saida, conversao = conv
    normalizacao: Optional[Normalizacao] = None
    ruins = _nao_monotonicos(pontos)
    if ruins:
        if not normalizar_nao_monotonica:
            return CurvaIndisponivel("curva_nao_monotonica", f"cliques/custo caem em: {ruins}")
        pontos = [p for p in pontos if p.modificacao_micros not in ruins]
        normalizacao = Normalizacao(tuple(ruins), "pontos com queda de cliques/custo removidos a pedido explícito")
        if len(pontos) < 2:
            return CurvaIndisponivel("curva_insuficiente", "após normalização restou menos de 2 pontos")
    avaliados: list[PontoAvaliado] = []
    for p in pontos:
        cl, cu = int(p.cliques), int(p.custo_micros)  # type: ignore[arg-type]
        cpc_medio = Fraction(cu, cl) if cl > 0 else Fraction(0)
        contrib_media = int(Fraction(cl) * rpc_conservador) - cu
        avaliados.append(PontoAvaliado(p.modificacao_micros, cl, cu, cpc_medio, contrib_media, p.conversoes))
    segmentos: list[Segmento] = []
    for a, b in zip(avaliados, avaliados[1:]):
        dcl, dcu = b.cliques - a.cliques, b.custo_micros - a.custo_micros
        cpc_marg = Fraction(dcu, dcl) if dcl > 0 else (Fraction(0) if dcu == 0 else Fraction(dcu, 1))  # sem cliques extras e com custo extra: infinito prático
        contrib = int(Fraction(dcl) * rpc_conservador) - dcu
        dconv = None if (a.conversoes is None or b.conversoes is None) else (b.conversoes - a.conversoes)
        sustent = dcl > 0 and cpc_marg <= rpc_conservador
        segmentos.append(Segmento(a.modificacao_micros, b.modificacao_micros, dcl, dcu, cpc_marg, contrib, dconv, sustent))
    ultimo_sust: Optional[PontoAvaliado] = avaliados[0]
    primeiro_destr: Optional[PontoAvaliado] = None
    for seg, ponto in zip(segmentos, avaliados[1:]):
        if seg.sustentavel and primeiro_destr is None:
            ultimo_sust = ponto
        elif primeiro_destr is None:
            primeiro_destr = ponto
    # o primeiro ponto só é "sustentável" se o seu CPC médio couber no RPC; senão nem o piso é aceitável
    if avaliados[0].cpc_medio > rpc_conservador and ultimo_sust is avaliados[0]:
        ultimo_sust = None
        primeiro_destr = avaliados[0] if primeiro_destr is None else primeiro_destr
    return FronteiraMarginal(
        tipo=s.tipo, moeda=moeda_saida, rpc_conservador=rpc_conservador, pontos=tuple(avaliados), segmentos=tuple(segmentos),
        ultimo_ponto_sustentavel=ultimo_sust, primeiro_ponto_destrutivo=primeiro_destr,
        expansao_aceitavel_ate_modificacao=None if ultimo_sust is None else ultimo_sust.modificacao_micros,
        faixa_observada=(avaliados[0].modificacao_micros, avaliados[-1].modificacao_micros), extrapolacao_permitida=False,
        normalizacao=normalizacao, moeda_original=s.moeda, conversao=conversao,
    )
