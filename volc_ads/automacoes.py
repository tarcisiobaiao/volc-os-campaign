"""As automações de criativo que esta casa RECUSA — declaradas uma vez.

## Por que elas saíram dos builders

Cada canal emitia a sua lista dentro do módulo que monta o payload
(`campanha/comum.py` para PMax, `campanha/demand_gen.py` para Demand Gen). Isso
estava certo enquanto o único leitor era o próprio builder. Deixou de estar
quando a TELA passou a ter de mostrá-las como fatos travados (T13): o backend
não pode importar `volc_ads.campanha.*` no boot — esses módulos arrastam
`google.ads.googleads` —, então a tela ficaria com uma segunda lista escrita à
mão, que divergiria no primeiro nome que só uma ganhasse.

Aqui elas ficam em stdlib pura, os builders as REFERENCIAM (não copiam) e o
contrato de canal do Hub as lê para desenhar um chip por automação. Uma verdade,
três leitores.

## Por que a ordem é estável

O selo do plano cobre a lista: duas provas semanticamente iguais não podem gerar
protobufs diferentes. Reordenar aqui muda a impressão do payload.

## Por que elas existem

Todas nascem LIGADAS quando ninguém fala — omitir NÃO é neutro. Cada uma quebra
uma das duas promessas que a receita desta casa faz: o clique vai para a LP
aprovada, e a peça veiculada é a peça aprovada.
"""

from __future__ import annotations

from typing import Dict, Mapping, Tuple

#: Demand Gen — três, e elas vivem no AD GROUP AD.
#:
#: ⚠️ `AdGroupAd.ad_group_ad_asset_automation_settings`, e NÃO
#: `Campaign.asset_automation_settings` como em PMax. Conferido no proto v25
#: instalado. O work breakdown do spec pedia nível de campanha; o campo de
#: campanha não governa `DemandGenMultiAssetAd`, e emitir ali deixaria as três
#: ligadas no objeto que de fato as consulta.
AUTOMACOES_DEMAND_GEN_RECUSADAS: Tuple[str, ...] = (
    "GENERATE_DESIGN_VERSIONS_FOR_IMAGES",
    "GENERATE_VIDEOS_FROM_OTHER_ASSETS",
    "GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS",
)

#: Performance Max — CINCO, e elas vivem na CAMPANHA.
#:
#: ⚠️ São cinco, e o comentário do builder dizia "as QUATRO automações" mesmo
#: depois de a quinta entrar. A quinta (`GENERATE_IMAGE_EXTRACTION`) não estava
#: no work breakdown: veio da revisão de contrato de API e sobreviveu à
#: conferência local no proto v25. As outras quatro protegem o DESTINO e a COPY;
#: esta protege a PEÇA — sem ela o anúncio pode veicular uma imagem raspada da
#: landing page, que nunca passou pelo portão de política, nunca teve
#: `content_sha256` e não está no `supply_sha256` do plano aprovado.
AUTOMACOES_PMAX_RECUSADAS: Tuple[str, ...] = (
    "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
    "TEXT_ASSET_AUTOMATION",
    "GENERATE_IMAGE_ENHANCEMENT",
    "GENERATE_ENHANCED_YOUTUBE_VIDEOS",
    "GENERATE_IMAGE_EXTRACTION",
)

#: Onde cada canal declara as automações — o campo do proto, por nome.
#: A tela mostra isto para o operador saber que os dois canais travam a mesma
#: coisa em lugares diferentes da árvore.
CAMPO_DA_AUTOMACAO: Mapping[str, str] = {
    "DEMAND_GEN": "ad_group_ad.ad_group_ad_asset_automation_settings",
    "PERFORMANCE_MAX": "campaign.asset_automation_settings",
}

#: O que cada automação faria se ficasse ligada — em uma frase que o operador lê.
#: ⚠️ Não é decoração: um chip "DESLIGADA" sem a consequência ensina o operador a
#: tratar a trava como ruído de tela.
POR_QUE_RECUSADA: Mapping[str, str] = {
    "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION":
        "mandaria o clique para outra página do site, escolhida pelo Google. O "
        "destino aprovado deixaria de ser o destino servido.",
    "TEXT_ASSET_AUTOMATION":
        "geraria texto novo. A copy aprovada deixaria de ser a copy servida.",
    "GENERATE_IMAGE_ENHANCEMENT":
        "alteraria a imagem aprovada, e o `supply_sha256` do selo deixaria de "
        "descrever o que veicula.",
    "GENERATE_ENHANCED_YOUTUBE_VIDEOS":
        "geraria vídeo a partir dos assets, sem aprovação de peça nenhuma.",
    "GENERATE_IMAGE_EXTRACTION":
        "raspa imagens DA LANDING PAGE para o pool visual da campanha — peça "
        "que nunca passou pelo portão de política nem tem hash.",
    "GENERATE_DESIGN_VERSIONS_FOR_IMAGES":
        "geraria versões de design das imagens aprovadas.",
    "GENERATE_VIDEOS_FROM_OTHER_ASSETS":
        "montaria vídeo a partir de outros assets da campanha.",
    "GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS":
        "geraria imagem animada a partir de outros assets da campanha.",
}

#: O estado em que todas viajam. Uma constante e não um literal repetido: é ela
#: que a tela mostra e que o read-back compara.
OPTED_OUT = "OPTED_OUT"

_POR_CANAL: Dict[str, Tuple[str, ...]] = {
    "DEMAND_GEN": AUTOMACOES_DEMAND_GEN_RECUSADAS,
    "PERFORMANCE_MAX": AUTOMACOES_PMAX_RECUSADAS,
}


def recusadas(canal: str) -> Tuple[str, ...]:
    """As automações que ESTE canal desliga. Vazio = o canal não as declara.

    ⚠️ Vazio NÃO é "o canal não tem automação": Search e Display não emitem
    `asset_automation_settings` nesta receita, e Display trava o equivalente por
    `control_spec` (dois booleanos `false` no anúncio). Ausência aqui é o
    contrato deste campo, não uma afirmação sobre o canal inteiro.
    """
    bruto = str(canal or "").strip().upper()
    nome = "PERFORMANCE_MAX" if bruto == "PMAX" else bruto
    return _POR_CANAL.get(nome, ())
