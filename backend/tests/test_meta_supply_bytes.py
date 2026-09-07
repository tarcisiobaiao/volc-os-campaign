"""O gate técnico da peça Meta: bytes, não cabeçalho.

## O defeito que estas provas fecham

`FINDINGS.json:F01` (P0, reproduzido hermeticamente pelo probe P02): o gate lia
`Content-Type`, conferia o tamanho total e hasheava. Um corpo com o literal
``NOT_AN_IMAGE`` rotulado ``image/png`` era selado como `AUTHORIZED` /
`READY_FOR_PAID_MEDIA`, e as dimensões vinham DECLARADAS pelo inventário. O
recibo passava a afirmar uma inspeção que nunca tinha acontecido — e ele viaja
até a aprovação durável, onde a migration confere só a FORMA do recibo, nunca
os bytes.

⚠️ Nenhum teste aqui toca conta Meta. Todo tráfego é `httpx.MockTransport`, e o
que se prova é o comportamento do gate diante de bytes controlados.

## O que estas provas NÃO afirmam

Que a peça esteja livre de marca, logotipo ou identidade de terceiro. A
decodificação prova FORMA — que os bytes são uma imagem real destas dimensões —
e nunca CONTEÚDO. Essa outra pergunta é da atestação humana, e nenhuma das duas
substitui a outra.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

import imagens_meta
from app.trafego.meta import dominio as meta_dom
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao import ativos as mod_ativos
from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
from app.trafego.meta_execucao.contrato import (
    ORIGEM_BIBLIOTECA,
    ORIGEM_MINIATURA,
    DeclaracaoPoliticaAtivoMeta,
    ErroDeNascimentoMeta,
)


TOKEN = "token-hermetico-nao-registrar"
ATOR = "operador-um"
CONTA = "1234567890"
IMAGEM_URL = "https://scontent.example.fbcdn.net/peca.png"


def _declaracao(**mudancas: Any) -> DeclaracaoPoliticaAtivoMeta:
    base: dict[str, Any] = dict(
        direitos_confirmados=True,
        identidade_de_terceiro_liberada=True,
        confirmada_em=datetime.now(timezone.utc),
    )
    base.update(mudancas)
    return DeclaracaoPoliticaAtivoMeta(**base)  # type: ignore[arg-type]


def _transporte(
    *,
    corpo: bytes,
    content_type: str = "image/png",
    status: int = 200,
    largura_declarada: int | None = 1080,
    altura_declarada: int | None = 1080,
    usar_miniatura: bool = False,
):
    """Uma conta com uma Página e uma imagem, e o CDN devolvendo `corpo`."""

    async def responder(request: httpx.Request) -> httpx.Response:
        caminho = request.url.path
        if caminho.endswith("/me/adaccounts"):
            return httpx.Response(200, json={"data": [{
                "id": f"act_{CONTA}", "name": "Conta", "currency": "BRL",
                "account_status": 1,
            }]})
        if caminho.endswith("/promote_pages"):
            return httpx.Response(200, json={"data": [{"id": "2222222222", "name": "Pagina"}]})
        if caminho.endswith("/adimages"):
            item: dict[str, Any] = {"hash": "hashImagem_123456", "name": "Peca"}
            if largura_declarada is not None:
                item["width"] = largura_declarada
            if altura_declarada is not None:
                item["height"] = altura_declarada
            # `url` é a peça; `url_128` é a miniatura. A escolha decide a origem
            # que o manifesto vai declarar.
            item["url_128" if usar_miniatura else "url"] = IMAGEM_URL
            return httpx.Response(200, json={"data": [item]})
        if caminho.endswith("/advideos"):
            return httpx.Response(200, json={"data": []})
        if request.url.host.endswith(".fbcdn.net"):
            return httpx.Response(
                status, content=corpo, headers={"content-type": content_type})
        raise AssertionError(request.url)

    return httpx.MockTransport(responder)


async def _resolver(transporte, *, declaracao: DeclaracaoPoliticaAtivoMeta | None = None):
    async with httpx.AsyncClient(transport=transporte, follow_redirects=False) as cliente:
        resolvedor = ResolvedorAtivosMeta(cliente)
        inventario = await resolvedor.inventariar(
            meta_dom.referencia_opaca_conta(CONTA), SegredoEfemero(TOKEN))
        asset_ref = inventario["imagens"][0]["referencia_opaca"]
        return await resolvedor.resolver_lote(
            account_ref=inventario["account_ref"],
            page_ref=inventario["paginas"][0]["referencia_opaca"],
            asset_refs=(asset_ref,),
            segredo=SegredoEfemero(TOKEN),
            ator=ATOR,
            declaracoes={asset_ref: declaracao or _declaracao()},
        )


# ---------------------------------------------------------------------------
# RECUSAS — cada uma por uma causa diferente, com nome próprio
# ---------------------------------------------------------------------------

async def test_not_an_image_rotulado_png_e_recusado_antes_de_ready() -> None:
    """A reprodução exata de F01/P02: o cabeçalho mente e o gate não acredita."""
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(_transporte(
            corpo=imagens_meta.NAO_E_IMAGEM, content_type="image/png"))
    assert erro.value.codigo == "META_ASSET_BYTES_NOT_DECODABLE"


async def test_imagem_truncada_abre_mede_e_ainda_assim_e_recusada() -> None:
    """Cabeçalho válido não é imagem íntegra.

    Este caso é o que separa "sniff de assinatura" de "decodificação": os
    primeiros bytes são um PNG legítimo e a dimensão sai do cabeçalho. Só o
    `load()` descobre que os pixels não estão todos lá.
    """
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(_transporte(corpo=imagens_meta.png_truncado()))
    assert erro.value.codigo in {
        "META_ASSET_BYTES_TRUNCATED", "META_ASSET_BYTES_NOT_DECODABLE"}


async def test_mime_divergente_do_formato_decodificado_e_recusado() -> None:
    """`image/png` no cabeçalho e JPEG nos bytes: os dois não podem ser verdade."""
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(_transporte(
            corpo=imagens_meta.jpeg(320, 240), content_type="image/png"))
    assert erro.value.codigo == "META_ASSET_MIME_DIVERGED"


async def test_bomba_de_pixels_morre_antes_de_decodificar() -> None:
    """O teto de BYTES não alcança este ataque; o teto de PIXELS alcança.

    12000x12000 em branco comprime para cerca de 157 KiB — passa folgado nos
    12 MB — e declara 144 milhões de pixels. A dimensão sai do cabeçalho, e é
    julgada antes de qualquer `load()`.
    """
    bomba = imagens_meta.bomba_de_pixels()
    assert len(bomba) < mod_ativos.LIMITE_DE_BYTES, (
        "a bomba precisa passar no teto de bytes, senão o teste mede o limite errado")
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(_transporte(corpo=bomba))
    assert erro.value.codigo == "META_ASSET_PIXELS_EXCEEDED"


async def test_corpo_que_excede_o_limite_e_cortado_durante_o_streaming(monkeypatch) -> None:
    """O teto é cobrado DURANTE a leitura, não depois de o corpo inteiro chegar.

    A prova é o número de bytes efetivamente acumulados: com o teto rebaixado, a
    leitura para logo depois de ultrapassá-lo em vez de materializar tudo.
    """
    monkeypatch.setattr(mod_ativos, "LIMITE_DE_BYTES", 4096)
    grande = imagens_meta.png(1080, 1080)
    assert len(grande) > 4096
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(_transporte(corpo=grande))
    assert erro.value.codigo == "META_ASSET_BYTES_TOO_LARGE"


async def test_redirecionamento_do_cdn_e_recusado_com_nome_proprio() -> None:
    """3xx não é "imagem inválida": é um desvio para fora da allowlist.

    Antes, o 3xx caía na checagem genérica (status < 400 e corpo vazio) e o
    operador recebia a mensagem errada para a causa real.
    """
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(_transporte(corpo=b"", status=302))
    assert erro.value.codigo == "META_ASSET_BYTES_REDIRECT_REFUSED"


async def test_host_fora_do_cdn_nao_e_lido() -> None:
    async def responder(request: httpx.Request) -> httpx.Response:
        caminho = request.url.path
        if caminho.endswith("/me/adaccounts"):
            return httpx.Response(200, json={"data": [{
                "id": f"act_{CONTA}", "name": "Conta", "currency": "BRL",
                "account_status": 1}]})
        if caminho.endswith("/promote_pages"):
            return httpx.Response(200, json={"data": [{"id": "2222222222", "name": "Pagina"}]})
        if caminho.endswith("/adimages"):
            return httpx.Response(200, json={"data": [{
                "hash": "hashImagem_123456", "name": "Peca",
                "url": "https://cdn.invasor.example/peca.png"}]})
        if caminho.endswith("/advideos"):
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"nao deveria buscar bytes fora do CDN: {request.url}")

    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(httpx.MockTransport(responder))
    assert erro.value.codigo == "META_ASSET_BYTES_HOST_REJECTED"


# ---------------------------------------------------------------------------
# ACEITAÇÃO — o teste não pode provar só recusas
# ---------------------------------------------------------------------------

async def test_imagem_valida_com_declaracao_admitida_continua_apta() -> None:
    """O caminho feliz continua feliz, e agora ele significa alguma coisa."""
    referencias = await _resolver(_transporte(corpo=imagens_meta.png(1080, 1080)))
    manifesto = next(iter(referencias.asset_supply_manifests.values()))
    assert manifesto.policy_state == "AUTHORIZED"
    assert manifesto.lifecycle == "READY_FOR_PAID_MEDIA"
    assert manifesto.mime_type == "image/png"
    assert (manifesto.width, manifesto.height) == (1080, 1080)
    assert manifesto.rendition == ORIGEM_BIBLIOTECA
    assert manifesto.dimensoes_sao_do_original is True


async def test_dimensao_da_biblioteca_nao_substitui_a_medida() -> None:
    """A biblioteca declara 1080x1080; os bytes têm 600x400. A medida vence.

    E a declaração NÃO é jogada fora: divergência é um fato observável, e o
    manifesto carrega as duas para que ninguém precise escolher no escuro.
    """
    referencias = await _resolver(_transporte(
        corpo=imagens_meta.png(600, 400),
        largura_declarada=1080, altura_declarada=1080))
    manifesto = next(iter(referencias.asset_supply_manifests.values()))
    assert (manifesto.width, manifesto.height) == (600, 400)
    assert (manifesto.declared_width, manifesto.declared_height) == (1080, 1080)
    assert manifesto.byte_size == len(imagens_meta.png(600, 400))


async def test_miniatura_e_medida_mas_nunca_etiquetada_como_a_peca() -> None:
    """Só há `url_128`: os bytes são lidos, e o manifesto DECLARA que é miniatura.

    Ler e mentir sobre a origem seria pior do que não ler. O recibo público leva
    `measured_on_original: false` para que nenhuma leitura posterior conclua que
    a dimensão descreve a peça.
    """
    referencias = await _resolver(_transporte(
        corpo=imagens_meta.png(128, 128), usar_miniatura=True))
    manifesto = next(iter(referencias.asset_supply_manifests.values()))
    assert manifesto.rendition == ORIGEM_MINIATURA
    assert manifesto.dimensoes_sao_do_original is False
    assert manifesto.prova_publica()["measured_on_original"] is False


# ---------------------------------------------------------------------------
# O RECIBO — a quem ele se vincula, e o que muda a revisão
# ---------------------------------------------------------------------------

async def test_hash_muda_com_os_bytes_e_nao_com_o_nome() -> None:
    """Renomear a peça na biblioteca não é trocar a peça."""
    um = await _resolver(_transporte(corpo=imagens_meta.png(600, 600, (10, 20, 30))))
    outro = await _resolver(_transporte(corpo=imagens_meta.png(600, 600, (30, 20, 10))))
    a = next(iter(um.asset_supply_manifests.values()))
    b = next(iter(outro.asset_supply_manifests.values()))
    assert a.content_sha256 != b.content_sha256
    assert a.supply_sha256 != b.supply_sha256
    assert a.policy_receipt_ref != b.policy_receipt_ref


async def test_recibo_se_vincula_ao_ator_e_a_conta() -> None:
    """Mesmos bytes, ator diferente: recibo diferente.

    Sem este vínculo o recibo diria apenas "estes bytes foram vistos alguma
    vez", sem saber dizer quem atestou nem sobre qual conta.
    """
    corpo = imagens_meta.png(300, 300)

    async def com_ator(ator: str):
        async with httpx.AsyncClient(
            transport=_transporte(corpo=corpo), follow_redirects=False
        ) as cliente:
            resolvedor = ResolvedorAtivosMeta(cliente)
            inventario = await resolvedor.inventariar(
                meta_dom.referencia_opaca_conta(CONTA), SegredoEfemero(TOKEN))
            asset_ref = inventario["imagens"][0]["referencia_opaca"]
            quando = datetime.now(timezone.utc)
            return await resolvedor.resolver_lote(
                account_ref=inventario["account_ref"],
                page_ref=inventario["paginas"][0]["referencia_opaca"],
                asset_refs=(asset_ref,), segredo=SegredoEfemero(TOKEN), ator=ator,
                declaracoes={asset_ref: _declaracao(confirmada_em=quando)})

    um = next(iter((await com_ator("operador-um")).asset_supply_manifests.values()))
    dois = next(iter((await com_ator("operador-dois")).asset_supply_manifests.values()))
    assert um.content_sha256 == dois.content_sha256, "os bytes são os mesmos"
    assert um.supply_sha256 != dois.supply_sha256, "o recibo não é o mesmo"
    assert um.policy_receipt_ref != dois.policy_receipt_ref


async def test_repeticao_idempotente_da_conferencia_nao_fabrica_prova_nova() -> None:
    """Mesma peça, mesmo ator, mesma atestação: MESMA referência de recibo.

    ⚠️ É isto que permite compilar, validar e aprovar sem que o plano mude entre
    os três atos. Um `now()` dentro do emissor produziria um carimbo novo a cada
    chamada, o hash do plano mudaria por acidente e a aprovação descreveria um
    plano que ninguém validou.
    """
    corpo = imagens_meta.png(500, 500)
    carimbo = datetime.now(timezone.utc)
    declaracao = _declaracao(confirmada_em=carimbo)

    primeira = await _resolver(_transporte(corpo=corpo), declaracao=declaracao)
    segunda = await _resolver(_transporte(corpo=corpo), declaracao=declaracao)
    terceira = await _resolver(_transporte(corpo=corpo), declaracao=declaracao)

    refs = {
        next(iter(r.asset_supply_manifests.values())).policy_receipt_ref
        for r in (primeira, segunda, terceira)
    }
    hashes = {
        next(iter(r.asset_supply_manifests.values())).supply_sha256
        for r in (primeira, segunda, terceira)
    }
    assert len(refs) == 1, "a repetição não pode emitir recibo novo"
    assert len(hashes) == 1


async def test_nova_atestacao_explicita_muda_a_revisao() -> None:
    """Renovar é um ATO, e ele invalida a revisão anterior de propósito."""
    corpo = imagens_meta.png(500, 500)
    antes = await _resolver(
        _transporte(corpo=corpo),
        declaracao=_declaracao(confirmada_em=datetime.now(timezone.utc) - timedelta(minutes=10)))
    depois = await _resolver(
        _transporte(corpo=corpo),
        declaracao=_declaracao(confirmada_em=datetime.now(timezone.utc)))
    a = next(iter(antes.asset_supply_manifests.values()))
    b = next(iter(depois.asset_supply_manifests.values()))
    assert a.content_sha256 == b.content_sha256
    assert a.policy_receipt_ref != b.policy_receipt_ref


@pytest.mark.parametrize("desvio,motivo", [
    (timedelta(hours=2), "atestação velha demais"),
    (timedelta(minutes=-30), "atestação no futuro"),
])
async def test_atestacao_expirada_ou_futura_nao_emite_recibo(
    desvio: timedelta, motivo: str,
) -> None:
    """Nem o passado distante nem o futuro autorizam mídia paga."""
    quando = datetime.now(timezone.utc) - desvio
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        await _resolver(
            _transporte(corpo=imagens_meta.png(300, 300)),
            declaracao=_declaracao(confirmada_em=quando))
    assert erro.value.codigo == "META_ASSET_POLICY_RECEIPT_EXPIRED", motivo


@pytest.mark.parametrize("campo", [
    "direitos_confirmados", "identidade_de_terceiro_liberada",
])
def test_atestacao_negada_nao_vira_clear_por_omissao(campo: str) -> None:
    """Falta de confirmação humana recusa; nunca é promovida a CLEAR."""
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _declaracao(**{campo: False})
    assert erro.value.codigo in {
        "META_ASSET_RIGHTS_UNCONFIRMED", "META_THIRD_PARTY_IDENTITY_UNVERIFIED"}


def test_ausencia_do_decodificador_fecha_em_vez_de_liberar(monkeypatch) -> None:
    """Sem motor de decodificação o gate FECHA.

    ⚠️ É a diferença entre este gate e o gate visual do Google, que também falha
    fechado (`GATE_UNAVAILABLE`). Responder CLEAR por falta de motor seria
    exatamente a mentira que o gate existe para impedir.
    """
    import builtins

    # ⚠️ Os bytes são gerados ANTES do apagão: o gerador também usa Pillow, e
    # patchá-lo primeiro faria o teste falhar montando a própria fixture — sem
    # nunca chegar ao gate que ele existe para medir.
    corpo = imagens_meta.png(10, 10)

    original = builtins.__import__

    def sem_pillow(nome: str, *args: Any, **kwargs: Any):
        if nome == "PIL" or nome.startswith("PIL."):
            raise ImportError("PIL indisponivel neste teste")
        return original(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sem_pillow)
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        mod_ativos._decodificar_imagem(corpo)
    assert erro.value.codigo == "META_ASSET_DECODER_UNAVAILABLE"
