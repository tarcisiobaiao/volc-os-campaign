"""Blueprint transport and historical replay: hermetic, no provider or database."""
import hashlib
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.criativo.agente.contrato import DirecaoDeArte, ElementoCongelado, SaidaDoAgente
from app.criativo.agente.prompts import SYSTEM_PROMPT, montar_missao
from app.criativo.agente.validacao import validar_saida, SaidaCriativaInvalida
from app.criativo.dominio import chave_de_idempotencia
from app.criativo.studio.autorizacao import assinatura_do_plano
from app.criativo.studio.spec_visual import CreativeSpec, especificar, compilar_prompt
from services.creative_engine.motores.openai_imagem import MotorOpenAIImagem
from test_criativo_agente_meta import pedido, saida as saida_bruta
from test_criativo_studio_adaptador import saida
from test_criativo_motor_openai import TransporteFalso, _pedido, _rodar


DIRECAO = {
    "composicao": "Cena à esquerda; headline no alto à direita e CTA abaixo, com respiro.",
    "cena": "Detalhe de um caderno sobre mesa de estudo, enquadramento oblíquo próximo, sem pessoa.",
    "tratamento": "Fotografia ultrarrealista: luz lateral de janela, textura de papel e madeira, profundidade natural.",
    "tipografia": "Headline pesada em duas linhas, complemento menor e CTA legível, alinhados à esquerda.",
    "paleta_e_contraste": "Madeira quente e fundo creme; texto azul escuro sobre a região clara.",
}


def _spec(*, versioned=True, modo="sem_foto", slot="4x5", direcao=None):
    lote = saida(1)
    campos = dict(direcao or DIRECAO)
    if versioned:
        campos["blueprint_version"] = "volc.art-direction/2"
    lote.pecas[0].direcao_de_arte = DirecaoDeArte.model_validate(campos)
    return especificar(lote.pecas[0], lote.copies_compartilhadas[0], slot, modo)


def _assinatura(spec):
    return assinatura_do_plano(
        run_ref="run-test", creative_refs=[spec.creative_ref], format_ids=[spec.formato],
        modelo="openai:gpt-image-2", qualidade="medium", total_de_renders=1,
        custo_estimado_usd=None, anexo_sha256=None, modo_de_composicao="sem_foto",
        creative_specs=[spec.model_dump(mode="json")],
    )


def test_legacy_prompt_is_byte_identical_and_not_promoted():
    lote = saida(1)
    spec = especificar(lote.pecas[0], lote.copies_compartilhadas[0], "4x5", "sem_foto")
    assert spec.schema_version == "volc.creative-spec/1"
    assert hashlib.sha256(compilar_prompt(spec).encode()).hexdigest() == "2784225d6845bcc7c31cf74a5f2328c2afadf3f9375e689d0777452272a3b4f0"
    data = spec.model_dump(mode="json")
    del data["schema_version"]
    assert CreativeSpec.model_validate(data).schema_version == "volc.creative-spec/1"
    assert _spec(versioned=False).schema_version == "volc.creative-spec/1"


