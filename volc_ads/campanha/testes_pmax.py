"""Testes do contrato de Performance Max.

Rodar da raiz do projeto:
    backend/.venv/bin/python -m pytest volc_ads/campanha/testes_pmax.py -q

**Nenhum teste aqui fala com o Google.** O cliente é montado sem credencial
(`_cliente_sem_rede`, o mesmo shim de `testes_search.py`/`testes_display.py`) e
injetado por monkeypatch. O que se prova é o PAYLOAD, as RECUSAS e o PORTÃO —
que é onde moram os defeitos que este arquivo persegue.

⚠️ Os protos são REAIS. `sondar_proto_v25()` instancia e serializa os tipos
gerados de v25 e nenhum teste substitui isso por dublê: "ausência de prova com
os protos v25 reais" foi exatamente o que reprovou o candidato de Demand Gen na
revisão anterior, e o mesmo erro em PMax custaria a mesma rodada.

Cinco grupos:

  CONTRATO   PMax não é Search: sem ad group, sem anúncio, sem keyword
             positiva, com lista fechada de dois lances.

  MENSURAÇÃO o portão que a missão pede. Ele é INDEPENDENTE de o canal estar
             fora do executor, e há um teste que o prova com o canal fingido
             habilitado — senão, no dia em que alguém ligar o construtor, o
             portão sumiria junto e ninguém perceberia.

  ASSET      recibo tipado por papel, papel do canal certo, peso, e a
             cobertura julgada por `observabilidade_pmax`.

  GRAFO      a ordem das operações, os ids temporários, os três PAUSED e o
             nível onde BUSINESS_NAME/LOGO moram conforme brand guidelines.

  FRONTEIRA  o canal continua fora do executor, e o plano diz isso com código
             próprio em vez de fingir que o canal não existe.
"""

from __future__ import annotations

import copy
import dataclasses
import enum
import hashlib
import pathlib
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

from volc_ads import subir as motor  # noqa: E402
from volc_ads.campanha import perfil, plano, pmax  # noqa: E402
from volc_ads.campanha.brief import (  # noqa: E402
    AcaoDeConversao,
    AssetRemotoAprovado,
    Brief,
    ConfiguracaoDemandGen,
    ConfiguracaoPMax,
    Copy,
    ImagemParaSubir,
    ImagensDisplay,
    ImagensPMax,
    Linhagem,
    SinalDeAudiencia,
    SubIntencao,
    _emitir_recibo_asset_aprovado,
    _emitir_recibo_de_mensuracao,
)

CID = "5478096539"
MCC = "6016739364"


# ── cliente sem rede ────────────────────────────────────────────────────────


class _Enums:
    """`client.enums` sem credencial — ver `testes_search._Enums`."""

    def __getattr__(self, nome: str):
        wrapper = getattr(import_module("google.ads.googleads.v25.enums"), nome)
        for attr in dir(wrapper):
            valor = getattr(wrapper, attr)
            if isinstance(valor, enum.EnumMeta):
                return valor
        raise AttributeError(nome)


def _cliente_sem_rede():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    c.enums = _Enums()
    return c


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch):
    """Nenhum teste deste arquivo carrega ~/google-ads.yaml."""
    monkeypatch.setattr(pmax, "cliente", lambda _login: _cliente_sem_rede())


# ── PNG real, medível ───────────────────────────────────────────────────────


def _png(largura: int, altura: int, *, semente: bytes) -> bytes:
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return (struct.pack(">I", len(dados)) + corpo
                + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    linha = (semente * 3 * largura)[: 3 * largura]
    cru = b"".join(b"\x00" + linha for _ in range(altura))
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", ihdr)
            + bloco(b"IDAT", zlib.compress(cru)) + bloco(b"IEND", b""))


def _medir(dados: bytes):
    largura, altura = struct.unpack(">II", dados[16:24])
    return "image/png", largura, altura, len(dados)


def _imagem(nome: str, papel: str, largura: int, altura: int, *,
            canal: str = pmax.CANAL,
            resource_name: str | None = None) -> ImagemParaSubir | AssetRemotoAprovado:
    """Um asset com recibo emitido pela MESMA fábrica que a ponte usa."""
    dados = _png(largura, altura, semente=nome.encode()[:1] or b"z")
    hash_ = "sha256:" + hashlib.sha256(dados).hexdigest()
    linhagem = Linhagem(
        nome=nome, papel=papel, identidade=f"cat-{nome}", conteudo_hash=hash_,
        mime="image/png", largura=largura, altura=altura,
        bytes_totais=len(dados), id_externo=resource_name,
        exigencia_fonte="matriz-api/performance-max.md §4",
        exigencia_provisoria=False,
    )
    recibo = _emitir_recibo_asset_aprovado(
        catalogo_id=f"cat-{nome}", canal=canal, nome=nome, papel=papel,
        conteudo_hash=hash_, mime="image/png", largura=largura, altura=altura,
        bytes_totais=len(dados), resource_name=resource_name,
        exigencia_fonte="matriz-api/performance-max.md §4",
        exigencia_provisoria=False, medidor_id="testes_pmax._medir",
        reconferidor=_medir, linhagem=linhagem,
    )
    if resource_name is not None:
        return AssetRemotoAprovado(resource_name=resource_name, dados=dados,
                                   recibo=recibo)
    return ImagemParaSubir(nome=nome, dados=dados, linhagem=linhagem,
                           mime="image/png", largura=largura, altura=altura,
                           recibo_aprovacao=recibo)


# ── mensuração ──────────────────────────────────────────────────────────────


def _acao(**troca) -> AcaoDeConversao:
    base = dict(
        resource_name=f"customers/{CID}/conversionActions/1",
        nome="Lead do formulário", tipo="WEBPAGE",
        categoria="SUBMIT_LEAD_FORM", status="ENABLED",
        primaria_para_meta=True, inclui_em_conversoes=True,
        carrega_valor=True, conversoes_ultimos_30d=12.0,
    )
    base.update(troca)
    return AcaoDeConversao(**base)


def _mensuracao(*acoes, quando=None, cid=CID, mcc=MCC):
    return _emitir_recibo_de_mensuracao(
        customer_id=cid, login_customer_id=mcc,
        lido_em=(quando or datetime.now(timezone.utc)).isoformat(),
        consulta=pmax.CONSULTA_DE_MENSURACAO,
        coletor="testes_pmax", acoes=acoes or (_acao(),),
    )


# ── briefs ──────────────────────────────────────────────────────────────────


def _imagens(**troca) -> ImagensPMax:
    base = dict(
        marketing=[_imagem("mkt", "marketing", 1200, 628)],
        marketing_quadrada=[_imagem("sq", "marketing_quadrada", 1200, 1200)],
        logo=[_imagem("logo", "logo", 1200, 1200)],
    )
    base.update(troca)
    return ImagensPMax(**base)


def _configuracao(**troca) -> ConfiguracaoPMax:
    base = dict(
        brand_guidelines_enabled=False,
        mensuracao=_mensuracao(),
        sinais=(SinalDeAudiencia("search_theme", "saque anual fgts"),),
        negativas=("emprestimo consignado",),
    )
    base.update(troca)
    return ConfiguracaoPMax(**base)


def _copy(**troca) -> Copy:
    base = dict(
        headlines=["Regras do Saque Anual", "Quem Tem Direito em 2026",
                   "Tabela Oficial por Faixa"],
        long_headlines=["Prazos, limites e quem tem direito ao saque anual"],
        # ⚠️ A primeira cabe em 60. A regra "ao menos uma DESCRIPTION com 60
        # caracteres ou menos" é da API (`SHORT_DESCRIPTION_REQUIRED`) e quem a
        # confere é `evaluate_asset_group_coverage`.
        descriptions=["Prazos e limites, com fonte citada.",
                      "Portal informativo com a tabela legal por faixa etaria."],
        business_name="Credito Up",
    )
    base.update(troca)
    return Copy(**base)


def _brief(**troca) -> Brief:
    base = dict(
        nicho="Saque Anual", slug="saque-anual",
        url_final="https://creditoup.com.br/r/saque-anual/",
        # ⚠️ VAZIO de propósito, e não é descuido. Keyword em PMax só pode ser
        # NEGATIVA; declarar positivas aqui faria TODO teste deste arquivo
        # morrer na mesma recusa, e nenhum deles provaria o que se propõe.
        keywords=[],
        copy=_copy(),
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        imagens_pmax=_imagens(),
        pmax=_configuracao(),
    )
    base.update(troca)
    return Brief(**base)


def _erros(resultado) -> str:
    return "\n".join(f"{a.campo}: {a.motivo}" for a in resultado.erros)


def _codigos(p) -> set[str]:
    return {b.codigo for b in p.bloqueios}


def _por_tipo(ops, tipo: str):
    return [o for o in ops if o._pb.WhichOneof("operation") == tipo]


# ═══════════════════════════════════════════════════════════════════════════
# CONTRATO — PMax não é Search
# ═══════════════════════════════════════════════════════════════════════════


def test_pmax_nao_reaproveita_contrato_de_search() -> None:
    """O grafo não tem NENHUM degrau de Search, e isso é estrutural.

    Não basta o builder ser um arquivo separado: se ele emitisse `ad_group_
    operation` ou `ad_group_ad_operation`, a API recusaria o mutate inteiro
    (consultar ad group numa campanha PMax não retorna nada). Este teste mede o
    payload, não a intenção.
    """
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)

    for proibido in ("ad_group_operation", "ad_group_ad_operation",
                     "ad_group_criterion_operation", "ad_operation"):
        assert not _por_tipo(ops, proibido), (
            f"PMax emitiu {proibido} — o canal NÃO TEM ad group nem anúncio "
            f"(matriz §1). Este payload seria recusado inteiro pela API")

    assert _por_tipo(ops, "asset_group_operation"), "sem asset group não há PMax"
    assert _por_tipo(ops, "asset_group_asset_operation")

    # E a campanha é de PMax de fato, não de Search com outro nome.
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    assert camp.advertising_channel_type.name == "PERFORMANCE_MAX"
    # `network_settings` NÃO é emitido: PMax não tem controle de rede (§13).
    assert not camp._pb.HasField("network_settings"), (
        "PMax declarou network_settings — o canal serve em Search, Display, "
        "YouTube, Discover, Gmail e Maps sem opt-out; emitir o campo declara "
        "um controle que não existe")


