"""Construtor de campanha de Display — a primeira fatia vertical do canal.

Mesmo desenho de `search.py`: UMA transação atômica, nada de chamada
encadeada. O grafo é

    budget → campanha (DISPLAY) → geo → idioma → ad group (DISPLAY_STANDARD)
           → responsive display ad (títulos, título longo, descrições, nome do
             negócio, imagens por papel e vídeos)

Tudo entra ou nada entra.

## O que Display herda de Search, e o que ele recusa

Herda tudo o que é julgamento de TEXTO — `campanha/conteudo.py`: contagem,
comprimento contado como o Google conta, duplicata, o portão país × vertical de
`policy/spec.py`, a exceção da caixa alta e a tradução de `Violacao` em achado.
Herda também os blocos de operação de `campanha/comum.py`: orçamento, campanha,
geo, idioma e ad group, com as MESMAS faixas de id temporário.

Recusa três coisas que Search permite, e as três recusas são de leilão ou de
formato, não de gosto:

1. **`estrategia_lance = "MANUAL_CPC"`.** É o padrão da casa e vale só para
   Search. `matriz-api/display.md` §8 mediu a tabela oficial de estratégias e
   `MANUAL_CPC` cai na linha `[NÃO CONFIRMADO]` — "compatibilidade específica
   com DISPLAY não é declarada canal a canal". Além disso
   `comum.op_campanha()` já não lê o campo no ramo DISPLAY: a campanha
   nasceria em MaxConv de qualquer jeito. Ignorar em silêncio faria o número
   que o operador digitou virar decoração, que é exatamente o defeito que o
   `MANUAL_CPC` de Search existe para não ter.
2. **DKI (`{KeyWord:…}`).** Display não casa keyword: a tag renderiza SEMPRE o
   fallback. Aceitá-la seria deixar o operador escrever um texto que ele acha
   dinâmico e não é.
3. **`ai_max`.** `campaign.ai_max_setting` é campo de Search. Quem barra é o
   perfil do canal (`campanha/perfil.py`), antes de o construtor rodar.

## O que a primeira fatia AINDA não monta, e por que isso é declarado

**Segmentação.** Um ad group de Display sem critério roda em inventário aberto,
escolhido pelo lance. É o comportamento padrão da API e é uma campanha que
veicula — mas não é a que a operação quer.

`matriz-api/display.md` §7 confirma como positivos e `[alta]` os critérios
Topic, User list, Custom audience, Custom intent (só ad group), Custom affinity,
Combined audience, faixa etária, gênero e faixa de renda. Eles entram na
próxima fatia.

⚠️ **Placement positivo NÃO entra, e a razão é uma contradição de fonte, não
falta de tempo.** A tabela oficial de critérios marca Placement como positivo
❌ / negativo ✅ (conferido no HTML, não só no texto extraído), enquanto
`Campaign.network_settings.target_content_network` descreve a rede como "ads
served on **specified placements** … specified using the Placement criterion" —
o que pressupõe o positivo. A matriz marca `[NÃO CONFIRMADO]` e recomenda
provar por `validate_only`; essa prova não pode ser feita nesta rodada. Entre
duas leituras oficiais que se contradizem, codificar uma é escolher no
cara-ou-coroa e descobrir no lote. Exclusão por posicionamento (negativo) é
onde as duas fontes concordam e é por onde a próxima fatia começa.

Enquanto isso, o construtor AVISA em voz alta em vez de fingir que segmentou.

**Sitelink, callout e snippet.** São assets de campanha que Search monta. A
matriz de Display não declara quais tipos servem neste canal nem em que
`field_type` — §1 lista `CampaignAssetSet` (remarketing dinâmico) e nada de
extensão de texto. Montar por analogia com Search subiria asset que não
veicula.

**Um ad group, não N.** `brief.sub_intencoes` particiona KEYWORDS, e Display
não opera keyword nesta fatia. N ad groups com o mesmo anúncio e a mesma
(ausência de) segmentação só repartiriam a verba por sorteio. Quando a
segmentação entrar, cada grupo passa a ter público próprio e a partição volta a
significar alguma coisa.

## Faixas de id temporário: Display não abre família nova

Budget `-1`, campanha `-2`, ad group `-3` — as mesmas de `comum.py`. A faixa de
asset (`-100` para baixo) **fica intocada**: as imagens e os vídeos chegam como
resource names de Asset JÁ CRIADO, vindos do motor de criativo, e resource name
real não é id temporário. Por isso `_checar_imagens()` recusa id negativo: um
`customers/123/assets/-100` no payload apontaria para o vão da faixa de Search e
o sintoma apareceria em outro recurso.
"""

