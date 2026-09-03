"""O PLANO como documento avaliável — o portão 1, antes de existir corpo escrito.

## O buraco que este módulo fecha

A alegação que derrubou a conta entrou pelo PLANO, não pelo corpo. O artefato
histórico do funil FGTS traz o H1 literal *"Saque-Aniversário FGTS Liberado pelo
Governo"*, e o portão de conteúdo do motor (`calm_utility`) bane a expressão no
CORPO — ou seja, ele olhava depois do ponto em que o defeito nasceu. Prova:
`backend/tests/test_landing_policy_regressao_fgts.py`.

Pior: o mesmo portão só recebia `content`. Título, H1, subtítulo, CTA, campo de
formulário e identidade do operador chegavam como campos ESTRUTURADOS, e um
portão que recebe só o corpo não tem como reprovar o que não está no corpo.

## A decisão de projeto: renderizar, não escrever varredura nova

Este módulo NÃO reimplementa nenhuma regra. Ele monta um documento canônico a
partir dos campos estruturados e entrega esse documento às MESMAS dez varreduras
que avaliam a página publicada.

O motivo é a equivalência: duas regras — uma para o plano, outra para a página —
divergem no primeiro mês, e aí o plano aprova o que a página reprova, ou o
contrário. Quem lê o recibo não teria como saber qual das duas estava certa.
Renderizando, "o plano passa" e "a página passa" respondem à mesma pergunta.

## Markdown e campo estruturado entram pela mesma porta

O corpo pode chegar como HTML (Gutenberg), Markdown (o que o LLM devolve) ou
texto puro. `_para_html` normaliza os três antes da varredura — um link em
`[texto](url)` é um link clicável tanto quanto `<a href>`, e um scanner que só
enxergasse HTML deixaria passar exatamente a forma que o redator produz.

## O que este módulo NÃO afirma

Ele não afirma que a página publicada será igual ao plano. Ele afirma que o
PLANO, avaliado como documento, não carrega defeito que reprovaria o destino —
e é por isso que o portão 2 roda de novo sobre o artefato final, sem confiar
neste.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from app.landing_policy.contrato import PapelDestino, PontoDePortao
from app.landing_policy.portao import Avaliacao, avaliar, papel_do_servidor
from app.landing_policy.varredura import PaginaObservada


@dataclass(frozen=True)
class PlanoDaPagina:
    """Os campos que o Redator/FunnelForge decide ANTES de escrever o corpo.

    Todo campo é opcional porque o plano é preenchido em etapas — mas ausência
    não vira aprovação: um plano sem identidade produz um documento sem
    identidade, e o portão reprova por identidade ausente, que é a verdade.
    """

    rota: str = ""
    titulo: str = ""
    h1: str = ""
    subtitulos: tuple[str, ...] = ()
    corpo: str = ""
    #: "html" | "markdown" | "texto" | "auto". `auto` decide pela forma do texto.
    formato: str = "auto"
    #: Alegações que o plano promete fazer, uma por item.
    alegacoes: tuple[str, ...] = ()
    #: Valores monetários que o plano já fixou. Entram no documento para que o
    #: formato pt-BR seja conferido no PLANO — corrigir depois de escrito custa
    #: uma rodada inteira de LLM.
    valores_monetarios: tuple[str, ...] = ()
    #: `{"href": ..., "texto": ..., "em_botao": bool}`
    links: tuple[dict[str, Any], ...] = ()
    #: `{"texto": ..., "destino": ...}` — o CTA é link em botão, e é assim que
    #: ele é renderizado, para cair nas mesmas regras de botão.
    ctas: tuple[dict[str, Any], ...] = ()
    #: `{"tipo": "password"|"text"|..., "nome": ...}`
    campos_de_formulario: tuple[dict[str, Any], ...] = ()
    #: `{"razao_social","cnpj","sobre","contato","privacidade"}`
    identidade: dict[str, Any] = field(default_factory=dict)
    disclosures: tuple[str, ...] = ()
    #: As fontes que a pesquisa trouxe. ⚠️ Elas NÃO viram hyperlink no documento:
    #: é justamente o defeito que a espinha v2 proíbe no destino pago. Viajam
    #: para `PaginaObservada.fontes_de_pesquisa`, que é o dossiê de evidência, e
    #: também para `hosts_declarados`, para dar lastro a link que o plano fez.
    fontes_de_pesquisa: tuple[str, ...] = ()
    #: `LP` | `PRESELL` | `SOLUTION` — o papel EDITORIAL do motor.
    papel_do_motor: str = ""
    #: Papel de política pedido pelo chamador. Só sobe o rigor; ver
    #: `portao.papel_do_servidor`.
    papel_pedido: str = ""
    promessa_do_anuncio: str = ""
    cnpj_esperado: str | None = None


# ── normalização de corpo ──────────────────────────────────────────────────

_MD_LINK_RE = re.compile(r"\[([^\]]{0,200})\]\(\s*(<?[^)\s]{1,500}>?)(?:\s+\"[^\"]*\")?\s*\)")
_MD_AUTOLINK_RE = re.compile(r"<((?:https?://|//)[^>\s]{1,500})>")
_MD_TITULO_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.M)
_URL_NUA_RE = re.compile(r"(?<![\"'=>\w])((?:https?://)[^\s<>\"')]{4,500})")
_PARECE_HTML_RE = re.compile(r"(?i)<(p|div|h[1-6]|a|ul|ol|li|section|!--\s*wp:)\b")


def _para_html(texto: str, formato: str) -> str:
    """Normaliza corpo para HTML, sem inventar estrutura que não existe.

    ⚠️ Markdown e URL nua NÃO são detalhe de apresentação aqui.

    O redator devolve Markdown. Um scanner que só enxergasse `<a href>` daria
    verde para `[40%](https://www.caixa.gov.br/)` — que é EXATAMENTE o defeito
    do incidente, escrito na sintaxe em que ele nasce. E uma URL nua no meio do
    texto vira link clicável na maioria dos temas de WordPress, então tratá-la
    como texto seria acreditar numa renderização que não é a que o leitor vê.
    """
    bruto = texto or ""
    if not bruto.strip():
        return ""
    if formato == "html" or (formato == "auto" and _PARECE_HTML_RE.search(bruto)):
        return bruto

    saida = _MD_AUTOLINK_RE.sub(lambda m: f'<a href="{_html.escape(m.group(1))}">{_html.escape(m.group(1))}</a>', bruto)
    saida = _MD_LINK_RE.sub(
        lambda m: '<a href="{}">{}</a>'.format(
            _html.escape(m.group(2).strip("<>")), _html.escape(m.group(1))
        ),
        saida,
    )
    saida = _MD_TITULO_RE.sub(
        lambda m: "<h{n}>{t}</h{n}>".format(n=min(len(m.group(1)), 6), t=_html.escape(m.group(2).strip())),
        saida,
    )
    # URL nua que sobrou (ou seja: não virou href acima) vira link explícito.
    saida = _URL_NUA_RE.sub(
        lambda m: f'<a href="{_html.escape(m.group(1))}">{_html.escape(m.group(1))}</a>', saida
    )
    blocos = [b.strip() for b in re.split(r"\n\s*\n", saida) if b.strip()]
    return "\n".join(b if b.startswith("<") else f"<p>{b}</p>" for b in blocos)


def _tag(nome: str, conteudo: str) -> str:
    return f"<{nome}>{_html.escape(conteudo)}</{nome}>" if conteudo else ""


def documento_do_plano(plano: PlanoDaPagina) -> str:
    """O plano, renderizado como o documento que ele descreve.

    A ordem importa: `<title>`, `<h1>` e subtítulos vêm ANTES do corpo porque é
    nessa ordem que o leitor os encontra, e `varrer_governo` pesa a manchete
    diferente do miolo.
    """
    partes: list[str] = ["<html><head>", _tag("title", plano.titulo), "</head><body>"]
    partes.append(_tag("h1", plano.h1))
    partes += [_tag("h2", s) for s in plano.subtitulos if s]
    partes.append(_para_html(plano.corpo, plano.formato))
    partes += [f"<p>{_html.escape(a)}</p>" for a in plano.alegacoes if a]
    if plano.valores_monetarios:
        partes.append(
            "<p>" + " ".join(_html.escape(v) for v in plano.valores_monetarios if v) + "</p>"
        )
    for link in plano.links:
        href = _html.escape(str(link.get("href") or ""))
        texto = _html.escape(str(link.get("texto") or ""))
        if not href:
            continue
        if link.get("em_botao"):
            partes.append(f'<div class="wp-block-button"><a class="wp-block-button__link" href="{href}">{texto}</a></div>')
        else:
            partes.append(f'<p><a href="{href}">{texto}</a></p>')
    for cta in plano.ctas:
        destino = _html.escape(str(cta.get("destino") or ""))
        texto = _html.escape(str(cta.get("texto") or ""))
        # CTA é sempre botão: é o clique que a página EMPURRA, e a política
        # trata isso de forma diferente de uma citação em prosa.
        partes.append(
            f'<div class="wp-block-button"><a class="wp-block-button__link" href="{destino}">{texto}</a></div>'
        )
    if plano.campos_de_formulario:
        campos = "".join(
            '<input type="{t}" name="{n}">'.format(
                t=_html.escape(str(c.get("tipo") or "text")),
                n=_html.escape(str(c.get("nome") or "")),
            )
            for c in plano.campos_de_formulario
        )
        partes.append(f"<form>{campos}</form>")
    partes += [f"<p>{_html.escape(d)}</p>" for d in plano.disclosures if d]

    ident = plano.identidade or {}
    rodape = " ".join(
        _html.escape(str(ident.get(k) or ""))
        for k in ("razao_social", "cnpj")
        if ident.get(k)
    )
    if rodape:
        partes.append(f"<p>{rodape}</p>")
    for rotulo, chave in (("Sobre", "sobre"), ("Contato", "contato"),
                          ("Política de Privacidade", "privacidade")):
        alvo = str(ident.get(chave) or "")
        if alvo:
            partes.append(f'<a href="{_html.escape(alvo)}">{rotulo}</a>')
    partes.append("</body></html>")
    return "".join(p for p in partes if p)


def pagina_do_plano(plano: PlanoDaPagina, *, base_do_site: str = "") -> PaginaObservada:
    """O plano como `PaginaObservada`, pronto para as dez varreduras.

    ⚠️ `sha256_observado` fica `None` de propósito: nada está no ar ainda. É o
    que faz `live_drift` e `approval_receipt` responderem `not_applicable` em
    vez de reprovarem toda página primeira por uma impossibilidade estrutural.
    """
    rota = (plano.rota or "").strip()
    url = urljoin(base_do_site or "", rota) if base_do_site else rota
    ident = plano.identidade or {}
    return PaginaObservada(
        url=url,
        html=documento_do_plano(plano),
        origem="generation_plan",
        cnpj_esperado=plano.cnpj_esperado or (str(ident.get("cnpj")) if ident.get("cnpj") else None),
        promessa_do_anuncio=plano.promessa_do_anuncio,
        fontes_de_pesquisa=tuple(plano.fontes_de_pesquisa),
        # ⚠️ HOST, não URL. `classificar_host` compara host com host; passar a
        # URL inteira fazia `fonte_declarada` ser inalcançável pelo caminho do
        # plano — toda fonte de pesquisa caía em `terceiro_desconhecido`.
        hosts_declarados=tuple(
            sorted({h for h in (urlparse(f).netloc.lower().split("@")[-1].split(":")[0]
                                for f in plano.fontes_de_pesquisa if f) if h})
        ),
        papel_declarado=plano.papel_pedido or plano.papel_do_motor,
    )


def avaliar_plano(
    plano: PlanoDaPagina,
    *,
    base_do_site: str = "",
    e_destino_de_campanha: bool = False,
    fontes: dict[str, Any] | None = None,
) -> tuple[Avaliacao, PapelDestino]:
    """O portão 1: avalia o PLANO e devolve o veredito e o papel que valeu.

    O papel sai de `papel_do_servidor`, nunca do campo que o chamador mandou —
    e a presença de campo de formulário no plano já sobe o regime para
    `conversion_page` sem ninguém precisar declarar nada.
    """
    papel = papel_do_servidor(
        e_destino_de_campanha=e_destino_de_campanha,
        coleta_dado_do_visitante=bool(plano.campos_de_formulario),
        papel_do_motor=plano.papel_do_motor,
        papel_pedido_pelo_cliente=plano.papel_pedido,
    )
    pagina = pagina_do_plano(plano, base_do_site=base_do_site)
    return avaliar(pagina, papel, PontoDePortao.ARTEFATO_DE_GERACAO, fontes=fontes), papel
