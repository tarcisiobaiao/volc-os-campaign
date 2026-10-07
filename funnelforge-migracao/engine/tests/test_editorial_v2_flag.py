"""A FLAG `run.editorial_v2` (etapa B4, item 3) e o que a ponte leva ao plano.

- padrão `false` no `config.yaml` e nas settings;
- o perfil do run liga (ou desliga) por funil: `tema.editorial_v2` (mesmo lugar
  do `terminal_exit_policy`) ou `editorial_v2` na raiz do perfil;
- a arquitetura do card também pode ligar (`funnel_architecture.editorial_v2`);
- depois que um run nasce no ramo novo, ele fica no ramo novo (o `state.json`
  guarda) — retomar sem o perfil não rebaixa um funil pela metade.
"""
from __future__ import annotations

from pathlib import Path

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.config.perfil import aplicar_perfil
from funnelforge.config.settings import RunConfig, load_settings
from funnelforge.domain.models import FunnelPlan, RunState
from funnelforge.pipeline.pipeline import editorial_v2_do_run
from tests.cenario_editorial import arquitetura_base, settings_do_cenario

ENGINE = Path(__file__).resolve().parents[1]


def test_flag_nasce_desligada_nas_settings_e_no_config_yaml(tmp_path: Path):
    assert RunConfig().editorial_v2 is False
    texto = (ENGINE / "config.yaml").read_text(encoding="utf-8")
    assert "editorial_v2: false" in texto
    (tmp_path / ".env").write_text("", encoding="utf-8")
    settings = load_settings(tmp_path / ".env", ENGINE / "config.yaml")
    assert settings.run.editorial_v2 is False


def test_config_yaml_tem_o_passo_do_briefing_com_o_contrato(tmp_path: Path):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    settings = load_settings(tmp_path / ".env", ENGINE / "config.yaml")
    briefing = settings.steps["briefing"]
    assert "briefing_contract" in briefing.validators
    assert briefing.web_search is False


def test_perfil_liga_por_funil_no_tema_ou_na_raiz(tmp_path: Path):
    base = settings_do_cenario(tmp_path)
    assert aplicar_perfil(base, {"tema": {"editorial_v2": True}}).run.editorial_v2 is True
    assert aplicar_perfil(base, {"editorial_v2": True}).run.editorial_v2 is True
    # o tema é mais específico que a raiz
    assert aplicar_perfil(base, {"editorial_v2": True,
                                 "tema": {"editorial_v2": False}}).run.editorial_v2 is False
    # perfil sem a chave não mexe; valor que não é booleano não liga nada
    assert aplicar_perfil(base, {"tema": {"termos": ["x"]}}).run.editorial_v2 is False
    assert aplicar_perfil(base, {"tema": {"editorial_v2": "true"}}).run.editorial_v2 is False


def test_perfil_desliga_explicitamente_um_config_que_liga(tmp_path: Path):
    ligado = settings_do_cenario(tmp_path, editorial_v2=True)
    assert ligado.run.editorial_v2 is True
    assert aplicar_perfil(ligado, {"tema": {"editorial_v2": False}}).run.editorial_v2 is False
    # e as outras escolhas do run sobrevivem à sobreposição
    novo = aplicar_perfil(ligado, {"tema": {"terminal_exit_policy": "official"}})
    assert novo.run.editorial_v2 is True
    assert novo.run.terminal_exit_policy == "official"


def test_arquitetura_do_card_pode_ligar(tmp_path: Path):
    arq = arquitetura_base()
    assert plano_do_funnel_architecture(arq).editorial_v2 is False
    arq["editorial_v2"] = True
    assert plano_do_funnel_architecture(arq).editorial_v2 is True
    arq["editorial_v2"] = "sim"          # só booleano de verdade liga
    assert plano_do_funnel_architecture(arq).editorial_v2 is False


def test_flag_efetiva_e_pegajosa_no_run(tmp_path: Path):
    desligado = settings_do_cenario(tmp_path)
    ligado = settings_do_cenario(tmp_path, editorial_v2=True)
    plano = FunnelPlan()
    assert editorial_v2_do_run(RunState(run_id="a", plan=plano), desligado) is False
    assert editorial_v2_do_run(RunState(run_id="b", plan=plano), ligado) is True
    assert editorial_v2_do_run(
        RunState(run_id="c", plan=FunnelPlan(editorial_v2=True)), desligado) is True
    # um run que nasceu no ramo novo continua nele, mesmo retomado sem o perfil
    assert editorial_v2_do_run(RunState(run_id="d", plan=plano, editorial_v2=True),
                               desligado) is True


def test_state_json_antigo_nasce_no_ramo_desligado():
    antigo = RunState.from_json('{"run_id": "antigo", "plan": {"pages": []}}')
    assert antigo.editorial_v2 is False
    assert antigo.briefings == {}
    assert antigo.plan.editorial_v2 is False
    assert antigo.plan.contexto_de_busca is None
