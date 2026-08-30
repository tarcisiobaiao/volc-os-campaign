"""O perfil de Search — o primeiro canal, e o único que existe hoje.

## Onde este arquivo fica no desenho

A dependência aponta **canal → núcleo**, sempre (ADR-17). Este módulo importa
`sincronizador`; `sincronizador` NUNCA importa este, exceto dentro de
`resolver_perfil()`, que é o único ponto do núcleo onde o nome de um canal
decide alguma coisa. Um canal novo entra criando um arquivo irmão deste e
registrando o perfil — sem tocar em `inventario.py`, em `sincronizador.py` nem
no schema do snapshot. É a régua do critério 3 da §10.4 do SPEC.

## O que Search injeta na varredura

Uma coisa só, hoje: o **lance**, que mora no grupo de anúncios e não na
campanha. O núcleo recebe o número já traduzido para o vocabulário comum
(`lance_micros`) e nunca vê a entidade que o carregava — é isso que permite a
Display, amanhã, injetar o seu equivalente sem que o inventário mude de forma.

## ⚠️ Campanha com grupos de lances DIFERENTES devolve `null`

`volc_ads/entrega.py` pega o primeiro grupo que aparecer. Isso é uma escolha que
some na tela: dois grupos com R$ 0,12 e R$ 3,00 viram "lance R$ 0,12", e o
`teto_de_cliques` calculado em cima disso descreve um teto que não existe para
metade da campanha.

Aqui, lances divergentes produzem `None` — ausência, não um dos valores. Sem
lance único, `verba ÷ lance` não é o teto de nada, e o contrato já trata `null`
como "não foi possível medir". A divergência vai para o log, com os valores, de
modo que ela seja investigável sem virar um número inventado na tela.

Somente leitura: GAQL só tem SELECT, e a query passa pelo `_exigir_leitura` do
núcleo antes de sair.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

from app.trafego import inventario as inv
from app.trafego import sincronizador as sinc

log = logging.getLogger("volc.trafego.adaptador_search")

#: O lance vive no grupo de anúncios. `status != 'REMOVED'` porque um grupo
#: removido não dá lance em leilão nenhum e o valor dele só confundiria.
GAQL_LANCE = """
SELECT campaign.id, ad_group.id, ad_group.cpc_bid_micros
FROM ad_group WHERE campaign.id IN ({ids}) AND ad_group.status != 'REMOVED'
"""

#: A URL de destino também não mora na campanha — ela mora no ANÚNCIO.
#:
#: `campaign.final_url_suffix` existe e é outra coisa: parâmetro de marcação,
#: não destino. O destino de uma campanha Search é `ad_group_ad.ad.final_urls`,
#: e é por isso que colhê-lo é trabalho do PERFIL: em Performance Max o mesmo
#: fato vive no asset group, e o núcleo não pode saber disso.
#:
#: O núcleo recebe `url_final` já traduzida para o vocabulário comum, e a coluna
#: que a guarda existe desde a v9_01 — declarada e nunca escrita, porque nenhuma
#: consulta a pedia. É a razão de `url_final` ser 100% NULA nas 84 campanhas
#: medidas em 26/08/2026, e de a regra de reconciliação mais forte do SPEC
#: ("URL final igual à `lp_url` de um funil") nunca ter tido do que casar.
#:
#: Somente leitura: `SELECT`, e a query passa pelo `_exigir_leitura` do núcleo.
GAQL_URL_FINAL = """
SELECT campaign.id, ad_group_ad.ad.final_urls
FROM ad_group_ad WHERE campaign.id IN ({ids}) AND ad_group_ad.status != 'REMOVED'
"""

#: Ids por consulta. A URL do `search` tem limite prático de tamanho, e uma
#: conta com centenas de campanhas montaria um `IN (...)` que a API recusa com
#: um erro que não diz que a causa foi o tamanho.
LOTE_DE_IDS = 200


class PerfilSearch:
    """O perfil, com um consumidor real hoje — a régua do ADR-19."""

    canal = inv.SEARCH

    def entidades_filhas(self) -> Tuple[str, ...]:
        return ("grupo de anúncios (lance)", "anúncio (URL final)")

    def ler_filhas(self, buscar: Callable[[str], Iterable[Any]],
                   campaign_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Devolve `{campaign_id: {"lance_micros": int|None}}`.

        ⚠️ `IN ()` é erro de sintaxe no GAQL, e o erro que volta fala de parse,
        não de lista vazia. Sem ids, não há o que perguntar — e não perguntar é
        mais barato que perguntar e tratar o erro.
        """
        ids = [str(i) for i in campaign_ids if str(i or "").strip()]
        if not ids:
            return {}

        vistos: Dict[str, List[int]] = {}
        for inicio in range(0, len(ids), LOTE_DE_IDS):
            lote = ids[inicio:inicio + LOTE_DE_IDS]
            for row in buscar(GAQL_LANCE.format(ids=",".join(lote))):
                alvo = str(row.campaign.id)
                bruto = getattr(row.ad_group, "cpc_bid_micros", None)
                if bruto is None:
                    continue
                vistos.setdefault(alvo, []).append(int(bruto))

        # ── a URL de destino, do anúncio ───────────────────────────────────
        #
        # Numa consulta separada de propósito: se ela falhar, o lance continua
        # chegando. Juntar as duas num `FROM ad_group_ad` faria uma conta sem
        # anúncio vivo perder também o lance, e "sem anúncio" é um estado
        # legítimo de campanha pausada.
        urls: Dict[str, set] = {}
        leu_urls = True
        try:
            for inicio in range(0, len(ids), LOTE_DE_IDS):
                lote = ids[inicio:inicio + LOTE_DE_IDS]
                for row in buscar(GAQL_URL_FINAL.format(ids=",".join(lote))):
                    alvo = str(row.campaign.id)
                    for u in (getattr(row.ad_group_ad.ad, "final_urls", None) or ()):
                        texto = str(u or "").strip()
                        if texto:
                            urls.setdefault(alvo, set()).add(texto)
        except Exception as exc:  # noqa: BLE001
            # Sem URL o inventário continua correto — ele só perde o sinal mais
            # forte da reconciliação, e perder um sinal é diferente de derrubar
            # a varredura da conta inteira.
            #
            # ⚠️ `leu_urls = False` é o que impede a falha de virar APAGAMENTO.
            # O payload do espelho é uniformizado (`_uniforme`): basta uma linha
            # do lote trazer a chave para TODAS a mandarem, e as sem valor
            # mandariam `null`. Como o gatilho não preserva `url_final`, uma
            # leitura de anúncio que falhou apagaria a URL de todas as campanhas
            # da conta — e a reconciliação, sem o sinal, voltaria a dizer "sem
            # campanha" e a oferecer duplicação.
            leu_urls = False
            log.warning("não consegui ler a URL final dos anúncios: %s", exc)

        saida: Dict[str, Dict[str, Any]] = {}
        for campanha in ids:
            # ⚠️ URLs divergentes devolvem `None`, pela mesma razão do lance:
            # escolher uma faria a reconciliação casar o funil errado com toda a
            # confiança. Uma campanha cujos anúncios apontam para páginas
            # diferentes não tem UMA URL de destino, e inventar uma é pior que
            # declarar ausência — a regra de composição sabe lidar com sinal
            # ausente, não com sinal errado.
            destino: Dict[str, Any] = {}
            if leu_urls:
                achados = sorted(urls.get(campanha, ()))
                if len(achados) > 1:
                    log.info(
                        "campanha %s tem %d URLs finais distintas; o espelho "
                        "declara `null` em vez de escolher uma",
                        campanha, len(achados))
                destino = {"url_final": achados[0] if len(achados) == 1 else None}

            lances = sorted(set(vistos.get(campanha, [])))
            if len(lances) == 1:
                saida[campanha] = {"lance_micros": lances[0], **destino}
            elif len(lances) > 1:
                log.info(
                    "campanha %s tem %d lances distintos (%s); o inventário "
                    "declara `null` em vez de escolher um — verba ÷ lance não "
                    "descreveria teto nenhum",
                    campanha, len(lances),
                    ", ".join(str(l) for l in lances))
                saida[campanha] = {"lance_micros": None, **destino}
            else:
                # Nenhum grupo vivo: sem lance para declarar, e isso é ausência.
                saida[campanha] = {"lance_micros": None, **destino}
        return saida


PERFIL = PerfilSearch()

# O registro acontece no import, e o import acontece dentro de
# `resolver_perfil()`. Assim o núcleo continua sem citar Search em tempo de
# carga, e um canal novo é um arquivo a mais — não uma linha a mais no núcleo.
sinc.registrar_perfil(PERFIL)
