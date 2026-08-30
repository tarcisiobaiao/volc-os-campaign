"""As rotas do Hub de Tráfego.

Roda contra o Supabase real (leitura) e contra a conta real via `validate_only`
(que é leitura: a API valida o payload e descarta, sem criar nada).

⚠️ NENHUM teste aqui abre a trava de escrita. `subir()` exige `destravar()` no
código E `FORGE_PERMITIR_ESCRITA=1` no ambiente; os testes provam que a rota
RECUSA, nunca que ela escreve.

As asserções são sobre INVARIANTES, não sobre a contagem do dia: "nenhum CPC sai
sem procedência" continua verdade amanhã; "23 keywords" não.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ⚠️ Sem isto, estes testes PULAM na suíte inteira: os módulos herméticos
# gravam "" em SUPABASE_URL no import e ninguém restaura. Ver o cabeçalho
# de `tests/conftest.py` — 4 destes sumiam em silêncio, medido em 18/08/2026.
pytestmark = pytest.mark.usefixtures("ambiente_real")


CARD = 73  # o card medido: cluster #4 + funil #6, o único com o ciclo completo


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app)


def _ok(r, *, permitido=(200,)):
    if r.status_code == 503:
        pytest.skip(f"engine indisponível neste ambiente: {r.json().get('detail','')[:120]}")
    assert r.status_code in permitido, r.text
    return r.json()


# ── a trava ─────────────────────────────────────────────────────────────────

def test_a_trava_esta_fechada(cliente: TestClient):
    """O estado padrão, e o que qualquer ambiente de teste tem de reportar.

    Se este teste falhar, alguém definiu FORGE_PERMITIR_ESCRITA no ambiente onde
    a suíte roda — e a suíte passaria a poder criar campanha de verdade.
    """
    d = _ok(cliente.get("/api/trafego/trava"))
    assert d["escrita_permitida"] is False
    assert d["env_presente"] is False
    # A frase mudou em 25/08/2026: ela ia para a tela do OPERADOR citando
    # `destravar()` e o nome da variável de ambiente — instruções que quem lê a
    # tela não pode executar. A REGRA não mudou, e é ela que este teste guarda:
    # os dois campos acima continuam False.
    #
    # O que se afirma aqui passou a ser o contrário: a explicação NÃO pode
    # conter vocabulário de implementação.
    explicacao = d["explicacao"]
    assert explicacao.strip(), "a trava tem de explicar por que está fechada"
    for vazamento in ("destravar", "FORGE_PERMITIR_ESCRITA", "validate_only",
                      "os.environ"):
        assert vazamento not in explicacao, (
            f"a explicação da trava vazou {vazamento!r} para a tela do operador"
        )


def test_subir_nao_alcanca_credito_up_mesmo_com_trava_fechada(cliente: TestClient):
    """A conta-laboratório é uma fronteira independente da trava global.

    O primeiro canário só pode nascer em Portal Mundo Mais. A Crédito Up é
    recusada antes de qualquer preparação ou tentativa de escrita — abrir a
    trava para o canário não amplia o alvo por acidente.
    """
    r = cliente.post("/api/trafego/subir", json={
        "opportunity_id": CARD, "customer_id": "8017851692",
        "login_customer_id": "6016739364", "motivo": "teste automatizado da recusa",
        "grupos": [], "budget_diario": 10.0,
    })
    if r.status_code == 503:
        pytest.skip("engine indisponível")
    assert r.status_code == 403, r.text
    assert "547-809-6539" in r.text
    assert r.status_code != 500, "a recusa da trava não pode virar erro de servidor"


def test_subir_canario_exige_confirmacao_explicita_de_pausada(cliente: TestClient):
    r = cliente.post("/api/trafego/subir", json={
        "opportunity_id": CARD, "customer_id": "5478096539",
        "login_customer_id": "6016739364",
        "motivo": "teste automatizado da confirmação explícita",
        "grupos": [], "budget_diario": 10.0, "cpc_inicial": 0.12,
        "plano_impressao": "f" * 64,
        "confirmar_criacao_pausada": False,
    })
    assert r.status_code == 403, r.text
    assert "PAUSADA" in r.text


# ── o quadro ────────────────────────────────────────────────────────────────

def test_o_quadro_nao_promete_metrica(cliente: TestClient):
    """Não existe camada de métrica no engine (`metrics.` = 0 ocorrências).

    A resposta declara isso, não só a tela: quem consumir esta rota não deve
    procurar performance aqui nem inventá-la a partir de outro campo.
    """
    d = _ok(cliente.get("/api/trafego/quadro"))
    assert d["sem_metrica"] is True
    assert d["por_que"]
    proibidos = {"roas", "ctr", "conversoes", "impressoes", "cliques", "gasto"}
    for p in d["prontos"]:
        assert not (proibidos & set(p)), f"campo de métrica vazou: {set(p) & proibidos}"


def test_so_entra_no_quadro_funil_que_publicou(cliente: TestClient):
    """Sem página no ar não há para onde mandar o clique."""
    d = _ok(cliente.get("/api/trafego/quadro"))
    for p in d["prontos"]:
        assert p["paginas_publicadas"] > 0
        assert p["titulo"]


def test_o_quadro_carrega_a_procedencia(cliente: TestClient):
    """Desde o quadro, e não só no cockpit: um número de volume ou de CPC sem
    dizer de onde veio é o defeito que esta entrega existe para não cometer."""
    d = _ok(cliente.get("/api/trafego/quadro"))
    for p in d["prontos"]:
        if p["tem_cluster"]:
            assert isinstance(p["servicos_declarados"], list)


# ── o cockpit ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cockpit(cliente: TestClient) -> dict:
    r = cliente.get(f"/api/trafego/candidatos/{CARD}")
    return _ok(r)


def test_nenhum_cpc_sai_sem_procedencia(cockpit: dict):
    """⚠️ A INVARIANTE CENTRAL DESTE MÓDULO.

    `services_used` do cluster inclui `n8n:dataforseo`, e `avg_cpc_local` e
    `currency` chegam NULOS. O `DATAFORSEO-MEDIDO.md` mediu, com 96 chamadas,
    que `keyword_info.cpc` superestima o CPC real em 7,4× E inverte a ordem
    dentro do cluster — nenhum fator de correção resolve.

    Um número de proveniência desconhecida apresentado como medição é o defeito
    exato que o `PORTOES_EXIGEM_MEDICAO` existe para impedir.
    """
    def conferir(c, onde):
        if c is None:
            return
        assert isinstance(c, dict), f"{onde}: CPC saiu pelado, sem procedência"
        assert c.get("procedencia"), f"{onde}: procedência vazia"
        assert "medido_na_conta" in c, f"{onde}: não diz se foi medido na conta"

    for g in cockpit["grupos"]:
        conferir(g["cpc_simples"], f"grupo {g['tipo']} simples")
        conferir(g["cpc_ponderado"], f"grupo {g['tipo']} ponderado")
        for k in g["keywords"]:
            conferir(k["cpc"], f"keyword {k['texto']}")
    for d in cockpit["descartadas"]:
        conferir(d["cpc"], f"descartada {d['texto']}")


def test_a_triagem_mostra_o_denominador(cockpit: dict):
    """"23 aprovadas" sem as 100 analisadas esconderia que 63 foram descartadas
    — e o descarte é trabalho já feito, não lixo a omitir."""
    t = cockpit["triagem"]
    assert t["analisadas"] >= t["aprovadas_anuncio"]
    assert t["analisadas"] > 0


def test_cada_sub_intencao_e_um_candidato_a_ad_group(cockpit: dict):
    """A estrutura já vinha pronta da mineração e o construtor antigo a
    ignorava: um ad group só significa um lance só para todos."""
    assert cockpit["grupos"], "nenhum grupo — o cockpit não teria o que montar"
    for g in cockpit["grupos"]:
        assert g["tipo"]
        assert g["keywords"], f"grupo {g['tipo']} sem keyword viraria ad group vazio"


def test_o_texto_da_lp_nao_viaja_por_padrao(cliente: TestClient):
    """É o artigo inteiro — dezenas de kB num payload pedido a cada abertura.

    Ele só viaja quando alguém vai cruzar anúncio × página, e aí viaja INTEIRO:
    comparar contra um resumo produziria falso negativo no caso que importa.
    """
    sem = _ok(cliente.get(f"/api/trafego/candidatos/{CARD}"))
    assert "texto_da_lp" not in sem["origem"]
    assert "tem_texto_da_lp" in sem["origem"]

    com = _ok(cliente.get(f"/api/trafego/candidatos/{CARD}?com_texto_da_lp=true"))
    if com["origem"]["tem_texto_da_lp"]:
        assert len(com["origem"]["texto_da_lp"]) > len(str(sem["origem"]))


def test_a_url_de_rascunho_avisa_que_e_provisoria(cockpit: dict):
    """De um RASCUNHO o WordPress devolve `?post_type=r&p=2146`, não o
    permalink. Anunciar essa URL manda tráfego para um endereço que vai mudar."""
    o = cockpit["origem"]
    if o.get("status_wp") == "draft":
        # ⚠️ Os códigos são MAIÚSCULOS (`LP_EM_RASCUNHO`, `URL_PROVISORIA`).
        # A primeira versão deste teste comparava minúscula e reprovava um
        # aviso que existia — falso positivo que teria mandado alguém "consertar"
        # código correto.
        codigos = {a["codigo"].upper() for a in cockpit["avisos"]}
        assert any("URL" in c or "RASCUNHO" in c or "DRAFT" in c for c in codigos), \
            f"LP em rascunho sem aviso; avisos foram {codigos}"


def test_a_vertical_declarada_fica_visivel(cockpit: dict):
    """`vertical` é o eixo do portão de habilitação (país × vertical) do
    `policy/spec.py`, não um rótulo. Guardar o que o card DIZIA ao lado do que
    a ponte resolveu é o que torna a divergência auditável — é a questão em
    aberto do FGTS (`informativo` declarado, página que intermedeia crédito)."""
    o = cockpit["origem"]
    assert o["vertical"]
    assert "vertical_declarada" in o


def test_card_inexistente_nao_vira_500(cliente: TestClient):
    r = cliente.get("/api/trafego/candidatos/999999")
    if r.status_code == 503:
        pytest.skip("engine indisponível")
    assert r.status_code != 500, r.text


# ── a prova ─────────────────────────────────────────────────────────────────

def test_provar_sem_copy_reprova_e_diz_por_que(cliente: TestClient):
    """Reprovar é o caminho esperado aqui, e o valor está em QUAL juiz reprovou.

    Um "não foi possível" obrigaria o operador a adivinhar o que consertar —
    que é exatamente o que o flow n8n fazia ao quebrar em silêncio.
    """
    r = cliente.post("/api/trafego/provar", json={
        "opportunity_id": CARD, "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "grupos": [], "budget_diario": 10.0,
    })
    if r.status_code in (503, 504):
        pytest.skip(f"engine ou API indisponível: {r.status_code}")
    if r.status_code == 422:
        assert r.json()["detail"], "422 sem mensagem acionável"
        return
    d = _ok(r)
    p = d["preparo"]
    assert p["aprovado"] is False, "brief sem copy não pode receber selo"
    assert p["recusa_local"] or p["falha_validacao"], \
        "reprovou sem dizer qual juiz — é o defeito do n8n de volta"


def test_o_selo_e_pre_requisito_de_subir(cliente: TestClient):
    """Sem selo, `subir()` recusa ANTES de pedir autorização de escrita.

    A ordem importa: pedir permissão para mandar um grafo não provado seria
    pedir a coisa errada.
    """
    from volc_ads import subir as sb
    import inspect
    fonte = inspect.getsource(sb.subir)
    assert "_exigir_selo" in fonte, "subir() deixou de exigir o selo"


# ── o portão da casa ────────────────────────────────────────────────────────
#
# Medido em 18/08/2026: a credencial alcança 39 contas anunciáveis distintas
# sob 9 MCCs, e só 3 são da VOLC. As outras são de cliente. Estes testes
# provam que o limite é do SERVIDOR — uma tela que esconde a lista não é
# portão, porque `customer_id` viaja no corpo de `/provar` e de `/subir`.

MCC_TERCEIRO = "5838529870"     # IESDE — outro MCC que a credencial alcança
CONTA_TERCEIRO = "8552871761"   # Colégio Positivo — acesso DIRETO da credencial


def test_o_escopo_nao_sai_do_ambiente():
    """O MCC da casa é constante no código, e tem de continuar sendo.

    `backend/.env` traz `GOOGLE_ADS_LOGIN_CUSTOMER_ID=8696453882` — o MCC
    "Projetos Fla&Fe", com 17 contas de terceiro (medido em 18/08/2026). Se
    alguém apontar o portão para o ambiente, a fronteira do sistema passa a ser
    editável por `.env`, sem rastro em revisão de código.
    """
    import inspect

    from app.trafego import escopo

    fonte = inspect.getsource(escopo)
    corpo = fonte.split('"""', 2)[-1]  # fora do docstring do módulo
    assert "environ" not in corpo and "getenv" not in corpo, \
        "escopo.py passou a ler o ambiente — a fronteira ficou editável por .env"
    assert escopo.MCC_DA_CASA == "6016739364"


