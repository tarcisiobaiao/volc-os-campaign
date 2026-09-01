"""Forma e política do texto — a camada que vale em QUALQUER canal.

Este módulo é uma EXTRAÇÃO, não uma novidade: cada função aqui saiu de
`campanha/search.py`, onde estava privada e portanto invisível para o segundo
canal. O construtor de Display precisava exatamente das mesmas seis coisas —
contar caractere como o Google conta, recusar duplicata, recusar DKI onde ele
não vale, traduzir `policy.Violacao` em achado do runner, avisar quando a
camada semântica não cobre o idioma do brief, e montar o nome da campanha — e
copiá-las teria criado duas implementações do mesmo julgamento, que divergem
no primeiro ajuste.

## O que NÃO está aqui, e por quê

Bloco de operação (`MutateOperation`) mora em `comum.py`; conhecimento de
canal mora em `perfil.py`; o que cada canal monta mora no seu construtor. Aqui
só entra o que julga TEXTO e não sabe em que anúncio ele vai parar.

`_checar_snippet_header` e `_vincular` continuaram em `search.py` de propósito:
snippet e asset de campanha são recursos do Search hoje, e "shared" não é
depósito de utilitário sem dono. Eles sobem para cá quando existir o segundo
consumidor real.

## A relação com `validacao.py`

`validacao.py` é o validador antigo, 100% pt-BR. Dele sobrevive o que não tem
idioma dentro: o contêiner de achados (`Resultado`/`Achado`), a integridade da
tag DKI e a triagem de keyword. Quem decide SENTIDO é `policy/spec.py`, e é
por isso que `politica()` aqui não chama `validacao.checar_lista()`: aquela
função aplica, no meio do caminho, a lista de palavras proibidas que a medição
em 6.651 headlines aprovados derrubou.
"""

from __future__ import annotations

import pathlib
import unicodedata

import yaml

from ..policy import spec as policy
from . import validacao
from .brief import Brief

# Os NÚMEROS de `limites.yaml` continuam sendo a fonte: são restrições da API,
# confirmadas por `validate_only` contra conta real (Search) ou lidas nas
# definições proto do SDK instalado (Display).
LIM = yaml.safe_load(
    (pathlib.Path(__file__).parent / "limites.yaml").read_text(encoding="utf-8")
)

# Severidades do spec.json que BARRAM o mutate. Portão é decisão binária: não
# existe modo de "passar mesmo assim". `limitacao` entra na lista de propósito
# — é o efeito FULLY_LIMITED, que deixou 57 anúncios sem veicular em 39 contas
# sob GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES. Anúncio que não veicula é
# reprovação com outro nome.
SEVERIDADE_BARRA = {"erro", "bloqueio", "limitacao"}

# ⚠️ A única regra do spec cuja severidade NÃO é honrada aqui, e o motivo é
# medido neste próprio repositório. `editorial.maiusculas.tudo_caixa_alta`
# implementa a exceção de sigla por LISTA FECHADA (SOS, FGTS, CPF, INSS, PIS,
# CNH, RG, IPTU, IR) — e a própria nota da regra diz que "siglas e marcas
# registradas são exceção". Toda sigla fora da lista dispara: a descrição do
# brief do FGTS ("Resolução CCFGTS 1.130/2025") derruba o mutate inteiro, e
# `validate_only` aceita a mesma copy. Nos outros seis países a lista não cobre
# RFC, CURP, DNI, IMSS, AFIP, SAT. Distinguir sigla de grito exige dicionário,
# dicionário é por idioma, e isso quebraria a promessa de valer em qualquer
# país — é a mesma conclusão que `copy/provar.py` já registrou. Quem adjudica
# caixa alta é o Google; aqui vira AVISO, sempre, para qualquer texto.
SO_AVISO = {"editorial.maiusculas.tudo_caixa_alta"}

# Campo do brief → campo do spec (`aplica_a`). Nome diferente do de
# `limites.yaml`, que é a chave dos limites numéricos, não da política.
#
# ⚠️ A tabela é UMA para todos os canais, e por isso as chaves de Display
# entram aqui e não numa segunda tabela dentro de `display.py`. `headline_rsa`
# e `headline_display` são limites numéricos diferentes do MESMO campo de
# política: um título é um título para o spec, independentemente do formato do
# anúncio que o carrega.
CAMPO_POLITICA = {
    "headline_rsa": "headline",
    "description_rsa": "description",
    "callout": "callout",
    "sitelink_texto": "sitelink",
    "sitelink_desc": "sitelink",
    "snippet_valor": "snippet",
    "headline_display": "headline",
    "description_display": "description",
    "long_headline_display": "long_headline",
    "headline_demandgen": "headline",
    "description_dgen": "description",
    "headline_pmax": "headline",
    "long_headline_pmax": "long_headline",
    "description_pmax": "description",
    "business_name": "business_name",
}


