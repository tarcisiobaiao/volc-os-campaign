"""Testes do catálogo — identidade pelo conteúdo, procedência do primeiro.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/criativo -q

O que se prova aqui é a resposta à pergunta que só aparece meses depois: "qual
criativo funcionou?". Ela fica sem resposta quando o mesmo arquivo existe duas
vezes com métricas separadas, ou quando existe sem saber de que prompt saiu.
Por isso duplicidade devolve o existente em vez de levantar, e por isso
procedência é obrigatória na construção, não na gravação.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads.criativo.catalogo import Catalogo  # noqa: E402
from volc_ads.criativo.contrato import (  # noqa: E402
    Asset,
    Falha,
    Origem,
    Procedencia,
    TipoDeAsset,
    hash_de_conteudo,
)

QUANDO = datetime(2026, 8, 26, 12, 0, 0)


def _asset(semente: str, tipo=TipoDeAsset.IMAGEM_MARKETING, *, motor="motor-a", **extra) -> Asset:
    campos = {"mime": "image/png", "bytes_totais": 2048, "largura": 1200, "altura": 628}
    campos.update(extra)
    return Asset(
        tipo=tipo,
        procedencia=Procedencia(
            motor=motor, versao_do_motor="1", insumo=f"prompt de {semente}", quando=QUANDO
        ),
        conteudo_hash=hash_de_conteudo(semente),
        **campos,
    )


# ── procedência obrigatória ─────────────────────────────────────────────────


def test_procedencia_sem_motor_nao_existe():
    with pytest.raises(ValueError, match="quem gerou"):
        Procedencia(motor="  ", versao_do_motor="1", insumo="algo", quando=QUANDO)


def test_procedencia_sem_insumo_nao_existe():
    with pytest.raises(ValueError, match="a partir de quê"):
        Procedencia(motor="veo", versao_do_motor="3.1", insumo="", quando=QUANDO)


def test_medida_zero_e_recusada_porque_zero_nao_e_ausencia():
    with pytest.raises(ValueError, match="medida ausente é None"):
        _asset("largura zero", largura=0)


def test_dimensao_desconhecida_e_None_e_a_proporcao_tambem():
    cego = Asset(
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        procedencia=Procedencia(motor="m", versao_do_motor="1", insumo="p", quando=QUANDO),
        conteudo_hash=hash_de_conteudo("cego"),
    )
    assert cego.largura is None and cego.proporcao is None and cego.medido is False


# ── deduplicação ────────────────────────────────────────────────────────────


def test_mesmo_conteudo_devolve_o_existente_em_vez_de_erro():
    catalogo = Catalogo()
    primeiro = catalogo.registrar(_asset("banner do FGTS"))
    segundo = catalogo.registrar(_asset("banner do FGTS"))

    assert primeiro.novo is True
    assert segundo.novo is False
    assert segundo.asset is primeiro.asset
    assert len(catalogo) == 1


def test_a_procedencia_do_primeiro_registro_prevalece_e_a_divergencia_e_dita():
    catalogo = Catalogo()
    catalogo.registrar(_asset("mesmo arquivo", motor="motor-a"))
    reencontro = catalogo.registrar(_asset("mesmo arquivo", motor="motor-b"))

    # Sobrescrever apagaria o prompt que de fato produziu o arquivo — a única
    # coisa que permite repetir um acerto.
    assert reencontro.asset.procedencia.motor == "motor-a"
    assert "procedência divergente" in reencontro.observacao


def test_o_mesmo_arquivo_em_dois_papeis_nao_vira_duas_copias():
    catalogo = Catalogo()
    catalogo.registrar(_asset("quadrada", tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA))
    segundo = catalogo.registrar(_asset("quadrada", tipo=TipoDeAsset.LOGO_QUADRADO))

    assert len(catalogo) == 1
    assert catalogo.papeis(segundo.asset.identidade) == frozenset({
        TipoDeAsset.IMAGEM_MARKETING_QUADRADA, TipoDeAsset.LOGO_QUADRADO,
    })
    assert "papel logo_quadrado anotado" in segundo.observacao


def test_a_identidade_interna_sai_do_conteudo_e_nao_do_relogio():
    a = _asset("estável")
    b = _asset("estável", motor="outro-motor")
    assert a.identidade == b.identidade
    assert a.identidade.startswith("cri_")


# ── identidade interna x id do Google ───────────────────────────────────────


def test_o_id_externo_nao_mexe_na_identidade_interna():
    catalogo = Catalogo()
    registro = catalogo.registrar(_asset("para subir"))
    identidade = registro.asset.identidade

    carimbado = catalogo.carimbar_id_externo(identidade, "customers/8017851692/assets/123")
    assert carimbado.identidade == identidade
    assert carimbado.id_externo.endswith("/123")
    assert catalogo.por_identidade(identidade).id_externo == carimbado.id_externo


# ── intenções ───────────────────────────────────────────────────────────────


def test_associar_duas_vezes_e_no_op_e_nao_erro():
    catalogo = Catalogo()
    registro = catalogo.registrar(_asset("compartilhado"))
    assert catalogo.associar(registro.asset.identidade, "FGTS 2026") is True
    assert catalogo.associar(registro.asset.identidade, "FGTS 2026") is False
    assert catalogo.assets_de("FGTS 2026") == (registro.asset,)


def test_um_asset_serve_a_mais_de_uma_intencao():
    catalogo = Catalogo()
    registro = catalogo.registrar(_asset("logo da casa"))
    catalogo.associar(registro.asset.identidade, "FGTS 2026")
    catalogo.associar(registro.asset.identidade, "Maquininha")
    assert catalogo.intencoes_de(registro.asset.identidade) == ("FGTS 2026", "Maquininha")


def test_associar_asset_de_fora_do_catalogo_levanta():
    with pytest.raises(KeyError):
        Catalogo().associar("cri_inexistente", "FGTS 2026")


def test_intencao_vazia_nao_e_intencao():
    catalogo = Catalogo()
    registro = catalogo.registrar(_asset("órfão"))
    with pytest.raises(ValueError, match="intenção vazia"):
        catalogo.associar(registro.asset.identidade, "  ")


# ── variantes ───────────────────────────────────────────────────────────────


def test_a_variante_encontra_o_pai_e_nao_se_confunde_com_ele():
    catalogo = Catalogo()
    pai = catalogo.registrar(_asset("original")).asset
    recorte = catalogo.registrar(
        _asset("recorte 1.91", derivado_de=pai.identidade)
    ).asset

    assert catalogo.variantes(pai.identidade) == (recorte,)
    assert catalogo.variantes(recorte.identidade) == ()
    assert recorte.identidade != pai.identidade


# ── falhas dentro do lote ───────────────────────────────────────────────────


def test_a_falha_viaja_no_lote_sem_derrubar_os_assets():
    catalogo = Catalogo()
    catalogo.absorver(
        assets=(_asset("boa 1"), _asset("boa 2")),
        falhas=(Falha(referencia="ped-1#2", motivo="motor recusou o prompt",
                      codigo="MOTOR.recusado", permanente=True),),
        intencao="FGTS 2026",
    )
    lote = catalogo.lote("FGTS 2026", "DISPLAY")

    assert len(lote.assets) == 2
    assert len(lote.falhas) == 1
    assert lote.falhas[0].permanente is True
    assert "motor recusou" in lote.resumo()


def test_falha_de_uma_intencao_nao_aparece_na_outra():
    catalogo = Catalogo()
    catalogo.registrar_falha(Falha(referencia="x", motivo="falhou"), intencao="FGTS 2026")
    assert catalogo.falhas("Maquininha") == ()
    assert len(catalogo.falhas("FGTS 2026")) == 1
    assert len(catalogo.falhas()) == 1


def test_absorver_devolve_quem_era_novo_e_quem_ja_estava():
    catalogo = Catalogo()
    catalogo.registrar(_asset("repetida"))
    registros = catalogo.absorver(
        assets=(_asset("repetida"), _asset("inédita")), intencao="FGTS 2026"
    )
    assert [r.novo for r in registros] == [False, True]
    # Mesmo o reencontro entra na intenção: o asset serve à campanha de qualquer jeito.
    assert len(catalogo.assets_de("FGTS 2026")) == 2


def test_origem_declarada_sobrevive_ao_catalogo():
    catalogo = Catalogo()
    registro = catalogo.registrar(_asset("do acervo", origem=Origem.ESTOQUE))
    assert registro.asset.origem is Origem.ESTOQUE
