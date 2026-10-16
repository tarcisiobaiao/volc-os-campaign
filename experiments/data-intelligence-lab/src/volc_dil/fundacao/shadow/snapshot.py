"""Snapshot `as_of(T)` imutável: o ÚNICO insumo que uma política shadow recebe.

Construção (`construir_snapshot(fluxo_indexado, T, config)`):

1. `fluxo.as_of(T)` (regra da thread A: maior `available_at <= T` por chave natural);
2. custo Google Ads campanha × dia e receita JoinAds campanha × dia (base `revenue_basis`) viram as
   entradas de `identidade.juntar_campanha_dia`, um dia por vez, para que cobertura de receita,
   balde `nao_atribuivel` e resolução determinística de identidade venham da thread C;
3. receitas de moedas diferentes no mesmo dia são juntadas em partições por moeda (a junção
   herdada recusa somar moedas); a mesma campanha com receita em duas moedas no mesmo dia é
   bloqueio (`moeda_misturada`);
4. o snapshot guarda FATOS (medidas com estado, status fino, idade), cobertura por dia,
   bloqueios e diagnósticos de dado — nunca o fluxo nem uma `Observacao`. Uma política não tem
   como olhar além de T porque não recebe nada que contenha o futuro.

Fingerprint = sha256(esquema, T, hash encadeado de TODAS as observações visíveis em T, contagem,
config, versão do código, hash dos fatos). Observação com `available_at > T` não entra em nada.
Fontes ignoradas de propósito: `legado_daily_metrics` (gatilho legado R5), sensor/site (tráfego
não atribuível a campanha hoje — 03 §0), métricas sem papel na margem (impressões etc.; entram no
fingerprint, não nos fatos).
"""
from __future__ import annotations

import dataclasses
import inspect
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from volc_dil.contracts.fingerprint import sha256_de
from volc_dil.contracts.money import Dinheiro, MoedasDiferentes
from volc_dil.contracts.observation import ContratoViolado
from volc_dil.contracts.vocab import COM_VALOR, EstadoMedida, Metrica

from ..identidade import (
    CampanhaRegistrada,
    CustoCampanhaDia,
    Gravidade,
    Medida,
    ReceitaChaveDia,
    ReceitaDominioDia,
    RegistroCampanhas,
    detectar_colisoes_registro,
    juntar_campanha_dia,
)
from ..identidade.juncao import LinhaCampanhaDia
from ..observacao.chaves import instante_canonico
from ..observacao.modelo import Observacao
from ..observacao.vocab import MAPA_ESTADO_HERDADO, StatusObservacao
from .fluxo import FluxoIndexado, ItemFluxo
from .tipos import EntidadeCampanha, para_json_seguro
from .versao import versao_codigo

ESQUEMA = "volc-dil.shadow.snapshot.v1"
FUSO_PADRAO = "America/Sao_Paulo"
STATUS_COM_VALOR_FECHADO = frozenset({StatusObservacao.OBSERVED.value, StatusObservacao.ZERO_CONFIRMED.value})
FONTES_IGNORADAS = frozenset({"legado_daily_metrics", "site_analytics", "gtm_sensor"})


class GraoMistoNoDia(ContratoViolado):
    """Receita do mesmo dia vinda de dois endpoints/grãos diferentes (cortes do mesmo dinheiro)."""


class SnapshotAdulterado(ContratoViolado):
    """O snapshot não confere com o próprio fingerprint ou contém conhecimento posterior a T."""


@dataclass(frozen=True)
class CambioDeclarado:
    """Taxa declarada por operador (NÃO é observação): `para` por 1 unidade de `de`, como fração exata."""

    de: str
    para: str
    numerador: int
    denominador: int
    fonte: str

    @property
    def taxa(self) -> Fraction:
        return Fraction(self.numerador, self.denominador)

    def para_json(self) -> dict:
        return {"de": self.de, "para": self.para, "taxa": f"{self.numerador}/{self.denominador}", "fonte": self.fonte}


