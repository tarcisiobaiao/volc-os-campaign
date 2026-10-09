"""Performance first, policy safe (08/10/2026): o contrato que leva ao maior
lucro esperado por visita sem atravessar intenção, valor, progressão honesta e
política.

Cobre os casos obrigatórios da missão:

- página com valor exclusivo preservada; pré-sell útil preservada, pré-sell sem
  escolha vira aviso, pré-sell que repete a LP pede fusão;
- três botões iguais recusados; CTA genérico identificado; CTA emocional e
  factual passa; CTA condicional para quem talvez já resolveu; destino cumpre o
  que o botão promete;
- página interna funciona em entrada direta;
- saída oficial não é forçada cedo e existe no momento da ação;
- revisor não bloqueia preferência de estilo, mas violação material bloqueia
  (casos de nota em `test_revisor_notas_existenciais`);
- Pautador -> brief leva dor e linguagem real ao arquiteto;
- campos novos vazios não mudam um byte de dump (pacote congelado, ouro V1 em
  `test_editorial_v2_flag_off_identico`; paralelismo em `test_paginas_paralelas`).
"""
from __future__ import annotations

import sys
from pathlib import Path

from funnelforge.domain.models import (
    BriefDoFunil,
    EditorialIntent,
    EditorialLink,
    FunnelPlan,
    JornadaDaPagina,
    Page,
    RequisitoFactual,
    SaidaOficialPrevista,
    ValorDaPagina,
)
from funnelforge.pipeline.copy_contract import cta_generico, cta_issues
from funnelforge.pipeline.inteligencia import compilar_brief, dores_da_demanda
from funnelforge.pipeline.jornada import (
    contexto_de_jornada,
    cta_do_link,
    politica_da_saida_oficial,
    revisar_esqueleto,
)
from funnelforge.pipeline.revisao import CRITERIOS_SO_AVISO
from funnelforge.prompts import render

_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from app.n8n_prompts import funnel_builder  # noqa: E402

LP, PR, DIREITO, RETIRADA, CADUNICO = (
    "gas", "gas-duvidas-pr", "gas-direito-p1", "gas-retirada-p2", "gas-cadunico-p3")


def _pagina(numero, slug, duvida, *, links=(), proxima="", tensao="", terminal="",
            saida=None, informacao="", entregas=("resposta_direta",), resposta="",
            rotulo="", h1="") -> Page:
    return Page(
        page_number=numero, page_type="LANDING PAGE" if numero == 1 else "SOLUÇÃO",
        h1_title=h1 or f"Gás do Povo: {duvida}", slug=slug,
        editorial=EditorialIntent(
            reader_question=f"Pergunta sobre {duvida}?", useful_delivery=informacao or duvida,
            cta_label=rotulo or f"Entender {duvida}",
            links=[EditorialLink(target=t, reason=f"motivo {t}", cta=c) for t, c in links]),
        jornada=JornadaDaPagina(
            duvida_id=duvida, pergunta_principal=f"Pergunta sobre {duvida}?",
            resposta_imediata=resposta or f"Resposta direta sobre {duvida} com critério verificável.",
            proxima_duvida=proxima, tensao_residual=tensao, condicao_terminal=terminal,
            saida_oficial=saida or SaidaOficialPrevista(),
            requisitos=[RequisitoFactual(id=f"{duvida}.regra", descricao=f"regra de {duvida}")],
            valor=ValorDaPagina(problema=f"problema de {duvida}",
                                informacao_nova=informacao or f"informação exclusiva de {duvida}",
                                capacidade_do_leitor=f"agir sobre {duvida}",
                                evidencia="dossiê", entregas=list(entregas))),
    )


