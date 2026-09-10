"""Contraprovas dos catalogos selecionaveis da Meta (T04).

Tudo aqui e HERMETICO: o dublê de cliente so tem `get`, nenhum socket e aberto,
e um `post`/`delete` acidental viraria AttributeError em vez de uma mutacao.
As asserções centrais nao sao "o feliz caminho funciona" — sao as quatro que o
codigo antigo nao passava:

* campo AUSENTE nao pode virar `False` e nao pode virar `AVAILABLE` (A12);
* catalogo vazio-e-completo, permissao negada, timeout, pagina truncada e
  leitura obsoleta sao CINCO respostas distintas, nao um `items: []` (A11);
* handle de outra conta/ator nao resolve, nem para ler nem para compilar (A13);
* nenhuma chave de PII/lista de membros atravessa a fronteira de publico.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.credenciais import SegredoEfemero

TOKEN = "token-de-sistema-que-nao-pode-vazar-9911"
CONTA = "123456789012"
OUTRA_CONTA = "999999999999"


# ---------------------------------------------------------------------------
# DUBLÊS
# ---------------------------------------------------------------------------


class RespostaFake:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        if isinstance(self._body, ValueError):
            raise self._body
        return self._body


class ClienteGraphFake:
    """Dublê de transporte: so GET, e cada chamada fica registrada.

    O roteiro e indexado pelo ULTIMO segmento da URL (`adaccounts`,
    `adspixels`, `customaudiences`, `customconversions`, `search`). Uma lista
    com mais de um corpo e consumida pagina a pagina; com um so corpo, ele se
    repete — o que mantem o teste legivel quando a mesma edge e lida duas vezes.
    """

    def __init__(self, roteiro: dict[str, Any], *, token: str = TOKEN) -> None:
        self.roteiro = {k: (list(v) if isinstance(v, list) else v)
                        for k, v in roteiro.items()}
        self.chamadas: list[dict[str, Any]] = []
        self.token = token

    async def get(self, url: str, *, params: dict[str, Any] | None = None,
                  headers: dict[str, str] | None = None) -> RespostaFake:
        assert headers == {"Authorization": f"Bearer {self.token}"}, "segredo tem de ir no header"
        assert self.token not in url, "segredo nunca na URL"
        assert self.token not in str(params or {}), "segredo nunca em query param"
        self.chamadas.append({"url": url, "params": dict(params or {})})
        chave = url.rstrip("/").rsplit("/", 1)[-1]
        corpo = self.roteiro[chave]
        if isinstance(corpo, list):
            corpo = corpo.pop(0) if len(corpo) > 1 else corpo[0]
        if isinstance(corpo, BaseException):
            raise corpo
        if isinstance(corpo, dict) and corpo.get("__status"):
            return RespostaFake(int(corpo["__status"]), corpo)
        return RespostaFake(200, corpo)

    def edges_chamadas(self) -> list[str]:
        return [c["url"].rstrip("/").rsplit("/", 1)[-1] for c in self.chamadas]


def pagina(data: list[Any], after: str | None = None) -> dict[str, Any]:
    corpo: dict[str, Any] = {"data": data}
    if after:
        corpo["paging"] = {"next": "https://graph.facebook.com/next",
                           "cursors": {"after": after}}
    return corpo


def contas_visiveis(*ids: str) -> dict[str, Any]:
    return pagina([
        {"id": f"act_{cid}", "name": f"Conta {cid[-4:]}", "currency": "BRL",
         "timezone_name": "America/Sao_Paulo"}
        for cid in (ids or (CONTA,))
    ])


def adaptador(cliente: ClienteGraphFake, **kwargs: Any) -> AdaptadorMetaSomenteLeitura:
    return AdaptadorMetaSomenteLeitura(cliente, **kwargs)  # type: ignore[arg-type]


def ref_da_conta(conta: str = CONTA) -> str:
    return dom.referencia_opaca_conta(conta)


# ===========================================================================
# 1. O BUG TRI-STATE (A12) — a contraprova central do pacote
# ===========================================================================


def test_is_archived_ausente_vira_unknown_e_nunca_available() -> None:
    """AUSENTE != False. `bool(linha.get("is_archived"))` dizia que sim.

    A conversao abaixo tem `is_unavailable=False` explicito e NENHUM
    `is_archived` — exatamente o corpo que a Meta devolve quando o token nao
    alcanca o campo. O codigo antigo (adaptador.py:256) lia `bool(None)` =>
    `False` => "nao arquivada" => `AVAILABLE_FIRED`, e o operador recebia
    permissao implicita para otimizar por uma conversao que podia estar morta.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([{
            "id": "555500001111",
            "name": "Lead sem flag",
            "custom_event_type": "LEAD",
            "is_unavailable": False,
            "first_fired_time": "2026-08-01T10:00:00+0000",
            "last_fired_time": "2026-09-04T10:00:00+0000",
        }])]})
        itens, _ = await adaptador(cliente).ler_conversoes_personalizadas(
            CONTA, SegredoEfemero(TOKEN))

        assert itens[0]["estado"] == dom.ESTADO_DESCONHECIDO
        assert itens[0]["motivo_desconhecido"] == dom.MOTIVO_IS_ARCHIVED_AUSENTE
        # A invariante, dita do jeito que ela importa:
        assert not itens[0]["estado"].startswith("AVAILABLE")

    asyncio.run(cenario())


