"""As varreduras — funções PURAS sobre o HTML de uma página, sem rede.

Cada varredura devolve uma `Verificacao`: o inventário do que foi observado, os
achados, e — o campo que mais importa — o STATUS de quem olhou. `unavailable`
aqui não é detalhe de implementação: é o que o portão transforma em reprova no
destino pago.

## Uma decisão que atravessa o arquivo: autorização vem de EVIDÊNCIA

Não há allowlist de host "confiável". Um host externo é classificado como
`fonte_declarada` quando quem chamou o portão trouxe a evidência daquela página
(a pesquisa que o motor fez, o inventário adtech que a casa declarou). Sem
evidência ele é `terceiro_desconhecido` — e desconhecido reprova destino pago.

É a mesma doutrina do `funnelforge.pipeline.validators.checks.same_domain`, e
pelo mesmo motivo: lista estática bloqueia o canal oficial de que a página
precisa e deixa passar o que entrou pela prosa.

## O HTML é dado, nunca instrução

Todo `html` que entra aqui é conteúdo público não confiável — preservado de um
site que pode estar comprometido. Ele é PARSEADO, nunca executado, nunca
interpretado como ordem, e nada dele é copiado inteiro para o artefato.
"""
from __future__ import annotations

import html as _html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from app.landing_policy.contrato import (
    STATUS_AUSENCIA_CONFIRMADA,
    STATUS_INDISPONIVEL,
    STATUS_NAO_APLICAVEL,
    STATUS_OBSERVADO,
    Achado,
    V_ALEGACOES,
    V_CONTEUDO,
    V_DERIVA,
    V_FORMULARIOS,
    V_GOVERNO,
    V_IDENTIDADE,
    V_LINKS_EXTERNOS,
    V_REDIRECIONAMENTO,
    V_SEGURANCA,
    Verificacao,
)


@dataclass(frozen=True)
class PaginaObservada:
    """Tudo que se sabe sobre uma página, e o que se sabe que NÃO se sabe.

    `variantes_sha256` é o mapa `rótulo de user-agent -> sha256 do HTML`. Com
    duas entradas divergentes, cloaking é observável; com uma só, a verificação
    é honestamente `unavailable` — não "limpa".
    """

    url: str
    html: str
    status_http: int | None = None
    saltos_redirecionamento: list[dict[str, Any]] | None = None
    cabecalhos: dict[str, str] = field(default_factory=dict)
    variantes_sha256: dict[str, str] = field(default_factory=dict)
    #: SHA-256 do HTML que a casa APROVOU. Sem ele não há como falar em deriva.
    sha256_aprovado: str | None = None
    sha256_observado: str | None = None
    #: Hosts que a pesquisa/declaração daquela página trouxe (não é allowlist).
    hosts_declarados: tuple[str, ...] = ()
    #: Hosts de adtech que a casa declara usar naquele site.
    adtech_declarada: tuple[str, ...] = ()
    #: CNPJ do operador, para conferir contra o que a página exibe.
    cnpj_esperado: str | None = None
    #: A promessa do anúncio, quando existe, para medir congruência.
    promessa_do_anuncio: str = ""
    #: Slugs/URLs iguais observados em OUTRO domínio (evidência, não suposição).
    duplicatas_entre_dominios: tuple[str, ...] = ()
    origem: str = "local_artifact"
    observado_em: str = ""


# ── parsing ────────────────────────────────────────────────────────────────

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|noscript)\b.*?</\1>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")


