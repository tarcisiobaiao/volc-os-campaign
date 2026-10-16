"""Mundo sintético determinístico do replay econômico v0.

O mundo tem uma VERDADE (parâmetros latentes + ruído diário) que só o avaliador
enxerga, e uma EMISSÃO: as observações que o VOLC conheceria, com atraso de
reporte, restatement (preliminar -> revisada), lacunas e falhas. Políticas nunca
recebem o mundo; recebem um `Snapshot` construído a partir do log emitido.

Simulação em malha fechada: a receita de um dia depende do gasto que a política
alocou. Por isso o replay é por SIMULADOR, não por log histórico (um log histórico
só avalia a política que o gerou, sem modelo contrafactual).

Determinismo: cada (cenário, unidade, dia) tem um RNG próprio derivado de sha256,
então todas as políticas enfrentam o MESMO mundo (números aleatórios comuns),
independentemente da ordem das chamadas.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from volc_dil.contracts import (
    ChaveUnidade,
    Cobertura,
    Dinheiro,
    EstadoMedida,
    Maturidade,
    Metrica,
    MetodoAtribuicao,
    Observacao,
    ValueKind,
)

TZ_NOME = "America/Sao_Paulo"
TZ = ZoneInfo(TZ_NOME)
FONTE_CUSTO = "google_ads_sint"
FONTE_RECEITA = "publisher_report_sint"
NATUREZA = "sintetico"


@dataclass(frozen=True)
class EspecCenario:
    """Parâmetros de um cenário. Tudo que define o mundo está aqui (e na seed)."""

    nome: str
    seed: int
    n_unidades: int = 8  # unidades na moeda principal
    n_unidades_outra_moeda: int = 1
    n_dias: int = 60
    data_inicio: str = "2026-07-01"
    conta: str = "acc-sint-1"
    moeda: str = "BRL"
    outra_moeda: str = "USD"
    orcamento_por_unidade_micros: int = 100_000_000  # 100/dia por unidade; total fixo por moeda
    elasticidade: float = 0.7  # receita ~ alpha * gasto^b (b<1: retorno decrescente)
    roas_ref_min: float = 0.7
    roas_ref_max: float = 1.6
    ruido_sigma: float = 0.20  # ruído lognormal diário da receita
    p_custo_nao_coletado: float = 0.03
    p_custo_backfill: float = 0.5  # fração das lacunas de custo preenchidas em d+2
    p_receita_falha_prelim: float = 0.05  # preliminar falha; revisão chega normal
    p_receita_nao_coletada: float = 0.02  # nunca chega (preliminar e revisão sem valor)
    vies_prelim_min: float = 0.60  # preliminar = verdade * U(min, max)
    vies_prelim_max: float = 1.05
    frac_unidades_prelim_otimista: float = 0.0  # unidades cujo preliminar superestima
    vies_otimista_min: float = 1.20
    vies_otimista_max: float = 1.60
    dia_quebra: Optional[int] = None  # regime não estacionário: troca de eficiência
    fator_queda: float = 0.5
    fator_alta: float = 1.6
    atraso_custo_h: int = 3  # custo do dia d disponível em d+1 03:00
    atraso_prelim_h: int = 6  # receita preliminar em d+1 06:00
    dias_revisao: int = 3  # receita revisada em d+3 06:00
    natureza: str = NATUREZA

    def para_json(self) -> dict:
        return asdict(self)

    @property
    def inicio(self) -> date:
        return date.fromisoformat(self.data_inicio)


@dataclass(frozen=True)
class Unidade:
    chave: ChaveUnidade
    moeda: str
    alpha: float  # eficiência latente (verdade, nunca exposta à política)
    prelim_otimista: bool


def _rng(*partes: object) -> random.Random:
    semente = hashlib.sha256("|".join(str(p) for p in partes).encode()).hexdigest()
    return random.Random(int(semente[:16], 16))


def chave_campanha(conta: str, entidade_id: str) -> ChaveUnidade:
    return ChaveUnidade(conta, "campaign", entidade_id, ("campaign", "day"))


def inicio_dia(dia: date) -> datetime:
    return datetime.combine(dia, time(0), TZ)


def as_of_decisao(dia: date) -> datetime:
    """Decisão do orçamento do dia `dia` é tomada às 23:00 da véspera."""
    return inicio_dia(dia) - timedelta(hours=1)


def dia_de(o: Observacao) -> date:
    return o.janela_inicio.astimezone(TZ).date()


@dataclass(frozen=True)
class DiaVerdade:
    eps: float
    custo_nao_coletado: bool
    custo_backfill: bool
    receita_falha_prelim: bool
    receita_nao_coletada: bool
    fator_prelim: float


class Mundo:
    """Verdade + emissão. Só o motor (para emitir) e o avaliador (para medir) tocam aqui."""

    def __init__(self, espec: EspecCenario):
        self.espec = espec
        r = _rng(espec.seed, espec.nome, "unidades")
        unidades: list[Unidade] = []
        ref = espec.orcamento_por_unidade_micros / 1_000_000
        b = espec.elasticidade
        total = espec.n_unidades + espec.n_unidades_outra_moeda
        n_otimistas = round(espec.frac_unidades_prelim_otimista * espec.n_unidades)
        for i in range(total):
            moeda = espec.moeda if i < espec.n_unidades else espec.outra_moeda
            roas = r.uniform(espec.roas_ref_min, espec.roas_ref_max)
            alpha = roas * ref ** (1 - b)
            unidades.append(
                Unidade(chave_campanha(espec.conta, f"cmp-{i:03d}"), moeda, alpha, i < n_otimistas)
            )
        self.unidades: tuple[Unidade, ...] = tuple(unidades)
        self._por_chave = {u.chave: u for u in unidades}
        # Ordem de eficiência (verdade) para definir quem cai/sobe na quebra de regime.
        ordem = sorted((u for u in unidades if u.moeda == espec.moeda), key=lambda u: -u.alpha)
        metade = len(ordem) // 2
        self._cai = {u.chave for u in ordem[:metade]}
        self._sobe = {u.chave for u in ordem[metade:]}
        r2 = _rng(espec.seed, espec.nome, "alocacao_inicial")
        self._pesos_iniciais = {u.chave: r2.randint(1, 10) for u in unidades}

    # ── verdade ────────────────────────────────────────────────────────────
    def dia(self, i: int) -> date:
        return self.espec.inicio + timedelta(days=i)

    def sorteio(self, chave: ChaveUnidade, i: int) -> DiaVerdade:
        e = self.espec
        r = _rng(e.seed, e.nome, chave.entidade_id, i)
        eps = r.lognormvariate(0.0, e.ruido_sigma)
        cnc = r.random() < e.p_custo_nao_coletado
        cbf = r.random() < e.p_custo_backfill
        rfp = r.random() < e.p_receita_falha_prelim
        rnc = r.random() < e.p_receita_nao_coletada
        u = self._por_chave[chave]
        if u.prelim_otimista:
            fp = r.uniform(e.vies_otimista_min, e.vies_otimista_max)
        else:
            fp = r.uniform(e.vies_prelim_min, e.vies_prelim_max)
        return DiaVerdade(eps, cnc, cbf, rfp, rnc, fp)

    def alpha_efetivo(self, chave: ChaveUnidade, i: int) -> float:
        u = self._por_chave[chave]
        e = self.espec
        if e.dia_quebra is not None and i >= e.dia_quebra:
            if chave in self._cai:
                return u.alpha * e.fator_queda
            if chave in self._sobe:
                return u.alpha * e.fator_alta
        return u.alpha

    def eficiencia(self, chave: ChaveUnidade, i: int) -> float:
        """alpha_efetivo * ruído do dia: o que um oráculo com informação perfeita conhece."""
        return self.alpha_efetivo(chave, i) * self.sorteio(chave, i).eps

    def receita_verdadeira(self, chave: ChaveUnidade, i: int, gasto_micros: int) -> int:
        if gasto_micros <= 0:
            return 0
        s = gasto_micros / 1_000_000
        valor = self.eficiencia(chave, i) * s ** self.espec.elasticidade
        return int(round(valor * 1_000_000))

    def moeda_de(self, chave: ChaveUnidade) -> str:
        return self._por_chave[chave].moeda

    def orcamento_total(self) -> dict[str, int]:
        tot: dict[str, int] = {}
        for u in self.unidades:
            tot[u.moeda] = tot.get(u.moeda, 0) + self.espec.orcamento_por_unidade_micros
        return dict(sorted(tot.items()))

    def alocacao_inicial(self) -> dict[ChaveUnidade, Dinheiro]:
        """Alocação herdada (não uniforme): é o que `current/static` mantém."""
        saida: dict[ChaveUnidade, Dinheiro] = {}
        for moeda, total in self.orcamento_total().items():
            membros = [u.chave for u in self.unidades if u.moeda == moeda]
            valores = repartir(total, [self._pesos_iniciais[c] for c in membros])
            for c, v in zip(membros, valores):
                saida[c] = Dinheiro(v, moeda)
        return saida

    # ── emissão (o que o VOLC conheceria) ─────────────────────────────────
    def emitir(self, i: int, alocacao: dict[ChaveUnidade, Dinheiro]) -> list[Observacao]:
        e = self.espec
        d = self.dia(i)
        ini = inicio_dia(d)
        fim = inicio_dia(d + timedelta(days=1))
        saida: list[Observacao] = []
        for u in self.unidades:
            sorteio = self.sorteio(u.chave, i)
            gasto = alocacao[u.chave]
            if gasto.moeda != u.moeda:
                raise ValueError("alocação em moeda diferente da unidade (o motor deveria ter recusado)")
            comum = dict(unidade=u.chave, janela_inicio=ini, janela_fim=fim, timezone=TZ_NOME,
                         versao_fonte="sint-v0", linhagem=(f"cenario:{e.nome}", f"seed:{e.seed}"))
            # custo
            t_custo = fim + timedelta(hours=e.atraso_custo_h)
            cid = f"{e.nome}:custo:{u.chave.entidade_id}:{d.isoformat()}"
            if sorteio.custo_nao_coletado:
                saida.append(Observacao(
                    metrica=Metrica.CUSTO, valor=None, estado=EstadoMedida.NAO_COLETADO,
                    observado_em=t_custo, disponivel_em=t_custo, fonte=FONTE_CUSTO, coleta_id=cid + ":v1",
                    cobertura=Cobertura.DESCONHECIDA, maturidade=Maturidade.PRELIMINAR,
                    metodo=MetodoAtribuicao.NAO_APLICAVEL, motivo="coletor de custo não rodou", **comum))
                if sorteio.custo_backfill:
                    t2 = t_custo + timedelta(days=1)
                    saida.append(_obs_valor(Metrica.CUSTO, gasto, t2, FONTE_CUSTO, cid + ":v2",
                                            Cobertura.COMPLETA, Maturidade.MADURA, None, comum))
            else:
                saida.append(_obs_valor(Metrica.CUSTO, gasto, t_custo, FONTE_CUSTO, cid + ":v1",
                                        Cobertura.COMPLETA, Maturidade.MADURA, None, comum))
            # receita: preliminar e revisada (restatement = outra observação, mesma chave lógica)
            verdade = self.receita_verdadeira(u.chave, i, gasto.micros)
            t_pre = fim + timedelta(hours=e.atraso_prelim_h)
            t_rev = fim + timedelta(days=e.dias_revisao - 1, hours=e.atraso_prelim_h)
            rid = f"{e.nome}:receita:{u.chave.entidade_id}:{d.isoformat()}"
            if sorteio.receita_nao_coletada:
                for t, sufixo in ((t_pre, ":v1"), (t_rev, ":v2")):
                    saida.append(Observacao(
                        metrica=Metrica.RECEITA, valor=None, estado=EstadoMedida.NAO_COLETADO,
                        observado_em=t, disponivel_em=t, fonte=FONTE_RECEITA, coleta_id=rid + sufixo,
                        cobertura=Cobertura.DESCONHECIDA, maturidade=Maturidade.PRELIMINAR,
                        metodo=MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE, value_kind=ValueKind.REPORTED_REVENUE,
                        motivo="relatório do publisher não trouxe a campanha", **comum))
                continue
            if sorteio.receita_falha_prelim:
                saida.append(Observacao(
                    metrica=Metrica.RECEITA, valor=None, estado=EstadoMedida.FALHA,
                    observado_em=t_pre, disponivel_em=t_pre, fonte=FONTE_RECEITA, coleta_id=rid + ":v1",
                    cobertura=Cobertura.DESCONHECIDA, maturidade=Maturidade.PRELIMINAR,
                    metodo=MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE, value_kind=ValueKind.REPORTED_REVENUE,
                    motivo="falha na coleta preliminar", **comum))
            else:
                prelim = int(round(verdade * sorteio.fator_prelim))
                saida.append(_obs_valor(Metrica.RECEITA, Dinheiro(prelim, u.moeda), t_pre, FONTE_RECEITA,
                                        rid + ":v1", Cobertura.PARCIAL, Maturidade.PRELIMINAR,
                                        ValueKind.REPORTED_REVENUE, comum))
            saida.append(_obs_valor(Metrica.RECEITA, Dinheiro(verdade, u.moeda), t_rev, FONTE_RECEITA,
                                    rid + ":v2", Cobertura.COMPLETA, Maturidade.REVISADA,
                                    ValueKind.REPORTED_REVENUE, comum))
        return saida


def _obs_valor(metrica, valor: Dinheiro, t, fonte, coleta_id, cobertura, maturidade, kind, comum) -> Observacao:
    estado = EstadoMedida.ZERO_CONFIRMADO if valor.eh_zero() else EstadoMedida.MEDIDO
    metodo = MetodoAtribuicao.NAO_APLICAVEL if metrica is Metrica.CUSTO else MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE
    return Observacao(metrica=metrica, valor=valor, estado=estado, observado_em=t, disponivel_em=t, fonte=fonte,
                      coleta_id=coleta_id, cobertura=cobertura, maturidade=maturidade, metodo=metodo,
                      value_kind=kind, **comum)


def repartir(total: int, pesos: list[int]) -> list[int]:
    """Reparte `total` micros por pesos inteiros com maior resto (determinístico, soma exata)."""
    if total < 0:
        raise ValueError("total negativo")
    if not pesos:
        return []
    if any(p < 0 for p in pesos):
        raise ValueError("peso negativo")
    soma = sum(pesos)
    if soma == 0:
        pesos = [1] * len(pesos)
        soma = len(pesos)
    base = [total * p // soma for p in pesos]
    restos = [(total * p % soma, -i) for i, p in enumerate(pesos)]
    falta = total - sum(base)
    for _, neg_i in sorted(restos, reverse=True)[:falta]:
        base[-neg_i] += 1
    return base


# ── catálogo de cenários ──────────────────────────────────────────────────

def catalogo(seed: int) -> list[EspecCenario]:
    return [
        EspecCenario(nome="estacionario", seed=seed),
        EspecCenario(nome="quebra_regime", seed=seed, dia_quebra=30),
        EspecCenario(nome="preliminar_otimista", seed=seed, frac_unidades_prelim_otimista=0.5),
        EspecCenario(nome="lacunas_altas", seed=seed, p_custo_nao_coletado=0.15, p_receita_falha_prelim=0.20,
                     p_receita_nao_coletada=0.08, ruido_sigma=0.35),
    ]


def cenario_mini(seed: int = 7) -> EspecCenario:
    """Cenário pequeno para fixture versionada e testes rápidos."""
    return EspecCenario(nome="mini", seed=seed, n_unidades=3, n_unidades_outra_moeda=1, n_dias=12,
                        p_custo_nao_coletado=0.10, p_receita_falha_prelim=0.15, p_receita_nao_coletada=0.05)

