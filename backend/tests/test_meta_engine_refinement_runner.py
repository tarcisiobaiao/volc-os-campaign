"""Hermetic contracts for the bounded paid-review runner."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('refinement_runner',Path(__file__).resolve().parents[2]/'scripts/meta_engine_refinement.py')
runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)

def packet(path='src/test.ts'):
    return {'scope':'synthetic review','question':'Review state transitions','excerpts':[{'path':path,'start':1,'end':1}]}

def test_allowlisted_ranges_and_pii_redaction(tmp_path):
    (tmp_path/'src').mkdir(); (tmp_path/'src/test.ts').write_text('const email="example@example.test";')
    text, sources=runner.bundle(packet(),tmp_path)
    assert 'example@example.test' not in text and '[REDACTED]' in text
    assert sources[0]['start']==1

@pytest.mark.parametrize('path',['.env','src/../.env','backend/app/config.py','backend/app/business_credentials.py'])
def test_configuration_and_paths_blocked(tmp_path,path):
    with pytest.raises(ValueError): runner.bundle(packet(path),tmp_path)

def test_mismatch_does_not_accept_review():
    assert runner.parse({'modelVersion':'different'})['status']=='model_mismatch'

def test_thought_is_not_retained():
    result=runner.parse({'modelVersion':runner.MODEL,'candidates':[{'finishReason':'STOP','content':{'parts':[
        {'thought':True,'text':'PRIVATE THOUGHT'}, {'text':'{"status":"ok","findings":[]}'}]}}]})
    assert result['status']=='review_received'
    assert 'PRIVATE THOUGHT' not in str(result)
    assert result['grounding_verified'] is False

def test_secret_is_blocked(tmp_path):
    (tmp_path/'src').mkdir(); (tmp_path/'src/test.ts').write_text('const key="sk-'+('x'*30)+'";')
    with pytest.raises(ValueError): runner.bundle(packet(),tmp_path)

def test_followup_feedback_is_transmitted_and_sanitized(tmp_path):
    (tmp_path/'src').mkdir(); (tmp_path/'src/test.ts').write_text('const ok=true;')
    request=packet(); request['feedback']='Previous local test failed for example@example.test'
    text,_=runner.bundle(request,tmp_path)
    assert 'Previous local test failed' in text
    assert 'example@example.test' not in text

def test_feedback_secrets_blocked(tmp_path):
    (tmp_path/'src').mkdir(); (tmp_path/'src/test.ts').write_text('const ok=true;')
    request=packet(); request['feedback']='sk-'+('x'*30)
    with pytest.raises(ValueError): runner.bundle(request,tmp_path)
