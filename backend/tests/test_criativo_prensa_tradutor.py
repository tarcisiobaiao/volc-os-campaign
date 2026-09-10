"""O tradutor CreativeSpec → post.spec/1.0.0: a peça do meio da PRENSA.

## Por que este módulo existe, e por que ele NÃO usa `variants`

O `PRENSA-SPEC.md` promete um campo `artboard.variants` que resolveria
multi-formato num render só. Ele não existe no motor. Medido em 10/09/2026
dentro do container: uma spec com três `variants` declaradas (4:5, 9:16, 1:1)
produziu UM PNG de 1088x1360, com sha256 **byte a byte idêntico** ao da mesma
spec sem `variants` nenhum. O bloco atravessa `resolve.py` inteiro, entra no
`.resolvido.json`, entra no `hash_canonico` — e `render.py` nunca o lê
(`grep -rn variants services/prensa/motor/*.py` não devolve nada).

O modo de falha é silencioso, e é essa a razão de existir um teste aqui: quem
escrever `variants` numa spec vai ver a peça sair certa em 4:5 e descobrir só na
publicação que story e quadrado nunca foram gerados. `test_tradutor_nunca_emite_variants`
é a única coisa entre esse erro e o feed.

O eixo de multiplicidade do motor é `slides` (lâmina de carrossel), um artboard
por spec — `render.py:879`. Logo multi-formato é N specs, e isso não é contorno:
é exatamente a doutrina que `test_criativo_ancora_e_multiformato` já sela, de
que cada formato é uma GERAÇÃO PRÓPRIA e nunca um recorte do 4x5.
"""
import pytest

from app.criativo.bancada.adaptadores import prensa_tradutor as tradutor
from app.criativo.studio.spec_visual import CreativeSpec


FAMILIA = ["azul royal", "amarelo ouro", "verde bandeira", "branco"]

#: Os quatro artboards de entrega do Meta. 4x5 é o feed; 9x16 story e reels;
#: 1x1 o quadrado; 1.91x1 a coluna direita e a Audience Network.
FORMATOS = [(1080, 1350), (1080, 1920), (1080, 1080), (1200, 628)]


def _spec(**troca) -> CreativeSpec:
    """A peça 1 do lote Pé-de-Meia real, reduzida ao que o tradutor lê."""
    base = dict(
        schema_version="volc.creative-spec/2",
        creative_ref="creative_acesso_govbr",
        conceito="Está buscando seu cadastro no Pé-de-Meia?",
        angulo="Instrução de login gov.br e checagem de status",
        intencao="Destacar a exigência do login gov.br atrai o estudante.",
        fato_refs=["fact_lp69ee05e62a0dd3b2"],
        texto_exato={
            "headline": "Vai consultar o Pé-de-Meia no app?",
            "complemento": "Entenda como usar a conta gov.br no Jornada do Estudante.",
            "cta": "Ver orientações",
        },
        copy_externa={"texto_principal": "…", "titulo": "…", "descricao": "…", "cta": "LEARN_MORE"},
        direcao_visual="Composição limpa em ângulo plongée sutil.",
        direcao_de_arte={
            "blueprint_version": "volc.art-direction/2",
            "rota_de_texto": "campo_cromatico",
            "registro": "editorial",
            "presenca_humana": "maos",
            "cena": "Mãos jovens de estudante sobre caderno pautado.",
            "tratamento": "Fotografia nítida com iluminação lateral suave.",
            "composicao": "Divisão em dois terços verticais.",
            "tipografia": "Headline em caixa alta sem serifa, peso bold, branca.",
            "paleta_e_contraste": "Dominante: azul royal; Apoio: branco; Acento: amarelo ouro.",
        },
        formato="feed_4x5",
        largura_final=1080,
        altura_final=1350,
        canvas_provider="1088x1360",
        margem_segura={"esquerda": 76, "direita": 76, "topo": 189, "base": 243},
        composicao="Entrega 1080x1350. Componha para esta proporção.",
        hierarquia="A headline é o maior elemento tipográfico da peça.",
        contraste="Piso de legibilidade: o texto precisa ser lido em miniatura.",
        papel_referencia="hibrido",
        familia_cromatica=list(FAMILIA),
        plano_de_composicao={
            "nome": "faixa_inferior",
            "pedido": "Compose with the subject in the UPPER half of the frame…",
            "zona": [0.05, 0.58, 0.95, 0.94],
        },
        proibidos=["alegações não sustentadas"],
    )
    base.update(troca)
    return CreativeSpec(**base)


