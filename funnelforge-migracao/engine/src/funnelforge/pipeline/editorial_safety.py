"""Structural safeguards for editorial pages and generated illustrations."""
from __future__ import annotations

import hashlib
import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, StrictBool

from funnelforge.domain.models import Issue
from funnelforge.widgets.calculos import _JS as CALCULO_JS
from funnelforge.widgets.estilo import JS as WIDGET_JS

POLICY_VERSION = "editorial-visual-v2"
NOTICE_ID = "volc-editorial-notice"
EDITORIAL_NOTICE = (
    "Conteúdo editorial independente. Não somos banco, correspondente bancário, "
    "órgão público ou plataforma de solicitação. Publicamos guias informativos, "
    "sem vínculo com as instituições citadas. Não realizamos contratações nem "
    "pedimos senhas, CPF ou dados bancários nesta página."
)
IMAGE_RULES = (
    "MANDATORY EDITORIAL IMAGE RULES: Create an unbranded editorial photograph. "
    "No logos, wordmarks, seals, coats of arms, flags used as institutional branding, "
    "government or bank insignia, branded uniforms, official documents or cards, "
    "QR codes, readable personal data, login screens, payment screens or replicas "
    "of official apps/websites anywhere in the image. No approval checkmarks, "
    "money received, guaranteed eligibility or completed-service success scenes. "
    "No readable words, letters, numeric labels or labeled charts in synthetic images; "
    "all typography and factual data visualization are rendered later by code. "
    "Depict the topic through the reader's real situation: people from the plausible "
    "audience doing the concrete activity, with recognizable unbranded objects of the "
    "niche; a still life of generic symbols does not explain the topic. Keep a simple, "
    "physically plausible composition. If people are present, "
    "each person's visible limbs must connect correctly, with no extra hands, arms, "
    "fingers or fused objects. Avoid the default beige home desk with mug and tablet. "
    "The topic is context, never permission to reproduce an institution's identity."
)


def notice_html(domain: str = "") -> str:
    host = urlsplit(domain).hostname or "Portal informativo"
    return (
        f'<aside id="{NOTICE_ID}" aria-label="Identidade editorial" '
        'style="background:#ffffff;color:#242424;font-size:14px;line-height:1.5;'
        'padding:12px 16px;max-width:100%;box-sizing:border-box">'
        f'<strong>{escape(host)}</strong><br>{EDITORIAL_NOTICE}</aside>'
    )


def valid_web_url(value: str, *, relative: bool = True) -> bool:
    if not isinstance(value, str) or not value or any(ord(c) < 33 for c in value):
        return False
    if "\\" in value or value.startswith("//"):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.username or parsed.password:
            return False
        return bool(parsed.scheme in ("https", "http") and parsed.hostname) or (
            relative and not parsed.scheme and value.startswith(("/", "#")))
    except ValueError:
        return False


