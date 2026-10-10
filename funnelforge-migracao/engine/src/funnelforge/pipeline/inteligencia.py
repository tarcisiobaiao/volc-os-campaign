"""Duas passagens no motor existente: intenção -> arquitetura -> fatos -> pacote."""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from dataclasses import asdict
from datetime import date

from funnelforge.domain.dossie import sha256_canonico, texto_normal
from funnelforge.domain.models import (
    BriefDoFunil, DuvidaDoBrief, JornadaDaPagina, RequisitoFactual,
    Issue, SinalEmocional, StepResult, StepStatus,
)


def chave_da_pergunta(texto):
    # Conservador: agrupa flexões/ordem e sinônimos estreitos; não decide fatos.
    # `texto_normal` é deliberadamente ASCII porque nasceu para comparar
    # números e trechos factuais em português. Demanda, porém, é multilíngue:
    # aplicá-lo aqui apagava tailandês por inteiro (e reduzia perguntas com
    # ano ao mero "2569"), fazendo PAA/autocomplete distintos virarem uma só
    # dúvida antes de o JEV ou o arquiteto recebê-los. Preserve letras,
    # marcas combinantes e números de qualquer escrita; pontuação vira espaço.
    t = unicodedata.normalize("NFKC", texto or "").casefold()
    t = "".join(
        ch if (unicodedata.category(ch)[:1] in {"L", "M", "N"} or ch.isspace()) else " "
        for ch in t
    )
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\b(elegivel|elegibilidade)\b", "direito", t)
    return " ".join(sorted(set(t.split()) - {"o", "a", "os", "as", "de", "do", "da", "ao", "eu"}))


def dores_da_demanda(card: dict) -> list[str]:
    """A linguagem de dor que o Pautador JÁ mediu, como dado para o arquiteto:
    a tensão da validação (com a evidência), as dores mineradas da entidade e a
    dor concreta. Hipótese de demanda, nunca fato sobre o leitor."""
    leitura = card.get("contexto_de_leitura") or {}
    dores = [str(d).strip() for d in leitura.get("dores_observadas") or [] if str(d).strip()]
    tensao = leitura.get("tensao") if isinstance(leitura.get("tensao"), dict) else {}
    if str(tensao.get("frase") or "").strip():
        evidencia = str(tensao.get("evidencia") or "").strip() or "validação"
        dores.append(f'{tensao["frase"].strip()} (medido: {evidencia})')
    for dor in card.get("pains") or []:
        if isinstance(dor, dict) and str(dor.get("pain_name") or "").strip():
            descricao = str(dor.get("pain_description") or "").strip()
            dores.append(dor["pain_name"].strip() + (f": {descricao}" if descricao else ""))
    if str(card.get("concrete_pain") or "").strip():
        dores.append(card["concrete_pain"].strip())
    return list(dict.fromkeys(dores))


def compilar_brief(card: dict, paa: dict, pesquisa: dict | None = None, *, provider=None) -> BriefDoFunil:
    tema = card.get("main_keyword") or card.get("keyword") or card.get("entidade") or ""
    leitura = card.get("contexto_de_leitura") or {}
    sinais = [{"tipo": "paa", "texto": q, "origem": paa["origem"], "factual": False}
              for q in paa["perguntas"]]
    # O contrato REAL da validação (`entities.orchestrator.contexto_de_leitura`)
    # é {perguntas_paa, tensao{frase, evidencia}}: as perguntas medidas entram
    # como demanda, como qualquer PAA.
    for q in leitura.get("perguntas_paa") or []:
        if isinstance(q, str) and q.strip():
            sinais.append({"tipo": "paa", "texto": q.strip(),
                           "origem": "card.contexto_de_leitura", "factual": False})
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
    contexto_medido = card.get("contexto_de_busca") or {}
    contexto_jev = {
        "tema": tema,
        "pais": card.get("country") or "",
        "idioma": card.get("native_language") or "",
        "duvida_ids": [d.jornada.duvida_id for d in duvidas],
        "contexto_medido": contexto_medido,
        "duvidas": [
            {
                "duvida_id": d.jornada.duvida_id,
                "prioridade": d.prioridade,
                "evidencia_demanda": d.evidencia_demanda,
            }
            for d in duvidas
        ],
    }
    decisoes = (provider or HeuristicaDeIntencao()).classificar(
        [d.jornada.pergunta_principal for d in duvidas], contexto=contexto_jev)
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
        dores_observadas=dores_da_demanda(card),
        desejos_observados=leitura.get("desejos_observados") or [], fatos_existentes=fatos,
        lacunas=(["PAA ausente; não impede arquitetura"] if not paa["perguntas"] else [])
                + (["pesquisa indisponível: " + dados["defeito"]] if dados.get("defeito") else []))
    brief.sha256 = sha256_canonico(brief.model_dump(exclude={"sha256"}))
    return brief


def plano_aprovado_valido(aprovada: dict | None) -> bool:
    """O plano aprovado converte e tem jornada? (o mesmo teste do `step_extract`)."""
    if not aprovada:
        return False
    from pydantic import ValidationError

    from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
    from funnelforge.pipeline.jornada import tem_jornada
    try:
        return tem_jornada(plano_do_funnel_architecture(copy.deepcopy(aprovada)))
    except (ValueError, ValidationError):
        return False


