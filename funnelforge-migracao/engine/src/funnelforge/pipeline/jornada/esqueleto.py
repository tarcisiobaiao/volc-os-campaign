"""Revisor do ESQUELETO: valida o mapa inteiro ANTES de qualquer chamada paga.

Os bloqueantes entram no `funnel_graph` (via `routing.validate_funnel_graph`),
o portão que aborta o run antes da pesquisa. Bloqueio exige prova estrutural;
proxy de termo (sobreposição de palavras) é sempre AVISO.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from funnelforge.domain.models import (
    CANAIS_FRIOS,
    FunnelPlan,
    Issue,
    Page,
    PageRole,
    effective_role,
)
from funnelforge.pipeline.copy_contract import cta_generico
from funnelforge.pipeline.jornada._comum import (
    adjacencia,
    ciclo_justificado,
    ciclos,
    classificar_saida_oficial,
    conclusiva,
    cta_do_link,
    descreve_ciclo,
    estado_do_leitor,
    justificado,
    links,
    norm,
    por_duvida,
    por_slug,
    rotulo,
    tem_jornada,
    tokens,
)
from funnelforge.pipeline.validators.briefing_contract import (
    INTENCOES_VISUAIS,
    canon_padrao,
)

#: Que ENTREGA da página justifica cada intenção visual. Um bloco cuja intenção
#: não corresponde a nenhuma entrega declarada é enfeite, não função.
ENTREGAS_POR_INTENCAO: dict[str, frozenset[str]] = {
    "comparar": frozenset({"comparacao", "tabela", "decisao_pratica"}),
    "passo_a_passo": frozenset({"passo_a_passo", "proximo_passo_concreto"}),
    "checklist": frozenset({"checklist"}),
    "fato_chave": frozenset({"resposta_direta", "fonte_oficial_explicada", "exemplo"}),
    "navegacao_por_regiao": frozenset({"decisao_pratica", "fonte_oficial_explicada",
                                       "tabela", "proximo_passo_concreto"}),
    "atencao": frozenset({"resposta_direta", "passo_a_passo", "checklist",
                          "fonte_oficial_explicada", "decisao_pratica"}),
    "faq": frozenset({"resposta_direta"}),
    "exemplos_numericos": frozenset({"exemplo", "calculo", "tabela"}),
    "cards_factuais": frozenset({"resposta_direta", "comparacao", "exemplo"}),
    "timeline": frozenset({"passo_a_passo", "tabela"}),
    "decisao": frozenset({"decisao_pratica"}),
    "proximos_passos": frozenset({"proximo_passo_concreto", "passo_a_passo"}),
    "citacao_util": frozenset({"fonte_oficial_explicada", "resposta_direta"}),
    "calculo": frozenset({"calculo", "ferramenta"}),
    "ferramenta": frozenset({"ferramenta", "calculo", "checklist", "decisao_pratica"}),
    "prova_oficial": frozenset({"fonte_oficial_explicada"}),
    "imagem_editorial": frozenset({"resposta_direta", "exemplo", "passo_a_passo"}),
}

#: Campos sem os quais um ativo interativo não é gerado.
CAMPOS_DO_ATIVO = ("logica", "resultado", "fallback_sem_js",
                   "acessibilidade", "evento_de_medicao")


@dataclass
class RevisaoDoEsqueleto:
    bloqueantes: list[Issue] = field(default_factory=list)
    avisos: list[Issue] = field(default_factory=list)


def ativo_completo(ativo) -> list[str]:
    """Os campos que faltam num ativo (lista vazia = completo)."""
    faltam = [c for c in CAMPOS_DO_ATIVO if not str(getattr(ativo, c, "") or "").strip()]
    if not (getattr(ativo, "rule_source_fact_id", "")
            or str(getattr(ativo, "fonte_da_regra", "") or "").strip()):
        faltam.append("rule_source_fact_id")
    if not ativo.entradas:
        faltam.append("entradas")
    return faltam


def _lp_so_roteia(page: Page, slugs: dict[str, Page]) -> bool:
    """A resposta da LP diz algo além do menu de destinos? Regra estreita: tira
    da resposta os termos que já estão nos rótulos/H1/motivos dos destinos; se
    não sobra nada, a LP só repete o menu."""
    resposta = tokens(page.jornada.resposta_imediata) if page.jornada else set()
    if not resposta:
        return True
    do_menu: set[str] = set()
    for link in links(page):
        alvo = slugs.get(link.target)
        if alvo is None:
            continue
        do_menu |= tokens(link.reason) | tokens(alvo.h1_title) | tokens(cta_do_link(link, alvo))
        if alvo.editorial is not None:
            do_menu |= tokens(alvo.editorial.cta_label)
    return not (resposta - do_menu)


def _ctas(p: Page, slugs: dict[str, Page], b, a, *, principal_ja_bloqueia: bool) -> None:
    """Os botões da página como o leitor os vê, um a um.

    Bloqueia só o que é prova estrutural: dois destinos diferentes com o MESMO
    texto (um dos botões promete o que o destino dele não entrega). Rótulo
    genérico, CTA sem nenhum termo do que o destino entrega e falta de tensão
    residual são AVISO: proxy de termo nunca bloqueia."""
    j = p.jornada
    vistos: dict[str, str] = {}
    for link in links(p):
        alvo = slugs.get(link.target)
        if alvo is None or alvo.jornada is None:
            continue
        texto = cta_do_link(link, alvo)
        chave = norm(texto)
        if chave and chave in vistos and vistos[chave] != alvo.slug:
            b(Issue(code="ctas_iguais",
                    message=f"[{j.duvida_id}] o botão '{texto}' leva a '{vistos[chave]}' e "
                            f"a '{alvo.slug}': destinos diferentes pedem promessas "
                            "diferentes. Declare `links[].cta` com a resposta de cada um."))
        vistos.setdefault(chave, alvo.slug)
        principal = alvo.jornada.duvida_id == j.proxima_duvida
        if principal_ja_bloqueia and principal and (
                cta_generico(texto) or chave == norm(alvo.h1_title)):
            continue  # o bloqueante `cta_principal_generico` já nomeia este caso
        if cta_generico(texto):
            a(Issue(code="cta_generico",
                    message=f"[{j.duvida_id}] '{texto}' serviria a qualquer destino: diga a "
                            "dor/desejo do leitor, a próxima resposta e a consequência."))
            continue
        entrega = " ".join(filter(None, (
            alvo.h1_title, alvo.jornada.pergunta_principal, alvo.jornada.resposta_imediata,
            alvo.editorial.useful_delivery if alvo.editorial else "",
            alvo.jornada.valor.informacao_nova if alvo.jornada.valor else "")))
        if tokens(texto) and not (tokens(texto) & tokens(entrega)):
            a(Issue(code="cta_sem_correspondencia_no_destino",
                    message=f"[{j.duvida_id}] '{texto}' não ecoa nada do que "
                            f"'{alvo.jornada.duvida_id}' entrega: confira se o destino "
                            "cumpre a promessa do botão."))
    if j.proxima_duvida and not j.tensao_residual.strip():
        a(Issue(code="tensao_residual_ausente",
                message=f"[{j.duvida_id}] tem próxima dúvida, mas não declara a "
                        "tensão residual que a entrega abre: o CTA principal fica sem motivo."))
    if effective_role(p) is PageRole.PRESELL and len(links(p)) < 2:
        a(Issue(code="presell_sem_escolha",
                message=f"[{j.duvida_id}] pré-sell com menos de dois caminhos não ajuda a "
                        "escolher: dê a ela ramificação real ou funda-a na LP."))


def _valor(plan: FunnelPlan, b, a) -> None:
    vistos: dict[str, str] = {}
    for p in plan.pages:
        j = p.jornada
        v = j.valor
        if v is None:
            b(Issue(code="valor_nao_declarado",
                    message=f"[{j.duvida_id}] sem `valor`: a página não diz que problema "
                            "resolve, que informação nova entrega e o que o leitor faz "
                            "depois. Página só para recircular não vai à redação."))
            continue
        faltam = [c for c in ("problema", "informacao_nova", "capacidade_do_leitor")
                  if not getattr(v, c).strip()]
        if not v.entregas:
            faltam.append("entregas")
        if faltam:
            b(Issue(code="valor_incompleto",
                    message=f"[{j.duvida_id}] valor sem {', '.join(faltam)}."))
        if not v.evidencia.strip():
            a(Issue(code="valor_sem_evidencia",
                    message=f"[{j.duvida_id}] não diz que evidência sustenta a resposta."))
        chave = norm(v.informacao_nova)
        if chave and chave in vistos:
            b(Issue(code="fusao_necessaria",
                    message=f"[{j.duvida_id}] entrega a mesma informação nova que "
                            f"[{vistos[chave]}]: funda as páginas antes da redação."))
        vistos.setdefault(chave, j.duvida_id)
    paginas = [p for p in plan.pages if p.jornada.valor is not None]
    for i, p in enumerate(paginas):
        for q in paginas[i + 1:]:
            vp, vq = p.jornada.valor, q.jornada.valor
            tp = tokens(f"{vp.informacao_nova} {vp.capacidade_do_leitor}")
            tq = tokens(f"{vq.informacao_nova} {vq.capacidade_do_leitor}")
            if not tp or not tq or norm(vp.informacao_nova) == norm(vq.informacao_nova):
                continue
            jac = len(tp & tq) / len(tp | tq)
            if jac >= 0.6 and set(vp.entregas) == set(vq.entregas):
                a(Issue(code="fusao_sugerida",
                        message=f"[{p.jornada.duvida_id} x {q.jornada.duvida_id}] entregas "
                                f"parecidas (sobreposição {jac:.2f}); confira se não são a "
                                f"mesma página. Motivo declarado para não fundir: "
                                f"'{vp.por_que_nao_fundir or 'não declarado'}'."))


def _plano_visual(p: Page, b, a) -> None:
    j = p.jornada
    entregas = set(j.valor.entregas) if j.valor else set()
    for i, bloco in enumerate(j.plano_visual):
        onde = f"[{j.duvida_id}] plano_visual[{i}] ({bloco.secao})"
        padrao = canon_padrao(bloco.padrao)
        if bloco.intencao not in INTENCOES_VISUAIS or not padrao:
            b(Issue(code="bloco_fora_do_vocabulario",
                    message=f"{onde}: intenção '{bloco.intencao}' / padrão '{bloco.padrao}' "
                            "fora do vocabulário do plano visual."))
            continue
        if padrao not in INTENCOES_VISUAIS[bloco.intencao]:
            b(Issue(code="bloco_incompativel_com_a_funcao",
                    message=f"{onde}: '{padrao}' não serve a '{bloco.intencao}' "
                            f"({', '.join(INTENCOES_VISUAIS[bloco.intencao])})."))
        if not bloco.funcao.strip():
            b(Issue(code="bloco_sem_funcao_editorial",
                    message=f"{onde}: declare a função editorial do bloco."))
        justifica = ENTREGAS_POR_INTENCAO.get(bloco.intencao, frozenset())
        if entregas and not (entregas & justifica):
            # AVISO, não bloqueio: um bloco a mais que nenhuma entrega declarou é
            # oportunidade editorial, não erro de estrutura. Medido no card real
            # #65 (08/10/2026): um "próximos passos" na LP abortava o funil
            # inteiro antes da pesquisa.
            a(Issue(code="bloco_sem_entrega_correspondente",
                    message=f"{onde}: '{bloco.intencao}' não corresponde a nenhuma entrega "
                            f"declarada ({', '.join(sorted(entregas))})."))
        if padrao == "html" and not j.ativos:
            b(Issue(code="ferramenta_sem_ativo",
                    message=f"{onde}: bloco de ferramenta sem `ativos` que a especifique."))
    declarados = {r.id for r in j.requisitos}
    for k, ativo in enumerate(j.ativos):
        for campo in ("rule_source_fact_id", "current_value_source_fact_id"):
            alvo = getattr(ativo, campo, "")
            if alvo and alvo not in declarados:
                b(Issue(code="ativo_requisito_inexistente",
                        message=f"[{j.duvida_id}] ativos[{k}].{campo} = '{alvo}' não é um "
                                "requisito factual declarado desta página."))
        faltam = ativo_completo(ativo)
        if faltam:
            a(Issue(code="ativo_rejeitado",
                    message=f"[{j.duvida_id}] ativos[{k}] ('{ativo.pergunta}') não será "
                            f"gerado: falta {', '.join(faltam)}."))


def revisar_esqueleto(plan: FunnelPlan | None) -> RevisaoDoEsqueleto:
    """Valida o MAPA inteiro da jornada. Sem jornada no plano: nada a dizer."""
    rev = RevisaoDoEsqueleto()
    if not tem_jornada(plan):
        return rev
    assert plan is not None
    b, a = rev.bloqueantes.append, rev.avisos.append
    sem = [p.slug for p in plan.pages if p.jornada is None]
    if sem:
        b(Issue(code="jornada_incompleta",
                message=f"Páginas sem jornada num funil com jornada: {sem}. "
                        "O arquiteto precisa declarar a jornada de todas."))
        return rev
    for p in plan.pages:
        if p.editorial is None:
            b(Issue(code="jornada_sem_editorial",
                    message=f"[{p.jornada.duvida_id}] jornada sem contrato editorial: "
                            "os destinos da página vêm de `editorial.links`."))
    if rev.bloqueantes:
        return rev

    slugs, ids = por_slug(plan), {}
    for p in plan.pages:
        ids.setdefault(p.jornada.duvida_id, []).append(p.slug)
    for duvida, lista in ids.items():
        if len(lista) > 1:
            b(Issue(code="duvida_duplicada",
                    message=f"[{duvida}] a mesma dúvida em {lista}: uma pergunta principal "
                            "por página; funda as páginas ou separe as dúvidas."))
    perguntas: dict[str, str] = {}
    for p in plan.pages:
        chave = norm(p.jornada.pergunta_principal)
        if chave in perguntas and perguntas[chave] != p.jornada.duvida_id:
            b(Issue(code="duvida_duplicada",
                    message=f"[{p.jornada.duvida_id}] repete a pergunta de "
                            f"[{perguntas[chave]}]: '{p.jornada.pergunta_principal}'."))
        perguntas.setdefault(chave, p.jornada.duvida_id)

    def _ref(origem: str, campo: str, valor: str) -> None:
        if valor and valor not in ids:
            b(Issue(code="referencia_de_duvida_inexistente",
                    message=f"[{origem}] {campo} aponta para a dúvida '{valor}', "
                            "que nenhuma página do funil responde."))

    for p in plan.pages:
        j = p.jornada
        for r in j.ja_resolvido:
            _ref(j.duvida_id, "ja_resolvido", r)
        if j.duvida_id in j.ja_resolvido:
            b(Issue(code="referencia_de_duvida_inexistente",
                    message=f"[{j.duvida_id}] declara a própria dúvida como já resolvida."))
        _ref(j.duvida_id, "proxima_duvida", j.proxima_duvida)
        for alvo in j.retornos_justificados:
            _ref(j.duvida_id, "retornos_justificados", alvo)
    if plan.jornada is not None:
        _ref("funil", "checkpoint", plan.jornada.checkpoint)
        _ref("funil", "solucao_principal", plan.jornada.solucao_principal)
        for c in plan.jornada.coortes:
            _ref(f"coorte:{c.canal}", "entrada", c.entrada)
            _ref(f"coorte:{c.canal}", "proximo_passo", c.proximo_passo)
    if rev.bloqueantes:
        return rev

    duvidas = por_duvida(plan)
    for p in plan.pages:
        j, papel = p.jornada, effective_role(p)
        if plan.brief_pre_arquitetura is not None:
            # Um HUB puramente decisional pode orientar a escolha sem afirmar
            # regra, número, prazo ou procedimento. Exigir um requisito factual
            # nele força o arquiteto a inventar uma pesquisa para um menu. LPs e
            # SOLUTIONs continuam fail-closed: elas fazem a entrega substantiva.
            if not j.requisitos:
                b(Issue(code="requisitos_previsiveis_ausentes", message=f"[{j.duvida_id}] "
                        "o arquiteto precisa declarar requisitos antes da redação."))
            if j.proxima_duvida and j.proxima_duvida in j.ja_resolvido:
                b(Issue(code="cta_repetido_apos_resolvido", message=f"[{j.duvida_id}] "
                        "CTA principal reoferece dúvida que o plano declara resolvida."))
            for link in links(p):
                alvo = slugs.get(link.target)
                if alvo and alvo.jornada and alvo.jornada.duvida_id == j.proxima_duvida:
                    label = cta_do_link(link, alvo)
                    if cta_generico(label) or norm(label) == norm(alvo.h1_title):
                        b(Issue(code="cta_principal_generico", message=f"[{j.duvida_id}] "
                                "rótulo principal não traduz o avanço concreto do leitor."))
        destinos = [slugs[l.target] for l in links(p) if l.target in slugs]
        ids_destino = {d.jornada.duvida_id for d in destinos}
        if papel is PageRole.LP:
            if _lp_so_roteia(p, slugs):
                b(Issue(code="lp_so_roteia",
                        message=f"[{j.duvida_id}] a LP só roteia: a resposta imediata está "
                                "vazia ou repete o menu de destinos. Ela precisa responder "
                                "algo por si antes de pedir o clique."))
        elif not j.resposta_imediata.strip():
            b(Issue(code="resposta_imediata_ausente",
                    message=f"[{j.duvida_id}] sem resposta imediata: a primeira dobra não "
                            "tem promessa a cumprir."))
        if papel is not PageRole.LP and j.entrada_direta == "depende_de_contexto":
            b(Issue(code="entrada_direta_dependente",
                    message=f"[{j.duvida_id}] depende da página anterior para fazer "
                            "sentido; quem entra direto pela busca ou por um link "
                            "compartilhado precisa resolver a tarefa aqui."))
        if j.proxima_duvida and j.proxima_duvida not in ids_destino:
            b(Issue(code="proxima_duvida_sem_destino",
                    message=f"[{j.duvida_id}] a próxima dúvida é '{j.proxima_duvida}', mas "
                            "nenhum destino da página a resolve; o CTA principal tem de "
                            "levar à próxima dúvida."))

        # REOFERTA: bloqueia só o que está resolvido em TODO caminho até aqui.
        estado = estado_do_leitor(plan, p)
        for d in destinos:
            alvo = d.jornada.duvida_id
            motivo = justificado(p, d)
            if alvo in estado.certamente:
                if motivo:
                    a(Issue(code="retorno_justificado",
                            message=f"[{j.duvida_id}] volta a '{alvo}' (resolvida em todo "
                                    f"caminho até aqui) com justificativa: {motivo}."))
                else:
                    b(Issue(code="cta_repetido_apos_resolvido",
                            message=f"[{j.duvida_id}] oferece de novo '{alvo}', que todo "
                                    "leitor que chega aqui já resolveu: é convite para "
                                    "circular, não orientação."))
            elif alvo in estado.possivelmente:
                a(Issue(code="cta_contextual",
                        message=f"[{j.duvida_id}] '{alvo}' está resolvida só em parte dos "
                                "caminhos (há entrada direta aqui): mantenha o CTA como "
                                "secundário e condicional, nunca como principal."))
        if not destinos and not conclusiva(p):
            b(Issue(code="beco_sem_saida",
                    message=f"[{j.duvida_id}] sem destino e sem conclusão declarada "
                            "(condição terminal ou saída oficial boa)."))
        if not j.proxima_duvida and not j.condicao_terminal.strip() and destinos:
            a(Issue(code="proxima_duvida_nao_declarada",
                    message=f"[{j.duvida_id}] tem destinos mas não declara a próxima "
                            "dúvida: o CTA principal fica sem critério."))

        calculada = classificar_saida_oficial(p)
        declarada = j.saida_oficial.classificacao
        if papel is PageRole.LP and calculada == "prematura":
            a(Issue(code="saida_oficial_prematura",
                    message=f"[{j.duvida_id}] saída oficial direto na LP antes da "
                            "qualificação: prematura (salvo justificativa explícita)."))
        if j.saida_oficial.esperada and declarada != calculada:
            a(Issue(code="saida_oficial_divergente",
                    message=f"[{j.duvida_id}] o arquiteto declarou a saída oficial como "
                            f"'{declarada}', a régua calcula '{calculada}' "
                            "(boa exige condição terminal ou justificativa)."))
        _plano_visual(p, b, a)
        _ctas(p, slugs, b, a,
              principal_ja_bloqueia=plan.brief_pre_arquitetura is not None)
    _valor(plan, b, a)

    adj = adjacencia(plan)
    for ciclo in ciclos(adj):
        descricao = descreve_ciclo(ciclo, slugs)
        motivo = ciclo_justificado(ciclo, slugs)
        if motivo:
            a(Issue(code="retorno_justificado",
                    message=f"ciclo {descricao} mantido com justificativa: {motivo}."))
        else:
            b(Issue(code="loop_sem_ganho",
                    message=f"ciclo {descricao} sem ganho de informação: o clique devolve "
                            "o leitor a uma dúvida que ele já resolveu. Declare "
                            "`retornos_justificados` ou tire uma das arestas."))

    entradas_ = {p.slug for p in plan.pages
                 if effective_role(p) is PageRole.LP or p.jornada.coortes_de_entrada}
    if plan.jornada is not None:
        entradas_ |= {duvidas[c.entrada].slug for c in plan.jornada.coortes}
    for slug in sorted(entradas_):
        vistos, pilha = set(), [slug]
        while pilha:
            atual = pilha.pop()
            if atual in vistos:
                continue
            vistos.add(atual)
            pilha.extend(adj.get(atual, []))
        if not any(conclusiva(slugs[s]) for s in vistos):
            b(Issue(code="entrada_sem_conclusao",
                    message=f"[{rotulo(slugs[slug])}] quem entra aqui não tem caminho "
                            "até uma conclusão (condição terminal ou saída oficial boa)."))

    fj = plan.jornada
    if fj is not None:
        if fj.checkpoint and not conclusiva(duvidas[fj.checkpoint]):
            a(Issue(code="checkpoint_sem_conclusao",
                    message=f"o checkpoint '{fj.checkpoint}' não declara condição terminal "
                            "nem saída oficial boa."))
        for c in fj.coortes:
            entrada = duvidas[c.entrada]
            ids_destino = {slugs[l.target].jornada.duvida_id for l in links(entrada)
                           if l.target in slugs}
            if c.proximo_passo and c.proximo_passo not in ids_destino:
                b(Issue(code="coorte_proximo_passo_fora_do_mapa",
                        message=f"[coorte:{c.canal}] o próximo passo '{c.proximo_passo}' "
                                f"não é destino de '{c.entrada}'."))
            if c.canal in CANAIS_FRIOS and c.profundidade == "guiada":
                a(Issue(code="coorte_fria_sem_resposta_direta",
                        message=f"[coorte:{c.canal}] tráfego frio com profundidade guiada: "
                                "quem chega sem tarefa decide em um ou dois olhares."))
        quentes = [c for c in fj.coortes if c.canal == "paid_search"]
        frias = [c for c in fj.coortes if c.canal in CANAIS_FRIOS]
        for q in quentes:
            for f in frias:
                if q.entrada == f.entrada and norm(q.promessa) == norm(f.promessa):
                    a(Issue(code="promessa_identica_entre_coortes",
                            message=f"[coorte:{q.canal} x coorte:{f.canal}] mesma promessa "
                                    f"na mesma entrada ('{q.promessa}'): busca paga de alta "
                                    "intenção e tráfego frio não deveriam receber a mesma "
                                    "promessa, profundidade e próximo passo por padrão."))
    _message_match(plan, a)
    return rev


def termos_de_aquisicao(plan: FunnelPlan) -> set[str]:
    termos: set[str] = set()
    anuncio = plan.contexto_de_anuncio
    if anuncio is not None and anuncio.estado == "presente":
        for t in [*anuncio.titulos, *anuncio.descricoes]:
            termos |= tokens(t)
    busca = plan.contexto_de_busca
    if busca is not None and busca.estado == "presente":
        for t in busca.termos:
            termos |= tokens(t.termo)
    return termos


def _message_match(plan: FunnelPlan, aviso) -> None:
    """Congruência query/anúncio → LP: proxy por termo, então só AVISO."""
    termos = termos_de_aquisicao(plan)
    if not termos:
        return
    lp = next((p for p in plan.pages if effective_role(p) is PageRole.LP and p.jornada), None)
    if lp is None:
        return
    texto = f"{lp.jornada.pergunta_principal} {lp.jornada.resposta_imediata}"
    if plan.jornada is not None:
        texto += " " + " ".join(c.promessa for c in plan.jornada.coortes
                                if c.canal == "paid_search")
    if not (tokens(texto) & termos):
        aviso(Issue(code="message_match_fraco",
                    message="a pergunta, a resposta e a promessa paga da LP não ecoam "
                            "nenhum termo do anúncio nem da busca."))
