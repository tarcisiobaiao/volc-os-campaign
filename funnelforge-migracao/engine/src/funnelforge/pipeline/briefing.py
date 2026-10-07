"""O BRIEFING PERSUASIVO de cada página (ramo `editorial_v2`, etapa B4).

## O defeito que isto conserta

O redator recebia H1, objetivo, esqueleto, keywords e fatos — e mais nada sobre
o leitor. O tom e o avatar que o arquiteto do funil escreveu morriam na ponte
(`briefing_volc` os guardava no plano e nenhum prompt os lia); a tensão medida
na validação virava instrução de "não aumentar a temperatura"; os termos de
busca nunca chegavam. O texto saía correto e genérico.

## O que o passo faz

Uma chamada de LLM por página, entre a pesquisa e a redação, que devolve o
briefing-v1: a dúvida real, a intenção (sempre hipótese), o que o leitor já
sabe e quer, as objeções com resposta, a promessa e onde ela é cumprida, a
entrega concreta, os benefícios demonstráveis (só com fato e limite), os
próximos passos com o rótulo da intenção do leitor, os limites, as hipóteses e
o tom proporcional. Cada afirmação diz de onde veio.

## O que é do código, não do modelo

- a régua (`referencias_do_briefing`): quais fatos, termos, perguntas,
  destinos e campos do arquiteto existem — o contrato confere contra ela;
- o que já é dado: a página, os termos observados (com estado), o briefing do
  arquiteto (tom, avatar, tensão, contrato editorial), a leitura e o anúncio.
  `normalizar_briefing` os escreve POR CIMA do que o modelo mandar.

## Falha fecha

Briefing reprovado pelo contrato depois das retentativas, erro do provedor ou
passo sem configuração -> `briefing_pN` FAILED com `briefing_indisponivel`. A
redação não começa (`step_write` confere) e nada é gasto com ela.
"""
from __future__ import annotations

import json
from typing import Any

from funnelforge.domain.models import (
    Issue,
    Page,
    PageRole,
    RunState,
    StepResult,
    StepStatus,
    effective_role,
)
from funnelforge.pipeline.inventario import InventarioFactual, montar_inventario
from funnelforge.pipeline.runner import LLMStepError
from funnelforge.pipeline.validators.briefing_contract import (
    VERSAO,
    numeros,
    parse_briefing,
    validar_briefing,
)
from funnelforge.prompts import render

_PAPEL_ROTULO = {
    PageRole.LP: "página de pouso (LP): a primeira que o leitor vê depois do anúncio ou da busca",
    PageRole.PRESELL: "guia de escolha (pré-sell): ajuda o leitor a achar o caminho do caso dele",
    PageRole.SOLUTION: "guia de solução: resolve uma dúvida específica por inteiro",
}


# ---------------------------------------------------------------------------
# a régua da página
# ---------------------------------------------------------------------------

def destinos_da_pagina(state: RunState, page: Page) -> list[dict]:
    """Os destinos que um próximo passo desta página PODE ter: as rotas do grafo
    (funil e recirculação) e os canais oficiais que a pesquisa verificou.

    O canal oficial entra pelos `official_links`, não pela rota: a aresta
    `external_official` só é ligada no `_write_ctx`, depois deste passo."""
    plano = state.plan
    por_slug = {p.slug: p for p in (plano.pages if plano else [])}
    saida: list[dict] = []
    vistos: set[str] = set()

    def _add(item: dict) -> None:
        chave = str(item["destino"]).rstrip("/")
        if chave and chave not in vistos:
            vistos.add(chave)
            item["id"] = f"d{len(saida) + 1}"
            saida.append(item)

    for rota in page.routes:
        if rota.kind == "funnel":
            alvo = por_slug.get(rota.target)
            entrega = ""
            if alvo is not None:
                entrega = (alvo.editorial.useful_delivery if alvo.editorial
                           else alvo.emotional_objective)
            _add({"tipo": "funnel", "destino": rota.target,
                  "h1": alvo.h1_title if alvo else "", "entrega": entrega or "",
                  "rotulo_do_arquiteto": rota.anchor, "motivo": rota.reason})
        elif rota.kind == "cross_funnel":
            _add({"tipo": "cross_funnel", "destino": rota.target, "h1": "",
                  "entrega": "outro guia deste site, sobre um assunto vizinho",
                  "rotulo_do_arquiteto": rota.anchor, "motivo": rota.reason})
    for url in state.official_links.get(page.page_number, []) or []:
        _add({"tipo": "external_official", "destino": url, "h1": "",
              "entrega": "canal oficial verificado na pesquisa desta página (outro site)",
              "rotulo_do_arquiteto": "", "motivo": ""})
    return saida


