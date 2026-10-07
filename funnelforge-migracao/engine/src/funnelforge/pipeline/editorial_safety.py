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
    "MANDATORY EDITORIAL IMAGE RULES: Create an unbranded editorial illustration. "
    "No logos, wordmarks, seals, coats of arms, flags used as institutional branding, "
    "government or bank insignia, branded uniforms, official documents or cards, "
    "QR codes, readable personal data, login screens, payment screens or replicas "
    "of official apps/websites anywhere in the image. No approval checkmarks, "
    "money received, guaranteed eligibility or completed-service success scenes. "
    "Depict the topic through specific unbranded activities, materials and environments. "
    "People are optional; use a simple, physically plausible composition. If present, "
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
            if tag == "textarea" or values.get("type", "text").lower() not in {
                "radio", "checkbox", "range", "button",
            }:
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
