"""O perfil de Performance Max — o canal que NÃO tem grupo nem anúncio.

## Por que ele não pode ser uma cópia de Search

PMax é o único canal sem `AdGroup` e sem `Ad`: o Google monta a combinação a
partir dos assets ligados ao **asset group**. Uma consulta `FROM ad_group_ad`
aqui não devolve pouco — devolve VAZIO, sempre. E vazio lido como "não há
duplicidade" foi um defeito real, corrigido em `canario._AUTORIDADE_DE_URL`:
a prova de destino de PMax nunca provou nada enquanto perguntou no lugar errado.

Este módulo exercita a MESMA autoridade que `canario` declara — `asset_group` /
`asset_group.final_urls` — em vez de reescrevê-la.

## O que ele lê, e o que ele declara

**Não há lance.** PMax aceita `MAXIMIZE_CONVERSIONS` e
`MAXIMIZE_CONVERSION_VALUE`, e não tem CPC de grupo porque não tem grupo.
`lance_micros` é `None` ESTRUTURAL, declarado e não descoberto.

**A URL é exclusiva por contrato.** Em Search e Display, várias URLs finais
significam "não há UMA URL" e o espelho declara `null`. Em PMax, o contrato desta
casa exige `final_urls = [LP aprovada]` — exatamente uma. Mais de uma não é
ambiguidade de medição: é `DIVERGENCIA_URL_EXCLUSIVA`, e o inventário registra o
fato em `urls_finais_lidas` para que a divergência seja investigável em vez de
virar um `null` mudo.

Somente leitura: GAQL só tem SELECT, e a query passa pelo `_exigir_leitura` do
núcleo antes de sair.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, Sequence, Tuple

from app.trafego import inventario as inv
from app.trafego import sincronizador as sinc

log = logging.getLogger("volc.trafego.adaptador_pmax")

#: A URL final e o estado do ASSET GROUP — a autoridade de PMax.
#:
#: ⚠️ `FROM asset_group`, e nunca `FROM ad_group_ad`. É a mesma tabela que
#: `canario._AUTORIDADE_DE_URL["PERFORMANCE_MAX"]` declara, e o motivo é o
#: mesmo: PMax não tem anúncio, então a segunda consulta voltaria vazia sempre.
GAQL_ASSET_GROUP = """
SELECT campaign.id, asset_group.id, asset_group.status, asset_group.final_urls
FROM asset_group
WHERE campaign.id IN ({ids}) AND asset_group.status != 'REMOVED'
"""

LOTE_DE_IDS = 200


class PerfilPerformanceMax:
    """O perfil de varredura de Performance Max."""

    canal = inv.PERFORMANCE_MAX

    def entidades_filhas(self) -> Tuple[str, ...]:
        # UMA entidade, e não duas. PMax não tem grupo de anúncios nem anúncio;
        # declarar dois rótulos faria o `faltou` do núcleo dizer que faltou ler
        # algo que não existe.
        return ("grupo de recursos (URL final e estado)",)

    def ler_filhas(self, buscar: Callable[[str], Iterable[Any]],
                   campaign_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        ids = [str(i) for i in campaign_ids if str(i or "").strip()]
        if not ids:
            return {}

        urls: Dict[str, set] = {}
        estados: Dict[str, set] = {}
        grupos: Dict[str, set] = {}
        leu = True
        try:
            for inicio in range(0, len(ids), LOTE_DE_IDS):
                lote = ids[inicio:inicio + LOTE_DE_IDS]
                for row in buscar(GAQL_ASSET_GROUP.format(ids=",".join(lote))):
                    alvo = str(row.campaign.id)
                    grupo = getattr(row, "asset_group", None)
                    ident = getattr(grupo, "id", None)
                    if ident:
                        grupos.setdefault(alvo, set()).add(str(ident))
                    estado = getattr(grupo, "status", None)
                    nome = getattr(estado, "name", None) or (
                        str(estado) if estado is not None else "")
                    if nome:
                        estados.setdefault(alvo, set()).add(str(nome))
                    for u in (getattr(grupo, "final_urls", None) or ()):
                        texto = str(u or "").strip()
                        if texto:
                            urls.setdefault(alvo, set()).add(texto)
        except Exception as exc:  # noqa: BLE001
            # ⚠️ `leu = False` impede a falha de virar APAGAMENTO. O payload do
            # espelho é uniformizado: sem esta guarda, uma leitura que quebrou
            # mandaria `null` para todas as campanhas PMax da conta, e a
            # reconciliação voltaria a oferecer duplicação.
            leu = False
            log.warning("não consegui ler o asset group de Performance Max: %s",
                        exc)

        saida: Dict[str, Dict[str, Any]] = {}
        for campanha in ids:
            linha: Dict[str, Any] = {
                # Ausência DECLARADA: PMax não tem grupo, logo não tem CPC.
                "lance_micros": None,
            }
            if leu:
                achados = sorted(urls.get(campanha, ()))
                linha["url_final"] = achados[0] if len(achados) == 1 else None
                # ⚠️ A LISTA INTEIRA VIAJA. Em PMax, `len(final_urls) > 1` é
                # divergência de contrato (a URL é exclusiva), não ambiguidade
                # de medição — e um `null` sozinho esconderia justamente o fato
                # que precisa ser investigado.
                linha["urls_finais_lidas"] = achados
                vistos = sorted(estados.get(campanha, ()))
                linha["asset_group_status"] = (
                    vistos[0] if len(vistos) == 1 else None)
                linha["asset_groups_lidos"] = len(grupos.get(campanha, ()))
                if len(achados) > 1:
                    log.info(
                        "campanha PMax %s tem %d URLs finais no asset group; a "
                        "URL desta receita é EXCLUSIVA, então isto é "
                        "divergência e não ambiguidade de leitura",
                        campanha, len(achados))
            saida[campanha] = linha
        return saida


PERFIL = PerfilPerformanceMax()

sinc.registrar_perfil(PERFIL)