def preparar_inteligencia(state, deps, card, *, pesquisar: bool = True):
    from funnelforge.adapters.attention_matrix import perguntas
    from funnelforge.adapters.research_perplexity import pesquisar_funil
    from funnelforge.pipeline.dossie import RespostaDaPesquisa
    paa = perguntas(card, deps.runner.runs_dir / "cache_paa", cliente=deps.attention_matrix)
    brief = compilar_brief(card, paa)
    if not pesquisar:
        # Esqueleto aprovado: o brief leva PAA, dores e linguagem; os fatos vêm
        # da pesquisa do dossiê, pelos requisitos das páginas.
        from funnelforge.adapters.decisao_intencao import JevDeIntencao
        state.brief_pre_arquitetura = compilar_brief(card, paa, provider=JevDeIntencao(
            enabled=deps.settings.run.jev_enabled))
        state.step_status["inteligencia"] = StepResult(
            step="inteligencia", status=StepStatus.OK, attempts=0,
            issues=[Issue(code="paa", message=json.dumps(paa, ensure_ascii=False)),
                    Issue(code="pesquisa_pelo_esqueleto_aprovado",
                          message="sem pesquisa antecipada: a primeira pesquisa é a do dossiê, "
                                  "pelos requisitos das páginas aprovadas")])
        return
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
        from funnelforge.pipeline.pipeline import leitura_do_bucket
        resp = pesquisar_funil(deps.llm, cfg, brief.intencao_principal, spec,
                               **leitura_do_bucket(deps))
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


def revisar_arquitetura_jev(state, deps, card, *, provider=None):
    """Lint semântico pós-arquitetura: uma chamada, consultivo e fail-soft."""
    from funnelforge.adapters.decisao_intencao import JevDeIntencao

    if state.plan is None or not getattr(deps.settings.run, "jev_enabled", False):
        return
    contexto = {
        "tema": card.get("main_keyword") or card.get("keyword") or card.get("entidade") or "",
        "pais": card.get("country") or "",
        "idioma": card.get("native_language") or "",
        "contexto_medido": card.get("contexto_de_busca") or {},
    }
    resultado = (provider or JevDeIntencao(enabled=True)).verificar_jornada(
        state.plan, contexto=contexto)
    state.revisao_semantica_jev = resultado
    issues = []
    for aresta in resultado.get("arestas") or []:
        if aresta.get("decisao") == "usar":
            continue
        issues.append(Issue(
            code="jev_cta_" + str(aresta.get("decisao") or "revisar"),
            message=json.dumps({
                "origem": aresta.get("origem_slug"),
                "destino": aresta.get("destino_slug"),
                "cta": aresta.get("cta"),
                "problemas": aresta.get("problemas") or [],
                "motivacao": aresta.get("motivacao"),
                "congruencia": aresta.get("congruencia"),
            }, ensure_ascii=False),
        ))
    if resultado.get("custo_estimado_usd") is not None:
        issues.append(Issue(
            code="jev_custo_estimado",
            message=("Estimativa pela tabela Jev 1.13; não é custo faturado: US$ "
                     f"{resultado['custo_estimado_usd']:.9f}"),
        ))
    usage = resultado.get("usage") or {}
    state.step_status["jev_pos_arquitetura"] = StepResult(
        step="jev_pos_arquitetura",
        status=StepStatus.FALLBACK if resultado.get("fallback") else StepStatus.OK,
        model_requested=resultado.get("requested_model") or "",
        model_used=resultado.get("served_model") or "",
        attempts=1 if resultado.get("served_model") else 0,
        prompt_tokens=int(usage.get("input_tokens") or 0),
        completion_tokens=int(usage.get("output_tokens") or 0),
        cost_usd=float(resultado.get("custo_usd") or 0.0),
        latency_ms=int(resultado.get("latencia_ms") or 0),
        issues=issues,
    )
    pasta = deps.runner.runs_dir / state.run_id
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "revisao_semantica_jev.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")


def ferramentas_da_pagina(state, page, deps):
    """Disponibilidade provada ANTES da promessa: fonte + componente + cálculo.

    O catálogo de orientação continua no gerador existente. Calculadoras
    declaradas são montadas aqui sem chamada, com operações e testes fixos.
    Especificação aberta/sem componente nunca ganha estado 'pronta'.
    """
    from funnelforge.pipeline.jornada import ativos_validos
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    from funnelforge.pipeline.validators.checks import sanitize_widget_block
    from funnelforge.widgets.calculos import renderizar_calculo, validar
    factual = projecao_para_o_prompt(state.dossie, page.page_number)
    desativados = {d.get("nome"): d.get("motivo", "sem evidência")
                  for d in factual.get("desativados", []) if d.get("tipo") == "ativo"}
    completos = {a.pergunta for a in ativos_validos(page)}
    itens = []
    for a in page.jornada.ativos:
        item = {"pergunta": a.pergunta, "fallback_sem_js": a.fallback_sem_js,
                "estado": "fallback_sem_js", "motivo": "sem componente de cálculo declarado"}
        if not deps.settings.run.widgets_enabled:
            item["motivo"] = "widgets desabilitados nesta execução"
        elif page.page_type == "LANDING PAGE":
            item["motivo"] = "calculadora pré-montada disponível apenas no corpo Gutenberg"
        elif a.pergunta not in completos:
            item["motivo"] = "especificação incompleta"
        elif a.pergunta in desativados:
            item["motivo"] = desativados[a.pergunta]
        elif a.calculo is not None:
            try:
                recibos = validar(a.calculo)
                if len(a.entradas) != len(a.calculo.rotulos):
                    raise ValueError("Entradas do ativo e da calculadora divergentes")
                bloco = renderizar_calculo(a.calculo, titulo=a.pergunta,
                                           identidade=f"{state.run_id}:{page.page_number}:{a.pergunta}")
                if sanitize_widget_block(bloco):
                    raise ValueError("Gabarito da calculadora recusado pelo sanitizador")
                item.update(estado="pronta", motivo="fonte vinculada e cálculo validado por código",
                            bloco=bloco, operacao=a.calculo.operacao, testes=recibos,
                            entrega="Calcular " + a.calculo.rotulo_resultado
                                    + "; resultado informativo, sem consulta de cadastro ou confirmação de elegibilidade")
            except ValueError as exc:
                item["motivo"] = str(exc)
        itens.append(item)
    return {"itens": itens, "estado": ("pronta" if itens and all(
        a["estado"] == "pronta" for a in itens) else "fallback_sem_js" if itens else "nao_pedida")}


