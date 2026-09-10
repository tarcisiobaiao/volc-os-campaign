"""The creative angle can vary; the subject cannot vanish from the image."""
import asyncio
import json

import pytest
from pydantic import ValidationError

from app.criativo.agente.contrato import EntradaNovaOperacao, PedidoDoAgente, ElementoCongelado, SaidaDoAgente
from app.criativo.agente.orquestrador import AgenteCriativoMeta, RespostaDoModeloInvalida
from app.criativo.agente.prompts import montar_missao
from app.criativo.agente.validacao import SaidaCriativaInvalida, validar_saida
from app.criativo.studio.spec_visual import especificar, compilar_prompt
from test_criativo_agente_meta import pedido, saida, ModeloFake, RepoFake, _app


def anchored():
    return pedido(1).model_copy(update={"assunto_principal": "Pé-de-Meia", "referencias_visuais": "Acentos verdes e amarelos; cena de estudo. Paleta editorial, sem logos."})


def output(headline="Pé-de-Meia: entenda a consulta", complemento="Informação antes da decisão."):
    raw = saida(1)
    raw["pecas"][0].update(headline_interna=headline, complemento_interno=complemento)
    return SaidaDoAgente.model_validate(raw)


@pytest.mark.parametrize("headline", ["O aplicativo não paga", "Jornada do Estudante: como entrar", "Pé-de-Meias novas"])
def test_generic_or_secondary_subject_cannot_pass(headline):
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(anchored(), output(headline))


def test_ancora_de_desejo_substitui_o_nome_do_canal_na_arte():
    """O lote reclamado de 09/09/2026, em forma de contraprova.

    A matéria era sobre o app "Jornada do Estudante" e o app É o assunto correto
    da página. Mas o que faz alguém parar o polegar é o dinheiro, e com um campo
    só o validador exigia o nome longo do canal dentro de toda imagem — as
    quatro headlines geradas continham "App Jornada do Estudante" porque não
    havia como passar sem ele.
    """
    pedido_arbitragem = pedido(1).model_copy(update={
        "assunto_principal": "App Jornada do Estudante",
        "ancora_de_desejo": "Pé-de-Meia",
    })
    # A headline que o motor NÃO conseguia emitir antes: fala do assunto que
    # interessa e não carrega o nome institucional do canal.
    validar_saida(pedido_arbitragem, output("Pé-de-Meia: quanto já entrou?", "Consulte pelo celular."))
    # E o nome do canal sozinho deixa de bastar: ele não é mais a âncora.
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(pedido_arbitragem, output("Login no App Jornada do Estudante", "Acesso com CPF."))


def test_variante_confirmada_pelo_operador_e_aceita_e_o_modelo_nao_inventa_a_sua():
    """Sinônimo perfeito era recusado; agora passa — mas só se o operador declarou."""
    sem_variantes = pedido(1).model_copy(update={"assunto_principal": "Pé-de-Meia"})
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(sem_variantes, output("Poupança do ensino médio: quanto já entrou?", "Veja o guia."))

    com_variantes = sem_variantes.model_copy(update={"ancoras_aceitas": ["Poupança do ensino médio"]})
    validar_saida(com_variantes, output("Poupança do ensino médio: quanto já entrou?", "Veja o guia."))


def test_sem_ancora_declarada_o_comportamento_historico_e_preservado():
    """Um pedido antigo não muda de significado por causa de um campo novo."""
    historico = pedido(1).model_copy(update={"assunto_principal": "Pé-de-Meia"})
    assert historico.ancora_de_desejo is None and historico.ancoras_aceitas == []
    validar_saida(historico, output("Pé-de-Meia: entenda a consulta", "Informação antes da decisão."))
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(historico, output("Entenda a consulta", "Informação antes da decisão."))


@pytest.mark.parametrize("headline,complemento", [
    ("PÉ DE MEIA: como consultar?", "Confira o guia."),
    ("Entenda a consulta", "Veja o guia do Pé–de–Meia."),
    ("Pe-de-Meia: entenda", "Informação independente."),
])
def test_topic_in_visible_headline_or_complement_passes(headline, complemento):
    validar_saida(anchored(), output(headline, complemento))


def test_topic_only_in_external_copy_cta_or_direction_does_not_pass():
    out = output("Como consultar?")
    out.pecas[0].cta_visual = "Ver Pé-de-Meia"
    out.pecas[0].direcao_visual = "Cena editorial sobre Pé-de-Meia."
    out.copies_compartilhadas[0].titulo = "Pé-de-Meia"
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(anchored(), out)


def test_legacy_without_anchor_and_frozen_pieces_are_preserved():
    out = output("O aplicativo não paga")
    validar_saida(pedido(1), out)
    snapshot = json.dumps(out.pecas[0].model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    req = anchored().model_copy(update={"elementos_congelados": [ElementoCongelado(
        ref="frozen_old", caminho=f"/pecas/{out.pecas[0].ref}", valor=snapshot, aprovado_em="2026-09-09T12:00:00Z",
    )]})
    validar_saida(req, out)
    out.pecas[0].headline_interna = "Pé-de-Meia: mudou"
    with pytest.raises(SaidaCriativaInvalida, match="congelado foi alterado"):
        validar_saida(req, out)


def test_validator_corrects_strategy_before_image_generation():
    model = ModeloFake([output("O aplicativo não paga").model_dump(mode="json"), output().model_dump(mode="json")])
    result = asyncio.run(AgenteCriativoMeta(model).executar(anchored()))
    assert result.tentativas == 2
    spec = especificar(result.saida.pecas[0], result.saida.copies_compartilhadas[0], "4x5", "sem_foto")
    assert "Pé-de-Meia: entenda a consulta" in compilar_prompt(spec)
    bad = ModeloFake([output("O aplicativo não paga").model_dump(mode="json")])
    with pytest.raises(RespostaDoModeloInvalida):
        asyncio.run(AgenteCriativoMeta(bad).executar(anchored()))


@pytest.mark.parametrize("topic", ["   ", "---", "!", "x" * 161])
def test_malformed_anchor_rejected(topic):
    raw = anchored().model_dump(mode="json")
    raw["assunto_principal"] = topic
    with pytest.raises(ValidationError):
        PedidoDoAgente.model_validate(raw)


def test_input_and_refinement_keep_topic_in_durable_payload():
    raw = anchored().model_dump(mode="json")
    entry = EntradaNovaOperacao.model_validate({k: v for k, v in raw.items() if k in EntradaNovaOperacao.model_fields})
    repo = RepoFake()
    client = _app(repo)
    created = client.post("/api/criativos/meta/agente/operacoes", json=entry.model_dump(mode="json"))
    assert created.status_code == 201, created.text
    assert repo.operacao["input"]["assunto_principal"] == "Pé-de-Meia"
    assert repo.run["input"]["referencias_visuais"] == entry.referencias_visuais
    envelope = json.loads(montar_missao(PedidoDoAgente.model_validate(repo.run["input"])))
    assert envelope["DADOS_NAO_CONFIAVEIS"]["assunto_principal"] == "Pé-de-Meia"
    # The continuation route reconstructs from persisted input, not from the page.
    continued = client.post(f"/api/criativos/meta/agente/operacoes/{created.json()['project_ref']}/runs", json={"fase": "NOVA_OPERACAO"})
    assert continued.status_code == 201, continued.text
    assert repo.run["input"]["assunto_principal"] == "Pé-de-Meia"