def test_legacy_direction_roundtrip_preserves_nested_json_and_frozen_approval():
    assert DirecaoDeArte.model_validate(DIRECAO).model_dump(mode="json") == DIRECAO
    bruto = saida_bruta()
    bruto["pecas"][0]["direcao_de_arte"] = DIRECAO.copy()
    output = SaidaDoAgente.model_validate(bruto)
    old_piece = output.pecas[0].model_dump(mode="json")
    assert "blueprint_version" not in old_piece["direcao_de_arte"]
    assert json.loads(output.model_dump_json())["pecas"][0] == old_piece
    req = pedido().model_copy(update={"elementos_congelados": [ElementoCongelado(
        ref="frozen_peca", caminho="/pecas/creative_variacao_1",
        valor=json.dumps(old_piece, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        aprovado_em="2026-09-09T12:00:00Z",
    )]})
    validar_saida(req, output)
    output.pecas[0].direcao_de_arte.blueprint_version = "volc.art-direction/2"
    with pytest.raises(SaidaCriativaInvalida, match="congelado foi alterado"):
        validar_saida(req, output)


@pytest.mark.parametrize("slot", ["1x1", "4x5", "9x16", "1.91x1"])
def test_v2_transports_all_five_decisions_with_exact_text_and_no_external_copy(slot):
    spec = _spec(slot=slot)
    restored = CreativeSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec
    prompt = compilar_prompt(restored)
    assert spec.schema_version == "volc.creative-spec/2"
    for decision in DIRECAO.values():
        assert decision in prompt
    for text in spec.texto_exato.values():
        assert text in prompt
    assert "COPY EXTERNA" not in prompt
    # A garantia é a mesma; a ameaça é que mudou. O prompt disparava um parágrafo
    # explicando que `sem_foto` não proíbe gerar cena fotográfica porque ele mesmo
    # imprimia `PAPEL DA REFERÊNCIA: sem_foto` e criava a ambiguidade que ia
    # desfazer. Agora o rótulo interno não viaja, então não há o que desambiguar —
    # e o teste passa a exigir a ausência do termo, que é a garantia mais forte.
    assert "sem_foto" not in prompt
    # O mesmo vale para o rótulo de proporção: `formato.rotulo` do 4x5 é
    # "Retrato", que em português é um pedido de retrato de PESSOA. Ele vazava na
    # última linha do prompt do motor e produzia um lote inteiro de retratos.
    assert "Retrato" not in prompt
    assert "compartilhadas" not in prompt


def test_explicit_illustration_is_not_silently_replaced_by_photo_and_no_copy_shortening():
    spec = _spec(direcao={**DIRECAO, "tratamento": "Ilustração em aquarela expressamente solicitada, com papel texturizado."})
    spec.texto_exato["headline"] = "Uma headline antiga muito longa, com condição estimada, que foi expressamente aprovada"
    before = spec.model_dump_json()
    prompt = compilar_prompt(spec)
    assert "Ilustração em aquarela expressamente solicitada" in prompt
    assert "Não converta uma ilustração explicitamente aprovada em fotografia" in prompt
    assert json.dumps(spec.texto_exato["headline"], ensure_ascii=False) in prompt
    assert spec.model_dump_json() == before


@pytest.mark.parametrize("missing", ["blueprint_version", *DIRECAO])
def test_v2_rejects_missing_blueprint_field_in_persisted_spec(missing):
    data = _spec().model_dump(mode="json")
    data["direcao_de_arte"].pop(missing)
    with pytest.raises(ValidationError):
        CreativeSpec.model_validate(data)


def test_version_and_each_visual_decision_change_plan_signature_and_job_identity():
    current, old = _spec(), _spec(versioned=False)
    assert _assinatura(current) != _assinatura(old)
    initial = {"creative_specs": [current.model_dump(mode="json")]}
    assert chave_de_idempotencia(initial) != chave_de_idempotencia({"creative_specs": [old.model_dump(mode="json")]})
    for field in DIRECAO:
        changed = current.model_copy(deep=True)
        changed.direcao_de_arte[field] += " Uma decisão diferente."
        assert _assinatura(changed) != _assinatura(current)
        assert chave_de_idempotencia({"creative_specs": [changed.model_dump(mode="json")]}) != chave_de_idempotencia(initial)
    assert _assinatura(CreativeSpec.model_validate_json(current.model_dump_json())) == _assinatura(current)


@pytest.mark.parametrize("modo", ["sem_foto", "hibrido", "reinterpretado", "referencia_visual"])
def test_v2_reaches_actual_motor_payload_without_paid_call(modo):
    spec = _spec(modo=modo)
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="fixture", transporte=transporte)
    request = replace(_pedido(), insumo=compilar_prompt(spec), contexto={"modo_de_composicao": modo})
    result = _rodar(motor, request)
    payload = transporte.chamadas[0]["payload"]
    assert payload["model"] == "gpt-image-2"
    assert payload["quality"] == "medium"
    assert DIRECAO["cena"] in payload["prompt"]
    assert "Headline interna 1" in payload["prompt"]
    assert "COPY EXTERNA" not in payload["prompt"]
    assert result.arquivos[0].metadados["prompt_sha256"] == hashlib.sha256(payload["prompt"].encode()).hexdigest()
    if modo == "hibrido":
        assert "região de texto" in spec.composicao
        assert "foto real" in payload["prompt"]