def campos_do_arquiteto(state: RunState, page: Page) -> dict[str, str]:
    """Os campos que o ARQUITETO do funil definiu para esta página e que o
    briefing pode citar como `briefing_do_arquiteto` (só os não vazios)."""
    plano = state.plan
    campos = {
        "h1": page.h1_title,
        "objetivo": page.emotional_objective,
        "estrutura": "; ".join(page.main_content_structure),
        "keywords": ", ".join(page.target_keywords),
        "tone_voice": plano.tone_voice if plano else "",
        "avatar_summary": plano.avatar_summary if plano else "",
        "editorial": (json.dumps(page.editorial.model_dump(), ensure_ascii=False)
                      if page.editorial else ""),
    }
    return {k: v for k, v in campos.items() if (v or "").strip()}


def referencias_do_briefing(state: RunState, page: Page,
                            inventario: InventarioFactual) -> dict:
    """A régua contra a qual `briefing_contract` confere o briefing."""
    arquiteto = campos_do_arquiteto(state, page)
    destinos = destinos_da_pagina(state, page)
    termos = (list(inventario.termos_de_busca.amostra)
              if inventario.termos_de_busca.estado == "presente" else [])
    anuncio = inventario.anuncio
    textos_do_anuncio = (list(anuncio.titulos) + list(anuncio.descricoes)
                         if anuncio.estado == "presente" else [])
    fatos = {}
    for f in inventario.fatos:
        fatos[f.id] = {
            "tipo": f.tipo, "texto": f.texto, "citavel": f.citavel,
            "verificada_ao_vivo": f.verificada_ao_vivo,
            "numeros": sorted(numeros(" ".join(
                (f.texto, f.dispositivo, str(f.vigente_desde or ""))))),
        }
    permitidos: set[str] = set()
    for f in fatos.values():
        permitidos |= set(f["numeros"])
    for texto in (*termos, *inventario.leitura.perguntas_paa, *textos_do_anuncio,
                  *arquiteto.values(), *(d["h1"] for d in destinos),
                  *(d["entrega"] for d in destinos)):
        permitidos |= numeros(texto)
    urls = ([s.url for s in inventario.fontes] + list(inventario.canais_oficiais)
            + [d["destino"] for d in destinos if str(d["destino"]).startswith("http")])
    return {
        "fatos": fatos,
        "termos": termos,
        "paa": list(inventario.leitura.perguntas_paa),
        "tensao": inventario.leitura.tensao is not None,
        "anuncio": len(textos_do_anuncio),
        "arquiteto": sorted(arquiteto),
        "destinos": {d["destino"]: d for d in destinos},
        "tem_rotas": bool(destinos),
        "urls": urls,
        "numeros_permitidos": sorted(permitidos),
        "tom_do_arquiteto": arquiteto.get("tone_voice", ""),
    }


# ---------------------------------------------------------------------------
# o inventário como o modelo do briefing o lê
# ---------------------------------------------------------------------------

def _sim(valor: bool | None) -> str:
    return "sim" if valor else ("não" if valor is False else "não declarado")


