"""Construtor de campanha de Search — grafo atômico completo.

Substitui as 9 chamadas HTTP encadeadas do n8n por UMA transação:
budget → campanha → geo → idioma → **N ad groups** (um por sub-intenção, cada
um com suas keywords, suas negativas, seu lance e seu RSA) → negativas de
campanha → sitelinks → callouts → snippets. Tudo entra ou nada entra.

Duas mudanças estruturais em relação à versão anterior, e as duas são de
correção, não de gosto:

1. **Um ad group por sub-intenção.** Antes era um só, com todas as keywords
   dentro — logo, um lance só para todas. O cluster medido do Pautador
   (`opportunity_id 73`) tem quatro sub-intenções com spread de CPC minerado
   de 9× entre a mais barata e a mais cara; um lance para as quatro é dinheiro
   deixado na mesa nos dois sentidos. A estrutura já vinha pronta da mineração
   e o construtor a ignorava.

2. **O juiz de conteúdo é `policy/spec.py`, não `campanha/validacao.py`.** O
   validador antigo é 100% pt-BR: copy em espanhol com os análogos exatos de
   todos os termos proibidos passava com ZERO achados e o runner dizia "ok" —
   inaceitável numa operação de sete países. De `validacao.py` sobrevive aqui
   só o que não tem idioma dentro: o contêiner de achados, a integridade da
   tag DKI e a triagem de keyword.

Os LIMITES NUMÉRICOS de `limites.yaml` (tamanho e contagem) continuam valendo.
O que morreu foi a lista de palavras proibidas do mesmo arquivo, medida em
6.651 headlines aprovados e servindo: "crédito" aparece 54× e em NENHUM
punido. O critério que a substitui é o papel do site — vertical `informativo`
contra `financeiro` —, que atravessa idioma.

O que este módulo NÃO faz: não escreve nada (quem escreve é `mutar()`, atrás
da trava de dois fatores de `gads/modo.py`); não busca a landing page, então
`spec.checar_destino()` fica de fora por falta de um status HTTP que ninguém
aqui coleta; e não escreve copy diferente por sub-intenção — os N ad groups
recebem o MESMO RSA, porque o brief carrega uma `Copy` só.
"""

from __future__ import annotations

import dataclasses

from ..gads.client import cliente, validar_mutacoes
from . import comum, conteudo, criterio, validacao
from .brief import SEM_SUB_INTENCAO, Brief, SubIntencao
from .criterio import Criterio
from .taxonomia import MAX_NOME_ADGROUP

# Faixa dos ids temporários de asset — declarada com as outras em `comum.py`,
# reexportada aqui porque é este módulo que a consome.
T_ASSET_BASE = comum.T_ASSET_BASE

CANAL = "SEARCH"

#: As estratégias de lance que ESTE canal aceita — as duas, e o padrão da casa
#: é `MANUAL_CPC` (ver `Brief.estrategia_lance`). Declarado aqui, no módulo do
#: canal, e lido por `campanha/perfil.py`.
LANCES_PERMITIDOS: tuple[str, ...] = ("MANUAL_CPC", "MAXIMIZE_CONVERSIONS")

#: Opções de construção além do brief. `ai_max` liga `campaign.ai_max_setting`,
#: que só existe em Search.
OPCOES: frozenset[str] = frozenset({"ai_max"})

# ⚠️ Os limites numéricos, a tabela de campo→política, as severidades que
# barram, a exceção da caixa alta, o nome da campanha e o portão país×vertical
# MIGRARAM para `campanha/conteudo.py`. Eram privados deste módulo e portanto
# invisíveis para o segundo canal; Display precisa exatamente do mesmo
# julgamento, e duas cópias divergem no primeiro ajuste. O que ficou aqui é o
# que é de Search: snippet, asset de campanha e a partição em sub-intenções.

# Fachada de compatibilidade, com condição de aposentadoria declarada.
# `copy/contrato._barra_o_lancamento` importa estes dois nomes DAQUI, e
# `copy/testes_juiz_semantico` prova por `inspect.getsource` que ele os importa
# de `campanha.search` — é assim que o portão do lançamento e o do runner usam
# um critério só. Reexportar mantém a prova válida e a fonte única; os dois
# somem no dia em que `copy/` (outro dono) passar a importar de
# `campanha.conteudo` diretamente.
_SEVERIDADE_BARRA = conteudo.SEVERIDADE_BARRA
_SO_AVISO = conteudo.SO_AVISO