def test_o_portao_normaliza_o_id_com_hifen():
    """`801-785-1692` é como o painel do Google mostra o id NA TELA dele.

    Quem copia de lá cola com hífen, e a API responde erro de id inválido sem
    dizer que a causa foi o separador.
    """
    from app.trafego import escopo

    cid, mid = escopo.exigir_escopo("801-785-1692", "601-673-9364")
    assert (cid, mid) == ("8017851692", "6016739364")


def test_o_portao_recusa_mcc_de_terceiro():
    """Sem rede: quem manda outro MCC não chega a fazer requisição nenhuma."""
    from app.trafego import escopo

    with pytest.raises(escopo.ForaDoEscopo):
        escopo.exigir_escopo("8017851692", MCC_TERCEIRO)


def test_o_portao_recusa_o_proprio_mcc_como_conta():
    """Manager administra contas; campanha entra nas filhas dele."""
    from app.trafego import escopo

    with pytest.raises(escopo.ForaDoEscopo):
        escopo.exigir_escopo(escopo.MCC_DA_CASA, escopo.MCC_DA_CASA)


def test_vincular_recusa_conta_de_terceiro(cliente: TestClient):
    """403 e não 404: a fronteira é conferida antes de o projeto ser lido.

    Se dependesse do Supabase, um banco fora do ar transformaria a recusa em
    503 — e a tentativa de operar em conta de cliente não ficaria registrada.
    """
    r = cliente.put("/api/trafego/projetos/1/conta", json={
        "google_ads_customer_id": "8017851692",
        "google_ads_manager_id": MCC_TERCEIRO,
    })
    assert r.status_code == 403, r.text
    assert MCC_TERCEIRO in r.json()["detail"]


