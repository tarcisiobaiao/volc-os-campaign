"""T14 — reler na conta por canal, e as sete respostas que `achou` não sabia dar.

## O defeito que este arquivo cobre

O read-back pós-criação era um `Optional[bool]` chamado `achou`. `achou is True`
significava apenas "existe uma campanha que casou o critério" — e uma campanha
`ENABLED` onde o contrato exige `PAUSED` devolvia exatamente isso: `True`. O item
era carimbado, o recibo fechava como sucesso, e a divergência (que é o fato caro)
não existia em lugar nenhum da resposta.

`achou is False` colapsava outros quatro fatos: "conferi e não está", "não
terminei de conferir", "quebrei conferindo" e "aqui não existe isso para
conferir". A única saída óbvia para `False` é tentar de novo — que é o ato errado
em três dos quatro.

⚠️ Nenhuma linha deste arquivo toca rede: `buscar` é injetado.
"""
from __future__ import annotations

from types import SimpleNamespace as N

import pytest

from app.trafego import releitura_por_canal as rel
from app.trafego import veredito_de_releitura as vrel
from app.trafego.veredito_de_releitura import EstadoDaReleitura as E


# ── dublês ──────────────────────────────────────────────────────────────────


def _campanha(kid="99", status="PAUSED", canal="DISPLAY",
              estrategia="MAXIMIZE_CONVERSIONS", nome="VOLC-CANARY-abc x"):
    return N(campaign=N(id=kid, name=nome, status=N(name=status),
                        advertising_channel_type=N(name=canal),
                        bidding_strategy_type=N(name=estrategia)))


def _grupo(gid="1", status="PAUSED"):
    return N(campaign=N(id="99"), ad_group=N(id=gid, status=N(name=status)))


def _anuncio(aid="1", status="PAUSED", urls=("https://x/",)):
    return N(campaign=N(id="99"),
             ad_group_ad=N(status=N(name=status),
                           ad=N(id=aid, final_urls=list(urls))))


def _asset_group(gid="7", status="PAUSED", urls=("https://x/",)):
    return N(campaign=N(id="99"),
             asset_group=N(id=gid, status=N(name=status),
                           final_urls=list(urls), final_mobile_urls=[]))


def busca(campanhas=(), grupos=(), anuncios=(), asset_groups=(), erro_em=()):
    def _buscar(gaql: str):
        for marca in erro_em:
            if marca in gaql:
                raise RuntimeError(f"a API recusou: {marca}")
        if "FROM campaign" in gaql:
            return list(campanhas)
        if "FROM ad_group_ad" in gaql:
            return list(anuncios)
        if "FROM ad_group" in gaql:
            return list(grupos)
        if "FROM asset_group" in gaql:
            return list(asset_groups)
        return []
    return _buscar


ESPERADO = {"status": "PAUSED", "canal": "DISPLAY"}


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — os sete estados existem, e são exatamente sete
# ═══════════════════════════════════════════════════════════════════════════


def test_os_sete_estados_existem_e_nao_ha_um_oitavo():
    assert set(vrel.ESTADOS) == {
        "congruente", "divergente", "ausencia_provada", "leitura_parcial",
        "falha", "nao_suportado", "ambiguo"}
    assert len(vrel.ESTADOS) == 7


def test_so_ausencia_provada_prova_ausencia():
    """⚠️ A propriedade mais importante do módulo.

    Nem `LEITURA_PARCIAL`, nem `FALHA`, nem `NAO_SUPORTADO` provam que não
    existe. Quem decide criar de novo consulta ESTA propriedade, e nunca o
    tamanho de uma lista.
    """
    def _v(estado, **extra):
        return vrel.VereditoDaReleitura(
            canal="DISPLAY", objeto=vrel.CAMPANHA, estado=estado, **extra)

    assert _v(E.AUSENCIA_PROVADA).prova_ausencia is True
    assert _v(E.LEITURA_PARCIAL, causa="teto", teto_atingido="linhas"
              ).prova_ausencia is False
    assert _v(E.FALHA, causa="quebrou").prova_ausencia is False
    assert _v(E.NAO_SUPORTADO).prova_ausencia is False
    assert _v(E.AMBIGUO, causa="duas").prova_ausencia is False
    assert _v(E.CONGRUENTE).prova_ausencia is False