def test_blueprint_instruction_and_schema_separate_lp_data_from_direction():
    envelope = json.loads(montar_missao(pedido()))
    direction_schema = envelope["SCHEMA_DE_SAIDA"]["$defs"]["DirecaoDeArte"]
    assert "blueprint_version" in direction_schema["properties"]
    assert "DADOS_NAO_CONFIAVEIS" in envelope
    for instruction in (
        "fotografia publicitária", "3–8 palavras", "LP é matéria/guia",
        "HIPÓTESES", "peças congeladas", "sem inventar interface oficial",
    ):
        assert instruction in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_new_agent_blueprint_survives_plan_job_persistence_and_executor(tmp_path):
    from app.criativo.agente import AgenteCriativoMeta
    from app.criativo.studio import PedidoDeGeracao
    from app.criativo.studio.adaptador import montar_plano, pedido_de_job
    from test_criativo_agente_meta import ModeloFake
    from test_criativo_execucao import _executor

    bruto = saida_bruta()
    # Cada peça recebe uma rota visual própria: o portão de cobertura recusa um
    # lote onde duas peças repetem a trinca (rota_de_texto, registro,
    # presenca_humana), que era exatamente o defeito do lote de 09/09/2026.
    eixos = [
        ("campo_cromatico", "editorial", "close"),
        ("integrado_na_cena", "foto_crua", "maos"),
        ("tipografia_protagonista", "grafico", "ausente"),
        ("rodape_limpo", "natureza_morta", "ausente"),
    ]
    for indice, piece in enumerate(bruto["pecas"]):
        rota, registro, presenca = eixos[indice % len(eixos)]
        piece["direcao_de_arte"] = {
            **DIRECAO, "blueprint_version": "volc.art-direction/2",
            "rota_de_texto": rota, "registro": registro, "presenca_humana": presenca,
            # A primeira peça leva checklist e vira densa: o portão de lote
            # recusa quando TODAS as peças têm a mesma contagem de blocos de
            # texto, porque aí densidade deixa de ser variável de teste.
            **({"checklist": ["Quem pode consultar", "Quais os critérios",
                              "Onde ver o calendário"]} if indice == 0 else {}),
        }
    result = await AgenteCriativoMeta(ModeloFake([bruto])).executar(pedido())
    # This JSON boundary models persistence; never replace it with model_copy.
    restored = SaidaDoAgente.model_validate_json(result.saida.model_dump_json())
    plan = montar_plano(
        saida=restored,
        pedido=PedidoDeGeracao(run_ref="crrun_" + "b" * 24,
                              selected_creative_refs=["creative_variacao_1"], format_ids=["1x1"]),
        caminhos_aprovados=frozenset(["/pecas/creative_variacao_1"]),
        contexto_do_publico="Pessoa interessada no tema da matéria.", objetivo="OUTCOME_TRAFFIC",
    )
    assert plan.pode_executar
    assert plan.briefings[0].creative_spec.schema_version == "volc.creative-spec/2"
    request = pedido_de_job(plan.briefings, nome_da_operacao="QA blueprint fixture")
    assert request["creative_specs"][0]["direcao_de_arte"]["cena"] == DIRECAO["cena"]
    executor = _executor(tmp_path)
    job, created = await executor.criar_job_de_imagem(request, "u1")
    assert created
    briefing = executor.repo.briefings[job["briefing_id"]]
    assert briefing["referencias"][0]["spec"] == request["creative_specs"][0]
    await executor._executar(job["id"])
    actual = executor.repo.masters[0]["insumo_sanitizado"]
    assert DIRECAO["cena"] in actual
    # A prova de que o compilador v2 rodou passou a ser estrutural, e não um
    # banner. O banner era texto que o modelo de imagem lia — e podia tentar
    # desenhar — só para que um teste pudesse afirmar qual ramo executou. Estas
    # duas marcas são impossíveis no v1, que abre com "Crie UMA arte publicitária"
    # e despeja a direção como um único blob JSON em "DIREÇÃO DE ARTE:".
    assert actual.startswith("Imagem de anúncio, entrega ")
    assert "\nCENA: " in actual and "\nPALETA E CONTRASTE: " in actual
    assert "DIREÇÃO DE ARTE: {" not in actual
    assert "Entenda o ponto 1" in actual
    repeated, created_again = await executor.criar_job_de_imagem(request, "u1")
    assert not created_again and repeated["id"] == job["id"]
