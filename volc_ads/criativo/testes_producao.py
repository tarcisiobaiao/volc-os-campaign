"""O caminho mínimo, ponta a ponta: receita → motor local → lote → ponte → entrega.

Rodar da raiz do projeto:
    backend/.venv/bin/python -m pytest volc_ads/criativo -q

Estes testes são a prova de que a camada de criativo tem um CAMINHO, e não só
peças. Até esta fatia, `validar_lote()` e `imagens_de_display()` existiam sem que
nada as chamasse em ordem a partir de um motor — a revisão adversarial de
27/08/2026 tinha apontado exatamente isso, e a resposta da época foi o caminho do
operador (`lote_de_pasta`), que exige quatro arquivos numa pasta e um humano.

Aqui não há pasta, não há humano e não há crédito: uma receita, um motor de
stdlib, e um `ImagensDisplay`/`ImagensDemandGen` com linhagem e recibo do outro
lado. E, no meio, a recusa que impede a mesma peça de ser apresentada como
produção.

## O que NÃO se prova aqui

Que a peça é boa. Ela não é: é um PNG de blocos. O que se prova é que a
geometria sai da régua, que a medida sai dos bytes, que a procedência sobrevive à
travessia e que a falha aparece com causa. Peça bonita é problema de motor pago.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads import criativo_ponte as ponte  # noqa: E402
from volc_ads.criativo import producao, requisitos  # noqa: E402
from volc_ads.criativo.adaptadores import medir_imagem  # noqa: E402
from volc_ads.criativo.adaptadores.falso import Defeito, MotorFalso  # noqa: E402
from volc_ads.criativo.adaptadores.png_local import MotorLocalDePNG  # noqa: E402
from volc_ads.criativo.contrato import (  # noqa: E402
    NaturezaDaProcedencia,
    Origem,
    TipoDeAsset,
)

QUANDO = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
INSUMO = "banner do FGTS de setembro"


def _produzir(receita_id="display-minimo", motor=None, **extra):
    campos = {"insumo": INSUMO, "quando": QUANDO}
    campos.update(extra)
    return producao.produzir(
        producao.receita_de(receita_id), motor or MotorLocalDePNG(), **campos
    )


# ── a receita é derivada da régua ───────────────────────────────────────────


def test_receita_desconhecida_e_erro_proprio_e_nao_KeyError_cru():
    with pytest.raises(producao.ReceitaDesconhecida) as capturado:
        producao.receita_de("nao-existe")
    assert "nao-existe" in str(capturado.value)


def test_os_papeis_do_display_saem_dos_obrigatorios_da_regua():
    exigencia = requisitos.exigencia_binaria_de("DISPLAY")
    papeis = producao.papeis_da_receita(producao.receita_de("display-minimo"), exigencia)
    assert set(papeis) == {
        TipoDeAsset.IMAGEM_MARKETING,
        TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
    }
    # As logos são `min 0` no Display — recomendadas, não exigidas. Produzi-las
    # aqui seria inventar uma obrigação que a régua não faz.
    assert TipoDeAsset.LOGO_QUADRADO not in papeis


def test_o_demand_gen_so_e_montavel_porque_a_derivacao_le_o_teto_combinado():
    """O caso que uma derivação ingênua erraria.

    Nenhuma imagem de marketing é individualmente obrigatória em Demand Gen
    (`min 0` em todas as quatro). O que o canal exige é ao menos UMA no conjunto
    "imagem base (paisagem ou quadrada)". Uma derivação que olhasse só
    `exigencia.obrigatorios` produziria o logo e mais nada, e o veredito
    devolveria `Q5.teto_combinado_falta` — correto, e inútil, porque o buraco
    estava na encomenda.
    """
    exigencia = requisitos.exigencia_binaria_de("DEMAND_GEN")
    papeis = producao.papeis_da_receita(
        producao.receita_de("demand-gen-minimo"), exigencia
    )
    assert TipoDeAsset.LOGO_QUADRADO in papeis           # o obrigatório individual
    base = {TipoDeAsset.IMAGEM_MARKETING, TipoDeAsset.IMAGEM_MARKETING_QUADRADA}
    assert base & set(papeis)                            # o obrigatório do conjunto


# ── o asset carrega tudo o que precisa carregar ─────────────────────────────


@pytest.mark.parametrize("receita_id", ["display-minimo", "demand-gen-minimo"])
def test_o_lote_produzido_passa_na_propria_regua_do_canal(receita_id):
    p = _produzir(receita_id)
    from volc_ads.criativo import validacao

    veredito = validacao.validar_lote(p.lote, p.exigencia)
    assert veredito.ok, veredito.resumo()
    assert not veredito.reprovados
    assert len(p.lote.assets) == len(p.pedidos)
    assert not p.lote.falhas


def test_cada_asset_carrega_hash_mime_dimensao_e_bytes_medidos_dos_proprios_bytes():
    p = _produzir()
    assert p.lote.assets

    for asset in p.lote.assets:
        dados = p.conteudo[asset.identidade]
        medida = medir_imagem.medir(dados)

        assert asset.conteudo_hash.startswith("sha256:")
        assert asset.mime == medida.mime == "image/png"
        assert asset.largura == medida.largura
        assert asset.altura == medida.altura
        assert asset.bytes_totais == medida.bytes_totais == len(dados)
        assert asset.medido


def test_a_procedencia_diz_motor_versao_insumo_pedido_instante_e_natureza():
    p = _produzir()
    for asset in p.lote.assets:
        proc = asset.procedencia
        assert proc.motor == "png-local"
        assert proc.versao_do_motor
        assert proc.insumo == INSUMO
        assert proc.pedido.startswith("png-local-")
        assert proc.quando == QUANDO
        assert proc.natureza is NaturezaDaProcedencia.LOCAL
        assert proc.publicavel is False
        # `Origem` e `natureza` respondem perguntas diferentes: de que CLASSE é
        # o arquivo, e se ele pode ser PUBLICADO. Colapsá-las é o defeito.
        assert asset.origem is Origem.GERADO
        # `0.0` seria a afirmação de que a imagem saiu de graça.
        assert proc.custo_usd is None


def test_duas_producoes_iguais_dao_as_mesmas_identidades_e_os_mesmos_hashes():
    a, b = _produzir(), _produzir()
    assert [x.identidade for x in a.lote.assets] == [x.identidade for x in b.lote.assets]
    assert [x.conteudo_hash for x in a.lote.assets] == [
        x.conteudo_hash for x in b.lote.assets
    ]
    assert a.conteudo == b.conteudo


def test_o_catalogo_amarra_os_assets_a_intencao_da_receita():
    p = _produzir(intencao="fgts-setembro")
    assert len(p.catalogo) == len(p.lote.assets)
    for asset in p.lote.assets:
        assert "fgts-setembro" in p.catalogo.intencoes_de(asset.identidade)


# ── a travessia da ponte ────────────────────────────────────────────────────


def test_em_ensaio_a_entrega_sai_com_linhagem_integra():
    p = _produzir()
    entrega = ponte.imagens_de_display(
        p.lote, p.conteudo, destino=ponte.Destino.ENSAIO
    )

    assert entrega.ok
    assert entrega.destino is ponte.Destino.ENSAIO
    assert len(entrega.linhagem) == len(p.lote.assets)

    por_identidade = {a.identidade: a for a in p.lote.assets}
    for linha in entrega.linhagem:
        asset = por_identidade[linha.identidade]
        # Projetar é copiar, nunca completar: cada campo da linhagem tem de ser
        # o campo do asset, não um valor plausível.
        assert linha.conteudo_hash == asset.conteudo_hash
        assert (linha.mime, linha.largura, linha.altura) == (
            asset.mime, asset.largura, asset.altura
        )
        assert linha.motor == "png-local"
        assert linha.insumo == INSUMO
        assert linha.insumo_hash == asset.procedencia.insumo_hash
        assert linha.quando == QUANDO.isoformat()
        assert linha.custo_usd is None
        assert linha.confirmada


def test_em_demand_gen_o_recibo_tipado_sai_e_aponta_para_o_mesmo_arquivo():
    p = _produzir("demand-gen-minimo")
    entrega = ponte.imagens_de_demand_gen(
        p.lote, p.conteudo, destino=ponte.Destino.ENSAIO
    )
    assert entrega.ok, entrega.resumo()

    por_identidade = {a.identidade: a for a in p.lote.assets}
    vistos = 0
    for papel in entrega.imagens.PAPEIS:
        for item in getattr(entrega.imagens, papel):
            recibo = item.recibo_aprovacao
            assert recibo is not None, papel
            asset = por_identidade[recibo.catalogo_id]
            assert recibo.conteudo_hash == asset.conteudo_hash
            assert (recibo.mime, recibo.largura, recibo.altura) == (
                asset.mime, asset.largura, asset.altura
            )
            assert recibo.bytes_totais == len(p.conteudo[asset.identidade])
            assert recibo.canal == "DEMAND_GEN"
            assert recibo.aprovacao_id
            assert recibo.medidor_id
            assert recibo.linhagem.conteudo_hash == asset.conteudo_hash
            assert recibo.linhagem.identidade == asset.identidade
            vistos += 1
    assert vistos == len(p.lote.assets)


# ── a recusa que a fatia existe para garantir ───────────────────────────────


@pytest.mark.parametrize(
    "receita_id,funcao",
    [
        ("display-minimo", ponte.imagens_de_display),
        ("demand-gen-minimo", ponte.imagens_de_demand_gen),
    ],
)
def test_peca_local_nao_atravessa_a_ponte_com_destino_de_producao(receita_id, funcao):
    p = _produzir(receita_id)
    entrega = funcao(p.lote, p.conteudo)   # o padrão É produção

    assert entrega.imagens is None
    assert entrega.ok is False
    # ⚠️ O par que a tela precisa distinguir: o lote é BOM e mesmo assim não sai
    # payload. Derivar "reprovado" de `entrega.ok` faria o operador procurar um
    # defeito de geometria que não existe.
    assert entrega.veredito.ok is True
    assert entrega.linhagem == ()

    motivos = " ".join(entrega.recusas)
    assert "local" in motivos
    assert "Destino.ENSAIO" in motivos
    for asset in p.lote.assets:
        assert asset.identidade in motivos


def test_a_entrega_declara_a_natureza_de_todo_asset_do_lote():
    p = _produzir()
    entrega = ponte.imagens_de_display(
        p.lote, p.conteudo, destino=ponte.Destino.ENSAIO
    )
    assert entrega.naturezas == {
        a.identidade: "local" for a in p.lote.assets
    }
    assert "local" in entrega.resumo()


def test_ausencia_de_declaracao_vira_aviso_e_nao_recusa():
    """`NAO_DECLARADA` não é `FIXTURE`, e os remédios são diferentes.

    Uma pede que alguém declare; a outra pede que alguém não publique. Tratar as
    duas igual quebraria o único caminho que hoje monta payload de verdade — o do
    operador, que lê uma pasta e não tem motor para declarar nada.
    """
    p = _produzir(motor=MotorFalso())
    assert p.natureza is NaturezaDaProcedencia.NAO_DECLARADA

    entrega = ponte.imagens_de_display(p.lote, p.conteudo)
    assert entrega.ok is True                      # passou
    assert not any("não pode ser apresentada" in m for m in entrega.recusas)
    assert entrega.avisos                          # e foi dito
    assert all("não declarada" in m for m in entrega.avisos)


# ── falha tem causa, e a causa tem código ───────────────────────────────────


def test_motor_fora_do_ar_devolve_lote_com_falhas_nomeadas_e_nao_excecao():
    """O lote vazio silencioso é o pior desfecho possível: `assets == ()` é
    indistinguível de "o canal não pede nada". Aqui ele vem com uma falha por
    papel, com código e com `permanente=False`."""
    p = _produzir(motor=MotorLocalDePNG(indisponivel=True))

    assert p.lote.assets == ()
    assert len(p.lote.falhas) == len(
        producao.papeis_da_receita(p.receita, p.exigencia)
    )
    for falha in p.lote.falhas:
        assert falha.codigo == "F5.motor_indisponivel"
        assert falha.permanente is False           # retentar depois pode dar certo
        assert falha.tipo is not None


def test_pendencia_so_vira_falha_quando_o_orcamento_acaba_e_diz_quantas_foram():
    p = _produzir(motor=MotorFalso(pendencias=99), tentativas_de_recebimento=2)

    assert p.lote.assets == ()
    for falha in p.lote.falhas:
        assert falha.codigo == "F7.geracao_pendente"
        # Pendência não é defeito do insumo: retentar mais tarde é exatamente o
        # remédio, e por isso ela não pode nascer permanente.
        assert falha.permanente is False
        assert "2 tentativa" in falha.motivo


def test_pendencia_que_termina_dentro_do_orcamento_nao_vira_falha():
    p = _produzir(motor=MotorFalso(pendencias=1), tentativas_de_recebimento=3)
    assert p.lote.assets
    assert not p.lote.falhas


def test_item_recusado_pelo_motor_vira_falha_permanente_sem_derrubar_o_lote():
    p = producao.produzir(
        producao.Receita(
            id="dois-marketing",
            canal="DISPLAY",
            papeis=(TipoDeAsset.IMAGEM_MARKETING,),
            quantidade_por_papel=2,
        ),
        MotorFalso(defeitos={0: Defeito.RECUSADO}),
        insumo=INSUMO,
        quando=QUANDO,
    )
    # Um recusado e um bom: o lote sobrevive à perda e a registra.
    assert len(p.lote.assets) == 1
    assert len(p.lote.falhas) == 1
    assert p.lote.falhas[0].permanente is True


def test_produzir_sem_insumo_e_erro_de_programador_e_nao_lote_vazio():
    with pytest.raises(ValueError, match="insumo"):
        _produzir(insumo="   ")


def test_motor_que_declara_natureza_numa_string_solta_vale_como_nao_declarada():
    """Parece resposta e não é comparável — pior que não responder."""

    class MotorMentiroso(MotorFalso):
        natureza = "producao"          # str, não `NaturezaDaProcedencia`

    p = _produzir(motor=MotorMentiroso())
    assert p.natureza is NaturezaDaProcedencia.NAO_DECLARADA
    assert p.publicavel is False