def test_provar_recusa_conta_de_terceiro(cliente: TestClient):
    """O bloqueio da tela não vale aqui — `customer_id` vem no corpo."""
    r = cliente.post("/api/trafego/provar", json={
        "opportunity_id": CARD, "customer_id": CONTA_TERCEIRO,
        "login_customer_id": MCC_TERCEIRO, "grupos": [],
    })
    assert r.status_code == 403, r.text


def test_subir_recusa_o_escopo_antes_da_trava(cliente: TestClient):
    """A ORDEM é a asserção: 403 (escopo), não 409 (trava).

    São duas condições independentes. Se a trava viesse primeiro, abri-la um
    dia — deliberadamente, para subir na conta da casa — deixaria a conta de
    terceiro alcançável no mesmo movimento.
    """
    r = cliente.post("/api/trafego/subir", json={
        "opportunity_id": CARD, "customer_id": "8017851692",
        "login_customer_id": MCC_TERCEIRO, "grupos": [],
        "motivo": "prova de que o escopo vem antes da trava",
    })
    assert r.status_code == 403, r.text


def test_o_escopo_so_oferece_conta_anunciavel_da_casa(cliente: TestClient):
    """A lista da aba Integrações não pode conter manager nem conta de fora."""
    r = cliente.get("/api/trafego/escopo")
    d = _ok(r, permitido=(200, 502))
    if r.status_code == 502:
        pytest.skip(f"API do Google indisponível: {str(d)[:120]}")
    assert d["mcc"] == "6016739364"
    assert d["contas"], "a casa ficou sem nenhuma conta anunciável"
    for c in d["contas"]:
        assert c["manager"] is False, f"{c['customer_id']} é MCC e não recebe campanha"
    assert d["ids_fora_do_escopo"] >= 0
    assert d["ids_acessiveis"] >= len(d["contas"])


