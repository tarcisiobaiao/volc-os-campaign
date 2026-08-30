"""As provas do Estúdio Criativo que não precisam de rede, banco nem crédito.

Nenhum teste daqui chama o provider, fala com o Supabase ou toca em disco fora de
`tmp_path`. O que eles provam é o que decide se o produto cobra duas vezes, mente
sobre progresso, vaza segredo ou promove uma peça que falhou.

A prova de ponta a ponta contra o motor real e contra o banco vive fora daqui,
em `scripts/provar-ciclo-v11.sh` (banco) e no relatório da rodada (job real).
Misturar as duas faria a suíte precisar de crédito de provider para rodar, e uma
suíte que precisa de dinheiro deixa de ser rodada.
"""

from __future__ import annotations

import base64
import json
import time

import pytest

from app.criativo import apresentacao, dominio
from app.criativo.armazenamento import (
    ArmazenamentoLocal,
    ArquivoRecusado,
    Assinador,
    ObjetoNaoEncontrado,
    TokenInvalido,
    chave_de_asset,
    conferir_chave,
    conferir_upload,
    nome_seguro,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. IDEMPOTÊNCIA
# ═══════════════════════════════════════════════════════════════════════════

BASE = {
    "projeto_titulo": "Consignado INSS",
    "objetivo": "gerar simulações",
    "mensagem": "antecipe seu décimo terceiro",
    "audiencia": "aposentados",
    "brand_pack_id": None,
    "modo": "full_llm",
    "slots": ["1x1", "4x5", "9x16"],
    "motor": "gemini:x",
    "motor_versao": "1.0.0",
}


def test_a_mesma_submissao_produz_a_mesma_chave():
    assert dominio.chave_de_idempotencia(dict(BASE)) == dominio.chave_de_idempotencia(dict(BASE))


def test_a_ordem_dos_formatos_nao_muda_a_chave():
    """Reordenar checkbox não é um pedido novo, e não pode custar de novo."""
    outro = {**BASE, "slots": ["9x16", "1x1", "4x5"]}
    assert dominio.chave_de_idempotencia(outro) == dominio.chave_de_idempotencia(BASE)


def test_espaco_a_mais_colado_de_um_documento_nao_muda_a_chave():
    outro = {**BASE, "mensagem": "  antecipe   seu\n décimo terceiro  "}
    assert dominio.chave_de_idempotencia(outro) == dominio.chave_de_idempotencia(BASE)


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("mensagem", "outra mensagem"),
        ("slots", ["1x1"]),
        ("modo", "prensa_hybrid"),
        ("brand_pack_id", "abc"),
        ("motor_versao", "2.0.0"),
    ],
)
def test_mudar_o_pedido_muda_a_chave(campo, valor):
    """Se o operador mudou o briefing, o job novo é OUTRA coisa, e cobra."""
    assert dominio.chave_de_idempotencia({**BASE, campo: valor}) != dominio.chave_de_idempotencia(BASE)


def test_a_chave_nao_carrega_o_conteudo_do_briefing():
    """A chave vai para o banco e para log. Ela não pode ser o briefing legível."""
    chave = dominio.chave_de_idempotencia(BASE)
    assert chave.startswith("cri_") and len(chave) == 68
    assert "consignado" not in chave.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 2. ESTADO DO LOTE — falha parcial
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "estados,esperado",
    [
        (["pronta", "pronta", "pronta"], "succeeded"),
        (["pronta", "falhou", "pronta"], "partial"),
        (["falhou", "falhou", "falhou"], "failed"),
        (["pronta", "gerando", "pendente"], "running"),
        (["cancelada", "cancelada"], "cancelled"),
        (["pronta", "cancelada"], "partial"),
        (["falhou", "cancelada"], "failed"),
        ([], "failed"),
    ],
)
def test_estado_do_lote(estados, esperado):
    assert dominio.estado_do_lote(estados) == esperado


def test_uma_peca_boa_no_meio_de_falhas_nunca_vira_failed():
    """A regra que impede jogar fora patrimônio já pago."""
    assert dominio.estado_do_lote(["falhou", "pronta", "falhou"]) == "partial"