def inventario_para_o_briefing(inv: InventarioFactual) -> str:
    linhas: list[str] = ["FATOS (cite pelos ids em \"ref\" e em \"fatos\"):"]
    if not inv.fatos:
        linhas.append("  NENHUM fato nesta página: sem benefício com fato, sem número.")
    for f in inv.fatos:
        partes = [f"  - {f.id} [{f.tipo}] {f.texto}"]
        if f.origem == "fatos_verificados":
            partes.append(f"fonte verificada ao vivo: {_sim(f.verificada_ao_vivo)}")
            if f.vigente_desde:
                partes.append(f"vigente desde {f.vigente_desde.isoformat()}")
        else:
            partes.append("observação qualitativa (não autoriza número)")
        if f.escopo:
            partes.append(f"escopo: {f.escopo}")
        if f.citavel is False:
            partes.append("NÃO CITÁVEL (fonte contraditória ou instável)")
        if f.tipo_origem == "regra_legado":
            partes.append("tipo atribuído pela regra de legado")
        linhas.append(" — ".join(partes))
    if inv.fontes:
        linhas.append("FONTES:")
        for s in inv.fontes:
            linhas.append(f"  - {s.id} {s.url} ({s.papel}; "
                          f"{'respondeu a uma visita real' if s.resolvida else 'não verificada ao vivo'})")
    linhas.append("CANAIS OFICIAIS VERIFICADOS: "
                  + (", ".join(inv.canais_oficiais) if inv.canais_oficiais else "nenhum"))
    tb = inv.termos_de_busca
    if tb.estado == "presente":
        linhas.append(f"TERMOS DE BUSCA OBSERVADOS (janela {tb.janela}; amostra de "
                      f"{len(tb.amostra)} de {tb.total_na_fonte}; "
                      f"{tb.descartados_por_dado_pessoal} descartados por dado pessoal):")
        for d in tb.amostra_detalhe:
            linhas.append(f"  - \"{d['termo']}\" (cliques {d['cliques']}, "
                          f"impressões {d['impressoes']})")
    elif tb.estado == "vazio_confirmado":
        linhas.append(f"TERMOS DE BUSCA: consulta feita em {tb.janela}: 0 termos. "
                      "Não use 'termo:' como evidência.")
    else:
        linhas.append(f"TERMOS DE BUSCA: NÃO COLETADOS — {tb.motivo_ausencia}. Não presuma "
                      "termos; não use 'termo:' como evidência.")
    leitura = inv.leitura
    if leitura.perguntas_paa:
        linhas.append("PERGUNTAS REAIS DOS LEITORES (PAA; cite como paa:<número>):")
        linhas += [f"  {i}. {p}" for i, p in enumerate(leitura.perguntas_paa, start=1)]
    else:
        linhas.append("PERGUNTAS REAIS DOS LEITORES (PAA): nenhuma coletada.")
    if leitura.tensao:
        linhas.append(f"TENSÃO OBSERVADA NA VALIDAÇÃO (é hipótese; cite como tensao): "
                      f"\"{leitura.tensao.get('frase', '')}\" (evidência: "
                      f"{leitura.tensao.get('evidencia') or 'não informada'})")
    anuncio = inv.anuncio
    if anuncio.estado == "presente":
        textos = list(anuncio.titulos) + list(anuncio.descricoes)
        linhas.append("ANÚNCIO QUE TRAZ O LEITOR A ESTA PÁGINA (cite como anuncio:<número>):")
        linhas += [f"  {i}. {t}" for i, t in enumerate(textos, start=1)]
    else:
        linhas.append(f"ANÚNCIO: ausente ({anuncio.motivo_ausencia}).")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# normalização e o texto que o redator recebe
# ---------------------------------------------------------------------------

def normalizar_briefing(dados: dict, state: RunState, page: Page,
                        inventario: InventarioFactual,
                        avisos: list[Issue] | None = None) -> dict:
    """O briefing VALIDADO, com o que é dado escrito pelo código por cima."""
    briefing = dict(dados)
    plano = state.plan
    briefing["versao"] = VERSAO
    briefing["pagina"] = {"numero": page.page_number, "slug": page.slug,
                          "papel": effective_role(page).value, "h1": page.h1_title}
    intencao = dict(briefing.get("intencao") or {})
    tb = inventario.termos_de_busca
    intencao["termos_observados"] = {
        "estado": tb.estado, "amostra": list(tb.amostra), "janela": tb.janela,
        "total_na_fonte": tb.total_na_fonte, "motivo_ausencia": tb.motivo_ausencia,
    }
    briefing["intencao"] = intencao
    briefing["briefing_do_arquiteto"] = {
        "tone_voice": plano.tone_voice if plano else "",
        "avatar_summary": plano.avatar_summary if plano else "",
        "objetivo_da_pagina": page.emotional_objective,
        "editorial": page.editorial.model_dump() if page.editorial else None,
        "tensao": inventario.leitura.tensao,
    }
    briefing["leitura"] = {"perguntas_paa": list(inventario.leitura.perguntas_paa),
                           "tensao": inventario.leitura.tensao}
    briefing["anuncio"] = inventario.anuncio.model_dump()
    briefing["avisos"] = [{"code": a.code, "message": a.message} for a in (avisos or [])]
    return briefing