def test_is_archived_false_explicito_nao_e_unknown() -> None:
    """O outro lado: com as DUAS flags afirmadas, o item volta a ser decidivel."""
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([{
            "id": "555500001111", "name": "Lead vivo",
            "is_archived": False, "is_unavailable": False,
            "first_fired_time": "2026-08-01T10:00:00+0000",
            "last_fired_time": "2026-09-04T10:00:00+0000",
        }])]})
        itens, _ = await adaptador(cliente).ler_conversoes_personalizadas(
            CONTA, SegredoEfemero(TOKEN))

        assert itens[0]["estado"] == dom.ESTADO_DISPONIVEL_COM_DISPARO
        assert itens[0]["estado"] != dom.ESTADO_DESCONHECIDO
        assert itens[0]["motivo_desconhecido"] is None

    asyncio.run(cenario())


def test_is_unavailable_true_com_is_archived_ausente_nao_vira_available() -> None:
    """Evidencia negativa PROVADA vence a ausencia da outra flag.

    `UNAVAILABLE` e mais restritivo que `UNKNOWN`, nunca menos: degradar para
    UNKNOWN apagaria do operador a unica informacao util da linha. O que segue
    proibido, em qualquer combinacao com flag ausente, e `AVAILABLE_*`.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([{
            "id": "555500002222", "name": "Lead morto", "is_unavailable": True,
        }])]})
        itens, _ = await adaptador(cliente).ler_conversoes_personalizadas(
            CONTA, SegredoEfemero(TOKEN))

        assert itens[0]["estado"] == dom.ESTADO_INDISPONIVEL
        assert not itens[0]["estado"].startswith("AVAILABLE")

    asyncio.run(cenario())


@pytest.mark.parametrize(("bruto", "esperado"), [
    (None, None), (True, True), (False, False),
    ("true", True), ("false", False), ("TRUE", True), (" False ", False),
    ("1", True), ("0", False),
])
def test_booleano_opcional_aceita_so_o_vocabulario_da_graph(bruto, esperado) -> None:
    assert dom.booleano_opcional(bruto, campo="flag") is esperado


@pytest.mark.parametrize("lixo", ["talvez", "yes", "no", "", 2, 1, 0, 1.0, [], {}])
def test_booleano_opcional_recusa_o_resto(lixo) -> None:
    """Contrato mudado deve PARAR a leitura, nao virar palpite."""
    with pytest.raises(dom.ContratoMetaInvalido):
        dom.booleano_opcional(lixo, campo="flag")


def test_flag_string_invalida_recusa_a_leitura_da_conversao() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([{
            "id": "555500003333", "name": "Contrato torto",
            "is_archived": "talvez", "is_unavailable": False,
        }])]})
        with pytest.raises(ErroDeLeituraMeta) as erro:
            await adaptador(cliente).ler_conversoes_personalizadas(
                CONTA, SegredoEfemero(TOKEN))
        assert erro.value.codigo == "META_INVALID_RESPONSE"

    asyncio.run(cenario())


def test_flag_string_false_e_lida_como_booleano_de_verdade() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([{
            "id": "555500004444", "name": "Flags como texto",
            "is_archived": "false", "is_unavailable": "0",
            "last_fired_time": "2026-09-04T10:00:00+0000",
        }])]})
        itens, _ = await adaptador(cliente).ler_conversoes_personalizadas(
            CONTA, SegredoEfemero(TOKEN))
        assert itens[0]["estado"] == dom.ESTADO_DISPONIVEL_COM_DISPARO

    asyncio.run(cenario())


def test_frescor_separa_nunca_disparou_de_carimbo_ausente() -> None:
    """`elif ultimo is None` (adaptador.py:264) era o defeito irmao de A12.

    Tres linhas, tres respostas:

    * `first` E `last` ausentes: assinatura coerente de "nunca disparou" —
      a Graph omite juntos os dois campos nulos que foram pedidos;
    * `first` presente e `last` ausente: CONTRADICAO. O objeto comprovadamente
      disparou; dizer "nunca disparou" seria mentir => UNKNOWN_FRESHNESS;
    * `last` presente com valor vazio: resposta EXPLICITA do provedor.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([
            {"id": "111100001111", "name": "Nunca disparou",
             "is_archived": False, "is_unavailable": False},
            {"id": "111100002222", "name": "Disparou, carimbo sumiu",
             "is_archived": False, "is_unavailable": False,
             "first_fired_time": "2026-08-01T10:00:00+0000"},
            {"id": "111100003333", "name": "Carimbo veio nulo",
             "is_archived": False, "is_unavailable": False,
             "last_fired_time": None},
        ])]})
        itens, _ = await adaptador(cliente).ler_conversoes_personalizadas(
            CONTA, SegredoEfemero(TOKEN))

        assert itens[0]["estado"] == dom.ESTADO_DISPONIVEL_SEM_DISPARO
        assert itens[1]["estado"] == dom.ESTADO_FRESCOR_DESCONHECIDO
        assert itens[1]["motivo_desconhecido"] == dom.MOTIVO_LAST_FIRED_AUSENTE
        assert itens[2]["estado"] == dom.ESTADO_DISPONIVEL_SEM_DISPARO
        assert dom.ESTADO_FRESCOR_DESCONHECIDO != dom.ESTADO_DISPONIVEL_SEM_DISPARO

    asyncio.run(cenario())


