from types import SimpleNamespace

import pytest

from funnelforge.adapters.image_gemini import GeminiImageGenerator, _aspect_ratio


class _Models:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _client(*, data: bytes | None = b"jpeg"):
    inline = SimpleNamespace(data=data, mime_type="image/jpeg")
    response = SimpleNamespace(
        parts=[SimpleNamespace(inline_data=inline)],
        usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=22),
    )
    return SimpleNamespace(models=_Models(response))


@pytest.mark.parametrize(("size", "ratio"), [
    ("1024x1536", "2:3"),
    ("1536x1024", "3:2"),
    ("1024x1024", "1:1"),
    ("garbage", "16:9"),
])
def test_aspect_ratio(size, ratio):
    assert _aspect_ratio(size) == ratio


def test_generate_returns_image_and_records_usage():
    client = _client()
    generator = GeminiImageGenerator(
        "not-used", model="gemini/gemini-3.1-flash-image-preview", client=client
    )

    assert generator.generate("editorial photo", "1024x1536") == b"jpeg"
    call = client.models.calls[0]
    assert call["model"] == "gemini-3.1-flash-image-preview"
    assert call["config"].response_modalities == ["IMAGE"]
    assert call["config"].image_config.aspect_ratio == "2:3"
    assert generator.last_usage is not None
    assert generator.last_usage.input_tokens == 11
    assert generator.last_usage.output_tokens == 22
    assert generator.last_usage.model == "gemini-3.1-flash-image-preview"


def test_generate_fails_closed_when_provider_returns_no_image():
    generator = GeminiImageGenerator("not-used", client=_client(data=None))
    with pytest.raises(RuntimeError, match="sem devolver imagem"):
        generator.generate("editorial photo")