class _EditorialHTML(HTMLParser):
    def __init__(self, *, rich_only: bool):
        super().__init__(convert_charrefs=True)
        self.rich_only = rich_only
        self.issues: list[Issue] = []
        self.raw_tag = ""
        self.script_parts: list[str] = []
        self.widget_ids: set[str] = set()
        # Calculadoras do motor (`widgets/calculos.py`): a <section> com id
        # "vc-…" e data-vc-operation. Só elas podem ter entrada numérica.
        self.calc_ids: set[str] = set()

    def reject(self, reason: str) -> None:
        self.issues.append(Issue(code="unsafe_editorial_html", message=reason))

    def handle_starttag(self, tag, attrs):
        if self.rich_only:
            if tag not in {"p", "strong", "em", "ul", "ol", "li", "br", "a"}:
                self.reject(f"Tag não permitida no texto da LP: {tag}")
            allowed = {"href", "title", "rel", "target"} if tag == "a" else set()
            if any(k not in allowed for k, _ in attrs):
                self.reject(f"Atributo não permitido no texto da LP: {tag}")
        elif tag not in {
            "p", "a", "strong", "em", "b", "i", "small", "br", "hr", "div", "span",
            "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote",
            "cite", "code", "pre", "figure", "figcaption", "img", "table", "caption",
            "thead", "tbody", "tfoot", "tr", "th", "td", "details", "summary",
            "section", "aside", "label", "button", "select", "option", "input",
            "script", "style",
        }:
            self.reject(f"Superfície não editorial: {tag}")
        values = dict(attrs)
        if tag == "section" and re.fullmatch(r"vw-[a-f0-9]+", values.get("id") or ""):
            self.widget_ids.add(values["id"])
        if (tag == "section" and re.fullmatch(r"vc-[a-f0-9]{12}", values.get("id") or "")
                and values.get("data-vc-operation")):
            self.calc_ids.add(values["id"])
        if tag in {"script", "style"}:
            self.raw_tag = tag
            self.script_parts = []
            if attrs:
                self.reject(f"Atributos não permitidos em {tag}")
        style = values.get("style") or ""
        if re.search(r"url\s*\(|@import|expression\s*\(|\\", style, re.I):
            self.reject("CSS ativo/externo em atributo de estilo")
        if any(k.startswith("on") or k in {"srcdoc", "formaction", "action"} for k in values):
            self.reject("Código ou envio de formulário em atributo HTML")
        for key in ("href", "src"):
            if key in values and not valid_web_url(values[key] or ""):
                self.reject(f"URL insegura em {key}")
        if tag in {"input", "textarea"}:
            # Editorial widgets may offer choices, never collect free-text credentials.
            # A única entrada digitável é a numérica da calculadora do motor:
            # id da calculadora, inputmode numérico, sem nome (nada é enviado).
            numerica_da_calculadora = (
                tag == "input" and values.get("type", "text").lower() == "text"
                and values.get("inputmode") in {"numeric", "decimal"}
                and "name" not in values
                and any(re.fullmatch(re.escape(c) + r"-\d+", values.get("id") or "")
                        for c in self.calc_ids))
            if not numerica_da_calculadora and (
                    tag == "textarea" or values.get("type", "text").lower() not in {
                        "radio", "checkbox", "range", "button"}):
                self.reject("Campo de texto/dados pessoais não permitido no guia editorial")

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        if self.raw_tag:
            self.script_parts.append(data)
        elif re.search(r"\[/?[a-zA-Z_][\w-]*(?:\s|=|\])", data):
            self.reject("Shortcode em conteúdo editorial não autorizado")

    def handle_endtag(self, tag):
        if tag == self.raw_tag:
            body = "".join(self.script_parts).strip()
            if tag == "script" and not any(
                body == WIDGET_JS.replace("__ID__", wid).strip() for wid in self.widget_ids
            ) and not any(
                body == CALCULO_JS.replace("__ID__", cid).strip() for cid in self.calc_ids
            ):
                self.reject("JavaScript diferente do widget determinístico do engine")
            if tag == "style" and re.search(r"url\s*\(|@import|expression\s*\(|\\", body, re.I):
                self.reject("CSS ativo/externo no conteúdo editorial")
            self.raw_tag = ""


def html_issues(content: str, *, rich_only: bool = False) -> list[Issue]:
    parser = _EditorialHTML(rich_only=rich_only)
    try:
        parser.feed(content)
        parser.close()
    except Exception:
        return [Issue(code="unsafe_editorial_html", message="HTML não analisável")]
    if parser.raw_tag:
        parser.reject("Bloco executável sem fechamento")
    if rich_only and re.search(r"\[/?[a-zA-Z_][\w-]*(?:\s|=|\])", content):
        parser.reject("Shortcode não permitido em texto gerado pela LLM")
    return parser.issues


class ImageReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    third_party_branding: StrictBool
    official_document_or_interface: StrictBool
    personal_data_or_qr: StrictBool
    implied_approval_or_outcome: StrictBool
    anatomy_or_physics_error: StrictBool
    topic_mismatch: StrictBool
    uncertain: StrictBool
    evidence: str
    anatomy_evidence: str
    topic_evidence: str

    @property
    def accepted(self) -> bool:
        return all(value.strip() for value in (
            self.evidence, self.anatomy_evidence, self.topic_evidence,
        )) and not any((
            self.third_party_branding, self.official_document_or_interface,
            self.personal_data_or_qr, self.implied_approval_or_outcome, self.uncertain,
            self.anatomy_or_physics_error, self.topic_mismatch,
        ))


