"""O contrato dos quatro canais, e as confusões que ele existe para impedir.

Cada teste aqui nomeia UM colapso que o contrato proíbe:

* `ausente` virando `zero` — leitura que não aconteceu contada como conta vazia;
* `bloqueado` virando `não sei` — e vice-versa, que levam a ações opostas;
* `não aplicável` virando `zero` — canal sem construtor "montando 0 assets";
* portão fechado sem causa — o botão cinza que faz procurar contorno;
* autorização derivada na tela — o veredito recalculado longe de quem o cobra.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import trafego
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario
from app.trafego import canario as can
from app.trafego import capacidades as cap
from app.trafego import contrato_canais as cc
from app.trafego import plataforma as plat
from app.trafego import prontidao as pr


# ── as três pessoas que o contrato distingue ────────────────────────────────

ADMIN_SEM_ESCRITA = cap.de_identidade(papel="ADMIN", escrita_permitida=False)
ADMIN_COM_ESCRITA = cap.de_identidade(papel="ADMIN", escrita_permitida=True)
OPERADOR = cap.de_identidade(papel="OPERADOR", escrita_permitida=True)
SEM_PAPEL = cap.de_identidade(papel="", escrita_permitida=True)


def _por_canal(capacidades=ADMIN_SEM_ESCRITA, **kw):
    return {c.canal: c for c in cc.contrato_dos_canais(
        capacidades=capacidades, **kw)}


# ── os quatro canais, sempre ────────────────────────────────────────────────


def test_os_quatro_canais_saem_sempre_inclusive_o_que_nao_cria():
    """Esconder Performance Max faria a tela mentir por omissão: a conta tem
    campanhas dele gastando dinheiro."""
    canais = _por_canal()
    assert tuple(canais) == ("SEARCH", "DISPLAY", "DEMAND_GEN",
                             "PERFORMANCE_MAX")


def test_todo_canal_traz_os_quatro_portoes_na_ordem():
    for canal, contrato in _por_canal().items():
        nomes = tuple(p.nome for p in contrato.portoes)
        assert nomes == cc.PORTOES, canal


# ── portão fechado sem causa é proibido ─────────────────────────────────────


def test_nenhum_portao_fecha_sem_dizer_por_que():
    for canal, contrato in _por_canal().items():
        for portao in contrato.portoes:
            if portao.estado in (cc.BLOQUEADO, cc.INDETERMINADO):
                assert portao.bloqueadores, f"{canal}/{portao.nome}"
                for b in portao.bloqueadores:
                    assert b.causa.strip(), f"{canal}/{portao.nome}/{b.codigo}"
                    assert b.origem in cc.ORIGENS


def test_portao_bloqueado_sem_bloqueador_e_recusado_na_construcao():
    with pytest.raises(ValueError, match="sem causa nomeada"):
        cc.Portao(nome=cc.PLANEJAVEL, estado=cc.BLOQUEADO)


def test_portao_permitido_com_bloqueador_e_recusado():
    """A tela mostraria permissão e impedimento ao mesmo tempo."""
    b = cc.Bloqueador(codigo="x", causa="porque sim", origem=cc.ORIGEM_PRODUTO)
    with pytest.raises(ValueError, match="PERMITIDO com bloqueador"):
        cc.Portao(nome=cc.PLANEJAVEL, estado=cc.PERMITIDO, bloqueadores=(b,))


def test_bloqueador_sem_causa_e_recusado():
    with pytest.raises(ValueError, match="botão cinza"):
        cc.Bloqueador(codigo="x", causa="  ", origem=cc.ORIGEM_PRODUTO)


# ── os quatro portões NÃO são um booleano ───────────────────────────────────


def test_display_atravessa_a_prova_e_para_na_janela_do_canario():
    """O construtor existe; a autorização não. São perguntas diferentes, e
    colapsá-las abriria Display no dia em que a trava global abrisse."""
    display = _por_canal(ADMIN_COM_ESCRITA)["DISPLAY"].por_nome
    assert display[cc.VALIDAVEL].estado == cc.PERMITIDO
    assert display[cc.CRIAVEL_PAUSADA].estado == cc.BLOQUEADO
    codigos = {b.codigo for b in display[cc.CRIAVEL_PAUSADA].bloqueadores}
    assert codigos == {"fora_da_janela_do_canario"}
    (bloq,) = display[cc.CRIAVEL_PAUSADA].bloqueadores
    assert bloq.origem == cc.ORIGEM_POLITICA


def test_search_com_escrita_aberta_chega_a_criavel_pausada():
    search = _por_canal(ADMIN_COM_ESCRITA)["SEARCH"].por_nome
    assert search[cc.CRIAVEL_PAUSADA].estado == cc.PERMITIDO


def test_demand_gen_tem_construtor_e_mesmo_assim_nao_cria():
    """`sem_construtor` para Demand Gen faria o operador concluir que ele ainda
    não foi escrito. Ele existe — o que falta é autorização de mutação."""
    dg = _por_canal(ADMIN_COM_ESCRITA)["DEMAND_GEN"].por_nome
    codigos = {b.codigo for b in dg[cc.CRIAVEL_PAUSADA].bloqueadores}
    assert "sem_construtor" not in codigos
    assert "mutacao_real_recusada" in codigos


def test_a_causa_do_portao_fala_daquele_portao():
    """O manifesto de Demand Gen declara quatro indisponibilidades; a primeira
    é sobre a PROVA. Devolvê-la no portão de criação responderia a uma pergunta
    que ninguém fez."""
    dg = _por_canal(ADMIN_COM_ESCRITA)["DEMAND_GEN"].por_nome
    (bloq,) = [b for b in dg[cc.CRIAVEL_PAUSADA].bloqueadores
               if b.codigo == "mutacao_real_recusada"]
    assert "criação real" in bloq.causa
    assert "nasce desligada" not in bloq.causa


def test_pmax_planeja_e_nao_prova_nem_cria():
    """A tabela da decisão de 01/09/2026, ponto a ponto.

    ⚠️ PMax é a razão de existirem quatro portões em vez de um booleano. Ele
    monta o plano inteiro offline — `pmax.planejar()` serializa protos v25 sem
    rede — e não está no registro do executor. "Indisponível" apagaria a
    primeira metade; "pronto" apagaria a segunda.
    """
    pmax = _por_canal(ADMIN_COM_ESCRITA)["PERFORMANCE_MAX"].por_nome
    assert pmax[cc.PLANEJAVEL].estado == cc.PERMITIDO
    assert pmax[cc.VALIDAVEL].estado == cc.BLOQUEADO
    assert pmax[cc.CRIAVEL_PAUSADA].estado == cc.BLOQUEADO
    assert pmax[cc.ATIVAVEL].estado == cc.BLOQUEADO


def test_pmax_recusa_por_decisao_registrada_e_nao_por_ausencia():
    """As duas leituras são OPOSTAS para quem opera: "o canal não existe aqui"
    convida a desistir; "o canal planeja e a porta ainda não abriu" convida a
    pedir a porta."""
    pmax = _por_canal(ADMIN_COM_ESCRITA)["PERFORMANCE_MAX"].por_nome
    for nome in (cc.VALIDAVEL, cc.CRIAVEL_PAUSADA):
        codigos = {b.codigo for b in pmax[nome].bloqueadores}
        assert cc.CODIGO_PMAX_FORA_DO_EXECUTOR in codigos, nome
        assert "sem_construtor" not in codigos, nome
        (bloq,) = [b for b in pmax[nome].bloqueadores
                   if b.codigo == cc.CODIGO_PMAX_FORA_DO_EXECUTOR]
        # `produto` e não `construtor`: quem abre esta porta é o dono, não quem
        # escreve o engine. Errar a origem manda a pessoa para a porta errada.
        assert bloq.origem == cc.ORIGEM_PRODUTO, nome
        assert "não é falha" in bloq.causa


def test_o_codigo_de_pmax_e_o_mesmo_do_engine():
    """Uma palavra só para o mesmo fato: o 422 da rota e este contrato precisam
    dizer a mesma coisa, e `plano.CODIGOS` é a lista fechada."""
    from volc_ads.campanha import plano

    assert cc.CODIGO_PMAX_FORA_DO_EXECUTOR == plano.PMAX_FORA_DO_EXECUTOR
    assert cc.CODIGO_PMAX_FORA_DO_EXECUTOR in plano.CODIGOS


def test_registros_que_discordam_produzem_ignorancia_e_nao_recusa():
    """Eu vi isto acontecer: `demand_gen` importou no meio de uma escrita e
    respondeu sem `planejar`. O portão fechou, anunciando ausência de capacidade
    num canal que monta plano desde sempre. Um "não" derivado de um registro que
    falhou é pior que um "não sei", porque parece medido."""
    m = plat.DEMAND_GEN  # o manifesto declara campos de pedido
    portao = cc._portao_planejavel(m, ADMIN_COM_ESCRITA, False)
    assert portao.estado == cc.INDETERMINADO
    assert portao.estado != cc.BLOQUEADO
    (bloq,) = portao.bloqueadores
    assert bloq.codigo == "montagem_indeterminada"


def test_engine_nao_consultavel_cai_no_manifesto_e_nao_em_recusa():
    portao = cc._portao_planejavel(plat.SEARCH, ADMIN_COM_ESCRITA, None)
    assert portao.estado == cc.PERMITIDO


# ── a porta experimental não é herdada ──────────────────────────────────────


def test_demand_gen_nao_herda_a_prova_geral(monkeypatch):
    """A capacidade estreita depende do ambiente, não da pessoa. Derivá-la da
    geral ofereceria à tela uma prova que o executor recusa."""
    dg = _por_canal(ADMIN_COM_ESCRITA)["DEMAND_GEN"].por_nome
    assert not ADMIN_COM_ESCRITA.google_demand_gen_validate_only
    assert dg[cc.VALIDAVEL].estado == cc.BLOQUEADO
    (bloq,) = [b for b in dg[cc.VALIDAVEL].bloqueadores
               if b.codigo == "demand_gen_experimental_desligado"]
    assert bloq.origem == cc.ORIGEM_SERVIDOR


# ── quem pediu muda o veredito, e a origem diz a quem pedir ─────────────────


def test_sem_papel_nem_planeja():
    sem = _por_canal(SEM_PAPEL)["SEARCH"].por_nome
    assert sem[cc.PLANEJAVEL].estado == cc.BLOQUEADO
    (bloq,) = sem[cc.PLANEJAVEL].bloqueadores
    assert bloq.origem == cc.ORIGEM_OPERADOR


def test_admin_sem_escrita_e_bloqueio_de_servidor_nao_de_papel():
    """Errar a origem manda a pessoa para a porta errada: um admin sem escrita
    está preso pela trava do servidor, não pelo próprio papel."""
    search = _por_canal(ADMIN_SEM_ESCRITA)["SEARCH"].por_nome
    (bloq,) = [b for b in search[cc.CRIAVEL_PAUSADA].bloqueadores
               if b.codigo == "sem_capacidade_de_escrita"]
    assert bloq.origem == cc.ORIGEM_SERVIDOR


def test_operador_sem_admin_e_bloqueio_de_papel():
    search = _por_canal(OPERADOR)["SEARCH"].por_nome
    (bloq,) = [b for b in search[cc.CRIAVEL_PAUSADA].bloqueadores
               if b.codigo == "sem_capacidade_de_escrita"]
    assert bloq.origem == cc.ORIGEM_OPERADOR


# ── ativável: fechado em todos, e por razões independentes ──────────────────


def test_ativavel_nunca_abre_em_canal_nenhum():
    for capacidades in (SEM_PAPEL, OPERADOR, ADMIN_SEM_ESCRITA,
                        ADMIN_COM_ESCRITA):
        for canal, contrato in _por_canal(capacidades).items():
            portao = contrato.por_nome[cc.ATIVAVEL]
            assert portao.estado == cc.BLOQUEADO, (canal, capacidades)
            assert not portao.aberto


def test_ativavel_nomeia_as_razoes_independentes():
    search = _por_canal(ADMIN_COM_ESCRITA)["SEARCH"].por_nome
    origens = {b.origem for b in search[cc.ATIVAVEL].bloqueadores}
    assert cc.ORIGEM_PRODUTO in origens
    assert cc.ORIGEM_POLITICA in origens
    assert cc.ORIGEM_MENSURACAO in origens
    assert cc.ORIGEM_OBSERVABILIDADE in origens


def test_o_bloqueio_de_smart_bidding_medido_so_aparece_em_search():
    """A releitura foi de UMA campanha, em Search. Emitir o mesmo bloqueio para
    Display transportaria uma medição de uma campanha que não existe."""
    canais = _por_canal(ADMIN_COM_ESCRITA)
    codigos_search = {b.codigo
                      for b in canais["SEARCH"].por_nome[cc.ATIVAVEL].bloqueadores}
    assert "meta_efetiva_divergente" in codigos_search
    for outro in ("DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX"):
        codigos = {b.codigo
                   for b in canais[outro].por_nome[cc.ATIVAVEL].bloqueadores}
        assert "meta_efetiva_divergente" not in codigos, outro


def test_o_bloqueio_medido_carrega_data_e_caminho_de_revalidacao():
    """Um bloqueio que envelhece em silêncio fecha uma porta que já poderia
    estar aberta, com a autoridade de um fato."""
    assert cc.BLOQUEIO_META_EFETIVA.observado_em == "2026-09-01"
    assert cc.BLOQUEIO_META_EFETIVA.revalidacao


def test_o_bloqueio_medido_sai_quando_a_leitura_viva_discorda():
    pronto = pr.Prontidao(
        conversion_goal_status=pr.PRONTO,
        conversion_signal_status=pr.PRONTO,
        measurement_readiness=pr.PRONTO,
        observability_status=pr.PRONTO,
        smart_bidding_eligible=True,
    )
    search = cc.contrato("SEARCH", capacidades=ADMIN_COM_ESCRITA,
                         prontidao=pronto).por_nome
    codigos = {b.codigo for b in search[cc.ATIVAVEL].bloqueadores}
    assert "meta_efetiva_divergente" not in codigos
    # …e continua fechado, porque a política não inclui ativação.
    assert search[cc.ATIVAVEL].estado == cc.BLOQUEADO


# ── ausente ≠ zero ≠ falha ≠ não aplicável ──────────────────────────────────


def test_mensuracao_sem_leitura_e_indeterminada_e_nao_reprovada():
    """`NAO_PRONTO` pede conserto; `INDETERMINADO` pede leitura. Colapsá-los
    manda o operador para a ação errada."""
    m = _por_canal()["SEARCH"].mensuracao
    assert m.lida is False
    assert m.measurement_readiness == pr.INDETERMINADO
    assert m.conversion_goal_status == pr.INDETERMINADO
    assert m.smart_bidding_eligible is False
    assert m.fonte


def test_mensuracao_copia_a_prontidao_em_vez_de_recalcular():
    pronto = pr.avaliar(recibo_registrado=False, metas_da_conta=None)
    m = cc.mensuracao_do_canal("SEARCH", prontidao=pronto)
    assert m.lida is True
    assert m.conversion_goal_status == pronto.conversion_goal_status
    assert m.measurement_readiness == pronto.measurement_readiness
    assert m.smart_bidding_eligible == pronto.smart_bidding_eligible


def test_smart_bidding_elegivel_sem_leitura_e_recusado_na_construcao():
    with pytest.raises(ValueError, match="sem ninguém ter lido"):
        cc.Mensuracao(lida=False, smart_bidding_eligible=True)


def test_espelho_nao_contado_e_espelho_vazio_sao_estados_diferentes():
    nao_contado = cc.observabilidade_do_canal("SEARCH")
    contado_vazio = cc.observabilidade_do_canal(
        "SEARCH", campanhas_no_espelho=0)
    assert nao_contado.campanhas_no_espelho is None
    assert contado_vazio.campanhas_no_espelho == 0
    assert nao_contado.causa != contado_vazio.causa


def test_espelho_vazio_nao_vira_veredito():
    """Zero campanhas de um canal é ambíguo: conta sem nenhuma, ou leitura que
    nunca chegou lá. Escolher uma delas afirmaria o que não se olhou."""
    o = cc.observabilidade_do_canal("DISPLAY", campanhas_no_espelho=0)
    assert o.estado == cc.INDETERMINADO
    assert o.estado != cc.BLOQUEADO


def test_contagem_truncada_e_declarada():
    o = cc.observabilidade_do_canal("SEARCH", campanhas_no_espelho=500,
                                    contagem_truncada=True)
    assert o.contagem_truncada is True
    assert o.json()["contagem_truncada"] is True


def test_assets_de_pmax_vem_de_onde_eles_sao_o_contrato():
    """Em PMax o papel É o contrato (`AssetFieldType`), e
    `perfil.PERFORMANCE_MAX.recursos_criativos` continua vazio — o registro não
    acompanhou o construtor. Ler dele devolveria "este canal não declara
    recursos criativos próprios", que é falso com autoridade de registro."""
    a = _por_canal()["PERFORMANCE_MAX"].assets
    assert a.estado == cc.PERMITIDO
    assert "marketing" in a.recursos
    assert "marketing_quadrada" in a.recursos
    assert a.fonte and "brief" in a.fonte