def _plano(**troca) -> FunnelPlan:
    """Um funil profit-first saudável: LP que responde, pré-sell que ajuda a
    escolher, três soluções com entrega exclusiva e a saída oficial no fim."""
    boa = SaidaOficialPrevista(esperada=True, classificacao="boa")
    paginas = {
        LP: _pagina(1, LP, "gas_do_povo", proxima="escolha", rotulo="Entender o Gás do Povo",
                    tensao="sabe a regra geral, mas não sabe qual é o caso da família",
                    resposta="O Gás do Povo cobre a recarga para famílias do CadÚnico com "
                             "renda até meio salário mínimo por pessoa.",
                    informacao="quem é atendido e qual é a regra central",
                    links=[(PR, "Descobrir qual é o meu caso antes de ir à revenda"),
                           (DIREITO, "Ver se minha família entra na regra de renda"),
                           (RETIRADA, "Saber onde retirar e o que levar")]),
        PR: _pagina(2, PR, "escolha", proxima="direito", rotulo="Escolher meu caso",
                    tensao="o leitor se reconhece num caso, mas não sabe o próximo passo dele",
                    informacao="o caso típico de cada família e o caminho de cada caso",
                    entregas=("decisao_pratica",),
                    links=[(DIREITO, "Ver se minha família entra na regra de renda"),
                           (RETIRADA, "Saber onde retirar e o que levar"),
                           (CADUNICO, "Corrigir o CadÚnico antes de perder a recarga")]),
        DIREITO: _pagina(3, DIREITO, "direito", proxima="retirada",
                         tensao="sabe que tem direito, mas não sabe onde retirar",
                         terminal="o leitor sabe se a família entra na regra", saida=boa,
                         rotulo="Ver se minha família entra na regra",
                         informacao="o cálculo da renda por pessoa com exemplo",
                         entregas=("calculo", "exemplo"),
                         links=[(RETIRADA, "Saber onde retirar a recarga e o que levar")]),
        RETIRADA: _pagina(4, RETIRADA, "retirada", proxima="cadunico",
                          tensao="se a revenda recusar, o problema costuma estar no cadastro",
                          terminal="o leitor sabe onde e como retirar", saida=boa,
                          rotulo="Saber onde retirar e o que levar",
                          informacao="onde retirar a recarga, documentos e o que fazer na recusa",
                          entregas=("passo_a_passo", "checklist"),
                          links=[(CADUNICO, "Corrigir o cadastro se a revenda recusar")]),
        CADUNICO: _pagina(5, CADUNICO, "cadunico",
                          terminal="o leitor sabe como atualizar o cadastro", saida=boa,
                          rotulo="Corrigir o CadÚnico",
                          informacao="como atualizar o cadastro e quando procurar o CRAS",
                          entregas=("passo_a_passo",)),
    }
    paginas.update(troca)
    return FunnelPlan(pages=list(paginas.values()), total_pages=len(paginas))


def _codigos(issues) -> list[str]:
    return [i.code for i in issues]


# ---------------------------------------------------------------------------
# esqueleto: páginas, pré-sell e botões
# ---------------------------------------------------------------------------

def test_funil_profit_first_saudavel_passa_sem_bloqueio_nem_aviso_de_cta():
    rev = revisar_esqueleto(_plano())
    assert rev.bloqueantes == []
    avisos = set(_codigos(rev.avisos))
    assert not avisos & {"ctas_iguais", "cta_generico", "cta_sem_correspondencia_no_destino",
                         "tensao_residual_ausente", "presell_sem_escolha", "fusao_sugerida"}


def test_paginas_com_valor_exclusivo_sao_preservadas_mesmo_com_tema_parecido():
    """Mesmo tema, entrega própria: nada pede fusão."""
    plano = _plano()
    rev = revisar_esqueleto(plano)
    assert "fusao_necessaria" not in _codigos(rev.bloqueantes)
    assert "fusao_sugerida" not in _codigos(rev.avisos)
    assert len(plano.pages) == 5


def test_presell_emocionalmente_util_nao_e_eliminada():
    rev = revisar_esqueleto(_plano())
    assert all("[escolha]" not in i.message for i in rev.bloqueantes + rev.avisos)