from __future__ import annotations

import hashlib
import re

from ..gads.client import cliente, validar_mutacoes
from . import comum, conteudo, plano, taxonomia, validacao
from .brief import Brief, ImagemParaSubir, ImagensDisplay

CANAL = "DISPLAY"

#: As estratégias de lance que ESTE canal aceita. Declarado aqui, no módulo do
#: canal, e lido por `campanha/perfil.py` — a dependência aponta canal → índice,
#: nunca o contrário, e por isso não há ciclo de import.
#:
#: `MANUAL_CPC` fica de fora porque Display não tem CPC manual como opção
#: razoável: sem termo de busca, o lance manual não tem sinal nenhum para
#: filtrar inventário.
LANCES_PERMITIDOS: tuple[str, ...] = ("MAXIMIZE_CONVERSIONS",)

#: Opções de construção que este canal aceita além do brief. Vazio: `ai_max` é
#: de Search e não existe aqui.
OPCOES: frozenset[str] = frozenset()

#: Papel → campo do proto. Só a TRADUÇÃO mora aqui; a ORDEM mora em
#: `ImagensDisplay.PAPEIS`, porque quem percorre as imagens fora deste módulo
#: (o recibo, via `linhagens()`) precisa da mesma sequência e não pode importar
#: o construtor. Duas declarações da mesma ordem divergiriam em silêncio, e o
#: sintoma seria a procedência da logo carimbada no banner.
_CAMPO_DO_PROTO: dict[str, str] = {
    "marketing": "marketing_images",
    "marketing_quadrada": "square_marketing_images",
    "logo": "logo_images",
    "logo_quadrado": "square_logo_images",
}

PAPEIS_DE_IMAGEM: tuple[tuple[str, str], ...] = tuple(
    (papel, _CAMPO_DO_PROTO[papel]) for papel in ImagensDisplay.PAPEIS
)

# `customers/8017851692/assets/123456` — o resource name de um Asset REAL.
# O id tem de ser positivo: negativo é id temporário, e id temporário aqui
# invadiria a faixa de asset que `comum.py` reserva para Search.
_RESOURCE_ASSET = re.compile(r"^customers/(\d+)/assets/(-?\d+)$")

_EXPLICACAO_DKI = (
    "Display não casa keyword, então {KeyWord:…} renderiza SEMPRE o fallback — "
    "escreva o texto do fallback direto no campo"
)


