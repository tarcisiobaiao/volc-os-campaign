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
    nucleo_da_unidade,
    numeros_do_texto,
    texto_normal,
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
    # False quando o servidor não devolve preço (plano ChatGPT): o custo fica
    # NÃO INFORMADO, nunca US$ 0,00 como cobrança comprovada.
    custo_informado: bool = True
    # Metadados sanitizados de CADA chamada ao provedor nesta rodada
    # (finishReason, bloqueio, segurança, busca, grounding, tokens, texto).
    metadados: list[dict] = field(default_factory=list)


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
            evidencia=str(bruto.get("evidencia_resumida") or bruto.get("evidencia") or "")[:300],
            dispositivo=str(bruto.get("dispositivo") or "")[:200])
        if resp.auth_mode == "hint_do_operador":
            # Só a rodada de hints (código, sem modelo) marca a origem e traz a
            # proveniência lida no documento. Resposta de modelo nunca escolhe
            # a própria origem nem se declara derivada.
            fato.origem = "hint_do_operador"
            fato.proveniencia = dict(bruto.get("proveniencia") or {})
        if bruto.get("motivo_nao_verificado"):
            # O provedor já conferiu e reprovou (ex.: a página citada não
            # confirma o valor): o fato fica com o motivo dele.
            fato.motivo_do_status = str(bruto["motivo_nao_verificado"])[:300]
        elif tipo not in TIPOS_DE_FATO:
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
        # Mesma DIMENSÃO (núcleo da unidade) e números diferentes = conflito.
        # "até 2" e "2" salários mínimos concordam; "2 salários" e "R$ 3.242"
        # são grandezas diferentes, não divergência.
        por_dimensao: dict[str, list[FatoDoDossie]] = {}
        for f in grupo:
            por_dimensao.setdefault(nucleo_da_unidade(f.unidade), []).append(f)
        for fatos_da_dimensao in por_dimensao.values():
            valores = {frozenset(numeros_do_texto(f.valor)) or texto_normal(f.valor).strip()
                       for f in fatos_da_dimensao}
            if len(valores) > 1:
                for f in fatos_da_dimensao:
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
        url = f.source_url or f.derivacao.get("fonte_base", "")
        if f.tipo in TIPOS_TEMPORAIS and f.valor and f.vigente_desde:
            fatos_verificados.append({
                "valor": f.valor, "unidade": f.unidade or "-", "fonte_primaria": url,
                "dispositivo": f.dispositivo or f.afirmacao[:160],
                "vigente_desde": f.vigente_desde, "verificado_em": f.verificado_em, "tipo": f.tipo})
        else:
            dados.append({"fato": f.afirmacao, "fonte": url, "tipo": f.tipo})
    fontes = list(dict.fromkeys(f.source_url or f.derivacao.get("fonte_base", "")
                                for f in verificados))
    fontes = [u for u in fontes if u]
    return ResearchFacts(resumo="", dados_validados=dados, fatos_verificados=fatos_verificados,
                         fontes=fontes, fontes_resolvidas=fontes, sparse=not verificados)


UFS = frozenset("ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se "
                "to".split())