def test_keyword_positiva_e_recusada_e_a_negativa_vira_criterio() -> None:
    """Em PMax keyword só existe como negativa (§8). As duas metades importam."""
    b = _brief(keywords=["saque anual fgts"])
    ops, r = pmax.construir(CID, b, login_customer_id=MCC)
    assert not r.ok
    assert not ops
    achado = next(a for a in r.erros if a.campo == "keywords")
    assert achado.codigo == plano.CAMPO_NAO_OPERADO, (
        "keyword positiva em PMax é campo NÃO OPERADO, não texto reprovado — "
        "e o código precisa dizer isso, porque a tela decide pelo código")

    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    negativas = [
        o.campaign_criterion_operation.create
        for o in _por_tipo(ops, "campaign_criterion_operation")
        if o.campaign_criterion_operation.create._pb.WhichOneof("criterion") == "keyword"
    ]
    assert len(negativas) == 1
    assert negativas[0].negative is True
    assert negativas[0].keyword.text == "emprestimo consignado"


@pytest.mark.parametrize("lance", ["MANUAL_CPC"])
def test_lance_fora_da_lista_fechada_e_recusado(lance: str) -> None:
    """§7: as duas suportadas são MaxConv e MaxConvValue. Só elas."""
    _, r = pmax.construir(CID, _brief(estrategia_lance=lance),
                          login_customer_id=MCC)
    achado = next(a for a in r.erros if a.campo == "estrategia_lance")
    assert achado.codigo == plano.LANCE_NAO_PERMITIDO


