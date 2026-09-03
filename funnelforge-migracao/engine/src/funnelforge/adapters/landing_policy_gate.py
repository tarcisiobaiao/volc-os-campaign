# funnel-forge/src/funnelforge/adapters/landing_policy_gate.py
"""A PONTE para `app.landing_policy` — e ela falha FECHADA.

## Por que uma ponte, e não uma cópia da regra

O contrato do destino pago mora em `backend/app/landing_policy/`. Ele é PURO
(só stdlib), mas está fora do venv do motor. Reimplementar aqui as dez
varreduras seria criar uma segunda autoridade sobre o mesmo fato: no primeiro
mês elas divergem, e aí o motor aprova o que o portão do backend reprova — ou o
contrário —, e quem lê o recibo não tem como saber qual das duas estava certa.

Então este módulo faz UMA coisa: acha o pacote e o importa. É o inverso exato de
`backend/app/redator/worker.raiz_do_motor()`, que sobe da raiz do backend até o
motor; aqui sobe-se da raiz do motor até o backend.

## Falha FECHADA, e o motivo de isso não ser rigor decorativo

Se o import não funcionar — pasta renomeada, venv reconstruído, motor copiado
para outra máquina sem o backend —, publicar um `paid_destination` é RECUSADO.
Nunca "não consegui olhar, então passou".

O caminho contrário é o que o handoff anterior deixaria acontecer: um `try/except
ImportError: pass` no topo de um adaptador é a forma mais barata de desligar um
portão inteiro sem que nada no log mude de cor. Aqui a indisponibilidade vira uma
`Issue` com código próprio (`portao_de_destino_indisponivel`), que reprova o
passo como qualquer outro defeito.

## O que este módulo NÃO afirma

Ele não afirma que a página no ar está correta: o portão lê o ARTEFATO que o
motor produziu, não o HTML que o tema do WordPress renderiza em volta dele. Ver
`_identidade_declarada` para o único ponto em que uma declaração entra, e por
que ela é rastreável a uma medição.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

from funnelforge.domain.models import Issue

#: Chave sob a qual o recibo entra em `state.published[n]`. Espelha
#: `app.landing_policy.CHAVE_DO_RECIBO`, mas é declarada aqui para que o motor
#: possa citá-la sem forçar o import (que pode falhar) só para ler uma string.
CHAVE_DO_RECIBO = "landing_policy_receipt"
JANELA_DE_FRESCOR_PADRAO_S = 86400

#: Código da issue que representa "o portão não pôde ser consultado". É terminal
#: em `retry_policy`: reescrever o texto não conserta um import quebrado.
CODIGO_INDISPONIVEL = "portao_de_destino_indisponivel"


class PortaoIndisponivel(RuntimeError):
    """O contrato do destino pago não pôde ser importado.

    Levantada, e não engolida, porque ela é a diferença entre "avaliei e está
    limpo" e "não consegui avaliar" — que é o assunto inteiro deste contrato.
    """


def raiz_do_backend() -> Path:
    """Onde `app.landing_policy` mora, a partir DESTE arquivo.

    `src/funnelforge/adapters/landing_policy_gate.py` -> sobe 5 níveis
    (adapters, funnelforge, src, engine, funnelforge-migracao) até a raiz do
    repositório, e de lá entra em `backend`.
    """
    return Path(__file__).resolve().parents[5] / "backend"


def _importar_contrato() -> ModuleType:
    """O import cru. É o ÚNICO ponto que teste monkeypatcha para provar a
    falha fechada — por isso ele não trata exceção nenhuma."""
    raiz = str(raiz_do_backend())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import app.landing_policy as contrato  # noqa: PLC0415 - import tardio de propósito

    return contrato


def contrato() -> ModuleType:
    """O pacote de política, ou `PortaoIndisponivel` com o caminho procurado.

    Sem cache próprio: `sys.modules` já faz esse trabalho depois do primeiro
    import, e um cache local aqui esconderia do teste o único seam que prova a
    falha fechada.
    """
    try:
        return _importar_contrato()
    except Exception as exc:  # noqa: BLE001 - qualquer falha de import fecha o portão
        raise PortaoIndisponivel(
            f"O contrato do destino pago não pôde ser importado de "
            f"{raiz_do_backend()}: {type(exc).__name__}: {exc}. Publicar um "
            f"destino pago sem portão é o que esta espinha existe para impedir."
        ) from exc


# ── o artefato da LP como PLANO avaliável ─────────────────────────────────

_CAMPO_DE_FORMULARIO_RE = re.compile(r"(?i)<(input|textarea|select)\b")


def _campos_de_formulario(*blobs: str) -> tuple[dict[str, str], ...]:
    """Campos de formulário APURADOS do artefato, nunca declarados.

    É este fato — e não um campo do chamador — que sobe o papel para
    `conversion_page` em `papel_do_servidor`. Uma LP que passa a coletar dado do
    visitante muda de regime sozinha, sem ninguém lembrar de reconfigurar nada.

    O tipo/nome não são extraídos: para a decisão de papel basta EXISTIR campo, e
    inventar um `tipo` que não foi lido seria evidência fabricada.
    """
    achados: list[dict[str, str]] = []
    for blob in blobs:
        for m in _CAMPO_DE_FORMULARIO_RE.finditer(blob or ""):
            achados.append({"tipo": "desconhecido", "nome": m.group(1).lower()})
    return tuple(achados)


def _identidade_declarada(settings: Any) -> tuple[dict[str, Any], tuple[str, ...]]:
    """A identidade e as divulgações que o TEMA do WordPress renderiza.

    ⚠️ Isto é DECLARAÇÃO, não observação — e o motor não tem como conferi-la no
    artefato, porque o artefato é só o corpo; o rodapé institucional vem do tema.

    A declaração não é chute: na captura preservada de
    `/r/fgts-saque-aniversario/` (a LP deste motor, neste tema), os bloqueios
    registrados em `GATE-RECEIPTS.json` NÃO incluem `IDENTIDADE_OPERADOR_AUSENTE`,
    `IDENTIDADE_CONTATO_AUSENTE`, `AVISO_NAO_OFICIAL_AUSENTE` nem
    `DIVULGACAO_DE_MONETIZACAO_AUSENTE` — o rodapé existe e foi medido. É por
    isso que ela vive em `site.rodape_institucional` (o texto verbatim daquela
    medição) em vez de numa constante escondida: outro site precisa declarar o
    dele, e VAZIO é fail-closed (sem rodapé declarado, o portão reprova por
    identidade ausente, que é a verdade para quem não mediu nada).

    Quem confere de verdade é o portão 3, sobre o HTML ao vivo. Aqui a
    declaração só evita que o portão 1 reprove toda LP por um fato que ele
    estruturalmente não enxerga.
    """
    cnpj = str(getattr(settings.site, "cnpj", "") or "").strip()
    rodape = str(getattr(settings.site, "rodape_institucional", "") or "").strip()
    identidade: dict[str, Any] = {"cnpj": cnpj} if cnpj else {}
    return identidade, ((rodape,) if rodape else ())


def _corpo_do_artefato(conteudo: dict) -> tuple[str, tuple[str, ...]]:
    """O corpo e os subtítulos da LP, na ordem em que o leitor os encontra.

    O template Elementor (`lp_template._SLOT_MAP`) põe herói, título do artigo,
    intro, as quatro seções, o FAQ e a transição nesta ordem — o documento
    canônico do plano precisa refletir a MESMA ordem, porque a varredura de
    governo pesa a manchete diferente do miolo.
    """
    partes: list[str] = []
    subtitulos: list[str] = []

    intro = str(conteudo.get("intro") or "")
    if intro:
        partes.append(intro)
    for secao in conteudo.get("sections") or []:
        if not isinstance(secao, dict):
            continue
        titulo = str(secao.get("title") or "")
        if titulo:
            subtitulos.append(titulo)
        corpo = str(secao.get("body") or "")
        if corpo:
            partes.append(corpo)
    faq_titulo = str(conteudo.get("faq_title") or "")
    if faq_titulo:
        subtitulos.append(faq_titulo)
    for item in conteudo.get("faq") or []:
        if not isinstance(item, dict):
            continue
        pergunta = str(item.get("q") or "")
        resposta = str(item.get("a") or "")
        if pergunta or resposta:
            partes.append(f"<p><strong>{pergunta}</strong> {resposta}</p>")
    transicao = str(conteudo.get("transition") or "")
    if transicao:
        partes.append(transicao)
    subtitulo_do_heroi = str(conteudo.get("hero_subtitle") or "")
    if subtitulo_do_heroi:
        subtitulos.insert(0, subtitulo_do_heroi)
    return "\n".join(partes), tuple(subtitulos)


def plano_da_landing_page(
    *,
    conteudo: dict,
    settings: Any,
    slug: str,
    papel_do_motor: str,
    hrefs: Sequence[str] = (),
    fontes_de_pesquisa: Sequence[str] = (),
    elementor_bruto: str = "",
) -> Any:
    """O artefato da LP como `PlanoDaPagina`, pronto para as dez varreduras.

    A LP é JSON estruturado + template Elementor: título, H1, CTA e destino
    chegam como CAMPOS, não como corpo. Um portão que recebesse só o corpo não
    teria como reprovar o que não está no corpo — foi assim que a alegação do
    incidente entrou pelo H1.

    `cta_texts[i]` casa com `hrefs[i]` porque é essa a correspondência que
    `lp_template._SLOT_MAP`/`_BUTTON_HREF` realizam: os seis widgets de botão
    são dois heróis repetindo os MESMOS três destinos.
    """
    api = contrato()
    corpo, subtitulos = _corpo_do_artefato(conteudo)
    identidade, disclosures = _identidade_declarada(settings)
    textos = [str(t) for t in (conteudo.get("cta_texts") or [])]
    ctas = tuple(
        {"texto": texto, "destino": (hrefs[i] if i < len(hrefs) else "")}
        for i, texto in enumerate(textos)
    )
    post_type = str(getattr(settings.site, "lp_post_type", "") or "pages")
    return api.PlanoDaPagina(
        rota=f"/{post_type}/{slug}",
        titulo=str(conteudo.get("article_title") or ""),
        # O ÚNICO h1 da página é o `hero_title` (o herói desktop repete o texto
        # com `hide_*`, mas sem a tag h1 — ver `lp_template._SLOT_MAP`).
        h1=str(conteudo.get("hero_title") or ""),
        subtitulos=subtitulos,
        corpo=corpo,
        formato="html",
        ctas=ctas,
        campos_de_formulario=_campos_de_formulario(
            json.dumps(conteudo, ensure_ascii=False), elementor_bruto),
        identidade=identidade,
        disclosures=disclosures,
        fontes_de_pesquisa=tuple(fontes_de_pesquisa),
        papel_do_motor=papel_do_motor,
    )


# ── o resultado, na moeda do motor ────────────────────────────────────────


@dataclass(frozen=True)
class ResultadoDoPortao:
    """O veredito do portão traduzido para o vocabulário do pipeline."""

    pronto: bool
    issues: list[Issue] = field(default_factory=list)
    #: Sempre presente quando o portão RODOU. `None` só quando ele não pôde ser
    #: consultado — e aí `issues` carrega `portao_de_destino_indisponivel`.
    recibo: dict[str, Any] | None = None
    #: O documento canônico avaliado. É dele que saem hash e impressão.
    documento: str = ""


def _issues(avaliacao: Any) -> list[Issue]:
    """Bloqueios E desconhecidos viram issue; o predicado é
    `paid_destination_ready`, nunca `if avaliacao.bloqueios`.

    ⚠️ Testar só bloqueios ignora DESCONHECIDO — verificação exigida que não pôde
    ser concluída. Era assim que o handoff anterior deixaria publicar uma página
    cuja varredura falhou: zero bloqueios, zero evidência, verde.
    """
    if avaliacao.paid_destination_ready:
        return []
    saida = [
        Issue(code=achado.codigo.lower(),
              message=f"{achado.mensagem} (evidência: {achado.evidencia})")
        for achado in avaliacao.bloqueios
    ]
    saida += [
        Issue(code="verificacao_inconclusiva",
              message=f"{d['verificacao']} terminou como {d['status']}: {d['motivo']}")
        for d in avaliacao.desconhecidos
    ]
    if not saida:
        # Não pronto SEM bloqueio e SEM desconhecido só acontece quando o papel
        # avaliado não é estrito. Devolver lista vazia aqui transformaria
        # "não medido como destino pago" em "aprovado".
        saida = [Issue(code="destino_pago_nao_pronto",
                       message="; ".join(avaliacao.motivos) or
                               "o portão não declarou o destino pronto")]
    return saida


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def avaliar_plano_de_destino(
    plano: Any,
    *,
    settings: Any,
    e_destino_de_campanha: bool,
    papel_declarado: str = "",
    carimbo_epoch: float | None = None,
    carimbo: str | None = None,
) -> ResultadoDoPortao:
    """Roda o portão no ponto ARTEFATO_DE_GERAÇÃO e devolve veredito + recibo.

    O recibo é emitido nos DOIS desfechos. Uma recusa sem recibo é
    indistinguível de uma publicação que ninguém tentou, e é justamente a recusa
    que alguém vai querer explicar seis semanas depois.
    """
    api = contrato()
    avaliacao, _papel = api.avaliar_plano(
        plano,
        base_do_site=str(getattr(settings.site, "domain", "") or ""),
        e_destino_de_campanha=e_destino_de_campanha,
    )
    documento = api.documento_do_plano(plano)
    extras: dict[str, Any] = {}
    if carimbo is not None:
        extras["carimbo"] = carimbo
    recibo = api.emitir_recibo(
        avaliacao,
        hash_do_conteudo=_sha256(documento),
        impressao_do_conteudo=api.impressao_canonica(documento),
        carimbo_epoch=carimbo_epoch,
        janela_de_frescor_s=api.JANELA_DE_FRESCOR_PADRAO_S,
        papel_declarado=papel_declarado,
        **extras,
    )
    return ResultadoDoPortao(
        pronto=avaliacao.paid_destination_ready,
        issues=_issues(avaliacao),
        recibo=recibo,
        documento=documento,
    )


def indisponivel(exc: PortaoIndisponivel) -> ResultadoDoPortao:
    """O resultado de um portão que não pôde ser consultado: VERMELHO."""
    return ResultadoDoPortao(
        pronto=False,
        issues=[Issue(code=CODIGO_INDISPONIVEL, message=str(exc))],
        recibo=None,
    )


def anexar_recibo(publicada: dict[str, Any], recibo: dict[str, Any]) -> dict[str, Any]:
    """Delega ao contrato — quem é dono da chave é ele, não o motor."""
    return contrato().anexar_recibo(publicada, recibo)


def gravar_recibo_de_recusa(run_dir: Path, page_number: int,
                            recibo: dict[str, Any]) -> Path:
    """Grava o recibo da RECUSA na pasta do run, atomicamente (via contrato)."""
    api = contrato()
    destino = Path(run_dir) / api.nome_do_recibo(page_number, recusado=True)
    return api.gravar_recibo_local(destino, recibo)


# ── o PLANO, antes de a primeira palavra ser paga ─────────────────────────

#: Códigos que só se medem com CORPO escrito. Excluí-los da checagem de PLANO
#: não é abrir exceção: é não acusar por uma ausência que a etapa seguinte
#: existe justamente para preencher — um plano não tem 600 palavras porque
#: ninguém escreveu nada ainda. Os dois voltam a ser medidos no portão sobre o
#: ARTEFATO (`step_content_gate`), aí sim com corpo.
SO_MEDIVEIS_COM_CORPO = frozenset({
    "CONTEUDO_ORIGINAL_INSUFICIENTE",
    "PAGINA_PONTE",
})


class _SiteDeclarado:
    """Adaptador mínimo de `ctx` para o que `_identidade_declarada` lê.

    Existe para que a checagem de plano e a do artefato compartilhem a MESMA
    função de declaração de identidade. Duas leituras do mesmo campo divergem, e
    aí o plano aprova o que o artefato reprova por identidade.
    """

    def __init__(self, ctx: dict[str, Any]) -> None:
        self.site = self
        self.cnpj = str(ctx.get("cnpj") or "")
        self.rodape_institucional = str(ctx.get("rodape_institucional") or "")


def _ctas_do_plano(ctx: dict[str, Any]) -> tuple[dict[str, str], ...]:
    """Os CTAs como o PLANO os conhece: âncora da rota + destino resolvido.

    No plano o rótulo do botão é `Route.anchor` (determinístico, montado por
    `routing.build_funnel_routes` a partir do H1 do destino). O texto que o
    leitor vai ler na LP é `cta_texts`, que o modelo ainda nem escreveu — por
    isso o portão sobre o ARTEFATO mede aquele, e este mede este.
    """
    from funnelforge.domain.models import Route, resolve_route  # noqa: PLC0415

    parsed = ctx.get("parsed") or {}
    brutas = (parsed.get("routes") if isinstance(parsed, dict) else None) or []
    dominio = str(ctx.get("domain") or "")
    post_type = str(ctx.get("post_type") or "")
    ctas: list[dict[str, str]] = []
    for bruta in brutas:
        rota = bruta if isinstance(bruta, Route) else Route(**bruta)
        if rota.kind not in ("funnel", "cross_funnel"):
            continue
        try:
            destino = resolve_route(rota, domain=dominio, post_type=post_type)
        except ValueError:
            # Rota que não resolve é defeito de grafo, e o `pagespec` já o
            # reprova com o código certo. Aqui ela entra sem destino em vez de
            # derrubar a checagem inteira de política.
            destino = ""
        ctas.append({"texto": rota.anchor, "destino": destino})
    return tuple(ctas)


def reprovas_do_plano(ctx: dict[str, Any]) -> list[Issue]:
    """O portão 1 no PLANO — de graça, antes de qualquer chamada paga.

    A alegação do incidente entrou pelo H1 do PLANO ("Saque-Aniversário FGTS
    Liberado pelo Governo"), e o portão de conteúdo só olhava o CORPO: ele
    chegava depois do ponto em que o defeito nasceu, e depois de pagar pesquisa
    + até três redações + juiz.

    Sem `ctx["h1"]` a checagem não roda: um ctx montado à mão em teste, ou um
    checkpoint antigo, não carrega os campos do plano — e inventar um plano
    vazio para avaliar produziria reprova por ausência de tudo, que é ruído, não
    achado.
    """
    h1 = str(ctx.get("h1") or "").strip()
    if not h1:
        return []
    try:
        api = contrato()
    except PortaoIndisponivel as exc:
        return indisponivel(exc).issues

    papel = ctx.get("role")
    papel_do_motor = getattr(papel, "value", str(papel or ""))
    settings_site = _SiteDeclarado(ctx)
    identidade, disclosures = _identidade_declarada(settings_site)
    e_destino_de_campanha = str(ctx.get("page_type") or "") == "LANDING PAGE"
    plano = api.PlanoDaPagina(
        rota=f"/{ctx.get('lp_post_type') or 'pages'}/{ctx.get('slug') or ''}",
        titulo=h1,
        h1=h1,
        subtitulos=tuple(str(s) for s in (ctx.get("subtitulos") or []) if str(s).strip()),
        formato="html",
        ctas=_ctas_do_plano(ctx),
        identidade=identidade,
        disclosures=disclosures,
        fontes_de_pesquisa=tuple(ctx.get("official_links") or []),
        papel_do_motor=papel_do_motor,
    )
    avaliacao, _papel = api.avaliar_plano(
        plano,
        base_do_site=str(ctx.get("domain") or ""),
        e_destino_de_campanha=e_destino_de_campanha,
    )
    return [
        Issue(code=achado.codigo.lower(),
              message=f"{achado.mensagem} (no PLANO — evidência: {achado.evidencia})")
        for achado in avaliacao.bloqueios
        if achado.codigo not in SO_MEDIVEIS_COM_CORPO
    ]