def _base(obj: Any) -> str:
    """O rótulo de procedência que acompanha cada linha do briefing."""
    if not isinstance(obj, dict):
        return ""
    base = obj.get("base")
    if base == "fato":
        return f"[fato {', '.join(str(r) for r in obj.get('ref') or [])}]"
    if base == "hipotese":
        ev = ", ".join(str(e) for e in obj.get("evidencia") or [])
        return f"[hipótese — não afirme como fato; evidência: {ev}]"
    if base == "briefing_do_arquiteto":
        return "[do arquiteto do funil]"
    if base == "identidade":
        return "[identidade do site]"
    return ""


def _t(obj: Any, chave: str = "texto") -> str:
    return str(obj.get(chave) or "").strip() if isinstance(obj, dict) else ""


def briefing_para_o_redator(briefing: dict) -> str:
    """O briefing como o redator do ramo novo o lê: texto, cada ponto com a sua
    procedência. Hipótese aparece COMO hipótese — nunca como fato."""
    b = briefing
    intencao = b.get("intencao") or {}
    leitor = b.get("leitor") or {}
    linhas: list[str] = [
        f"BRIEFING DESTA PÁGINA ({b.get('versao', VERSAO)}) — escreva a partir dele.",
        "Procedência entre colchetes: [fato nX] = fato da base factual; [hipótese] = "
        "inferência que orienta a ênfase mas NUNCA vira afirmação; [do arquiteto do "
        "funil] = o que o plano do funil definiu.",
        "",
        f"PERGUNTA DO LEITOR: {_t(intencao.get('pergunta_do_leitor'))} "
        f"{_base(intencao.get('pergunta_do_leitor'))}",
        f"INTENÇÃO PROVÁVEL DA BUSCA: {_t(intencao.get('intencao_real_da_busca'))} "
        f"{_base(intencao.get('intencao_real_da_busca'))}",
    ]
    termos = intencao.get("termos_observados") or {}
    if termos.get("estado") == "presente":
        amostra = ", ".join(f"\"{t}\"" for t in termos.get("amostra") or [])
        linhas.append(f"TERMOS DE BUSCA OBSERVADOS ({termos.get('janela')}): {amostra}")
    elif termos.get("estado") == "vazio_confirmado":
        linhas.append(f"TERMOS DE BUSCA: consulta feita em {termos.get('janela')}: 0 termos.")
    else:
        linhas.append(f"TERMOS DE BUSCA: NÃO COLETADOS — {termos.get('motivo_ausencia')}. "
                      "Não presuma termos.")
    linhas += [
        f"O QUE O LEITOR JÁ SABE: {_t(leitor.get('conhecimento_previo'))} "
        f"{_base(leitor.get('conhecimento_previo'))}",
        f"O QUE ELE QUER RESOLVER: {_t(leitor.get('desejo_ou_problema'))} "
        f"{_base(leitor.get('desejo_ou_problema'))}",
    ]
    objecoes = leitor.get("objecoes") or []
    if objecoes:
        linhas.append("DÚVIDAS E OBJEÇÕES QUE ESTA PÁGINA RESPONDE:")
        for obj in objecoes:
            linhas.append(f"  - objeção: {_t(obj.get('objecao'))} {_base(obj.get('objecao'))}")
            linhas.append(f"    resposta: {_t(obj.get('resposta'))} {_base(obj.get('resposta'))}")
    promessa = b.get("promessa_da_pagina") or {}
    linhas.append(f"PROMESSA DESTA PÁGINA: {_t(promessa)} {_base(promessa)} — cumprida em: "
                  f"{_t(promessa, 'cumprida_em')}")
    entrega = b.get("entrega_concreta") or {}
    linhas.append(f"ENTREGA CONCRETA ({entrega.get('formato', '')}):")
    for item in entrega.get("itens") or []:
        linhas.append(f"  - {_t(item)} {_base(item)}")
    beneficios = b.get("beneficios") or []
    if beneficios:
        linhas.append("BENEFÍCIOS DEMONSTRÁVEIS (afirme só estes, sempre com o limite):")
        for ben in beneficios:
            linhas.append(f"  - {_t(ben)} [fato {', '.join(ben.get('fatos') or [])}] — "
                          f"limite: {_t(ben, 'limite')}")
    else:
        linhas.append("BENEFÍCIOS DEMONSTRÁVEIS: nenhum com fato — não prometa benefício.")
    passos = b.get("proximos_passos") or []
    if passos:
        linhas.append("PRÓXIMOS PASSOS (rótulo com a intenção do leitor; o destino entrega isso):")
        for p in passos:
            linhas.append(
                f"  - [{p.get('tipo')}] {p.get('destino')} — rótulo: \"{_t(p, 'rotulo')}\" — "
                f"intenção do leitor: {_t(p.get('intencao_do_leitor'))} "
                f"{_base(p.get('intencao_do_leitor'))} — o que encontra lá: "
                f"{_t(p.get('o_que_encontra'))} {_base(p.get('o_que_encontra'))}")
    limites = b.get("limites") or []
    if limites:
        linhas.append("LIMITES (não ultrapasse):")
        for lim in limites:
            linhas.append(f"  - {_t(lim)} {_base(lim)}")
    hipoteses = b.get("hipoteses") or []
    if hipoteses:
        linhas.append("HIPÓTESES (orientam a ênfase; nunca as afirme como fato):")
        for h in hipoteses:
            extra = f" — como confirmar: {_t(h, 'como_confirmar')}" if _t(h, "como_confirmar") else ""
            linhas.append(f"  - {h.get('id', '')} ({h.get('sobre', '')}): {_t(h)}{extra}")
    tom = b.get("tom") or {}
    linhas.append(f"TOM: registro {_t(tom, 'registro')}; intensidade {_t(tom, 'intensidade')}; "
                  f"por quê: {_t(tom, 'justificativa')} {_base(tom)}")
    arq = b.get("briefing_do_arquiteto") or {}
    linhas.append("BRIEFING DO ARQUITETO DO FUNIL (quem é o leitor e a voz pedida; "
                  "considere, não copie):")
    linhas.append(f"  - tom e voz pedidos: {arq.get('tone_voice') or 'não definido'}")
    linhas.append(f"  - leitor: {arq.get('avatar_summary') or 'não definido'}")
    if arq.get("objetivo_da_pagina"):
        linhas.append(f"  - objetivo desta página: {arq['objetivo_da_pagina']}")
    tensao = arq.get("tensao") or {}
    if tensao:
        linhas.append(f"  - tensão observada na validação (hipótese): \"{tensao.get('frase', '')}\" "
                      f"(evidência: {tensao.get('evidencia') or 'não informada'})")
    editorial = arq.get("editorial") or {}
    if editorial:
        linhas.append(f"  - contrato editorial: dúvida \"{editorial.get('reader_question', '')}\"; "
                      f"entrega \"{editorial.get('useful_delivery', '')}\"")
    paa = (b.get("leitura") or {}).get("perguntas_paa") or []
    if paa:
        linhas.append("PERGUNTAS REAIS DOS LEITORES (PAA):")
        linhas += [f"  {i}. {p}" for i, p in enumerate(paa, start=1)]
    anuncio = b.get("anuncio") or {}
    if anuncio.get("estado") == "presente":
        textos = list(anuncio.get("titulos") or []) + list(anuncio.get("descricoes") or [])
        linhas.append("PROMESSA DO ANÚNCIO QUE TRAZ O LEITOR (a página precisa cumpri-la): "
                      + " | ".join(textos))
    return "\n".join(linhas)