# ===========================================================================
# 2. CATALOGO DE FONTES DE MENSURACAO (F22)
# ===========================================================================


def roteiro_de_fontes(linhas: list[Any]) -> dict[str, Any]:
    return {"adaccounts": [contas_visiveis()], "adspixels": [pagina(linhas)]}


def test_shared_pixel_does_not_request_foreign_owner_account_permission() -> None:
    class SharedPixelClient(ClienteGraphFake):
        async def get(self, url, *, params=None, headers=None):
            if url.endswith('/adspixels') and 'owner_ad_account' in (params or {}).get('fields', ''):
                return RespostaFake(403, {'error': {'code': 200}})
            return await super().get(url, params=params, headers=headers)

    async def scenario():
        client = SharedPixelClient(roteiro_de_fontes([{
            'id': '777700001111', 'name': 'Pixel compartilhado',
            'is_unavailable': False, 'last_fired_time': '2026-09-08T00:00:00+0000',
        }]))
        rows, pages = await adaptador(client).ler_fontes_de_mensuracao(CONTA, SegredoEfemero(TOKEN))
        assert len(rows) == 1 and pages == 1
        assert rows[0]['source_kind'] == 'PIXEL'
        assert rows[0]['pertence_a_conta_lida'] is None
    asyncio.run(scenario())


def test_catalogo_de_fontes_devolve_linhas_e_nao_apenas_contagem() -> None:
    """F22: `preflight_conta` guardava `len(linhas)`; o operador precisa das linhas."""
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_fontes([{
            "id": "777700001111", "name": "Pixel do site",
            "is_unavailable": False,
            "last_fired_time": "2026-09-06T12:00:00+0000",
            "owner_ad_account": {"id": f"act_{CONTA}"},
        }]))
        envelope = await adaptador(cliente).catalogo_de_fontes_de_mensuracao(
            ref_da_conta(), SegredoEfemero(TOKEN))

        item = envelope["items"][0]
        assert set(item) == set(AdaptadorMetaSomenteLeitura.CHAVES_DE_FONTE_DE_MENSURACAO)
        assert item["estado"] == dom.ESTADO_DISPONIVEL_COM_DISPARO
        assert item["id_mascarado"] == "••••1111"
        assert item["pertence_a_conta_lida"] is True
        assert item["referencia_opaca"] == dom.referencia_opaca_objeto(
            CONTA, "pixel", "777700001111")
        # O id cru nunca atravessa a projecao browser-facing.
        assert "777700001111" not in str(envelope["items"])
        assert envelope["total"] == 1 and envelope["invalidos"] == 0
        assert "adspixels" in cliente.edges_chamadas()

    asyncio.run(cenario())