def construir(cid: str, brief: Brief, *, login_customer_id: str, ai_max: bool = False):
    """Monta as operações e valida o conteúdo localmente.

    Devolve (operacoes, resultado_da_validacao). Se `resultado.ok` for False,
    NÃO envie: a validação local é mais barata que a da API, e a da API é
    mais barata que a reprovação de política.
    """
    c = cliente(login_customer_id)
    r = validacao.Resultado()
    # A porta HTTP congela este valor entre `validate_only` e a escrita. Sem
    # isso, cada reconstrução mudaria os nomes e, portanto, a impressão do
    # protobuf — tornando impossível provar que o escrito é o que foi revisto.
    ts = brief.carimbo_nome or comum.carimbo()
    base = conteudo.nome_da_campanha(brief, ts)

    # O portão país × vertical, montado e disparado. Vale em todo canal e por
    # isso mora em `conteudo.py` — Display abre exatamente o mesmo.
    pol = conteudo.abrir_portao(brief, r)

    headlines = conteudo.forma(brief.copy.headlines, "headline_rsa", r, permitir_dki=True)
    descriptions = conteudo.forma(brief.copy.descriptions, "description_rsa", r)
    callouts = conteudo.forma(brief.copy.callouts, "callout", r)

    sitelinks = []
    for s in brief.copy.sitelinks:
        sub = validacao.Resultado()
        txt = conteudo.forma([s.texto], "sitelink_texto", sub)
        if not txt:
            r.achados.extend(sub.achados)
            continue
        descs = [d for d in (s.descricao1, s.descricao2) if d]
        # ⚠️ Resultado descartado, comportamento herdado: descrição de sitelink
        # acima de 35 chars some sem uma linha de aviso. O sintoma que aparece
        # é o outro — "descrição única descartada" logo abaixo —, que aponta
        # para o par e não para o comprimento.
        descs = conteudo.forma(descs, "sitelink_desc", validacao.Resultado())
        if len(descs) == 1:
            # Descrição solta seria recusada pela API (as duas são pareadas).
            # Descartamos em vez de derrubar o mutate inteiro por um sitelink.
            r.aviso("sitelink_desc", descs[0],
                    "descrição única descartada — a API exige as duas ou nenhuma")
            descs = []
        sitelinks.append((txt[0], descs))
    if len(sitelinks) < 2:
        r.erro("sitelink", f"{len(sitelinks)}", "mínimo de 2 sitelinks")

    snippet_vals: list[str] = []
    if brief.copy.snippet:
        _checar_snippet_header(brief, r)
        snippet_vals = conteudo.forma(brief.copy.snippet.valores, "snippet_valor", r)

    # Política sobre o texto que sobreviveu à forma. Roda por LISTA e não por
    # item porque duas regras do spec só existem no conjunto: repetição de
    # palavra entre recursos do mesmo grupo é invisível item a item.
    conteudo.politica(pol, headlines, "headline_rsa", r)
    conteudo.politica(pol, descriptions, "description_rsa", r)
    conteudo.politica(pol, callouts, "callout", r)
    conteudo.politica(pol, [t for t, _ in sitelinks], "sitelink_texto", r)
    conteudo.politica(pol, [d for _, ds in sitelinks for d in ds], "sitelink_desc", r)
    conteudo.politica(pol, snippet_vals, "snippet_valor", r)

    grupos = _grupos(brief, ts, r)

    # As negativas, triadas com o `r` DE VERDADE. Na versão anterior os dois
    # blocos abaixo recebiam um `validacao.Resultado()` descartável, e por isso
    # negativa longa demais ou com palavras demais sumia do payload em
    # silêncio. Agora o achado chega ao operador — e a lista vazia, que é o
    # caso comum, não inventa um erro (ver `checar_criterios`).
    _pos, neg_camp, neg_grupo = criterio.por_nivel(brief.criterios)

    negativas_campanha = validacao.checar_criterios(
        neg_camp, r, rotulo="negativa_campanha"
    )
    negativas_por_grupo: dict[str, list] = {}
    for sub, _kws, _nome in grupos:
        do_grupo = [c for c in neg_grupo if c.em_grupo(sub.nome)]
        negativas_por_grupo[sub.nome] = validacao.checar_criterios(
            do_grupo, r, rotulo=f"negativa[{sub.nome}]"
        )

    # Conflito positiva × negativa. Não é opinião sobre a qualidade da
    # negativa: é contradição que o operador declarou sem perceber — a keyword
    # entra no payload, a campanha sobe e ela nunca serve uma consulta.
    # Aviso e não erro: há caso legítimo (negativa PHRASE estreitando uma
    # positiva BROAD), e quem decide é quem revisa, com o conflito na tela.
    aprovadas = list(negativas_campanha)
    for lista in negativas_por_grupo.values():
        aprovadas.extend(lista)
    positivas_ok = [c for _s, kws, _n in grupos for c in kws]
    for cf in criterio.conflitos(positivas_ok + aprovadas):
        r.aviso("conflito", cf.negativa.texto, str(cf))

    if not r.ok:
        return [], r

    ops = [
        comum.op_budget(c, cid, brief, f"Budget_{ts}"),
        comum.op_campanha(c, cid, brief, base, "SEARCH", ai_max=ai_max),
        comum.op_geo(c, cid, brief),
        comum.op_idioma(c, cid, brief),
    ]

    # URL limpa. A marcação inteira vai no `final_url_suffix` da campanha, que
    # o Google aplica a esta URL e à de todo sitelink e asset — ver marcacao.py.
    url = comum.url_destino(brief)

    for i, (sub, kws, nome) in enumerate(grupos):
        ops.append(
            comum.op_adgroup(
                c, cid, brief, nome, "SEARCH_STANDARD",
                indice=i, cpc_inicial=sub.cpc_inicial, tcpa=sub.tcpa,
            )
        )
        ag = comum.temp_adgroup(cid, i)

        # keywords — cada uma com o match type QUE ELA declara. O default do
        # brief (`PHRASE`) só preenche quem não declarou: EXACT sufoca volume
        # em nicho novo, BROAD sem histórico de conversão vira ralo.
        for crit in kws:
            o = c.get_type("MutateOperation")
            k = o.ad_group_criterion_operation.create
            k.ad_group = ag
            k.status = c.enums.AdGroupCriterionStatusEnum.ENABLED
            k.keyword.text = crit.texto
            k.keyword.match_type = getattr(
                c.enums.KeywordMatchTypeEnum, crit.match_type
            )
            ops.append(o)

        # negativas de ad group — as que não declaram grupo valem em TODOS os
        # grupos (era `brief.negativas_adgroup`); as que declaram valem só no
        # seu (era `sub.negativas`). É a razão de a separação por sub-intenção
        # valer mesmo com lance automático: negativa por grupo é impossível
        # com um ad group único.
        #
        # ⚠️ O match type é o DA NEGATIVA, não mais `BROAD` fixo. BROAD numa
        # negativa bloqueia toda consulta que contenha os tokens em qualquer
        # ordem — quem escreve "curso gratis" quase sempre queria PHRASE, e a
        # versão anterior trocava a intenção do operador sem dizer.
        for crit in negativas_por_grupo.get(sub.nome, ()):
            o = c.get_type("MutateOperation")
            k = o.ad_group_criterion_operation.create
            k.ad_group = ag
            k.negative = True
            k.keyword.text = crit.texto
            k.keyword.match_type = getattr(
                c.enums.KeywordMatchTypeEnum, crit.match_type
            )
            ops.append(o)

        # RSA — um por ad group. Ad group sem anúncio não veicula nada, então
        # este bloco não é opcional quando os grupos se multiplicam. A copy é a
        # mesma nos N grupos: o brief carrega uma `Copy` só.
        o = c.get_type("MutateOperation")
        ada = o.ad_group_ad_operation.create
        ada.ad_group = ag
        ada.status = c.enums.AdGroupAdStatusEnum.ENABLED
        ada.ad.final_urls.append(url)
        for t in headlines:
            a = c.get_type("AdTextAsset")
            a.text = t
            ada.ad.responsive_search_ad.headlines.append(a)
        for t in descriptions:
            a = c.get_type("AdTextAsset")
            a.text = t
            ada.ad.responsive_search_ad.descriptions.append(a)
        ops.append(o)

    # negativas de campanha — valem para todos os ad groups, com o match type
    # que cada uma declara (ver a nota acima sobre BROAD fixo).
    for crit in negativas_campanha:
        o = c.get_type("MutateOperation")
        cc = o.campaign_criterion_operation.create
        cc.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
        cc.negative = True
        cc.keyword.text = crit.texto
        cc.keyword.match_type = getattr(c.enums.KeywordMatchTypeEnum, crit.match_type)
        ops.append(o)

    # assets + vínculo com a campanha, no mesmo mutate. Vínculo de CAMPANHA e
    # não de ad group: sitelink e callout servem os N grupos de uma vez, e um
    # `campaign_asset` por asset evita multiplicar operação por grupo.
    # ⚠️ Índice, e não aritmética solta. `comum.temp_asset()` levanta antes de
    # emitir um id fora da faixa de texto; a versão anterior decrementava um
    # inteiro à mão e podia atravessar para a faixa de imagem sem que nada
    # reclamasse — os dois ids são válidos para a API, e a referência passaria
    # a apontar para o asset errado.
    n = 0
    for texto, descs in sitelinks:
        rn = comum.temp_asset(cid, n)
        o = c.get_type("MutateOperation")
        asset = o.asset_operation.create
        asset.resource_name = rn
        asset.sitelink_asset.link_text = texto
        # As descrições do sitelink são PAREADAS: a API exige description2
        # sempre que description1 existe. Uma só faz o mutate inteiro falhar
        # com field_error.REQUIRED — descoberto no teste de atomicidade.
        if len(descs) >= 2:
            asset.sitelink_asset.description1 = descs[0]
            asset.sitelink_asset.description2 = descs[1]
        # A mesma URL limpa do anúncio, sem bifurcar. Antes cada sitelink
        # recebia `&sl=N` para ser identificável no relatório; agora quem
        # identifica é o `{extensionid}` do sufixo, que o Google preenche
        # sozinho. Uma URL só significa uma landing page só na política e um
        # `landing_page_view` só no relatório — antes eram N destinos distintos
        # para a mesma página.
        asset.final_urls.append(url)
        ops.append(o)
        ops.append(_vincular(c, cid, rn, "SITELINK"))
        n += 1

    for texto in callouts:
        rn = comum.temp_asset(cid, n)
        o = c.get_type("MutateOperation")
        o.asset_operation.create.resource_name = rn
        o.asset_operation.create.callout_asset.callout_text = texto
        ops.append(o)
        ops.append(_vincular(c, cid, rn, "CALLOUT"))
        n += 1

    if snippet_vals and brief.copy.snippet:
        rn = comum.temp_asset(cid, n)
        o = c.get_type("MutateOperation")
        sa = o.asset_operation.create
        sa.resource_name = rn
        sa.structured_snippet_asset.header = brief.copy.snippet.header
        sa.structured_snippet_asset.values.extend(snippet_vals)
        ops.append(o)
        ops.append(_vincular(c, cid, rn, "STRUCTURED_SNIPPET"))

    return ops, r