def _cartao_de_orientacao(w, bloco: str, conteudo: dict | None = None) -> dict:
    """O que o redator, o sniper e o revisor precisam saber da peça pronta."""
    from funnelforge.widgets.contrato import ARQUETIPOS
    spec = ARQUETIPOS[w.arquetipo]
    return {"pergunta": w.titulo, "estado": "pronta", "tipo": "orientacao",
            "arquetipo": w.arquetipo, "nome": str(spec["nome"]),
            "entradas": [c.rotulo + ": " + " / ".join(o.texto for o in c.opcoes)
                         for c in w.controles],
            "resultado": "orientação por situação: " + "; ".join(c.chip for c in w.cenarios),
            "limites": "orienta com os fatos da página; não consulta cadastro nem confirma "
                       "direito, valor ou aprovação",
            "entrega": f"{spec['nome']}: {spec['eyebrow']}", "bloco": bloco,
            # O conteúdo validado da peça: é dele que a correção localizada do
            # revisor parte, para refazer o HTML pelo gabarito.
            "conteudo": conteudo or {}}


def preparar_widgets_de_orientacao(state, deps, ferramentas: dict) -> dict:
    """Os widgets de orientação do funil, prontos ANTES da redação, numa chamada.

    O conteúdo vem dos fatos do pacote de cada página; HTML, CSS e JS vêm de
    `widgets/render.py`. Antes, no caminho com pacotes, o widget de orientação
    era gerado depois da redação, uma chamada por página, e nem o redator nem
    os botões sabiam que ele existiria. Peça que não passa no contrato, no
    sanitizador ou no lastro factual não vira ferramenta e não é prometida.
    Página com ativo do arquiteto (calculadora) fica com o ativo."""
    from funnelforge.domain.models import PageRole, ResearchFacts, effective_role
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    from funnelforge.pipeline.validators.checks import run_validators, sanitize_widget_block
    from funnelforge.prompts import render
    from funnelforge.widgets.contrato import WidgetInvalido, chave_por_nome, ler
    from funnelforge.widgets.render import renderizar
    cfg = deps.settings.steps.get("widget")
    if not deps.settings.run.widgets_enabled or cfg is None:
        return {}
    candidatas = []
    for p in state.plan.pages:
        if effective_role(p) is not PageRole.SOLUTION or ferramentas[p.page_number]["itens"]:
            continue
        arquetipo = st.widget_archetype_for(state, p)
        if arquetipo is None:
            continue
        candidatas.append(p)
    if not candidatas:
        return {}
    paginas = []
    for p in candidatas:
        factual = projecao_para_o_prompt(state.dossie, p.page_number)
        paginas.append({
            "pagina": p.page_number, "h1": p.h1_title, "pergunta": p.jornada.pergunta_principal,
            "resposta": p.jornada.resposta_imediata,
            "plano_visual": [b.intencao for b in p.jornada.plano_visual],
            "sugestao": chave_por_nome(st.widget_archetype_for(state, p)) or "",
            "fatos": factual.get("fatos") or []})
    prompt = render("widgets_do_funil", paginas=paginas)
    recibo = {"paginas": [p.page_number for p in candidatas], "prontas": [], "recusadas": {}}
    try:
        texto, res = deps.runner.run_llm_step(
            "widgets_do_funil", cfg.model_copy(update={"validators": []}),
            [{"role": "user", "content": prompt}], ctx={}, run_id=state.run_id)
        entradas = st._tolerant_json(texto).get("widgets") or []
    except Exception as exc:  # noqa: BLE001 - sem peça pronta, nada é prometido
        res = getattr(exc, "step_result", StepResult(step="widgets_do_funil",
                                                     status=StepStatus.FAILED))
        entradas = []
        recibo["defeito"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    por_numero = {p.page_number: p for p in candidatas}
    for e in entradas:
        n = e.get("page_number") if isinstance(e, dict) else None
        if n not in por_numero or n in recibo["prontas"]:
            continue
        bruto = e.get("widget")
        if not isinstance(bruto, dict):
            recibo["recusadas"][n] = "NONE: " + str(e.get("motivo") or "")[:200]
            continue
        try:
            w = ler(json.dumps(bruto, ensure_ascii=False))
        except WidgetInvalido as invalido:
            recibo["recusadas"][n] = "; ".join(invalido.motivos)[:400]
            continue
        bloco = renderizar(w)
        problemas = sanitize_widget_block(bloco) + run_validators(
            ["critical_fact_grounding"], bloco,
            {"facts": state.facts.get(n, ResearchFacts(sparse=True)),
             "editorial_v2": bool(getattr(state, "editorial_v2", False))})
        if problemas:
            recibo["recusadas"][n] = "; ".join(f"{i.code}: {i.message}" for i in problemas)[:400]
            continue
        ferramentas[n]["orientacao"] = _cartao_de_orientacao(w, bloco, bruto)
        recibo["prontas"].append(n)
    res.issues = list(res.issues) + [Issue(code="widgets_do_funil",
                                           message=json.dumps(recibo, ensure_ascii=False))]
    state.step_status["widgets_do_funil"] = res
    return recibo


def congelar_pacotes(state, deps):
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
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
    ferramentas = {p.page_number: ferramentas_da_pagina(state, p, deps) for p in state.plan.pages}
    preparar_widgets_de_orientacao(state, deps, ferramentas)
    entregas = _entregas_das_ferramentas(state, ferramentas)
    # Os botões do funil inteiro, numa chamada, sobre as entregas e ferramentas
    # já confirmadas. Os rótulos entram nas rotas ANTES do hash do pacote.
    from funnelforge.pipeline.ctas import definir_ctas_do_funil
    rotulados = definir_ctas_do_funil(state, deps, ferramentas, entregas)
    for p in state.plan.pages:
        pacotes[p.page_number] = _montar_pacote(state, deps, p, ferramentas, entregas, rotulados)
    state.pacotes = copy.deepcopy(pacotes)
    (pasta / "pacotes.json").write_text(json.dumps(pacotes, ensure_ascii=False, indent=2))
    (pasta / "brief_pre_arquitetura.json").write_text(state.brief_pre_arquitetura.model_dump_json(indent=2))


def _entregas_das_ferramentas(state, ferramentas: dict) -> dict:
    """Só a ferramenta que NÃO ficou pronta muda a promessa e os botões. Com a
    calculadora validada, a entrega planejada vale como está: apagar os rótulos
    aprovados obrigava o redator a reescrevê-los (e saíam mornos)."""
    entregas = {}
    for p in state.plan.pages:
        itens = ferramentas[p.page_number]["itens"]
        if any(a["estado"] != "pronta" for a in itens):
            entregas[p.page_number] = " ".join(
                a["entrega"] if a["estado"] == "pronta" else a["fallback_sem_js"]
                for a in itens).strip()
    return entregas


def _montar_pacote(state, deps, p, ferramentas: dict, entregas: dict, rotulados: set) -> dict:
    """O pacote congelado de UMA página (com sha256)."""
    from funnelforge.pipeline.jornada import contexto_de_jornada
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    from funnelforge.pipeline.briefing import destinos_da_pagina
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
              "data": date.today().isoformat(), "tom": state.plan.tone_voice,
              "avatar": state.plan.avatar_summary,
              "screenshot": p.jornada.screenshot_necessario,
              "imagem": p.jornada.imagem_necessaria, "schema": p.jornada.schema_tipos,
              "restricoes": ["Não redesenhar a jornada ou pesquisar. Não inventar fatos, "
                              "ferramentas, URLs ou trocar a próxima dúvida.",
                              "Use somente fatos permitidos; remova blocos desativados."]}
    if state.revisao_semantica_jev:
        pacote["semantica_jev"] = {
            "estado": "presente",
            "consultivo": True,
            "arestas": [
                a for a in (state.revisao_semantica_jev.get("arestas") or [])
                if a.get("origem_pagina") == p.page_number
            ],
        }
    # O plano original fica para auditoria. A entrega operacional e os
    # destinos recebem o resultado factual/funcional, não uma promessa
    # de ferramenta que ainda não existe.
    dossier = next((d for d in state.dossie.get("paginas", [])
                    if d["page_number"] == p.page_number), {})
    pacote["evidencia_por_requisito"] = (dossier.get("cobertura") or {}).get("requisitos", [])
    pacote["pesquisa_on_demand"] = {"tentativas": 0, "orcamento_chamadas": 0,
                                    "motivo": "complemento_em_lote_finalizado"}
    pacote["ferramenta"] = ferramentas[p.page_number]
    indisponiveis = [a for a in pacote["ferramenta"]["itens"] if a["estado"] != "pronta"]
    if p.page_number in entregas:
        j["resposta_imediata"] = entregas[p.page_number]
        if j["valor"]:
            j["valor"]["capacidade_do_leitor"] = entregas[p.page_number]
    if indisponiveis:
        pacote["estado"] = "human_review"
        pacote["restricoes"].append("Apresente somente o fallback_sem_js especificado; "
                                    "não prometa uma ferramenta interativa disponível.")
        fallback = entregas[p.page_number]
        entrega = fallback or ("Responder à dúvida com os fatos verificados, sem ferramenta interativa: "
                               + j["pergunta"])
        j["resposta_imediata"] = entrega
        j["condicao_terminal"] = entrega
        j.pop("tensao_residual", None)
        j["ativos"] = [a for a in j["ativos"] if a["pergunta"] not in {
            x["pergunta"] for x in indisponiveis}]
        j["plano_visual"] = [b for b in j["plano_visual"]
                             if b["intencao"] not in ("calculo", "ferramenta")]
        if j["valor"]:
            j["valor"]["capacidade_do_leitor"] = entrega
            j["valor"]["informacao_nova"] = entrega
            j["valor"]["entregas"] = [e for e in j["valor"]["entregas"]
                                       if e not in ("calculo", "ferramenta")]
    pacote["entrega_confirmada"] = {"promessa": j["resposta_imediata"],
                                    "ferramentas": pacote["ferramenta"]["estado"],
                                    "substituiu_promessa": p.page_number in entregas}
    for destino in pacote["destinos"]:
        alvo = next((a for a in state.plan.pages if destino.get("tipo") == "funnel"
                     and str(destino.get("destino", "")).strip("/") == a.slug.strip("/")), None)
        if alvo is not None:
            destino["ferramentas"] = ferramentas[alvo.page_number]["estado"]
            if alvo.page_number in entregas:
                destino["entrega"] = entregas[alvo.page_number]
    # Uma aresta pode ter copy de uma ferramenta que saiu. A LLM escreve
    # o rótulo final sobre a entrega confirmada, sem trocar href/topologia.
    # Só sem o rótulo do sniper (chamada falhou ou rótulo recusado pelo
    # código) o redator ainda reescreve o botão de ferramenta que saiu.
    for link in pacote["links"]:
        alvo = next((a for a in state.plan.pages if link["kind"] == "funnel"
                     and link["href"].rstrip("/").endswith("/" + a.slug)), None)
        if (alvo is not None and (p.page_number, alvo.slug) in rotulados):
            continue
        if p.page_number in entregas or (alvo is not None and alvo.page_number in entregas):
            link["reformular_cta"] = True
            link["anchor"] = ""
    for destino in j["destinos"]:
        if (p.page_number, destino["slug"]) in rotulados:
            continue
        if p.page_number in entregas or any(a.slug == destino["slug"]
                and a.page_number in entregas for a in state.plan.pages):
            destino["cta"] = ""
    pacote["sha256"] = sha256_canonico(pacote)
    return pacote


