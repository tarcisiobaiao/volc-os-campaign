"""Testes da validação de asset — a lista inteira, e o lote que sobrevive.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/criativo -q

Dois comportamentos concentram quase todos os testes daqui, e os dois custam
dinheiro quando falham:

  TUDO DE UMA VEZ   parar na primeira violação transforma a correção num jogo
                    de tentativa e erro, e cada rodada num motor pago é COGS.

  LOTE SOBREVIVE    reprovar 20 imagens porque 1 estava fora joga fora 19 boas.
                    A contagem mínima, porém, olha os APROVADOS — senão o
                    "temos 5 imagens" esconde que só 3 servem.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads.criativo import requisitos, validacao  # noqa: E402
from volc_ads.criativo.contrato import (  # noqa: E402
    Asset,
    Classe,
    LoteDeAssets,
    Procedencia,
    TipoDeAsset,
    hash_de_conteudo,
)

QUANDO = datetime(2026, 8, 26, 12, 0, 0)
DISPLAY = requisitos.exigencia_de("DISPLAY")
PMAX = requisitos.exigencia_de("PERFORMANCE_MAX")


def _procedencia(semente: str) -> Procedencia:
    return Procedencia(
        motor="teste", versao_do_motor="1", insumo=f"prompt {semente}", quando=QUANDO
    )


def _imagem(tipo, largura, altura, *, semente, mime="image/png", peso=2048) -> Asset:
    return Asset(
        tipo=tipo,
        procedencia=_procedencia(semente),
        conteudo_hash=hash_de_conteudo(f"{tipo.value}|{semente}"),
        mime=mime,
        bytes_totais=peso,
        largura=largura,
        altura=altura,
    )


def _texto(tipo, texto: str) -> Asset:
    return Asset(
        tipo=tipo,
        procedencia=_procedencia(texto),
        conteudo_hash=hash_de_conteudo(f"{tipo.value}|{texto}"),
        texto=texto,
    )


def _lote_minimo_valido(extras=()) -> LoteDeAssets:
    """O menor lote que o Display aceita, para que cada teste mexa em uma coisa só."""
    return LoteDeAssets(
        canal="DISPLAY",
        assets=(
            _imagem(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente="paisagem"),
            _imagem(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 1200, 1200, semente="quadrada"),
            _texto(TipoDeAsset.HEADLINE, "Saque do FGTS 2026"),
            _texto(TipoDeAsset.HEADLINE_LONGA, "Entenda quem tem direito ao saque do FGTS"),
            _texto(TipoDeAsset.DESCRICAO, "Veja regras, prazos e o calendário oficial."),
            _texto(TipoDeAsset.NOME_DA_EMPRESA, "Portal Mundo Mais"),
            *extras,
        ),
    )


def _codigos(resultado) -> set[str]:
    return {v.codigo for v in resultado.violacoes}


# ── o lote de referência ────────────────────────────────────────────────────


def test_o_lote_minimo_passa_e_avisa_o_logo_ausente():
    r = validacao.validar_lote(_lote_minimo_valido(), DISPLAY)
    assert r.ok, r.resumo()
    # Logo é recomendado, não exigido: o payload sobe, a peça fica pior.
    assert "Q3.abaixo_do_recomendado" in _codigos(r)
    assert all(v.severidade == "aviso" for v in r.violacoes)


def test_o_resumo_cita_a_fonte_e_so_avisa_quando_ela_e_provisoria():
    r = validacao.validar_lote(_lote_minimo_valido(), DISPLAY)
    assert "provisórios" not in r.resumo()

    video = validacao.validar_lote(
        LoteDeAssets(canal="VIDEO"), requisitos.exigencia_de("VIDEO")
    )
    assert "provisórios" in video.resumo()


# ── todas as violações, não a primeira ──────────────────────────────────────


def test_um_asset_ruim_devolve_todas_as_suas_violacoes_de_uma_vez():
    # Em Performance Max, que é o canal cuja tabela oficial declara peso.
    ruim = _imagem(
        TipoDeAsset.IMAGEM_MARKETING, 100, 100,
        semente="tudo errado", mime="image/bmp", peso=6_000_000,
    )
    achados = validacao.validar_asset(ruim, PMAX.de(TipoDeAsset.IMAGEM_MARKETING))
    codigos = {v.codigo for v in achados}
    assert {"F1.mime", "P1.peso", "D1.dimensao_minima", "D3.proporcao"} <= codigos


def test_o_que_a_especificacao_nao_sabe_ela_nao_cobra():
    # O mesmo arquivo pesado passa no Display, porque o proto do RDA não
    # declara peso máximo. Inventar um teto aqui reprovaria localmente algo que
    # a API talvez aceite — e o número emprestado de PMax seria um chute com
    # cara de regra.
    pesado = _imagem(TipoDeAsset.IMAGEM_MARKETING, 1200, 628,
                     semente="pesado", peso=6_000_000)
    assert validacao.validar_asset(pesado, DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING)) == ()


def test_cada_violacao_carrega_o_remedio_e_nao_so_o_defeito():
    ruim = _imagem(TipoDeAsset.IMAGEM_MARKETING, 1200, 1200, semente="quadrada demais")
    achados = validacao.validar_asset(ruim, DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING))
    proporcao = next(v for v in achados if v.codigo == "D3.proporcao")
    # Recorte é local e de graça; regerar é chamada paga pelo mesmo enquadramento.
    assert proporcao.classe is Classe.SANEAVEL_EM_CODIGO


def test_dimensao_abaixo_do_minimo_pede_geracao_nova_e_nao_recorte():
    # Ampliar por interpolação não cria pixel — nenhum conserto local resolve.
    pequena = _imagem(TipoDeAsset.IMAGEM_MARKETING, 382, 200, semente="pequena")
    achados = validacao.validar_asset(pequena, DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING))
    assert any(v.classe is Classe.REGERAR_ASSET for v in achados)


# ── medida ausente não é aprovação ──────────────────────────────────────────


def test_dimensao_desconhecida_vira_medir_antes_em_vez_de_passar():
    cega = Asset(
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        procedencia=_procedencia("sem medida"),
        conteudo_hash=hash_de_conteudo("sem medida"),
        mime="image/png",
        bytes_totais=2048,
    )
    achados = validacao.validar_asset(cega, DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING))
    assert [v.codigo for v in achados] == ["M1.sem_medida"]
    assert achados[0].classe is Classe.MEDIR_ANTES


def test_asset_sem_medida_nao_conta_para_a_quantidade_minima():
    lote = LoteDeAssets(canal="DISPLAY", assets=(
        Asset(
            tipo=TipoDeAsset.IMAGEM_MARKETING,
            procedencia=_procedencia("cega"),
            conteudo_hash=hash_de_conteudo("cega"),
            mime="image/png", bytes_totais=2048,
        ),
    ))
    r = validacao.validar_lote(lote, DISPLAY)
    faltas = [v for v in r.do_lote if v.codigo == "Q1.faltam"]
    paisagem = next(v for v in faltas if v.alvo == TipoDeAsset.IMAGEM_MARKETING.value)
    # A mensagem separa entregue de aprovado de propósito: "temos 1 imagem" é
    # verdade e é irrelevante quando nenhuma delas serve.
    assert "entregues 1, aprovados 0" in paisagem.detalhe


# ── o lote sobrevive ao asset ruim ──────────────────────────────────────────


def test_asset_reprovado_nao_derruba_os_aprovados():
    lote = _lote_minimo_valido(extras=(
        _imagem(TipoDeAsset.IMAGEM_MARKETING, 50, 26, semente="minúscula"),
    ))
    r = validacao.validar_lote(lote, DISPLAY)
    assert len(r.aprovados) == 6
    assert len(r.reprovados) == 1
    assert r.reprovados[0].largura == 50
    # A imagem ruim é perda conhecida: o lote segue publicável porque a que
    # sobrou já cumpre o mínimo do canal.
    assert r.ok
    assert r.erros and not r.erros_do_lote


def test_perda_que_deixa_buraco_derruba_o_lote_e_diz_qual_slot():
    lote = LoteDeAssets(canal="DISPLAY", assets=tuple(
        a for a in _lote_minimo_valido().assets
        if a.tipo is not TipoDeAsset.IMAGEM_MARKETING
    ) + (_imagem(TipoDeAsset.IMAGEM_MARKETING, 50, 26, semente="minúscula"),))
    r = validacao.validar_lote(lote, DISPLAY)
    assert not r.ok
    assert [v.alvo for v in r.erros_do_lote] == ["imagem_marketing"]


def test_asset_de_tipo_sem_slot_no_canal_e_aviso_e_nao_erro():
    lote = _lote_minimo_valido(extras=(
        _imagem(TipoDeAsset.IMAGEM_MARKETING_RETRATO, 960, 1200, semente="retrato"),
    ))
    r = validacao.validar_lote(lote, DISPLAY)
    sem_slot = next(v for v in r.do_lote if v.codigo == "E2.sem_slot")
    assert sem_slot.severidade == "aviso"
    assert r.ok, r.resumo()


# ── contagem e tetos ────────────────────────────────────────────────────────


def test_teto_combinado_pega_o_que_a_contagem_por_tipo_deixa_passar():
    # 8 + 8: cada tipo cabe no seu máximo de 15, o conjunto estoura o teto de 15
    # e a API recusaria o payload inteiro — por isso é erro, não aviso.
    extras = [
        _imagem(TipoDeAsset.IMAGEM_MARKETING, 1200, 628, semente=f"p{i}")
        for i in range(7)
    ] + [
        _imagem(TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 1200, 1200, semente=f"q{i}")
        for i in range(7)
    ]
    r = validacao.validar_lote(_lote_minimo_valido(extras=tuple(extras)), DISPLAY)
    teto = next(v for v in r.do_lote if v.codigo == "Q4.teto_combinado")
    assert teto.severidade == "erro"
    assert "16 acima do teto conjunto 15" in teto.detalhe
    assert not r.ok


def test_excesso_de_um_tipo_so_e_aviso_porque_cortar_e_de_graca():
    extras = tuple(
        _texto(TipoDeAsset.HEADLINE, f"Título número {i}") for i in range(6)
    )
    r = validacao.validar_lote(_lote_minimo_valido(extras=extras), DISPLAY)
    excesso = next(v for v in r.do_lote if v.codigo == "Q2.excedem")
    assert excesso.severidade == "aviso"
    assert excesso.classe is Classe.CORTAR_EXCEDENTE


def test_lote_vazio_lista_tudo_que_falta_de_uma_vez():
    r = validacao.validar_lote(LoteDeAssets(canal="DISPLAY"), DISPLAY)
    faltando = {v.alvo for v in r.do_lote if v.codigo == "Q1.faltam"}
    assert faltando == {
        "imagem_marketing", "imagem_marketing_quadrada",
        "headline", "headline_longa", "descricao", "nome_da_empresa",
    }


# ── texto ───────────────────────────────────────────────────────────────────


def test_texto_estourado_pede_reescrita_e_diz_de_quanto_passou():
    longa = _texto(TipoDeAsset.HEADLINE, "Saque do FGTS 2026 para quem tem direito hoje")
    achados = validacao.validar_asset(longa, DISPLAY.de(TipoDeAsset.HEADLINE))
    assert achados[0].codigo == "X1.caracteres"
    assert achados[0].classe is Classe.REESCREVER_TEXTO
    assert "limite 30" in achados[0].detalhe


def test_texto_vazio_e_violacao_e_nao_asset_aprovado():
    vazio = _texto(TipoDeAsset.HEADLINE, "   ")
    achados = validacao.validar_asset(vazio, DISPLAY.de(TipoDeAsset.HEADLINE))
    assert [v.codigo for v in achados] == ["X2.texto_vazio"]


# ── vídeo ───────────────────────────────────────────────────────────────────


def test_video_curto_demais_pede_regeracao_e_video_sem_duracao_pede_medida():
    spec = PMAX.de(TipoDeAsset.VIDEO)
    curto = Asset(
        tipo=TipoDeAsset.VIDEO, procedencia=_procedencia("curto"),
        conteudo_hash=hash_de_conteudo("curto"), mime="video/mp4",
        bytes_totais=4096, duracao_s=3.0,
    )
    assert [v.codigo for v in validacao.validar_asset(curto, spec)] == ["T1.duracao_curta"]

    sem_duracao = Asset(
        tipo=TipoDeAsset.VIDEO, procedencia=_procedencia("mudo"),
        conteudo_hash=hash_de_conteudo("mudo"), mime="video/mp4", bytes_totais=4096,
    )
    achados = validacao.validar_asset(sem_duracao, spec)
    assert achados[0].classe is Classe.MEDIR_ANTES


# ── agrupamento por remédio ─────────────────────────────────────────────────


def test_falta_de_descricao_curta_e_erro_do_conjunto_e_nao_de_cada_item():
    # Cinco descrições de 90 caracteres passam uma a uma e o asset group é
    # recusado com SHORT_DESCRIPTION_REQUIRED.
    longas = tuple(
        _texto(TipoDeAsset.DESCRICAO, f"Descrição {i} " + "x" * 70) for i in range(2)
    )
    lote = LoteDeAssets(canal="PERFORMANCE_MAX", assets=longas)
    r = validacao.validar_lote(lote, PMAX)
    curta = next(v for v in r.do_lote if v.codigo == "X3.falta_a_curta")
    assert curta.severidade == "erro" and curta.classe is Classe.REESCREVER_TEXTO

    com_curta = LoteDeAssets(canal="PERFORMANCE_MAX", assets=longas + (
        _texto(TipoDeAsset.DESCRICAO, "Veja o calendário oficial."),
    ))
    assert not [
        v for v in validacao.validar_lote(com_curta, PMAX).do_lote
        if v.codigo == "X3.falta_a_curta"
    ]


def test_a_cascata_consulta_por_classe_e_nao_por_codigo():
    lote = _lote_minimo_valido(extras=(
        _imagem(TipoDeAsset.IMAGEM_MARKETING, 1200, 1200, semente="fora de proporção"),
        _texto(TipoDeAsset.DESCRICAO, "x" * 200),
    ))
    r = validacao.validar_lote(lote, DISPLAY)
    assert r.por_classe(Classe.SANEAVEL_EM_CODIGO)
    assert r.por_classe(Classe.REESCREVER_TEXTO)
    assert not r.por_classe(Classe.ESTRUTURA)