def chave(texto: str) -> str:
    """Chave de comparação: minúscula, sem acento. Só para deduplicar.

    Escrita aqui, e não importada, porque as duas implementações que existem
    no pacote são privadas (`validacao._normalizar`, `policy.spec._sem_acento`)
    e importar privado de outro módulo é combinar de quebrar junto. São quatro
    linhas de stdlib com semântica fechada — não é o tipo de código que evolui.
    """
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def nome_da_campanha(brief: Brief, ts: str, *, marcador: str = "") -> str:
    """`BR - 20260819_123824 / Maquininha de Cartão / https://…/r/slug/`

    ## Por que ESTE formato, e não o que o engine usava

    O engine montava `FORGE BR 20260819_123824 Maquininha de Cartão` — quatro
    campos separados por espaço, sem a URL. A operação já tinha uma taxonomia,
    usada no flow n8n que criou as campanhas de fevereiro:

        BR - {carimbo} / {termo principal} / {URL da landing page}

    Ela não é decorativa. Cada barra separa uma pergunta que se faz olhando a
    lista de campanhas: **onde** compro, **o que** compro, **para onde** mando.
    A URL no nome é o que permite achar a campanha partindo da página — e é o
    cruzamento que o `finalUrlSuffix` faz do outro lado.

    O espaço como separador perdia isso: `FORGE BR 20260819 Maquininha de
    Cartão` não tem onde o carimbo termina e o termo começa.

    `prefixo_nome` continua existindo e entra na frente quando não for o padrão
    — quem quiser marcar um lote de teste não perde o recurso.

    ## O `marcador` de canal, e por que ele é PARÂMETRO

    `taxonomia.py` aprendeu observando 383 campanhas dos primos que o
    modificador de canal implícito é o defeito nº 1 da nomenclatura deles:
    quatro campanhas de Demand Gen dizem "Display" no nome porque ninguém
    marcava nada. Com dois canais no ar, o nome precisa dizer qual é.

    Ele é parâmetro e tem padrão VAZIO porque quem decide o marcador é o
    perfil do canal (`perfil.py`), não um `if` aqui dentro — e porque Search
    nasceu sem marcador. Mudar o nome das campanhas de Search agora quebraria
    o `analisar()` de tudo que já subiu, sem consertar nada.
    """
    partes = [f"{brief.pais} - {ts}", brief.nicho[:40]]
    if brief.url_final:
        partes.append(brief.url_final)
    nome = " / ".join(partes)
    if marcador:
        # Entre colchetes, como em `taxonomia.montar()`: delimitador explícito
        # impede que um tema contendo a palavra "Display" seja lido como canal.
        nome = f"{nome} [{marcador}]"
    # O padrão histórico do engine não entra: ele existia por falta de formato,
    # não por decisão. Um prefixo declarado pelo operador, sim.
    if brief.prefixo_nome and brief.prefixo_nome != "FORGE":
        nome = f"{brief.prefixo_nome} {nome}"
    return nome


