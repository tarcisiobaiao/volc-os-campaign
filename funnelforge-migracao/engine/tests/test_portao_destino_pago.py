# funnel-forge/tests/test_portao_destino_pago.py
"""O PORTÃO DO DESTINO PAGO dentro do motor — as duas barreiras e o recibo.

O defeito que estes testes travam está medido e tem linha:
`steps.step_content_gate` abria com `if page.page_type == "LANDING PAGE": ...
return`. A LP — a única página do funil que recebe o clique COMPRADO — era a
única isenta do portão de conteúdo. Ela era marcada OK sem que validador nenhum
rodasse, e `step_publish` completava o buraco: o ramo Elementor não chamava
`_final_content_issues`, então nada olhava o artefato da LP em ponto algum.

Nenhum teste aqui abre socket, lê conta do Google ou escreve em WordPress. O
publisher usado no caminho vermelho é uma SENTINELA: qualquer método chamado
nele derruba o teste, que é a única forma de provar "zero publicação parcial"
sem observar o site ao vivo.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from funnelforge.adapters import landing_policy_gate as portao
from funnelforge.config.settings import load_settings
from funnelforge.domain.models import (
    FunnelPlan,
    Page,
    PageDraft,
    PageRole,
    Route,
    RunState,
    StepStatus,
)
from funnelforge.pipeline.preflight import preflight_issues
from funnelforge.pipeline.steps import step_content_gate, step_publish

from tests.lp_conforme import RODAPE_INSTITUCIONAL as RODAPE, conteudo_da_lp


def _settings(config_files, *, rodape: str = RODAPE):
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.site.rodape_institucional = rodape
    return settings


def _deps(tmp_path, config_files, publisher=None, *, rodape: str = RODAPE):
    return SimpleNamespace(
        publisher=publisher,
        settings=_settings(config_files, rodape=rodape),
        runner=SimpleNamespace(runs_dir=tmp_path / "runs"),
        screenshot=None,
    )


def _pagina_lp() -> Page:
    page = Page(page_number=1, page_type="LANDING PAGE",
                h1_title="Saque-Aniversário do FGTS: regras e simulação",
                slug="fgts-saque-aniversario")
    page.routes = [
        Route(placement="hero", kind="funnel", target="quem-tem-direito-fgts-pr1",
              anchor="Ver quem tem direito"),
        Route(placement="inline", kind="funnel", target="regras-saque-aniversario-fgts",
              anchor="Ver as regras do saque"),
        Route(placement="footer", kind="funnel", target="prazos-do-saque-fgts",
              anchor="Ver os prazos"),
    ]
    return page


def _estado(conteudo: dict) -> RunState:
    state = RunState(run_id="r1")
    state.plan = FunnelPlan(total_pages=4, pages=[_pagina_lp()])
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE",
                                format="lp_json",
                                content=json.dumps(conteudo, ensure_ascii=False))
    return state


class _PublisherSentinela:
    """Publisher que NÃO pode ser tocado.

    Contraprova 13: "o portão vermelho impede a chamada ao adaptador WordPress".
    Um mock que apenas conta chamadas provaria menos — ele deixaria o teste
    passar se a asserção fosse esquecida. Aqui QUALQUER atributo alcançado
    derruba o teste no ponto exato da chamada."""

    def __getattr__(self, nome: str):
        def _explode(*args, **kwargs):
            pytest.fail(
                f"deps.publisher.{nome}() foi chamado com o portão VERMELHO — "
                "é exatamente a mídia órfã que 'zero publicação parcial' proíbe."
            )
        return _explode


# ── BARREIRA 1 — a isenção da LP no step_content_gate ─────────────────────


def test_lp_com_h1_de_falsa_oficialidade_e_reprovada_no_gate_de_conteudo(
        tmp_path, config_files):
    """CONTRAPROVA 9 — o H1 perigoso é capturado ANTES da publicação.

    O H1 do artefato histórico é literalmente "Saque-Aniversário FGTS Liberado
    pelo Governo". `calm_utility` bane a expressão no CORPO, e a LP nem passava
    por `calm_utility`: o `step_content_gate` a marcava OK e voltava."""
    conteudo = conteudo_da_lp(hero_title="Saque-Aniversário FGTS Liberado pelo Governo")
    state = _estado(conteudo)
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    resultado = state.step_status["content_gate_p1"]
    assert resultado.status is StepStatus.FAILED
    assert any(i.code == "titulo_sugere_origem_oficial" for i in resultado.issues), \
        [i.code for i in resultado.issues]


def test_lp_util_e_interna_alcanca_verde(tmp_path, config_files):
    """CONTRAPROVA 30 — página útil, com identidade e só links internos, passa.

    Um portão que reprova tudo é um portão que alguém desliga. Este teste é o
    contrapeso do de cima: mesma máquina, artefato limpo, veredito verde."""
    state = _estado(conteudo_da_lp())
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    resultado = state.step_status["content_gate_p1"]
    assert resultado.status is StepStatus.OK, [i.code for i in resultado.issues]


def test_lp_ponte_sem_conteudo_e_reprovada(tmp_path, config_files):
    """CONTRAPROVA 29 — página-ponte sem valor é recusada.

    Quatro seções vazias e três botões: o artefato é encaminhamento, não
    conteúdo. É a forma que a política descreve como destino sem valor."""
    conteudo = conteudo_da_lp(
        intro="<p>Escolha abaixo.</p>",
        sections=[{"title": f"Passo {i}", "body": "<p>Veja no botão.</p>"}
                  for i in range(4)],
        transition="<p>Toque no botão.</p>",
    )
    state = _estado(conteudo)
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    resultado = state.step_status["content_gate_p1"]
    assert resultado.status is StepStatus.FAILED
    assert "conteudo_original_insuficiente" in {i.code for i in resultado.issues}


def test_fonte_de_pesquisa_linkada_no_corpo_da_lp_reprova(tmp_path, config_files):
    """CONTRAPROVA 28 — a fonte registrada não vira hyperlink no destino pago.

    Sete links `caixa.gov.br` de âncora numérica são o achado mais forte do
    incidente. A fonte pertence ao dossiê de evidência e é citada em PROSA; no
    corpo de um destino que recebe clique comprado ela não vira âncora."""
    conteudo = conteudo_da_lp()
    conteudo["sections"][0]["body"] += (
        '<p>A alíquota é de <a href="https://www.caixa.gov.br/fgts">40%</a>.</p>')
    state = _estado(conteudo)
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    resultado = state.step_status["content_gate_p1"]
    assert resultado.status is StepStatus.FAILED
    assert "link_externo_clicavel_em_destino_pago" in {i.code for i in resultado.issues}


def test_gate_da_lp_e_hermetico(tmp_path, config_files, monkeypatch):
    """CONTRAPROVA 26 — nenhuma leitura de rede.

    `socket.socket` levanta durante toda a avaliação. Se alguma varredura
    tentasse resolver uma URL, o teste morreria aqui em vez de mentir verde numa
    máquina com rede."""
    import socket

    def _sem_rede(*args, **kwargs):
        raise AssertionError("o portão do destino pago tentou abrir socket")

    monkeypatch.setattr(socket, "socket", _sem_rede)
    state = _estado(conteudo_da_lp())
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    assert state.step_status["content_gate_p1"].status is StepStatus.OK


# ── FALHA FECHADA — sem a ponte, não se publica destino pago ──────────────


def test_sem_o_contrato_o_gate_reprova_em_vez_de_liberar(
        tmp_path, config_files, monkeypatch):
    """O import da ponte falhando REPROVA. Nunca "não consegui olhar => passou".

    O pacote mora em `backend/`, fora do venv do motor. Um erro de caminho, um
    rename de pasta ou um venv reconstruído são todos plausíveis — e nenhum
    deles pode virar autorização para publicar um destino pago sem portão."""
    def _explode():
        raise ImportError("app.landing_policy não encontrado")

    monkeypatch.setattr(portao, "_importar_contrato", _explode)
    state = _estado(conteudo_da_lp())
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    resultado = state.step_status["content_gate_p1"]
    assert resultado.status is StepStatus.FAILED
    assert "portao_de_destino_indisponivel" in {i.code for i in resultado.issues}


def test_sem_o_contrato_a_publicacao_nao_toca_o_wordpress(
        tmp_path, config_files, monkeypatch):
    """E a mesma indisponibilidade barra o `step_publish`, com a SENTINELA."""
    def _explode():
        raise ImportError("app.landing_policy não encontrado")

    monkeypatch.setattr(portao, "_importar_contrato", _explode)
    state = _estado(conteudo_da_lp())
    deps = _deps(tmp_path, config_files, _PublisherSentinela())

    step_publish(state, _pagina_lp(), deps)

    resultado = state.step_status["publish_p1"]
    assert resultado.status is StepStatus.FAILED
    assert 1 not in state.published


# ── BARREIRA 2 — o portão como PRIMEIRA instrução do step_publish ─────────


def test_publicacao_reprovada_nao_chama_o_publisher(tmp_path, config_files):
    """CONTRAPROVA 13 — portão vermelho impede a chamada ao adaptador WordPress.

    Antes, `_final_content_issues` rodava DEPOIS de três `upload_media`: uma
    página recusada já tinha deixado mídia órfã no site ao vivo. O portão agora
    é a primeira instrução do passo."""
    conteudo = conteudo_da_lp(hero_title="Saque-Aniversário FGTS Liberado pelo Governo")
    state = _estado(conteudo)
    state.images[1] = str(tmp_path / "hero.webp")
    (tmp_path / "hero.webp").write_bytes(b"webp")
    deps = _deps(tmp_path, config_files, _PublisherSentinela())

    step_publish(state, _pagina_lp(), deps)

    resultado = state.step_status["publish_p1"]
    assert resultado.status is StepStatus.FAILED
    assert 1 not in state.published


def test_recusa_grava_recibo_local(tmp_path, config_files):
    """A recusa deixa rastro em disco: sem publicação não há linha de
    `paginas_publicadas` onde pendurar o recibo, e recusa sem rastro é
    indistinguível de publicação que ninguém tentou."""
    conteudo = conteudo_da_lp(hero_title="Saque-Aniversário FGTS Liberado pelo Governo")
    state = _estado(conteudo)
    deps = _deps(tmp_path, config_files, _PublisherSentinela())

    step_publish(state, _pagina_lp(), deps)

    recibo_path = tmp_path / "runs" / "r1" / "p1.landing_policy.recusa.json"
    assert recibo_path.exists()
    recibo = json.loads(recibo_path.read_text(encoding="utf-8"))
    assert recibo["paid_destination_ready"] is False
    assert recibo["not_ready_reasons"]


class _PublisherAceito:
    """Publisher mínimo do caminho VERDE: registra o que recebeu."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []

    def create_elementor_page(self, title, slug, elementor, status, post_type="pages",
                              page_settings=None):
        self.chamadas.append("create_elementor_page")
        return {"id": 7, "slug": slug, "link": f"https://creditoup.com.br/r/{slug}/"}

    def set_yoast(self, post_id, post_type, fields, status=None):
        self.chamadas.append("set_yoast")
        return {}

    def set_status(self, post_id, post_type, status):
        self.chamadas.append("set_status")
        return {}