# ─────────────────────────────────────────────────────────────────────────────
# 1. A regressão que o achado desta sessão comprou
# ─────────────────────────────────────────────────────────────────────────────

def test_tradutor_nunca_emite_variants():
    """`artboard.variants` é contrato morto: o motor o ignora em SILÊNCIO.

    Falharia se alguém "implementasse multi-formato" acreditando no
    PRENSA-SPEC.md — o teste é o recibo do experimento que refutou o campo.
    """
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350))
    assert "variants" not in post["artboard"]


def test_cada_formato_e_uma_spec_inteira_e_nao_um_recorte():
    """Quatro artboards, quatro specs — a mesma copy, geometria nativa em cada."""
    lote = tradutor.traduzir_lote(_spec(), FORMATOS)

    assert len(lote) == len(FORMATOS)
    assert [(p["artboard"]["base"]["w"], p["artboard"]["base"]["h"]) for p in lote] == FORMATOS
    # a copy é a MESMA nas quatro: irmãs, não recortes
    assert len({tradutor.headline_de(p) for p in lote}) == 1
    # e os spec_id são distintos, senão o motor sobrescreve o PNG anterior
    assert len({p["spec_id"] for p in lote}) == len(FORMATOS)


# ─────────────────────────────────────────────────────────────────────────────
# 2. A âncora é o desejo — e o tradutor não reescreve texto aprovado
# ─────────────────────────────────────────────────────────────────────────────

def test_headline_viaja_byte_a_byte_do_texto_exato():
    """O tradutor é transporte, não redação: acento, caixa e pontuação intactos."""
    spec = _spec()
    post = tradutor.traduzir(spec, artboard=(1080, 1350))

    assert tradutor.headline_de(post) == spec.texto_exato["headline"]


def test_complemento_e_cta_tambem_viajam_inteiros():
    spec = _spec()
    post = tradutor.traduzir(spec, artboard=(1080, 1350))
    textos = tradutor.textos_de(post)

    assert textos["complemento"] == spec.texto_exato["complemento"]
    assert textos["cta"] == spec.texto_exato["cta"]


def test_campo_de_texto_vazio_nao_vira_camada_fantasma():
    """CTA vazio some do plano; camada de texto sem runs é recusa no resolve."""
    spec = _spec(texto_exato={
        "headline": "Vai consultar o Pé-de-Meia no app?",
        "complemento": "",
        "cta": "",
    })
    post = tradutor.traduzir(spec, artboard=(1080, 1350))

    assert set(tradutor.textos_de(post)) == {"headline"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Família cromática: cor sustentada por código, não por prosa
# ─────────────────────────────────────────────────────────────────────────────

def test_familia_cromatica_vira_skin_com_duas_cores_em_superficie_grande():
    """Instrução em prosa não segura cor — um lote inteiro voltou azul-marinho.

    A skin é o lugar onde a família vira pixel obrigatório: a superfície de
    fundo e o acento saem de cores DIFERENTES da família declarada.
    """
    skin = tradutor.skin_da_familia(FAMILIA)

    superficie = skin["color"]["surface"]["base"]
    acento = skin["color"]["accent"]["text"]
    assert superficie != acento
    assert {superficie, acento} <= set(skin["familia_resolvida"].values())


def test_familia_com_menos_de_duas_cores_e_recusada_no_tradutor():
    """Falha fechada antes do custo: uma cor só não é família."""
    with pytest.raises(tradutor.FamiliaCromaticaInsuficiente):
        tradutor.skin_da_familia(["azul royal"])


def test_cor_desconhecida_nao_vira_cinza_silencioso():
    """Nome que o léxico não conhece é recusa, não um default que ninguém vê."""
    with pytest.raises(tradutor.CorDesconhecida, match="fúcsia interplanetário"):
        tradutor.skin_da_familia(["fúcsia interplanetário", "azul royal"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. O que o resolve.py recusa — e que o tradutor tem de evitar antes do custo
# ─────────────────────────────────────────────────────────────────────────────

def test_accent_cai_sobre_a_ancora_de_desejo_e_nao_sobre_o_mecanismo():
    """O acento é a cor mais forte da peça; ela pertence ao DESEJO.

    `assunto_principal` é o app; `ancora_de_desejo` é o dinheiro. Deixar o
    bisturi cair em "app" pintaria de ouro exatamente o mecanismo que a
    blindagem de `test_criativo_ancora_e_multiformato` existe para tirar da
    frente.
    """
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350), ancora="Pé-de-Meia")
    acentuados = [r["text"] for r in tradutor.runs_da_headline(post) if r.get("accent")]

    assert acentuados == ["Pé-de-Meia"]


def test_accent_respeita_o_budget_de_duas_palavras():
    """`resolve.py:100` reprova >2 palavras acentuadas. Accent é bisturi.

    Uma âncora longa não pode arrastar a headline inteira para o acento: o
    resolve recusaria a peça DEPOIS de o tradutor ter feito todo o trabalho.
    """
    spec = _spec(texto_exato={
        "headline": "Todas as palavras desta headline enorme querem virar acento agora",
        "complemento": "",
        "cta": "",
    })
    post = tradutor.traduzir(
        spec, artboard=(1080, 1350), ancora="palavras desta headline enorme querem",
    )

    acentuadas = sum(
        len(run["text"].split())
        for run in tradutor.runs_da_headline(post)
        if run.get("accent")
    )
    assert 0 < acentuadas <= 2


def test_ancora_ausente_da_headline_nao_inventa_acento():
    """Sem casamento literal, nenhum run é acentuado — e a peça segue válida."""
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350), ancora="Bolsa Família")

    assert not [r for r in tradutor.runs_da_headline(post) if r.get("accent")]
    assert tradutor.headline_de(post) == _spec().texto_exato["headline"]