def test_o_vinculo_vem_dos_ids_e_nao_de_google_ads_status(cliente: TestClient):
    """⚠️ `google_ads_status` é coluna do WEBGO e significa outra coisa lá.

    `supabaseDataService.ts` a lê como `=== 'connected'` para dizer que a
    ingestão de gasto está ligada. Medido em 18/08/2026, o projeto 1 está
    'connected' com os dois ids NULOS — quem acreditar nela mostra conta
    vinculada onde não existe nenhuma.
    """
    d = _ok(cliente.get("/api/trafego/projetos"))
    for p in d["projetos"]:
        esperado = bool(p["google_ads_customer_id"] and p["google_ads_manager_id"])
        assert p["vinculada"] is esperado, \
            f"projeto {p['id']}: vinculada={p['vinculada']} com ids " \
            f"{p['google_ads_customer_id']}/{p['google_ads_manager_id']}"


# ── o estágio 3: a copy ─────────────────────────────────────────────────────

def test_a_copy_do_engine_nao_chega_vazia_na_campanha():
    """⚠️ O DEFEITO QUE ESTE TESTE EXISTE PARA IMPEDIR ERA SILENCIOSO.

    A cascata de `volc_ads/copy` produz `title/description1/description2` no
    sitelink e `values` no snippet — vocabulário do `PROMPT.md`. O router lia
    `texto/descricao1/descricao2/valores`, nomes inventados aqui. Ligar o
    estágio 3 faria toda copy gerada chegar com sitelinks e snippet VAZIOS:
    `.get("texto", "")` devolve `""`, o Brief aceita string vazia, e nenhuma
    exceção sobe. O anúncio subiria sem extensão nenhuma e ninguém saberia.
    """
    from app.routers.trafego import CopyEntrada, _copy_do_corpo

    c = _copy_do_corpo(CopyEntrada(
        headlines=["Cartão para Negativado"],
        descriptions=["Veja as regras da MP 1.355/2026."],
        sitelinks=[{"title": "Regras da MP", "description1": "O que vale",
                    "description2": "E o que muda"}],
        callouts=["Portal Informativo"],
        snippet={"header": "Serviços", "values": ["Análise", "Comparação"]},
    ))
    assert c.sitelinks[0].texto == "Regras da MP"
    assert c.sitelinks[0].descricao1 == "O que vale"
    assert c.snippet.valores == ["Análise", "Comparação"]


