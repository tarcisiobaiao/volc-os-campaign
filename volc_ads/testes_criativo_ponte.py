"""Testes da fronteira criativo → Display.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/testes_criativo_ponte.py -q

**Nenhum teste aqui fala com o Google, com motor pago ou com o relógio** — e
isso é garantido pela fixture `_sem_credencial`, não prometido no comentário.
A primeira versão deste arquivo fazia a promessa sem a fixture, e seis testes
alcançavam `accounts.google.com` para renovar OAuth; o gatekeeper mediu com o
socket bloqueado e a promessa caiu.

Todo instante é injetado; os bytes são PNG/JPEG/GIF construídos byte a byte,
com dimensão de verdade no cabeçalho, para que a validação de geometria seja
exercitada e não simulada.

Os quatro grupos, e o que cada um persegue:

  PAPEL       a tabela `TipoDeAsset → papel`, conferida contra as proporções do
              `requisitos.yaml`. É a armadilha mais cara: `logo` é 4:1.

  PORTÃO      lote reprovado não produz payload NENHUM. Não parcial: nenhum.

  IDENTIDADE  o hash é recomputado dos bytes que entram no payload. Procedência
              que não se confere é decoração.

  AUSÊNCIA    desconhecido continua `None`; validação ausente não vira
              aprovação; asset sem bytes não vira asset disponível; procedência
              incompleta não vira procedência confirmada.
"""

from __future__ import annotations

import ast
import pathlib
import struct
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from volc_ads import criativo_ponte as ponte  # noqa: E402
from volc_ads.campanha.brief import ImagemParaSubir, ImagensDisplay, Linhagem  # noqa: E402
from volc_ads.criativo import requisitos  # noqa: E402
from volc_ads.criativo.contrato import (  # noqa: E402
    Asset,
    Falha,
    LoteDeAssets,
    Origem,
    Procedencia,
    TipoDeAsset,
    hash_de_conteudo,
)

RAIZ = pathlib.Path(__file__).resolve().parents[1]


# ── nenhuma credencial, e isto é verificado e não prometido ─────────────────
#
# ⚠️ A primeira versão deste arquivo AFIRMAVA no docstring que nada aqui fala
# com o Google, e a afirmação era falsa. Os testes que chamam
# `search.construir` / `display.construir` descem até `gads.client.cliente()`,
# que chama `GoogleAdsClient.load_from_storage()` — e isso faz refresh de OAuth
# contra `accounts.google.com`, com a credencial de disco. Não é `mutate` nem
# `validate_only` (a Ads API nunca é chamada), mas é rede e é credencial viva:
# numa máquina sem `~/google-ads.yaml` a suíte quebrava.
#
# O shim é IMPORTADO de `testes_display`, não recriado. Já existem duas cópias
# dele no repositório (`testes_search` e `testes_display`); uma terceira seria
# a terceira declaração da mesma verdade, e a que divergisse primeiro venceria
# em silêncio.
from volc_ads.campanha.testes_display import _cliente_sem_rede  # noqa: E402


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch):
    """Nenhum teste deste arquivo carrega `~/google-ads.yaml`.

    Os DOIS construtores são trocados: este arquivo exercita Display (o caminho
    da fatia) e Search (a prova de que Search não foi contaminado). Trocar só um
    deixaria metade dos testes dependendo de credencial.
    """
    from volc_ads.campanha import display as _display, search as _search
    monkeypatch.setattr(_display, "cliente", lambda _login: _cliente_sem_rede())
    monkeypatch.setattr(_search, "cliente", lambda _login: _cliente_sem_rede())

#: Relógio injetado. Nenhum teste deste arquivo lê o relógio da máquina — um
#: teste que muda de resultado conforme o dia não prova comportamento, prova
#: que hoje deu certo.
QUANDO = datetime(2026, 8, 27, 15, 30, 0, tzinfo=timezone.utc)


# ── bytes de verdade, com dimensão no cabeçalho ─────────────────────────────


def png(largura: int, altura: int, *, semente: bytes = b"") -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13) + b"IHDR"
        + struct.pack(">II", largura, altura)
        + b"\x08\x06\x00\x00\x00"
        + semente
    )


def _asset(tipo: TipoDeAsset, largura: int, altura: int, *,
           semente: bytes = b"", motor: str = "motor-de-teste",
           versao: str = "1.4.2", insumo: str = "um prompt qualquer",
           custo=None, rotulo: str = "", quando: datetime | None = None,
           origem: Origem = Origem.GERADO,
           derivado_de: str | None = None,
           id_externo: str | None = None,
           mime: str | None = "image/png",
           medido: bool = True) -> tuple[Asset, bytes]:
    """Devolve o par (asset, bytes) — porque o `Asset` não carrega conteúdo."""
    dados = png(largura, altura, semente=semente)
    return Asset(
        tipo=tipo,
        procedencia=Procedencia(
            motor=motor, versao_do_motor=versao, insumo=insumo,
            quando=quando or QUANDO, pedido="ped-001", custo_usd=custo,
        ),
        conteudo_hash=hash_de_conteudo(dados),
        origem=origem,
        bytes_totais=len(dados),
        mime=mime if medido else None,
        largura=largura if medido else None,
        altura=altura if medido else None,
        rotulo=rotulo,
        derivado_de=derivado_de,
        id_externo=id_externo,
    ), dados


def _brief_com(imagens: ImagensDisplay):
    """O mesmo formato de brief que `campanha/testes_display.py` já usa.

    Reaproveitar a forma importa: um brief inventado aqui poderia divergir do
    que o construtor realmente aceita, e o teste passaria a provar a minha
    suposição em vez do contrato.
    """
    from volc_ads.campanha.brief import Brief, Copy
    return Brief(
        nicho="Consórcio", slug="consorcio",
        url_final="https://creditoup.com.br/r/consorcio/",
        keywords=["consorcio"], estrategia_lance="MAXIMIZE_CONVERSIONS",
        copy=Copy(headlines=["Consórcio de imóvel"],
                  descriptions=["Simule agora e veja a parcela."],
                  long_headlines=["Consórcio de imóvel com parcela que cabe"],
                  business_name="Crédito Up"),
        imagens_display=imagens)


def _lote_completo(**kw):
    """Um lote DISPLAY mínimo e válido: banner 1.91:1 + quadrado 1:1."""
    kw.setdefault("rotulo", "principal")
    banner, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628,
                        semente=b"banner", **kw)
    quadrado, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600,
                          semente=b"quadrado", **kw)
    lote = LoteDeAssets(canal="DISPLAY", assets=(banner, quadrado),
                        intencao="campanha de teste")
    conteudo = {banner.identidade: b1, quadrado.identidade: b2}
    return lote, conteudo


# ════════════════════════════════════════════════════════════════════════════
# PAPEL
# ════════════════════════════════════════════════════════════════════════════


def test_a_tabela_de_papeis_bate_com_as_proporcoes_declaradas_no_yaml():
    """⚠️ `logo` é 4:1 e `logo_quadrado` é 1:1 — o pareamento intuitivo é errado.

    Este teste confere a tabela contra a FONTE (`requisitos.yaml`), não contra
    a intuição de quem lê. Se alguém "consertar" a tabela trocando as duas
    logos, aqui falha; sem ele, falharia na API, com o erro apontando para o
    anúncio e não para a tabela.
    """
    exigencia = requisitos.exigencia_binaria_de("DISPLAY")
    esperado = {
        "marketing": (191, 100),
        "marketing_quadrada": (1, 1),
        "logo": (4, 1),
        "logo_quadrado": (1, 1),
    }
    for tipo, papel in ponte.PAPEL_POR_TIPO.items():
        spec = exigencia.de(tipo)
        assert spec is not None, f"{tipo.value} sem especificação em DISPLAY"
        assert spec.proporcao_alvo == esperado[papel], (
            f"{tipo.value} → '{papel}': o YAML diz {spec.proporcao_alvo}, "
            f"a tabela implica {esperado[papel]}")


def test_a_tabela_cobre_exatamente_os_quatro_papeis_de_imagem():
    assert set(ponte.PAPEL_POR_TIPO.values()) == set(ImagensDisplay.PAPEIS)
    assert len(ponte.PAPEL_POR_TIPO) == len(ImagensDisplay.PAPEIS)


def test_quatro_imagens_medidas_viram_os_quatro_papeis_certos():
    banner, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente=b"a")
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"b")
    logo, b3 = _asset(TipoDeAsset.LOGO_PAISAGEM, 1024, 256, semente=b"c")
    logoq, b4 = _asset(TipoDeAsset.LOGO_QUADRADO, 256, 256, semente=b"d")
    lote = LoteDeAssets(canal="DISPLAY", assets=(banner, quad, logo, logoq))
    e = ponte.imagens_de_display(lote, {
        banner.identidade: b1, quad.identidade: b2,
        logo.identidade: b3, logoq.identidade: b4})

    assert e.ok, e.resumo()
    assert len(e.imagens.marketing) == 1
    assert len(e.imagens.marketing_quadrada) == 1
    assert len(e.imagens.logo) == 1, "a logo 4:1 não entrou em `logo`"
    assert len(e.imagens.logo_quadrado) == 1
    # E a 4:1 é mesmo a que está em `logo`.
    assert e.imagens.logo[0].largura == 1024
    assert e.imagens.logo_quadrado[0].largura == 256


def test_video_aprovado_nao_tem_papel_de_imagem_e_e_recusado_com_o_caminho_certo():
    """O vídeo passa na validação e MESMO ASSIM não vira imagem.

    ⚠️ `mime="video/mp4"` é essencial ao teste, e a primeira versão dele o
    esqueceu: sem mime, `validar_lote` reprova com `M1.sem_medida` e o asset
    nunca chega ao ramo que este teste quer exercitar — o teste passaria a
    provar outra coisa, e ficaria verde por acidente.
    """
    lote, conteudo = _lote_completo()
    video = Asset(
        tipo=TipoDeAsset.VIDEO,
        procedencia=Procedencia(motor="veo", versao_do_motor="3.1",
                                insumo="um roteiro", quando=QUANDO),
        conteudo_hash=hash_de_conteudo(b"mp4"), mime="video/mp4", duracao_s=15.0)
    lote = LoteDeAssets(canal="DISPLAY", assets=lote.assets + (video,))
    conteudo[video.identidade] = b"mp4"
    e = ponte.imagens_de_display(lote, conteudo)

    assert video in e.veredito.aprovados, (
        "premissa do teste: o vídeo tem de ser APROVADO para provar que a "
        "recusa vem da falta de papel, e não da validação")
    assert e.ok, "o vídeo não pode derrubar as imagens boas"
    assert any("brief.videos" in m for m in e.recusas), e.recusas
    assert len(e.linhagem) == 2, "o vídeo não pode ter virado imagem"


# ════════════════════════════════════════════════════════════════════════════
# PORTÃO — lote reprovado não vira payload
# ════════════════════════════════════════════════════════════════════════════