def test_pixel_e_dataset_nao_sao_achatados_no_mesmo_tipo() -> None:
    """PIXEL, DATASET e UNKNOWN sao TRES valores, nunca um rotulo so.

    A edge tipada fornece PIXEL sem exigir discriminador redundante.
    Um discriminador explicito desconhecido continua UNKNOWN.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_fontes([
            {"id": "777700001111", "name": "Fonte A", "type": "PIXEL",
             "is_unavailable": False, "last_fired_time": "2026-09-06T12:00:00+0000"},
            {"id": "777700002222", "name": "Fonte B", "source_kind": "dataset",
             "is_unavailable": False, "last_fired_time": "2026-09-06T12:00:00+0000"},
            {"id": "777700003333", "name": "Fonte C",
             "is_unavailable": False, "last_fired_time": "2026-09-06T12:00:00+0000"},
            {"id": "777700004444", "name": "Fonte D", "type": "CONVERSIONS_API",
             "is_unavailable": False, "last_fired_time": "2026-09-06T12:00:00+0000"},
        ]))
        envelope = await adaptador(cliente).catalogo_de_fontes_de_mensuracao(
            ref_da_conta(), SegredoEfemero(TOKEN))
        kinds = [i["source_kind"] for i in envelope["items"]]

        assert kinds == [dom.KIND_PIXEL, dom.KIND_DATASET,
                         dom.KIND_PIXEL, dom.ESTADO_DESCONHECIDO]
        assert dom.KIND_PIXEL != dom.KIND_DATASET
        assert len(set(kinds)) == 3
        assert envelope["items"][0]["motivo_do_source_kind"] is None
        assert envelope["items"][2]["motivo_do_source_kind"] is None
        assert (envelope["items"][3]["motivo_do_source_kind"]
                == dom.MOTIVO_SOURCE_KIND_NAO_RECONHECIDO)
        # O handle NAO segue o kind: se seguisse, o mesmo objeto trocaria de
        # referencia no dia em que a Meta passasse a discriminar.
        assert envelope["items"][0]["referencia_opaca"] == dom.referencia_opaca_objeto(
            CONTA, "pixel", "777700001111")

    asyncio.run(cenario())


def test_fonte_sem_last_fired_time_fica_unknown_freshness() -> None:
    """`AdsPixel` nao tem `first_fired_time`: nao ha com o que cruzar a ausencia."""
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_fontes([
            {"id": "777700001111", "name": "Sem carimbo", "is_unavailable": False},
        ]))
        envelope = await adaptador(cliente).catalogo_de_fontes_de_mensuracao(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["items"][0]["estado"] == dom.ESTADO_FRESCOR_DESCONHECIDO
        assert (envelope["items"][0]["motivo_desconhecido"]
                == dom.MOTIVO_LAST_FIRED_AUSENTE)
        assert not envelope["items"][0]["estado"].startswith("AVAILABLE")

    asyncio.run(cenario())


def test_fonte_sem_is_unavailable_fica_unknown() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_fontes([
            {"id": "777700001111", "name": "Sem flag",
             "last_fired_time": "2026-09-06T12:00:00+0000"},
        ]))
        envelope = await adaptador(cliente).catalogo_de_fontes_de_mensuracao(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["items"][0]["estado"] == dom.ESTADO_DESCONHECIDO
        assert (envelope["items"][0]["motivo_desconhecido"]
                == dom.MOTIVO_IS_UNAVAILABLE_AUSENTE)

    asyncio.run(cenario())


def test_fonte_de_outro_business_nao_e_dada_como_da_conta() -> None:
    """`owner_ad_account` ausente e `None`, nunca `False` — o defeito de A12 de novo."""
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_fontes([
            {"id": "777700001111", "name": "Compartilhado", "is_unavailable": False,
             "last_fired_time": "2026-09-06T12:00:00+0000",
             "owner_ad_account": {"id": f"act_{OUTRA_CONTA}"}},
            {"id": "777700002222", "name": "Dono nao veio", "is_unavailable": False,
             "last_fired_time": "2026-09-06T12:00:00+0000"},
        ]))
        envelope = await adaptador(cliente).catalogo_de_fontes_de_mensuracao(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["items"][0]["pertence_a_conta_lida"] is False
        assert envelope["items"][1]["pertence_a_conta_lida"] is None

    asyncio.run(cenario())


# ===========================================================================
# 3. CATALOGO DE PUBLICOS (F12/F13/F14)
# ===========================================================================


def roteiro_de_publicos(linhas: list[Any], contas: list[str] | None = None) -> dict[str, Any]:
    return {"adaccounts": [contas_visiveis(*(contas or [CONTA]))],
            "customaudiences": [pagina(linhas)]}


def test_publico_nao_deixa_pii_nem_lista_de_membros_atravessar() -> None:
    """A asserção e sobre as CHAVES do dict devolvido, nao sobre inspecao de valor.

    A resposta simulada traz de proposito tudo o que NAO pode sair: lista de
    membros, e-mails, telefones hash, origem do arquivo de cliente e a regra do
    publico. Nada disso tem chave correspondente na projecao — e o teste falha
    se alguem acrescentar uma.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_publicos([{
            "id": "888800001111", "name": "Compradores 180d",
            "subtype": "CUSTOM", "account_id": CONTA,
            "delivery_status": {"code": 200, "description": "Pronto"},
            "operation_status": {"code": 200, "description": "Normal"},
            "approximate_count_lower_bound": 12000,
            "approximate_count_upper_bound": 13000,
            # ↓ tudo abaixo e o que NAO pode atravessar
            "users": ["ana@example.com", "+5541999990000"],
            "customer_file_source": "USER_PROVIDED_ONLY",
            "data_source": {"type": "USER_PROVIDED_ONLY"},
            "rule": "url contains /obrigado",
            "pixel_id": "777700001111",
        }]))
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))
        item = envelope["items"][0]

        assert set(item) == set(AdaptadorMetaSomenteLeitura.CHAVES_DE_PUBLICO)
        for proibida in ("users", "customer_file_source", "data_source", "rule",
                         "pixel_id", "email", "phone", "hash", "members"):
            assert proibida not in item
        for veneno in ("ana@example.com", "+5541999990000",
                       "USER_PROVIDED_ONLY", "/obrigado", "888800001111"):
            assert veneno not in str(envelope["items"])
        assert item["estado"] == dom.ESTADO_DISPONIVEL
        assert item["subtype"] == "CUSTOM"
        assert item["tamanho_aproximado_min"] == 12000
        assert item["id_mascarado"] == "••••1111"

    asyncio.run(cenario())


