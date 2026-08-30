"""
Escolha de PERGUNTA no arraste DESCOBERTAS -> EM VALIDAÇÃO (v7_17).

A entidade não tem UMA pergunta, tem várias, todas legítimas — foi por isso que
rotular a ENTIDADE não funcionou (33,3% de estabilidade entre rodadas contra
23,5% de acaso, p = 0,43; ver app/entities/leitura.py). Aqui o objeto é a
PERGUNTA, que é a unidade do gerador de funil.

O que estes testes protegem:
  1. os quatro desfechos gravam, e nenhum deles depende de nota;
  2. as descartadas são preservadas — o contrafactual que a base nunca teve;
  3. NENHUM código lê `pautador_question_choices` para calcular score.

Run:  cd backend && pytest tests/test_question_choice.py -v
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import ValidationError

from app.entities.leitura import respostas_validas
from app.entities.mock import mock_entity_discovery
from app.entities.orchestrator import _norm_item
from app.entities.schemas import QuestionChoiceRequest

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
TABELA = "pautador_question_choices"


# ── o contrato da escolha ───────────────────────────────────────────────────
def test_os_quatro_desfechos_sao_aceitos():
    for outcome in ("chosen", "custom", "skipped", "entity_rejected"):
        assert QuestionChoiceRequest(outcome=outcome).outcome == outcome


def test_desfecho_invalido_e_recusado():
    with pytest.raises(ValidationError):
        QuestionChoiceRequest(outcome="talvez")


def test_nota_e_justificativa_sao_opcionais():
    """Obrigar texto produz texto vazio; e não há nota nenhuma no contrato."""
    r = QuestionChoiceRequest()
    assert r.notes is None and r.custom_frase is None
    campos = set(QuestionChoiceRequest.model_fields)
    proibidos = {c for c in campos if any(p in c for p in ("score", "nota", "rank", "peso", "rating"))}
    assert not proibidos, f"o contrato da escolha não pode ter nota: {proibidos}"


def test_skipped_nao_precisa_de_indice():
    """`skipped` é DADO — o operador viu as perguntas e pulou. Não é ausência."""
    assert QuestionChoiceRequest(outcome="skipped").chosen_index is None


# ── as perguntas candidatas que alimentam a tela ────────────────────────────
def test_candidatas_trazem_frase_e_os_dois_eixos_por_pergunta():
    item = mock_entity_discovery("Brasil", "BR", "pt-BR", 3)["entities"][1]
    respostas = _norm_item(item, "Brasil", "BR", "pt-BR")["opportunity"]["respostas"]
    assert len(respostas) == 3
    for r in respostas:
        assert r["frase"] and r["engajamento_level"]
        # `ignorancia` POR PERGUNTA: no nível da pergunta o eixo é bem definido
        assert r["ignorancia_level"]


def test_ignorancia_por_pergunta_e_opcional_e_torta_nao_derruba():
    """Um eixo ausente ou torto não pode custar a pergunta inteira: sem a frase
    na tela, o operador não tem o que escolher."""
    opp = {"respostas": [
        {"frase": "sem ignorancia", "engajamento_level": "condicional"},
        {"frase": "ignorancia torta", "engajamento_level": "condicional", "ignorancia_level": "talvez"},
    ]}
    out = respostas_validas(opp)
    assert len(out) == 2
    assert "ignorancia_level" not in out[0] and "ignorancia_level" not in out[1]


def test_descartadas_sao_o_complemento_da_escolhida():
    """O contrafactual: toda pergunta que o sistema já viu foi uma que alguém
    escolheu. Sem guardar as outras duas não há o que perguntar depois."""
    candidatas = [{"frase": f"p{i}", "engajamento_level": "condicional"} for i in range(3)]
    escolhido = 1
    descartadas = [c for j, c in enumerate(candidatas) if j != escolhido]
    assert len(descartadas) == 2
    assert candidatas[escolhido] not in descartadas


# ── a trava: nada disto pode virar score ────────────────────────────────────
def _fontes_python():
    for f in APP.rglob("*.py"):
        if "motor_pautas" in f.parts or "__pycache__" in f.parts:
            continue
        yield f


def test_nenhum_codigo_calcula_score_a_partir_da_tabela_de_escolhas():
    """A trava do §3. Se o mesmo LLM inventa as perguntas e depois pontua as
    próprias invenções, isso é circuito fechado de opinião, não medição.

    Falha se um módulo que menciona a tabela também menciona score/ranking/
    ordenação. O ledger existe para criar histórico — quando houver desfecho
    medido (receita e custo por pergunta × página × período), aí se pergunta se
    o eixo prevê alguma coisa. Não antes.

    A granularidade é a FUNÇÃO, não o arquivo: um módulo pode legitimamente
    tocar a tabela numa função e ordenar outra coisa por score em outra.
    """
    SUSPEITOS = ("score", "rank", "ordenar", "order_by", "weight", "peso", "rating")
    culpados = []
    for f in _fontes_python():
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if TABELA not in txt:
            continue
        arvore = ast.parse(txt)
        for fn in ast.walk(arvore):
            if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            # só as constantes de string do CORPO — docstring e comentários
            # citam "score" justamente para explicar a proibição.
            textos = [n.value.lower() for n in ast.walk(fn)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if not any(TABELA in t for t in textos):
                continue
            nomes = {n.id.lower() for n in ast.walk(fn) if isinstance(n, ast.Name)}
            nomes |= {n.attr.lower() for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
            corpo = textos[1:] if ast.get_docstring(fn) else textos
            achados = {s for s in SUSPEITOS
                       if any(s in n for n in nomes) or any(s in t for t in corpo)}
            if achados:
                culpados.append(f"{f.relative_to(APP)}::{fn.name} -> {sorted(achados)}")
    assert not culpados, "escolha de pergunta não pode alimentar score:\n" + "\n".join(culpados)


def test_a_escolha_nao_e_lida_por_nenhum_modulo_de_scoring():
    for nome in ("entities/scoring.py", "scoring.py", "entities/leitura.py"):
        f = APP / nome
        if f.exists():
            assert TABELA not in f.read_text(encoding="utf-8")


def test_endpoint_de_escolha_nao_muda_status_do_card():
    """O registro NÃO move o card e NÃO bloqueia: quem move é o arraste. Um
    registro que trava o trabalho deixa de ser preenchido em uma semana."""
    arvore = ast.parse((APP / "routers" / "entities.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arvore)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
              and n.name == "record_question_choice")
    chamadas = {n.func.attr for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for proibida in ("update_entity_opportunity", "update_entity", "patch", "delete"):
        assert proibida not in chamadas, f"o registro não pode chamar {proibida}"
    # e grava de fato
    assert "insert_question_choice" in chamadas