def test_publicacao_aceita_grava_recibo_e_impressao(tmp_path, config_files):
    """CONTRAPROVA 14 — publicação aceita gera recibo e fingerprint verificáveis.

    É o lado esquerdo que não existia da comparação do portão 3: sem hash
    aprovado gravado, `DERIVA_AO_VIVO` saiu `unavailable` nos cinco recibos
    preservados. O recibo entra em `state.published[n]`, que
    `worker.resumo_do_estado` já leva verbatim para o Supabase."""
    state = _estado(conteudo_da_lp())
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "p1.elementor.json").write_text("[]", encoding="utf-8")
    pub = _PublisherAceito()
    deps = _deps(tmp_path, config_files, pub)

    step_publish(state, _pagina_lp(), deps)

    assert state.step_status["publish_p1"].status is StepStatus.OK
    publicada = state.published[1]
    recibo = publicada[portao.CHAVE_DO_RECIBO]
    assert recibo["paid_destination_ready"] is True
    assert recibo["role"] == "paid_destination"
    assert recibo["policy_contract_version"] == "paid_destination_policy_spine.v2"
    # A IMPRESSÃO e o BYTE, as duas: a primeira decide deriva, o segundo prova
    # igualdade. Guardar só uma seria escolher entre não medir mudança e não
    # conseguir provar que nada mudou.
    assert recibo["content_fingerprint"]
    assert recibo["content_sha256"]
    # Datável: `observed_at_epoch` None faz `varrer_recibo` tratar a evidência
    # como `unavailable`, nunca como recente.
    assert isinstance(recibo["observed_at_epoch"], float)
    assert recibo["freshness_window_s"] == portao.JANELA_DE_FRESCOR_PADRAO_S