def test_spec_traduzida_tem_os_cinco_campos_que_o_resolve_exige():
    """`resolve.py:109` — ausência de qualquer um é err() antes de abrir o Chrome."""
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350))

    assert {"schema_version", "spec_id", "skin", "artboard", "gates"} <= set(post)


def test_todo_texto_com_fit_auto_declara_overflow_fail():
    """`resolve.py:97` — fit auto sem overflow='fail' é recusa fail-closed."""
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350))

    for camada in tradutor.camadas_de_texto(post):
        fit = camada["fit"]
        if fit["mode"] == "auto":
            assert fit["overflow"] == "fail"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Geometria: a zona do plano é fracionária, e é por isso que ela reproporciona
# ─────────────────────────────────────────────────────────────────────────────

def test_safe_area_sai_da_margem_segura_da_peca():
    spec = _spec()
    post = tradutor.traduzir(spec, artboard=(1080, 1350))

    assert post["artboard"]["safe_area"] == {
        "top": spec.margem_segura["topo"],
        "bottom": spec.margem_segura["base"],
        "left": spec.margem_segura["esquerda"],
        "right": spec.margem_segura["direita"],
    }


def test_zona_fracionaria_do_plano_reproporciona_em_cada_artboard():
    """`planos.PLANOS[*]['zona']` é (x0,y0,x1,y1) em FRAÇÃO do canvas.

    É essa escolha de unidade que faz multi-formato custar uma multiplicação e
    não um recorte: a mesma faixa inferior de 0.58→0.94 vira 783→1269 no 4x5 e
    1113→1804 no 9x16, sem ninguém redesenhar nada.
    """
    spec = _spec()
    cena = {"id": "cena", "file": "out/cena.png"}
    quatro_por_cinco = tradutor.traduzir(spec, artboard=(1080, 1350), asset=cena)
    story = tradutor.traduzir(spec, artboard=(1080, 1920), asset=cena)

    assert tradutor.zona_em_pixels(quatro_por_cinco)["y"] == round(0.58 * 1350)
    assert tradutor.zona_em_pixels(story)["y"] == round(0.58 * 1920)


def test_peca_sem_plano_de_composicao_ainda_traduz():
    """`plano_de_composicao` é vazio no caminho 'modelo' e em specs históricas."""
    post = tradutor.traduzir(_spec(plano_de_composicao={}), artboard=(1080, 1350))

    assert tradutor.headline_de(post)