def test_so_congruente_e_sucesso_e_divergente_bloqueia():
    """CONTRAPROVA: divergência NUNCA vira sucesso."""
    divergente = vrel.VereditoDaReleitura(
        canal="DISPLAY", objeto=vrel.CAMPANHA, estado=E.DIVERGENTE,
        campos_divergentes=("status",))
    assert divergente.sucesso is False
    assert divergente.bloqueia is True

    congruente = vrel.VereditoDaReleitura(
        canal="DISPLAY", objeto=vrel.CAMPANHA, estado=E.CONGRUENTE)
    assert congruente.sucesso is True
    assert congruente.bloqueia is False


def test_divergencia_sem_campo_nomeado_e_recusada_por_construcao():
    """Um bloqueio que não diz o que discorda é infalsificável."""
    with pytest.raises(ValueError, match="campo divergente"):
        vrel.VereditoDaReleitura(canal="DISPLAY", objeto=vrel.CAMPANHA,
                                 estado=E.DIVERGENTE)


def test_estado_sem_conclusao_precisa_dizer_por_que():
    for estado in (E.LEITURA_PARCIAL, E.FALHA, E.AMBIGUO):
        with pytest.raises(ValueError, match="sem causa"):
            vrel.VereditoDaReleitura(canal="DISPLAY", objeto=vrel.CAMPANHA,
                                     estado=estado)


def test_o_teto_nomeado_precisa_ser_pagina_ou_linha():
    """⚠️ Página e linha são cortes DIFERENTES, e a evidência tem de dizer qual."""
    with pytest.raises(ValueError, match="teto"):
        vrel.VereditoDaReleitura(canal="DISPLAY", objeto=vrel.CAMPANHA,
                                 estado=E.LEITURA_PARCIAL, causa="cortou",
                                 teto_atingido="paginas_ou_linhas")


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — os objetos são os DO CANAL
# ═══════════════════════════════════════════════════════════════════════════


def test_pmax_tem_asset_group_e_nao_tem_anuncio():
    """PMax é o único canal sem AdGroup e sem Ad — e isso é declarado."""
    assert rel.objetos_de("PERFORMANCE_MAX") == ("campanha", "asset_group")
    assert rel.objetos_de("PMAX") == ("campanha", "asset_group")
    for canal in ("SEARCH", "DISPLAY", "DEMAND_GEN"):
        assert rel.objetos_de(canal) == ("campanha", "grupo", "anuncio")


def test_pmax_nunca_consulta_ad_group_ad():
    """CONTRAPROVA: em PMax, `FROM ad_group_ad` devolve VAZIO sempre.

    E vazio lido como ausência é o defeito que a autoridade de URL do canário já
    corrigiu do outro lado. Aqui a resposta é ler o asset group.
    """
    consultas: list = []

    def _buscar(gaql: str):
        consultas.append(gaql)
        if "FROM campaign" in gaql:
            return [_campanha(canal="PERFORMANCE_MAX")]
        if "FROM asset_group" in gaql:
            return [_asset_group()]
        return []

    rel.reler_na_conta(canal="PERFORMANCE_MAX", buscar=_buscar,
                       campaign_id="99",
                       esperado={"status": "PAUSED",
                                 "canal": "PERFORMANCE_MAX"})
    tudo = " ".join(consultas)
    assert "FROM asset_group" in tudo
    assert "ad_group_ad" not in tudo
    assert "FROM ad_group " not in tudo


def test_canal_desconhecido_e_nao_suportado_e_nao_ausencia():
    v = rel.reler_na_conta(canal="TIKTOK", buscar=busca(), campaign_id="99")
    assert len(v) == 1
    assert v[0].estado is E.NAO_SUPORTADO
    assert v[0].prova_ausencia is False


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — os desfechos, um a um
# ═══════════════════════════════════════════════════════════════════════════