def test_assets_nao_aplicavel_nao_reporta_quantidade_zero():
    """`0 de uma lista` sugeriria que a lista existe e o canal monta zero dela."""
    a = cc.Assets(estado=cc.NAO_APLICAVEL, causa="não há pedido")
    assert a.json()["quantidade"] is None


def test_assets_dos_canais_com_construtor_vem_do_engine():
    canais = _por_canal()
    assert canais["SEARCH"].assets.estado == cc.PERMITIDO
    assert "sitelink" in canais["SEARCH"].assets.recursos
    assert "logo" in canais["DISPLAY"].assets.recursos
    assert canais["DISPLAY"].assets.json()["quantidade"] == len(
        canais["DISPLAY"].assets.recursos)


def test_assets_indeterminado_exige_causa():
    with pytest.raises(ValueError, match="não perguntei"):
        cc.Assets(estado=cc.INDETERMINADO)


def test_assets_permitido_com_lista_vazia_e_recusado():
    with pytest.raises(ValueError, match="lista vazia"):
        cc.Assets(estado=cc.PERMITIDO, recursos=())


# ── o canário, por superfície ───────────────────────────────────────────────


class _SupaDesligado:
    enabled = False


class _SupaQueResponde:
    enabled = True

    def __init__(self, por_tabela):
        self.por_tabela = por_tabela
        self.consultas = []

    async def select(self, tabela, params):
        self.consultas.append((tabela, params))
        valor = self.por_tabela.get(tabela, [])
        if isinstance(valor, Exception):
            raise valor
        return valor


