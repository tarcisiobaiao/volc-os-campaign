from funnelforge.pipeline.validators import checks
from funnelforge.pipeline.validators.checks import run_validators
from funnelforge.domain.models import PageRole


def test_calm_utility_flags_official_impersonation():
    issues = run_validators(["calm_utility"], "Benefício liberado pelo governo agora.", {})
    assert any(i.code == "official_impersonation" for i in issues)


def test_calm_utility_flags_fear_and_passes_clean():
    assert any(i.code == "fear_language"
               for i in run_validators(["calm_utility"],
                                       "nao perca o prazo, muitos perdem", {}))
    assert run_validators(["calm_utility"], "Guia calmo de utilidade publica.", {}) == []


def test_cta_style_role_aware_and_bans_execution():
    # cta_style (FIX 1) is scoped to CTA BUTTON text only -- exercise it via
    # the marker-format `=== WIDGET: BOTÃO ===` block, same as a real draft.
    exec_txt = "=== WIDGET: BOTÃO ===\nTexto: Agendar agora\n"
    assert any(i.code == "cta_execution"
               for i in run_validators(["cta_style"], exec_txt,
                                       {"role": PageRole.SOLUTION}))
    fp_txt = "=== WIDGET: BOTÃO ===\nTexto: Sera que eu tenho? Quero ver\n"
    lp = run_validators(["cta_style"], fp_txt, {"role": PageRole.LP})
    assert any(i.code == "cta_first_person" for i in lp)
    interior = run_validators(["cta_style"], fp_txt, {"role": PageRole.SOLUTION})
    assert not any(i.code == "cta_first_person" for i in interior)


def test_no_private_cta_tuple_remains():
    assert not hasattr(checks, "_CTA_FIRST_PERSON")


def test_lp_json_contract_fala_a_lingua_da_lp():
    """A LP e JSON, nao Gutenberg. `cta_style` sobre esse JSON devolve lista
    vazia (ela so enxerga wp:buttons / marcadores) -- seria portao que sempre
    passa. `lp_json_contract` parseia e delega ao MESMO validate_lp_content."""
    import json as _json
    from funnelforge.pipeline.validators.checks import run_validators

    valido = {
        "hero_title": "Tema",
        "hero_subtitle": "Promessa -- toque abaixo e veja como resolver",
        "article_title": "Titulo",
        "intro": "<p>Dor pratica. Promessa direta.</p>",
        "sections": [{"title": f"S{i}", "body": "<p>x</p>"} for i in range(4)],
        "faq": [{"q": "P?", "a": "Sim."} for _ in range(5)],
        "transition": "<p>t</p>",
        "cta_texts": ["Ver o passo a passo »", "Como funciona »", "Ver a lista »"],
    }
    bruto = _json.dumps(valido, ensure_ascii=False)
    assert run_validators(["lp_json_contract"], bruto, {}) == []
    # tolera cercas de markdown, como o resto do pipeline
    assert run_validators(["lp_json_contract"], f"```json\n{bruto}\n```", {}) == []
    # saida que nao e JSON vira issue (e, no runner, feedback + nova tentativa)
    codes = {i.code for i in run_validators(["lp_json_contract"], "desculpa, nao consegui", {})}
    assert codes == {"parse_error"}
    # e as regras da LP valem de verdade aqui dentro
    ruim = dict(valido, cta_texts=["Sera que eu tenho direito? Quero ver »",
                                   "Agendar agora »", "Ver »"])
    codes = {i.code for i in run_validators(
        ["lp_json_contract"], _json.dumps(ruim, ensure_ascii=False), {})}
    assert "cta_first_person" in codes and "cta_execution" in codes


def test_cta_style_sobre_o_json_da_lp_nao_ve_nada():
    """Prova, por escrito, POR QUE o validador novo existe: os validadores de
    pagina interior sao CEGOS para a LP. Se um dia alguem trocar
    `lp_json_contract` por `cta_style` em write_p1.validators, este teste
    lembra que isso e um portao que sempre passa."""
    import json as _json
    from funnelforge.domain.models import PageRole
    from funnelforge.pipeline.validators.checks import run_validators

    lp = _json.dumps({"cta_texts": ["Sera que eu tenho direito? Quero ver »",
                                    "Agendar meu atendimento »"]}, ensure_ascii=False)
    assert run_validators(["cta_style"], lp, {"role": PageRole.LP}) == []