def construir(cid: str, brief: Brief, *, login_customer_id: str):
    """Monta as operações e valida o conteúdo localmente.

    Devolve (operacoes, resultado_da_validacao). Mesma assinatura de
    `search.construir`, menos o `ai_max` — que é campo de Search e por isso não
    existe aqui. Se `resultado.ok` for False, NÃO envie.
    """
    r = validacao.Resultado()
    ts = comum.carimbo()
    base = conteudo.nome_da_campanha(
        brief, ts, marcador=taxonomia.MODIFICADOR[CANAL]
    )

    _recusar_o_que_e_de_search(brief, r)
    _avisar_o_que_a_fatia_ainda_nao_monta(brief, r)

    # O mesmo portão país × vertical de Search. Display não tem desconto de
    # política: o anúncio de um portal informativo vendendo empréstimo é
    # reprovado no conteúdo tanto quanto na busca.
    pol = conteudo.abrir_portao(brief, r)

    headlines = conteudo.forma(brief.copy.headlines, "headline_display", r,
                               explicacao_dki=_EXPLICACAO_DKI)
    descriptions = conteudo.forma(brief.copy.descriptions, "description_display", r,
                                  explicacao_dki=_EXPLICACAO_DKI)
    longas = conteudo.forma(brief.copy.long_headlines, "long_headline_display", r,
                            explicacao_dki=_EXPLICACAO_DKI)
    # ⚠️ Contagens e limites: `matriz-api/display.md` §3, tabela "Texto",
    # confiança `[alta]`, fonte P (protos do SDK v25 instalado) —
    # headlines 1..5 ≤30, long_headline 1 obrigatório ≤90, descriptions 1..5
    # ≤90, business_name obrigatório ≤25 (este último com `[D4]` junto). Os
    # números moram em `limites.yaml`; número mágico não mora em código.
    if not brief.copy.long_headlines:
        # A mensagem de `forma()` ("0 itens, mínimo é 1") é verdadeira e muda
        # pouco: `long_headlines` é o campo que o brief comentava como "Demand
        # Gen" e quase ninguém preenche. Dizer ONDE preencher é o que separa
        # uma recusa de um enigma.
        r.erro("long_headline_display", "",
               "o responsive display ad EXIGE um título longo (≤90 chars) e o "
               "brief não trouxe nenhum — preencha `copy.long_headlines` com "
               "pelo menos um item; o construtor usa o primeiro")
    nomes = conteudo.forma([brief.copy.business_name], "business_name", r)
    if not brief.copy.business_name.strip():
        r.erro("business_name", "",
               "o responsive display ad leva o nome do anunciante em todo "
               "formato nativo — preencha `copy.business_name` (≤25 chars)")

    imagens = _checar_imagens(cid, brief, r)
    videos = _checar_videos(cid, brief, r)

    # Política sobre o texto que sobreviveu à forma. Por LISTA, como em Search:
    # duas regras do spec só existem no conjunto.
    conteudo.politica(pol, headlines, "headline_display", r)
    conteudo.politica(pol, descriptions, "description_display", r)
    conteudo.politica(pol, longas, "long_headline_display", r)
    conteudo.politica(pol, nomes, "business_name", r)

    if not r.ok:
        return [], r

    # A autenticação é uma dependência de MONTAGEM, não de validação local.
    # Instanciar o cliente antes deste portão fazia um brief já inválido tentar
    # renovar OAuth e mascarava os achados locais quando a rede estava fora.
    # Além de tornar a prova não determinística, isso confundia "Google não
    # respondeu" com "o contrato do anúncio está incompleto".
    c = cliente(login_customer_id)

    ops = [
        comum.op_budget(c, cid, brief, f"Budget_{ts}"),
        comum.op_campanha(c, cid, brief, base, CANAL),
        comum.op_geo(c, cid, brief),
        comum.op_idioma(c, cid, brief),
    ]

    # UM ad group. `indice=0` mantém o id temporário -3, o mesmo primeiro id que
    # Search usa — a faixa é compartilhada e a disciplina também.
    ops.append(
        comum.op_adgroup(c, cid, brief, f"AdGroup_{ts}", "DISPLAY_STANDARD",
                         indice=0)
    )
    ag = comum.temp_adgroup(cid, 0)

    # URL limpa. A marcação inteira vai no `final_url_suffix` da campanha, que
    # `comum.op_campanha()` montou com o contrato de DISPLAY — sem `{keyword}`
    # nem `{matchtype}`, que chegariam vazios neste canal.
    url = comum.url_destino(brief)

    o = c.get_type("MutateOperation")
    ada = o.ad_group_ad_operation.create
    ada.ad_group = ag
    ada.status = c.enums.AdGroupAdStatusEnum.ENABLED
    ada.ad.final_urls.append(url)
    rda = ada.ad.responsive_display_ad

    for t in headlines:
        a = c.get_type("AdTextAsset")
        a.text = t
        rda.headlines.append(a)
    # `long_headline` é campo SINGULAR no proto, não repetido. `forma()` já
    # cortou a lista em 1 item por `limites.yaml`; o índice 0 é o único.
    rda.long_headline.text = longas[0]
    for t in descriptions:
        a = c.get_type("AdTextAsset")
        a.text = t
        rda.descriptions.append(a)
    rda.business_name = nomes[0]

    # ── as imagens: resource name pronto, ou asset que nasce aqui ──────────
    #
    # Os dois caminhos convivem de propósito. `str` é o asset que já existe na
    # conta — quem o criou foi outra rodada, e o construtor só o referencia.
    # `ImagemParaSubir` é o asset que ainda não existe: ele vira uma
    # `asset_operation` NESTA MESMA requisição, com os bytes dentro, e o anúncio
    # o referencia pelo id temporário.
    #
    # ⚠️ A ordem importa e não é estética: a API resolve id temporário só
    # DEPOIS de ele ser definido. Por isso as operações de asset são acumuladas
    # aqui e inseridas ANTES da operação do anúncio, alguns blocos abaixo.
    ops_de_asset: list = []
    for atributo, campo in PAPEIS_DE_IMAGEM:
        destino = getattr(rda, campo)
        for item in getattr(imagens, atributo):
            if isinstance(item, ImagemParaSubir):
                rn = comum.temp_imagem(cid, len(ops_de_asset))
                oa = c.get_type("MutateOperation")
                cria = oa.asset_operation.create
                cria.resource_name = rn
                cria.name = item.nome
                cria.type_ = c.enums.AssetTypeEnum.IMAGE
                cria.image_asset.data = item.dados
                ops_de_asset.append(oa)
            else:
                rn = item
            img = c.get_type("AdImageAsset")
            img.asset = rn
            destino.append(img)

    for rn in videos:
        vid = c.get_type("AdVideoAsset")
        vid.asset = rn
        rda.youtube_videos.append(vid)

    # Os assets entram ANTES do anúncio que os referencia — ver o comentário
    # sobre ordem, acima. Inserir depois faria a API recusar o mutate inteiro
    # com um erro sobre o ANÚNCIO, e o defeito estaria na ordem da lista.
    ops.extend(ops_de_asset)
    ops.append(o)
    return ops, r