def recongelar_paginas(state, deps, numeros: list[int]) -> dict:
    """Refaz SÓ os pacotes das páginas pedidas (ex.: a saída oficial de uma
    página mudou), com as ferramentas já prontas e o sniper só para as arestas
    cujo destino mudou. Os demais pacotes ficam como estão e são conferidos."""
    from funnelforge.pipeline.ctas import definir_ctas_do_funil
    ferramentas = {n: copy.deepcopy(state.pacotes[n]["ferramenta"]) for n in state.pacotes}
    entregas = _entregas_das_ferramentas(state, ferramentas)
    rotulados = definir_ctas_do_funil(state, deps, ferramentas, entregas)
    novos = {}
    for p in state.plan.pages:
        if p.page_number in numeros:
            novos[p.page_number] = _montar_pacote(state, deps, p, ferramentas, entregas,
                                                  rotulados)
    state.pacotes = {**state.pacotes, **copy.deepcopy(novos)}
    for p in state.plan.pages:
        pacote_conferido(state, p)
    pasta = deps.runner.runs_dir / state.run_id
    (pasta / "pacotes.json").write_text(json.dumps(state.pacotes, ensure_ascii=False, indent=2))
    return novos


def pacote_conferido(state, page):
    pacote = copy.deepcopy(state.pacotes[page.page_number])
    sha = pacote.pop("sha256")
    if sha256_canonico(pacote) != sha:
        raise ValueError("pacote congelado diverge do SHA-256")
    if pacote["pagina"] != page.model_dump(mode="json"):
        raise ValueError("página mudou depois do congelamento")
    pacote["sha256"] = sha
    return pacote


