"""Como um caminho aponta para um pedaço da saída — e por que ele não usa índice.

## O defeito que este módulo existe para fechar

A aprovação grava um `path` e um `snapshot`. Na run seguinte, `validar_saida`
reabre esse `path` na saída NOVA e exige que o valor não tenha mudado: é assim
que "aprovado congela" funciona.

Isso só é verdade se o caminho apontar para a MESMA coisa nas duas runs. Com
índice, não aponta. `/pecas/0` é "a primeira peça do lote", e o lote é
reordenado a cada geração — aprovar a peça do grupo A e receber, na run
seguinte, a peça do grupo B na posição 0 faz a contraprova comparar dois objetos
diferentes. O resultado é o pior dos dois: ou acusa alteração no que ninguém
mexeu, ou aprova silenciosamente uma peça que o operador nunca viu.

Pior ainda, o padrão de `PedidoDeDecisao.caminho` aceita `-` no segmento, então
`/pecas/-1` passava na validação de forma e `lista[int("-1")]` resolvia para o
ÚLTIMO elemento. Um índice negativo não é só instável: ele nomeia uma posição
que se move na direção contrária à que qualquer leitor humano espera.

## O contrato aqui

Dentro de uma lista, o segmento é o **`ref` do elemento**, não a posição:

    /pecas/creative_hook_frio        em vez de   /pecas/0
    /copies_compartilhadas/copy_a    em vez de   /copies_compartilhadas/2

Refs são estáveis por construção (o contrato as valida com padrão próprio) e
sobrevivem à reordenação. Um segmento numérico é **recusado**, e a recusa é
explícita em vez de silenciosa, porque um caminho por índice que "quase funciona"
é exatamente o que produziu o defeito acima.

Elementos sem `ref` (dicionários simples dentro de listas) não são endereçáveis;
aprovar o pai é a resposta certa e é o que a interface oferece.
"""

from __future__ import annotations

from typing import Any


class CaminhoInvalido(KeyError):
    """O caminho não existe, ou existe de um jeito que não sobrevive à próxima run."""

    def __init__(self, caminho: str, motivo: str) -> None:
        super().__init__(caminho)
        self.caminho = caminho
        self.motivo = motivo


def _segmento(bruto: str) -> str:
    return bruto.replace("~1", "/").replace("~0", "~")


def resolver(documento: Any, caminho: str) -> Any:
    """Devolve o valor apontado por `caminho`, recusando endereçamento instável."""
    if not caminho.startswith("/"):
        raise CaminhoInvalido(caminho, "um caminho começa com '/'")

    atual = documento
    for parte in caminho.lstrip("/").split("/"):
        chave = _segmento(parte)
        if isinstance(atual, list):
            if chave.lstrip("-").isdigit():
                raise CaminhoInvalido(
                    caminho,
                    "dentro de uma lista o segmento é o 'ref' do elemento, "
                    "não a posição: a posição muda a cada geração",
                )
            encontrado = next(
                (
                    item
                    for item in atual
                    if isinstance(item, dict) and item.get("ref") == chave
                ),
                None,
            )
            if encontrado is None:
                raise CaminhoInvalido(caminho, f"nenhum elemento com ref {chave!r}")
            atual = encontrado
        elif isinstance(atual, dict) and chave in atual:
            atual = atual[chave]
        else:
            raise CaminhoInvalido(caminho, f"segmento {chave!r} não existe")
    return atual
