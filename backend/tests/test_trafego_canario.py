"""Guardas do único alvo autorizado para o primeiro mutate Search."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import asyncio
import socket

import pytest
from fastapi import HTTPException

from app.trafego import canario
from app.routers import trafego
from app.seguranca.identidade import Identidade


RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste canário tentou abrir uma conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


#: A rede que o canário exige: Google Search ON, parceiros e Display OFF.
#: Importada do domínio, e não redigitada aqui — um dublê que declara a própria
#: rede provaria a rede do dublê.
from volc_ads.campanha.brief import RedeDePesquisa as _Rede  # noqa: E402

REDE_DO_CANARIO = _Rede(google_search=True, search_partners=False,
                        display_expansion=False)


def _pedido(**mudancas):
    base = dict(
        customer_id=canario.CONTA,
        login_customer_id=canario.MCC,
        canal="SEARCH",
        budget_diario="20.00",
        cpc_inicial="1.00",
        chave_intencao="a" * 64,
        carimbo_nome="20260828_120000",
        confirmar_criacao_pausada=True,
        rede=REDE_DO_CANARIO,
    )
    base.update(mudancas)
    return base


def test_a_politica_nomeia_a_conta_laboratorio_e_nao_inclui_ativacao():
    assert canario.POLITICA.para_json() == {
        "customer_id": "5478096539",
        "customer_id_formatado": "547-809-6539",
        "customer_label": "Portal Mundo Mais",
        "login_customer_id": "6016739364",
        "canal": "SEARCH",
        "cria_pausada": True,
        "inclui_ativacao": False,
        "orcamento_diario_maximo_brl": "20.00",
        "cpc_maximo_brl": "1.00",
    }


@pytest.mark.parametrize(
    ("mudanca", "trecho"),
    [
        ({"customer_id": "8017851692"}, "547-809-6539"),
        ({"login_customer_id": "999"}, "547-809-6539"),
        ({"canal": "DISPLAY"}, "apenas SEARCH"),
        ({"budget_diario": "20.01"}, "supera o teto"),
        ({"cpc_inicial": "1.01"}, "supera o teto"),
        ({"confirmar_criacao_pausada": False}, "confirmação explícita"),
        # A rede entrou na janela do canário em 01/09/2026.
        ({"rede": None}, "rede declarada"),
        ({"rede": _Rede(True, True, False)}, "Search Partners DESLIGADO"),
    ],
)
def test_o_canario_falha_fechado_fora_da_janela(mudanca, trecho):
    with pytest.raises(canario.CanarioRecusado, match=trecho):
        canario.exigir(**_pedido(**mudanca))


def test_a_marca_e_deterministica_e_nao_carrega_a_conta_credito_up():
    assert canario.exigir(**_pedido()) == "VOLC-CANARY-aaaaaaaaaaaa"


def test_carimbo_do_nome_e_congelavel_e_formato_invalido_falha_fechado():
    assert canario.carimbo_do_nome("20260828_120000") == "20260828_120000"
    with pytest.raises(canario.CanarioRecusado, match="carimbo"):
        canario.carimbo_do_nome("agora")


def test_a_impressao_do_plano_independe_da_ordem_do_dicionario():
    assert canario.impressao_do_plano({"a": 1, "b": [2, 3]}) == (
        canario.impressao_do_plano({"b": [2, 3], "a": 1})
    )
    assert canario.impressao_do_plano({"a": 2}) != (
        canario.impressao_do_plano({"a": 1})
    )


class _Servico:
    def __init__(self, linhas):
        self.linhas = linhas
        self.chamadas = []

    def search(self, **kwargs):
        self.chamadas.append(kwargs)
        return self.linhas


def _campanha(cid="123", nome="VOLC-CANARY-aaaaaaaaaaaa teste", status="PAUSED"):
    return SimpleNamespace(
        campaign=SimpleNamespace(
            id=cid, name=nome, status=SimpleNamespace(name=status),
        ),
    )


def _cliente_google_sem_rede():
    """Cliente proto mínimo, local a este arquivo e sem carregar credencial."""
    import enum
    from importlib import import_module

    modulo = pytest.importorskip("google.ads.googleads.client")

    class Enums:
        def __getattr__(self, nome: str):
            wrapper = getattr(import_module("google.ads.googleads.v25.enums"), nome)
            for atributo in dir(wrapper):
                valor = getattr(wrapper, atributo)
                if isinstance(valor, enum.EnumMeta):
                    return valor
            raise AttributeError(nome)

    cliente = modulo.GoogleAdsClient.__new__(modulo.GoogleAdsClient)
    cliente.version = "v25"
    cliente.use_proto_plus = True
    cliente.enums = Enums()
    return cliente


# ── o DESTINO da campanha, hermético ───────────────────────────────────────
#
# ⚠️ ESTE BLOCO NASCEU EM 03/09/2026, quando `/provar` e `/subir` passaram a ler
# a página de destino AO VIVO antes de cunhar a impressão aprovável (barreira 3).
# A rota ganhou uma dependência nova; um teste hermético que não a dubla passa a
# provar a ausência da rede, não a rota — foi por isso que `RepoDePlanoDeTeste`
# também precisou existir quando o plano de mensuração virou pré-requisito.
#
# O que a página abaixo carrega é o mínimo que o papel `paid_destination` exige:
# CNPJ do operador, contato, privacidade, aviso de não-vínculo, divulgação de
# monetização e corpo acima do piso de palavras. Cada ausência dessas é um
# BLOQUEIO — uma "página limpa" que não conseguisse ficar verde provaria só que
# a fixture envelheceu.

_RODAPE_DO_DESTINO = """
<p>Sobre o nosso site: portal informativo independente.</p>
<p>Os conteudos aqui publicados sao de carater informativo e nao possuem vinculo,
parceria ou qualquer ligacao com orgaos publicos ou entidades governamentais.</p>
<p>O site e financiado por blocos de anuncios em parceria com o Google Adsense.</p>
<p>Projeto da Volc Negocios Digitais 42.724.548/0001-24.</p>
<a href="/sobre">Sobre</a> <a href="/contato">Contato</a>
<a href="/politica-de-privacidade">Politica de Privacidade</a> <a href="/termos">Termos</a>
"""

_CORPO_DO_DESTINO = " ".join(
    [
        "O texto explica com calma as regras vigentes e como o leitor confere cada",
        "informacao no canal oficial, sem prometer resultado nenhum.",
    ]
    * 90
)

HTML_DO_DESTINO = (
    "<html><head><title>Guia informativo</title></head><body>"
    f"<h1>Guia informativo</h1><p>{_CORPO_DO_DESTINO}</p>"
    f"{_RODAPE_DO_DESTINO}</body></html>"
)

from app.landing_policy import (  # noqa: E402  (depois do HTML que ele carimba)
    CHAVE_DO_RECIBO as _CHAVE_DO_RECIBO,
    POLICY_CONTRACT_VERSION as _CONTRATO_DA_POLITICA,
    impressao_canonica as _impressao_canonica,
    versao_da_fonte as _versao_da_fonte,
)


def _recibo_de_aprovacao(html: str = HTML_DO_DESTINO) -> dict:
    """O recibo que a barreira 2 pendura na página publicada.

    ⚠️ `observed_at_epoch` é relativo a AGORA. A janela de frescor é de 24 h, e
    um carimbo congelado faria estes arquivos começarem a reprovar sozinhos no
    dia seguinte — por um motivo que não é o deles.
    """
    import hashlib
    import time as _time

    return {
        "policy_contract_version": _CONTRATO_DA_POLITICA,
        "policy_source_version": _versao_da_fonte(),
        "observed_at_epoch": _time.time() - 60,
        "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "content_fingerprint": _impressao_canonica(html),
        "paid_destination_ready": True,
    }


def _leitura_do_destino(url: str, *, user_agent: str = "", timeout: int = 20,
                        max_bytes: int = 2_000_000) -> dict:
    """Dublê de `fetch_public_https_chain`, com a forma EXATA da função real.

    Todas as variantes recebem o mesmo HTML: é o caso "sem cloaking, sem
    redirecionamento, sem deriva". Quem quer exercitar cada uma dessas falhas
    dubla por conta própria — ver `tests/test_barreira3_destino_de_campanha.py`.
    """
    import hashlib

    return {
        "url": url,
        "final_url": url,
        "status": 200,
        "hops": [],
        "headers": {"content-type": "text/html; charset=utf-8"},
        "user_agent": user_agent,
        "sha256": hashlib.sha256(HTML_DO_DESTINO.encode("utf-8")).hexdigest(),
        "bytes": len(HTML_DO_DESTINO.encode("utf-8")),
        "html": HTML_DO_DESTINO,
    }


def _linhas_da_rota(pp):
    """Recorte mínimo da porta de leitura; o contrato depois dela é real."""
    keyword = {
        "keyword": "guia do saque anual",
        "volume": 100,
        "cpc": 0.20,
        "competition": "LOW",
        "trend_score": 0,
        "tags": [],
        "reason": "fixture hermética",
    }
    return pp.Linhas(
        opportunity_id=1,
        cluster={
            "id": 1,
            "main_keyword": "Saque Anual",
            "total_volume": 100,
            "avg_cpc_local": None,
            "currency": None,
            "services_used": ["fixture:hermetica"],
            "production_ads_queue": [keyword],
            "content_seo_queue": [],
            "summary": {
                "total_analyzed": 1,
                "ads_approved": 1,
                "breakdown": {"discards": 0},
            },
            "funis_sugeridos": [{
                "rank": 1,
                "sub_intencoes": [{
                    "tipo": "INTENCAO",
                    "descricao": "Busca informativa",
                    "volume_sub": 100,
                    "keywords": [keyword],
                }],
            }],
        },
        run={
            "id": 1,
            "opportunity_id": 1,
            "project_id": 1,
            "lp_url": "https://portalmundomais.com.br/saque-anual/",
            "paginas_publicadas": [{
                "role": "LP",
                "slug": "saque-anual",
                "post_type": "r",
                "url_wp": "https://portalmundomais.com.br/saque-anual/",
                "status_wp": "publish",
                "page_number": 1,
                # ⚠️ O RECIBO DE APROVAÇÃO, dentro do dict da página publicada.
                #
                # Desde 03/09/2026 `/provar` e `/subir` avaliam o destino ao
                # vivo, e destino de campanha sem recibo resolvível REPROVA —
                # `recibo_da_url` procura exatamente aqui. Uma fixture sem
                # recibo passaria a representar "a casa nunca aprovou esta
                # página", que não é o cenário que estes arquivos exercitam.
                _CHAVE_DO_RECIBO: _recibo_de_aprovacao(),
            }],
        },
        entidade={
            "country_code": "BR",
            "language": "pt-BR",
            "vertical": "educacao",
            "canonical_name": "Saque Anual",
            "slug": "saque-anual",
        },
        wordpress={
            "project_id": 1,
            "wp_url": "https://portalmundomais.com.br",
            "post_type": "rec",
            "lp_post_type": "r",
        },
        estado_do_run={"facts": {}, "drafts": {"1": {"content": "{}"}}},
        run_dir="/tmp/fixture-hermetica-inexistente",
    )


def _payload_da_rota(**mudancas):
    base = {
        "opportunity_id": 1,
        "customer_id": canario.CONTA,
        "login_customer_id": canario.MCC,
        "canal": "SEARCH",
        "grupos": [{
            "tipo": "INTENCAO",
            "keywords": ["guia do saque anual"],
        }],
        "budget_diario": 10.0,
        "cpc_inicial": 0.20,
        # ⚠️ Desde 01/09/2026 o canário EXIGE a rede declarada. Ela não tem
        # default aqui de propósito: o payload de teste representa o pedido de
        # um operador, e um operador que não escolhe a rede é exatamente o que
        # o contrato novo recusa.
        "rede": {"google_search": True, "search_partners": False,
                 "display_expansion": False},
        "vertical": "informativo",
        "carimbo_nome": "20260828_120000",
        "copy": {
            "headlines": [
                "Regras do Saque Anual",
                "Quem Tem Direito em 2026",
                "Tabela Oficial por Faixa",
                "O Prazo de 90 Dias",
            ],
            "descriptions": [
                "Prazos, limites e quem tem direito, com fonte citada.",
                "Portal informativo com a tabela legal por faixa etaria.",
            ],
            "sitelinks": [
                {
                    "title": "Regras de 2026",
                    "description1": "O que vale hoje",
                    "description2": "E o que muda",
                },
                {
                    "title": "Quem tem direito",
                    "description1": "As condicoes",
                    "description2": "Em linguagem simples",
                },
            ],
            "callouts": ["Conteudo informativo", "Fontes oficiais"],
        },
    }
    base.update(mudancas)
    return base


def _instalar_portas_hermeticas(monkeypatch: pytest.MonkeyPatch):
    """Isola Supabase, Google e a leitura do destino; o resto do contrato é real.

    Real de propósito: `Escolha`, a ponte do Pautador, o `Brief`, o builder de
    Search e o PORTÃO DE DESTINO. O que é dublado são só as portas de saída —
    quem dubla o portão prova o dublê.
    """
    pytest.importorskip("google.ads.googleads")
    from app.publisher_quality import fetch as pqf
    from volc_ads import pautador_ponte as pp
    from volc_ads import subir as sb
    from volc_ads.campanha import search

    planos_remotos = []

    def carregar(opportunity_id: int, *, run_id: int | None = None):
        assert opportunity_id == 1
        assert run_id in (None, 1)
        return _linhas_da_rota(pp)

    def cliente_sem_rede(login_customer_id: str):
        assert login_customer_id == canario.MCC
        return _cliente_google_sem_rede()

    def validar_mutacoes(
        customer_id: str,
        operacoes: list,
        *,
        login_customer_id: str,
    ):
        assert customer_id == canario.CONTA
        assert login_customer_id == canario.MCC
        nome = next(
            op.campaign_operation.create.name
            for op in operacoes
            if op._pb.WhichOneof("operation") == "campaign_operation"
        )
        plano = {
            "impressao": sb._impressao(operacoes),
            "nome": nome,
        }
        if planos_remotos:
            assert plano == planos_remotos[0], (
                "a subida chegou à primeira porta remota com um plano "
                "diferente do aprovado"
            )
        planos_remotos.append(plano)

    monkeypatch.setattr(pp, "carregar", carregar)
    monkeypatch.setattr(search, "cliente", cliente_sem_rede)
    monkeypatch.setattr(sb, "validar_mutacoes", validar_mutacoes)
    # A leitura pública do destino (barreira 3). Sem o dublê, as rotas abririam
    # socket de verdade — e a fixture de rede derrubaria o arquivo inteiro por um
    # motivo que não é o dele.
    monkeypatch.setattr(pqf, "fetch_public_https_chain", _leitura_do_destino)
    monkeypatch.setattr(
        trafego.escopo,
        "conta_da_casa",
        lambda customer_id: {"customer_id": customer_id},
    )
    return planos_remotos


def test_a_busca_por_marca_e_read_only_e_devolve_o_que_achou():
    servico = _Servico([_campanha()])
    achados = canario.campanhas_com_marca(
        customer_id=canario.CONTA,
        login_customer_id=canario.MCC,
        marca="VOLC-CANARY-aaaaaaaaaaaa",
        servico=servico,
    )
    assert achados[0]["campaign_id"] == "123"
    assert servico.chamadas[0]["customer_id"] == canario.CONTA
    assert "SELECT campaign.id" in servico.chamadas[0]["query"]
    assert "mutate" not in servico.chamadas[0]["query"].lower()


def test_a_busca_por_destino_bloqueia_uma_campanha_viva_com_a_mesma_url():
    linha = _campanha()
    linha.ad_group_ad = SimpleNamespace(
        ad=SimpleNamespace(final_urls=["https://portalmundomais.com.br/beneficio/"])
    )
    servico = _Servico([linha])
    achados = canario.campanhas_com_destino(
        customer_id=canario.CONTA,
        login_customer_id=canario.MCC,
        url_final="https://portalmundomais.com.br/beneficio",
        servico=servico,
    )
    assert [a["campaign_id"] for a in achados] == ["123"]
    assert "campaign.status != 'REMOVED'" in servico.chamadas[0]["query"]


def test_marca_invalida_e_destino_sem_https_param_antes_da_rede():
    servico = _Servico([])
    with pytest.raises(canario.CanarioRecusado, match="marca"):
        canario.campanhas_com_marca(
            customer_id=canario.CONTA,
            login_customer_id=canario.MCC,
            marca="x' OR true",
            servico=servico,
        )
    with pytest.raises(canario.CanarioRecusado, match="HTTPS"):
        canario.campanhas_com_destino(
            customer_id=canario.CONTA,
            login_customer_id=canario.MCC,
            url_final="http://inseguro.test",
            servico=servico,
        )
    assert servico.chamadas == []


def test_a_caixa_legada_de_bidding_nao_tem_mais_porta_de_escrita():
    fonte = (RAIZ / "src/components/campaign/BiddingActionBox.tsx").read_text()
    assert "@/lib/supabase" not in fonte
    assert ".from('bid_actions')" not in fonte
    assert "fetch(" not in fonte
    assert "fluxos.agenciavolc.com.br/webhook" not in fonte
    assert "Aplicação bloqueada nesta página legada" in fonte


def test_plano_efetivo_diferente_do_aprovado_para_antes_da_consulta_remota(
    monkeypatch: pytest.MonkeyPatch,
):
    """O que passou no validate_only é o que o humano autorizou.

    A diferença é conferida antes da busca remota e, principalmente, antes do
    mutate. Assim, uma autocorreção nova entre as duas requisições não herda a
    aprovação do plano antigo.
    """
    planos_remotos = _instalar_portas_hermeticas(monkeypatch)

    def consulta_remota_proibida(
        *, customer_id: str, login_customer_id: str, marca: str,
    ):
        pytest.fail(
            "a consulta remota veio antes da conferência do selo: "
            f"{customer_id}/{login_customer_id}/{marca}"
        )

    monkeypatch.setattr(
        canario, "campanhas_com_marca", consulta_remota_proibida,
    )

    body = trafego.SubirEntrada(**_payload_da_rota(
        motivo="canário pausado com aprovação humana",
        plano_impressao="a" * 64,
        confirmar_criacao_pausada=True,
    ))
    identidade = Identidade(
        sub="operador", email="tarcisio@agenciavolc.com.br",
        papel="ADMIN", origem="teste",
    )

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(body, identidade=identidade))
    assert erro.value.status_code == 409
    assert "payload efetivo mudou" in str(erro.value.detail)
    assert len(planos_remotos) == 1


def test_provar_e_subir_reconstroem_o_mesmo_plano_antes_da_rede(
    monkeypatch: pytest.MonkeyPatch,
):
    """As rotas usam o contrato real e param antes de qualquer escrita."""
    planos_remotos = _instalar_portas_hermeticas(monkeypatch)
    payload = _payload_da_rota()

    prova = asyncio.run(trafego.provar(trafego.ProvarEntrada(**payload)))
    autorizacao = prova["autorizacao"]

    assert prova["preparo"]["aprovado"] is True
    assert autorizacao["carimbo_nome"] == "20260828_120000"
    assert autorizacao["plano_impressao"] == planos_remotos[0]["impressao"]
    assert planos_remotos[0]["nome"] == (
        f"VOLC-CANARY-{autorizacao['chave_intencao'][:12]} BR - "
        "20260828_120000 / Saque Anual / "
        "https://portalmundomais.com.br/saque-anual/"
    )

    def campanhas_com_marca(
        *, customer_id: str, login_customer_id: str, marca: str,
    ):
        assert customer_id == canario.CONTA
        assert login_customer_id == canario.MCC
        assert marca == f"VOLC-CANARY-{autorizacao['chave_intencao'][:12]}"
        assert planos_remotos == [planos_remotos[0], planos_remotos[0]]
        return ({"campaign_id": "ja-existe", "campaign_name": marca},)

    def campanhas_com_destino(
        *, customer_id: str, login_customer_id: str, url_final: str,
    ):
        assert customer_id == canario.CONTA
        assert login_customer_id == canario.MCC
        assert url_final == "https://portalmundomais.com.br/saque-anual/"
        return ()

    monkeypatch.setattr(canario, "campanhas_com_marca", campanhas_com_marca)
    monkeypatch.setattr(canario, "campanhas_com_destino", campanhas_com_destino)

    body_subida = trafego.SubirEntrada(**{
        **payload,
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": autorizacao["plano_impressao"],
        "confirmar_criacao_pausada": True,
    })
    identidade = Identidade(
        sub="operador", email="tarcisio@agenciavolc.com.br",
        papel="ADMIN", origem="teste",
    )

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(body_subida, identidade=identidade))

    assert erro.value.status_code == 409
    assert "já aparece na conta" in str(erro.value.detail)
    assert len(planos_remotos) == 2
    assert planos_remotos[1] == planos_remotos[0]
