# funnel-forge/tests/test_settings.py
from pathlib import Path
import pytest
from pydantic import ValidationError
from funnelforge.config.settings import SiteConfig, load_settings


def test_load_settings_reads_env_and_yaml(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-test\nWP_URL=https://creditoup.com.br\nWP_USER=admin\nWP_APP_TOKEN=abc\n"
    )
    (tmp_path / "config.yaml").write_text(
        "run:\n  max_retries: 3\n  publish: false\n"
        "site:\n  domain: https://creditoup.com.br\n  post_type: rec\n"
        "  author: {name: Fulano, credential: Jornalista}\n"
        "steps:\n"
        "  write_p1: {model: claude-opus-4-8, fallbacks: [gpt-5.2],\n"
        "             temperature: 0.7, validators: [winning_lp]}\n"
    )
    s = load_settings(tmp_path / ".env", tmp_path / "config.yaml")
    assert s.secrets.openai_api_key == "sk-test"
    assert s.secrets.wp_url == "https://creditoup.com.br"
    assert s.run.max_retries == 3
    assert s.run.publish is False
    assert s.site.domain == "https://creditoup.com.br"
    assert s.site.author_name == "Fulano"
    assert s.steps["write_p1"].model == "claude-opus-4-8"
    assert s.steps["write_p1"].fallbacks == ["gpt-5.2"]
    assert s.steps["write_p1"].validators == ["winning_lp"]


def test_site_config_rejects_placeholder_cnpj() -> None:
    with pytest.raises(ValidationError):
        SiteConfig(domain="https://creditoup.com.br", cnpj="00.000.000/0001-00")


def test_config_antigo_com_allowlist_carrega_sem_efeito(tmp_path: Path):
    """SUBSTITUI test_load_settings_parses_official_entry_points.

    `allowed_external`/`official_entry_points` sairam do SiteConfig: a
    autorizacao de link externo passou a vir da PESQUISA de cada pagina, nao de
    lista por instalacao. O contrato de migracao e que um config.yaml ANTIGO
    ainda carrega (chave desconhecida e ignorada, sem migracao manual) -- so
    para de fazer efeito. Isso e o que este teste prova; o parse do mapa legado
    nao existe mais para ser testado."""
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-test\nWP_URL=https://creditoup.com.br\nWP_USER=admin\nWP_APP_TOKEN=abc\n"
    )
    (tmp_path / "config.yaml").write_text(
        "run:\n  max_retries: 1\n  publish: false\n"
        "site:\n  domain: https://creditoup.com.br\n  post_type: rec\n"
        "  author: {name: Equipe, credential: c}\n"
        "  allowed_external: [https://gov.br, https://www.caixa.gov.br]\n"
        "  official_entry_points:\n"
        "    https://gov.br: https://meu.inss.gov.br\n"
        "steps:\n"
        "  write_p1: {model: claude-opus-4-8, fallbacks: [], temperature: 0.7, validators: []}\n"
    )
    s = load_settings(tmp_path / ".env", tmp_path / "config.yaml")
    assert s.site.domain == "https://creditoup.com.br"
    assert not hasattr(s.site, "allowed_external")
    assert not hasattr(s.site, "official_entry_points")
    # e as chaves velhas nao ressuscitam como preferencia/denylist
    assert s.site.official_preference == []
    assert s.site.blocked_hosts == []


def test_load_settings_parses_new_blocks(config_files: Path):
    s = load_settings(config_files / ".env", config_files / "config.yaml")
    assert s.site.cnpj == "42.724.548/0001-24"
    # Sem allowlist: `official_preference` so ORDENA e `blocked_hosts` e
    # denylist opcional -- ambos VAZIOS por padrao, que e o caso normal de um
    # funil novo (iFood, Serasa) rodando sem ninguem editar lista nenhuma.
    assert s.site.official_preference == []
    assert s.site.blocked_hosts == []
    assert s.site.authors and s.site.authors[0].name
    assert s.routing["LP"].cta_min == 5 and s.routing["LP"].cta_max == 8
    assert "funnel" in s.routing["LP"].required_targets
    assert s.routing["SOLUTION"].distinct_targets is True
    # Honest-graph (Plano A): the SOLUTION_TERMINAL key exists and requires the
    # cross-funnel exit (the dead requires_* flags are no longer relied upon).
    assert "cross_funnel" in s.routing["SOLUTION_TERMINAL"].required_targets
    assert s.ads.vignette.window_seconds == 600
    assert [sl.slot_id for sl in s.ads.slots["LP"]] == ["lp-hero", "lp-footer"]
    assert s.ads.slots["LP"][0].min_height_px == 280
    assert s.index["LP"].robots == "noindex,follow"
    assert s.uniqueness.jaccard_threshold == 0.35


def test_load_settings_defaults_image_model_and_quality(config_files: Path):
    """`config_files`'s config.yaml (conftest.py) has no `run.image_model`/
    `run.image_quality` -- both must default to gpt-image-2 / medium so a
    config predating this field still loads."""
    s = load_settings(config_files / ".env", config_files / "config.yaml")
    assert s.run.image_model == "gpt-image-2"
    assert s.run.image_quality == "medium"


def test_load_settings_parses_run_image_model_and_quality(tmp_path: Path):
    """`run.image_model`/`run.image_quality` are the IMAGE-GENERATION
    model/quality (wired into OpenAIImageGenerator by cli.py's build_deps),
    distinct from `steps.image.model` (the TEXT model that crafts the
    English image prompt)."""
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    (tmp_path / "config.yaml").write_text(
        "run:\n  max_retries: 1\n  publish: false\n  hero_image: true\n"
        "  image_model: gpt-image-2\n  image_quality: high\n"
        "site:\n  domain: https://creditoup.com.br\n  post_type: rec\n"
        "  author: {name: Fulano, credential: Jornalista}\n"
        "steps:\n"
        "  image: {model: gpt-4.1, fallbacks: [], temperature: 1.0, validators: []}\n"
    )
    s = load_settings(tmp_path / ".env", tmp_path / "config.yaml")
    assert s.run.image_model == "gpt-image-2"
    assert s.run.image_quality == "high"
    # the CRAFTING model (steps.image.model) stays independent of it
    assert s.steps["image"].model == "gpt-4.1"
