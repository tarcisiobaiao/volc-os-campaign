"""Hermetic measurement preflight: negative evidence is not unknown metadata."""
import asyncio
from types import SimpleNamespace

import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta.adaptador import ErroDeLeituraMeta
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.contrato_v2 import MensuracaoMeta
from app.trafego.meta_execucao.publicos import resolver_referencias_de_publico
from test_meta_catalogos_selecionaveis import ClienteGraphFake, pagina, adaptador, CONTA, TOKEN
from test_meta_contrato_v2 import _plano_v2, _conjunto

PIXEL = "777700001111"
CONVERSION = "555500001111"


@pytest.mark.parametrize("tipo,edge,flags", [
    ("pixel", "adspixels", {"is_unavailable": True}),
    ("custom_conversion", "customconversions", {"is_unavailable": True}),
    ("custom_conversion", "customconversions", {"is_archived": True}),
])
def test_explicit_negative_selection_is_rejected_without_exposing_ids(tipo, edge, flags):
    async def scenario():
        reader = adaptador(ClienteGraphFake({edge: [pagina([{"id": PIXEL, **flags}])]}))
        ref = dom.referencia_opaca_objeto(CONTA, tipo, PIXEL)
        with pytest.raises(ErroDeLeituraMeta) as caught:
            await reader.resolver_ids_por_referencia(CONTA, tipo, [ref], SegredoEfemero(TOKEN))
        assert caught.value.codigo == "META_MEASUREMENT_SELECTION_UNAVAILABLE"
        assert PIXEL not in str(caught.value)
        assert CONTA not in str(caught.value)
    asyncio.run(scenario())


@pytest.mark.parametrize("source,should_fail", [(PIXEL, False), ("777700002222", True), (None, False), ("invalid", False)])
def test_conversion_source_binding_is_checked_when_known_without_extra_requests(source, should_fail):
    async def scenario():
        source_ref = dom.referencia_opaca_objeto(CONTA, "pixel", PIXEL)
        conversion_ref = dom.referencia_opaca_objeto(CONTA, "custom_conversion", CONVERSION)
        measurement = MensuracaoMeta(proposito="OPTIMIZE", source_kind="PIXEL",
            source_ref=source_ref, custom_conversion_ref=conversion_ref)
        plan = _plano_v2(recipe_id="WEB_SALES_CONVERSION", conjuntos=(_conjunto(mensuracao=measurement),))
        client = ClienteGraphFake({
            "adspixels": [pagina([{"id": PIXEL}])],
            "customconversions": [pagina([{"id": CONVERSION, "event_source_id": source}])],
        })
        reader = adaptador(client)
        async def accounts(_):
            return (SimpleNamespace(referencia_opaca=plan.account_ref, id_externo=CONTA),)
        reader.descobrir_contas = accounts
        async def resolve():
            return await resolver_referencias_de_publico(None, plano=plan,
                account_ref=plan.account_ref, segredo=SegredoEfemero(TOKEN), catalogo=reader)
        if should_fail:
            with pytest.raises(ErroDeNascimentoMeta) as caught:
                await resolve()
            assert caught.value.codigo == "META_MEASUREMENT_SOURCE_MISMATCH"
            assert PIXEL not in str(caught.value)
        else:
            result = await resolve()
            assert result.fonte(source_ref) == PIXEL
            assert result.conversao(conversion_ref) == CONVERSION
        assert client.edges_chamadas() == ["adspixels", "customconversions"]
    asyncio.run(scenario())


def test_unselected_archived_conversion_does_not_block_valid_selection():
    async def scenario():
        client = ClienteGraphFake({"customconversions": [pagina([
            {"id": "555500009999", "is_archived": True}, {"id": CONVERSION},
        ])]})
        ref = dom.referencia_opaca_objeto(CONTA, "custom_conversion", CONVERSION)
        result = await adaptador(client).resolver_ids_por_referencia(CONTA, "custom_conversion", [ref], SegredoEfemero(TOKEN))
        assert result == {ref: CONVERSION}
    asyncio.run(scenario())


def test_read_refusal_is_translated_to_domain_error_before_compilation():
    from app.trafego.meta_execucao.publicos import _resolver_mensuracao
    async def scenario():
        reader = adaptador(ClienteGraphFake({"customconversions": [pagina([
            {"id": CONVERSION, "is_archived": True},
        ])]}))
        ref = dom.referencia_opaca_objeto(CONTA, "custom_conversion", CONVERSION)
        with pytest.raises(ErroDeNascimentoMeta) as caught:
            await _resolver_mensuracao(reader, CONTA, "custom_conversion", [ref], SegredoEfemero(TOKEN), "conversões")
        assert caught.value.codigo == "META_MEASUREMENT_SELECTION_UNAVAILABLE"
    asyncio.run(scenario())
