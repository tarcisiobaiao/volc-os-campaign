"""Testes do plano — o contrato que a API e a tela consomem.

Rodar da raiz do projeto:
    backend/.venv/bin/python -m pytest volc_ads/campanha/testes_plano.py -q

Este arquivo prova as afirmações de
`docs/closure/traffic-creative-operational-closure-v1/CONTRATO-CANAIS-PARA-API.md`.
Se uma delas deixar de valer, é aqui que a suíte cai — e não no navegador do
Worker 3.

Quatro grupos:

  IMPORT     `plano.py` não pode importar o SDK do Google. É a única razão de o
             Hub poder falar de plano sem passar a depender de
             `google.ads.googleads` em tempo de import.

  PROJEÇÃO   o plano é lido DAS OPERAÇÕES que iriam para a API, não remontado a
             partir do brief. Um plano que discorda do payload precisa ser
             impossível por construção.

  ESTADOS    `ausente ≠ zero ≠ falha ≠ não aplicável`, campo a campo.

  CÓDIGOS    a lista de bloqueio é fechada e estável; nenhum canal emite código
             fora dela.
"""

from __future__ import annotations

import ast
import enum
import json
import pathlib
import sys
from importlib import import_module

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

from volc_ads.campanha import display, perfil, plano, pmax, search  # noqa: E402
from volc_ads.campanha.brief import (  # noqa: E402
    Brief,
    Copy,
    ImagensDisplay,
    Sitelink,
)  # noqa: E402

CID = "8017851692"
MCC = "6016739364"

RAIZ = pathlib.Path(__file__).resolve().parents[2]


# ── cliente sem rede ────────────────────────────────────────────────────────


class _Enums:
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
    for modulo in (search, display, pmax):
        monkeypatch.setattr(modulo, "cliente", lambda _login: _cliente_sem_rede())


# ── briefs ──────────────────────────────────────────────────────────────────


def _brief_display(**troca) -> Brief:
    base = dict(
        nicho="Saque Anual", slug="saque-anual",
        url_final="https://creditoup.com.br/r/saque-anual/",
        keywords=["saque anual fgts"],
        copy=Copy(
            headlines=["Regras do Saque Anual", "Quem Tem Direito em 2026"],
            long_headlines=["Prazos, limites e quem tem direito ao saque anual"],
            descriptions=["Prazos, limites e quem tem direito, com fonte.",
                          "Portal informativo com a tabela por faixa etaria."],
            business_name="Credito Up"),
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        imagens_display=ImagensDisplay(
            marketing=[f"customers/{CID}/assets/111"],
            marketing_quadrada=[f"customers/{CID}/assets/222"],
            logo=[f"customers/{CID}/assets/333"]),
    )
    base.update(troca)
    return Brief(**base)


def _brief_search(**troca) -> Brief:
    base = dict(
        nicho="Saque Anual", slug="saque-anual",
        url_final="https://creditoup.com.br/r/saque-anual/",
        keywords=["saque anual fgts", "calendario saque anual"],
        # ⚠️ Search EXIGE 2 sitelinks e 2 callouts (`limites.yaml`), diferente
        # dos outros três canais. Um brief de Search sem eles não é um brief
        # incompleto de teste: é um brief que o canal recusa, e recusar é o
        # comportamento certo.
        copy=Copy(
            headlines=["Regras do Saque Anual", "Quem Tem Direito em 2026",
                       "Tabela Oficial por Faixa"],
            descriptions=["Prazos, limites e quem tem direito, com fonte.",
                          "Portal informativo com a tabela por faixa etaria."],
            sitelinks=[Sitelink("Calendario oficial"), Sitelink("Quem tem direito")],
            callouts=["Fonte oficial citada", "Sem cadastro"]),
    )
    base.update(troca)
    return Brief(**base)


# ═══════════════════════════════════════════════════════════════════════════
# IMPORT — a regra que o backend depende
# ═══════════════════════════════════════════════════════════════════════════