def test_validar_lote_e_chamado_e_o_veredito_volta_sem_traducao():
    """O critério central da tarefa: `validar_lote()` tem chamador de produção."""
    from volc_ads.criativo.validacao import ResultadoDeValidacao
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    assert isinstance(e.veredito, ResultadoDeValidacao)
    assert e.veredito.canal == "DISPLAY"
    assert e.veredito.fonte, "o veredito tem de dizer contra qual régua julgou"


def test_lote_sem_a_quadrada_obrigatoria_nao_devolve_payload_nenhum():
    banner, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628)
    lote = LoteDeAssets(canal="DISPLAY", assets=(banner,))
    e = ponte.imagens_de_display(lote, {banner.identidade: b1})

    assert e.imagens is None, "payload parcial é o objeto que não pode existir"
    assert not e.ok
    assert e.linhagem == ()
    assert "Q1.faltam" in ponte.violacoes_por_codigo(e)


def test_imagem_fora_de_proporcao_e_reprovada_e_nao_chega_ao_payload():
    """Uma 1:1 no slot 1.91:1 passa em qualquer contagem e é recusada pela API."""
    torta, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 800, 800, semente=b"torta")
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    lote = LoteDeAssets(canal="DISPLAY", assets=(torta, quad))
    e = ponte.imagens_de_display(lote, {torta.identidade: b1, quad.identidade: b2})

    codigos = ponte.violacoes_por_codigo(e)
    assert "D3.proporcao" in codigos, codigos.keys()
    # O banner reprovou, então o papel obrigatório ficou vazio → sem payload.
    assert e.imagens is None
    assert torta not in e.veredito.aprovados


def test_imagem_abaixo_da_dimensao_minima_nao_chega_ao_payload():
    pequena, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 382, 200, semente=b"p")
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    lote = LoteDeAssets(canal="DISPLAY", assets=(pequena, quad))
    e = ponte.imagens_de_display(lote, {pequena.identidade: b1, quad.identidade: b2})
    assert "D1.dimensao_minima" in ponte.violacoes_por_codigo(e)
    assert e.imagens is None


def test_asset_sem_medida_para_em_MEDIR_ANTES_e_nao_vira_aprovacao_por_omissao():
    """Validação ausente NÃO é validação aprovada."""
    cego, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, medido=False)
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    lote = LoteDeAssets(canal="DISPLAY", assets=(cego, quad))
    e = ponte.imagens_de_display(lote, {cego.identidade: b1, quad.identidade: b2})

    from volc_ads.criativo.contrato import Classe
    assert e.veredito.por_classe(Classe.MEDIR_ANTES), "sem medida passou batido"
    assert "M1.sem_medida" in ponte.violacoes_por_codigo(e)
    assert e.imagens is None


def test_o_teto_combinado_de_marketing_derruba_o_lote_e_nao_corta_sozinho():
    """15 é teto do CONJUNTO; escolher qual sai é de quem encomendou o lote."""
    assets, conteudo = [], {}
    for i in range(16):
        a, b = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628,
                      semente=f"banner{i}".encode())
        assets.append(a)
        conteudo[a.identidade] = b
    q, bq = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    assets.append(q)
    conteudo[q.identidade] = bq
    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=tuple(assets)), conteudo)
    assert "Q4.teto_combinado" in ponte.violacoes_por_codigo(e)
    assert e.imagens is None


def test_falhas_do_lote_nao_derrubam_as_imagens_que_deram_certo():
    """20 imagens com 1 recusada são 19 boas e um problema, não um lote perdido."""
    lote, conteudo = _lote_completo()
    lote = LoteDeAssets(canal="DISPLAY", assets=lote.assets, falhas=(
        Falha(referencia="ped-001#3", motivo="o motor recusou o prompt",
              codigo="F2.politica", permanente=True),
    ))
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok, "uma falha de geração não pode derrubar o que foi entregue"
    assert len(e.linhagem) == 2


# ════════════════════════════════════════════════════════════════════════════
# IDENTIDADE — o hash é conferido, não afirmado
# ════════════════════════════════════════════════════════════════════════════


def test_o_hash_da_linhagem_e_recomputavel_dos_bytes_que_entram_no_payload():
    """A prova de que a procedência descreve ESTE arquivo, e não outro."""
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok
    for papel in ImagensDisplay.PAPEIS:
        for img in getattr(e.imagens, papel):
            assert img.linhagem is not None
            assert hash_de_conteudo(img.dados) == img.linhagem.conteudo_hash, (
                f"{img.nome}: a linhagem descreve outro arquivo")


def test_bytes_que_nao_batem_com_o_hash_sao_descartados_com_recusa_nomeada():
    lote, conteudo = _lote_completo()
    banner = lote.assets[0]
    conteudo[banner.identidade] = png(1200, 628, semente=b"OUTRO ARQUIVO")

    e = ponte.imagens_de_display(lote, conteudo)
    assert e.imagens is None, "bytes trocados não podem virar payload"
    assert any("recomputado" in m for m in e.recusas), e.recusas
    # E o motivo verdadeiro aparece: o lote foi aprovado, faltou o conteúdo.
    assert any("faltou foi o conteúdo" in m for m in e.recusas), e.recusas


def test_asset_sem_bytes_no_mapa_nao_vira_asset_disponivel():
    lote, conteudo = _lote_completo()
    del conteudo[lote.assets[0].identidade]
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.imagens is None
    assert any("não persistido não é asset disponível" in m for m in e.recusas)
    # O veredito da VALIDAÇÃO continua aprovado — as duas perguntas são
    # diferentes, e confundi-las esconderia qual delas falhou.
    assert e.veredito.ok, "o lote era bom; o que faltou foram os bytes"


def test_bytes_vazios_contam_como_ausencia_e_nao_como_arquivo_de_zero_byte():
    lote, conteudo = _lote_completo()
    conteudo[lote.assets[0].identidade] = b""
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.imagens is None
    assert any("sem bytes em mãos" in m for m in e.recusas)


def test_asset_ja_existente_na_conta_e_recusado_com_o_motivo_e_o_caminho():
    """Rebaixá-lo em silêncio para um `str` perderia a linhagem sem avisar."""
    ja, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628,
                    id_externo="customers/8017851692/assets/999111")
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    lote = LoteDeAssets(canal="DISPLAY", assets=(ja, quad))
    e = ponte.imagens_de_display(lote, {ja.identidade: b1, quad.identidade: b2})
    assert any("já existe na conta" in m for m in e.recusas), e.recusas
    assert any("a linhagem não acompanha" in m for m in e.recusas)
    assert e.imagens is None  # o papel obrigatório esvaziou


def test_o_mesmo_conteudo_duas_vezes_no_mesmo_papel_e_deduplicado():
    a1, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente=b"igual")
    a2, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente=b"igual")
    assert a1.conteudo_hash == a2.conteudo_hash
    q, bq = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(a1, a2, q)),
        {a1.identidade: b1, a2.identidade: b2, q.identidade: bq})
    assert e.ok
    assert len(e.imagens.marketing) == 1, "duas cópias gastariam duas vagas do teto"
    assert any("conteúdo idêntico" in m for m in e.recusas)


def test_o_mesmo_arquivo_em_dois_papeis_NAO_e_deduplicado():
    """Uma 1:1 é logo quadrada e marketing quadrada ao mesmo tempo — legítimo."""
    dados = png(600, 600, semente=b"serve-aos-dois")
    comum = dict(conteudo_hash=hash_de_conteudo(dados), bytes_totais=len(dados),
                 mime="image/png", largura=600, altura=600)
    p = Procedencia(motor="m", versao_do_motor="1", insumo="i", quando=QUANDO)
    quad = Asset(tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA, procedencia=p, **comum)
    logoq = Asset(tipo=TipoDeAsset.LOGO_QUADRADO, procedencia=p, **comum)
    banner, bb = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628)

    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(banner, quad, logoq)),
        {banner.identidade: bb, quad.identidade: dados, logoq.identidade: dados})
    assert e.ok, e.resumo()
    assert len(e.imagens.marketing_quadrada) == 1
    assert len(e.imagens.logo_quadrado) == 1
    assert len(e.linhagem) == 3
    # Mesmo hash, papéis diferentes — e as duas linhagens existem.
    assert (e.imagens.marketing_quadrada[0].linhagem.conteudo_hash
            == e.imagens.logo_quadrado[0].linhagem.conteudo_hash)


# ════════════════════════════════════════════════════════════════════════════
# LINHAGEM — o que ela carrega, e o que ela se recusa a inventar
# ════════════════════════════════════════════════════════════════════════════


def test_a_linhagem_carrega_a_procedencia_inteira():
    banner, b1 = _asset(
        TipoDeAsset.IMAGEM_MARKETING, 1200, 628, motor="openai:gpt-image-2",
        versao="2026-08", insumo="banner de FGTS, tom sóbrio", custo=0.04,
        rotulo="fgts-banner", derivado_de="cri_paidopai", origem=Origem.DERIVADO)
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(banner, quad)),
        {banner.identidade: b1, quad.identidade: b2})
    assert e.ok, e.resumo()

    ln = e.imagens.marketing[0].linhagem
    assert ln.motor == "openai:gpt-image-2"
    assert ln.versao_do_motor == "2026-08"
    assert ln.insumo == "banner de FGTS, tom sóbrio"
    assert ln.insumo_hash == banner.procedencia.insumo_hash
    assert ln.conteudo_hash == banner.conteudo_hash
    assert ln.identidade == banner.identidade
    assert ln.mime == "image/png"
    assert (ln.largura, ln.altura) == (1200, 628)
    assert ln.bytes_totais == len(b1)
    assert ln.custo_usd == 0.04
    assert ln.quando == QUANDO.isoformat()
    assert ln.origem == "derivado"
    assert ln.derivado_de == "cri_paidopai", "a transformação aplicada se perdeu"
    assert ln.pedido == "ped-001"
    assert ln.papel == "marketing"
    assert ln.confirmada is True


def test_a_linhagem_registra_contra_qual_regua_o_arquivo_foi_julgado():
    """Um veredito sem a régua não é auditável seis meses depois."""
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    exigencia = requisitos.exigencia_binaria_de("DISPLAY")
    for ln in e.linhagem:
        assert ln.exigencia_fonte == exigencia.fonte
        assert ln.exigencia_provisoria is exigencia.provisorio
    assert "matriz-api" in e.linhagem[0].exigencia_fonte


def test_custo_ausente_viaja_como_None_e_nunca_como_zero():
    """`0.0` afirmaria que a imagem foi de graça. `None` diz que não se sabe."""
    lote, conteudo = _lote_completo(custo=None)
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok
    for ln in e.linhagem:
        assert ln.custo_usd is None
        assert ln.para_json()["custo_usd"] is None


