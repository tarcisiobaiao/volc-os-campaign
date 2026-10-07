"""`run.publish_status` é vocabulário fechado (B5, contrato decisão 8).

Antes era `str` livre: qualquer valor era gravado verbatim no "pino" final do
status do WordPress. Agora só os status que o WordPress aceita carregam; no
ramo editorial novo o `step_publish` ainda exige `draft` (test_revisor_fluxo).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from funnelforge.config.settings import RunConfig, load_settings


@pytest.mark.parametrize("status", ["draft", "pending", "private", "future", "publish"])
def test_status_do_wordpress_carregam(status):
    assert RunConfig(publish_status=status).publish_status == status


@pytest.mark.parametrize("status", ["live", "Draft", "", "publicado"])
def test_status_fora_do_vocabulario_e_recusado(status):
    with pytest.raises(ValidationError):
        RunConfig(publish_status=status)


def test_config_com_status_invalido_nao_carrega(tmp_path):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        "run: {publish_status: live}\nsite: {domain: 'https://x.com.br'}\nsteps: {}\n",
        encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(tmp_path / ".env", tmp_path / "config.yaml")


def test_config_do_motor_continua_rascunho():
    from pathlib import Path

    import yaml

    motor = Path(__file__).resolve().parents[1]
    dados = yaml.safe_load((motor / "config.yaml").read_text(encoding="utf-8"))
    assert dados["run"]["publish_status"] == "draft"
    assert dados["run"]["editorial_v2"] is False
    assert dados["steps"]["revisor"]["temperature"] == 0.0
    assert dados["steps"]["revisor"]["validators"] == []
