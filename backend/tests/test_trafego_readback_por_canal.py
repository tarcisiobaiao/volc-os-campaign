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
    # ⚠️ E A AUSÊNCIA DE VERDADE NÃO BLOQUEIA. Esta linha faltava, e é ela que
    # impede a "correção" preguiçosa do achado da campanha oca: meter
    # `AUSENCIA_PROVADA` em `ESTADOS_QUE_BLOQUEIAM` faria toda ausência
    # bloquear, e ausência conferida é conclusão neutra.
    r = vrel.resumo(v)
    assert r["estado"] == "ausencia_provada"
    assert r["bloqueia"] is False


def test_campanha_presente_sem_filhos_e_divergencia_estrutural_e_bloqueia():
    """⚠️ Campanha OCA não é conta limpa: ela existe e não veicula.

    Ausência da CAMPANHA é conclusão neutra. Ausência dos FILHOS de uma campanha
    que EXISTE é divergência estrutural — e neutralizar isso não era acadêmico:
    reproduzido em 06/09/2026 até o ledger, `/reconciliar` respondia 200 e
    gravava `achou=True` com o motivo "campanha encontrada na leitura da conta"
    para uma campanha com zero grupos e zero anúncios, e ainda vinculava o plano
    de mensuração a ela.

    O módulo tinha a informação para distinguir os dois casos e a jogava fora: o
    laço dos filhos só é alcançado quando a campanha-mãe foi RESOLVIDA.
    """
    v = rel.reler_na_conta(
        canal="DISPLAY",
        buscar=busca(campanhas=[_campanha()]),   # grupo e anúncio VAZIOS
        campaign_id="99", esperado=ESPERADO)

    assert v[0].estado is E.CONGRUENTE            # a mãe está lá, e está certa

    for filho in (x for x in v if x.objeto in ("grupo", "anuncio")):
        assert filho.estado is E.DIVERGENTE, filho.estado
        assert filho.prova_ausencia is False      # não afirma "não existe"
        assert filho.bloqueia is True
        assert filho.quantidade == 0
        assert "quantidade" in filho.campos_divergentes
        assert filho.esperado["quantidade_minima"] >= 1

    r = vrel.resumo(v)
    assert r["estado"] == "divergente"
    assert r["bloqueia"] is True
    # ⚠️ E bloquear NÃO é autorizar reenvio.
    assert r["reenvio_por_readback"] is False
    assert r["proximo_ato_tipo"] == vrel.ATO_CONFERIR_NA_CONTA


def test_pmax_criada_sem_asset_group_tambem_bloqueia():
    """A campanha oca de PMax é oca pelo objeto que PMax tem."""
    v = rel.reler_na_conta(
        canal="PERFORMANCE_MAX",
        buscar=busca(campanhas=[_campanha(canal="PERFORMANCE_MAX")]),
        campaign_id="99",
        esperado={"status": "PAUSED", "canal": "PERFORMANCE_MAX"})
    grupo = next(x for x in v if x.objeto == "asset_group")
    assert grupo.estado is E.DIVERGENTE
    assert vrel.resumo(v)["bloqueia"] is True


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