def test_o_vocabulario_em_portugues_continua_aceito():
    """Quem já mandava `texto`/`valores` não pode quebrar."""
    from app.routers.trafego import CopyEntrada, _copy_do_corpo

    c = _copy_do_corpo(CopyEntrada(
        headlines=["x"], descriptions=["y"],
        sitelinks=[{"texto": "Antigo", "descricao1": "a", "descricao2": "b"}],
        snippet={"header": "Tipos", "valores": ["um"]},
    ))
    assert c.sitelinks[0].texto == "Antigo"
    assert c.snippet.valores == ["um"]


def test_copy_sem_keyword_recusa_e_diz_o_motivo(cliente: TestClient):
    """A copy ancora nos termos que vão para o anúncio. Sem eles não há o quê."""
    r = cliente.post("/api/trafego/copy", json={"opportunity_id": CARD, "keywords": []})
    if r.status_code == 503:
        pytest.skip("engine indisponível")
    assert r.status_code == 422, r.text
    assert "ancorar" in r.json()["detail"]


def test_fato_de_tipo_desconhecido_e_descartado_e_relatado():
    """⚠️ Descartar em silêncio seria pior que falhar.

    Medido em 18/08/2026 no card 73: 4 dos 6 fatos do funil têm
    `tipo: 'afirmacao'`, e a seção 2 do `PROMPT.md` só conhece
    `numero, prazo, data, mudanca, condicao, orgao, fonte_legal, processo`.
    Remapear seria eu escolhendo o que o texto afirma — inventar com cara de
    conserto. Cai, e o relatório diz qual e por quê.
    """
    import sys
    from types import SimpleNamespace

    _raiz = str(__import__("pathlib").Path(__file__).resolve().parents[2])
    if _raiz not in sys.path:
        sys.path.insert(0, _raiz)
    from volc_ads.copy import encomendar as enc

    origem = SimpleNamespace(
        nicho="Cartão para Negativado", url_final="https://creditoup.com.br/x",
        pais="BR", idioma="pt", vertical="financeiro",
        fatos=(
            SimpleNamespace(id="f1", tipo="afirmacao", texto="algo", fonte="https://x"),
            SimpleNamespace(id="n1", tipo="numero", texto="5% — MP 1.355/2026",
                            fonte="https://www.gov.br/"),
        ),
    )
    e, descartados = enc.encomendar(SimpleNamespace(origem=origem),
                                    keywords=["cartão para negativado"])
    assert [f.id for f in e.fatos] == ["n1"]
    assert any("f1" in d and "afirmacao" in d for d in descartados), descartados


