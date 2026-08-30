"""
Testes do prompt do Arquiteto de Funil (Pautador Pro — Task 6 / R4, R5, R6, R8).

Cobre:
- R4: campos `intro_section` / `closing_section` no schema de saída por página,
  com `hook_to_next_page`/`next_page_slug` explicitamente como metadado estrutural.
- R5: nenhum token de ano/data ([ano]/{ano}) nos templates de H1.
- R6: bloco de proibições de tom (PROIBIDO) substituindo o núcleo alarmista.
- R8: profundidade mínima de H2 por página de solução + anti-"linguiça".

Testa apenas o texto do prompt (system message + template de usuário) — não
testa parsing/consumo do JSON pelo page_factory (fora de escopo da Task 6).
"""
from app.n8n_prompts import funnel_builder as fb


def _full_prompt() -> str:
    """Concatena system message + template de usuário renderizado — o texto
    completo que efetivamente chega ao Gemini."""
    rendered_user = fb.build_funnel_architect_user(
        pais="Brasil",
        tema="Programa Exemplo",
        lingua="Português - Brasil",
        data_atual="2026-07-23",
        supporting_data="kw1, kw2",
        user_questions="Pergunta 1?",
    )
    return fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE + "\n" + rendered_user


# ---------------------------------------------------------------------------
# R4 — intro_section / closing_section
# ---------------------------------------------------------------------------

def test_output_schema_has_intro_and_closing():
    prompt = _full_prompt()
    assert "intro_section" in prompt
    assert "closing_section" in prompt


def test_existing_page_keys_still_present():
    """page_factory.py depende destas chaves — não podem ser removidas/renomeadas."""
    prompt = _full_prompt()
    for key in (
        "page_number",
        "page_type",
        "h1_title",
        "slug",
        "emotional_objective",
        "main_content_structure",
        "hook_to_next_page",
        "next_page_slug",
        "target_keywords",
    ):
        assert f'"{key}"' in prompt, f"chave existente {key!r} não pode sumir do schema"


def test_hook_to_next_page_is_structural_not_reader_cta():
    prompt = _full_prompt()
    assert "closing_section" in prompt
    # regra explícita de que hook_to_next_page/next_page_slug são metadado
    # estrutural e não podem viver dentro do closing_section
    assert "metadado" in prompt.lower() and "estrutural" in prompt.lower()


# ---------------------------------------------------------------------------
# IDIOMA POR CAMPO — split nativo (publicável) vs pt-BR (briefing do redator)
# ---------------------------------------------------------------------------

def test_per_field_language_rule_present():
    """O prompt precisa deixar EXPLÍCITO que nem tudo vai no idioma nativo:
    só o conteúdo PUBLICÁVEL (h1_title/H2/slug/keywords/hooks) vai em
    __LINGUA__; o briefing para o redator brasileiro (emotional_objective,
    intro_section, closing_section, funnel_strategy.avatar_summary/tone_voice)
    é SEMPRE pt-BR."""
    prompt = _full_prompt()
    assert "IDIOMA POR CAMPO" in prompt
    assert "h1_title" in prompt and "PT-BR" in prompt
    for field in (
        "emotional_objective",
        "intro_section",
        "closing_section",
        "avatar_summary",
        "tone_voice",
    ):
        assert field in prompt


def test_intro_and_closing_are_bullet_directives_in_pt_br():
    """intro_section/closing_section não são mais prosa pronta para publicar —
    são DIRETRIZES em bullets, em pt-BR, para o redator brasileiro escrever o
    texto final."""
    prompt = _full_prompt()
    assert "diretriz" in prompt.lower()
    assert "bullet" in prompt.lower()
    # exemplos de schema devem ser arrays, não string única
    assert '"intro_section": [' in prompt
    assert '"closing_section": [' in prompt
    # não pode sobrar instrução dizendo que intro/closing são publicados/
    # publicáveis ou no idioma nativo (isso é papel exclusivo de h1/H2/slug/etc.)
    prompt_lower = prompt.lower()
    assert "introdução provocativa que engaja o leitor, publicada" not in prompt_lower
    assert "introdução ponte que conecta" not in prompt_lower or "diretriz" in prompt_lower


# ---------------------------------------------------------------------------
# R5 — sem datas no H1
# ---------------------------------------------------------------------------

def test_no_year_token_in_h1_templates():
    prompt = _full_prompt()
    assert "[ano]" not in prompt
    assert "{ano}" not in prompt


def test_r5_inviolable_rule_present():
    prompt = _full_prompt()
    assert "PROIBIDO incluir ano ou data em qualquer" in prompt
    assert "h1_title" in prompt