def test_lote_vazio_nao_e_sucesso():
    """"Zero peças e nenhum erro" é o desfecho mais suspeito possível."""
    assert dominio.estado_do_lote([]) == "failed"


def test_retry_e_cancelamento_so_valem_onde_fazem_sentido():
    assert dominio.pode_retentar("partial") and dominio.pode_retentar("failed")
    assert not dominio.pode_retentar("succeeded")
    assert not dominio.pode_retentar("running")
    assert dominio.pode_cancelar("running") and dominio.pode_cancelar("queued")
    assert not dominio.pode_cancelar("succeeded")


# ═══════════════════════════════════════════════════════════════════════════
# 3. SANITIZAÇÃO — nada técnico chega ao operador
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "entrada",
    [
        "falhou ao abrir /Users/mac/volc-factory/out/short_odete.mp4",
        "GET https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSyBsegredo",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def",
        'File "/private/tmp/app/x.py", line 42',
        "Traceback (most recent call last):\n  File x\nValueError: nope",
        "insert into criativo_master values (1)",
        "api_key=sk-abcdefghijklmnop",
        "SELECT * FROM criativo_job WHERE id = 1",
    ],
)
def test_o_que_nunca_pode_chegar_ao_operador(entrada):
    saida = dominio.sanitizar(entrada)
    for proibido in ("/Users/", "/private/", "AIza", "sk-", "eyJ", "Bearer ",
                     "Traceback", "criativo_master", "criativo_job", "http"):
        assert proibido not in saida, f"{proibido!r} vazou em {saida!r}"


def test_mensagem_vazia_vira_frase_honesta_e_nunca_string_vazia():
    assert dominio.sanitizar("") == "O motor não informou o motivo."
    assert dominio.sanitizar("   ").strip() != ""


def test_mensagem_que_vira_so_omissao_cai_para_frase_generica():
    """Meia mensagem técnica é pior que uma frase honesta."""
    saida = dominio.sanitizar("/Users/a /Users/b /Users/c")
    assert "[omitido]" not in saida or saida.startswith("O motor")


def test_mensagem_longa_e_truncada_com_marca_visivel():
    saida = dominio.sanitizar("erro " * 200)
    assert len(saida) <= 245 and saida.endswith("…")


def test_falha_sanitiza_sozinha_na_construcao():
    """Sanitizar na borda de saída seria tarde: o objeto pode ser logado antes."""
    f = dominio.Falha(codigo="X", mensagem="quebrou em /Users/mac/segredo.py",
                      permanente=True, em="2026-01-01T00:00:00Z")
    assert "/Users/" not in f.mensagem
    assert "/Users/" not in json.dumps(f.para_dict())


# ═══════════════════════════════════════════════════════════════════════════
# 4. FORMATOS — o catálogo do backend e o do frontend não podem divergir
# ═══════════════════════════════════════════════════════════════════════════