def forma(
    itens: list[str],
    chave_limite: str,
    r: validacao.Resultado,
    *,
    permitir_dki: bool = False,
    explicacao_dki: str = "",
) -> list[str]:
    """Limites numéricos de `limites.yaml` — a parte que sobreviveu à medição.

    Sem uma palavra de idioma nenhum dentro: comprimento (contado como o Google
    conta, resolvendo o DKI pelo fallback), contagem, duplicata e integridade
    da tag. O que decide SENTIDO é `politica()`.

    `explicacao_dki` é o pedaço da recusa que só o CANAL sabe. "DKI não é
    permitido neste campo" é verdade em Search (descrição de RSA) e em Display
    (todo campo) por motivos diferentes: lá é regra do formato, aqui é que não
    existe keyword para inserir. Uma frase parametrizada evita a alternativa
    ruim — cada canal reimplementar esta função para trocar uma mensagem.
    """
    lim = LIM["texto"][chave_limite]
    aprovados: list[str] = []

    for texto in itens:
        texto = (texto or "").strip()
        if not texto:
            r.erro(chave_limite, texto, "texto vazio")
            continue
        if not validacao.dki_integro(texto):
            r.erro(chave_limite, texto, "tag DKI truncada ou chave desbalanceada")
            continue
        # `resolver_dki` devolve o texto com a tag trocada pelo fallback, que é
        # o que o usuário vê e o que o Google mede. Texto sem tag volta idêntico
        # — daí a comparação servir de detector de presença.
        visto = policy.resolver_dki(texto)
        if not permitir_dki and visto != texto:
            motivo = "DKI não é permitido neste campo"
            if explicacao_dki:
                motivo = f"{motivo} — {explicacao_dki}"
            r.erro(chave_limite, texto, motivo)
            continue
        if len(visto) > lim["max_chars"]:
            r.erro(chave_limite, texto,
                   f"{len(visto)} chars > limite {lim['max_chars']}")
            continue
        aprovados.append(texto)

    # duplicatas são recusadas pela API em headlines/descriptions
    vistos, unicos = set(), []
    for t in aprovados:
        k = chave(t)
        if k in vistos:
            r.aviso(chave_limite, t, "duplicado — removido")
            continue
        vistos.add(k)
        unicos.append(t)

    if len(unicos) < lim["min_itens"]:
        r.erro(chave_limite, f"{len(unicos)} itens", f"mínimo é {lim['min_itens']}")

    # ⚠️ Corte SILENCIOSO era perda paga sem recibo.
    #
    # `unicos[: max_itens]` descartava o excedente sem um achado. O RSA aceita 15
    # títulos e o RDA aceita 5 — um brief escrito para Search e reaproveitado em
    # Display perdia 10 títulos e 12 textos no total, e nada no diário dizia
    # quais. Esses textos vêm do ciclo de copy, que passa por juiz semântico: são
    # trabalho pago, e o operador precisa saber que o que ele leu não é o que
    # subiu.
    #
    # É AVISO e não erro: cortar é o comportamento certo — a API recusaria o
    # mutate inteiro com o excedente. O defeito era não contar.
    if len(unicos) > lim["max_itens"]:
        cortados = unicos[lim["max_itens"]:]
        r.aviso(chave_limite,
                f"{len(unicos)} itens para um teto de {lim['max_itens']}",
                f"{len(cortados)} texto(s) não sobem e não aparecem no anúncio: "
                + " · ".join(t[:32] for t in cortados[:6])
                + (" …" if len(cortados) > 6 else ""))
    return unicos[: lim["max_itens"]]


def politica(
    pol: policy.Validador,
    textos: list[str],
    chave_limite: str,
    r: validacao.Resultado,
) -> None:
    """As três camadas de `policy/spec.py` sobre uma LISTA.

    Roda por lista e não por item porque duas regras do spec só existem no
    conjunto: repetição de palavra entre recursos do mesmo grupo é invisível
    item a item.
    """
    campo = CAMPO_POLITICA[chave_limite]
    for v in pol.checar_lista([t for t in textos if t], campo):
        registrar(v, r)


def registrar(v: policy.Violacao, r: validacao.Resultado) -> None:
    """Traduz uma `Violacao` do spec para um achado do runner, sem perder fonte.

    A fonte vai junto porque é ela que separa regra de opinião: o número do
    documento oficial permite conferir a decisão sem confiar em quem a escreveu.
    """
    motivo = f"{v.titulo} (política {v.politica})"
    if v.detalhe:
        motivo = f"{motivo} — {v.detalhe}"
    if v.regra in SO_AVISO or v.severidade not in SEVERIDADE_BARRA:
        r.aviso(v.campo, v.texto, motivo)
    else:
        r.erro(v.campo, v.texto, motivo)


def avisar_cobertura(pol: policy.Validador, r: validacao.Resultado) -> None:
    """Diz em voz alta quando a camada semântica não cobre o idioma do brief.

    Um anúncio em dinamarquês passaria "limpo" só porque não existe lista de
    clickbait em dinamarquês. Falso negativo silencioso é pior que reprovar:
    o runner precisa saber que está parcialmente cego.
    """
    cob = policy.cobertura_semantica(pol.spec, pol.idioma)
    if cob["cobertura"] != "completa":
        r.aviso("politica", pol.idioma, cob["aviso"])


def abrir_portao(brief: Brief, r: validacao.Resultado) -> policy.Validador:
    """O portão país × vertical, montado e disparado — igual em todo canal.

    O validador de política é UM por (país, vertical, idioma). O idioma vem do
    brief e não do país porque são eixos distintos: campanha em espanhol
    segmentando os EUA usa regras `es` e portão `US`.
    """
    pol = policy.Validador(
        pais=brief.pais, vertical=brief.vertical, idioma=brief.idioma
    )
    avisar_cobertura(pol, r)
    for v in pol.checar_habilitacao(certificacoes=brief.certificacoes):
        registrar(v, r)
    return pol
