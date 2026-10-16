"""Junção campanha × dia de custo (Google Ads) × tráfego (sensor) × receita (JoinAds).

Contrato de entrada (R1-F5): a junção recebe um ESTADO `as_of`, não um fluxo de leituras.
- `as_of` é obrigatório e tem fuso; nada com `disponivel_em`/`ts` posterior entra (`FuturoNaJuncao`).
- Cada linha de receita declara identidade completa: `endpoint`, `grao`, `dimensao`, `dia`, `dominio`,
  `custom_key`, `custom_value`, e `disponivel_em`. É a versão vigente em `as_of` daquela identidade
  (o chamador resolve as versões antes, ex. `joinads_observation_latest` ou `as_of` da thread A).
- Um único grão de receita por chamada; grão misto (`GraoMistoNaReceita`) e identidade repetida
  (`LinhaDuplicada`) são recusados — somar dois cortes do mesmo dinheiro dobraria a receita.
  O mesmo vale para custo (conta × campanha × dia) e earnings (domínio × dia).

Garantias:
- null ≠ zero: cada medida carrega `EstadoMedida`; ausência é `ausente`/`nao_coletado`, perda conhecida
  é `nao_atribuivel`, nunca 0 (cliques `None` incluídos, R1-F6);
- tráfego segue `graos.MATRIZ` (R1-F6): sessões por campanha × dia só saem se a capacidade
  Google Ads × Sensor permitir — hoje `nao_atribuivel`; com `trafego_campanha_comprovado=True` (condição
  `requer` da matriz provada) vale a potencial. Zero de sessão exige sensor visto no host da campanha;
- receita sem chave fica num balde explícito e NÃO é distribuída;
- cobertura de receita compara universos iguais (R1-F19): só domínio × dia com earnings E /key-value
  coletado entra no denominador; o resto é reportado à parte, com aviso.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from fractions import Fraction
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from volc_dil.contracts.money import Dinheiro, MoedasDiferentes
from volc_dil.contracts.vocab import COM_VALOR, GRAVIDADE, EstadoMedida, MetodoAtribuicao

from .chave_campanha import MotivoRecusa, OrigemValor, interpretar_campanha_da_sessao, interpretar_chave_campanha
from .graos import Confianca, Fonte, Grao, GraoTempo, capacidade, exigir_grao
from .normalizacao import UtmSessao
from .resolvedor import RegistroCampanhas, Resolucao, normalizar_host

FUSO_PADRAO = "America/Sao_Paulo"  # fuso da conta Google Ads (attribution-map@043c77f5)

#: Grãos de receita que somam para campanha × dia, com o número de dimensões extras de cada um
#: (`joinads_v2_normalize.js:187-233` em `wip/historico-joinads-20261015`; legado `/key-value` = campaign_day).
GRAOS_RECEITA_CAMPANHA = {"campaign_day": 0, "campaign_adunit_day": 1, "campaign_country_adunit_day": 2}


# ---------------------------------------------------------------- erros de contrato

class ContratoDeEntrada(ValueError):
    """Entrada que não é um estado `as_of` bem formado."""


class LinhaDuplicada(ContratoDeEntrada):
    """Mesma identidade de linha duas vezes: o chamador passou fluxo/versões, não estado."""


class GraoMistoNaReceita(ContratoDeEntrada):
    """Dois grãos/endpoints de receita na mesma junção: cortes diferentes do mesmo dinheiro."""


class FuturoNaJuncao(ContratoDeEntrada):
    """Linha disponível depois do `as_of` pedido."""


# ---------------------------------------------------------------- entradas

@dataclass(frozen=True)
class CustoCampanhaDia:
    customer_id: str
    campaign_id: str
    dia: date  # dia civil no fuso da conta
    custo: Optional[Dinheiro]
    cliques: Optional[int]
    estado: EstadoMedida = EstadoMedida.MEDIDO
    disponivel_em: Optional[datetime] = None


@dataclass(frozen=True)
class EventoSensorReady:
    """Uma linha `raw_events` com `event_name = 'volc_sensor_ready'` (o único evento com UTM)."""

    sid: str
    pid: str
    ts: datetime  # timestamptz (UTC)
    utm: UtmSessao
    bot: bool = False
    host: str = ""  # raw_events.host (minúsculas, pode ter www.)


@dataclass(frozen=True)
class ReceitaChaveDia:
    """Versão vigente em `as_of` de UMA linha key-value da JoinAds.

    Identidade: (endpoint, grao, dia, dominio, custom_key, custom_value, dimensao). Ex.: v2
    `key_value_campaign_adunit`/`campaign_adunit_day`/dimensao=(ad_unit,); legado `/key-value`/`campaign_day`/().
    """

    dia: date
    dominio: str
    endpoint: str
    grao: str
    custom_key: Optional[str]
    custom_value: Optional[str]
    receita: Optional[Dinheiro]
    estado: EstadoMedida = EstadoMedida.MEDIDO
    dimensao: tuple[str, ...] = ()
    disponivel_em: Optional[datetime] = None

    def identidade(self) -> tuple:
        return (self.endpoint, self.grao, self.dia, normalizar_host(self.dominio),
                (self.custom_key or "").strip(), (self.custom_value or "").strip(), tuple(self.dimensao))


@dataclass(frozen=True)
class ReceitaDominioDia:
    """Total `/earnings` por domínio × dia: denominador da cobertura de receita."""

    dia: date
    dominio: str
    receita: Optional[Dinheiro]
    estado: EstadoMedida = EstadoMedida.MEDIDO
    disponivel_em: Optional[datetime] = None


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
    receita_total: Optional[Dinheiro]  # earnings no universo comparável
    receita_com_chave: Optional[Dinheiro]
    receita_sem_chave: Optional[Dinheiro]
    fracao_receita_com_chave: Optional[Fraction]
    denominador_receita: str  # 'earnings_dominio_dia' | 'soma_key_value' | 'indisponivel'
    fuso_receita_verificado: bool
    receita_earnings_sem_kv: Optional[Dinheiro] = None  # domínio × dia sem /key-value coletado
    receita_kv_sem_earnings: Optional[Dinheiro] = None  # receita com chave fora do universo de earnings
    capacidade_trafego: str = ""  # confiança efetiva de Google Ads × Sensor em campanha × dia
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
    host: str = ""


def sessoes_de_eventos(eventos: Iterable[EventoSensorReady], registro: RegistroCampanhas,
                       fuso: str = FUSO_PADRAO) -> list[SessaoResolvida]:
    """Agrupa `volc_sensor_ready` por `sid`. Dia e host = 1º evento (dia no `fuso`); campanha = única
    entre as páginas da sessão (duas campanhas distintas na mesma aba → `nao_atribuivel`)."""
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
        out.append(SessaoResolvida(sid, dia, paga, bot, res, perdida and not resolucoes, multi,
                                   normalizar_host(evs[0].host)))
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
        raise ContratoDeEntrada("linha com estado medido e valor None")
    total = _soma(valores)
    # Zero só é "confirmado" quando a fonte o declarou assim; um 0 "medido" (ex.: DEFAULT 0 do
    # legado joinads_metrics) continua "medido" — o resolvedor não promove ausência a zero.
    estado = EstadoMedida.ZERO_CONFIRMADO if all(e is EstadoMedida.ZERO_CONFIRMADO for _, e in itens) \
        else EstadoMedida.MEDIDO
    return Medida(estado, total)


def _fracao(num: int, den: int) -> Optional[Fraction]:
    return None if den == 0 else Fraction(num, den)


def _exigir_disponivel(instante: Optional[datetime], as_of: datetime, oque: str, obrigatorio: bool) -> None:
    if instante is None:
        if obrigatorio:
            raise ContratoDeEntrada(f"{oque} sem disponivel_em: a junção recebe estado as_of, não fluxo")
        return
    if instante.tzinfo is None:
        raise ContratoDeEntrada(f"{oque}: disponivel_em sem fuso")
    if instante > as_of:
        raise FuturoNaJuncao(f"{oque}: disponível em {instante.isoformat()} > as_of {as_of.isoformat()}")


def _validar_receitas(receitas: list[ReceitaChaveDia], as_of: datetime) -> Optional[tuple[str, str]]:
    familias = {(r.endpoint, r.grao) for r in receitas}
    if len(familias) > 1:
        raise GraoMistoNaReceita("grãos/endpoints de receita misturados: " +
                                 ", ".join(f"{e}/{g}" for e, g in sorted(familias)))
    vistos: set = set()
    for r in receitas:
        if r.grao not in GRAOS_RECEITA_CAMPANHA:
            raise ContratoDeEntrada(f"grão de receita {r.grao!r} não soma para campanha × dia")
        if len(r.dimensao) != GRAOS_RECEITA_CAMPANHA[r.grao]:
            raise ContratoDeEntrada(f"dimensão {r.dimensao!r} incoerente com o grão {r.grao}")
        _exigir_disponivel(r.disponivel_em, as_of, "receita key-value", obrigatorio=True)
        k = r.identidade()
        if k in vistos:
            raise LinhaDuplicada(f"identidade de receita repetida: {k}")
        vistos.add(k)
    return next(iter(familias)) if familias else None


# ---------------------------------------------------------------- junção

def juntar_campanha_dia(
    custos: Iterable[CustoCampanhaDia],
    eventos_sensor: Iterable[EventoSensorReady],
    receitas_chave: Iterable[ReceitaChaveDia],
    registro: RegistroCampanhas,
    *,
    as_of: datetime,
    receitas_dominio: Optional[Iterable[ReceitaDominioDia]] = None,
    dominios_dia_kv_coletados: Optional[set] = None,
    fuso_sensor: str = FUSO_PADRAO,
    fuso_receita_verificado: bool = False,
    excluir_bots: bool = True,
    trafego_campanha_comprovado: bool = False,
    grao: Grao = Grao.CAMPANHA,
    tempo: GraoTempo = GraoTempo.DIA,
) -> ResultadoJuncao:
    """Custo × tráfego × receita por campanha × dia, com cobertura e sem rateio (contrato no módulo)."""
    if (grao, tempo) != (Grao.CAMPANHA, GraoTempo.DIA):
        # Recusa tipada: o par econômico (custo × receita) decide o grão máximo.
        exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, grao, tempo)
        raise NotImplementedError(f"junção implementada só em campanha×dia; pedido {grao.value}×{tempo.value}")
    exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, Grao.CAMPANHA, GraoTempo.DIA)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ContratoDeEntrada("as_of precisa ser datetime com fuso")

    avisos: list[str] = []
    if not fuso_receita_verificado:
        avisos.append("fuso de fechamento do dia JoinAds não verificado (src/sql/joinads/README.md 'Ainda em aberto')")

    # custo — um estado por conta × campanha × dia
    custo_por: dict[tuple, CustoCampanhaDia] = {}
    for c in custos:
        _exigir_disponivel(c.disponivel_em, as_of, "custo", obrigatorio=False)
        k = (c.customer_id, c.campaign_id, c.dia)
        if k in custo_por:
            raise LinhaDuplicada(f"custo repetido para {k}")
        custo_por[k] = c

    # tráfego
    eventos = list(eventos_sensor)
    for e in eventos:
        if e.ts.tzinfo is not None and e.ts > as_of:
            raise FuturoNaJuncao(f"evento do sensor em {e.ts.isoformat()} > as_of")
    cap = capacidade(Fonte.GOOGLE_ADS, Fonte.SENSOR, Grao.CAMPANHA, GraoTempo.DIA)
    conf_trafego = cap.potencial if trafego_campanha_comprovado else cap.hoje
    sessoes = sessoes_de_eventos(eventos, registro, fuso_sensor)
    bots = [s for s in sessoes if s.bot]
    validas = [s for s in sessoes if not (excluir_bots and s.bot)]
    sess_por: dict[tuple, int] = defaultdict(int)
    conf_por: dict[tuple, set] = defaultdict(set)
    perdas_por: dict[tuple, int] = defaultdict(int)  # (dia, host)
    hosts_com_sensor: set[tuple] = set()  # (dia, host)
    for s in validas:
        hosts_com_sensor.add((s.dia, s.host))
        if s.resolucao.atribuivel:
            k = (s.resolucao.customer_id, s.resolucao.campaign_id, s.dia)
            sess_por[k] += 1
            conf_por[k].add(s.resolucao.confianca)
        if s.perdida_pelo_sensor or s.multicampanha:
            perdas_por[(s.dia, s.host)] += 1

    # receita — estado as_of de um único grão
    receitas = list(receitas_chave)
    _validar_receitas(receitas, as_of)
    receita_por: dict[tuple, list[ReceitaChaveDia]] = defaultdict(list)
    nao_atribuida: list[tuple[ReceitaChaveDia, str]] = []
    for r in receitas:
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
        c = custo_por.get(chave)
        custo = _medida_dinheiro([(c.custo, c.estado)] if c else [], "sem linha de custo Google Ads")
        if c is None:
            cliques = Medida(EstadoMedida.AUSENTE, None, "sem linha de custo Google Ads")
        elif c.estado not in COM_VALOR:
            cliques = Medida(c.estado, None, "linha de custo sem valor")
        elif c.cliques is None:
            cliques = Medida(EstadoMedida.NAO_COLETADO, None, "cliques não informados na linha de custo")
        else:
            cliques = Medida(EstadoMedida.MEDIDO, c.cliques)
        sess = _medida_sessoes(chave, conf_trafego, cap.chave, cap.requer, registro, sess_por,
                               perdas_por, hosts_com_sensor)
        rs = receita_por.get(chave, [])
        receita = _medida_dinheiro([(r.receita, r.estado) for r in rs],
                                   "sem linha JoinAds para a campanha no dia")
        confs = conf_por.get(chave, set()) if sess.estado in COM_VALOR else set()
        conf = (Confianca.PROBABILISTICA if Confianca.PROBABILISTICA in confs
                else Confianca.DETERMINISTICA if confs else None)
        linhas.append(LinhaCampanhaDia(conta, cid, dia, custo, cliques, sess, receita,
                                       MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE if rs
                                       else MetodoAtribuicao.UNRECONCILED, conf))

    rec = _cobertura_receita(receitas, receita_por, nao_atribuida, receitas_dominio, dominios_dia_kv_coletados,
                             as_of, avisos)
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
        fuso_receita_verificado=fuso_receita_verificado,
        capacidade_trafego=conf_trafego.value,
        avisos=tuple(avisos),
        **rec,
    )
    return ResultadoJuncao(tuple(linhas), cobertura, tuple(nao_atribuida))


def _medida_sessoes(chave, conf_trafego, cap_chave, cap_requer, registro, sess_por, perdas_por,
                    hosts_com_sensor) -> Medida:
    conta, cid, dia = chave
    if conf_trafego is Confianca.NAO_ATRIBUIVEL:
        return Medida(EstadoMedida.NAO_ATRIBUIVEL, None,
                      f"matriz Google Ads × Sensor em campanha × dia = nao_atribuivel ({cap_chave}); requer: {cap_requer}")
    n = sess_por.get(chave, 0)
    if n:
        return Medida(EstadoMedida.MEDIDO, n)
    campanhas = [c for c in registro.por_id(cid, dia) if c.customer_id == conta]
    hosts = frozenset().union(*(c.hosts_normalizados for c in campanhas)) if campanhas else frozenset()
    perdas = sum(v for (d, h), v in perdas_por.items() if d == dia and (not hosts or h in hosts))
    if perdas:
        return Medida(EstadoMedida.NAO_ATRIBUIVEL, None,
                      f"{perdas} sessão(ões) paga(s) sem campanha legível no dia (id descartado ou multicampanha)")
    if not hosts:
        return Medida(EstadoMedida.AUSENTE, None, "host da campanha não declarado: zero não comprovável")
    if any((dia, h) in hosts_com_sensor for h in hosts):
        return Medida(EstadoMedida.ZERO_CONFIRMADO, 0,
                      "zero no universo observado pelo sensor no host da campanha (sem consentimento/GPC fica fora)")
    return Medida(EstadoMedida.AUSENTE, None, "nenhum evento do sensor no host da campanha no dia")


def _cobertura_receita(receitas, receita_por, nao_atribuida, receitas_dominio, dominios_dia_kv_coletados,
                       as_of, avisos) -> dict:
    """Denominador comparável: domínio × dia com earnings E /key-value coletado (R1-F19)."""
    def chave_dd(dia, dominio):
        return (dia, normalizar_host(dominio))

    com_valor = [(r, chave_dd(r.dia, r.dominio)) for rs in receita_por.values() for r in rs
                 if r.estado in COM_VALOR and r.receita is not None]
    sem_valor_kv = [(r, chave_dd(r.dia, r.dominio)) for r, _ in nao_atribuida
                    if r.estado in COM_VALOR and r.receita is not None]
    universo_kv = ({chave_dd(d, h) for d, h in dominios_dia_kv_coletados} if dominios_dia_kv_coletados is not None
                   else {chave_dd(r.dia, r.dominio) for r in receitas})
    out = dict(receita_total=None, receita_com_chave=None, receita_sem_chave=None, fracao_receita_com_chave=None,
               denominador_receita="indisponivel", receita_earnings_sem_kv=None, receita_kv_sem_earnings=None)

    if receitas_dominio is None:
        if com_valor or sem_valor_kv:
            total = _soma([r.receita for r, _ in com_valor + sem_valor_kv])
            base = _soma([r.receita for r, _ in com_valor]) if com_valor else Dinheiro(0, total.moeda)
            out.update(receita_total=total, receita_com_chave=base if com_valor else None,
                       receita_sem_chave=total - base, denominador_receita="soma_key_value",
                       fracao_receita_com_chave=None if total.micros == 0 else Fraction(base.micros, total.micros))
            avisos.append("sem /earnings: cobertura de receita medida só dentro do /key-value")
        elif com_valor:
            out["receita_com_chave"] = _soma([r.receita for r, _ in com_valor])
        return out

    earnings: dict[tuple, ReceitaDominioDia] = {}
    for e in receitas_dominio:
        _exigir_disponivel(e.disponivel_em, as_of, "earnings", obrigatorio=False)
        k = chave_dd(e.dia, e.dominio)
        if k in earnings:
            raise LinhaDuplicada(f"earnings repetido para {k}")
        earnings[k] = e
    if any(e.estado not in COM_VALOR or e.receita is None for e in earnings.values()):
        avisos.append("earnings por domínio com dia sem valor: denominador indisponível")
        return out
    universo = set(earnings) & universo_kv
    fora_kv = [earnings[k].receita for k in sorted(set(earnings) - universo_kv)]
    if fora_kv:
        out["receita_earnings_sem_kv"] = _soma(fora_kv)
        avisos.append(f"{len(fora_kv)} domínio(s) × dia com earnings sem /key-value coletado: fora do denominador")
    kv_fora = [r.receita for r, k in com_valor if k not in earnings]
    if kv_fora:
        out["receita_kv_sem_earnings"] = _soma(kv_fora)
        avisos.append("receita com chave em domínio × dia sem /earnings: fora do numerador")
    if not universo:
        return out
    total = _soma([earnings[k].receita for k in sorted(universo)])
    dentro = [r.receita for r, k in com_valor if k in universo]
    base = _soma(dentro) if dentro else Dinheiro(0, total.moeda)
    if base.moeda != total.moeda:
        raise MoedasDiferentes(f"{base.moeda} × {total.moeda}")
    sem = total - base
    if sem.micros < 0:
        avisos.append("receita com chave excede o total de earnings: revisar janela/fuso/domínio")
    out.update(receita_total=total, receita_com_chave=base if dentro else None, receita_sem_chave=sem,
               denominador_receita="earnings_dominio_dia",
               fracao_receita_com_chave=None if total.micros == 0 else Fraction(base.micros, total.micros))
    return out


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
            "receita_earnings_sem_kv": din(c.receita_earnings_sem_kv),
            "receita_kv_sem_earnings": din(c.receita_kv_sem_earnings),
            "capacidade_trafego": c.capacidade_trafego,
            "fuso_receita_verificado": c.fuso_receita_verificado, "avisos": list(c.avisos),
        },
        "receita_nao_atribuida": [{"dia": r.dia.isoformat(), "endpoint": r.endpoint, "grao": r.grao,
                                   "custom_key": r.custom_key, "custom_value": r.custom_value, "motivo": m,
                                   "receita": din(r.receita), "estado": r.estado.value}
                                  for r, m in resultado.receita_nao_atribuida],
    }