def test_mime_ausente_e_reprovado_e_por_isso_nao_chega_ao_payload():
    """A régua de DISPLAY cobra mime — descoberto ao escrever este teste.

    A primeira versão dele assumia que mime era opcional e afirmava que a
    imagem passaria com `confirmada is False`. A `requisitos.yaml` desmentiu:
    `padroes.imagem.mimes` vale para as quatro famílias, e sem mime o asset
    para em `M1.sem_medida`. O teste passou a provar o que é verdade.
    """
    from volc_ads.criativo.contrato import Classe
    dados = png(1200, 628, semente=b"sem-mime")
    banner = Asset(
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        procedencia=Procedencia(motor="m", versao_do_motor="1", insumo="i",
                                quando=QUANDO),
        conteudo_hash=hash_de_conteudo(dados), bytes_totais=len(dados),
        mime=None, largura=1200, altura=628)
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(banner, quad)),
        {banner.identidade: dados, quad.identidade: b2})
    assert not e.ok
    assert e.veredito.por_classe(Classe.MEDIR_ANTES)
    assert banner in e.veredito.reprovados


def test_o_que_passa_pela_regua_do_display_sai_com_procedencia_confirmada():
    """E isso NÃO é decreto: é acoplamento entre a régua e a confirmação.

    `confirmada` exige identidade, hash, motor, insumo, instante, mime e as
    duas dimensões. A validação de DISPLAY já cobra mime e dimensão; `Asset` e
    `Procedencia` já cobram os outros nos seus `__post_init__`. Logo, para este
    canal, "aprovado" implica "confirmado".

    O teste existe para o dia em que essa implicação deixar de valer — um canal
    novo com régua mais frouxa, ou um campo a mais em `confirmada`. Nesse dia
    ele falha, e a pergunta "o recibo ainda sabe de onde veio o criativo?"
    aparece antes de a resposta virar não.
    """
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok
    for ln in e.linhagem:
        assert ln.confirmada is True, f"{ln.nome} passou na régua sem procedência"


def test_linhagem_montada_a_mao_nao_se_diz_confirmada():
    """Procedência incompleta não vira procedência confirmada.

    O caminho que produz linhagem incompleta não é a ponte — é o operador que
    monta `ImagemParaSubir` por fora. `Linhagem.desconhecida` é o que representa
    esse caso, e ela nunca se declara confirmada.
    """
    magra = Linhagem.desconhecida("montada-a-mao", "marketing")
    assert magra.confirmada is False
    assert magra.para_json()["confirmada"] is False
    # Nem mesmo quase-completa: falta o instante, e isso basta.
    quase = Linhagem(
        nome="quase", papel="marketing", identidade="cri_1",
        conteudo_hash="sha256:" + "a" * 64, motor="m", insumo="i",
        mime="image/png", largura=600, altura=314)
    assert quase.quando is None
    assert quase.confirmada is False, "sem instante de geração não há rastro"


def test_datetime_ingenuo_viaja_sem_offset_em_vez_de_ganhar_um_inventado():
    """Assumir UTC inventaria informação; recusar inventaria uma exigência.

    `Procedencia` não declara se `quando` é aware ou naive, e as fixtures da
    casa usam naive. A ausência de offset na string É a resposta honesta.
    """
    ingenuo = datetime(2026, 8, 27, 15, 30, 0)
    lote, conteudo = _lote_completo(quando=ingenuo)
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok
    quando = e.linhagem[0].quando
    assert quando == "2026-08-27T15:30:00"
    assert "+" not in quando and not quando.endswith("Z"), "fuso inventado"


def test_o_offset_declarado_sobrevive_a_travessia():
    saopaulo = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone(timedelta(hours=-3)))
    lote, conteudo = _lote_completo(quando=saopaulo)
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.linhagem[0].quando == "2026-08-27T12:00:00-03:00"


def test_asset_sem_rotulo_recebe_a_identidade_como_nome():
    """Nome vazio é impossível (`ImagemParaSubir` recusa) e inventado é pior."""
    lote, conteudo = _lote_completo(rotulo="")
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok
    for papel in ImagensDisplay.PAPEIS:
        for img in getattr(e.imagens, papel):
            assert img.nome == img.linhagem.identidade
            assert img.nome.startswith("cri_")


# ════════════════════════════════════════════════════════════════════════════
# ORDEM E UNICIDADE — até o payload
# ════════════════════════════════════════════════════════════════════════════


def test_a_linhagem_da_entrega_e_a_de_ImagensDisplay_sao_a_mesma_lista():
    """Duas declarações da mesma ordem divergiriam; esta prova que é uma só."""
    banner, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente=b"a")
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"b")
    logo, b3 = _asset(TipoDeAsset.LOGO_PAISAGEM, 1024, 256, semente=b"c")
    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(logo, banner, quad)),
        {banner.identidade: b1, quad.identidade: b2, logo.identidade: b3})
    assert e.ok
    # LISTA, não conjunto: conjunto passaria com as posições trocadas.
    assert list(e.linhagem) == list(e.imagens.linhagens())
    # E a ordem é a canônica dos PAPÉIS, não a ordem de entrada do lote.
    assert [ln.papel for ln in e.linhagem] == [
        "marketing", "marketing_quadrada", "logo"]


def test_a_ponte_chega_ate_o_mutate_com_a_linhagem_alinhada():
    """A fatia inteira, ponta a ponta e offline: lote → payload → linhagem."""
    from volc_ads.campanha import display

    banner, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente=b"a",
                        rotulo="banner")
    quad, b2 = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600,
                      semente=b"b", rotulo="quadrado")
    logo, b3 = _asset(TipoDeAsset.LOGO_PAISAGEM, 1024, 256, semente=b"c",
                      rotulo="logo-larga")
    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(banner, quad, logo)),
        {banner.identidade: b1, quad.identidade: b2, logo.identidade: b3})
    assert e.ok, e.resumo()

    brief = _brief_com(e.imagens)
    ops, r = display.construir("8017851692", brief, login_customer_id="6016739364")
    assert r.ok, [str(a) for a in r.achados]

    nomes_no_payload = [
        o.asset_operation.create.name for o in ops
        if o._pb.WhichOneof("operation") == "asset_operation"]
    assert nomes_no_payload == [ln.nome for ln in e.linhagem]
    assert nomes_no_payload == ["banner", "quadrado", "logo-larga"]

    # Os ids temporários: únicos, contíguos e na faixa própria de imagem.
    rns = [o.asset_operation.create.resource_name for o in ops
           if o._pb.WhichOneof("operation") == "asset_operation"]
    assert len(set(rns)) == len(rns), "id temporário repetido"
    assert rns == [f"customers/8017851692/assets/{-200 - i}" for i in range(3)]

    # E os bytes que saem no mutate são os que a linhagem descreve.
    for op, ln in zip(
            [o for o in ops if o._pb.WhichOneof("operation") == "asset_operation"],
            e.linhagem):
        assert hash_de_conteudo(op.asset_operation.create.image_asset.data) == \
            ln.conteudo_hash


def test_uma_imagem_da_ponte_nao_dispara_o_aviso_de_linhagem_ausente():
    """A contraprova do aviso: quem passou pela ponte não é acusado."""
    from volc_ads.campanha import display
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    brief = _brief_com(e.imagens)
    _, r = display.construir("8017851692", brief, login_customer_id="6016739364")
    assert not [a for a in r.achados if "sem linhagem" in a.motivo]
    assert not [a for a in r.achados if "linhagem incompleta" in a.motivo]


# ════════════════════════════════════════════════════════════════════════════
# ESTRUTURA — a ponte é caminho único, não conselho
# ════════════════════════════════════════════════════════════════════════════


def _chamadas_a(nome: str, arquivo: pathlib.Path) -> int:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    n = 0
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        if isinstance(f, ast.Name) and f.id == nome:
            n += 1
        elif isinstance(f, ast.Attribute) and f.attr == nome:
            n += 1
    return n


def test_so_a_ponte_constroi_ImagemParaSubir_dentro_de_volc_ads():
    """Higiene de caminho único dentro de `volc_ads` — e SÓ isso.

    ## O que este guard NÃO garante, e a revisão provou

    Ele conta `ast.Call` cujo `func` se chama `ImagemParaSubir`. Três evasões
    triviais passam por baixo, e a adversarial de 27/08/2026 as demonstrou:

        from ...brief import ImagemParaSubir as IPS ; IPS(...)   alias
        getattr(brief, "ImagemParaSubir")(...)                   getattr
        dataclasses.replace(img_da_ponte, dados=outros_bytes)     replace

    A terceira é a mais perigosa e a mais provável de alguém escrever de
    boa-fé, porque preserva a linhagem `confirmada` do arquivo ANTIGO.

    **A defesa real não é este guard — é a conferência de hash** em
    `subir._linhagem_do_payload`, que compara a linhagem com os bytes que vão
    sair. Ela pega as três evasões, e pega também o código de `backend/`,
    `api/` e `scripts/`, que este guard nem varre. Ver
    `test_bytes_trocados_depois_da_ponte_perdem_a_procedencia`.

    Isto aqui continua valendo como higiene: mantém `volc_ads` com um caminho
    só, e falha cedo se alguém abrir um segundo. Mas não é a garantia.

    ⚠️ A permissão é por CAMINHO relativo, não por `arquivo.name`: comparar por
    nome isentaria qualquer `volc_ads/*/criativo_ponte.py`.
    """
    permitidos = {"volc_ads/criativo_ponte.py"}
    infratores = []
    for arquivo in sorted(RAIZ.joinpath("volc_ads").rglob("*.py")):
        relativo = str(arquivo.relative_to(RAIZ))
        if relativo in permitidos or arquivo.name.startswith("testes_"):
            continue
        if _chamadas_a("ImagemParaSubir", arquivo):
            infratores.append(relativo)
    assert not infratores, (
        "estes arquivos montam `ImagemParaSubir` fora da ponte, e por isso sem "
        f"validação de geometria nem linhagem: {infratores}")


def test_o_guard_de_estrutura_realmente_enxerga_uma_construcao():
    """Um guard que não detecta nada fica verde para sempre — este detecta.

    Sem esta contraprova, `_chamadas_a` poderia estar quebrado e o teste acima
    passaria por não achar nada em lugar nenhum.
    """
    assert _chamadas_a("ImagemParaSubir", RAIZ / "volc_ads/criativo_ponte.py") >= 1
    assert _chamadas_a("NaoExisteEsteNome", RAIZ / "volc_ads/criativo_ponte.py") == 0


def test_a_ponte_nao_le_o_relogio_da_maquina():
    """Instante de geração vem do asset. Um `now()` aqui inventaria o fato."""
    fonte = (RAIZ / "volc_ads/criativo_ponte.py").read_text(encoding="utf-8")
    for proibido in ("datetime.now(", "datetime.utcnow(", "time.time("):
        assert proibido not in fonte, f"a ponte lê o relógio: {proibido}"


#: Componentes de caminho de modulo que alcancam escrita real.
_PROIBIDOS = ("gads", "google")
#: Nomes que, chamados, abrem escrita ou falam com a API.
_PERIGOSAS = ("destravar", "mutar", "validar_mutacoes", "exigir_leitura_apenas")