def test_sem_plano_a_zona_e_a_area_segura_inteira():
    """Sem plano, a largura útil é a área segura inteira — não uma faixa chutada.

    `planos_de` só devolve zona para `campo_cromatico` e `rodape_limpo`; as
    outras rotas chegam aqui com `plano_de_composicao` vazio. Inventar uma faixa
    nesse caso apertaria `tipografia_protagonista`, cuja graça é a letra dominar
    o quadro.
    """
    spec = _spec(plano_de_composicao={})
    post = tradutor.traduzir(spec, artboard=(1080, 1350))
    zona = tradutor.zona_em_pixels(post)

    assert zona["x"] == spec.margem_segura["esquerda"]
    assert zona["w"] == 1080 - spec.margem_segura["esquerda"] - spec.margem_segura["direita"]


def test_skin_declara_o_sha256_da_fonte_que_o_motor_confere():
    """`resolve.py:valida_fontes` recusa fonte sem sha e sha divergente.

    Uma skin gerada em runtime que esquecesse o campo produziria KeyError no
    resolve — falha feia, tarde, e depois de o tradutor ter feito o trabalho.
    Fonte adulterada é recusa pré-custo, e o sha fixado aqui é o recibo disso.
    """
    skin = tradutor.skin_da_familia(FAMILIA)

    for fonte in skin["fonts"]:
        assert len(fonte["sha256"]) == 64
        assert fonte["file"].startswith("fonts/")


def test_ancora_aceita_como_sinonimo_tambem_recebe_o_acento():
    """`ancoras_aceitas` existe porque "poupança do ensino médio" É Pé-de-Meia.

    A peça 4 do lote real não escreve a âncora literal — escreve o sinônimo que
    o operador aprovou. Aceitar só a string canônica deixaria justamente a peça
    mais bem escrita do lote sem o acento no desejo.
    """
    spec = _spec(texto_exato={
        "headline": "poupança do ensino médio: dados fora do ar?",
        "complemento": "", "cta": "",
    })
    post = tradutor.traduzir(
        spec, artboard=(1080, 1350),
        ancora="Pé-de-Meia", ancoras_aceitas=["poupança do ensino médio"],
    )
    acentuados = [r["text"] for r in tradutor.runs_da_headline(post) if r.get("accent")]

    assert acentuados == ["poupança do"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. O que o gate de DOM reprovou num lote real, e que virou regra aqui
# ─────────────────────────────────────────────────────────────────────────────

def test_zona_do_plano_e_recortada_pela_area_segura():
    """As duas geometrias vêm de sistemas diferentes e DISCORDAM.

    Medido: as 16 peças do lote Pé-de-Meia foram reprovadas 16/16 com
    "tinta fora da safe area (l:54 …)". `planos.PLANOS["faixa_superior"]["zona"]`
    começa em 0.05 (54 px num canvas de 1080) e `especificar` calcula margem de
    7% (76 px). A zona é HIPÓTESE sobre onde a foto está calma; a área segura é
    CONTRATO com a plataforma. Tinta só pode viver na interseção — e quem tem de
    ceder é a hipótese.
    """
    spec = _spec(
        margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 76},
        plano_de_composicao={"nome": "faixa_superior", "pedido": "…",
                             "zona": [0.05, 0.06, 0.95, 0.42]},
    )
    zona = tradutor.zona_em_pixels(tradutor.traduzir(
        spec, artboard=(1080, 1350), asset={"id": "cena", "file": "out/cena.png"}))

    # x=54 era ilegal e foi empurrado para a borda da área segura
    assert zona["x"] == 76
    # y=81 já era legal (0.06 * 1350) e sobrevive intacto: o recorte só corrige
    # quem estava fora, e não achata a hipótese que estava certa
    assert zona["y"] == 81
    assert zona["x"] + zona["w"] <= 1080 - 76


def test_skin_declara_ink_padding_porque_o_gate_mede_TINTA_e_nao_caixa():
    """`render.py:611` reprova pela TINTA, e o glifo pinta fora do layout box.

    Toda skin do acervo declara `ink_padding` (`render.py:265` o aplica como
    padding CSS). Uma skin gerada sem ele encosta a letra na borda da área
    segura e a peça é recusada depois de renderizada — tarde e caro.
    """
    skin = tradutor.skin_da_familia(FAMILIA)

    assert skin["type"]["display"]["ink_padding"]
    assert skin["type"]["body"]["ink_padding"]