def test_canario_com_registro_indisponivel_nao_afirma_ausencia():
    r = asyncio.run(cc.canario_operacional(_SupaDesligado()))
    assert r["campaign_id"] == cc.CANARIO_CAMPANHA_ID
    assert [s["visivel"] for s in r["superficies"]] == [None, None, None]
    for s in r["superficies"]:
        assert s["causa"]


def test_canario_visivel_no_registro_e_ausente_no_espelho():
    """O caso REAL de 01/09/2026: a campanha existe, o recibo existe, e a
    leitura contínua de entrega não a enxerga porque ela está pausada."""
    supa = _SupaQueResponde({
        "trafego_recibo": [{"recibo_id": "r1", "desfecho": "sucesso",
                            "resposta_id_externo": cc.CANARIO_CAMPANHA_ID}],
        "trafego_campanha": [{"volc_campaign_id": "gads-5478096539-24195821946",
                              "campaign_id": cc.CANARIO_CAMPANHA_ID,
                              "customer_id": can.CONTA,
                              "procedencia": "volc_os"}],
        "trafego_campanha_espelho": [],
    })
    r = asyncio.run(cc.canario_operacional(supa))
    por_nome = {s["nome"]: s for s in r["superficies"]}
    assert por_nome["registro_de_criacao"]["visivel"] is True
    assert por_nome["identidade_de_campanha"]["visivel"] is True
    assert por_nome["espelho_de_leitura"]["visivel"] is False
    assert "campanhas ativas" in por_nome["espelho_de_leitura"]["causa"]
    assert "2 de 3" in r["resumo"]