def test_tudo_pausado_e_congruente():
    v = rel.reler_na_conta(
        canal="DISPLAY",
        buscar=busca(campanhas=[_campanha()], grupos=[_grupo()],
                     anuncios=[_anuncio()]),
        campaign_id="99", esperado=ESPERADO)
    assert [x.estado for x in v] == [E.CONGRUENTE] * 3
    r = vrel.resumo(v)
    assert r["estado"] == "congruente"
    assert r["bloqueia"] is False


def test_anuncio_enabled_e_divergente_e_bloqueia_o_conjunto():
    """⚠️ Nascer PAUSED é contrato. `ENABLED` aqui significa que algo pode gastar."""
    v = rel.reler_na_conta(
        canal="DISPLAY",
        buscar=busca(campanhas=[_campanha()], grupos=[_grupo()],
                     anuncios=[_anuncio(status="ENABLED")]),
        campaign_id="99", esperado=ESPERADO)
    anuncio = next(x for x in v if x.objeto == "anuncio")
    assert anuncio.estado is E.DIVERGENTE
    assert anuncio.campos_divergentes == ("status",)
    r = vrel.resumo(v)
    assert r["estado"] == "divergente"
    assert r["bloqueia"] is True
    assert r["reenvio_por_readback"] is False


def test_campanha_com_estrategia_trocada_e_divergente():
    v = rel.reler_na_conta(
        canal="DISPLAY",
        buscar=busca(campanhas=[_campanha(estrategia="MANUAL_CPC")],
                     grupos=[_grupo()], anuncios=[_anuncio()]),
        campaign_id="99",
        esperado={"status": "PAUSED", "canal": "DISPLAY",
                  "estrategia_lance": "MAXIMIZE_CONVERSIONS"})
    campanha = v[0]
    assert campanha.estado is E.DIVERGENTE
    assert "estrategia_lance" in campanha.campos_divergentes


def test_sem_linhas_e_ausencia_provada_e_os_filhos_nao_afirmam_nada():
    v = rel.reler_na_conta(canal="DISPLAY", buscar=busca(), campaign_id="99",
                           esperado=ESPERADO)
    assert v[0].estado is E.AUSENCIA_PROVADA
    assert v[0].quantidade == 0
    # ⚠️ Sem id de campanha não há por onde consultar os filhos. Isso é
    # NAO_SUPORTADO para ESTA leitura, e não ausência.
    assert [x.estado for x in v[1:]] == [E.NAO_SUPORTADO, E.NAO_SUPORTADO]


def test_duas_campanhas_e_ambiguo_e_nunca_escolhe_uma():
    v = rel.reler_na_conta(
        canal="DISPLAY",
        buscar=busca(campanhas=[_campanha("1"), _campanha("2")]),
        marca="VOLC-CANARY-abc", esperado=ESPERADO)
    assert v[0].estado is E.AMBIGUO
    assert v[0].quantidade == 2
    assert v[0].id_externo is None, "ambíguo NÃO elege um dos candidatos"
    assert vrel.resumo(v)["bloqueia"] is True


def test_falha_de_leitura_nao_vira_ausencia_e_nao_apaga_os_outros():
    """"Não consegui ler o anúncio" e "não existe anúncio" são fatos diferentes."""
    v = rel.reler_na_conta(
        canal="DISPLAY",
        buscar=busca(campanhas=[_campanha()], grupos=[_grupo()],
                     erro_em=("FROM ad_group_ad",)),
        campaign_id="99", esperado=ESPERADO)
    anuncio = next(x for x in v if x.objeto == "anuncio")
    assert anuncio.estado is E.FALHA
    assert anuncio.prova_ausencia is False
    # A campanha e o grupo continuam lidos: uma falha não apaga o que já veio.
    assert v[0].estado is E.CONGRUENTE
    assert next(x for x in v if x.objeto == "grupo").estado is E.CONGRUENTE


