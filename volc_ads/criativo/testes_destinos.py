"""O catálogo de envelopes e o medidor que separa recompor de recortar.

Rodar:
    .venv-worker/bin/python -m pytest volc_ads/criativo/testes_destinos.py -q

A travessia ponta a ponta está em `backend/tests/test_criativo_golden_imagem.py`.
Aqui ficam as regras do próprio módulo — as que precisam valer mesmo quando
nenhuma peça foi produzida:

  · o rótulo de proporção é CONFERIDO contra as dimensões, não decorativo;
  · ausência de medida é `None` e nunca `0`;
  · "ninguém releu o armazenamento" é diferente de "releu e não bateu";
  · sem Pillow não há veredito de adaptação — há recusa nomeada;
  · o mestre não é adaptação de nada, e isso tem rótulo próprio.
"""

from __future__ import annotations

import io
import random

import pytest

from volc_ads.criativo import destinos as D
from volc_ads.criativo.contrato import NaturezaDaProcedencia, TipoDeAsset

HASH = "sha256:" + "a" * 64
OUTRO_HASH = "sha256:" + "b" * 64


# ── o catálogo ──────────────────────────────────────────────────────────────


def teste_o_catalogo_cobre_as_quatro_proporcoes_que_a_fatia_exige():
    """1:1, 4:5, 1.91:1 e 9:16. O logo entra além delas, não no lugar delas."""
    proporcoes = {e.proporcao for e in D.ENVELOPES}
    assert {"1:1", "4:5", "1.91:1", "9:16"} <= proporcoes
    assert {(1080, 1080), (1080, 1350), (1200, 628), (1080, 1920)} <= {
        (e.largura, e.altura) for e in D.ENVELOPES
    }


def teste_slugs_e_slots_sao_unicos():
    """Dois slots iguais na mesma encomenda fariam o motor escrever no mesmo
    arquivo, e o segundo apagaria o primeiro — com o gate aprovando um pedido
    que na verdade só foi atendido pela metade."""
    assert len({e.slug for e in D.ENVELOPES}) == len(D.ENVELOPES)
    assert len({e.slot for e in D.ENVELOPES}) == len(D.ENVELOPES)


def teste_todo_envelope_declara_destino_conhecido_e_fonte():
    for envelope in D.ENVELOPES:
        assert envelope.destino in D.DESTINOS
        assert envelope.fonte.strip()
        assert envelope.superficie.strip()
        assert isinstance(envelope.tipo, TipoDeAsset)


def teste_cada_destino_tem_pelo_menos_um_envelope():
    """Um destino sem envelope seria um destino que o sistema não sabe atender —
    e ele apareceria como pacote vazio em toda produção, para sempre."""
    for destino in D.DESTINOS:
        assert D.envelopes_de_destino(destino), destino


def teste_o_rotulo_de_proporcao_e_conferido_contra_as_dimensoes():
    """MUTANTE do catálogo: um rótulo que ninguém confere é decoração.

    Se `__post_init__` deixasse de conferir, dava para escrever `9:16` num
    1200x628 e a tela mostraria a proporção errada ao lado do arquivo certo.
    """
    with pytest.raises(ValueError, match="não descreve"):
        D.Envelope(
            slug="mentiroso",
            destino=D.META,
            superficie="teste",
            tipo=TipoDeAsset.IMAGEM_MARKETING,
            largura=1200,
            altura=628,
            proporcao="9:16",
            fonte="inventado",
        )


def teste_envelope_recusa_dimensao_nao_positiva_destino_e_fonte_ausentes():
    comum = dict(
        slug="x",
        superficie="teste",
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        proporcao="1:1",
        fonte="teste",
    )
    with pytest.raises(ValueError, match="nunca zero"):
        D.Envelope(destino=D.META, largura=0, altura=100, **comum)
    with pytest.raises(D.DestinoDesconhecido):
        D.Envelope(destino="tiktok", largura=100, altura=100, **comum)
    with pytest.raises(ValueError, match="sem fonte"):
        D.Envelope(
            slug="x",
            destino=D.META,
            superficie="teste",
            tipo=TipoDeAsset.IMAGEM_MARKETING,
            largura=100,
            altura=100,
            proporcao="1:1",
            fonte="   ",
        )