# ── o que este canal recusa ────────────────────────────────────────────────


def _recusar_o_que_e_de_search(brief: Brief, r: validacao.Resultado) -> None:
    """Campos que o brief multicanal carrega e que Display não pode honrar.

    Recusar em vez de ignorar. `comum.op_campanha()` já não lê
    `estrategia_lance` no ramo DISPLAY: sem esta checagem, um brief com
    `MANUAL_CPC` subiria uma campanha em tCPA e o operador continuaria achando
    que declarou o lance.
    """
    if brief.estrategia_lance not in LANCES_PERMITIDOS:
        r.erro("estrategia_lance", brief.estrategia_lance,
               f"Display não aceita {brief.estrategia_lance} — sem termo de "
               f"busca o lance manual não tem sinal que filtre inventário. "
               f"Declare estrategia_lance='MAXIMIZE_CONVERSIONS' no brief "
               f"(com `tcpa` preenchido a campanha nasce em tCPA; sem ele, em "
               f"MaxConv puro). Aceitos aqui: {', '.join(LANCES_PERMITIDOS)}")

    if brief.ai_max:
        r.erro("ai_max", "True",
               "`campaign.ai_max_setting` é campo de Search e a API recusa o "
               "mutate de Display com ele. Deixe `ai_max=False` no brief")


def _avisar_o_que_a_fatia_ainda_nao_monta(brief: Brief, r: validacao.Resultado) -> None:
    """O que o brief traz, esta fatia não usa, e o operador precisa saber.

    Aviso e não erro: nenhum destes campos torna o payload inválido. O que eles
    tornam inválido é a EXPECTATIVA — e descartar em silêncio é o defeito que
    `Brief._checar_keywords_ou_sub_intencoes` já existe para não repetir do
    outro lado.
    """
    kws = list(brief.keywords) + [k for s in brief.sub_intencoes for k in s.keywords]
    if kws:
        r.aviso("keywords", f"{len(kws)} termos",
                "Display não opera keyword nesta fatia: a segmentação de "
                "conteúdo (tópicos, listas e posicionamento) entra quando a "
                "matriz de API do canal fixar campo e enum. As keywords do "
                "brief NÃO viram critério — a campanha veicula em inventário "
                "aberto, escolhido pelo lance")

    if len(brief.sub_intencoes) > 1:
        r.aviso("sub_intencoes", f"{len(brief.sub_intencoes)} grupos",
                "Display monta UM ad group nesta fatia. Sem segmentação por "
                "grupo, N grupos com o mesmo anúncio repartiriam a verba por "
                "sorteio em vez de por intenção")

    # ⚠️ Conta pelo CONTRATO RESOLVIDO, não pelos campos antigos.
    #
    # Esta guarda lia só `negativas_campanha`/`negativas_adgroup`. Quando o
    # contrato tipado entrou, a ponte passou a mandar as duas listas VAZIAS e
    # tudo em `criterios` — então um pedido de Display com exclusões declaradas
    # deixava de emitir o aviso, e o operador recebia `aprovado: true` sem
    # nenhuma operação de exclusão e sem uma linha dizendo por quê.
    #
    # `brief.criterios` já é a resolução dos dois contratos (ver
    # `Brief._resolver_criterios`), então contar por ele vale para os dois.
    negativas = [c for c in brief.criterios if c.negativa]
    if negativas:
        r.aviso("negativas", f"{len(negativas)}",
                "as negativas do brief não entram no payload de Display nesta "
                "fatia — a exclusão de inventário é outro recurso e depende da "
                "matriz de API do canal")

    if brief.imagens and brief.imagens_display is None:
        # O erro de imagem ausente sai em `_checar_imagens`; aqui só se aponta
        # que a lista chapada existe e ficou de fora.
        r.aviso("imagens", f"{len(brief.imagens)} assets",
                "`brief.imagens` é uma lista chapada e não diz a proporção de "
                "cada asset — ver `imagens_display`")