def test_a_cascata_nao_chama_o_google():
    """O juiz do Google é NULO aqui, e isso é escolha declarada.

    `/provar` julga esta mesma copy dentro do payload inteiro uma linha depois
    — e a cascata roda até 8 rodadas. Ligar o Google aqui seria oito
    `validate_only` (a chamada mais lenta do fluxo) para julgar um texto que
    ainda vai ser julgado por completo.
    """
    import sys

    _raiz = str(__import__("pathlib").Path(__file__).resolve().parents[2])
    if _raiz not in sys.path:
        sys.path.insert(0, _raiz)
    from volc_ads.copy import encomendar as enc

    assert enc._sem_google({"headlines": []}) is None


# ── a vertical precisa SOBREVIVER ao refresh ────────────────────────────────
#
# ⚠️ Medido no card 65 em 19/08/2026: o operador escolheu `informativo`, a
# página recarregou, a escolha voltou para o inferido `governo_documentos`, e a
# prova reprovou com "Exige certificacao_servicos_oficiais (política 15332527)".
# A vertical vivia num `useState` do React — sobrevivia a cliques e morria num
# F5. Duas horas de ida e volta por um estado que não persistia.

def test_a_rota_de_copy_devolve_a_vertical_declarada(cliente: TestClient):
    """Sem isto a tela não tem como repor a escolha e volta ao inferido."""
    r = cliente.get("/api/trafego/copy/65", params={"run_id": 9})
    if r.status_code == 503:
        pytest.skip("Supabase indisponível neste ambiente")
    if r.status_code != 200 or not r.json().get("existe"):
        pytest.skip("card 65 sem copy neste ambiente")
    corpo = r.json()
    assert "vertical" in corpo, "a vertical não viaja para a tela"
    assert "certificacoes" in corpo


def test_a_escrita_grava_a_vertical_do_pedido():
    """A copy É ESCRITA contra uma vertical. Guardá-las juntas é o que mantém
    as duas coerentes — texto escrito sob uma regra e provado sob outra foi
    exatamente o defeito de 19/08."""
    import inspect

    from app.routers import trafego

    fonte = inspect.getsource(trafego.escrever_copy)
    assert '"vertical": body.vertical' in fonte
    assert '"certificacoes": list(body.certificacoes or [])' in fonte


def test_a_projecao_da_copy_le_a_vertical_da_linha():
    import inspect

    from app.routers import trafego

    fonte = inspect.getsource(trafego._copy_para_tela)
    assert 'linha.get("vertical")' in fonte
