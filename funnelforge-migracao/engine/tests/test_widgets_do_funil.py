"""Widgets de orientação prontos ANTES da redação: conteúdo do pacote, código do projeto."""
import json
import re

from funnelforge.domain.models import PageDraft, StepStatus
from funnelforge.pipeline.inteligencia import congelar_pacotes, prompt_do_pacote
from funnelforge.pipeline.steps import step_widget
from tests.test_ctas_do_funil import estado, roteiro

_PAGINA_RE = re.compile(r"^## Página (\d+) —", re.M)
_WIDGETS = "Você prepara as peças interativas"

NAVEGADOR = {
    "arquetipo": "navegador", "titulo": "Em que etapa da inscrição você está?",
    "subtitulo": "Escolha a etapa e veja o que fazer agora.",
    "controles": [{"id": "etapa", "rotulo": "Em que etapa você está?",
                   "opcoes": [{"valor": "inicio", "texto": "Ainda não comecei"},
                              {"valor": "envio", "texto": "Já enviei a inscrição"}]}],
    "cenarios": [
        {"quando": {"etapa": "inicio"}, "chip": "primeiro passo", "tom": "neutro",
         "titulo": "Comece pela unidade do seu estado",
         "passos": ["Procure a unidade do Senac do seu estado", "Separe os documentos"]},
        {"quando": {"etapa": "envio"}, "chip": "acompanhar", "tom": "ok",
         "titulo": "Acompanhe a resposta da unidade",
         "passos": ["Guarde o comprovante da inscrição", "Confira o contato da unidade"]}],
    "rodape": "Orientação com base nas regras do Senac."}


def com_widgets(respostas):
    base = roteiro()

    def responder(model, messages):
        prompt = messages[-1]["content"]
        if _WIDGETS in prompt:
            paginas = [int(n) for n in _PAGINA_RE.findall(prompt)]
            return json.dumps({"widgets": [
                {"page_number": n, **respostas(i)} for i, n in enumerate(paginas)]})
        return base(model, messages)
    return responder


def widget_calls(llm):
    return [c for c in llm.calls if _WIDGETS in c["messages"][-1]["content"]]


def test_uma_chamada_so_vira_ferramenta_o_que_passa_no_contrato(tmp_path):
    invalido = dict(NAVEGADOR, cenarios=NAVEGADOR["cenarios"][:1])
    respostas = {0: {"widget": NAVEGADOR},
                 1: {"widget": "NONE", "motivo": "a resposta é um único dado"},
                 2: {"widget": invalido}}
    state, deps, llm = estado(tmp_path, com_widgets(lambda i: respostas.get(i, respostas[1])))

    congelar_pacotes(state, deps)

    assert len(widget_calls(llm)) == 1
    recibo = json.loads(next(i.message for i in state.step_status["widgets_do_funil"].issues
                             if i.code == "widgets_do_funil"))
    pronta = recibo["prontas"]
    assert len(pronta) == 1 and recibo["recusadas"]
    assert any(m.startswith("NONE") for m in recibo["recusadas"].values())
    assert any("cenário" in m for m in recibo["recusadas"].values())
    n = pronta[0]
    orientacao = state.pacotes[n]["ferramenta"]["orientacao"]
    assert orientacao["tipo"] == "orientacao" and 'class="vw-' in orientacao["bloco"]
    assert orientacao["entradas"] and "não consulta cadastro" in orientacao["limites"]
    page = next(p for p in state.plan.pages if p.page_number == n)
    prompt = prompt_do_pacote(state, page)
    assert "Ferramenta pronta nesta página" in prompt and "Navegador de Jornada" in prompt
    assert orientacao["bloco"][:60] not in prompt         # o redator recebe a capacidade
    sem = [p for p in state.plan.pages if p.page_number not in pronta]
    assert all("orientacao" not in state.pacotes[p.page_number]["ferramenta"] for p in sem)


def test_widget_pronto_entra_sem_chamada_e_nada_e_gerado_depois(tmp_path):
    state, deps, llm = estado(tmp_path, com_widgets(lambda i: {"widget": NAVEGADOR}
                                                    if i == 0 else {"widget": "NONE"}))
    congelar_pacotes(state, deps)
    pronta = next(n for n, p in state.pacotes.items() if p["ferramenta"].get("orientacao"))
    corpo = ("<!-- wp:heading --><h2>Um</h2><!-- /wp:heading -->"
             "<!-- wp:paragraph --><p>Texto.</p><!-- /wp:paragraph -->"
             "<!-- wp:heading --><h2>Dois</h2><!-- /wp:heading -->")
    for p in state.plan.pages:
        if p.page_type != "LANDING PAGE":
            state.drafts[p.page_number] = PageDraft(page_number=p.page_number,
                                                    page_type=p.page_type,
                                                    format="gutenberg", content=corpo)
    antes = len(llm.calls)

    for p in state.plan.pages:
        step_widget(state, p, deps)

    assert len(llm.calls) == antes                          # nenhuma geração pós-redação
    assert state.step_status[f"widget_p{pronta}"].status is StepStatus.OK
    assert 'class="vw-' in state.drafts[pronta].content
    outra = next(p for p in state.plan.pages if p.page_type != "LANDING PAGE"
                 and p.page_number != pronta and not state.pacotes[p.page_number]
                 ["ferramenta"]["itens"])
    assert state.step_status[f"widget_p{outra.page_number}"].status is StepStatus.SKIPPED
    assert 'class="vw-' not in state.drafts[outra.page_number].content
