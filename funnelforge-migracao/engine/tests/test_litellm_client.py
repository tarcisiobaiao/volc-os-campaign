from funnelforge.adapters.litellm_client import LiteLLMClient


def test_calls_litellm_and_returns_text(mocker):
    message = type("M", (), {"content": "oi"})()
    choice = type("C", (), {"message": message})()
    fake_resp = type("R", (), {
        "choices": [choice],
        "model": "claude-opus-4-8"
    })()
    m = mocker.patch(
        "funnelforge.adapters.litellm_client.completion",
        return_value=fake_resp
    )
    messages = [{"role": "user", "content": "x"}]
    out = LiteLLMClient().complete(
        "claude-opus-4-8", ["gpt-5.2"], messages, 0.5
    )
    assert out.text == "oi"
    assert out.model_used == "claude-opus-4-8"
    kwargs = m.call_args.kwargs
    assert kwargs["fallbacks"] == ["gpt-5.2"]
    assert kwargs["temperature"] == 0.5


def test_complete_passes_num_retries_and_timeout_for_transient_5xx_resilience(mocker):
    """FIX 3 (smoke): a transient `OpenAIException InternalServerError`
    crashed a step with no retry. LiteLLM must be told to retry transient
    429/5xx with backoff (num_retries) and bound the call (timeout) before
    failing over to fallbacks."""
    message = type("M", (), {"content": "oi"})()
    choice = type("C", (), {"message": message})()
    fake_resp = type("R", (), {"choices": [choice], "model": "gpt-4.1"})()
    m = mocker.patch(
        "funnelforge.adapters.litellm_client.completion",
        return_value=fake_resp
    )
    LiteLLMClient().complete("gpt-4.1", [], [{"role": "user", "content": "x"}], 0.2)
    kwargs = m.call_args.kwargs
    # UM retry aqui, não dois (Frente 3): a retentativa de transporte agora
    # existe também no `Runner`, com espera exponencial e classificação de erro.
    # Com 2 aqui × 3 tentativas do runner um único passo chegava a ~9
    # requisições — e as internas são INVISÍVEIS ao ledger, porque
    # `completion_cost` só mede a resposta final.
    assert kwargs["num_retries"] == 1
    assert kwargs["timeout"] == 120