def test_maximize_conversion_value_ocupa_o_ramo_certo_do_oneof() -> None:
    """O segundo lance existe de verdade, e leva o target_roas dentro."""
    b = _brief(estrategia_lance="MAXIMIZE_CONVERSION_VALUE", target_roas=4.0)
    ops, r = pmax.construir(CID, b, login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversion_value"
    assert camp.maximize_conversion_value.target_roas == pytest.approx(4.0)


def test_tcpa_ausente_nao_vira_zero() -> None:
    """`ausente ≠ zero`, no campo onde a diferença é dinheiro.

    Escrever `target_cpa_micros = 0` diria que alguém escolheu zero de meta. O
    oneof precisa apenas ser SELECIONADO, e é o que `SetInParent` faz.
    """
    ops, r = pmax.construir(CID, _brief(tcpa=None), login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"
    # `target_cpa_micros` é escalar em proto3 e NÃO tem presença — `HasField`
    # levanta nele. Por isso a prova é sobre os BYTES: uma mensagem em que
    # ninguém escreveu nada serializa vazia, e `target_cpa_micros = 0` também
    # serializaria vazia. O que separa os dois é o teste seguinte, com meta.
    assert camp.maximize_conversions._pb.SerializeToString() == b"", (
        "o ramo de lance carrega valor onde ninguém escolheu meta")

    com_meta, r2 = pmax.construir(CID, _brief(tcpa=25.0), login_customer_id=MCC)
    assert r2.ok, _erros(r2)
    camp2 = _por_tipo(com_meta, "campaign_operation")[0].campaign_operation.create
    assert camp2.maximize_conversions.target_cpa_micros == 25_000_000


@pytest.mark.parametrize("campo,valor,codigo", [
    ("ai_max", True, plano.CAMPO_NAO_OPERADO),
    ("sub_intencoes", [SubIntencao(nome="x", keywords=["a"])],
     plano.CAMPO_NAO_OPERADO),
    ("imagens_display", ImagensDisplay(marketing=["customers/1/assets/2"]),
     plano.CAMPO_NAO_OPERADO),
    ("demand_gen", ConfiguracaoDemandGen(
        upgraded_targeting=True, controles_de_canal=None, audiencias=None,
        intencoes=None, exclusoes_de_audiencia=None), plano.CAMPO_NAO_OPERADO),
    ("videos", ["customers/5478096539/assets/9"], plano.CAMPO_NAO_OPERADO),
])
def test_campos_de_outros_canais_falham_fechado(campo, valor, codigo) -> None:
    """Descarte em silêncio é o defeito. Cada campo alheio RECUSA, com código."""
    _, r = pmax.construir(CID, _brief(**{campo: valor}), login_customer_id=MCC)
    assert not r.ok, f"{campo} passou em silêncio"
    assert codigo in {a.codigo for a in r.erros}


def test_extensoes_de_search_nao_migram_por_analogia() -> None:
    b = _brief(copy=_copy(callouts=["Fonte oficial", "Sem cadastro"]))
    _, r = pmax.construir(CID, b, login_customer_id=MCC)
    achado = next(a for a in r.erros if a.campo == "copy.extensoes")
    assert achado.codigo == plano.CAMPO_NAO_OPERADO


def test_brief_de_pmax_nao_e_obrigado_a_declarar_keyword_positiva() -> None:
    """A isenção do contrato de entrada existe e é do PMax.

    Sem ela o `Brief` exigiria `keywords` para poder ser construído e o builder
    as recusaria na linha seguinte: a entrada exigiria o que o canal proíbe.
    """
    b = Brief(nicho="n", slug="s", url_final="https://x.com/",
              keywords=[], copy=_copy(),
              estrategia_lance="MAXIMIZE_CONVERSIONS",
              imagens_pmax=_imagens(), pmax=_configuracao())
    assert b.pmax is not None

    with pytest.raises(ValueError, match="brief sem keyword"):
        Brief(nicho="n", slug="s", url_final="https://x.com/", keywords=[],
              copy=_copy(), estrategia_lance="MAXIMIZE_CONVERSIONS")


# ═══════════════════════════════════════════════════════════════════════════
# MENSURAÇÃO — o portão
# ═══════════════════════════════════════════════════════════════════════════


def test_mensuracao_ausente_bloqueia_criacao_e_prova() -> None:
    _, r = pmax.construir(CID, _brief(pmax=_configuracao(mensuracao=None)),
                          login_customer_id=MCC)
    achado = next(a for a in r.erros if a.campo == "pmax.mensuracao")
    assert achado.codigo == plano.MENSURACAO_INADEQUADA


def test_mensuracao_inadequada_bloqueia_criacao_e_prova() -> None:
    """Nenhuma ação válida ⇒ PMax não pode nascer. As três condições, uma a uma."""
    for troca in (
        {"status": "PAUSED"},
        {"primaria_para_meta": False},
        {"inclui_em_conversoes": False},
    ):
        cfg = _configuracao(mensuracao=_mensuracao(_acao(**troca)))
        p = pmax.planejar(CID, _brief(pmax=cfg), login_customer_id=MCC)
        assert plano.MENSURACAO_INADEQUADA in _codigos(p), (
            f"ação com {troca} passou pelo portão — as três condições são da "
            f"API e valem juntas")
        assert p.prontidao.pode_criar is False
        assert p.prontidao.monta is False


def test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠️ O portão de mensuração é INDEPENDENTE de o canal estar no executor.

    Hoje PMax está bloqueado por DOIS motivos empilhados: não há construtor no
    perfil, e a mensuração pode ser inadequada. Só o segundo é regra de
    negócio. Um teste que medisse o bloqueio final não distinguiria os dois — e
    no dia em que alguém habilitasse o canal, o portão sumiria junto e a suíte
    continuaria verde.

    Aqui a prontidão é forçada a "tudo liberado" e o bloqueio de mensuração
    tem de continuar de pé por si.
    """
    monkeypatch.setattr(
        pmax, "_prontidao",
        lambda cfg, r, ops: plano.Prontidao(
            monta=True, pode_provar=True, pode_criar=True))

    cfg = _configuracao(mensuracao=_mensuracao(_acao(status="PAUSED")))
    p = pmax.planejar(CID, _brief(pmax=cfg), login_customer_id=MCC)

    assert p.prontidao.pode_criar is True, "o teste não forçou a prontidão"
    assert plano.MENSURACAO_INADEQUADA in _codigos(p), (
        "com o canal fingido habilitado, o ÚNICO bloqueio que sobra é o de "
        "mensuração — e ele desapareceu. O portão que a missão pede não "
        "existe por si: ele estava sendo carregado pelo canal desabilitado")


def test_recibo_de_mensuracao_autoatestado_nao_e_leitura() -> None:
    """Um objeto que declara a própria procedência não prova leitura nenhuma.

    Mesmo defeito que a revisão de Demand Gen encontrou na linhagem, e a mesma
    correção: a fábrica é privada e a impressão é conferida.
    """
    autentico = _mensuracao()
    assert autentico.integro is True

    # ⚠️ `dataclasses.replace` não serve: a classe é `init=False` de propósito,
    # e é exatamente essa recusa que impede alguém de "reconstruir" um recibo.
    # Alterar o campo depois é o caminho que sobra para um falsário — e é ele
    # que a impressão precisa pegar.
    forjado = copy.copy(autentico)
    object.__setattr__(forjado, "coletor", "eu mesmo")
    assert forjado.integro is False

    p = pmax.planejar(CID, _brief(pmax=_configuracao(mensuracao=forjado)),
                      login_customer_id=MCC)
    assert plano.MENSURACAO_INADEQUADA in _codigos(p)
    assert any("não foi emitido" in b.causa for b in p.bloqueios)


@pytest.mark.parametrize("troca,esperado", [
    ({"cid": "9999999999"}, "conta"),
    ({"mcc": "9999999999"}, "MCC"),
])
def test_mensuracao_de_outra_conta_ou_mcc_e_recusada(troca, esperado) -> None:
    """Conversão não atravessa conta, e o recibo carrega de onde foi lido."""
    cfg = _configuracao(mensuracao=_mensuracao(**troca))
    _, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert any(a.campo == "pmax.mensuracao" and esperado in a.motivo
               for a in r.erros), _erros(r)


def test_maximize_conversion_value_exige_acao_que_carregue_valor() -> None:
    """Otimizar VALOR sobre conversões sem valor é otimizar por zero."""
    cfg = _configuracao(mensuracao=_mensuracao(_acao(carrega_valor=False)))
    b = _brief(estrategia_lance="MAXIMIZE_CONVERSION_VALUE", target_roas=4.0,
               pmax=cfg)
    _, r = pmax.construir(CID, b, login_customer_id=MCC)
    assert any("nenhuma das ações válidas tem `value_settings`" in a.motivo
               for a in r.erros), _erros(r)

    # E a MESMA conta, com a MESMA ação, passa em MaximizeConversions.
    _, r2 = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r2.ok, _erros(r2)


def test_volume_nao_medido_e_volume_zero_sao_avisos_diferentes() -> None:
    """`ausente ≠ zero`, no campo onde confundir custa uma campanha inteira."""
    nao_medido = _configuracao(
        mensuracao=_mensuracao(_acao(conversoes_ultimos_30d=None)))
    medido_zero = _configuracao(
        mensuracao=_mensuracao(_acao(conversoes_ultimos_30d=0.0)))

    _, r1 = pmax.construir(CID, _brief(pmax=nao_medido), login_customer_id=MCC)
    _, r2 = pmax.construir(CID, _brief(pmax=medido_zero), login_customer_id=MCC)

    assert r1.ok and r2.ok, "nenhum dos dois é bloqueio"
    assert any("ninguém mediu o volume" in a.motivo for a in r1.achados)
    assert any("volume medido é zero" in a.motivo for a in r2.achados)
    assert not any("ninguém mediu o volume" in a.motivo for a in r2.achados), (
        "zero medido virou 'ninguém mediu' — os dois estados colapsaram")


def test_recibo_velho_avisa_e_nao_bloqueia() -> None:
    """Uma leitura antiga continua sendo uma leitura."""
    ontem = datetime.now(timezone.utc) - (pmax.IDADE_MAXIMA_DA_MENSURACAO
                                          + timedelta(hours=1))
    cfg = _configuracao(mensuracao=_mensuracao(quando=ontem))
    _, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    assert any("Releia antes de autorizar gasto" in a.motivo for a in r.achados)


def test_ler_mensuracao_nao_tem_caminho_para_mutar() -> None:
    """A leitura é leitura. Nenhum import daqui alcança `mutar()`."""
    import ast
    import inspect

    # Por ÁRVORE SINTÁTICA, não por texto: o docstring deste módulo cita
    # `mutar()` para explicar por que não o usa, e uma busca textual acusaria
    # justamente a documentação da garantia.
    arvore = ast.parse(inspect.getsource(pmax))
    importados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            importados.update(a.asname or a.name for a in no.names)
        elif isinstance(no, ast.Import):
            importados.update((a.asname or a.name).split(".")[0] for a in no.names)
    assert "mutar" not in importados, (
        "`campanha/pmax.py` importou `mutar` — o único caminho de mutação real "
        "do engine não pode ser alcançável a partir deste módulo")

    chamados = {
        no.func.id if isinstance(no.func, ast.Name) else getattr(no.func, "attr", "")
        for no in ast.walk(arvore) if isinstance(no, ast.Call)
    }
    assert "mutar" not in chamados
    assert "destravar" not in chamados, (
        "este módulo tentou abrir a trava de escrita de `gads/modo.py`")
    assert "validate_only" not in pmax.CONSULTA_DE_MENSURACAO
    assert pmax.CONSULTA_DE_MENSURACAO.lstrip().upper().startswith("SELECT")


# ═══════════════════════════════════════════════════════════════════════════
# ASSET — recibo, papel, peso e a cobertura reusada
# ═══════════════════════════════════════════════════════════════════════════


def test_asset_sem_recibo_falha_fechado() -> None:
    """PMax NÃO aceita resource name solto, diferente de Display."""
    im = _imagens(marketing=[f"customers/{CID}/assets/111"])
    p = pmax.planejar(CID, _brief(imagens_pmax=im), login_customer_id=MCC)
    assert plano.ASSET_SEM_RECIBO in _codigos(p)
    assert p.prontidao.monta is False


def test_recibo_de_outro_canal_nao_vale_em_pmax() -> None:
    """Relabeling de recibo: aprovado para Demand Gen NÃO serve aqui.

    Os dois canais têm tabelas de papel e geometria diferentes. Aceitar o
    recibo do outro seria a mesma classe de bypass que a revisão anterior
    encontrou — só que na fronteira do catálogo em vez da do selo.
    """
    im = _imagens(marketing=[_imagem("mkt", "marketing", 1200, 628,
                                     canal="DEMAND_GEN")])
    p = pmax.planejar(CID, _brief(imagens_pmax=im), login_customer_id=MCC)
    assert plano.ASSET_RECIBO_DIVERGENTE in _codigos(p)
    assert any("não PERFORMANCE_MAX" in b.causa for b in p.bloqueios)


def test_asset_adulterado_morre_por_hash_antes_do_cliente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bytes trocados depois do recibo não chegam a construir cliente."""
    monkeypatch.setattr(
        pmax, "cliente",
        lambda _l: pytest.fail("cliente foi construído com asset adulterado"))

    item = _imagem("mkt", "marketing", 1200, 628)
    adulterado = dataclasses.replace(item, dados=_png(1200, 628, semente=b"Z"))
    p = pmax.planejar(CID, _brief(imagens_pmax=_imagens(marketing=[adulterado])),
                      login_customer_id=MCC)
    assert plano.ASSET_RECIBO_DIVERGENTE in _codigos(p)


def test_imagens_pmax_ausente_e_bloqueio_e_nao_plano_vazio() -> None:
    p = pmax.planejar(CID, _brief(imagens_pmax=None), login_customer_id=MCC)
    assert plano.ASSET_OBRIGATORIO_AUSENTE in _codigos(p)
    assert p.unidades == ()


def test_asset_acima_do_peso_da_api_e_recusado_localmente() -> None:
    """5120 KB é teto da API; recusar antes é mais barato que o mutate."""
    teto = pmax._LIM["pmax_asset"]["peso_maximo_bytes"]
    grande = _imagem("grande", "marketing", 1400, 1400)
    assert len(grande.dados) < teto, "a imagem de teste já nasceu grande demais"

    class _LimiteBaixo(dict):
        pass

    original = pmax._LIM["pmax_asset"]["peso_maximo_bytes"]
    pmax._LIM["pmax_asset"]["peso_maximo_bytes"] = 10
    try:
        p = pmax.planejar(CID, _brief(imagens_pmax=_imagens(marketing=[grande])),
                          login_customer_id=MCC)
        assert plano.ASSET_ACIMA_DO_TETO in _codigos(p)
    finally:
        pmax._LIM["pmax_asset"]["peso_maximo_bytes"] = original


def test_a_cobertura_do_plano_usa_a_regua_do_observador() -> None:
    """A tabela de mínimos NÃO é reescrita aqui: ela vem de observabilidade_pmax.

    Sem MARKETING_IMAGE o plano tem de bloquear, e o bloqueio precisa citar
    `PMAX_FIELD_REQUIREMENTS` — que é o que prova que a régua do portão e a
    régua do observador são a mesma.
    """
    p = pmax.planejar(CID, _brief(imagens_pmax=_imagens(marketing=[])),
                      login_customer_id=MCC)
    lacunas = [b for b in p.bloqueios if b.campo == "asset_group.cobertura"]
    assert lacunas, "o plano passou sem MARKETING_IMAGE obrigatória"
    assert any("MARKETING_IMAGE" in b.causa for b in lacunas)
    assert all("PMAX_FIELD_REQUIREMENTS" in b.causa for b in lacunas)


def test_descricao_curta_obrigatoria_e_conferida_pelo_texto_real() -> None:
    """`SHORT_DESCRIPTION_REQUIRED`: ao menos uma DESCRIPTION com ≤60.

    A regra só é verificável se o TEXTO do asset chegar ao avaliador. É por isso
    que `plano.Asset.identidade` carrega o texto quando a origem é `texto` — e
    este teste é o que mede se ele chegou.
    """
    longas = ["Portal informativo com prazos, limites e a tabela legal completa.",
              "Regras do saque anual explicadas por faixa etaria e por ano-base."]
    assert all(len(d) > 60 for d in longas)

    p = pmax.planejar(CID, _brief(copy=_copy(descriptions=longas)),
                      login_customer_id=MCC)
    assert any("60 characters" in b.causa for b in p.bloqueios), (
        "nenhuma descrição cabe em 60 e o plano não reclamou — o texto do "
        "asset não chegou ao avaliador de cobertura")


def test_asset_remoto_aprovado_e_referenciado_sem_renascer() -> None:
    """Asset que já existe na conta é REFERENCIADO, não recriado."""
    rn = f"customers/{CID}/assets/987654321"
    remoto = _imagem("mkt", "marketing", 1200, 628, resource_name=rn)
    ops, r = pmax.construir(
        CID, _brief(imagens_pmax=_imagens(marketing=[remoto])),
        login_customer_id=MCC)
    assert r.ok, _erros(r)

    criados = [o.asset_operation.create for o in _por_tipo(ops, "asset_operation")]
    assert rn not in {c.resource_name for c in criados}, (
        "o asset remoto foi recriado — a API responderia com asset duplicado")
    vinculos = [o.asset_group_asset_operation.create
                for o in _por_tipo(ops, "asset_group_asset_operation")]
    assert rn in {v.asset for v in vinculos}


def test_resource_name_de_outra_conta_e_recusado() -> None:
    remoto = _imagem("mkt", "marketing", 1200, 628,
                     resource_name="customers/1111111111/assets/2")
    p = pmax.planejar(CID, _brief(imagens_pmax=_imagens(marketing=[remoto])),
                      login_customer_id=MCC)
    assert _codigos(p) & {plano.ASSET_RECIBO_DIVERGENTE,
                          plano.RESOURCE_NAME_INVALIDO}


def test_video_entra_por_resource_name_e_nao_por_bytes() -> None:
    rn = f"customers/{CID}/assets/555"
    ops, r = pmax.construir(
        CID, _brief(imagens_pmax=_imagens(videos_youtube=[rn])),
        login_customer_id=MCC)
    assert r.ok, _erros(r)
    vinculos = [o.asset_group_asset_operation.create
                for o in _por_tipo(ops, "asset_group_asset_operation")]
    assert any(v.asset == rn and v.field_type.name == "YOUTUBE_VIDEO"
               for v in vinculos)


# ═══════════════════════════════════════════════════════════════════════════
# GRAFO — ordem, ids temporários, PAUSED, e o nível da marca
# ═══════════════════════════════════════════════════════════════════════════


def test_grafo_atomico_na_ordem_que_a_api_resolve() -> None:
    """Asset antes do vínculo; asset group antes do vínculo. Sempre.

    A API resolve id temporário só DEPOIS de ele ser definido. Inserir o
    vínculo antes faria a API recusar o mutate inteiro com um erro sobre o
    VÍNCULO — e o defeito estaria na ordem da lista.
    """
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    tipos = [o._pb.WhichOneof("operation") for o in ops]

    assert tipos[0] == "campaign_budget_operation"
    assert tipos[1] == "campaign_operation"

    ultimo_asset = max(i for i, t in enumerate(tipos) if t == "asset_operation")
    grupo = tipos.index("asset_group_operation")
    primeiro_vinculo = tipos.index("asset_group_asset_operation")
    assert ultimo_asset < grupo < primeiro_vinculo, (
        f"ordem inválida: último asset={ultimo_asset}, grupo={grupo}, "
        f"primeiro vínculo={primeiro_vinculo}")

    sinal = tipos.index("asset_group_signal_operation")
    assert sinal > grupo, "sinal antes do asset group que ele referencia"


def test_a_campanha_e_o_asset_group_nascem_pausados() -> None:
    """Despausar é ato explícito, nunca efeito colateral de criar."""
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    grupo = _por_tipo(ops, "asset_group_operation")[0].asset_group_operation.create
    assert camp.status.name == "PAUSED"
    assert grupo.status.name == "PAUSED"


def test_o_orcamento_declara_periodo_e_nao_e_compartilhado() -> None:
    """§3: em PMax `period` é obrigatório e o budget NÃO pode ser compartilhado."""
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    b = _por_tipo(ops, "campaign_budget_operation")[0].campaign_budget_operation.create
    assert b.period.name == "DAILY"
    assert b.explicitly_shared is False


def test_a_faixa_de_id_do_asset_group_e_propria() -> None:
    """Faixa própria, e o teto é o da API (100 asset groups por campanha)."""
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    grupo = _por_tipo(ops, "asset_group_operation")[0].asset_group_operation.create
    assert grupo.resource_name == f"customers/{CID}/assetGroups/-300"

    from volc_ads.campanha import comum
    with pytest.raises(ValueError, match="fora da faixa reservada"):
        comum.temp_asset_group(CID, comum.T_ASSET_GROUP_MAX)


def test_brand_guidelines_decide_o_NIVEL_de_business_name_e_logo() -> None:
    """§5: ligado ⇒ CampaignAsset; desligado ⇒ AssetGroupAsset.

    Errar o nível não é detalhe: com ele ligado, deixar no asset group responde
    `BRAND_ASSETS_NOT_LINKED_AT_CAMPAIGN_LEVEL`; com ele desligado, deixar na
    campanha responde `REQUIRED_BUSINESS_NAME_ASSET_NOT_LINKED`.
    """
    def _niveis(brand: bool):
        ops, r = pmax.construir(
            CID, _brief(pmax=_configuracao(brand_guidelines_enabled=brand)),
            login_customer_id=MCC)
        assert r.ok, _erros(r)
        campanha = {o.campaign_asset_operation.create.field_type.name
                    for o in _por_tipo(ops, "campaign_asset_operation")}
        grupo = {o.asset_group_asset_operation.create.field_type.name
                 for o in _por_tipo(ops, "asset_group_asset_operation")}
        camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
        return campanha, grupo, camp.brand_guidelines_enabled

    campanha_on, grupo_on, flag_on = _niveis(True)
    assert flag_on is True
    assert {"BUSINESS_NAME", "LOGO"} <= campanha_on
    assert not ({"BUSINESS_NAME", "LOGO"} & grupo_on)

    campanha_off, grupo_off, flag_off = _niveis(False)
    assert flag_off is False
    assert campanha_off == set()
    assert {"BUSINESS_NAME", "LOGO"} <= grupo_off


def test_brand_guidelines_sem_escolha_e_recusa_e_nao_default() -> None:
    """Campo IMUTÁVEL sem update normal que desfaça. Não há default seguro."""
    cfg = _configuracao(brand_guidelines_enabled=None)
    _, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    achado = next(a for a in r.erros
                  if a.campo == "pmax.brand_guidelines_enabled")
    assert achado.codigo == plano.CONFIGURACAO_AUSENTE


def test_sinal_vazio_declarado_e_diferente_de_sinal_nao_escolhido() -> None:
    """`()` é "não dar dica"; `None` é ninguém ter escolhido."""
    ops, r = pmax.construir(CID, _brief(pmax=_configuracao(sinais=())),
                            login_customer_id=MCC)
    assert r.ok, _erros(r)
    assert not _por_tipo(ops, "asset_group_signal_operation")

    _, r2 = pmax.construir(CID, _brief(pmax=_configuracao(sinais=None)),
                           login_customer_id=MCC)
    achado = next(a for a in r2.erros if a.campo == "pmax.sinais")
    assert achado.codigo == plano.CONFIGURACAO_AUSENTE


def test_os_dois_tipos_de_sinal_ocupam_ramos_diferentes_do_oneof() -> None:
    cfg = _configuracao(sinais=(
        SinalDeAudiencia("search_theme", "saque fgts"),
        SinalDeAudiencia("audience", f"customers/{CID}/audiences/42"),
    ))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    ramos = [o.asset_group_signal_operation.create._pb.WhichOneof("signal")
             for o in _por_tipo(ops, "asset_group_signal_operation")]
    assert ramos == ["search_theme", "audience"]


def test_sinal_de_audiencia_fora_da_forma_canonica_e_recusado() -> None:
    with pytest.raises(ValueError, match="forma canônica"):
        SinalDeAudiencia("audience", "42")
    with pytest.raises(ValueError, match="inválido"):
        SinalDeAudiencia("local_services_id", "abc")


# ═══════════════════════════════════════════════════════════════════════════
# PROTOS v25 REAIS
# ═══════════════════════════════════════════════════════════════════════════


def test_sdk_v25_real_instancia_e_serializa_o_grafo_pmax() -> None:
    """Prova offline, sem rede e sem credencial, com os protos DE VERDADE.

    Esta é a prova que substitui o `validate_only` que este canal não pode
    rodar. Ela não é um dublê: os tipos vêm do namespace gerado de v25 e cada
    um é serializado.
    """
    suporte = pmax.sondar_proto_v25()
    assert suporte.disponivel, suporte.motivo
    esperados = {
        "Campaign", "CampaignBudget", "CampaignCriterion", "CampaignAsset",
        "AssetGroup", "AssetGroupAsset", "AssetGroupSignal.search_theme",
        "AssetGroupSignal.audience", "Asset.text", "Asset.image",
        "MutateOperation.campaign", "MutateOperation.asset_group",
        "MutateOperation.asset_group_asset",
        "MutateOperation.asset_group_signal",
        "MutateOperation.campaign_asset",
    }
    assert esperados <= set(suporte.objetos_serializados)


def test_todas_as_operacoes_do_plano_serializam_de_verdade() -> None:
    """`n_bytes_operacoes` é prova executável, não promessa de docstring."""
    p = pmax.planejar(CID, _brief(), login_customer_id=MCC)
    assert p.prontidao.monta is True
    assert p.n_operacoes >= 20
    assert p.n_bytes_operacoes > 0
    assert len(p.impressao) == 64

    ops, _ = pmax.construir(CID, _brief(), login_customer_id=MCC)
    for o in ops:
        assert o._pb.SerializeToString(deterministic=True), (
            "uma operação serializou vazia — ela não chegaria à API")


def test_sdk_ausente_rebaixa_capacidade_sem_construir_cliente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK incompatível é CAPACIDADE rebaixada, não fallback silencioso."""
    monkeypatch.setattr(
        pmax, "sondar_proto_v25",
        lambda: pmax.SuporteProtoV25(False, "v25 ausente nesta máquina"))
    monkeypatch.setattr(
        pmax, "cliente",
        lambda _l: pytest.fail("cliente construído com SDK incompatível"))

    p = pmax.planejar(CID, _brief(), login_customer_id=MCC)
    assert plano.SDK_V25_INDISPONIVEL in _codigos(p)
    assert p.n_operacoes == 0


# ═══════════════════════════════════════════════════════════════════════════
# FRONTEIRA — o canal continua fora do executor, e diz isso
# ═══════════════════════════════════════════════════════════════════════════


def test_pmax_prova_pelo_perfil_e_continua_fora_do_executor() -> None:
    """A porta de PROVA abriu; a de CRIAÇÃO não. São duas."""
    p = perfil.PERFORMANCE_MAX
    assert p.construtor is pmax.construir
    assert p.validador is pmax.validar
    assert p.sabe_provar is True
    assert p.sabe_criar is False
    assert p.permite_mutacao_real is False

    assert "PERFORMANCE_MAX" in perfil.canais_que_provam()
    assert "PERFORMANCE_MAX" not in perfil.canais_que_criam()
    assert "PERFORMANCE_MAX" in motor.PROVADORES_POR_CANAL
    assert "PERFORMANCE_MAX" not in motor.CONSTRUTORES_POR_CANAL


def test_flag_do_perfil_sozinha_nao_abre_a_criacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠️ CONTRAPROVA: são DUAS travas independentes, e uma não destranca a outra.

    Ligar `permite_mutacao_real` no perfil faria PMax entrar em
    `canais_que_criam()`. Isso ainda não cria nada: o canário de Performance Max
    não foi aceito, e `canario.exigir` recusa por
    `CANAIS_COM_CRIACAO_AUTORIZADA` — que lista apenas SEARCH.

    O teste existe porque a pergunta "o que impede a criação de PMax?" tem duas
    respostas, e um sistema que só tivesse uma delas ficaria a um commit de
    distância de criar sem autorização humana.
    """
    import dataclasses

    from volc_ads import autorizacao_de_canal as aut

    aberto = dataclasses.replace(perfil.PERFORMANCE_MAX,
                                 permite_mutacao_real=True)
    assert aberto.sabe_criar is True, "a primeira trava de fato abriu"

    # ⚠️ E a SEGUNDA continua fechada, no lado que o EXECUTOR alcança. Até
    # 06/09/2026 esta trava só existia em `app.trafego.canario`, que
    # `volc_ads.subir` não importa — e um script in-process com a trava de
    # escrita aberta criaria sem passar por ela.
    assert "PERFORMANCE_MAX" not in aut.CANAIS_COM_CRIACAO_AUTORIZADA
    assert aut.canais_autorizados() == ("SEARCH",)
    with pytest.raises(aut.CriacaoNaoAutorizada, match="não autoriza CRIAR"):
        aut.exigir("PERFORMANCE_MAX")
    # E o executor cobra a mesma trava, pelo mesmo objeto.
    with pytest.raises(motor.CanalSemMutacaoReal, match="não autoriza CRIAR"):
        motor._recusar_canal_sem_mutacao("DISPLAY")


def test_pmax_planeja_e_prova_pelo_perfil() -> None:
    """Planejar e provar são perguntas diferentes — e hoje as duas respondem sim."""
    assert perfil.PERFORMANCE_MAX.sabe_planejar is True
    assert "PERFORMANCE_MAX" in perfil.canais_que_planejam()
    assert set(perfil.canais_que_provam()) == set(perfil.canais_que_planejam())
    assert set(perfil.canais_que_criam()) < set(perfil.canais_que_provam())

    p = perfil.planejar("PMAX", CID, _brief(), login_customer_id=MCC)
    assert p.canal == "PERFORMANCE_MAX"
    assert p.prontidao.monta is True


def test_o_plano_de_pmax_carrega_codigo_proprio_e_nao_o_de_canal_inexistente() -> None:
    """O canal monta e prova; o que o plano ainda declara é a criação fechada."""
    p = pmax.planejar(CID, _brief(), login_customer_id=MCC)
    assert plano.PMAX_FORA_DO_EXECUTOR in _codigos(p)
    assert plano.CANAL_SEM_BUILDER not in _codigos(p)
    assert p.prontidao.pode_provar is True
    assert p.prontidao.pode_criar is False
    assert "permite_mutacao_real" in p.prontidao.motivo_nao_cria
    assert "canário" in p.prontidao.motivo_nao_cria


def test_exigir_prova_aceita_pmax_e_exigir_criacao_recusa() -> None:
    assert perfil.exigir_prova("PERFORMANCE_MAX") is perfil.PERFORMANCE_MAX
    with pytest.raises(perfil.CanalSemConstrutor):
        perfil.exigir("PERFORMANCE_MAX")
    assert perfil.exigir_planejador("PMAX") is perfil.PERFORMANCE_MAX


def test_opcao_de_outro_canal_e_recusada_no_planejar() -> None:
    with pytest.raises(perfil.OpcaoIndisponivel, match="ai_max"):
        perfil.planejar("PERFORMANCE_MAX", CID, _brief(),
                        login_customer_id=MCC, ai_max=True)


def test_o_plano_declara_as_ausencias_em_vez_de_escondê_las() -> None:
    """`não aplicável` é resposta declarada, nunca lacuna."""
    p = pmax.planejar(CID, _brief(), login_customer_id=MCC)
    assert p.nao_operado is pmax.NAO_OPERADO
    assert any("retail" in linha for linha in p.nao_operado)
    assert not any("asset_automation_settings" in linha for linha in p.nao_operado)
    # E a ausência de segmentação positiva é dita com todas as letras.
    assert any("não tem targeting positivo" in linha
               for linha in p.segmentacao.aberto_por_ausencia)
    assert any("sem opt-out" in linha
               for linha in p.segmentacao.aberto_por_ausencia)


# ── T09 · a trava de URL exclusiva, inteira ─────────────────────────────────
#
# PMax só é elegível para esta receita enquanto o clique fica na LP aprovada e
# a peça veiculada é a peça aprovada. Quatro automações quebram uma dessas duas
# coisas, e as quatro nascem LIGADAS quando ninguém fala.


def test_as_automacoes_de_pmax_viajam_todas_desligadas():
    """CONTRAPROVA T09 + achado B5 + v25.2: as 7, todas OPTED_OUT, em ordem estável.

    As cinco primeiras são as de sempre, na mesma ordem (o selo cobre a lista).
    As duas novas entram no FIM: `AUTOMATED_VIDEO_CRAWL` (v25.2) e
    `GENERATE_DESIGN_VERSIONS_FOR_IMAGES`, que a API aceita em PMax
    (validate_only, 08/10/2026) embora o guia só a cite em Demand Gen.
    """
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create

    lidas = [
        (s.asset_automation_type.name, s.asset_automation_status.name)
        for s in camp.asset_automation_settings
    ]
    assert lidas == [
        ("FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION", "OPTED_OUT"),
        ("TEXT_ASSET_AUTOMATION", "OPTED_OUT"),
        ("GENERATE_IMAGE_ENHANCEMENT", "OPTED_OUT"),
        ("GENERATE_ENHANCED_YOUTUBE_VIDEOS", "OPTED_OUT"),
        # A quinta veio da revisão de contrato de API: ela raspa imagens da
        # landing page para o pool visual, e uma peça que entra por aí não
        # passou pelo portão de política nem está no `supply_sha256` do plano.
        ("GENERATE_IMAGE_EXTRACTION", "OPTED_OUT"),
        ("AUTOMATED_VIDEO_CRAWL", "OPTED_OUT"),
        ("GENERATE_DESIGN_VERSIONS_FOR_IMAGES", "OPTED_OUT"),
    ]
    # As cinco de `automacoes.py` são prefixo exato — a tela as lê de lá.
    from volc_ads import automacoes
    assert tuple(t for t, _ in lidas[:5]) == automacoes.AUTOMACOES_PMAX_RECUSADAS
    # Nenhuma delas pode viajar LIGADA, nem por acidente de ordem.
    assert all(estado == "OPTED_OUT" for _, estado in lidas)


def test_pmax_nao_emite_page_feed_que_a_api_recusa():
    """⚠️ INVERTIDO em 08/10/2026, por medição — não por gosto.

    O teste anterior exigia `excluded_parent_asset_set_types == [PAGE_FEED]`. O
    primeiro validate_only de PMax em conta real (Crédito Up) recusou o mutate
    INTEIRO por isso: `CampaignError.INVALID_EXCLUDED_PARENT_ASSET_SET_TYPE`,
    "The asset set type is invalid to be set in excluded_parent_asset_set_types
    field" — e cada outra operação voltou como RESOURCE_NOT_FOUND em cascata.

    A trava que ele pretendia continua de pé por outro caminho: page feed só é
    consumido pela expansão de URL final, que viaja OPTED_OUT.
    """
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    assert list(camp.excluded_parent_asset_set_types) == []
    fue = {s.asset_automation_type.name: s.asset_automation_status.name
           for s in camp.asset_automation_settings}
    assert fue["FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION"] == "OPTED_OUT"


def test_pmax_nao_emite_o_campo_que_nao_existe_na_v25():
    """CONTRAPROVA T09: `url_expansion_opt_out` não existe em v25 e não é emitido.

    A tentação óbvia é procurar um booleano com esse nome. Conferido no proto
    instalado: `Campaign` não o tem. Emitir um campo inexistente faria a API
    recusar o mutate inteiro — depois de o operador ter aprovado o plano.
    """
    from google.ads.googleads.v25.resources.types.campaign import Campaign

    campos = {f.name for f in Campaign.pb(Campaign()).DESCRIPTOR.fields}
    assert "url_expansion_opt_out" not in campos
    assert "asset_automation_settings" in campos
    assert "excluded_parent_asset_set_types" in campos

    ops, _ = pmax.construir(CID, _brief(), login_customer_id=MCC)
    camp = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    assert not camp._pb.HasField("network_settings"), (
        "PMax não tem controle de rede; emitir o campo declararia um controle "
        "que não existe"
    )


def test_o_asset_group_tem_uma_url_so_e_nenhum_caminho_de_exibicao():
    """CONTRAPROVA T09: uma única URL final, sem mobile e sem path1/path2.

    `final_mobile_urls` mandaria o celular para outro lugar; `path1`/`path2`
    mudam o endereço EXIBIDO sem mudar o servido, e as duas coisas afastam o
    que o operador aprovou do que o usuário vê e recebe.
    """
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    grupos = _por_tipo(ops, "asset_group_operation")
    assert len(grupos) == 1

    ag = grupos[0].asset_group_operation.create
    assert len(ag.final_urls) == 1
    assert list(ag.final_mobile_urls) == []
    assert ag.path1 == ""
    assert ag.path2 == ""
    assert ag.status.name == "PAUSED"


def test_nenhum_objeto_pmax_nasce_ligado():
    """CONTRAPROVA T09/invariante: varredura, não lista.

    Um objeto novo amanhã não pode escapar por ninguém ter lembrado de
    acrescentá-lo a uma lista de verificação escrita hoje.
    """
    ops, r = pmax.construir(CID, _brief(), login_customer_id=MCC)
    assert r.ok, _erros(r)
    for o in ops:
        qual = o._pb.WhichOneof("operation")
        criado = getattr(getattr(o, qual), "create", None)
        estado = getattr(criado, "status", None)
        nome = getattr(estado, "name", None)
        if nome is not None:
            assert nome != "ENABLED", f"{qual} nasceu ENABLED"


# ═══════════════════════════════════════════════════════════════════════════
# v25.2 — múltiplos asset groups, URL options, video crawl, sinais, metas
#
# Tudo aqui é offline, com os protos v25 reais. As decisões que dependem do
# que a API ACEITA foram medidas por validate_only na Crédito Up em 08/10/2026
# (ver `pmax_config.py`); estes testes guardam o PAYLOAD que reproduz a prova.
# ═══════════════════════════════════════════════════════════════════════════

from volc_ads.campanha import pmax_config as pc  # noqa: E402
from volc_ads.campanha import pmax_grafo  # noqa: E402


def _v25(**troca) -> pc.ConfiguracaoPMaxV25:
    base = dict(
        brand_guidelines_enabled=False,
        mensuracao=_mensuracao(),
        sinais=(SinalDeAudiencia("search_theme", "saque anual fgts"),),
        negativas=("emprestimo consignado",),
    )
    base.update(troca)
    return pc.ConfiguracaoPMaxV25(**base)


def _grupo(nome="Grupo B", **troca) -> pc.AssetGroupPMax:
    base = dict(
        nome=nome,
        url_final="https://creditoup.com.br/r/saque-anual/?secao=b",
        textos=pc.TextosPMax(
            headlines=("Calendario do Saque", "Quem Pode Sacar", "Regras Oficiais"),
            long_headlines=("Calendario oficial e regras do saque anual",),
            descriptions=("Calendario e regras, com fonte.",
                          "Guia informativo com o calendario oficial do saque."),
        ),
        imagens=_imagens(
            marketing=[_imagem("bmkt", "marketing", 1200, 628)],
            marketing_quadrada=[_imagem("bsq", "marketing_quadrada", 1200, 1200)],
            logo=[_imagem("blogo", "logo", 1200, 1200)],
        ),
        sinais=(SinalDeAudiencia("search_theme", "calendario saque"),),
    )
    base.update(troca)
    return pc.AssetGroupPMax(**base)


def _campanha_de(ops):
    return _por_tipo(ops, "campaign_operation")[0].campaign_operation.create


def _enum_nomes(nome: str) -> set[str]:
    return set(_Enums().__getattr__(nome).__members__) - {"UNSPECIFIED", "UNKNOWN"}


def test_vocabulario_de_pmax_config_bate_com_o_proto_v25() -> None:
    """`pmax_config` não importa o SDK (a tela o lê); o proto é quem o confere."""
    automacoes = _enum_nomes("AssetAutomationTypeEnum")
    assert set(pc.AUTOMACOES_PMAX_V25) <= automacoes
    assert set(pc.AUTOMACOES_RECUSADAS_PELA_API_EM_PMAX) <= automacoes
    assert not set(pc.AUTOMACOES_PMAX_V25) & set(pc.AUTOMACOES_RECUSADAS_PELA_API_EM_PMAX)
    assert set(pc.PLATAFORMAS_DE_VIDEO_CRAWL) == _enum_nomes("VideoCrawlSourcePlatformEnum")
    assert set(pc.CATEGORIAS_DE_CONVERSAO) == _enum_nomes("ConversionActionCategoryEnum")
    assert set(pc.ORIGENS_DE_CONVERSAO) == _enum_nomes("ConversionOriginEnum")
    assert set(pc.MATCH_TYPES_NEGATIVOS) == _enum_nomes("KeywordMatchTypeEnum")
    assert set(pc.MODOS_CLIENTE_NOVO) == _enum_nomes("CustomerLifecycleOptimizationModeEnum")
    assert set(pc.OPERADORES_DE_URL) == _enum_nomes("WebpageConditionOperatorEnum")
    assert set(pc.OPERANDOS_DE_URL) <= _enum_nomes("WebpageConditionOperandEnum")


def test_configuracao_antiga_e_a_v25_com_defaults_geram_o_mesmo_payload() -> None:
    """Defaults preservam o comportamento: promover não decide nada."""
    antiga = _brief(carimbo_nome="20261008_120000")
    nova = _brief(carimbo_nome="20261008_120000",
                  pmax=pc.estender(antiga.pmax))
    ops_a, ra = pmax.construir(CID, antiga, login_customer_id=MCC)
    ops_b, rb = pmax.construir(CID, nova, login_customer_id=MCC)
    assert ra.ok and rb.ok, _erros(ra) + _erros(rb)
    assert ([o._pb.SerializeToString(deterministic=True) for o in ops_a]
            == [o._pb.SerializeToString(deterministic=True) for o in ops_b])
    assert len(_por_tipo(ops_a, "asset_group_operation")) == 1


def test_dois_asset_groups_cada_um_com_o_que_e_seu() -> None:
    cfg = _v25(grupos_adicionais=(_grupo(),))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)

    grupos = [o.asset_group_operation.create
              for o in _por_tipo(ops, "asset_group_operation")]
    assert [g.resource_name for g in grupos] == [
        f"customers/{CID}/assetGroups/-300", f"customers/{CID}/assetGroups/-301"]
    assert all(g.status.name == "PAUSED" for g in grupos)
    assert list(grupos[1].final_urls) == ["https://creditoup.com.br/r/saque-anual/?secao=b"]

    por_grupo: dict[str, set[str]] = {}
    for o in _por_tipo(ops, "asset_group_asset_operation"):
        v = o.asset_group_asset_operation.create
        por_grupo.setdefault(v.asset_group, set()).add(v.field_type.name)
    # Brand guidelines DESLIGADO: os dois grupos têm BUSINESS_NAME e LOGO próprios.
    for rn in (g.resource_name for g in grupos):
        assert {"HEADLINE", "LONG_HEADLINE", "DESCRIPTION", "BUSINESS_NAME",
                "LOGO", "MARKETING_IMAGE", "SQUARE_MARKETING_IMAGE"} <= por_grupo[rn]

    sinais = {(o.asset_group_signal_operation.create.asset_group,
               o.asset_group_signal_operation.create.search_theme.text)
              for o in _por_tipo(ops, "asset_group_signal_operation")}
    assert sinais == {(grupos[0].resource_name, "saque anual fgts"),
                      (grupos[1].resource_name, "calendario saque")}

    # Ordem: todo asset antes do primeiro grupo; cada vínculo depois do SEU grupo.
    tipos = [o._pb.WhichOneof("operation") for o in ops]
    assert max(i for i, t in enumerate(tipos) if t == "asset_operation") < tipos.index(
        "asset_group_operation")
    posicao = {g.resource_name: tipos.index("asset_group_operation") for g in grupos[:1]}
    posicao[grupos[1].resource_name] = [
        i for i, t in enumerate(tipos) if t == "asset_group_operation"][1]
    for i, o in enumerate(ops):
        if tipos[i] == "asset_group_asset_operation":
            assert i > posicao[o.asset_group_asset_operation.create.asset_group]


def test_texto_e_imagem_iguais_em_dois_grupos_viram_um_asset() -> None:
    """A faixa de id é finita: o mesmo conteúdo é UM asset ligado duas vezes."""
    g = _grupo(textos=pc.TextosPMax(
        headlines=("Regras do Saque Anual", "Quem Pode Sacar", "Regras Oficiais"),
        long_headlines=("Prazos, limites e quem tem direito ao saque anual",),
        descriptions=("Prazos e limites, com fonte citada.",
                      "Guia informativo com o calendario oficial do saque.")),
        imagens=_imagens())
    ops, r = pmax.construir(CID, _brief(pmax=_v25(grupos_adicionais=(g,))),
                            login_customer_id=MCC)
    assert r.ok, _erros(r)
    textos = [o.asset_operation.create.text_asset.text
              for o in _por_tipo(ops, "asset_operation")
              if o.asset_operation.create.text_asset.text]
    assert len(textos) == len(set(textos))
    dados = [bytes(o.asset_operation.create.image_asset.data)
             for o in _por_tipo(ops, "asset_operation")
             if o.asset_operation.create.image_asset.data]
    assert len(dados) == len(set(dados)) == 3


def test_url_options_do_asset_group_acrescentam_ao_sufixo_da_campanha() -> None:
    """v25.2: o sufixo do grupo SUBSTITUI o da campanha — por isso ele o contém."""
    opcoes = pc.OpcoesDeUrl(
        sufixo_extra=(("vc_ag", "b"), ("vc_tema", "{_tema}")),
        tracking_url_template="{lpurl}?vc_tpl={_tema}",
        parametros_personalizados=(("tema", "calendario"),))
    cfg = _v25(path1="saque", path2="anual",
               grupos_adicionais=(_grupo(opcoes_de_url=opcoes, path1="saque"),))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _campanha_de(ops)
    g0, g1 = [o.asset_group_operation.create
              for o in _por_tipo(ops, "asset_group_operation")]
    assert (g0.path1, g0.path2) == ("saque", "anual")
    assert g0.final_url_suffix == "" and g0.tracking_url_template == ""
    assert g1.final_url_suffix.startswith(camp.final_url_suffix + "&")
    assert g1.final_url_suffix.endswith("vc_ag=b&vc_tema={_tema}")
    assert g1.tracking_url_template == "{lpurl}?vc_tpl={_tema}"
    assert [(p.key, p.value) for p in g1.url_custom_parameters] == [("tema", "calendario")]


@pytest.mark.parametrize("opcoes,trecho", [
    (pc.OpcoesDeUrl(sufixo_extra=(("vc_x", "{_naodeclarado}"),)), "macro personalizada"),
    (pc.OpcoesDeUrl(tracking_url_template="https://rastreio.example/x"), "{lpurl}"),
    (pc.OpcoesDeUrl(parametros_personalizados=(("com_underscore", "v"),)), "alfanumérica"),
    (pc.OpcoesDeUrl(sufixo_extra=(("vc_x", "{inexistente}"),)), "macro inexistente"),
])
def test_url_options_invalidas_falham_local(opcoes, trecho) -> None:
    cfg = _v25(opcoes_de_url=opcoes)
    _, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert not r.ok
    assert trecho in _erros(r)


@pytest.mark.parametrize("p1,p2,trecho", [
    ("a" * 16, "", "15"), ("", "anual", "sem `path1`"), ("com/barra", "", "barra")])
def test_caminho_de_exibicao_tem_regua(p1, p2, trecho) -> None:
    _, r = pmax.construir(CID, _brief(pmax=_v25(path1=p1, path2=p2)),
                          login_customer_id=MCC)
    assert trecho in _erros(r)


def test_automacao_optada_viaja_opted_in_e_as_outras_continuam_fora() -> None:
    cfg = _v25(automacoes_optadas=("FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
                                   "TEXT_ASSET_AUTOMATION"))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    estado = {s.asset_automation_type.name: s.asset_automation_status.name
              for s in _campanha_de(ops).asset_automation_settings}
    assert list(estado) == list(pc.AUTOMACOES_PMAX_V25)
    assert estado["FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION"] == "OPTED_IN"
    assert estado["TEXT_ASSET_AUTOMATION"] == "OPTED_IN"
    assert {k for k, v in estado.items() if v == "OPTED_OUT"} == set(
        pc.AUTOMACOES_PMAX_V25) - {"FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
                                   "TEXT_ASSET_AUTOMATION"}


@pytest.mark.parametrize("troca,trecho", [
    # medido: DYNAMIC_TEXT_ASSET_CANNOT_OPT_OUT_WITH_FINAL_URL_EXPANSION_OPT_IN
    (dict(automacoes_optadas=("FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",)),
     "TEXT_ASSET_AUTOMATION"),
    # medido: ENUM_VALUE_NOT_PERMITTED
    (dict(automacoes_optadas=("GENERATE_VERTICAL_YOUTUBE_VIDEOS",)),
     "ENUM_VALUE_NOT_PERMITTED"),
    (dict(automacoes_optadas=("AUTOMATED_VIDEO_CRAWL",),
          video_crawl_direitos_declarados=True), "sem nenhuma fonte"),
    (dict(automacoes_optadas=("AUTOMATED_VIDEO_CRAWL",),
          video_crawl=(pc.FonteDeVideoCrawl("https://creditoup.com.br/", "LANDING_PAGE"),)),
     "direitos"),
    (dict(video_crawl=(pc.FonteDeVideoCrawl("https://creditoup.com.br/", "LANDING_PAGE"),)),
     "não viajariam"),
    (dict(automacoes_optadas=("AUTOMATED_VIDEO_CRAWL",), video_crawl_direitos_declarados=True,
          video_crawl=(pc.FonteDeVideoCrawl("https://vimeo.com/x", "YOUTUBE"),)),
     "youtube.com"),
])
def test_automacoes_tem_regua_local(troca, trecho) -> None:
    _, r = pmax.construir(CID, _brief(pmax=_v25(**troca)), login_customer_id=MCC)
    assert not r.ok
    assert trecho in _erros(r)


def test_video_crawl_v252_viaja_no_oneof_da_automacao() -> None:
    fontes = (pc.FonteDeVideoCrawl("https://creditoup.com.br/r/saque-anual/", "LANDING_PAGE"),
              pc.FonteDeVideoCrawl("https://www.youtube.com/@exemplo", "YOUTUBE"),
              pc.FonteDeVideoCrawl("https://www.instagram.com/exemplo/", "SOCIAL", False))
    cfg = _v25(automacoes_optadas=("AUTOMATED_VIDEO_CRAWL",), video_crawl=fontes,
               video_crawl_direitos_declarados=True)
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    crawl = next(s for s in _campanha_de(ops).asset_automation_settings
                 if s.asset_automation_type.name == "AUTOMATED_VIDEO_CRAWL")
    assert crawl.asset_automation_status.name == "OPTED_IN"
    assert crawl._pb.WhichOneof("setting") == "automated_video_crawl_setting"
    infos = [(i.url, i.source_platform.name, i.enabled)
             for i in crawl.automated_video_crawl_setting.automated_video_crawl_infos]
    assert infos == [(f.url, f.plataforma, f.habilitada) for f in fontes]
    # E desligado não carrega fonte nenhuma.
    ops2, _ = pmax.construir(CID, _brief(pmax=_v25()), login_customer_id=MCC)
    off = next(s for s in _campanha_de(ops2).asset_automation_settings
               if s.asset_automation_type.name == "AUTOMATED_VIDEO_CRAWL")
    assert off.asset_automation_status.name == "OPTED_OUT"
    assert off._pb.WhichOneof("setting") is None


def test_negativas_com_match_type_e_a_legada_continua_broad() -> None:
    cfg = _v25(negativas_tipadas=(pc.NegativaPMax("saque emergencial", "PHRASE"),
                                  pc.NegativaPMax("fgts login", "EXACT")))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    kws = [(o.campaign_criterion_operation.create.keyword.text,
            o.campaign_criterion_operation.create.keyword.match_type.name,
            o.campaign_criterion_operation.create.negative)
           for o in _por_tipo(ops, "campaign_criterion_operation")
           if o.campaign_criterion_operation.create._pb.WhichOneof("criterion") == "keyword"]
    assert kws == [("emprestimo consignado", "BROAD", True),
                   ("saque emergencial", "PHRASE", True), ("fgts login", "EXACT", True)]

    _, r2 = pmax.construir(CID, _brief(pmax=_v25(negativas_tipadas=(
        pc.NegativaPMax("emprestimo consignado", "BROAD"),))), login_customer_id=MCC)
    assert "repetida" in _erros(r2)


def test_exclusao_de_marca_cria_a_lista_no_mesmo_mutate() -> None:
    cfg = _v25(marcas_excluidas=(pc.MarcaExcluida("/g/11trqcwsy6", "Coursera"),
                                 pc.MarcaExcluida("/g/11k9cpgffz", "Udemy")))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    tipos = [o._pb.WhichOneof("operation") for o in ops]
    ss = _por_tipo(ops, "shared_set_operation")[0].shared_set_operation.create
    assert ss.type_.name == "BRANDS"
    assert ss.resource_name == f"customers/{CID}/sharedSets/-500"
    assert [o.shared_criterion_operation.create.brand.entity_id
            for o in _por_tipo(ops, "shared_criterion_operation")] == [
        "/g/11trqcwsy6", "/g/11k9cpgffz"]
    crit = [o.campaign_criterion_operation.create
            for o in _por_tipo(ops, "campaign_criterion_operation")
            if o.campaign_criterion_operation.create._pb.WhichOneof("criterion") == "brand_list"]
    assert len(crit) == 1 and crit[0].negative is True
    assert crit[0].brand_list.shared_set == ss.resource_name
    # A lista nasce ANTES do critério que a referencia.
    assert tipos.index("shared_set_operation") < max(
        i for i, o in enumerate(ops) if tipos[i] == "campaign_criterion_operation")

    _, r2 = pmax.construir(CID, _brief(pmax=_v25(
        marcas_excluidas=(pc.MarcaExcluida("Coursera"),))), login_customer_id=MCC)
    assert "entity_id" in _erros(r2)


def test_exclusao_de_url_e_negativa_e_avisa_quando_a_expansao_esta_desligada() -> None:
    cfg = _v25(exclusoes_de_url=(pc.ExclusaoDeUrl("sem blog", "/blog/"),))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    w = next(o.campaign_criterion_operation.create
             for o in _por_tipo(ops, "campaign_criterion_operation")
             if o.campaign_criterion_operation.create._pb.WhichOneof("criterion") == "webpage")
    assert w.negative is True and w.webpage.criterion_name == "sem blog"
    cond = w.webpage.conditions[0]
    assert (cond.operand.name, cond.operator.name, cond.argument) == ("URL", "CONTAINS", "/blog/")
    assert any(a.campo == "pmax.exclusoes_de_url" and a.severidade == "aviso"
               for a in r.achados)


def test_metas_de_conversao_viajam_como_update_no_id_temporario() -> None:
    """Medido: a API aceita UPDATE em `campaignConversionGoals/-2~CAT~ORIGEM`."""
    cfg = _v25(metas_de_conversao=(pc.MetaDeConversao("PURCHASE", "WEBSITE", True),
                                   pc.MetaDeConversao("DOWNLOAD", "APP", False)))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    metas = [o.campaign_conversion_goal_operation
             for o in _por_tipo(ops, "campaign_conversion_goal_operation")]
    assert [(m.update.resource_name, m.update.biddable, list(m.update_mask.paths))
            for m in metas] == [
        (f"customers/{CID}/campaignConversionGoals/-2~PURCHASE~WEBSITE", True, ["biddable"]),
        (f"customers/{CID}/campaignConversionGoals/-2~DOWNLOAD~APP", False, ["biddable"]),
    ]
    tipos = [o._pb.WhichOneof("operation") for o in ops]
    assert tipos.index("campaign_operation") < tipos.index("campaign_conversion_goal_operation")

    _, r2 = pmax.construir(CID, _brief(pmax=_v25(metas_de_conversao=(
        pc.MetaDeConversao("COMPRA", "WEBSITE", True),))), login_customer_id=MCC)
    assert "ConversionActionCategory" in _erros(r2)


def test_meta_de_cliente_novo_e_fase_2_e_nao_entra_no_mutate() -> None:
    """v25 removeu `CampaignLifecycleGoal`; o mecanismo é `CampaignGoalConfig`."""
    nc = pc.MetaClienteNovo(goal=f"customers/{CID}/goals/77", modo="TARGET_SPECIFIC",
                            valor_adicional=10.0)
    cfg = _v25(meta_cliente_novo=nc)
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    assert any(a.campo == "pmax.meta_cliente_novo" and a.severidade == "aviso"
               for a in r.achados)
    assert "campaign_goal_config_operation" not in pmax.CAMPOS_DE_OPERACAO_V25

    c = _cliente_sem_rede()
    pos = pmax_grafo.operacoes_pos_criacao(
        c, CID, f"customers/{CID}/campaigns/123", cfg)
    assert len(pos) == 1
    g = pos[0].create
    assert g.campaign == f"customers/{CID}/campaigns/123"
    assert g.goal == nc.goal
    s = g.campaign_new_customer_acquisition_settings
    assert s.target_option.name == "TARGET_SPECIFIC"
    assert s.value_settings_override.additional_value == 10.0
    assert pos[0]._pb.SerializeToString(deterministic=True)

    for ruim, trecho in (
        (pc.MetaClienteNovo(goal="customers/1/goals/2", modo="TARGET_ALL"), "outra conta"),
        (pc.MetaClienteNovo(goal=nc.goal, modo="BID_HIGHER"), "modo"),
        (pc.MetaClienteNovo(goal=nc.goal, modo="TARGET_ALL", valor_adicional=1.0,
                            multiplicador_de_valor=1.5), "oneof"),
    ):
        _, rr = pmax.construir(CID, _brief(pmax=_v25(meta_cliente_novo=ruim)),
                               login_customer_id=MCC)
        assert trecho in _erros(rr), trecho


def test_video_do_youtube_nasce_no_mesmo_mutate_por_id() -> None:
    cfg = _v25(videos=(pc.VideoYouTube("M7lc1UVf-VE"),),
               grupos_adicionais=(_grupo(videos=(pc.VideoYouTube("M7lc1UVf-VE"),)),))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    videos = [o.asset_operation.create for o in _por_tipo(ops, "asset_operation")
              if o.asset_operation.create.type_.name == "YOUTUBE_VIDEO"]
    assert len(videos) == 1, "o mesmo vídeo em dois grupos é um asset só"
    assert videos[0].youtube_video_asset.youtube_video_id == "M7lc1UVf-VE"
    assert videos[0].resource_name == f"customers/{CID}/assets/-400"
    links = [o.asset_group_asset_operation.create
             for o in _por_tipo(ops, "asset_group_asset_operation")
             if o.asset_group_asset_operation.create.field_type.name == "YOUTUBE_VIDEO"]
    assert {v.asset_group for v in links} == {
        f"customers/{CID}/assetGroups/-300", f"customers/{CID}/assetGroups/-301"}

    with pytest.raises(ValueError, match="11"):
        pc.VideoYouTube("https://youtu.be/M7lc1UVf-VE")
    muitos = tuple(pc.VideoYouTube(f"video{i:06d}") for i in range(16))
    _, r2 = pmax.construir(CID, _brief(pmax=_v25(videos=muitos)), login_customer_id=MCC)
    assert "YOUTUBE_VIDEO aceita até 15" in _erros(r2)


def test_brand_guidelines_leva_o_logo_PAISAGEM_para_a_campanha_tambem() -> None:
    """Medido: LANDSCAPE_LOGO no asset group com brand guidelines ligado responde
    BRAND_ASSETS_NOT_LINKED_AT_CAMPAIGN_LEVEL. Até 08/10 só LOGO subia."""
    imagens = _imagens(logo_paisagem=[_imagem("lp", "logo_paisagem", 1200, 300)])
    ops, r = pmax.construir(
        CID, _brief(imagens_pmax=imagens, pmax=_v25(brand_guidelines_enabled=True)),
        login_customer_id=MCC)
    assert r.ok, _erros(r)
    campanha = {o.campaign_asset_operation.create.field_type.name
                for o in _por_tipo(ops, "campaign_asset_operation")}
    grupo = {o.asset_group_asset_operation.create.field_type.name
             for o in _por_tipo(ops, "asset_group_asset_operation")}
    assert {"BUSINESS_NAME", "LOGO", "LANDSCAPE_LOGO"} <= campanha
    assert not {"BUSINESS_NAME", "LOGO", "LANDSCAPE_LOGO"} & grupo

    _, r2 = pmax.construir(CID, _brief(pmax=_v25(
        brand_guidelines_enabled=True, grupos_adicionais=(_grupo(),))),
        login_customer_id=MCC)
    assert "BRAND_ASSETS_NOT_LINKED_AT_CAMPAIGN_LEVEL" in _erros(r2)


def test_guias_de_texto_e_de_marca_viajam_na_campanha() -> None:
    cfg = _v25(brand_guidelines_enabled=True,
               termos_excluidos=("gratis",),
               restricoes_de_mensagem=("Nao prometer aprovacao.",),
               diretrizes_de_marca=pc.DiretrizesDeMarca("#0B3D91", "#F2A900", "Roboto"))
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _campanha_de(ops)
    assert list(camp.text_guidelines.term_exclusions) == ["gratis"]
    m = camp.text_guidelines.messaging_restrictions[0]
    assert m.restriction_type.name == "RESTRICTION_BASED_EXCLUSION"
    assert (camp.brand_guidelines.main_color, camp.brand_guidelines.accent_color,
            camp.brand_guidelines.predefined_font_family) == ("#0B3D91", "#F2A900", "Roboto")

    for troca, trecho in (
        (dict(diretrizes_de_marca=pc.DiretrizesDeMarca(fonte="Arial")), "brand_guidelines_enabled=True"),
        (dict(brand_guidelines_enabled=True,
              diretrizes_de_marca=pc.DiretrizesDeMarca("#0B3D91")), "andam juntas"),
        (dict(termos_excluidos=("x" * 31,)), "30"),
    ):
        _, rr = pmax.construir(CID, _brief(pmax=_v25(**troca)), login_customer_id=MCC)
        assert trecho in _erros(rr), trecho


@pytest.mark.parametrize("estrategia,meta,ramo,campo,valor", [
    ("MAXIMIZE_CONVERSIONS", {}, "maximize_conversions", "target_cpa_micros", 0),
    ("MAXIMIZE_CONVERSIONS", {"tcpa": 3.5}, "maximize_conversions", "target_cpa_micros", 3_500_000),
    ("MAXIMIZE_CONVERSION_VALUE", {}, "maximize_conversion_value", "target_roas", 0.0),
    ("MAXIMIZE_CONVERSION_VALUE", {"target_roas": 4.0}, "maximize_conversion_value", "target_roas", 4.0),
])
def test_os_quatro_lances_provados_ocupam_o_ramo_certo(estrategia, meta, ramo, campo, valor) -> None:
    ops, r = pmax.construir(CID, _brief(estrategia_lance=estrategia, **meta,
                                        pmax=_v25(grupos_adicionais=(_grupo(),))),
                            login_customer_id=MCC)
    assert r.ok, _erros(r)
    camp = _campanha_de(ops)
    assert camp._pb.WhichOneof("campaign_bidding_strategy") == ramo
    assert getattr(getattr(camp, ramo), campo) == valor


def test_grupos_adicionais_tem_a_mesma_regua_do_grupo_zero() -> None:
    sem_imagem = _grupo(imagens=_imagens(marketing=[]))
    p = pmax.planejar(CID, _brief(pmax=_v25(grupos_adicionais=(sem_imagem,))),
                      login_customer_id=MCC)
    lacunas = [b for b in p.bloqueios if b.campo == "asset_group.cobertura"]
    assert lacunas and all(b.valor == "Grupo B" for b in lacunas)

    for troca, trecho in (
        (dict(grupos_adicionais=(_grupo(nome="AG"), _grupo(nome="ag"))), "repetido"),
        (dict(grupos_adicionais=(_grupo(sinais=None),)), "sinais do grupo"),
        (dict(sinais=tuple(SinalDeAudiencia("search_theme", f"tema {i}")
                           for i in range(51))), "até 50 search themes"),
        (dict(grupos_adicionais=(_grupo(url_final="http://creditoup.com.br/x"),)), "https"),
    ):
        _, r = pmax.construir(CID, _brief(pmax=_v25(**troca)), login_customer_id=MCC)
        assert trecho in _erros(r), trecho


def test_payload_maximo_serializa_e_nada_nasce_ligado() -> None:
    """O payload que a prova validate_only usou, inteiro, contra o proto real."""
    cfg = _v25(
        brand_guidelines_enabled=True,
        path1="saque", path2="anual",
        opcoes_de_url=pc.OpcoesDeUrl(sufixo_extra=(("vc_ag", "a"),)),
        videos=(pc.VideoYouTube("M7lc1UVf-VE"),),
        grupos_adicionais=(_grupo(imagens=_imagens(logo=[])),),
        automacoes_optadas=("FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
                            "TEXT_ASSET_AUTOMATION", "AUTOMATED_VIDEO_CRAWL"),
        video_crawl=(pc.FonteDeVideoCrawl("https://creditoup.com.br/", "LANDING_PAGE"),),
        video_crawl_direitos_declarados=True,
        exclusoes_de_url=(pc.ExclusaoDeUrl("sem blog", "/blog/"),),
        termos_excluidos=("gratis",),
        diretrizes_de_marca=pc.DiretrizesDeMarca("#0B3D91", "#F2A900", "Roboto"),
        negativas_tipadas=(pc.NegativaPMax("fgts login", "EXACT"),),
        listas_de_negativas=(f"customers/{CID}/sharedSets/123",),
        marcas_excluidas=(pc.MarcaExcluida("/g/11trqcwsy6"),),
        listas_de_marcas_excluidas=(f"customers/{CID}/sharedSets/456",),
        metas_de_conversao=(pc.MetaDeConversao("PURCHASE", "WEBSITE", True),),
    )
    p = pmax.planejar(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert p.prontidao.monta is True, [b.causa for b in p.bloqueios]
    assert sum(1 for u in p.unidades if u.tipo == "asset_group") == 2
    ops, r = pmax.construir(CID, _brief(pmax=cfg), login_customer_id=MCC)
    assert r.ok, _erros(r)
    tipos = {o._pb.WhichOneof("operation") for o in ops}
    assert tipos <= pmax.CAMPOS_DE_OPERACAO_V25
    for o in ops:
        assert o._pb.SerializeToString(deterministic=True)
        qual = o._pb.WhichOneof("operation")
        criado = getattr(getattr(o, qual), "create", None)
        nome = getattr(getattr(criado, "status", None), "name", None)
        assert nome != "ENABLED", f"{qual} nasceu ENABLED"
    assert _por_tipo(ops, "campaign_shared_set_operation")[0] \
        .campaign_shared_set_operation.create.shared_set == f"customers/{CID}/sharedSets/123"