# ── assets: o que chega pronto do motor de criativo ────────────────────────


def _checar_imagens(cid: str, brief: Brief, r: validacao.Resultado) -> ImagensDisplay:
    """As quatro famílias de imagem do RDA, contadas e conferidas.

    Devolve sempre um `ImagensDisplay` (vazio quando houve erro) para que o
    chamador não precise tratar `None`: quando `r.ok` é False nada é emitido.
    """
    lim = conteudo.LIM["display_asset"]
    im = brief.imagens_display
    if im is None:
        r.erro("imagens_display", "",
               "o responsive display ad exige imagem por PAPEL e o brief não "
               "trouxe nenhuma. Preencha `brief.imagens_display` "
               "(`ImagensDisplay`) com os resource names de Asset já criados: "
               "`marketing` (1.91:1, mín 600x314) e `marketing_quadrada` "
               "(1:1, mín 300x300) são obrigatórias; `logo` (4:1) e "
               "`logo_quadrado` (1:1) entram quando houver. Uma lista chapada "
               "não serve: o resource name não carrega a proporção",
               plano.ASSET_OBRIGATORIO_AUSENTE)
        return ImagensDisplay()

    # ⚠️ Só o `str` é resource name. Uma `ImagemParaSubir` é um asset que ainda
    # NÃO existe na conta — conferir formato de resource name nela seria exigir
    # que ela fosse o que ela declaradamente não é. O que ela precisa (nome e
    # bytes) já é exigido no `__post_init__` dela, e a geometria é conferida por
    # `volc_ads/criativo/validacao.py`, que é o dono dessa régua.
    #
    # As duas formas contam igual nos tetos abaixo: o que a API vê é o número de
    # imagens no anúncio, e de onde cada uma veio não muda o teto.
    novas = 0
    # ⚠️ IDENTIDADE POR CONTEÚDO, e a razão foi MEDIDA contra a API em
    # 01/09/2026, não deduzida.
    #
    # Um `validate_only` real na conta 547-809-6539 recusou o mutate inteiro com
    #
    #   asset_error.DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE
    #   @mutate_operations[7].asset_operation.create.name:
    #   "Duplicate assets across mutates cannot have different asset level fields."
    #
    # e, em cascata, três `mutate_error.RESOURCE_NOT_FOUND` no anúncio — porque
    # os ids temporários dos assets recusados deixaram de resolver. O payload
    # tinha dois `ImagemParaSubir` com os MESMOS BYTES em papéis diferentes
    # (quadrada e logo quadrado) e `name` diferente.
    #
    # O Google identifica asset pelo CONTEÚDO. Dois `asset_operation.create` com
    # a mesma imagem e nomes distintos são o mesmo asset pedindo dois nomes, e
    # ele recusa o request inteiro. Display não tinha essa guarda; Demand Gen
    # tinha, e a assimetria era invisível offline: a suíte ficava verde sobre um
    # payload que a API recusa.
    #
    # A recusa é local e antecipa exatamente o erro da API — inclusive quando os
    # papéis são diferentes, que é o caso legítimo mais provável (a mesma arte
    # servindo de quadrada e de logo). O conserto é usar o arquivo uma vez só;
    # deduplicar aqui em silêncio mudaria o payload sem o operador saber qual
    # dos dois papéis perdeu a imagem.
    identidades: dict[str, str] = {}
    for atributo, campo in PAPEIS_DE_IMAGEM:
        for item in getattr(im, atributo):
            if isinstance(item, ImagemParaSubir):
                novas += 1
                identidade = "bytes:" + hashlib.sha256(item.dados).hexdigest()
                rotulo = f"{atributo}/{item.nome}"
            else:
                _checar_resource_name(cid, item, f"imagens_display.{atributo}",
                                      campo, r)
                identidade = f"remoto:{str(item).strip()}"
                rotulo = f"{atributo}/{item}"

            anterior = identidades.get(identidade)
            if anterior is not None:
                r.erro(
                    f"imagens_display.{atributo}", rotulo,
                    f"asset repetido no mesmo mutate: este conteúdo já entra "
                    f"como {anterior}. O Google identifica asset pelo CONTEÚDO "
                    f"e recusa o request inteiro com "
                    f"asset_error.DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE "
                    f"(medido por validate_only em 01/09/2026). Use o arquivo "
                    f"uma vez só, ou envie artes diferentes por papel",
                    plano.ASSET_ACIMA_DO_TETO,
                )
                continue
            identidades[identidade] = rotulo

    # ⚠️ Imagem sem LINHAGEM entra, e fica registrada no `Resultado`.
    #
    # ATENÇÃO AO ALCANCE DESTE AVISO, porque ele é menor do que parece e a
    # revisão adversarial de 27/08/2026 mediu: `campanha/validacao.Resultado.ok`
    # ignora avisos, e `subir.preparar()` DESCARTA o `Resultado` inteiro no
    # caminho de sucesso — `Preparo` não tem campo para avisos. Ou seja: este
    # texto aparece para quem chama `construir()` direto, e NÃO chega à tela do
    # operador. Isso é anterior a esta fatia (o aviso antigo, "não foi medida",
    # tinha exatamente o mesmo destino) e continua aberto.
    #
    # ⚠️ ATÉ ONDE A LINHAGEM VAI, DE VERDADE. Esta frase já foi escrita errada
    # duas vezes, cada vez menos errada, e este é o estado conferido arquivo a
    # arquivo em 27/08/2026:
    #
    #   Preparo.linhagem / Recibo.linhagem    existem e são derivados do PAYLOAD
    #   projecao.preparo() / .recibo()        a CHAVE `linhagem` está no JSON
    #   ProvarEntrada (routers/trafego.py)    NÃO TEM CAMPO DE IMAGEM NENHUM
    #   src/types/trafego.ts                  não declara `linhagem`
    #   Lancamento.tsx                        nenhum componente a renderiza
    #
    # A consequência da terceira linha engole as outras: como o corpo HTTP não
    # tem onde receber imagem, `/provar` e `/subir` NUNCA constroem uma
    # `ImagemParaSubir`, e `linhagem` chega ao JSON **sempre vazia**. A chave
    # existe; o valor nunca é produzido por esse caminho.
    #
    # Hoje quem vê procedência é o operador que roda
    # `python -m volc_ads.criativo_ponte`, offline. Fechar o caminho HTTP e a
    # tela são duas pendências separadas, registradas como pendências — não
    # como feito.
    #
    # Desde 27/08/2026 `criativo/validacao.py` tem chamador fora de teste:
    # `volc_ads/criativo_ponte.py` roda `validar_lote()` antes de existir
    # qualquer `ImagemParaSubir`, e um lote reprovado não vira payload nenhum.
    # Então a pergunta deste bloco mudou. Ela não é mais "alguém mediu?" — é
    # "este arquivo passou pela ponte?".
    #
    # A diferença importa: medida presente sem linhagem quer dizer que alguém
    # preencheu `largura`/`altura` à mão, e nenhuma régua de proporção,
    # dimensão mínima ou mime foi aplicada. O número existe e não foi julgado.
    #
    # Continua sendo AVISO e não erro, e a razão não mudou: `display` não sabe
    # geometria, e um segundo juiz dela criaria as duas verdades que se quer
    # evitar. O que `display` pode afirmar sozinho é sobre a PRESENÇA da
    # linhagem — isso é fato dele, não pixel.
    for atributo, _campo in PAPEIS_DE_IMAGEM:
        for item in getattr(im, atributo):
            if not isinstance(item, ImagemParaSubir):
                continue
            if item.linhagem is None:
                r.aviso(f"imagens_display.{atributo}", item.nome,
                        "sem linhagem: não passou por `volc_ads/criativo_ponte."
                        "imagens_de_display()`, então nenhuma validação de "
                        "proporção, dimensão mínima ou mime a cobriu, e o "
                        "recibo não saberá dizer de onde ela veio. Monte o lote "
                        "pela ponte, ou aceite que a recusa virá da API")
            elif not item.linhagem.confirmada:
                # Passou pela ponte e ainda assim a procedência está incompleta
                # — motor não declarado, insumo perdido, medida ausente. Dizer
                # "veio da ponte, logo está confirmada" seria exatamente o
                # carimbo falso que `confirmada` existe para impedir.
                r.aviso(f"imagens_display.{atributo}", item.nome,
                        "linhagem incompleta: a origem foi registrada em parte "
                        "e não é rastro confiável. O recibo vai gravá-la com "
                        "`confirmada: false` — não a leia como procedência "
                        "estabelecida")

    if novas > comum.T_IMAGEM_MAX:
        r.erro("imagens_display", f"{novas} imagens novas",
               f"a faixa de id temporário de imagem comporta "
               f"{comum.T_IMAGEM_MAX} — acima disso os ids invadiriam outra "
               f"faixa e a referência apontaria para o asset errado, sem erro "
               f"de API porque os dois ids são válidos")

    # `matriz-api/display.md` §3, tabela "Imagens": mínimo de dimensão e
    # proporção por papel, teto combinado de 15 (marketing) e 5 (logo), e
    # "ao menos uma marketing_image e ao menos uma square_marketing_image são
    # obrigatórias". Confiança `[alta]`, fonte P + `[D4]`.
    #
    # ⚠️ Peso de arquivo e dimensão RECOMENDADA estão `[NÃO CONFIRMADO]` na
    # matriz — a doc oficial remete ao Help Center e não publica números. Por
    # isso este validador conta e confere resource name, e NÃO afirma nada
    # sobre bytes ou pixels. Reaproveitar os 5120 KB de PMax seria inventar
    # um limite de outro canal.
    if len(im.marketing) < lim["marketing_min"]:
        r.erro("imagens_display.marketing", f"{len(im.marketing)}",
               f"mínimo de {lim['marketing_min']} imagem 1.91:1 (mín 600x314) "
               f"— o proto do RDA diz 'at least one marketing_image is "
               f"required'. Sem ela o mutate inteiro é recusado")
    if len(im.marketing_quadrada) < lim["marketing_quadrada_min"]:
        r.erro("imagens_display.marketing_quadrada", f"{len(im.marketing_quadrada)}",
               f"mínimo de {lim['marketing_quadrada_min']} imagem 1:1 (mín "
               f"300x300) — o proto do RDA diz 'at least one square "
               f"marketing_image is required'")

    total_marketing = len(im.marketing) + len(im.marketing_quadrada)
    if total_marketing > lim["marketing_total_max"]:
        r.erro("imagens_display", f"{total_marketing} imagens de marketing",
               f"o teto é {lim['marketing_total_max']} somando `marketing` e "
               f"`marketing_quadrada` — corte antes de enviar")

    total_logo = len(im.logo) + len(im.logo_quadrado)
    if total_logo > lim["logo_total_max"]:
        r.erro("imagens_display", f"{total_logo} logos",
               f"o teto é {lim['logo_total_max']} somando `logo` e "
               f"`logo_quadrado`")
    if total_logo == 0:
        # ⚠️ AVISO e não erro, e a diferença é medida: o proto escreve "is
        # required" para as duas famílias de marketing e NÃO escreve para logo.
        # Barrar aqui recusaria localmente um payload que a API aceita.
        r.aviso("imagens_display.logo", "0",
                "sem logo o anúncio deixa de ser elegível para parte dos "
                "formatos nativos. O proto não a declara obrigatória, então "
                "não barramos — `docs/growth-engine/matriz-api/display.md` é "
                "quem promove isto a erro, se for o caso")

    return im


