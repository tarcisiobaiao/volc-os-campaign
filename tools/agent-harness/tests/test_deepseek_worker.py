import json
import os
import unittest
from unittest.mock import patch

from volc_agent_harness.deepseek_worker import (
    DeepSeekProposalError,
    DeepSeekProposalWorker,
    ProposalRequest,
    build_remote_payload,
    validate_proposal,
)


def request(**overrides):
    values = {
        "task_id": "copy-001",
        "target_path": "src/copy.py",
        "source_text": "prefixo benefício garantido sufixo",
        "span": "garantido",
        "allowed_replacements": ("possível", "sujeito à análise"),
        "writable_paths": ("src",),
        "instruction": "Remova a promessa absoluta.",
    }
    values.update(overrides)
    return ProposalRequest(**values)


def response(**overrides):
    values = {
        "observed_span": "garantido",
        "replacement": "possível",
        "reason": "Evita uma promessa absoluta.",
        "confidence": 0.91,
        "external_writes": 0,
    }
    values.update(overrides)
    return values


class DeepSeekProposalContractTest(unittest.TestCase):
    def test_remote_payload_has_only_minimum_sanitized_context(self) -> None:
        item = request(
            source_text=(
                "SERVICE_ROLE_KEY=segredo prefixo benefício garantido sufixo "
                "Bearer abcdefghijklmnopqrstuvwxyz"
            )
        )
        payload = build_remote_payload(item)
        self.assertEqual(
            set(payload), {"span", "allowed_replacements", "context", "instruction"}
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("src/copy.py", serialized)
        self.assertNotIn("segredo", serialized)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_rejects_non_unique_span_before_remote_call(self) -> None:
        with self.assertRaisesRegex(DeepSeekProposalError, "exatamente uma vez"):
            build_remote_payload(request(source_text="garantido e garantido"))

    def test_rejects_target_outside_ownership_and_protected_paths(self) -> None:
        with self.assertRaisesRegex(DeepSeekProposalError, "ownership"):
            build_remote_payload(request(target_path="backend/app.py"))
        with self.assertRaisesRegex(DeepSeekProposalError, "protegido"):
            build_remote_payload(
                request(target_path=".env.local", writable_paths=(".env.local",))
            )

    def test_validated_result_is_inert_and_bound_to_source_hash(self) -> None:
        proposal = validate_proposal(request(), response())
        self.assertEqual(proposal.occurrence_count, 1)
        self.assertEqual(len(proposal.source_sha256), 64)
        self.assertFalse(proposal.applied)
        self.assertFalse(hasattr(proposal, "apply"))

    def test_rejects_extra_fields_wrong_span_allowlist_and_external_write(self) -> None:
        with self.assertRaisesRegex(DeepSeekProposalError, "campos"):
            validate_proposal(request(), {**response(), "patch": "x"})
        with self.assertRaisesRegex(DeepSeekProposalError, "observed_span"):
            validate_proposal(request(), response(observed_span="benefício"))
        with self.assertRaisesRegex(DeepSeekProposalError, "allowlist"):
            validate_proposal(request(), response(replacement="reescrita livre"))
        with self.assertRaisesRegex(DeepSeekProposalError, "zero"):
            validate_proposal(request(), response(external_writes=1))

    def test_worker_uses_env_key_without_logging_or_exposing_thinking(self) -> None:
        captured = {}

        def transport(api_key, base_url, payload, timeout):
            captured.update({
                "api_key": api_key,
                "base_url": base_url,
                "payload": payload,
                "timeout": timeout,
            })
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps(response()),
                        "reasoning_content": "não deve ser lido",
                    }
                }]
            }

        worker = DeepSeekProposalWorker(transport=transport)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "chave-ultrassecreta"}):
            proposal = worker.propose(request())
        self.assertEqual(proposal.replacement, "possível")
        self.assertEqual(captured["api_key"], "chave-ultrassecreta")
        self.assertEqual(captured["payload"]["tools"], [])
        self.assertNotIn("chave-ultrassecreta", repr(worker))
        self.assertNotIn("reasoning_content", json.dumps(captured["payload"]))

    def test_missing_key_fails_before_transport(self) -> None:
        called = False

        def transport(*args):
            nonlocal called
            called = True
            return {}

        worker = DeepSeekProposalWorker(transport=transport)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DeepSeekProposalError, "ausente"):
                worker.propose(request())
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