def test_o_catalogo_do_backend_bate_com_o_do_frontend():
    """Um slot que a interface oferece e o motor não conhece vira job pago que falha.

    Este teste lê `src/types/criativos.ts` como TEXTO de propósito: importar TS
    do pytest exigiria um runtime de node, e o que importa aqui é que os dois
    arquivos concordem, não como eles são carregados.

    ⚠️ A primeira versão deste teste conferia `f"altura: {f.altura}" in ts` —
    substring solta no arquivo inteiro, sem amarrar ao slot. Trocar as alturas de
    `4x5` e `9x16` entre si mantém as MESMAS substrings (`altura: 1350` e
    `altura: 1920` continuam existindo em algum lugar) e o teste seguia verde com
    os dois formatos fisicamente trocados. Agora a dimensão é lida do bloco do
    próprio slot.
    """
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    arquivo = (raiz / "src" / "types" / "criativos.ts").read_text(encoding="utf-8")

    # ⚠️ Segunda correção, 28/08/2026 (auditoria adversarial). Prender a dimensão
    # ao slot não bastou: a varredura ainda percorria o arquivo INTEIRO e ficava
    # com a ÚLTIMA ocorrência de cada slot. Bastava existir, mais abaixo, outro
    # array com `slot: '1x1'` e valores corretos para o teste ficar verde com o
    # catálogo real corrompido. Provado por mutação com bloco-isca. Agora a
    # leitura é ancorada ao array que o backend de fato espelha.
    inicio = arquivo.find("export const FORMATOS_DE_IMAGEM")
    assert inicio != -1, "FORMATOS_DE_IMAGEM não existe em criativos.ts"
    # O array termina com `] as const;` — procurar `];` não acha nada e a âncora
    # falharia calada se a asserção abaixo não existisse.
    fim = re.search(r"^\]", arquivo[inicio:], re.M)
    assert fim, "não achei o fim do array FORMATOS_DE_IMAGEM"
    ts = arquivo[inicio : inicio + fim.start()]

    # Cada entrada do catálogo TS, com a dimensão presa ao seu próprio slot.
    no_ts: dict[str, tuple[int, int]] = {}
    for m in re.finditer(
        r"slot:\s*'(?P<slot>[^']+)'(?P<corpo>.*?)altura:\s*(?P<altura>\d+)",
        ts,
        re.S,
    ):
        largura = re.search(r"largura:\s*(\d+)", m.group("corpo"))
        assert largura, f"slot {m.group('slot')} sem largura no bloco"
        no_ts[m.group("slot")] = (int(largura.group(1)), int(m.group("altura")))

    for f in dominio.FORMATOS:
        assert f.slot in no_ts, f"slot {f.slot} não existe no contrato TS"
        assert no_ts[f.slot] == (f.largura, f.altura), (
            f"slot {f.slot}: backend diz {f.largura}x{f.altura}, "
            f"TS diz {no_ts[f.slot][0]}x{no_ts[f.slot][1]}"
        )
    assert len(no_ts) == len(dominio.FORMATOS), (
        f"o array TS tem {len(no_ts)} slots e o backend tem {len(dominio.FORMATOS)}: "
        "um slot a mais na interface é um formato que o motor recusa depois do clique"
    )


def test_slot_desconhecido_e_erro_proprio_e_nao_keyerror():
    """`KeyError` subiria como 500 e acusaria o servidor de um erro do cliente."""
    with pytest.raises(dominio.SlotDesconhecido):
        dominio.formato_de("42x42")


def test_cada_formato_sabe_pedir_a_propria_dimensao():
    for f in dominio.FORMATOS:
        spec = f.especificacao()
        assert spec.largura_recomendada == f.largura
        assert spec.altura_recomendada == f.altura
        assert spec.fonte_dos_numeros


# ═══════════════════════════════════════════════════════════════════════════
# 5. ARMAZENAMENTO — política de arquivo e travessia de caminho
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "chave",
    [
        "../fora.png",
        "criativos/../../etc/passwd",
        "/absoluto.png",
        "criativos//dupla.png",
        "criativos/%2e%2e/x.png",
        "CRIATIVOS/Maiuscula.png",
        "",
    ],
)
def test_chave_que_tenta_escapar_e_recusada(chave):
    with pytest.raises(ArquivoRecusado):
        conferir_chave(chave)


def test_o_caminho_resolvido_e_conferido_alem_da_string(tmp_path):
    """A allowlist julga a string; `resolve()` julga o caminho real."""
    loja = ArmazenamentoLocal(tmp_path)
    loja.guardar("a/b.png", b"\x89PNG\r\n\x1a\n" + b"x" * 40, "image/png")
    assert loja.existe("a/b.png")
    assert not loja.existe("../fora.png")
    with pytest.raises(ObjetoNaoEncontrado):
        loja.ler("a/inexistente.png")


def test_upload_grande_demais_e_recusado():
    with pytest.raises(ArquivoRecusado):
        conferir_upload(b"x" * (26 * 1024 * 1024), "image/png")


