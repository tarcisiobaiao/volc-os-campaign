"""F03 / D2 — acesso programatico a novidade regulatoria brasileira.

Uma funcao por fonte. Todas devolvem `list[Item]`, onde Item e um dict com,
no minimo, as quatro chaves do contrato:

    {"titulo": str, "data": str|None, "url": str, "texto": str}

mais duas de proveniencia, exigidas pela disciplina antifabricacao do PRD:

    "fonte": str   -- identificador curto da fonte (ex.: "dou_diario")
    "meta":  dict  -- campos crus da fonte + "coletado_em" (UTC ISO)

REGRAS DESTE MODULO
-------------------
1. SOMENTE LEITURA. Nenhuma funcao aqui escreve em disco, em banco, no
   Supabase ou em qualquer API. Sao GETs HTTP e parsing em memoria.
2. NADA E INVENTADO. Todo item vem de uma resposta HTTP real e carrega a
   URL de onde veio. Se uma fonte nao devolve data parseavel, `data` fica
   `None` -- nunca e preenchida com "hoje" para tapar buraco. Uma data
   errada no sentinela faz o operador preparar campanha para um evento que
   nao existe.
3. FONTE QUE NAO FUNCIONA CONTINUA EXISTINDO. As funcoes bloqueadas estao
   implementadas e levantam `FonteBloqueada` (subclasse de
   NotImplementedError) com o codigo HTTP e a mensagem exata do bloqueio,
   medidos em 2026-08-05. Assim o bloqueio e um fato registrado no codigo,
   nao um comentario que apodrece.

O BLOQUEIO DO in.gov.br -- DIAGNOSTICO MEDIDO
---------------------------------------------
`https://www.in.gov.br/...` devolvia "HTTP 000" no teste do operador. Nao e
bloqueio de IP, nao e endereco errado, nao e a rede. E o WAF da borda (Azion)
com uma DENYLIST DE User-Agent de biblioteca. Medido em 2026-08-05:

    UA ausente                  -> HTTP 403
    UA "curl/8.7.1"             -> conexao morta (curl exit 92, erro de
                                   framing HTTP/2 = RST_STREAM do servidor)
    UA "python-requests/2.34.2" -> conexao morta (mesmo exit 92)
    UA "forge-sentinela/1.0"    -> HTTP 200
    UA "Wget/1.21"              -> HTTP 200
    UA "Mozilla/5.0"            -> HTTP 200

Ou seja: qualquer User-Agent que NAO seja o default de curl/requests passa.
Nao e preciso (nem desejavel) fingir ser navegador -- este modulo se
identifica honestamente como `forge-sentinela/1.0`. O que nao se pode e
deixar o `requests` mandar o UA dele por default, que e exatamente o que
acontece se voce esquecer o header.

Sem-www e com-www sao hosts diferentes: `in.gov.br` -> 302 para
`www.in.gov.br`; so o www serve conteudo.

CLI
---
    .venv/bin/python -m forge.sentinela.fontes_br

Varre todas as fontes com termos de novidade regulatoria e imprime a
contagem real por fonte. Sem argumentos, usa a data de hoje.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

import requests

__all__ = [
    "Item",
    "FonteBloqueada",
    "TERMOS_NOVIDADE",
    "dou_diario",
    "dou_busca",
    "dou_texto_integral",
    "camara_proposicoes",
    "senado_materias",
    "agencia_gov_noticias",
    "querido_diario",
    "govbr_plone_noticias",
    "secom_releases",
    "dados_gov_br_conjuntos",
    "FONTES",
    "coletar_tudo",
]

Item = dict[str, Any]


class FonteBloqueada(NotImplementedError):
    """Fonte investigada, testada e comprovadamente inacessivel daqui.

    Subclasse de NotImplementedError de proposito: o contrato da tarefa pede
    NotImplementedError, mas o chamador que quiser tratar so bloqueio de fonte
    (e nao um metodo esquecido) consegue distinguir.
    """


# --------------------------------------------------------------------------
# HTTP -- centraliza o User-Agent, o timeout e a educacao com o servidor.
# --------------------------------------------------------------------------

#: UA honesto. NAO trocar por "" nem deixar o requests usar o default dele:
#: o WAF do in.gov.br mata a conexao para "python-requests/*" (ver docstring).
USER_AGENT = "forge-sentinela/1.0 (+https://github.com/; monitor de politicas publicas)"

_PAUSA_PADRAO_S = 0.4  # cortesia entre requisicoes; nenhuma fonte impos limite
_TIMEOUT_PADRAO = (10, 60)  # (connect, read) -- DO3 chega a 2,6 MB

_sessao: requests.Session | None = None


def _http() -> requests.Session:
    global _sessao
    if _sessao is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "pt-BR,pt;q=0.9",
            }
        )
        _sessao = s
    return _sessao


def _get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    accept: str | None = None,
    timeout: tuple[int, int] = _TIMEOUT_PADRAO,
    pausa: float = _PAUSA_PADRAO_S,
) -> requests.Response:
    """GET com UA correto. Levanta requests.HTTPError em status >= 400."""
    headers = {"Accept": accept} if accept else None
    resp = _http().get(url, params=params, headers=headers, timeout=timeout)
    if pausa:
        time.sleep(pausa)
    resp.raise_for_status()
    return resp


def _agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Normalizacao -- data SEMPRE ISO ou None. Nunca "hoje" como fallback.
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_ESPACO_RE = re.compile(r"\s+")


def _limpar(texto: str | None) -> str:
    """Tira tags HTML (a busca do DOU devolve <span class='highlight'>) e
    normaliza espacos. Nunca devolve None."""
    if not texto:
        return ""
    return _ESPACO_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", texto))).strip()


def _iso(valor: str | None) -> str | None:
    """Converte as varias datas das fontes BR para YYYY-MM-DD.

    Devolve None quando nao consegue converter com certeza. Chute de data e
    exatamente o erro que este projeto nao pode cometer.
    """
    if not valor:
        return None
    v = valor.strip()
    # ISO ja pronto / ISO com hora ("2026-08-05T15:59")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # DD/MM/YYYY (DOU)
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", v)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # RFC 822 ("Wed, 05 Aug 2026 18:07:00 -0300") -- feeds RSS
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    # "20260805000000" (displayDate do portlet de busca do DOU)
    if re.fullmatch(r"\d{14}", v):
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
    return None


def _br(d: date) -> str:
    """DD-MM-YYYY, formato que o in.gov.br exige na querystring."""
    return d.strftime("%d-%m-%Y")


def _sem_acento(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


def _item(
    *, titulo: str, data: str | None, url: str, texto: str, fonte: str, meta: dict
) -> Item:
    meta = dict(meta)
    meta["coletado_em"] = _agora_utc()
    return {
        "titulo": _limpar(titulo),
        "data": data,
        "url": url,
        "texto": _limpar(texto),
        "fonte": fonte,
        "meta": meta,
    }


# --------------------------------------------------------------------------
# Vocabulario D2 -- o que caracteriza "novidade regulatoria" (S5 do PRD).
# --------------------------------------------------------------------------

#: Frases que aparecem no ato que CRIA um programa/beneficio -- o momento que
#: o D2 quer pegar. Derivadas do padrao de "Gas do Povo" / "Reforma Casa
#: Brasil": o ato institui, cria ou regulamenta algo novo.
TERMOS_NOVIDADE: tuple[str, ...] = (
    "institui o programa",
    "institui o auxilio",
    "cria o programa",
    "fica instituido",
    "regulamenta o programa",
    "novo programa",
    "beneficio",
    "auxilio",
    "calendario de pagamento",
)


def filtrar_novidade(
    itens: Iterable[Item], termos: Sequence[str] = TERMOS_NOVIDADE
) -> list[Item]:
    """Filtro barato, sem LLM, de itens que cheiram a novidade regulatoria.

    Deliberadamente burro: o PRD manda o cron NAO chamar o LLM. Isto so
    reduz o volume diario (3.600 atos) para uma fila que o hermes consegue
    ler. Falso positivo aqui e barato; falso negativo e que custa.
    """
    alvos = [_sem_acento(t) for t in termos]
    out = []
    for it in itens:
        blob = _sem_acento(f"{it.get('titulo','')} {it.get('texto','')}")
        achados = [t for t in alvos if t in blob]
        if achados:
            it = dict(it)
            it["meta"] = {**it.get("meta", {}), "termos_casados": achados}
            out.append(it)
    return out


# ==========================================================================
# FONTE 1 -- DOU, leitura do jornal do dia.  FUNCIONA.
# ==========================================================================

DOU_BASE = "https://www.in.gov.br"

#: Secoes do DOU. do1=atos normativos (onde nasce programa novo), do2=pessoal,
#: do3=contratos/licitacoes, *e = edicao extra (onde sai o ato urgente).
DOU_SECOES_PADRAO: tuple[str, ...] = ("do1", "do1e")
DOU_SECOES_TODAS: tuple[str, ...] = ("do1", "do2", "do3", "do1e", "do2e", "do3e")

_PARAMS_RE = re.compile(
    r'<script id="params" type="application/json">(.*?)</script>', re.S
)


def dou_diario(
    dia: date | None = None,
    secoes: Sequence[str] = DOU_SECOES_PADRAO,
) -> list[Item]:
    """Todos os atos publicados no DOU em um dia, por secao.

    Estado: FUNCIONA (medido 2026-08-05).
    URL base : https://www.in.gov.br/leiturajornal?data=DD-MM-YYYY&secao=do1
    Auth     : nenhuma.
    Formato  : HTML com um <script id="params" type="application/json"> que
               carrega `jsonArray` -- a lista completa de atos do dia. Nao e
               API documentada, e o payload de hidratacao do front. Estavel
               na pratica, mas e um contrato implicito: se o portal trocar de
               front, isto quebra, e a funcao deve falhar alto (KeyError /
               lista vazia), nunca inventar.
    Limite   : nenhum observado -- 12 requisicoes sequenciais, 12x HTTP 200.
    Custo    : do1 ~0,5 MB / do2 ~0,9 MB / do3 ~2,6 MB.

    O campo `content` do jsonArray e um RESUMO truncado (~400 chars) do ato.
    Para o texto integral, use `dou_texto_integral(item["url"])`.

    Este e o caminho certo para a varredura diaria do D2: devolve o dia
    inteiro numa requisicao por secao, sem paginacao.
    """
    dia = dia or date.today()
    itens: list[Item] = []
    for secao in secoes:
        resp = _get(
            f"{DOU_BASE}/leiturajornal",
            params={"data": _br(dia), "secao": secao},
        )
        m = _PARAMS_RE.search(resp.text)
        if not m:
            # Falha alto e explicito: melhor um erro que uma lista vazia
            # silenciosa que faz o operador achar que o DOU nao publicou.
            raise RuntimeError(
                f"DOU secao={secao} data={_br(dia)}: <script id='params'> nao "
                f"encontrado em {len(resp.text)} bytes -- o front do in.gov.br "
                f"provavelmente mudou. NAO assuma dia vazio."
            )
        for a in json.loads(m.group(1)).get("jsonArray", []):
            url_titulo = a.get("urlTitle") or ""
            itens.append(
                _item(
                    titulo=a.get("title") or a.get("titulo") or "",
                    data=_iso(a.get("pubDate")),
                    url=f"{DOU_BASE}/web/dou/-/{url_titulo}" if url_titulo else "",
                    texto=a.get("content") or "",
                    fonte="dou_diario",
                    meta={
                        "secao": secao,
                        "pub_name": a.get("pubName"),
                        "art_type": a.get("artType"),
                        "edicao": a.get("editionNumber"),
                        "pagina": a.get("numberPage"),
                        "orgao": a.get("hierarchyStr"),
                        "hierarquia": a.get("hierarchyList"),
                        "texto_truncado": True,
                    },
                )
            )
    return itens


# ==========================================================================
# FONTE 2 -- DOU, busca por palavra-chave.  FUNCIONA (com teto).
# ==========================================================================

_PARAMS_BUSCA_RE = re.compile(
    r'<script id="_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params" '
    r'type="application/json">(.*?)</script>',
    re.S,
)

#: Valores aceitos por `exactDate`. "personalizado" exige publishFrom/publishTo.
DOU_JANELAS = ("dia", "semana", "mes", "ano", "personalizado")


def dou_busca(
    termo: str,
    *,
    secao: str = "todos",
    janela: str = "dia",
    desde: date | None = None,
    ate: date | None = None,
    limite: int = 50,
) -> list[Item]:
    """Busca por palavra-chave em todo o DOU, incluindo edicoes extras.

    Estado: FUNCIONA (medido 2026-08-05).
    URL base : https://www.in.gov.br/consulta/-/buscar/dou
    Auth     : nenhuma.
    Formato  : HTML com <script id="_br_com_seatecnologia_in_buscadou_
               BuscaDouPortlet_params"> carregando `jsonArray`. O `content`
               vem com <span class='highlight'> ao redor do termo -- este
               modulo remove as tags.
    Limite   : `delta` aceita ate 50. Valores acima (60, 100, 500) sao
               ignorados e a resposta cai para 20.
               *** NAO HA PAGINACAO POR QUERYSTRING. *** Testados e sem
               efeito: currentPage, page, pagina, cur, e o parametro
               Liferay-scoped _..._BuscaDouPortlet_cur. `start=20` quebra o
               payload. Ou seja: esta funcao ve no maximo os 50 melhores
               resultados. Para cobertura completa do dia use `dou_diario`,
               que nao tem esse teto.

    Serve para lookback ("esse programa apareceu no DOU nas ultimas semanas?"),
    nao para varredura exaustiva.
    """
    if janela not in DOU_JANELAS:
        raise ValueError(f"janela deve ser uma de {DOU_JANELAS}, recebi {janela!r}")
    params: dict[str, Any] = {
        "q": termo,
        "s": secao,
        "sortType": 0,  # 0 = relevancia
        "delta": min(limite, 50),
        "exactDate": janela,
    }
    if janela == "personalizado":
        if not (desde and ate):
            raise ValueError("janela='personalizado' exige desde= e ate=")
        params["publishFrom"] = _br(desde)
        params["publishTo"] = _br(ate)

    resp = _get(f"{DOU_BASE}/consulta/-/buscar/dou", params=params)
    m = _PARAMS_BUSCA_RE.search(resp.text)
    if not m:
        raise RuntimeError(
            f"DOU busca q={termo!r}: payload do portlet nao encontrado em "
            f"{len(resp.text)} bytes -- front mudou."
        )
    itens = []
    for a in json.loads(m.group(1)).get("jsonArray", []):
        url_titulo = a.get("urlTitle") or ""
        itens.append(
            _item(
                titulo=a.get("title") or "",
                data=_iso(a.get("pubDate")) or _iso(a.get("displayDate")),
                url=f"{DOU_BASE}/web/dou/-/{url_titulo}" if url_titulo else "",
                texto=a.get("content") or "",
                fonte="dou_busca",
                meta={
                    "termo": termo,
                    "pub_name": a.get("pubName"),
                    "art_type": a.get("artType"),
                    "edicao": a.get("editionNumber"),
                    "orgao": a.get("hierarchyStr"),
                    "hierarquia": a.get("hierarchyList"),
                    "texto_truncado": True,
                },
            )
        )
    return itens


_PARAGRAFO_RE = re.compile(r'class="dou-paragraph"[^>]*>(.*?)</p>', re.S)


def dou_texto_integral(url: str) -> str:
    """Texto integral de um ato do DOU a partir da URL do item.

    Estado: FUNCIONA (medido 2026-08-05 -- 46 paragrafos extraidos de um ato).
    Os paragrafos ficam em <p class="dou-paragraph">. Devolve "" se a pagina
    nao tiver paragrafos (nao levanta: ato pode ser so tabela/imagem).

    Chame sob demanda, so para os itens que ja passaram no filtro -- sao ~3.600
    atos por dia e baixar todos e desperdicio.
    """
    if not url:
        return ""
    resp = _get(url)
    return _limpar(" ".join(_PARAGRAFO_RE.findall(resp.text)))


# ==========================================================================
# FONTE 3 -- Camara dos Deputados, dados abertos.  FUNCIONA.
# ==========================================================================

CAMARA_BASE = "https://dadosabertos.camara.leg.br/api/v2"


def camara_proposicoes(
    termo: str | None = None,
    *,
    dias: int = 7,
    limite: int = 50,
) -> list[Item]:
    """Proposicoes apresentadas na Camara, opcionalmente por palavra-chave.

    Estado: FUNCIONA (medido 2026-08-05).
    URL base : https://dadosabertos.camara.leg.br/api/v2/proposicoes
    Auth     : NENHUMA. API publica, documentada e versionada (v2).
    Formato  : JSON limpo -- {"dados": [...], "links": [...]}. Paginacao real
               por `pagina`/`itens` com links rel=next.
    Limite   : nenhum publicado; nenhum observado.

    `keywords=` filtra por palavra-chave indexada (testado com "auxilio").
    Sem termo, devolve tudo apresentado na janela de `dias`.

    Valor para o D2: pega o programa na TRAMITACAO, antes de virar ato. E o
    sinal mais adiantado de todos -- e tambem o mais ruidoso, porque a maior
    parte das proposicoes nunca vira lei. Use como sinal fraco de S5, nunca
    sozinho.
    """
    params: dict[str, Any] = {
        "dataApresentacaoInicio": (date.today() - timedelta(days=dias)).isoformat(),
        "ordem": "DESC",
        "ordenarPor": "id",
        "itens": min(limite, 100),
    }
    if termo:
        params["keywords"] = termo
    dados = _get(
        f"{CAMARA_BASE}/proposicoes", params=params, accept="application/json"
    ).json()
    itens = []
    for p in dados.get("dados", []):
        sigla = f"{p.get('siglaTipo','')} {p.get('numero','')}/{p.get('ano','')}"
        itens.append(
            _item(
                titulo=sigla.strip(),
                data=_iso(p.get("dataApresentacao")),
                url=f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={p.get('id')}",
                texto=p.get("ementa") or "",
                fonte="camara_proposicoes",
                meta={
                    "id": p.get("id"),
                    "sigla_tipo": p.get("siglaTipo"),
                    "uri_api": p.get("uri"),
                    "termo": termo,
                },
            )
        )
    return itens


# ==========================================================================
# FONTE 4 -- Senado Federal, dados abertos.  FUNCIONA.
# ==========================================================================

SENADO_BASE = "https://legis.senado.leg.br/dadosabertos"


def senado_materias(
    termo: str,
    *,
    ano: int | None = None,
    limite: int = 50,
) -> list[Item]:
    """Materias legislativas do Senado por palavra-chave.

    Estado: FUNCIONA (medido 2026-08-05 -- 26 materias para "auxilio"/2026).
    URL base : https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista
    Auth     : NENHUMA.
    Formato  : XML por default. *** E PRECISO MANDAR `Accept: application/json`
               ***, senao vem XML. A resposta JSON e um XML traduzido: vem
               aninhada em PesquisaBasicaMateria.Materias.Materia, e quando ha
               um unico resultado o campo Materia e um OBJETO, nao lista --
               esta funcao normaliza os dois casos.
    Limite   : nenhum publicado; nenhum observado.

    ATENCAO: o servico irmao `materia/atualizadas` devolve, no proprio corpo,
    um bloco "Descontinuacao" com DataDepreciacao 2025-03-18. Nao construa
    nada em cima dele. `pesquisa/lista` respondeu normal em 2026-08-05, mas
    vale checar o bloco Metadados da resposta periodicamente -- ele e a
    forma como o Senado avisa que vai desligar um endpoint.
    """
    params: dict[str, Any] = {"palavraChave": termo, "ano": ano or date.today().year}
    dados = _get(
        f"{SENADO_BASE}/materia/pesquisa/lista",
        params=params,
        accept="application/json",
    ).json()
    raiz = dados.get("PesquisaBasicaMateria", {})
    mats = raiz.get("Materias", {}).get("Materia", [])
    if isinstance(mats, dict):  # resultado unico vem como objeto
        mats = [mats]
    itens = []
    for m in mats[:limite]:
        codigo = m.get("Codigo")
        itens.append(
            _item(
                titulo=m.get("DescricaoIdentificacao") or "",
                data=_iso(m.get("Data")),
                url=f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}",
                texto=m.get("Ementa") or "",
                fonte="senado_materias",
                meta={
                    "codigo": codigo,
                    "sigla": m.get("Sigla"),
                    "autor": m.get("Autor"),
                    "uri_api": m.get("UrlDetalheMateria"),
                    "termo": termo,
                    "aviso_descontinuacao": raiz.get("Metadados", {}).get(
                        "Descontinuacao"
                    ),
                },
            )
        )
    return itens


# ==========================================================================
# FONTE 5 -- Agencia Gov (EBC), releases do governo federal.  FUNCIONA.
# ==========================================================================

AGENCIA_GOV_RSS = "https://agenciagov.ebc.com.br/rss.xml"


def agencia_gov_noticias(limite: int = 50) -> list[Item]:
    """Releases oficiais do governo federal (Agencia Gov / EBC).

    Estado: FUNCIONA (medido 2026-08-05 -- 15 itens, o mais novo do mesmo dia).
    URL base : https://agenciagov.ebc.com.br/rss.xml
    Auth     : nenhuma.
    Formato  : RSS 2.0. Cada <item> tem title, description, pubDate e
               <guid> COM A URL -- nao ha elemento <link>; quem procurar
               link vai achar que o feed nao tem URL. Ha um
               <content:encoded> mas ele vem VAZIO (CDATA em branco), entao
               `texto` usa a description.
    Limite   : o feed traz ~15 itens (janela curta, ~2 dias). E um feed de
               ultimas, nao um arquivo -- precisa ser lido com frequencia ou
               perde item. Nao ha paginacao.

    Este e o substituto que funciona para gov.br/secom (ver `secom_releases`).
    Valor para o D2: o release costuma sair NO MESMO DIA do ato no DOU, em
    portugues comum, ja com o nome de marketing do programa -- que e
    exatamente o termo que o usuario vai buscar no Google.
    """
    resp = _get(AGENCIA_GOV_RSS)
    raiz = ET.fromstring(resp.content)
    itens = []
    for it in raiz.findall(".//item")[:limite]:
        g = lambda t: (it.findtext(t) or "").strip()  # noqa: E731
        itens.append(
            _item(
                titulo=g("title"),
                data=_iso(g("pubDate")),
                # guid carrega a URL; <link> nao existe neste feed.
                url=g("link") or g("guid"),
                texto=g("description"),
                fonte="agencia_gov",
                meta={"pub_date_bruta": g("pubDate")},
            )
        )
    return itens


# ==========================================================================
# FONTE 6 -- Querido Diario (OKBR).  FUNCIONA, mas e MUNICIPAL.
# ==========================================================================

#: *** O host importa. *** https://queridodiario.ok.org.br/api/... devolve
#: HTTP 200 com o HTML do SPA (content-type text/html) para QUALQUER caminho
#: -- parece que funcionou e nao funcionou. A API real e outro host.
QUERIDO_DIARIO_BASE = "https://api.queridodiario.ok.org.br"


def querido_diario(
    termo: str,
    *,
    desde: date | None = None,
    ate: date | None = None,
    limite: int = 20,
) -> list[Item]:
    """Busca full-text em diarios oficiais MUNICIPAIS agregados pela OKBR.

    Estado: FUNCIONA (medido 2026-08-05).
    URL base : https://api.queridodiario.ok.org.br/gazettes
    Auth     : NENHUMA.
    Formato  : JSON {"total_gazettes": int, "gazettes": [...]}, com
               `excerpts` (trechos com o termo), `territory_name`,
               `state_code`, `url` (PDF) e `txt_url` (texto puro).
               OpenAPI publicado em /openapi.json (versao 0.19.0 em
               2026-08-05); tambem existem /cities, /gazettes/by_theme/...
    Limite   : nenhum publicado; nenhum observado.

    *** ESCOPO -- LEIA ANTES DE PRIORIZAR ISTO. ***
    Querido Diario agrega diarios MUNICIPAIS. Nao contem o DOU federal. Na
    verificacao de 2026-08-05, "institui o programa" desde 01/08 devolveu 11
    diarios, o primeiro de Sampaio/TO (programa municipal de vacinacao em
    escolas). Para a operacao de arbitragem, que compra busca de alcance
    nacional, isso e quase todo ruido: um programa de um municipio de 4 mil
    habitantes nao gera volume de busca. Mantenha como fonte de terceira
    ordem -- util so para capital/regiao metropolitana grande, e mesmo assim
    depois que D1/D2 federais estiverem rodando.
    """
    params: dict[str, Any] = {"querystring": termo, "size": limite}
    if desde:
        params["published_since"] = desde.isoformat()
    if ate:
        params["published_until"] = ate.isoformat()
    dados = _get(
        f"{QUERIDO_DIARIO_BASE}/gazettes", params=params, accept="application/json"
    ).json()
    itens = []
    for g in dados.get("gazettes", []):
        local = f"{g.get('territory_name','')}/{g.get('state_code','')}"
        itens.append(
            _item(
                titulo=f"Diario Oficial de {local} - ed. {g.get('edition','?')}",
                data=_iso(g.get("date")),
                url=g.get("url") or g.get("txt_url") or "",
                texto=" ".join(g.get("excerpts") or []),
                fonte="querido_diario",
                meta={
                    "territorio": g.get("territory_name"),
                    "uf": g.get("state_code"),
                    "edicao_extra": g.get("is_extra_edition"),
                    "txt_url": g.get("txt_url"),
                    "total_na_busca": dados.get("total_gazettes"),
                    "escopo": "municipal",
                    "termo": termo,
                },
            )
        )
    return itens


# ==========================================================================
# FONTES BLOQUEADAS -- existem, foram testadas, nao funcionam. Documentado.
# ==========================================================================


def govbr_plone_noticias(orgao: str = "mds", limite: int = 20) -> list[Item]:
    """Noticias de um ministerio via API REST do gov.br.  *** BLOQUEADA. ***

    Os sites gov.br/<orgao> rodam Plone e portanto EXPOEM plone.restapi em
    `/@search`, que seria o jeito limpo de pegar noticia de ministerio com
    filtro por tipo e data. O endpoint responde, mas nega:

        GET https://www.gov.br/mds/pt-br/noticias/@search
            ?portal_type=Noticia&sort_on=Date&sort_order=descending
        Accept: application/json
        -> HTTP 401
           {"message": "Missing 'plone.restapi: Use REST API' permission",
            "type": "Unauthorized"}

    Nao ha como contornar sem credencial: a permissao de usar a REST API nao
    e concedida ao anonimo. Nao existe token publico documentado.

    O RSS classico do Plone tambem nao esta disponivel:
        /mds/pt-br/noticias/RSS            -> HTTP 404 {"error_type":"NotFound"}
        /pt-br/noticias/ultimas-noticias/RSS -> HTTP 404 {"error_type":"NotFound"}
        /inss/pt-br/noticias/RSS           -> HTTP 200 mas devolve text/html
                                              (a pagina normal; o sufixo RSS e
                                              ignorado -- 200 enganoso)
        /pt-br/noticias/RSS                -> HTTP 200 RSS 1.0 VALIDO, porem
                                              contem 1 unico item, que e o
                                              link da PASTA "ultimas-noticias",
                                              nao as noticias. Inutil.

    ALTERNATIVA QUE FUNCIONA: `agencia_gov_noticias()`, que cobre releases do
    governo federal inteiro, incluindo os ministerios.

    Ultima verificacao: 2026-08-05.
    """
    raise FonteBloqueada(
        "gov.br plone.restapi: HTTP 401 "
        '{"message": "Missing \'plone.restapi: Use REST API\' permission", '
        '"type": "Unauthorized"} em '
        f"https://www.gov.br/{orgao}/pt-br/noticias/@search -- permissao nao "
        "concedida ao anonimo, sem token publico. RSS do Plone tambem indisponivel "
        "(404, ou 200 devolvendo HTML). Use agencia_gov_noticias(). "
        "Verificado em 2026-08-05."
    )


def secom_releases(limite: int = 20) -> list[Item]:
    """Releases da Secom/Presidencia.  *** BLOQUEADA -- caminho nao existe. ***

    O caminho citado no briefing nao existe mais no portal:

        GET https://www.gov.br/secom/pt-br/assuntos/noticias
            -> HTTP 404, content-type application/json, corpo exato:
               {"error_type": "NotFound"}
        GET https://www.gov.br/secom/pt-br/assuntos/noticias/RSS
            -> HTTP 404, mesmo corpo.

    Repare que o 404 vem como JSON da borda, nao como pagina de erro do
    Plone: quem so olhar o content-type pode achar que e uma API.

    Nao e bloqueio de bot -- o mesmo User-Agent pega HTTP 200 em outros
    caminhos gov.br no mesmo instante (ex.: /pt-br/noticias e /mds/pt-br/
    noticias devolveram 200). E caminho errado/removido.

    ALTERNATIVA QUE FUNCIONA: `agencia_gov_noticias()` -- a Agencia Gov e o
    canal de release do governo federal e tem RSS aberto.

    Ultima verificacao: 2026-08-05.
    """
    raise FonteBloqueada(
        "gov.br/secom: HTTP 404 {\"error_type\": \"NotFound\"} em "
        "https://www.gov.br/secom/pt-br/assuntos/noticias e em .../noticias/RSS. "
        "Caminho removido/inexistente (nao e bloqueio: outros caminhos gov.br "
        "devolvem 200 com o mesmo UA). Use agencia_gov_noticias(). "
        "Verificado em 2026-08-05."
    )


def dados_gov_br_conjuntos(busca: str = "dou", limite: int = 20) -> list[Item]:
    """Catalogo de dados abertos federal.  *** BLOQUEADA -- exige chave. ***

    O portal responde (o host esta no ar, HTTP 200 na home), mas a API exige
    chave de API e devolve 401 com CORPO VAZIO -- sem mensagem, sem dica:

        GET https://dados.gov.br/api/publico/conjuntos-dados?nomeConjuntoDados=dou
            -> HTTP 401, content-length 0
        GET https://dados.gov.br/dados/api/publico/conjuntos-dados?...
            -> HTTP 401, content-length 0

    A chave e obtida por cadastro no proprio portal (login gov.br) e vai no
    header `chave-api-dados-abertos`. Nao ha acesso anonimo.

    AVALIACAO PARA O D2: mesmo com chave, isto e um CATALOGO de datasets --
    diz quais conjuntos de dados existem, nao publica o ato novo. Nao e uma
    fonte de novidade regulatoria. Prioridade baixa; nao vale o cadastro
    agora.

    Ultima verificacao: 2026-08-05.
    """
    raise FonteBloqueada(
        "dados.gov.br: HTTP 401 com corpo vazio (content-length 0) em "
        "https://dados.gov.br/api/publico/conjuntos-dados -- exige header "
        "'chave-api-dados-abertos' obtido por cadastro com login gov.br. "
        "Sem acesso anonimo. Alem disso e catalogo de datasets, nao fonte de "
        "ato novo -- baixa prioridade para o D2. Verificado em 2026-08-05."
    )


# ==========================================================================
# Registro + varredura
# ==========================================================================

#: nome -> (callable, funciona?, uma linha de descricao)
FONTES: dict[str, tuple[Any, bool, str]] = {
    "dou_diario": (dou_diario, True, "DOU do dia, secoes do1+do1e (varredura D2)"),
    "dou_busca": (dou_busca, True, "DOU por palavra-chave, teto de 50, sem paginacao"),
    "camara_proposicoes": (camara_proposicoes, True, "Camara, proposicoes por keyword"),
    "senado_materias": (senado_materias, True, "Senado, materias por palavra-chave"),
    "agencia_gov": (agencia_gov_noticias, True, "Releases do governo federal (RSS)"),
    "querido_diario": (querido_diario, True, "Diarios MUNICIPAIS (OKBR) - baixo valor"),
    "govbr_plone": (govbr_plone_noticias, False, "BLOQUEADA: 401 plone.restapi"),
    "secom": (secom_releases, False, "BLOQUEADA: 404, caminho inexistente"),
    "dados_gov_br": (dados_gov_br_conjuntos, False, "BLOQUEADA: 401, exige chave"),
}


def coletar_tudo(
    dia: date | None = None, termo: str = "auxilio"
) -> dict[str, dict[str, Any]]:
    """Roda todas as fontes e devolve o resultado real de cada uma.

    Nunca levanta: cada fonte e isolada, e o erro (inclusive FonteBloqueada)
    vira dado no relatorio. Um sentinela que morre porque uma fonte caiu nao
    e um sentinela.
    """
    dia = dia or date.today()
    chamadas = [
        ("dou_diario", lambda: dou_diario(dia)),
        ("dou_busca", lambda: dou_busca(termo, janela="dia")),
        ("camara_proposicoes", lambda: camara_proposicoes(termo, dias=7)),
        ("senado_materias", lambda: senado_materias(termo)),
        ("agencia_gov", lambda: agencia_gov_noticias()),
        ("querido_diario", lambda: querido_diario(termo, desde=dia - timedelta(days=3))),
        ("govbr_plone", lambda: govbr_plone_noticias()),
        ("secom", lambda: secom_releases()),
        ("dados_gov_br", lambda: dados_gov_br_conjuntos()),
    ]
    out: dict[str, dict[str, Any]] = {}
    for nome, fn in chamadas:
        try:
            itens = fn()
            out[nome] = {"ok": True, "n": len(itens), "itens": itens, "erro": None}
        except FonteBloqueada as e:
            out[nome] = {"ok": False, "n": 0, "itens": [], "erro": f"BLOQUEADA: {e}"}
        except Exception as e:  # rede, parsing, mudanca de contrato
            out[nome] = {
                "ok": False,
                "n": 0,
                "itens": [],
                "erro": f"{type(e).__name__}: {e}",
            }
    return out


def _cli() -> int:
    dia = date.today()
    termo = "auxilio"
    if len(sys.argv) > 1:
        dia = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    if len(sys.argv) > 2:
        termo = sys.argv[2]

    print(f"F03/D2 - fontes BR  |  dia={dia.isoformat()}  termo={termo!r}")
    print(f"UA={USER_AGENT}")
    print("=" * 78)

    res = coletar_tudo(dia, termo)
    for nome, r in res.items():
        marca = "OK  " if r["ok"] else "FALHA"
        print(f"\n[{marca}] {nome}: {r['n']} itens")
        if r["erro"]:
            print(f"       {r['erro'][:400]}")
        for it in r["itens"][:3]:
            print(f"       - {it['data']} | {it['titulo'][:64]}")
            if it["url"]:
                print(f"         {it['url'][:100]}")

    # Recorte D2: quanto do DOU do dia cheira a novidade regulatoria.
    dou = res.get("dou_diario", {}).get("itens", [])
    if dou:
        filtrados = filtrar_novidade(dou)
        print("\n" + "=" * 78)
        print(
            f"FILTRO D2 (sem LLM): {len(filtrados)} de {len(dou)} atos do DOU casaram "
            f"com TERMOS_NOVIDADE"
        )
        for it in filtrados[:5]:
            print(
                f"  - {it['data']} | {it['titulo'][:56]} "
                f"| {it['meta'].get('termos_casados')}"
            )
            print(f"    {it['url'][:100]}")

    ok = sum(1 for r in res.values() if r["ok"])
    total_itens = sum(r["n"] for r in res.values())
    print("\n" + "=" * 78)
    print(f"RESUMO: {ok}/{len(res)} fontes responderam | {total_itens} itens no total")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