def test_frame_declara_zona_h_para_o_bloco_nao_transbordar_por_baixo():
    """Largura e nº de linhas não bastam: a ALTURA do bloco é outra restrição.

    Medido no lote real: com `faixa_inferior` (zona 0.58→0.94) o bloco crescia
    para baixo e o CTA saía em b=1286 num canvas de 1350 com base segura 76 —
    limite 1274. `render.py:571` já sabe resolver isso: um frame com
    `data-zona-h` faz o fitter encolher os filhos `auto` até o bloco caber. O
    orçamento é a menor das duas fronteiras: o fim da zona e a área segura.
    """
    spec = _spec(
        margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 76},
        plano_de_composicao={"nome": "faixa_inferior", "pedido": "…",
                             "zona": [0.05, 0.58, 0.95, 0.94]},
    )
    frame = tradutor.frame_de(tradutor.traduzir(
        spec, artboard=(1080, 1350), asset={"id": "cena", "file": "out/cena.png"}))

    # zona termina em 0.94*1350 = 1269; área segura termina em 1274. Vence a zona.
    assert frame["zona_h"] == 1269 - frame["pos"]["y"]


def test_zona_h_nunca_ultrapassa_a_area_segura_inferior():
    """Quando a zona vai até a borda, quem limita é a área segura."""
    spec = _spec(
        margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 200},
        plano_de_composicao={"nome": "faixa_inferior", "pedido": "…",
                             "zona": [0.05, 0.58, 0.95, 1.0]},
    )
    post = tradutor.traduzir(spec, artboard=(1080, 1350),
                             asset={"id": "cena", "file": "out/cena.png"})
    frame = tradutor.frame_de(post)

    assert frame["pos"]["y"] + frame["zona_h"] == 1350 - 200


def test_sem_foto_o_plano_de_composicao_nao_governa_a_zona():
    """O plano existe para DESVIAR da foto. Sem foto, não há o que desviar.

    Medido olhando o lote: `faixa_superior` empurrou as quatro peças para o
    terço de cima e deixou 65% de campo cromático vazio embaixo — porque a zona
    reserva espaço para uma cena que, em `typography_only`, não existe. A
    tipografia então ancora no rodapé da área segura, que é a convenção das
    skins do acervo (kintsugi, volcnews) e o que dá peso editorial ao bloco.
    """
    spec = _spec(
        margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 76},
        plano_de_composicao={"nome": "faixa_superior", "pedido": "…",
                             "zona": [0.05, 0.06, 0.95, 0.42]},
    )
    frame = tradutor.frame_de(tradutor.traduzir(spec, artboard=(1080, 1350)))

    assert frame["pos"]["anchor"] == "bottom_left"
    assert frame["pos"]["y"] == 76


def test_com_foto_o_plano_volta_a_governar():
    """Havendo cena, a zona do plano é a hipótese sobre onde ela está calma."""
    spec = _spec(plano_de_composicao={"nome": "faixa_inferior", "pedido": "…",
                                      "zona": [0.05, 0.58, 0.95, 0.94]})
    post = tradutor.traduzir(spec, artboard=(1080, 1350),
                             asset={"id": "cena", "file": "out/cena.png"})
    frame = tradutor.frame_de(post)

    assert frame["pos"]["anchor"] == "top_left"
    assert frame["pos"]["y"] == round(0.58 * 1350)


# ─────────────────────────────────────────────────────────────────────────────
# 7. A cena: uma imagem de IA paga uma vez, servindo N formatos
# ─────────────────────────────────────────────────────────────────────────────

CENA = {"id": "cena", "file": "out/bg_plano_faixa_inferior.png"}


def test_com_cena_a_spec_usa_layers_de_topo_e_nao_slides():
    """⚠️ `scrim.gradient.auto` e `colocacao.modo=auto` são MUTUAMENTE EXCLUSIVOS.

    `resolve.py` mede o scrim varrendo `resolvido.get("layers")` — as camadas de
    TOPO — e resolve a colocação automática varrendo `resolvido.get("slides")`.
    Uma spec com `slides` nunca tem o scrim medido; uma com `layers` nunca tem a
    colocação medida. Havendo cena escolhemos o scrim, porque é ele que SELA o
    contraste do texto sobre a foto — a colocação só o desvia.
    """
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350), asset=CENA)

    assert "layers" in post
    assert "slides" not in post