def test_upload_de_mime_nao_aceito_e_recusado():
    for mime in ("text/html", "application/pdf", "image/svg+xml", "application/octet-stream"):
        with pytest.raises(ArquivoRecusado):
            conferir_upload(b"x" * 100, mime)


def test_upload_vazio_e_recusado():
    with pytest.raises(ArquivoRecusado):
        conferir_upload(b"", "image/png")


@pytest.mark.parametrize(
    "cru,esperado_sem",
    [("../../etc/passwd", "/"), ("a\x00b.png", "\x00"), ("../x", "..")],
)
def test_nome_de_arquivo_e_sanitizado(cru, esperado_sem):
    assert esperado_sem not in nome_seguro(cru)


def test_nome_vazio_apos_limpeza_nao_vira_arquivo_sem_nome():
    assert nome_seguro("...") == "arquivo"
    assert nome_seguro("") == "arquivo"


def test_a_chave_do_asset_e_derivada_do_conteudo():
    """Mesmo conteúdo, mesma chave: dedup de graça e cache que nunca mente."""
    h = "sha256:" + "a" * 64
    c1 = chave_de_asset("proj", "job", "1x1", h, "png")
    c2 = chave_de_asset("proj", "job", "1x1", h, "png")
    assert c1 == c2
    c3 = chave_de_asset("proj", "job", "1x1", "sha256:" + "b" * 64, "png")
    assert c3 != c1


def test_escrita_e_atomica_e_nao_deixa_arquivo_truncado(tmp_path):
    loja = ArmazenamentoLocal(tmp_path)
    dados = b"\x89PNG\r\n\x1a\n" + b"y" * 500
    loja.guardar("x/y.png", dados, "image/png")
    assert loja.ler("x/y.png") == dados
    assert not list(tmp_path.rglob("*.parcial"))


# ═══════════════════════════════════════════════════════════════════════════
# 6. URL ASSINADA
# ═══════════════════════════════════════════════════════════════════════════

SEGREDO = "um-segredo-de-teste-com-mais-de-16-chars"


def test_token_valido_devolve_a_chave():
    a = Assinador(SEGREDO)
    assert a.conferir(a.assinar("criativos/a/b.png")) == "criativos/a/b.png"


def test_token_adulterado_e_recusado():
    a = Assinador(SEGREDO)
    t = a.assinar("criativos/a/b.png")
    corpo, assinatura = t.split(".", 1)
    with pytest.raises(TokenInvalido):
        a.conferir(f"{corpo}.{assinatura[:-4]}xxxx")


def test_token_de_outro_segredo_e_recusado():
    t = Assinador(SEGREDO).assinar("criativos/a/b.png")
    with pytest.raises(TokenInvalido):
        Assinador("outro-segredo-completamente-diferente").conferir(t)


def test_token_expirado_e_recusado():
    a = Assinador(SEGREDO)
    t = a.assinar("criativos/a/b.png", ttl_s=1)
    time.sleep(1.2)
    with pytest.raises(TokenInvalido):
        a.conferir(t)


def test_o_token_autoriza_UMA_chave_e_nao_o_bucket():
    """Trocar a chave dentro do corpo invalida a assinatura."""
    a = Assinador(SEGREDO)
    t = a.assinar("criativos/a/b.png")
    corpo, assinatura = t.split(".", 1)
    dados = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    dados["c"] = "criativos/outro/arquivo.png"
    forjado = base64.urlsafe_b64encode(
        json.dumps(dados, separators=(",", ":"), sort_keys=True).encode()
    ).rstrip(b"=").decode()
    with pytest.raises(TokenInvalido):
        a.conferir(f"{forjado}.{assinatura}")


@pytest.mark.parametrize("lixo", ["", "sem-ponto", "a.b.c.d", "@@@.###"])
def test_token_malformado_vira_erro_tipado_e_nao_excecao_crua(lixo):
    with pytest.raises(TokenInvalido):
        Assinador(SEGREDO).conferir(lixo)