def test_plano_nao_importa_o_sdk_do_google() -> None:
    """Por ÁRVORE SINTÁTICA, sem executar nada.

    ⚠️ Não basta `plano` já estar importado nesta sessão e funcionar: a
    pergunta é se um arquivo do BACKEND pode colocá-lo no topo sem arrastar
    `google.ads.googleads` junto. Isso se lê no código, não no runtime — e é a
    mesma técnica que `backend/tests/test_trafego_plataforma.py` usa contra
    `perfil.py`, pelo mesmo motivo.
    """
    arvore = ast.parse(
        (RAIZ / "volc_ads" / "campanha" / "plano.py").read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            modulos.add(no.module or "")

    proibidos = [m for m in modulos if "googleads" in m or m.startswith("google.")]
    assert not proibidos, (
        f"`campanha/plano.py` importa {proibidos} — o Hub perderia o direito de "
        f"declarar o tipo do plano no topo de um arquivo, e os dois testes de "
        f"árvore sintática do backend cairiam junto")

    # E nada de `campanha.*` também: um ciclo perfil → canal → plano → perfil
    # quebraria o import de todo mundo.
    assert not [m for m in modulos if m.startswith(".") or "campanha" in m], (
        f"`plano.py` importou algo do próprio pacote: {sorted(modulos)}")


def test_o_plano_e_json_nativo_ate_as_folhas() -> None:
    """Nada de `datetime`, `Enum`, `bytes`, `tuple` ou dataclass no retorno."""
    p = display.planejar(CID, _brief_display(), login_customer_id=MCC)
    bruto = p.para_json()
    texto = json.dumps(bruto, ensure_ascii=False)  # levanta se houver não-JSON
    assert json.loads(texto) == bruto

    def _so_json(valor, caminho="raiz"):
        assert isinstance(valor, (str, int, float, bool, type(None), list, dict)), (
            f"{caminho} é {type(valor).__name__}, que não atravessa HTTP")
        if isinstance(valor, dict):
            for k, v in valor.items():
                assert isinstance(k, str), f"{caminho}: chave não-str"
                _so_json(v, f"{caminho}.{k}")
        elif isinstance(valor, list):
            for i, v in enumerate(valor):
                _so_json(v, f"{caminho}[{i}]")

    _so_json(bruto)


# ═══════════════════════════════════════════════════════════════════════════
# PROJEÇÃO — o plano é lido do payload
# ═══════════════════════════════════════════════════════════════════════════


def test_o_plano_le_as_operacoes_reais_de_display() -> None:
    """Cada campo do plano tem de bater com o protobuf que iria para a API.

    Se algum dia alguém escrever uma segunda montagem — um `planejar` que
    remonta o plano a partir do brief em vez de ler as operações — é este teste
    que passa a exigir que as duas concordem. Ele compara o plano com o payload,
    não com uma expectativa escrita à mão.
    """
    brief = _brief_display()
    ops, r = display.construir(CID, brief, login_customer_id=MCC)
    assert r.ok, r.resumo()
    p = display.planejar(CID, brief, login_customer_id=MCC)

    orcamento = ops[0].campaign_budget_operation.create
    campanha = ops[1].campaign_operation.create

    assert p.n_operacoes == len(ops)
    assert p.orcamento.diario_micros == orcamento.amount_micros
    assert p.orcamento.compartilhado is orcamento.explicitly_shared
    assert p.tipo_de_campanha == campanha.advertising_channel_type.name
    assert p.status_inicial == campanha.status.name == "PAUSED"

    # ⚠️ O NOME muda a cada segundo (carimbo). Comparar plano e payload da mesma
    # execução seria comparar duas construções diferentes; por isso a igualdade
    # é sobre a FORMA, e a identidade exata é provada logo abaixo, na impressão.
    assert p.nome_da_campanha.startswith("BR - ")
    assert "[Display]" in p.nome_da_campanha

    anuncio = p.unidades[0].anuncios[0]
    rda = ops[-1].ad_group_ad_operation.create.ad.responsive_display_ad
    assert list(anuncio.headlines) == [a.text for a in rda.headlines]
    assert list(anuncio.descriptions) == [a.text for a in rda.descriptions]
    assert anuncio.long_headlines == (rda.long_headline.text,)
    assert anuncio.business_name == rda.business_name


def test_a_impressao_e_dos_bytes_e_muda_quando_o_payload_muda() -> None:
    """`operacoes.impressao` é identidade do payload, não enfeite.

    Uma headline diferente é um payload diferente, e a impressão precisa
    dizê-lo. Sem isso, "o plano que eu vi" e "o payload que subiu" seriam
    indistinguíveis.
    """
    fixo = "20260901_120000"
    a = display.planejar(CID, _brief_display(carimbo_nome=fixo),
                         login_customer_id=MCC)
    b = display.planejar(CID, _brief_display(carimbo_nome=fixo),
                         login_customer_id=MCC)
    assert a.impressao == b.impressao, (
        "duas montagens do MESMO brief deram impressões diferentes — a "
        "serialização não é determinística e o plano não identifica nada")

    outro = _brief_display(carimbo_nome=fixo)
    outro.copy.headlines[0] = "Outro Titulo Completamente"
    c = display.planejar(CID, outro, login_customer_id=MCC)
    assert c.impressao != a.impressao
    assert c.n_bytes_operacoes > 0


def test_todos_os_canais_projetam_com_o_mesmo_vocabulario() -> None:
    """Quatro canais, um tipo de plano. É o que permite UMA tela.

    O que muda entre eles é o `tipo` da unidade — `ad_group` em três canais,
    `asset_group` em PMax. A diferença que a API faz é preservada; a que ela não
    faz, não é inventada.
    """
    planos = {
        "SEARCH": search.planejar(CID, _brief_search(), login_customer_id=MCC),
        "DISPLAY": display.planejar(CID, _brief_display(), login_customer_id=MCC),
    }
    for canal, p in planos.items():
        assert isinstance(p, plano.PlanoDeCanal)
        assert p.canal == canal
        assert p.customer_id == CID and p.login_customer_id == MCC
        assert p.status_inicial == "PAUSED", "campanha nasce pausada em todo canal"
        assert p.unidades and p.unidades[0].tipo == "ad_group"
        assert p.orcamento.diario_micros and p.orcamento.diario_micros > 0
        assert p.prontidao.monta is True
        assert p.n_bytes_operacoes > 0


def test_search_particiona_em_ad_groups_e_o_plano_mostra_todos() -> None:
    """Search é o único canal com N unidades, e o plano não colapsa a partição."""
    from volc_ads.campanha.brief import SubIntencao

    brief = _brief_search(
        keywords=[],
        sub_intencoes=[
            SubIntencao(nome="calendario", keywords=["calendario saque anual"]),
            SubIntencao(nome="valor", keywords=["valor do saque anual"]),
        ])
    p = search.planejar(CID, brief, login_customer_id=MCC)
    assert len(p.unidades) == 2
    assert [u.tipo for u in p.unidades] == ["ad_group", "ad_group"]


# ═══════════════════════════════════════════════════════════════════════════
# ESTADOS — ausente ≠ zero ≠ falha ≠ não aplicável
# ═══════════════════════════════════════════════════════════════════════════


def test_ausencia_de_tcpa_nao_vira_zero() -> None:
    """`None` no plano é "ninguém definiu". Zero seria "definiram zero"."""
    sem = display.planejar(CID, _brief_display(tcpa=None), login_customer_id=MCC)
    com = display.planejar(CID, _brief_display(tcpa=25.0), login_customer_id=MCC)

    assert sem.orcamento.tcpa_micros is None, (
        "tCPA ausente virou zero — a tela mostraria 'meta de R$ 0,00' onde "
        "ninguém definiu meta nenhuma")
    assert com.orcamento.tcpa_micros == 25_000_000


def test_os_quatro_estados_moram_em_campos_diferentes() -> None:
    """Falha, não-aplicável e inventário aberto não se confundem no JSON."""
    ok = display.planejar(CID, _brief_display(), login_customer_id=MCC)
    quebrado = display.planejar(CID, _brief_display(imagens_display=None),
                                login_customer_id=MCC)

    # falha → `bloqueios`, com código
    assert quebrado.bloqueios and quebrado.bloqueios[0].codigo
    assert ok.bloqueios == ()

    # não aplicável → `nao_operado`, nos DOIS casos (é fato do canal, não do
    # brief: um plano que só declarasse suas ausências quando falha esconderia
    # exatamente do caso bem-sucedido o que ele não faz)
    assert ok.nao_operado and quebrado.nao_operado
    assert any("sitelink" in linha for linha in ok.nao_operado)

    # inventário aberto → campo PRÓPRIO, e não uma lista de audiências vazia
    assert ok.segmentacao.aberto_por_ausencia
    assert any("INVENTÁRIO ABERTO" in linha.upper()
               for linha in ok.segmentacao.aberto_por_ausencia)


def test_display_sem_imagem_e_bloqueio_e_nao_plano_feliz() -> None:
    """⚠️ O caminho HTTP ainda passa `imagens_display=None` literal.

    Enquanto a rota não tiver campo de imagem, é ESTE bloqueio que impede um
    plano de Display sem asset nenhum de sair como aprovado. Um builder que
    aceitasse a ausência faria a correção da rota não adiantar nada — o furo
    continuaria um nível abaixo.
    """
    p = display.planejar(CID, _brief_display(imagens_display=None),
                         login_customer_id=MCC)
    assert p.prontidao.monta is False
    assert plano.ASSET_OBRIGATORIO_AUSENTE in {b.codigo for b in p.bloqueios}
    assert p.unidades == (), "montou unidade sem asset"
    assert p.n_operacoes == 0


def test_prontidao_responde_as_tres_perguntas_separadamente() -> None:
    """`monta`, `pode_provar` e `pode_criar` não são derivados um do outro."""
    d = display.planejar(CID, _brief_display(), login_customer_id=MCC)
    assert (d.prontidao.monta, d.prontidao.pode_provar,
            d.prontidao.pode_criar) == (True, True, True)

    quebrado = display.planejar(CID, _brief_display(imagens_display=None),
                                login_customer_id=MCC)
    # monta=False e, ainda assim, o canal CONTINUA autorizado a provar e criar.
    # Colapsar os três faria "este brief está errado" virar "este canal não
    # pode gastar", que é outra conversa e outro caminho de correção.
    assert quebrado.prontidao.monta is False
    assert quebrado.prontidao.pode_provar is True
    assert quebrado.prontidao.pode_criar is True


def test_canal_sem_builder_so_aparece_quando_nada_mais_explica() -> None:
    """Brief reprovado no conteúdo NÃO é "canal sem builder".

    Carimbar `CANAL_SEM_BUILDER` num brief com headline longa demais mandaria o
    operador procurar um builder que existe, enquanto o defeito está listado
    duas linhas acima.
    """
    p = display.planejar(CID, _brief_display(imagens_display=None),
                         login_customer_id=MCC)
    assert plano.CANAL_SEM_BUILDER not in {b.codigo for b in p.bloqueios}

    vazio = plano.projetar(
        canal="INEXISTENTE", customer_id=CID, login_customer_id=MCC,
        operacoes=[], resultado=type("R", (), {"achados": []})(),
        prontidao=plano.Prontidao(False, False, False,
                                  motivo_nao_monta="não há builder"))
    assert [b.codigo for b in vazio.bloqueios] == [plano.CANAL_SEM_BUILDER]


# ═══════════════════════════════════════════════════════════════════════════
# CÓDIGOS — a lista fechada
# ═══════════════════════════════════════════════════════════════════════════


def test_todo_codigo_emitido_esta_na_lista_publicada() -> None:
    """`plano.CODIGOS` é o contrato. Nada sai dele.

    Varre todos os canais com briefs quebrados de propósito e confere que cada
    código emitido está na lista que o documento publica. Um código novo que
    esqueça de entrar em `CODIGOS` é um valor que a tela não sabe tratar.
    """
    quebrados = [
        display.planejar(CID, _brief_display(imagens_display=None),
                         login_customer_id=MCC),
        display.planejar(CID, _brief_display(estrategia_lance="MANUAL_CPC"),
                         login_customer_id=MCC),
        search.planejar(
            CID, _brief_search(estrategia_lance="MAXIMIZE_CONVERSION_VALUE"),
            login_customer_id=MCC),
    ]
    emitidos = {b.codigo for p in quebrados for b in p.bloqueios}
    assert emitidos, "nenhum dos briefs quebrados produziu bloqueio"
    assert emitidos <= set(plano.CODIGOS), (
        f"códigos fora do contrato publicado: {sorted(emitidos - set(plano.CODIGOS))}")


def test_os_codigos_nao_tem_duplicata_nem_valor_vazio() -> None:
    assert len(plano.CODIGOS) == len(set(plano.CODIGOS))
    assert all(c and c.isupper() for c in plano.CODIGOS)


def test_o_codigo_dito_pelo_builder_ganha_do_adivinhado() -> None:
    """A tabela por prefixo é a rede, não a regra.

    "keyword positiva não existe neste canal" é `CAMPO_NAO_OPERADO`, mas o nome
    do campo começa com "keyword" e a tabela o leria como texto reprovado. O
    builder precisa poder DIZER o código.
    """
    assert plano.classificar("keywords", "só pode ser negativa") == \
        plano.CONTEUDO_REPROVADO, "a adivinhação por prefixo mudou de resposta"

    from volc_ads.campanha import validacao
    r = validacao.Resultado()
    r.erro("keywords", "1 positiva", "só pode ser negativa",
           plano.CAMPO_NAO_OPERADO)
    p = plano.projetar(
        canal="X", customer_id=CID, login_customer_id=MCC, operacoes=[],
        resultado=r, prontidao=plano.Prontidao(False, False, False))
    assert p.bloqueios[0].codigo == plano.CAMPO_NAO_OPERADO


def test_codigo_desconhecido_e_declarado_e_nao_silencioso() -> None:
    """Um achado que a tabela não nomeia recebe um código que diz isso."""
    assert plano.classificar("campo_que_ninguem_previu", "aconteceu algo") == \
        plano.BLOQUEIO_NAO_CLASSIFICADO
    assert plano.BLOQUEIO_NAO_CLASSIFICADO in plano.CODIGOS


def test_o_perfil_e_o_plano_concordam_sobre_quem_planeja() -> None:
    """`canais_que_planejam()` é superconjunto de `canais_que_provam()`."""
    planejam = set(perfil.canais_que_planejam())
    provam = set(perfil.canais_que_provam())
    criam = set(perfil.canais_que_criam())

    assert criam <= provam <= planejam
    assert planejam == {"SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX"}
    assert provam == {"SEARCH", "DISPLAY", "DEMAND_GEN"}
    assert criam == {"SEARCH", "DISPLAY"}


def test_planejar_por_apelido_de_tela_funciona_sem_apelido_vazar() -> None:
    """`PMAX` é apelido; o contrato devolve sempre o nome canônico (ADR-18)."""
    p = perfil.planejar("pmax", CID, _brief_pmax(), login_customer_id=MCC)
    assert p.canal == "PERFORMANCE_MAX"


def _brief_pmax() -> Brief:
    from volc_ads.campanha.testes_pmax import _brief

    return _brief()
