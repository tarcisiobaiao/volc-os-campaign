"""A nota do anúncio, lida do Google — e não adivinhada por nós.

## Por que este módulo existe

Três rodadas do MESMO erro, medidas nesta operação:

    card 74, 19/08  · termo em 1 de 15 títulos  → Ad Strength **Médio**
    card 65, 19/08  · termo em 4 de 15 títulos  → Ad Strength **Ruim**
    card 65, 2ª vez · termo em 7 de 15 títulos  → ainda abaixo do necessário

A cada reprovação eu apertava um limiar que eu mesmo havia CHUTADO. Isso não é
engenharia, é reagir — e a régua chutada só é auditada quando o dano já está na
conta.

## ⚠️ E O LIMIAR CHUTADO ESTAVA ERRADO NA VARIÁVEL, NÃO NO VALOR

Quarta rodada, 19/08/2026, campanha `24161105437`, subida pausada só para medir:
termo em **15 de 15** títulos e **4 de 4** descrições — a cobertura no teto — e o
Google devolveu **a MESMA nota (AVERAGE) e os MESMOS dois itens**. Apertar o
limiar nunca ia funcionar: "Try including more keywords" pede keywords
DISTINTAS, não a mesma repetida.

Quinta rodada, campanha `24156373085`, mesma conta, mesmo dia: copy reescrita
para espelhar buscas diferentes — 16 das 82 keywords do grupo cobertas (contra
7) e 16 das 36 palavras recorrentes (contra 13) — e o painel mostrou **Bom**.

    4/15 de raiz, 7/82 keywords espelhadas   → Médio
    15/15 de raiz, 7/82 keywords espelhadas  → Médio   ← repetir não move
    raiz livre, 16/82 keywords espelhadas    → Bom     ← variedade move

É o primeiro Bom desta operação, e é o número que a `C11` do contrato passou a
cobrar. Ver `copy/contrato.py::_c11_variedade_de_keywords`.

Nota do que NÃO foi preciso: o item "Inclua palavras-chave bastante usadas nos
títulos" continuava DESMARCADO no painel quando a nota virou Bom. Perseguir as
keywords de maior volume até fechar aquele item não é requisito para chegar lá.

## ⚠️ O CAMPO DA API ATRASA EM RELAÇÃO AO PAINEL — e muito

Medido na `24156373085`: o painel já mostrava **Bom** e `ad_group_ad.ad_strength`
continuava `PENDING` **40 minutos** depois da criação, em 27 leituras.

Isso não invalida o módulo, mas muda como usá-lo: o laço
"subir pausado → ler → refazer" NÃO fecha dentro de uma sessão. Quem chamar
precisa tratar `PENDING` como "volte mais tarde" — e nunca como reprovação, que
faria o motor refazer uma copy que o Google ainda não olhou. É por isso que
`Veredito.pendente` existe separado de `precisa_refazer`.

A verdade de campo estava a uma consulta de distância. `ad_group_ad` expõe
`ad_strength` (o enum POOR/AVERAGE/GOOD/EXCELLENT) e `action_items` — a lista
de recomendações, no mesmo texto que o operador lê no painel. Consultado em
19/08/2026 nas duas campanhas da conta:

    "Try including more keywords in your headlines."
    "Try including more keywords in your descriptions."

O segundo item me disse algo que nenhum limiar meu diria: a checagem C9 olhava
só TÍTULOS. Metade do que o Google pede passava sem ninguém olhar.

## O laço que isto fecha

Campanha nasce PAUSED — não entra em leilão e não gasta. E mesmo assim o Google
revisa e pontua. Ou seja: o juiz mais rígido custa ZERO e responde em minutos.

    subir pausado → ler ad_strength + action_items → se não for GOOD/EXCELLENT,
    realimentar a cascata com os itens DO GOOGLE → refazer

Deixa de existir limiar meu. Existe o veredito deles.

## O que este módulo NÃO faz

Não escreve nada — é `search()`, leitura pura, sem `destravar()`. Não decide
remover nem relançar: devolve o veredito para quem orquestra. E não traduz os
`action_items`: eles vão como o Google os escreveu, porque o texto exato é o
que se realimenta ao modelo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .gads.client import cliente

#: Notas em que o anúncio está bom o bastante para não refazer.
#:
#: `GOOD` entra junto com `EXCELLENT` de propósito: a diferença entre os dois
#: costuma ser variedade de ativo, não relevância de termo, e perseguir
#: EXCELLENT custaria rodadas de LLM por ganho que ninguém mediu nesta operação.
BOAS = frozenset({"GOOD", "EXCELLENT"})

#: Notas que exigem refazer.
RUINS = frozenset({"POOR", "AVERAGE"})


@dataclass(frozen=True)
class Veredito:
    """O que o Google achou de UM anúncio, com o que ele mesmo recomenda."""

    resource_name: str
    campaign_id: str
    campaign_name: str
    ad_strength: str
    itens: tuple[str, ...] = ()
    aprovacao: str = ""

    @property
    def boa(self) -> bool:
        return self.ad_strength in BOAS

    @property
    def precisa_refazer(self) -> bool:
        return self.ad_strength in RUINS

    @property
    def pendente(self) -> bool:
        """⚠️ `PENDING` não é ruim — é "ainda não avaliei".

        Tratar pendente como reprovado faria o motor refazer uma copy que o
        Google nem olhou, e refazer custa a cascata inteira. Quem vir isto
        espera e pergunta de novo.
        """
        return self.ad_strength in ("PENDING", "UNKNOWN", "UNSPECIFIED")

    def resumo(self) -> str:
        cabeca = f"{self.ad_strength} · {self.campaign_name[:60]}"
        if not self.itens:
            return cabeca
        return cabeca + "\n" + "\n".join(f"  • {i}" for i in self.itens)


_GAQL = """
SELECT campaign.id, campaign.name, campaign.status,
       ad_group_ad.resource_name, ad_group_ad.ad_strength,
       ad_group_ad.action_items,
       ad_group_ad.policy_summary.approval_status
