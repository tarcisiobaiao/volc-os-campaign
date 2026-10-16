"""Auditoria metamórfica null × zero.

Uma política correta precisa DISTINGUIR "receita sem valor" de "receita zero confirmada".
Teste: trocar cada observação sem valor do snapshot por um zero confirmado da mesma chave
lógica. Se a decisão não muda em nenhum dos snapshots auditados, a política se comporta
como se tratasse null como 0 (ou ignora completamente a lacuna) — sinal de alerta.
Se muda, a política reage à diferença entre ausência e zero.

O zero de substituição tem a cobertura que um valor real teria naquela versão (completa se
não for preliminar), para que uma política correta que exige cobertura completa o enxergue.

Políticas que não leem dado nenhum (static, equal) também não mudam; para não confundir
"cega a dados" com "null como zero", um segundo teste perturba a receita de UMA unidade
(×3, não preserva razões entre unidades — F1-07): se nenhuma perturbação muda a decisão,
a política é classificada como `cega_a_dados`.
"""
from __future__ import annotations

from dataclasses import replace

from volc_dil.contracts import Cobertura, Dinheiro, EstadoMedida, Maturidade, Metrica, Observacao, Snapshot
from volc_dil.contracts.vocab import COM_VALOR

from .politicas import ContextoDecisao, Decisao, Politica


def _como_zero(o: Observacao, moeda: str) -> Observacao:
    cob = Cobertura.PARCIAL if o.maturidade is Maturidade.PRELIMINAR else Cobertura.COMPLETA
    return replace(o, valor=Dinheiro(0, moeda), estado=EstadoMedida.ZERO_CONFIRMADO, motivo=None, cobertura=cob)


def snapshot_null_vira_zero(snap: Snapshot, ctx: ContextoDecisao) -> Snapshot:
    trocadas = []
    for o in snap.observacoes:
        if o.estado not in COM_VALOR and o.unidade in ctx.moeda_por_unidade:
            trocadas.append(_como_zero(o, ctx.moeda_por_unidade[o.unidade]))
        else:
            trocadas.append(o)
    return Snapshot.construir(trocadas, snap.as_of, politica_futuro="falhar", rotulo="auditoria_null_zero")


def snapshot_unidade_perturbada(snap: Snapshot, unidade) -> Snapshot:
    """Receita de UMA unidade ×3 (+1 unidade monetária): muda razões entre unidades."""
    trocadas = [replace(o, valor=Dinheiro(o.valor.micros * 3 + 1_000_000, o.valor.moeda), estado=EstadoMedida.MEDIDO)
                if o.unidade == unidade and o.metrica is Metrica.RECEITA and isinstance(o.valor, Dinheiro) else o
                for o in snap.observacoes]
    return Snapshot.construir(trocadas, snap.as_of, politica_futuro="falhar", rotulo="auditoria_sensibilidade")


def _assinatura(d: Decisao) -> tuple:
    return tuple(sorted((u.entidade_id, v.micros) for u, v in d.alocacao.items()))


def auditar_null_vs_zero(politica: Politica, casos: list[tuple[Snapshot, ContextoDecisao]]) -> dict:
    n_com_lacuna = n_diverge = n_sensivel = 0
    for snap, ctx in casos:
        if all(o.estado in COM_VALOR for o in snap.observacoes):
            continue
        n_com_lacuna += 1
        a = politica.decidir(snap, ctx)
        b = politica.decidir(snapshot_null_vira_zero(snap, ctx), ctx)
        n_diverge += _assinatura(a) != _assinatura(b)
        for u in sorted(ctx.unidades):
            if _assinatura(politica.decidir(snapshot_unidade_perturbada(snap, u), ctx)) != _assinatura(a):
                n_sensivel += 1
                break
    cega = n_com_lacuna > 0 and n_sensivel == 0
    return {
        "politica": politica.nome,
        "snapshots_com_lacuna": n_com_lacuna,
        "decisoes_que_distinguem_null_de_zero": n_diverge,
        "decisoes_sensiveis_a_valores": n_sensivel,
        "cega_a_dados": cega,
        "suspeita_null_como_zero": n_com_lacuna > 0 and n_diverge == 0 and not cega,
    }