def test_sem_cena_nao_ha_scrim_nem_grao():
    """Scrim sobre nada é uma chapa preta por cima de um campo de cor."""
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350))

    assert not [c for c in tradutor.camadas_de(post) if c["type"] in ("scrim", "image")]


def test_cena_empilha_imagem_scrim_vinheta_e_grao_nessa_ordem():
    """Empilhamento é a ordem do array (`render.py` não tem z-index).

    Foto embaixo; scrim selando o contraste; vinheta fechando a borda; o texto;
    e o grão POR CIMA de tudo, que é o que costura a letra de código à foto de
    IA e tira o aspecto de adesivo colado.
    """
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350), asset=CENA)
    tipos = [c["type"] for c in tradutor.camadas_de(post)]

    assert tipos == ["image", "scrim", "vinheta", "frame", "texture"]


def test_faixa_medida_pelo_scrim_e_derivada_da_zona_do_texto():
    """Não se declara à mão onde o texto vai estar — o código já sabe.

    `resolve.scrim_auto` mede a luminância da foto DENTRO de `faixa_texto` e
    devolve o alpha mínimo para o contraste alvo. Se essa faixa for digitada
    solta, ela e a zona do texto divergem na primeira mudança de plano, e o
    engine passa a selar contraste num lugar onde não há letra.
    """
    spec = _spec(
        margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 76},
        plano_de_composicao={"nome": "faixa_inferior", "pedido": "…",
                             "zona": [0.05, 0.58, 0.95, 0.94]},
    )
    post = tradutor.traduzir(spec, artboard=(1080, 1350), asset=CENA)
    scrim = next(c for c in tradutor.camadas_de(post) if c["type"] == "scrim")

    assert scrim["style"]["gradient"]["auto"] is True
    assert scrim["style"]["gradient"]["faixa_texto"] == [0.58, 0.94]
    assert scrim["asset_ref"] == CENA["id"]


def test_faixa_medida_segue_a_zona_RECORTADA_e_nao_a_pedida():
    """Quem manda é onde a letra ficou, não onde o plano pediu que ficasse.

    Com base segura de 243 px num canvas de 1350, a zona `faixa_inferior` é
    cortada em 0.82 e não vai até 0.94. Medir o scrim na faixa pedida selaria
    contraste num trecho de foto que o texto nunca ocupa — e deixaria de selar
    onde ele ocupa.
    """
    spec = _spec(
        margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 243},
        plano_de_composicao={"nome": "faixa_inferior", "pedido": "…",
                             "zona": [0.05, 0.58, 0.95, 0.94]},
    )
    post = tradutor.traduzir(spec, artboard=(1080, 1350), asset=CENA)
    scrim = next(c for c in tradutor.camadas_de(post) if c["type"] == "scrim")

    assert scrim["style"]["gradient"]["faixa_texto"] == [0.58, 0.82]


def test_cta_vira_botao_de_verdade_e_nao_uma_linha_de_texto():
    """Arbitragem quer botão: alvo de clique aparente, não um link tipográfico.

    O motor já tem a peça — um `frame` com `style.fill` vira container pintado
    (`render.py`), e ganha `data-mask` justamente por ser vizinho declarado e
    não tinta de texto, que é o que faz o gate de clearance julgá-lo certo.
    """
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350), asset=CENA, botao=True)
    botao = tradutor.botao_de(post)

    assert botao["style"]["fill"] == "$color.accent.text"
    assert botao["style"]["radius"] > 0
    assert botao["children"][0]["style"]["color"] == "$color.text.on_accent"
    assert botao["children"][0]["runs"][0]["text"] == "Ver orientações"


def test_sem_cta_nao_se_desenha_botao_vazio():
    spec = _spec(texto_exato={"headline": "Vai consultar o Pé-de-Meia no app?",
                              "complemento": "Entenda como usar.", "cta": ""})
    post = tradutor.traduzir(spec, artboard=(1080, 1350), asset=CENA, botao=True)

    assert tradutor.botao_de(post) is None


