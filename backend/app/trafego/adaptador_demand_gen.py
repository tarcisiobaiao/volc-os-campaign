"""O perfil de Demand Gen — e o campo de LEITURA que não é o de escrita.

## As três diferenças que este canal impõe

**Não há lance.** Demand Gen só aceita `MAXIMIZE_CONVERSIONS`, e sem meta
numérica (`campanha/demand_gen.py:LANCES_PERMITIDOS`). `lance_micros` é `None`
ESTRUTURAL: o adaptador declara a ausência em vez de consultar
`cpc_bid_micros` para descobri-la. Consultar seria pior que inútil — devolveria
sempre vazio, e vazio lido como "não consegui medir" faria uma característica do
canal parecer uma falha de leitura, que é o defeito que a autoridade de URL de
PMax já sofreu.

**A superfície é lida por outro campo.** O pedido escreve
`ad_group.demand_gen_ad_group_settings.channel_controls`; a conta responde em
`channel_config`, que é **output only**. Ler o campo de escrita de volta traria
o que MANDAMOS, não o que a conta APLICOU — e a divergência entre os dois é
exatamente o que o read-back existe para encontrar.

**A URL continua no anúncio.** O `Ad` de Demand Gen é
`demand_gen_multi_asset_ad`, mas `final_urls` continua morando no `Ad` — mesma
autoridade de Search e Display, e é o que `canario._AUTORIDADE_DE_URL` declara.

Somente leitura: GAQL só tem SELECT, e a query passa pelo `_exigir_leitura` do
núcleo antes de sair.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, Sequence, Tuple

from app.trafego import inventario as inv
from app.trafego import sincronizador as sinc

log = logging.getLogger("volc.trafego.adaptador_demand_gen")

#: A superfície EFETIVA, pelo campo de leitura.
#:
#: ⚠️ `channel_config`, e NUNCA `channel_controls`. O segundo é o que se manda;
#: o primeiro é o que a conta aplicou. Ler o campo de escrita de volta produziria
#: um read-back que sempre concorda consigo mesmo.
GAQL_SUPERFICIES = """
SELECT campaign.id, ad_group.id,
       ad_group.demand_gen_ad_group_settings.channel_controls.channel_config
FROM ad_group WHERE campaign.id IN ({ids}) AND ad_group.status != 'REMOVED'
"""

#: A URL de destino, do anúncio multi-asset.
GAQL_URL_FINAL = """
SELECT campaign.id, ad_group_ad.ad.final_urls
FROM ad_group_ad WHERE campaign.id IN ({ids}) AND ad_group_ad.status != 'REMOVED'
"""

LOTE_DE_IDS = 200


class PerfilDemandGen:
    """O perfil de varredura de Demand Gen."""

    canal = inv.DEMAND_GEN

    def entidades_filhas(self) -> Tuple[str, ...]:
        return ("grupo de anúncios (superfícies)",
                "anúncio multi-asset (URL final)")

    def ler_filhas(self, buscar: Callable[[str], Iterable[Any]],
                   campaign_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        ids = [str(i) for i in campaign_ids if str(i or "").strip()]
        if not ids:
            return {}

        superficies: Dict[str, set] = {}
        leu_superficies = True
        try:
            for inicio in range(0, len(ids), LOTE_DE_IDS):
                lote = ids[inicio:inicio + LOTE_DE_IDS]
                for row in buscar(GAQL_SUPERFICIES.format(ids=",".join(lote))):
                    alvo = str(row.campaign.id)
                    ajustes = getattr(row.ad_group,
                                      "demand_gen_ad_group_settings", None)
                    controles = getattr(ajustes, "channel_controls", None)
                    config = getattr(controles, "channel_config", None)
                    nome = getattr(config, "name", None) or (
                        str(config) if config is not None else "")
                    if nome:
                        superficies.setdefault(alvo, set()).add(str(nome))
        except Exception as exc:  # noqa: BLE001
            leu_superficies = False
            log.warning(
                "não consegui ler as superfícies aplicadas de Demand Gen: %s",
                exc)

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
            leu_urls = False
            log.warning("não consegui ler a URL final dos anúncios Demand Gen: %s",
                        exc)

        saida: Dict[str, Dict[str, Any]] = {}
        for campanha in ids:
            linha: Dict[str, Any] = {
                # ⚠️ AUSÊNCIA DECLARADA, não medida. Demand Gen não tem lance:
                # o canal aceita `MAXIMIZE_CONVERSIONS` sem meta numérica, e não
                # existe `cpc_bid_micros` para consultar. Declarar aqui é o que
                # impede o inventário de exibir "não consegui medir" para um
                # fato que simplesmente não existe neste canal.
                "lance_micros": None,
            }
            if leu_urls:
                achados = sorted(urls.get(campanha, ()))
                if len(achados) > 1:
                    log.info(
                        "campanha Demand Gen %s tem %d URLs finais distintas; "
                        "o espelho declara `null` em vez de escolher uma",
                        campanha, len(achados))
                linha["url_final"] = achados[0] if len(achados) == 1 else None
            if leu_superficies:
                vistas = sorted(superficies.get(campanha, ()))
                # Uma campanha com grupos em superfícies diferentes não tem UMA
                # superfície. `null` em vez de escolher, pela mesma razão do
                # lance de Search.
                linha["superficies"] = vistas[0] if len(vistas) == 1 else None
            saida[campanha] = linha
        return saida


PERFIL = PerfilDemandGen()

sinc.registrar_perfil(PERFIL)
