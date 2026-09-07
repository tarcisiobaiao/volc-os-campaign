"""Contraprovas determinísticas aplicadas depois da resposta do modelo."""

from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any

from .conhecimento import carregar_regras
from .contrato import PedidoDoAgente, PecaCriativa, SaidaDoAgente, contem_metadado_operacional


_ID_OU_SEGREDO_EXTERNO = re.compile(
    r"(?:\bEAA[A-Za-z0-9]+|\bact_\d+|\bcustomers/\d+|/Users/|/home/|https?://)",
    re.IGNORECASE,
)


class SaidaCriativaInvalida(ValueError):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("; ".join(erros))


def _distancia(a: PecaCriativa, b: PecaCriativa) -> int:
    campos = (
        "estado_mental_ref",
        "angulo",
        "hipotese",
        "mecanismo_de_interrupcao",
        "formato",
    )
    return sum(getattr(a, c).casefold() != getattr(b, c).casefold() for c in campos)


def _resolver_json_pointer(documento: Any, caminho: str) -> Any:
    atual = documento
    for parte in caminho.lstrip("/").split("/"):
        chave = parte.replace("~1", "/").replace("~0", "~")
        if isinstance(atual, list):
            try:
                atual = atual[int(chave)]
            except (ValueError, IndexError) as exc:
                raise KeyError(caminho) from exc
        elif isinstance(atual, dict) and chave in atual:
            atual = atual[chave]
        else:
            raise KeyError(caminho)
    return atual


def validar_saida(pedido: PedidoDoAgente, saida: SaidaDoAgente) -> None:
    erros: list[str] = []
    if saida.project_ref != pedido.project_ref:
        erros.append("project_ref diverge do pedido")
    if saida.fase_concluida != pedido.fase:
        erros.append("fase_concluida diverge da fase pedida")
    if len(saida.pecas) != pedido.quantidade_de_pecas:
        erros.append(
            f"lote contém {len(saida.pecas)} peças; esperado {pedido.quantidade_de_pecas}"
        )

    fatos = {f.ref for f in pedido.fatos_da_oferta}
    regras = {r["id"] for r in carregar_regras()["rules"]}
    estados = {e.ref for e in saida.jornada}
    grupos = {g.ref for g in saida.grupos}
    copies = {c.ref: c for c in saida.copies_compartilhadas}
    texto_da_saida = saida.model_dump_json().casefold()
    if _ID_OU_SEGREDO_EXTERNO.search(saida.model_dump_json()):
        erros.append("saída contém URL, caminho privado ou identificador bruto de provedor")
    for restricao in pedido.restricoes:
        for termo in restricao.termos_bloqueados:
            if termo.casefold() in texto_da_saida:
                erros.append(f"termo bloqueado por {restricao.ref} apareceu na saída")

    colecoes = {
        "estados": [e.ref for e in saida.jornada],
        "grupos": [g.ref for g in saida.grupos],
        "copies": list(copies),
        "pecas": [p.ref for p in saida.pecas],
    }
    for nome, ids in colecoes.items():
        repetidos = [ref for ref, n in Counter(ids).items() if n > 1]
        if repetidos:
            erros.append(f"{nome} contém refs duplicadas: {', '.join(repetidos)}")

    for ref in saida.diagnostico.fato_refs:
        if ref not in fatos:
            erros.append(f"diagnóstico cita fato inexistente: {ref}")
    for grupo in saida.grupos:
        ausentes = set(grupo.estado_mental_refs) - estados
        if ausentes:
            erros.append(f"{grupo.ref} cita estados inexistentes: {sorted(ausentes)}")
        if not any(peca.group_ref == grupo.ref for peca in saida.pecas):
            erros.append(f"{grupo.ref} não possui nenhuma peça no lote")
    for copy in saida.copies_compartilhadas:
        if copy.group_ref not in grupos:
            erros.append(f"{copy.ref} cita grupo inexistente")
        ausentes = set(copy.fato_refs) - fatos
        if ausentes:
            erros.append(f"{copy.ref} cita fatos inexistentes: {sorted(ausentes)}")

    congelados = {e.caminho: e.valor for e in pedido.elementos_congelados}
    documento = saida.model_dump(mode="json")
    for caminho, valor in congelados.items():
        try:
            atual = _resolver_json_pointer(documento, caminho)
        except KeyError:
            erros.append(f"elemento congelado ausente da saída: {caminho}")
            continue
        canonico = json.dumps(atual, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if canonico != valor:
            erros.append(f"elemento congelado foi alterado: {caminho}")

    for peca in saida.pecas:
        if peca.group_ref not in grupos:
            erros.append(f"{peca.ref} cita grupo inexistente")
        if peca.estado_mental_ref not in estados:
            erros.append(f"{peca.ref} cita estado mental inexistente")
        copy = copies.get(peca.shared_copy_ref)
        if copy is None:
            erros.append(f"{peca.ref} cita copy compartilhada inexistente")
        elif copy.group_ref != peca.group_ref:
            erros.append(f"{peca.ref} usa copy de outro grupo")
        if peca.formato not in pedido.formatos_permitidos:
            erros.append(f"{peca.ref} usa formato não permitido: {peca.formato}")
        fatos_ausentes = set(peca.fato_refs) - fatos
        if fatos_ausentes:
            erros.append(f"{peca.ref} cita fatos inexistentes: {sorted(fatos_ausentes)}")
        regras_ausentes = set(peca.rule_refs) - regras
        if regras_ausentes:
            erros.append(f"{peca.ref} cita regras inexistentes: {sorted(regras_ausentes)}")
        if contem_metadado_operacional(peca):
            erros.append(f"{peca.ref} vazou metadado operacional na peça")

    # Toda dupla precisa diferir em três dimensões estratégicas. O corpus chama
    # distâncias 1–2 de cosméticas e recomenda concentrar exploração em 3–5.
    for i, atual in enumerate(saida.pecas):
        for outra in saida.pecas[i + 1 :]:
            if _distancia(atual, outra) < 3:
                erros.append(f"{atual.ref} e {outra.ref} são variações cosméticas")

    if erros:
        raise SaidaCriativaInvalida(erros[:30])
