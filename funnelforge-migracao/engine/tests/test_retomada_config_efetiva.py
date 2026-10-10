"""A retomada usa a configuração com que o run nasceu, não uma inferência."""
from pathlib import Path

from funnelforge.config.perfil import aplicar_perfil, configuracao_efetiva_do_run
from funnelforge.config.settings import load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


def test_snapshot_restaura_modelos_workers_prints_e_tetos(tmp_path):
    base = load_settings(tmp_path / "nada.env", CONFIG)
    snap = base.model_dump(mode="json")
    snap["run"].update(page_workers=3, editorial_v2=True, dossie_factual=True)
    snap["steps"]["write_page"]["model"] = "chatgpt/gpt-6-sol"
    snap["steps"]["write_page"]["fallbacks"] = []
    snap["openai"].update(auth_mode="chatgpt_plan", writer_model="gpt-6-sol")
    snap["budget"]["max_usd_per_run"] = 1.0
    snap["screenshot"]["mode"] = "desktop"
    snap.pop("secrets")
    snap["site"] = {"domain": "https://outro.exemplo"}     # site não vem do snapshot
    efetiva = configuracao_efetiva_do_run(base, snap)
    assert efetiva.run.page_workers == 3 and efetiva.run.editorial_v2
    assert efetiva.steps["write_page"].model == "chatgpt/gpt-6-sol"
    assert efetiva.steps["write_page"].fallbacks == []
    assert efetiva.openai.auth_mode == "chatgpt_plan"
    assert efetiva.budget.max_usd_per_run == 1.0 and efetiva.screenshot.mode == "desktop"
    assert efetiva.site.domain == base.site.domain
    assert efetiva.secrets == base.secrets
    perfil = aplicar_perfil(efetiva, {"site": {"domain": "https://creditoup.com.br"}})
    assert perfil.site.domain == "https://creditoup.com.br"
    assert perfil.steps["write_page"].model == "chatgpt/gpt-6-sol"