def _checar_videos(cid: str, brief: Brief, r: validacao.Resultado) -> list[str]:
    """`youtube_videos` do RDA — opcional, teto de 5 (proto v25).

    ⚠️ Duração mínima, proporção e resolução estão `[NÃO CONFIRMADO]` na
    matriz: o proto só declara a CONTAGEM. Os ≥10s e o 16:9/1:1/9:16 que
    circulam são da tabela de Performance Max, de outro canal — este validador
    não os aplica.
    """
    lim = conteudo.LIM["display_asset"]
    videos = [v for v in brief.videos if (v or "").strip()]
    for rn in videos:
        _checar_resource_name(cid, rn, "videos", "youtube_videos", r)
    if len(videos) > lim["video_max"]:
        r.erro("videos", f"{len(videos)}",
               f"o RDA aceita no máximo {lim['video_max']} vídeos do YouTube")
        return videos[: lim["video_max"]]
    return videos


def _checar_resource_name(
    cid: str, rn: str, campo: str, destino: str, r: validacao.Resultado
) -> None:
    """Um asset de Display precisa ser REAL, desta conta, e nunca temporário.

    Três defeitos que só apareceriam do lado do Google, com sintoma longe da
    causa:

    * formato torto (`assets/123` sem o `customers/`) vira
      `RESOURCE_NAME_MALFORMED` sobre o anúncio inteiro;
    * asset de OUTRA conta responde `RESOURCE_NOT_FOUND` — e a conta que não
      achou é a do mutate, não a dona do asset, o que manda procurar no lugar
      errado;
    * id NEGATIVO é id temporário. Ele invadiria a faixa que `comum.py` reserva
      (`-100` para baixo) e passaria a apontar para outro recurso do mesmo
      mutate — a colisão que não avisa.
    """
    m = _RESOURCE_ASSET.match((rn or "").strip())
    if m is None:
        r.erro(campo, rn,
               f"não é resource name de Asset. O formato é "
               f"`customers/{cid}/assets/<id>` — o motor de criativo devolve "
               f"exatamente isso ao criar o asset (destino: {destino})")
        return
    conta, ident = m.group(1), int(m.group(2))
    if conta != str(cid):
        r.erro(campo, rn,
               f"o asset é da conta {conta} e o mutate é na {cid}. Asset não "
               f"atravessa conta: crie-o na conta de destino")
    if ident <= 0:
        r.erro(campo, rn,
               f"id {ident} é TEMPORÁRIO (negativo). Imagens e vídeos de "
               f"Display entram por resource name de Asset JÁ CRIADO; um id "
               f"temporário aqui colidiria com a faixa reservada em `comum.py` "
               f"({comum.T_ASSET_BASE} para baixo)")