def test_leitura_no_teto_e_parcial_e_nomeia_o_teto_de_LINHAS():
    """⚠️ Truncamento NÃO prova ausência — e o teto que cortou é de LINHAS."""
    muitas = [_campanha(str(i)) for i in range(rel.TETO_DE_LINHAS_DA_RELEITURA + 2)]
    v = rel.reler_na_conta(canal="DISPLAY", buscar=busca(campanhas=muitas),
                           marca="VOLC-CANARY-abc", esperado=ESPERADO)
    assert v[0].estado is E.LEITURA_PARCIAL
    assert v[0].teto_atingido == vrel.TETO_DE_LINHAS
    assert v[0].prova_ausencia is False
    assert vrel.resumo(v)["bloqueia"] is True


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — read-back NUNCA reenvia criação
# ═══════════════════════════════════════════════════════════════════════════


def test_nenhum_proximo_ato_manda_reenviar():
    """CONTRAPROVA: em nenhum dos sete desfechos a saída é repetir o mutate.

    Nem em `AUSENCIA_PROVADA`, que é o caso tentador: "conferi e não está" NÃO
    autoriza criar de novo — quem cria é a rota de criação, com autorização
    humana e ledger próprios. Uma releitura que dispara criação transforma uma
    resposta perdida em duas campanhas.
    """
    for estado in E:
        ato = vrel._proximo_ato(estado)
        assert "reenvi" not in ato.lower(), (estado, ato)
        assert "tente de novo criando" not in ato.lower()
    assert vrel.resumo(())["reenvio_por_readback"] is False


def test_o_modulo_de_releitura_nao_tem_caminho_de_escrita():
    """Somente leitura: toda consulta é SELECT e nenhuma monta operação."""
    import ast
    import inspect

    # ⚠️ Por ÁRVORE SINTÁTICA, e não por `in` no texto: a docstring do módulo
    # fala de `mutate` para explicar QUANDO o read-back roda, e um teste que
    # casa string proibiria a explicação junto com o comportamento.
    arvore = ast.parse(inspect.getsource(rel))
    chamadas = {
        no.func.attr if isinstance(no.func, ast.Attribute)
        else getattr(no.func, "id", "")
        for no in ast.walk(arvore) if isinstance(no, ast.Call)
    }
    for proibida in ("mutar", "mutate", "destravar", "MutateOperation",
                     "validar_mutacoes", "subir", "preparar"):
        assert proibida not in chamadas, (
            f"o read-back chama {proibida}: ele nunca reenvia criação")
    for literal in (no.value for no in ast.walk(arvore)
                    if isinstance(no, ast.Constant) and isinstance(no.value, str)):
        texto = literal.strip().upper()
        if texto.startswith(("SELECT", "INSERT", "UPDATE", "DELETE")):
            assert texto.startswith("SELECT"), (
                f"consulta que não é leitura no read-back: {literal[:60]!r}")
    for consulta in (rel.GAQL_CAMPANHA, rel.GAQL_GRUPO, rel.GAQL_ANUNCIO,
                     rel.GAQL_ASSET_GROUP):
        assert consulta.strip().startswith("SELECT")


def test_conjunto_vazio_e_falha_e_nunca_congruente():
    """"Não li nada" nunca é "está tudo certo"."""
    assert vrel.compor(()) is E.FALHA
    assert vrel.resumo(())["estado"] == "falha"


def test_a_ordem_de_gravidade_poe_divergente_acima_de_tudo():
    def _v(estado, **e):
        return vrel.VereditoDaReleitura(canal="DISPLAY", objeto=vrel.CAMPANHA,
                                        estado=estado, **e)

    assert vrel.compor((
        _v(E.CONGRUENTE),
        _v(E.AUSENCIA_PROVADA),
        _v(E.DIVERGENTE, campos_divergentes=("status",)),
    )) is E.DIVERGENTE
    assert vrel.compor((_v(E.CONGRUENTE), _v(E.NAO_SUPORTADO))) is E.NAO_SUPORTADO
