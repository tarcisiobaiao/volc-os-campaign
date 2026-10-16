"""Junção campanha × dia de custo (Google Ads) × tráfego (sensor) × receita (JoinAds).

Garantias:
- null ≠ zero: cada medida carrega `EstadoMedida`; ausência de linha é `ausente`, perda conhecida
  é `nao_atribuivel`, nunca 0;
- receita sem chave (ou com chave não registrada) fica num balde explícito e NÃO é distribuída;
- cobertura: fração de sessões com UTM resolvida e fração da receita com chave, como `Fraction`
  exata, ou `None` quando o denominador não existe (nunca 0 % inventado);
- grão: só campanha × dia. Qualquer outro grão passa por `graos.exigir_grao` e é recusado com
  erro tipado quando as fontes não o sustentam.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from fractions import Fraction
from typing import Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from volc_dil.contracts.money import Dinheiro, MoedasDiferentes
from volc_dil.contracts.vocab import COM_VALOR, GRAVIDADE, EstadoMedida, MetodoAtribuicao

from .chave_campanha import MotivoRecusa, OrigemValor, interpretar_campanha_da_sessao, interpretar_chave_campanha
from .graos import Confianca, Fonte, Grao, GraoTempo, exigir_grao
from .normalizacao import UtmSessao
from .resolvedor import RegistroCampanhas, Resolucao

FUSO_PADRAO = "America/Sao_Paulo"  # fuso da conta Google Ads (attribution-map@043c77f5)


# ---------------------------------------------------------------- entradas

@dataclass(frozen=True)
class CustoCampanhaDia:
    customer_id: str
    campaign_id: str
    dia: date  # dia civil no fuso da conta
    custo: Optional[Dinheiro]
    cliques: Optional[int]
    estado: EstadoMedida = EstadoMedida.MEDIDO


@dataclass(frozen=True)
class EventoSensorReady:
    """Uma linha `raw_events` com `event_name = 'volc_sensor_ready'` (o único evento com UTM)."""

    sid: str
    pid: str
    ts: datetime  # timestamptz (UTC)
    utm: UtmSessao
    bot: bool = False


@dataclass(frozen=True)
class ReceitaChaveDia:
    """Linha `/key-value` da JoinAds (ou `joinads_observation` v2 com grain campaign_*_day)."""

    dia: date
    dominio: str
    custom_key: Optional[str]
    custom_value: Optional[str]
    receita: Optional[Dinheiro]
    estado: EstadoMedida = EstadoMedida.MEDIDO


@dataclass(frozen=True)
class ReceitaDominioDia:
    """Total `/earnings` por domínio × dia: denominador da cobertura de receita."""

    dia: date
    dominio: str
    receita: Optional[Dinheiro]
    estado: EstadoMedida = EstadoMedida.MEDIDO


# ---------------------------------------------------------------- saídas

@dataclass(frozen=True)
class Medida:
    estado: EstadoMedida
    valor: object = None  # Dinheiro | int | None
    motivo: str = ""

    def __post_init__(self) -> None:
        if (self.valor is None) == (self.estado in COM_VALOR):
            raise ValueError(f"estado {self.estado.value} incoerente com valor {self.valor!r}")


@dataclass(frozen=True)
class LinhaCampanhaDia:
    customer_id: str
    campaign_id: str
    dia: date
    custo: Medida
    cliques: Medida
    sessoes: Medida
    receita: Medida
    metodo_receita: MetodoAtribuicao
    confianca_sessoes: Optional[Confianca] = None  # a mais fraca entre as sessões contadas


@dataclass(frozen=True)
class Cobertura:
    sessoes_total: int
    sessoes_bot_excluidas: int
    sessoes_resolvidas: int
    sessoes_pagas: int
    sessoes_pagas_resolvidas: int
    sessoes_perdidas_pelo_sensor: int
    sessoes_multicampanha: int
    fracao_sessoes_resolvidas: Optional[Fraction]
    fracao_sessoes_pagas_resolvidas: Optional[Fraction]
    receita_total: Optional[Dinheiro]
    receita_com_chave: Optional[Dinheiro]
    receita_sem_chave: Optional[Dinheiro]
    fracao_receita_com_chave: Optional[Fraction]
    denominador_receita: str  # 'earnings_dominio_dia' | 'soma_key_value' | 'indisponivel'
    fuso_receita_verificado: bool
    avisos: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoJuncao:
    linhas: tuple[LinhaCampanhaDia, ...]
    cobertura: Cobertura
    receita_nao_atribuida: tuple[tuple[ReceitaChaveDia, str], ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- sessões

@dataclass(frozen=True)
class SessaoResolvida:
    sid: str
    dia: date
    paga: bool
    bot: bool
    resolucao: Resolucao
    perdida_pelo_sensor: bool
    multicampanha: bool


def sessoes_de_eventos(eventos: Iterable[EventoSensorReady], registro: RegistroCampanhas,
                       fuso: str = FUSO_PADRAO) -> list[SessaoResolvida]:
    """Agrupa `volc_sensor_ready` por `sid`. Dia = 1º evento no `fuso`; campanha = única entre as
    páginas da sessão (duas campanhas distintas na mesma aba → `nao_atribuivel`)."""
    tz = ZoneInfo(fuso)
    por_sid: dict[str, list[EventoSensorReady]] = defaultdict(list)
    for e in eventos:
        if e.ts.tzinfo is None:
            raise ValueError("ts sem fuso: raw_events.ts é timestamptz")
        por_sid[e.sid].append(e)
    out = []
    for sid, evs in sorted(por_sid.items()):
        evs.sort(key=lambda e: e.ts)
        dia = evs[0].ts.astimezone(tz).date()
        paga = any(e.utm.paid == 1 for e in evs)
        bot = any(e.bot for e in evs)
        resolucoes: dict[tuple, Resolucao] = {}
        perdida = False
        for e in evs:
            ch = interpretar_campanha_da_sessao(e.utm.campaign, paid=e.utm.paid,
                                                source=e.utm.source, medium=e.utm.medium)
            if ch.recusa is MotivoRecusa.DESCARTADO_PELO_SENSOR:
                perdida = True
            r = registro.resolver(ch, dia)
            if r.atribuivel:
                resolucoes[(r.customer_id, r.campaign_id)] = r
        multi = len(resolucoes) > 1
        if multi:
            res = Resolucao(Confianca.NAO_ATRIBUIVEL, "multiplas_campanhas_na_sessao")
        elif resolucoes:
            res = next(iter(resolucoes.values()))
        else:
            res = Resolucao(Confianca.NAO_ATRIBUIVEL,
                            "descartado_pelo_sensor" if perdida else "sem_utm_de_campanha")
        out.append(SessaoResolvida(sid, dia, paga, bot, res, perdida and not resolucoes, multi))
    return out


# ---------------------------------------------------------------- utilitários

def _soma(valores: list[Dinheiro]) -> Dinheiro:
    moedas = {v.moeda for v in valores}
    if len(moedas) > 1:
        raise MoedasDiferentes(" × ".join(sorted(moedas)))
    total = valores[0]
    for v in valores[1:]:
        total = total + v
    return total


def _pior(estados: Iterable[EstadoMedida]) -> Optional[EstadoMedida]:
    estados = set(estados)
    for e in GRAVIDADE:
        if e in estados:
            return e
    return None


def _medida_dinheiro(itens: list[tuple[Optional[Dinheiro], EstadoMedida]], motivo_ausente: str) -> Medida:
    if not itens:
        return Medida(EstadoMedida.AUSENTE, None, motivo_ausente)
    pior = _pior(e for _, e in itens if e not in COM_VALOR)
    if pior is not None:
        return Medida(pior, None, "ao menos uma linha sem valor; a pior causa vence")
    valores = [v for v, _ in itens]
    if any(v is None for v in valores):
        raise ValueError("linha com estado medido e valor None")
    total = _soma(valores)
    # Zero só é "confirmado" quando a fonte o declarou assim; um 0 "medido" (ex.: DEFAULT 0 do
    # legado joinads_metrics) continua "medido" — o resolvedor não promove ausência a zero.
    estado = EstadoMedida.ZERO_CONFIRMADO if all(e is EstadoMedida.ZERO_CONFIRMADO for _, e in itens) \
        else EstadoMedida.MEDIDO
    return Medida(estado, total)


def _fracao(num: int, den: int) -> Optional[Fraction]:
    return None if den == 0 else Fraction(num, den)


# ---------------------------------------------------------------- junção

def juntar_campanha_dia(
    custos: Iterable[CustoCampanhaDia],
    eventos_sensor: Iterable[EventoSensorReady],
    receitas_chave: Iterable[ReceitaChaveDia],
    registro: RegistroCampanhas,
    *,
    receitas_dominio: Optional[Iterable[ReceitaDominioDia]] = None,
    fuso_sensor: str = FUSO_PADRAO,
    fuso_receita_verificado: bool = False,
    excluir_bots: bool = True,
    grao: Grao = Grao.CAMPANHA,
    tempo: GraoTempo = GraoTempo.DIA,
) -> ResultadoJuncao:
    """Custo × tráfego × receita por campanha × dia, com cobertura e sem rateio."""
    if (grao, tempo) != (Grao.CAMPANHA, GraoTempo.DIA):
        # Recusa tipada: o par econômico (custo × receita) decide o grão máximo.
        exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, grao, tempo)
        raise NotImplementedError(f"junção implementada só em campanha×dia; pedido {grao.value}×{tempo.value}")
    exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, Grao.CAMPANHA, GraoTempo.DIA)

    avisos: list[str] = []
    if not fuso_receita_verificado:
        avisos.append("fuso de fechamento do dia JoinAds não verificado (src/sql/joinads/README.md 'Ainda em aberto')")

    # custo
    custo_por: dict[tuple, list[CustoCampanhaDia]] = defaultdict(list)
    for c in custos:
        custo_por[(c.customer_id, c.campaign_id, c.dia)].append(c)

    # tráfego
    sessoes = sessoes_de_eventos(eventos_sensor, registro, fuso_sensor)
    bots = [s for s in sessoes if s.bot]
    validas = [s for s in sessoes if not (excluir_bots and s.bot)]
    sess_por: dict[tuple, int] = defaultdict(int)
    conf_por: dict[tuple, set] = defaultdict(set)
    perdas_por_dia: dict[date, int] = defaultdict(int)
    dias_com_sensor: set[date] = set()
    for s in validas:
        dias_com_sensor.add(s.dia)
        if s.resolucao.atribuivel:
            k = (s.resolucao.customer_id, s.resolucao.campaign_id, s.dia)
            sess_por[k] += 1
            conf_por[k].add(s.resolucao.confianca)
        if s.perdida_pelo_sensor or s.multicampanha:
            perdas_por_dia[s.dia] += 1

    # receita
    receita_por: dict[tuple, list[ReceitaChaveDia]] = defaultdict(list)
    nao_atribuida: list[tuple[ReceitaChaveDia, str]] = []
    for r in receitas_chave:
        ch = interpretar_chave_campanha(r.custom_value, OrigemValor.JOINADS, custom_key=r.custom_key)
        res = registro.resolver(ch, r.dia)
        if res.confianca is Confianca.DETERMINISTICA:
            receita_por[(res.customer_id, res.campaign_id, r.dia)].append(r)
        elif res.atribuivel:  # probabilística: tráfego aceita, receita não
            nao_atribuida.append((r, f"receita_exige_chave_deterministica:{res.motivo}"))
        else:
            nao_atribuida.append((r, res.motivo))

    linhas = []
    for chave in sorted(set(custo_por) | set(sess_por) | set(receita_por)):
        conta, cid, dia = chave
        cs = custo_por.get(chave, [])
        custo = _medida_dinheiro([(c.custo, c.estado) for c in cs], "sem linha de custo Google Ads")
        if not cs:
            cliques = Medida(EstadoMedida.AUSENTE, None, "sem linha de custo Google Ads")
        elif _pior(c.estado for c in cs if c.estado not in COM_VALOR):
            cliques = Medida(_pior(c.estado for c in cs if c.estado not in COM_VALOR), None)
        else:
            n = sum(c.cliques for c in cs if c.cliques is not None)
            cliques = Medida(EstadoMedida.ZERO_CONFIRMADO if n == 0 else EstadoMedida.MEDIDO, n)
        n_sess = sess_por.get(chave, 0)
        if n_sess:
            sess = Medida(EstadoMedida.MEDIDO, n_sess)
        elif perdas_por_dia.get(dia):
            sess = Medida(EstadoMedida.NAO_ATRIBUIVEL, None,
                          f"{perdas_por_dia[dia]} sessão(ões) paga(s) do dia sem campanha legível "
                          "(sensor descarta id numérico ou sessão multicampanha)")
        elif dia in dias_com_sensor:
            sess = Medida(EstadoMedida.ZERO_CONFIRMADO, 0,
                          "zero no universo observado pelo sensor (sem consentimento/GPC fica fora)")
        else:
            sess = Medida(EstadoMedida.AUSENTE, None, "nenhum evento do sensor no dia")
        rs = receita_por.get(chave, [])
        receita = _medida_dinheiro([(r.receita, r.estado) for r in rs],
                                   "sem linha JoinAds para a campanha no dia")
        confs = conf_por.get(chave, set())
        conf = (Confianca.PROBABILISTICA if Confianca.PROBABILISTICA in confs
                else Confianca.DETERMINISTICA if confs else None)
        linhas.append(LinhaCampanhaDia(conta, cid, dia, custo, cliques, sess, receita,
                                       MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE if rs
                                       else MetodoAtribuicao.UNRECONCILED, conf))

    # cobertura de receita
    com_chave_vals = [r.receita for rs in receita_por.values() for r in rs
                      if r.estado in COM_VALOR and r.receita is not None]
    sem_chave_vals = [r.receita for r, _ in nao_atribuida if r.estado in COM_VALOR and r.receita is not None]
    com_chave = _soma(com_chave_vals) if com_chave_vals else None
    denominador = "indisponivel"
    total: Optional[Dinheiro] = None
    if receitas_dominio is not None:
        rd = list(receitas_dominio)
        if rd and all(r.estado in COM_VALOR and r.receita is not None for r in rd):
            total = _soma([r.receita for r in rd])
            denominador = "earnings_dominio_dia"
        elif rd:
            avisos.append("earnings por domínio com dia sem valor: denominador indisponível")
    elif com_chave_vals or sem_chave_vals:
        total = _soma(com_chave_vals + sem_chave_vals)
        denominador = "soma_key_value"
        avisos.append("sem /earnings: cobertura de receita medida só dentro do /key-value")
    sem_chave: Optional[Dinheiro] = None
    frac_rec: Optional[Fraction] = None
    if total is not None:
        base = com_chave if com_chave is not None else Dinheiro(0, total.moeda)
        if base.moeda != total.moeda:
            raise MoedasDiferentes(f"{base.moeda} × {total.moeda}")
        sem_chave = total - base
        if sem_chave.micros < 0:
            avisos.append("receita com chave excede o total de earnings: revisar janela/fuso/domínio")
        frac_rec = None if total.micros == 0 else Fraction(base.micros, total.micros)

    pagas = [s for s in validas if s.paga]
    cobertura = Cobertura(
        sessoes_total=len(validas),
        sessoes_bot_excluidas=len(bots) if excluir_bots else 0,
        sessoes_resolvidas=sum(1 for s in validas if s.resolucao.atribuivel),
        sessoes_pagas=len(pagas),
        sessoes_pagas_resolvidas=sum(1 for s in pagas if s.resolucao.atribuivel),
        sessoes_perdidas_pelo_sensor=sum(1 for s in validas if s.perdida_pelo_sensor),
        sessoes_multicampanha=sum(1 for s in validas if s.multicampanha),
        fracao_sessoes_resolvidas=_fracao(sum(1 for s in validas if s.resolucao.atribuivel), len(validas)),
        fracao_sessoes_pagas_resolvidas=_fracao(sum(1 for s in pagas if s.resolucao.atribuivel), len(pagas)),
        receita_total=total,
        receita_com_chave=com_chave,
        receita_sem_chave=sem_chave,
        fracao_receita_com_chave=frac_rec,
        denominador_receita=denominador,
        fuso_receita_verificado=fuso_receita_verificado,
        avisos=tuple(avisos),
    )
    return ResultadoJuncao(tuple(linhas), cobertura, tuple(nao_atribuida))


def para_json(resultado: ResultadoJuncao) -> dict:
    """Serialização estável (sem float) para recibos."""
    def med(m: Medida):
        v = m.valor.para_json() if isinstance(m.valor, Dinheiro) else m.valor
        return {"estado": m.estado.value, "valor": v, "motivo": m.motivo}

    def fr(f: Optional[Fraction]):
        return None if f is None else f"{f.numerator}/{f.denominator}"

    def din(d: Optional[Dinheiro]):
        return None if d is None else d.para_json()

    c = resultado.cobertura
    return {
        "linhas": [{"customer_id": l.customer_id, "campaign_id": l.campaign_id, "dia": l.dia.isoformat(),
                    "custo": med(l.custo), "cliques": med(l.cliques), "sessoes": med(l.sessoes),
                    "receita": med(l.receita), "metodo_receita": l.metodo_receita.value,
                    "confianca_sessoes": l.confianca_sessoes.value if l.confianca_sessoes else None}
                   for l in resultado.linhas],
        "cobertura": {
            "sessoes_total": c.sessoes_total, "sessoes_bot_excluidas": c.sessoes_bot_excluidas,
            "sessoes_resolvidas": c.sessoes_resolvidas, "sessoes_pagas": c.sessoes_pagas,
            "sessoes_pagas_resolvidas": c.sessoes_pagas_resolvidas,
            "sessoes_perdidas_pelo_sensor": c.sessoes_perdidas_pelo_sensor,
            "sessoes_multicampanha": c.sessoes_multicampanha,
            "fracao_sessoes_resolvidas": fr(c.fracao_sessoes_resolvidas),
            "fracao_sessoes_pagas_resolvidas": fr(c.fracao_sessoes_pagas_resolvidas),
            "receita_total": din(c.receita_total), "receita_com_chave": din(c.receita_com_chave),
            "receita_sem_chave": din(c.receita_sem_chave),
            "fracao_receita_com_chave": fr(c.fracao_receita_com_chave),
            "denominador_receita": c.denominador_receita,
            "fuso_receita_verificado": c.fuso_receita_verificado, "avisos": list(c.avisos),
        },
        "receita_nao_atribuida": [{"dia": r.dia.isoformat(), "custom_key": r.custom_key,
                                   "custom_value": r.custom_value, "motivo": m,
                                   "receita": din(r.receita), "estado": r.estado.value}
                                  for r, m in resultado.receita_nao_atribuida],
    }