def _literais_de_codigo(arvore: ast.AST) -> list[str]:
    """Strings que sao CODIGO, nunca documentacao.

    ⚠️ Docstrings sao excluidos de proposito. A versao anterior varria todo
    `ast.Constant` e acusava um arquivo que apenas ESCREVIA num comentario
    "quem fala com a API e volc_ads.gads.client" — sem importar nada. Isso e
    exatamente o que o guard de ciclo ao lado ja aprendeu a evitar: confundir
    citacao com dependencia ensina a apagar documentacao para ficar verde.
    """
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef,
                           ast.AsyncFunctionDef)):
            corpo = getattr(no, "body", None) or []
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                docstrings.add(id(corpo[0].value))

    saida: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and id(no) not in docstrings:
            if isinstance(no.value, str):
                saida.append(no.value)
            elif isinstance(no.value, bytes):
                # `b"volc_ads.gads.modo".decode()` escapava por nao ser str.
                try:
                    saida.append(no.value.decode("utf-8"))
                except UnicodeDecodeError:
                    pass
        elif isinstance(no, ast.JoinedStr):
            # f-string: junta as partes literais. `f"volc_ads.{x}.modo"` vira
            # "volc_ads..modo", que ainda casa por componente.
            saida.append("".join(
                parte.value for parte in no.values
                if isinstance(parte, ast.Constant) and isinstance(parte.value, str)))
        elif isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
            # Soma de literais: `'volc_ads.' + 'ga' + 'ds' + '.modo'`.
            pedacos: list[str] = []

            def _colher(n):
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
                    _colher(n.left)
                    _colher(n.right)
                elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                    pedacos.append(n.value)

            _colher(no)
            if pedacos:
                saida.append("".join(pedacos))
    return saida


def alcanca_escrita(caminho: pathlib.Path) -> list[str]:
    """As formas ESTATICAS de um arquivo alcancar o SDK ou a trava.

    ## O que ela NAO garante, e isto precisa estar escrito

    Uma varredura estatica **nunca** e completa contra evasao dinamica:
    `chr()`, `globals()`, `__builtins__`, string vinda de arquivo ou de
    variavel de ambiente passam por baixo de qualquer versao disto. A versao
    anterior deste docstring dizia "TODAS as formas" e era falsa — e o ciclo 4
    da revisao mostrou tres evasoes que passavam: f-string, soma de literais e
    bytes decodificados.

    **A protecao real de escrita nao e este AST.** E `gads/modo.py`: dois
    fatores, `destravar()` no codigo E `FORGE_PERMITIR_ESCRITA=1` no ambiente,
    com `exigir_leitura_apenas` levantando antes de qualquer byte sair. Isto
    aqui e higiene: pega o descuido e o obscurecimento barato, e falha cedo se
    alguem abrir um segundo caminho sem querer.

    ATENCAO: isto e uma FUNCAO, e nao o corpo de um teste, por um motivo
    medido. A versao anterior era um bloco de asserts dentro do teste, e a
    "contraprova" dele reimplementava a regra sobre uma arvore sintetica em vez
    de chamar o guard. O teste chamado "o guard pega as tres evasoes" ficava
    VERDE com o guard cego. Uma contraprova que nao executa o codigo que ela diz
    provar e a forma mais pura de prova que aceita qualquer erro.

    E a comparacao e por COMPONENTE do caminho, nao por prefixo. A versao
    anterior fazia `literal.split(".")[0] not in ("gads","google")` — e o
    literal da evasao real e "volc_ads.gads.modo", cujo primeiro componente e
    `volc_ads`. O guard so pegava "gads.modo", que e justamente a string que NAO
    importa nada, porque o pacote real e `volc_ads.gads`.
    """
    achados: list[str] = []
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))

    for modulo in _modulos_importados(caminho):
        if any(parte in _PROIBIDOS for parte in modulo.split(".")):
            achados.append(f"import de {modulo!r}")

    for texto in _literais_de_codigo(arvore):
        alvo = texto.strip()
        if alvo == "FORGE_PERMITIR_ESCRITA":
            achados.append("literal da variavel da trava")
        if alvo in _PERIGOSAS:
            achados.append(f"literal que abre escrita por getattr: {alvo!r}")
        # ⚠️ So o que TEM CARA de caminho de modulo. Sem isto, uma frase de
        # comentario ou de mensagem de erro contendo a palavra vira acusacao.
        if " " in alvo or "\n" in alvo:
            continue
        if any(parte in _PROIBIDOS for parte in alvo.split(".")):
            achados.append(f"literal que alcanca o SDK: {alvo!r}")

    for nome in _PERIGOSAS:
        if _chamadas_a(nome, caminho):
            achados.append(f"chamada a {nome}()")
    return achados


def test_a_ponte_nao_importa_o_sdk_do_google_nem_a_trava():
    """Ela monta dados. Falar com a API e do construtor, e escrever e de subir."""
    achados = alcanca_escrita(RAIZ / "volc_ads/criativo_ponte.py")
    assert achados == [], achados


def test_o_guard_de_escrita_PEGA_as_evasoes_reais(tmp_path):
    """CONTRAPROVA QUE CHAMA O GUARD — a anterior nao chamava.

    Escreve uma ponte adulterada que destrava e muta por import dinamico e
    `getattr`, e exige que `alcanca_escrita` a acuse. Sem isto, o guard acima
    pode voltar a ficar cego sem ninguem notar.
    """
    adulterada = tmp_path / "ponte_falsa.py"
    adulterada.write_text(
        "from importlib import import_module\n"
        "def _atalho(cid, ops):\n"
        "    modo = import_module('volc_ads.gads.modo')\n"
        "    cli = import_module('volc_ads.gads.client')\n"
        "    with getattr(modo, 'destravar')('subida direta pela ponte'):\n"
        "        return getattr(cli, 'mutar')(cid, ops)\n",
        encoding="utf-8")
    achados = alcanca_escrita(adulterada)
    assert achados, "o guard passou uma ponte que destrava e MUTA"
    assert any("volc_ads.gads.modo" in a for a in achados), achados
    assert any("destravar" in a for a in achados), achados

    for linha in ("import gads",
                  "from volc_ads import gads",
                  "from volc_ads.gads.modo import destravar as abrir",
                  "from google.ads.googleads.client import mutar"):
        outro = tmp_path / "outro.py"
        outro.write_text(linha + "\n", encoding="utf-8")
        assert alcanca_escrita(outro), f"escapou: {linha}"

    # As tres evasoes que o ciclo 4 mostrou passando.
    evasoes = {
        "f-string": 'x = import_module(f"volc_ads.{\'ga\' + \'ds\'}.modo")\n',
        "soma de literais": 'x = import_module("volc_ads." + "ga" + "ds" + ".modo")\n',
        "bytes decodificados": 'x = import_module(b"volc_ads.gads.modo".decode())\n',
    }
    for nome, codigo in evasoes.items():
        arq = tmp_path / "ev.py"
        arq.write_text(codigo, encoding="utf-8")
        assert alcanca_escrita(arq), f"escapou por {nome}"


def test_o_guard_de_escrita_nao_acusa_documentacao(tmp_path):
    """E ele NAO pode acusar quem so CITA o caminho num docstring.

    Um guard que confunde citacao com dependencia ensina a apagar documentacao
    para ficar verde — e o ciclo 4 mostrou este arquivo exato sendo acusado.
    """
    limpo = tmp_path / "limpo.py"
    limpo.write_text(
        '"""Quem fala com a API e volc_ads.gads.client; aqui nao se escreve."""\n'
        "import json\n"
        "def f(x):\n"
        '    """Nao chama destravar nem mutar; ver volc_ads.gads.modo."""\n'
        "    return json.dumps({'nota': 'nada aqui fala com a API'})\n",
        encoding="utf-8")
    assert alcanca_escrita(limpo) == [], alcanca_escrita(limpo)


def test_a_ponte_nao_promete_o_que_nao_faz():
    """Sem `NotImplementedError`, sem `TODO`, sem campo 'para o futuro'."""
    fonte = (RAIZ / "volc_ads/criativo_ponte.py").read_text(encoding="utf-8")
    assert "NotImplementedError" not in fonte
    assert "TODO" not in fonte


def _modulos_importados(arquivo: pathlib.Path) -> set[str]:
    """Só IMPORTS, via AST.

    ⚠️ A primeira versão desta checagem procurava a substring no arquivo
    inteiro e acusava `brief.py` — que apenas *menciona* a ponte num docstring,
    para dizer ao leitor onde a linhagem é montada. Um guard que confunde
    citação com dependência ensina a apagar documentação para ficar verde.
    """
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            # `from . import x` tem module None; o que interessa é o alvo.
            nomes.update(
                f"{no.module or ''}.{a.name}" if no.module else a.name
                for a in no.names)
            if no.module:
                nomes.add(no.module)
    return nomes


def test_criativo_e_campanha_continuam_sem_conhecer_a_ponte():
    """A direção da dependência é de mão única, e é o que evita o ciclo."""
    for pasta in ("criativo", "campanha"):
        for arquivo in sorted(RAIZ.joinpath("volc_ads", pasta).rglob("*.py")):
            if arquivo.name.startswith("testes_"):
                continue
            importados = _modulos_importados(arquivo)
            assert not any("criativo_ponte" in m for m in importados), (
                f"{arquivo.name} importa a ponte — isso fecha um ciclo")


def test_o_guard_de_ciclo_enxerga_um_import_de_verdade():
    """Contraprova: sem ela, o guard acima poderia estar cego e ficar verde."""
    da_ponte = _modulos_importados(RAIZ / "volc_ads/criativo_ponte.py")
    assert any("campanha.brief" in m for m in da_ponte), da_ponte
    assert any("criativo" in m for m in da_ponte), da_ponte


def test_criativo_continua_sem_importar_campanha():
    """`criativo/requisitos.py` lê `limites.yaml` como ARQUIVO justamente por isso."""
    for arquivo in sorted(RAIZ.joinpath("volc_ads/criativo").rglob("*.py")):
        if arquivo.name.startswith("testes_"):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                assert "campanha" not in no.module, (
                    f"{arquivo.name} importa campanha.{no.module}")