def image_receipt(path: str | Path, review: ImageReview) -> dict:
    return {"policy": POLICY_VERSION, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "accepted": review.accepted, "review": review.model_dump()}


def reviewed_image_issues(state, page_number: int) -> list[Issue]:
    path = state.images.get(page_number)
    if not path:
        return []
    receipt = state.image_reviews.get(page_number, {})
    try:
        review = ImageReview.model_validate(receipt.get("review"))
        if review.accepted and receipt == image_receipt(path, review):
            return []
    except (OSError, ValueError, TypeError):
        pass
    return [Issue(code="image_review_required",
                  message="Imagem ausente de revisão visual aprovada ou bytes alterados.")]


# ---------------------------------------------------------------------------
# Links por PAPEL da página (operador, 15/10/2026). Regra objetiva de URL e
# papel, sem leitura de sentido: LP e pré-sell organizam a decisão e só levam
# o leitor a páginas do próprio site; fonte e canal oficial clicáveis ficam nas
# páginas de SOLUÇÃO. A evidência continua no bucket, no dossiê e no recibo do
# revisor; "fonte factual" e "link visível ao leitor" são coisas diferentes.
# ---------------------------------------------------------------------------

PAPEIS_SEM_LINK_EXTERNO = frozenset({"LP", "PRESELL"})


class _Ancoras(HTMLParser):
    """O ÚNICO leitor de âncoras da regra de links por papel.

    O portão (`hrefs_do_html`) e o saneador (`remover_ancoras`) usam esta mesma
    classe: o que o portão enxerga como âncora é exatamente o que o saneador
    sabe tirar (href sem aspas, maiúsculas, entidades, `<a/>`, `<a>` sem
    fechamento). Antes eram uma regex de um lado e o parser do outro, e um
    `<a href=https://x>` sem aspas passava pelo saneador e reprovava no portão.
    Guarda o href e a posição de cada tag para o saneador cortar só a tag."""

    def __init__(self, texto: str) -> None:
        super().__init__(convert_charrefs=True)
        self._inicio_da_linha = [0]
        for i, c in enumerate(texto):
            if c == "\n":
                self._inicio_da_linha.append(i + 1)
        self._texto = texto
        self._abertas: list[dict] = []
        self.ancoras: list[dict] = []

    def _agora(self) -> int:
        linha, coluna = self.getpos()
        return self._inicio_da_linha[linha - 1] + coluna

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        inicio = self._agora()
        bruto = self.get_starttag_text() or ""
        ancora = {"href": (dict(attrs).get("href") or "").strip(),
                  "abre": (inicio, inicio + len(bruto)), "fecha": None}
        self.ancoras.append(ancora)
        self._abertas.append(ancora)

    def handle_startendtag(self, tag, attrs):
        # `<a href="..."/>`: uma tag só, sem corpo. Não abre nada.
        self.handle_starttag(tag, attrs)
        if tag == "a":
            self._abertas.pop()

    def handle_endtag(self, tag):
        if tag != "a" or not self._abertas:
            return
        inicio = self._agora()
        fim = self._texto.find(">", inicio)
        self._abertas.pop()["fecha"] = (inicio, len(self._texto) if fim == -1 else fim + 1)


def _ancoras_do_html(content: str) -> list[dict] | None:
    parser = _Ancoras(content or "")
    try:
        parser.feed(content or "")
        parser.close()
    except Exception:  # noqa: BLE001 - HTML ilegível é problema do html_issues
        return None
    return parser.ancoras


def hrefs_do_html(content: str) -> list[str]:
    """Os `href` de todas as âncoras do HTML (vazio quando não há âncora)."""
    return [a["href"] for a in (_ancoras_do_html(content) or [])]