def validar(cid: str, brief: Brief, *, login_customer_id: str):
    """Valida local + na API (`validate_only`). Nada é criado.

    Mesma forma de `search.validar`: devolve (resultado_local, falha, n_ops). A
    falha é `None` quando a API aceitou o grafo.
    """
    ops, r = construir(cid, brief, login_customer_id=login_customer_id)
    if not r.ok:
        return r, None, 0
    falha = validar_mutacoes(cid, ops, login_customer_id=login_customer_id)
    return r, falha, len(ops)


# ── o plano, para quem não pode importar protobuf ──────────────────────────

#: Ausências DECLARADAS de Display. Esta é a MESMA tupla que
#: `campanha/perfil.py` publica como `DISPLAY.acoes_indisponiveis`: o perfil a
#: referencia daqui em vez de repetir o texto, porque a doutrina do índice é
#: "cada fato é declarado uma vez, no módulo do canal".
NAO_OPERADO: tuple[str, ...] = (
    "segmentar: topic, user list, custom audience, custom intent e "
    "demografia estão confirmados `[alta]` em matriz-api/display.md §7 e "
    "entram na próxima fatia. Nesta, a campanha nasce em inventário "
    "aberto, escolhido pelo lance.",
    "segmentação POSITIVA por placement não entra: a tabela oficial de "
    "critérios marca placement como positivo ❌, e "
    "`network_settings.target_content_network` descreve a rede como "
    "'specified placements'. As duas fontes são oficiais e se contradizem; "
    "a matriz marca `[NÃO CONFIRMADO]` e a prova por `validate_only` na "
    "conta real ainda não foi autorizada. Exclusão por placement "
    "(negativo) é onde as duas concordam e é por onde a próxima fatia "
    "começa.",
    "extensões de campanha: sitelink, callout e snippet não são montados — "
    "a matriz não declara tipo nem field_type para Display, e montá-los "
    "por analogia com Search subiria asset que não veicula.",
    "lance manual: `MANUAL_CPC` está `[NÃO CONFIRMADO]` para Display na "
    "tabela oficial de estratégias, e sem termo de busca ele não teria "
    "sinal que filtrasse inventário. Só MaxConv (com tCPA dentro).",
)


