"""Contrato canônico de copy e identificação editorial do motor."""
from __future__ import annotations

import re
import unicodedata
from html import escape
from urllib.parse import urlsplit

from funnelforge.domain.models import Issue
from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT
from funnelforge.pipeline.editorial_safety import EDITORIAL_NOTICE

SHORT_NOTICE = "Conteúdo independente, sem vínculo com as instituições citadas. Financiado por anúncios."


def fold(text: str) -> str:
    return " ".join(''.join(c for c in unicodedata.normalize('NFKD', text)
                           if not unicodedata.combining(c)).lower().split())


def footer_discloses(ctx: dict) -> bool:
    text = fold(ctx.get("rodape_institucional", ""))
    return bool(ctx.get("rodape_institucional_persistente")
                and re.search(r"sem vinculo|nao possuem vinculo|nao tem vinculo", text)
                and re.search(r"anuncios|publicidade|adsense", text))


def short_notice_html(domain: str = "") -> str:
    host = urlsplit(domain).hostname or "Portal informativo"
    return (f'<aside aria-label="Identidade editorial" style="padding:12px 16px;'
            f'font-size:14px;color:#242424"><strong>{escape(host)}</strong> — '
            f'{SHORT_NOTICE}</aside>')


def clean_body_notice(content: str, *, footer: bool) -> str:
    """Remove só os dois avisos canônicos exatos; preserva alertas contextuais."""
    notices = {fold(COMPLIANCE_NOTICE_TEXT), fold(EDITORIAL_NOTICE), fold(SHORT_NOTICE)}
    def remove(m):
        plain = re.sub(r'<[^>]+>', '', m.group(0))
        return '' if fold(plain) in notices else m.group(0)
    content = re.sub(r'<!--\s*wp:paragraph\b[^>]*-->.*?<!--\s*/wp:paragraph\s*-->',
                     remove, content, flags=re.S | re.I)
    content = re.sub(r'<p\b[^>]*>.*?</p>', remove, content, flags=re.S | re.I).strip()
    if not footer:
        content += f'\n<!-- wp:paragraph -->\n<p>{SHORT_NOTICE}</p>\n<!-- /wp:paragraph -->'
    return content


#: Rótulo que serviria a QUALQUER destino: não diz a dor/desejo do leitor, a
#: próxima resposta nem a consequência. Uma lista só — o portão do redator
#: (`cta_issues`) e o revisor de esqueleto (`jornada.esqueleto`) usam esta.
_CTA_GENERICO_RE = re.compile(
    r'(saiba mais|continuar|continue|clique aqui|ver informacoes|ver mais|leia mais|'
    r'entenda mais|confira|conferir|acessar|acesse|avancar|seguir|'
    r'proximo|proxima|proximo passo|proxima pagina|'
    r'(?:ler|leia|abrir|abra|acessar|acesse|ver|veja) (?:o )?'
    r'(?:guia|conteudo|passo a passo)|'
    r'(?:ler|leia|abrir|abra|acessar|acesse|ver|veja) (?:o )?guia de .+|'
    r'guia de .+|'
    r'(?:identificar|descobrir|escolher) qual (?:duvida|tema|assunto)'
    r'(?: resolver| ver)?(?: primeiro)?)')


def cta_generico(label: str) -> bool:
    return bool(_CTA_GENERICO_RE.fullmatch(fold(label).strip(' >»!.')))


def cta_issues(pairs: list[tuple[str, str]], ctx: dict) -> list[Issue]:
    if not ctx.get("copy_rapida"):
        return []
    issues = []
    host = urlsplit(ctx.get("domain", "")).hostname
    for label, href in pairs:
        text = fold(label).strip(' >»!.')
        internal = not urlsplit(href).hostname or urlsplit(href).hostname == host
        if cta_generico(label):
            issues.append(Issue(code="cta_generic", message=f'CTA "{label}": nomeie a resposta '
                                'obtida no destino, com ação + ganho concreto.'))
        if internal and re.match(r'^(consult(ar|e)|solicit(ar|e)|liber(ar|e)|receb(er|a)|'
                                 r'calcul(ar|e)|sac(ar|ue))\b', text):
            issues.append(Issue(code="cta_editorial_execution", message=f'CTA "{label}" promete '
                                'execução em conteúdo editorial. Use "Ver como…" + resposta.'))
        if not internal and not re.search(r'externo|site d[ao]|pagina d[ao]|canal d[ao]|'
                                          r'\.[a-z]{2,}', text):
            issues.append(Issue(code="cta_external_channel", message=f'CTA "{label}": identifique '
                                'o canal externo por nome, sem simular execução neste portal.'))
    return issues


def disclosure_issues(content: str, ctx: dict) -> list[Issue]:
    if not ctx.get("copy_rapida"):
        return []
    issues = []
    if COMPLIANCE_NOTICE_TEXT in content or EDITORIAL_NOTICE in content:
        issues.append(Issue(code="long_body_disclaimer", message="Disclaimer longo no corpo do perfil rápido."))
    count = content.count(SHORT_NOTICE)
    if count > 1:
        issues.append(Issue(code="duplicate_disclosure", message="Identificação curta duplicada."))
    if not footer_discloses(ctx) and count != 1:
        issues.append(Issue(code="independent_identity_missing",
                            message="Sem footer persistente: exige identificação curta única."))
    return issues