def test_presell_sem_escolha_vira_aviso_e_nao_bloqueia_o_funil():
    pr = _pagina(2, PR, "escolha", proxima="direito", tensao="t",
                 informacao="três situações típicas e o caminho de cada uma",
                 links=[(DIREITO, "Ver se minha família entra na regra de renda")])
    rev = revisar_esqueleto(_plano(**{PR: pr}))
    assert "presell_sem_escolha" in _codigos(rev.avisos)
    assert "presell_sem_escolha" not in _codigos(rev.bloqueantes)


def test_presell_que_repete_a_lp_pede_fusao():
    pr = _pagina(2, PR, "escolha", proxima="direito", tensao="t",
                 informacao="quem é atendido e qual é a regra central",
                 links=[(DIREITO, "Ver se minha família entra na regra de renda"),
                        (RETIRADA, "Saber onde retirar e o que levar")])
    rev = revisar_esqueleto(_plano(**{PR: pr}))
    assert "fusao_necessaria" in _codigos(rev.bloqueantes)


def test_tres_botoes_iguais_para_destinos_diferentes_sao_recusados():
    igual = "Ver o próximo passo do benefício"
    pr = _pagina(2, PR, "escolha", proxima="direito", tensao="t",
                 informacao="três situações típicas e o caminho de cada uma",
                 links=[(DIREITO, igual), (RETIRADA, igual), (CADUNICO, igual)])
    rev = revisar_esqueleto(_plano(**{PR: pr}))
    assert _codigos(rev.bloqueantes).count("ctas_iguais") == 2


def test_rotulo_do_destino_repetido_em_varios_links_tambem_e_recusado():
    """Sem `links[].cta`, todos herdam o rótulo do destino; se dois destinos
    têm o MESMO rótulo, a página mostra dois botões iguais."""
    retirada = _plano().pages[3].model_copy(deep=True)
    retirada.editorial.cta_label = "Ver se minha família entra na regra"
    pr = _pagina(2, PR, "escolha", proxima="direito", tensao="t",
                 informacao="três situações típicas e o caminho de cada uma",
                 links=[(DIREITO, ""), (RETIRADA, "")])
    rev = revisar_esqueleto(_plano(**{PR: pr, RETIRADA: retirada}))
    assert "ctas_iguais" in _codigos(rev.bloqueantes)


def test_cta_generico_e_identificado():
    for rotulo in ("Saiba mais", "Continuar", "Próximo", "Ver conteúdo", "Ver guia",
                   "Clique aqui", "Acessar", "Confira", "Ver o guia de Gás do Povo"):
        assert cta_generico(rotulo), rotulo
    pr = _pagina(2, PR, "escolha", proxima="direito", tensao="t",
                 informacao="três situações típicas e o caminho de cada uma",
                 links=[(DIREITO, "Ver se minha família entra na regra de renda"),
                        (RETIRADA, "Confira")])
    rev = revisar_esqueleto(_plano(**{PR: pr}))
    assert "cta_generico" in _codigos(rev.avisos)
    assert rev.bloqueantes == []


def test_cta_principal_generico_bloqueia_no_caminho_do_brief():
    pr = _pagina(2, PR, "escolha", proxima="direito", tensao="t",
                 informacao="três situações típicas e o caminho de cada uma",
                 links=[(DIREITO, "Saiba mais"), (RETIRADA, "Saber onde retirar e o que levar")])
    plano = _plano(**{PR: pr})
    plano.brief_pre_arquitetura = BriefDoFunil(intencao_principal="Gás do Povo",
                                               trabalho_do_leitor="receber a recarga")
    assert "cta_principal_generico" in _codigos(revisar_esqueleto(plano).bloqueantes)


def test_cta_emocional_e_factual_passa():
    rotulos = ["Ver se minha família entra na regra de renda",
               "Corrigir o CadÚnico antes de perder a recarga",
               "Saber onde retirar e o que levar"]
    assert not any(cta_generico(r) for r in rotulos)
    pares = [(r, "https://exemplo.com.br/gas-direito-p1/") for r in rotulos]
    assert cta_issues(pares, {"copy_rapida": True, "domain": "https://exemplo.com.br"}) == []