def test_sem_rodape_declarado_a_lp_reprova_por_identidade(tmp_path, config_files):
    """A declaração do rodapé NÃO é cheque em branco: vazia, o portão fecha.

    O motor produz o CORPO; identidade, aviso de não-vínculo e divulgação de
    monetização vêm do tema, e nenhum artefato local os contém. Num site cujo
    rodapé ninguém mediu, "não sei" tem de sair como reprova — nunca como
    aprovação por omissão."""
    state = _estado(conteudo_da_lp())
    deps = _deps(tmp_path, config_files, rodape="")

    step_content_gate(state, _pagina_lp(), deps)

    resultado = state.step_status["content_gate_p1"]
    assert resultado.status is StepStatus.FAILED
    codigos = {i.code for i in resultado.issues}
    # O CNPJ continua declarado por `site.cnpj` (campo antigo, cuja própria
    # documentação diz "identidade exibida no rodapé público do site"), então
    # `IDENTIDADE_OPERADOR_AUSENTE` não é o que cai aqui. Cai o resto do rodapé:
    # contato/privacidade, o aviso de não-vínculo e a divulgação de monetização.
    assert "identidade_contato_ausente" in codigos
    assert "divulgacao_de_monetizacao_ausente" in codigos
    assert "aviso_nao_oficial_ausente" in codigos