class _Parser(HTMLParser):
    """Colhe só o que as varreduras usam. Nunca executa nada."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, Any]] = []
        self.forms: list[dict[str, str]] = []
        self.inputs: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.iframes: list[str] = []
        self.imgs: list[str] = []
        #: `preload`/`preconnect`/`dns-prefetch` — a página DECLARA aqui com quem
        #: vai falar. Ignorá-los foi como `script.joinads.me` passou despercebido
        #: na primeira varredura: ele só aparece nesses rel, porque o `<script>`
        #: que o executa é uma cópia minificada servida pelo próprio domínio.
        self.hints: list[dict[str, str]] = []
        self.canonical: str | None = None
        self._pilha_ancora: list[dict[str, Any]] = []
        self._profundidade_botao = 0
        self._em_script = False
        self._texto_script: list[str] = []
        self._attrs_script: dict[str, str] = {}

    # `wp:buttons`/`.wp-block-button`/`.elementor-button` marcam o clique que a
    # página EMPURRA — é outra coisa que uma citação em prosa, e a política
    # trata as duas de forma diferente.
    _CLASSES_BOTAO = ("wp-block-button", "elementor-button", "su-button", "btn", "button")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap = {k.lower(): (v or "") for k, v in attrs}
        t = tag.lower()
        classe = amap.get("class", "").lower()
        if any(c in classe for c in self._CLASSES_BOTAO):
            self._profundidade_botao += 1
        if t == "link":
            rel = amap.get("rel", "").lower()
            if rel == "canonical":
                self.canonical = amap.get("href") or self.canonical
            elif rel in ("preload", "preconnect", "dns-prefetch", "modulepreload"):
                self.hints.append({"rel": rel, "href": amap.get("href", ""),
                                   "as": amap.get("as", "")})
        elif t == "a":
            registro = {
                "href": amap.get("href", ""),
                "rel": amap.get("rel", ""),
                "target": amap.get("target", ""),
                "classe": classe,
                "em_botao": self._profundidade_botao > 0
                or any(c in classe for c in self._CLASSES_BOTAO),
                "_texto": [],
            }
            self.links.append(registro)
            self._pilha_ancora.append(registro)
        elif t == "form":
            self.forms.append(
                {
                    "action": amap.get("action", ""),
                    "method": (amap.get("method") or "get").lower(),
                    "classe": classe,
                    "id": amap.get("id", ""),
                    "role": amap.get("role", ""),
                }
            )
        elif t in ("input", "select", "textarea"):
            self.inputs.append(
                {
                    "tag": t,
                    "type": (amap.get("type") or "").lower(),
                    "name": amap.get("name", ""),
                    "id": amap.get("id", ""),
                    "placeholder": amap.get("placeholder", ""),
                    "autocomplete": amap.get("autocomplete", ""),
                }
            )
        elif t == "script":
            self._em_script = True
            self._attrs_script = amap
            self._texto_script = []
        elif t == "iframe":
            self.iframes.append(amap.get("src", ""))
        elif t == "img":
            self.imgs.append(amap.get("src") or amap.get("data-src") or "")

    def handle_data(self, data: str) -> None:
        if self._em_script:
            self._texto_script.append(data)
        for registro in self._pilha_ancora:
            registro["_texto"].append(data)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "script" and self._em_script:
            self.scripts.append({**self._attrs_script, "texto": "".join(self._texto_script)})
            self._em_script = False
            self._attrs_script = {}
            self._texto_script = []
        elif t == "a" and self._pilha_ancora:
            self._pilha_ancora.pop()
        elif self._profundidade_botao > 0 and t in ("div", "span", "a", "li"):
            # Heurística: fecha o escopo de botão no fim do contêiner mais
            # provável. Erra para MENOS botão, nunca para mais — um botão não
            # reconhecido vira link em prosa, que é a classificação mais frouxa,
            # e por isso o `em_botao` também é setado na própria âncora.
            self._profundidade_botao -= 1


def analisar(html: str) -> _Parser:
    p = _Parser()
    p.feed(html or "")
    for registro in p.links:
        registro["texto"] = re.sub(r"\s+", " ", "".join(registro.pop("_texto"))).strip()
    return p


def texto_visivel(html: str) -> str:
    sem_codigo = _SCRIPT_STYLE_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", _html.unescape(_TAG_RE.sub(" ", sem_codigo))).strip()


# ── classificação de host ──────────────────────────────────────────────────

_SUFIXOS_GOVERNO = (".gov.br", ".gov", ".jus.br", ".leg.br", ".mp.br", ".gov.uk", ".gob.es")
_ADTECH_GOOGLE = (
    "googlesyndication.com",
    "doubleclick.net",
    "googletagservices.com",
    "googletagmanager.com",
    "google-analytics.com",
    "adservice.google.com",
    "googleadservices.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "gstatic.com",
)

CLASSE_MESMO_SITE = "mesmo_site"
CLASSE_GOVERNO = "governo_oficial"
CLASSE_ADTECH_GOOGLE = "adtech_google"
CLASSE_ADTECH_DECLARADA = "adtech_declarada"
CLASSE_FONTE_DECLARADA = "fonte_declarada"
CLASSE_TERCEIRO_DESCONHECIDO = "terceiro_desconhecido"
CLASSE_RELATIVO = "relativo"


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().split("@")[-1].split(":")[0]
    except ValueError:
        return ""


def _mesmo_site(host: str, site: str) -> bool:
    if not host or not site:
        return False
    return host == site or host.endswith("." + site) or site.endswith("." + host)


def e_governo(host: str) -> bool:
    return bool(host) and any(host == s.lstrip(".") or host.endswith(s) for s in _SUFIXOS_GOVERNO)


def classificar_host(host: str, pagina: PaginaObservada) -> str:
    site = _host(pagina.url)
    if not host:
        return CLASSE_RELATIVO
    if _mesmo_site(host, site):
        return CLASSE_MESMO_SITE
    if e_governo(host):
        return CLASSE_GOVERNO
    if any(host == a or host.endswith("." + a) for a in _ADTECH_GOOGLE):
        return CLASSE_ADTECH_GOOGLE
    if any(_mesmo_site(host, a.lower()) for a in pagina.adtech_declarada):
        return CLASSE_ADTECH_DECLARADA
    if any(_mesmo_site(host, d.lower()) for d in pagina.hosts_declarados):
        return CLASSE_FONTE_DECLARADA
    return CLASSE_TERCEIRO_DESCONHECIDO


# ── identidade ─────────────────────────────────────────────────────────────

_CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
_ROTULOS_CONTATO = ("contato", "fale conosco", "contact")
_ROTULOS_SOBRE = ("sobre", "quem somos", "about")
_ROTULOS_PRIVACIDADE = ("privacidade", "privacy", "termos", "terms")

#: Credencial/parceria que a página AFIRMA ter. Afirmar sem lastro é o defeito
#: que a política de misrepresentation descreve como omitir/obscurecer
#: qualificação — e é também a coisa mais fácil de um gerador de texto inventar.
#: O `s?` do plural não é detalhe: "somos licenciados pelo Banco Central" é a
#: forma mais natural da frase, e a versão sem plural não a pegava.
_CREDENCIAL_RE = re.compile(
    r"(?i)\b(licenciad[oa]s?|credenciad[oa]s?|autorizad[oa]s?\s+pel[oa]|parceir[oa]s?\s+oficia(l|is)|"
    r"correspondentes?\s+banc[áa]ri[oa]s?|representantes?\s+oficia(l|is)|conveniad[oa]s?)\b"
)
_NAO_AFILIACAO_RE = re.compile(
    r"(?i)(n[ãa]o\s+(possui|possuem|temos|tem|h[áa])\s+(nenhum\s+)?(v[íi]nculo|rela[çc][ãa]o|liga[çc][ãa]o))"
    r"|(sem\s+v[íi]nculo)"
    r"|(n[ãa]o\s+(somos|é|e)\s+(um\s+)?(site|canal|portal)\s+(oficial|do\s+governo))"
    r"|(n[ãa]o\s+possuem\s+v[íi]nculo)"
)
_MONETIZACAO_RE = re.compile(r"(?i)(adsense|google\s+ads|blocos?\s+de\s+an[úu]ncios?|publicidade)")

#: A moldura de RECOMENDAÇÃO: "banco parceiro, como o X ou o Y". O que vem
#: depois dela é uma marca de terceiro apresentada como canal — e apresentar
#: marca de terceiro como canal sem lastro é a forma mais barata de fazer o
#: leitor achar que existe uma parceria que ninguém comprovou.
_MOLDURA_DE_PARCERIA_RE = re.compile(
    r"(?i)(bancos?\s+parceir[oa]s?|institui[çc][õo]es?\s+parceiras?|"
    r"(?:bancos?|aplicativos?|institui[çc][õo]es?|empresas?|fintechs?)\s+como)"
    r"[^.;!?]{0,120}"
)
#: Nome próprio de duas letras ou mais iniciando por maiúscula, ignorando o que
#: abre frase. Não é NER — é o suficiente para exigir lastro, não para acusar.
_NOME_PROPRIO_RE = re.compile(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]{2,})\b")
_NAO_SAO_MARCAS = {
    "Banco", "Bancos", "Caixa", "Pix", "Como", "Para", "Você", "Voce", "Este",
    "Esta", "Isso", "Além", "Depois", "Antes", "Fundo", "Aplicativo", "Governo",
}


def _marcas_sem_lastro(texto: str, hosts_declarados: set[str]) -> list[str]:
    """Marcas apresentadas como canal dentro de uma moldura de parceria.

    Uma marca cujo nome aparece em algum host declarado está com lastro e sai da
    lista — a evidência é a declaração daquela página, nunca uma allowlist de
    marcas "boas". Sem moldura de parceria não há acusação: citar "Santander"
    num texto é jornalismo, apresentá-lo como "banco parceiro" é outra coisa.
    """
    achados: list[str] = []
    for trecho in _MOLDURA_DE_PARCERIA_RE.finditer(texto):
        corpo = trecho.group(0)
        for nome in _NOME_PROPRIO_RE.findall(corpo):
            if nome in _NAO_SAO_MARCAS:
                continue
            chave = nome.lower()
            if any(chave in host for host in hosts_declarados):
                continue
            if nome not in achados:
                achados.append(nome)
    return achados[:5]


def varrer_identidade(pagina: PaginaObservada) -> Verificacao:
    parser = analisar(pagina.html)
    texto = texto_visivel(pagina.html)
    baixo = texto.lower()
    achados: list[Achado] = []

    cnpjs = sorted(set(_CNPJ_RE.findall(texto)))
    tem_contato = any(r in baixo for r in _ROTULOS_CONTATO) or any(
        r in (l.get("texto") or "").lower() for l in parser.links for r in _ROTULOS_CONTATO
    )
    tem_sobre = any(r in baixo for r in _ROTULOS_SOBRE)
    tem_privacidade = any(r in baixo for r in _ROTULOS_PRIVACIDADE)
    tem_nao_afiliacao = bool(_NAO_AFILIACAO_RE.search(texto))
    tem_monetizacao = bool(_MONETIZACAO_RE.search(texto))

    if not cnpjs and not (tem_sobre and tem_contato):
        achados.append(
            Achado(
                "IDENTIDADE_OPERADOR_AUSENTE",
                "Nenhuma identidade de operador observada: sem CNPJ e sem bloco "
                "'sobre'+'contato' na página.",
                evidencia={"cnpj_observado": False, "sobre": tem_sobre, "contato": tem_contato},
            )
        )
    if not tem_contato or not tem_privacidade:
        achados.append(
            Achado(
                "IDENTIDADE_CONTATO_AUSENTE",
                "Faltam os caminhos de contato/privacidade que identificam quem responde pela página.",
                evidencia={"contato": tem_contato, "privacidade": tem_privacidade},
            )
        )
    esperado = (pagina.cnpj_esperado or "").strip()
    if esperado and cnpjs and esperado not in cnpjs:
        achados.append(
            Achado(
                "IDENTIDADE_CNPJ_DIVERGENTE",
                "A página exibe um CNPJ diferente do CNPJ declarado do operador.",
                evidencia={"na_pagina": cnpjs, "esperado_presente": False},
            )
        )
    for m in _CREDENCIAL_RE.finditer(texto):
        achados.append(
            Achado(
                "IDENTIDADE_CREDENCIAL_NAO_COMPROVADA",
                "A página afirma credencial/parceria. O portão não tem como comprovar "
                "isso e não inventa lastro: exige evidência anexada ou a remoção da afirmação.",
                evidencia={"trecho": texto[max(0, m.start() - 60) : m.end() + 60]},
            )
        )
        break
    if not tem_monetizacao:
        achados.append(
            Achado(
                "DIVULGACAO_DE_MONETIZACAO_AUSENTE",
                "Nenhuma divulgação de monetização por anúncios observada.",
            )
        )

    declarados = {d.lower() for d in pagina.hosts_declarados}
    for marca in _marcas_sem_lastro(texto, declarados):
        achados.append(
            Achado(
                "MARCA_TERCEIRA_SEM_LASTRO",
                "A página apresenta uma marca de terceiro como canal/parceiro e não há "
                "host declarado que sustente isso. O portão não inventa parceria.",
                evidencia={"marca": marca},
            )
        )

    inventario = [
        {"sinal": "cnpj", "presente": bool(cnpjs), "quantidade": len(cnpjs)},
        {"sinal": "sobre", "presente": tem_sobre},
        {"sinal": "contato", "presente": tem_contato},
        {"sinal": "privacidade", "presente": tem_privacidade},
        {"sinal": "nao_afiliacao", "presente": tem_nao_afiliacao},
        {"sinal": "divulgacao_monetizacao", "presente": tem_monetizacao},
    ]
    return Verificacao(
        nome=V_IDENTIDADE,
        status=STATUS_OBSERVADO if texto else STATUS_INDISPONIVEL,
        achados=achados,
        inventario=inventario,
        detalhe="" if texto else "página sem texto visível para inspecionar",
    )


# ── links externos ─────────────────────────────────────────────────────────

#: Âncora que é só um VALOR — número, percentual, dinheiro, prazo. Amarrar um
#: valor a um link de governo faz o leitor ler "este número vem de lá", que é
#: exatamente a implicação de vínculo que a política proíbe.
_ANCORA_DE_VALOR_RE = re.compile(
    r"^(?:r?\$\s*)?[\d][\d\s.,]*\s*"
    r"(?:%|reais?|r\$|dias?|meses?|anos?|horas?|parcelas?|saques?\s+anuais?|x)?\.?$",
    re.I,
)


def _ancora_e_valor(texto: str) -> bool:
    limpo = (texto or "").strip()
    if not limpo or len(limpo) > 40:
        return False
    if not any(c.isdigit() for c in limpo):
        return False
    return bool(_ANCORA_DE_VALOR_RE.match(limpo))


def varrer_links(pagina: PaginaObservada) -> Verificacao:
    parser = analisar(pagina.html)
    achados: list[Achado] = []
    inventario: list[dict[str, Any]] = []
    vistos_desconhecidos: set[str] = set()

    for link in parser.links:
        href = (link.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absoluto = urljoin(pagina.url or "", href)
        host = _host(absoluto)
        classe = classificar_host(host, pagina)
        texto = link.get("texto") or ""
        item = {
            "host": host,
            "classe": classe,
            "ancora": texto[:80],
            "ancora_e_valor": _ancora_e_valor(texto),
            "em_botao": bool(link.get("em_botao")),
            "rel": link.get("rel", ""),
        }
        inventario.append(item)

        if classe != CLASSE_GOVERNO and re.search(r"(?i)\b(caixa|gov\.br|governo|inss|receita\s+federal)\b", texto):
            achados.append(
                Achado(
                    "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE",
                    "Texto do link usa marca/órgão público, mas o destino não é domínio governamental.",
                    evidencia={"host": host, "ancora": texto[:60]},
                )
            )
        if classe == CLASSE_GOVERNO and item["ancora_e_valor"]:
            achados.append(
                Achado(
                    "LINK_GOVERNO_COM_ANCORA_DE_VALOR",
                    "Link para site de governo com âncora que é só um valor. O leitor lê "
                    "o número como se fosse dado do órgão, e a página não é do órgão.",
                    evidencia={"host": host, "ancora": texto[:60]},
                )
            )
        if classe == CLASSE_TERCEIRO_DESCONHECIDO and host not in vistos_desconhecidos:
            vistos_desconhecidos.add(host)
            achados.append(
                Achado(
                    "LINK_EXTERNO_NAO_CLASSIFICADO",
                    "Host externo sem evidência declarada. Sem lastro, o portão não "
                    "classifica — e o que não classifica não aprova.",
                    evidencia={"host": host, "em_botao": bool(link.get("em_botao"))},
                )
            )
            if link.get("em_botao"):
                achados.append(
                    Achado(
                        "BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO",
                        "Botão manda o clique comprado para um terceiro sem lastro declarado.",
                        evidencia={"host": host, "ancora": texto[:60]},
                    )
                )
        if classe == CLASSE_GOVERNO and link.get("em_botao"):
            achados.append(
                Achado(
                    "AFILIACAO_GOVERNAMENTAL_IMPLICITA",
                    "O botão principal aponta para um site de governo: para o leitor, a "
                    "página está entregando o serviço oficial.",
                    evidencia={"host": host, "ancora": texto[:60]},
                )
            )
        if texto and not item["ancora_e_valor"] and _ancora_incongruente(texto, absoluto):
            achados.append(
                Achado(
                    "ANCORA_INCONGRUENTE_COM_DESTINO",
                    "O texto do link promete um assunto que o caminho do destino não contém.",
                    evidencia={"ancora": texto[:60], "caminho": urlparse(absoluto).path[:80]},
                )
            )

    return Verificacao(
        nome=V_LINKS_EXTERNOS,
        status=STATUS_OBSERVADO if inventario else STATUS_AUSENCIA_CONFIRMADA,
        achados=achados,
        inventario=inventario,
    )


_STOP = {
    "a", "o", "as", "os", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "para",
    "por", "com", "que", "se", "ver", "veja", "como", "seu", "sua", "meu", "minha", "um",
    "uma", "ao", "aos", "the", "of", "to", "mais", "sobre", "aqui", "agora", "passo",
}


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _tokens(texto: str) -> set[str]:
    """Tokens comparáveis: minúsculas e SEM ACENTO.

    Sem dobrar o acento, "Direitos e Benefícios" e `/category/beneficios/` não
    têm token em comum e o portão acusa incongruência num link perfeitamente
    congruente — medido no artefato preservado. O caminho da URL quase nunca
    tem acento; o texto do link quase sempre tem.
    """
    return {
        t
        for t in re.split(r"[^0-9a-z]+", _sem_acento((texto or "").lower()))
        if len(t) > 3 and t not in _STOP
    }


def _ancora_incongruente(ancora: str, destino: str) -> bool:
    """Só acusa quando há o que comparar dos DOIS lados.

    Um caminho sem palavras (`/`, `/2026/`) não prova incongruência nenhuma —
    prova que não dá para medir. Acusar ali seria transformar ausência de
    evidência em defeito, que é o erro simétrico ao falso verde.
    """
    caminho = urlparse(destino).path
    alvo = _tokens(caminho.replace("-", " ").replace("/", " "))
    origem = _tokens(ancora)
    if not alvo or not origem or len(caminho.strip("/")) < 4:
        return False
    return not (alvo & origem)


# ── formulários e dado sensível ────────────────────────────────────────────

_CAMPOS_SENSIVEIS = {
    "cpf": r"cpf",
    "cnpj": r"cnpj",
    "rg": r"\brg\b|identidade",
    "nascimento": r"nascimento|birth|data_nasc",
    "telefone": r"telefone|celular|phone|whats",
    "email": r"e-?mail",
    "endereco": r"endere[çc]o|address|\bcep\b",
    "cartao": r"cart[ãa]o|card|cvv|credit",
    "senha": r"senha|password|pwd",
    "otp": r"\botp\b|token|c[óo]digo\s+de\s+autentica[çc][ãa]o|one[-\s]?time",
    "renda": r"renda|salario|sal[áa]rio|income",
    "documento": r"upload|arquivo|file|selfie|foto\s*do",
}
_TIPOS_CREDENCIAL = {"password"}
#: Campo de busca do próprio site não é coleta de dado — é navegação. Sem esta
#: exceção, todo WordPress do mundo vira "formulário de coleta".
_NOMES_DE_BUSCA = {"s", "q", "search", "busca", "query"}


def varrer_formularios(pagina: PaginaObservada) -> Verificacao:
    parser = analisar(pagina.html)
    achados: list[Achado] = []
    inventario: list[dict[str, Any]] = []
    texto_baixo = texto_visivel(pagina.html).lower()
    tem_privacidade = any(r in texto_baixo for r in _ROTULOS_PRIVACIDADE)

    campos_sensiveis: list[str] = []
    for campo in parser.inputs:
        assinatura = " ".join(
            [campo.get("name", ""), campo.get("id", ""), campo.get("placeholder", ""),
             campo.get("autocomplete", "")]
        ).lower()
        tipo = campo.get("type", "")
        busca = campo.get("name", "").lower() in _NOMES_DE_BUSCA or tipo == "search"
        classes = [
            rotulo
            for rotulo, padrao in _CAMPOS_SENSIVEIS.items()
            if re.search(padrao, assinatura)
        ]
        if tipo in _TIPOS_CREDENCIAL:
            classes.append("credencial")
        inventario.append(
            {
                "tag": campo.get("tag"),
                "tipo": tipo,
                "busca_do_site": busca,
                "classes_sensiveis": sorted(set(classes)),
            }
        )
        if busca or not classes:
            continue
        campos_sensiveis.extend(classes)
        if "credencial" in classes or "senha" in classes:
            achados.append(
                Achado(
                    "CAMPO_CREDENCIAL_OBSERVADO",
                    "Campo de senha/credencial observado no destino. É a assinatura "
                    "literal descrita pela política de phishing.",
                    evidencia={"tipo": tipo, "classes": sorted(set(classes))},
                )
            )

    if campos_sensiveis:
        achados.append(
            Achado(
                "FORMULARIO_DADO_SENSIVEL",
                "O destino coleta dado pessoal. Num destino pago isso exige papel "
                "`conversion_page` declarado e divulgação explícita.",
                evidencia={"classes": sorted(set(campos_sensiveis))},
            )
        )
        if not tem_privacidade:
            achados.append(
                Achado(
                    "FORMULARIO_SEM_POLITICA_DE_PRIVACIDADE",
                    "Há coleta de dado e nenhum caminho de política de privacidade observado.",
                )
            )

    for form in parser.forms:
        acao = (form.get("action") or "").strip()
        if acao and _host(urljoin(pagina.url or "", acao)) and classificar_host(
            _host(urljoin(pagina.url or "", acao)), pagina
        ) == CLASSE_TERCEIRO_DESCONHECIDO:
            achados.append(
                Achado(
                    "FORMULARIO_DADO_SENSIVEL",
                    "Formulário posta para um host de terceiro sem lastro declarado.",
                    evidencia={"host_da_acao": _host(urljoin(pagina.url or "", acao))},
                )
            )

    return Verificacao(
        nome=V_FORMULARIOS,
        status=STATUS_OBSERVADO if inventario else STATUS_AUSENCIA_CONFIRMADA,
        achados=achados,
        inventario=inventario,
    )


# ── alegações e divulgações ────────────────────────────────────────────────

#: Promessa de resultado que a página não controla. O intervalo `[^.;!?]{0,60}`
#: existe porque a frase real quase nunca é justaposta — "a liberação do dinheiro
#: costuma ocorrer em poucos minutos" foi medida no ar, e a versão sem intervalo
#: não a pegava. O limite fica dentro da MESMA oração (o `[^.;!?]` não atravessa
#: pontuação), para não casar sujeito de uma frase com predicado de outra.
_RESULTADO_IMPROVAVEL = (
    r"(?i)("
    r"sem\s+consulta\s+(ao\s+)?(spc|serasa)"
    r"|n[ãa]o\s+(realiza[m]?|faz(em)?)\s+consultas?[^.;!?]{0,60}(spc|serasa|prote[çc][ãa]o\s+ao\s+cr[ée]dito)"
    r"|sem\s+an[áa]lise\s+de\s+cr[ée]dito"
    r"|(aprova[çc][ãa]o|libera[çc][ãa]o|dinheiro|cr[ée]dito|pix|sald[o])[^.;!?]{0,60}"
    r"(garantid[oa]|imediat[oa]|na\s+hora|em\s+(poucos\s+)?minutos)"
    r"|100\s*%\s*(de\s+)?(aprova|garantid)"
    r"|garantid[oa]\s+para\s+(todos|negativados)"
    r"|liberad[oa]\s+pelo\s+governo"
    r"|nome\s+limpo\s+(em|na)\s+\d+"
    r")"
)
#: Valor monetário bem formado em pt-BR. O que NÃO casa e ainda assim parece
#: dinheiro é vazamento de máquina — `2900.00 R$` foi medido no ar.
_DINHEIRO_OK_RE = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?\b")
_DINHEIRO_TORTO_RE = re.compile(r"\b\d+\.\d{2}\s*R\$|\bR\$\s?\d+\.\d{2}\b|\b\d+,\d{3,}\s*R\$")
_ALEGACAO_FINANCEIRA_RE = re.compile(
    r"(?i)(al[íi]quota|taxa\s+de\s+juros|juros|parcela|empr[ée]stimo|antecipa[çc][ãa]o|"
    r"cr[ée]dito|financiamento|consignado|saque|R\$|\d+\s*%)"
)
_DIVULGACAO_RE = re.compile(
    r"(?i)(car[áa]ter\s+informativ|conte[úu]do\s+informativ|n[ãa]o\s+(somos|é|e)\s+(uma\s+)?"
    r"institui[çc][ãa]o\s+financeira|n[ãa]o\s+(realizamos|fazemos)\s+(nenhum\s+)?(tipo\s+de\s+)?"
    r"(empr[ée]stimo|solicita[çc]|contrata[çc])|consulte\s+(sempre\s+)?(o\s+)?(canal|site)\s+oficial|"
    r"sujeit[oa]\s+a\s+an[áa]lise|valores?\s+(s[ãa]o\s+)?(meramente\s+)?ilustrativ)"
)


def varrer_alegacoes(pagina: PaginaObservada) -> Verificacao:
    texto = texto_visivel(pagina.html)
    achados: list[Achado] = []
    if not texto:
        return Verificacao(
            nome=V_ALEGACOES,
            status=STATUS_INDISPONIVEL,
            detalhe="página sem texto visível para inspecionar",
        )

    improvaveis = [m.group(0) for m in re.finditer(_RESULTADO_IMPROVAVEL, texto)]
    financeiras = [m.group(0) for m in re.finditer(_ALEGACAO_FINANCEIRA_RE, texto)]
    tortos = sorted({m.group(0).strip() for m in _DINHEIRO_TORTO_RE.finditer(texto)})
    tem_divulgacao = bool(_DIVULGACAO_RE.search(texto))

    for trecho in sorted(set(improvaveis))[:5]:
        achados.append(
            Achado(
                "ALEGACAO_DE_RESULTADO_IMPROVAVEL",
                "Promessa de resultado que a página não pode garantir ao leitor.",
                evidencia={"trecho": trecho[:80]},
            )
        )
    if financeiras and not tem_divulgacao:
        achados.append(
            Achado(
                "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO",
                "A página faz alegação financeira (valor, alíquota, prazo, crédito) e "
                "não traz a divulgação que diz de onde ela vem e o que ela não é.",
                evidencia={"ocorrencias": len(financeiras), "amostra": sorted(set(financeiras))[:6]},
            )
        )
    for torto in tortos[:5]:
        achados.append(
            Achado(
                "VALOR_MONETARIO_MALFORMADO",
                "Valor monetário fora do formato pt-BR — vazamento de máquina em texto "
                "que o leitor lê como número oficial.",
                evidencia={"trecho": torto},
            )
        )

    inventario = [
        {"tipo": "valor_monetario_ok", "quantidade": len(_DINHEIRO_OK_RE.findall(texto))},
        {"tipo": "valor_monetario_malformado", "quantidade": len(tortos)},
        {"tipo": "alegacao_financeira", "quantidade": len(financeiras)},
        {"tipo": "resultado_improvavel", "quantidade": len(improvaveis)},
        {"tipo": "divulgacao", "presente": tem_divulgacao},
    ]
    return Verificacao(
        nome=V_ALEGACOES, status=STATUS_OBSERVADO, achados=achados, inventario=inventario
    )


# ── serviços governamentais ────────────────────────────────────────────────

#: Órgãos/programas cuja MENÇÃO já muda o que a página precisa provar. Não é
#: allowlist nem blocklist: é o gatilho da exigência de aviso de não-vínculo.
_ORGAOS = (
    "caixa econômica federal", "caixa econômica", "caixa", "inss", "receita federal",
    "gov.br", "governo federal", "ministério", "detran", "senai", "fgts", "pis/pasep",
    "pis", "pasep", "bolsa família", "pé-de-meia", "pé de meia", "bpc", "loas",
    "auxílio", "benefício social", "cadúnico", "cadastro único",
)
#: Documento/serviço que a política "Government documents and services" nomeia
#: como restrito à aquisição direta por provedor certificado/autorizado.
_DOCUMENTOS_RESTRITOS = (
    "carteira de identidade", "identidade nacional", "cin", "rg digital", "passaporte",
    "cnh", "carteira de motorista", "certidão de nascimento", "certidão de óbito",
    "título de eleitor", "cpf", "licenciamento de veículo", "visto",
)
#: Verbo que promete EXECUTAR o serviço no lugar do leitor, e não explicá-lo.
_VERBO_DE_AQUISICAO = (
    r"(?i)\b(emitir|emiss[ãa]o\s+d[eo]|solicitar\s+(seu|sua|o|a)|tirar\s+(seu|sua|o|a)|"
    r"agendar\s+(seu|sua|o|a)|requerer|gerar\s+(seu|sua|o|a)\s+(documento|certid))"
)


def varrer_governo(pagina: PaginaObservada) -> Verificacao:
    texto = texto_visivel(pagina.html)
    if not texto:
        return Verificacao(
            nome=V_GOVERNO, status=STATUS_INDISPONIVEL, detalhe="página sem texto visível"
        )
    baixo = texto.lower()
    achados: list[Achado] = []

    mencoes = {orgao: baixo.count(orgao) for orgao in _ORGAOS if orgao in baixo}
    documentos = sorted({d for d in _DOCUMENTOS_RESTRITOS if d in baixo})
    tem_aviso = bool(_NAO_AFILIACAO_RE.search(texto))
    total = sum(mencoes.values())

    if total and not tem_aviso:
        achados.append(
            Achado(
                "AVISO_NAO_OFICIAL_AUSENTE",
                "A página fala de órgão/benefício público e não declara em lugar nenhum "
                "que não é canal oficial e não tem vínculo.",
                evidencia={"mencoes": total, "orgaos": sorted(mencoes)[:8]},
            )
        )
        achados.append(
            Achado(
                "AFILIACAO_GOVERNAMENTAL_IMPLICITA",
                "Sem aviso de não-vínculo, a repetição do nome do órgão faz o leitor "
                "concluir afiliação que não existe.",
                evidencia={"mencoes": total},
            )
        )
    if documentos and re.search(_VERBO_DE_AQUISICAO, texto):
        achados.append(
            Achado(
                "SERVICO_GOVERNAMENTAL_RESTRITO",
                "A página oferece aquisição de documento/serviço de governo. Isso é "
                "restrito a governo certificado ou provedor autorizado — e autorização "
                "é link a partir de site oficial de governo, não contrato comercial.",
                evidencia={"documentos": documentos[:6]},
            )
        )

    inventario = [{"orgao": k, "mencoes": v} for k, v in sorted(mencoes.items())]
    inventario += [{"documento_restrito": d} for d in documentos]
    return Verificacao(
        nome=V_GOVERNO,
        status=STATUS_OBSERVADO if mencoes or documentos else STATUS_AUSENCIA_CONFIRMADA,
        achados=achados,
        inventario=inventario,
        detalhe="aviso de não-vínculo observado" if tem_aviso else "",
    )


# ── conteúdo, originalidade e congruência ──────────────────────────────────

#: Piso de palavras para um destino que recebe clique comprado. Não é métrica de
#: SEO: é a fronteira entre "página com conteúdo próprio" e "página cujo
#: propósito principal é mandar o leitor para outro lugar".
PISO_DE_PALAVRAS = 600
#: Acima disto, a página é mais botão do que texto — a assinatura de página-ponte.
RAZAO_PONTE = 0.03


def varrer_conteudo(pagina: PaginaObservada) -> Verificacao:
    parser = analisar(pagina.html)
    texto = texto_visivel(pagina.html)
    palavras = len(texto.split())
    achados: list[Achado] = []
    if not texto:
        return Verificacao(
            nome=V_CONTEUDO, status=STATUS_INDISPONIVEL, detalhe="página sem texto visível"
        )

    botoes = [l for l in parser.links if l.get("em_botao")]
    razao = (len(botoes) / palavras) if palavras else 1.0

    if palavras < PISO_DE_PALAVRAS:
        achados.append(
            Achado(
                "CONTEUDO_ORIGINAL_INSUFICIENTE",
                f"Destino com {palavras} palavras visíveis (piso {PISO_DE_PALAVRAS}).",
                evidencia={"palavras": palavras, "piso": PISO_DE_PALAVRAS},
            )
        )
    if botoes and razao > RAZAO_PONTE:
        achados.append(
            Achado(
                "PAGINA_PONTE",
                "A página é mais encaminhamento do que conteúdo: densidade de botões "
                "acima do limite para um destino pago.",
                evidencia={"botoes": len(botoes), "palavras": palavras, "razao": round(razao, 4)},
            )
        )
    if pagina.promessa_do_anuncio:
        prometido = _tokens(pagina.promessa_do_anuncio)
        entregue = _tokens(texto[:4000])
        if prometido and not (prometido & entregue):
            achados.append(
                Achado(
                    "DESTINO_INCONGRUENTE_COM_ANUNCIO",
                    "Nada do que o anúncio promete aparece no início do destino.",
                    evidencia={"promessa": pagina.promessa_do_anuncio[:80]},
                )
            )
    for outro in pagina.duplicatas_entre_dominios:
        achados.append(
            Achado(
                "CONTEUDO_DUPLICADO_ENTRE_DOMINIOS",
                "A mesma rota existe em outro domínio do operador. Variação de domínio "
                "para o mesmo conteúdo é lida como tentativa de contornar enforcement.",
                evidencia={"outro_domínio": outro},
            )
        )

    inventario = [
        {"metrica": "palavras_visiveis", "valor": palavras},
        {"metrica": "botoes", "valor": len(botoes)},
        {"metrica": "links", "valor": len(parser.links)},
        {"metrica": "razao_botao_palavra", "valor": round(razao, 4)},
    ]
    return Verificacao(
        nome=V_CONTEUDO, status=STATUS_OBSERVADO, achados=achados, inventario=inventario
    )


# ── sinais de segurança do destino ─────────────────────────────────────────

_OFUSCACAO_RE = re.compile(r"\beval\s*\(|new\s+Function\s*\(|String\.fromCharCode\s*\(")
_SERVICE_WORKER_RE = re.compile(
    r"(?i)serviceworker|service-worker|firebase-messaging|pushmanager|"
    r"notification\.requestpermission|web[_-]?push"
)


def varrer_seguranca(pagina: PaginaObservada) -> Verificacao:
    parser = analisar(pagina.html)
    achados: list[Achado] = []
    corpo_scripts = "\n".join(s.get("texto", "") for s in parser.scripts)

    externos: dict[str, dict[str, str]] = {}

    def _registrar(bruto: str, origem: str) -> None:
        host = _host(urljoin(pagina.url or "", (bruto or "").strip()))
        if not host:
            return
        atual = externos.setdefault(
            host, {"classe": classificar_host(host, pagina), "origem": origem}
        )
        if origem not in atual["origem"]:
            atual["origem"] = f"{atual['origem']}+{origem}"

    for script in parser.scripts:
        _registrar(script.get("src") or "", "script")
    for src in parser.iframes:
        _registrar(src, "iframe")
    for hint in parser.hints:
        # `preload as=script` e `dns-prefetch` são declaração de intenção de
        # carregar código de terceiro. Contam como superfície, mesmo quando o
        # `<script>` correspondente é servido do próprio domínio.
        _registrar(hint.get("href") or "", f"link:{hint.get('rel')}")

    for host, dados in sorted(externos.items()):
        if dados["classe"] == CLASSE_TERCEIRO_DESCONHECIDO:
            achados.append(
                Achado(
                    "SCRIPT_TERCEIRO_NAO_DECLARADO",
                    "Script/iframe/preload de terceiro que a casa não declarou para este site.",
                    evidencia={"host": host, "origem": dados["origem"]},
                )
            )

    mistos = sorted(
        {
            _host(u)
            for u in re.findall(r'(?:src|href)=["\'](http://[^"\']+)', pagina.html or "")
            if "w3.org" not in u
        }
    )
    if mistos:
        achados.append(
            Achado(
                "CONTEUDO_MISTO",
                "Sub-recurso carregado por http:// numa página https.",
                evidencia={"hosts": mistos[:6]},
            )
        )
    if re.search(r"(?i)(window|document)\.location\s*=|location\.href\s*=|location\.replace\s*\(", corpo_scripts):
        achados.append(
            Achado(
                "SCRIPT_REDIRECIONA_CLIENT_SIDE",
                "JavaScript de redirecionamento client-side observado após o carregamento.",
            )
        )

    push = _SERVICE_WORKER_RE.search(pagina.html or "")
    if push:
        achados.append(
            Achado(
                "SERVICE_WORKER_OU_PUSH_OBSERVADO",
                "Service worker / notificação push observado no destino. Não é violação "
                "por si; é superfície de experiência que o revisor vê antes do conteúdo.",
                evidencia={"sinal": push.group(0)[:40]},
            )
        )
    ofuscacao = _OFUSCACAO_RE.search(corpo_scripts)
    if ofuscacao:
        achados.append(
            Achado(
                "OFUSCACAO_DE_SCRIPT_OBSERVADA",
                "Construção de código dinâmico observada no script da página.",
                evidencia={"construcao": ofuscacao.group(0)[:40]},
            )
        )

    inventario = [
        {"host": h, "classe": d["classe"], "origem": d["origem"]}
        for h, d in sorted(externos.items())
    ]
    inventario.append({"metrica": "scripts", "valor": len(parser.scripts)})
    inventario.append({"metrica": "iframes", "valor": len(parser.iframes)})
    return Verificacao(
        nome=V_SEGURANCA, status=STATUS_OBSERVADO, achados=achados, inventario=inventario
    )


# ── redirecionamento e cloaking ────────────────────────────────────────────


#: Rótulo de variante que representa um RASTREADOR. Cloaking é divergência
#: entre o que o rastreador vê e o que a pessoa vê — não entre desktop e mobile.
_ROTULO_DE_RASTREADOR_RE = re.compile(r"(?i)bot\b|bot[-_]|googlebot|adsbot|crawler|spider")


def varrer_redirecionamento(pagina: PaginaObservada) -> Verificacao:
    """Redirecionamento e cloaking — as duas coisas que só existem AO VIVO.

    ## O falso positivo que esta função já teve, e por que ele importava

    A primeira versão acusava cloaking sempre que DUAS variantes quaisquer
    tivessem hashes diferentes. Rodando sobre a preservação real, ela acusou
    `/r/fgts-saque-aniversario/` — porque desktop e mobile diferem em 27 bytes,
    um token rotativo de push. Desktop ≠ mobile é design responsivo; o Googlebot
    daquela mesma leitura devolveu HTML BYTE A BYTE IGUAL ao do desktop, ou seja,
    a evidência era exatamente a oposta da acusação.

    Acusar cloaking sem esse cuidado seria a mesma alegação forte sem lastro que
    este pacote inteiro existe para impedir — e num pacote de apelação seria pior
    que inútil: seria uma admissão falsa.

    ## A regra que ficou

    Cloaking exige uma variante ROTULADA como rastreador e pelo menos uma
    humana; a acusação é o hash do rastreador não estar entre os hashes humanos.
    Divergência entre variantes humanas vai para o inventário como observação de
    dispositivo, sem virar achado.

    Sem rastreador rotulado, ou sem cadeia de redirecionamento, a verificação é
    `unavailable` — e no destino pago isso reprova por ausência, que é o
    desfecho correto para "não deu para olhar".
    """
    achados: list[Achado] = []
    saltos = pagina.saltos_redirecionamento
    variantes = {k: v for k, v in (pagina.variantes_sha256 or {}).items() if v}
    rastreadores = {k: v for k, v in variantes.items() if _ROTULO_DE_RASTREADOR_RE.search(k)}
    humanos = {k: v for k, v in variantes.items() if k not in rastreadores}
    cloaking_observavel = bool(rastreadores and humanos)

    if saltos is None or not cloaking_observavel:
        faltando = []
        if saltos is None:
            faltando.append("cadeia de redirecionamento não medida")
        if not cloaking_observavel:
            faltando.append(
                "sem par rastreador/usuário rotulado para comparar (variantes: "
                f"{sorted(variantes) or 'nenhuma'})"
            )
        return Verificacao(
            nome=V_REDIRECIONAMENTO,
            status=STATUS_INDISPONIVEL,
            inventario=[{"variante": k, "sha256_12": v[:12]} for k, v in sorted(variantes.items())],
            detalhe="; ".join(faltando),
        )

    origem = _host(pagina.url)
    for salto in saltos or []:
        destino = _host(str(salto.get("to") or ""))
        achados.append(
            Achado(
                "REDIRECIONAMENTO_OBSERVADO",
                "O destino pago redireciona antes de servir o conteúdo.",
                evidencia={"status": salto.get("status"), "para_host": destino},
            )
        )
        if destino and not _mesmo_site(destino, origem):
            achados.append(
                Achado(
                    "REDIRECIONAMENTO_CROSS_DOMAIN",
                    "O redirecionamento sai do domínio declarado no anúncio.",
                    evidencia={"de": origem, "para": destino},
                )
            )

    hashes_humanos = set(humanos.values())
    divergentes = sorted(
        rotulo for rotulo, sha in rastreadores.items() if sha not in hashes_humanos
    )
    if divergentes:
        achados.append(
            Achado(
                "DIVERGENCIA_RASTREADOR_USUARIO",
                "O HTML servido ao rastreador não é o servido à pessoa. É a assinatura "
                "de cloaking descrita pela política de circumventing systems.",
                evidencia={
                    "rastreadores_divergentes": divergentes,
                    "variantes": {k: v[:12] for k, v in sorted(variantes.items())},
                },
            )
        )

    inventario = [{"salto": i, **{k: v for k, v in s.items() if k != "from"}}
                  for i, s in enumerate(saltos or [])]
    inventario += [
        {
            "variante": k,
            "sha256_12": v[:12],
            "papel": "rastreador" if k in rastreadores else "usuário",
        }
        for k, v in sorted(variantes.items())
    ]
    if len(set(humanos.values())) > 1:
        # Registrado, NUNCA acusado: dois dispositivos humanos com HTML diferente
        # é design responsivo, não cloaking.
        inventario.append(
            {"observacao": "variantes humanas divergem entre si (dispositivo, não cloaking)",
             "variantes": sorted(humanos)}
        )
    return Verificacao(
        nome=V_REDIRECIONAMENTO,
        status=STATUS_OBSERVADO,
        achados=achados,
        inventario=inventario,
    )


def varrer_deriva(pagina: PaginaObservada) -> Verificacao:
    """A página no ar ainda é a que a casa aprovou?

    Sem `sha256_aprovado` a pergunta não tem como ser respondida. Antes da
    publicação ela nem faz sentido — daí `not_applicable` quando não há nada no
    ar para comparar, e `unavailable` quando há e falta a referência.
    """
    observado = pagina.sha256_observado
    aprovado = pagina.sha256_aprovado
    if observado is None:
        return Verificacao(
            nome=V_DERIVA,
            status=STATUS_NAO_APLICAVEL,
            detalhe="nenhum HTML ao vivo observado nesta avaliação",
        )
    if not aprovado:
        return Verificacao(
            nome=V_DERIVA,
            status=STATUS_INDISPONIVEL,
            detalhe="não há hash aprovado registrado para comparar com o que está no ar",
        )
    if observado != aprovado:
        return Verificacao(
            nome=V_DERIVA,
            status=STATUS_OBSERVADO,
            achados=[
                Achado(
                    "DERIVA_AO_VIVO",
                    "O conteúdo no ar não é o que foi aprovado.",
                    evidencia={"aprovado_12": aprovado[:12], "observado_12": observado[:12]},
                )
            ],
            inventario=[{"aprovado_12": aprovado[:12], "observado_12": observado[:12]}],
        )
    return Verificacao(
        nome=V_DERIVA,
        status=STATUS_OBSERVADO,
        inventario=[{"aprovado_12": aprovado[:12], "observado_12": observado[:12]}],
    )


VARREDURAS = {
    V_IDENTIDADE: varrer_identidade,
    V_LINKS_EXTERNOS: varrer_links,
    V_FORMULARIOS: varrer_formularios,
    V_ALEGACOES: varrer_alegacoes,
    V_GOVERNO: varrer_governo,
    V_CONTEUDO: varrer_conteudo,
    V_SEGURANCA: varrer_seguranca,
    V_REDIRECIONAMENTO: varrer_redirecionamento,
    V_DERIVA: varrer_deriva,
}