def test_cta_continua_recusando_promessa_de_execucao():
    pares = [("Liberar minha recarga agora", "https://exemplo.com.br/gas-direito-p1/")]
    codigos = _codigos(cta_issues(pares, {"copy_rapida": True,
                                          "domain": "https://exemplo.com.br"}))
    assert "cta_editorial_execution" in codigos


def test_destino_cumpre_o_que_o_botao_promete():
    rev = revisar_esqueleto(_plano())
    assert "cta_sem_correspondencia_no_destino" not in _codigos(rev.avisos)
    direito = _plano().pages[2].model_copy(deep=True)
    direito.editorial.links[0].cta = "Simular o financiamento da casa própria"
    rev = revisar_esqueleto(_plano(**{DIREITO: direito}))
    assert "cta_sem_correspondencia_no_destino" in _codigos(rev.avisos)


def test_cta_por_origem_vai_para_a_ancora_e_o_contexto_do_redator():
    plano = _plano()
    pr, direito = plano.pages[1], plano.pages[2]
    link = pr.editorial.links[2]
    assert cta_do_link(link, plano.pages[4]) == "Corrigir o CadÚnico antes de perder a recarga"
    sem_cta = EditorialLink(target=CADUNICO, reason="r")
    assert cta_do_link(sem_cta, plano.pages[4]) == "Corrigir o CadÚnico"
    ctx = contexto_de_jornada(plano, direito)
    assert ctx["destinos"][0]["cta"] == "Saber onde retirar a recarga e o que levar"
    assert ctx["tensao_residual"] == "sabe que tem direito, mas não sabe onde retirar"
    texto = render("jornada_da_pagina", jornada=ctx)
    assert 'botão aprovado: "Saber onde retirar a recarga e o que levar"' in texto
    assert "Tensão residual legítima" in texto
    assert "promessa → resposta imediata → aprofundamento útil" in texto


def test_cta_condicional_para_quem_talvez_ja_resolveu():
    """Quem chega a `retirada` pela LP não passou por `direito`; quem vem de
    `direito`, passou. Um link de volta para `direito` é secundário e condicional."""
    retirada = _plano().pages[3].model_copy(deep=True)
    retirada.editorial.links.append(EditorialLink(
        target=DIREITO, reason="quem entrou direto ainda não fez a conta",
        cta="Se ainda não fez a conta da renda, ver se sua família entra"))
    retirada.jornada.retornos_justificados = {"direito": "quem entrou direto não fez a conta"}
    plano = _plano(**{RETIRADA: retirada})
    ctx = contexto_de_jornada(plano, plano.pages[3])
    volta = next(d for d in ctx["destinos"] if d["slug"] == DIREITO)
    assert volta["contextual"] and not volta["principal"]
    assert "[SECUNDÁRIO, CONDICIONAL]" in render("jornada_da_pagina", jornada=ctx)
    assert "cta_contextual" in _codigos(revisar_esqueleto(plano).avisos)


def test_tensao_residual_ausente_e_aviso():
    direito = _plano().pages[2].model_copy(deep=True)
    direito.jornada.tensao_residual = ""
    rev = revisar_esqueleto(_plano(**{DIREITO: direito}))
    assert "tensao_residual_ausente" in _codigos(rev.avisos)
    assert rev.bloqueantes == []


def test_pagina_interna_funciona_em_entrada_direta():
    plano = _plano()
    texto = render("jornada_da_pagina", jornada=contexto_de_jornada(plano, plano.pages[3]))
    assert "Quem entra direto" in texto
    retirada = plano.pages[3].model_copy(deep=True)
    retirada.jornada.entrada_direta = "depende_de_contexto"
    rev = revisar_esqueleto(_plano(**{RETIRADA: retirada}))
    assert "entrada_direta_dependente" in _codigos(rev.bloqueantes)


# ---------------------------------------------------------------------------
# saída oficial: no momento da ação, nunca escondida
# ---------------------------------------------------------------------------

