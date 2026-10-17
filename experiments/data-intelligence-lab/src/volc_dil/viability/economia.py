"""Kernel de fronteira econômica: funções puras sobre `EntradaViabilidade`.

Toda quantia é `Dinheiro` (micros inteiros). Toda razão é `Fraction` exata. Nenhum float.
Fatores de conservadorismo são PREMISSAS declaradas (nome + valor) e aparecem na saída;
não são calibrações. Ausência propaga como `Indisponivel`, nunca como zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Optional, Union

from volc_dil.contracts import Dinheiro

from .contrato import COM_VALOR, REALIZADA, EntradaViabilidade, Evidencia


@dataclass(frozen=True)
class Indisponivel:
    motivo: str
    detalhe: str = ""


def micros_de_fracao(fr: Fraction) -> int:
    """Fraction → int com arredondamento half-even, SÓ com aritmética inteira (sem Decimal, sem float).

    `divmod` em Python arredonda o quociente para −∞ e deixa o resto em [0, d); por isso a mesma
    comparação `2·resto` vs `denominador` decide o empate para positivos e negativos.
    """
    n, d = fr.numerator, fr.denominator
    q, r = divmod(n, d)
    dobro = 2 * r
    if dobro < d:
        return q
    if dobro > d:
        return q + 1
    return q if q % 2 == 0 else q + 1


def _micros_x(micros: int, fator: Union[Fraction, Decimal]) -> int:
    f = Fraction(fator) if isinstance(fator, Decimal) else fator
    return micros_de_fracao(Fraction(micros) * f)


# Premissas conservadoras (nome → fator). Declaradas, não calibradas.
PREMISSAS = {
    "receita_realizada_margem": Fraction(9, 10),     # receita reconciliada/observada: −10%
    "moeda_atestada_desconto": Fraction(85, 100),    # moeda só atestada: −15%
    "cambio_estimado_desconto": Fraction(85, 100),   # câmbio literal/estimado: −15%
    "cambio_atestado_desconto": Fraction(95, 100),   # câmbio atestado: −5%
    "receita_imatura_desconto": Fraction(7, 10),     # receita imatura: −30% e NÃO realizada
    "receita_projetada_desconto": Fraction(1, 2),    # projeção: −50% e NÃO realizada
    "receita_estimada_desconto": Fraction(6, 10),    # estimativa: −40% e NÃO realizada
    "custo_reconciliacao_margem": Fraction(105, 100),  # custo D0→D-1 pode subir: +5%
    "rpc_otimista_uplift": Fraction(12, 10),         # releituras D+1..D+7 podem subir: +20%
}


@dataclass(frozen=True)
class ReceitaComparavel:
    valor: Dinheiro                 # na moeda do custo, líquida do que foi possível aplicar
    evidencia: Evidencia
    moeda_evidencia: Evidencia
    cambio_evidencia: Optional[Evidencia]
    limitacoes: tuple[str, ...]
    aplicados: tuple[str, ...]


def _negativos(e: EntradaViabilidade) -> Optional[Indisponivel]:
    """Custo, receita, cliques e visitas observados nunca são negativos. O contrato (V2) recusa na
    construção; o kernel recusa de novo, defensivamente, para que a contribuição (que PODE ser
    negativa) jamais nasça de uma entrada negativa."""
    for nome in ("custo", "receita"):
        m = getattr(e, nome)
        if m.valor is not None and m.valor.micros < 0:
            return Indisponivel("valor_negativo", f"{nome}={m.valor.micros} micros")
    for nome in ("cliques", "visitas"):
        m = getattr(e, nome)
        if m is not None and m.valor is not None and m.valor < 0:
            return Indisponivel("valor_negativo", f"{nome}={m.valor}")
    return None


def receita_liquida_comparavel(e: EntradaViabilidade) -> Union[ReceitaComparavel, Indisponivel]:
    r = e.receita
    if r.valor is None:
        return Indisponivel(f"receita_{r.evidencia.value}")
    if e.custo.valor is None:
        return Indisponivel(f"custo_{e.custo.evidencia.value}")
    if r.moeda_evidencia is Evidencia.INVALID:
        return Indisponivel("moeda_receita_invalid")
    neg = _negativos(e)
    if neg is not None:
        return neg
    limitacoes: list[str] = []
    aplicados: list[str] = []
    micros = r.valor.micros
    cambio_ev: Optional[Evidencia] = None
    if r.valor.moeda != e.custo.valor.moeda:
        c = e.cambio
        if c.taxa is None or c.evidencia not in COM_VALOR:
            return Indisponivel("cambio_ausente", f"{r.valor.moeda}->{e.custo.valor.moeda}")
        if c.de != r.valor.moeda or c.para != e.custo.valor.moeda:
            return Indisponivel("cambio_par_incompativel", f"{c.de}->{c.para}")
        micros = _micros_x(micros, c.taxa)
        cambio_ev = c.evidencia
        aplicados.append(f"cambio:{c.proveniencia}:{c.taxa}")
        if c.evidencia is not Evidencia.OBSERVED:
            limitacoes.append(f"cambio_{c.evidencia.value}")
    if e.revshare.valor is not None:
        micros = _micros_x(micros, e.revshare.valor)
        aplicados.append(f"revshare:{e.revshare.proveniencia}:{e.revshare.valor}")
        if e.revshare.evidencia is not Evidencia.OBSERVED:
            limitacoes.append(f"revshare_{e.revshare.evidencia.value}")
    else:
        limitacoes.append("revshare_desconhecido_nao_aplicado")
    if e.imposto.valor is not None:
        micros = _micros_x(micros, Fraction(1) - Fraction(e.imposto.valor))
        aplicados.append(f"imposto:{e.imposto.proveniencia}:{e.imposto.valor}")
    else:
        limitacoes.append("imposto_desconhecido_nao_aplicado")
    if r.moeda_evidencia is not Evidencia.OBSERVED:
        limitacoes.append(f"moeda_receita_{r.moeda_evidencia.value}")
    if r.evidencia not in REALIZADA:
        limitacoes.append(f"receita_{r.evidencia.value}")
    return ReceitaComparavel(Dinheiro(micros, e.custo.valor.moeda), r.evidencia, r.moeda_evidencia, cambio_ev,
                             tuple(limitacoes), tuple(aplicados))


@dataclass(frozen=True)
class EconomiaObservada:
    """Grão da decisão é o CLIQUE: custo e receita são divididos pelos mesmos cliques, logo o break-even
    por clique compara CPC com RPC por clique. RPC por visita é SÓ reportado (nunca entra no break-even);
    sem visitas (None) ou com visitas == 0 ele fica indisponível com motivo e NUNCA cai para cliques."""
    moeda: str
    cliques: int
    visitas_elegiveis: Optional[int]      # None = sem medida de visitas; 0 é valor observado válido
    custo: Dinheiro
    receita_liquida: Dinheiro
    cpc: Fraction                         # micros por clique
    rpc: Fraction                         # micros por clique (== rpc_por_clique; grão do break-even)
    contribuicao: Dinheiro
    break_even_cpc: Fraction              # = rpc por clique (RPC conservador é aplicado no envelope)
    receita_evidencia: Evidencia
    moeda_evidencia: Evidencia
    cambio_evidencia: Optional[Evidencia]
    limitacoes: tuple[str, ...]
    aplicados: tuple[str, ...]
    rpc_por_visita: Optional[Fraction] = None            # só reportado
    rpc_por_visita_indisponivel: Optional[str] = None    # "visitas_ausente" | "visitas_zero"

    @property
    def rpc_por_clique(self) -> Fraction:
        return self.rpc


def calcular_economia(e: EntradaViabilidade) -> Union[EconomiaObservada, Indisponivel]:
    if e.cliques.valor is None:
        return Indisponivel(f"cliques_{e.cliques.evidencia.value}")
    if e.cliques.valor == 0:
        return Indisponivel("cliques_zero")
    if e.custo.valor is None:
        return Indisponivel(f"custo_{e.custo.evidencia.value}")
    neg = _negativos(e)
    if neg is not None:
        return neg
    rc = receita_liquida_comparavel(e)
    if isinstance(rc, Indisponivel):
        return rc
    cpc = Fraction(e.custo.valor.micros, e.cliques.valor)
    rpc = Fraction(rc.valor.micros, e.cliques.valor)
    visitas: Optional[int] = None if (e.visitas is None or e.visitas.valor is None) else e.visitas.valor
    rpc_visita: Optional[Fraction] = None
    rpc_visita_motivo: Optional[str] = None
    if visitas is None:
        rpc_visita_motivo = "visitas_ausente"
    elif visitas == 0:
        rpc_visita_motivo = "visitas_zero"
    else:
        rpc_visita = Fraction(rc.valor.micros, visitas)
    return EconomiaObservada(
        moeda=e.custo.valor.moeda, cliques=e.cliques.valor, visitas_elegiveis=visitas, custo=e.custo.valor,
        receita_liquida=rc.valor, cpc=cpc, rpc=rpc, contribuicao=rc.valor - e.custo.valor, break_even_cpc=rpc,
        receita_evidencia=rc.evidencia, moeda_evidencia=rc.moeda_evidencia, cambio_evidencia=rc.cambio_evidencia,
        limitacoes=rc.limitacoes, aplicados=rc.aplicados, rpc_por_visita=rpc_visita, rpc_por_visita_indisponivel=rpc_visita_motivo,
    )


@dataclass(frozen=True)
class Envelope:
    moeda: str
    cpc_central: Fraction
    cpc_conservador: Fraction
    rpc_central: Fraction
    rpc_conservador: Fraction
    rpc_otimista: Fraction
    contribuicao_central: Dinheiro
    contribuicao_conservadora: Dinheiro
    receita_realizada: bool
    premissas: tuple[tuple[str, str], ...]   # (nome, valor) aplicados
    limitacoes: tuple[str, ...]
    economia: EconomiaObservada
    custo_conservador: Optional[Dinheiro] = None     # custo × margem de reconciliação
    receita_conservadora: Optional[Dinheiro] = None  # receita líquida × fatores de evidência

    def perda_liquida_conservadora(self) -> Dinheiro:
        """max(0, custo_cons − receita_cons): perda líquida sob as premissas; nunca o gasto bruto."""
        return Dinheiro(max(0, -self.contribuicao_conservadora.micros), self.moeda)


def _fator_receita(eco: EconomiaObservada) -> tuple[Fraction, list[tuple[str, str]], list[str], bool]:
    f = Fraction(1)
    prem: list[tuple[str, str]] = []
    lim: list[str] = list(eco.limitacoes)
    realizada = eco.receita_evidencia in REALIZADA

    def aplica(nome: str) -> None:
        nonlocal f
        f *= PREMISSAS[nome]
        prem.append((nome, str(PREMISSAS[nome])))

    if eco.receita_evidencia in REALIZADA:
        aplica("receita_realizada_margem")
    elif eco.receita_evidencia is Evidencia.IMMATURE:
        aplica("receita_imatura_desconto"); lim.append("receita_imatura")
    elif eco.receita_evidencia is Evidencia.PROJECTED:
        aplica("receita_projetada_desconto"); lim.append("receita_projected")
    elif eco.receita_evidencia is Evidencia.ESTIMATED:
        aplica("receita_estimada_desconto"); lim.append("receita_estimated")
    elif eco.receita_evidencia is Evidencia.ATTESTED:
        aplica("moeda_atestada_desconto"); lim.append("receita_attested")
    if eco.moeda_evidencia is Evidencia.ATTESTED:
        aplica("moeda_atestada_desconto")
    elif eco.moeda_evidencia in (Evidencia.UNKNOWN, Evidencia.ESTIMATED):
        aplica("moeda_atestada_desconto"); lim.append(f"moeda_receita_{eco.moeda_evidencia.value}")
    if eco.cambio_evidencia is not None:
        if eco.cambio_evidencia is Evidencia.ATTESTED:
            aplica("cambio_atestado_desconto")
        elif eco.cambio_evidencia is not Evidencia.OBSERVED:
            aplica("cambio_estimado_desconto")
    return f, prem, sorted(set(lim)), realizada


def envelope_conservador(e: EntradaViabilidade) -> Union[Envelope, Indisponivel]:
    eco = calcular_economia(e)
    if isinstance(eco, Indisponivel):
        return eco
    f_rev, prem, lim, realizada = _fator_receita(eco)
    f_custo = PREMISSAS["custo_reconciliacao_margem"]
    prem.append(("custo_reconciliacao_margem", str(f_custo)))
    f_otim = PREMISSAS["rpc_otimista_uplift"]
    prem.append(("rpc_otimista_uplift", str(f_otim)))
    rpc_cons = eco.rpc * f_rev
    cpc_cons = eco.cpc * f_custo
    rec_cons = Dinheiro(_micros_x(eco.receita_liquida.micros, f_rev), eco.moeda)
    custo_cons = Dinheiro(_micros_x(eco.custo.micros, f_custo), eco.moeda)
    return Envelope(
        moeda=eco.moeda, cpc_central=eco.cpc, cpc_conservador=cpc_cons, rpc_central=eco.rpc, rpc_conservador=rpc_cons,
        rpc_otimista=eco.rpc * f_otim, contribuicao_central=eco.contribuicao, contribuicao_conservadora=rec_cons - custo_cons,
        receita_realizada=realizada, premissas=tuple(prem), limitacoes=tuple(lim), economia=eco,
        custo_conservador=custo_cons, receita_conservadora=rec_cons,
    )


@dataclass(frozen=True)
class Fronteira:
    moeda: str
    cpc_central: Fraction
    rpc_conservador: Fraction
    required_rpc: Fraction                       # RPC necessário ao CPC atual para contribuição zero
    required_rpc_multiplier: Optional[Fraction]  # None quando rpc_conservador == 0
    queda_cpc_necessaria: Fraction               # 0..1
    folga_cpc: Fraction                          # micros de folga por clique quando favorável
    distancia_economica: Fraction                # (cpc − rpc_cons)/cpc; <= 0 favorável
    iso_contribuicao_zero: tuple[tuple[Fraction, Fraction], ...]  # pares (cpc, rpc) com contribuição zero
    envelope: Envelope


def fronteira(e: EntradaViabilidade) -> Union[Fronteira, Indisponivel]:
    env = envelope_conservador(e)
    if isinstance(env, Indisponivel):
        return env
    cpc, rpc = env.cpc_central, env.rpc_conservador
    mult = None if rpc == 0 else cpc / rpc
    queda = max(Fraction(0), Fraction(1) - (rpc / cpc)) if cpc > 0 else Fraction(0)
    folga = max(Fraction(0), rpc - cpc)
    dist = (cpc - rpc) / cpc if cpc > 0 else Fraction(0)
    iso = tuple((rpc * k, rpc * k) for k in (Fraction(1), Fraction(3, 2), Fraction(2), Fraction(3))) if rpc > 0 else ()
    return Fronteira(env.moeda, cpc, rpc, cpc, mult, queda, folga, dist, iso, env)


@dataclass(frozen=True)
class Cenario:
    nome: str
    contribuicao: Dinheiro
    rpc: Fraction
    premissas: tuple[str, ...]


def _receita_cenario(e: EntradaViabilidade, eco: EconomiaObservada, f_receita: Fraction, f_cambio: Fraction,
                     revshare: Optional[Fraction]) -> int:
    """Recalcula a receita comparável sob multiplicadores explícitos. Mantém as regras de ausência."""
    r = e.receita.valor
    if r is None:
        raise ValueError("cenário de estresse sem receita: ausência não vira zero")
    micros = _micros_x(r.micros, f_receita)
    if r.moeda != eco.moeda:
        micros = _micros_x(micros, Fraction(e.cambio.taxa) * f_cambio)  # type: ignore[arg-type]
    rs = revshare if revshare is not None else (Fraction(e.revshare.valor) if e.revshare.valor is not None else None)
    if rs is not None:
        micros = _micros_x(micros, rs)
    if e.imposto.valor is not None:
        micros = _micros_x(micros, Fraction(1) - Fraction(e.imposto.valor))
    return micros


def estresse(e: EntradaViabilidade) -> Union[list[Cenario], Indisponivel]:
    eco = calcular_economia(e)
    if isinstance(eco, Indisponivel):
        return eco
    if e.receita.valor is None:
        return Indisponivel(f"receita_{e.receita.evidencia.value}", "estresse exige receita com valor")
    converte = e.receita.valor.moeda != eco.moeda
    cenarios = [
        ("base", Fraction(1), Fraction(1), None, ("sem_multiplicadores",)),
        ("receita_x2", Fraction(2), Fraction(1), None, ("receita×2",)),
        ("cambio_x1.5", Fraction(1), Fraction(3, 2) if converte else Fraction(1), None, ("cambio×1.5" if converte else "cambio_nao_aplicavel",)),
        ("revshare_0.7", Fraction(1), Fraction(1), Fraction(7, 10), ("revshare=0.7",)),
        ("maturacao_uplift_1.3", Fraction(13, 10), Fraction(1), None, ("maturacao×1.3",)),
        ("combinado_favoravel", Fraction(2) * Fraction(13, 10), Fraction(3, 2) if converte else Fraction(1), None, ("receita×2", "cambio×1.5", "maturacao×1.3")),
    ]
    out: list[Cenario] = []
    for nome, fr, fc, rs, prem in cenarios:
        micros = _receita_cenario(e, eco, fr, fc, rs)
        out.append(Cenario(nome, Dinheiro(micros - eco.custo.micros, eco.moeda), Fraction(micros, eco.cliques), prem))
    return out
