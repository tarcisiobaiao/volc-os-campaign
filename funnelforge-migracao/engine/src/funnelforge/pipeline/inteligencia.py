"""Duas passagens no motor existente: intenção -> arquitetura -> fatos -> pacote."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict
from datetime import date

from funnelforge.domain.dossie import sha256_canonico, texto_normal
from funnelforge.domain.models import (
    BriefDoFunil, DuvidaDoBrief, JornadaDaPagina, RequisitoFactual,
    Issue, SinalEmocional, StepResult, StepStatus,
)


def chave_da_pergunta(texto):
    # Conservador: agrupa flexões/ordem e sinônimos estreitos; não decide fatos.
    t = texto_normal(texto)
    t = re.sub(r"\b(elegivel|elegibilidade)\b", "direito", t)
    return " ".join(sorted(set(t.split()) - {"o", "a", "os", "as", "de", "do", "da", "ao", "eu"}))


def compilar_brief(card: dict, paa: dict, pesquisa: dict | None = None, *, provider=None) -> BriefDoFunil:
    tema = card.get("main_keyword") or card.get("keyword") or card.get("entidade") or ""
    leitura = card.get("contexto_de_leitura") or {}
    sinais = [{"tipo": "paa", "texto": q, "origem": paa["origem"], "factual": False}
              for q in paa["perguntas"]]
    for campo in ("search_terms", "autocomplete", "related_queries", "expansion_hooks"):
        for item in card.get(campo) or []:
            texto = item.get("termo") or item.get("keyword") if isinstance(item, dict) else item
            if isinstance(texto, str):
                sinais.append({"tipo": campo, "texto": texto, "origem": "card." + campo,
                               "factual": False})
    grupos = {}
    for s in sinais:
        chave = chave_da_pergunta(s["texto"])
        if chave:
            grupos.setdefault(chave, []).append(s)
    duvidas = []
    for chave, grupo in grupos.items():
        qid = "q_" + sha256_canonico(chave)[:12]
        duvidas.append(DuvidaDoBrief(
            jornada=JornadaDaPagina(duvida_id=qid, pergunta_principal=grupo[0]["texto"],
                trabalho_do_leitor=grupo[0]["texto"], requisitos=[RequisitoFactual(
                    id=qid + ".resposta", descricao="Provar a resposta a: " + grupo[0]["texto"])]),
            variantes=sorted(set(s["texto"] for s in grupo)),
            prioridade=max((card.get("volumes") or {}).get(s["texto"]) or 0 for s in grupo),
            evidencia_demanda=grupo, confianca="media"))
    duvidas.sort(key=lambda d: (-d.prioridade, d.jornada.duvida_id))
    from funnelforge.adapters.decisao_intencao import HeuristicaDeIntencao
    decisoes = (provider or HeuristicaDeIntencao()).classificar(
        [d.jornada.pergunta_principal for d in duvidas],
        contexto={"tema": tema, "pais": card.get("country") or "",
                  "idioma": card.get("native_language") or "",
                  "duvida_ids": [d.jornada.duvida_id for d in duvidas]})
    sinais_emocionais = (decisoes.get("perfil_emocional") or {}).get("sinais") or []
    for indice, (d, formato) in enumerate(zip(duvidas, decisoes["formatos"])):
        d.formato = formato
        if indice < len(sinais_emocionais):
            d.sinal_emocional = SinalEmocional.model_validate(sinais_emocionais[indice])
    dados = pesquisa or {}
    citadas = set(dados.get("citacoes") or [])
    fatos = [dict(f, estado="a_conferir") for f in (dados.get("dados") or {}).get("fatos", [])
             if f.get("fonte") in citadas]
    contexto = {k: card[k] for k in ("reasoning", "description", "editorial_context",
                "historico", "contexto_de_busca", "contexto_de_anuncio", "fatos_existentes")
                if k in card}
    historico = contexto.get("historico")
    if isinstance(historico, dict) and isinstance(historico.get("arquitetura_referencia"), dict):
        arq = historico["arquitetura_referencia"]
        contexto["historico"] = {k: v for k, v in historico.items() if k != "arquitetura_referencia"}
        contexto["historico"]["paginas_anteriores"] = [{
            "numero": p.get("page_number"), "titulo": p.get("h1_title"), "slug": p.get("slug"),
            "cta": (p.get("editorial") or {}).get("cta_label"),
            "jornada": {k: v for k, v in (p.get("jornada") or {}).items() if k in (
                "duvida_id", "pergunta_principal", "resposta_imediata", "proxima_duvida",
                "ja_resolvido", "valor", "saida_oficial")}}
            for p in arq.get("pages", [])]
    recibo_decisao = {k: v for k, v in decisoes.items() if k != "perfil_emocional"}
    brief = BriefDoFunil(
        intencao_principal=tema, trabalho_do_leitor=card.get("trabalho_do_leitor") or tema,
        consciencia=card.get("consciencia") or "nao_observada",
        entidade=str(card.get("entidade") or tema), pais=card.get("country") or "",
        idioma=card.get("native_language") or "", duvidas=duvidas, sinais=sinais,
        perfil_emocional=decisoes.get("perfil_emocional"),
        contexto={**contexto, "decisao_intencao": recibo_decisao,
                  "fontes_encontradas": sorted(citadas)},
        dores_observadas=leitura.get("dores_observadas") or [],
        desejos_observados=leitura.get("desejos_observados") or [], fatos_existentes=fatos,
        lacunas=(["PAA ausente; não impede arquitetura"] if not paa["perguntas"] else [])
                + (["pesquisa indisponível: " + dados["defeito"]] if dados.get("defeito") else []))
    brief.sha256 = sha256_canonico(brief.model_dump(exclude={"sha256"}))
    return brief


def preparar_inteligencia(state, deps, card):
    from funnelforge.adapters.attention_matrix import perguntas
    from funnelforge.adapters.research_perplexity import pesquisar_funil
    from funnelforge.pipeline.dossie import RespostaDaPesquisa
    paa = perguntas(card, deps.runner.runs_dir / "cache_paa", cliente=deps.attention_matrix)
    brief = compilar_brief(card, paa)
    spec = [{"duvida_id": d.jornada.duvida_id, "pergunta": d.jornada.pergunta_principal,
             "promessa": "", "requisitos": [r.model_dump() for r in d.jornada.requisitos]}
            for d in brief.duvidas]
    if not spec:
        spec = [{"duvida_id": "raiz", "pergunta": brief.intencao_principal, "promessa": "",
                 "requisitos": [{"id": "raiz.contexto", "descricao": brief.intencao_principal,
                                  "tipos": ["processo", "condicao", "orgao"]}]}]
    cfg = deps.settings.steps["dossie"]
    if cfg.fallbacks:
        raise ValueError("pesquisa pré-arquitetura não aceita fallback")
    try:
        resp = pesquisar_funil(deps.llm, cfg, brief.intencao_principal, spec)
    except Exception as exc:
        from funnelforge.pipeline.budget import OrcamentoEstourado
        if isinstance(exc, OrcamentoEstourado):
            raise
        resp = RespostaDaPesquisa(dados={"fatos": []}, citacoes=[], defeito=type(exc).__name__)
    state.pesquisa_pre_arquitetura = asdict(resp)
    from funnelforge.pipeline.pipeline import _base_do_modelo
    if resp.modelo_servido and _base_do_modelo(resp.modelo_servido) != _base_do_modelo(cfg.model):
        raise ValueError("pesquisa pré-arquitetura recebeu modelo diferente do solicitado")
    from funnelforge.adapters.decisao_intencao import JevDeIntencao
    state.brief_pre_arquitetura = compilar_brief(card, paa, asdict(resp), provider=
        JevDeIntencao(enabled=deps.settings.run.jev_enabled))
    state.step_status["inteligencia"] = StepResult(
        step="inteligencia", status=StepStatus.OK, model_requested=resp.modelo_pedido,
        model_used=resp.modelo_servido, auth_mode=resp.auth_mode,
        attempts=len(resp.metadados) or 1, latency_ms=resp.latencia_ms,
        prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
        cost_usd=resp.custo_usd, issues=[Issue(code="paa", message=json.dumps(paa, ensure_ascii=False))])


def mensagens_do_arquiteto(brief):
    from funnelforge.adapters.attention_matrix import modulo_do_repo
    prompt = modulo_do_repo("backend/app/n8n_prompts/funnel_builder.py")
    return [{"role": "system", "content": prompt.FUNNEL_ARCHITECT_SYSTEM_MESSAGE},
            {"role": "user", "content": prompt.build_funnel_architect_user(
                pais=brief.pais, tema=brief.intencao_principal, lingua=brief.idioma,
                data_atual=date.today().isoformat(), supporting_data="Contexto e proveniência estão no brief_pre_arquitetura abaixo.",
                user_questions="\n".join(d.jornada.pergunta_principal for d in brief.duvidas),
                brief_pre_arquitetura=brief.model_dump())}]


def congelar_pacotes(state, deps):
    from funnelforge.pipeline.jornada import contexto_de_jornada
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    from funnelforge.pipeline.briefing import destinos_da_pagina
    if state.pacotes:
        if set(state.pacotes) != {p.page_number for p in state.plan.pages}:
            raise ValueError("conjunto de pacotes congelados incompleto")
        for p in state.plan.pages:
            pacote = pacote_conferido(state, p)
            if pacote["factual"] != projecao_para_o_prompt(state.dossie, p.page_number):
                raise ValueError("evidência mudou depois do congelamento")
        return
    pasta = deps.runner.runs_dir / state.run_id
    pasta.mkdir(parents=True, exist_ok=True)
    pacotes = {}
    for p in state.plan.pages:
        from funnelforge.pipeline import steps as st
        from funnelforge.pipeline.routing import resolve_page_links
        ctx = st._write_ctx(state, p, deps)
        j = contexto_de_jornada(state.plan, p, state.dossie)
        factual = projecao_para_o_prompt(state.dossie, p.page_number)
        estado = factual.get("estado", "review")
        pacote = {"page_number": p.page_number, "pagina": p.model_dump(mode="json"),
                  "jornada": j, "factual": factual,
                  "estado": "human_review" if estado == "review" else estado,
                  "destinos": destinos_da_pagina(state, p),
                  "links": resolve_page_links(p, deps.settings,
                                              authorized_external=ctx["official_links"]),
                  "dominio": deps.settings.site.domain,
                  "total_pages": state.plan.total_pages,
                  "autor": deps.settings.site.author_name,
                  "credencial": deps.settings.site.author_credential,
                  "cnpj": deps.settings.site.cnpj,
                  "data": date.today().isoformat(), "tom": state.plan.tone_voice, "avatar": state.plan.avatar_summary,
                  "screenshot": p.jornada.screenshot_necessario,
                  "imagem": p.jornada.imagem_necessaria, "schema": p.jornada.schema_tipos,
                  "restricoes": ["Não redesenhar a jornada ou pesquisar. Não inventar fatos, "
                                  "ferramentas, URLs ou trocar a próxima dúvida.",
                                  "Use somente fatos permitidos; remova blocos desativados."]}
        # Reusa o fallback textual do ativo; nunca inventa ferramenta no writer.
        dossier = next((d for d in state.dossie.get("paginas", [])
                        if d["page_number"] == p.page_number), {})
        pacote["evidencia_por_requisito"] = (dossier.get("cobertura") or {}).get("requisitos", [])
        pacote["pesquisa_on_demand"] = {"tentativas": 0, "orcamento_chamadas": 0,
                                        "motivo": "complemento_em_lote_finalizado"}
        pacote["ferramenta"] = {"ativos": [a.model_dump(mode="json") for a in p.jornada.ativos],
                                "estado": "fallback_sem_js" if p.jornada.ativos else "nao_pedida"}
        if p.jornada.ativos:
            pacote["estado"] = "human_review"
            pacote["restricoes"].append("Apresente somente o fallback_sem_js especificado; "
                                        "não prometa uma ferramenta interativa disponível.")
        pacote["sha256"] = sha256_canonico(pacote)
        pacotes[p.page_number] = pacote
    state.pacotes = copy.deepcopy(pacotes)
    (pasta / "pacotes.json").write_text(json.dumps(pacotes, ensure_ascii=False, indent=2))
    (pasta / "brief_pre_arquitetura.json").write_text(state.brief_pre_arquitetura.model_dump_json(indent=2))


def pacote_conferido(state, page):
    pacote = copy.deepcopy(state.pacotes[page.page_number])
    sha = pacote.pop("sha256")
    if sha256_canonico(pacote) != sha:
        raise ValueError("pacote congelado diverge do SHA-256")
    if pacote["pagina"] != page.model_dump(mode="json"):
        raise ValueError("página mudou depois do congelamento")
    pacote["sha256"] = sha
    return pacote


def prompt_do_pacote(state, page):
    from funnelforge.prompts import render
    pacote = pacote_conferido(state, page)
    p, j = pacote["pagina"], pacote["jornada"]
    lp = p["page_type"] == "LANDING PAGE"
    nome = "redator_p1_v2" if lp else (
        "redator_presell_v2" if p["role"] == "PRESELL" else "redator_pages_v2")
    destinos = [{"role_label": "próxima dúvida", "h1": d["h1"],
                 "delivery": d["entrega"], "objective": d["motivo"]}
                for d in pacote["destinos"] if d["tipo"] == "funnel"]
    prompt = render(nome, headline=p["h1_title"], objective=p["emotional_objective"],
        skeleton="\n".join(p["main_content_structure"]), keywords=", ".join(p["target_keywords"]),
        cta_text=p["hook_to_next_page"], page_num=p["page_number"],
        total_pages=pacote["total_pages"], role=p["role"],
        editorial=p["editorial"], jornada=j, lp_destinations=destinos,
        facts=json.dumps(pacote["factual"], ensure_ascii=False),
        domain=pacote["dominio"], routes=pacote["links"],
        official_links=pacote["factual"].get("urls_oficiais", []), platform_links=[],
        qualifier_lens=j["pergunta"], qualifier_questions=[], next_solutions=[],
        is_terminal=bool(j["condicao_terminal"]), terminal_official=j["saida_oficial"]["classificacao"] == "boa",
        cross_funnel_label="", engajamento=p["engajamento"],
        plano_visual=j["plano_visual"], exigencia_visual=[], visual_required_blocks=[],
        signature_block="", author_name=pacote["autor"], author_credential=pacote["credencial"],
        cnpj=pacote["cnpj"], today=pacote["data"], escrita_natural=True,
        briefing_texto=json.dumps(pacote, ensure_ascii=False))
    regra_lp = (
        " Na LP, cite o nome da fonte em prosa, mas não gere hyperlink externo "
        "clicável no corpo; o destino pago deve manter a sessão no funil."
        if lp else ""
    )
    return prompt + "\nPacote congelado prevalece: preserve destinos e rótulos aprovados. " \
        "Não pesquise, não invente ferramentas. Blocos dependentes de lacuna devem ser omitidos." \
        + regra_lp


def revisar_lote(state, pages, deps):
    """Uma chamada; mesmas políticas, notas, patcher e recibos do revisor V2."""
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.revisao import documento_de, montar_prompt_do_revisor
    prompts = []
    for p in pages:
        st.step_seo(state, p, deps)
        doc = documento_de(state.drafts[p.page_number], state.seo.get(p.page_number))
        ctx = st._contexto_da_revisao(state, p, deps, doc)
        prompts.append({"page_number": p.page_number,
                        "prompt": montar_prompt_do_revisor(doc, ctx)})
    mensagem = ("REVISOR GLOBAL: revise todas as páginas em uma única resposta. "
                "Preserve o contrato individual integral, critérios, notas e políticas. "
                "Não redesenhe a jornada. Não pesquise. Responda JSON: "
                '{"paginas":[{"page_number":1,"revisao":{...resposta do revisor...}}]}. '
                "Uma entrada exata por página; nenhum texto fora do JSON.\n"
                + json.dumps({"brief_pre_arquitetura": state.brief_pre_arquitetura.model_dump(),
                              "paginas": prompts}, ensure_ascii=False))
    try:
        texto, recibo = deps.runner.run_llm_step("revisor_lote", deps.settings.steps["revisor"],
            [{"role": "user", "content": mensagem}], ctx={}, run_id=state.run_id)
        entradas = st._tolerant_json(texto).get("paginas") or []
        por_numero = {}
        for e in entradas:
            n = e.get("page_number")
            if n in por_numero:
                raise ValueError("página duplicada na revisão global")
            por_numero[n] = e.get("revisao")
    except Exception as exc:
        recibo = getattr(exc, "step_result", StepResult(step="revisor_lote", status=StepStatus.FAILED))
        por_numero = {}
    state.step_status["revisor_lote"] = recibo
    for p in pages:
        revisao = por_numero.get(p.page_number) or {
            "decisao": "revisao_humana", "achados": [], "patches": []}
        # A chamada está debitada UMA vez em revisor_lote, nunca em cada página.
        local = StepResult(step=f"revisor_p{p.page_number}", status=StepStatus.OK, attempts=0,
                           model_requested=recibo.model_requested, model_used=recibo.model_used,
                           auth_mode=recibo.auth_mode)
        st._revisar_pagina(state, p, deps,
                          resposta_precalculada=(json.dumps(revisao, ensure_ascii=False), local))