def remover_ancoras(content: str, remover, *, sufixo_depois=None,
                    sufixo_no_corpo=None) -> tuple[str, int]:
    """Tira as TAGS `<a>`/`</a>` das âncoras cujo href satisfaz `remover(href)`;
    o texto da âncora fica. Mesmo parser do portão (`hrefs_do_html`): toda
    âncora que o portão enxerga, este corte enxerga.

    `sufixo_depois`/`sufixo_no_corpo` (regex) apagam o complemento que só fazia
    sentido com o link (", em site externo"), logo depois do `</a>` ou no fim do
    texto da âncora. Devolve (texto, quantas âncoras saíram)."""
    texto = content or ""
    ancoras = _ancoras_do_html(texto)
    if not ancoras:
        return texto, 0
    cortes: list[tuple[int, int]] = []
    total = 0
    for ancora in ancoras:
        if not remover(ancora["href"]):
            continue
        total += 1
        cortes.append(ancora["abre"])
        fecha = ancora["fecha"]
        if fecha is None:
            continue
        if sufixo_no_corpo is not None:
            corpo = texto[ancora["abre"][1]:fecha[0]]
            m = sufixo_no_corpo.search(corpo)
            if m:
                cortes.append((ancora["abre"][1] + m.start(), fecha[0]))
        fim = fecha[1]
        if sufixo_depois is not None:
            m = sufixo_depois.match(texto, fim)
            if m and m.end() > fim:
                fim = m.end()
        cortes.append((fecha[0], fim))
    saida: list[str] = []
    cursor = 0
    for inicio, fim in sorted(cortes):
        if inicio < cursor:
            inicio = cursor
        saida.append(texto[cursor:inicio])
        cursor = max(cursor, fim)
    saida.append(texto[cursor:])
    return "".join(saida), total


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def href_externo(href: str, dominio: str) -> bool:
    """Aponta para outro host? Relativo, âncora (#) e o próprio site não são."""
    if not href or href.startswith("#") or (href.startswith("/") and not href.startswith("//")):
        return False
    host, site = _host(href), _host(dominio if "//" in dominio else "https://" + dominio)
    if not host:
        return False
    return host != site and not host.endswith("." + site)


def links_externos_por_papel(content: str, *, papel: str, dominio: str) -> list[Issue]:
    """LP/pré-sell com `href` para outro host = erro estrutural. Solução: nada.

    Não é revisão de qualidade: é classificação de URL pelo papel da página.
    Quem decide promessa, tom e contexto continua sendo o revisor contextual."""
    if str(getattr(papel, "value", papel)) not in PAPEIS_SEM_LINK_EXTERNO:
        return []
    externos = sorted({h for h in hrefs_do_html(content) if href_externo(h, dominio)})
    if not externos:
        return []
    codigo = "link_externo_na_lp" if str(getattr(papel, "value", papel)) == "LP" \
        else "link_externo_na_presell"
    return [Issue(code=codigo, message=(
        f"{len(externos)} link(s) para outro site nesta página ({', '.join(externos[:4])}). "
        "LP e pré-sell só levam a páginas do próprio funil; fonte e canal oficial "
        "clicáveis ficam nas páginas de solução."))]


def links_no_texto_da_lp(campos: list[str]) -> list[Issue]:
    """Na LP, `<a>` só existe nos botões que o renderer monta. Qualquer âncora no
    texto gerado (intro, seções, FAQ, transição), interna ou externa, é erro."""
    total = sum(len(hrefs_do_html(c)) for c in campos if isinstance(c, str))
    if not total:
        return []
    return [Issue(code="link_no_texto_da_lp", message=(
        f"{total} link(s) no texto da LP. Os únicos links da LP são os botões do "
        "template, que o renderer monta com os destinos do funil."))]


def sem_ancoras(texto: str) -> tuple[str, int]:
    """Troca cada âncora pelo próprio texto (defesa da redação da LP V2, antes
    do contrato). Mesmo parser do portão. Devolve o texto e quantas saíram."""
    return remover_ancoras(texto, lambda _href: True)
