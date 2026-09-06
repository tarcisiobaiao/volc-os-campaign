"""Quais canais têm CRIAÇÃO autorizada — declarado uma vez, cobrado nos dois lados.

## O defeito que este módulo fecha

`backend/app/trafego/canario.py` declarava `CANAIS_COM_CRIACAO_AUTORIZADA` e
`canario.exigir` o cobrava em `/subir`. Era a trava que fazia Search ser, de
fato, o único canal que cria — `volc_ads/campanha/perfil.py` já declara
`DISPLAY.permite_mutacao_real=True` desde T03.

O problema é onde ela morava. `volc_ads/subir.subir()` **não importa** o
`canario` — ele é do backend, e a dependência aponta sempre `backend → volc_ads`.
A única guarda de canal do executor era `_recusar_canal_sem_mutacao`, que lê só o
perfil. Consequência medida em 06/09/2026: um script in-process com

    with modo.destravar("..."):   # + FORGE_PERMITIR_ESCRITA=1
        subir.subir(preparo_display, motivo="...")

criaria uma campanha Display real **sem passar pela janela do canário**. A rota
HTTP recusava; o executor, não. Uma trava que só existe num dos dois caminhos que
chegam ao `mutate` não é uma trava — é uma convenção.

## Por que a declaração mora aqui e não lá

Aqui é o lugar que os DOIS lados alcançam: `volc_ads` é importável pelo backend,
e o contrário não existe. `canario.py` passou a REFERENCIAR este conjunto em vez
de declarar o seu — não há cópia para divergir, e o teste
`test_canario_referencia_a_autoridade_unica_de_canal` cobra a identidade dos
objetos, não a igualdade dos valores.

Stdlib pura, de propósito: nenhum import de `google.ads`, de `app.` ou de
`volc_ads.campanha`. É o que permite ao backend importá-lo no topo.

## O que ele NÃO é

Não é a autorização de ESCRITA (`gads/modo.py`, dois fatores, global e sem
canal). Não é a capacidade local de prova (`VOLC_DEMAND_GEN_VALIDATE_ONLY`,
`VOLC_PMAX_VALIDATE_ONLY`). Não é `permite_mutacao_real`, que é o que o ENGINE
sabe fazer. É a quarta pergunta, e a única humana: **este canal já teve o
canário aceito?**

As quatro são independentes. Abrir uma nunca abriu outra, e é por isso que elas
têm nomes diferentes.
"""

from __future__ import annotations

from typing import Any, FrozenSet, Tuple

#: Os canais cujo canário JÁ FOI aceito por ato humano, com runbook próprio.
#:
#: ⚠️ Mudar este conjunto é autorizar gasto real num canal novo. Ele não deve
#: mudar junto com código: cada entrada exige o canário DAQUELE canal executado
#: e registrado. Em 06/09/2026 há exatamente um.
CANAIS_COM_CRIACAO_AUTORIZADA: FrozenSet[str] = frozenset({"SEARCH"})

#: Apelido de tela. `PMAX` nunca é valor de contrato (ADR-18).
_APELIDOS = {"PMAX": "PERFORMANCE_MAX"}


class CriacaoNaoAutorizada(RuntimeError):
    """O canário deste canal não foi aceito. Nada foi enviado."""


def canonizar(canal: Any) -> str:
    bruto = str(canal or "").strip().upper()
    return _APELIDOS.get(bruto, bruto)


def autorizado(canal: Any) -> bool:
    return canonizar(canal) in CANAIS_COM_CRIACAO_AUTORIZADA


def exigir(canal: Any) -> str:
    """Devolve o canal canônico, ou levanta. É o portão do executor.

    ⚠️ Ele NÃO substitui `canario.exigir`, que cobra conta, MCC, teto, CPC,
    rede e a confirmação humana de criação pausada. Ele é o mínimo que vale
    inclusive para quem chama `subir.subir()` direto, sem passar pela rota — e
    é justamente esse caminho que ficava sem trava de canal.
    """
    nome = canonizar(canal)
    if nome not in CANAIS_COM_CRIACAO_AUTORIZADA:
        disponiveis = ", ".join(sorted(CANAIS_COM_CRIACAO_AUTORIZADA))
        raise CriacaoNaoAutorizada(
            f"o canário ainda não autoriza CRIAR em {nome or '(canal ausente)'}: "
            f"apenas {disponiveis} tem canário aceito. Provar continua "
            "liberado; criar exige o canário do canal, que é um ato humano "
            "separado com runbook próprio. Nada foi enviado.\n"
            "⚠️ Isto NÃO é uma dúvida sobre o estado inicial: quando este canal "
            "criar, ele criará PAUSADO como todos os outros.")
    return nome


def canais_autorizados() -> Tuple[str, ...]:
    return tuple(sorted(CANAIS_COM_CRIACAO_AUTORIZADA))
