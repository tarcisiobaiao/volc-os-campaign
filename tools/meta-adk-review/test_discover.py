"""Hermetic discovery contract and actual ADK recovery execution."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from config import MODEL
from discover import Audit, build, validate_result


def fixture():
    return dict(schema_version='volc.ads.discovery.v1', status='provisional_no_account_data',
        thesis='Fixture hypothesis only', rejected_ideas=[], critique_changes=[],
        first_three=['I0', 'I1', 'I2'], missing_inputs=['live account evidence'],
        opportunities=[dict(id=f'I{i}', title='Fixture', priority='P1', confidence='low',
            current_evidence=['relative.py'], mechanism_and_delta='Hypothesis', frontend='Preview',
            engine_and_data='Source', meta_sources=[], prerequisites_and_unknowns=['data'],
            experiment_and_metrics='Compare cohorts', confounders_and_stop_condition='Lag',
            effort='small', first_ticket='Read only', acceptance='Test') for i in range(8)])


class DiscoveryTests(unittest.TestCase):
    def test_validates_dict_json_and_fence(self):
        for raw in (fixture(), json.dumps(fixture()), '```json\n' + json.dumps(fixture()) + '\n```'):
            self.assertEqual(validate_result(raw)['status'], 'provisional_no_account_data')

    def test_rejects_missing_and_duplicate_identifiers(self):
        for refs in (['I0', 'I0', 'I2'], ['missing', 'I1', 'I2']):
            data = fixture()
            data['first_three'] = refs
            with self.assertRaises(ValueError):
                validate_result(data)

    def test_rejects_unearned_completion_claim(self):
        data = fixture()
        data['status'] = 'implemented'
        with self.assertRaises(ValueError):
            validate_result(data)

    def test_budget_stops_fourth_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = Audit(Path(tmp))
            audit.calls = 3
            with self.assertRaises(RuntimeError):
                audit.before(SimpleNamespace(agent_name='other'), None)

    def test_requires_exact_model_and_grounding(self):
        for model, grounding in (('other', None), (MODEL, None)):
            with tempfile.TemporaryDirectory() as tmp:
                audit = Audit(Path(tmp))
                response = LlmResponse(model_version=model,
                    content=types.Content(role='model', parts=[types.Part(text='fixture')]),
                    grounding_metadata=grounding)
                with self.assertRaises(RuntimeError):
                    audit.after(SimpleNamespace(agent_name='opportunity_researcher'), response)

    def test_recovery_actual_adk_one_call_no_tools_or_native_schema(self):
        class FakeModel(BaseLlm):
            model: str = MODEL

            async def generate_content_async(self, llm_request, stream=False):
                assert not llm_request.config.tools
                assert not llm_request.config.response_schema
                yield LlmResponse(model_version=MODEL,
                    content=types.Content(role='model', parts=[types.Part(text=json.dumps(fixture()))]),
                    usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=10))

        with tempfile.TemporaryDirectory() as tmp:
            audit = Audit(Path(tmp))
            audit.calls = 2

            async def exercise():
                with patch('discover.Gemini', return_value=FakeModel()):
                    runner = InMemoryRunner(node=build(None, audit, 'no private data', 'public research', 'lead correction'),
                                            app_name='fixture_discovery')
                    try:
                        await runner.run_debug('fixture', quiet=True)
                    finally:
                        await runner.close()

            asyncio.run(exercise())
            self.assertEqual(audit.calls, 3)
            self.assertEqual(len(audit.result['opportunities']), 8)


if __name__ == '__main__':
    unittest.main()