def test_nenhum_proximo_ato_e_um_ato_de_despacho():
    """CONTRAPROVA: em nenhum dos sete desfechos a saída é repetir o mutate.

    ⚠️ ESTE TESTE CASAVA A PROSA DO PRÓPRIO AUTOR, e por isso não guardava
    nada. Ele afirmava a propriedade com `assert "reenvi" not in ato.lower()` e
    `assert "tente de novo criando" not in ato.lower()` — duas substrings da
    redação vigente. Medido em 06/09/2026: trocar o texto de `AUSENCIA_PROVADA`
    para "conferi e não está: crie a campanha de novo pela rota de criação"
    mantinha os 20 testes do arquivo VERDES, e a orientação impressa ao operador
    passava a ser exatamente o ato que transforma uma resposta perdida em duas
    campanhas. As substrings proibidas tinham sido escolhidas para caber na
    prosa: o texto vigente já continha "criar de novo".

    Agora o ato é um valor de um conjunto FECHADO e é o VALOR que se compara. A
    prosa continua existindo, e continua livre para melhorar.
    """
    # (a) exaustivo: um oitavo estado sem ato mapeado estoura, não passa calado.
    assert set(vrel._ATO_POR_ESTADO) == set(E)

    # (b) o vocabulário é congelado AQUI. Alargá-lo para caber um ato de criação
    # passa a exigir editar esta linha, que é um ato visível; antes bastava
    # reescrever uma frase.
    assert set(vrel.ATOS_DO_READBACK) == {
        "nada_a_fazer", "conferir_na_conta", "reler", "consertar_a_leitura",
        "decisao_humana", "escalar_para_a_rota_de_criacao"}

    # (c) escalar não é executar, e os dois conjuntos não se tocam.
    assert set(vrel.ATOS_DO_READBACK).isdisjoint(vrel.ATOS_DE_DESPACHO)

    # (d) e nenhum estado — nem `AUSENCIA_PROVADA`, o caso tentador — sai com um
    # ato de despacho.
    for estado in E:
        ato = vrel.tipo_do_ato(estado)
        assert ato in vrel.ATOS_DO_READBACK, (estado, ato)
        assert ato not in vrel.ATOS_DE_DESPACHO, (estado, ato)

    assert vrel.resumo(())["reenvio_por_readback"] is False
    assert vrel.resumo(())["proximo_ato_tipo"] == vrel.ATO_CONSERTAR_A_LEITURA


def test_search_recem_criado_pela_casa_nao_bloqueia():
    """⚠️ Os filhos de Search nascem ENABLED — dentro de uma campanha PAUSED.

    `comum.op_adgroup` tem `status: str = "ENABLED"` como default e `search.py`
    chama sem passar status; `search.py` também liga o `AdGroupAd`. A própria
    docstring de `op_adgroup` explica: "Search nasce assim desde sempre — o
    grupo ligado dentro de uma campanha PAUSED, que não veicula".

    O read-back exigia PAUSED de TODO filho, contra uma premissa falsa sobre os
    builders desta casa. Medido em 06/09/2026: uma campanha Search correta,
    criada pelos próprios construtores e nunca ativada, saía `divergente` e
    `/reconciliar` respondia 409 — em 100% dos lançamentos do ÚNICO canal com
    criação autorizada. Os testes não pegavam porque só exercitavam DISPLAY,
    que de fato cria tudo pausado.
    """
    v = rel.reler_na_conta(
        canal="SEARCH",
        buscar=busca(campanhas=[_campanha(canal="SEARCH")],
                     grupos=[_grupo(status="ENABLED")],
                     anuncios=[_anuncio(status="ENABLED")]),
        campaign_id="99",
        # O MESMO `esperado` que a rota monta.
        esperado={"status": rel.NASCE_PAUSADO, "canal": rel.canonizar("SEARCH")})

    r = vrel.resumo(v)
    assert r["estado"] == "congruente", [x.estado for x in v]
    assert r["bloqueia"] is False
    for filho in (x for x in v if x.objeto in ("grupo", "anuncio")):
        assert filho.estado is E.CONGRUENTE
        assert filho.campos_divergentes == ()