def teste_envelope_desconhecido_e_erro_nomeado_com_a_lista():
    with pytest.raises(D.EnvelopeDesconhecido) as erro:
        D.envelope_de("nao-existe")
    assert "meta-feed-1x1" in str(erro.value)
    with pytest.raises(D.DestinoDesconhecido):
        D.envelopes_de_destino("linkedin")


# ── a variante entregue ─────────────────────────────────────────────────────


def _variante(**extra) -> D.VarianteEntregue:
    campos = dict(
        envelope_slug="meta-feed-1x1",
        conteudo_hash=HASH,
        mime="image/png",
        largura=1080,
        altura=1080,
        bytes_totais=1234,
        adaptacao=D.MESTRE,
    )
    campos.update(extra)
    return D.VarianteEntregue(**campos)


def teste_variante_recusa_hash_sem_algoritmo_e_medida_zerada():
    with pytest.raises(ValueError, match="algoritmo"):
        _variante(conteudo_hash="a" * 64)
    for campo in ("largura", "altura", "bytes_totais"):
        with pytest.raises(ValueError, match="nunca 0"):
            _variante(**{campo: 0})


def teste_variante_recusa_adaptacao_fora_do_vocabulario():
    with pytest.raises(ValueError, match="vocabulário"):
        _variante(adaptacao="adaptado")


def teste_variante_recusa_envelope_inexistente():
    with pytest.raises(D.EnvelopeDesconhecido):
        _variante(envelope_slug="meta-feed-16x9")


def teste_verificacao_de_armazenamento_tem_tres_respostas_e_nao_duas():
    """`None` (ninguém releu), `False` (releu e divergiu), `True` (releu e bateu).

    Colapsar as duas primeiras num booleano é o defeito clássico: um `ok=False`
    logo depois do upload diria que o objeto está corrompido quando ninguém
    chegou a olhar para ele.
    """
    assert _variante().armazenamento_verificado is None
    assert _variante().armazenada is False
    assert _variante(chave_de_armazenamento="criativos/a/b/c.png").armazenada is True
    assert (
        _variante(relido_hash=OUTRO_HASH).armazenamento_verificado is False
    )
    assert _variante(relido_hash=HASH).armazenamento_verificado is True


def teste_na_medida_compara_com_o_envelope_e_nao_consigo_mesma():
    assert _variante().na_medida is True
    assert _variante(largura=1200).na_medida is False
    # Sem medida não há como afirmar que está na medida.
    assert _variante(largura=None, altura=None).na_medida is False


# ── o pacote de destino ─────────────────────────────────────────────────────


def teste_pacote_recusa_variante_de_outro_destino():
    """Sem esta guarda, uma peça do Meta entraria no pacote do Google e o
    `faltando` diria que está tudo lá."""
    with pytest.raises(ValueError, match="não é envelope de"):
        D.PacoteDeDestino(
            destino=D.GOOGLE,
            variantes=(_variante(),),
            natureza=NaturezaDaProcedencia.LOCAL,
        )


def teste_pacote_incompleto_lista_o_que_falta():
    pacote = D.PacoteDeDestino(
        destino=D.META,
        variantes=(_variante(),),
        natureza=NaturezaDaProcedencia.PRODUCAO,
    )
    assert pacote.faltando == ("meta-feed-4x5",)
    assert pacote.completo is False
    assert pacote.publicavel is False


def teste_pacote_vazio_nao_se_diz_verificado():
    """⚠️ `all([])` é `True` em Python, e é assim que um pacote SEM NADA dentro
    passa a responder "tudo verificado". A guarda existe por causa disso."""
    pacote = D.PacoteDeDestino(
        destino=D.ORGANICO,
        variantes=(),
        natureza=NaturezaDaProcedencia.PRODUCAO,
    )
    assert pacote.verificado is False
    assert pacote.completo is False
    assert pacote.publicavel is False