def test_saida_oficial_nao_e_forcada_cedo():
    plano = _plano()
    for pagina in (plano.pages[2], plano.pages[3]):        # boa, mas com dúvida aberta
        pol = politica_da_saida_oficial(pagina)
        assert pol.classe == "boa" and pol.exige and not pol.primeiro
        texto = render("jornada_da_pagina", jornada=contexto_de_jornada(plano, pagina))
        assert "o CTA principal continua sendo a próxima dúvida" in texto


def test_saida_oficial_existe_no_momento_da_acao():
    plano = _plano()
    pol = politica_da_saida_oficial(plano.pages[4])        # terminal: agir
    assert pol.classe == "boa" and pol.exige and pol.primeiro
    assert politica_da_saida_oficial(plano.pages[0]).exige is False   # LP não sai


# ---------------------------------------------------------------------------
# revisor com autoridade reduzida (os casos de nota estão no teste do revisor)
# ---------------------------------------------------------------------------

def test_revisor_so_trava_politica_e_destino_e_aceita_copy_forte():
    assert CRITERIOS_SO_AVISO == {"cta_discipline", "useful_delivery"}
    texto = render("revisor", pagina={"numero": 3, "papel": "SOLUTION"},
                   criterios=["compliance", "cta_discipline", "useful_delivery",
                              "destination_relevance"],
                   criterios_so_aviso=["cta_discipline", "useful_delivery"], nota_minima=7,
                   exemplo_de_notas="{}", blocos={}, campos=["corpo"], tem_widget=False,
                   identidade={}, jornada={}, regras=[], notas_c=[], pacote={},
                   max_patches=8, ha_termos=False)
    assert "Copy comercialmente forte, emocional e factual passa" in texto
    assert "exceto em cta_discipline, useful_delivery" in texto


# ---------------------------------------------------------------------------
# Pautador -> brief -> arquiteto
# ---------------------------------------------------------------------------

def test_pautador_leva_dor_e_perguntas_medidas_ao_brief():
    card = {"main_keyword": "Gás do Povo", "country": "BR",
            "contexto_de_leitura": {"perguntas_paa": ["Quem tem direito ao Gás do Povo?"],
                                    "tensao": {"frase": "vou perder a recarga?",
                                               "evidencia": "PAA"}},
            "pains": [{"pain_name": "Revenda recusou",
                       "pain_description": "o cadastro não aparece"}],
            "concrete_pain": "não sei se fui incluído"}
    assert dores_da_demanda(card) == ["vou perder a recarga? (medido: PAA)",
                                      "Revenda recusou: o cadastro não aparece",
                                      "não sei se fui incluído"]
    brief = compilar_brief(card, {"perguntas": [], "origem": "teste"})
    assert brief.dores_observadas == dores_da_demanda(card)
    assert [d.jornada.pergunta_principal for d in brief.duvidas] == [
        "Quem tem direito ao Gás do Povo?"]


def test_arquiteto_recebe_o_contrato_profit_first():
    prompt = (funnel_builder.FUNNEL_ARCHITECT_SYSTEM_MESSAGE
              + funnel_builder.build_funnel_architect_user(
                  pais="BR", tema="Gás do Povo", lingua="pt-BR", data_atual="2026-10-08",
                  supporting_data="", user_questions=""))
    assert "Rótulo igual para entrega igual é correto" not in prompt
    assert "maior lucro esperado por visita" in prompt
    assert "tensao_residual" in prompt and '"cta": "..."' in prompt
    assert "Não minimize páginas" in prompt
    assert "Seguro não significa" in prompt and "sem emoção" in prompt


def test_campos_novos_vazios_nao_mudam_o_dump():
    """Pacotes congelados e estados antigos conferem byte a byte."""
    link = EditorialLink(target="a", reason="b")
    assert link.model_dump(mode="json") == {"target": "a", "reason": "b"}
    jornada = JornadaDaPagina(duvida_id="a", pergunta_principal="p")
    assert "tensao_residual" not in jornada.model_dump(mode="json")
    plano = _plano()
    plano.pages[2].jornada.tensao_residual = ""
    assert "tensao_residual" not in contexto_de_jornada(plano, plano.pages[2])
