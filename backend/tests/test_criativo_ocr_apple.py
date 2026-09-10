import io
import json
import os
import platform
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.criativo.politica import inspecao
from app.criativo.politica.detectores.ocr_apple import DetectorOcrApple, OcrAppleIndisponivel


def fixture_image():
    image = Image.new("RGB", (1200, 400), "white")
    ImageDraw.Draw(image).text((70, 120), "TESTE OCR 2026", fill="black", font=ImageFont.load_default(size=75))
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def test_ocr_does_not_claim_brand_capability():
    assert DetectorOcrApple.capacidades == (inspecao.CAPACIDADE_TEXTO_NA_IMAGEM,)
    assert DetectorOcrApple.deterministico is False


def test_decodes_actual_image_but_never_accepts_failed_cli_as_clear(monkeypatch):
    detector = DetectorOcrApple(Path("/not-executed"), "fixture")
    def failure(*args, **kwargs):
        raise subprocess.TimeoutExpired("ocr", 30)
    monkeypatch.setattr(subprocess, "run", failure)
    with pytest.raises(OcrAppleIndisponivel):
        detector.inspecionar(fixture_image(), mime="image/png")


def test_ocr_uses_stdin_bytes_and_typed_complete_output(monkeypatch):
    detector = DetectorOcrApple(Path("/fixture-ocr"), "fixture")
    png = fixture_image()
    def run(argv, **kwargs):
        assert argv == ["/fixture-ocr"]
        assert kwargs["input"] == png
        assert "shell" not in kwargs
        return SimpleNamespace(stdout=json.dumps({"text": "TESTE", "completed": True}).encode())
    monkeypatch.setattr(subprocess, "run", run)
    result = detector.inspecionar(png, mime="image/png")
    assert result.texto == "TESTE"
    assert result.rotulos == ()


@pytest.mark.skipif(platform.system() != "Darwin" or os.getenv("VOLC_TEST_APPLE_OCR") != "1",
                    reason="Explicit local real OCR fixture test")
def test_real_apple_vision_reads_synthetic_fixture():
    detector = DetectorOcrApple.se_disponivel()
    assert detector is not None, "Apple Vision OCR must compile on this Mac"
    result = detector.inspecionar(fixture_image(), mime="image/png")
    assert "TESTE" in result.texto.upper()
    assert "OCR" in result.texto.upper()
    assert "2026" in result.texto
    assert result.rotulos == ()