# ── ad groups ───────────────────────────────────────────────────────────────


def _grupos(
    brief: Brief, ts: str, r: validacao.Resultado
) -> list[tuple[SubIntencao, list[Criterio], str]]:
    """Resolve a identidade de cada ad group: keywords triadas e nome final.

    A deduplicação de keyword atravessa os grupos de propósito. A mesma
    keyword com o mesmo match type em dois ad groups da mesma campanha não
    dobra a entrega: o Google escolhe uma para o leilão e a outra fica ociosa
    por duplicidade — e qual das duas vence não é a que você declarou. O lance
    do grupo perdedor vira ficção, que é exatamente o que a separação por
    sub-intenção existe para evitar. O primeiro grupo declarado fica com ela.

    ⚠️ A chave de duplicidade agora é (texto, match type), e não só o texto.
    O parágrafo acima sempre disse "com o mesmo match type" — mas, com um
    match type só para o brief inteiro, comparar o texto bastava. Com match
    type por keyword, comparar só o texto passaria a apagar `"curso"` PHRASE
    porque `"curso"` EXACT já existia em outro grupo: dois critérios que a API
    aceita lado a lado e que não competem entre si.
    """
    if len(brief.sub_intencoes) > comum.T_ADGROUP_MAX:
        r.erro("sub_intencoes", f"{len(brief.sub_intencoes)} grupos",
               f"máximo de {comum.T_ADGROUP_MAX} ad groups por mutate")
        return []

    saida: list[tuple[SubIntencao, list[Criterio], str]] = []
    vistos: dict[tuple[str, str], str] = {}
    nomes: set[str] = set()
    for sub in brief.grupos():
        parcial = validacao.Resultado()
        do_grupo = [
            c for c in brief.criterios if not c.negativa and c.em_grupo(sub.nome)
        ]
        kws = validacao.checar_criterios(
            do_grupo, parcial, exigir_pelo_menos_um=True
        )
        for a in parcial.achados:
            # O achado nasce sem saber de que grupo veio; sem o rótulo, "80
            # chars > 80" num brief de quatro grupos não diz onde procurar.
            r.achados.append(dataclasses.replace(a, campo=f"{a.campo}[{sub.nome}]"))

        unicas = []
        for kw in kws:
            chave = (conteudo.chave(kw.texto), kw.match_type)
            dono = vistos.get(chave)
            if dono is not None:
                r.aviso("keyword", kw.texto,
                        f"já está em {dono!r} — mantida só lá (duplicata entre "
                        f"ad groups compete consigo mesma)")
                continue
            vistos[chave] = sub.nome
            unicas.append(kw)

        if not unicas:
            r.erro("sub_intencoes", sub.nome,
                   "nenhuma keyword própria sobrou depois da triagem")
            continue

        nome = _nome_adgroup(sub, ts)
        if nome in nomes:
            # Só acontece com dois rótulos idênticos nos primeiros 239
            # caracteres (255 do limite menos os 16 do carimbo `_AAAAMMDD_HHMMSS`).
            # Vale a checagem porque a consequência é desproporcional:
            # a API recusa o ad group com DUPLICATE_ADGROUP_NAME e, num mutate
            # atômico, isso derruba a campanha inteira por causa de um rótulo.
            r.erro("sub_intencoes", sub.nome,
                   f"nome de ad group colide com outro depois da truncagem "
                   f"({nome!r}) — a API recusa com DUPLICATE_ADGROUP_NAME")
            continue
        nomes.add(nome)
        saida.append((sub, unicas, nome))
    return saida


