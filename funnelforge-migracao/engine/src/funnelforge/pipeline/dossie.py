"""DOSSIÊ FACTUAL PRÉ-REDAÇÃO: pesquisa forte uma vez, fatos congelados.

ESQUELETO APROVADO → PESQUISA ÚNICA DO FUNIL → DOSSIÊ → PORTÃO DE COBERTURA
→ (páginas liberadas) redação.

Composição, não arquitetura nova:
- a pesquisa é o mesmo caminho de grounding (`adapters/research_perplexity`):
  citações do PROVEDOR, redirects resolvidos; URL que o modelo só digitou não
  vira fonte;
- a verificação ao vivo é o mesmo `url_verifier` do run (cache compartilhado);
- cada página recebe seus fatos verificados em `state.facts[n]` — o formato
  que redator, juiz, revisor, `base_factual` e `critical_fact_grounding` já
  leem — e seus canais oficiais por `registrar_canais_oficiais`;
- a jornada diz o que cada página precisa provar (`requisitos`, entregas,
  saída oficial, plano visual, ativos).

O portão de cobertura é determinístico: página sem lastro para a promessa não
chama briefing, redação, SEO, widget, revisão, imagem, print, build nem publish.
Lacuna gera no máximo DUAS rodadas de pesquisa dirigida, e só para o que falta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from funnelforge.domain.dossie import (
    TIPOS_TEMPORAIS,
    CoberturaDaPagina,
    CoberturaDoRequisito,
    DossieDaPagina,
    DossieDoFunil,
    FatoDoDossie,
    FonteDoDossie,
    TelemetriaDaPesquisa,
    id_do_fato,
    sha256_canonico,
)
from funnelforge.domain.models import (
    TIPOS_DE_FATO,
    Issue,
    Page,
    RequisitoFactual,
    ResearchFacts,
    RunState,
    StepResult,
    StepStatus,
    canon_rotulo,
    canon_tipo_de_fato,
    effective_role,
)
from funnelforge.pipeline.jornada._comum import estado_do_leitor, links, por_slug
from funnelforge.pipeline.jornada.contexto import ativos_validos, politica_da_saida_oficial

MAX_RODADAS_DE_COMPLEMENTO = 2
_HOSTS_OFICIAIS = (".gov.br", ".gov", ".leg.br", ".jus.br", ".mil.br", ".mp.br")


@dataclass
class RespostaDaPesquisa:
    """O que uma rodada de pesquisa do funil devolve (porta da pesquisa)."""
    dados: dict
    citacoes: list[str]               # URLs CANÔNICAS que o grounding citou
    modelo_pedido: str = ""
    modelo_servido: str = ""
    auth_mode: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    custo_usd: float = 0.0
    latencia_ms: int = 0
    consultas_de_busca: int = 0       # cobradas por consulta, fora de `custo_usd`
    finish_reason: str = ""
    defeito: str = ""                 # resposta vazia/ilegível: aborta o dossiê


class PesquisaSemResposta(RuntimeError):
    """A pesquisa do dossiê voltou vazia ou ilegível: nada a compilar, nenhuma
    complementação às cegas."""


# pesquisar(assunto, paginas_spec, faltantes) -> RespostaDaPesquisa
Pesquisar = Callable[[str, list[dict], list[dict] | None], RespostaDaPesquisa]


def requisitos_da_pagina(page: Page) -> list[RequisitoFactual]:
    """Os requisitos declarados; sem declaração, o mínimo honesto: a resposta
    principal precisa de UM fato verificado que não seja só contexto."""
    j = page.jornada
    if j is None:
        return []
    if j.requisitos:
        return list(j.requisitos)
    return [RequisitoFactual(id="resposta_principal",
                             descricao=f"fato que sustenta a resposta de '{j.pergunta_principal}'",
                             tipos=[t for t in TIPOS_DE_FATO if t != "contexto"])]


def especificacao_das_paginas(pages: list[Page]) -> list[dict]:
    spec = []
    for p in pages:
        j = p.jornada
        spec.append({
            "duvida_id": j.duvida_id, "pergunta": j.pergunta_principal,
            "promessa": j.resposta_imediata,
            "entregas": list(j.valor.entregas) if j.valor else [],
            "requisitos": [{"id": r.id, "descricao": r.descricao, "tipos": r.tipos}
                           for r in requisitos_da_pagina(p)],
        })
    return spec


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _tipo_da_fonte(url: str, oficiais: set[str]) -> str:
    host = urlparse(url).netloc.lower()
    if host == "gov.br" or host.endswith(_HOSTS_OFICIAIS):
        return "oficial"
    hosts_oficiais = {urlparse(o).netloc.lower() for o in oficiais}
    if _norm_url(url) in {_norm_url(o) for o in oficiais} or host in hosts_oficiais:
        return "canal_oficial"
    return "secundaria"


def _data(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def fatos_da_resposta(resp: RespostaDaPesquisa) -> list[FatoDoDossie]:
    """Converte a saída do modelo em fatos com status INICIAL. Só a citação do
    provedor torna uma URL candidata a fonte; o resto nasce `unverified`."""
    citadas = {_norm_url(c) for c in resp.citacoes}
    saida: list[FatoDoDossie] = []
    for bruto in (resp.dados.get("fatos") or []):
        if not isinstance(bruto, dict):
            continue
        afirmacao = str(bruto.get("afirmacao") or bruto.get("fato") or "").strip()
        url = str(bruto.get("fonte") or bruto.get("source_url") or "").strip()
        tipo = canon_tipo_de_fato(bruto.get("tipo")) or ""
        if not afirmacao or not url:
            continue
        valor, unidade = str(bruto.get("valor") or "").strip(), str(bruto.get("unidade") or "").strip()
        fato = FatoDoDossie(
            fact_id=id_do_fato(url, tipo, afirmacao, valor), afirmacao=afirmacao, tipo=tipo,
            valor=valor, unidade=unidade, source_url=url,
            vigente_desde=_data(bruto.get("vigente_desde")),
            paginas=[canon_rotulo(p) for p in (bruto.get("paginas") or []) if isinstance(p, str)],
            requisitos=[canon_rotulo(r) for r in (bruto.get("requisitos") or [])
                        if isinstance(r, str)],
            evidencia=str(bruto.get("evidencia") or "")[:300],
            dispositivo=str(bruto.get("dispositivo") or "")[:200])
        if tipo not in TIPOS_DE_FATO:
            fato.motivo_do_status = f"tipo '{bruto.get('tipo')}' fora do vocabulário"
        elif _norm_url(url) not in citadas:
            fato.motivo_do_status = "fonte não citada pelo grounding do provedor"
        elif tipo in TIPOS_TEMPORAIS and (not valor or not fato.vigente_desde):
            fato.motivo_do_status = "número/data sem valor ou sem referência temporal"
        elif not url.startswith("https://"):
            fato.motivo_do_status = "fonte não é https"
        saida.append(fato)
    return saida


def verificar_ao_vivo(fatos: list[FatoDoDossie], verificador: Any, hoje: date) -> None:
    """Promove a `verified` só o fato sem reprovação prévia cuja fonte RESPONDEU.
    Bloqueio (WAF, timeout) não é prova: o fato fica `unverified`."""
    for f in fatos:
        if f.status != "unverified" or f.motivo_do_status:
            continue
        if verificador is None:
            f.motivo_do_status = "sem verificador de URL no run"
            continue
        try:
            ok = bool(verificador.verify_url(f.source_url))
        except Exception:  # noqa: BLE001 - falha de verificação é resultado, não exceção
            ok = False
        if ok:
            f.status, f.verificado_em = "verified", hoje
        else:
            motivo = getattr(verificador, "motivo", None)
            f.motivo_do_status = ("fonte não respondeu na verificação ao vivo"
                                  + (f" ({motivo(f.source_url)})" if callable(motivo) else ""))


def marcar_conflitos(fatos: list[FatoDoDossie]) -> list[str]:
    """Fatos VERIFICADOS que cobrem o mesmo requisito com valores diferentes
    entram em conflito: nenhum deles sustenta a página até alguém decidir."""
    grupos: dict[str, list[FatoDoDossie]] = {}
    for f in fatos:
        if f.status == "verified" and f.valor:
            for r in f.requisitos:
                grupos.setdefault(r, []).append(f)
    conflitos: list[str] = []
    for grupo in grupos.values():
        valores = {(" ".join(f.valor.lower().split()), f.unidade.lower().strip()) for f in grupo}
        if len(valores) > 1:
            for f in grupo:
                f.status = "conflict"
                f.motivo_do_status = "fontes divergem sobre o mesmo requisito"
                conflitos.append(f.fact_id)
    return sorted(set(conflitos))


def _fatos_para_a_pagina(fatos: list[FatoDoDossie], page: Page) -> list[FatoDoDossie]:
    duvida = page.jornada.duvida_id
    return [f for f in fatos if duvida in f.paginas]


def _research_facts(fatos: list[FatoDoDossie]) -> ResearchFacts:
    """A PROJEÇÃO no formato que o motor já lê: só fatos verificados."""
    verificados = [f for f in fatos if f.status == "verified"]
    fatos_verificados, dados = [], []
    for f in verificados:
        if f.tipo in TIPOS_TEMPORAIS and f.valor and f.vigente_desde:
            fatos_verificados.append({
                "valor": f.valor, "unidade": f.unidade or "-", "fonte_primaria": f.source_url,
                "dispositivo": f.dispositivo or f.afirmacao[:160],
                "vigente_desde": f.vigente_desde, "verificado_em": f.verificado_em, "tipo": f.tipo})
        else:
            dados.append({"fato": f.afirmacao, "fonte": f.source_url, "tipo": f.tipo})
    fontes = list(dict.fromkeys(f.source_url for f in verificados))
    return ResearchFacts(resumo="", dados_validados=dados, fatos_verificados=fatos_verificados,
                         fontes=fontes, fontes_resolvidas=fontes, sparse=not verificados)


def cobertura_da_pagina(state: RunState, page: Page, fatos: list[FatoDoDossie]) -> CoberturaDaPagina:
    j = page.jornada
    cob = CoberturaDaPagina()
    verificados = [f for f in fatos if f.status == "verified"]
    for r in requisitos_da_pagina(page):
        candidatos = [f for f in verificados if f.tipo in r.tipos and (
            r.id in f.requisitos or (r.id == "resposta_principal" and f.tipo != "contexto"))]
        em_conflito = [f for f in fatos if f.status == "conflict" and r.id in f.requisitos]
        coberto = bool(candidatos)
        motivo = "" if coberto else ("fontes em conflito" if em_conflito else "sem fato verificado")
        cob.requisitos.append(CoberturaDoRequisito(
            requisito_id=r.id, coberto=coberto, fatos=[f.fact_id for f in candidatos], motivo=motivo))
        if r.critico and not coberto:
            cob.blockers.append(f"requisito '{r.id}' ({r.descricao}): {motivo}")
    oficiais = list(state.official_links.get(page.page_number) or [])
    politica = politica_da_saida_oficial(page)
    if politica and politica.exige and not oficiais:
        cob.blockers.append("saída oficial exigida pela jornada sem canal oficial verificado")
    numericos = [f for f in verificados if f.tipo in ("numero", "condicao", "prazo")]
    for bloco in j.plano_visual:
        if bloco.intencao in ("calculo", "exemplos_numericos") and not numericos:
            cob.blockers.append(f"bloco '{bloco.secao}' ({bloco.intencao}) sem número verificado")
        if bloco.intencao == "prova_oficial" and not oficiais:
            cob.blockers.append(f"bloco '{bloco.secao}' (prova_oficial) sem canal oficial verificado")
    lastro = {_norm_url(f.source_url) for f in verificados} | {_norm_url(o) for o in oficiais}
    for ativo in ativos_validos(page):
        if _norm_url(ativo.fonte_da_regra) not in lastro:
            cob.blockers.append(f"ativo '{ativo.pergunta}': fonte da regra fora das fontes "
                                "verificadas desta página")
    cob.ready_to_write = not cob.blockers
    return cob


def _faltantes(paginas: dict[int, CoberturaDaPagina], pages: list[Page]) -> list[dict]:
    por_numero = {p.page_number: p for p in pages}
    faltam = []
    for n, cob in paginas.items():
        reqs = {r.id: r for r in requisitos_da_pagina(por_numero[n])}
        for c in cob.requisitos:
            if not c.coberto and c.requisito_id in reqs:
                r = reqs[c.requisito_id]
                faltam.append({"duvida_id": por_numero[n].jornada.duvida_id,
                               "requisito": r.id, "descricao": r.descricao, "tipos": r.tipos})
    return faltam


def compilar_dossie(state: RunState, deps: Any, pesquisar: Pesquisar, *,
                    registrar_canais: Callable[[RunState, Page, Any], None],
                    hoje: date | None = None) -> DossieDoFunil:
    """Pesquisa única + até duas complementações dirigidas → dossiê fechado.
    Escreve `state.facts[n]` e `state.official_links[n]` das páginas da jornada."""
    hoje = hoje or date.today()
    pages = [p for p in (state.plan.pages if state.plan else []) if p.jornada is not None]
    assunto = (state.plan.jornada.intencao_principal if state.plan and state.plan.jornada
               else (pages[0].h1_title if pages else ""))
    spec = especificacao_das_paginas(pages)
    fatos: dict[str, FatoDoDossie] = {}
    citacoes: set[str] = set()
    telemetria: list[TelemetriaDaPesquisa] = []
    faltantes: list[dict] | None = None
    coberturas: dict[int, CoberturaDaPagina] = {}
    conflitos: list[str] = []
    for rodada in range(1, MAX_RODADAS_DE_COMPLEMENTO + 2):
        resp = pesquisar(assunto, spec, faltantes)
        telemetria.append(TelemetriaDaPesquisa(
            rodada=rodada, modelo_pedido=resp.modelo_pedido, modelo_servido=resp.modelo_servido,
            auth_mode=resp.auth_mode, citacoes=len(resp.citacoes),
            prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
            custo_usd=resp.custo_usd, latencia_ms=resp.latencia_ms,
            consultas_de_busca=getattr(resp, "consultas_de_busca", 0),
            finish_reason=getattr(resp, "finish_reason", ""),
            faltantes_pedidos=[f"{f['duvida_id']}:{f['requisito']}" for f in (faltantes or [])]))
        if getattr(resp, "defeito", ""):
            raise PesquisaSemResposta(f"rodada {rodada}: {resp.defeito}")
        citacoes |= {_norm_url(c) for c in resp.citacoes}
        novos = [f for f in fatos_da_resposta(resp) if f.fact_id not in fatos]
        verificar_ao_vivo(novos, getattr(deps, "url_verifier", None), hoje)
        for f in novos:
            fatos[f.fact_id] = f
        for f in fatos.values():                 # conflito é recalculado do zero
            if f.status == "conflict":
                f.status, f.motivo_do_status = "verified", ""
        conflitos = marcar_conflitos(list(fatos.values()))
        for page in pages:
            state.facts[page.page_number] = _research_facts(
                _fatos_para_a_pagina(list(fatos.values()), page))
            state.official_links.pop(page.page_number, None)
            registrar_canais(state, page, deps)
            coberturas[page.page_number] = cobertura_da_pagina(
                state, page, _fatos_para_a_pagina(list(fatos.values()), page))
        faltantes = _faltantes(coberturas, pages)
        if not faltantes:
            break
    oficiais = {u for p in pages for u in (state.official_links.get(p.page_number) or [])}
    for f in fatos.values():
        f.tipo_da_fonte = _tipo_da_fonte(f.source_url, oficiais)
    return montar_dossie(state, pages, list(fatos.values()), coberturas, conflitos,
                         citacoes, telemetria, assunto)


def montar_dossie(state: RunState, pages: list[Page], fatos: list[FatoDoDossie],
                  coberturas: dict[int, CoberturaDaPagina], conflitos: list[str],
                  citacoes: set[str], telemetria: list[TelemetriaDaPesquisa],
                  assunto: str) -> DossieDoFunil:
    fatos = sorted(fatos, key=lambda f: f.fact_id)
    slugs = por_slug(state.plan)
    paginas: list[DossieDaPagina] = []
    lacunas: list[dict] = []
    for page in pages:
        j = page.jornada
        dela = _fatos_para_a_pagina(fatos, page)
        cob = coberturas[page.page_number]
        politica = politica_da_saida_oficial(page)
        dp = DossieDaPagina(
            page_number=page.page_number, slug=page.slug, role=effective_role(page).value,
            duvida_id=j.duvida_id, pergunta=j.pergunta_principal, promessa=j.resposta_imediata,
            entregas=list(j.valor.entregas) if j.valor else [],
            ja_resolvido=sorted(estado_do_leitor(state.plan, page).certamente),
            proxima_duvida=j.proxima_duvida,
            requisitos=[r.id for r in requisitos_da_pagina(page)],
            fatos_verificados=sorted(f.fact_id for f in dela if f.status == "verified"),
            fatos_nao_confirmados=sorted(f.fact_id for f in dela if f.status == "unverified"),
            conflitos=sorted(f.fact_id for f in dela if f.status == "conflict"),
            urls_oficiais=list(state.official_links.get(page.page_number) or []),
            cta={"destinos": [{"slug": l.target, "resolve": slugs[l.target].jornada.duvida_id
                               if l.target in slugs and slugs[l.target].jornada else ""}
                              for l in links(page)],
                 "saida_oficial": politica.classe if politica else "nao_aplicavel"},
            layout=[b.intencao for b in j.plano_visual],
            assets=[a.pergunta for a in ativos_validos(page)]
                   + (["print_oficial"] if state.official_links.get(page.page_number) else []),
            cobertura=cob)
        dp.sha256 = sha256_canonico({"pagina": dp.model_dump(mode="json", exclude={"sha256"}),
                                     "fatos": [f.model_dump(mode="json") for f in dela]})
        paginas.append(dp)
        for c in cob.requisitos:
            if not c.coberto:
                lacunas.append({"pagina": page.page_number, "requisito": c.requisito_id,
                                "motivo": c.motivo})
    oficiais = {u for p in paginas for u in p.urls_oficiais}
    fontes = []
    for url in sorted({f.source_url for f in fatos}):
        dos = [f for f in fatos if f.source_url == url]
        fontes.append(FonteDoDossie(
            url=url, tipo_da_fonte=_tipo_da_fonte(url, oficiais),
            citada_pelo_grounding=_norm_url(url) in citacoes,
            verificada=any(f.status in ("verified", "conflict") for f in dos),
            motivo="; ".join(sorted({f.motivo_do_status for f in dos if f.motivo_do_status}))))
    dossie = DossieDoFunil(run_id=state.run_id, assunto=assunto,
                           gerado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           fontes=fontes, fatos=fatos, paginas=paginas, conflitos=conflitos,
                           lacunas=lacunas, pesquisa=telemetria)
    dossie.sha256 = hash_do_dossie(dossie)
    return dossie


def hash_do_dossie(dossie: DossieDoFunil) -> str:
    """O hash do CONTEÚDO canônico: fatos e páginas. Hora, run e telemetria da
    pesquisa ficam fora — o mesmo conteúdo tem o mesmo hash em qualquer run."""
    return sha256_canonico(dossie.model_dump(
        mode="json", include={"schema_version", "assunto", "fatos", "paginas", "conflitos"}))


def paginas_afetadas(antigo: dict, novo: DossieDoFunil) -> list[int]:
    """Páginas cujo pacote mudou entre dois dossiês (hash por página)."""
    antes = {p["page_number"]: p.get("sha256") for p in (antigo or {}).get("paginas", [])}
    return sorted(p.page_number for p in novo.paginas if antes.get(p.page_number) != p.sha256)


_ESTADO_POR_PAGINA = ("drafts", "seo", "images", "image_reviews", "screenshots", "briefings",
                      "revisoes", "recibos", "decisoes_humanas", "normalizacoes",
                      "decoracoes", "metadados")


def invalidar_paginas(state: RunState, paginas: list[int]) -> None:
    """Mudança factual invalida SÓ as páginas afetadas: tira o que foi escrito
    a partir do pacote antigo (e o veredito), mantém o resto do run."""
    for n in paginas:
        for campo in _ESTADO_POR_PAGINA:
            getattr(state, campo).pop(n, None)
        sufixo = f"_p{n}"
        for chave in [k for k in state.step_status if k.endswith(sufixo)
                      and not k.startswith(("research_", "dossie_"))]:
            state.step_status.pop(chave)
        state.step_status.pop(f"page_{n}", None)


def projecao_para_o_prompt(dossie: dict, numero: int) -> dict:
    """O PageDossier congelado como o redator, o juiz e o revisor o recebem:
    curto — fatos verificados com id, fonte e vigência; nada de dump."""
    pagina = next((p for p in dossie.get("paginas", []) if p.get("page_number") == numero), None)
    if pagina is None:
        return {}
    por_id = {f["fact_id"]: f for f in dossie.get("fatos", [])}
    return {
        "sha256": pagina.get("sha256", ""),
        "fatos": [{"id": i, "afirmacao": por_id[i]["afirmacao"], "tipo": por_id[i]["tipo"],
                   "valor": por_id[i].get("valor", ""), "unidade": por_id[i].get("unidade", ""),
                   "fonte": por_id[i]["source_url"],
                   "vigente_desde": por_id[i].get("vigente_desde") or ""}
                  for i in pagina.get("fatos_verificados", []) if i in por_id],
        "urls_oficiais": list(pagina.get("urls_oficiais") or []),
    }


@dataclass
class ResultadoDoPortao:
    prontas: list[int] = field(default_factory=list)
    bloqueadas: dict[int, list[str]] = field(default_factory=dict)


def aplicar_portao(state: RunState, dossie: DossieDoFunil) -> ResultadoDoPortao:
    """Grava o veredito do portão no estado: `dossie_pN` OK/FAILED e, para a
    página bloqueada, `blocked_pN` — o laço do pipeline não a toca."""
    res = ResultadoDoPortao()
    for pg in dossie.paginas:
        n = pg.page_number
        state.step_status[f"research_p{n}"] = StepResult(
            step=f"research_p{n}", status=StepStatus.OK, model_used="dossie",
            issues=[Issue(code="fatos_do_dossie",
                          message=f"{len(pg.fatos_verificados)} fato(s) verificado(s) do dossiê "
                                  f"{dossie.sha256[:12]}")])
        if pg.cobertura.ready_to_write:
            state.step_status[f"dossie_p{n}"] = StepResult(step=f"dossie_p{n}",
                                                           status=StepStatus.OK)
            state.step_status.pop(f"blocked_p{n}", None)
            res.prontas.append(n)
        else:
            issues = [Issue(code="dossie_sem_cobertura", message=b) for b in pg.cobertura.blockers]
            state.step_status[f"dossie_p{n}"] = StepResult(step=f"dossie_p{n}",
                                                           status=StepStatus.FAILED, issues=issues)
            state.step_status[f"blocked_p{n}"] = StepResult(
                step=f"blocked_p{n}", status=StepStatus.FAILED,
                issues=[Issue(code="fail_closed",
                              message="dossiê sem cobertura: nenhuma chamada de briefing, "
                                      "redação, SEO, widget, revisão, imagem, print, build ou "
                                      "publish para esta página")] + issues)
            res.bloqueadas[n] = list(pg.cobertura.blockers)
    return res