def test_pausar_um_filho_nunca_e_divergencia_e_ligar_onde_nasce_pausado_sempre_e():
    """⚠️ A DIREÇÃO IMPORTA: o contrato protege contra VEICULAR, não contra pausar.

    A primeira versão da correção por canal comparava por igualdade exata, e com
    isso inverteu o defeito em vez de fechá-lo: com `alvo=ENABLED` para os
    filhos de Search, um grupo que alguém PAUSOU — ato humano legítimo, e o lado
    seguro — passava a divergir e /reconciliar respondia 409. A verificação
    focal deste fechamento mediu a inversão.

    O conjunto aceito é o estado de nascimento MAIS o pausado, em todo canal. O
    caso perigoso — ENABLED onde o builder cria PAUSED — continua divergindo.
    """
    def _conjunto(canal, status_do_grupo, status_do_anuncio):
        v = rel.reler_na_conta(
            canal=canal,
            buscar=busca(campanhas=[_campanha(canal=canal)],
                         grupos=[_grupo(status=status_do_grupo)],
                         anuncios=[_anuncio(status=status_do_anuncio)]),
            campaign_id="99",
            esperado={"status": rel.NASCE_PAUSADO, "canal": canal})
        return vrel.resumo(v)

    # Search: nasce ENABLED, e pausado depois também está certo.
    assert _conjunto("SEARCH", "ENABLED", "ENABLED")["bloqueia"] is False
    assert _conjunto("SEARCH", "PAUSED", "PAUSED")["bloqueia"] is False
    assert _conjunto("SEARCH", "PAUSED", "ENABLED")["bloqueia"] is False

    # Display: nasce PAUSED, e ENABLED é o que ameaça — em qualquer objeto.
    assert _conjunto("DISPLAY", "PAUSED", "PAUSED")["bloqueia"] is False
    assert _conjunto("DISPLAY", "PAUSED", "ENABLED")["bloqueia"] is True
    assert _conjunto("DISPLAY", "ENABLED", "PAUSED")["bloqueia"] is True


def test_campanha_nascida_enabled_continua_bloqueando():
    """⚠️ A PROVA DO NASCIMENTO NÃO AFROUXOU — ela é sobre a CAMPANHA.

    `comum.py` faz `camp.status = PAUSED` nos quatro canais, e é a campanha
    pausada que garante que nada veicule sem decisão humana. Um grupo ligado
    dentro dela não gasta; uma campanha ligada, sim.

    Este teste falharia se alguém "consertasse" o achado dos filhos tirando o
    `status` do `esperado` da campanha. E ativação posterior não vira ausência:
    ela é DIVERGÊNCIA, que é decisão humana.
    """
    v = rel.reler_na_conta(
        canal="SEARCH",
        buscar=busca(campanhas=[_campanha(canal="SEARCH", status="ENABLED")],
                     grupos=[_grupo(status="ENABLED")],
                     anuncios=[_anuncio(status="ENABLED")]),
        campaign_id="99",
        esperado={"status": rel.NASCE_PAUSADO, "canal": rel.canonizar("SEARCH")})

    campanha = next(x for x in v if x.objeto == vrel.CAMPANHA)
    assert campanha.estado is E.DIVERGENTE
    assert campanha.campos_divergentes == ("status",)
    assert campanha.prova_ausencia is False
    assert vrel.resumo(v)["bloqueia"] is True