#: Arquivos que JÁ dependiam de Pillow antes desta fatia, com o estado real.
#:
#: `funnelforge_imagem.py:84` faz `from PIL import Image` DENTRO de `_medir`,
#: com `except ImportError` devolvendo `(None, None, None)`. Pillow não está em
#: `backend/requirements.txt`, `requirements-dev.txt` nem
#: `requirements-graphify.txt` — está só no venv. Isso é uma dependência não
#: declarada, e é um defeito de verdade: no ambiente sem Pillow aquele
#: adaptador para de medir em silêncio.
#:
#: ⚠️ Ele NÃO é consertado aqui, e não é apagado para o portão ficar verde.
#: É código de outro dono (o adaptador do motor pago), fora do escopo desta
#: fatia, e removê-lo esconderia um problema em vez de resolvê-lo. Fica
#: nomeado para que a próxima pessoa o encontre.
#: ⚠️ `testes_motor.py` entrou nesta lista pela revisão adversarial de
#: 27/08/2026: ele faz `pytest.importorskip("PIL.Image")`, um import por
#: STRING que a primeira versão de `_importa_pillow` não enxergava. A
#: afirmação "funnelforge_imagem é o único importador" era verdadeira só no
#: eixo AST — e um guard que só vê o caso ingênuo dá uma garantia que não tem.
#: ⚠️ Por CAMINHO relativo, nunca por `arquivo.name`. Comparar por basename
#: isentaria qualquer `volc_ads/<outra_pasta>/testes_motor.py` novo — a mesma
#: classe de defeito que o guard vizinho de `ImagemParaSubir` já corrigiu, e
#: que este aqui tinha mantido.
#: ⚠️ `destinos.py` e `testes_destinos.py` entraram em 01/09/2026, e a decisão
#: está aqui em vez de a lista ter crescido em silêncio — que é para isso que
#: este guard existe. O P17-T08 pede provar a diferença entre RECOMPOSIÇÃO e
#: CROP "medindo os pixels, não confiando no nome", e medir pixel é ler pixel.
#: O uso é sob demanda e falha explícita: `_pillow()` devolve `None` quando
#: Pillow não está lá e o chamador levanta `MedicaoDePixelsIndisponivel` — não
#: existe caminho em que a ausência da biblioteca vire um veredito de adaptação
#: dado de graça. E Pillow já está em `backend/requirements.txt` como
#: CAPACIDADE DE PRODUTO, com o motivo escrito lá: sem ela a peça sai na
#: dimensão nativa do provider em vez da pedida.
PILLOW_HERDADO = {
    "volc_ads/criativo/adaptadores/funnelforge_imagem.py",
    "volc_ads/criativo/testes_motor.py",
    "volc_ads/criativo/destinos.py",
    "volc_ads/criativo/testes_destinos.py",
}

#: Funções que importam por string e por isso escapam de `ast.Import`.
_IMPORTA_POR_STRING = {"importorskip", "import_module", "__import__"}


def _importa_pillow(arquivo: pathlib.Path) -> bool:
    """Detecta `import PIL`, `from PIL import …` E o import por string.

    O eixo AST sozinho é insuficiente: `importorskip("PIL.Image")` e
    `import_module("PIL")` trazem Pillow sem produzir um nó `Import`.
    """
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            if any(a.name.split(".")[0] == "PIL" for a in no.names):
                return True
        elif isinstance(no, ast.ImportFrom) and no.module:
            if no.module.split(".")[0] == "PIL":
                return True
        elif isinstance(no, ast.Call):
            alvo = no.func
            nome = (alvo.attr if isinstance(alvo, ast.Attribute)
                    else alvo.id if isinstance(alvo, ast.Name) else "")
            if nome not in _IMPORTA_POR_STRING:
                continue
            for arg in no.args:
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and arg.value.split(".")[0] == "PIL"):
                    return True
    return False


def test_o_codigo_desta_fatia_nao_depende_de_pillow():
    """O medidor é stdlib. Se deixar de ser, a medida some no ambiente sem PIL."""
    for caminho in ("volc_ads/criativo_ponte.py",
                    "volc_ads/criativo/adaptadores/medir_imagem.py"):
        assert not _importa_pillow(RAIZ / caminho), f"{caminho} importa Pillow"


def test_a_lista_de_pillow_herdado_continua_exata():
    """Nem cresce sem alguém notar, nem encolhe sem alguém consertar.

    Se um arquivo novo passar a importar Pillow, este teste falha e a decisão
    volta à mesa. Se `funnelforge_imagem` deixar de importar, ele também falha
    — e aí a exceção deve sair desta lista, não ser mantida por inércia.
    """
    encontrados = {
        str(a.relative_to(RAIZ))
        for a in sorted(RAIZ.joinpath("volc_ads").rglob("*.py"))
        if _importa_pillow(a)
    }
    assert encontrados == PILLOW_HERDADO, (
        f"a dependência de Pillow em volc_ads mudou: {encontrados} "
        f"(esperado {PILLOW_HERDADO})")


# ════════════════════════════════════════════════════════════════════════════
# CANAIS VIZINHOS — Search e os não implementados
# ════════════════════════════════════════════════════════════════════════════


def test_search_nao_passa_por_aqui_e_diz_quem_e_o_dono():
    lote = LoteDeAssets(canal="SEARCH")
    with pytest.raises(ValueError, match="campanha/validacao.py"):
        ponte.imagens_de_display(lote, {})


def test_canal_desconhecido_levanta_em_vez_de_devolver_lote_vazio():
    with pytest.raises(ValueError, match="TIKTOK"):
        ponte.imagens_de_display(LoteDeAssets(canal="TIKTOK"), {})


def test_a_exigencia_pode_ser_injetada_sem_reler_o_yaml():
    """Para um canal futuro, ou para provar contra uma régua hipotética."""
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(
        lote, conteudo, exigencia=requisitos.exigencia_binaria_de("DISPLAY"))
    assert e.ok


# ════════════════════════════════════════════════════════════════════════════
# PROJEÇÃO para o diário do construtor
# ════════════════════════════════════════════════════════════════════════════


def test_anexar_escreve_as_violacoes_no_Resultado_de_campanha_preservando_severidade():
    from volc_ads.campanha import validacao as vc
    banner, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 800, 800, semente=b"torta")
    lote = LoteDeAssets(canal="DISPLAY", assets=(banner,))
    e = ponte.imagens_de_display(lote, {banner.identidade: b1})

    r = vc.Resultado()
    ponte.anexar(e, r)
    assert not r.ok, "a proporção errada tem de derrubar o resultado"
    assert any("D3.proporcao" in a.valor for a in r.achados)
    assert any("saneavel_em_codigo" in a.motivo for a in r.achados), \
        "a classe é o remédio e não pode se perder na projeção"


def test_anexar_nao_promove_aviso_a_erro():
    """Portão com falso positivo é portão que alguém desliga."""
    from volc_ads.campanha import validacao as vc
    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    r = vc.Resultado()
    ponte.anexar(e, r)
    # O lote é válido; sem logo há apenas `Q3.abaixo_do_recomendado`, um aviso.
    assert r.ok, [f"{a.severidade} {a.campo} {a.motivo}" for a in r.achados]


# ════════════════════════════════════════════════════════════════════════════
# O RECIBO DESCREVE O PAYLOAD, NÃO A INTENÇÃO
# ════════════════════════════════════════════════════════════════════════════


def test_search_com_imagens_display_nao_contamina_a_linhagem_do_recibo():
    """GUARDA DE REGRESSÃO de um defeito que existiu e foi reproduzido.

    A primeira versão de `subir._linhagem_do_brief` lia o BRIEF. Um brief de
    Search com `imagens_display` preenchido devolvia 1 linhagem enquanto
    `search.construir` — que ignora esse campo por completo — criava 0 assets
    de imagem. O recibo gravaria a procedência de uma imagem que nunca nasceu.

    `campos_operados` do perfil já dizia que `imagens_display` não é de Search,
    mas declaração não é guarda: nada a aplicava. Agora a autoridade é o
    payload, como em `_nome_campanha`.
    """
    from volc_ads import subir
    from volc_ads.campanha import search
    from volc_ads.campanha.brief import Brief, Copy

    b = Brief(
        nicho="FGTS", slug="fgts", url_final="https://exemplo.com.br/",
        keywords=["fgts"], copy=Copy(headlines=["t"], descriptions=["d"]),
        imagens_display=ImagensDisplay(marketing=[
            ImagemParaSubir(
                nome="banner", dados=png(1200, 628),
                linhagem=Linhagem(nome="banner", papel="marketing",
                                  motor="motor-de-teste"))]))
    ops, _ = search.construir("8017851692", b, login_customer_id="6016739364")

    assert len(subir._linhagem_do_brief(b)) == 1, "premissa: o brief declara uma"
    assert subir._imagens_criadas(ops) == [], "Search não cria asset de imagem"
    assert subir._linhagem_do_payload(b, ops) == (), (
        "o recibo de Search descreveria uma imagem que nunca foi criada")


def test_em_display_a_linhagem_do_payload_bate_com_a_do_brief():
    """A contraprova: onde as imagens nascem de verdade, nada é perdido."""
    from volc_ads import subir
    from volc_ads.campanha import display

    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    brief = _brief_com(e.imagens)
    ops, r = display.construir("8017851692", brief, login_customer_id="6016739364")
    assert r.ok, [str(a) for a in r.achados]

    do_payload = subir._linhagem_do_payload(brief, ops)
    assert list(do_payload) == list(e.linhagem), "a linhagem se perdeu no caminho"
    assert [ln.nome for ln in do_payload] == [n for n, _ in subir._imagens_criadas(ops)]
    assert all(ln.confirmada for ln in do_payload)


def test_asset_de_texto_do_search_nao_e_contado_como_imagem():
    """Sitelink e callout são `asset_operation` sem `image_asset.data`.

    Contá-los atribuiria procedência de IMAGEM a um asset de TEXTO — e o
    recibo diria que um sitelink saiu de um motor de imagem.
    """
    from volc_ads import subir
    from volc_ads.campanha import search
    from volc_ads.campanha.brief import Brief, Copy, Sitelink

    b = Brief(
        nicho="FGTS", slug="fgts", url_final="https://exemplo.com.br/",
        keywords=["fgts"],
        copy=Copy(
            # Três títulos DISTINTOS: duplicados são removidos e o mínimo de 3
            # não seria atingido — a premissa do teste morreria em silêncio.
            headlines=["Antecipe seu FGTS", "Simule o saque agora",
                       "Veja seu valor hoje"],
            descriptions=["Simule agora e veja o valor disponível.",
                          "Consulta rápida e sem burocracia."],
            sitelinks=[Sitelink(texto="Simular", descricao1="Rápido",
                                descricao2="E sem burocracia"),
                       Sitelink(texto="Como funciona", descricao1="Passo a passo",
                                descricao2="Em poucos minutos")],
            callouts=["Simulação rápida", "Atendimento digital"]))
    ops, _ = search.construir("8017851692", b, login_customer_id="6016739364")

    de_asset = [o for o in ops if o._pb.WhichOneof("operation") == "asset_operation"]
    assert de_asset, "premissa: Search monta assets de texto neste brief"
    assert subir._imagens_criadas(ops) == [], (
        f"{len(de_asset)} assets de texto foram contados como imagem")


def test_imagem_a_mao_no_payload_entra_como_desconhecida_e_nao_desloca():
    """Posição sem procedência apurada não encurta a lista."""
    from volc_ads import subir
    from volc_ads.campanha import display

    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    # Uma imagem montada por fora, sem linhagem, no meio do papel.
    e.imagens.marketing.insert(0, ImagemParaSubir(
        nome="intrusa", dados=png(1200, 628, semente=b"intrusa"),
        mime="image/png", largura=1200, altura=628))

    brief = _brief_com(e.imagens)
    ops, r = display.construir("8017851692", brief, login_customer_id="6016739364")
    assert r.ok

    do_payload = subir._linhagem_do_payload(brief, ops)
    assert len(do_payload) == len(subir._imagens_criadas(ops)) == 3
    assert [ln.nome for ln in do_payload] == ["intrusa", "principal", "principal"]
    assert do_payload[0].papel == "marketing", (
        "a intrusa tem linhagem `desconhecida` vinda do brief, com papel real")
    assert do_payload[0].confirmada is False
    assert do_payload[1].confirmada is True