def test_publico_sem_delivery_status_fica_unknown_e_tamanho_nao_e_inventado() -> None:
    """`CustomAudience` nao tem `is_archived`: a disponibilidade vive no status.

    Ausente => UNKNOWN pela mesma regra do item 1. E um publico sem tamanho
    publicado fica com tamanho `None`: nao pode virar "pequeno demais" nem
    "grande o suficiente" por default. `-1` (nao calculado) tambem nao e tamanho.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_publicos([
            {"id": "888800002222", "name": "Sem status", "subtype": "LOOKALIKE",
             "account_id": CONTA},
            {"id": "888800003333", "name": "Tamanho nao calculado",
             "account_id": CONTA,
             "delivery_status": {"code": 414, "description": "Publico pequeno"},
             "approximate_count_lower_bound": -1,
             "approximate_count_upper_bound": -1},
        ]))
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))

        primeiro, segundo = envelope["items"]
        assert primeiro["estado"] == dom.ESTADO_DESCONHECIDO
        assert primeiro["motivo_desconhecido"] == dom.MOTIVO_DELIVERY_STATUS_AUSENTE
        assert not primeiro["estado"].startswith("AVAILABLE")
        assert primeiro["subtype"] == "LOOKALIKE"       # sem invencao
        assert primeiro["tamanho_aproximado_min"] is None
        assert segundo["estado"] == dom.ESTADO_INDISPONIVEL
        assert segundo["delivery_status_code"] == 414
        assert segundo["tamanho_aproximado_min"] is None

    asyncio.run(cenario())


def test_selecionar_do_catalogo_de_publicos_e_so_get() -> None:
    """Selecionar do catalogo NUNCA cria publico nem lookalike (F14)."""
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_publicos([
            {"id": "888800001111", "name": "Semelhante 1%", "subtype": "LOOKALIKE",
             "account_id": CONTA,
             "delivery_status": {"code": 200, "description": "Pronto"}},
        ]))
        await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))

        # O dublê so implementa `get`: qualquer mutacao teria explodido.
        for verbo in ("post", "put", "patch", "delete", "request"):
            assert not hasattr(cliente, verbo)
        assert cliente.edges_chamadas() == ["adaccounts", "customaudiences"]

    asyncio.run(cenario())


# ===========================================================================
# 4. CATALOGO GEOGRAFICO (F15/F16/F17)
# ===========================================================================


def roteiro_de_geo(linhas: list[Any]) -> dict[str, Any]:
    return {"adaccounts": [contas_visiveis()], "search": [pagina(linhas)]}


def test_geo_texto_livre_nao_vira_key_e_a_key_vem_da_resposta() -> None:
    """"Curitiba" nao e um identificador de cidade; `2418779` e.

    A `key` devolvida AQUI e a chave canonica que o compilador poe em
    `targeting.geo_locations`. Ela sai da RESPOSTA, nunca do que o operador
    digitou — e uma linha sem key legivel vira INVALID em vez de cair para o
    `name` ou para o termo pesquisado.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_geo([
            {"key": "2418779", "name": "Curitiba", "type": "city",
             "country_code": "BR", "region": "Parana",
             "supports_region": True, "supports_city": True},
            {"name": "Curitiba (sem key)", "type": "city", "country_code": "BR"},
        ]))
        envelope = await adaptador(cliente).catalogo_de_geolocalizacoes(
            ref_da_conta(), "Curitiba", SegredoEfemero(TOKEN),
            tipos=("city",), pais="br")

        bom, ruim = envelope["items"]
        assert set(bom) == set(AdaptadorMetaSomenteLeitura.CHAVES_DE_GEOLOCALIZACAO)
        assert bom["key"] == "2418779"
        assert bom["key"] != "Curitiba" and bom["key"] != bom["name"]
        assert ruim["estado"] == dom.ESTADO_INVALIDO
        assert ruim["key"] is None                 # nao caiu para o `name`
        assert envelope["invalidos"] == 1
        # O termo digitado viajou como PERGUNTA (`q`), nunca como identidade.
        busca = cliente.chamadas[-1]
        assert busca["url"].endswith("/search")
        assert busca["params"]["type"] == "adgeolocation"
        assert busca["params"]["q"] == "Curitiba"
        assert busca["params"]["country_code"] == "BR"
        assert "Curitiba" not in [i["key"] for i in envelope["items"] if i["key"]]

    asyncio.run(cenario())


def test_geo_supports_ausente_e_none_e_nao_false() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_geo([
            {"key": "BR", "name": "Brazil", "type": "country"},
        ]))
        envelope = await adaptador(cliente).catalogo_de_geolocalizacoes(
            ref_da_conta(), "Brazil", SegredoEfemero(TOKEN), tipos=("country",))

        item = envelope["items"][0]
        assert item["supports_region"] is None
        assert item["supports_city"] is None
        assert item["estado"] == dom.ESTADO_DISPONIVEL

    asyncio.run(cenario())


def test_geo_tipo_nao_registrado_e_recusado_antes_de_qualquer_rede() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_geo([]))
        with pytest.raises(dom.ContratoMetaInvalido):
            await adaptador(cliente).buscar_geolocalizacoes(
                "Batel", ("bairro_inventado",), SegredoEfemero(TOKEN))
        assert cliente.chamadas == []

    asyncio.run(cenario())


