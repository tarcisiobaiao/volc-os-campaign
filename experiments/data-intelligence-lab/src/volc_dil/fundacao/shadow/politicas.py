"""Políticas determinísticas do shadow. Recebem SÓ o `SnapshotShadow`; devolvem `DecisaoShadow`.

Nenhuma política lê fluxo, banco, rede, relógio ou modelo de linguagem. Todas são funções puras
do snapshot e dos próprios parâmetros (que entram na `versao`).

Catálogo:
- `Manter` — não fazer nada (baseline obrigatória).
- `BaselineHerdada(Igual())` = `equal` e `BaselineHerdada(GulosaConservadora())` = `greedy_conservador`:
  as baselines do replay v0 herdado (`volc_dil.replay.politicas`), sem cópia — o snapshot é
  reprojetado no contrato econômico herdado e a alocação devolvida vira fator de verba por campanha.
- `RegraMargem` — margem madura (receita convertida − custo)/custo numa janela de dias maduros,
  com cobertura e maturidade mínimas; senão `insuficiente`.
- `Guardiao72h(interna)` (P05-T09) — campanha nova (menos de 72 h desde o 1º custo observado OU
  menos de 3 dias com dado maduro) só recebe `alerta`: todo corte da política interna é rebaixado.
- `regra_margem_imatura()` — a mesma regra aceitando receita preliminar (controle: mede o custo
  de agir com sinal imaturo).
- `regra_margem_null_zero()` — ANTI-BASELINE: ausência vira 0 e "campanha sem custo e sem receita"
  vira pausa por "campanha morta". Existe para ser detectada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction
from typing import Optional, Protocol
from zoneinfo import ZoneInfo

from volc_dil.contracts import (
    ChaveUnidade,
    Cobertura,
    Dinheiro,
    EstadoMedida,
    Maturidade,
    Metrica,
    MetodoAtribuicao,
    Snapshot,
    ValueKind,
)
from volc_dil.contracts import Observacao as ObservacaoEconomica
from volc_dil.contracts.vocab import COM_VALOR
from volc_dil.replay.motor import validar_decisao
from volc_dil.replay.politicas import ContextoDecisao, GulosaConservadora, Igual

from .snapshot import STATUS_COM_VALOR_FECHADO, FatoCampanhaDia, SnapshotShadow
from .tipos import (
    ACOES_DE_CORTE,
    BPS,
    Acao,
    Confianca,
    DecisaoShadow,
    Diagnostico,
    EntidadeCampanha,
    PropostaShadow,
    Severidade,
)


class PoliticaShadow(Protocol):
    nome: str
    versao: str

    def decidir(self, snapshot: SnapshotShadow) -> DecisaoShadow: ...


class SnapshotObrigatorio(TypeError):
    """A política recebeu algo que não é um `SnapshotShadow` (ex.: o fluxo)."""


def exigir_snapshot(s: object) -> SnapshotShadow:
    if not isinstance(s, SnapshotShadow):
        raise SnapshotObrigatorio(f"política shadow recebe SnapshotShadow, não {type(s).__name__}")
    return s


def propor(snap: SnapshotShadow, pol: PoliticaShadow, ent: EntidadeCampanha, acao: Acao, fator: int,
           confianca: Confianca, motivo: str, evidencia: Optional[dict] = None) -> PropostaShadow:
    return PropostaShadow(pol.nome, pol.versao, snap.as_of_iso, snap.fingerprint, ent, acao, fator, confianca,
                          motivo, evidencia or {})


def diagnosticar(snap: SnapshotShadow, pol: PoliticaShadow, codigo: str, sev: Severidade, detalhe: str,
                 ent: Optional[EntidadeCampanha] = None, evidencia: Optional[dict] = None) -> Diagnostico:
    return Diagnostico(pol.nome, snap.as_of_iso, snap.fingerprint, codigo, sev, detalhe, ent, evidencia or {})


def _dias_janela(snap: SnapshotShadow, n: int) -> list[date]:
    return [snap.dia_corte - timedelta(days=k) for k in range(n, 0, -1)]


def _diag_dados(snap: SnapshotShadow, pol: PoliticaShadow) -> list[Diagnostico]:
    return [diagnosticar(snap, pol, d.codigo, Severidade.AVISO, d.detalhe, d.entidade) for d in snap.diagnosticos_dados]


# --------------------------------------------------------------------------- manter
@dataclass(frozen=True)
class Manter:
    nome: str = "manter"
    versao: str = "manter@1"

    def decidir(self, snapshot: SnapshotShadow) -> DecisaoShadow:
        snap = exigir_snapshot(snapshot)
        return DecisaoShadow(tuple(propor(snap, self, e, Acao.MANTER, BPS, Confianca.ALTA, "baseline: não fazer nada")
                                   for e in snap.campanhas))


# --------------------------------------------------------------------------- regra de margem
@dataclass(frozen=True)
class RegraMargem:
    limiar_pausa_bps: int = -3000
    limiar_reducao_bps: int = 0
    fator_reducao_bps: int = 7000
    janela_dias: int = 7
    min_dias_maduros: int = 3
    maturidade_h: int = 72
    ausente_como_zero: bool = False  # True SÓ na anti-baseline
    nome: str = "regra_margem"

    @property
    def versao(self) -> str:
        return (f"regra_margem@1(pausa<{self.limiar_pausa_bps},reduz<{self.limiar_reducao_bps}->{self.fator_reducao_bps},"
                f"janela={self.janela_dias},min={self.min_dias_maduros},mat={self.maturidade_h}h,"
                f"null0={int(self.ausente_como_zero)})")

    def _dia_utilizavel(self, snap: SnapshotShadow, f: Optional[FatoCampanhaDia], ent: EntidadeCampanha, d: date) -> Optional[str]:
        if f is None:
            return "sem_fato"
        cob = snap.cobertura_de(d)
        if cob is not None and "custom_key_substituida" in cob.bloqueios and ent in cob.sem_receita_valida:
            return "custom_key_substituida"
        if cob is not None and "moeda_misturada_receita" in cob.bloqueios:
            return "moeda_misturada_receita"
        if f.custo_status not in STATUS_COM_VALOR_FECHADO:
            return f"custo_{f.custo_status or 'ausente'}"
        if f.receita_status not in STATUS_COM_VALOR_FECHADO or f.receita.estado not in COM_VALOR:
            return f"receita_{f.receita_status or 'ausente'}"
        if f.idade_h < self.maturidade_h:
            return f"imatura_{f.idade_h}h"
        return None

    def decidir(self, snapshot: SnapshotShadow) -> DecisaoShadow:
        snap = exigir_snapshot(snapshot)
        propostas, diags = [], _diag_dados(snap, self)
        for ent in snap.campanhas:
            usados: list[date] = []
            recusas: list[str] = []
            custo = receita = 0
            imaturos = 0
            moeda_c: Optional[str] = None
            sem_cambio: Optional[str] = None
            for d in _dias_janela(snap, self.janela_dias):
                f = snap.fato(ent, d)
                if not self.ausente_como_zero:
                    porque = self._dia_utilizavel(snap, f, ent, d)
                    if porque is not None:
                        recusas.append(f"{d.isoformat()}:{porque}")
                        continue
                c = f.custo.valor if f is not None and isinstance(f.custo.valor, Dinheiro) else None
                r = f.receita.valor if f is not None and isinstance(f.receita.valor, Dinheiro) else None
                if c is not None:
                    moeda_c = c.moeda
                    custo += c.micros
                if r is not None:
                    taxa = snap.cambio(r.moeda, (c.moeda if c is not None else moeda_c) or r.moeda)
                    if taxa is None:
                        sem_cambio = f"{r.moeda}->{c.moeda if c else moeda_c}"
                        break
                    receita += (r.micros * taxa.numerator) // taxa.denominator
                if f is not None and f.idade_h < 72:
                    imaturos += 1
                usados.append(d)
            ev = {"dias": [d.isoformat() for d in usados], "n_dias": len(usados), "custo_micros": custo,
                  "receita_convertida_micros": receita, "moeda": moeda_c, "dias_imaturos_usados": imaturos,
                  "maturidade_h": self.maturidade_h, "recusas": recusas[:7]}
            if sem_cambio is not None:
                propostas.append(propor(snap, self, ent, Acao.INSUFICIENTE, BPS, Confianca.NENHUMA,
                                        f"moeda_sem_cambio:{sem_cambio}", ev))
                continue
            if len(usados) < self.min_dias_maduros and not self.ausente_como_zero:
                propostas.append(propor(snap, self, ent, Acao.INSUFICIENTE, BPS, Confianca.NENHUMA,
                                        f"dias maduros {len(usados)} < {self.min_dias_maduros}", ev))
                continue
            if custo == 0:
                if self.ausente_como_zero and receita == 0:  # BUG DELIBERADO: ausência como prova de campanha morta
                    propostas.append(propor(snap, self, ent, Acao.PAUSAR, 0, Confianca.ALTA, "campanha_morta: custo 0 e receita 0", ev))
                else:
                    propostas.append(propor(snap, self, ent, Acao.INSUFICIENTE, BPS, Confianca.NENHUMA,
                                            "custo zero confirmado na janela: margem indefinida (não é prova de campanha morta)", ev))
                    diags.append(diagnosticar(snap, self, "sem_entrega_confirmada", Severidade.INFO,
                                              "custo zero confirmado em todos os dias maduros", ent, ev))
                continue
            margem = (receita - custo) * BPS // custo
            ev["margem_bps"] = margem
            conf = Confianca.ALTA if len(usados) >= 5 else Confianca.MEDIA
            if self.ausente_como_zero or imaturos:
                conf = Confianca.BAIXA
            if margem < self.limiar_pausa_bps:
                propostas.append(propor(snap, self, ent, Acao.PAUSAR, 0, conf, f"margem {margem} bps < {self.limiar_pausa_bps}", ev))
            elif margem < self.limiar_reducao_bps:
                propostas.append(propor(snap, self, ent, Acao.REDUZIR_VERBA, self.fator_reducao_bps, conf,
                                        f"margem {margem} bps < {self.limiar_reducao_bps}", ev))
            else:
                propostas.append(propor(snap, self, ent, Acao.MANTER, BPS, conf, f"margem {margem} bps", ev))
        return DecisaoShadow(tuple(propostas), tuple(diags))


def regra_margem_imatura() -> RegraMargem:
    """Controle: aceita receita preliminar (idade >= 0 h). Mede o custo do sinal imaturo."""
    return RegraMargem(maturidade_h=0, nome="regra_margem_imatura")


def regra_margem_null_zero() -> RegraMargem:
    """ANTI-BASELINE: ausência = 0, sem maturidade; 'sem custo e sem receita' vira pausa."""
    return RegraMargem(maturidade_h=0, ausente_como_zero=True, nome="regra_margem_null_zero")


# --------------------------------------------------------------------------- guardião 72 h
@dataclass(frozen=True)
class Guardiao72h:
    interna: PoliticaShadow = field(default_factory=RegraMargem)
    horas: int = 72
    min_dias_maduros: int = 3  # campanha segue "nova" até ter este nº de dias com dado maduro

    @property
    def nome(self) -> str:
        return f"guardiao_72h[{self.interna.nome}]"

    @property
    def versao(self) -> str:
        return f"guardiao_72h@1(h={self.horas},min_maduros={self.min_dias_maduros})+{self.interna.versao}"

    def _dias_maduros(self, snap: SnapshotShadow, ent: EntidadeCampanha) -> int:
        """Dias com custo e receita fechados e idade >= `horas` (dado maduro)."""
        return sum(1 for f in snap.fatos_de(ent) if f.idade_h >= self.horas and f.custo_status in STATUS_COM_VALOR_FECHADO
                   and f.receita_status in STATUS_COM_VALOR_FECHADO)

    def decidir(self, snapshot: SnapshotShadow) -> DecisaoShadow:
        snap = exigir_snapshot(snapshot)
        base = self.interna.decidir(snap)
        propostas, diags = [], []
        for p in base.propostas:
            idade = snap.horas_desde_primeiro_custo(p.entidade)
            maduros = self._dias_maduros(snap, p.entidade)
            nova = idade is None or idade < self.horas or maduros < self.min_dias_maduros
            ev = dict(p.evidencia_dict())
            ev["horas_desde_primeiro_custo"] = idade
            ev["dias_com_dado_maduro"] = maduros
            acao, fator, motivo, conf = p.acao, p.fator_bps, p.motivo, p.confianca
            if nova and p.acao in ACOES_DE_CORTE:
                ev["acao_original"] = p.acao.value
                ev["fator_original_bps"] = p.fator_bps
                acao, fator, conf = Acao.ALERTA, BPS, Confianca.BAIXA
                motivo = (f"guardiao_72h: campanha nova ({idade if idade is not None else 'sem custo observado'} h desde o 1º custo, "
                          f"{maduros} dia(s) com dado maduro); "
                          f"corte '{p.acao.value}' de {self.interna.nome} rebaixado a alerta ({p.motivo})")
            if nova:
                diags.append(diagnosticar(snap, self, "campanha_nova_em_observacao", Severidade.INFO,
                                          f"{idade} h desde o 1º custo observado; {maduros} dia(s) com dado maduro "
                                          f"(nova se < {self.horas} h ou < {self.min_dias_maduros} dias maduros)", p.entidade))
            propostas.append(PropostaShadow(self.nome, self.versao, p.as_of, p.fingerprint_corte, p.entidade, acao, fator,
                                            conf, motivo, ev))
        for d in base.diagnosticos:
            diags.append(Diagnostico(self.nome, d.as_of, d.fingerprint_corte, d.codigo, d.severidade, d.detalhe, d.entidade, d.evidencia))
        return DecisaoShadow(tuple(propostas), tuple(diags))


# --------------------------------------------------------------------------- baselines herdadas
_FECHADO = STATUS_COM_VALOR_FECHADO


def _obs_herdada(snap: SnapshotShadow, f: FatoCampanhaDia, metrica: Metrica, maturidade_h: int) -> Optional[ObservacaoEconomica]:
    if f.idade_h < 0:
        return None  # dia em curso: as baselines herdadas decidem sobre dias fechados
    zona = ZoneInfo(snap.config.fuso)
    ini = datetime(f.dia.year, f.dia.month, f.dia.day, tzinfo=zona)
    fim = ini + timedelta(days=1)
    custo = f.custo.valor if isinstance(f.custo.valor, Dinheiro) else None
    if metrica is Metrica.CUSTO:
        med, status, motivo = f.custo, f.custo_status, f.custo_motivo
        valor = custo
    else:
        med, status, motivo = f.receita, f.receita_status, f.receita_motivo
        valor = f.receita.valor if isinstance(f.receita.valor, Dinheiro) else None
        if valor is not None and custo is not None and valor.moeda != custo.moeda:
            taxa = snap.cambio(valor.moeda, custo.moeda)
            if taxa is None:
                return None
            valor = Dinheiro(valor.micros * taxa.numerator // taxa.denominator, custo.moeda)
    tem_valor = valor is not None and med.estado in COM_VALOR
    fechado = status in _FECHADO and tem_valor
    maduro = fechado and f.idade_h >= maturidade_h
    return ObservacaoEconomica(
        unidade=ChaveUnidade(f.entidade.customer_id, "campaign", f.entidade.campaign_id, ("campaign", "day")),
        metrica=metrica, valor=valor if tem_valor else None,
        estado=med.estado if tem_valor else (med.estado if med.estado not in COM_VALOR else EstadoMedida.NAO_COLETADO),
        janela_inicio=ini, janela_fim=fim, timezone=snap.config.fuso, observado_em=fim, disponivel_em=fim,
        fonte="shadow_juncao", versao_fonte=snap.versao_codigo[:16], coleta_id="corte",
        cobertura=Cobertura.COMPLETA if fechado else (Cobertura.PARCIAL if tem_valor else Cobertura.DESCONHECIDA),
        maturidade=Maturidade.MADURA if maduro else Maturidade.PRELIMINAR,
        metodo=MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE if metrica is Metrica.RECEITA else MetodoAtribuicao.NAO_APLICAVEL,
        value_kind=ValueKind.REPORTED_REVENUE if metrica is Metrica.RECEITA else None,
        motivo=None if tem_valor else (med.motivo or f"{status or 'ausente'}: {motivo or 'sem valor'}"),
        linhagem=("shadow_juncao", snap.fingerprint[:16]),
    )


@dataclass(frozen=True)
class BaselineHerdada:
    """Adapta uma política de alocação do replay v0 herdado (`Igual`, `GulosaConservadora`) ao shadow.

    Universo = campanhas com custo fechado e > 0 no último dia fechado (D-1); esse custo é o proxy
    da verba vigente (o snapshot não lê orçamento). A alocação herdada vira fator por campanha.
    """

    herdada: object = field(default_factory=Igual)
    maturidade_h: int = 72
    piso_bps: int = 1000

    @property
    def nome(self) -> str:
        return getattr(self.herdada, "nome")

    @property
    def versao(self) -> str:
        h = self.herdada
        params = ",".join(f"{k}={getattr(h, k)}" for k in ("janela_dias", "dias_maturacao", "teto_bps", "margem_bps") if hasattr(h, k))
        return f"herdada:{h.nome}@v0({params})+mat={self.maturidade_h}h+piso={self.piso_bps}"

    def decidir(self, snapshot: SnapshotShadow) -> DecisaoShadow:
        snap = exigir_snapshot(snapshot)
        ontem = snap.dia_corte - timedelta(days=1)
        atual: dict[ChaveUnidade, Dinheiro] = {}
        ents: dict[ChaveUnidade, EntidadeCampanha] = {}
        for e in snap.campanhas:
            f = snap.fato(e, ontem)
            if f is None or f.custo_status not in _FECHADO or not isinstance(f.custo.valor, Dinheiro) or f.custo.valor.micros <= 0:
                continue
            u = ChaveUnidade(e.customer_id, "campaign", e.campaign_id, ("campaign", "day"))
            atual[u] = f.custo.valor
            ents[u] = e
        por_moeda: dict[str, list[ChaveUnidade]] = {}
        for u, v in atual.items():
            por_moeda.setdefault(v.moeda, []).append(u)
        fora = [e for e in snap.campanhas if e not in ents.values()]
        propostas = [propor(snap, self, e, Acao.INSUFICIENTE, BPS, Confianca.NENHUMA,
                            "fora do universo: sem custo fechado > 0 em D-1 (proxy da verba vigente)") for e in fora]
        validas = {m: us for m, us in por_moeda.items() if len(us) >= 2}
        for m, us in por_moeda.items():
            if len(us) < 2:
                propostas += [propor(snap, self, ents[u], Acao.INSUFICIENTE, BPS, Confianca.NENHUMA,
                                     f"universo {m} com {len(us)} campanha: nada a realocar") for u in us]
        if validas:
            unidades = tuple(sorted(u for us in validas.values() for u in us))
            obs = []
            for f in snap.fatos:
                u = ChaveUnidade(f.entidade.customer_id, "campaign", f.entidade.campaign_id, ("campaign", "day"))
                if u not in unidades:
                    continue
                for met in (Metrica.CUSTO, Metrica.RECEITA):
                    o = _obs_herdada(snap, f, met, self.maturidade_h)
                    if o is not None:
                        obs.append(o)
            herd_snap = Snapshot.construir(obs, snap.as_of, politica_futuro="falhar", rotulo=f"shadow/{snap.as_of_iso}")
            orc = {m: sum(atual[u].micros for u in us) for m, us in validas.items()}
            # piso nunca acima da menor verba vigente: manter a alocação atual tem de ser sempre válido
            piso = {m: min(orc[m] // len(us) * self.piso_bps // BPS, min(atual[u].micros for u in us)) for m, us in validas.items()}
            ctx = ContextoDecisao(dia=snap.dia_corte, as_of=snap.as_of, unidades=unidades,
                                  moeda_por_unidade={u: atual[u].moeda for u in unidades}, orcamento_total=orc,
                                  alocacao_atual={u: atual[u] for u in unidades}, piso_micros=piso)
            dec = self.herdada.decidir(herd_snap, ctx)  # type: ignore[attr-defined]
            validar_decisao(dec, ctx)
            for u in unidades:
                novo, velho = dec.alocacao[u].micros, atual[u].micros
                fator = novo * BPS // velho
                if fator == BPS:
                    acao = Acao.MANTER
                elif fator == 0:
                    acao = Acao.PAUSAR
                elif fator < BPS:
                    acao = Acao.REDUZIR_VERBA
                else:
                    acao = Acao.AUMENTAR_VERBA
                ev = {"verba_proxy_micros": velho, "verba_proposta_micros": novo, "moeda": atual[u].moeda,
                      "excluida": dec.excluidas.get(u), "insumos": dec.insumos}
                conf = Confianca.BAIXA if self.nome == "equal" else Confianca.MEDIA
                propostas.append(propor(snap, self, ents[u], acao, fator, conf,
                                        dec.excluidas.get(u) or f"alocação {self.nome}", ev))
        return DecisaoShadow(tuple(propostas), tuple(_diag_dados(snap, self)))


def equal() -> BaselineHerdada:
    return BaselineHerdada(Igual())


def greedy_conservador() -> BaselineHerdada:
    return BaselineHerdada(GulosaConservadora())


def catalogo_padrao() -> tuple:
    """Políticas do relatório: baselines, regra madura, guardião e controles."""
    return (Manter(), equal(), greedy_conservador(), RegraMargem(), Guardiao72h(RegraMargem()),
            regra_margem_imatura(), Guardiao72h(regra_margem_imatura()), regra_margem_null_zero())
