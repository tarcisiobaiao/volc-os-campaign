"""A tipografia é desenhada, e a zona pedida é conferida.

Os dois módulos vieram do motor-imagem da VOLC. O kit tipográfico veio com um
defeito medido, e este arquivo é o que impede o defeito de voltar.
"""
import pytest
from PIL import Image, ImageDraw

from app.criativo.studio import planos, tipografia


def _desenho():
    return ImageDraw.Draw(Image.new("RGB", (1080, 1350), "white"))


def test_o_peso_variavel_muda_a_letra_de_fato():
    """O bug de porte, virado contraprova.

    A origem chamava `set_variation_by_axes([peso])` com UM valor numa fonte de
    DOIS eixos (Optical size, Weight). O primeiro eixo recebia o peso, o peso
    nunca chegava, e as três hierarquias saíam com a mesma largura — sem
    exceção nenhuma, porque o `except: pass` da origem engolia tudo.
    """
    larguras = [tipografia.fonte(100, peso).getlength("ABERTAS") for peso in (100, 400, 900)]
    assert len(set(larguras)) == 3, (
        f"pesos diferentes produziram larguras {larguras}: o eixo de peso não foi aplicado"
    )
    assert larguras[0] < larguras[1] < larguras[2], "mais peso tem de ocupar mais largura"


def test_sem_arquivo_de_fonte_falha_fechado(monkeypatch, tmp_path):
    """Nunca cair na fonte bitmap do PIL: ela parece tipografia e não é."""
    tipografia.fonte.cache_clear()
    monkeypatch.setattr(tipografia, "CAMINHO_DA_FONTE", tmp_path / "nao-existe.ttf")
    with pytest.raises(tipografia.FonteIndisponivel):
        tipografia.fonte(48, 700)
    tipografia.fonte.cache_clear()


def test_ajuste_encolhe_ate_a_palavra_mais_longa_caber():
    desenho = _desenho()
    fnt, texto = tipografia.ajustar(
        desenho, "Pé-de-Meia sumiu do app?", largura_max=300,
        tamanho_inicial=160, peso=900, caixa_alta=True,
    )
    assert texto == "PÉ-DE-MEIA SUMIU DO APP?"
    maior = max(desenho.textlength(p, font=fnt) for p in texto.split())
    assert maior <= 300


def test_quebra_respeita_a_largura_e_as_quebras_explicitas():
    desenho = _desenho()
    fnt = tipografia.fonte(40, 500)
    largura = 600  # largo o bastante para "primeira linha" caber inteira

    linhas = tipografia.quebrar(desenho, "primeira linha\nsegunda linha bem mais longa", fnt, largura)
    # A quebra explícita é fronteira de parágrafo: o primeiro trecho não se
    # mistura com o segundo mesmo havendo espaço na linha.
    assert linhas[0] == "primeira linha"
    assert all(desenho.textlength(l, font=fnt) <= largura for l in linhas if l)

    # E nenhuma linha estoura quando a caixa é estreita.
    estreitas = tipografia.quebrar(desenho, "segunda linha bem mais longa", fnt, 200)
    assert len(estreitas) > 1
    assert all(desenho.textlength(l, font=fnt) <= 200 for l in estreitas if " " in l)


