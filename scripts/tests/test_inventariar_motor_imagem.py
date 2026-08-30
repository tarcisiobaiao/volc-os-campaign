import json
import struct
import zlib
from pathlib import Path

from scripts.inventariar_motor_imagem import build_snapshot


def _png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    raw = b"\x00" + b"\x00\x00\x00" * width
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw * height))
        + chunk(b"IEND", b"")
    )


def test_classifica_tipografia_sem_imagem_e_preserva_prova(tmp_path: Path):
    poc = tmp_path / "compartilhado" / "prensa-poc"
    out = poc / "out"
    out.mkdir(parents=True)
    (poc / "spec_carrossel.json").write_text(json.dumps({
        "schema_version": "post.spec/1",
        "spec_id": "carrossel",
        "skin": {"id": "VOS:test", "versao": "1"},
        "slides": [{"id": "s1", "layers": [{"type": "text"}, {"type": "texture"}]}],
    }))
    _png(out / "carrossel_s01.png", 1080, 1350)
    (out / "carrossel_s01.pixelgate.json").write_text(json.dumps({
        "status": "PIXEL_READY", "passed": True, "checks": [{"passed": True}]
    }))

    snapshot = build_snapshot(tmp_path)

    assert snapshot["specs"][0]["production_mode"] == "typography_only"
    assert snapshot["artifacts"][0]["dimensions"] == [1080, 1350]
    assert snapshot["artifacts"][0]["sidecars"]["pixel_gate"]["passed"] is True
    assert snapshot["summary"]["outputs_with_pixel_gate_passed"] == 1


def test_classifica_foto_ia_e_grafico_deterministico(tmp_path: Path):
    poc = tmp_path / "compartilhado" / "prensa-poc"
    poc.mkdir(parents=True)
    (poc / "spec_foto.json").write_text(json.dumps({
        "spec_id": "foto", "assets": [{"kind": "photo_ia", "ia_gerada": True}]
    }))
    (poc / "spec_grafico.json").write_text(json.dumps({
        "spec_id": "grafico", "slides": [{"layers": [{"type": "grafico"}, {"type": "text"}]}]
    }))

    modes = {item["spec_id"]: item["production_mode"] for item in build_snapshot(tmp_path)["specs"]}

    assert modes == {
        "foto": "prensa_hybrid_llm_asset",
        "grafico": "deterministic_graphics_and_typography",
    }