def passos_por_destino(briefing: dict | None) -> dict[str, dict]:
    """{destino: {rotulo, intencao, o_que_encontra}} para os redatores v2."""
    saida: dict[str, dict] = {}
    for p in (briefing or {}).get("proximos_passos") or []:
        destino = str(p.get("destino") or "").strip().rstrip("/")
        if destino and destino not in saida:
            saida[destino] = {"rotulo": _t(p, "rotulo"),
                              "intencao": _t(p.get("intencao_do_leitor")),
                              "o_que_encontra": _t(p.get("o_que_encontra"))}
    return saida


# ---------------------------------------------------------------------------
# o passo
# ---------------------------------------------------------------------------

def _falha(state: RunState, key: str, mensagem: str,
           pago: StepResult | None = None) -> None:
    res = pago or StepResult(step=key, status=StepStatus.FAILED, attempts=0)
    res.status = StepStatus.FAILED
    res.issues = list(res.issues) + [Issue(code="briefing_indisponivel", message=mensagem)]
    state.step_status[key] = res


def _gravar(deps: Any, state: RunState, page: Page, nome: str, conteudo: str) -> None:
    try:
        pasta = deps.runner.runs_dir / state.run_id
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"p{page.page_number}.{nome}").write_text(conteudo, encoding="utf-8")
    except OSError:
        pass  # artefato de auditoria nunca derruba a página


