"""As imagens de Display atravessando o HTTP — e o silêncio que isso encerra.

Até 01/09/2026 `ProvarEntrada` não tinha campo de imagem e o brief de Display
saía com `imagens_display=None` sempre. Um pedido de Display por HTTP produzia,
por construção, um plano sem asset nenhum — e respondia 200. A tela mostrava
prontidão para um anúncio que a API recusaria.

O que estes testes protegem não é "existe um campo": é que a AUSÊNCIA de imagem
volta a ser um estado nomeado, com três frases diferentes para três ausências
diferentes, antes de qualquer chamada ao Google.
"""
from __future__ import annotations

import base64
import hashlib
import struct

import pytest
from pydantic import ValidationError

from app.routers import trafego


def _png(largura: int, altura: int, nome: str) -> bytes:
    """O mesmo cabeçalho PNG mínimo que as provas de Demand Gen já usam."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", largura, altura)
        + b"\x08\x06\x00\x00\x00"
        + nome.encode()
    )


def _asset(tipo: str, nome: str, largura: int, altura: int) -> dict:
    dados = _png(largura, altura, nome)
    return {
        "tipo": tipo,
        "nome": nome,
        "dados_base64": base64.b64encode(dados).decode(),
        "conteudo_hash": "sha256:" + hashlib.sha256(dados).hexdigest(),
        "origem": "gerado",
        "procedencia": {
            "motor": "fixture-hermetica",
            "versao_do_motor": "1",
            "insumo": f"gerar {nome}",
            "quando": "2026-08-29T12:00:00+00:00",
        },
    }


def _corpo(**extra) -> dict:
    base = {
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "DISPLAY",
        "estrategia_lance": "MAXIMIZE_CONVERSIONS",
    }
    base.update(extra)
    return base


# ── o campo existe, e pertence a Display ────────────────────────────────────


def test_o_envelope_de_display_carrega_imagens():
    body = trafego.ProvarEntrada.model_validate(_corpo(
        assets_display=[_asset("imagem_marketing", "banner", 600, 314)]))
    assert body.assets_display is not None
    assert len(body.assets_display) == 1


def test_assets_display_em_search_e_recusado_e_nao_ignorado():
    """O modelo é compartilhado e permissivo por compatibilidade Search. Sem
    esta guarda, um pedido de Search com imagens seria ACEITO e as imagens
    sumiriam — o operador teria mandado peças e visto um plano sem nenhuma."""
    with pytest.raises(ValidationError, match="exige `canal=DISPLAY`"):
        trafego.ProvarEntrada.model_validate(_corpo(
            canal="SEARCH",
            assets_display=[_asset("imagem_marketing", "banner", 600, 314)]))


def test_assets_display_em_demand_gen_tambem_e_recusado():
    with pytest.raises(ValidationError, match="exige `canal=DISPLAY`"):
        trafego.ProvarEntrada.model_validate(_corpo(
            canal="DEMAND_GEN",
            assets_display=[_asset("imagem_marketing", "banner", 600, 314)]))


# ── três ausências, três frases ─────────────────────────────────────────────


def test_display_sem_campo_de_imagem_recusa_antes_do_google():
    """Ausência do campo: o pedido não falou de imagem."""
    body = trafego.ProvarEntrada.model_validate(_corpo())
    assert body.assets_display is None
    with pytest.raises(ValueError, match="não trouxe nenhuma"):
        trafego._imagens_de_display(body, nicho="fixture")


def test_display_com_lista_vazia_recusa_com_outra_frase():
    """Lista vazia: o pedido DECLAROU que não há imagem. É outra coisa, e pede
    outra ação — a primeira é corrigir o pedido, esta é esperar a produção."""
    body = trafego.ProvarEntrada.model_validate(_corpo(assets_display=[]))
    assert body.assets_display == []
    with pytest.raises(ValueError, match="VAZIO"):
        trafego._imagens_de_display(body, nicho="fixture")


def test_as_duas_ausencias_nao_dizem_a_mesma_coisa():
    sem = trafego.ProvarEntrada.model_validate(_corpo())
    vazio = trafego.ProvarEntrada.model_validate(_corpo(assets_display=[]))
    with pytest.raises(ValueError) as a:
        trafego._imagens_de_display(sem, nicho="fixture")
    with pytest.raises(ValueError) as b:
        trafego._imagens_de_display(vazio, nicho="fixture")
    assert str(a.value) != str(b.value)


def test_lote_reprovado_pela_ponte_recusa_com_o_veredito_dela():
    """Terceira ausência: mandou imagens, e elas não servem. A frase carrega o
    resumo da ponte, e não uma tradução local — traduzir criaria uma segunda
    autoridade sobre o contrato do Estúdio."""
    body = trafego.ProvarEntrada.model_validate(_corpo(
        # 10x10 não atende a geometria mínima de nenhum papel de Display.
        assets_display=[_asset("imagem_marketing", "pequena", 10, 10)]))
    with pytest.raises(ValueError, match="recusados pela fronteira do Estúdio"):
        trafego._imagens_de_display(body, nicho="fixture")


# ── o caminho feliz: as imagens chegam separadas por papel ──────────────────


def test_lote_valido_vira_imagens_display_com_papel():
    body = trafego.ProvarEntrada.model_validate(_corpo(assets_display=[
        _asset("imagem_marketing", "banner", 600, 314),
        _asset("imagem_marketing_quadrada", "quadrada", 300, 300),
    ]))
    # ⚠️ Devolve DOIS valores desde 01/09/2026: as imagens e os avisos da ponte.
    # Os avisos existem porque a ponte aceita `NAO_DECLARADA` em destino de
    # produção como dívida consciente, e a contrapartida dessa dívida é o asset
    # sem procedência sair NOMEADO. Descartá-los aqui desfaria a troca.
    imagens, avisos = trafego._imagens_de_display(body, nicho="fixture")
    assert imagens is not None
    # A fixture não declara natureza, então a ponte tem o que avisar — e o
    # aviso precisa chegar com código, não como frase solta.
    assert all(a.codigo == "ASSET_SEM_PROCEDENCIA" for a in avisos)
    # ⚠️ O papel é DECLARADO, nunca adivinhado pela ordem da lista: subir a
    # quadrada no campo do banner faria a API recusar o mutate inteiro por
    # proporção, com um erro apontando para o anúncio e não para quem montou.
    assert len(imagens.marketing) == 1
    assert len(imagens.marketing_quadrada) == 1
    assert not imagens.logo


# ── os tetos da fronteira ───────────────────────────────────────────────────


def test_o_teto_de_quantidade_de_display_vem_do_limite_da_api():
    """15 imagens de marketing (combinadas) + 5 logos (combinadas) = 20. O
    número não foi escolhido no router; ele está declarado em
    `brief.ImagensDisplay` como o teto do ResponsiveDisplayAdInfo."""
    assert trafego.TETO_QUANTIDADE_ASSETS_DISPLAY == 20


def test_o_teto_de_quantidade_e_cobrado_antes_de_decodificar(monkeypatch):
    monkeypatch.setattr(trafego, "TETO_QUANTIDADE_ASSETS_DISPLAY", 1)
    itens = [
        trafego.AssetDemandGenEntrada.model_validate(
            _asset("imagem_marketing", "a", 600, 314)),
        trafego.AssetDemandGenEntrada.model_validate(
            _asset("imagem_marketing", "b", 600, 314)),
    ]
    with pytest.raises(ValueError, match="assets_display excede o teto"):
        list(trafego._assets_decodificados_display(itens))


def test_o_decodificador_de_display_nao_herda_o_teto_de_demand_gen(monkeypatch):
    """Os tetos de bytes coincidem hoje porque protegem a MESMA memória, e não
    porque um deriva do outro. Mexer num não pode mexer no outro."""
    monkeypatch.setattr(trafego, "TETO_BYTES_ASSET_DEMAND_GEN", 1)
    item = trafego.AssetDemandGenEntrada.model_validate(
        _asset("imagem_marketing", "a", 600, 314))
    assert list(trafego._assets_decodificados_display([item]))


# ── a identidade do plano ───────────────────────────────────────────────────
#
# ⚠️ ESTES DOIS TESTES EXISTEM POR UM DEFEITO QUE EU INTRODUZI E REPRODUZI.
#
# Declarar `assets_display` no modelo bastou para mudar a impressão de TODO
# plano Search: `model_dump(exclude_none=False)` inclui a chave com `null`, e a
# chave do canário passou de `e0ccfc66…` para `68d83100…` sem uma linha do
# pedido ter mudado. Em teste isso é vermelho. Na conta real seria outra marca
# `VOLC-CANARY-` e outra chave de idempotência — as duas defesas contra a
# segunda campanha procurando um valor inexistente ao mesmo tempo.


def _impressao(corpo: dict) -> str:
    body = trafego.ProvarEntrada.model_validate(corpo)
    return trafego._impressao_aprovavel(
        body, cid="8017851692", mid="6016739364")


def test_campo_ausente_nao_muda_a_identidade_de_um_plano_search():
    """Um campo que o plano não usa não pode mudar a identidade dele."""
    corpo = {
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "SEARCH",
    }
    plano = trafego._plano_aprovavel(
        trafego.ProvarEntrada.model_validate(corpo),
        cid="8017851692", mid="6016739364")
    assert "assets_display" not in plano


def test_imagem_presente_entra_na_identidade():
    """Trocar uma imagem entre a prova e a escrita precisa invalidar a
    autorização, exatamente como trocar uma headline invalida."""
    base = _corpo(assets_display=[_asset("imagem_marketing", "banner", 600, 314)])
    outra = _corpo(assets_display=[_asset("imagem_marketing", "outra", 600, 314)])
    assert _impressao(base) != _impressao(outra)


def test_o_mesmo_pedido_com_imagem_tem_a_mesma_identidade():
    corpo = _corpo(assets_display=[
        _asset("imagem_marketing", "banner", 600, 314)])
    assert _impressao(corpo) == _impressao(corpo)


def test_a_lista_de_campos_tardios_e_declarada_e_pequena():
    """Ela não é uma porta para 'campos que não importam': cada nome aqui é um
    campo que não existia quando uma chave já emitida foi calculada."""
    assert trafego.CAMPOS_QUE_SO_ENTRAM_NA_IDENTIDADE_QUANDO_EXISTEM == (
        "assets_display",)