FROM ad_group_ad
WHERE campaign.id = {campanha} AND ad_group_ad.status != 'REMOVED'
"""


def ler(customer_id: str, campaign_id: str, *,
        login_customer_id: str, servico: Any = None) -> tuple[Veredito, ...]:
    """Os vereditos dos anúncios de UMA campanha. Leitura pura.

    `servico` existe para o teste injetar um dublê — a consulta é a parte que
    não dá para provar sem rede, e a decisão em cima dela é a que importa.
    """
    svc = servico or cliente(login_customer_id).get_service("GoogleAdsService")
    saida: list[Veredito] = []
    for row in svc.search(customer_id=str(customer_id),
                          query=_GAQL.format(campanha=campaign_id)):
        aga = row.ad_group_ad
        saida.append(Veredito(
            resource_name=str(aga.resource_name),
            campaign_id=str(row.campaign.id),
            campaign_name=str(row.campaign.name),
            ad_strength=_nome(aga.ad_strength),
            itens=tuple(str(i) for i in (aga.action_items or ())),
            aprovacao=_nome(getattr(aga.policy_summary, "approval_status", None)),
        ))
    return tuple(saida)


def _nome(v: Any) -> str:
    """Enum do proto → string. `None` e valor cru também viram texto."""
    return getattr(v, "name", None) or (str(v) if v is not None else "")


@dataclass(frozen=True)
class Realimentacao:
    """Os itens do Google traduzidos em instrução para a cascata.

    ⚠️ O texto do Google viaja INTEIRO e em inglês, como ele o escreveu. Traduzir
    ou resumir seria eu reinterpretando o veredito — e foi exatamente a minha
    interpretação que errou três vezes. O modelo lê inglês.
    """

    nota: str
    itens: tuple[str, ...] = ()
    linhas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def acionavel(self) -> bool:
        return bool(self.itens)

    def como_prompt(self) -> str:
        if not self.itens:
            return ""
        return (
            "\n\n=== O GOOGLE JÁ AVALIOU ESTE ANÚNCIO ===\n"
            f"Ad Strength: {self.nota}\n"
            "Estes são os itens que ELE apontou, no texto original:\n"
            + "\n".join(f"  - {i}" for i in self.itens)
            + "\nReescreva atendendo a cada um. Não é opinião de revisor: é o "
              "veredito da plataforma sobre este anúncio.\n"
        )


def realimentar(vereditos: tuple[Veredito, ...]) -> Realimentacao:
    """Junta os vereditos numa instrução única para a próxima geração.

    A nota que vale é a PIOR: um anúncio bom não compensa um ruim no mesmo
    grupo, e é o ruim que precisa de conserto.
    """
    if not vereditos:
        return Realimentacao(nota="", itens=(), linhas=())
    ordem = {"POOR": 0, "AVERAGE": 1, "PENDING": 2, "UNKNOWN": 2,
             "UNSPECIFIED": 2, "GOOD": 3, "EXCELLENT": 4}
    pior = min(vereditos, key=lambda v: ordem.get(v.ad_strength, 2))
    itens: list[str] = []
    for v in vereditos:
        for i in v.itens:
            if i not in itens:
                itens.append(i)
    linhas = tuple(f"{v.ad_strength} · {len(v.itens)} item(ns)" for v in vereditos)
    return Realimentacao(nota=pior.ad_strength, itens=tuple(itens), linhas=linhas)
