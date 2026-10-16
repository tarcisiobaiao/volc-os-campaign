"""Kernel de bloqueios: regras que valem para QUALQUER política, aplicadas depois dela.

A política propõe; o kernel não muda a ação proposta, só anota `bloqueios`. Proposta bloqueada
continua no ledger (é evidência de que a política quis agir com dado ruim) e na avaliação conta
como `manter`. Só ações que mudam verba recebem bloqueio; `manter`/`alerta`/`insuficiente` passam.

Bloqueios:
- `colisao_identidade:*` — o registro de campanhas não identifica a entidade de forma única
  (id em duas contas, mesma UTM textual em duas campanhas, truncamento ambíguo);
- `moeda_misturada` — receita da campanha em mais de uma moeda no mesmo dia;
- `moeda_sem_cambio:<de>-><para>` — custo e receita em moedas diferentes sem câmbio declarado;
- `custom_key_substituida:<dia>` — num dia da janela a JoinAds trocou a chave pedida e esta
  campanha não tem linha de receita válida nesse dia (a receita dela pode estar na linha trocada);
- `moeda_misturada_receita:<dia>` — o dia inteiro não pôde ser juntado por moeda;
- `receita_recusada_pela_juncao:<erro>:<dia>` — a junção da C recusou a receita do dia (grão misto,
  linha duplicada: somar duplicaria dinheiro — R1-F5);
- `cobertura_receita_baixa:<dia>` — fração da receita com chave abaixo do mínimo num dia de evidência.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from .snapshot import SnapshotShadow
from .tipos import ACOES_QUE_MUDAM_VERBA, DecisaoShadow, ExecucaoProibida, PropostaShadow


@dataclass(frozen=True)
class ConfigKernel:
    janela_dias: int = 7
    cobertura_minima: Fraction = Fraction(9, 10)

    def para_json(self) -> dict:
        return {"janela_dias": self.janela_dias,
                "cobertura_minima": f"{self.cobertura_minima.numerator}/{self.cobertura_minima.denominator}"}


class PropostaForaDoCorte(RuntimeError):
    """Proposta que não pertence ao snapshot entregue (outro corte, outra entidade, outra política)."""


def _dias_evidencia(p: PropostaShadow, snap: SnapshotShadow, cfg: ConfigKernel) -> list[date]:
    ev = p.evidencia_dict()
    if ev.get("dias"):
        return [date.fromisoformat(d) for d in ev["dias"]]
    return [snap.dia_corte - timedelta(days=k) for k in range(1, cfg.janela_dias + 1)]


def bloqueios_para(p: PropostaShadow, snap: SnapshotShadow, cfg: ConfigKernel) -> tuple[str, ...]:
    if p.acao not in ACOES_QUE_MUDAM_VERBA:
        return ()
    b: set[str] = set(snap.bloqueios_de(p.entidade))
    janela = [snap.dia_corte - timedelta(days=k) for k in range(1, cfg.janela_dias + 1)]
    for dia in janela:
        cob = snap.cobertura_de(dia)
        if cob is None:
            continue
        if "custom_key_substituida" in cob.bloqueios and p.entidade in cob.sem_receita_valida:
            b.add(f"custom_key_substituida:{dia.isoformat()}")
        if "moeda_misturada_receita" in cob.bloqueios:
            b.add(f"moeda_misturada_receita:{dia.isoformat()}")
        for x in cob.bloqueios:
            if x.startswith("receita_recusada_pela_juncao"):
                b.add(f"{x}:{dia.isoformat()}")
    for dia in _dias_evidencia(p, snap, cfg):
        cob = snap.cobertura_de(dia)
        frac = None if cob is None else cob.fracao_minima
        if cob is not None and frac is not None and frac < cfg.cobertura_minima:
            b.add(f"cobertura_receita_baixa:{dia.isoformat()}")
    moedas = {(f.custo_moeda, f.receita_moeda) for f in snap.fatos_de(p.entidade) if f.custo_moeda and f.receita_moeda}
    for de_custo, de_receita in sorted(moedas):
        if snap.cambio(de_receita, de_custo) is None:
            b.add(f"moeda_sem_cambio:{de_receita}->{de_custo}")
    return tuple(sorted(b))


def aplicar_kernel(snap: SnapshotShadow, politica: str, decisao: DecisaoShadow, cfg: ConfigKernel = ConfigKernel()) -> DecisaoShadow:
    """Valida que cada proposta pertence ao corte e anota bloqueios."""
    universo = set(snap.campanhas)
    saida = []
    vistos = set()
    for p in decisao.propostas:
        if p.executavel is not False:  # pragma: no cover - barrado no construtor
            raise ExecucaoProibida("proposta executável")
        if p.as_of != snap.as_of_iso or p.fingerprint_corte != snap.fingerprint:
            raise PropostaForaDoCorte(f"proposta de outro corte ({p.as_of}) entregue no corte {snap.as_of_iso}")
        if p.politica != politica:
            raise PropostaForaDoCorte(f"proposta assinada por {p.politica!r} na decisão de {politica!r}")
        if p.entidade not in universo:
            raise PropostaForaDoCorte(f"entidade fora do snapshot: {p.entidade.rotulo()}")
        if p.entidade in vistos:
            raise PropostaForaDoCorte(f"duas propostas para {p.entidade.rotulo()} no mesmo corte")
        vistos.add(p.entidade)
        saida.append(p.com_bloqueios(bloqueios_para(p, snap, cfg)))
    return DecisaoShadow(tuple(saida), decisao.diagnosticos)
