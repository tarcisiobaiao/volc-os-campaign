from pathlib import Path
from funnelforge.pipeline.doctrine import doctrine_context
from funnelforge.pipeline.validators.checks import run_validators
from funnelforge.prompts import render


def test_identity_validator_flags_foreign_identity():
    ctx = {"cnpj": "00.000.000/0001-00"}
    assert any(i.code == "wrong_cnpj"
               for i in run_validators(["identity"], "CNPJ 22.026.064/0001-02", ctx))
    assert any(i.code == "placeholder_cnpj"
               for i in run_validators(["identity"], "[Razão Social / CNPJ]", ctx))
    assert any(i.code == "fake_credential"
               for i in run_validators(["identity"], "licenciado pelo SATED/PR", ctx))
    assert run_validators(["identity"], "CNPJ 00.000.000/0001-00", ctx) == []


def test_redator_p1_omits_site_chrome_handled_by_theme():
    """CNPJ, the "Sobre o Site" footer, nav and the author byline are injected
    by the WordPress theme (fixed footer), NOT generated in page content. The
    redator_p1 prompt must OMIT those output markers (and never invent a fake
    credential/registry). The config CNPJ value is no longer templated in."""
    out = render("redator_p1", headline="h", cta_link="/x", objective="o", skeleton="s",
                 keywords="k", facts="{}", domain="https://creditoup.com.br",
                 author_name="Equipe Crédito Up", author_credential="Redação de serviço.",
                 cnpj="00.000.000/0001-00", **doctrine_context())
    low = out.lower()
    # the chrome output markers are gone from the prompt's format contract
    assert "=== widget: byline ===" not in low
    assert "=== widget: rodape ===" not in low
    assert "=== widget: nav ===" not in low
    # the injected config CNPJ value is no longer rendered into the prompt
    assert "00.000.000/0001-00" not in out
    # anti-fabrication guardrails intact
    assert "credencial verificável" not in low
    assert "[razão social" not in low and "sated" not in low


def test_redator_pages_has_no_official_sounding_layer():
    out = render("redator_pages", page_num=2, total_pages=5, page_type="HUB", avatar="a",
                 tone="t", headline="h", objective="o", current_url="u", cta_text="c",
                 cta_link="/x", domain="https://creditoup.com.br", skeleton="s",
                 keywords="k", facts="{}", author_name="Equipe Crédito Up",
                 cnpj="00.000.000/0001-00", **doctrine_context())
    low = out.lower()
    assert "semantic_monetization" not in low
    assert "comunicado oficial" not in low and "sistema oficial" not in low


def test_blueprint_scrubbed_of_fossilized_identity():
    bp = Path(__file__).resolve().parents[2] / "WINNING-LP-BLUEPRINT.md"
    if bp.exists():
        text = bp.read_text(encoding="utf-8")
        assert "SATED" not in text and "22.026.064/0001-02" not in text