def test_falha_de_leitura_do_canario_nao_vira_ausencia():
    supa = _SupaQueResponde({"trafego_recibo": RuntimeError("rede caiu")})
    r = asyncio.run(cc.canario_operacional(supa))
    por_nome = {s["nome"]: s for s in r["superficies"]}
    assert por_nome["registro_de_criacao"]["visivel"] is None
    assert "falhou" in por_nome["registro_de_criacao"]["causa"]


def test_espelho_sem_identidade_nao_conclui_ausencia():
    supa = _SupaQueResponde({"trafego_recibo": [], "trafego_campanha": []})
    r = asyncio.run(cc.canario_operacional(supa))
    por_nome = {s["nome"]: s for s in r["superficies"]}
    assert por_nome["espelho_de_leitura"]["visivel"] is None


def test_contagem_do_espelho_indisponivel_e_none_e_nao_zeros():
    """Zero por indisponibilidade faria a tela dizer 'nenhuma campanha lida' e
    o operador concluir que a varredura falhou."""
    assert asyncio.run(cc.contar_espelho_por_canal(_SupaDesligado())) is None


def test_canal_que_falha_na_contagem_nao_entra_como_zero():
    supa = _SupaQueResponde({"trafego_campanha_espelho": RuntimeError("boom")})
    assert asyncio.run(cc.contar_espelho_por_canal(supa)) is None