def teste_publicavel_exige_producao_completude_e_verificacao():
    """Três perguntas independentes; falhar em qualquer uma reprova.

    A tabela abaixo é o que separa "a peça está pronta" de "a peça pode subir":
    um lote completo e verificado de motor local continua não sendo anúncio.
    """
    variantes = (
        _variante(relido_hash=HASH, chave_de_armazenamento="criativos/a/b/c.png"),
        _variante(
            envelope_slug="meta-feed-4x5",
            conteudo_hash=OUTRO_HASH,
            largura=1080,
            altura=1350,
            adaptacao=D.RECOMPOSICAO,
            relido_hash=OUTRO_HASH,
            chave_de_armazenamento="criativos/a/b/d.png",
        ),
    )
    pronto = D.PacoteDeDestino(
        destino=D.META, variantes=variantes, natureza=NaturezaDaProcedencia.PRODUCAO
    )
    assert pronto.completo is True
    assert pronto.verificado is True
    assert pronto.publicavel is True

    for natureza in (
        NaturezaDaProcedencia.LOCAL,
        NaturezaDaProcedencia.FIXTURE,
        NaturezaDaProcedencia.NAO_DECLARADA,
    ):
        assert (
            D.PacoteDeDestino(
                destino=D.META, variantes=variantes, natureza=natureza
            ).publicavel
            is False
        ), natureza

    sem_releitura = tuple(
        D.VarianteEntregue(
            envelope_slug=v.envelope_slug,
            conteudo_hash=v.conteudo_hash,
            mime=v.mime,
            largura=v.largura,
            altura=v.altura,
            bytes_totais=v.bytes_totais,
            adaptacao=v.adaptacao,
            chave_de_armazenamento=v.chave_de_armazenamento,
        )
        for v in variantes
    )
    quase = D.PacoteDeDestino(
        destino=D.META,
        variantes=sem_releitura,
        natureza=NaturezaDaProcedencia.PRODUCAO,
    )
    assert quase.completo is True
    assert quase.verificado is False
    assert quase.publicavel is False


def teste_publicacao_automatica_e_sempre_falsa_e_nao_e_campo_de_construcao():
    pacote = D.PacoteDeDestino(
        destino=D.META, variantes=(), natureza=NaturezaDaProcedencia.PRODUCAO
    )
    assert pacote.publicacao_automatica is False
    with pytest.raises(TypeError):
        D.PacoteDeDestino(  # type: ignore[call-arg]
            destino=D.META,
            variantes=(),
            natureza=NaturezaDaProcedencia.PRODUCAO,
            publicacao_automatica=True,
        )


def teste_montar_pacotes_cria_pacote_ate_para_destino_sem_variante():
    """Destino vazio some da lista se ninguém cuidar, e "não produzimos nada
    para o Google" fica igual a "o Google não é destino deste sistema"."""
    pacotes = D.montar_pacotes(
        [_variante()], natureza=NaturezaDaProcedencia.LOCAL
    )
    assert [p.destino for p in pacotes] == list(D.DESTINOS)
    por_destino = {p.destino: p for p in pacotes}
    assert por_destino[D.GOOGLE].variantes == ()
    assert por_destino[D.GOOGLE].faltando == (
        "google-display-191x1",
        "google-logo-1x1",
    )
    assert por_destino[D.META].faltando == ("meta-feed-4x5",)


def teste_pacote_serializa_sem_perder_as_ausencias():
    pacote = D.montar_pacotes(
        [_variante()], natureza=NaturezaDaProcedencia.LOCAL
    )[1]
    corpo = pacote.para_json()
    assert corpo["destino"] == D.META
    assert corpo["publicacao_automatica"] is False
    assert corpo["variantes"][0]["armazenamento_verificado"] is None
    assert corpo["variantes"][0]["chave_de_armazenamento"] is None


# ── o medidor de pixels ─────────────────────────────────────────────────────


def teste_mestre_nao_e_veredito_de_comparacao():
    """`MESTRE` é rótulo do catálogo. Se ele pudesse sair de
    `classificar_adaptacao`, "não comparei" viraria um veredito."""
    assert D.MESTRE in D.ADAPTACOES
    with pytest.raises(ValueError, match="não é veredito"):
        D.Adaptacao(tipo=D.MESTRE, motivo="", evidencia={})
    with pytest.raises(ValueError, match="vocabulário"):
        D.Adaptacao(tipo="esticado", motivo="", evidencia={})