def _visao_sem_url_do_redator(pacote):
    """LP e pré-sell: o redator vê o fato, o id e o NOME da fonte, nunca a URL.

    No run da tarifa social (09/10) a URL chegou ao redator da LP 14 vezes
    (fatos do `factual`, do dossiê da jornada e o pacote inteiro como briefing)
    e voltou como texto "(fonte: https://...)" e, na pré-sell, como 13 `<a>`.
    A evidência continua no pacote congelado e no dossiê; isto muda só a cópia
    que vira prompt (`pacote_conferido` já devolve uma cópia). O nome (host)
    é o mesmo de `base_factual.nome_da_fonte`: é ele que o portão
    `critical_fact_grounding` aceita como citação num destino sem link.
    """
    from funnelforge.pipeline.base_factual import nome_da_fonte
    j = pacote.get("jornada") or {}
    for base in (pacote.get("factual") or {}, j.get("dossie") or {}):
        for fato in base.get("fatos") or []:
            if isinstance(fato, dict) and "fonte" in fato:
                fato["citar_como"] = nome_da_fonte(fato.pop("fonte"))
        if "urls_oficiais" in base:
            base["urls_oficiais"] = []
        for vinculo in base.get("vinculos") or []:
            if isinstance(vinculo, dict):
                vinculo.pop("url", None)
    return pacote