def planejar(cid: str, brief: Brief, *, login_customer_id: str) -> plano.PlanoDeCanal:
    """Monta offline e projeta o payload em plano serializável.

    ⚠️ **Display sem imagem não produz plano feliz.** `_checar_imagens()`
    recusa `imagens_display is None` com erro, e o erro chega aqui como
    bloqueio `ASSET_OBRIGATORIO_AUSENTE` com `monta=False`. Isso importa porque
    o caminho HTTP ainda passa `imagens_display=None` literal
    (`backend/app/routers/trafego.py`, `ProvarEntrada` sem campo de imagem):
    enquanto essa rota não for corrigida, é ESTE bloqueio que impede um plano
    de Display vazio de parecer aprovado.
    """
    ops, r = construir(cid, brief, login_customer_id=login_customer_id)
    monta = bool(ops) and r.ok
    return plano.projetar(
        canal=CANAL,
        customer_id=cid,
        login_customer_id=login_customer_id,
        operacoes=ops,
        resultado=r,
        prontidao=plano.Prontidao(
            monta=monta,
            pode_provar=True,
            pode_criar=True,
            motivo_nao_monta=(
                "" if monta
                else "o brief não passou na validação local; veja bloqueios"),
        ),
        nao_operado=NAO_OPERADO,
        aberto_por_ausencia=(
            "audiência e posicionamento: a campanha nasce em INVENTÁRIO "
            "ABERTO, escolhido pelo lance. Não é 'segmentada com zero "
            "audiências' — é uma campanha que pode aparecer em qualquer site "
            "da rede de display.",
        ),
        nivel_geo_idioma="campanha",
    )