def _nome_adgroup(sub: SubIntencao, ts: str) -> str:
    """Nome do ad group, com o carimbo SEMPRE preservado.

    Truncar `f"{nome}_{ts}"` pelo fim comeria justamente o carimbo, que é o
    que torna o nome único entre rodadas. Truncamos o rótulo e mantemos o
    sufixo — o inverso perde a informação que serve para desempatar.
    """
    if sub.nome == SEM_SUB_INTENCAO:
        return f"AdGroup_{ts}"
    sufixo = f"_{ts}"
    return sub.nome.strip()[: MAX_NOME_ADGROUP - len(sufixo)] + sufixo


def _checar_snippet_header(brief: Brief, r: validacao.Resultado) -> None:
    """O header do snippet é uma string FECHADA e por idioma.

    ⚠️ `limites.yaml` só traz a linha pt-BR da tabela oficial. Para es e en o
    validador local não tem o que comparar, e chutar uma tradução seria pior
    que não checar — a tabela inteira, com as 40 e poucas localidades, está em
    `google_ads_api/structured_snippets.md`. Nesses idiomas quem adjudica é o
    `validate_only`, que recusa header inválido.
    """
    header = (brief.copy.snippet.header if brief.copy.snippet else "") or ""
    if brief.idioma == "pt":
        validacao.checar_snippet_header(header, r)
        return
    r.aviso("snippet_header", header,
            f"não verificado localmente: `limites.yaml` só tem a tabela pt-BR "
            f"e o brief é {brief.idioma!r} — ver structured_snippets.md")


def _vincular(c, cid: str, asset_rn: str, campo: str):
    o = c.get_type("MutateOperation")
    ca = o.campaign_asset_operation.create
    ca.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    ca.asset = asset_rn
    ca.field_type = getattr(c.enums.AssetFieldTypeEnum, campo)
    return o


def validar(cid: str, brief: Brief, *, login_customer_id: str, ai_max: bool = False):
    """Valida local + na API (`validate_only`). Nada é criado."""
    ops, r = construir(cid, brief, login_customer_id=login_customer_id, ai_max=ai_max)
    if not r.ok:
        return r, None, 0
    falha = validar_mutacoes(cid, ops, login_customer_id=login_customer_id)
    return r, falha, len(ops)