def step_briefing(state: RunState, page: Page, deps: Any) -> None:
    """Gera, valida e guarda o briefing-v1 desta página. Falha fecha."""
    key = f"briefing_p{page.page_number}"
    state.briefings.pop(page.page_number, None)
    pesquisa = state.step_status.get(f"research_p{page.page_number}")
    if pesquisa is not None and pesquisa.status is StepStatus.FAILED:
        _falha(state, key, "Briefing não iniciado: a pesquisa factual não passou pelo gate.")
        return
    cfg = deps.settings.steps.get("briefing")
    if cfg is None:
        _falha(state, key, "Passo 'briefing' ausente na configuração (steps.briefing): "
                           "a página não será escrita e nada foi gasto.")
        return
    # O contrato vale SEMPRE, mesmo que alguém o tire da lista do config; e o
    # briefing não busca na web — os fatos vêm da pesquisa desta página.
    cfg = cfg.model_copy(update={
        "validators": list(dict.fromkeys([*(cfg.validators or []), "briefing_contract"])),
        "web_search": False,
    })
    inventario = montar_inventario(state, page)
    ref = referencias_do_briefing(state, page, inventario)
    _gravar(deps, state, page, "inventario.json", inventario.model_dump_json(indent=2))
    plano = state.plan
    papel = effective_role(page)
    prompt = render(
        "briefing",
        pagina={"numero": page.page_number, "slug": page.slug, "papel": papel.value,
                "papel_rotulo": _PAPEL_ROTULO[papel], "h1": page.h1_title,
                "objetivo": page.emotional_objective,
                "estrutura": list(page.main_content_structure),
                "keywords": ", ".join(page.target_keywords)},
        editorial=page.editorial.model_dump() if page.editorial else {},
        arquiteto={"tone_voice": plano.tone_voice if plano else "",
                   "avatar_summary": plano.avatar_summary if plano else ""},
        inventario_texto=inventario_para_o_briefing(inventario),
        destinos=destinos_da_pagina(state, page),
        refs_arquiteto=["arquiteto:" + c for c in ref["arquiteto"]],
        termos_observados=ref["termos"],
    )
    try:
        texto, res = deps.runner.run_llm_step(
            key, cfg, [{"role": "user", "content": prompt}],
            ctx={"briefing_ref": ref}, run_id=state.run_id)
    except LLMStepError as exc:
        _falha(state, key, f"Briefing indisponível: {exc.motivo}. A página não será escrita.",
               pago=exc.step_result)
        return
    if res.status is StepStatus.FAILED:
        _falha(state, key, "Briefing reprovado pelo contrato depois das retentativas: a "
                           "página não será escrita (nada gasto com redação).", pago=res)
        return
    try:
        dados = parse_briefing(texto)
    except (ValueError, json.JSONDecodeError) as exc:  # o runner já validou; defesa
        _falha(state, key, f"Briefing ilegível: {exc}.", pago=res)
        return
    erros, avisos = validar_briefing(dados, ref)
    if erros:  # não acontece depois do runner; se acontecer, fecha
        res.issues = list(res.issues) + erros
        _falha(state, key, "Briefing incoerente com o contrato.", pago=res)
        return
    briefing = normalizar_briefing(dados, state, page, inventario, avisos)
    state.briefings[page.page_number] = briefing
    res.issues = list(res.issues) + avisos
    state.step_status[key] = res
    _gravar(deps, state, page, "briefing.json",
            json.dumps(briefing, ensure_ascii=False, indent=2))
