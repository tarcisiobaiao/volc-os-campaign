"""
Separação dos dois textos do admin (v7_14).

  · insights          -> user prompt do AGENTE de funil
  · task_description  -> corpo da task no ClickUp

Nenhum dos dois pode aparecer no DOCX do briefing. Até a v7_13 o `insights` era
impresso num box "Registrado pelo admin" no fim do documento — o prompt do agente
vazava para dentro do material entregue ao redator.

Run:  cd backend && pytest tests/test_admin_fields_separation.py -v
"""
from __future__ import annotations

import os
import sys
import zipfile
from io import BytesIO

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY", "CLICKUP_API_TOKEN"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.docx.funnel_briefing import build_funnel_briefing

INSIGHTS = "PROMPT_SECRETO_DO_AGENTE_naovazar"
TAREFA = "DESCRICAO_DA_TAREFA_para_o_executor"


def _card() -> dict:
    return {
        "id": 1,
        "country_code": "BR",
        "insights": INSIGHTS,
        "task_description": TAREFA,
        "entity": {
            "canonical_name": "CadÚnico",
            "full_name": "Cadastro Único",
            "country": "Brasil",
            "language": "pt-BR",
        },
        "pains": [{"pain_name": "Benefício bloqueado"}],
        "seed_queries": [{"query": "cadunico consulta"}],
        "funnel_hypotheses": [],
    }


def _funnel() -> dict:
    return {
        "funnel_strategy": {"avatar_summary": "Beneficiários do CadÚnico"},
        "pages": [
            {
                "position": 1,
                "page_number": 1,
                "page_title": "Como consultar o CadUnico",
                "emotional_goal": "Explicar a consulta sem burocracia",
            }
        ],
        "writing_jobs": [],
        "funnel_hypotheses": [],
    }


def _docx_text(raw: bytes) -> str:
    """Texto de TODAS as partes XML do .docx (um .docx é um zip de XMLs)."""
    with zipfile.ZipFile(BytesIO(raw)) as z:
        return "\n".join(
            z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml")
        )


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def test_docx_nao_contem_nenhum_dos_dois_campos():
    texto = _docx_text(build_funnel_briefing(_card(), _funnel(), year=2026))

    assert INSIGHTS not in texto, "o user prompt do agente vazou para o briefing"
    assert TAREFA not in texto, "a descrição da tarefa vazou para o briefing"
    assert "Registrado pelo admin" not in texto
    assert "Comentários" not in texto


def test_docx_continua_trazendo_o_conteudo_do_funil():
    """A remoção não pode ter levado junto o que o documento existe para mostrar."""
    texto = _docx_text(build_funnel_briefing(_card(), _funnel(), year=2026))

    assert "CadÚnico" in texto
    assert "Como consultar o CadUnico" in texto
    assert "Explicar a consulta sem burocracia" in texto


def test_docx_gera_sem_os_campos_no_card():
    """Card antigo (sem as colunas novas) não pode quebrar a geração."""
    card = _card()
    card.pop("insights")
    card.pop("task_description")
    raw = build_funnel_briefing(card, _funnel(), year=2026)
    assert raw[:2] == b"PK"  # zip válido






# ── a evidência de política precisa CHEGAR à tela ───────────────────────────
#
# ⚠️ Medido no card 65 em 19/08/2026. A tela mostrou duas vezes
# "A policy was violated. See PolicyViolationDetails for more detail." — a
# mensagem genérica do Google, que ela mesma manda trocar pelo detalhe.
#
# O detalhe existia no `FalhaGads`: NON_FAMILY_SAFE('como sacar o fgts na
# caixa') e PERSONAL_LOANS('saldo bloqueado fgts empréstimo como
# desbloquear'), as duas com `isentavel=True`. `projecao._falha` pedia
# `codigo`, `familia`, `caminho`, `indice` e `is_exemptible` — cinco nomes que
# a dataclass NÃO tem. Com `getattr(..., "")` nada levanta: os campos chegam
# vazios e o erro é mudo.

def test_projecao_da_falha_usa_os_nomes_reais_da_dataclass():
    """Os nomes têm de casar com `volc_ads/gads/errors.py`. Um `getattr` com
    nome errado não falha — devolve vazio, e o operador fica sem o motivo."""
    from dataclasses import fields

    from app.trafego import projecao
    from volc_ads.gads.errors import ChavePolitica, ErroGads, FalhaGads, Politica

    reais = {f.name for f in fields(ErroGads)}
    assert {"campo_codigo", "valor_codigo", "caminho_campo", "indice_operacao"} <= reais

    erro = ErroGads(
        campo_codigo="policy_violation_error", valor_codigo="POLICY_ERROR",
        mensagem="A policy was violated. See PolicyViolationDetails for more detail.",
        caminho_campo="mutate_operations[13]...keyword.text", indice_operacao=13,
        gatilho="como sacar o fgts na caixa",
        politica=Politica(formato="violacao", isentavel=True,
                          chave=ChavePolitica("NON_FAMILY_SAFE",
                                              "como sacar o fgts na caixa")),
    )
    d = projecao._falha(FalhaGads(erros=(erro,), request_id="req-1"))

    e = d["erros"][0]
    assert e["codigo"] == "policy_violation_error"
    assert e["valor"] == "POLICY_ERROR"
    assert e["indice"] == 13
    assert e["caminho"].startswith("mutate_operations[13]")
    assert e["gatilho"] == "como sacar o fgts na caixa"


def test_a_tela_recebe_o_texto_que_violou_e_se_da_para_isentar():
    """Sem estes dois, "reprovado" é um beco: não se sabe o que tirar nem se
    existe caminho de volta."""
    from app.trafego import projecao
    from volc_ads.gads.errors import ChavePolitica, ErroGads, FalhaGads, Politica

    erro = ErroGads(
        campo_codigo="policy_violation_error", valor_codigo="POLICY_ERROR",
        mensagem="A policy was violated.", gatilho="como sacar o fgts na caixa",
        politica=Politica(formato="violacao", isentavel=True,
                          chave=ChavePolitica("NON_FAMILY_SAFE",
                                              "como sacar o fgts na caixa")),
    )
    d = projecao._falha(FalhaGads(erros=(erro,)))

    assert d["textos_violadores"] == ["como sacar o fgts na caixa"]
    assert d["chaves_isentaveis"] and "NON_FAMILY_SAFE" in d["chaves_isentaveis"][0]
    assert d["de_politica"] is True
    p = d["erros"][0]["politica"]
    assert p["isentavel"] is True
    assert p["remedio"] == "exempt_policy_violation_keys"
    assert p["chave"] == {"policy_name": "NON_FAMILY_SAFE",
                          "violating_text": "como sacar o fgts na caixa"}


def test_violacao_nao_isentavel_e_dita_como_nao_isentavel():
    """`isentavel=False` significa "esta tem de sair". Confundir com `None`
    faria a tela oferecer um pedido de isenção que a API rejeita."""
    from app.trafego import projecao
    from volc_ads.gads.errors import ErroGads, FalhaGads, Politica

    erro = ErroGads(campo_codigo="policy_violation_error", valor_codigo="POLICY_ERROR",
                    mensagem="x", gatilho="y",
                    politica=Politica(formato="violacao", isentavel=False))
    d = projecao._falha(FalhaGads(erros=(erro,)))

    assert d["erros"][0]["politica"]["isentavel"] is False
    assert d["chaves_isentaveis"] == []