def test_linhagem_fabricada_nao_sobrevive_a_conferencia_do_payload():
    """GUARDA DE REGRESSÃO do achado ALTO da revisão adversarial de 27/08/2026.

    Cenário reproduzido antes da correção: uma `ImagemParaSubir` montada à mão,
    com 42 bytes de TEXTO por conteúdo e uma `Linhagem` declarando
    `sha256:dddd…`, motor `openai:gpt-image-2`, mime `image/png` e 1200×628.

      r.ok: True · avisos sobre imagem: nenhum
      recibo: {"conteudo_hash": "sha256:dddd…", "confirmada": true}

    O recibo afirmava procedência confirmada sobre bytes que a linhagem não
    descrevia. A ponte reconfere o hash — mas essa conferência é propriedade
    DELA, e quem não passa por ela não era conferido por ninguém.

    Agora `_linhagem_do_payload` confere contra os bytes que vão sair, no
    último ponto antes de o payload virar requisição.
    """
    from volc_ads import subir
    from volc_ads.campanha import display

    mentira = b"isto nao e uma imagem, sao 42 bytes puros"
    forjada = Linhagem(
        nome="banner", papel="marketing", identidade="cri_falso",
        conteudo_hash="sha256:" + "d" * 64, motor="openai:gpt-image-2",
        insumo="um prompt que nunca rodou", quando="2026-08-27T00:00:00+00:00",
        mime="image/png", largura=1200, altura=628)
    assert forjada.confirmada is True, (
        "premissa: a linhagem forjada É internamente completa — é justamente "
        "por isso que só a conferência contra os bytes a desmente")

    brief = _brief_com(ImagensDisplay(
        marketing=[ImagemParaSubir(nome="banner", dados=mentira,
                                   linhagem=forjada)],
        marketing_quadrada=[ImagemParaSubir(
            nome="quadrado", dados=png(600, 600, semente=b"q"))]))
    ops, r = display.construir("8017851692", brief, login_customer_id="6016739364")
    assert r.ok, "premissa: o construtor não barra isto, e não deve barrar"

    do_payload = subir._linhagem_do_payload(brief, ops)
    assert len(do_payload) == 2
    forjada_no_recibo = do_payload[0]
    assert forjada_no_recibo.conteudo_hash is None, (
        "o hash mentiroso chegou ao recibo")
    assert forjada_no_recibo.motor is None, "o motor inventado chegou ao recibo"
    assert forjada_no_recibo.confirmada is False, (
        "o recibo afirmaria procedência confirmada sobre bytes desconhecidos")
    assert forjada_no_recibo.papel == subir.PAPEL_NAO_APURADO
    # E o nome sobrevive, porque ele É verdade: é o que a conta vai mostrar.
    assert forjada_no_recibo.nome == "banner"


def test_bytes_trocados_depois_da_ponte_perdem_a_procedencia():
    """`dataclasses.replace(img, dados=outros)` era a evasão mais provável.

    Ela escapa do guard por AST — `replace` não é uma chamada a
    `ImagemParaSubir` — e preservava uma linhagem `confirmada` descrevendo o
    arquivo antigo. A defesa real não é o guard: é a conferência por hash.
    """
    import dataclasses
    from volc_ads import subir
    from volc_ads.campanha import display

    lote, conteudo = _lote_completo()
    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok and e.linhagem[0].confirmada is True

    adulterada = dataclasses.replace(
        e.imagens.marketing[0], dados=png(1200, 628, semente=b"OUTRO ARQUIVO"))
    assert adulterada.linhagem is e.imagens.marketing[0].linhagem, (
        "premissa: `replace` PRESERVA a linhagem antiga — é esse o problema")

    e.imagens.marketing[0] = adulterada
    brief = _brief_com(e.imagens)
    ops, _ = display.construir("8017851692", brief, login_customer_id="6016739364")

    do_payload = subir._linhagem_do_payload(brief, ops)
    assert do_payload[0].confirmada is False
    assert do_payload[0].conteudo_hash is None
    # A que NÃO foi adulterada continua intacta — a conferência é por arquivo.
    assert do_payload[1].confirmada is True


def test_confere_usa_o_mesmo_hash_do_criativo():
    """Duas implementações do mesmo formato, conferidas uma contra a outra.

    `Linhagem.confere` recomputa com `hashlib` porque `brief.py` não pode
    importar `criativo/`. Este teste é a guarda contra a divergência — mesma
    técnica que a casa usa quando um número tem dois leitores.
    """
    for dados in (b"a", png(600, 314), b"\x00" * 1000, "acentuação".encode()):
        real = hash_de_conteudo(dados)
        assert Linhagem(nome="x", papel="marketing",
                        conteudo_hash=real).confere(dados) is True
    # E não confirma o que não foi afirmado.
    assert Linhagem.desconhecida("x", "marketing").confere(b"qualquer") is False


def test_o_portao_do_veredito_sozinho_derruba_o_lote():
    """ISOLA o portão — porque quatro testes que dizem prová-lo não o provam.

    A adversarial de 27/08/2026 mutou `ResultadoDeValidacao.ok` para `True`
    sempre e mediu: `test_lote_sem_a_quadrada…`, `test_imagem_fora_de_proporcao…`,
    `test_imagem_abaixo_da_dimensao_minima…` e `test_asset_sem_medida…`
    continuavam VERDES. O que os salva é o passo 5 (papel obrigatório vazio),
    não o portão do passo 3. Não é falso-positivo — é ambiguidade de
    diagnóstico: se o portão sumisse, quatro testes diriam que ele está lá.

    Este caso não tem essa ambiguidade. Os DOIS papéis obrigatórios estão
    cheios e aprovados; o que derruba é uma violação DE LOTE (o teto combinado
    de 15). Se o portão sumir, só este cai — e ele diz por quê.
    """
    assets, conteudo = [], {}
    for i in range(16):
        a, b = _asset(TipoDeAsset.IMAGEM_MARKETING, 1200, 628,
                      semente=f"b{i}".encode())
        assets.append(a)
        conteudo[a.identidade] = b
    q, bq = _asset(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 600, 600, semente=b"q")
    assets.append(q)
    conteudo[q.identidade] = bq

    e = ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=tuple(assets)), conteudo)

    # A premissa que dá sentido ao teste: nada aqui está reprovado
    # individualmente, e os dois papéis obrigatórios TERIAM imagem.
    assert e.veredito.reprovados == (), "premissa: nenhum asset individual reprovou"
    assert len(e.veredito.aprovados) == 17
    assert e.veredito.erros_do_lote, "premissa: a violação é DO LOTE"
    assert "Q4.teto_combinado" in ponte.violacoes_por_codigo(e)

    # E mesmo assim: nada é montado. É o portão, e só ele.
    assert e.imagens is None
    assert e.linhagem == ()
    assert e.recusas == (), (
        "o passo 5 nem chegou a rodar — a prova de que quem barrou foi o portão")


# ════════════════════════════════════════════════════════════════════════════
# O CONSUMIDOR — a pasta do operador
# ════════════════════════════════════════════════════════════════════════════


def _pasta_com(tmp_path, **por_papel):
    """Monta `tmp/<papel>/<nome>.png` com dimensões de verdade no cabeçalho."""
    for papel, arquivos in por_papel.items():
        pasta = tmp_path / papel
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, dados in arquivos.items():
            (pasta / nome).write_bytes(dados)
    return tmp_path


def test_uma_pasta_de_arquivos_vira_lote_medido_com_procedencia(tmp_path):
    """O caminho do operador: arquivos em disco → lote validado. Sem rede."""
    raiz = _pasta_com(
        tmp_path,
        marketing={"banner.png": png(1200, 628, semente=b"a")},
        marketing_quadrada={"quadrado.png": png(600, 600, semente=b"b")},
        logo={"logo-larga.png": png(1024, 256, semente=b"c")})

    lote, conteudo, avisos = ponte.lote_de_pasta(
        raiz, motor="humano:tarcisio", insumo="banners do FGTS")

    assert avisos == (), "os três arquivos são mensuráveis"
    assert lote.falhas == ()
    assert len(lote.assets) == 3
    # O papel veio da PASTA, não de adivinhação por proporção.
    assert {a.tipo for a in lote.assets} == {
        TipoDeAsset.IMAGEM_MARKETING, TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
        TipoDeAsset.LOGO_PAISAGEM}
    # Medido de verdade a partir dos bytes.
    banner = next(a for a in lote.assets if a.tipo is TipoDeAsset.IMAGEM_MARKETING)
    assert (banner.largura, banner.altura) == (1200, 628)
    assert banner.mime == "image/png"
    assert banner.rotulo == "banner"
    # E os bytes conferem com o hash — é o que a ponte vai reconferir.
    assert hash_de_conteudo(conteudo[banner.identidade]) == banner.conteudo_hash

    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok, e.resumo()
    assert all(ln.confirmada for ln in e.linhagem)
    assert e.linhagem[0].motor == "humano:tarcisio"
    assert e.linhagem[0].origem == "humano"


def test_o_instante_e_o_mtime_e_a_procedencia_diz_isso(tmp_path):
    """`quando` não é o instante de geração, e o campo não finge que é.

    Um campo que parece ser uma coisa e é outra é pior que um campo vazio.
    """
    import os
    raiz = _pasta_com(tmp_path,
                      marketing={"b.png": png(1200, 628)},
                      marketing_quadrada={"q.png": png(600, 600)})
    quando = 1_800_000_000  # instante fixo: nenhum relógio é lido
    for p in raiz.rglob("*.png"):
        os.utime(p, (quando, quando))

    lote, _, _ = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    for a in lote.assets:
        assert a.procedencia.quando.timestamp() == quando
        assert "mtime" in a.procedencia.nota, (
            "a procedência não avisa que este instante não é o da geração")


def test_arquivo_ilegivel_vira_falha_e_nao_derruba_os_outros(tmp_path):
    raiz = _pasta_com(
        tmp_path,
        marketing={"bom.png": png(1200, 628, semente=b"a"),
                   "vazio.png": b""},
        marketing_quadrada={"q.png": png(600, 600, semente=b"b")})

    lote, conteudo, _ = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    assert len(lote.assets) == 2, "o arquivo vazio derrubou os bons"
    assert [f.codigo for f in lote.falhas] == ["F3.arquivo_vazio"]

    e = ponte.imagens_de_display(lote, conteudo)
    assert e.ok, "uma falha de leitura não pode reprovar o lote inteiro"


def test_arquivo_que_nao_da_para_medir_avisa_e_e_reprovado_pela_regua(tmp_path):
    """Medida ausente não é contornada no adaptador — quem julga é `validar_lote`."""
    raiz = _pasta_com(
        tmp_path,
        marketing={"misterio.bin": b"nao sou uma imagem de formato conhecido"},
        marketing_quadrada={"q.png": png(600, 600, semente=b"b")})

    lote, conteudo, avisos = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    assert any("não deu para medir" in a for a in avisos), avisos

    e = ponte.imagens_de_display(lote, conteudo)
    assert "M1.sem_medida" in ponte.violacoes_por_codigo(e)
    assert e.imagens is None, "sem medida não vira payload"