def test_geo_termo_vazio_e_recusado() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_geo([]))
        with pytest.raises(dom.ContratoMetaInvalido):
            await adaptador(cliente).buscar_geolocalizacoes(
                "   ", ("city",), SegredoEfemero(TOKEN))
        assert cliente.chamadas == []

    asyncio.run(cenario())


# ===========================================================================
# 5. A11 — CINCO SITUACOES, CINCO RESPOSTAS DISTINTAS
# ===========================================================================


def test_catalogo_vazio_completo_e_um_estado_proprio() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_publicos([]))
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["ok"] is True
        assert envelope["estado"] == "VAZIO_COMPLETO"
        assert envelope["completo"] is True
        assert envelope["motivo"] is None
        assert envelope["total"] == 0
        assert envelope["estado_do_catalogo"] == dom.CATALOGO_VIGENTE

    asyncio.run(cenario())


def test_permissao_negada_nao_se_parece_com_catalogo_vazio() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({
            "adaccounts": [contas_visiveis()],
            "customaudiences": [{"__status": 403, "error": {"message": TOKEN}}],
        })
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["ok"] is False
        assert envelope["estado"] == "INDISPONIVEL"
        assert envelope["motivo"] == "META_PERMISSIONS_INSUFFICIENT"
        assert envelope["retryable"] is False
        assert envelope["completo"] is False
        assert envelope["estado"] != "VAZIO_COMPLETO"
        assert TOKEN not in str(envelope)

    asyncio.run(cenario())


def test_timeout_nao_se_parece_com_permissao_negada_nem_com_vazio() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({
            "adaccounts": [contas_visiveis()],
            "customaudiences": httpx.ReadTimeout("segredo-no-timeout"),
        })
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["ok"] is False
        assert envelope["estado"] == "INDISPONIVEL"
        assert envelope["motivo"] == "META_TRANSPORT_FAILURE"
        # E o que separa timeout de permissao negada: um se tenta de novo.
        assert envelope["retryable"] is True
        assert envelope["motivo"] != "META_PERMISSIONS_INSUFFICIENT"
        assert "segredo-no-timeout" not in str(envelope)

    asyncio.run(cenario())


def test_paginacao_incompleta_e_sinalizada_e_nao_silenciada() -> None:
    """`items: []` com `completo=False` NAO e um catalogo vazio.

    O teto de paginas e atingido no modo estrito, que levanta em vez de
    entregar meia lista como se fosse a lista. O envelope registra PARCIAL: o
    operador ve "existe mais do que voce esta vendo", nunca "nao ha nada".
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake({
            "adaccounts": [contas_visiveis()],
            "customaudiences": [pagina(
                [{"id": "888800001111", "name": "P1", "account_id": CONTA,
                  "delivery_status": {"code": 200, "description": "Pronto"}}],
                after="cursor-1")],
        })
        envelope = await adaptador(
            cliente, max_paginas_por_edge=1,
        ).catalogo_de_publicos(ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["estado"] == "PARCIAL"
        assert envelope["completo"] is False
        assert envelope["motivo"] == "META_PAGINATION_LIMIT"
        assert envelope["estado"] != "VAZIO_COMPLETO"
        assert envelope["estado"] != "INDISPONIVEL"

    asyncio.run(cenario())


def test_leitura_obsoleta_e_marcada_visivel_e_nunca_rebuscada_em_silencio() -> None:
    """Frescor e DADO, nao cache. Nao existe TTL de armazenamento nesta lane.

    A releitura do estado usa APENAS o instante que o proprio envelope carrega:
    zero chamadas novas, itens intactos, e o rotulo muda para OBSOLETO. Marcar
    e diferente de esconder — e diferente de buscar de novo por conta propria.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_publicos([
            {"id": "888800001111", "name": "P1", "account_id": CONTA,
             "delivery_status": {"code": 200, "description": "Pronto"}},
        ]))
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN), ttl_s=300)
        chamadas_apos_leitura = len(cliente.chamadas)

        assert envelope["ttl_s"] == 300
        assert envelope["estado_do_catalogo"] == dom.CATALOGO_VIGENTE

        observado = datetime.fromisoformat(envelope["observado_em"])
        vencido = dom.reavaliar_frescor(
            envelope, agora=observado + timedelta(seconds=301))

        assert vencido["estado_do_catalogo"] == dom.CATALOGO_OBSOLETO
        assert vencido["items"] == envelope["items"]      # marcado, nao escondido
        assert vencido["estado"] == "COM_ITENS"           # eixo ORTOGONAL ao vazio
        assert len(cliente.chamadas) == chamadas_apos_leitura   # nada re-buscado
        # E dentro do prazo continua vigente: o rotulo nao e decorativo.
        assert dom.reavaliar_frescor(
            envelope, agora=observado + timedelta(seconds=299),
        )["estado_do_catalogo"] == dom.CATALOGO_VIGENTE

    asyncio.run(cenario())


