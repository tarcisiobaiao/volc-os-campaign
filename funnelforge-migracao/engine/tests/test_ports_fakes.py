from tests.fakes import FakeLLM


def test_fake_llm_returns_scripted_responses():
    llm = FakeLLM(responses=["hello", "world"])
    r1 = llm.complete("m", [], [{"role": "user", "content": "x"}], 0.0)
    r2 = llm.complete("m", [], [{"role": "user", "content": "y"}], 0.0)
    assert r1.text == "hello" and r2.text == "world"
    assert llm.calls[0]["model"] == "m"


def test_fake_llm_uses_fallback_on_primary_error():
    def responder(model, messages):
        if model == "bad":
            raise RuntimeError("boom")
        return "recovered"
    llm = FakeLLM(responses=responder)
    r = llm.complete("bad", ["good"], [{"role": "user", "content": "x"}], 0.0)
    assert r.text == "recovered" and r.model_used == "good"