def test_pasta_sem_subpasta_de_papel_levanta_dizendo_quais_sao(tmp_path):
    (tmp_path / "solta.png").write_bytes(png(1200, 628))
    with pytest.raises(ponte.PonteIncompleta, match="marketing_quadrada"):
        ponte.lote_de_pasta(tmp_path, motor="m", insumo="i")


def test_pasta_inexistente_levanta_em_vez_de_devolver_lote_vazio(tmp_path):
    with pytest.raises(ponte.PonteIncompleta, match="não é uma pasta"):
        ponte.lote_de_pasta(tmp_path / "nao-existe", motor="m", insumo="i")


def test_main_devolve_0_no_lote_bom_e_1_no_ruim(tmp_path, capsys):
    """O código de saída é o contrato com quem chama o comando."""
    bom = _pasta_com(
        tmp_path / "bom",
        marketing={"b.png": png(1200, 628, semente=b"a")},
        marketing_quadrada={"q.png": png(600, 600, semente=b"b")})
    saida_json = tmp_path / "linhagem.json"
    codigo = ponte.main([
        "--pasta", str(bom), "--motor", "humano:tarcisio",
        "--insumo", "banners de setembro", "--json", str(saida_json)])
    assert codigo == 0
    texto = capsys.readouterr().out
    assert "2 imagens, 2 com procedência confirmada" in texto
    assert "Nada foi enviado" in texto

    import json
    envelope = json.loads(saida_json.read_text(encoding="utf-8"))
    assert envelope["ok"] is True
    assert envelope["canal"] == "DISPLAY"
    gravada = envelope["linhagem"]
    assert [x["papel"] for x in gravada] == ["marketing", "marketing_quadrada"]
    assert all(x["confirmada"] for x in gravada)
    assert gravada[0]["custo_usd"] is None, "custo de arquivo humano e ausencia"
    assert gravada[0]["versao_do_motor"] == ""

    # E o lote que nao serve devolve 1, sem payload.
    ruim = _pasta_com(
        tmp_path / "ruim",
        marketing={"torta.png": png(800, 800, semente=b"c")},
        marketing_quadrada={"q.png": png(600, 600, semente=b"d")})
    json_ruim = tmp_path / "ruim.json"
    assert ponte.main(["--pasta", str(ruim), "--motor", "m",
                       "--insumo", "i", "--json", str(json_ruim)]) == 1
    saida_ruim = capsys.readouterr().out
    # ⚠️ A NEGAÇÃO faz parte da asserção. A versão anterior aceitava
    # "serve para montar a campanha", que fica verde se a mensagem for
    # invertida para o oposto do que ela diz.
    assert "NÃO serve para montar a campanha" in saida_ruim, saida_ruim
    assert "imagens prontas" not in saida_ruim, (
        "um lote reprovado nao pode anunciar prontidao")
    # E ele TAMBEM diz que nada saiu — as duas saidas dizem isso, e devem.
    assert "Nada foi enviado" in saida_ruim

    # ATENCAO: o ENVELOPE, e nao uma lista crua. Um `[]` num lote reprovado e
    # indistinguivel de "zero imagens" para quem le o arquivo em vez do codigo
    # de saida — ausencia tratada como zero.
    rejeitado = json.loads(json_ruim.read_text(encoding="utf-8"))
    assert rejeitado["ok"] is False
    assert rejeitado["linhagem"] == []
    assert any("D3.proporcao" in v for v in rejeitado["violacoes"]), (
        "o arquivo nao diz POR QUE o lote nao serve")


def test_main_exige_procedencia_e_nao_a_inventa(tmp_path):
    """Sem `--motor` e `--insumo` o comando recusa: procedência é obrigatória."""
    raiz = _pasta_com(tmp_path, marketing={"b.png": png(1200, 628)})
    with pytest.raises(SystemExit):
        ponte.main(["--pasta", str(raiz)])
    with pytest.raises(SystemExit):
        ponte.main(["--pasta", str(raiz), "--motor", "m"])


def test_o_consumidor_liga_o_medidor_ao_caminho_funcional():
    """O medidor deixa de ser código sem consumidor — achado MÉDIO-6.

    `lote_de_pasta` é o que chama `medir_imagem.medir()`. Sem ele, o medidor
    seria exatamente o que esta entrega argumenta contra: código novo nascido
    sem ninguém que o use.
    """
    fonte = (RAIZ / "volc_ads/criativo_ponte.py").read_text(encoding="utf-8")
    assert "medir_imagem.medir(" in fonte
    assert _chamadas_a("medir", RAIZ / "volc_ads/criativo_ponte.py") >= 1


def test_linhagem_sem_hash_perde_tudo_menos_nome_e_papel():
    """GUARDA do MÉDIO-C1: omitir o hash não pode sair mais barato que mentir.

    Antes: quem DECLARAVA hash falso era raspado; quem OMITIA o campo levava
    motor, insumo, `insumo_hash`, dimensão inventada e `custo_usd: 99.0` para
    dentro do recibo. O incentivo estava invertido.
    """
    from volc_ads import subir
    from volc_ads.campanha import display

    mentira = b"isto nao e uma imagem, sao 42 bytes puros"
    sem_hash = Linhagem(
        nome="banner", papel="marketing", identidade="cri_falso",
        motor="openai:gpt-image-2", insumo="prompt que nunca rodou",
        insumo_hash="f" * 16, pedido="ped-inventado",
        quando="2026-08-27T00:00:00+00:00", origem="gerado",
        mime="image/png", largura=1200, altura=628, custo_usd=99.0)
    assert sem_hash.conteudo_hash is None, "premissa: ela não declara hash"

    brief = _brief_com(ImagensDisplay(
        marketing=[ImagemParaSubir(nome="banner", dados=mentira,
                                   linhagem=sem_hash)],
        marketing_quadrada=[ImagemParaSubir(
            nome="q", dados=png(600, 600, semente=b"q"))]))
    ops, _ = display.construir("8017851692", brief, login_customer_id="6016739364")
    ln = subir._linhagem_do_payload(brief, ops)[0]

    assert ln.motor is None, "o motor inventado sobreviveu"
    assert ln.insumo is None and ln.insumo_hash is None
    assert ln.custo_usd is None, "custo inventado chegaria ao relatório de COGS"
    assert ln.largura is None and ln.altura is None
    assert ln.confirmada is False
    # Sobrevive só o verificável fora da própria afirmação.
    assert ln.nome == "banner"
    assert ln.papel == "marketing", "o papel vem da estrutura do brief"


def test_hash_certo_com_medidas_mentirosas_tambem_e_recusado():
    """GUARDA do MÉDIO-C2: `confere` prova os bytes, não o que se diz deles.

    Bastava computar o sha256 CERTO de 42 bytes de texto e declarar
    `mime="image/png", largura=1200, altura=628` para o recibo gravar
    `confirmada: true` sobre uma dimensão que nunca existiu.
    """
    from volc_ads import subir
    from volc_ads.campanha import display

    mentira = b"isto nao e uma imagem, sao 42 bytes puros"
    coerente_e_falsa = Linhagem(
        nome="banner", papel="marketing", identidade="cri_x",
        conteudo_hash=hash_de_conteudo(mentira),
        motor="openai:gpt-image-2", insumo="p",
        quando="2026-08-27T00:00:00+00:00",
        mime="image/png", largura=1200, altura=628, custo_usd=99.0)
    assert coerente_e_falsa.confere(mentira), (
        "premissa: o HASH bate — é isso que torna o caso perigoso")

    brief = _brief_com(ImagensDisplay(
        marketing=[ImagemParaSubir(nome="banner", dados=mentira,
                                   linhagem=coerente_e_falsa)],
        marketing_quadrada=[ImagemParaSubir(
            nome="q", dados=png(600, 600, semente=b"q"))]))
    ops, _ = display.construir("8017851692", brief, login_customer_id="6016739364")
    ln = subir._linhagem_do_payload(brief, ops)[0]
    assert ln.confirmada is False, "mime e dimensão inventados passaram"
    assert ln.motor is None


def test_bytes_irreconheciveis_nao_corroboram_nada_do_que_se_afirma():
    """`confirmada` significa CORROBORADO — e o que nao se apura nao confirma.

    ATENCAO: a versao anterior deste teste afirmava o contrario ("ausencia de
    medida NAO refuta") e a revisao adversarial mostrou que ela nao distinguia
    um WebP legitimo de lixo declarando WebP: os proprios bytes que ela usava
    nem eram um WebP valido. Pior, a regra que ela protegia deixava passar
    `mime="image/webp"` sobre 42 bytes de texto, com dimensao inventada.

    A regra certa: se nao reconhecemos a assinatura, nao ha como corroborar
    formato nem dimensao — entao uma linhagem que os AFIRMA nao e confirmada.

    Isto NAO prejudica formato novo legitimo: a API v25 so aceita PNG, JPEG e
    GIF (criativo/requisitos.yaml: padroes.imagem.mimes), e um WebP seria
    barrado por F1.mime na validacao, muito antes daqui.
    """
    from volc_ads import subir
    from volc_ads.criativo.adaptadores import medir_imagem

    lixo = b"nao sou imagem de formato nenhum que este medidor conheca"
    assert medir_imagem.medir(lixo).mime is None, "premissa: assinatura desconhecida"

    afirma_formato = Linhagem(nome="w", papel="marketing",
                              conteudo_hash=hash_de_conteudo(lixo),
                              mime="image/webp")
    assert subir._medidas_batem(afirma_formato, lixo) is False

    afirma_dimensao = Linhagem(nome="w", papel="marketing",
                               conteudo_hash=hash_de_conteudo(lixo),
                               largura=1200, altura=628)
    assert subir._medidas_batem(afirma_dimensao, lixo) is False

    # NAO afirma nada sobre o conteudo -> nada a refutar.
    calada = Linhagem(nome="w", papel="marketing",
                      conteudo_hash=hash_de_conteudo(lixo),
                      motor="m", insumo="i", bytes_totais=len(lixo))
    assert subir._medidas_batem(calada, lixo) is True

    # E o tamanho sempre da para conferir, mesmo sem reconhecer o formato.
    mentindo_no_tamanho = Linhagem(nome="w", papel="marketing",
                                   bytes_totais=999_999)
    assert subir._medidas_batem(mentindo_no_tamanho, lixo) is False