def test_contraste_wcag_bate_os_extremos_conhecidos():
    assert tipografia.contraste((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0, abs=0.01)
    assert tipografia.contraste((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0, abs=0.01)


def test_o_plano_e_deterministico_e_varia_entre_pecas():
    """Mesma semente, mesmo plano — mas peças distintas não caem no mesmo canto."""
    a = planos.escolher("campo_cromatico", 0)
    assert a == planos.escolher("campo_cromatico", 0)
    b = planos.escolher("campo_cromatico", 1)
    assert a is not None and b is not None and a[0] != b[0]


@pytest.mark.parametrize("rota", ["integrado_na_cena", "tipografia_protagonista", None])
def test_rota_que_nao_reserva_zona_nao_ganha_plano(rota):
    """Reservar zona onde a arte decidiu integrar o texto seria contradizê-la."""
    assert planos.escolher(rota, 0) is None


def test_o_pedido_nunca_nomeia_marcador_visivel():
    """A lei nº 1: pede-se a LUZ, não um retângulo."""
    proibidos = ("rectangle", "box", "bar ", "banner", "reserved", "placeholder", "overlay")
    for nome, plano in planos.PLANOS.items():
        texto = plano["pedido"].casefold()
        for termo in proibidos:
            assert termo not in texto, f"{nome} pede marcador visível: {termo!r}"


def test_contencao_mede_pelo_denominador_certo():
    """Contenção, não cobertura: um bloco de texto nunca cobre meia página.

    A zona achada é pequena e cai INTEIRA dentro da região pedida — obediência
    perfeita. Medir cobertura devolveria um número baixo e reprovaria.
    """
    pedida = (0.05, 0.58, 0.95, 0.94)
    achada = (0.10, 0.62, 0.50, 0.75)
    assert planos.contencao(pedida, achada) == pytest.approx(1.0, abs=0.001)


def test_conferir_reprova_texto_fora_do_lugar_pedido():
    plano = planos.PLANOS["faixa_inferior"]
    canvas = {"w": 1080, "h": 1350}
    dentro = planos.conferir(plano, {"x": 108, "y": 850, "w": 500, "h": 200}, canvas)
    assert dentro["obedeceu"] and dentro["contencao"] == pytest.approx(1.0, abs=0.01)

    # O modelo pôs a área livre no topo, e o plano pedia embaixo.
    fora = planos.conferir(plano, {"x": 108, "y": 60, "w": 500, "h": 200}, canvas)
    assert not fora["obedeceu"]
    assert fora["zona_achada"] and fora["zona_pedida"] == list(plano["zona"])


# ── PRENSA: medir a zona, conferir, e caber ────────────────────────────────

def _cena(largura=1080, altura=1350, ruido_ate=0.55):
    """Cena com metade de cima 'ocupada' e metade de baixo lisa."""
    import io, random
    from PIL import Image
    img = Image.new("RGB", (largura, altura), (18, 18, 22))
    pixels = img.load()
    rng = random.Random(7)
    for y in range(int(altura * ruido_ate)):
        for x in range(0, largura, 3):
            tom = rng.randrange(0, 255)
            pixels[x, y] = (tom, tom, tom)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()


def test_a_zona_calma_e_achada_onde_o_plano_pediu():
    from PIL import Image
    import io
    from app.criativo.studio import prensa
    img = Image.open(io.BytesIO(_cena())).convert("RGB")
    zona = prensa.medir_zona_calma(img, planos.PLANOS["faixa_inferior"]["zona"])
    assert zona.fracao_calma >= prensa.MINIMO_DE_CALMA
    assert zona.y >= int(0.55 * 1350) - 30, "a faixa calma tem de cair na metade de baixo"


def test_cena_sem_area_calma_reprova_em_vez_de_fingir():
    """Contenção sozinha aprovaria: a busca é confinada e sempre 'cabe'."""
    from PIL import Image
    import io
    from app.criativo.studio import prensa
    img = Image.open(io.BytesIO(_cena(ruido_ate=1.0))).convert("RGB")
    zona = prensa.medir_zona_calma(img, planos.PLANOS["faixa_inferior"]["zona"])
    assert zona.fracao_calma < prensa.MINIMO_DE_CALMA


def test_a_pilha_inteira_cabe_na_zona_e_o_cta_nao_sai_da_imagem():
    from app.criativo.studio import prensa
    impressa = prensa.imprimir(
        cena=_cena(),
        textos={"headline": "Pé-de-Meia: o app faz o pagamento?",
                "complemento": "O Jornada do Estudante serve para consulta.",
                "cta": "Entenda a regra"},
        plano=planos.PLANOS["faixa_inferior"],
    )
    assert impressa.veredito["altura_da_pilha"] <= impressa.zona["h"]
    fim_do_cta = impressa.tipografia["cta"]["y"]
    assert fim_do_cta < 1350, "o CTA não pode ser desenhado fora da imagem"
    assert impressa.tipografia["headline"]["tamanho_px"] > impressa.tipografia["complemento"]["tamanho_px"]


def test_copy_impossivel_falha_em_vez_de_cortar():
    """Peça com texto cortado parece pronta, e é pior que falhar."""
    from app.criativo.studio import prensa
    with pytest.raises(prensa.TextoNaoCabe):
        prensa.imprimir(
            cena=_cena(),
            textos={"headline": "palavra " * 200, "complemento": "detalhe " * 200,
                    "cta": "conferir"},
            plano=planos.PLANOS["diagonal_superior_direita"],
        )


def test_a_tinta_do_cta_sai_de_contraste_medido():
    from app.criativo.studio import prensa
    for acento in ((255, 203, 0), (20, 30, 90)):
        impressa = prensa.imprimir(
            cena=_cena(), textos={"headline": "Curto", "cta": "Ver guia"},
            plano=planos.PLANOS["faixa_inferior"], acento=acento,
        )
        assert impressa.tipografia["cta"]["contraste_no_botao"] >= 4.5


def test_a_tinta_do_texto_sai_de_contraste_medido_contra_a_zona():
    """O default fixo escreveu branco sobre mármore claro numa peça real.

    A zona de `faixa_inferior_clara` é branca de propósito. Uma tinta padrão
    branca some ali — legível no monitor, invisível na miniatura do feed.
    """
    import io
    from PIL import Image
    from app.criativo.studio import prensa

    def cena_com_rodape(tom):
        img = Image.new("RGB", (1080, 1350), (30, 30, 30))
        img.paste(Image.new("RGB", (1080, 580), tom), (0, 770))
        buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

    clara = prensa.imprimir(cena=cena_com_rodape((242, 242, 240)),
                            textos={"headline": "Curto", "cta": "Ver guia"},
                            plano=planos.PLANOS["faixa_inferior_clara"])
    assert clara.veredito["tinta"] == [17, 17, 17], "fundo claro pede tinta escura"

    escura = prensa.imprimir(cena=cena_com_rodape((16, 20, 28)),
                             textos={"headline": "Curto", "cta": "Ver guia"},
                             plano=planos.PLANOS["faixa_inferior"])
    assert escura.veredito["tinta"] == [255, 255, 255], "fundo escuro pede tinta clara"