def abrangencia_da_fonte(url: str) -> tuple[str, str]:
    """('nacional' | 'regional' | 'outra', uf). Pelo host: `pb.senac.br` e
    `sp.gov.br` são regionais; `senac.br` e `planalto.gov.br`, nacionais."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    rotulos = host.split(".")
    uf = next((r for r in rotulos[:-2] if r in UFS), "")
    if uf:
        return "regional", uf
    if host == "gov.br" or host.endswith(".gov.br") or len(rotulos) == 2:
        return "nacional", ""
    return "outra", ""


def _dominio(host: str) -> str:
    return ".".join((host or "").lower().split(".")[-2:])


def _fonte_oficial(url: str, oficiais: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host == "gov.br" or host.endswith(".gov.br") or host.endswith(_HOSTS_OFICIAIS):
        return True
    return _dominio(host) in {_dominio(urlparse(o).hostname or "") for o in oficiais}


def _ordem(f: FatoDoDossie) -> tuple:
    """Versão canônica primeiro (dn.senac.br, norma federal), depois a vigência
    mais recente, depois o id (determinístico)."""
    return (0 if (f.proveniencia or {}).get("canonica") else 1,
            -(f.vigente_desde.toordinal() if f.vigente_desde else 0), f.fact_id)


def _melhor_fonte(candidatos: list[FatoDoDossie], niveis: list[tuple[str, Callable]]):
    from funnelforge.pipeline.proveniencia import escopo_do_fato
    for nivel, aceita in niveis:
        dele = [f for f in candidatos if aceita(*escopo_do_fato(f))]
        if dele:
            return sorted(dele, key=_ordem)[0], nivel
    return None, ""


def _melhor_por_escopo(candidatos: list[FatoDoDossie]) -> FatoDoDossie | None:
    """Premissa de derivado: nacional antes de regional; canônica antes."""
    from funnelforge.pipeline.proveniencia import escopo_do_fato
    if not candidatos:
        return None
    return sorted(candidatos, key=lambda f: (escopo_do_fato(f)[0] != "nacional",) + _ordem(f))[0]


def _fato_oficial(f: FatoDoDossie, oficiais: list[str]) -> bool:
    if f.origem == "derivado":
        return bool(f.derivacao.get("oficial"))
    if (f.proveniencia or {}).get("issuer_scope") in ("national", "regional"):
        return True
    return _fonte_oficial(f.source_url, oficiais)


def vincular_ativo(ativo: Any, page: Page, verificados: list[FatoDoDossie],
                   oficiais: list[str], ufs: list[str], hoje: date
                   ) -> tuple[list[dict], list[str], list[dict]]:
    """Liga cada necessidade declarada do ativo ao melhor fato CITADO e
    VERIFICADO, por prioridade: fonte nacional oficial; fonte oficial regional
    da geografia do conteúdo; para valor vigente, edital oficial atual de
    qualquer UF, com a abrangência explícita. Nada de rebind arbitrário: só
    fato verificado, de fonte oficial, que cobre o requisito declarado."""
    reqs = {r.id: r for r in requisitos_da_pagina(page)}
    geo = set(ufs)
    nacional = ("fonte nacional oficial", lambda a, uf: a == "nacional")
    regional = ("fonte oficial regional da geografia do conteúdo",
                lambda a, uf: a == "regional" and uf in geo)
    edital = ("edital oficial atual (abrangência regional explícita)",
              lambda a, uf: a == "regional")
    vinculos, bloqueios, faltas = [], [], []
    for papel, req_id in (("regra", ativo.rule_source_fact_id),
                          ("valor_vigente", ativo.current_value_source_fact_id)):
        if not req_id:
            continue
        r = reqs.get(req_id)
        candidatos = [f for f in verificados
                      if req_id in f.requisitos and _fato_oficial(f, oficiais)
                      and (r is None or f.tipo in r.tipos)]
        if papel == "valor_vigente":
            candidatos = [f for f in candidatos if f.valor and f.vigente_desde
                          and f.vigente_desde.year == hoje.year]
            niveis = [nacional, regional, edital]
            exige = (f"valor em reais vigente em {hoje.year}, com data e abrangência "
                     "explícitas, de fonte oficial")
        else:
            niveis = [nacional, regional]
            exige = ("fonte NACIONAL oficial (ex.: Departamento Nacional ou norma federal "
                     "em gov.br); edital ou página regional não prova regra universal")
        fato, nivel = _melhor_fonte(candidatos, niveis)
        if fato is None:
            bloqueios.append(f"ativo '{ativo.pergunta}': {papel} ('{req_id}') sem {exige}")
            faltas.append({"requisito": req_id, "papel": papel,
                           "descricao": f"{r.descricao if r else req_id} — {exige}",
                           "tipos": list(r.tipos) if r else []})
            continue
        from funnelforge.pipeline.proveniencia import escopo_do_fato
        abrangencia, uf = escopo_do_fato(fato)
        vinculos.append({"ativo": ativo.pergunta, "papel": papel, "requisito": req_id,
                         "fact_id": fato.fact_id, "url": fato.source_url, "nivel": nivel,
                         "origem": fato.origem,
                         "formula": fato.derivacao.get("formula", ""),
                         "premissas": list(fato.derivacao.get("premissas", [])),
                         "emissor": (fato.proveniencia or {}).get("issuer", ""),
                         "abrangencia": abrangencia, "uf": uf.upper(), "valor": fato.valor,
                         "unidade": fato.unidade,
                         "vigente_desde": fato.vigente_desde.isoformat()
                         if fato.vigente_desde else ""})
    return vinculos, bloqueios, faltas


def cobertura_da_pagina(state: RunState, page: Page, fatos: list[FatoDoDossie],
                        hoje: date | None = None) -> CoberturaDaPagina:
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
    ufs = list(state.plan.jornada.ufs) if state.plan and state.plan.jornada else []
    for ativo in ativos_validos(page):
        if ativo.rule_source_fact_id:
            vinculos, bloqueios, faltas = vincular_ativo(ativo, page, verificados, oficiais,
                                                         ufs, hoje or date.today())
            cob.vinculos += vinculos
            cob.blockers += bloqueios
            cob.vinculos_faltantes += faltas
        elif _norm_url(ativo.fonte_da_regra) not in lastro:
            # LEGADO: card sem o contrato semântico — a URL declarada tem de
            # estar entre as fontes verificadas.
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
        for v in cob.vinculos_faltantes:
            duvida = por_numero[n].jornada.duvida_id
            faltam = [f for f in faltam
                      if not (f["duvida_id"] == duvida and f["requisito"] == v["requisito"])]
            faltam.append({"duvida_id": duvida, "requisito": v["requisito"],
                           "descricao": v["descricao"], "tipos": v["tipos"]})
    return faltam


def compilar_dossie(state: RunState, deps: Any, pesquisar: Pesquisar, *,
                    registrar_canais: Callable[[RunState, Page, Any], None],
                    hoje: date | None = None, hints: list[dict] | None = None,
                    ler_documento: Callable[[str], dict] | None = None) -> DossieDoFunil:
    """Pesquisa única + até duas complementações dirigidas → dossiê fechado.
    Escreve `state.facts[n]` e `state.official_links[n]` das páginas da jornada.

    `hints` (do operador) entram como rodada 0, sem modelo: o código lê o
    documento e confere a afirmação. `ler_documento` lê o conteúdo das fontes
    verificadas para registrar a PROVENIÊNCIA (emissor e escopo) — sem ele, o
    escopo vem do host, como antes."""
    from funnelforge.pipeline.proveniencia import (
        derivar_fatos, proveniencia_do_documento, verificar_hints)
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
    documentos: dict[str, dict] = {}
    recusas: list[dict] = []

    def absorver(resp: RespostaDaPesquisa, rodada: int, faltantes: list[dict] | None) -> None:
        nonlocal conflitos, recusas
        telemetria.append(TelemetriaDaPesquisa(
            rodada=rodada, modelo_pedido=resp.modelo_pedido, modelo_servido=resp.modelo_servido,
            auth_mode=resp.auth_mode, citacoes=len(resp.citacoes),
            prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
            custo_usd=resp.custo_usd, latencia_ms=resp.latencia_ms,
            consultas_de_busca=getattr(resp, "consultas_de_busca", 0),
            finish_reason=getattr(resp, "finish_reason", ""),
            chamadas=list(getattr(resp, "metadados", []) or []),
            faltantes_pedidos=[f"{f['duvida_id']}:{f['requisito']}" for f in (faltantes or [])]))
        if getattr(resp, "defeito", ""):
            raise PesquisaSemResposta(f"rodada {rodada}: {resp.defeito}")
        citacoes.update(_norm_url(c) for c in resp.citacoes)
        novos = [f for f in fatos_da_resposta(resp) if f.fact_id not in fatos]
        verificar_ao_vivo(novos, getattr(deps, "url_verifier", None), hoje)
        for f in novos:
            fatos[f.fact_id] = f
            if ler_documento is not None and f.status == "verified" and not f.proveniencia:
                if f.source_url not in documentos:
                    documentos[f.source_url] = ler_documento(f.source_url)
                doc = documentos[f.source_url]
                if doc.get("ok"):
                    f.proveniencia = proveniencia_do_documento(f.source_url, doc)
        for fid in [k for k, f in fatos.items() if f.origem == "derivado"]:
            del fatos[fid]                       # derivado é recalculado do zero
        for f in fatos.values():                 # conflito é recalculado do zero
            if f.status == "conflict":
                f.status, f.motivo_do_status = "verified", ""
        marcar_conflitos(list(fatos.values()))
        # Canais oficiais a partir dos fatos LITERAIS; depois o derivado (que
        # precisa saber o que é oficial); depois a cobertura com tudo.
        for page in pages:
            state.facts[page.page_number] = _research_facts(
                _fatos_para_a_pagina(list(fatos.values()), page))
            state.official_links.pop(page.page_number, None)
            registrar_canais(state, page, deps)
        oficiais_agora = [u for p in pages for u in (state.official_links.get(p.page_number)
                                                       or [])]
        derivados, recusas = derivar_fatos(list(fatos.values()), pages, hoje,
                                           lambda f: _fato_oficial(f, oficiais_agora))
        for f in derivados:
            fatos[f.fact_id] = f
        for f in fatos.values():
            if f.status == "conflict":
                f.status, f.motivo_do_status = "verified", ""
        conflitos = marcar_conflitos(list(fatos.values()))
        for page in pages:
            state.facts[page.page_number] = _research_facts(
                _fatos_para_a_pagina(list(fatos.values()), page))
            coberturas[page.page_number] = cobertura_da_pagina(
                state, page, _fatos_para_a_pagina(list(fatos.values()), page), hoje)
            for rec in recusas:
                if rec["pagina"] == page.page_number:
                    coberturas[page.page_number].blockers.append(
                        f"derivado '{rec['requisito']}' recusado: {rec['motivo']}")
                    coberturas[page.page_number].ready_to_write = False

    if hints:
        absorver(verificar_hints(hints, ler_documento), 0, None)
    for rodada in range(1, MAX_RODADAS_DE_COMPLEMENTO + 2):
        absorver(pesquisar(assunto, spec, faltantes), rodada, faltantes)
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
    for url in sorted({f.source_url for f in fatos if f.source_url}):
        dos = [f for f in fatos if f.source_url == url]
        fontes.append(FonteDoDossie(
            proveniencia=next((f.proveniencia for f in dos if f.proveniencia), {}),
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


def _abrangencia_do_fato(f: dict) -> str:
    from funnelforge.pipeline.proveniencia import escopo_do_fato
    a, uf = escopo_do_fato(FatoDoDossie.model_validate(f))
    return f"regional {uf.upper()}" if a == "regional" else ("nacional" if a == "nacional" else "")


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
                   "abrangencia": _abrangencia_do_fato(por_id[i]),
                   "derivacao": (por_id[i].get("derivacao") or {}).get("formula", ""),
                   "premissas": list((por_id[i].get("derivacao") or {}).get("premissas", [])),
                   "emissor": (por_id[i].get("proveniencia") or {}).get("issuer", ""),
                   "vigente_desde": por_id[i].get("vigente_desde") or ""}
                  for i in pagina.get("fatos_verificados", []) if i in por_id],
        "urls_oficiais": list(pagina.get("urls_oficiais") or []),
        "vinculos": list((pagina.get("cobertura") or {}).get("vinculos") or []),
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
