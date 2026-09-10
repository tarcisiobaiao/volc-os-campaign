"""No external calls: image-only egress, strict conclusions and paid-call reuse."""
import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from PIL import Image, PngImagePlugin

from app.criativo.politica import inspecao
from app.criativo.politica.detectores import gemini_marcas as vision


def png(color="white"):
    output = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    info.add_text("campaign", "PRIVATE_CAMPAIGN_DO_NOT_SEND")
    Image.new("RGB", (40, 40), color).save(output, "PNG", pnginfo=info)
    return output.getvalue()


def answer(brands=None, **overrides):
    result = {"modelVersion": vision.MODELO, "candidates": [{
        "finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
            "completed": True, "brands": brands or [],
        })}]},
    }]}
    result.update(overrides)
    return result


def http(monkeypatch, data=None, status=200):
    calls = []
    def post(client, url, *, headers, json):
        calls.append((url, headers, json))
        return httpx.Response(status, json=data if data is not None else answer())
    monkeypatch.setattr(httpx.Client, "post", post)
    return calls


def test_only_sanitized_pixels_fixed_instruction_exact_model_medium(monkeypatch):
    calls = http(monkeypatch)
    detector = vision.DetectorGeminiMarcas("test-secret")
    assert detector.inspecionar(png(), mime="image/png").rotulos == ()
    url, headers, body = calls[0]
    assert url.endswith("/gemini-3.8-flash:generateContent") and "?" not in url
    assert headers == {"x-goog-api-key": "test-secret"}
    assert set(body) == {"system_instruction", "contents", "generationConfig"}
    assert body["system_instruction"]["parts"] == [{"text": vision.INSTRUCAO}]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "MEDIUM"}
    assert body["generationConfig"]["maxOutputTokens"] == 4096
    part = body["contents"][0]["parts"]
    assert len(part) == 1 and set(part[0]) == {"inline_data"}
    decoded = base64.b64decode(part[0]["inline_data"]["data"])
    assert b"PRIVATE_CAMPAIGN" not in decoded
    with Image.open(io.BytesIO(decoded)) as clean:
        assert not clean.info
        assert clean.getpixel((0, 0)) == (255, 255, 255, 255)
    assert "test-secret" not in json.dumps(body)
    assert detector.capacidades == (inspecao.CAPACIDADE_MARCA_VISUAL,)


@pytest.mark.parametrize("data", [
    answer(modelVersion="another-model"), answer(modelVersion=None),
    answer(candidates=[]), answer(candidates=[{"finishReason": "MAX_TOKENS"}]),
    answer(candidates=[{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]),
    answer([{"name": "x", "confidence": True}]),
    answer([{"name": "x", "confidence": float("nan")}]),
    answer([{"name": "x", "confidence": 1.01}]),
    answer([{"name": "", "confidence": .9}]),
    answer([{"name": "x\nsecret", "confidence": .9}]),
])
def test_incomplete_invalid_or_substituted_output_never_passes(monkeypatch, data):
    http(monkeypatch, data)
    with pytest.raises(vision.InspecaoGeminiIndisponivel):
        vision.DetectorGeminiMarcas("test-secret").inspecionar(png(), mime="image/png")


@pytest.mark.parametrize("status", [400, 401, 408, 429, 500])
def test_failure_not_cached_no_retry_no_sensitive_error(monkeypatch, status):
    calls = http(monkeypatch, {"error": "SECRET_FROM_PROVIDER"}, status)
    detector = vision.DetectorGeminiMarcas("test-secret")
    for _ in range(2):
        with pytest.raises(vision.InspecaoGeminiIndisponivel) as error:
            detector.inspecionar(png(), mime="image/png")
        assert "SECRET" not in str(error.value)
    assert len(calls) == 2


def test_same_pixels_single_flight_changed_pixels_new_call_and_expiry(monkeypatch):
    calls = http(monkeypatch)
    detector = vision.DetectorGeminiMarcas("test-secret")
    content = png()
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: detector.inspecionar(content, mime="image/png"), range(10)))
    assert len(calls) == 1
    detector.inspecionar(png("black"), mime="image/png")
    assert len(calls) == 2
    now = vision.time.monotonic()
    monkeypatch.setattr(vision.time, "monotonic", lambda: now + 601)
    detector.inspecionar(content, mime="image/png")
    assert len(calls) == 3


@pytest.mark.parametrize("content,mime", [(b"invalid", "image/png"), (png(), "image/jpeg"), (png(), "image/gif")])
def test_invalid_image_no_network(monkeypatch, content, mime):
    calls = http(monkeypatch)
    with pytest.raises(vision.InspecaoGeminiIndisponivel):
        vision.DetectorGeminiMarcas("test-secret").inspecionar(content, mime=mime)
    assert not calls


def test_external_detector_not_registered_globally_weak_labels_warn(monkeypatch):
    calls = http(monkeypatch, answer([{"name": "possible mark", "confidence": .3}]))
    class Local:
        nome = "local"
        versao = "1"
        capacidades = (inspecao.CAPACIDADE_TEXTO_NA_IMAGEM,)
        def inspecionar(self, *args, **kwargs): return inspecao.LeituraDePixel()
    monkeypatch.setattr(inspecao, "_DETECTORES_DE_PIXEL", [Local()])
    detector = vision.DetectorGeminiMarcas("test-secret")
    kwargs = dict(bytes_da_peca=png(), mime="image/png", copy=None,
                  nome_do_arquivo=None, prompt=None, identidade_propria=None)
    local = inspecao.inspecionar(**kwargs)
    assert local.portao_indisponivel and not calls
    meta = inspecao.inspecionar(**kwargs, detectores_adicionais=(detector,))
    assert not meta.portao_indisponivel and not meta.achados
    assert "VISUAL_BRAND_LOW_CONFIDENCE:possible mark" in meta.motivos
    assert len(calls) == 1 and detector not in inspecao.detectores_de_pixel_registrados()


def test_consent_disabled_does_not_return_detector(monkeypatch):
    from app import config
    from types import SimpleNamespace
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        criativo_policy_gemini_vision_enabled=False, resolved_gemini_key="test-secret"))
    assert vision.detector_meta_se_autorizado() is None
