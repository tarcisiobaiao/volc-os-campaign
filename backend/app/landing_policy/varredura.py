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
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from app.landing_policy.contrato import (
    JANELA_DE_FRESCOR_PADRAO_S,
    impressao,
    POLICY_CONTRACT_VERSION,
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
    V_RECIBO,
    V_REDIRECIONAMENTO,
    V_SEGURANCA,
    Verificacao,
    TETO_DE_SALTOS_PADRAO,
    versao_da_fonte,
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
    #: A IMPRESSÃO CANÔNICA aprovada — a projeção estrutural, não o byte. É ela
    #: que decide `DERIVA_AO_VIVO` quando existe; o byte vira observação de
    #: dispositivo. Ver `impressao_canonica` para por que as duas coexistem.
    impressao_aprovada: str | None = None
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
    #: O recibo de aprovação anterior desta URL, quando existe. É o que
    #: `varrer_recibo` confere: presença, frescor e versão de política. `None`
    #: significa "nenhum recibo resolvível", que no destino pago reprova — não
    #: por rigor decorativo, mas porque sem ele `DERIVA_AO_VIVO` é immensurável,
    #: e foi exatamente essa a lacuna dos quatro destinos preservados.
    recibo_de_aprovacao: dict[str, Any] | None = None
    #: Instante da avaliação, em epoch UTC. Só o frescor usa; fica separado de
    #: `observado_em` (que é texto humano) porque comparar data é aritmética e
    #: parsear string de data em três formatos é como o frescor deixa de valer.
    avaliado_em_epoch: float | None = None
    #: A janela de frescor desta avaliação, em segundos.
    janela_de_frescor_s: int = JANELA_DE_FRESCOR_PADRAO_S
    #: Teto de saltos de redirecionamento aceito até a URL final.
    teto_de_saltos: int = TETO_DE_SALTOS_PADRAO
    #: Papel DECLARADO no cadastro, apenas para registro no inventário. NUNCA é
    #: usado para decidir severidade: quem decide é o papel que o portão recebeu,
    #: e no ponto de campanha ele é FORÇADO. Ver `portao.papel_do_servidor`.
    papel_declarado: str = ""
    #: O documento é um FRAGMENTO, não a página que o visitante recebe.
    #:
    #: ⚠️ Campo de SERVIDOR, apurado do formato do artefato — nunca vindo do
    #: cliente. Antes de publicar, o backend enxerga o CONTEÚDO da página; o
    #: rodapé de identidade (razão social, CNPJ, sobre, contato, privacidade,
    #: divulgação de monetização) é renderizado pelo TEMA do WordPress. A coluna
    #: `cnpj` foi removida de `project_wordpress` exatamente por isso — ver
    #: `src/sql/pautador/03_perfil_enxuto.sql:11`.
    #:
    #: Exigir identidade de um fragmento reprovaria TODA landing page por uma
    #: impossibilidade estrutural, que é o mesmo erro que `EXIGENCIAS_POR_PONTO`
    #: existe para não cometer com redirecionamento e cloaking. E bloqueio falso
    #: é como a operação desliga o portão.
    #:
    #: A lacuna é fechada na barreira 3: `identity` está em
    #: `NAO_APLICAVEL_E_DESCONHECIDO_EM` no ponto de campanha, então uma leitura
    #: AO VIVO nunca pode alegar "não se aplica".
    documento_parcial: bool = False
    #: ⚠️ ESTA AVALIAÇÃO É O ATO DE AUDITORIA, não a conferência de uma anterior.
    #:
    #: Campo de SERVIDOR, ligado APENAS por `redator.reauditoria.provar_destino`
    #: e por `confirmar_reauditoria` — nunca por payload, e nunca pelo caminho de
    #: campanha, que força papel e ponto e não constrói esta página.
    #:
    #: Quando ligado, `approval_receipt` e `live_drift` respondem
    #: `not_applicable`: perguntar por uma aprovação anterior a um ato de
    #: aprovação é circular, e foi essa circularidade que deixou o ciclo do
    #: recibo `live` sem entrada. Todas as outras oito verificações continuam
    #: exigidas e conclusivas — o ato audita a página inteira.
    e_o_ato_de_auditoria: bool = False
    #: Hosts que o CHROME do site legitimamente linka — crédito do tema, rede
    #: social da casa, autoria.
    #:
    #: ⚠️ CONFIGURAÇÃO DO SERVIDOR/SITE, e ela é DELIBERADAMENTE separada de
    #: `hosts_declarados` e de `adtech_declarada`. Uma allowlist enviada pelo
    #: cliente não autoriza host nenhum aqui, e `adtech_declarada` autoriza
    #: RECURSO TÉCNICO (script, pixel), não navegação do leitor. Reaproveitar
    #: qualquer uma das duas transformaria um campo de payload na chave que
    #: abre a política de links.
    #:
    #: Vazio é fail-closed: sem procedência confiável, o link do tema continua
    #: reprovando — com o código e o próximo ato dele.
    chrome_declarado_pelo_site: tuple[str, ...] = ()
    #: Fontes de pesquisa que o motor usou naquela página. Elas pertencem ao
    #: dossiê de evidência; virar hyperlink no corpo de um destino pago é o
    #: defeito que `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO` descreve.
    fontes_de_pesquisa: tuple[str, ...] = ()


# ── parsing ────────────────────────────────────────────────────────────────

#: Folga entre relógios de máquinas diferentes. Cinco minutos absorve deriva de
#: NTP sem absorver um carimbo posto de propósito no futuro.
_TOLERANCIA_DE_RELOGIO_S = 300

#: As regiões do documento. `corpo` é o conteúdo editorial e o CTA — o que o
#: funil escreveu. As outras quatro são o CHROME que o tema do WordPress
#: renderiza em volta dele.
REGIAO_CORPO = "corpo"
REGIAO_CABECALHO = "cabecalho"
REGIAO_RODAPE = "rodape"
REGIAO_NAVEGACAO = "navegacao"
REGIAO_WIDGET = "widget"
REGIAO_ADTECH = "adtech"

#: Tudo que não é `corpo`. A distinção não LIBERA link nenhum — ela troca o
#: código emitido e, com ele, o próximo ato e o dono do conserto.
REGIOES_DE_CHROME = frozenset(
    {REGIAO_CABECALHO, REGIAO_RODAPE, REGIAO_NAVEGACAO, REGIAO_WIDGET, REGIAO_ADTECH}
)

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
        #: `<base href>` — reescreve todo link relativo da página.
        self.base: str = ""
        #: Pilha de regiões. O topo diz onde estamos; vazia = corpo editorial.
        self._pilha_regiao: list[tuple[str, str]] = []
        #: ⚠️ O TÍTULO E OS CABEÇALHOS, que a v1 não colhia.
        #:
        #: `texto_visivel` achatava tudo num único texto, então o portão olhava o
        #: H1 apenas como mais uma frase do corpo — e uma manchete tem peso que
        #: uma frase do meio da página não tem. Foi por aí que
        #: "Saque-Aniversário FGTS Liberado pelo Governo" atravessou: a expressão
        #: era banida no CORPO, e o H1 não era corpo.
        self.titulo: str = ""
        self.cabecalhos: list[dict[str, str]] = []
        self._em_titulo = False
        self._texto_titulo: list[str] = []
        self._nivel_cabecalho = ""
        self._texto_cabecalho: list[str] = []
        self._pilha_ancora: list[dict[str, Any]] = []
        self._profundidade_botao = 0
        self._em_script = False
        self._texto_script: list[str] = []
        self._attrs_script: dict[str, str] = {}

    # `wp:buttons`/`.wp-block-button`/`.elementor-button` marcam o clique que a
    # página EMPURRA — é outra coisa que uma citação em prosa, e a política
    # trata as duas de forma diferente.
    _CLASSES_BOTAO = ("wp-block-button", "elementor-button", "su-button", "btn", "button")

    #: ⚠️ REGIÕES DO DOCUMENTO, e por que elas passaram a existir.
    #:
    #: Um destino pago no ar não é o artefato: é o artefato DENTRO do tema do
    #: WordPress. O crédito "Orgulhosamente com WordPress", o ícone de rede
    #: social e o link do autor são hyperlinks externos que o TEMA renderiza, e
    #: a política do VOLC fala do corpo editorial e do CTA.
    #:
    #: Sem procedência, a barreira 3 acusava esses links como se fossem
    #: conteúdo do funil — e o operador recebia uma recusa que não tinha como
    #: consertar mexendo no funil. Atribuir ao conteúdo um link que o conteúdo
    #: não pôs é acusação falsa, e acusação falsa é como um portão perde a
    #: autoridade que ele precisa ter nos outros 42 códigos.
    #:
    #: A procedência NÃO libera nada por si: ela troca o código e o próximo ato.
    _TAGS_DE_CHROME = {
        "header": REGIAO_CABECALHO,
        "footer": REGIAO_RODAPE,
        "nav": REGIAO_NAVEGACAO,
        "aside": REGIAO_WIDGET,
    }
    #: Classe/id que o tema usa quando não usa a tag semântica. Erra para MENOS
    #: chrome: o que não for reconhecido continua sendo CORPO, e corpo é o
    #: regime estrito. Uma heurística de chrome que errasse para mais viraria a
    #: porta de saída da própria política.
    _MARCAS_DE_CHROME = (
        ("site-header", REGIAO_CABECALHO), ("masthead", REGIAO_CABECALHO),
        ("topbar", REGIAO_CABECALHO), ("page-header", REGIAO_CABECALHO),
        ("site-footer", REGIAO_RODAPE), ("colophon", REGIAO_RODAPE),
        ("footer-", REGIAO_RODAPE), ("rodape", REGIAO_RODAPE),
        ("main-navigation", REGIAO_NAVEGACAO), ("menu-", REGIAO_NAVEGACAO),
        ("breadcrumb", REGIAO_NAVEGACAO), ("navbar", REGIAO_NAVEGACAO),
        ("sidebar", REGIAO_WIDGET), ("widget", REGIAO_WIDGET),
        ("ai-viewport", REGIAO_ADTECH), ("ai-widget", REGIAO_ADTECH),
        ("adsbygoogle", REGIAO_ADTECH), ("ad-slot", REGIAO_ADTECH),
        ("code-block", REGIAO_ADTECH),
    )

    @property
    def regiao(self) -> str:
        return self._pilha_regiao[-1][1] if self._pilha_regiao else REGIAO_CORPO

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap = {k.lower(): (v or "") for k, v in attrs}
        t = tag.lower()
        classe = amap.get("class", "").lower()
        marcador = f"{classe} {amap.get('id', '').lower()} {amap.get('role', '').lower()}"
        regiao_nova = self._TAGS_DE_CHROME.get(t)
        if regiao_nova is None:
            for marca, alvo_regiao in self._MARCAS_DE_CHROME:
                if marca in marcador:
                    regiao_nova = alvo_regiao
                    break
        if regiao_nova is not None:
            self._pilha_regiao.append((t, regiao_nova))
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
                "regiao": self.regiao,
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
        elif t == "base":
            # ⚠️ `<base href>` REESCREVE TODO LINK RELATIVO DA PÁGINA.
            #
            # Sem colhê-lo, `<base href="https://evil.example/">` seguido de
            # `<a href="oferta">` era resolvido contra a URL da própria página e
            # classificado como MESMO SITE. Uma tag muda o destino de todos os
            # links de uma vez, e ela era invisível para a varredura.
            self.base = amap.get("href") or self.base
        elif t in ("button", "input") and amap.get("formaction"):
            # `formaction` sobrepõe o `action` do formulário no clique daquele
            # botão. É navegação disparada por clique, com destino próprio.
            self.links.append({
                "href": amap.get("formaction", ""), "rel": "", "target": "",
                "classe": classe, "em_botao": True, "origem_da_tag": t,
                "regiao": self.regiao, "_texto": [amap.get("value", "")],
            })
        elif t == "area":
            # Área clicável de mapa de imagem. É `<a href>` com outra roupa.
            self.links.append({
                "href": amap.get("href", ""), "rel": amap.get("rel", ""),
                "target": amap.get("target", ""), "classe": classe,
                "em_botao": False, "origem_da_tag": t,
                "regiao": self.regiao, "_texto": [amap.get("alt", "")],
            })
        elif t == "title":
            self._em_titulo = True
            self._texto_titulo = []
        elif t in ("h1", "h2", "h3"):
            self._nivel_cabecalho = t
            self._texto_cabecalho = []

    def handle_data(self, data: str) -> None:
        if self._em_script:
            self._texto_script.append(data)
        if self._em_titulo:
            self._texto_titulo.append(data)
        if self._nivel_cabecalho:
            self._texto_cabecalho.append(data)
        for registro in self._pilha_ancora:
            registro["_texto"].append(data)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._pilha_regiao and self._pilha_regiao[-1][0] == t:
            self._pilha_regiao.pop()
        if t == "title" and self._em_titulo:
            self.titulo = re.sub(r"\s+", " ", "".join(self._texto_titulo)).strip()
            self._em_titulo = False
            self._texto_titulo = []
            return
        if t in ("h1", "h2", "h3") and self._nivel_cabecalho == t:
            texto = re.sub(r"\s+", " ", "".join(self._texto_cabecalho)).strip()
            if texto:
                self.cabecalhos.append({"nivel": t, "texto": texto})
            self._nivel_cabecalho = ""
            self._texto_cabecalho = []
            return
        if t == "script" and self._em_script:
            self.scripts.append({**self._attrs_script, "texto": "".join(self._texto_script)})
            self._em_script = False
            self._attrs_script = {}
            self._texto_script = []
        elif t == "a" and self._pilha_ancora:
            self._pilha_ancora.pop()
        if self._profundidade_botao > 0 and t in ("div", "span", "a", "li"):
            # Heurística: fecha o escopo de botão no fim do contêiner mais
            # provável. Erra para MENOS botão, nunca para mais — um botão não
            # reconhecido vira link em prosa, que é a classificação mais frouxa,
            # e por isso o `em_botao` também é setado na própria âncora.
            #
            # ⚠️ ERA UM `elif` DA CADEIA DE `</a>`, E ISSO INVERTIA A HEURÍSTICA.
            #
            # Fechar uma âncora consumia o ramo, então `</a>` NUNCA decrementava
            # a profundidade: depois do primeiro `<div class="wp-block-button">`
            # da página, TODO link seguinte era marcado `em_botao`. O comentário
            # acima descrevia o oposto do que o código fazia, e o efeito era
            # fabricar `PAGINA_PONTE` e `BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO` em
            # páginas corretas. Bloqueio falso é como um portão é desligado pela
            # operação — e um portão desligado não protege nada.
            self._profundidade_botao -= 1


def analisar(html: str) -> _Parser:
    p = _Parser()
    p.feed(html or "")
    for registro in p.links:
        registro["texto"] = re.sub(r"\s+", " ", "".join(registro.pop("_texto"))).strip()
        registro.setdefault("origem_da_tag", "a")
        registro.setdefault("regiao", REGIAO_CORPO)
    return p


#: Elemento escondido por CSS inline ou por atributo. O conteúdo dele NÃO é
#: texto visível — e tratá-lo como visível é o que deixa a página satisfazer
#: identidade e disclosure com um bloco `display:none` que o leitor nunca vê.
#: É uma forma vizinha de cloaking: o revisor lê o HTML, o visitante lê a tela.
_ESCONDIDO_RE = re.compile(
    r"(?is)<(\w+)\b[^>]*?(?:"
    r"style=[\"'][^\"']*?(?:display\s*:\s*none|visibility\s*:\s*hidden|"
    r"font-size\s*:\s*0|opacity\s*:\s*0)[^\"']*[\"']"
    r"|\shidden(?=[\s/>])"
    r"|aria-hidden=[\"']true[\"']"
    r")[^>]*>.*?</\1\s*>"
)


def texto_visivel(html: str) -> str:
    """O texto que o LEITOR vê — não o texto que está no arquivo.

    ⚠️ Bloco escondido por CSS inline sai antes do achatamento. Sem isso, um
    `<div style="display:none">` com CNPJ, aviso de não-vínculo e divulgação de
    monetização satisfaz identidade, governo e alegações de uma vez — e o
    visitante não vê nenhum dos três. O revisor do Google lê a tela, não o
    `<div>`.

    O que NÃO é tratado: CSS de folha externa. Uma classe `.oculto{display:none}`
    definida em `<style>` continua invisível para esta função, porque resolver
    cascata exige um motor de renderização. É limite declarado, não descuido —
    e é por isso que a varredura de segurança continua registrando o que carrega.
    """
    sem_codigo = _SCRIPT_STYLE_RE.sub(" ", html or "")
    anterior = None
    # Laço: blocos escondidos podem estar aninhados, e uma passada só remove o
    # externo, devolvendo o interno ao texto "visível".
    while anterior != sem_codigo:
        anterior = sem_codigo
        sem_codigo = _ESCONDIDO_RE.sub(" ", sem_codigo)
    return re.sub(r"\s+", " ", _html.unescape(_TAG_RE.sub(" ", sem_codigo))).strip()


# ── impressão canônica ─────────────────────────────────────────────────────


#: Ruído que muda entre duas leituras da MESMA página aprovada: nonce de CSP,
#: token rotativo do plugin de push, carimbo de cache, id de sessão do tema.
#: Nenhum deles é conteúdo; todos mudam o sha256 do byte.
_RUIDO_VOLATIL = (
    re.compile(r"(?i)\bnonce=[\"'][^\"']{4,}[\"']"),
    re.compile(r"(?i)\bdata-(?:time|shares|info|nonce|token|cache)=[\"'][^\"']*[\"']"),
    re.compile(r"(?i)[?&](?:ver|v|cache|_|t|ts|rand)=[A-Za-z0-9._-]{1,40}"),
    re.compile(r"(?i)\b[0-9a-f]{32,64}\b"),
    re.compile(r"(?i)\b\d{10,13}\b"),
)


def _normalizar_href(href: str) -> str:
    """O destino de um link, sem o que muda sozinho.

    Minúsculas no esquema e no host, query e fragmento fora, barra final
    normalizada. O CAMINHO é preservado: ele é o destino, e mudar o destino é
    mudança material mesmo quando o host continua o mesmo.
    """
    bruto = (href or "").strip()
    if not bruto:
        return ""
    partes = urlsplit(bruto)
    caminho = partes.path or ""
    if len(caminho) > 1:
        caminho = caminho.rstrip("/")
    return urlunsplit((partes.scheme.lower(), partes.netloc.lower(), caminho, "", ""))


def impressao_canonica(html: str) -> str:
    """A impressão do que a página É para o leitor, não dos bytes que a servem.

    ## Por que o sha256 do byte não serve sozinho para medir DERIVA

    Ele serve — e é a evidência mais forte que existe — para provar IGUALDADE:
    foi assim que a acusação de cloaking contra `/r/fgts-saque-aniversario/` foi
    REFUTADA, com Googlebot e usuário devolvendo 174 243 bytes idênticos.

    Ele não serve para medir MUDANÇA. Na mesma leitura, desktop e mobile daquela
    página diferiram em 27 bytes — um token rotativo do plugin de push. Um
    portão que reprovasse por deriva a cada rotação de token seria desligado na
    primeira semana, e aí não protegeria nada. Um que ignorasse a deriva não
    veria a edição manual no WordPress. Os dois são o mesmo erro com sinais
    trocados.

    ## O que entra na impressão

    A PROJEÇÃO ESTRUTURAL: título, cabeçalhos, texto visível normalizado, o
    inventário de links clicáveis (host + âncora + se é botão) e o de campos de
    formulário. É exatamente o conjunto sobre o qual as nove varreduras decidem
    — então duas páginas com a mesma impressão canônica recebem, por construção,
    o mesmo veredito.

    O recibo carrega as DUAS: `content_sha256` (o byte, evidência) e
    `content_fingerprint` (a estrutura, comparação). Guardar só uma seria
    escolher entre não conseguir provar igualdade e não conseguir medir mudança.
    """
    limpo = html or ""
    for padrao in _RUIDO_VOLATIL:
        limpo = padrao.sub(" ", limpo)
    parser = analisar(limpo)
    projecao = {
        "titulo": parser.titulo,
        "cabecalhos": [c["texto"] for c in parser.cabecalhos],
        "texto": texto_visivel(limpo).lower(),
        # ⚠️ O HREF INTEIRO, não só o host.
        #
        # A primeira versão guardava apenas `_host(href)`, e para link relativo
        # o host é string vazia — então trocar o destino de um CTA de
        # `/oferta-a` para `/oferta-b` deixava a impressão IDÊNTICA, e
        # `DERIVA_AO_VIVO` não disparava. Repontar o botão principal depois da
        # aprovação é exatamente a mudança material que a deriva existe para
        # pegar, e ela era a única invisível.
        #
        # A query sai do href pela mesma razão de `registro.url_canonica`:
        # `?utm_*` muda a cada carregamento em alguns temas e não é conteúdo.
        "links": sorted(
            f"{_normalizar_href(l.get('href') or '')}|{(l.get('texto') or '')[:60]}|"
            f"{int(bool(l.get('em_botao')))}"
            for l in parser.links
            if (l.get("href") or "").strip()
        ),
        "campos": sorted(
            f"{(i.get('type') or '').lower()}|{(i.get('name') or '').lower()}"
            for i in parser.inputs
        ),
        # ⚠️ O SCRIPT ENTRA NA IMPRESSÃO, e ele faltava.
        #
        # Sem isto, injetar um `<script>` que redireciona só quem não é
        # Googlebot deixava a impressão canônica IDÊNTICA — e como a deriva tem
        # precedência sobre o byte, a página continuava "sem deriva" depois de
        # ganhar um cloaking inteiro. O que decide o destino do visitante é
        # conteúdo, mesmo quando não é texto.
        #
        # Entra o DIGEST, não o corpo: script minificado muda de nome de
        # variável a cada build, e guardar o texto faria deriva de rotina.
        "scripts": sorted(
            impressao(
                {
                    "src": _normalizar_href(sc.get("src") or ""),
                    "tem_redirecionamento": bool(
                        _REDIRECIONA_CLIENTE_RE.search(sc.get("texto") or "")
                    ),
                    "tem_ofuscacao": bool(_OFUSCACAO_RE.search(sc.get("texto") or "")),
                    "tamanho": len(sc.get("texto") or "") // 256,
                }
            )[:16]
            for sc in parser.scripts
        ),
        "meta_refresh": bool(_META_REFRESH_RE.search(limpo)),
    }
    return impressao(projecao)


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
#: `mailto:`/`tel:` — caminho de contato, explicitamente permitido e coerente com
#: a exigência de identidade. Entra no inventário para que "permitido" e "não
#: encontrado" não tenham a mesma aparência no recibo.
CLASSE_CONTATO_DIRETO = "contato_direto"
#: Host que o CHROME do site legitimamente linka, declarado pela configuração do
#: servidor. NÃO é `fonte_declarada` (evidência de pesquisa do chamador) nem
#: `adtech_declarada` (recurso técnico): é procedência sobre o template.
CLASSE_CHROME_DO_SITE = "chrome_do_site"
#: `javascript:`/`data:`/`blob:` — clicável, e com destino que não se resolve
#: lendo o documento. É não-classificável por construção.
CLASSE_NAO_RESOLVIVEL = "nao_resolvivel"

#: As classes que NÃO são navegação para fora do domínio canônico. Tudo que não
#: está aqui é hyperlink externo clicável — e no `paid_destination` isso reprova
#: por política interna do VOLC, mais restritiva que a do Google.
#:
#: `adtech_google` e `adtech_declarada` ficam de fora da regra por serem, no
#: inventário desta casa, recurso técnico do slot de anúncio e não navegação
#: editorial oferecida ao leitor. Quando um deles aparece como `<a href>` num
#: botão, ele continua sendo pego por `BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO` e
#: pelas regras de terceiro — o que não pode acontecer é uma tag de medição
#: virar "link externo editorial" e afogar o achado que importa.
#: ⚠️ `adtech_google` e `adtech_declarada` SAÍRAM DESTA LISTA.
#:
#: O raciocínio original era que uma tag de medição não é navegação editorial.
#: Ele estava certo sobre a tag — e errado sobre o efeito: `varrer_links` só
#: enxerga `<a href>`, `<area href>` e `formaction`. Tudo que chega aqui JÁ É
#: clique do leitor. Então `<a href="https://googleadservices.com/aclk">` ficava
#: verde por ser "recurso técnico", sendo um hyperlink visível para fora.
#:
#: Script, imagem e fonte continuam de fora da regra porque nunca entram no
#: inventário de links — eles são colhidos separadamente por `varrer_seguranca`.
_CLASSES_INTERNAS = frozenset({
    CLASSE_MESMO_SITE,
    CLASSE_RELATIVO,
    CLASSE_CONTATO_DIRETO,
})


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().split("@")[-1].split(":")[0]
    except ValueError:
        return ""


def _mesmo_site(host: str, site: str) -> bool:
    """`host` pertence a `site`? A relação é de SUBDOMÍNIO, e ela tem direção.

    ⚠️ A versão anterior era simétrica (`site.endswith("." + host)` também
    valia), então declarar `docs.exemplo.com` como fonte autorizava
    `exemplo.com` inteiro — o pai herdava a autorização do filho. Autorização
    tem que descer, nunca subir.
    """
    if not host or not site:
        return False
    return host == site or host.endswith("." + site)


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
    if any(_mesmo_site(host, c.lower()) for c in pagina.chrome_declarado_pelo_site):
        # Chrome do site, declarado pela CONFIGURAÇÃO DO SERVIDOR — não por
        # allowlist do cliente. Declarar com procedência é o que faz a recusa
        # deixar de ser sobre este host; sem isso ele continua não classificado.
        return CLASSE_CHROME_DO_SITE
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
#: ⚠️ EXIGE PRIMEIRA PESSOA, e a exigência é o conserto de um falso bloqueio.
#:
#: A regra é sobre a página AFIRMAR ter credencial. A versão anterior casava
#: qualquer ocorrência do adjetivo, então ela acusava ORIENTAÇÃO AO CONSUMIDOR —
#: "o consignado só pode ser feito por bancos autorizados pelo Banco Central",
#: "procure sempre um correspondente bancário credenciado". São exatamente as
#: frases que uma página honesta escreve, e ela reprovava por escrevê-las.
_CREDENCIAL_RE = re.compile(
    r"(?i)\b(somos|s[ãa]o|est?amos|sou|nossa\s+empresa\s+[ée]|este\s+(site|portal)\s+[ée])\s+"
    r"(uma\s+|um\s+|os\s+|as\s+)?"
    r"(licenciad[oa]s?|credenciad[oa]s?|autorizad[oa]s?\s+pel[oa]|parceir[oa]s?\s+oficia(l|is)|"
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
        # ⚠️ O SUBSTANTIVO QUE ABRE A MOLDURA NÃO É A MARCA.
        #
        # `_MOLDURA_DE_PARCERIA_RE` inclui "Bancos como", "Empresas como" no
        # `group(0)`, e `_NOME_PROPRIO_RE` colhia "Empresas" como marca de
        # terceiro. Medido: "Empresas como a sua podem ser afetadas" reprovava a
        # página por `MARCA_TERCEIRA_SEM_LASTRO`. A marca é o que vem DEPOIS da
        # moldura, nunca a moldura.
        corpo = trecho.group(0)
        abertura = trecho.group(1) or ""
        corpo = corpo[len(abertura):] if corpo.startswith(abertura) else corpo
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
    if pagina.documento_parcial:
        # Não há rodapé para observar num fragmento. `not_applicable` é a
        # resposta honesta — e ela é conclusiva antes da publicação e DEIXA de
        # ser conclusiva no ponto de campanha, onde a página inteira está no ar.
        return Verificacao(
            nome=V_IDENTIDADE,
            status=STATUS_NAO_APLICAVEL,
            detalhe=(
                "documento parcial: o rodapé de identidade é renderizado pelo tema "
                "e não existe no artefato. Verificável apenas na leitura ao vivo."
            ),
        )
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

    # ⚠️ ERAM DOIS REQUISITOS INDEPENDENTES COLAPSADOS NUM `OU`.
    #
    # A regra anterior — `not cnpjs and not (tem_sobre and tem_contato)` —
    # aprovava por CNPJ **ou** por "sobre"+"contato". Uma página sem CNPJ
    # nenhum, contendo só as palavras "Sobre" e "Contato", passava como
    # operador identificado. É a mesma forma do defeito `adsense OU utilidade
    # pública` que o `ROOT-CAUSE-ANALYSIS.md` nomeia: dois requisitos
    # diferentes, um `ou` no meio, e o mais barato satisfazendo o outro.
    #
    # São perguntas diferentes: "QUEM é o operador, com registro" e "COMO se
    # chega até ele". A segunda já tinha achado próprio
    # (`IDENTIDADE_CONTATO_AUSENTE`); a primeira passa a ter o seu.
    if not cnpjs:
        achados.append(
            Achado(
                "IDENTIDADE_OPERADOR_AUSENTE",
                "Nenhum registro de operador (CNPJ) na página. 'Sobre' e 'Contato' "
                "dizem como chegar a alguém; eles não dizem QUEM responde.",
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
    # ⚠️ O `and cnpjs` continua, e agora é correto: sem CNPJ na página,
    # `IDENTIDADE_OPERADOR_AUSENTE` já reprovou acima. Antes desta correção o
    # par deixava um buraco no meio — a página sem CNPJ não caía nem por
    # ausência (bastava "Sobre"+"Contato") nem por divergência (não havia o que
    # divergir).
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
    # ⚠️ A REGRA DO VOLC FALA DO CORPO VISÍVEL, e a varredura lia o HTML inteiro.
    #
    # Um `<div style="display:none"><a href="...">` reprovava a página por
    # "hyperlink externo na experiência paga" — e o leitor nunca vê aquele link.
    # Bloqueio falso é como a operação desliga o portão.
    #
    # O link escondido NÃO some: ele entra no inventário marcado `oculto`, e um
    # host desconhecido continua caindo em `LINK_EXTERNO_NAO_CLASSIFICADO` —
    # essa regra é sobre CLASSIFICAÇÃO, não sobre visibilidade. Esconder um link
    # não o torna confiável; só o tira do corpo visível.
    ocultos = {
        (l.get("href") or "").strip()
        for l in analisar(_ESCONDIDO_RE.sub(" ", pagina.html or "")).links
    }
    ocultos = {
        (l.get("href") or "").strip() for l in parser.links
    } - ocultos
    achados: list[Achado] = []
    inventario: list[dict[str, Any]] = []
    vistos_desconhecidos: set[str] = set()
    # Só para a EVIDÊNCIA do achado: saber que o link externo é justamente uma
    # fonte da pesquisa daquela página torna a mensagem acionável ("mova para o
    # dossiê") em vez de genérica ("tem link externo").
    _hosts_de_pesquisa = {_host(f) for f in pagina.fontes_de_pesquisa if f}

    for link in parser.links:
        href = (link.get("href") or "").strip()
        # ⚠️ MINÚSCULAS ANTES DE COMPARAR ESQUEMA.
        #
        # `startswith(("javascript:", ...))` era case-sensitive, e
        # `JaVaScRiPt:` escapava — depois `urljoin`/`_host` devolviam host
        # vazio, que `classificar_host` lê como link RELATIVO. Ou seja: a
        # capitalização transformava um esquema não resolvível em link interno.
        esquema_baixo = href.lower()
        # ⚠️ CTA COM DESTINO VAZIO: DETECTADO, INVENTARIADO, E NÃO BLOQUEADO.
        #
        # A frente do motor reportou a lacuna: um botão cujo `href` é vazio saía
        # por este mesmo `continue` e nenhuma varredura o via. É lacuna real.
        #
        # Uma primeira versão desta linha o transformou em bloqueio — e o
        # primeiro contato com a realidade foi um FALSO BLOQUEIO: num run
        # `--only p1` as rotas interiores ainda não existem, então TODO CTA da
        # LP tem href vazio por ordem de construção, não por defeito. O portão
        # reprovou uma página correta, que é como a operação desliga o portão.
        #
        # A distinção que faltaria — "a rota ainda não resolveu" × "o botão
        # morreu" — não é observável a partir do documento sozinho. Enquanto ela
        # não existir, o fato entra no inventário e a decisão fica com quem tem
        # o contexto do pipeline. Ver REMAINING-RISKS.md §4.
        if link.get("em_botao") and href.strip() in ("", "#"):
            inventario.append({
                "host": "", "classe": CLASSE_NAO_RESOLVIVEL,
                "ancora": (link.get("texto") or "")[:80], "ancora_e_valor": False,
                "em_botao": True, "rel": "", "cta_sem_destino": True,
            })
        if not href or esquema_baixo.startswith("#"):
            # Âncora interna não é navegação para fora. Não entra no inventário
            # porque inventariá-la afogaria o que importa num sumário.
            continue
        if esquema_baixo.startswith(("mailto:", "tel:")):
            # Permitidos e coerentes: um destino pago PRECISA de caminho de
            # contato. Entram no inventário para que a decisão fique visível —
            # "não achei" e "achei e permiti" não podem ter a mesma aparência.
            inventario.append({"host": "", "classe": CLASSE_CONTATO_DIRETO,
                               "ancora": (link.get("texto") or "")[:80],
                               "ancora_e_valor": False,
                               "em_botao": bool(link.get("em_botao")),
                               "rel": link.get("rel", "")})
            continue
        if esquema_baixo.startswith(("javascript:", "data:", "blob:", "vbscript:", "file:")):
            # ⚠️ ANTES DA v2 ISTO CAÍA NO MESMO `continue` DA ÂNCORA INTERNA.
            #
            # `javascript:` é navegação clicável cujo destino o portão não tem
            # como resolver lendo HTML — é a definição de não classificável, e
            # não classificado reprova destino pago. Tratá-lo como âncora
            # interna era a forma mais barata de esconder um link do inventário.
            esquema = esquema_baixo.split(":", 1)[0]
            if esquema not in vistos_desconhecidos:
                vistos_desconhecidos.add(esquema)
                achados.append(
                    Achado(
                        "LINK_EXTERNO_NAO_CLASSIFICADO",
                        f"Link clicável com esquema {esquema}: o destino não é "
                        f"resolvível na leitura do documento, e o que não "
                        f"classifica não aprova.",
                        evidencia={"esquema": esquema,
                                   "em_botao": bool(link.get("em_botao"))},
                    )
                )
            inventario.append({"host": "", "classe": CLASSE_NAO_RESOLVIVEL,
                               "ancora": (link.get("texto") or "")[:80],
                               "ancora_e_valor": False,
                               "em_botao": bool(link.get("em_botao")),
                               "rel": link.get("rel", "")})
            continue
        # A base do documento tem precedência sobre a URL da página — é
        # exatamente para isso que `<base href>` existe, e ignorá-la fazia um
        # link relativo apontar para outro domínio parecer interno.
        base = urljoin(pagina.url or "", parser.base) if parser.base else (pagina.url or "")
        absoluto = urljoin(base, href)
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
            "oculto": href in ocultos,
            "tag": link.get("origem_da_tag", "a"),
            "regiao": str(link.get("regiao") or REGIAO_CORPO),
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
        # ── A REGRA INTERNA DO VOLC, e o motivo de ela não julgar caso a caso ──
        #
        # ⚠️ POLÍTICA INTERNA MAIS RESTRITIVA QUE A DO GOOGLE. O Google não
        # proíbe hyperlink externo em página de destino; ele proíbe sugerir
        # vínculo e proíbe a página-ponte. A decisão de banir TODO hyperlink
        # externo clicável no corpo visível e no CTA de um `paid_destination` é
        # da casa.
        #
        # Ela existe porque a regra anterior — barrar só o host NÃO CLASSIFICADO
        # — deixava passar exatamente o que foi ao ar: `caixa.gov.br` é host de
        # governo, classificado, e uma fonte de pesquisa declarada é
        # `fonte_declarada`, também classificada. As duas passavam em silêncio.
        #
        # O achado é emitido para TODO papel; quem decide se ele reprova é
        # `contrato.severidade()`. Em `editorial_solution` e `organic_article` a
        # referência externa continua permitida e o achado fica registrado — o
        # papel da página decide o peso, nunca a existência do fato.
        if classe not in _CLASSES_INTERNAS and href not in ocultos:
            regiao = str(link.get("regiao") or REGIAO_CORPO)
            no_chrome = regiao in REGIOES_DE_CHROME
            # ⚠️ SÓ A CONFIGURAÇÃO DO SITE autoriza um host de chrome.
            #
            # `hosts_declarados` e `adtech_declarada` NÃO valem aqui: a primeira
            # é a evidência de pesquisa que o chamador trouxe, a segunda
            # autoriza recurso técnico. Nenhuma das duas é procedência sobre o
            # template do site, e aceitar qualquer uma faria um campo de payload
            # virar a chave que abre a política de links.
            autorizado_no_chrome = no_chrome and any(
                _mesmo_site(host, c.lower()) for c in pagina.chrome_declarado_pelo_site
            )
            if autorizado_no_chrome:
                item["chrome_declarado"] = True
            elif no_chrome:
                achados.append(
                    Achado(
                        "LINK_EXTERNO_NO_CHROME",
                        "Hyperlink externo no chrome do site (cabeçalho, rodapé, "
                        "navegação ou widget). Ele continua saindo do destino pago — "
                        "e o dono do conserto é o TEMA/WordPress, não o conteúdo do "
                        "funil: remover do template, ou declarar o host no chrome do "
                        "site com procedência.",
                        evidencia={"host": host, "regiao": regiao,
                                   "ancora": texto[:60],
                                   "proximo_ato": "tema/WordPress"},
                    )
                )
            else:
                achados.append(
                    Achado(
                            "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO",
                        "Hyperlink externo clicável no CORPO da experiência paga. A "
                        "fonte fica no dossiê de evidência e é citada em prosa; ela "
                        "não vira âncora no corpo de um destino que recebe clique "
                        "comprado.",
                        evidencia={"host": host, "classe": classe,
                                   "regiao": regiao,
                                   "ancora": texto[:60],
                                   "em_botao": bool(link.get("em_botao")),
                                   "e_fonte_de_pesquisa": host in _hosts_de_pesquisa},
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
                "busca_do_site": busca and not classes,
                "classes_sensiveis": sorted(set(classes)),
            }
        )
        # ⚠️ `type="search"` NÃO É PASSE LIVRE.
        #
        # A isenção existe porque a busca do WordPress (`<input name="s">`) não
        # é coleta de dado, e reprovar por causa dela seria falso bloqueio. Mas
        # ela era decidida SÓ pelo tipo: `<input type="search" name="cpf">`
        # entrava como busca e o CPF sumia da varredura.
        #
        # Quando o campo carrega classe sensível, o que ele pede vale mais que
        # como ele foi rotulado — nome e placeholder são o que o visitante lê.
        if busca and classes:
            busca = False
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
#: ⚠️ DOIS TERMOS SAÍRAM DA LISTA, e a saída é o conserto de um falso bloqueio.
#:
#: "cin" casava por substring dentro de "cinco" e "vacina"; "visto" é, em
#: português, o particípio mais comum de "ver". Com "emitir" na mesma página —
#: um verbo banal — a frase "Aprenda a emitir notas em cinco passos" emitia
#: `SERVICO_GOVERNAMENTAL_RESTRITO`. Texto editorial comum reprovado por
#: coincidência de letras é o caminho mais curto para a operação desligar o
#: portão, e portão desligado não protege nada.
#:
#: Os dois voltam pela forma NÃO ambígua: "CIN" só como sigla escrita por
#: extenso ao lado do nome do documento, e "visto" só com o qualificador que o
#: torna documento ("visto americano", "visto consular", "visto de trabalho").
_DOCUMENTOS_RESTRITOS = (
    "carteira de identidade", "identidade nacional", "carteira de identidade nacional",
    "rg digital", "passaporte", "cnh", "carteira de motorista",
    "certidão de nascimento", "certidão de óbito", "título de eleitor", "cpf",
    "licenciamento de veículo",
    "visto americano", "visto consular", "visto de trabalho", "visto de turismo",
    "visto de estudante", "visto permanente",
)
#: Verbo que promete EXECUTAR o serviço no lugar do leitor, e não explicá-lo.
_VERBO_DE_AQUISICAO = (
    r"(?i)\b(emitir|emiss[ãa]o\s+d[eo]|solicitar\s+(seu|sua|o|a)|tirar\s+(seu|sua|o|a)|"
    r"agendar\s+(seu|sua|o|a)|requerer|gerar\s+(seu|sua|o|a)\s+(documento|certid))"
)


#: A moldura que faz o leitor concluir que a página É o canal oficial, ou que o
#: órgão liberou algo POR MEIO dela. Não é blacklist de palavra solta: cada
#: entrada é uma CONSTRUÇÃO — "governo" sozinho é jornalismo, "liberado pelo
#: governo" é promessa de origem.
_OFICIALIZANTE_RE = re.compile(
    r"(?i)("
    r"liberad[oa]s?\s+pel[oa]\s+(governo|caixa|inss|receita|minist[ée]rio)"
    r"|(governo|caixa|inss|receita\s+federal|minist[ée]rio)\s+liber(a|ou|ado)"
    # "consulte o canal oficial" é ORIENTAÇÃO, e é literalmente a divulgação que
    # o contrato exige. O que acusa é a página DIZER que é o canal oficial.
    r"|\b(este|esse|nosso|somos\s+o)\s+(site|portal|canal|p[áa]gina|sistema)\s+oficial"
    r"|\b(site|portal|canal|sistema)\s+oficial\s+d[oae]s?\s+"
    r"(governo|caixa|inss|receita|minist[ée]rio|fgts)"
    # ⚠️ "Portal do INSS" não casava. A regra pedia a palavra "oficial", e a
    # forma mais direta de se apresentar como o órgão é não usá-la: o nome do
    # órgão logo depois de "portal/site/central/atendimento" já entrega a
    # promessa inteira.
    # ⚠️ `consulta` e `servi[çc]os?` SAÍRAM deste ramo, e `atendimento` também.
    #
    # Medido: "Consulta do FGTS: como ver seu saldo pelo aplicativo" é manchete
    # editorial banal e casava. Pior — a própria frase que `_DIVULGACAO_RE`
    # EXIGE ("consulte sempre o canal oficial") casava no ramo de cima, então
    # uma regra acusava exatamente o que a outra pedia. Restam as construções
    # que afirmam ser o CANAL do órgão, não falar sobre ele.
    r"|(site|portal|central(\s+de\s+atendimento)?)\s+d[oae]s?\s+"
    r"(governo|caixa|inss|receita\s+federal|minist[ée]rio|fgts|detran|senai)\b"
    r"|oficial\s+d[oa]\s+(governo|caixa|inss|receita|minist[ée]rio)"
    r"|novo\s+(benef[íi]cio|aux[íi]lio)\s+aprovado\s+pel[oa]"
    r")"
)


@lru_cache(maxsize=512)
def _padrao_de_termo(termo: str) -> re.Pattern[str]:
    """Termo com fronteira de palavra nas pontas alfanuméricas.

    `re.escape` cuida do ponto de "gov.br" e da barra de "pis/pasep"; o `\b`
    só entra onde a ponta é alfanumérica, senão ele nunca casaria.
    """
    corpo = re.escape(termo)
    inicio = r"\b" if termo[:1].isalnum() else ""
    fim = r"\b" if termo[-1:].isalnum() else ""
    return re.compile(f"(?i){inicio}{corpo}{fim}")


def _contar_termo(texto: str, termo: str) -> int:
    return len(_padrao_de_termo(termo).findall(texto))


def varrer_governo(pagina: PaginaObservada) -> Verificacao:
    texto = texto_visivel(pagina.html)
    if not texto:
        return Verificacao(
            nome=V_GOVERNO, status=STATUS_INDISPONIVEL, detalhe="página sem texto visível"
        )
    baixo = texto.lower()
    achados: list[Achado] = []

    # ⚠️ FRONTEIRA DE PALAVRA, e ela faltava nos dois.
    #
    # `_ORGAOS` contém "pis" e `_DOCUMENTOS_RESTRITOS` contém "cin" e "visto".
    # Por substring, "cin" casa dentro de "cinco" e "visto" é o particípio de
    # "ver" — então "Aprenda a emitir notas em cinco passos" emitia
    # `SERVICO_GOVERNAMENTAL_RESTRITO`. Falso bloqueio em texto editorial comum
    # é o caminho mais curto para a operação desligar o portão.
    mencoes = {orgao: n for orgao in _ORGAOS if (n := _contar_termo(baixo, orgao))}
    documentos = sorted({d for d in _DOCUMENTOS_RESTRITOS if _contar_termo(baixo, d)})
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
    # ── O TÍTULO E OS CABEÇALHOS, e por que eles não são "mais texto" ──────
    #
    # O H1 é a promessa que o clique comprado paga, e o leitor o lê antes de
    # qualquer rodapé. Um aviso de não-vínculo no pé da página não desfaz uma
    # manchete que diz que o governo liberou algo — quando o leitor chega ao
    # rodapé, ele já decidiu o que a página é.
    #
    # É por isso que este achado NÃO depende de `tem_aviso`: diferente de
    # `AVISO_NAO_OFICIAL_AUSENTE`, ele não é sobre faltar a ressalva; é sobre a
    # manchete afirmar uma origem que a página não tem. O funil histórico do
    # FGTS tinha rodapé completo E o H1 "Saque-Aniversário FGTS Liberado pelo
    # Governo": pelo contrato v1, ele passava.
    parser = analisar(pagina.html)
    manchetes = [{"onde": "title", "texto": parser.titulo}] if parser.titulo else []
    manchetes += [{"onde": c["nivel"], "texto": c["texto"]} for c in parser.cabecalhos]
    suspeitas = [
        m for m in manchetes
        if _OFICIALIZANTE_RE.search(m["texto"])
        and any(orgao in m["texto"].lower() for orgao in _ORGAOS)
    ]
    for suspeita in suspeitas[:4]:
        achados.append(
            Achado(
                "TITULO_SUGERE_ORIGEM_OFICIAL",
                "A manchete sugere que a página é o canal oficial ou que o órgão "
                "liberou algo por meio dela. O aviso no rodapé não desfaz isso: "
                "o leitor decide na primeira tela.",
                evidencia={"onde": suspeita["onde"], "texto": suspeita["texto"][:80]},
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
    inventario += [{"manchete": m["onde"], "texto": m["texto"][:80]} for m in manchetes[:12]]
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
#: Redirecionamento disparado pelo cliente. `location.assign` faltava, e com ele
#: cabia um cloaking inteiro: um script que só redireciona quem NÃO é Googlebot
#: serve os mesmos bytes às duas leituras, então a comparação rastreador/usuário
#: não vê nada — quem decide o destino é o JavaScript, depois.
_REDIRECIONA_CLIENTE_RE = re.compile(
    r"(?i)(window|document)\s*\.\s*location\s*="
    r"|\blocation\s*\.\s*(href|hash|pathname)\s*="
    r"|\blocation\s*\.\s*(replace|assign)\s*\("
    r"|\blocation\s*="
    r"|\bwindow\s*\.\s*open\s*\("
    r"|\bnavigation\s*\.\s*navigate\s*\("
)
#: `<meta http-equiv="refresh" content="0;url=...">` — redirecionamento sem uma
#: linha de JavaScript, e a varredura não o enxergava de jeito nenhum.
_META_REFRESH_RE = re.compile(
    r"(?is)<meta[^>]+http-equiv\s*=\s*[\"']?refresh[\"']?[^>]*>"
)
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
            # ⚠️ `href` SAIU DA BUSCA. Um link de navegação `http://` não é
            # sub-recurso: ele não é carregado na página, é seguido pelo
            # clique. Incluí-lo fazia o recibo afirmar "sub-recurso carregado
            # por http:// numa página https" sobre um link comum — uma frase
            # falsa dentro de um artefato de apelação, que é o pior lugar
            # possível para uma imprecisão.
            for u in re.findall(r'src=["\'](http://[^"\']+)', pagina.html or "")
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
    achado_de_redirecionamento = _REDIRECIONA_CLIENTE_RE.search(corpo_scripts)
    if achado_de_redirecionamento:
        achados.append(
            Achado(
                "SCRIPT_REDIRECIONA_CLIENT_SIDE",
                "JavaScript de redirecionamento client-side observado. Ele decide o "
                "destino DEPOIS da leitura, então servir os mesmos bytes aos dois "
                "user-agents não prova que os dois terminam no mesmo lugar.",
                evidencia={"construcao": achado_de_redirecionamento.group(0)[:60]},
            )
        )
    meta_refresh = _META_REFRESH_RE.search(pagina.html or "")
    if meta_refresh:
        achados.append(
            Achado(
                "SCRIPT_REDIRECIONA_CLIENT_SIDE",
                "`meta http-equiv=refresh` observado: a página redireciona sem uma "
                "linha de JavaScript, e sem aparecer na cadeia HTTP.",
                evidencia={"tag": meta_refresh.group(0)[:80]},
            )
        )

    # ⚠️ O STATUS HTTP ERA COLETADO E NÃO DECIDIA NADA.
    #
    # `PaginaObservada.status_http` existia desde a v1 e nenhuma varredura o
    # lia. Um destino que devolve 404 ou 410 ao revisor é o caso LITERAL de
    # "destinations that don't work" — e a página, sem conteúdo, passava por
    # todas as outras varreduras justamente por não ter nada que reprovasse.
    #
    # `volc_ads/policy/spec.py::checar_destino` modelava exatamente esta regra e
    # nunca era chamado; `volc_ads/campanha/search.py` registra em prosa que ele
    # ficava de fora "por falta de um status HTTP que ninguém aqui coleta". A
    # barreira 3 passou a coletar, e a regra passou a ter onde morar.
    if pagina.status_http is not None and not (200 <= int(pagina.status_http) < 300):
        achados.append(
            Achado(
                "DESTINO_NAO_RESPONDE",
                "O destino não devolve conteúdo: o status HTTP da leitura ao vivo "
                "está fora da faixa aceita.",
                evidencia={"status_http": int(pagina.status_http)},
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
    # A CADEIA, antes dos saltos individuais. Um salto é rotina de servidor
    # (http→https, com/sem barra final); uma cadeia é outra coisa. Cada elo a
    # mais é uma chance de o revisor e o visitante terminarem em páginas
    # diferentes, que é literalmente o que a política de circumventing systems
    # descreve.
    if len(saltos or []) > pagina.teto_de_saltos:
        achados.append(
            Achado(
                "CADEIA_DE_REDIRECIONAMENTO_EXCESSIVA",
                "A cadeia de redirecionamento até a URL final passa do teto aceito "
                "para um destino canônico.",
                evidencia={
                    "saltos": len(saltos or []),
                    "teto": pagina.teto_de_saltos,
                    "hosts": [_host(str(x.get("to") or "")) for x in (saltos or [])][:6],
                },
            )
        )
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
    # ⚠️ A IMPRESSÃO CANÔNICA TEM PRECEDÊNCIA SOBRE O BYTE.
    #
    # Quando a casa gravou a impressão canônica na aprovação, a comparação é
    # feita sobre ela: duas leituras da mesma página aprovada diferem em bytes
    # (token rotativo de push, nonce, carimbo de cache) sem diferir em nada que
    # o leitor veja. Reprovar por deriva a cada rotação de token faria a
    # operação desligar o portão, e um portão desligado não protege nada.
    #
    # Sem impressão gravada — recibo antigo, artefato de outra época — o byte
    # continua sendo a única referência, e ele é usado assim mesmo: uma medida
    # ruidosa é melhor que nenhuma, desde que o recibo diga QUAL foi usada.
    if pagina.e_o_ato_de_auditoria and not pagina.impressao_aprovada:
        # Deriva mede distância até uma aprovação. Na primeira auditoria não há
        # de onde derivar — e é justamente o marco zero que este ato grava.
        return Verificacao(
            nome=V_DERIVA,
            status=STATUS_NAO_APLICAVEL,
            detalhe=(
                "primeira auditoria ao vivo desta URL: não há aprovação anterior "
                "de onde derivar, e é o marco zero que este ato registra"
            ),
        )
    if pagina.impressao_aprovada:
        observada = impressao_canonica(pagina.html) if pagina.html else None
        if observada is None:
            return Verificacao(
                nome=V_DERIVA,
                status=STATUS_INDISPONIVEL,
                detalhe="impressão aprovada registrada, mas nenhum HTML ao vivo para comparar",
            )
        divergiu = observada != pagina.impressao_aprovada
        return Verificacao(
            nome=V_DERIVA,
            status=STATUS_OBSERVADO,
            achados=(
                [
                    Achado(
                        "DERIVA_AO_VIVO",
                        "O conteúdo no ar não é o que foi aprovado — a diferença é "
                        "estrutural, não ruído de rotação.",
                        evidencia={
                            "base": "impressao_canonica",
                            "aprovado_12": pagina.impressao_aprovada[:12],
                            "observado_12": observada[:12],
                        },
                    )
                ]
                if divergiu
                else []
            ),
            inventario=[
                {
                    "base": "impressao_canonica",
                    "aprovado_12": pagina.impressao_aprovada[:12],
                    "observado_12": observada[:12],
                    "sha256_aprovado_12": (pagina.sha256_aprovado or "")[:12],
                    "sha256_observado_12": (pagina.sha256_observado or "")[:12],
                }
            ],
        )

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


# ── o recibo de aprovação ──────────────────────────────────────────────────


def varrer_recibo(pagina: PaginaObservada) -> Verificacao:
    """A única varredura que não olha a página: ela olha o RECIBO da aprovação.

    ## Por que ela é separada de `varrer_deriva`

    `live_drift` responde "o conteúdo no ar é o aprovado?". Ela pressupõe que
    exista um aprovado. Quando não existe, ela devolve `unavailable` — verdade,
    e insuficiente: a operação lê "não deu para comparar" e vai procurar o
    problema na comparação, quando o problema é que ninguém aprovou nada.

    São dois defeitos com consertos diferentes ("grave o hash na publicação" ×
    "reavalie o destino"), e a operação precisa de nomes diferentes para
    consertar o certo. Foi essa confusão que deixou `DERIVA_AO_VIVO` sair
    `unavailable` nos quatro destinos preservados sem ninguém tratar a ausência
    do recibo como o achado que ela era.

    ## As três perguntas, nesta ordem

    1. **existe?** Sem recibo resolvível, o portão não tem contra o que comparar.
    2. **é desta política?** Recibo emitido contra outra versão do contrato ou
       outra versão da matriz não prova nada sobre a regra vigente. Reaproveitá-lo
       em silêncio é a forma mais barata de um sistema mentir sobre a própria
       cobertura.
    3. **ainda vale?** Página no ar muda sem avisar. Um recibo velho descreve um
       conteúdo que pode não existir mais.

    ## Fora do ponto de campanha ela é `not_applicable`, não `unavailable`

    Antes de publicar não existe aprovação anterior a conferir. `unavailable`
    ali diria "não consegui olhar" para algo que não tem o que ser olhado — e a
    exigência por ponto de portão já cuida de não transformar isso em reprova.
    A distinção existe para o recibo não carregar um "não sei" que é, na
    verdade, um "não se aplica".
    """
    recibo = pagina.recibo_de_aprovacao
    if pagina.e_o_ato_de_auditoria and recibo is None:
        # ESTA avaliação é a auditoria. Não existe aprovação anterior porque
        # ela está sendo feita agora — e cobrar uma seria circular.
        return Verificacao(
            nome=V_RECIBO,
            status=STATUS_NAO_APLICAVEL,
            detalhe=(
                "esta avaliação É o ato de auditoria ao vivo: a aprovação anterior "
                "não existe por construção, e é ela que este ato produz"
            ),
        )
    if recibo is None and pagina.sha256_observado is None:
        # ⚠️ NADA NO AR AINDA: não há aprovação anterior a conferir.
        #
        # O discriminador é o MESMO de `varrer_deriva` de propósito — as duas
        # respondem perguntas sobre uma página publicada, e usar critérios
        # diferentes para decidir "já existe no ar?" faria as duas discordarem
        # sobre a mesma página.
        #
        # Emitir `RECIBO_DE_APROVACAO_AUSENTE` aqui reprovaria toda página
        # primeira, na geração, por uma impossibilidade estrutural — que é
        # exatamente o erro que `EXIGENCIAS_POR_PONTO` existe para não cometer.
        return Verificacao(
            nome=V_RECIBO,
            status=STATUS_NAO_APLICAVEL,
            detalhe="nenhuma leitura ao vivo nesta avaliação: não há aprovação anterior a conferir",
        )
    if recibo is None:
        return Verificacao(
            nome=V_RECIBO,
            status=STATUS_INDISPONIVEL,
            achados=[
                Achado(
                    "RECIBO_DE_APROVACAO_AUSENTE",
                    "Nenhum recibo de aprovação resolvível para esta URL. Sem ele "
                    "não há hash aprovado, e sem hash aprovado a deriva do que "
                    "está no ar é immensurável.",
                    evidencia={"url": pagina.url[:120]},
                )
            ],
            detalhe="nenhum recibo de aprovação resolvível para esta URL",
        )

    achados: list[Achado] = []
    contrato_do_recibo = str(recibo.get("policy_contract_version") or "")
    fonte_do_recibo = str(recibo.get("policy_source_version") or "")
    fonte_vigente = versao_da_fonte()
    if contrato_do_recibo != POLICY_CONTRACT_VERSION or fonte_do_recibo != fonte_vigente:
        achados.append(
            Achado(
                "RECIBO_DE_POLITICA_DESATUALIZADO",
                "O recibo foi emitido contra outra versão da política. Ele não "
                "prova nada sobre a regra vigente.",
                evidencia={
                    "contrato_do_recibo": contrato_do_recibo or "ausente",
                    "contrato_vigente": POLICY_CONTRACT_VERSION,
                    "fonte_do_recibo": fonte_do_recibo or "ausente",
                    "fonte_vigente": fonte_vigente,
                },
            )
        )

    # ⚠️ O VEREDITO DO RECIBO, ANTES DA DATA DELE.
    #
    # Conferir versão e frescor sem ler o veredito é o erro mais sutil possível:
    # o portão fica verde por causa de um artefato que diz vermelho. Medido na
    # revisão adversarial cruzada — um recibo com `paid_destination_ready:
    # false` e um bloqueio listado satisfazia esta verificação.
    if recibo.get("paid_destination_ready") is not True:
        achados.append(
            Achado(
                "RECIBO_NAO_APROVA_O_DESTINO",
                "O recibo existe, é desta política e está no prazo — e ele diz que "
                "a página NÃO foi aprovada.",
                evidencia={
                    "paid_destination_ready": recibo.get("paid_destination_ready"),
                    "verdict": recibo.get("verdict"),
                    "bloqueios_no_recibo": [
                        b.get("code")
                        for b in (recibo.get("blockers") or [])
                        if isinstance(b, dict)
                    ][:6],
                },
            )
        )

    # ⚠️ E A QUE CONTEÚDO ELE SE REFERE.
    #
    # Um recibo aprova UM conteúdo, não uma URL para sempre. Sem esta amarra, a
    # aprovação vira credencial transferível: bastava passar o recibo de uma
    # página limpa junto com o HTML de outra. Também medido.
    #
    # A comparação é sobre a IMPRESSÃO CANÔNICA quando ela existe nos dois
    # lados — o byte diverge por rotação de anúncio e faria falso vermelho.
    # ⚠️ SÓ SE COMPARA IMPRESSÃO DO MESMO ESCOPO DE DOCUMENTO.
    #
    # O recibo do portão 2 carimba a impressão do ARTEFATO — o corpo que o motor
    # produziu. O portão 3 observa a página AO VIVO, que é o artefato DENTRO do
    # tema do WordPress: cabeçalho, menu, rodapé institucional, slots de anúncio.
    # São dois documentos diferentes por construção, e eles NUNCA vão ter a mesma
    # impressão canônica.
    #
    # A primeira versão desta amarra comparava os dois sem olhar o escopo, e o
    # efeito medido foi total: `RECIBO_DE_OUTRO_CONTEUDO` em 100% das páginas
    # corretas, ou seja, a barreira 3 nunca podia ficar verde. Um portão que
    # nunca aprova é indistinguível de um portão quebrado.
    #
    # A proteção que a amarra existe para dar — recibo de OUTRA página não
    # aprova esta — continua valendo dentro do mesmo escopo. Entre escopos
    # diferentes a pergunta não é respondível, e a resposta honesta é registrar
    # isso no inventário em vez de fabricar um veredito nos dois sentidos.
    escopo_do_recibo = str(recibo.get("fingerprint_scope") or "artifact")
    escopo_observado = "live" if pagina.sha256_observado else "artifact"
    impressao_do_recibo = str(recibo.get("content_fingerprint") or "")
    if impressao_do_recibo and pagina.html and escopo_do_recibo == escopo_observado:
        impressao_no_ar = impressao_canonica(pagina.html)
        if impressao_do_recibo != impressao_no_ar:
            achados.append(
                Achado(
                    "RECIBO_DE_OUTRO_CONTEUDO",
                    "O recibo aprova um conteúdo diferente do que está sendo "
                    "avaliado agora.",
                    evidencia={
                        "no_recibo_12": impressao_do_recibo[:12],
                        "observado_12": impressao_no_ar[:12],
                    },
                )
            )
    elif not impressao_do_recibo:
        # Recibo antigo, sem impressão canônica gravada. Cai no sha256 do byte,
        # que é ruidoso — por isso vira RISCO por meio do inventário, e não
        # bloqueio: acusar deriva por rotação de token é como o portão é
        # desligado. A ausência fica registrada no inventário abaixo.
        pass

    emitido_em = recibo.get("observed_at_epoch")
    agora = pagina.avaliado_em_epoch
    idade: float | None = None
    if isinstance(emitido_em, (int, float)) and isinstance(agora, (int, float)):
        idade = float(agora) - float(emitido_em)
        # ⚠️ IDADE NEGATIVA É RECIBO DO FUTURO, e ele passava.
        #
        # `idade > janela` deixa passar qualquer carimbo adiante do relógio —
        # inclusive um posto por quem quisesse comprar frescor. Um recibo que
        # diz ter sido observado amanhã não é fresco: é inconsistente, e
        # inconsistência não vira aprovação.
        # ⚠️ A JANELA É SOBRE A OBSERVAÇÃO AO VIVO, NÃO SOBRE O ARTEFATO.
        #
        # Um recibo de escopo `artifact` carimba quando o CONTEÚDO foi aprovado.
        # Esse fato não envelhece: o conteúdo aprovado continua sendo aquele.
        # O que envelhece é a leitura da página no ar — e a barreira 3 faz uma
        # leitura NOVA a cada chamada, então ela é fresca por construção.
        #
        # Medido: aplicando a janela ao recibo do artefato, publicar hoje e
        # subir a campanha depois de amanhã produzia `RECIBO_DE_APROVACAO_VENCIDO`
        # PARA SEMPRE, sem nenhuma rota que reemitisse o recibo. A operação
        # ficaria com uma LP publicada que nunca mais poderia virar campanha.
        #
        # Carimbo no futuro continua reprovando em qualquer escopo: isso não é
        # idade, é inconsistência.
        vencido_por_idade = (
            escopo_do_recibo == "live" and idade > pagina.janela_de_frescor_s
        )
        if idade < -_TOLERANCIA_DE_RELOGIO_S or vencido_por_idade:
            achados.append(
                Achado(
                    "RECIBO_DE_APROVACAO_VENCIDO",
                    "A observação que sustenta este recibo está fora da janela de "
                    "frescor. 'Estava apto' não é 'está apto' — e um carimbo no "
                    "futuro não é frescor, é inconsistência.",
                    evidencia={
                        "idade_s": int(idade),
                        "janela_s": int(pagina.janela_de_frescor_s),
                        "no_futuro": idade < 0,
                    },
                )
            )
    else:
        # ⚠️ NÃO CONSEGUIR MEDIR O FRESCOR NÃO É FRESCOR CONFIRMADO.
        #
        # Devolver `observed` aqui faria um recibo sem carimbo parecer sempre
        # novo — o mesmo falso verde que a doutrina inteira existe para impedir.
        return Verificacao(
            nome=V_RECIBO,
            status=STATUS_INDISPONIVEL,
            achados=achados,
            inventario=[{"recibo_sem_carimbo_comparavel": True}],
            detalhe=(
                "recibo sem `observed_at_epoch` ou avaliação sem "
                "`avaliado_em_epoch`: o frescor não pôde ser medido"
            ),
        )

    return Verificacao(
        nome=V_RECIBO,
        status=STATUS_OBSERVADO,
        achados=achados,
        inventario=[
            {
                "policy_contract_version": contrato_do_recibo,
                "policy_source_version": fonte_do_recibo,
                "idade_s": int(idade) if idade is not None else None,
                "janela_s": int(pagina.janela_de_frescor_s),
                "content_sha256_12": str(recibo.get("content_sha256") or "")[:12],
                "content_fingerprint_12": impressao_do_recibo[:12] or None,
                "fingerprint_scope_do_recibo": escopo_do_recibo,
                "fingerprint_scope_observado": escopo_observado,
                "impressao_conferida": bool(
                    impressao_do_recibo and pagina.html and escopo_do_recibo == escopo_observado
                ),
                "paid_destination_ready_no_recibo": bool(
                    recibo.get("paid_destination_ready")
                ),
            }
        ],
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
    V_RECIBO: varrer_recibo,
}
