from __future__ import annotations
import json
import re
import time
from pathlib import Path
from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import StepResult, StepStatus
from funnelforge.ports.llm import LLMClient
from funnelforge.pipeline.budget import Orcamento, OrcamentoEstourado
from funnelforge.pipeline.retry_policy import Veredito, classificar_excecao, classificar_issues
from funnelforge.pipeline.validators.checks import run_validators

# A returned `model_used` often echoes back a provider-versioned/dated
# variant of the configured model (e.g. config `gpt-4.1` -> API returns
# `gpt-4.1-2025-04-14`; config `gemini/gemini-2.5-pro` -> API returns bare
# `gemini-2.5-pro`, no provider prefix). Comparing the raw strings falsely
# reports FALLBACK for the SAME model. Normalize both sides to their base
# name -- strip the `provider/` prefix and any trailing `-YYYY-MM-DD` /
# `-YYYYMMDD` date suffix -- before deciding whether a fallback actually
# fired.
_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{8}$")


def _normalize_model_base(model: str) -> str:
    base = model.rsplit("/", 1)[-1]
    return _DATE_SUFFIX_RE.sub("", base)


class LLMStepError(RuntimeError):
    """Falha definitiva de um passo de LLM, carregando a telemetria JÁ PAGA.

    O `Runner` levanta (em vez de devolver um StepResult) para preservar o
    contrato que o pipeline já tem: `step_image` engole e marca SKIPPED, o loop
    de páginas registra a falha e segue para a próxima página. O que muda é que
    o custo das tentativas que morreram viaja junto em `step_result` — antes
    ele evaporava com a exceção e o relatório mentia para menos.
    """

    def __init__(self, step_result: StepResult, veredito: Veredito) -> None:
        self.step_result = step_result
        self.veredito = veredito
        self.motivo = veredito.motivo
        self.classe = veredito.classe
        super().__init__(
            f"{step_result.step}: {veredito.motivo} "
            f"(tentativas={step_result.attempts}, já pago US$ {step_result.cost_usd:.4f})"
        )


