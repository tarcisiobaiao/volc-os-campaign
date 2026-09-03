"""A BARREIRA 2 no lado do backend — as duas portas que levam ao WordPress.

## Por que este módulo existe, e por que ele não decide política nenhuma

Quem decide é `app.landing_policy`. Aqui mora só a TRADUÇÃO entre o que o
backend tem na mão (a linha do run, o `state.json` do motor, o card do Pautador)
e o que o contrato do portão pede (`PaginaObservada`/`PlanoDaPagina`, o papel
apurado pelo servidor, o ponto de portão). Nenhuma regra nova, nenhum código de
achado novo: se uma tradução daqui precisasse inventar severidade, ela estaria
no lugar errado.

## As DUAS portas, e por que elas não podem compartilhar o mesmo portão

    A) POST /redator/disparar          → roda o funil INTEIRO e publica
    B) POST /redator/runs/{id}/publicar/{page} → publica UMA página já escrita

Elas chegam ao mesmo lugar (o motor, com `--publish`), mas com evidências
diferentes na mão:

* na porta **B** existe artefato: o rascunho está no disco, e o portão lê o HTML
  que vai virar post. É o ponto `PRE_PUBLICACAO_WORDPRESS`, com todas as seis
  verificações exigidas;
* na porta **A** o funil ainda não foi escrito. O que existe é o PLANO do card —
  H1, slug, estrutura de H2. É o ponto `ARTEFATO_DE_GERACAO`, e ele responde uma
  pergunta menor, descrita em `bloqueios_decidiveis_no_plano`.

## O que este módulo NÃO cobre, e quem cobre

A escrita real acontece DENTRO do subprocesso do motor. Um `funnelforge run ...
--publish` digitado num terminal não passa por aqui — e é por isso que o portão
dentro do motor não é opcional. O que estas funções garantem é que as DUAS
portas do backend recusam antes de gastar o subprocesso, e que a recusa deixa
recibo.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.landing_policy import (
    JANELA_DE_FRESCOR_PADRAO_S,
    Avaliacao,
    PaginaObservada,
    PapelDestino,
    PlanoDaPagina,
    PontoDePortao,
    Veredito,
    avaliar,
    avaliar_plano,
    documento_do_plano,
    emitir_recibo,
    impressao_canonica,
    papel_do_servidor,
)


def papel_e_estrito(papel: PapelDestino) -> bool:
    """Este papel carrega a régua do clique comprado?

    ⚠️ Perguntado AO CONTRATO, e não recopiado daqui. Uma avaliação sem achado
    nenhum só responde `paid_destination_ready` quando o papel é estrito — então
    a pergunta é feita com uma avaliação vazia, e a resposta é a do contrato.

    Uma cópia local da lista de papéis estritos ficaria velha na direção
    PERMISSIVA no dia em que o contrato ganhasse um papel estrito novo: o papel
    novo seria tratado como frouxo aqui, e uma página que deveria subir de régua
    passaria. Cópia que erra para o lado do "pode publicar" é a pior espécie.
    """
    vazia = Avaliacao(
        url="", papel=papel, ponto=PontoDePortao.PRE_PUBLICACAO_WORDPRESS,
        veredito=Veredito.APROVADO,
    )
    return vazia.paid_destination_ready


# ── o papel EDITORIAL que o motor conhece ──────────────────────────────────
#
# `funnelforge.domain.models.PageRole` tem exatamente três valores. Qualquer
# outra coisa gravada no lugar não é um papel novo: é um campo corrompido, ou
# alguém escrevendo no `state.json`/no card.
#
# ⚠️ E aqui mora uma armadilha medida no contrato: `papel_do_servidor` traduz
# papel do motor DESCONHECIDO para `organic_article` — o papel MAIS FROUXO. Ou
# seja, gravar `role: "artigo"` na página 1 rebaixaria a régua da LP sem erro
# nenhum. Por isso a tradução aqui é fechada: fora dos três, o papel volta a ser
# derivado do SLUG, que é a mesma regra que o motor usa para montar a rota.
_PAPEIS_DO_MOTOR = ("LP", "PRESELL", "SOLUTION")

# A regra do motor, copiada de `funnelforge/domain/models.py::derive_role`:
# `-pr` → PRESELL, `-p<N>` → SOLUTION, o resto é LP. Copiada e não importada
# porque o motor roda em outro venv, como outro processo — importar dele aqui
# acoplaria a API ao ambiente do motor por três linhas de regex.
_SLUG_PRESELL_RE = re.compile(r"-pr\d*$")
_SLUG_SOLUTION_RE = re.compile(r"-p\d+$")

# Basta UM destes para a página coletar dado do visitante, e aí o papel sobe
# para `conversion_page` — o regime mais duro do contrato. É detecção do
# ARTEFATO, não campo declarado: a única direção em que um falso positivo pode
# errar é subindo o rigor, e essa é a direção segura.
_COLETA_RE = re.compile(r"(?is)<\s*(form|input|textarea|select)\b")


def papel_do_motor_no_disco(pagina_do_plano: Dict[str, Any]) -> str:
    """O papel editorial daquela página, apurado do artefato do motor.

    Prefere o campo `role` do plano, mas só quando ele é um dos três papéis que
    o motor sabe escrever. Fora disso, decide pelo SLUG — nunca devolve string
    desconhecida, porque string desconhecida vira o papel mais frouxo lá na
    frente e é assim que um portão se desliga por digitação.
    """
    bruto = str(pagina_do_plano.get("role") or "").strip().upper()
    if bruto in _PAPEIS_DO_MOTOR:
        return bruto
    slug = str(pagina_do_plano.get("slug") or "").strip().rstrip("/")
    if _SLUG_PRESELL_RE.search(slug):
        return "PRESELL"
    if _SLUG_SOLUTION_RE.search(slug):
        return "SOLUTION"
    return "LP"


def coleta_dado_do_visitante(html: str) -> bool:
    """A página pede dado do visitante? Lido do HTML, não do cadastro."""
    return bool(_COLETA_RE.search(html or ""))


def pagina_do_plano_no_estado(
    estado: Dict[str, Any], page_number: int
) -> Dict[str, Any]:
    """A entrada de `state.plan.pages` daquela página, ou `{}`."""
    for p in ((estado or {}).get("plan") or {}).get("pages") or []:
        try:
            if int((p or {}).get("page_number") or 0) == int(page_number):
                return p or {}
        except (TypeError, ValueError):
            continue
    return {}


def url_da_pagina(perfil_wp: Optional[Dict[str, Any]], pagina_do_plano: Dict[str, Any],
                  papel_do_motor: str) -> str:
    """A URL que aquela página terá no WordPress.

    ⚠️ O `HANDOFF-PATCH-PUBLICACAO.md` montava `{wp_base_url}/r/{slug}/`. A
    coluna chama `wp_url` (`wp_base_url` não existe em `project_wordpress`, e
    `.get` devolveria `""` em silêncio) e o post type da LP é configurável por
    projeto — `lp_post_type`, default `r`; as interiores usam `post_type`,
    default `rec`. Montar `/r/` para todas produziria uma URL que não é a da
    página, e é a URL que o recibo grava como identidade do que foi avaliado.
    """
    base = str((perfil_wp or {}).get("wp_url") or "").rstrip("/")
    if papel_do_motor == "LP":
        tipo = str((perfil_wp or {}).get("lp_post_type") or "r").strip("/")
    else:
        tipo = str((perfil_wp or {}).get("post_type") or "rec").strip("/")
    slug = str(pagina_do_plano.get("slug") or "").strip("/")
    if not base:
        # Sem base não se inventa host: o caminho relativo é a verdade do que se
        # sabe. Uma URL fabricada entraria no recibo como se fosse observação.
        return f"/{tipo}/{slug}/" if slug else ""
    return f"{base}/{tipo}/{slug}/" if slug else f"{base}/"


def avaliar_rascunho(
    *,
    html: str,
    url: str,
    papel_do_motor: str,
    cnpj_esperado: Optional[str] = None,
    promessa_do_anuncio: str = "",
    e_destino_de_campanha: bool = False,
    papel_pedido_pelo_cliente: str = "",
) -> Tuple[Avaliacao, PapelDestino]:
    """O portão 2: o rascunho que vai virar post, avaliado antes de virar.

    O papel sai de `papel_do_servidor` — nunca de um campo do payload. Levanta
    `PapelRelaxadoPeloCliente` quando alguém pede régua mais frouxa; quem chama
    traduz isso em recusa, e não em papel aceito.
    """
    papel = papel_do_servidor(
        e_destino_de_campanha=e_destino_de_campanha,
        coleta_dado_do_visitante=coleta_dado_do_visitante(html),
        papel_do_motor=papel_do_motor,
        papel_pedido_pelo_cliente=papel_pedido_pelo_cliente,
    )
    pagina = PaginaObservada(
        url=url,
        html=html or "",
        cnpj_esperado=cnpj_esperado or None,
        promessa_do_anuncio=promessa_do_anuncio,
        # `pre_publication_draft`: o artefato é o rascunho no disco do servidor,
        # não a página no ar. Chamar isto de observação ao vivo seria dizer que
        # alguém leu o que o público vê.
        origem="pre_publication_draft",
        papel_declarado=str(papel_do_motor or ""),
    )
    return avaliar(pagina, papel, PontoDePortao.PRE_PUBLICACAO_WORDPRESS), papel


def recibo_do_conteudo(
    avaliacao: Avaliacao, html: str, *, papel_declarado: str = ""
) -> Dict[str, Any]:
    """O recibo daquela passagem, com hash E impressão canônica.

    As duas coisas viajam porque respondem a perguntas diferentes: o sha256 é a
    prova de igualdade byte a byte, e a impressão é a projeção estrutural que
    decide DERIVA — um tema que muda um espaço em branco altera o byte e não
    altera a página. Sem a impressão, o portão 3 chamaria de deriva o que é
    ruído de renderização.
    """
    conteudo = html or ""
    agora = datetime.now(timezone.utc)
    return emitir_recibo(
        avaliacao,
        hash_do_conteudo=hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
        carimbo=agora.isoformat(),
        impressao_do_conteudo=impressao_canonica(conteudo),
        # O carimbo COMPARÁVEL. Sem ele o recibo não é datável, e frescor sem
        # aritmética é frescor que ninguém consegue conferir.
        carimbo_epoch=time.time(),
        janela_de_frescor_s=JANELA_DE_FRESCOR_PADRAO_S,
        papel_declarado=papel_declarado,
    )


# ── porta A: o PLANO, antes de existir corpo ───────────────────────────────
#
# ⚠️ POR QUE ESTE PORTÃO NÃO PODE EXIGIR `paid_destination_ready`
#
# Medido nesta branch, avaliando o plano de uma LP típica do card (H1, slug,
# lista de H2 — o que o card tem no instante do disparo):
#
#     CONTEUDO_ORIGINAL_INSUFICIENTE      (15 palavras visíveis, piso 600)
#     IDENTIDADE_OPERADOR_AUSENTE
#     IDENTIDADE_CONTATO_AUSENTE
#     DIVULGACAO_DE_MONETIZACAO_AUSENTE
#     ALEGACAO_FINANCEIRA_SEM_DIVULGACAO
#     AVISO_NAO_OFICIAL_AUSENTE
#     AFILIACAO_GOVERNAMENTAL_IMPLICITA
#
# Todos são achados de AUSÊNCIA, e nenhum deles distingue "o plano está errado"
# de "o corpo ainda não foi escrito" — que é exatamente o que o disparo vai
# fazer a seguir. Reprovar por eles aqui pararia 100% dos disparos e ensinaria a
# operação a contornar o portão, que é como um portão morre.
#
# O que o plano JÁ DECIDE são os achados de COMISSÃO: os que citam texto que
# alguém escreveu no card e que nenhuma redação posterior desfaz. O H1 do
# incidente — "Saque-Aniversário FGTS Liberado pelo Governo" — é desta família,
# e é a prova de que o defeito nasce no plano: ver
# `backend/tests/test_landing_policy_regressao_fgts.py`.
#
# ⚠️ Esta lista é uma decisão DESTE portão, não do contrato. O contrato não tem
# (ainda) o conceito "achado decidível num documento incompleto"; enquanto não
# tiver, a lista mora aqui, explícita, e cada entrada diz que texto do plano ela
# aponta. Um código novo NÃO entra por omissão: ele fica de fora deste portão e
# é decidido no portão 2, contra o artefato inteiro.
CODIGOS_DECIDIVEIS_NO_PLANO = frozenset({
    # A manchete que diz que o governo liberou algo. O aviso de não-vínculo no
    # rodapé não desfaz o que o leitor lê primeiro — e é a linha literal do
    # artefato do funil FGTS.
    "TITULO_SUGERE_ORIGEM_OFICIAL",
    # "Liberado", "garantido", "aprovado na hora": promessa de resultado que o
    # plano já fixou, e que o redator vai desenvolver, não desfazer.
    "ALEGACAO_DE_RESULTADO_IMPROVAVEL",
    # Um link do plano com âncora de valor ("R$ 2.900") apontando para órgão
    # público. Sete deles foram ao ar na URL que a conta suspensa anunciava.
    "LINK_GOVERNO_COM_ANCORA_DE_VALOR",
    # Marca de governo no texto e destino que não é do governo.
    "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE",
    # Serviço público restrito oferecido pela página.
    "SERVICO_GOVERNAMENTAL_RESTRITO",
    # Marca de terceiro sem lastro na pesquisa daquela página.
    "MARCA_TERCEIRA_SEM_LASTRO",
    # Botão do plano levando a terceiro não autorizado.
    "BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO",
    # Âncora que promete um assunto e leva a outro — a divergência
    # anúncio↔destino no menor tamanho possível, e ela já está no plano.
    "ANCORA_INCONGRUENTE_COM_DESTINO",
    # "2900.00 R$" — vazamento de máquina apresentado como cifra.
    "VALOR_MONETARIO_MALFORMADO",
    # A promessa do anúncio e o destino discordam. Só entra quando alguém
    # informou a promessa; sem ela a varredura não emite o código.
    "DESTINO_INCONGRUENTE_COM_ANUNCIO",
})


def plano_da_pagina_do_card(
    pagina_do_card: Dict[str, Any], *, papel_do_motor: str,
    cnpj_esperado: Optional[str] = None,
) -> PlanoDaPagina:
    """A página do `funnel_architecture` como `PlanoDaPagina`.

    ⚠️ `role`/`papel` do card entra como `papel_pedido`, NÃO como papel.
    `funnel_architecture` é dado gravável pela API (ver
    `routers/entities.py`), então tratá-lo como papel deixaria o rigor do portão
    à escolha de quem escreve o card. Como `papel_pedido`, ele só consegue SUBIR
    a régua; pedir régua mais frouxa levanta `PapelRelaxadoPeloCliente`.
    """
    estrutura = pagina_do_card.get("main_content_structure") or []
    titulo = str(pagina_do_card.get("h1_title") or pagina_do_card.get("page_title") or "")
    return PlanoDaPagina(
        rota=str(pagina_do_card.get("slug") or ""),
        titulo=titulo,
        h1=titulo,
        subtitulos=tuple(str(s) for s in estrutura if str(s or "").strip()),
        # `hook_to_next_page` é o texto do botão que o plano já fixou: ele é CTA,
        # e CTA entra como CTA para cair nas mesmas regras de botão.
        ctas=(
            ({"texto": str(pagina_do_card.get("hook_to_next_page") or ""),
              "destino": "/" + str(pagina_do_card.get("next_page_slug") or "").strip("/")},)
            if pagina_do_card.get("hook_to_next_page") else ()
        ),
        papel_do_motor=papel_do_motor,
        papel_pedido=str(pagina_do_card.get("role") or pagina_do_card.get("papel") or ""),
        cnpj_esperado=cnpj_esperado,
    )


def documento_do_plano_do_card(
    pagina_do_card: Dict[str, Any], *, papel_do_motor: str = "LP",
    cnpj_esperado: Optional[str] = None,
) -> str:
    """O documento que o portão 1 realmente avaliou.

    Existe para o RECIBO: o `content_sha256` tem de ser o hash do que passou
    pelas varreduras, e não do dicionário do card. Hash de uma coisa com
    veredito de outra é um recibo que parece prova e não é.
    """
    return documento_do_plano(
        plano_da_pagina_do_card(
            pagina_do_card, papel_do_motor=papel_do_motor, cnpj_esperado=cnpj_esperado))


def avaliar_plano_do_card(
    pagina_do_card: Dict[str, Any],
    *,
    base_do_site: str = "",
    papel_do_motor: str = "LP",
    e_destino_de_campanha: bool = True,
    cnpj_esperado: Optional[str] = None,
) -> Tuple[Avaliacao, PapelDestino]:
    """O portão 1 sobre a arquitetura do card. Levanta `PapelRelaxadoPeloCliente`."""
    plano = plano_da_pagina_do_card(
        pagina_do_card, papel_do_motor=papel_do_motor, cnpj_esperado=cnpj_esperado)
    return avaliar_plano(
        plano, base_do_site=base_do_site, e_destino_de_campanha=e_destino_de_campanha)


def bloqueios_decidiveis_no_plano(avaliacao: Avaliacao) -> list[str]:
    """Os motivos que o PLANO já decide, em uma linha por motivo.

    Vazio não significa "o plano está aprovado". Significa: nada que este ponto
    de portão consiga decidir sobre um documento incompleto ficou de pé. O resto
    é decidido contra o artefato — no portão 2 desta API e no portão dentro do
    motor, que é quem vê o corpo escrito.

    ⚠️ Os DESCONHECIDOS entram na lista, e essa é a parte que não se negocia.
    Um achado de ausência é ambíguo num plano incompleto; uma varredura que não
    concluiu não é ambígua — ela é a leitura que faltou. Deixá-la de fora
    reproduziria exatamente o defeito do handoff anterior, que testava só
    `bloqueios` e deixaria publicar página cuja varredura falhou.
    """
    motivos = [
        f"bloqueio {a.codigo}: {a.mensagem}"
        for a in avaliacao.bloqueios
        if a.codigo in CODIGOS_DECIDIVEIS_NO_PLANO
    ]
    motivos += [
        f"desconhecido {d['verificacao']}: {d['motivo']}" for d in avaliacao.desconhecidos
    ]
    return motivos