# ── a rota ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(trafego.router)
    quem = Identidade(sub="u1", email="op@volc", papel="ADMIN", origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: quem
    app.dependency_overrides[exigir_admin] = lambda: quem
    return TestClient(app)


def test_a_rota_devolve_os_quatro_canais_com_veredito_e_motivo(cliente):
    r = cliente.get("/api/trafego/canais")
    assert r.status_code == 200
    corpo = r.json()
    assert [c["canal"] for c in corpo["canais"]] == list(cc.CANAIS)
    for canal in corpo["canais"]:
        for portao in canal["portoes"]:
            assert portao["estado"] in cc.ESTADOS
            assert "aberto" in portao
            if portao["estado"] != cc.PERMITIDO:
                assert portao["bloqueadores"]


def test_a_rota_declara_que_nao_leu_o_google(cliente):
    corpo = cliente.get("/api/trafego/canais").json()
    assert corpo["fontes"]["leitura_viva_do_google"] is False
    assert corpo["fontes"]["por_que_sem_leitura_viva"]


def test_a_rota_de_um_canal_aceita_o_apelido_de_tela(cliente):
    r = cliente.get("/api/trafego/canais/pmax")
    assert r.status_code == 200
    assert r.json()["canal"]["canal"] == "PERFORMANCE_MAX"


def test_canal_inexistente_e_404_e_nao_500(cliente):
    r = cliente.get("/api/trafego/canais/TIKTOK")
    assert r.status_code == 404
    assert "TIKTOK" in r.json()["detail"]


def test_a_resposta_nao_carrega_segredo(cliente):
    """Nem nome de variável de ambiente, nem chave, nem caminho de arquivo do
    servidor — a mesma regra que `/capacidades` já cumpre."""
    bruto = cliente.get("/api/trafego/canais").text
    for proibido in ("SUPABASE_SERVICE_ROLE_KEY", "FORGE_PERMITIR_ESCRITA",
                     "VOLC_DEMAND_GEN_VALIDATE_ONLY", "/Users/", "/root/"):
        assert proibido not in bruto, proibido


def test_a_rota_traz_o_canario_em_search(cliente):
    corpo = cliente.get("/api/trafego/canais").json()
    search = next(c for c in corpo["canais"] if c["canal"] == "SEARCH")
    canario = search["operacional"]["canario"]
    assert canario["campaign_id"] == cc.CANARIO_CAMPANHA_ID
    assert canario["estado_declarado"] == "PAUSED"
    assert canario["superficies"]


# ── o 422 de Performance Max ────────────────────────────────────────────────


def test_o_422_de_pmax_carrega_codigo_e_estado_proprios():
    """Sem isto, o operador lê o mesmo 422 de um canal inexistente. As duas
    leituras são opostas: uma convida a desistir, a outra a pedir a porta."""
    from volc_ads.campanha import plano

    detalhe = trafego._recusa_de_canal("PMAX", ValueError("seja lá o que for"))
    assert detalhe["codigo"] == plano.PMAX_FORA_DO_EXECUTOR
    assert detalhe["estado"] == "indisponivel_por_decisao"
    assert detalhe["canal"] == "PERFORMANCE_MAX"
    assert "não está habilitado nesta versão" in detalhe["mensagem"]


def test_o_422_de_pmax_nao_reusa_o_codigo_de_canal_inexistente():
    from volc_ads.campanha import plano

    detalhe = trafego._recusa_de_canal("pmax", ValueError("x"))
    assert detalhe["codigo"] != plano.CANAL_SEM_BUILDER


def test_o_422_preserva_a_frase_crua_do_executor():
    """Ela é a procedência da recusa, e quem depura precisa dela. O que muda é
    quem lê primeiro — o operador lê `mensagem`, não o `ValueError`."""
    detalhe = trafego._recusa_de_canal("PMAX", ValueError("frase do executor"))
    assert detalhe["detalhe_do_executor"] == "frase do executor"


def test_canal_desconhecido_continua_com_o_codigo_de_ausencia():
    from volc_ads.campanha import plano

    detalhe = trafego._recusa_de_canal("TIKTOK", ValueError("não existe"))
    assert detalhe["codigo"] == plano.CANAL_SEM_BUILDER
    assert detalhe["estado"] == "sem_porta_de_prova"


# ── a leitura de campo do canário ───────────────────────────────────────────


def test_a_estrategia_de_lance_do_canario_e_escolha_e_nao_ausencia():
    """`MANUAL_CPC` não é campo em branco. Mostrá-lo vazio faria o operador
    procurar a estratégia que 'faltou configurar'."""
    leitura = cc.leitura_de_campo_do_canario()
    assert leitura["estrategia_de_lance"]["valor"] == "MANUAL_CPC"
    assert leitura["estrategia_de_lance"]["estado"] == "escolhido"
    assert leitura["estrategia_de_lance"]["por_que_importa"]


def test_as_razoes_do_estado_sao_lista_e_nao_uma_so():
    """São duas simultâneas e dizem coisas diferentes: uma é consequência do
    desenho, a outra é o veredito que ainda não chegou."""
    razoes = cc.leitura_de_campo_do_canario()["primary_status_reasons"]
    assert isinstance(razoes, list)
    assert len(razoes) == 2
    assert {r["codigo"] for r in razoes} == {
        "CAMPAIGN_PAUSED", "MOST_ADS_UNDER_REVIEW"}


def test_em_revisao_nao_e_verde_nem_vermelho():
    """`MOST_ADS_UNDER_REVIEW` é o veredito que o canário existe para colher.
    Pintá-lo de verde afirmaria uma aprovação que não houve."""
    razoes = cc.leitura_de_campo_do_canario()["primary_status_reasons"]
    (revisao,) = [r for r in razoes if r["codigo"] == "MOST_ADS_UNDER_REVIEW"]
    assert revisao["natureza"] == "em_revisao"
    assert revisao["natureza"] not in ("ok", "falha", "por_desenho")
    assert "não é aprovação nem reprovação" in revisao["texto"]


def test_a_pausa_e_declarada_como_desenho_e_nao_como_problema():
    razoes = cc.leitura_de_campo_do_canario()["primary_status_reasons"]
    (pausa,) = [r for r in razoes if r["codigo"] == "CAMPAIGN_PAUSED"]
    assert pausa["natureza"] == "por_desenho"


def test_a_leitura_de_campo_carrega_a_data_em_que_foi_feita():
    """Ela envelhece, e a tela precisa poder dizer isso em vez de apresentá-la
    como o estado de agora."""
    assert cc.leitura_de_campo_do_canario()["observado_em"] == "2026-09-01"


def test_anuncios_em_revisao_bloqueiam_a_ativacao_de_search():
    search = _por_canal(ADMIN_COM_ESCRITA)["SEARCH"].por_nome
    codigos = {b.codigo for b in search[cc.ATIVAVEL].bloqueadores}
    assert "anuncios_em_revisao" in codigos


def test_a_revisao_nao_sai_quando_a_meta_e_resolvida():
    """Bloqueios independentes: fechar um não abre o portão. Foi por isso que
    eles nasceram nomeados em vez de a primeira razão encerrar a lista."""
    pronto = pr.Prontidao(
        conversion_goal_status=pr.PRONTO,
        conversion_signal_status=pr.PRONTO,
        measurement_readiness=pr.PRONTO,
        observability_status=pr.PRONTO,
        smart_bidding_eligible=True,
    )
    search = cc.contrato("SEARCH", capacidades=ADMIN_COM_ESCRITA,
                         prontidao=pronto).por_nome
    codigos = {b.codigo for b in search[cc.ATIVAVEL].bloqueadores}
    assert "meta_efetiva_divergente" not in codigos
    assert "anuncios_em_revisao" in codigos


def test_a_leitura_de_campo_sobrevive_ao_registro_operacional_fora_do_ar():
    """Ela é sobre a CONTA, não sobre o nosso banco. Omiti-la esconderia o que
    se sabe por causa do que não se conseguiu conferir."""
    r = asyncio.run(cc.canario_operacional(_SupaDesligado()))
    assert r["leitura_de_campo"]["primary_status"] == "PAUSED"