def _visao_do_redator(pacote: dict) -> dict:
    """O pacote como o redator o lê: sem o que o prompt já mostra noutra seção.

    A jornada vai em <jornada_do_leitor> e os fatos em <dados>. No run de 09/10
    o mesmo pacote também viajava inteiro no briefing, e o mesmo fato aparecia
    quatro vezes no prompt da p4 (jornada da página, jornada do pacote, fatos
    do pacote e fatos do dossiê da jornada). O pacote congelado não muda, e o
    sha256 dele continua no prompt como recibo de qual pacote foi lido."""
    visao = {k: v for k, v in pacote.items()
             if k not in ("jornada", "factual", "pesquisa_on_demand")}
    visao["pagina"] = {k: v for k, v in pacote.get("pagina", {}).items()
                       if k not in ("jornada", "routes")}
    visao["estado_da_evidencia"] = {k: pacote.get("factual", {}).get(k)
                                    for k in ("estado", "degradacoes", "desativados")}
    return visao


def _jornada_traz_os_fatos(jornada: dict, factual: dict) -> bool:
    """A lista do DOSSIÊ na jornada é a mesma dos fatos do pacote (mesmos ids)?"""
    na_jornada = [f.get("id") for f in ((jornada or {}).get("dossie") or {}).get("fatos") or []]
    return bool(na_jornada) and na_jornada == [f.get("id") for f in factual.get("fatos") or []]


def _base_complementar(factual: dict) -> dict:
    return {"fatos": "os fatos verificados desta página estão no DOSSIÊ FACTUAL CONGELADO "
                     "da jornada, com o trecho de cada fonte: só eles sustentam número, prazo "
                     "ou regra",
            "urls_oficiais": factual.get("urls_oficiais") or [],
            "estado": factual.get("estado", ""),
            "vinculos": factual.get("vinculos") or []}


def visao_do_pacote_para_revisao(pacote: dict) -> dict:
    """O pacote que o redator leu, para o revisor: mesma visão, sem o código
    das ferramentas (o revisor lê a ferramenta na própria página)."""
    visao = _visao_do_redator(copy.deepcopy(pacote))
    ferramenta = visao.get("ferramenta") or {}
    for item in [*(ferramenta.get("itens") or []),
                 *([ferramenta["orientacao"]] if ferramenta.get("orientacao") else [])]:
        item.pop("bloco", None)
        item.pop("conteudo", None)
    return visao


_CAMPOS_FIXOS_DO_WIDGET = frozenset({"arquetipo", "id", "valor", "tom", "padrao", "quando"})


def corretor_de_widget(orientacao: dict, facts):
    """A correção localizada do texto do widget de orientação, para o revisor.

    Troca UMA ocorrência do trecho num campo de texto do conteúdo da peça (nunca
    id, valor de opção, tom ou condição), relê pelo contrato, refaz o HTML por
    `widgets/render.py` e confere sanitizador e lastro factual. O bloco antigo
    sai do rascunho por inteiro. Várias correções na mesma rodada se acumulam."""
    from dataclasses import replace

    from funnelforge.domain.models import ResearchFacts
    from funnelforge.pipeline.validators.checks import run_validators, sanitize_widget_block
    from funnelforge.widgets.contrato import WidgetInvalido, ler
    from funnelforge.widgets.render import renderizar
    if not orientacao.get("conteudo") or not orientacao.get("bloco"):
        return None
    atual = {"conteudo": copy.deepcopy(orientacao["conteudo"]),
             "bloco": orientacao["bloco"].strip()}

    def corrigir(doc, antes: str, depois: str):
        alvos = []

        def visitar(no, caminho):
            if isinstance(no, dict):
                for k, v in no.items():
                    if k not in _CAMPOS_FIXOS_DO_WIDGET:
                        visitar(v, [*caminho, k])
            elif isinstance(no, list):
                for i, v in enumerate(no):
                    visitar(v, [*caminho, i])
            elif isinstance(no, str) and antes in no:
                alvos.append(caminho)
        conteudo = copy.deepcopy(atual["conteudo"])
        visitar(conteudo, [])
        if len(alvos) != 1:
            return None, "antes_ausente_ou_duplicado_no_widget"
        *pai, chave = alvos[0]
        no = conteudo
        for passo in pai:
            no = no[passo]
        if no[chave].count(antes) != 1:
            return None, "antes_ausente_ou_duplicado_no_widget"
        no[chave] = no[chave].replace(antes, depois)
        try:
            w = ler(json.dumps(conteudo, ensure_ascii=False))
        except WidgetInvalido as invalido:
            return None, "widget_invalido: " + "; ".join(invalido.motivos)[:200]
        bloco = renderizar(w).strip()
        if sanitize_widget_block(bloco) or run_validators(
                ["critical_fact_grounding"], bloco,
                {"facts": facts if facts is not None else ResearchFacts(sparse=True),
                 "editorial_v2": True}):
            return None, "widget_reprovado_na_conferencia"
        if atual["bloco"] not in doc.corpo:
            return None, "widget_do_pacote_nao_encontrado"
        corrigido = replace(doc, corpo=doc.corpo.replace(atual["bloco"], bloco, 1))
        atual.update(conteudo=conteudo, bloco=bloco)
        return corrigido, ""
    return corrigir


def brief_para_revisao(brief) -> dict:
    """O brief da chegada sem os fatos 'a conferir' da pesquisa antecipada: o
    revisor julga com o MESMO inventário do redator, nada a mais."""
    if brief is None:
        return {}
    dados = brief.model_dump()
    return {"intencao_principal": dados.get("intencao_principal", ""),
            "trabalho_do_leitor": dados.get("trabalho_do_leitor", ""),
            "consciencia": dados.get("consciencia", ""),
            "perguntas_do_leitor": [((d.get("jornada") or {}).get("pergunta_principal") or "")
                                    for d in dados.get("duvidas") or []],
            "dores_observadas": dados.get("dores_observadas") or [],
            "desejos_observados": dados.get("desejos_observados") or []}