# ===========================================================================
# 6. ROBUSTEZ POR ITEM
# ===========================================================================


def test_item_invalido_nao_derruba_a_pagina_mas_e_contado() -> None:
    """Um item podre vira LINHA INVALID; "li tudo" nao vira "li o que deu"."""
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiro_de_publicos([
            {"id": "888800001111", "name": "Bom", "account_id": CONTA,
             "delivery_status": {"code": 200, "description": "Pronto"}},
            {"id": "nao-e-numero", "name": "Id ilegivel"},
            "isto nem e um documento",
            {"id": "888800002222", "name": "Tambem bom", "account_id": CONTA,
             "delivery_status": {"code": 200, "description": "Pronto"}},
        ]))
        envelope = await adaptador(cliente).catalogo_de_publicos(
            ref_da_conta(), SegredoEfemero(TOKEN))

        assert envelope["total"] == 4
        assert envelope["invalidos"] == 2
        assert envelope["completo"] is True
        estados = [i["estado"] for i in envelope["items"]]
        assert estados == [dom.ESTADO_DISPONIVEL, dom.ESTADO_INVALIDO,
                           dom.ESTADO_INVALIDO, dom.ESTADO_DISPONIVEL]
        # Item invalido nao tem handle: e inerte por construcao, nao selecionavel.
        assert envelope["items"][1]["referencia_opaca"] is None
        assert (envelope["items"][1]["motivo_desconhecido"]
                == dom.MOTIVO_CONTRATO_DO_ITEM_INVALIDO)
        # E a forma da linha nao muda, para a UI nao quebrar ao renderizar.
        assert set(envelope["items"][2]) == set(
            AdaptadorMetaSomenteLeitura.CHAVES_DE_PUBLICO)

    asyncio.run(cenario())


