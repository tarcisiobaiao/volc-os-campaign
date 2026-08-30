# funnel-forge/src/funnelforge/adapters/briefing_volc.py
"""A PONTE DO BRIEFING: `funnel_architecture` (VOLC O.S.) -> `FunnelPlan`.

O card do Pautador já guarda o funil INTEIRO em jsonb, com três chaves —
`funnel_strategy`, `pages[]` e `writing_jobs[]` (ver
`backend/app/routers/entities.py`, onde a coluna é gravada, e
`backend/app/agents/funnel_pro/page_factory.py`, que produz as duas listas).
Esse objeto é praticamente o `FunnelPlan`. Converter direto:

- MATA a chamada de LLM do `step_extract`. Ela existia para reconstruir, a
  partir de texto corrido, um objeto que o sistema já tem estruturado.
- MATA o caminho do DOCX. O `DocxBriefingLoader` lê só
  `Document(...).paragraphs`, e o briefing do VOLC põe Keywords-alvo, CTA,
  Link do CTA e Slug numa TABELA — por isso o funil de produção saiu com
  0 de 7 páginas com `target_keywords`.
- Faz o plano ser aquilo que uma PESSOA aprovou no Pautador, não o que um
  modelo inferiu de um texto que já era derivado desse mesmo objeto.

## De onde sai cada campo (e por quê)

`writing_jobs[]` é a fonte primária, `pages[]` é o complemento. A razão é
crua: a `page_factory` do VOLC descarta, ao montar `pages[]`, exatamente os
campos de que o engine precisa — o `pages[]` canônico NÃO tem slug, NÃO tem
`page_type`, NÃO tem keywords e NÃO tem `next_page_slug`. Tudo isso só
sobrevive dentro de `writing_jobs[].writer_briefing`.

| Page (engine)          | origem                                              |
|------------------------|-----------------------------------------------------|
| slug                   | writer_briefing.current_url (ÚNICO já sufixado)     |
| page_number            | writer_briefing.page_num -> pages[].position -> ordem|
| page_type              | DERIVADO do papel (ver `_PAGE_TYPE_POR_PAPEL`)      |
| role                   | `derive_role(slug)`                                 |
| h1_title               | writer_briefing.headline -> pages[].page_title      |
| emotional_objective    | writer_briefing.objective -> pages[].emotional_goal |
| main_content_structure | pages[].subtitles -> writer_briefing.skeleton       |
| target_keywords        | writer_briefing.keywords (STRING com vírgulas)      |
| hook_to_next_page      | writer_briefing.cta_text                            |
| next_page_slug         | writer_briefing.cta_link, sem a barra               |
| engajamento            | "" — `declarar_engajamento` preenche depois         |

## `intro_section` / `closing_section`: ficam de fora, de propósito

Não têm campo em `Page`, e a tentação óbvia — pendurar no
`main_content_structure` — é justamente o erro. Esse campo vira o
`skeleton` dos prompts do redator, que o leem como "Estrutura (H2
obrigatórios, siga fielmente)": a introdução do arquiteto viraria um H2
chamado "introdução". Pior, os prompts já têm doutrina PRÓPRIA e mais dura
para abertura e fecho (`<introducao_direta>`: no máximo 1 <p>, proibido
parágrafo de roadmap; `<formato_de_saida>`: a última seção termina em
texto, nunca em botão) — doutrina que a auditoria de 11/08 instalou. Mandar
o texto de intro/fecho do arquiteto para lá seria reabrir, pela porta dos
fundos, o que aquela auditoria fechou.

Eles NÃO se perdem: o comando `run-volc` grava a arquitetura de origem
inteira em `runs/<run_id>/funnel_architecture.json`, ao lado do
`funnel_plan.json` gerado. A procedência fica auditável; o prompt fica limpo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from funnelforge.domain.models import FunnelPlan, Page, PageRole, derive_role

# O `page_type` que vem do VOLC é texto livre do arquiteto — "SOLUÇÃO"
# acentuado, "PRÉ-SELL", "Hub", "LANDING PAGE". E o engine compara
# `page.page_type == "LANDING PAGE"` em três lugares decisivos (`step_write`,
# `step_build` e o gate de imagem em `run_pipeline`). Comparar string livre
# com acento contra constante sem acento é a falha silenciosa clássica: a LP
# entraria pelo caminho do redator de página interna. Então o `page_type` aqui
# é DERIVADO do papel, e o papel sai do slug — a mesma convenção dos dois lados.
_PAGE_TYPE_POR_PAPEL: dict[PageRole, str] = {
    PageRole.LP: "LANDING PAGE",
    PageRole.PRESELL: "HUB",
    PageRole.SOLUTION: "SOLUTION",
}

# Sentinela que a `page_factory` do VOLC injeta quando o arquiteto não devolveu
# uma lista de keywords (`page_factory.py`: `keywords_text = "Keywords do tema
# principal"`). Não é keyword: é um recado para humano. Se passar, entra no
# prompt do redator e no `keywords` do juiz como se fosse termo de busca.
_KEYWORDS_SENTINELA = "keywords do tema principal"


def _texto(valor: Any) -> str:
    """String limpa, ou "" para qualquer outra coisa (None, número, dict)."""
    return valor.strip() if isinstance(valor, str) else ""


def _lista_de_texto(valor: Any) -> list[str]:
    """Lista de strings não vazias. Aceita lista (o caso normal, `subtitles`)
    ou string multilinha (`skeleton`, que a `page_factory` monta como
    "- item\\n- item"), porque o arquiteto às vezes devolve a estrutura já
    concatenada e o `page_factory` repassa como veio."""
    if isinstance(valor, list):
        return [t for t in (_texto(v) for v in valor) if t]
    bruto = _texto(valor)
    if not bruto:
        return []
    linhas = (linha.strip().lstrip("-").strip() for linha in bruto.splitlines())
    return [linha for linha in linhas if linha]


def _keywords(valor: Any) -> list[str]:
    """`writer_briefing.keywords` é STRING separada por vírgula — a
    `page_factory` do VOLC junta a lista do arquiteto com ", ". Sem esta
    conversão o `target_keywords` fica vazio (ou, pior, com a frase inteira
    como se fosse uma keyword só). Preserva a ordem, tira duplicata e derruba
    a sentinela."""
    brutos = ([_texto(v) for v in valor] if isinstance(valor, list)
              else [parte.strip() for parte in _texto(valor).split(",")])
    saida: dict[str, None] = {}
    for kw in brutos:
        if kw and kw.lower() != _KEYWORDS_SENTINELA:
            saida.setdefault(kw, None)
    return list(saida)


def _sufixo_por_posicao(posicao: int) -> str:
    """A MESMA regra de `backend/app/entities/funnel_roles.role_for_position`:
    P1 sem sufixo, P2 "-pr", P3+ "-p{posicao-2}". Está duplicada aqui de
    propósito — o engine não importa o backend, e a convenção é justamente o
    contrato entre os dois. Se um dia ela mudar, muda nos dois lugares."""
    if posicao <= 1:
        return ""
    if posicao == 2:
        return "-pr"
    return f"-p{posicao - 2}"


# Todo sufixo que a convenção usa. Reconhecê-los é o que permite TIRAR o
# errado antes de pôr o certo — ver `_slug_com_sufixo`.
_SUFIXO_RE = re.compile(r"-(?:pr|p\d+)$")


def _slug_com_sufixo(slug: str, posicao: int) -> str:
    """Impõe o sufixo da POSIÇÃO, trocando o que estiver lá.

    ## ⚠️ Antes ele só ACRESCENTAVA, e isso custou um run inteiro

    A versão anterior era idempotente no sentido fraco: se o slug já terminasse
    em QUALQUER sufixo, ela não mexia. Medido no card 65 em 19/08/2026: o
    arquiteto escreveu a `current_url` da landing page como
    `fgts-saque-aniversario-p1` — com sufixo de página-solução. Esta função viu
    um sufixo e não tocou; `derive_role` leu `-p1` e devolveu SOLUTION; nenhuma
    das cinco páginas ficou com papel LP; o BFS de `reachable_slugs` partiu de
    uma lista vazia e as CINCO saíram como `unreachable_page`.

    O run terminou como `done` em nove segundos, com zero páginas e custo de
    US$ 0,0048.

    A raiz é haver duas fontes de verdade para a mesma coisa: o backend declara
    `role: "landing"` no job, e o engine RE-DERIVA o papel do texto do slug. Não
    dá para o engine deixar de derivar — `derive_role` é o contrato dele com o
    mundo —, mas dá para garantir que o slug que chega à derivação corresponda à
    posição declarada. É o que esta função passa a fazer: tira o sufixo que
    estiver e põe o da posição.

    Consequência deliberada: a posição VENCE o texto que o arquiteto escreveu.
    Ele erra o sufixo às vezes; a posição vem de `page_num`, que é dado, não
    prosa.
    """
    slug = slug.strip().strip("/")
    if not slug:
        return slug
    base = _SUFIXO_RE.sub("", slug)
    return base + _sufixo_por_posicao(posicao)


def _arquitetura(dados: dict[str, Any]) -> dict[str, Any]:
    """Aceita tanto o `funnel_architecture` puro quanto a linha do banco que o
    contém (`{"id": ..., "funnel_architecture": {...}}`), para o operador poder
    salvar o retorno do Supabase sem editar o JSON na mão."""
    interno = dados.get("funnel_architecture")
    return interno if isinstance(interno, dict) else dados


def plano_do_funnel_architecture(dados: dict[str, Any]) -> FunnelPlan:
    """Converte o `funnel_architecture` de um card do Pautador em `FunnelPlan`.

    Levanta `ValueError` (mensagem em português, ela chega ao operador) quando
    a arquitetura não tem o mínimo para virar um funil. Falhar aqui é barato;
    falhar depois custa um run inteiro.
    """
    arq = _arquitetura(dados)
    jobs = [j for j in (arq.get("writing_jobs") or []) if isinstance(j, dict)]
    canonicas = [p for p in (arq.get("pages") or []) if isinstance(p, dict)]
    if not jobs:
        raise ValueError(
            "funnel_architecture sem `writing_jobs`: é ele que carrega o slug de cada "
            "página (writer_briefing.current_url) — o `pages[]` canônico não tem slug. "
            "Rode a etapa 'Em funil' do Pautador de novo para regravar a arquitetura."
        )

    # `pages[]` entra só como complemento, indexado pela posição.
    por_posicao: dict[int, dict[str, Any]] = {}
    for indice, canonica in enumerate(canonicas, start=1):
        try:
            posicao = int(canonica.get("position") or indice)
        except (TypeError, ValueError):
            posicao = indice
        por_posicao.setdefault(posicao, canonica)

    paginas: list[Page] = []
    destino_por_posicao: dict[int, str] = {}      # posição -> cta_link, sem barra
    for indice, job in enumerate(jobs, start=1):
        wb = job.get("writer_briefing") or {}
        if not isinstance(wb, dict):
            wb = {}
        try:
            posicao = int(wb.get("page_num") or indice)
        except (TypeError, ValueError):
            posicao = indice

        slug = _slug_com_sufixo(_texto(wb.get("current_url")), posicao)
        if not slug:
            raise ValueError(
                f"Página {posicao} do funil sem `writer_briefing.current_url`: sem slug "
                "não há URL, não há grafo e não há o que publicar."
            )
        papel = derive_role(slug)
        canonica = por_posicao.get(posicao, {})

        paginas.append(Page(
            page_number=posicao,
            page_type=_PAGE_TYPE_POR_PAPEL[papel],
            role=papel,
            h1_title=_texto(wb.get("headline")) or _texto(canonica.get("page_title")),
            slug=slug,
            emotional_objective=(_texto(wb.get("objective"))
                                 or _texto(canonica.get("emotional_goal"))),
            main_content_structure=(_lista_de_texto(canonica.get("subtitles"))
                                    or _lista_de_texto(wb.get("skeleton"))),
            hook_to_next_page=_texto(wb.get("cta_text")),
            target_keywords=_keywords(wb.get("keywords")),
            # `next_page_slug` só é resolvido depois, quando todos os slugs
            # do funil já existem — ver o segundo passo abaixo.
            next_page_slug="",
        ))
        destino_por_posicao[posicao] = _texto(wb.get("cta_link")).strip("/")

    paginas.sort(key=lambda p: p.page_number)

    # 2º passo — `next_page_slug` só vale se APONTAR para uma página deste
    # funil. A `page_factory` do VOLC preenche `cta_link` com "/inicio" na
    # última página e "/pagina-N" quando o arquiteto não declarou destino:
    # slugs de páginas que não existem. Eles não quebram o grafo (as rotas de
    # verdade saem de `build_funnel_routes`), mas viram href morto no
    # `step_build` da LP quando `page.routes` está vazio, e texto errado no
    # prompt do juiz (`_cta_link`). Melhor vazio que inventado.
    por_slug = {p.slug: p for p in paginas}
    for pagina in paginas:
        alvo = destino_por_posicao.get(pagina.page_number, "")
        pagina.next_page_slug = alvo if alvo in por_slug and alvo != pagina.slug else ""

    estrategia = arq.get("funnel_strategy") or {}
    primeiro_wb = (jobs[0].get("writer_briefing") or {}) if jobs else {}
    primeiro_wb = primeiro_wb if isinstance(primeiro_wb, dict) else {}
    return FunnelPlan(
        avatar_summary=(_texto(estrategia.get("avatar_summary"))
                        or _texto(primeiro_wb.get("avatar_context"))),
        tone_voice=(_texto(estrategia.get("tone_voice"))
                    or _texto(primeiro_wb.get("tone"))),
        # `pages` é AUTORITATIVO sobre a contagem, igual ao `_plan_from_raw` do
        # `steps.py`: um `total_pages` desencontrado no `funnel_strategy` nunca
        # deve divergir do plano nem do relatório.
        total_pages=len(paginas),
        pages=paginas,
    )


def carregar_arquitetura(caminho: Path) -> dict[str, Any]:
    """Lê o JSON do card (arquivo salvo do Supabase ou do endpoint)."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError(
            f"{caminho}: esperava um objeto JSON com `pages`/`writing_jobs`, "
            f"veio {type(dados).__name__}."
        )
    return dados
