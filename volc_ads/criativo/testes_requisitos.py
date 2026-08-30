"""Testes das exigências por canal — quem é dono de qual número.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/criativo -q

**Nenhum teste aqui fala com o Google.** O que se prova é de onde vem cada
número e o que acontece quando a fonte muda de lugar — porque o defeito que
esta camada precisa evitar não é aritmético, é de propriedade: duas tabelas
declarando o mesmo teto divergem, e a divergência só aparece no dia em que
alguém atualiza uma e esquece a outra.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads.criativo import requisitos  # noqa: E402
from volc_ads.criativo.contrato import EspecificacaoDeAsset, TipoDeAsset  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]
LIMITES = yaml.safe_load((RAIZ / "volc_ads/campanha/limites.yaml").read_text(encoding="utf-8"))


# ── propriedade dos números ─────────────────────────────────────────────────


def test_o_caractere_do_display_vem_do_dono_e_nao_de_uma_copia():
    spec = requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.HEADLINE)
    assert spec.caracteres_maximos == LIMITES["texto"]["headline_display"]["max_chars"]
    assert "limites.yaml" in spec.fonte_dos_numeros


def test_a_contagem_do_display_tambem_vem_do_dono():
    # `marketing_total_max` é COMBINADO no proto; aqui ele vale também como
    # teto individual, que é um limite superior verdadeiro e barato de conferir.
    spec = requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.IMAGEM_MARKETING)
    assert spec.quantidade_minima == LIMITES["display_asset"]["marketing_min"]
    assert spec.quantidade_maxima == LIMITES["display_asset"]["marketing_total_max"]


def test_headline_longa_do_display_e_obrigatoria_e_singular():
    # `long_headline` é Required no RDA. Opcional-com-default aqui derrubaria o
    # construtor de Display no primeiro payload.
    spec = requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.HEADLINE_LONGA)
    assert spec.obrigatorio is True
    assert (spec.quantidade_minima, spec.quantidade_maxima) == (1, 1)


def test_headline_longa_do_display_e_singular_e_a_do_demand_gen_nao():
    # O proto do RDA declara `long_headline` SINGULAR; o Demand Gen aceita cinco.
    # Herdar o número errado sobe um payload que a API recusa inteiro.
    assert requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.HEADLINE_LONGA).quantidade_maxima == 1
    assert requisitos.exigencia_de("DEMAND_GEN").de(TipoDeAsset.HEADLINE_LONGA).quantidade_maxima == 5


def test_todo_numero_declara_de_onde_veio():
    for canal in requisitos.CANAIS:
        for spec in requisitos.exigencia_de(canal).especificacoes:
            assert spec.fonte_dos_numeros, f"{canal}/{spec.tipo.value} sem fonte"


def test_os_canais_cobertos_pela_matriz_nao_se_dizem_provisorios():
    for canal in ("DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX"):
        exigencia = requisitos.exigencia_de(canal)
        assert exigencia.provisorio is False
        assert "matriz-api" in exigencia.fonte


def test_o_canal_que_a_matriz_nao_cobre_continua_dizendo_que_nao_sabe():
    # Vídeo não tem página na matriz, e o formato (in-stream, in-feed, bumper,
    # Shorts) muda duração e textos exigidos sem que isso esteja modelado.
    assert requisitos.exigencia_de("VIDEO").provisorio is True
    assert "VIDEO" in requisitos.aviso_de_procedencia()
    assert "PROVISÓRIO" in requisitos.aviso_de_procedencia("VIDEO")
    assert "matriz-api" in requisitos.aviso_de_procedencia("DISPLAY")


# ── o número emprestado, que é o defeito caro desta tabela ──────────────────


def test_display_nao_herda_o_peso_maximo_de_performance_max():
    # A tabela completa com 5120 KB é a de PMax. O proto do RDA não declara
    # peso, e a matriz marca `[NÃO CONFIRMADO]`. Um lote que valide contra o
    # teto emprestado passa aqui e é recusado pela API depois, com o erro
    # apontando para o asset e não para a regra.
    display = requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.IMAGEM_MARKETING)
    pmax = requisitos.exigencia_de("PERFORMANCE_MAX").de(TipoDeAsset.IMAGEM_MARKETING)
    assert display.bytes_maximos is None
    assert pmax.bytes_maximos == 5242880


def test_display_nao_herda_spec_nenhuma_de_video_de_performance_max():
    display = requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.VIDEO)
    assert display.quantidade_maxima == 5          # a contagem o proto declara
    assert display.duracao_minima_s is None        # a duração, não
    assert display.bytes_maximos is None
    assert requisitos.exigencia_de("PERFORMANCE_MAX").de(TipoDeAsset.VIDEO).duracao_minima_s == 10.0


def test_o_logo_do_demand_gen_tem_teto_proprio_e_nao_o_das_imagens():
    exigencia = requisitos.exigencia_de("DEMAND_GEN")
    # 150 KB no logo contra 5 MB nas imagens: duas linhas da MESMA tabela.
    assert exigencia.de(TipoDeAsset.LOGO_QUADRADO).bytes_maximos == 153600
    assert exigencia.de(TipoDeAsset.IMAGEM_MARKETING).bytes_maximos == 5242880
    # 144×144 é o piso do Help Center e satisfaz também os 128×128 do proto.
    assert exigencia.de(TipoDeAsset.LOGO_QUADRADO).largura_minima == 144


def test_demand_gen_separa_teto_total_do_minimo_da_imagem_base():
    combinados = requisitos.exigencia_de("DEMAND_GEN").combinados
    teto = next(t for t in combinados if "todas as orientações" in t.rotulo)
    base = next(t for t in combinados if "imagem base" in t.rotulo)

    assert teto.maximo == LIMITES["demand_gen_asset"]["marketing_total_max"]
    assert teto.minimo == 0
    assert base.maximo is None
    assert base.minimo == LIMITES["demand_gen_asset"]["marketing_pair_min"]
    assert set(base.tipos) == {
        TipoDeAsset.IMAGEM_MARKETING,
        TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
    }


# ── o que o canal exige, e o que ele só recomenda ───────────────────────────


def test_logo_do_display_e_recomendado_sem_ser_exigido():
    # O proto escreve "is required" para as imagens de marketing e NÃO escreve
    # para logo. Barrar por logo ausente recusaria localmente um payload que a
    # API aceita — e portão que dá falso positivo é portão que alguém desliga.
    spec = requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.LOGO_QUADRADO)
    assert spec.quantidade_minima == 0
    assert spec.quantidade_recomendada == 1
    assert spec.obrigatorio is False


def test_display_nao_tem_slot_de_retrato():
    # `ResponsiveDisplayAdInfo` não tem imagem de retrato. Declarar o slot faria
    # a camada encomendar uma geração paga que nunca subiria.
    assert requisitos.exigencia_de("DISPLAY").de(TipoDeAsset.IMAGEM_MARKETING_RETRATO) is None
    assert requisitos.exigencia_de("PERFORMANCE_MAX").de(TipoDeAsset.IMAGEM_MARKETING_RETRATO)


def test_o_teto_combinado_existe_e_cita_o_dono():
    tetos = {t.rotulo: t for t in requisitos.exigencia_de("DISPLAY").combinados}
    imagens = next(t for t in tetos.values() if TipoDeAsset.IMAGEM_MARKETING in t.tipos)
    assert imagens.maximo == LIMITES["display_asset"]["marketing_total_max"]
    assert "limites.yaml" in imagens.fonte_dos_numeros


# ── fronteiras ──────────────────────────────────────────────────────────────


def test_search_diz_quem_e_o_dono_em_vez_de_devolver_lote_vazio():
    # Devolver exigência vazia seria lido como "não precisa de nada", que é
    # verdade para imagem e mentira para a copy.
    with pytest.raises(ValueError, match="campanha/validacao.py"):
        requisitos.exigencia_de("SEARCH")


def test_canal_desconhecido_levanta_com_a_lista():
    with pytest.raises(ValueError, match="DEMAND_GEN"):
        requisitos.exigencia_de("TIKTOK")


def test_especificacao_com_maximo_abaixo_do_minimo_e_recusada():
    with pytest.raises(ValueError, match="< mínimo"):
        EspecificacaoDeAsset(
            tipo=TipoDeAsset.HEADLINE, quantidade_minima=3, quantidade_maxima=1
        )


# ── a projeção binária: só arquivo, sem texto ───────────────────────────────


def test_a_exigencia_inteira_do_display_cobra_texto_e_por_isso_nao_serve_a_um_lote_de_imagens():
    """O fato que motiva `exigencia_binaria_de`, provado em vez de afirmado.

    Se um dia o YAML deixar de cobrar texto em DISPLAY, este teste falha — e
    aí a projeção binária perdeu a razão de existir e deve ser reavaliada, não
    mantida por inércia.
    """
    inteira = requisitos.exigencia_de("DISPLAY")
    textuais_obrigatorios = [
        t for t in inteira.obrigatorios if t not in requisitos.TIPOS_BINARIOS
    ]
    assert textuais_obrigatorios, (
        "DISPLAY deixou de exigir texto; a projeção binária virou desnecessária")


def test_a_exigencia_binaria_do_display_nao_carrega_nenhum_tipo_textual():
    e = requisitos.exigencia_binaria_de("DISPLAY")
    assert e.especificacoes, "projeção vazia esconderia o canal inteiro"
    for spec in e.especificacoes:
        assert spec.tipo in requisitos.TIPOS_BINARIOS, f"{spec.tipo.value} é texto"
    assert set(e.obrigatorios) == {
        TipoDeAsset.IMAGEM_MARKETING, TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
    }


def test_a_projecao_preserva_numero_fonte_e_provisoriedade():
    """Projetar é filtrar, nunca recalcular: os números têm de ser os MESMOS."""
    inteira = requisitos.exigencia_de("DISPLAY")
    binaria = requisitos.exigencia_binaria_de("DISPLAY")
    assert binaria.canal == inteira.canal
    assert binaria.fonte == inteira.fonte
    assert binaria.provisorio == inteira.provisorio
    for spec in binaria.especificacoes:
        assert spec == inteira.de(spec.tipo), (
            f"{spec.tipo.value} foi alterado na projeção — filtrar não é recalcular")


def test_os_tetos_combinados_de_arquivo_sobrevivem_a_projecao():
    """Os tetos de 15 e de 5 são a razão de o `TetoCombinado` existir."""
    binaria = requisitos.exigencia_binaria_de("DISPLAY")
    maximos = sorted(t.maximo for t in binaria.combinados)
    assert maximos == [
        LIMITES["display_asset"]["logo_total_max"],
        LIMITES["display_asset"]["marketing_total_max"],
    ]
    # E nenhum teto sobrevivente mistura texto com arquivo: um teto assim
    # somaria parcelas que não estão no lote e cobraria itens inexistentes.
    for teto in binaria.combinados:
        assert all(t in requisitos.TIPOS_BINARIOS for t in teto.tipos)


def test_search_continua_dizendo_quem_e_o_dono_tambem_na_projecao():
    """Canal sem asset binário levanta com o dono no texto, não devolve vazio."""
    with pytest.raises(ValueError, match="campanha/validacao.py"):
        requisitos.exigencia_binaria_de("SEARCH")


def test_canal_desconhecido_levanta_tambem_na_projecao():
    with pytest.raises(ValueError, match="DEMAND_GEN"):
        requisitos.exigencia_binaria_de("TIKTOK")


def test_todo_canal_com_construtor_tem_projecao_binaria_utilizavel():
    """Guarda para o próximo canal: PMax e Demand Gen já passam por aqui."""
    for canal in ("DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX"):
        e = requisitos.exigencia_binaria_de(canal)
        assert e.especificacoes, f"{canal} projetou vazio"