def test_conversoes_personalizadas_continuam_levantando_em_item_malformado() -> None:
    """O outro lado, deliberadamente NAO alterado.

    `ler_conversoes_personalizadas` ja existia e ja tinha consumidor
    (`preflight_conta`, adaptador.py:153). Trocar "levanta" por "linha INVALID"
    ali mudaria, sem pedido, o significado de `contagens['custom_conversion']`
    no preflight — que hoje e `None` quando a leitura falhou. Os catalogos NOVOS
    nascem tolerantes; o antigo segue estrito, e este teste guarda a diferenca.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customconversions": [pagina([
            {"id": "555500001111", "name": "Boa", "is_archived": False,
             "is_unavailable": False, "last_fired_time": "2026-09-04T10:00:00+0000"},
            {"id": "nao-e-numero", "name": "Podre"},
        ])]})
        with pytest.raises(ErroDeLeituraMeta) as erro:
            await adaptador(cliente).ler_conversoes_personalizadas(
                CONTA, SegredoEfemero(TOKEN))
        assert erro.value.codigo == "META_INVALID_RESPONSE"

    asyncio.run(cenario())


# ===========================================================================
# 7. A13 — ISOLAMENTO
# ===========================================================================


def test_referencia_opaca_de_outra_conta_nao_resolve_e_nao_chega_a_rede() -> None:
    """O isolamento vem da RELEITURA das contas acessiveis, nao de um `if`."""
    async def cenario() -> None:
        for metodo, argumentos in (
            ("catalogo_de_publicos", ()),
            ("catalogo_de_fontes_de_mensuracao", ()),
            ("catalogo_de_conversoes_personalizadas", ()),
        ):
            cliente = ClienteGraphFake({
                "adaccounts": [contas_visiveis(CONTA)],
                "customaudiences": [pagina([])],
                "adspixels": [pagina([])],
                "customconversions": [pagina([])],
            })
            alvo = getattr(adaptador(cliente), metodo)
            with pytest.raises(dom.ContratoMetaInvalido, match="referencia opaca"):
                await alvo(ref_da_conta(OUTRA_CONTA), SegredoEfemero(TOKEN), *argumentos)
            # A conta foi relida; a edge do catalogo nem chegou a ser chamada.
            assert cliente.edges_chamadas() == ["adaccounts"]

    asyncio.run(cenario())


def test_referencia_opaca_de_objeto_e_escopada_por_conta() -> None:
    """O MESMO id externo em duas contas produz handles diferentes."""
    daqui = dom.referencia_opaca_objeto(CONTA, "custom_audience", "888800001111")
    de_la = dom.referencia_opaca_objeto(OUTRA_CONTA, "custom_audience", "888800001111")
    assert daqui != de_la
    # E o tipo tambem escopa: publico e pixel nao colidem.
    assert daqui != dom.referencia_opaca_objeto(CONTA, "pixel", "888800001111")


# ===========================================================================
# 8. RESOLUCAO SERVER-ONLY DE REFERENCIA -> ID CRU
# ===========================================================================


def test_resolver_ids_traduz_handle_da_propria_conta() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customaudiences": [pagina([
            {"id": "888800001111"}, {"id": "888800002222"},
        ])]})
        alvo = dom.referencia_opaca_objeto(CONTA, "custom_audience", "888800002222")
        indice = await adaptador(cliente).resolver_ids_por_referencia(
            CONTA, "custom_audience", [alvo], SegredoEfemero(TOKEN))

        assert indice == {alvo: "888800002222"}

    asyncio.run(cenario())


def test_resolver_ids_ignora_handle_de_outra_conta() -> None:
    """A13 pelo caminho do compilador: o handle de la nao esta na lista de ca."""
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customaudiences": [pagina([
            {"id": "888800001111"},
        ])]})
        de_la = dom.referencia_opaca_objeto(
            OUTRA_CONTA, "custom_audience", "888800001111")
        daqui = dom.referencia_opaca_objeto(CONTA, "custom_audience", "888800001111")

        indice = await adaptador(cliente).resolver_ids_por_referencia(
            CONTA, "custom_audience", [de_la, daqui], SegredoEfemero(TOKEN))

        assert de_la not in indice
        assert indice == {daqui: "888800001111"}

    asyncio.run(cenario())


def test_resolver_ids_recalcula_e_ignora_referencia_vinda_no_corpo() -> None:
    """Confiar na referencia do corpo deixaria a resposta escolher a que id mapear."""
    async def cenario() -> None:
        mentira = dom.referencia_opaca_objeto(CONTA, "custom_audience", "888800009999")
        cliente = ClienteGraphFake({"customaudiences": [pagina([
            {"id": "888800001111", "referencia_opaca": mentira},
        ])]})
        indice = await adaptador(cliente).resolver_ids_por_referencia(
            CONTA, "custom_audience", [mentira], SegredoEfemero(TOKEN))

        assert indice == {}     # a referencia recalculada e a que vale

    asyncio.run(cenario())


def test_resolver_ids_recusa_tipo_fora_do_vocabulario() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customaudiences": [pagina([])]})
        with pytest.raises(dom.ContratoMetaInvalido):
            await adaptador(cliente).resolver_ids_por_referencia(
                CONTA, "adset", ["metaobj_qualquer"], SegredoEfemero(TOKEN))
        assert cliente.chamadas == []

    asyncio.run(cenario())


def test_resolver_ids_sem_referencias_nao_custa_leitura() -> None:
    """Compilar sem selecao nao pode gastar uma chamada a Graph."""
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customaudiences": [pagina([{"id": "1"}])]})
        for vazio in ([], (), ["", "   "]):
            indice = await adaptador(cliente).resolver_ids_por_referencia(
                CONTA, "custom_audience", vazio, SegredoEfemero(TOKEN))
            assert indice == {}
        assert cliente.chamadas == []

    asyncio.run(cenario())


def test_resolver_ids_pula_item_ilegivel_sem_perder_os_outros() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customaudiences": [pagina([
            {"id": "nao-e-numero"},
            "nem documento e",
            {"id": "888800002222"},
        ])]})
        alvo = dom.referencia_opaca_objeto(CONTA, "custom_audience", "888800002222")
        indice = await adaptador(cliente).resolver_ids_por_referencia(
            CONTA, "custom_audience", [alvo], SegredoEfemero(TOKEN))

        assert indice == {alvo: "888800002222"}

    asyncio.run(cenario())


def test_resolver_ids_ausente_devolve_dicionario_sem_levantar() -> None:
    """"Nao achei" e "nao sei ler" continuam sendo erros diferentes.

    A ausencia e devolvida como buraco no dicionario; quem a transforma em
    META_AUDIENCE_REFERENCE_UNRESOLVED e o chamador. Ja "nao sei ler" continua
    sendo ErroDeLeituraMeta, levantado pelo transporte.
    """
    async def cenario() -> None:
        cliente = ClienteGraphFake({"customaudiences": [pagina([{"id": "888800001111"}])]})
        fantasma = dom.referencia_opaca_objeto(
            CONTA, "custom_audience", "888800007777")
        indice = await adaptador(cliente).resolver_ids_por_referencia(
            CONTA, "custom_audience", [fantasma], SegredoEfemero(TOKEN))
        assert indice == {}

        ruim = ClienteGraphFake({"customaudiences": httpx.ReadTimeout("x")})
        with pytest.raises(ErroDeLeituraMeta):
            await adaptador(ruim).resolver_ids_por_referencia(
                CONTA, "custom_audience", [fantasma], SegredoEfemero(TOKEN))

    asyncio.run(cenario())


def test_resolver_ids_cobre_pixel_e_custom_conversion_nas_edges_certas() -> None:
    async def cenario() -> None:
        for tipo, edge, identificador in (
            ("pixel", "adspixels", "777700001111"),
            ("custom_conversion", "customconversions", "555500001111"),
        ):
            cliente = ClienteGraphFake({edge: [pagina([{"id": identificador}])]})
            alvo = dom.referencia_opaca_objeto(CONTA, tipo, identificador)
            indice = await adaptador(cliente).resolver_ids_por_referencia(
                CONTA, tipo, [alvo], SegredoEfemero(TOKEN))

            assert indice == {alvo: identificador}
            assert cliente.edges_chamadas() == [edge]

    asyncio.run(cenario())
