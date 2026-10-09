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


#: Teto do rótulo do botão: ~2 linhas num botão de 390 px. O prompt pede
#: "até uns 50"; o portão dá folga e só barra o que já virou duas orações
#: ("Entender quem pode ter direito e evitar uma conclusão pelo NIS…", 76).
CTA_MAX_CHARS = 60

# O RISCO de um botão interno não é o verbo, é dizer que ESTE SITE executa:
# consulta de dado pessoal, pedido, liberação, pagamento, saque, aprovação.
# Até 09/10 o portão barrava todo rótulo iniciado por consultar/calcular/…
# e mandava "Use 'Ver como…'"; somado ao prompt, "Entender/Ver como…" virou a
# única forma que passava e todo funil saía com os mesmos botões mornos.
_EXECUCAO_RE = re.compile(r'^(solicit(ar|e)|liber(ar|e)|receb(er|a)|sac(ar|ue))\b')
_CONSULTA_RE = re.compile(r'^consult(ar|e)\b(?P<resto>.*)$')
_FERRAMENTA_RE = re.compile(r'^(calcul(ar|e)|simul(ar|e))\b'
                            r'|^estim(ar|e) (?:o |a |os |as )?(meu|minha|meus|minhas|seu|sua|seus|suas)\b')
_POSSE = r'(?:meu|minha|meus|minhas|seu|sua|seus|suas)'
_DADOS = (r'saldo|extrato|cpf|nis|pagamentos?|parcelas?|resultado|protocolo|pedido|'
          r'cadastro|beneficio|dinheiro|deposito')
_DADO_CONSULTADO = rf'(?:{_DADOS})'
# Depois de "consultar", situação/status também são o dado pessoal consultado.
_DADO_PESSOAL = rf'(?:{_DADOS}|situacao|status)'
_CANAL = r'\b(?:app|aplicativo|portal|site|canal|gov\.br|caixa|agora)\b'
# "Ver meu saldo", "Conferir meu benefício": consulta pessoal que o site não faz.
# "Ver se minha família atende aos requisitos" passa: família não é dado consultado.
_CONSULTA_PESSOAL_RE = re.compile(
    rf'^(?:ver|veja|conferir|confira|checar|verificar|acompanhar|saber|descobrir)'
    rf'(?: se)?(?: (?:o|a|os|as))? {_POSSE} (?:\w+ )?{_DADO_CONSULTADO}\b')
_APROVACAO_RE = re.compile(r'\bse (?:\w+ ){0,2}(?:fui|foi|fomos|foram|serei|sera|vou ser|esta|estou)'
                           r' (?:aprovad|liberad|depositad|pag[oa]\b|contemplad|selecionad)')
_ENQUADRAMENTO_RE = re.compile(r'\b(?:como|onde|quando|o que)\b')


def _href_canonico(href: str) -> str:
    partes = urlsplit(href or "")
    return f"{(partes.hostname or '').lower()}{partes.path.rstrip('/')}"


def _destino_tem_ferramenta(href: str, ctx: dict) -> bool:
    """`ctx["destinos_com_ferramenta"]`: URLs ou slugs dos destinos com ferramenta
    funcionando (ativo interativo/calculadora). Ausente = nenhum: prometer cálculo
    sem saber que a ferramenta existe é a mentira que o botão não pode contar."""
    alvo = _href_canonico(href)
    slug = alvo.rsplit('/', 1)[-1]
    for d in ctx.get("destinos_com_ferramenta") or ():
        d_canon = _href_canonico(d) if urlsplit(d).hostname else d.strip('/').rsplit('/', 1)[-1]
        if d_canon and d_canon in (alvo, slug):
            return True
    return False


def _promessa_interna_indevida(text: str, href: str, ctx: dict) -> str:
    """Motivo pelo qual um botão INTERNO promete o que o site não faz; "" se não promete."""
    if _EXECUCAO_RE.match(text):
        return "diz que o site solicita, libera, paga ou saca"
    consulta = _CONSULTA_RE.match(text)
    if consulta:
        resto = consulta.group("resto").strip()
        if (not resto or re.search(rf'\b{_POSSE}\b|\b{_DADO_PESSOAL}\b', resto)
                or re.search(_CANAL, resto)):
            return "diz que o site faz a consulta"
    if _FERRAMENTA_RE.match(text) and not _destino_tem_ferramenta(href, ctx):
        return "promete um cálculo, mas o destino não tem ferramenta funcionando"
    for padrao, motivo in ((_CONSULTA_PESSOAL_RE, "promete consultar dado pessoal do leitor"),
                           (_APROVACAO_RE, "promete informar aprovação ou pagamento do leitor")):
        hit = padrao.search(text)
        quadro = _ENQUADRAMENTO_RE.search(text)
        if hit and not (quadro and quadro.start() < hit.start()):
            return motivo
    return ""


def cta_issues(pairs: list[tuple[str, str]], ctx: dict) -> list[Issue]:
    if not ctx.get("copy_rapida"):
        return []
    issues = []
    host = urlsplit(ctx.get("domain", "")).hostname
    destino_do_rotulo: dict[str, str] = {}
    for label, href in pairs:
        text = fold(label).strip(' >»!.')
        internal = not urlsplit(href).hostname or urlsplit(href).hostname == host
        if cta_generico(label):
            issues.append(Issue(code="cta_generic", message=f'CTA "{label}": nomeie a resposta '
                                'obtida no destino, com ação + ganho concreto.'))
        motivo = _promessa_interna_indevida(text, href, ctx) if internal else ""
        if motivo:
            issues.append(Issue(code="cta_editorial_execution", message=(
                f'CTA "{label}" {motivo}; o destino é conteúdo deste site. Nomeie o que o '
                'leitor confere ou resolve lá, sem prometer aprovação, pagamento, consulta '
                'de dados pessoais ou cadastro.')))
        if not internal and not re.search(r'externo|site d[ao]|pagina d[ao]|canal d[ao]|'
                                          r'\.[a-z]{2,}', text):
            issues.append(Issue(code="cta_external_channel", message=f'CTA "{label}": identifique '
                                'o canal externo por nome, sem simular execução neste portal.'))
        visivel = " ".join(label.split()).strip(' >»')
        if len(visivel) > CTA_MAX_CHARS:
            issues.append(Issue(code="cta_longo", message=(
                f'CTA "{label}" tem {len(visivel)} caracteres (máx. {CTA_MAX_CHARS}): no '
                'celular vira bloco de texto. Uma ação e um objeto; corte a segunda oração '
                '("e evitar…", "e saber onde…").')))
        destino = _href_canonico(href)
        anterior = destino_do_rotulo.setdefault(text, destino)
        if anterior != destino:
            issues.append(Issue(code="cta_rotulo_repetido", message=(
                f'CTA "{label}" repete o texto de um botão que leva a outro destino; '
                'cada destino precisa nomear a própria resposta.')))
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