def test_segredo_curto_e_recusado_na_construcao():
    with pytest.raises(ValueError):
        Assinador("curto")


def test_um_token_valido_nao_serve_para_chave_que_escapa():
    """Defesa em profundidade: mesmo assinado, `..` não passa."""
    a = Assinador(SEGREDO)
    with pytest.raises(ArquivoRecusado):
        a.assinar("../fora.png")


# ═══════════════════════════════════════════════════════════════════════════
# 7. ENQUADRAMENTO — três formatos reais, e o registro de como chegaram
# ═══════════════════════════════════════════════════════════════════════════


def _png(largura: int, altura: int) -> bytes:
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (30, 71, 161)).save(buf, format="PNG")
    return buf.getvalue()


pillow = pytest.importorskip("PIL", reason="Pillow ausente: normalização degrada, não falha")


def test_o_provider_ja_na_medida_nao_e_tocado():
    from services.creative_engine.enquadramento import enquadrar

    e = enquadrar(_png(1080, 1080), 1080, 1080)
    assert e.enquadramento == "nativo"
    assert (e.largura, e.altura) == (1080, 1080)


def test_mesma_proporcao_so_escala():
    from services.creative_engine.enquadramento import enquadrar

    e = enquadrar(_png(540, 540), 1080, 1080)
    assert e.enquadramento == "resize"
    assert (e.largura, e.altura) == (1080, 1080)
    assert (e.nativa_largura, e.nativa_altura) == (540, 540)


def test_proporcao_diferente_recorta_e_registra():
    """A diferença entre compor e esticar tem de sobreviver no registro."""
    from services.creative_engine.enquadramento import enquadrar

    e = enquadrar(_png(928, 1152), 1080, 1350)
    assert e.enquadramento == "cover_crop"
    assert (e.largura, e.altura) == (1080, 1350)
    assert (e.nativa_largura, e.nativa_altura) == (928, 1152)
    assert any("crop" in t for t in e.transformacoes)


def test_o_9x16_do_provider_e_recortado_e_nunca_esticado():
    """768x1376 tem razão 0.5581 contra 0.5625 do alvo. 0.8% de distorção
    continua sendo distorção, e o ADR-001 pede saída sem distorção."""
    from services.creative_engine.enquadramento import enquadrar

    e = enquadrar(_png(768, 1376), 1080, 1920)
    assert e.enquadramento == "cover_crop"
    assert (e.largura, e.altura) == (1080, 1920)


def test_bytes_ilegiveis_preservam_o_original_em_vez_de_perder_a_peca():
    """E o rótulo diz que NÃO houve normalização, em vez de `nativo`.

    `nativo` é traduzido na tela como "o motor entregou já nesta dimensão", e
    exibir essa frase ao lado de um pedido que não foi atendido é a mentira que
    `nao_normalizado` existe para impedir.
    """
    from services.creative_engine.enquadramento import enquadrar

    e = enquadrar(b"nao sou imagem", 1080, 1080)
    assert e.enquadramento == "nao_normalizado"
    assert e.largura is None and e.altura is None
    assert e.conteudo == b"nao sou imagem"


@pytest.mark.parametrize(
    "medida,rotulo",
    [((1080, 1080), "1:1"), ((1080, 1350), "4:5"), ((1080, 1920), "9:16"),
     ((1200, 628), "1.91:1"), ((1920, 1080), "16:9")],
)
def test_o_rotulo_de_proporcao_e_o_que_a_industria_escreve(medida, rotulo):
    from services.creative_engine.enquadramento import rotulo_de_proporcao

    assert rotulo_de_proporcao(*medida) == rotulo


@pytest.mark.parametrize(
    "medida,razao",
    [((1080, 1080), "1:1"), ((1080, 1350), "4:5"), ((1080, 1920), "9:16")],
)
def test_a_proporcao_pedida_ao_provider_e_a_do_formato(medida, razao):
    from services.creative_engine.enquadramento import razao_nativa

    assert razao_nativa(*medida) == razao