# ---------------------------------------------------------------------------
# R6 — tom informacional, sem alarmismo
# ---------------------------------------------------------------------------

def test_banned_phrases_present():
    sys = fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE
    assert "PROIBIDO" in sys


def test_tom_prohibitions_block_present():
    sys = fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE
    assert "TOM (PROIBIÇÕES)" in sys
    assert "em X segundos" in sys
    assert "garantido" in sys.lower()


def test_no_alarmist_core_remains_anywhere_in_prompt():
    """Gate amplo do R6: nenhum resquício do núcleo alarmista original pode
    sobreviver em NENHUMA seção do prompt (system message + template de
    usuário renderizado), sob pena de contradizer o bloco `## ⚖️ TOM
    (PROIBIÇÕES)`. Cobre <user_avatar_protocol>, <funnel_architecture> e o
    <output_format>/<execution_order>, não só psychology_engine/hooks_mastery."""
    prompt_lower = _full_prompt().lower()
    for banned in (
        "compuls",
        "medo que você cria",
        "clicar compulsivamente",
        "clique parece compuls",
    ):
        assert banned not in prompt_lower, f"resquício alarmista ainda presente: {banned!r}"


def test_exaggerated_stats_removed():
    """As estatísticas fabricadas usadas como EXEMPLO de copy (ganchos/loops)
    devem sumir. (O bloco de proibições pode citar o padrão "elimina X%" como
    ilustração do que é banido — isso é esperado e não é o que este teste
    verifica.)"""
    prompt = _full_prompt()
    for banned in (
        "elimina 73% dos candidatos — e a maioria",
        "60% dos candidatos são eliminados",
        "Um erro comum elimina 70% dos candidatos",
        "90% das pessoas não sabem",
        "90% dos candidatos ignoram",
    ):
        assert banned not in prompt


# ---------------------------------------------------------------------------
# R8 — profundidade mínima por página de solução
# ---------------------------------------------------------------------------

def test_minimum_h2_depth_rule_present():
    prompt = _full_prompt()
    assert "4 H2" in prompt or "mínimo de 4" in prompt.lower() or "MÍNIMO DE 4" in prompt


def test_anti_padding_and_self_check_present():
    prompt = _full_prompt()
    assert "linguiça" in prompt.lower()
    assert "esta página é necessária" in prompt.lower()


# ---------------------------------------------------------------------------
# Assinatura preservada (build_funnel_architect_user)
# ---------------------------------------------------------------------------

def test_build_user_signature_still_renders_tokens():
    rendered = fb.build_funnel_architect_user(
        pais="Brasil",
        tema="Programa Exemplo",
        lingua="Português - Brasil",
        data_atual="2026-07-23",
        supporting_data="kw1, kw2",
        user_questions="Pergunta 1?",
    )
    assert "Brasil" in rendered
    assert "Programa Exemplo" in rendered
    assert "__PAIS__" not in rendered
    assert "__TEMA__" not in rendered


# ---------------------------------------------------------------------------
# Direcionamento do admin (campo Insights do card) — v7_12
# ---------------------------------------------------------------------------

def _base_kwargs() -> dict:
    return {
        "pais": "Brasil",
        "tema": "Programa Exemplo",
        "lingua": "Português - Brasil",
        "data_atual": "2026-07-23",
        "supporting_data": "kw1, kw2",
        "user_questions": "Pergunta 1?",
    }


def test_sem_direcionamento_o_prompt_e_byte_a_byte_o_de_hoje():
    """Card sem insights não pode mudar NADA no prompt — é o caminho de 100% das
    entidades que já existem hoje."""
    base = fb.build_funnel_architect_user(**_base_kwargs())
    for vazio in ("", "   ", None):
        assert fb.build_funnel_architect_user(**_base_kwargs(), admin_direction=vazio) == base


def test_direcionamento_entra_como_bloco_no_fim_da_missao():
    texto = "Focar em aposentados que caíram em golpe de empréstimo."
    rendered = fb.build_funnel_architect_user(**_base_kwargs(), admin_direction=texto)

    assert texto in rendered
    assert "DIRECIONAMENTO DO ADMIN" in rendered
    # o bloco vem DEPOIS das regras de saída (última instrução lida pelo modelo)
    assert rendered.index("</output_rules>") < rendered.index("DIRECIONAMENTO DO ADMIN")
    # e não desfaz o contrato de saída
    assert "__PAIS__" not in rendered


def test_direcionamento_muito_longo_e_truncado():
    rendered = fb.build_funnel_architect_user(**_base_kwargs(), admin_direction="x" * 9000)
    assert "x" * 4000 in rendered
    assert "x" * 4100 not in rendered
