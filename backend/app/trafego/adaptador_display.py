"""O perfil de Display — irmão de `adaptador_search`, e diferente onde importa.

## O que muda em relação a Search

**O lance.** Display nasce travado em `MAXIMIZE_CONVERSIONS` (contrato do canal,
`campanha/display.py:LANCES_PERMITIDOS`), e uma campanha em Smart Bidding não
tem `cpc_bid_micros` no grupo. Ausência de lance aqui é o caso NORMAL — e por
isso ela é DECLARADA (`lance_micros=None`), não descoberta por acidente.

⚠️ Isso é diferente de Search, onde `None` significa "grupos com lances
divergentes" ou "nenhum grupo vivo". O núcleo recebe `null` nos dois casos e o
contrato já trata `null` como "não foi possível medir" — mas o motivo viaja no
log, porque as duas ausências pedem investigações diferentes.

**O tCPA.** Onde Search tem CPC, Display pode ter `target_cpa_micros` dentro do
`MaximizeConversions`. Ele é lido no mesmo lote, e é o número que descreve o teto
econômico deste canal.

**A URL.** Igual a Search: mora no ANÚNCIO (`ad_group_ad.ad.final_urls`), e não
na campanha. É a autoridade que `canario._AUTORIDADE_DE_URL["DISPLAY"]` já
declara — este módulo não a reescreve, ele a exercita.

Somente leitura: GAQL só tem SELECT, e a query passa pelo `_exigir_leitura` do
núcleo antes de sair.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

from app.trafego import inventario as inv
from app.trafego import sincronizador as sinc

log = logging.getLogger("volc.trafego.adaptador_display")

#: O lance e a meta de custo por aquisição, no grupo.
#:
#: ⚠️ `ad_group.target_cpa_micros` E `ad_group.cpc_bid_micros` na MESMA consulta:
#: os dois vivem no `ad_group` e uma campanha Display tem no máximo um deles
#: preenchido. Duas consultas separadas fariam uma falha de uma apagar o valor
#: da outra, que é o defeito que `adaptador_search` já documenta para a URL.
GAQL_ECONOMIA = """
SELECT campaign.id, ad_group.id, ad_group.cpc_bid_micros,
       ad_group.target_cpa_micros
FROM ad_group WHERE campaign.id IN ({ids}) AND ad_group.status != 'REMOVED'
"""

#: A URL de destino mora no ANÚNCIO, como em Search — e não na campanha.
GAQL_URL_FINAL = """
SELECT campaign.id, ad_group_ad.ad.final_urls
FROM ad_group_ad WHERE campaign.id IN ({ids}) AND ad_group_ad.status != 'REMOVED'
"""

#: Ids por consulta. Mesmo motivo de Search: `IN (...)` grande é recusado com um
#: erro que não diz que a causa foi o tamanho.
LOTE_DE_IDS = 200


class PerfilDisplay:
    """O perfil de varredura de Display."""

    canal = inv.DISPLAY

    def entidades_filhas(self) -> Tuple[str, ...]:
        return ("grupo de anúncios (lance e meta)", "anúncio (URL final)")

    def ler_filhas(self, buscar: Callable[[str], Iterable[Any]],
                   campaign_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Devolve `{campaign_id: {"lance_micros": …, "url_final": …}}`.

        ⚠️ `IN ()` é erro de sintaxe no GAQL, e o erro que volta fala de parse,
        não de lista vazia. Sem ids, não há o que perguntar.
        """
        ids = [str(i) for i in campaign_ids if str(i or "").strip()]
        if not ids:
            return {}

        lances: Dict[str, List[int]] = {}
        metas: Dict[str, List[int]] = {}
        for inicio in range(0, len(ids), LOTE_DE_IDS):
            lote = ids[inicio:inicio + LOTE_DE_IDS]
            for row in buscar(GAQL_ECONOMIA.format(ids=",".join(lote))):
                alvo = str(row.campaign.id)
                bruto = getattr(row.ad_group, "cpc_bid_micros", None)
                if bruto:
                    lances.setdefault(alvo, []).append(int(bruto))
                alvo_cpa = getattr(row.ad_group, "target_cpa_micros", None)
                if alvo_cpa:
                    metas.setdefault(alvo, []).append(int(alvo_cpa))

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
            # ⚠️ `leu_urls = False` é o que impede a falha de virar APAGAMENTO —
            # o payload do espelho é uniformizado, e uma leitura que falhou
            # mandaria `null` para todas as campanhas da conta. O mesmo
            # raciocínio, palavra por palavra, de `adaptador_search`.
            leu_urls = False
            log.warning("não consegui ler a URL final dos anúncios Display: %s",
                        exc)

        saida: Dict[str, Dict[str, Any]] = {}
        for campanha in ids:
            destino: Dict[str, Any] = {}
            if leu_urls:
                achados = sorted(urls.get(campanha, ()))
                if len(achados) > 1:
                    log.info(
                        "campanha Display %s tem %d URLs finais distintas; o "
                        "espelho declara `null` em vez de escolher uma",
                        campanha, len(achados))
                destino = {"url_final": achados[0] if len(achados) == 1 else None}

            vistos = sorted(set(lances.get(campanha, [])))
            if len(vistos) == 1:
                lance = vistos[0]
            else:
                if len(vistos) > 1:
                    log.info(
                        "campanha Display %s tem %d lances distintos (%s); o "
                        "inventário declara `null` em vez de escolher um",
                        campanha, len(vistos),
                        ", ".join(str(x) for x in vistos))
                else:
                    # ⚠️ O CASO NORMAL, e ele é DECLARADO. Display em
                    # MaximizeConversions não tem CPC de grupo; `null` aqui não
                    # é falha de leitura nem grupo morto — é a economia deste
                    # canal, que se mede por verba e meta, não por lance.
                    log.debug(
                        "campanha Display %s sem cpc_bid_micros: esperado em "
                        "MAXIMIZE_CONVERSIONS", campanha)
                lance = None

            alvos = sorted(set(metas.get(campanha, [])))
            saida[campanha] = {
                "lance_micros": lance,
                # A meta de custo, quando há UMA. Divergente vira `null` pela
                # mesma razão do lance: escolher uma descreveria um teto que não
                # existe para metade da campanha.
                "tcpa_micros": alvos[0] if len(alvos) == 1 else None,
                **destino,
            }
        return saida


PERFIL = PerfilDisplay()

# O registro acontece no import, e o import acontece dentro de
# `resolver_perfil()`. Assim o núcleo continua sem citar Display em tempo de
# carga, e um canal novo é um arquivo a mais — não uma linha a mais no núcleo.
sinc.registrar_perfil(PERFIL)