# ═══════════════════════════════════════════════════════════════════════════
# 8. O MOTOR — tradução do contrato, sem rede
# ═══════════════════════════════════════════════════════════════════════════


class TransporteFalso:
    """Dublê do HTTP. Guarda o que foi enviado e devolve o que for mandado."""

    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.chamadas = resposta, erro, []

    def post_json(self, url, payload, timeout):
        self.chamadas.append((url, payload))
        if self.erro:
            raise self.erro
        return self.resposta


def _resposta_com_imagem(largura=1024, altura=1024):
    return {
        "candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "image/png",
            "data": base64.b64encode(_png(largura, altura)).decode(),
        }}]}}],
        "usageMetadata": {"candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}]},
    }


def _pedido(slot="1x1"):
    from volc_ads.criativo.porta import PedidoDeGeracao

    f = dominio.formato_de(slot)
    return PedidoDeGeracao(referencia=f"t/{slot}", tipo=f.tipo, insumo="uma peça",
                           especificacao=f.especificacao())


def test_o_motor_cumpre_a_porta_do_repositorio():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem
    from volc_ads.criativo.porta import MotorDeCriativo

    assert isinstance(MotorGeminiImagem(chave="x"), MotorDeCriativo)


def test_a_proporcao_pedida_vai_no_payload():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

    t = TransporteFalso(_resposta_com_imagem())
    m = MotorGeminiImagem(chave="x", transporte=t)
    m.solicitar_geracao(_pedido("9x16"))
    _, payload = t.chamadas[0]
    assert payload["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
    assert "9:16" in payload["contents"][0]["parts"][0]["text"]


def test_cada_formato_e_UMA_chamada_propria():
    """Três formatos são três composições, não um bitmap recortado três vezes."""
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

    t = TransporteFalso(_resposta_com_imagem())
    m = MotorGeminiImagem(chave="x", transporte=t)
    for slot in ("1x1", "4x5", "9x16"):
        m.solicitar_geracao(_pedido(slot))
    razoes = [p["generationConfig"]["imageConfig"]["aspectRatio"] for _, p in t.chamadas]
    assert razoes == ["1:1", "4:5", "9:16"]


def test_sem_credencial_o_motor_recusa_antes_de_falar_com_a_rede():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem
    from volc_ads.criativo.porta import MotorIndisponivel

    t = TransporteFalso(_resposta_com_imagem())
    m = MotorGeminiImagem(chave="", transporte=t)
    assert not m.configurado
    with pytest.raises(MotorIndisponivel):
        m.solicitar_geracao(_pedido())
    assert t.chamadas == []


def test_pedido_sem_dimensao_e_recusado_antes_de_gastar():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem
    from volc_ads.criativo.contrato import TipoDeAsset
    from volc_ads.criativo.porta import PedidoDeGeracao, PedidoRecusado

    t = TransporteFalso(_resposta_com_imagem())
    m = MotorGeminiImagem(chave="x", transporte=t)
    p = PedidoDeGeracao(referencia="t", tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
                        insumo="x", especificacao=None)
    with pytest.raises(PedidoRecusado):
        m.solicitar_geracao(p)
    assert t.chamadas == []


@pytest.mark.parametrize(
    "status,permanente",
    [(401, False), (403, False), (429, False), (400, True), (404, True), (500, False)],
)
def test_o_status_do_provider_vira_erro_tipado_com_permanencia_correta(status, permanente):
    """`permanente` decide o retry. Marcar 429 como permanente desistiria de um
    pedido que ia dar certo; marcar 400 como transitório queimaria cota."""
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem, RespostaHTTP

    t = TransporteFalso(erro=RespostaHTTP(status=status, corpo="detalhe interno do provider"))
    m = MotorGeminiImagem(chave="x", transporte=t)
    with pytest.raises(Exception) as exc:
        m.solicitar_geracao(_pedido())
    assert getattr(exc.value, "permanente", None) is permanente


def test_a_mensagem_de_erro_nao_carrega_a_resposta_bruta_do_provider():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem, RespostaHTTP

    t = TransporteFalso(erro=RespostaHTTP(status=400, corpo="SEGREDO_DO_PROVIDER_AQUI"))
    m = MotorGeminiImagem(chave="x", transporte=t)
    with pytest.raises(Exception) as exc:
        m.solicitar_geracao(_pedido())
    assert "SEGREDO_DO_PROVIDER_AQUI" not in str(exc.value)


def test_resposta_200_sem_imagem_e_recusa_permanente_e_nao_sucesso_vazio():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem
    from volc_ads.criativo.porta import PedidoRecusado

    t = TransporteFalso({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})
    m = MotorGeminiImagem(chave="x", transporte=t)
    with pytest.raises(PedidoRecusado):
        m.solicitar_geracao(_pedido())


def test_receber_com_id_desconhecido_e_erro_tipado():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem
    from volc_ads.criativo.porta import PedidoDesconhecido

    m = MotorGeminiImagem(chave="x", transporte=TransporteFalso(_resposta_com_imagem()))
    with pytest.raises(PedidoDesconhecido):
        m.receber("gem_nunca_emitido")


def test_o_custo_do_provider_e_estimativa_e_nunca_medida():
    """A API devolve tokens, não dólares. `custo_usd` medido fica ausente."""
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

    m = MotorGeminiImagem(chave="x", transporte=TransporteFalso(_resposta_com_imagem()))
    r = m.receber(m.solicitar_geracao(_pedido()))
    arq = r.arquivos[0]
    assert arq.custo_usd is None
    assert r.custo_usd is None
    assert float(arq.metadados["custo_estimado_usd"]) > 0
    assert "referência de provider" in arq.metadados["custo_fonte"]


def test_a_chave_do_provider_nao_aparece_no_objeto_devolvido():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

    m = MotorGeminiImagem(chave="AIzaSySEGREDO", transporte=TransporteFalso(_resposta_com_imagem()))
    r = m.receber(m.solicitar_geracao(_pedido()))
    assert "AIzaSySEGREDO" not in json.dumps(r.arquivos[0].metadados)


def test_a_procedencia_registra_nativo_e_enquadramento():
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

    m = MotorGeminiImagem(chave="x", transporte=TransporteFalso(_resposta_com_imagem(928, 1152)))
    r = m.receber(m.solicitar_geracao(_pedido("4x5")))
    meta = r.arquivos[0].metadados
    assert meta["nativo_largura"] == "928" and meta["nativo_altura"] == "1152"
    assert meta["enquadramento"] == "cover_crop"


# ═══════════════════════════════════════════════════════════════════════════
# 9. APRESENTAÇÃO — a última fronteira antes do browser
# ═══════════════════════════════════════════════════════════════════════════

LINHA_MASTER = {
    "id": "m1", "job_id": "j1", "projeto_id": "p1", "slot": "1x1", "kind": "imagem",
    "storage_chave": "criativos/p1/j1/1x1_abc.png", "content_hash": "sha256:" + "a" * 64,
    "mime": "image/png", "largura": 1080, "altura": 1080, "bytes_totais": 1234,
    "duracao_ms": None, "motor": "gemini:x", "motor_versao": "1.0.0",
    "insumo_hash": "deadbeef", "insumo_sanitizado": "O PROMPT SECRETO INTEIRO",
    "brand_pack_id": None, "brand_pack_versao": None, "sintetico": True,
    "disclosure": "IA", "licenca": None, "credito": None, "versao": 1,
    "raiz_id": None, "substitui_id": None, "criado_em": "2026-08-27T00:00:00Z",
    "arquivado_em": None, "custo_usd": None,
}


def test_o_dto_do_ativo_nao_carrega_chave_de_storage_nem_prompt():
    dto = apresentacao.master_dto(LINHA_MASTER, Assinador(SEGREDO), procedencia_execucao="volc_os")
    bruto = json.dumps(dto)
    assert "criativos/p1/j1" not in bruto
    assert "storage" not in bruto.lower()
    assert "O PROMPT SECRETO INTEIRO" not in bruto
    assert dto["procedencia"]["insumoHash"] == "deadbeef"


def test_o_preview_e_url_assinada_e_nao_caminho():
    dto = apresentacao.master_dto(LINHA_MASTER, Assinador(SEGREDO), procedencia_execucao="volc_os")
    assert dto["previewUrl"].startswith("/api/criativos/arquivo/")


def test_medida_ausente_atravessa_como_null_e_nunca_zero():
    linha = {**LINHA_MASTER, "largura": None, "altura": None, "bytes_totais": None}
    dto = apresentacao.master_dto(linha, Assinador(SEGREDO), procedencia_execucao="volc_os")
    assert dto["largura"] is None and dto["altura"] is None and dto["bytesTotais"] is None
    assert 0 not in (dto["largura"], dto["altura"], dto["bytesTotais"])


def test_uso_vazio_e_declarado_como_nao_apurado():
    """`uso desconhecido` não é `sem uso` (SPEC §10)."""
    dto = apresentacao.master_dto(LINHA_MASTER, Assinador(SEGREDO), procedencia_execucao="volc_os")
    assert dto["usos"] == [] and dto["usoApurado"] is False


def test_o_evento_sem_progresso_medido_atravessa_como_null():
    """Zero percentual inventado. Se virar 0, a interface desenha barra vazia."""
    dto = apresentacao.evento_dto(
        {"seq": 3, "fase": "gerando", "mensagem": None, "percentual": None,
         "slot": "1x1", "em": "2026-08-27T00:00:00Z"}
    )
    assert dto["percentual"] is None


def test_a_rendition_falha_carrega_motivo_e_nao_apaga_as_outras():
    a = Assinador(SEGREDO)
    boas = apresentacao.rendition_dto(
        {"id": "r1", "slot": "1x1", "estado": "pronta", "largura_pedida": 1080,
         "altura_pedida": 1080, "storage_chave": "criativos/a/b.png",
         "content_hash": "sha256:" + "a" * 64, "master_id": "m1"}, a)
    ruim = apresentacao.rendition_dto(
        {"id": "r2", "slot": "4x5", "estado": "falhou", "largura_pedida": 1080,
         "altura_pedida": 1350, "erro_codigo": "MOTOR.recusado",
         "erro_mensagem": "recusado por política", "erro_permanente": True,
         "erro_em": "2026-08-27T00:00:00Z"}, a)
    assert boas["estado"] == "pronta" and boas["previewUrl"]
    assert ruim["erro"]["permanente"] is True
    assert ruim["previewUrl"] is None


def test_o_dto_do_job_nao_vaza_a_chave_de_idempotencia():
    """Ela é derivada do briefing e vai para log; não precisa ir ao browser."""
    dto = apresentacao.job_dto(
        {"id": "j1", "briefing_id": "b1", "motor": "m", "motor_versao": "1",
         "estado": "succeeded", "tentativa": 1, "idempotency_key": "cri_SEGREDO",
         "insumo_hash": "h", "criado_em": "2026-08-27T00:00:00Z"},
        [], Assinador(SEGREDO))
    assert "cri_SEGREDO" not in json.dumps(dto)


def test_procedencia_nao_apurada_nao_vira_afirmacao_de_autoria():
    """A ausência de leitura não pode virar "produzida aqui".

    O default anterior era `"volc_os"`, e três dos quatro chamadores omitiam o
    argumento. A tela transforma esse campo numa frase categórica, então um
    ativo cujo job ninguém leu era apresentado como produzido pelo VOLC O.S. —
    a exata afirmação que o módulo de vídeo inteiro existe para impedir.
    """
    dto = apresentacao.master_dto(
        LINHA_MASTER, Assinador(SEGREDO), procedencia_execucao=None
    )
    assert dto["procedenciaExecucao"] is None


def test_procedencia_observada_atravessa_como_observada():
    dto = apresentacao.master_dto(
        LINHA_MASTER, Assinador(SEGREDO), procedencia_execucao="observado"
    )
    assert dto["procedenciaExecucao"] == "observado"
