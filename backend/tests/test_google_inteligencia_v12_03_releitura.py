"""Contraprovas da releitura do ledger PMax pela identidade canonica (v12_03).

Cada teste aqui nasceu como uma tentativa de REFUTAR a releitura, nao de
confirma-la. As propriedades sob ataque:

* uma linha so entra na fotografia se casar em TODOS os componentes da
  identidade — conta, MCC, campanha interna e externa, canal, familia, bucket,
  origem e versao de API;
* ausencia de linha, falha, parcial, inelegivel, nao suportado e velho mantem o
  portao FECHADO;
* seis familias verdes e uma ausente nao bastam;
* o veredito da propria execucao — autoatestado — nao abre nada;
* remover `pmax_observabilidade_nao_provada` NAO torna PMax criavel;
* a releitura nao alcanca nenhuma superficie de mutacao do Google Ads, porque
  ela nao fala com o Google Ads.

Nenhum teste deste arquivo abre socket, e nenhum toca no Supabase oficial.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.trafego import capacidades as cap
from app.trafego import contrato_canais as cc
from volc_ads.inteligencia_google import pmax, releitura
from volc_ads.inteligencia_google.persistencia import (
    ErroPersistenciaGoogle, SupabaseGoogleIntelligence,
)
from volc_ads.inteligencia_google.releitura import (
    ErroReleitura, ErroReleituraAmbigua, IdentidadeDaFotografia,
)

ROOT = Path(__file__).resolve().parents[2]

CONTA = "8017851692"
OUTRA_CONTA = "7016739360"
MCC = "6016739364"
CAMPANHA = "24156373100"
VOLC_ID = "c3d5c0de-0000-4000-8000-000000000003"
BUCKET = "daily:2026-09-01"
AGORA = datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)

IDENTIDADE = IdentidadeDaFotografia(
    customer_id=CONTA, login_customer_id=MCC, volc_campaign_id=VOLC_ID,
    campaign_id=CAMPANHA, bucket=BUCKET,
)


def linha(familia, *, estado="com_dados", coleta_id=None, coletada_em=None,
          payload=None, **trocas):
    """Uma linha do ledger como o PostgREST a devolveria."""

    if coleta_id is None:
        coleta_id = f"11111111-0000-4000-8000-{abs(hash(familia)) % 10**12:012d}"

    corpo = {
        "coleta_id": coleta_id,
        "chave_idempotencia": f"chave-{familia}",
        "tipo_sinal": pmax.TIPO_SINAL_POR_FAMILIA[familia],
        "estado": estado,
        "customer_id": CONTA,
        "login_customer_id": MCC,
        "volc_campaign_id": VOLC_ID,
        "campaign_id": CAMPANHA,
        "janela_inicio": None,
        "janela_fim": None,
        "competencia": "2026-09-01",
        "coletada_em": (coletada_em or AGORA).isoformat(),
        "api_versao": "v25",
        "coletor_versao": 3,
        "quantidade": 1 if estado == "com_dados" else (0 if estado == "vazio_confirmado" else None),
        "payload_sha256": "a" * 64,
        "erro_codigo": None,
        "erro_classe": None,
        "payload": {
            "somente_leitura": True,
            "fonte": pmax.FONTE_GOOGLE_ADS,
            "canal": pmax.CANAL_PMAX,
            "familia": familia,
            "bucket": BUCKET,
            "origem": "alvo_explicito",
        },
    }
    if payload:
        corpo["payload"] = {**corpo["payload"], **payload}
    corpo.update(trocas)
    return corpo


def fotografia_inteira(**por_familia):
    """As sete familias verdes, com sobrescritas por familia quando pedido."""

    return [
        linha(familia, **por_familia.get(familia, {}))
        for familia in pmax.FAMILIAS_PMAX
    ]


def prontidao(linhas, *, agora=AGORA, identidade=IDENTIDADE):
    return releitura.avaliar_prontidao_relida(linhas, identidade, agora=agora)


class LedgerDuble:
    """Porta de persistencia. Devolve linhas; nunca fala com rede."""

    def __init__(self, linhas):
        self.linhas = list(linhas)
        self.identidades = []

    def coletas_por_identidade(self, identidade, *, limite=100):
        self.identidades.append(identidade)
        return list(self.linhas)


# ---------------------------------------------------------------------------
# a fotografia completa: o unico caminho que fica verde
# ---------------------------------------------------------------------------


def test_sete_familias_relidas_persistidas_e_recentes_provam():
    veredito = prontidao(fotografia_inteira())

    assert veredito.provada is True
    assert veredito.faltando == ()
    assert veredito.linhagem == pmax.LINHAGEM_RELEITURA
    assert veredito.serializar()["autoatestada"] is False


def test_a_fotografia_relida_declara_a_identidade_que_a_delimitou():
    foto = releitura.fotografia_relida(fotografia_inteira(), IDENTIDADE)

    assert foto["linhagem"] == pmax.LINHAGEM_RELEITURA
    assert foto["identidade"] == IDENTIDADE.json()
    assert foto["total"] == len(pmax.FAMILIAS_PMAX)
    assert foto["descartadas"] == []
    assert [c["familia"] for c in foto["coletas"]] == list(pmax.FAMILIAS_PMAX)
    assert all(c["persistido"] is True and c["coleta_id"] for c in foto["coletas"])


# ---------------------------------------------------------------------------
# E. a setima familia continua em RECOMENDACOES_ARMAZENADAS
# ---------------------------------------------------------------------------


def test_e_a_setima_familia_e_lida_por_tipo_sinal_mais_familia():
    foto = releitura.fotografia_relida(fotografia_inteira(), IDENTIDADE)
    recomendacao = [
        c for c in foto["coletas"] if c["familia"] == pmax.FAMILIA_RECOMENDACOES
    ][0]

    assert recomendacao["tipo_sinal"] == "RECOMENDACOES_ARMAZENADAS"
    assert recomendacao["tipo_sinal"] in pmax.TIPOS_SINAL_DA_V12_01


def test_e_varredura_de_conta_no_mesmo_tipo_sinal_nao_vira_familia_pmax():
    """A varredura continua grava `RECOMENDACOES_ARMAZENADAS` sem `familia`.

    Se ela contasse como a setima familia, uma campanha nunca fotografada
    herdaria observabilidade da varredura da conta inteira.
    """

    varredura = linha(pmax.FAMILIA_RECOMENDACOES)
    varredura["payload"] = {
        k: v for k, v in varredura["payload"].items() if k != "familia"
    }
    linhas = [
        l for l in fotografia_inteira()
        if l["payload"]["familia"] != pmax.FAMILIA_RECOMENDACOES
    ] + [varredura]

    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert pmax.FAMILIA_RECOMENDACOES in veredito.faltando


def test_e_recibo_de_outra_pergunta_com_familia_forjada_nao_conta():
    """`DIAGNOSTICO_ENTREGA` com `payload.familia` preenchido a mao.

    Sem conferir `tipo_sinal` CONTRA a familia, este recibo — que responde pelo
    diagnostico Search da mesma campanha — passaria a responder por PMax.
    """

    forjado = linha(pmax.FAMILIA_CAMPANHA, tipo_sinal="DIAGNOSTICO_ENTREGA")
    linhas = [
        l for l in fotografia_inteira()
        if l["payload"]["familia"] != pmax.FAMILIA_CAMPANHA
    ] + [forjado]

    foto = releitura.fotografia_relida(linhas, IDENTIDADE)
    assert pmax.FAMILIA_CAMPANHA not in {c["familia"] for c in foto["coletas"]}
    assert any("incoerente com o tipo_sinal" in d["motivo"] for d in foto["descartadas"])
    assert prontidao(linhas).provada is False


# ---------------------------------------------------------------------------
# G. o coleta_id e o que prova gravacao
# ---------------------------------------------------------------------------


def test_g_linha_sem_coleta_id_nao_prova_gravacao():
    linhas = fotografia_inteira(**{pmax.FAMILIA_SINAIS: {"coleta_id": ""}})

    foto = releitura.fotografia_relida(linhas, IDENTIDADE)
    assert any(
        "nao prova gravacao no ledger" in d["motivo"] for d in foto["descartadas"]
    )
    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert pmax.FAMILIA_SINAIS in veredito.faltando


def test_g_persistido_nao_vem_de_alguem_afirmando_que_gravou():
    """Mesmo com `persistido: True` na linha, sem `coleta_id` nao vale."""

    mentirosa = linha(pmax.FAMILIA_ASSETS, coleta_id="")
    mentirosa["persistido"] = True
    linhas = [
        l for l in fotografia_inteira() if l["payload"]["familia"] != pmax.FAMILIA_ASSETS
    ] + [mentirosa]

    assert prontidao(linhas).provada is False


# ---------------------------------------------------------------------------
# H. ausencia, falha, parcial, inelegivel, nao suportado e velho fecham o portao
# ---------------------------------------------------------------------------


def test_h_ledger_sem_linha_mantem_o_portao_fechado():
    veredito = prontidao([])

    assert veredito.provada is False
    assert set(veredito.faltando) == set(pmax.FAMILIAS_PMAX)
    assert all("ausente da fotografia" in m for m in veredito.motivos)


@pytest.mark.parametrize(
    "estado", ["falhou", "parcial", "inelegivel", "nao_suportado"],
)
def test_h_estado_que_nao_concluiu_leitura_nao_e_familia_verde(estado):
    extra = (
        {"erro_codigo": "DEPENDENCIA_FALHOU:PMAX_ASSET_GROUPS",
         "erro_classe": "DependenciaDeLeitura"}
        if estado == "falhou" else {}
    )
    linhas = fotografia_inteira(
        **{pmax.FAMILIA_ASSETS: {"estado": estado, **extra}}
    )

    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert pmax.FAMILIA_ASSETS in veredito.faltando
    assert any(estado in m for m in veredito.motivos)


def test_h_vazio_confirmado_continua_sendo_leitura_concluida():
    """Zero NAO e ausencia: verde com zero recomendacao continua contando."""

    linhas = fotografia_inteira(
        **{pmax.FAMILIA_RECOMENDACOES: {"estado": "vazio_confirmado"}}
    )
    assert prontidao(linhas).provada is True


def test_h_fotografia_velha_nao_abre_o_portao():
    velha = AGORA - timedelta(hours=30)
    linhas = fotografia_inteira(
        **{pmax.FAMILIA_CAMPANHA: {"coletada_em": velha}}
    )

    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert any("frescor" in m for m in veredito.motivos)


def test_h_instante_ilegivel_nao_vira_recente():
    linhas = fotografia_inteira(
        **{pmax.FAMILIA_DESEMPENHO: {"coletada_em": None}}
    )
    linhas = [
        dict(l, coletada_em="ontem de tarde")
        if l["payload"]["familia"] == pmax.FAMILIA_DESEMPENHO else l
        for l in linhas
    ]

    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert any("instante" in m for m in veredito.motivos)


def test_h_falha_de_leitura_do_ledger_nunca_vira_fotografia_vazia():
    """Um `None` do PostgREST e leitura que nao concluiu, nao ledger vazio."""

    supa = SupabaseGoogleIntelligence(
        "https://database.agenciavolc.com.br", "chave-de-teste")
    supa._request = lambda *a, **k: None  # noqa: SLF001

    with pytest.raises(ErroReleitura, match="nao e fotografia vazia"):
        supa.coletas_por_identidade(IDENTIDADE)


def test_h_resposta_fora_de_forma_tambem_falha_fechado():
    supa = SupabaseGoogleIntelligence(
        "https://database.agenciavolc.com.br", "chave-de-teste")
    supa._request = lambda *a, **k: {"message": "erro"}  # noqa: SLF001

    with pytest.raises(ErroReleitura, match="esperava lista"):
        supa.coletas_por_identidade(IDENTIDADE)


def test_h_indisponibilidade_do_postgrest_sobe_como_falha():
    supa = SupabaseGoogleIntelligence(
        "https://database.agenciavolc.com.br", "chave-de-teste")

    def cai(*_a, **_k):
        raise ErroPersistenciaGoogle("PostgREST indisponivel")

    supa._request = cai  # noqa: SLF001
    with pytest.raises(ErroPersistenciaGoogle):
        supa.coletas_por_identidade(IDENTIDADE)


# ---------------------------------------------------------------------------
# I. mistura de conta, campanha, bucket ou origem nao forma fotografia verde
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("troca, componente", [
    ({"customer_id": OUTRA_CONTA}, "customer_id"),
    ({"login_customer_id": "9999999999"}, "login_customer_id"),
    ({"volc_campaign_id": "outro-volc-id"}, "volc_campaign_id"),
    ({"campaign_id": "24156373099"}, "campaign_id"),
    ({"api_versao": "v24"}, "api_versao"),
])
def test_i_coluna_de_outra_identidade_nao_entra(troca, componente):
    linhas = fotografia_inteira(**{pmax.FAMILIA_SINAIS: troca})

    foto = releitura.fotografia_relida(linhas, IDENTIDADE)
    assert any(componente in d["motivo"] for d in foto["descartadas"])
    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert pmax.FAMILIA_SINAIS in veredito.faltando


@pytest.mark.parametrize("troca, componente", [
    ({"bucket": "daily:2026-08-31"}, "bucket"),
    ({"origem": "varredura_continua"}, "origem"),
    ({"canal": "SEARCH"}, "canal"),
])
def test_i_payload_de_outra_identidade_nao_entra(troca, componente):
    linhas = fotografia_inteira(**{pmax.FAMILIA_ASSET_GROUPS: {"payload": troca}})

    foto = releitura.fotografia_relida(linhas, IDENTIDADE)
    assert any(componente in d["motivo"] for d in foto["descartadas"])
    assert prontidao(linhas).provada is False


def test_i_a_mesma_campanha_em_duas_contas_nao_se_mistura():
    """Dois clientes, o MESMO `campaign_id`. A fotografia e de UM deles."""

    da_outra_conta = [
        dict(l, customer_id=OUTRA_CONTA,
             volc_campaign_id="d4e6c0de-0000-4000-8000-000000000004",
             coleta_id=f"outra-{l['payload']['familia']}")
        for l in fotografia_inteira()
    ]
    parcial = [
        l for l in fotografia_inteira()
        if l["payload"]["familia"] != pmax.FAMILIA_ASSETS
    ]

    veredito = prontidao(parcial + da_outra_conta)
    assert veredito.provada is False
    assert pmax.FAMILIA_ASSETS in veredito.faltando


def test_i_duas_fotografias_do_mesmo_dia_nao_se_completam():
    """Buckets diferentes sao rodadas diferentes; juntar as duas inventa uma
    fotografia que nunca existiu inteira em momento nenhum."""

    manha = [
        dict(l, coleta_id=f"manha-{l['payload']['familia']}",
             payload={**l["payload"], "bucket": "4h:2026-09-01T08:00Z"})
        for l in fotografia_inteira()
        if l["payload"]["familia"] in (pmax.FAMILIA_ASSETS, pmax.FAMILIA_SINAIS)
    ]
    tarde = [
        l for l in fotografia_inteira()
        if l["payload"]["familia"] not in (pmax.FAMILIA_ASSETS, pmax.FAMILIA_SINAIS)
    ]

    veredito = prontidao(tarde + manha)
    assert veredito.provada is False
    assert set(veredito.faltando) == {pmax.FAMILIA_ASSETS, pmax.FAMILIA_SINAIS}


def test_i_duas_coletas_para_a_mesma_familia_e_ambiguidade_e_nao_desempate():
    linhas = fotografia_inteira() + [
        linha(pmax.FAMILIA_CAMPANHA, coleta_id="uma-segunda-coleta",
              coletada_em=AGORA - timedelta(minutes=5))
    ]

    with pytest.raises(ErroReleituraAmbigua, match="mais recente"):
        releitura.fotografia_relida(linhas, IDENTIDADE)


def test_i_a_mesma_linha_repetida_na_resposta_nao_e_ambiguidade():
    uma = linha(pmax.FAMILIA_CAMPANHA, coleta_id="repetida")
    linhas = [
        l for l in fotografia_inteira()
        if l["payload"]["familia"] != pmax.FAMILIA_CAMPANHA
    ] + [uma, dict(uma)]

    assert prontidao(linhas).provada is True


def test_i_identidade_sem_componente_e_recusada_na_construcao():
    for campo in ("customer_id", "login_customer_id", "volc_campaign_id",
                  "campaign_id", "bucket", "canal", "origem", "api_versao"):
        dados = dict(
            customer_id=CONTA, login_customer_id=MCC, volc_campaign_id=VOLC_ID,
            campaign_id=CAMPANHA, bucket=BUCKET, canal=pmax.CANAL_PMAX,
            origem="alvo_explicito", api_versao="v25",
        )
        dados[campo] = "   "
        with pytest.raises(ErroReleitura, match=campo):
            IdentidadeDaFotografia(**dados)


def test_i_o_filtro_do_postgrest_carrega_a_identidade_inteira():
    """A fronteira nao pode ser so do lado do dominio: o que sai na URL tambem
    precisa recortar por conta, MCC e campanha — e nunca pedir 'a mais recente'."""

    supa = SupabaseGoogleIntelligence(
        "https://database.agenciavolc.com.br", "chave-de-teste")
    vistos = {}

    def espiar(path, **_k):
        vistos["path"] = path
        return []

    supa._request = espiar  # noqa: SLF001
    supa.coletas_por_identidade(IDENTIDADE)

    path = vistos["path"]
    assert path.startswith("trafego_google_inteligencia_coleta?")
    for esperado in (
        f"customer_id=eq.{CONTA}", f"login_customer_id=eq.{MCC}",
        f"volc_campaign_id=eq.{VOLC_ID}", f"campaign_id=eq.{CAMPANHA}",
        "api_versao=eq.v25",
    ):
        assert esperado in path, esperado
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit("https://volc.invalid/" + path).query)
    assert query.get("limit") == ["101"]
    assert "order=coletada_em.desc" in path


def test_i_releitura_truncada_nao_vira_fotografia_completa():
    """O `order desc` existe para estabilidade, nao para esconder ambiguidades.

    A porta pede `limite + 1`; se o sentinela chega, a resposta esta cortada e
    nao pode ser promovida a `provada=True` com linhagem de ledger.
    """

    supa = SupabaseGoogleIntelligence(
        "https://database.agenciavolc.com.br", "chave-de-teste")
    supa._request = lambda *_a, **_k: [linha(pmax.FAMILIA_CAMPANHA)] * 101  # noqa: SLF001

    with pytest.raises(ErroReleitura, match="truncada"):
        supa.coletas_por_identidade(IDENTIDADE, limite=100)


def test_i_o_filtro_pede_so_o_vocabulario_da_fotografia():
    supa = SupabaseGoogleIntelligence(
        "https://database.agenciavolc.com.br", "chave-de-teste")
    vistos = {}
    supa._request = lambda path, **_k: (vistos.setdefault("path", path), [])[1]  # noqa: SLF001
    supa.coletas_por_identidade(IDENTIDADE)

    for tipo in releitura.TIPOS_SINAL_DA_FOTOGRAFIA:
        assert tipo in vistos["path"], tipo
    # DIAGNOSTICO_ENTREGA responde por outra pergunta e nao entra no recorte.
    assert "DIAGNOSTICO_ENTREGA" not in vistos["path"]


# ---------------------------------------------------------------------------
# J. seis familias verdes e uma ausente nao bastam
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ausente", pmax.FAMILIAS_PMAX)
def test_j_seis_verdes_e_uma_ausente_nao_bastam(ausente):
    linhas = [
        l for l in fotografia_inteira() if l["payload"]["familia"] != ausente
    ]

    veredito = prontidao(linhas)
    assert veredito.provada is False
    assert veredito.faltando == (ausente,)


def test_j_porta_do_ledger_e_do_dominio_dao_o_mesmo_veredito():
    ledger = LedgerDuble(fotografia_inteira())

    pela_porta = releitura.prontidao_do_ledger(ledger, IDENTIDADE, agora=AGORA)
    assert pela_porta.provada is True
    assert ledger.identidades == [IDENTIDADE]
    assert pela_porta.serializar() == prontidao(fotografia_inteira()).serializar()


# ---------------------------------------------------------------------------
# K / L. o portao de canal: autoatestado nao abre, releitura abre so um bloqueio
# ---------------------------------------------------------------------------


def test_a_linhagem_exigida_pelo_contrato_e_a_do_dominio():
    """Dois arquivos, um valor. Se o dominio renomear, o contrato cai junto."""

    assert cc.LINHAGEM_RELEITURA_DO_LEDGER == pmax.LINHAGEM_RELEITURA


def test_k_veredito_autoatestado_da_propria_execucao_nao_abre():
    autoatestado = pmax.ProntidaoPMax(
        provada=True, faltando=(), motivos=("as sete familias...",),
        linhagem=pmax.LINHAGEM_EXECUCAO,
    ).serializar()

    observacao = cc.observabilidade_do_canal(
        "PERFORMANCE_MAX", prontidao_pmax=autoatestado)
    assert observacao.estado == cc.INDETERMINADO
    assert "autoatestado" in observacao.causa


def test_k_veredito_sem_linhagem_declarada_nao_abre():
    observacao = cc.observabilidade_do_canal(
        "PERFORMANCE_MAX", prontidao_pmax={"provada": True})
    assert observacao.estado == cc.INDETERMINADO


def test_k_veredito_em_formato_ilegivel_nao_abre():
    observacao = cc.observabilidade_do_canal(
        "PERFORMANCE_MAX", prontidao_pmax=["provada"])
    assert observacao.estado == cc.INDETERMINADO
    assert observacao.causa


def test_h_releitura_incompleta_mantem_o_bloqueador_de_observabilidade():
    incompleta = prontidao(
        [l for l in fotografia_inteira()
         if l["payload"]["familia"] != pmax.FAMILIA_SINAIS]
    ).serializar()

    observacao = cc.observabilidade_do_canal(
        "PERFORMANCE_MAX", prontidao_pmax=incompleta)
    assert observacao.estado == cc.INDETERMINADO
    assert pmax.FAMILIA_SINAIS in observacao.causa
    extras = cc._bloqueios_de_observabilidade_na_criacao(  # noqa: SLF001
        "PERFORMANCE_MAX", observacao)
    assert [b.codigo for b in extras] == [cc.CODIGO_PMAX_SEM_OBSERVABILIDADE]


def test_l_sete_familias_relidas_abrem_a_observabilidade():
    provado = prontidao(fotografia_inteira()).serializar()

    observacao = cc.observabilidade_do_canal(
        "PERFORMANCE_MAX", prontidao_pmax=provado)
    assert observacao.estado == cc.PERMITIDO
    assert observacao.coletor == cc.COLETOR_PMAX
    assert cc._bloqueios_de_observabilidade_na_criacao(  # noqa: SLF001
        "PERFORMANCE_MAX", observacao) == ()


def _pmax(**kw):
    contratos = {c.canal: c for c in cc.contrato_dos_canais(
        capacidades=cap.de_identidade(papel="ADMIN", escrita_permitida=True), **kw)}
    return contratos["PERFORMANCE_MAX"]


def test_l_a_prova_remove_SOMENTE_o_bloqueador_de_observabilidade():
    provado = prontidao(fotografia_inteira()).serializar()

    antes = {b.codigo for b in _pmax().por_nome[cc.CRIAVEL_PAUSADA].bloqueadores}
    depois_portao = _pmax(prontidao_pmax=provado).por_nome[cc.CRIAVEL_PAUSADA]
    depois = {b.codigo for b in depois_portao.bloqueadores}

    assert cc.CODIGO_PMAX_SEM_OBSERVABILIDADE in antes
    assert antes - depois == {cc.CODIGO_PMAX_SEM_OBSERVABILIDADE}
    assert cc.CODIGO_PMAX_FORA_DO_EXECUTOR in depois


def test_l_nenhuma_campanha_pmax_passa_a_ser_criavel():
    """O portao continua FECHADO. PMAX_FORA_DO_EXECUTOR nao e observabilidade."""

    provado = prontidao(fotografia_inteira()).serializar()
    portoes = _pmax(prontidao_pmax=provado).por_nome

    assert portoes[cc.CRIAVEL_PAUSADA].estado == cc.BLOQUEADO
    assert portoes[cc.CRIAVEL_PAUSADA].aberto is False
    assert portoes[cc.VALIDAVEL].estado == cc.BLOQUEADO
    assert portoes[cc.ATIVAVEL].estado == cc.BLOQUEADO


def test_l_a_prova_de_pmax_nao_vaza_para_os_outros_canais():
    provado = prontidao(fotografia_inteira()).serializar()
    contratos = {c.canal: c for c in cc.contrato_dos_canais(
        capacidades=cap.de_identidade(papel="ADMIN", escrita_permitida=True),
        prontidao_pmax=provado)}

    for canal in ("SEARCH", "DISPLAY", "DEMAND_GEN"):
        assert contratos[canal].observabilidade.coletor == cc.COLETOR_DO_HUB, canal


def test_k_sem_releitura_o_canal_continua_como_estava():
    observacao = cc.observabilidade_do_canal("PERFORMANCE_MAX")

    assert observacao.estado == cc.INDETERMINADO
    assert observacao.causa
    assert _pmax().por_nome[cc.CRIAVEL_PAUSADA].estado == cc.BLOQUEADO


# ---------------------------------------------------------------------------
# M. nenhuma funcao de mutate Google Ads e alcancavel pela releitura
# ---------------------------------------------------------------------------


def test_m_a_releitura_nao_importa_google_ads():
    """Verificado na ARVORE: comentario nenhum produz import."""

    arvore = ast.parse((ROOT / "volc_ads/inteligencia_google/releitura.py").read_text())
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])

    assert "google" not in importados
    assert not (importados & {"urllib", "requests", "httpx", "socket", "http"})


@pytest.mark.parametrize("arquivo", [
    "volc_ads/inteligencia_google/releitura.py",
    "supabase/migrations/v12_03_pmax_observability_ledger.sql",
    "supabase/migrations/v12_03_rollback.sql",
    "scripts/provar-google-inteligencia-v12_03.sql",
    "scripts/provar-google-inteligencia-v12_03.sh",
])
def test_m_nenhum_artefato_desta_lane_contem_mutacao_google(arquivo):
    proibidos = (
        ".mutate_", "mutate_operation", "applyrecommendation",
        "apply_recommendation", "dismiss_recommendation", "validate_only",
        "googleadsservice", "campaignservice", "forge_permitir_escrita=1",
    )
    fonte = (ROOT / arquivo).read_text().lower()
    assert not [token for token in proibidos if token in fonte]


def test_m_a_releitura_nao_alcanca_o_coletor_do_google():
    """A porta que a releitura usa expoe UMA operacao, e ela e de leitura."""

    usadas = set()
    arvore = ast.parse((ROOT / "volc_ads/inteligencia_google/releitura.py").read_text())
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute) and isinstance(no.ctx, ast.Load):
            usadas.add(no.attr)

    assert "coletas_por_identidade" in usadas
    assert not (usadas & {"registrar", "search_stream", "get_service", "mutate"})
