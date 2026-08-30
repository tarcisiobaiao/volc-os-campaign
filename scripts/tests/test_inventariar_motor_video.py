import json
from pathlib import Path

from scripts.inventariar_motor_video import build_snapshot


def _minimal_contract(root: Path) -> None:
    contract = root / "contrato" / "motor"
    schema = root / "contrato" / "schema"
    contract.mkdir(parents=True)
    schema.mkdir(parents=True)
    (contract / "mapa.json").write_text(json.dumps({
        "versao": "1.0",
        "regras_globais": ["REGRA:teste"],
        "nichos": {"teste": {"skin": "skin"}},
        "vozes": {"VOZ:teste": {}},
        "skins": {
            "skin": {
                "runner": "formatos/teste/make.py",
                "hook_default": "imagem",
                "qa": {"perfil": "base"},
            }
        },
    }))
    (schema / "contrato.schema.json").write_text(json.dumps({"required": ["slug", "skin"]}))


def test_inventaria_formato_contrato_e_nao_le_segredo(tmp_path: Path):
    root = tmp_path / "motor-video"
    factory = tmp_path / "factory"
    format_dir = root / "formatos" / "teste"
    format_dir.mkdir(parents=True)
    (format_dir / "make.py").write_text("print('ok')")
    (format_dir / "compositor.tsx").write_text("export const X = 1")
    (format_dir / "som.py").write_text("pass")
    (format_dir / "design.md").write_text("# design")
    (root / ".env").write_text("SEGREDO=nao-pode-aparecer")
    (root / ".env.exemplo").write_text("GEMINI_API_KEY=\nKIE_API_KEY=\n")
    _minimal_contract(root)

    snapshot = build_snapshot(root, factory, ffprobe_bin="")

    assert snapshot["summary"]["formats"] == 1
    assert snapshot["summary"]["filesystem_complete_formats"] == 1
    assert snapshot["formats"][0]["contract_skins"] == ["skin"]
    assert snapshot["hook_modes"] == {"imagem": 1}
    assert snapshot["providers"]["configured_variable_names"] == ["GEMINI_API_KEY", "KIE_API_KEY"]
    assert "nao-pode-aparecer" not in json.dumps(snapshot)


def test_ausencia_e_compartilhamento_nao_viram_completude(tmp_path: Path):
    root = tmp_path / "motor-video"
    format_dir = root / "formatos" / "novela"
    format_dir.mkdir(parents=True)
    (format_dir / "make.py").write_text("pass")
    (format_dir / "COMPARTILHADO.md").write_text("reusa compositor e som")
    _minimal_contract(root)

    snapshot = build_snapshot(root, tmp_path / "factory", ffprobe_bin="")
    row = snapshot["formats"][0]

    assert row["filesystem_complete"] is False
    assert row["shared_notes"] == ["COMPARTILHADO.md"]
    assert "compositor_proprio_ausente" in row["gaps"]
    assert "som_proprio_ausente" in row["gaps"]
