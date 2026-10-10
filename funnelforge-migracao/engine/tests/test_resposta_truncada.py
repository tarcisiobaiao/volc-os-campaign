"""Resposta cortada pelo teto de saída é defeito mecânico achado na hora."""
from funnelforge.config.settings import StepConfig
from funnelforge.pipeline.runner import Runner
from funnelforge.ports.llm import LLMResult



class _LLM:
    def __init__(self, finais):
        self.finais = list(finais)
        self.calls = 0

    def complete(self, model, fallbacks, messages, temperature, response_schema=None, **kw):
        self.calls += 1
        fim = self.finais.pop(0)
        return LLMResult(text="<!-- wp:paragraph --><p>texto</p><!-- /wp:paragraph -->",
                         model_used=model, finish_reason=fim)


def test_truncada_retenta_e_a_completa_passa(tmp_path):
    llm = _LLM(["length", "stop"])
    runner = Runner(llm=llm, max_retries=1, runs_dir=tmp_path, sleep=lambda _s: None)
    texto, res = runner.run_llm_step("write_p2", StepConfig(model="m"),
                                     [{"role": "user", "content": "x"}], ctx={}, run_id="r")
    assert llm.calls == 2 and res.status.value == "RETRIED"


def test_truncada_sem_retentativa_falha_sem_seguir(tmp_path):
    runner = Runner(llm=_LLM(["length"]), max_retries=0, runs_dir=tmp_path,
                    sleep=lambda _s: None)
    _texto, res = runner.run_llm_step("write_p2", StepConfig(model="m"),
                                      [{"role": "user", "content": "x"}], ctx={}, run_id="r")
    assert res.status.value == "FAILED"
    assert any(i.code == "resposta_truncada" for i in res.issues)
