"""Big idea is approved planning, never extra text secretly added at render."""

import json

import pytest
from pydantic import ValidationError

from app.criativo.agente.contrato import BigIdea, DirecaoDeArte, ElementoCongelado, EntradaNovaOperacao, PedidoDoAgente, SaidaDoAgente
from app.criativo.agente.prompts import SYSTEM_PROMPT, montar_missao
from app.criativo.agente.validacao import SaidaCriativaInvalida, validar_saida
from app.criativo.contexto_pagina import ContextoDaPagina
from app.criativo.studio.spec_visual import CreativeSpec, compilar_prompt, especificar
from test_criativo_agente_meta import OWNER, PROJECT_REF, RUN_REF, RepoFake, _app, pedido, saida
from test_criativo_blueprint_v2 import DIRECAO


URL = "https://example.com/guia"
FACT_A = "fact_lp_" + "a" * 16
FACT_B = "fact_lp_" + "b" * 16
BIG_IDEA = {
    "ideia_central": "Uma pequena informação muda a próxima pergunta.",
    "pergunta_latente": "Qual detalhe consultar antes do próximo passo?",
    "promessa_do_clique": "Ler um guia independente com os passos da consulta.",
    "cena_chave": "Mão virando a página de um caderno; a luz revela uma anotação sem palavras legíveis.",
}


def _contexto():
    return ContextoDaPagina(
        url_solicitada=URL, url_final=URL, analisado_em="2026-09-09T12:00:00Z",
        conteudo_sha256="c" * 64, titulo="Guia independente", assunto="Consulta informativa",
        proposta="Explicar passos de consulta.", publico_sugerido="Pessoas buscando informação.",
        momento_sugerido="Pesquisa inicial.", angulos_sugeridos=[], informacoes_ausentes=[], avisos=[],
        fatos=[{
            "ref": ref, "declaracao": texto, "trecho": texto, "origem_url": URL,
        } for ref, texto in [(FACT_A, "O guia descreve passos de consulta."), (FACT_B, "O guia descreve documentação.")]],
        motivacoes_sugeridas=[{
            "tipo": "desejo", "hipotese": "Buscar clareza para fazer uma consulta.",
            "pergunta_latente": "Por onde começar a consulta?",
            "entrega_da_pagina": "Uma explicação dos passos de consulta.", "fato_refs": [FACT_A],
        }, {
            "tipo": "receio", "hipotese": "Receio de esquecer uma informação.",
            "pergunta_latente": "Quais documentos conferir?",
            "entrega_da_pagina": "Uma descrição da documentação.", "fato_refs": [FACT_A, FACT_B],
        }],
    )


def _pedido(*, aprovar_a=True, aprovar_b=False):
    raw = pedido(1).model_dump(mode="json")
    contexto = _contexto()
    raw.update(url_destino=URL, contexto_da_pagina=contexto.model_dump(mode="json"))
    for fato, aprovado in zip(contexto.fatos, (aprovar_a, aprovar_b)):
        if aprovado:
            raw["fatos_da_oferta"].append({"ref": fato.ref, "declaracao": fato.declaracao, "origem": "LANDING_PAGE"})
    return PedidoDoAgente.model_validate(raw)


def _saida(*, big_idea=True):
    raw = saida(1)
    if big_idea:
        raw["pecas"][0]["big_idea"] = dict(BIG_IDEA)
    return SaidaDoAgente.model_validate(raw)


@pytest.mark.parametrize("explicito_null", [False, True])
def test_historical_omission_and_null_roundtrip_without_new_key(explicito_null):
    raw = saida(1)
    if explicito_null:
        raw["pecas"][0]["big_idea"] = None
    out = SaidaDoAgente.model_validate(raw)
    assert out.pecas[0].big_idea is None
    assert "big_idea" not in out.pecas[0].model_dump(mode="json")
    assert "big_idea" not in json.loads(out.model_dump_json())["pecas"][0]
    restored = SaidaDoAgente.model_validate_json(out.model_dump_json())
    assert restored.model_dump_json() == out.model_dump_json()
    validar_saida(pedido(1), restored)


