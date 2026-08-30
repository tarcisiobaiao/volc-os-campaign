"""Provas do diagnóstico de campanha que não gasta.

Nenhuma fala com o Google: o serviço é um dublê e o relógio é injetado. O que
se prova aqui é a DECISÃO — quando alertar, quando calar, e que o alerta não
inventa número nenhum.

Rodar:
    backend/.venv/bin/python -m pytest volc_ads/testes_entrega.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from volc_ads import entrega


AGORA = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _d(**campos) -> entrega.Diagnostico:
    base = dict(campaign_id="1", campaign_name="C", status="ENABLED",
                horas_ligada=30.0, impressoes=0, cliques=0, custo=0.0)
    base.update(campos)
    return entrega.Diagnostico(**base)


# ── quando alertar, e quando calar ──────────────────────────────────────────

def test_ligada_ha_muito_e_sem_gastar_alerta():
    assert _d().alerta


def test_pausada_nao_alerta():
    """Campanha pausada não gastar é o comportamento correto dela."""
    assert not _d(status="PAUSED").alerta


def test_quem_gastou_nao_alerta():
    """Gastar pouco é outro assunto — este módulo só olha o ZERO."""
    assert not _d(custo=0.01).alerta


def test_ligada_ha_pouco_nao_alerta():
    """O Google ainda revisa e distribui nas primeiras horas. Alertar aí seria
    ensinar o operador a ignorar o sino."""
    assert not _d(horas_ligada=entrega.HORAS_ATE_ALERTAR - 0.1).alerta
    assert _d(horas_ligada=float(entrega.HORAS_ATE_ALERTAR)).alerta


def test_sem_saber_ha_quanto_tempo_NAO_alerta():
    """⚠️ O silêncio é uma resposta.

    `change_event` só cobre 14 dias: campanha ligada antes disso não tem como
    ter a hora conhecida. Alertar mesmo assim produziria o primeiro alerta
    falso — e o primeiro alerta falso ensina a ignorar todos os outros."""
    assert not _d(horas_ligada=None).alerta


# ── os dois sintomas pedem olhares opostos ──────────────────────────────────

def test_zero_impressao_manda_olhar_lance():
    d = _d(impressoes=0)
    assert d.sintoma == entrega.SEM_IMPRESSAO
    assert "o lance do grupo" in d.revisar()


def test_com_impressao_de_sobra_manda_olhar_o_anuncio_e_nao_o_lance():
    """Entrou no leilão o bastante e ninguém clicou: subir lance não conserta
    texto ruim — pagaria mais caro para continuar não sendo clicado."""
    d = _d(impressoes=entrega.IMPRESSOES_PARA_CULPAR_O_ANUNCIO + 40)
    assert d.sintoma == entrega.SEM_CLIQUE
    assert "o texto do anúncio" in d.revisar()
    assert "o lance do grupo" not in d.revisar()


def test_o_que_o_google_diz_vem_sempre_primeiro():
    """Quando ele diz algo, é sempre a causa — e é texto dele, não nosso."""
    for imp in (0, 40):
        assert _d(impressoes=imp).revisar()[0] == "o que o Google está dizendo"


# ── o alerta não inventa número ─────────────────────────────────────────────

def test_o_teto_de_cliques_e_divisao_de_dois_fatos():
    """Orçamento ÷ lance. Sem estimativa de terceiro no meio."""
    assert _d(orcamento=20.0, lance=0.12).teto_de_cliques == 166


def test_sem_lance_ou_orcamento_o_teto_e_None_e_nao_um_chute():
    assert _d(orcamento=20.0, lance=None).teto_de_cliques is None
    assert _d(orcamento=None, lance=0.12).teto_de_cliques is None


def test_o_modulo_nao_conhece_cpc_de_terceiro():
    """⚠️ A prova que guarda a decisão de desenho.

    Comparar o lance com o CPC do DataForSEO daria uma frase devastadora
    ("R$ 0,12 contra mediana de R$ 10,54") e um alerta que mente no dia em que
    a estimativa inflar.

    A prova é de DEPENDÊNCIA, não de palavra: o texto que explica POR QUE não
    usamos precisa poder citar a fonte sem quebrar o teste. Se alguém importar
    o cluster para cá, isto quebra."""
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(entrega))
    importados = {
        (getattr(n, "module", "") or "") + "." + (a.name or "")
        for n in ast.walk(arvore)
        if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
    }
    for proibido in ("dataforseo", "pautador_ponte", "motor_pautas", "sensores"):
        assert not any(proibido in i.lower() for i in importados), (
            f"{proibido!r} virou dependência — o alerta passou a usar estimativa")

    campos = {c for c in entrega.Diagnostico.__dataclass_fields__}
    for suspeito in ("mercado", "estimado", "cpc_medio", "referencia"):
        assert not any(suspeito in c for c in campos), (
            f"campo {suspeito!r} no diagnóstico: número de terceiro na tela")


def test_nao_escreve_nada():
    """Leitura pura, como o `forca.py`. A prova é de dependência e de chamada:
    sem a trava de escrita importada, sem serviço de mutação."""
    import ast
    import inspect

    fonte = inspect.getsource(entrega)
    arvore = ast.parse(fonte)
    importados = {
        (getattr(n, "module", "") or "") + "." + (a.name or "")
        for n in ast.walk(arvore)
        if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
    }
    for proibido in ("modo", "subir", "isencao"):
        assert not any(i.lower().endswith(proibido) for i in importados), (
            f"{proibido!r} importado num módulo de leitura")

    chamadas = {n.func.attr for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "search" in chamadas, "o módulo precisa consultar de fato"
    for escrita in ("mutate", "mutate_campaigns", "mutate_ad_groups", "destravar"):
        assert escrita not in chamadas, f"chamada de escrita {escrita!r}"


# ── a leitura, contra um dublê ──────────────────────────────────────────────

class _Campo:
    def __init__(self, nome): self.name = nome


class _Linha:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _svc(por_consulta: dict[str, list]):
    class _S:
        def search(self, customer_id, query):
            for chave, linhas in por_consulta.items():
                if chave in query:
                    return iter(linhas)
            return iter(())
    return _S()


def _campanha(cid="24155134757", nome="Maq", status="ENABLED", orcamento=20_000_000):
    return _Linha(
        campaign=_Linha(id=cid, name=nome, status=_Campo(status),
                        serving_status=_Campo("SERVING"),
                        primary_status=_Campo("ELIGIBLE"),
                        primary_status_reasons=[]),
        campaign_budget=_Linha(amount_micros=orcamento))


def test_junta_as_cinco_consultas_num_diagnostico():
    svc = _svc({
        "campaign.serving_status": [_campanha()],
        "FROM ad_group WHERE": [_Linha(campaign=_Linha(id="24155134757"),
                                       ad_group=_Linha(cpc_bid_micros=120_000))],
        "FROM ad_group_ad WHERE": [_Linha(
            campaign=_Linha(id="24155134757"),
            ad_group_ad=_Linha(policy_summary=_Linha(
                approval_status=_Campo("APPROVED"))))],
    })
    d = entrega.verificar("8017851692", ["24155134757"],
                          login_customer_id="6016739364", servico=svc, agora=AGORA)[0]
    assert d.lance == 0.12
    assert d.orcamento == 20.0
    assert d.aprovacao_do_anuncio == "APPROVED"
    assert d.teto_de_cliques == 166


def test_metrica_do_periodo_e_SOMADA_e_nao_a_ultima_linha():
    """⚠️ `segments.date` devolve UMA LINHA POR DIA.

    Ler a última daria o gasto de hoje e chamaria de "nunca gastou" uma
    campanha que gastou na segunda — o alerta acusaria uma campanha saudável."""
    dias = [_Linha(campaign=_Linha(id="9"),
                   metrics=_Linha(impressions=n, clicks=0, cost_micros=m))
            for n, m in ((5, 3_000_000), (2, 0), (0, 0))]
    svc = _svc({"campaign.serving_status": [_campanha(cid="9")],
                "segments.date": dias})
    d = entrega.verificar("1", ["9"], login_customer_id="2",
                          servico=svc, agora=AGORA)[0]
    assert d.impressoes == 7 and d.custo == 3.0
    assert not d.alerta, "gastou R$ 3,00 no período e ainda assim alertou"


def test_uma_consulta_que_falha_degrada_e_nao_derruba():
    """A tela não pode ficar sem alerta nenhum porque `change_event` recusou."""
    class _S:
        def search(self, customer_id, query):
            if "change_event" in query:
                raise RuntimeError("sem permissão")
            if "campaign.serving_status" in query:
                return iter([_campanha(cid="9")])
            return iter(())
    d = entrega.verificar("1", ["9"], login_customer_id="2",
                          servico=_S(), agora=AGORA)
    assert len(d) == 1 and d[0].horas_ligada is None


# ── a hora em que ligou ─────────────────────────────────────────────────────

def _evento(quando, tipo="CAMPAIGN", campos=("status",), novo_status="ENABLED",
            cid="9", origem="GOOGLE_ADS_WEB_CLIENT"):
    return _Linha(change_event=_Linha(
        change_date_time=quando,
        change_resource_type=_Campo(tipo),
        client_type=_Campo(origem),
        user_email="tarcisio@agenciavolc.com.br",
        changed_fields=_Linha(paths=list(campos)),
        old_resource=_Linha(campaign=_Linha(status=_Campo("PAUSED")),
                            ad_group=_Linha(cpc_bid_micros=1_000_000)),
        new_resource=_Linha(campaign=_Linha(status=_Campo(novo_status)),
                            ad_group=_Linha(cpc_bid_micros=120_000)),
        campaign=f"customers/1/campaigns/{cid}"))


def test_a_hora_de_ligar_vem_do_change_event():
    svc = _svc({"campaign.serving_status": [_campanha(cid="9")],
                "change_event": [_evento("2026-08-19 06:00:00")]})
    d = entrega.verificar("1", ["9"], login_customer_id="2",
                          servico=svc, agora=AGORA)[0]
    assert d.horas_ligada == pytest.approx(30.0, abs=0.1)
    assert d.alerta


def test_status_de_GRUPO_nao_conta_como_hora_de_ligar():
    """⚠️ `status` aparece em `changed_fields` de grupo e de anúncio também.

    Contar um deles daria "ligada há 3 h" numa campanha que roda há semanas — e
    o alerta sumiria justamente de quem mais precisa dele."""
    svc = _svc({"campaign.serving_status": [_campanha(cid="9")],
                "change_event": [_evento("2026-08-20 09:00:00", tipo="AD_GROUP")]})
    d = entrega.verificar("1", ["9"], login_customer_id="2",
                          servico=svc, agora=AGORA)[0]
    assert d.horas_ligada is None


def test_pausar_nao_conta_como_ligar():
    svc = _svc({"campaign.serving_status": [_campanha(cid="9")],
                "change_event": [_evento("2026-08-19 06:00:00", novo_status="PAUSED")]})
    assert entrega.verificar("1", ["9"], login_customer_id="2",
                             servico=svc, agora=AGORA)[0].horas_ligada is None


# ── quem mexeu, e por onde ──────────────────────────────────────────────────

def test_alteracao_de_lance_aparece_com_origem_e_valores():
    """O campo que resolveu, em dez segundos, a contradição de 20/08/2026."""
    svc = _svc({"campaign.serving_status": [_campanha(cid="9")],
                "change_event": [_evento("2026-08-19 22:39:45",
                                         campos=("cpc_bid_micros",), tipo="AD_GROUP")]})
    d = entrega.verificar("1", ["9"], login_customer_id="2",
                          servico=svc, agora=AGORA)[0]
    assert len(d.alteracoes) == 1
    a = d.alteracoes[0]
    assert a.campo == "lance" and a.de == "R$ 1.00" and a.para == "R$ 0.12"
    assert "no painel" in a.resumo()


def test_campo_irrelevante_nao_polui_a_lista():
    """`changed_fields` traz nome, sufixo de URL, rede. Vinte linhas de ruído
    enterram a alteração que importa."""
    svc = _svc({"campaign.serving_status": [_campanha(cid="9")],
                "change_event": [_evento("2026-08-19 10:00:00",
                                         campos=("name", "final_url_suffix"))]})
    assert entrega.verificar("1", ["9"], login_customer_id="2",
                             servico=svc, agora=AGORA)[0].alteracoes == ()


# ── o que o sino conta ──────────────────────────────────────────────────────

def test_alertar_filtra_so_quem_precisa_de_olho():
    todos = (_d(campaign_id="1"), _d(campaign_id="2", custo=5.0),
             _d(campaign_id="3", status="PAUSED"))
    assert [d.campaign_id for d in entrega.alertar(todos)] == ["1"]


def test_o_gatilho_esta_declarado_como_escolha_e_nao_como_medicao():
    """⚠️ 24 h não foi medido — é política de operação. Um número sem essa
    ressalva vira "o Google recomenda 24 h" na boca do próximo que ler."""
    import inspect

    fonte = inspect.getsource(entrega)
    i = fonte.index("HORAS_ATE_ALERTAR = ")
    trecho = fonte[max(0, i - 700):i].lower()
    assert "não é número medido" in trecho or "nao e numero medido" in trecho


# ── a fonte é a CONTA, não a nossa tabela ───────────────────────────────────
#
# ⚠️ Medido em 20/08/2026. A primeira versão lia os ids de `campaigns`:
#
#     customer_id VAZIO nas quatro linhas
#     as campanhas subidas na véspera AUSENTES
#     status_source = 'auto' — o fluxo n8n escreve na mesma tabela
#
# Tabela com dois donos é cache, não verdade. O alerta que dependesse dela
# ficaria mudo justamente quando mais importa — e alerta quebrado é
# indistinguível de "está tudo bem".

def test_sem_lista_pergunta_as_LIGADAS_da_conta():
    vistas = []

    class _S:
        def search(self, customer_id, query):
            vistas.append(query)
            if "campaign.status = 'ENABLED'" in query:
                return iter([_campanha(cid="9")])
            return iter(())

    d = entrega.verificar("1", None, login_customer_id="2", servico=_S(), agora=AGORA)
    assert len(d) == 1 and d[0].campaign_id == "9"
    assert any("campaign.status = 'ENABLED'" in q for q in vistas)


def test_com_lista_respeita_a_lista():
    """O caminho antigo continua valendo: quem já sabe os ids não paga a varredura."""
    vistas = []

    class _S:
        def search(self, customer_id, query):
            vistas.append(query)
            if "campaign.serving_status" in query:
                return iter([_campanha(cid="77")])
            return iter(())

    entrega.verificar("1", ["77"], login_customer_id="2", servico=_S(), agora=AGORA)
    assert any("campaign.id IN (77)" in q for q in vistas)
    assert not any("campaign.status = 'ENABLED'" in q for q in vistas)


def test_conta_sem_campanha_nao_monta_consulta_vazia():
    """⚠️ `IN ()` é erro de sintaxe no GAQL. Sem esta saída, uma conta sem
    campanha ligada derrubaria as quatro consultas seguintes — e o log encheria
    de erro por uma situação que é normal."""
    consultas = []

    class _S:
        def search(self, customer_id, query):
            consultas.append(query)
            return iter(())

    assert entrega.verificar("1", None, login_customer_id="2",
                             servico=_S(), agora=AGORA) == ()
    assert len(consultas) == 1, "consultou depois de saber que não havia campanha"


def test_as_demais_consultas_usam_os_ids_QUE_VIERAM():
    """Pedir por id que não existe na conta e depois consultá-lo nas outras
    quatro seria perguntar sobre campanha que não está lá."""
    vistas = []

    class _S:
        def search(self, customer_id, query):
            vistas.append(query)
            if "campaign.serving_status" in query:
                return iter([_campanha(cid="5")])       # pedi 5 e 6, veio só 5
            return iter(())

    entrega.verificar("1", ["5", "6"], login_customer_id="2",
                      servico=_S(), agora=AGORA)
    grupo = next(q for q in vistas if "FROM ad_group WHERE" in q)
    assert "IN (5)" in grupo, grupo


# ── uma impressão não é "o anúncio está ruim" ───────────────────────────────
#
# ⚠️ PEGO NA PRÓPRIA CONTA, EM 20/08/2026, rodando o módulo contra a produção.
# A maquininha tinha UMA impressão em 24 horas e o alerta dizia:
#
#     "Entrou no leilão e ninguém clicou. Revise: o texto do anúncio."
#
# Uma impressão não diz nada sobre CTR. O operador gastaria uma cascata de copy
# consertando o que não está quebrado — o problema é ela quase não entrar no
# leilão. O corte era `impressoes > 0`.

def test_uma_impressao_nao_manda_reescrever_o_anuncio():
    d = _d(impressoes=1)
    assert d.sintoma == entrega.SEM_IMPRESSAO
    assert "o lance do grupo" in d.revisar()
    assert "o texto do anúncio" not in d.revisar()


def test_impressao_de_sobra_e_zero_clique_aponta_o_anuncio():
    d = _d(impressoes=entrega.IMPRESSOES_PARA_CULPAR_O_ANUNCIO)
    assert d.sintoma == entrega.SEM_CLIQUE
    assert "o texto do anúncio" in d.revisar()


def test_o_corte_de_impressoes_esta_declarado_como_escolha():
    """Como as 24 h: número de operação, não medição. Sem a ressalva, vira
    "o Google recomenda 100 impressões" na boca do próximo que ler."""
    import inspect

    fonte = inspect.getsource(entrega)
    i = fonte.index("IMPRESSOES_PARA_CULPAR_O_ANUNCIO = ")
    trecho = fonte[max(0, i - 900):i].lower()
    assert "não é número medido" in trecho or "nao e numero medido" in trecho