@dataclass(frozen=True)
class ConfigCorte:
    janela_dias: int = 14
    fuso: str = FUSO_PADRAO
    revenue_basis: str = "client"
    cambios: tuple[CambioDeclarado, ...] = ()
    registro: Optional[tuple[CampanhaRegistrada, ...]] = None  # None = derivado do custo visível
    fuso_receita_verificado: bool = False

    def para_json(self) -> dict:
        return {
            "janela_dias": self.janela_dias, "fuso": self.fuso, "revenue_basis": self.revenue_basis,
            "cambios": [c.para_json() for c in self.cambios],
            "registro": None if self.registro is None else [
                [c.customer_id, c.campaign_id, c.nome, c.valido_de.isoformat(),
                 c.valido_ate.isoformat() if c.valido_ate else None, c.template.value] for c in self.registro],
            "fuso_receita_verificado": self.fuso_receita_verificado,
        }


@dataclass(frozen=True)
class FatoCampanhaDia:
    entidade: EntidadeCampanha
    dia: date
    custo: Medida
    receita: Medida
    custo_status: Optional[str]  # status fino da versão vigente (None = nenhuma observação)
    custo_motivo: Optional[str]
    receita_status: Optional[str]
    receita_motivo: Optional[str]
    idade_h: int  # horas inteiras desde o fim do dia local até T (negativo: dia em curso)
    custo_versoes: int
    receita_versoes: int

    @property
    def custo_moeda(self) -> Optional[str]:
        return self.custo.valor.moeda if isinstance(self.custo.valor, Dinheiro) else None

    @property
    def receita_moeda(self) -> Optional[str]:
        return self.receita.valor.moeda if isinstance(self.receita.valor, Dinheiro) else None

    def para_json(self) -> dict:
        def med(m: Medida):
            v = m.valor.para_json() if isinstance(m.valor, Dinheiro) else m.valor
            return {"estado": m.estado.value, "valor": v, "motivo": m.motivo}

        return {"entidade": [self.entidade.customer_id, self.entidade.campaign_id], "dia": self.dia.isoformat(),
                "custo": med(self.custo), "receita": med(self.receita), "custo_status": self.custo_status,
                "custo_motivo": self.custo_motivo, "receita_status": self.receita_status,
                "receita_motivo": self.receita_motivo, "idade_h": self.idade_h,
                "custo_versoes": self.custo_versoes, "receita_versoes": self.receita_versoes}


@dataclass(frozen=True)
class CoberturaDia:
    dia: date
    fracoes: tuple[tuple[str, Optional[Fraction]], ...]  # (moeda, fração da receita com chave)
    denominador: str
    receita_nao_atribuida: int  # nº de linhas no balde nao_atribuivel
    bloqueios: tuple[str, ...]
    sem_receita_valida: tuple[EntidadeCampanha, ...] = ()  # campanhas sem linha de receita válida no dia

    @property
    def fracao_minima(self) -> Optional[Fraction]:
        valores = [f for _, f in self.fracoes if f is not None]
        if not valores or len(valores) != len(self.fracoes):
            return None
        return min(valores)

    def para_json(self) -> dict:
        return {"dia": self.dia.isoformat(), "fracoes": [[m, para_json_seguro(f)] for m, f in self.fracoes],
                "denominador": self.denominador, "receita_nao_atribuida": self.receita_nao_atribuida,
                "bloqueios": list(self.bloqueios),
                "sem_receita_valida": [[e.customer_id, e.campaign_id] for e in self.sem_receita_valida]}


@dataclass(frozen=True)
class DiagnosticoDado:
    codigo: str
    entidade: Optional[EntidadeCampanha]
    detalhe: str

    def para_json(self) -> list:
        return [self.codigo, None if self.entidade is None else [self.entidade.customer_id, self.entidade.campaign_id],
                self.detalhe]