def prompt_do_pacote(state, page):
    from funnelforge.prompts import render
    pacote = pacote_conferido(state, page)
    p, j = pacote["pagina"], pacote["jornada"]
    # O redator precisa da capacidade, não do CSS/JS já testado. O bloco
    # completo permanece no pacote congelado para injeção determinística.
    for ativo in pacote.get("ferramenta", {}).get("itens", []):
        ativo.pop("bloco", None)
    if pacote.get("ferramenta", {}).get("orientacao"):
        pacote["ferramenta"]["orientacao"].pop("bloco", None)
        pacote["ferramenta"]["orientacao"].pop("conteudo", None)
    if pacote.get("entrega_confirmada", {}).get("substituiu_promessa"):
        p["editorial"]["useful_delivery"] = j["resposta_imediata"]
        p["jornada"] = j
        p["hook_to_next_page"] = "Escrever o CTA após a entrega confirmada, sem presumir cálculo realizado"
    # `pacote_conferido` devolve uma cópia. O plano original preserva a
    # proposta do arquiteto para auditoria; ao redator só chegam hrefs que o
    # roteamento manteve. Slug descartado (por exemplo retorno regressivo)
    # não pode reaparecer no JSON de briefing como instrução de navegação.
    if p.get("editorial") is not None:
        p["editorial"]["links"] = [
            {"target": link["href"], "cta": link["anchor"],
             "reason": link.get("reason", "")}
            for link in pacote["links"] if link["kind"] == "funnel"
        ]
    lp = p["page_type"] == "LANDING PAGE"
    sem_link = lp or p["role"] == "PRESELL"
    if sem_link:
        pacote = _visao_sem_url_do_redator(pacote)
        j = pacote["jornada"]
    nome = "redator_p1_v2" if lp else (
        "redator_presell_v2" if p["role"] == "PRESELL" else "redator_pages_v2")
    destinos = [{"role_label": "próxima dúvida", "h1": d["h1"],
                 "delivery": d["entrega"], "objective": d["motivo"]}
                for d in pacote["destinos"] if d["tipo"] == "funnel"]
    # Pré-sell e soluções escrevem a frase antes de cada botão: precisam da
    # entrega CONFIRMADA de cada destino (com o fallback, se a ferramenta de
    # lá não ficou pronta), a mesma que a LP já recebia em `lp_destinations`.
    entregas_dos_destinos = [
        {"h1": d["h1"], "objective": d["entrega"] + (
            " (ferramenta interativa pronta lá)" if d.get("ferramentas") == "pronta" else "")}
        for d in pacote["destinos"] if d["tipo"] == "funnel"]
    prompt = render(nome, headline=p["h1_title"], objective=p["emotional_objective"],
        skeleton="\n".join(p["main_content_structure"]), keywords=", ".join(p["target_keywords"]),
        cta_text=p["hook_to_next_page"], page_num=p["page_number"],
        total_pages=pacote["total_pages"], role=p["role"],
        editorial=p["editorial"], jornada=j, lp_destinations=destinos,
        # Os fatos já vão na lista do DOSSIÊ da jornada, com o trecho de cada
        # fonte; aqui fica só o que ela não mostra (sem o mesmo fato duas vezes).
        facts=json.dumps(_base_complementar(pacote["factual"])
                         if _jornada_traz_os_fatos(j, pacote["factual"]) else pacote["factual"],
                         ensure_ascii=False),
        com_trechos=True,
        domain=pacote["dominio"], routes=pacote["links"],
        official_links=pacote["factual"].get("urls_oficiais", []), platform_links=[],
        qualifier_lens=j["pergunta"], qualifier_questions=[],
        next_solutions=entregas_dos_destinos,
        navegacao_no_topo=not lp and any(l["kind"] == "funnel" for l in pacote["links"]),
        is_terminal=bool(j["condicao_terminal"]), terminal_official=j["saida_oficial"]["classificacao"] == "boa",
        cross_funnel_label="", engajamento=p["engajamento"],
        plano_visual=j["plano_visual"], exigencia_visual=[], visual_required_blocks=[],
        signature_block="", author_name=pacote["autor"], author_credential=pacote["credencial"],
        cnpj=pacote["cnpj"], today=pacote["data"], escrita_natural=True,
        briefing_texto=json.dumps(_visao_do_redator(pacote), ensure_ascii=False))
    regra_lp = (
        " Nesta página, cite a instituição em prosa só quando ajudar, sem URL escrita, "
        "sem \"fonte:\" e sem hyperlink externo no corpo; o leitor continua no funil."
        if sem_link else ""
    )
    dobra = (getattr(state, "ctas_do_funil", None) or {}).get("primeira_dobra") or {}
    if lp and dobra.get("titulo"):
        regra_lp += (" Primeira dobra aprovada para esta execução (use exatamente): "
                     f"hero_title = «{dobra['titulo']}»; "
                     f"hero_subtitle = «{dobra['subtitulo']}». "
                     "A intro continua daí, sem repetir o subtítulo.")
    prontas = [a for a in pacote.get("ferramenta", {}).get("itens", [])
               if a.get("estado") == "pronta"]
    if pacote.get("ferramenta", {}).get("orientacao"):
        prontas.append(pacote["ferramenta"]["orientacao"])
    ferramenta = ("".join(
        " Ferramenta pronta nesta página, inserida pelo sistema: "
        + str(a.get("nome") or a.get("pergunta") or "") + " (entradas: "
        + "; ".join(a.get("entradas") or []) + "; resultado: "
        + str(a.get("resultado") or a.get("entrega") or "") + "; limite: "
        + str(a.get("limites") or "não confirma direito") + "). Conte com ela no texto, "
        "sem reescrever o conteúdo dela nem criar outra." for a in prontas))
    ctas = ("Preserve os hrefs. Nos links reformular_cta=true, escreva um rótulo específico "
            "pela entrega confirmada do destino e pela próxima dúvida, nunca 'depois do cálculo' "
            "se não há calculadora. Não copie a promessa antiga. "
            if any(l.get("reformular_cta") for l in pacote["links"]) else
            "Preserve destinos e rótulos aprovados. ")
    return prompt + "\nPacote congelado prevalece: " + ctas + \
        "Slug e duvida_id são identificadores, nunca href; use somente os links resolvidos. " \
        "Não pesquise, não invente ferramentas. Blocos dependentes de lacuna devem ser omitidos." \
        + ferramenta + regra_lp