def test_a_grafia_do_mime_nao_decide_se_a_conferencia_acontece():
    """`IMAGE/PNG` e `image/jpg` eram dois contornos so de escrita.

    Medido em 27/08/2026: sobre os mesmos 42 bytes de texto, `image/png` era
    refutado e `IMAGE/PNG`, `image/jpg` e `image/webp` passavam. Quem declara
    escolhia a string e com ela escolhia se seria conferido.
    """
    from volc_ads import subir
    mentira = b"isto nao e uma imagem, sao 42 bytes puros"
    for grafia in ("image/png", "IMAGE/PNG", "  Image/PNG  ", "image/jpg",
                   "image/webp", "image/gif"):
        ln = Linhagem(nome="b", papel="marketing",
                      conteudo_hash=hash_de_conteudo(mentira),
                      mime=grafia, largura=1200, altura=628)
        assert subir._medidas_batem(ln, mentira) is False, f"escapou: {grafia!r}"

    # E a normalizacao nao pode reprovar o legitimo escrito de outro jeito.
    real = png(1200, 628, semente=b"real")
    for grafia in ("image/png", "IMAGE/PNG", " image/png "):
        ln = Linhagem(nome="b", papel="marketing",
                      conteudo_hash=hash_de_conteudo(real),
                      mime=grafia, largura=1200, altura=628)
        assert subir._medidas_batem(ln, real) is True, f"falso positivo: {grafia!r}"


def test_assinatura_certa_com_cabecalho_zerado_nao_corrobora_dimensao():
    """A segunda porta do MEDIO-C2: mime bate, dimensao nao foi medida.

    Um PNG de assinatura valida e IHDR zerado faz `medir_imagem` devolver
    `largura=None` de proposito. Declarar 1200x628 sobre ele passava, porque
    `None` nao refutava.
    """
    from volc_ads import subir
    ihdr_zerado = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    ln = Linhagem(nome="b", papel="marketing",
                  conteudo_hash=hash_de_conteudo(ihdr_zerado),
                  mime="image/png", largura=1200, altura=628, custo_usd=99.0)
    assert subir._medidas_batem(ln, ihdr_zerado) is False


def test_arquivo_sem_permissao_vira_falha_e_nao_derruba_o_lote(tmp_path, monkeypatch):
    """GUARDA do BAIXO-F: o docstring prometia isso e o código não cumpria.

    `read_bytes()` sem `try` matava o lote inteiro com `PermissionError`. O
    teste que dizia provar a promessa usava um arquivo VAZIO — outro caso.
    """
    # ⚠️ ERRO INJETADO, e não `chmod`. Com `chmod 000` o teste virava `skip`
    # quando rodado como root — e em container de CI isso é o padrão. A única
    # prova deste comportamento desaparecia e a suíte ficava verde. Injetar o
    # erro funciona como root também, e é determinístico em qualquer plataforma.
    import pathlib as _pathlib
    raiz = _pasta_com(
        tmp_path,
        marketing={"bom.png": png(1200, 628, semente=b"a"),
                   "trancado.png": png(1200, 628, semente=b"z")},
        marketing_quadrada={"q.png": png(600, 600, semente=b"b")})

    original = _pathlib.Path.read_bytes

    def _recusa_o_trancado(self, *a, **k):
        if self.name == "trancado.png":
            raise PermissionError(13, "Permission denied", str(self))
        return original(self, *a, **k)

    monkeypatch.setattr(_pathlib.Path, "read_bytes", _recusa_o_trancado)
    lote, conteudo, _ = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    monkeypatch.undo()

    assert len(lote.assets) == 2, "o arquivo ilegível derrubou os bons"
    assert [f.codigo for f in lote.falhas] == ["F4.ilegivel"]
    assert not lote.falhas[0].permanente, "permissão pode mudar; não é permanente"
    assert ponte.imagens_de_display(lote, conteudo).ok


def test_nenhum_arquivo_some_em_silencio(tmp_path):
    """GUARDA do MÉDIO-D: pasta com typo e subpasta aninhada perdiam 5 arquivos."""
    raiz = tmp_path
    (raiz / "logos").mkdir(parents=True)          # typo: deveria ser `logo`
    (raiz / "marketing" / "aprovados").mkdir(parents=True)
    (raiz / "marketing_quadrada").mkdir()
    for i in range(3):
        (raiz / "logos" / f"l{i}.png").write_bytes(
            png(1024, 256, semente=str(i).encode()))
    for i in range(2):
        (raiz / "marketing" / "aprovados" / f"b{i}.png").write_bytes(
            png(1200, 628, semente=str(i).encode()))
    (raiz / "marketing" / "banner.png").write_bytes(png(1200, 628, semente=b"x"))
    (raiz / "marketing_quadrada" / "q.png").write_bytes(png(600, 600, semente=b"y"))
    (raiz / "solto.png").write_bytes(png(1200, 628, semente=b"solto"))

    _, _, avisos = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    texto = "\n".join(avisos)
    assert "'logos/' ignorada (3 arquivo(s))" in texto, texto
    assert "'marketing/aprovados/' ignorada (2 arquivo(s))" in texto, texto
    assert "'solto.png' ignorado" in texto, texto


def test_a_inversao_da_tabela_de_papeis_e_conferida_no_import():
    """Hipótese da revisão: inverter dict só é seguro com valores únicos."""
    assert len(ponte._TIPO_POR_PASTA) == len(ponte.PAPEL_POR_TIPO)
    assert set(ponte._TIPO_POR_PASTA.values()) == set(ponte.PAPEL_POR_TIPO)


def test_pasta_que_difere_so_na_caixa_avisa_a_verdade(tmp_path):
    """GUARDA do achado 4 do ciclo 3: o aviso mentia em macOS.

    `raiz / "marketing"` resolve `Marketing/` em APFS e nao resolve em ext4. O
    aviso dizia "pasta ignorada" enquanto a leitura JA TINHA LIDO os arquivos —
    o operador via uma perda que nao houve. E o mesmo diretorio aprovado no
    macOS reprovava no Linux.
    """
    raiz = tmp_path
    (raiz / "Marketing").mkdir()
    (raiz / "marketing_quadrada").mkdir()
    (raiz / "Marketing" / "b.png").write_bytes(png(1200, 628, semente=b"x"))
    (raiz / "marketing_quadrada" / "q.png").write_bytes(png(600, 600, semente=b"y"))

    lote, _, avisos = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    texto = "\n".join(avisos)
    # ⚠️ O COMPORTAMENTO primeiro, e so depois a mensagem. A versao anterior
    # asseria so o texto do aviso: se a leitura parasse de ler `Marketing/` em
    # macOS, o teste continuava verde afirmando o contrario.
    import sys as _sys
    if (raiz / "marketing" / "b.png").exists():   # sistema case-insensitive
        assert len(lote.assets) == 2, (
            f"macOS le `Marketing/` e o lote trouxe {len(lote.assets)} assets")
    assert "difere do papel 'marketing' apenas na caixa" in texto, texto
    # O aviso NAO pode afirmar perda: em macOS o arquivo entra.
    assert "ignorada" not in texto, (
        "o aviso afirma perda que pode nao ter acontecido")
    # E ele nomeia a consequencia real de mudar de maquina.
    assert "Linux" in texto


def test_o_envelope_json_carrega_o_que_se_perdeu_na_leitura(tmp_path, capsys):
    """GUARDA do achado 5: as duas correcoes do mesmo commit nao se falavam.

    O envelope existia para quem le o ARQUIVO em vez do codigo de saida — e
    gravava `ok: true` sem vestigio dos arquivos perdidos por typo de pasta nem
    das falhas de leitura. O leitor concluia "lote perfeito".
    """
    import json
    raiz = tmp_path / "lote"
    (raiz / "logos").mkdir(parents=True)
    (raiz / "marketing").mkdir()
    (raiz / "marketing_quadrada").mkdir()
    for i in range(3):
        (raiz / "logos" / f"l{i}.png").write_bytes(png(1024, 256, semente=str(i).encode()))
    (raiz / "marketing" / "b.png").write_bytes(png(1200, 628, semente=b"x"))
    (raiz / "marketing" / "vazio.png").write_bytes(b"")
    (raiz / "marketing_quadrada" / "q.png").write_bytes(png(600, 600, semente=b"y"))

    destino = tmp_path / "relatorio.json"
    codigo = ponte.main(["--pasta", str(raiz), "--motor", "m", "--insumo", "i",
                         "--json", str(destino)])
    capsys.readouterr()
    assert codigo == 0, "o lote em si e valido"

    env = json.loads(destino.read_text(encoding="utf-8"))
    assert env["ok"] is True
    assert any("logos/" in a for a in env["avisos_de_leitura"]), env["avisos_de_leitura"]
    assert any("F3.arquivo_vazio" in f for f in env["falhas_de_leitura"]), (
        env["falhas_de_leitura"])


def test_relatorio_de_rodada_anterior_nao_sobrevive_a_uma_que_falha(tmp_path):
    """GUARDA do BAIXO-3 do ciclo 4: relatorio obsoleto e pior que nenhum.

    `lote_de_pasta` levanta antes de o envelope ser escrito. Com `--json`
    apontando para um caminho ja existente, o leitor que consome o ARQUIVO em
    vez do codigo de saida lia `ok: true` de uma rodada que nunca aconteceu —
    com a linhagem de OUTRO lote.
    """
    import json
    bom = _pasta_com(
        tmp_path / "bom",
        marketing={"b.png": png(1200, 628, semente=b"a")},
        marketing_quadrada={"q.png": png(600, 600, semente=b"b")})
    destino = tmp_path / "rel.json"

    assert ponte.main(["--pasta", str(bom), "--motor", "m", "--insumo", "i",
                       "--json", str(destino)]) == 0
    antes = json.loads(destino.read_text(encoding="utf-8"))
    assert antes["ok"] is True and antes["linhagem"], "premissa: rodada boa"

    vazia = tmp_path / "vazia"
    vazia.mkdir()
    assert ponte.main(["--pasta", str(vazia), "--motor", "m", "--insumo", "i",
                       "--json", str(destino)]) == 1

    depois = json.loads(destino.read_text(encoding="utf-8"))
    assert depois["ok"] is False, "o relatorio da rodada anterior sobreviveu"
    assert "linhagem" not in depois, "a linhagem de outro lote sobreviveu"
    assert depois["estado"] == "leitura falhou"


def test_pasta_so_com_caixa_errada_diz_isso_na_excecao(tmp_path):
    """H2 do ciclo 4: em Linux, `Marketing/` sozinha cai em PonteIncompleta.

    O aviso de caixa era montado e descartado junto com o retorno, e o operador
    lia "nao tem nenhuma subpasta de papel" sem saber que a pasta certa estava
    ali com a caixa errada. Em macOS (case-insensitive) a pasta E lida e este
    caminho nao dispara — por isso o teste aceita os dois desfechos, mas exige
    que o de excecao NOMEIE a causa.
    """
    raiz = tmp_path
    (raiz / "Marketing").mkdir()
    (raiz / "Marketing" / "b.png").write_bytes(png(1200, 628, semente=b"x"))

    try:
        lote, _, avisos = ponte.lote_de_pasta(raiz, motor="m", insumo="i")
    except ponte.PonteIncompleta as exc:
        assert "apenas na caixa" in str(exc), (
            f"a excecao nao diz que a pasta certa esta ali: {exc}")
    else:
        # macOS: leu mesmo. Entao o aviso tem de estar la, e o arquivo dentro.
        assert len(lote.assets) == 1
        assert any("apenas na caixa" in a for a in avisos), avisos