def test_o_perfil_de_nascimento_bate_com_os_builders():
    """⚠️ IMPEDE A DERIVA QUE CRIOU O DEFEITO — lido por ÁRVORE SINTÁTICA.

    O backend não pode importar `volc_ads/campanha/*` (eles arrastam o SDK do
    Google), então `NASCE_COM_STATUS` é declarado aqui e a coerência com os
    construtores é COBRADA lendo o fonte deles. Falharia no dia em que um
    builder trocasse o estado de nascimento sem o perfil acompanhar — que é
    exatamente o buraco por onde este defeito entrou.
    """
    import ast
    import pathlib as _p

    raiz = _p.Path(__file__).resolve().parents[2] / "volc_ads" / "campanha"

    def _status_por_enum(arquivo: str) -> dict[str, set[str]]:
        """`{EnumDeStatus: {VALORES}}` atribuídos a `.status` naquele builder.

        ⚠️ Agrupado POR ENUM, e não numa bolsa única. A primeira versão deste
        helper juntava todo `X.status = <Attribute>` num conjunto só — e
        `search.py` também liga um `AdGroupCriterionStatusEnum.ENABLED`, que
        sozinho satisfazia a asserção do ANÚNCIO. A verificação focal provou:
        quatro derivas independentes dos builders passavam verdes.
        """
        arvore = ast.parse((raiz / arquivo).read_text(encoding="utf-8"))
        achados: dict[str, set[str]] = {}
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Assign):
                continue
            alvo = no.targets[0]
            if not (isinstance(alvo, ast.Attribute) and alvo.attr == "status"):
                continue
            valor = no.value
            if not (isinstance(valor, ast.Attribute)
                    and isinstance(valor.value, ast.Attribute)):
                continue
            achados.setdefault(valor.value.attr, set()).add(valor.attr)
        return achados

    # Os QUATRO builders, cada objeto contra o SEU enum.
    esperado_dos_builders = {
        # arquivo: {enum: (objeto do read-back, estado)}
        "search.py": {"AdGroupAdStatusEnum": ("SEARCH", vrel.ANUNCIO)},
        "display.py": {"AdGroupAdStatusEnum": ("DISPLAY", vrel.ANUNCIO)},
        "demand_gen.py": {"AdGroupAdStatusEnum": ("DEMAND_GEN", vrel.ANUNCIO),
                          "AdGroupStatusEnum": ("DEMAND_GEN", vrel.GRUPO)},
        "pmax.py": {"AssetGroupStatusEnum": ("PERFORMANCE_MAX", vrel.ASSET_GROUP)},
    }
    for arquivo, mapa in esperado_dos_builders.items():
        por_enum = _status_por_enum(arquivo)
        for enum, (canal, objeto) in mapa.items():
            estados = por_enum.get(enum, set())
            assert estados, f"{arquivo} não atribui {enum} a nenhum .status"
            assert estados == {rel.NASCE_COM_STATUS[canal][objeto]}, (
                arquivo, enum, estados, rel.NASCE_COM_STATUS[canal][objeto])

    # E o default de `op_adgroup` — a outra metade do caso de Search, e o que
    # Display/Demand Gen sobrescrevem explicitamente.
    comum = ast.parse((raiz / "comum.py").read_text(encoding="utf-8"))
    op = next(n for n in ast.walk(comum)
              if isinstance(n, ast.FunctionDef) and n.name == "op_adgroup")
    padrao = {a.arg: d for a, d in zip(op.args.kwonlyargs, op.args.kw_defaults)}
    assert padrao["status"].value == rel.NASCE_COM_STATUS["SEARCH"][vrel.GRUPO]

    # Display pede o grupo PAUSADO na chamada, e é isso que o perfil declara.
    display = ast.parse((raiz / "display.py").read_text(encoding="utf-8"))
    pedidos = {k.value.value
               for c in ast.walk(display) if isinstance(c, ast.Call)
               and getattr(c.func, "attr", "") == "op_adgroup"
               for k in c.keywords if k.arg == "status"}
    assert pedidos == {rel.NASCE_COM_STATUS["DISPLAY"][vrel.GRUPO]}, pedidos

    # Todo canal com objetos declarados tem perfil para cada filho.
    for canal, objetos in rel.OBJETOS_POR_CANAL.items():
        for objeto in objetos[1:]:
            assert objeto in rel.NASCE_COM_STATUS[canal], (canal, objeto)


def test_nem_o_readback_nem_o_veredito_importam_despachante():
    """Lista BRANCA de imports — a negra deixava passar o caminho prático.

    ⚠️ `test_o_modulo_de_releitura_nao_tem_caminho_de_escrita` proíbe uma lista
    de CHAMADAS por nome, e por isso um reenvio que importasse o despachante e o
    chamasse por outro nome passaria. Um despacho de verdade exige um cliente, e
    um cliente entra por import ou pelo `buscar` injetado — este teste fecha a
    primeira porta, e a segunda é do chamador.
    """
    import ast
    import inspect

    for modulo in (rel, vrel):
        arvore = ast.parse(inspect.getsource(modulo))
        importados: list[str] = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados += [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                importados.append(no.module or "")
                importados += [f"{no.module or ''}.{a.name}" for a in no.names]
        for nome in importados:
            assert not nome.startswith("volc_ads"), (modulo.__name__, nome)
            for proibido in ("executor", "subir", "gads", "sincronizador",
                             "client"):
                assert proibido not in nome, (modulo.__name__, nome)


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