@dataclass(frozen=True)
class SnapshotShadow:
    as_of: datetime
    dia_corte: date
    config: ConfigCorte
    fatos: tuple[FatoCampanhaDia, ...]
    campanhas: tuple[EntidadeCampanha, ...]
    primeiro_custo: tuple[tuple[EntidadeCampanha, date], ...]
    cobertura: tuple[CoberturaDia, ...]
    bloqueios_entidade: tuple[tuple[EntidadeCampanha, tuple[str, ...]], ...]
    diagnosticos_dados: tuple[DiagnosticoDado, ...]
    avisos: tuple[str, ...]
    n_visiveis: int
    fingerprint_visiveis: str
    versao_codigo: str
    rotulo: str = "corte"
    fingerprint: str = field(default="")

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ContratoViolado("as_of do snapshot precisa de timezone")
        fp = self._calcular_fingerprint()
        if self.fingerprint and self.fingerprint != fp:
            raise SnapshotAdulterado("fingerprint informado não confere com o conteúdo")
        object.__setattr__(self, "fingerprint", fp)
        object.__setattr__(self, "_idx", {(f.entidade, f.dia): f for f in self.fatos})

    # ------------------------------------------------------------------ integridade
    def _corpo(self) -> dict:
        return {
            "esquema": ESQUEMA, "as_of": self.as_of_iso, "dia_corte": self.dia_corte.isoformat(),
            "rotulo": self.rotulo, "config": self.config.para_json(),
            "fatos": [f.para_json() for f in self.fatos],
            "campanhas": [[e.customer_id, e.campaign_id] for e in self.campanhas],
            "primeiro_custo": [[e.customer_id, e.campaign_id, d.isoformat()] for e, d in self.primeiro_custo],
            "cobertura": [c.para_json() for c in self.cobertura],
            "bloqueios_entidade": [[e.customer_id, e.campaign_id, list(b)] for e, b in self.bloqueios_entidade],
            "diagnosticos_dados": [d.para_json() for d in self.diagnosticos_dados],
            "avisos": list(self.avisos), "n_visiveis": self.n_visiveis,
            "fingerprint_visiveis": self.fingerprint_visiveis, "versao_codigo": self.versao_codigo,
        }

    def _calcular_fingerprint(self) -> str:
        return sha256_de(self._corpo())

    def verificar_integridade(self) -> None:
        if self._calcular_fingerprint() != self.fingerprint:
            raise SnapshotAdulterado("snapshot alterado depois de construído")
        limite = self.as_of.astimezone(ZoneInfo(self.config.fuso)).date()
        for f in self.fatos:
            if f.dia > limite:
                raise SnapshotAdulterado(f"fato de dia posterior ao corte: {f.dia}")

    def para_json(self) -> dict:
        d = self._corpo()
        d["fingerprint"] = self.fingerprint
        return d

    # ------------------------------------------------------------------ leitura
    @property
    def as_of_iso(self) -> str:
        return instante_canonico(self.as_of)

    def fato(self, entidade: EntidadeCampanha, dia: date) -> Optional[FatoCampanhaDia]:
        return self._idx.get((entidade, dia))  # type: ignore[attr-defined]

    def fatos_de(self, entidade: EntidadeCampanha) -> tuple[FatoCampanhaDia, ...]:
        return tuple(f for f in self.fatos if f.entidade == entidade)

    def primeiro_dia_custo(self, entidade: EntidadeCampanha) -> Optional[date]:
        for e, d in self.primeiro_custo:
            if e == entidade:
                return d
        return None

    def horas_desde_primeiro_custo(self, entidade: EntidadeCampanha) -> Optional[int]:
        d = self.primeiro_dia_custo(entidade)
        if d is None:
            return None
        inicio = datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(self.config.fuso))
        return int((self.as_of - inicio).total_seconds() // 3600)

    def bloqueios_de(self, entidade: EntidadeCampanha) -> tuple[str, ...]:
        for e, b in self.bloqueios_entidade:
            if e == entidade:
                return b
        return ()

    def cobertura_de(self, dia: date) -> Optional[CoberturaDia]:
        for c in self.cobertura:
            if c.dia == dia:
                return c
        return None

    def cambio(self, de: str, para: str) -> Optional[Fraction]:
        if de == para:
            return Fraction(1)
        for c in self.config.cambios:
            if c.de == de and c.para == para:
                return c.taxa
        return None

    def com_fatos(self, fatos: Iterable[FatoCampanhaDia], rotulo: str) -> "SnapshotShadow":
        """Cópia com outros fatos (auditoria metamórfica). Fingerprint novo, rótulo explícito."""
        return replace(self, fatos=tuple(sorted(fatos, key=lambda f: (f.entidade, f.dia))), rotulo=rotulo, fingerprint="")


# --------------------------------------------------------------------------- construção
def _dia_local(t: datetime, fuso: str) -> date:
    return t.astimezone(ZoneInfo(fuso)).date()


def _eh_dia(o: Observacao, fuso: str) -> bool:
    ini = o.janela_inicio.astimezone(ZoneInfo(fuso))
    fim = o.janela_fim.astimezone(ZoneInfo(fuso))
    return ini.hour == 0 and ini.minute == 0 and fim.date() == ini.date() + timedelta(days=1) and fim.hour == 0 \
        and "day" in o.grao and "hour" not in o.grao


def _dims(o: Observacao) -> dict:
    return dict(o.dimensoes)


def _eh_custo(o: Observacao) -> bool:
    return (o.fonte == "google_ads" and o.entidade.tipo == "campaign" and o.metrica is Metrica.CUSTO
            and set(o.grao) == {"campaign", "day"})


def _eh_cliques(o: Observacao) -> bool:
    return (o.fonte == "google_ads" and o.entidade.tipo == "campaign" and o.metrica is Metrica.CLIQUES
            and set(o.grao) == {"campaign", "day"})


def _eh_receita(o: Observacao, basis: str) -> bool:
    if o.fonte != "joinads" or o.metrica is not Metrica.RECEITA:
        return False
    return _dims(o).get("revenue_basis", basis) == basis


def _chave_receita(o: Observacao) -> tuple[Optional[str], Optional[str]]:
    """(custom_key, custom_value) como a JoinAds devolveu."""
    d = _dims(o)
    tipo = o.entidade.tipo
    if tipo.startswith("kv:"):
        return tipo[3:], o.entidade.id
    if tipo == "campaign":
        return d.get("custom_key", "utm_campaign"), d.get("custom_value", o.entidade.id)
    if tipo == "post":
        return d.get("custom_key", "id_post_wp"), o.entidade.id
    if tipo == "land_uri":
        return d.get("custom_key", "land_uri"), o.entidade.id
    return d.get("custom_key"), d.get("custom_value")


def _dinheiro(o: Observacao) -> Optional[Dinheiro]:
    return None if o.valor is None else Dinheiro(o.valor, o.moeda)  # type: ignore[arg-type]


def _estado(o: Observacao) -> EstadoMedida:
    if o.status is StatusObservacao.PARTIAL and o.valor is None:
        return EstadoMedida.NAO_COLETADO
    return MAPA_ESTADO_HERDADO[o.status]


def _pior_status(obs: list[Observacao]) -> tuple[Optional[str], Optional[str]]:
    if not obs:
        return None, None
    ordem = ["invalid", "unavailable", "late", "missing", "unsupported", "partial", "observed", "zero_confirmed"]
    o = min(obs, key=lambda x: (ordem.index(x.status.value), x.motivo or ""))
    return o.status.value, o.motivo


# --------------------------------------------------------------------------- compatibilidade com a junção da C
# A thread C endureceu `juntar_campanha_dia` depois da R1 (as_of obrigatório, identidade de linha de receita,
# erros tipados). O shadow fala as duas versões: detecta a assinatura e só passa os campos que existem.
_JUNCAO_PARAMS = set(inspect.signature(juntar_campanha_dia).parameters)
_CAMPOS_RECEITA = {f.name for f in dataclasses.fields(ReceitaChaveDia)}
_CAMPOS_CUSTO = {f.name for f in dataclasses.fields(CustoCampanhaDia)}
_CAMPOS_DOMINIO = {f.name for f in dataclasses.fields(ReceitaDominioDia)}
try:  # API nova (R1): recusa de entrada mal formada é tipada
    from ..identidade.juncao import ContratoDeEntrada as _ErroEntradaJuncao  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - API antiga
    class _ErroEntradaJuncao(Exception):
        pass

GRAOS_RECEITA_DIM = {"campaign_day": (), "campaign_adunit_day": ("ad_unit_name",),
                     "campaign_country_adunit_day": ("country_iso", "ad_unit_name")}


def _so(campos: set, **kw):
    return {k: v for k, v in kw.items() if k in campos}


def _custo_dia(conta, cid, d, custo, cliques, estado, disponivel_em) -> CustoCampanhaDia:
    return CustoCampanhaDia(conta, cid, d, custo, cliques, estado, **_so(_CAMPOS_CUSTO, disponivel_em=disponivel_em))


def _receita_dia(o: Observacao, dia: date, ck, cv) -> ReceitaChaveDia:
    d = _dims(o)
    grao = d.get("joinads_grain", "campaign_day")
    dimensao = tuple(d[k] for k in GRAOS_RECEITA_DIM.get(grao, ()) if k in d)
    return ReceitaChaveDia(dia, o.conta, **_so(_CAMPOS_RECEITA, endpoint=d.get("joinads_endpoint", "key_value"), grao=grao,
                                                   dimensao=dimensao, disponivel_em=o.available_at),
                           custom_key=ck, custom_value=cv, receita=_dinheiro(o), estado=_estado(o))


def _dominio_dia(o: Observacao, dia: date) -> ReceitaDominioDia:
    return ReceitaDominioDia(dia, o.conta, _dinheiro(o), _estado(o), **_so(_CAMPOS_DOMINIO, disponivel_em=o.available_at))


def _familia(o: Observacao) -> tuple:
    d = _dims(o)
    return (d.get("joinads_endpoint", "key_value"), d.get("joinads_grain", "campaign_day"))


def _juntar_dia(custos: list[CustoCampanhaDia], receitas: list[ReceitaChaveDia], dominio: list[ReceitaDominioDia],
                registro: RegistroCampanhas, config: ConfigCorte, t: Optional[datetime] = None):
    """Junção de um dia, particionada por moeda de receita. Devolve (linhas, coberturas, n_nao_atrib, bloqueio_ents)."""
    grupos: dict[str, list[ReceitaChaveDia]] = defaultdict(list)
    for r in receitas:
        grupos[r.receita.moeda if r.receita is not None else ""].append(r)

    dom_grupos: dict[str, list[ReceitaDominioDia]] = defaultdict(list)
    for r in dominio:
        dom_grupos[r.receita.moeda if r.receita is not None else ""].append(r)
    if not grupos:
        grupos[""] = []
    custo_linhas: dict[tuple, LinhaCampanhaDia] = {}
    receita_por: dict[tuple, list[tuple[str, Medida]]] = defaultdict(list)
    coberturas: list[tuple[str, Optional[Fraction]]] = []
    denominadores: set[str] = set()
    nao_atrib = 0
    for moeda, rs in sorted(grupos.items()):
        dom = dom_grupos.get(moeda) if moeda else None
        extra = _so(_JUNCAO_PARAMS, as_of=t, dominios_dia_kv_coletados={(r.dia, r.dominio) for r in rs} if rs else None)
        res = juntar_campanha_dia(custos, [], rs, registro, receitas_dominio=dom if dom else None,
                                  fuso_sensor=config.fuso, fuso_receita_verificado=config.fuso_receita_verificado, **extra)
        nao_atrib += len(res.receita_nao_atribuida)
        if moeda:
            coberturas.append((moeda, res.cobertura.fracao_receita_com_chave))
            denominadores.add(res.cobertura.denominador_receita)
        for ln in res.linhas:
            k = (ln.customer_id, ln.campaign_id)
            custo_linhas.setdefault(k, ln)
            if not (ln.receita.estado is EstadoMedida.AUSENTE and ln.receita.motivo.startswith("sem linha JoinAds")):
                receita_por[k].append((moeda, ln.receita))
    linhas: dict[tuple, tuple[Medida, Medida]] = {}
    misturadas: set[tuple] = set()
    for k, ln in custo_linhas.items():
        rec = receita_por.get(k, [])
        sem_valor = [m for _, m in rec if m.estado not in COM_VALOR]
        com_valor = [(mo, m) for mo, m in rec if m.estado in COM_VALOR]
        if sem_valor:
            receita = sem_valor[0]
        elif len({mo for mo, _ in com_valor}) > 1:
            misturadas.add(k)
            receita = Medida(EstadoMedida.FALHA, None, "moeda_misturada: receita da campanha em mais de uma moeda no dia")
        elif com_valor:
            receita = com_valor[0][1]
        else:
            receita = ln.receita
        linhas[k] = (ln.custo, receita)
    return linhas, tuple(coberturas), "|".join(sorted(denominadores)) or "indisponivel", nao_atrib, misturadas


def construir_snapshot(fluxo: FluxoIndexado, t: datetime, config: ConfigCorte = ConfigCorte(),
                       *, rotulo: str = "corte") -> SnapshotShadow:
    if not isinstance(fluxo, FluxoIndexado):
        raise ContratoViolado("construir_snapshot recebe FluxoIndexado")
    fuso = config.fuso
    zona = ZoneInfo(fuso)
    vig = fluxo.as_of(t)
    n_vers: dict[str, int] = fluxo.n_versoes(t)
    dia_corte = _dia_local(t, fuso)
    dia_min = dia_corte - timedelta(days=config.janela_dias)

    custo_obs: dict[tuple, list[ItemFluxo]] = defaultdict(list)
    cliques_obs: dict[tuple, Observacao] = {}
    receita_obs: dict[date, list[ItemFluxo]] = defaultdict(list)
    dominio_obs: dict[date, list[Observacao]] = defaultdict(list)
    primeiro: dict[EntidadeCampanha, date] = {}
    vistos_registro: dict[tuple[str, str], date] = {}
    diags: list[DiagnosticoDado] = []
    ignoradas: dict[str, int] = defaultdict(int)

    for nat, item in vig.items():
        o = item.obs
        if o.fonte in FONTES_IGNORADAS:
            ignoradas[o.fonte] += 1
            continue
        if not _eh_dia(o, fuso):
            continue
        dia = _dia_local(o.janela_inicio, fuso)
        if _eh_custo(o):
            ent = EntidadeCampanha(o.conta, o.entidade.id)
            k = (o.conta, o.entidade.id)
            vistos_registro[k] = min(dia, vistos_registro.get(k, dia))
            if o.valor is not None and o.valor > 0:
                primeiro[ent] = min(dia, primeiro.get(ent, dia))
            if dia >= dia_min:
                custo_obs[(o.conta, o.entidade.id, dia)].append(item)
                if o.status is StatusObservacao.MISSING and (o.motivo or "").startswith("zero_sem"):
                    diags.append(DiagnosticoDado("zero_sem_prova_de_linha", ent, f"{dia.isoformat()}:{o.motivo}"))
        elif _eh_cliques(o) and dia >= dia_min:
            cliques_obs[(o.conta, o.entidade.id, dia)] = o
        elif _eh_receita(o, config.revenue_basis) and dia >= dia_min:
            if o.entidade.tipo == "domain":
                dominio_obs[dia].append(o)
            else:
                receita_obs[dia].append(item)

    if config.registro is not None:
        registro = RegistroCampanhas(list(config.registro))
    else:
        registro = RegistroCampanhas([CampanhaRegistrada(c, i, i, d) for (c, i), d in sorted(vistos_registro.items())])

    bloq_ent: dict[EntidadeCampanha, set[str]] = defaultdict(set)
    for col in detectar_colisoes_registro(registro.campanhas):
        if col.gravidade is not Gravidade.BLOQUEIA:
            continue
        if col.tipo.value == "id_em_duas_contas":
            for conta in col.envolvidos:
                bloq_ent[EntidadeCampanha(conta, col.chave)].add(f"colisao_identidade:{col.tipo.value}")
        else:
            for env in col.envolvidos:
                conta, _, cid = env.partition("/")
                bloq_ent[EntidadeCampanha(conta, cid)].add(f"colisao_identidade:{col.tipo.value}")

    dias = sorted({d for (_, _, d) in custo_obs} | set(receita_obs) | set(dominio_obs))
    fatos: list[FatoCampanhaDia] = []
    coberturas: list[CoberturaDia] = []
    for dia in dias:
        custos = []
        for (conta, cid, d), itens in sorted(custo_obs.items()):
            if d != dia:
                continue
            o = itens[0].obs
            cl = cliques_obs.get((conta, cid, d))
            custos.append(_custo_dia(conta, cid, d, _dinheiro(o), None if cl is None else cl.valor, _estado(o), o.available_at))
        bloqueios_dia: set[str] = set()
        receitas = []
        rec_por_cid: dict[str, list[Observacao]] = defaultdict(list)
        validas: set[str] = set()
        for item in receita_obs.get(dia, []):
            o = item.obs
            ck, cv = _chave_receita(o)
            if (o.motivo or "").startswith("chave_substituida"):
                bloqueios_dia.add("custom_key_substituida")
            receitas.append(_receita_dia(o, dia, ck, cv))
            if ck == "utm_campaign" and cv:
                rec_por_cid[cv].append(o)
                if o.status.value in STATUS_COM_VALOR_FECHADO or o.status is StatusObservacao.PARTIAL:
                    validas.add(cv)
        dominio = [_dominio_dia(o, dia) for o in dominio_obs.get(dia, [])]
        familias: dict[str, set] = defaultdict(set)
        for item in receita_obs.get(dia, []):
            familias[item.obs.moeda or ""].add(_familia(item.obs))
        try:
            if any(len(f) > 1 for f in familias.values()):
                raise GraoMistoNoDia("dois endpoints/grãos de receita no mesmo dia: somar duplicaria o dinheiro (R1-F5)")
            linhas, fracoes, denom, n_na, misturadas = _juntar_dia(custos, receitas, dominio, registro, config, t)
        except MoedasDiferentes:
            bloqueios_dia.add("moeda_misturada_receita")
            linhas, fracoes, denom, n_na, misturadas = _juntar_dia(custos, [], [], registro, config, t)
        except (GraoMistoNoDia, _ErroEntradaJuncao) as e:
            # a junção recusou a receita do dia (grão misto, linha duplicada…): o dia fica sem receita, com bloqueio
            bloqueios_dia.add(f"receita_recusada_pela_juncao:{type(e).__name__}")
            linhas, fracoes, denom, n_na, misturadas = _juntar_dia(custos, [], [], registro, config, t)
        fim_dia = datetime(dia.year, dia.month, dia.day, tzinfo=zona) + timedelta(days=1)
        idade = int((t - fim_dia).total_seconds() // 3600)
        sem_receita: list[EntidadeCampanha] = []
        for (conta, cid), (custo, receita) in sorted(linhas.items()):
            ent = EntidadeCampanha(conta, cid)
            if (conta, cid) in misturadas:
                bloq_ent[ent].add("moeda_misturada")
            citens = custo_obs.get((conta, cid, dia), [])
            cst, cmot = _pior_status([i.obs for i in citens])
            robs = rec_por_cid.get(cid, [])
            rst, rmot = _pior_status(robs)
            if cid not in validas:
                sem_receita.append(ent)
            fatos.append(FatoCampanhaDia(
                ent, dia, custo, receita, cst, cmot, rst, rmot, idade,
                sum(n_vers.get(i.chave_natural, 0) for i in citens),
                sum(n_vers.get(o.chave_natural, 0) for o in robs)))
        coberturas.append(CoberturaDia(dia, fracoes, denom, n_na, tuple(sorted(bloqueios_dia)), tuple(sorted(sem_receita))))

    campanhas = sorted({f.entidade for f in fatos} | {EntidadeCampanha(c, i) for c, i in vistos_registro})
    avisos = []
    if not config.fuso_receita_verificado:
        avisos.append("fuso de fechamento do dia JoinAds não verificado")
    amb = fluxo.quarentena_visivel(t)
    if amb:
        diags.append(DiagnosticoDado("versao_ambigua_em_quarentena", None,
                                     f"{len(amb)} leituras de {len({i.chave_natural for i in amb})} fatos fora do as_of"))
    for fonte, n in sorted(ignoradas.items()):
        diags.append(DiagnosticoDado("fonte_ignorada", None, f"{fonte}:{n} fatos vigentes não lidos"))
    return SnapshotShadow(
        as_of=t.astimezone(timezone.utc), dia_corte=dia_corte, config=config,
        fatos=tuple(sorted(fatos, key=lambda f: (f.entidade, f.dia))), campanhas=tuple(campanhas),
        primeiro_custo=tuple(sorted(primeiro.items())), cobertura=tuple(coberturas),
        bloqueios_entidade=tuple(sorted((e, tuple(sorted(b))) for e, b in bloq_ent.items() if b)),
        diagnosticos_dados=tuple(sorted(diags, key=lambda d: (d.codigo, d.entidade or EntidadeCampanha("~", "~"), d.detalhe))),
        avisos=tuple(avisos), n_visiveis=fluxo.n_visiveis(t), fingerprint_visiveis=fluxo.fingerprint_visiveis(t),
        versao_codigo=versao_codigo(), rotulo=rotulo)