def test_skin_traz_grao_e_vinheta_porque_a_camada_os_referencia_por_token():
    """`$efeitos.grao.opacity` num spec sem `efeitos` na skin é ref não resolvida."""
    efeitos = tradutor.skin_da_familia(FAMILIA)["efeitos"]

    assert efeitos["grao"]["opacity"] > 0
    assert efeitos["vinheta"]["cor"]


def test_botao_e_camada_de_topo_porque_frame_aninhado_escapa_do_fluxo():
    """⚠️ `frame` NÃO se aninha. `_pos_css` (`render.py:65`) emite
    `position:absolute` para TODO frame, e sem `pos` isso vira `left:0;top:0`.

    Medido: o botão declarado como filho do bloco de conteúdo saltou para a
    origem do canvas e reprovou as quatro peças com
    `colisão de texto: headline × cta (185×29px)`. Nenhuma spec do acervo aninha
    frame em frame — todas põem no topo, com `pos` próprio. O botão segue a
    mesma regra.
    """
    post = tradutor.traduzir(_spec(), artboard=(1080, 1350), asset=CENA, botao=True)
    botao = tradutor.botao_de(post)

    assert botao in tradutor.camadas_de(post)
    assert botao not in tradutor.frame_de(post)["children"]
    assert botao["pos"]["anchor"] == "bottom_left"


def test_sem_foto_o_bloco_SOBE_para_abrir_espaco_ao_botao():
    """Âncora inferior: a reserva de rodapé levanta o bloco inteiro.

    A altura do botão é contável AQUI porque é o tradutor quem escolhe corpo,
    padding e raio do CTA — não é fato para perguntar a ninguém.
    """
    spec = _spec(margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 76})
    com = tradutor.frame_de(tradutor.traduzir(spec, artboard=(1080, 1350), botao=True))
    sem = tradutor.frame_de(tradutor.traduzir(spec, artboard=(1080, 1350), botao=False))

    assert com["pos"]["y"] - sem["pos"]["y"] == (
        tradutor.ALTURA_DO_BOTAO + tradutor.RESPIRO_DO_BOTAO)


def test_com_foto_a_reserva_ENCOLHE_o_orcamento_de_altura():
    """Âncora superior: o topo do bloco é o plano, então quem cede é a base.

    Levantar o `y` aqui moveria o texto para fora da zona calma que a foto
    abriu — a reserva tira altura do orçamento, não posição do bloco.
    """
    spec = _spec(margem_segura={"esquerda": 76, "direita": 76, "topo": 76, "base": 76})
    com = tradutor.frame_de(tradutor.traduzir(spec, artboard=(1080, 1350),
                                              asset=CENA, botao=True))
    sem = tradutor.frame_de(tradutor.traduzir(spec, artboard=(1080, 1350),
                                              asset=CENA, botao=False))

    assert com["pos"]["y"] == sem["pos"]["y"]
    assert com["zona_h"] < sem["zona_h"]
    # o invariante que importa: a base do bloco não invade a faixa do botão
    piso = 1350 - 76 - tradutor.ALTURA_DO_BOTAO - tradutor.RESPIRO_DO_BOTAO
    assert com["pos"]["y"] + com["zona_h"] <= piso


def test_corte_da_foto_ancora_no_lado_oposto_a_zona_do_texto():
    """A única alavanca de enquadramento que a spec tem, e ela é derivável.

    `object-fit:cover` é fixo no motor, mas `object_position` é honrado
    (`render.py`, ramo `image`). Medido: a mesma foto 4:5 num artboard 1.91:1
    com corte centrado DECAPITA o sujeito — sobrou barba e ombro. O plano já
    diz onde o sujeito está, porque reservou o lado contrário para o texto:
    `faixa_inferior` pede o sujeito na metade de CIMA, logo o corte ancora no
    topo. Ninguém precisa declarar isso.
    """
    spec = _spec(plano_de_composicao={"nome": "faixa_inferior", "pedido": "…",
                                      "zona": [0.05, 0.58, 0.95, 0.94]})
    post = tradutor.traduzir(spec, artboard=(1200, 628), asset=CENA)
    imagem = next(c for c in tradutor.camadas_de(post) if c["type"] == "image")

    assert imagem["object_position"] == "center top"


