from __future__ import annotations
import io

from funnelforge.ports.llm import LLMResult
from funnelforge.ports.services import CaptureResult


def png_bytes(width: int = 1, height: int = 1) -> bytes:
    """A real (tiny) PNG for screenshot fakes/processing tests -- no network."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()


def content_png(width: int = 400, height: int = 1200) -> bytes:
    """A PNG that reads as a WELL-RENDERED page to the blank/under-render guard:
    high per-band pixel variance (gaussian noise) so no band looks flat. Used to
    exercise the accept-path of step_screenshot's validity guards."""
    from PIL import Image

    buf = io.BytesIO()
    Image.effect_noise((width, height), 80).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def blank_png(width: int = 400, height: int = 1200) -> bytes:
    """A PNG that reads as BLANK/under-rendered to the guard: one flat solid fill
    (zero per-band variance) -> the whole frame is a contiguous blank band."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


class FakeScreenshotProvider:
    """Scriptable stand-in for the Playwright ScreenshotProvider (CARD-0005):
    returns a `CaptureResult` (png + status + is_error_page) and records every
    URL it was asked to capture, so tests can assert gating/cap/whitelist AND the
    B3 validity guards (status/error/blank + retry) without a browser or network.

    - `data`/`status`/`is_error_page`: the fixed result every capture returns.
    - `results`: a queue of `CaptureResult` consumed in order across calls (drives
      the retry path -- e.g. blank first, content on the retry). The last entry
      repeats once exhausted.
    - `fail=True`: simulate a provider that always raises.

    Every call is also recorded in `calls` as a dict of the kwargs it was
    invoked with (`scroll`/`settle_ms`/`mode`/...), so a test can assert the
    blank retry actually asked for scroll + a larger settle -- not a byte-
    identical re-shoot."""

    def __init__(self, data: bytes | None = None, fail: bool = False,
                 status: int | None = 200, is_error_page: bool = False,
                 results: list[CaptureResult] | None = None) -> None:
        self._data = data if data is not None else content_png()
        self._fail = fail
        self._status = status
        self._is_error_page = is_error_page
        self._results = list(results) if results is not None else None
        self._i = 0
        self.captured: list[str] = []
        self.calls: list[dict] = []

    def capture(self, url: str, *, mode: str = "desktop",
                full_page: bool = False, timeout_s: int = 30,
                scroll: bool = False, settle_ms: int = 1500) -> CaptureResult:
        self.captured.append(url)
        self.calls.append({"url": url, "mode": mode, "full_page": full_page,
                           "timeout_s": timeout_s, "scroll": scroll,
                           "settle_ms": settle_ms})
        if self._fail:
            raise RuntimeError("screenshot provider boom")
        if self._results is not None:
            res = self._results[min(self._i, len(self._results) - 1)]
            self._i += 1
            return res
        return CaptureResult(png=self._data, status=self._status,
                             is_error_page=self._is_error_page)


class FakeLLM:
    def __init__(self, responses):
        self._responses = responses
        self._i = 0
        self.calls: list[dict] = []

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        chain = [model, *fallbacks]
        last_exc = None
        for m in chain:
            self.calls.append(
                {"model": m, "messages": messages, "temperature": temperature}
            )
            try:
                if callable(self._responses):
                    text = self._responses(m, messages)
                else:
                    text = self._responses[self._i]
                    self._i += 1
                return LLMResult(text=text, model_used=m)
            except Exception as e:  # simulate provider failure -> try fallback
                last_exc = e
                continue
        raise last_exc  # type: ignore[misc]
