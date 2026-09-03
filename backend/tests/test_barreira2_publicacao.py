"""BARREIRA 2 — as duas portas do backend que levam ao WordPress.

## O que estes testes provam, e por que cada prova tem esta forma

Existem DUAS portas para o WordPress, e um portão numa deixava a outra aberta:

    A) POST /redator/disparar                  → funil INTEIRO, com `--publish`
    B) POST /redator/runs/{id}/publicar/{page} → UMA página já escrita

A prova central é a SENTINELA. Não basta ver o 409: um portão que recusa DEPOIS
de chamar o adaptador já escreveu no site do cliente, e a resposta 409 seria uma
mentira educada. Por isso `worker.publicar_pagina` e
`asyncio.create_subprocess_exec` são trocados por funções que chamam
`pytest.fail` — o teste só passa se elas NUNCA forem invocadas.

## Hermético, e o que isso quer dizer aqui

Nenhum teste abre socket, nenhum toca no Supabase e nenhum executa o motor. O
Supabase é um dublê em memória, a pasta do run é um `tmp_path`, e o subprocesso
é a sentinela acima. Um teste desta barreira que precisasse de rede seria um
teste que ninguém roda — e barreira que ninguém roda não é barreira.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import publicacao as pub

# ── o mundo de mentira ─────────────────────────────────────────────────────

PARAGRAFO = (
    "<p>Organizar a rotina de leitura exige menos esforco do que parece quando "
    "cada etapa fica escrita e visivel. Comece separando os assuntos por tema, "
    "depois escolha um horario fixo e mantenha a lista curta o suficiente para "
    "caber num dia comum de trabalho. Quem tenta abracar tudo de uma vez perde "
    "o fio e abandona o habito na primeira semana, e recomecar custa mais do "
    "que seguir devagar. Anotar o que ficou pendente ajuda a retomar sem culpa "
    "e sem inventar uma nova regra a cada tropeco do calendario cheio.</p>"
)

#: Um rascunho que PASSA no portão: 700+ palavras, identidade do operador com
#: CNPJ, contato, privacidade, divulgação de monetização e nenhum hyperlink
#: externo. Ele existe para provar que o caminho verde é alcançável — um portão
#: que nada atravessa não é portão, é uma parede com placa.
HTML_LIMPO = (
    "<html><head><title>Rotina de leitura: um guia pratico</title></head><body>"
    "<h1>Rotina de leitura: um guia pratico</h1>"
    + "".join(f"<h2>Etapa {i}</h2>{PARAGRAFO}" for i in range(1, 12))
    + "<footer><p>Editora Exemplo Ltda — CNPJ 12.345.678/0001-90.</p>"
      "<p>Esta pagina exibe publicidade e nao possui vinculo com nenhum orgao "
      "publico.</p>"
      '<p><a href="/sobre/">Sobre</a> · <a href="/contato/">Contato</a> · '
      '<a href="/politica-de-privacidade/">Politica de Privacidade</a></p>'
      "</footer></body></html>"
)

#: O mesmo rascunho com o defeito do incidente: links de órgão público com
#: âncora de valor. Ver `docs/closure/hermes-redator-google-ads-policy-incident-v1`.
HTML_COM_LINK_DE_GOVERNO = HTML_LIMPO.replace(
    "</footer>",
    '</footer><p>Consulte <a href="https://www.caixa.gov.br/beneficio">R$ 2.900</a> '
    'e <a href="https://www.gov.br/liberado">40%</a> agora.</p>',
)


class _SupaFalso:
    """O Supabase, em memória. Guarda o que foi perguntado, para os testes que
    medem QUAL tabela a rota leu — um `select` na tabela errada não dá erro, ele
    devolve vazio, e foi assim que um ramo inteiro desta rota ficou morto."""

    enabled = True

    def __init__(self, tabelas: Dict[str, List[Dict[str, Any]]] | None = None) -> None:
        self.tabelas = tabelas or {}
        self.consultas: List[tuple] = []
        self.patches: List[Dict[str, Any]] = []

    async def select(self, tabela: str, params: Dict[str, Any]):
        self.consultas.append((tabela, params))
        return list(self.tabelas.get(tabela, []))

    async def patch(self, tabela: str, filtro: Dict[str, Any], valores: Dict[str, Any]):
        self.patches.append(valores)
        return []

    async def insert(self, tabela: str, linhas: List[Dict[str, Any]]):
        criado = {"id": 99, **linhas[0]}
        self.tabelas.setdefault(tabela, []).append(criado)
        return [criado]


def _run(**troca) -> Dict[str, Any]:
    base = {
        "id": 1, "opportunity_id": 7, "project_id": 3, "run_id": "rotina-20260903",
        "status": "done", "modo": "publicado", "paginas_publicadas": [],
        "artefatos": {"pasta": "rotina-20260903"},
    }
    base.update(troca)
    return base


def _estado(*, html: str = HTML_LIMPO, formato: str = "gutenberg",
            role: str = "LP", slug: str = "rotina-de-leitura") -> Dict[str, Any]:
    return {
        "run_id": "rotina-20260903",
        "plan": {"pages": [{"page_number": 1, "slug": slug, "role": role,
                            "h1_title": "Rotina de leitura"}]},
        "drafts": {"1": {"page_number": 1, "format": formato, "content": html}},
        "step_status": {"build_p1": {"status": "OK"}},
        "published": {},
    }


PERFIL_WP = {
    "project_id": 3, "wp_url": "https://exemplo.com.br", "wp_username": "volc",
    "wp_app_password_enc": "cifrado", "conexao_ok": True,
    "post_type": "rec", "lp_post_type": "r",
}


@pytest.fixture()
def cliente() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def sentinela(monkeypatch):
    """Troca TUDO que fala com o mundo por uma armadilha.

    ⚠️ São dois níveis de propósito. `worker.publicar_pagina` é o adaptador que a
    rota chama; `asyncio.create_subprocess_exec` é o que REALMENTE escreve no
    WordPress, um nível abaixo. Vigiar só o de cima deixaria passar uma chamada
    que alguém acrescentasse por outro caminho.

    ⚠️ E `montar_perfil` vira dublê AQUI, e não é conveniência: ele decifra a
    senha e explode sem `VOLC_SEGREDO_KEY`. Sem o dublê, um portão ausente
    pararia na falta do cofre e o teste ficaria verde por acidente de ambiente —
    a sentinela nunca seria alcançada, e a prova mediria a máquina, não o código.
    """
    import app.redator as rd
    from app.redator import worker as w

    def armadilha(nome):
        async def nunca(*a, **k):
            pytest.fail(f"{nome} foi chamado — o portão recusou DEPOIS de publicar")
        return nunca

    monkeypatch.setattr(rd, "montar_perfil", lambda **k: {"wordpress": {"url": "x"}})
    monkeypatch.setattr(w, "publicar_pagina", armadilha("worker.publicar_pagina"))
    monkeypatch.setattr(w, "executar", armadilha("worker.executar"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec",
                        armadilha("asyncio.create_subprocess_exec"))


@pytest.fixture()
def mundo(monkeypatch, tmp_path: Path):
    """O run no disco, o Supabase de mentira e o perfil do site."""
    run_dir = tmp_path / "rotina-20260903"
    run_dir.mkdir()

    supa = _SupaFalso({pub.TABELA_RUNS: [_run()]})
    monkeypatch.setattr(pub, "_supa", lambda: supa)
    monkeypatch.setattr(pub, "_pasta_do_run", lambda linha: run_dir)

    async def buscar(_supa, _project_id):
        return dict(PERFIL_WP)

    monkeypatch.setattr(pub, "_buscar", buscar)
    return {"supa": supa, "run_dir": run_dir}


def _gravar_estado(mundo, estado: Dict[str, Any]) -> None:
    (mundo["run_dir"] / "state.json").write_text(
        json.dumps(estado, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 13 — o portão vermelho impede a chamada ao adaptador
# ═══════════════════════════════════════════════════════════════════════════


def test_portao_vermelho_recusa_antes_de_chamar_o_adaptador(
    cliente, mundo, sentinela
):
    """Uma LP com links de governo de âncora numérica não chega ao WordPress.

    É o defeito literal do incidente: sete links `caixa.gov.br` com âncora de
    valor numa página que virou destino de campanha. A sentinela é a parte que
    importa — o 409 sozinho não distingue "recusou" de "publicou e depois
    reclamou".
    """
    _gravar_estado(mundo, _estado(html=HTML_COM_LINK_DE_GOVERNO))

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert "portão de política de destino" in detalhe["erro"]
    assert detalhe["motivos"], "a recusa tem de dizer POR QUE"
    assert detalhe["recibo"]["paid_destination_ready"] is False


def test_a_recusa_deixa_recibo_no_disco(cliente, mundo, sentinela):
    """Recusa sem rastro é indistinguível de publicação que ninguém tentou."""
    _gravar_estado(mundo, _estado(html=HTML_COM_LINK_DE_GOVERNO))

    cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    recibo = mundo["run_dir"] / "p1.landing_policy.recusa.json"
    assert recibo.exists(), sorted(p.name for p in mundo["run_dir"].iterdir())
    gravado = json.loads(recibo.read_text(encoding="utf-8"))
    assert gravado["paid_destination_ready"] is False
    assert gravado["gate_point"] == "pre_publication_wordpress"
    assert gravado["role"] == "paid_destination"


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 8 — evidência que falta não vira verde
# ═══════════════════════════════════════════════════════════════════════════


def test_varredura_que_nao_concluiu_reprova_mesmo_sem_bloqueio(
    cliente, mundo, sentinela, monkeypatch
):
    """O defeito exato do `HANDOFF-PATCH-PUBLICACAO.md`.

    Ele testava `if _avaliacao.bloqueios:`. Aqui a página está LIMPA — nenhum
    bloqueio — e uma varredura exigida explode. Com o predicado do handoff isto
    publicaria; com `paid_destination_ready`, não publica, porque
    "não consegui olhar" não é "olhei e está limpo".
    """
    from app.landing_policy import varredura as vd

    def explode(_pagina):
        raise RuntimeError("o parser morreu no meio")

    monkeypatch.setitem(vd.VARREDURAS, "identity", explode)
    _gravar_estado(mundo, _estado(html=HTML_LIMPO))

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert not detalhe["recibo"]["blockers"], "o cenário exige página SEM bloqueio"
    assert detalhe["recibo"]["unknowns"], "o desconhecido tem de estar no recibo"
    assert any("identity" in m for m in detalhe["motivos"]), detalhe["motivos"]


def test_artefato_ilegivel_nao_vira_pagina_limpa(cliente, mundo, sentinela):
    """A LP é publicada a partir do Elementor, não do `content` do rascunho.

    `state.drafts[1].format == "lp_json"` significa que o `content` é JSON e que
    o que vai ao ar está em `p1.elementor.json` — cuja projeção legível é o
    `p1.preview.html`. Sem esse arquivo não há o que ler, e não ler nunca pode
    valer como leitura limpa.
    """
    _gravar_estado(mundo, _estado(html='{"article_title": "Rotina"}',
                                  formato="lp_json"))

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 409, r.text
    motivos = r.json()["detail"]["motivos"]
    assert any("preview.html" in m for m in motivos), motivos


def test_a_lp_e_lida_do_preview_quando_o_rascunho_e_json(
    cliente, mundo, monkeypatch
):
    """E quando o `preview.html` existe, é ELE que o portão lê."""
    _gravar_estado(mundo, _estado(html='{"article_title": "Rotina"}',
                                  formato="lp_json"))
    (mundo["run_dir"] / "p1.preview.html").write_text(HTML_LIMPO, encoding="utf-8")
    _liberar_o_resto(monkeypatch)

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 200, r.text
    assert "p1.preview.html" in r.json()["recibo"]["evidence_refs"]


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 14 — a publicação aceita gera recibo e impressão
# ═══════════════════════════════════════════════════════════════════════════


def _liberar_o_resto(monkeypatch, resultado: Dict[str, Any] | None = None) -> Dict:
    """Tudo DEPOIS do portão vira dublê: perfil montado e adaptador de mentira.

    O que se mede aqui é o portão. `montar_perfil` decifraria a senha (precisa do
    cofre) e `publicar_pagina` falaria com o motor — nenhum dos dois é o assunto,
    e os dois trariam ambiente para dentro de um teste hermético.
    """
    import app.redator as rd
    from app.redator import worker as w

    capturado: Dict[str, Any] = {}
    monkeypatch.setattr(rd, "montar_perfil", lambda **k: {"wordpress": {"url": "x"}})

    async def publica(**kwargs):
        capturado.update(kwargs)
        return resultado if resultado is not None else {
            "ok": True,
            "publicada": {"page_number": 1, "post_id": 4242, "status_wp": "draft",
                          "url_wp": "https://exemplo.com.br/?post_type=r&p=4242"},
        }

    monkeypatch.setattr(w, "publicar_pagina", publica)
    return capturado


def test_publicacao_aceita_gera_recibo_com_hash_e_impressao(
    cliente, mundo, monkeypatch
):
    """O caminho verde existe, e ele deixa recibo — com as DUAS provas.

    O `content_sha256` prova igualdade byte a byte; a `content_fingerprint` é a
    projeção estrutural, que é quem decide deriva depois. Um recibo com só o byte
    chamaria de deriva um espaço em branco trocado pelo tema.
    """
    from app.landing_policy import impressao_canonica

    _gravar_estado(mundo, _estado(html=HTML_LIMPO))
    _liberar_o_resto(monkeypatch)

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is True
    recibo = corpo["recibo"]
    assert recibo["paid_destination_ready"] is True
    assert recibo["role"] == "paid_destination"
    assert len(recibo["content_sha256"]) == 64
    assert recibo["content_fingerprint"] == impressao_canonica(HTML_LIMPO)
    # Datável: sem epoch, frescor vira comparação de string de data — que é
    # como o frescor deixa de valer.
    assert recibo["observed_at_epoch"] > 0
    assert recibo["policy_contract_version"] == "paid_destination_policy_spine.v2"

    gravado = mundo["run_dir"] / "p1.landing_policy.json"
    assert gravado.exists(), sorted(p.name for p in mundo["run_dir"].iterdir())


def test_a_publicacao_so_e_disparada_com_a_autorizacao_do_portao(
    cliente, mundo, monkeypatch
):
    """A rota entrega ao worker a IMPRESSÃO do recibo, não um booleano.

    Um booleano diria "alguém autorizou"; a impressão diz QUAL avaliação
    autorizou, e é ela que o `_disparar_motor` exige para montar `--publish`.
    """
    from app.landing_policy import impressao_do_recibo

    _gravar_estado(mundo, _estado(html=HTML_LIMPO))
    capturado = _liberar_o_resto(monkeypatch)

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 200, r.text
    autorizacao = capturado["autorizacao"]
    assert autorizacao.startswith("portao_de_publicacao:p1:")
    assert autorizacao.endswith(impressao_do_recibo(r.json()["recibo"]))


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 24 — o cliente não relaxa o papel
# ═══════════════════════════════════════════════════════════════════════════


def test_papel_frouxo_gravado_no_estado_nao_rebaixa_a_lp(
    cliente, mundo, sentinela
):
    """`role: "organic_article"` na página 1 não vira papel frouxo.

    O contrato traduz papel do motor DESCONHECIDO para `organic_article` — o mais
    frouxo de todos. Se o backend repassasse qualquer string, bastaria gravar
    lixo no `state.json` para desligar a régua. O slug decide, como no motor.
    """
    _gravar_estado(mundo, _estado(html=HTML_COM_LINK_DE_GOVERNO,
                                  role="organic_article"))

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["recibo"]["role"] == "paid_destination"


def test_o_papel_do_motor_e_sanitizado_e_cai_no_slug():
    """A unidade da regra acima, sem HTTP."""
    from app.redator import politica_de_destino as pol

    assert pol.papel_do_motor_no_disco({"role": "organic_article",
                                        "slug": "rotina-de-leitura"}) == "LP"
    assert pol.papel_do_motor_no_disco({"role": "", "slug": "rotina-p3"}) == "SOLUTION"
    assert pol.papel_do_motor_no_disco({"role": "", "slug": "rotina-pr"}) == "PRESELL"
    assert pol.papel_do_motor_no_disco({"role": "SOLUTION",
                                        "slug": "rotina"}) == "SOLUTION"


def test_pagina_interior_publica_com_o_achado_registrado(
    cliente, mundo, monkeypatch
):
    """A régua do destino pago é do destino pago.

    Uma interior não recebe clique comprado; medi-la com a régua da LP seria
    reprovar por um risco que ela não corre. O achado continua no recibo — ele
    muda de PESO, não some.
    """
    _gravar_estado(mundo, _estado(html=HTML_COM_LINK_DE_GOVERNO,
                                  role="SOLUTION", slug="rotina-p3"))
    _liberar_o_resto(monkeypatch)

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 200, r.text
    recibo = r.json()["recibo"]
    assert recibo["role"] == "editorial_solution"
    assert recibo["risks"], "o achado tem de continuar registrado"


# ═══════════════════════════════════════════════════════════════════════════
# A OUTRA PORTA — /redator/disparar
# ═══════════════════════════════════════════════════════════════════════════


CARD_LIMPO = {
    "id": 7, "status": "ready", "entity_id": None,
    "funnel_architecture": {"pages": [
        {"page_number": 1, "page_type": "LANDING PAGE",
         "h1_title": "Rotina de leitura: um guia pratico",
         "slug": "rotina-de-leitura",
         "main_content_structure": ["H2: Por onde comecar"],
         "hook_to_next_page": "Veja o passo a passo",
         "next_page_slug": "rotina-de-leitura-p2"},
    ]},
}


def _card(**troca_da_pagina) -> Dict[str, Any]:
    pagina = {**CARD_LIMPO["funnel_architecture"]["pages"][0], **troca_da_pagina}
    return {**CARD_LIMPO, "funnel_architecture": {"pages": [pagina]}}


@pytest.fixture()
def mundo_do_disparo(monkeypatch):
    supa = _SupaFalso({
        "pautador_entity_opportunities": [_card()],
        pub.TABELA_RUNS: [],
    })
    monkeypatch.setattr(pub, "_supa", lambda: supa)

    async def buscar(_supa, _project_id):
        return dict(PERFIL_WP)

    monkeypatch.setattr(pub, "_buscar", buscar)
    return supa


def test_o_disparo_recusa_o_plano_que_ja_nasce_reprovado(
    cliente, mundo_do_disparo, sentinela
):
    """O H1 do incidente, barrado ANTES de gastar ~US$ 2 e ~45 min.

    "Saque-Aniversário FGTS Liberado pelo Governo" é a manchete literal do
    artefato preservado. Ela é decidível no PLANO: nenhuma redação posterior
    desfaz uma manchete que diz que o governo liberou algo.
    """
    mundo_do_disparo.tabelas["pautador_entity_opportunities"] = [
        _card(h1_title="Saque-Aniversario FGTS Liberado pelo Governo")]

    r = cliente.post("/api/publicacao/redator/disparar",
                     json={"opportunity_id": 7, "project_id": 3})

    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert any("TITULO_SUGERE_ORIGEM_OFICIAL" in m for m in detalhe["motivos"]), detalhe
    # E nenhum run foi criado: recusar depois de gravar a linha deixaria um run
    # fantasma segurando o par (card, site) contra a próxima tentativa.
    assert not mundo_do_disparo.tabelas.get(pub.TABELA_RUNS)


def test_o_disparo_recusa_papel_mais_frouxo_pedido_no_card(
    cliente, mundo_do_disparo, sentinela
):
    """`funnel_architecture` é dado gravável pela API.

    Um `role` mais frouxo dentro do card é uma tentativa de baixar a régua pela
    borda — o servidor é a autoridade do papel, e a tentativa vira recusa em vez
    de virar papel aceito.
    """
    mundo_do_disparo.tabelas["pautador_entity_opportunities"] = [
        _card(role="organic_article")]

    r = cliente.post("/api/publicacao/redator/disparar",
                     json={"opportunity_id": 7, "project_id": 3})

    assert r.status_code == 409, r.text
    motivos = " ".join(r.json()["detail"]["motivos"])
    assert "mais frouxo" in motivos, motivos


def test_o_disparo_limpo_passa_e_leva_a_autorizacao_do_plano(
    cliente, mundo_do_disparo, monkeypatch
):
    """O plano sem defeito decidível segue — com a autorização na mão.

    ⚠️ E o que este portão NÃO faz aparece aqui: o plano limpo passa mesmo sem
    identidade, sem 600 palavras e sem divulgação de monetização, porque nada
    disso existe antes de o corpo ser escrito. Quem decide esses é o portão do
    motor, com o artefato pronto.
    """
    from app.redator import worker as w

    capturado: Dict[str, Any] = {}

    async def executar(**kwargs):
        capturado.update(kwargs)

    import app.redator as rd

    monkeypatch.setattr(w, "executar", executar)
    monkeypatch.setattr(rd, "montar_perfil", lambda **k: {"wordpress": {"url": "x"}})

    r = cliente.post("/api/publicacao/redator/disparar",
                     json={"opportunity_id": 7, "project_id": 3})

    assert r.status_code == 200, r.text
    assert r.json()["motor_conectado"] is True
    # A task de segundo plano precisa de uma volta do loop para rodar.
    assert capturado.get("publicar") is True
    assert str(capturado.get("autorizacao", "")).startswith("portao_do_plano:card:")


def test_o_disparo_pede_a_coluna_que_ele_le(cliente, mundo_do_disparo, sentinela):
    """`entity_id` tem de estar no `select`.

    PostgREST devolve SÓ as colunas pedidas. Sem `entity_id` no `select`, o
    `if opps[0].get("entity_id")` da rota é falso mesmo com a entidade existindo
    — a entidade nunca era carregada, e o tema do run perdia termos e canal
    oficial sem erro nenhum.
    """
    mundo_do_disparo.tabelas["pautador_entity_opportunities"] = [
        _card(h1_title="Saque-Aniversario FGTS Liberado pelo Governo")]

    cliente.post("/api/publicacao/redator/disparar",
                 json={"opportunity_id": 7, "project_id": 3})

    pedido = next(p for t, p in mundo_do_disparo.consultas
                  if t == "pautador_entity_opportunities")
    assert "entity_id" in pedido["select"], pedido


# ═══════════════════════════════════════════════════════════════════════════
# UM ÚNICO PONTO DE DISPARO COM --publish
# ═══════════════════════════════════════════════════════════════════════════


def test_publish_tem_um_dono_so_no_worker():
    """`--publish` aparece uma vez no arquivo, dentro de `_disparar_motor`.

    Enquanto ele era montado em dois lugares independentes, um portão numa porta
    deixava a outra aberta — que é exatamente como o `/disparar` ficou de fora do
    patch de handoff.
    """
    import inspect

    from app.redator import worker as w

    fonte = inspect.getsource(w)
    assert fonte.count('"--publish"') == 1, "há mais de um lugar montando --publish"
    assert '"--publish"' in inspect.getsource(w._disparar_motor)
    # As duas portas passam pelo helper, e nenhuma monta o comando por conta.
    for funcao in (w.executar, w.publicar_pagina):
        corpo = inspect.getsource(funcao)
        assert "_disparar_motor(" in corpo, funcao.__name__
        assert "create_subprocess_exec" not in corpo, funcao.__name__


def test_publicar_sem_autorizacao_nao_chega_a_criar_processo(monkeypatch, tmp_path):
    """Fecha por ausência: `--publish` sem portão levanta, e nada é disparado."""
    from app.redator import worker as w

    monkeypatch.setattr(w, "_executavel", lambda: tmp_path / "funnelforge")

    async def nunca(*a, **k):
        pytest.fail("um processo foi criado sem autorização de portão")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", nunca)

    with pytest.raises(w.PublicacaoSemPortao):
        asyncio.run(w._disparar_motor(
            raiz=tmp_path, argumentos=["resume", "x"], publicar=True,
            autorizacao=""))


def test_sem_publicar_o_comando_nao_ganha_a_flag(monkeypatch, tmp_path):
    """E o caminho que NÃO publica continua funcionando sem autorização nenhuma —
    rodar o funil sem publicar não escreve em site nenhum."""
    from app.redator import worker as w

    monkeypatch.setattr(w, "_executavel", lambda: tmp_path / "funnelforge")
    capturado: Dict[str, Any] = {}

    async def falso(*cmd, **k):
        capturado["cmd"] = list(cmd)
        return object()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", falso)

    asyncio.run(w._disparar_motor(raiz=tmp_path, argumentos=["run-volc", "a.json"],
                                  publicar=False))

    assert "--publish" not in capturado["cmd"], capturado["cmd"]


# ═══════════════════════════════════════════════════════════════════════════
# UMA PUBLICAÇÃO QUE FALHA NÃO DEVOLVE 200
# ═══════════════════════════════════════════════════════════════════════════


def test_publicacao_que_falha_nao_sai_com_200(cliente, mundo, monkeypatch):
    """`ok: false` dentro de um 200 é lido como sucesso por quem ramifica por
    status — inclusive por um retry que só olha `resp.ok` e tentaria de novo
    achando que a primeira tinha dado certo."""
    _gravar_estado(mundo, _estado(html=HTML_LIMPO))
    _liberar_o_resto(monkeypatch, resultado={"ok": False, "erro": "401 do WordPress"})

    r = cliente.post("/api/publicacao/redator/runs/1/publicar/1")

    assert r.status_code == 502, r.text
    detalhe = r.json()["detail"]
    assert detalhe["ok"] is False
    assert "401" in detalhe["erro"]
    # O corpo continua informativo: o recibo do portão viaja com a falha, senão
    # a única prova de que a página FOI avaliada morre com a requisição.
    assert detalhe["recibo"]["paid_destination_ready"] is True