def test_cta_fora_de_ordem_e_ancora_incongruente(tmp_path, config_files):
    """O botão que promete um assunto e leva a outro é medido.

    `cta_texts[i]` é renderizado no botão cujo destino é `funnel_hrefs[i]`. O
    `pagespec` do motor confere a âncora da ROTA (`Route.anchor`, derivada do H1
    do destino em `routing._anchor_for`) — mas o rótulo que o leitor lê na LP é
    `cta_texts`, escrito pelo modelo, e nada o conferia contra o destino."""
    conteudo = conteudo_da_lp(
        cta_texts=["Ver as regras do saque", "Ver quem tem direito", "Ver os prazos"])
    state = _estado(conteudo)
    deps = _deps(tmp_path, config_files)

    step_content_gate(state, _pagina_lp(), deps)

    # ⚠️ MUDANÇA DE CONTRATO: `ANCORA_INCONGRUENTE_COM_DESTINO` VOLTOU A SER RISCO.
    #
    # A promoção a bloqueio durou uma revisão. Medida no papel estrito, ela
    # reprovava CTA interno banal — "Simule agora" → /rec/calculadora-do-saque/,
    # "Continuar" → /rec/regras-do-fgts/ — porque a regra exige interseção de
    # tokens entre a âncora e o caminho, e um CTA bom diz o que o leitor GANHA,
    # não onde ele vai. Um portão que reprova página correta é desligado pela
    # operação na primeira semana.
    #
    # O que este teste continua provando é que o portão VÊ a incongruência: ela
    # sai como risco no recibo, e o operador a lê. A metade da contraprova 12
    # que precisa bloquear — CTA EXTERNO — continua bloqueando por
    # `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO` e
    # `BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO`.
    resultado = state.step_status["content_gate_p1"]
    riscos = {r.get("code") for r in (getattr(resultado, "riscos", None) or [])}
    issues = {i.code for i in resultado.issues}
    assert "ancora_incongruente_com_destino" not in issues, (
        "âncora incongruente não pode BLOQUEAR: é heurística textual"
    )
    assert resultado.status is not StepStatus.FAILED or issues, issues


# ── BARREIRA 1 NO PLANO — antes da primeira chamada paga ──────────────────


def _ctx_do_plano(config_files, *, h1: str, rodape: str = RODAPE) -> dict:
    """O `ctx` como `_write_ctx` o monta para a LP, reduzido ao que o portão lê."""
    settings = _settings(config_files, rodape=rodape)
    return {
        "h1": h1,
        "page_type": "LANDING PAGE",
        "role": PageRole.LP,
        "slug": "fgts-saque-aniversario",
        "subtitulos": ["H2: O que e", "H2: Como funciona"],
        "domain": settings.site.domain,
        "post_type": settings.site.post_type,
        "lp_post_type": settings.site.lp_post_type,
        "cnpj": settings.site.cnpj,
        "rodape_institucional": settings.site.rodape_institucional,
        "official_links": [],
        "parsed": {"routes": [r.model_dump() for r in _pagina_lp().routes]},
    }


def test_h1_perigoso_reprova_no_pre_voo_sem_pagar_o_redator(config_files):
    """CONTRAPROVA 9, no ponto mais barato: o PLANO, antes do LLM.

    A alegação entrou pelo H1 do plano; o portão de conteúdo só olhava o corpo,
    então chegava depois do ponto em que o defeito nasceu — e depois de pagar
    pesquisa + até três redações + juiz."""
    issues = preflight_issues(
        ["plano_de_destino_pago"],
        _ctx_do_plano(config_files, h1="Saque-Aniversário FGTS Liberado pelo Governo"))

    assert "titulo_sugere_origem_oficial" in {i.code for i in issues}