def test_plano_de_faixa_superior_inverte_a_ancora_do_corte():
    """Sujeito embaixo, texto em cima: o corte tem de segurar a base."""
    spec = _spec(plano_de_composicao={"nome": "faixa_superior", "pedido": "…",
                                      "zona": [0.05, 0.06, 0.95, 0.42]})
    post = tradutor.traduzir(spec, artboard=(1200, 628), asset=CENA)
    imagem = next(c for c in tradutor.camadas_de(post) if c["type"] == "image")

    assert imagem["object_position"] == "center bottom"


def test_plano_de_coluna_ancora_o_corte_no_eixo_horizontal():
    """`coluna_direita` reserva a direita para o texto — o sujeito está à esquerda."""
    spec = _spec(plano_de_composicao={"nome": "coluna_direita", "pedido": "…",
                                      "zona": [0.48, 0.20, 0.95, 0.92]})
    post = tradutor.traduzir(spec, artboard=(1200, 628), asset=CENA)
    imagem = next(c for c in tradutor.camadas_de(post) if c["type"] == "image")

    assert imagem["object_position"] == "left center"


def test_ancora_declarada_pelo_operador_vence_a_derivada():
    """Derivar é o padrão; a foto que foge da regra ainda pode ser dirigida."""
    post = tradutor.traduzir(_spec(), artboard=(1200, 628),
                             asset={**CENA, "object_position": "right bottom"})
    imagem = next(c for c in tradutor.camadas_de(post) if c["type"] == "image")

    assert imagem["object_position"] == "right bottom"


# ─────────────────────────────────────────────────────────────────────────────
# 8. A faixa medida tem de ser a faixa VISTA
# ─────────────────────────────────────────────────────────────────────────────

def test_faixa_do_scrim_e_convertida_para_o_espaco_da_FOTO():
    """⚠️ `resolve.scrim_auto` mede o ARQUIVO, não a área visível.

    Ele abre o asset e fatia pela fração da altura DELE (`resolve.py:76`),
    ignorando o artboard e o corte — recebe a spec e nunca a usa. Fora do 4:5
    nativo, a faixa em coordenadas de artboard aponta para pixels que ninguém
    vê: numa entrega 1.91:1 com corte ancorado no topo, a faixa 0.58→0.73 do
    quadro cai em 0.24→0.31 da foto, onde está o rosto claro e não o fundo
    escuro. Medir errado devolve selo otimista, e selo otimista é texto ilegível
    aprovado por um número.
    """
    convertida = tradutor.faixa_na_foto(
        faixa=[0.58, 0.73], artboard=(1200, 628), foto=(1088, 1360),
        object_position="center top",
    )

    assert convertida == [0.2428, 0.3056]


def test_conversao_e_identidade_quando_a_proporcao_bate():
    """Foto 4:5 num artboard 4:5: não há corte, logo não há o que converter."""
    assert tradutor.faixa_na_foto(
        faixa=[0.58, 0.94], artboard=(1088, 1360), foto=(1088, 1360),
        object_position="center center",
    ) == [0.58, 0.94]


def test_sem_dimensao_declarada_a_faixa_passa_intacta():
    """O tradutor não lê disco. Sem `w`/`h` no asset, não há conversão possível.

    Passar a faixa crua é o comportamento honesto: o selo sai como sempre saiu,
    e quem quiser a medição certa declara o tamanho da foto.
    """
    post = tradutor.traduzir(_spec(), artboard=(1200, 628), asset=CENA)
    scrim = next(c for c in tradutor.camadas_de(post) if c["type"] == "scrim")

    assert scrim["style"]["gradient"]["faixa_texto"] == scrim["style"]["gradient"]["faixa_no_quadro"]


def test_com_dimensao_declarada_a_faixa_medida_muda():
    spec = _spec(margem_segura={"esquerda": 84, "direita": 84, "topo": 84, "base": 84})
    post = tradutor.traduzir(spec, artboard=(1200, 628),
                             asset={**CENA, "w": 1088, "h": 1360})
    grad = next(c for c in tradutor.camadas_de(post) if c["type"] == "scrim")["style"]["gradient"]

    assert grad["faixa_texto"] != grad["faixa_no_quadro"]
    # o corte ancorou no topo, então a faixa medida sobe na foto
    assert grad["faixa_texto"][0] < grad["faixa_no_quadro"][0]
