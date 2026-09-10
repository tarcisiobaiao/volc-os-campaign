"""Regressões de qualidade e procedência: nenhum socket nem chamada paga."""
import hashlib
import json
from dataclasses import replace

import pytest

from app.criativo.studio.spec_visual import CreativeSpec, especificar, compilar_prompt
from test_criativo_studio_adaptador import saida
from test_criativo_execucao import _executor, PEDIDO
from test_criativo_motor_openai import TransporteFalso, _pedido, _rodar
from services.creative_engine.motores.openai_imagem import MotorOpenAIImagem


def _spec(slot="4x5", modo="sem_foto"):
    lote = saida(1)
    return especificar(lote.pecas[0], lote.copies_compartilhadas[0], slot, modo)


@pytest.mark.parametrize("slot", ["1x1", "4x5", "9x16", "1.91x1"])
def test_spec_roundtrip_e_texto_exato_sem_copy_externa(slot):
    spec = CreativeSpec.model_validate_json(_spec(slot).model_dump_json())
    prompt = compilar_prompt(spec)
    assert "Headline interna 1" in prompt and "Complemento 1" in prompt and "Ver como" in prompt
    assert "COPY EXTERNA" not in prompt
    assert spec.copy_externa["texto_principal"].startswith("COPY EXTERNA")
    assert spec.revisao_visual == "humana_pendente"


def test_vertical_tem_protecao_e_composicao_propria():
    vertical, square = _spec("9x16"), _spec("1x1")
    assert vertical.margem_segura["base"] > square.margem_segura["base"]
    assert vertical.composicao != square.composicao


@pytest.mark.parametrize("modo", ["sem_foto", "hibrido", "reinterpretado", "referencia_visual"])
def test_payload_real_nunca_contradiz_texto_aprovado(modo):
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="teste", transporte=transporte)
    spec = _spec(modo=modo)
    pedido = replace(_pedido(), insumo=compilar_prompt(spec), contexto={"modo_de_composicao": modo})
    resposta = _rodar(motor, pedido)
    payload = transporte.chamadas[0]["payload"]
    assert payload["model"] == "gpt-image-2" and payload["quality"] == "medium"
    assert "Sem texto, sem letras" not in payload["prompt"]
    for texto in spec.texto_exato.values():
        assert texto in payload["prompt"]
    meta = resposta.arquivos[0].metadados
    assert meta["prompt_efetivo"] == payload["prompt"]
    assert meta["prompt_sha256"] == hashlib.sha256(payload["prompt"].encode()).hexdigest()


@pytest.mark.asyncio
async def test_spec_persistida_retoma_e_muda_idempotencia(tmp_path):
    ex = _executor(tmp_path)
    spec = _spec("1x1").model_dump(mode="json")
    pedido = {**PEDIDO, "slots": ["1x1"], "creative_specs": [spec]}
    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    briefing = ex.repo.briefings[job["briefing_id"]]
    assert briefing["referencias"] == [{"tipo": "creative_spec", "spec": spec}]
    await ex._executar(job["id"])
    assert "TEXTO EXATO OBRIGATÓRIO" in ex.repo.masters[0]["insumo_sanitizado"]
    changed = json.loads(json.dumps(spec))
    changed["texto_exato"]["headline"] = "Outra headline"
    other, created = await ex.criar_job_de_imagem({**pedido, "creative_specs": [changed]}, "u1")
    assert created and other["id"] != job["id"]
