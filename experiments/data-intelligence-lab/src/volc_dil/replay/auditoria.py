"""Auditoria metamórfica null × zero.

Uma política correta precisa DISTINGUIR "receita sem valor" de "receita zero confirmada".
Teste: trocar cada observação sem valor do snapshot por um zero confirmado da mesma chave
lógica. Se a decisão não muda em nenhum dos snapshots auditados, a política se comporta
como se tratasse null como 0 (ou ignora completamente a lacuna) — sinal de alerta.
Se muda, a política reage à diferença entre ausência e zero.

Políticas que não leem dado nenhum (static, equal) também não mudam; para não confundir
"cega a dados" com "null como zero", um segundo teste dobra todos os valores presentes:
se nem isso muda a decisão, a política é classificada como `cega_a_dados`.
"""
from __future__ import annotations

from dataclasses import replace

from volc_dil.contracts import Cobertura, Dinheiro, EstadoMedida, Observacao, Snapshot
from volc_dil.contracts.vocab import COM_VALOR

from .politicas import ContextoDecisao, Decisao, Politica


def _como_zero(o: Observacao, moeda: str) -> Observacao:
    return replace(o, valor=Dinheiro(0, moeda), estado=EstadoMedida.ZERO_CONFIRMADO, motivo=None,
                   cobertura=Cobertura.PARCIAL if o.cobertura is Cobertura.DESCONHECIDA else o.cobertura)


def snapshot_null_vira_zero(snap: Snapshot, ctx: ContextoDecisao) -> Snapshot:
    trocadas = []
    for o in snap.observacoes:
        if o.estado not in COM_VALOR and o.unidade in ctx.moeda_por_unidade:
            trocadas.append(_como_zero(o, ctx.moeda_por_unidade[o.unidade]))
        else:
            trocadas.append(o)
    return Snapshot.construir(trocadas, snap.as_of, politica_futuro="falhar", rotulo="auditoria_null_zero")


def snapshot_valores_dobrados(snap: Snapshot) -> Snapshot:
    trocadas = [replace(o, valor=Dinheiro(o.valor.micros * 2 + 1_000_000, o.valor.moeda), estado=EstadoMedida.MEDIDO)
                if isinstance(o.valor, Dinheiro) else o for o in snap.observacoes]
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
        c = politica.decidir(snapshot_valores_dobrados(snap), ctx)
        n_diverge += _assinatura(a) != _assinatura(b)
        n_sensivel += _assinatura(a) != _assinatura(c)
    cega = n_com_lacuna > 0 and n_sensivel == 0
    return {
        "politica": politica.nome,
        "snapshots_com_lacuna": n_com_lacuna,
        "decisoes_que_distinguem_null_de_zero": n_diverge,
        "decisoes_sensiveis_a_valores": n_sensivel,
        "cega_a_dados": cega,
        "suspeita_null_como_zero": n_com_lacuna > 0 and n_diverge == 0 and not cega,
    }