class Runner:
    def __init__(self, llm: LLMClient, max_retries: int, runs_dir: Path,
                 budget: Orcamento | None = None, backoff_s: float = 2.0,
                 backoff_max_s: float = 30.0, sleep=None):
        self.llm = llm
        self.max_retries = max_retries
        self.runs_dir = runs_dir
        # Freio de gasto (Frente 3). None = sem teto (comportamento antigo), que
        # é o que os testes e um dry run usam.
        self.budget = budget
        # Espera entre tentativas de erro TRANSITÓRIO do provedor (429/5xx/
        # timeout). Exponencial: backoff_s, 2x, 4x... limitada por backoff_max_s.
        self.backoff_s = backoff_s
        self.backoff_max_s = backoff_max_s
        # `sleep` é injetável para o teste não dormir de verdade.
        #
        # ⚠️ O default é resolvido AQUI, na construção — e não como
        # `sleep=time.sleep` na assinatura. Default de função é avaliado no
        # import, então ele congelava a `time.sleep` original e um
        # `monkeypatch.setattr(time, "sleep", ...)` feito depois não tinha
        # efeito nenhum. Foi assim que um único teste do caminho de falha da
        # pesquisa passou a dormir 12 s de verdade, de 16 s da suíte inteira.
        self.sleep = sleep if sleep is not None else time.sleep

    def _espera(self, tentativa: int) -> float:
        return min(self.backoff_s * (2 ** max(0, tentativa - 1)), self.backoff_max_s)

    def run_llm_step(self, name, cfg: StepConfig, messages: list[dict], ctx: dict, *,
                     run_id: str, response_schema: type | None = None
                     ) -> tuple[str, StepResult]:
        msgs = [dict(m) for m in messages]
        self.snapshot_prompt(run_id, name, msgs)
        parts = run_id.rsplit("-", 2)
        ts = "-".join(parts[-2:]) if len(parts) >= 3 else run_id
        attempts = 0
        last_issues: list = []
        model_used = text = ""
        prompt_tokens = completion_tokens = latency_ms = 0
        cost_usd = 0.0

        def _parcial() -> StepResult:
            """StepResult com TUDO que já foi pago, inclusive tentativas
            descartadas. Nenhuma saída deste método pode perder telemetria."""
            return StepResult(
                step=name, status=StepStatus.FAILED, model_used=model_used,
                attempts=attempts, issues=last_issues, prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens, cost_usd=cost_usd,
                latency_ms=latency_ms)

        while attempts <= self.max_retries:
            attempts += 1
            # Confere o teto ANTES de cada chamada paga. Estoura -> sobe para o
            # pipeline, que aborta com mensagem clara em vez de seguir gastando.
            if self.budget is not None:
                self.budget.exigir_saldo(name)
            try:
                res = self.llm.complete(cfg.model, cfg.fallbacks, msgs, cfg.temperature,
                                        response_schema)
            except OrcamentoEstourado:
                raise
            except Exception as exc:  # noqa: BLE001 - classificado logo abaixo
                veredito = classificar_excecao(exc)
                ultima = attempts > self.max_retries
                self.log(run_id, {"ts": ts, "step": name, "attempt": attempts,
                                  "erro": f"{type(exc).__name__}: {exc}"[:400],
                                  "classe": veredito.classe, "motivo": veredito.motivo,
                                  "retentar": bool(veredito.retentar and not ultima)})
                if not veredito.retentar or ultima:
                    raise LLMStepError(_parcial(), veredito) from exc
                self.sleep(self._espera(attempts))
                continue

            text, model_used = res.text, res.model_used
            prompt_tokens += res.prompt_tokens
            completion_tokens += res.completion_tokens
            cost_usd += res.cost_usd
            latency_ms += res.latency_ms
            if self.budget is not None:
                self.budget.registrar(name, res.cost_usd)
            last_issues = run_validators(cfg.validators, text, ctx)
            veredito = classificar_issues(last_issues, ctx)
            self.log(run_id, {"ts": ts, "step": name, "attempt": attempts,
                              "model": model_used,
                              "prompt_tokens": res.prompt_tokens,
                              "completion_tokens": res.completion_tokens,
                              "cost_usd": res.cost_usd, "latency_ms": res.latency_ms,
                              "n_issues": len(last_issues),
                              "classe": veredito.classe,
                              "retentar": veredito.retentar})
            if not last_issues:
                status = StepStatus.OK if attempts == 1 else StepStatus.RETRIED
                if _normalize_model_base(model_used) != _normalize_model_base(cfg.model):
                    status = StepStatus.FALLBACK
                return text, StepResult(
                    step=name, status=status, model_used=model_used, attempts=attempts,
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                    cost_usd=cost_usd, latency_ms=latency_ms)
            # Reprovação que NÃO depende do texto (rotas do pagespec, ausência
            # de link oficial): reescrever devolve o mesmo veredito. Sela aqui.
            if not veredito.retentar:
                break
            feedback = "Corrija OBRIGATORIAMENTE: " + "; ".join(
                f"[{i.code}] {i.message}" for i in last_issues)
            msgs.append({"role": "assistant", "content": text})
            msgs.append({"role": "user", "content": feedback})
        return text, _parcial()

    def checkpoint(self, run_id: str, state_json: str) -> None:
        d = self.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "state.json.tmp"
        tmp.write_text(state_json, encoding="utf-8")
        tmp.replace(d / "state.json")

    def log(self, run_id: str, entry: dict) -> None:
        d = self.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        with (d / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def snapshot_prompt(self, run_id: str, step: str, messages: list[dict]) -> None:
        """Persist the exact rendered prompt for `step` so a run is fully
        reproducible/auditable. Written once (initial prompt, pre-retry)."""
        d = self.runs_dir / run_id / "prompts"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{step}.txt").write_text(
            "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages),
            encoding="utf-8",
        )

    def finalize_run_id(self, old: str, new: str) -> None:
        """Rename runs/<old> -> runs/<new> once the real run_id is known.
        No-op if old == new or runs/<old> is absent."""
        if old == new:
            return
        src = self.runs_dir / old
        if not src.exists():
            return
        dst = self.runs_dir / new
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dst)
