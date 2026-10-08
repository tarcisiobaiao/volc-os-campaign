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

#: Demand Gen, formato VÍDEO RESPONSIVO — quatro, também no AD GROUP AD.
#:
#: ⚠️ Automação de criativo em Demand Gen é por TIPO DE ANÚNCIO: um tipo de
#: multi-asset num anúncio de vídeo devolve `enum_error.ENUM_VALUE_NOT_PERMITTED`
#: (medido em validate_only na Crédito Up, 08/10/2026). Por isso estas quatro
#: são uma lista própria, e não um acréscimo às três de cima: cada formato
#: declara as SUAS. Carrossel não tem automação ad-level na v25.
AUTOMACOES_DEMAND_GEN_VIDEO_RECUSADAS: Tuple[str, ...] = (
    "GENERATE_LANDING_PAGE_PREVIEW",
    "GENERATE_LANDING_PAGE_TEXT",
    "GENERATE_SHORTER_YOUTUBE_VIDEOS",
    "GENERATE_VERTICAL_YOUTUBE_VIDEOS",
)

#: Performance Max v25.2 — as DUAS que a API passou a aceitar em PMax e que o
#: builder declara OPTED_OUT depois das cinco históricas (`pmax_config.
#: AUTOMACOES_PMAX_V25`, na mesma ordem: as cinco primeiro, estas no fim).
#:
#: ⚠️ Lista SEPARADA de `AUTOMACOES_PMAX_RECUSADAS`, e não acréscimo a ela: as
#: cinco são o prefixo exato do que viaja e o selo de planos já aprovados cobre
#: a ordem. Diferente das cinco, estas duas podem ser OPTADAS pelo dono
#: (`ConfiguracaoPMaxV25.automacoes_optadas`); o default continua OPTED_OUT.
AUTOMACOES_PMAX_V25_NOVAS: Tuple[str, ...] = (
    "AUTOMATED_VIDEO_CRAWL",
    "GENERATE_DESIGN_VERSIONS_FOR_IMAGES",
)

#: Todas as que o payload de PMax declara, na ordem em que viajam.
AUTOMACOES_PMAX: Tuple[str, ...] = AUTOMACOES_PMAX_RECUSADAS + AUTOMACOES_PMAX_V25_NOVAS

#: As automações de Demand Gen POR FORMATO de anúncio — a mesma tabela de
#: `campanha/demand_gen_config.AUTOMACOES_POR_FORMATO` (teste confere), aqui
#: em stdlib pura para a tela.
AUTOMACOES_DEMAND_GEN_POR_FORMATO: Mapping[str, Tuple[str, ...]] = {
    "MULTI_ASSET": AUTOMACOES_DEMAND_GEN_RECUSADAS,
    "VIDEO_RESPONSIVO": AUTOMACOES_DEMAND_GEN_VIDEO_RECUSADAS,
    "CARROSSEL": (),
}

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
    # ── Demand Gen, vídeo responsivo ───────────────────────────────────────
    "GENERATE_LANDING_PAGE_PREVIEW":
        "geraria imagem com prévia da landing page — peça sem portão de "
        "política nem hash.",
    "GENERATE_LANDING_PAGE_TEXT":
        "geraria texto a partir da landing page. A copy aprovada deixaria de "
        "ser a copy servida.",
    "GENERATE_SHORTER_YOUTUBE_VIDEOS":
        "cortaria o vídeo aprovado em versões mais curtas, escolhidas pelo "
        "Google.",
    "GENERATE_VERTICAL_YOUTUBE_VIDEOS":
        "geraria versão vertical do vídeo aprovado, com enquadramento escolhido "
        "pelo Google.",
    # ── Performance Max v25.2 ──────────────────────────────────────────────
    "AUTOMATED_VIDEO_CRAWL":
        "buscaria vídeos nas URLs declaradas (landing page, rede social, canal "
        "do YouTube) e os veicularia — peça que nunca passou pelo portão de "
        "política. Ligar exige declarar as fontes e os direitos sobre os vídeos.",
}

#: Para a tela: em que formato de anúncio cada automação de Demand Gen vale.
#: PMax não tem formato (a campanha inteira é uma combinação), e fica de fora.
FORMATO_DA_AUTOMACAO: Mapping[str, str] = {
    nome: formato
    for formato, nomes in AUTOMACOES_DEMAND_GEN_POR_FORMATO.items()
    for nome in nomes
}

#: O estado em que todas viajam. Uma constante e não um literal repetido: é ela
#: que a tela mostra e que o read-back compara.
OPTED_OUT = "OPTED_OUT"

#: ⚠️ Demand Gen lista as SETE (três de multi-asset + quatro de vídeo): a tela
#: mostra o que o canal trava, e cada anúncio leva só as do seu formato
#: (`FORMATO_DA_AUTOMACAO` diz qual). PMax lista as SETE que o payload declara.
_POR_CANAL: Dict[str, Tuple[str, ...]] = {
    "DEMAND_GEN": AUTOMACOES_DEMAND_GEN_RECUSADAS + AUTOMACOES_DEMAND_GEN_VIDEO_RECUSADAS,
    "PERFORMANCE_MAX": AUTOMACOES_PMAX,
}


def recusadas(canal: str, formato: str | None = None) -> Tuple[str, ...]:
    """As automações que ESTE canal desliga. Vazio = o canal não as declara.

    `formato` (só Demand Gen) restringe às do tipo de anúncio — é a lista que
    um anúncio daquele formato de fato carrega.

    ⚠️ Vazio NÃO é "o canal não tem automação": Search e Display não emitem
    `asset_automation_settings` nesta receita, e Display trava o equivalente por
    `control_spec` (dois booleanos `false` no anúncio). Ausência aqui é o
    contrato deste campo, não uma afirmação sobre o canal inteiro.
    """
    bruto = str(canal or "").strip().upper()
    nome = "PERFORMANCE_MAX" if bruto == "PMAX" else bruto
    if formato is not None and nome == "DEMAND_GEN":
        return AUTOMACOES_DEMAND_GEN_POR_FORMATO.get(str(formato).strip().upper(), ())
    return _POR_CANAL.get(nome, ())