def teste_indeterminado_nao_conta_como_recomposicao():
    assert (
        D.Adaptacao(tipo=D.INDETERMINADO, motivo="", evidencia={}).recomposta is False
    )
    assert D.Adaptacao(tipo=D.CROP_RESIZE, motivo="", evidencia={}).recomposta is False
    assert D.Adaptacao(tipo=D.RECOMPOSICAO, motivo="", evidencia={}).recomposta is True


def teste_sem_pillow_nao_ha_perfil_e_sim_recusa_nomeada(monkeypatch):
    """Ausência de medida não pode virar "nenhuma diferença medida"."""
    monkeypatch.setattr(D, "_pillow", lambda: None)
    with pytest.raises(D.MedicaoDePixelsIndisponivel):
        D.perfilar(b"qualquer coisa")


def teste_bytes_que_nao_sao_imagem_recusam_em_vez_de_perfilar_zero():
    pytest.importorskip("PIL")
    with pytest.raises(D.MedicaoDePixelsIndisponivel):
        D.perfilar(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def teste_bytes_identicos_nao_sao_recomposicao():
    """`IDENTICO` e `RECOMPOSICAO` são desfechos diferentes: um diz que nada foi
    adaptado, o outro que houve trabalho. Colapsá-los premiaria o replay."""
    dados = _png_de_duas_cores(32, 32)
    veredito = D.classificar_adaptacao(dados, dados)
    assert veredito.tipo == D.IDENTICO
    assert veredito.recomposta is False


def teste_mestre_fora_do_regime_de_duas_cores_devolve_indeterminado():
    """A fronteira declarada no cabeçalho do módulo, exercida.

    Numa peça com nuvem de cores, o overshoot deixa de ser assinatura de
    reamostragem — e o módulo diz que não sabe, em vez de chutar recomposição.
    """
    pytest.importorskip("PIL")
    ruido = _png_ruidoso(48, 48)
    outro = _png_ruidoso(48, 48, semente=7)
    perfil = D.perfilar(ruido)
    assert perfil.de_duas_cores is False
    veredito = D.classificar_adaptacao(ruido, outro)
    assert veredito.tipo == D.INDETERMINADO
    assert veredito.recomposta is False


def teste_reamostrar_um_png_de_duas_cores_e_visto_como_recorte():
    """O discriminante, no menor caso possível: a mesma peça reamostrada.

    Não depende do motor tipográfico nem da bancada — é a propriedade física do
    LANCZOS contra uma composição de duas cores.
    """
    Image = pytest.importorskip("PIL.Image")
    original = _png_de_duas_cores(64, 64)
    with Image.open(io.BytesIO(original)) as img:
        maior = img.convert("RGB").resize((128, 128), Image.LANCZOS)
        saida = io.BytesIO()
        maior.save(saida, format="PNG")
    veredito = D.classificar_adaptacao(original, saida.getvalue())
    assert veredito.tipo == D.CROP_RESIZE
    assert veredito.evidencia["variante"]["fora_da_rampa"] > 0


# ── helpers de bytes, para não depender de fixture em disco ─────────────────


def _png_de_duas_cores(largura: int, altura: int) -> bytes:
    """Fundo escuro com um retângulo claro. Duas cores exatas, sem antialias."""
    Image = pytest.importorskip("PIL.Image")
    img = Image.new("RGB", (largura, altura), (12, 17, 27))
    for y in range(altura // 4, altura * 3 // 4):
        for x in range(largura // 8, largura * 7 // 8):
            img.putpixel((x, y), (243, 246, 250))
    saida = io.BytesIO()
    img.save(saida, format="PNG")
    return saida.getvalue()


def _png_ruidoso(largura: int, altura: int, *, semente: int = 1) -> bytes:
    """Ruído RGB determinístico: a nuvem de cores não cabe em reta nenhuma."""
    Image = pytest.importorskip("PIL.Image")
    sorteio = random.Random(semente)
    img = Image.new("RGB", (largura, altura))
    for y in range(altura):
        for x in range(largura):
            img.putpixel(
                (x, y),
                (
                    sorteio.randrange(256),
                    sorteio.randrange(256),
                    sorteio.randrange(256),
                ),
            )
    saida = io.BytesIO()
    img.save(saida, format="PNG")
    return saida.getvalue()