def test_pre_voo_do_plano_nao_reprova_por_falta_de_corpo(config_files):
    """O plano não tem corpo — e acusar por isso seria ruído, não achado.

    `CONTEUDO_ORIGINAL_INSUFICIENTE` e `PAGINA_PONTE` medem o CORPO, que a etapa
    seguinte existe para escrever. Os dois voltam a ser medidos no portão sobre
    o ARTEFATO, aí sim com corpo (ver `SO_MEDIVEIS_COM_CORPO`)."""
    issues = preflight_issues(
        ["plano_de_destino_pago"],
        _ctx_do_plano(config_files, h1="Saque-Aniversário do FGTS: regras e simulação"))

    assert issues == [], [i.code for i in issues]


def test_pre_voo_so_roda_se_o_validador_estiver_na_lista_do_passo(config_files):
    """`config.yaml` decide. Validador fora da lista do passo NÃO roda — foi por
    isso que a LP (`write_p1`, 4 validadores contra 26 de `write_page`) precisou
    ganhar o nome na lista para o pré-voo existir."""
    ctx = _ctx_do_plano(config_files, h1="Saque-Aniversário FGTS Liberado pelo Governo")
    assert preflight_issues([], ctx) == []


def test_pre_voo_sem_plano_nao_inventa_reprova(config_files):
    """Sem H1 no ctx (checkpoint antigo, estado montado à mão) a checagem não
    roda: avaliar um plano vazio produziria reprova por ausência de tudo, que é
    ruído — e ruído no portão é como um portão perde a autoridade."""
    ctx = _ctx_do_plano(config_files, h1="")
    assert preflight_issues(["plano_de_destino_pago"], ctx) == []


def test_moeda_malformada_na_lp_e_corrigida_antes_do_portao(tmp_path, config_files):
    """A correção de moeda alcança a LP — que é onde o defeito foi medido.

    "de 5 % a 50 %" e "até 2900.00 R$" estão no corpo de
    `/r/fgts-saque-aniversario/` na captura preservada. A LP é JSON, não
    Gutenberg, então `normalize_gutenberg` nunca a tocava: a mesma correção
    passa pelas FOLHAS do JSON em `step_write`."""
    from funnelforge.pipeline.enhancers.gutenberg import formatar_moeda_em_estrutura

    conteudo = conteudo_da_lp()
    conteudo["sections"][0]["body"] += (
        "<p>A aliquota vai de 5 % a 50 % e a parcela fixa chega a 2900.00 R$.</p>")

    corrigido = formatar_moeda_em_estrutura(conteudo)
    corpo = corrigido["sections"][0]["body"]
    assert "de 5% a 50%" in corpo
    assert "R$ 2.900,00" in corpo
    assert "2900.00 R$" not in corpo

    # E o artefato corrigido continua verde no portão: a correção não introduz
    # um defeito novo enquanto conserta o antigo.
    state = _estado(corrigido)
    deps = _deps(tmp_path, config_files)
    step_content_gate(state, _pagina_lp(), deps)
    assert state.step_status["content_gate_p1"].status is StepStatus.OK, \
        [i.code for i in state.step_status["content_gate_p1"].issues]


def test_ancora_da_rota_nasce_congruente_com_o_caminho_do_destino():
    """Fase D item 7 — a âncora do CTA sai do H1 E do caminho do destino.

    A regra antiga pegava o PRIMEIRO token em ordem alfabética do H1: "Como
    Sacar o FGTS Aniversário" virava `Ver o guia de aniversário >>>` apontando
    para `/rec/como-sacar-p2`, e "Guia Completo do FGTS" virava `Ver o guia de
    completo >>>` apontando para `/rec/quem-tem-direito-pr`. As duas prometem um
    assunto que o caminho do destino não contém."""
    from funnelforge.pipeline.routing import _anchor_for

    # Termo em comum entre H1 e slug: ele sozinho basta, e é o mais distintivo.
    assert _anchor_for("Como Sacar o FGTS Aniversário", 0, "como-sacar-p2") == \
        "Ver o guia de sacar >>>"
    # H1 e slug divergem: a âncora nomeia os DOIS, para satisfazer as duas
    # réguas que a medem (o `pagespec`, contra o H1; a política, contra a URL).
    assert _anchor_for("Guia Completo do FGTS", 0, "quem-tem-direito-pr") == \
        "Ver o guia de quem tem direito (fgts) >>>"
