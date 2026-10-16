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
- `cobertura_receita_baixa:<dia>` — fração da receita com chave abaixo do mínimo num dia de evidência;
- `cobertura_receita_nao_comprovada:<dia>:<denominador>` — num dia de evidência a cobertura da partição de
  receita da campanha não é medida contra `/earnings` (earnings ausente, `unavailable`, ou só a soma do próprio
  key-value, que dá 1 por construção). Sem denominador independente não há prova de cobertura (R2-G3).
  `ConfigKernel(cobertura_sem_earnings="aceitar_declarado")` existe SÓ para fontes sintéticas que não emitem
  earnings (simulador da E: toda receita tem chave por construção) e fica registrado na config do ledger.
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
    cobertura_sem_earnings: str = "bloquear"  # | "aceitar_declarado" (só sintético sem earnings)

    def __post_init__(self) -> None:
        if self.cobertura_sem_earnings not in ("bloquear", "aceitar_declarado"):
            raise ValueError(f"cobertura_sem_earnings desconhecida: {self.cobertura_sem_earnings!r}")

    def para_json(self) -> dict:
        return {"janela_dias": self.janela_dias,
                "cobertura_minima": f"{self.cobertura_minima.numerator}/{self.cobertura_minima.denominator}",
                "cobertura_sem_earnings": self.cobertura_sem_earnings}


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
    explicita = bool(p.evidencia_dict().get("dias"))
    for dia in _dias_evidencia(p, snap, cfg):
        cob = snap.cobertura_de(dia)
        f = snap.fato(p.entidade, dia)
        moeda = f.receita_moeda if f is not None else None
        if cob is None or not cob.fracoes:
            if not explicita:
                continue  # janela padrão: dia sem nenhuma receita lida ainda não é evidência de nada
            particoes = [(None, "indisponivel")]  # a política declarou usar um dia sem receita medida
        elif moeda is not None:
            particoes = [cob.cobertura_da_moeda(moeda)]
        else:  # campanha sem receita no dia: toda partição do dia precisa estar comprovada
            particoes = [(fr, d) for _, fr, d in cob.fracoes] or [(None, "indisponivel")]
        for frac, denom in particoes:
            if denom != "earnings_dominio_dia" or frac is None:
                if cfg.cobertura_sem_earnings == "bloquear" or frac is None:
                    b.add(f"cobertura_receita_nao_comprovada:{dia.isoformat()}:{denom}")
                    continue
            if frac < cfg.cobertura_minima:
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