@pytest.mark.parametrize("caminho", ["/pecas", "/pecas/creative_variacao_1"])
def test_frozen_historical_piece_stays_literal_despite_new_context(caminho):
    out = _saida(big_idea=False)
    snapshot = out.model_dump(mode="json")["pecas"]
    if caminho != "/pecas":
        snapshot = snapshot[0]
    req = _pedido().model_copy(update={"elementos_congelados": [ElementoCongelado(
        ref="frozen_legacy", caminho=caminho,
        valor=json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        aprovado_em="2026-09-09T12:00:00Z",
    )]})
    validar_saida(req, out)
    out.pecas[0].big_idea = BigIdea(**BIG_IDEA)
    with pytest.raises(SaidaCriativaInvalida, match="congelado foi alterado"):
        validar_saida(req, out)


def test_supported_motivational_context_requires_big_idea_before_render():
    with pytest.raises(SaidaCriativaInvalida, match="falta big_idea"):
        validar_saida(_pedido(), _saida(big_idea=False))
    validar_saida(_pedido(), _saida())


def test_no_approved_support_does_not_impose_new_requirement_on_legacy_output():
    validar_saida(_pedido(aprovar_a=False), _saida(big_idea=False))


def test_valid_big_idea_and_direction_fit_frozen_snapshot_on_continuation(monkeypatch):
    out = _saida()
    out.pecas[0].direcao_de_arte = DirecaoDeArte(
        composicao="c" * 500, cena="c" * 500, tratamento="t" * 400,
        tipografia="t" * 300, paleta_e_contraste="p" * 400,
        blueprint_version="volc.art-direction/2",
        rota_de_texto="campo_cromatico", registro="editorial", presenca_humana="close",
    )
    out.pecas[0].big_idea = BigIdea(
        ideia_central="i" * 300, pergunta_latente="p" * 200,
        promessa_do_clique="p" * 300, cena_chave="c" * 400,
    )
    validar_saida(_pedido(), out)
    snapshot = json.dumps(out.pecas[0].model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert len(snapshot) > 4000  # New planning made a formerly valid snapshot exceed the old cap.
    frozen = ElementoCongelado(
        ref="frozen_complete", caminho="/pecas/creative_variacao_1", valor=snapshot,
        aprovado_em="2026-09-09T12:00:00Z",
    )
    req = _pedido().model_copy(update={"elementos_congelados": [frozen]})
    validar_saida(req, SaidaDoAgente.model_validate_json(out.model_dump_json()))
    # Exercise both real route functions, not just construction of the DTO.
    repo = RepoFake()
    raw = _pedido().model_dump(mode="json")
    entrada = {k: v for k, v in raw.items() if k in EntradaNovaOperacao.model_fields}
    repo.operacao = {"project_ref": PROJECT_REF, "input": entrada, "owner_id": OWNER}
    repo.run = {"project_ref": PROJECT_REF, "run_ref": RUN_REF, "status": "COMPLETED", "output": out.model_dump(mode="json")}
    decisoes = []

    async def registrar(row):
        row = {**row, "created_at": "2026-09-09T12:00:00Z"}
        decisoes.append(row)
        return row

    async def listar(*args):
        return decisoes

    monkeypatch.setattr(repo, "registrar_decisao", registrar)
    monkeypatch.setattr(repo, "listar_decisoes", listar)
    cliente = _app(repo)
    aprovado = cliente.post(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/decisoes", json={
        "run_ref": RUN_REF, "decisao": "APROVADO", "escopo": "PONTUAL", "caminho": frozen.caminho,
    })
    assert aprovado.status_code == 201, aprovado.text
    continuado = cliente.post(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/runs", json={"fase": "NOVA_OPERACAO"})
    assert continuado.status_code == 201, continuado.text
    assert repo.run["input"]["elementos_congelados"][0]["valor"] == snapshot
    validar_saida(PedidoDoAgente.model_validate(repo.run["input"]), out)


def test_frozen_snapshot_limit_remains_bounded():
    common = {"ref": "frozen_limit", "caminho": "/pecas/creative_variacao_1", "aprovado_em": "2026-09-09T12:00:00Z"}
    assert len(ElementoCongelado(**common, valor="x" * 16000).valor) == 16000
    with pytest.raises(ValidationError):
        ElementoCongelado(**common, valor="x" * 16001)


def test_partial_field_freeze_does_not_exempt_whole_piece_from_big_idea():
    out = _saida(big_idea=False)
    req = _pedido().model_copy(update={"elementos_congelados": [ElementoCongelado(
        ref="frozen_headline", caminho="/pecas/creative_variacao_1/headline_interna",
        valor=json.dumps(out.pecas[0].headline_interna, ensure_ascii=False),
        aprovado_em="2026-09-09T12:00:00Z",
    )]})
    with pytest.raises(SaidaCriativaInvalida, match="falta big_idea"):
        validar_saida(req, out)
    out.pecas[0].big_idea = BigIdea(**BIG_IDEA)
    validar_saida(req, out)


@pytest.mark.parametrize("aprovar_a,aprovar_b,total", [(True, True, 2), (True, False, 1), (False, True, 0), (False, False, 0)])
def test_mission_filters_rejected_support_without_mutating_persisted_context(aprovar_a, aprovar_b, total):
    req = _pedido(aprovar_a=aprovar_a, aprovar_b=aprovar_b)
    before = req.model_dump_json()
    envelope = json.loads(montar_missao(req))
    actual = envelope["DADOS_NAO_CONFIAVEIS"]["contexto_da_pagina"]["motivacoes_sugeridas"]
    assert len(actual) == total
    aprovados = {f.ref for f in req.fatos_da_oferta}
    assert all(set(m["fato_refs"]) <= aprovados for m in actual)
    assert len(req.contexto_da_pagina.motivacoes_sugeridas) == 2
    assert req.model_dump_json() == before
    assert "São pontes" in SYSTEM_PROMPT and "não prova de como o público pensa" in SYSTEM_PROMPT


@pytest.mark.parametrize("campo", list(BIG_IDEA))
def test_incomplete_or_empty_big_idea_is_rejected(campo):
    data = dict(BIG_IDEA)
    del data[campo]
    with pytest.raises(ValidationError):
        BigIdea.model_validate(data)
    with pytest.raises(ValidationError):
        BigIdea.model_validate({**BIG_IDEA, campo: "   "})


def test_big_idea_is_not_injected_as_image_text_and_approved_scene_reaches_prompt():
    out = _saida()
    out.pecas[0].direcao_de_arte = DirecaoDeArte.model_validate({
        **DIRECAO, "blueprint_version": "volc.art-direction/2", "cena": BIG_IDEA["cena_chave"],
        "rota_de_texto": "campo_cromatico", "registro": "editorial", "presenca_humana": "close",
    })
    out.pecas[0].direcao_visual = "Close editorial do instante de descoberta; uma cena central com área de texto separada."
    validar_saida(_pedido(), out)
    spec = especificar(out.pecas[0], out.copies_compartilhadas[0], "4x5", "sem_foto")
    restored = CreativeSpec.model_validate_json(spec.model_dump_json())
    prompt = compilar_prompt(restored)
    assert BIG_IDEA["cena_chave"] in prompt
    assert out.pecas[0].direcao_visual in prompt
    assert all(value not in prompt for key, value in BIG_IDEA.items() if key != "cena_chave")
    assert "big_idea" not in prompt
    assert all(value not in spec.texto_exato.values() for value in BIG_IDEA.values())
    # Planning alone cannot silently change an already-approved renderer spec.
    out.pecas[0].big_idea = BigIdea(**{**BIG_IDEA, "cena_chave": "Outra cena hipotética, ainda não transposta à direção aprovada."})
    unchanged = especificar(out.pecas[0], out.copies_compartilhadas[0], "4x5", "sem_foto")
    assert unchanged.model_dump_json() == spec.model_dump_json()
    assert "Transponha explicitamente a cena_chave" in SYSTEM_PROMPT