def _inventario_de_midia(state, page):
    """O que a página tem de fato, para o revisor não julgar promessa no escuro."""
    n = page.page_number
    revisao = (state.image_reviews or {}).get(n) or {}
    ferramenta = ((state.pacotes or {}).get(n) or {}).get("ferramenta") or {}
    return {
        "imagem": {"aprovada": bool(revisao.get("accepted")),
                   "cena": ((revisao.get("review") or {}).get("evidence") or "")[:240]},
        "prints_oficiais": [s.get("url") for s in (state.screenshots or {}).get(n) or []],
        "ferramenta": {"estado": ferramenta.get("estado", "nao_pedida"),
                       "itens": [{"pergunta": i.get("pergunta"), "estado": i.get("estado"),
                                  "entrega": i.get("entrega", "")}
                                 for i in [*(ferramenta.get("itens") or []),
                                           *([ferramenta["orientacao"]]
                                             if ferramenta.get("orientacao") else [])]]},
    }


def revisar_lote(state, pages, deps, *, direcao: str = ""):
    """Uma chamada; mesmas políticas, notas, patcher e recibos do revisor V2.

    `direcao` é a orientação do operador para ESTA revisão (ex.: primeira dobra
    e CTAs). Entra como dado do operador, abaixo das regras: não autoriza fato,
    número, link ou capacidade sem lastro no inventário."""
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.briefing import indice_factual_do_lote
    from funnelforge.pipeline.revisao import documento_de, montar_prompt_do_revisor
    prompts = []
    fatos_do_lote = []
    for p in pages:
        st.step_seo(state, p, deps)
        doc = documento_de(state.drafts[p.page_number], state.seo.get(p.page_number))
        # Os fatos vão uma vez, no índice do lote; cada página cita os ids dela.
        ctx = st._contexto_da_revisao(state, p, deps, doc, fatos_no_indice=True)
        fatos_do_lote += list(getattr(ctx, "fatos_do_inventario", None) or [])
        prompts.append({"page_number": p.page_number,
                        "prompt": montar_prompt_do_revisor(doc, ctx),
                        "inventario_de_midia": _inventario_de_midia(state, p)})
    # O pacote de políticas é o mesmo em todas as páginas do lote: vai uma vez.
    politicas = {m.group(0) for e in prompts
                 if (m := re.search(r"<pacote_de_politicas>[\s\S]*?</pacote_de_politicas>",
                                    e["prompt"]))}
    comum = ""
    if len(politicas) == 1 and all("<pacote_de_politicas>" in e["prompt"] for e in prompts):
        comum = politicas.pop()
        for e in prompts:
            e["prompt"] = e["prompt"].replace(
                comum, "<pacote_de_politicas>o mesmo para todas as páginas: ver "
                       "PACOTE DE POLÍTICAS DO LOTE no início</pacote_de_politicas>")
    mensagem = ("REVISOR GLOBAL: revise todas as páginas em uma única resposta. "
                "Preserve o contrato individual integral, critérios, notas e políticas. "
                "Não redesenhe a jornada. Não pesquise. inventario_de_midia diz o que existe "
                "de verdade em cada página (imagem aprovada, prints oficiais, ferramenta): "
                "não prometa nem peça o que não está lá. Responda JSON: "
                '{"paginas":[{"page_number":1,"revisao":{...resposta do revisor...}}]}. '
                "Uma entrada exata por página; nenhum texto fora do JSON.\n"
                + (("DIREÇÃO DO OPERADOR para esta revisão (aplique com patches "
                    "localizados, só com fatos do inventário de cada página): "
                    + direcao.strip() + "\n") if direcao.strip() else "")
                + (("PACOTE DE POLÍTICAS DO LOTE (vale para todas as páginas):\n" + comum
                    + "\n") if comum else "")
                + indice_factual_do_lote(fatos_do_lote) + "\n"
                + json.dumps({"brief_pre_arquitetura": brief_para_revisao(
                    state.brief_pre_arquitetura), "paginas": prompts}, ensure_ascii=False))
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
