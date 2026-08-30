"""O quadro de alertas sem GAQL — e as quatro provas de que ele não consulta.

⚠️ ESTE ARQUIVO EXISTE POR CAUSA DE UM CUSTO MEDIDO. Em 24/08/2026,
`GET /api/trafego/alertas` rodava ~5 consultas GAQL **por conta** em tempo de
render, e o `Layout` monta o sino em toda página do produto. Abrir o Pautador
custava rede para o Google. O gate desta fase é que isso pare de acontecer, e um
gate que se verifica lendo o código não é gate: é combinado.

As provas aqui são ARMADILHAS NO CAMINHO, não asserções sobre intenção. Um
`MetaPathFinder` é instalado em `sys.meta_path` e explode se qualquer coisa
tentar importar `volc_ads` ou `google.ads` durante a requisição — e os módulos
já carregados são retirados de `sys.modules` antes, senão um import já resolvido
não passaria pelo `meta_path` e o teste ficaria verde por acidente.

São quatro caminhos, e cada um é uma tela real:

  1. render de `/trafego`         → `GET /api/trafego/inventario`
  2. render do sino               → `GET /api/trafego/inventario/alertas`
  3. abertura da aba Atenção      → `GET /api/trafego/inventario?atencao=true`
  4. a ação explícita             → `POST /api/trafego/inventario/atualizar`

O quarto é o inverso dos três primeiros: ele PROVA que a atualização manual é o
único caminho que pode consultar. Sem ele, os outros três passariam num sistema
que simplesmente não consegue mais falar com o Google — e aí a suíte estaria
verde por quebra, não por conserto.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.seguranca.identidade import (Identidade, exigir_admin, exigir_servico,
                                      exigir_usuario)
from app.trafego import alertas as alr
from app.trafego import dominio as dom
from app.trafego import inventario as inv

AGORA = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
CONTA = "8017851692"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _iso(minutos_atras: float) -> str:
    return (AGORA - timedelta(minutes=minutos_atras)).isoformat()


def _uuid(kid: str) -> str:
    from app.trafego.sincronizador import volc_campaign_id

    return volc_campaign_id(CONTA, kid)


# ── dublês ──────────────────────────────────────────────────────────────────


def _conta(cid: str = CONTA, **kw: Any) -> Dict[str, Any]:
    """Uma linha de `trafego_snapshot_conta`, com as colunas reais."""
    base = {
        "customer_id": cid, "nome": f"conta {cid}",
        "tentativa_em": _iso(6), "tentativa_resultado": "ok",
        "tentativa_motivo": None, "tentativa_duracao_ms": 90,
        "leitura_boa_em": _iso(6), "leitura_boa_campanhas": 1,
    }
    base.update(kw)
    return base


def _campanha(kid: str, **kw: Any) -> Dict[str, Any]:
    """`trafego_campanha` ⋈ `trafego_campanha_espelho`, já achatadas.

    ⚠️ `presenca` NULA é o caso normal — a CHECK do banco aceita os seis estados
    do ADR-13 **ou** NULL, e nenhum dos seis nomeia "está lá, sem ressalva".
    """
    base = {
        "volc_campaign_id": _uuid(kid), "customer_id": CONTA, "campaign_id": kid,
        "nome": f"campanha {kid}", "estado_externo": "ENABLED",
        "veiculacao": "SERVING", "canal": "SEARCH", "estrategia": "MANUAL_CPC",
        "lance_micros": 120_000, "verba_diaria_micros": 10_000_000,
        "impressoes": 1, "cliques": 0, "custo_micros": 0, "moeda": "BRL",
        "entrega_lida_em": _iso(6), "lido_em": _iso(6), "presenca": None,
    }
    base.update(kw)
    return base


def _ligada_ha(horas: float, kid: str,
               base: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
    """A transição que faz `horas_ligada` valer `horas`.

    `base` existe porque a ROTA não recebe relógio injetado — ela usa `now()`,
    como em produção. Ancorar a fixture em `AGORA` faria o teste de rota medir a
    distância até 24/08 e falhar amanhã, o que é uma falha por calendário e não
    por defeito.
    """
    quando = (base or AGORA) - timedelta(hours=horas)
    return {_uuid(kid): [{"ocorrido_em": quando.isoformat(),
                          "de": None, "para": "ENABLED"}]}


class FonteEmMemoria:
    """O snapshot de mentira. Registra tudo o que foi pedido."""

    def __init__(self, contas: List[Dict[str, Any]],
                 campanhas: List[Dict[str, Any]],
                 transicoes: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self._contas = contas
        self._campanhas = campanhas
        self._transicoes = transicoes or {}
        self.chamadas: List[str] = []

    async def contas(self) -> List[Dict[str, Any]]:
        self.chamadas.append("contas")
        return list(self._contas)

    async def campanhas(self) -> List[Dict[str, Any]]:
        self.chamadas.append("campanhas")
        return list(self._campanhas)

    async def transicoes_de_estado(
        self, volc_campaign_ids: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        self.chamadas.append("transicoes")
        return {k: v for k, v in self._transicoes.items() if k in set(volc_campaign_ids)}


async def _quadro(fonte: FonteEmMemoria) -> Dict[str, Any]:
    return (await alr.montar_quadro(fonte, agora=AGORA)).json()


# ===========================================================================
# 1. A projeção: `horas_ligada` sai do diário, não da conta
# ===========================================================================


@pytest.mark.anyio
async def test_horas_ligada_sai_do_diario_de_eventos():
    """O dado que obrigava a rota a consultar o Google agora está no snapshot.

    A varredura apenda a transição de estado em `trafego_evento`; "desde quando
    está ENABLED" vira uma leitura de Postgres. Era ESTE campo que não tinha
    coluna nenhuma e mantinha `/alertas` amarrada ao GAQL.
    """
    fonte = FonteEmMemoria([_conta()], [_campanha("241")], _ligada_ha(30, "241"))
    corpo = await _quadro(fonte)

    assert len(corpo["alertas"]) == 1
    assert corpo["alertas"][0]["horas_ligada"] == pytest.approx(30.0, abs=0.01)
    assert fonte.chamadas == ["contas", "campanhas", "transicoes"]


@pytest.mark.anyio
async def test_sem_transicao_no_diario_horas_ligada_e_null_e_nao_zero():
    """Regra B no campo mais perigoso do quadro.

    Uma campanha que já estava ligada antes de o diário existir tem estado
    conhecido e antiguidade DESCONHECIDA. Chamar isso de "ligada há 0 horas"
    faria uma campanha parada há um mês parecer recém-criada — e o alerta, que
    depende de `horas_ligada >= 24`, nunca dispararia para ela.

    Por isso `None`, e por isso `merece_alerta` recusa: não alertar é o modo
    honesto de falhar quando não se sabe desde quando.
    """
    fonte = FonteEmMemoria([_conta()], [_campanha("241")], {})
    corpo = await _quadro(fonte)

    assert corpo["alertas"] == []
    assert alr.horas_ligada([], AGORA) is None


@pytest.mark.anyio
async def test_a_ultima_transicao_manda_e_pausada_nao_conta_horas():
    """Ligada, pausada, religada: valem as horas desde a ÚLTIMA religada."""
    transicoes = [
        {"ocorrido_em": (AGORA - timedelta(hours=90)).isoformat(),
         "de": None, "para": "ENABLED"},
        {"ocorrido_em": (AGORA - timedelta(hours=50)).isoformat(),
         "de": "ENABLED", "para": "PAUSED"},
        {"ocorrido_em": (AGORA - timedelta(hours=30)).isoformat(),
         "de": "PAUSED", "para": "ENABLED"},
    ]
    assert alr.horas_ligada(transicoes, AGORA) == pytest.approx(30.0, abs=0.01)
    # E a ordem em que os eventos chegam não muda a resposta.
    assert alr.horas_ligada(list(reversed(transicoes)), AGORA) == pytest.approx(
        30.0, abs=0.01)
    # Terminando em PAUSED, a pergunta não se aplica.
    assert alr.horas_ligada(transicoes[:2], AGORA) is None


@pytest.mark.anyio
async def test_o_que_nao_e_derivavel_sai_null_e_o_quadro_diz_o_que_nao_sabe():
    """Nem reduzir a tela nem inventar o dado: declarar a ignorância.

    `aprovacao_do_anuncio` vive numa entidade filha que a varredura comum não lê;
    `alteracoes[].origem` e `.quem` vivem no histórico da conta, que só uma
    consulta ao Google responderia. Os três saem `null` — e `nao_sabemos` diz
    isso em texto, para a tela poder escrever "não sei" em vez de um branco que
    parece "está tudo bem".
    """
    fonte = FonteEmMemoria([_conta()], [_campanha("241")], _ligada_ha(30, "241"))
    corpo = await _quadro(fonte)
    alerta = corpo["alertas"][0]

    assert alerta["aprovacao_do_anuncio"] is None
    assert alerta["alteracoes"][0]["origem"] is None
    assert alerta["alteracoes"][0]["quem"] is None
    # A transição em si É derivável, e ela viaja.
    assert alerta["alteracoes"][0]["para"] == "ENABLED"
    assert alerta["alteracoes"][0]["campo"] == "estado_externo"

    assert len(corpo["nao_sabemos"]) == 2
    assert any("aprovacao_do_anuncio" in t for t in corpo["nao_sabemos"])
    assert any("origem" in t for t in corpo["nao_sabemos"])


@pytest.mark.anyio
async def test_razoes_descrevem_o_que_o_espelho_mostra_sem_inferir_causa():
    """Cada linha é um FATO gravado. Nenhuma diz "está parada porque"."""
    fonte = FonteEmMemoria(
        [_conta()],
        [_campanha("241", veiculacao="PENDING", lance_micros=None)],
        _ligada_ha(30, "241"))
    razoes = (await _quadro(fonte))["alertas"][0]["razoes"]

    assert any("veiculação PENDING" in r for r in razoes)
    assert any("não leu lance" in r for r in razoes)
    assert not any("porque" in r for r in razoes)


@pytest.mark.anyio
async def test_o_sintoma_nao_e_impressoes_maior_que_zero():
    """[E-01, 20/08]: a maquininha tinha UMA impressão em 24 horas.

    O corte ingênuo (`impressoes > 0`) mandava reescrever o texto do anúncio —
    conselho errado com cara de diagnóstico, sobre uma campanha cujo problema
    era não entrar no leilão. O corte é `IMPRESSOES_PARA_CULPAR_O_ANUNCIO`.
    """
    uma = FonteEmMemoria([_conta()], [_campanha("241", impressoes=1)],
                         _ligada_ha(30, "241"))
    assert (await _quadro(uma))["alertas"][0]["sintoma"] == dom.SEM_IMPRESSAO

    muitas = FonteEmMemoria([_conta()], [_campanha("241", impressoes=500)],
                            _ligada_ha(30, "241"))
    alerta = (await _quadro(muitas))["alertas"][0]
    assert alerta["sintoma"] == dom.SEM_CLIQUE
    assert "o texto do anúncio" in alerta["revisar"]


@pytest.mark.anyio
async def test_campanha_pausada_nunca_vira_alerta_por_nao_entregar():
    """Ela não deveria entregar. Alertar encheria a lista de linhas corretas —
    e é assim que um alerta morre: ninguém mais olha."""
    fonte = FonteEmMemoria([_conta()],
                           [_campanha("241", estado_externo="PAUSED")],
                           _ligada_ha(30, "241"))
    corpo = await _quadro(fonte)
    assert corpo["alertas"] == []
    assert corpo["verificadas"] == 0


@pytest.mark.anyio
async def test_campanha_que_gastou_nao_e_alerta():
    fonte = FonteEmMemoria([_conta()],
                           [_campanha("241", custo_micros=4_300_000, impressoes=88)],
                           _ligada_ha(30, "241"))
    assert (await _quadro(fonte))["alertas"] == []


# ===========================================================================
# 2. As invariantes A–E, uma por teste nomeado
# ===========================================================================


@pytest.mark.anyio
async def test_invariante_A_nenhum_numero_sem_frescor():
    """Todo alerta carrega a data de onde ele saiu, e o envelope também.

    Um alerta afirma algo sobre AGORA ("não está gastando") a partir de um dado
    do passado. Sem a idade visível, um snapshot de ontem produz um alerta com
    cara de tempo real — pior que não alertar, porque o operador age.
    """
    fonte = FonteEmMemoria([_conta()], [_campanha("241")], _ligada_ha(30, "241"))
    corpo = await _quadro(fonte)

    assert corpo["leitura"]["idade_s"] == 360
    alerta = corpo["alertas"][0]
    assert alerta["leitura"]["idade_s"] == 360
    assert alerta["leitura"]["lido_em"].startswith("2026-08-24T11:54")

    # E a construção recusa número sem carimbo, na origem.
    with pytest.raises(dom.LeituraAusente):
        dom.Entrega(impressoes=1, custo_micros=0)


@pytest.mark.anyio
async def test_invariante_B_ausencia_e_null_nunca_zero():
    """Entrega não medida sai `null` — e aí não há alerta, porque "não medi"
    não é "não gastou"."""
    fonte = FonteEmMemoria(
        [_conta()],
        # Sem `entrega_lida_em` não há como carimbar número nenhum: a linha
        # inteira de entrega volta a ser desconhecida.
        [_campanha("241", entrega_lida_em=None, impressoes=None, cliques=None,
                   custo_micros=None)],
        _ligada_ha(30, "241"))
    corpo = await _quadro(fonte)

    assert corpo["alertas"] == [], "custo desconhecido não é custo zero"
    assert dom.merece_alerta(estado_externo="ENABLED", custo_micros=None,
                             horas_ligada=99) is False
    # Mas a linha PEDE ATENÇÃO: ligada e sem saber se entrega é exatamente o
    # estado que alguém precisa conferir.
    assert dom.pede_atencao(presenca_armazenada=None, estado_externo="ENABLED",
                            impressoes=None, cliques=None,
                            entrega_medida=False) is True
    # E zero medido continua sendo um fato: ele alerta.
    assert dom.merece_alerta(estado_externo="ENABLED", custo_micros=0,
                             horas_ligada=99) is True


@pytest.mark.anyio
async def test_invariante_C_falha_de_uma_conta_nao_contamina_a_outra():
    """A conta que falhou continua no quadro, com o carimbo da última leitura
    BOA e uma linha em `faltou`. A outra não é afetada."""
    boa = _conta("8017851692")
    caiu = _conta("3849678045", tentativa_resultado="falhou", tentativa_em=_iso(1),
                  tentativa_motivo="USER_PERMISSION_DENIED",
                  leitura_boa_em=_iso(600), leitura_boa_campanhas=1)
    da_caida = {**_campanha("900"), "customer_id": "3849678045",
                "volc_campaign_id": "b1e1a0c2-0000-5000-8000-000000000900"}

    fonte = FonteEmMemoria([boa, caiu], [_campanha("241"), da_caida],
                           {**_ligada_ha(30, "241")})
    corpo = await _quadro(fonte)

    por_conta = {c["customer_id"]: c for c in corpo["contas"]}
    assert por_conta["8017851692"]["frescor"] == inv.RECENTE
    assert por_conta["3849678045"]["frescor"] == inv.FALHOU
    assert por_conta["3849678045"]["erro"] == "USER_PERMISSION_DENIED"
    # O último dado bom da conta que caiu continua visível, com a idade DELE.
    assert por_conta["3849678045"]["leitura"]["idade_s"] == 600 * 60

    assert corpo["parcial"] is True
    assert [f["customer_id"] for f in corpo["faltou"]] == ["3849678045"]
    # O envelope é `parcial`, nunca `falhou`: uma de duas caiu.
    assert corpo["frescor"] == inv.PARCIAL


@pytest.mark.anyio
async def test_invariante_C_a_campanha_da_conta_que_caiu_diz_que_nao_se_sabe():
    """Presença vira `sincronizacao_falhou`, e a razão aparece por escrito."""
    caiu = _conta(tentativa_resultado="falhou", tentativa_em=_iso(1),
                  tentativa_motivo="deadline exceeded",
                  leitura_boa_em=_iso(600), leitura_boa_campanhas=1)
    fonte = FonteEmMemoria([caiu], [_campanha("241")], _ligada_ha(30, "241"))
    alerta = (await _quadro(fonte))["alertas"][0]

    assert alerta["presenca"] == inv.SINCRONIZACAO_FALHOU
    assert any("última varredura desta conta falhou" in r for r in alerta["razoes"])


def test_invariante_D_idempotencia_permite_retry_depois_do_fracasso():
    """Só sucesso é memorizado — e a garantia é estrutural, não uma condição.

    O evento de rodada é apendado APENAS no fim do caminho feliz, então a
    existência dele já significa "deu certo". A prova comportamental (falha →
    retry refaz → sucesso → retry não refaz) está em
    `test_trafego_sincronizador.py::test_idempotencia_nao_memoriza_fracasso`;
    o que se guarda aqui é que os dois caminhos não compartilham chave.
    """
    from app.trafego import sincronizador as sinc

    vid = _uuid("241")
    assert sinc.chave_da_rodada(vid) != alr.chave_de_estado(vid)
    assert alr.chave_de_estado(vid).startswith(alr.TIPO_ESTADO)


@pytest.mark.anyio
async def test_invariante_E_estado_desconhecido_degrada_e_nunca_vira_recente():
    """Um valor que ninguém reconhece não pode arrastar o quadro para cima.

    Frescor é a promessa de que o número na tela é novo. Uma promessa emitida
    por omissão não é promessa: se não sabemos a idade, "não sei" é `velho` —
    que faz o operador conferir — e nunca `recente`, que faz ele confiar.
    """
    assert dom.frescor_do_conjunto(["recente", "estado_do_futuro"]) == inv.VELHO
    assert dom.frescor_da_conta(resultado="quem_sabe", lido_em=AGORA,
                                campanhas=1, agora=AGORA) == inv.VELHO

    # E uma presença fora do vocabulário não vira um dos seis por engano.
    assert dom.presenca_projetada("inventado", conta_falhou=False) == \
        inv.CONTA_NAO_IDENTIFICADA

    # No quadro inteiro: conta com resultado ilegível não sai `recente`.
    fonte = FonteEmMemoria([_conta(tentativa_resultado="???")],
                           [_campanha("241")], _ligada_ha(30, "241"))
    corpo = await _quadro(fonte)
    assert corpo["contas"][0]["frescor"] != inv.RECENTE


# ===========================================================================
# 3. AS QUATRO PROVAS DE ZERO GAQL
# ===========================================================================


class BloqueioDeImport:
    """Explode se alguém tentar importar o SDK do Google durante a requisição.

    Armadilha no CAMINHO, e não asserção sobre intenção: não há como um módulo
    "só desta vez" carregar o SDK e o teste continuar verde.
    """

    ALVOS = ("volc_ads", "google.ads")

    def find_spec(self, fullname, path=None, target=None):  # noqa: D102
        for alvo in self.ALVOS:
            if fullname == alvo or fullname.startswith(alvo + "."):
                raise AssertionError(
                    f"um caminho de RENDER importou {fullname!r}. Abrir uma "
                    f"página do produto não pode custar rede para o Google "
                    f"(ADR-08)."
                )
        return None


class _SemGoogle:
    """Contexto que remove o SDK de `sys.modules` e arma o bloqueio.

    A remoção é o detalhe que faz a prova valer: um import já resolvido não
    passa pelo `meta_path`, e sem isto o teste ficaria verde por acidente.
    """

    def __enter__(self):
        self.guardados = {n: m for n, m in list(sys.modules.items())
                          if n == "volc_ads" or n.startswith("volc_ads.")
                          or n.startswith("google.ads")}
        for n in self.guardados:
            del sys.modules[n]
        self.bloqueio = BloqueioDeImport()
        sys.meta_path.insert(0, self.bloqueio)
        return self

    def __exit__(self, *exc):
        sys.meta_path.remove(self.bloqueio)
        sys.modules.update(self.guardados)
        return False


@pytest.fixture
def app_completo():
    """O app com os dois routers, dublês injetados e portões abertos."""
    from app.routers import trafego_inventario as rota
    from tests.test_trafego_sincronizador import (CONTA as CONTA_GADS, BuscaFalsa,
                                                  RepoFalso, linha_de_campanha,
                                                  linha_de_lance,
                                                  linha_de_metrica)

    class FonteDeInventarioFalsa:
        async def contas(self, filtros):
            return [_conta()]

        async def campanhas(self, plano):
            return [_campanha("241")]

        async def contagem(self, plano):
            return {CONTA: 1}

        async def contagem_em_atencao(self, plano):
            return 1

        async def contagem_por_natureza(self, plano):
            return 1, 0

    buscas: List[Any] = []

    def fabrica(conta):
        b = BuscaFalsa(campanhas=[linha_de_campanha("241")],
                       metricas=[linha_de_metrica("241", 1, 0, 0)],
                       lances=[linha_de_lance("241", "g1", 120_000)])
        buscas.append(b)
        return b

    # ⚠️ A rota usa `now()` — ela não recebe relógio injetado, e não receber é
    # o certo: um parâmetro de tempo numa rota de leitura é uma porta para
    # alguém "consertar" o frescor pelo lado de fora.
    agora_real = datetime.now(timezone.utc)
    fonte_de_alertas = FonteEmMemoria(
        [_conta(leitura_boa_em=agora_real.isoformat(),
                tentativa_em=agora_real.isoformat())],
        [_campanha("241", entrega_lida_em=agora_real.isoformat(),
                   lido_em=agora_real.isoformat())],
        _ligada_ha(30, "241", base=agora_real))

    rota.definir_fonte(FonteDeInventarioFalsa())
    rota.definir_fonte_de_alertas(fonte_de_alertas)
    rota.definir_varredura(RepoFalso(), fabrica)
    rota.definir_contas([CONTA_GADS])

    app = FastAPI()
    rota.registrar(app)
    ident = Identidade(sub="u1", email="op@volc", papel="ADMIN", origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: ident
    app.dependency_overrides[exigir_admin] = lambda: ident
    app.dependency_overrides[exigir_servico] = lambda: Identidade(
        sub="svc", email="", papel="SERVICO", origem="servico")

    yield app, rota, buscas

    rota.definir_fonte(None)
    rota.definir_fonte_de_alertas(None)
    rota.definir_varredura(None, None)
    rota.definir_contas(None)
    app.dependency_overrides.clear()


def test_render_de_trafego_nao_toca_no_google_ads(app_completo):
    """PROVA 1 — a listagem do inventário. É o corpo da página `/trafego`."""
    app, _, _ = app_completo
    with _SemGoogle(), TestClient(app) as cliente:
        r = cliente.get("/api/trafego/inventario")
    assert r.status_code == 200, r.text
    assert r.json()["contas"][0]["customer_id"] == CONTA


def test_render_do_sino_nao_toca_no_google_ads(app_completo):
    """PROVA 2 — o quadro de alertas, que o `Layout` monta em TODA página.

    Era esta rota que custava ~5 GAQL por conta a cada navegação.
    """
    app, _, _ = app_completo
    with _SemGoogle(), TestClient(app) as cliente:
        r = cliente.get("/api/trafego/inventario/alertas")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["alertas"][0]["horas_ligada"] == pytest.approx(30.0, abs=0.01)
    assert corpo["horas_ate_alertar"] == dom.HORAS_ATE_ALERTAR
    # Regra A no envelope: o quadro diz de quando ele é.
    assert corpo["frescor"] in inv.FRESCORES and corpo["leitura"] is not None


def test_abertura_da_aba_atencao_nao_toca_no_google_ads(app_completo):
    """PROVA 3 — a aba Atenção é `GET /inventario?atencao=true`."""
    app, _, _ = app_completo
    with _SemGoogle(), TestClient(app) as cliente:
        r = cliente.get("/api/trafego/inventario", params={"atencao": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["totais"]["atencao"] == 1


def test_so_a_atualizacao_explicita_pode_consultar_o_google(app_completo):
    """PROVA 4 — o inverso das outras três, e ela é indispensável.

    Sem esta, as três primeiras passariam num sistema que simplesmente perdeu a
    capacidade de falar com o Google: a suíte ficaria verde por quebra, não por
    conserto. Aqui a varredura manual É exercitada, e ela chama o leitor.

    O segundo bloco é o que impede a regressão silenciosa: se alguém acrescentar
    uma rota GET nova ao router, a lista abaixo muda e o teste falha — obrigando
    quem acrescentou a declarar de que lado da fronteira ela está.
    """
    app, _, buscas = app_completo

    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": CONTA, "janela": "LAST_7_DAYS"})
    assert r.status_code == 200, r.text
    assert buscas and buscas[0].consultas, (
        "a atualização manual não consultou nada — se ela também parou de "
        "falar com o Google, as outras provas não significam mais nada")
    assert r.json()["custo"]["consultas_gaql"] >= 1
    assert r.json()["escrita_permitida"] is False

    somente_leitura = {(m, r_.path) for r_ in app.routes
                       for m in getattr(r_, "methods", ())
                       if str(getattr(r_, "path", "")).startswith("/api/trafego")}
    assert somente_leitura == {
        ("GET", "/api/trafego/inventario"),
        ("GET", "/api/trafego/inventario/alertas"),
        ("GET", "/api/trafego/inventario/vocabulario"),
        ("POST", "/api/trafego/inventario/atualizar"),
        ("POST", "/api/trafego/inventario/sincronizacoes"),
        # ── vínculo campanha ↔ funil ────────────────────────────────────────
        #
        # Escrita, e escrita NOSSA: as duas gravam em `trafego_vinculo`, uma
        # tabela do VOLC. Nenhuma delas toca no Google — nem para ler.
        #
        # É a distinção que este teste existe para manter: "escreve" aqui
        # significa "escreve no nosso banco", e continua não havendo caminho
        # deste router para um `mutate` na conta de anúncio. A única rota que
        # fala com o Google é a varredura manual acima, e ela só faz SELECT.
        # Leitura pura, do snapshot: a página canônica de UMA campanha. Não
        # varre o inventário e não fala com o Google — as provas estão em
        # `test_trafego_inventario.py`.
        ("GET", "/api/trafego/campanhas/{volc_campaign_id}"),
        # Leitura pura, e do NOSSO banco: quais funis internos casam com esta
        # campanha. Sugere e não grava — quem grava é `POST /vinculos`, logo
        # abaixo. Não fala com o Google nem para ler: compara o snapshot já
        # lido com `pautador_funnel_runs`.
        ("GET", "/api/trafego/campanhas/{volc_campaign_id}/correspondencias"),
        ("POST", "/api/trafego/vinculos"),
        ("POST", "/api/trafego/vinculos/{vinculo_id}/desfazer"),
    }, ("uma rota nova apareceu no router. Se ela for de LEITURA, acrescente-a "
        "às provas de zero GAQL; se for de escrita, diga por quê aqui.")


def test_o_modulo_de_alertas_nao_importa_o_engine_no_topo():
    """A prova estática, que sobrevive a um dublê mal feito."""
    import ast
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[1]
    for relativo in ("app/trafego/alertas.py", "app/trafego/inventario.py",
                     "app/routers/trafego_inventario.py"):
        arvore = ast.parse((raiz / relativo).read_text(encoding="utf-8"))
        for no in arvore.body:  # só o nível de módulo
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                nomes = [a.name for a in no.names] + [getattr(no, "module", "") or ""]
                for n in nomes:
                    assert not n.startswith(("volc_ads", "google.ads")), \
                        f"{relativo} importa {n} no topo"


def test_o_quadro_nao_le_tabela_fora_do_schema_canonico():
    """As tabelas que a projeção declara tocar existem na migration."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[2]
    sql = (raiz / inv.SCHEMA_CANONICO).read_text(encoding="utf-8")
    for tabela in alr.TABELAS_DO_QUADRO:
        assert f"CREATE TABLE public.{tabela}" in sql


# ===========================================================================
# 4. A costura entre o sino e a aba: uma regra, dois consumidores
# ===========================================================================


def test_atencao_e_alerta_saem_da_mesma_regra_e_nao_de_uma_coluna():
    """A tabela antiga tinha um booleano GERADO chamado `atencao`.

    O schema canônico não tem, e não ter é melhor: a condição passa a ser
    derivada num lugar só, e o sino, a aba e o quadro não podem mais divergir
    porque três leituras da mesma coluna interpretaram o `NULL` diferente.
    """
    ligada_sem_impressao = {
        "presenca": None, "estado_externo": "ENABLED",
        "impressoes": 0, "cliques": 0, "entrega_lida_em": _iso(6),
    }
    assert inv.pede_atencao(ligada_sem_impressao, conta_falhou=False) is True
    assert dom.sintoma_de_entrega(estado_externo="ENABLED", impressoes=0,
                                  cliques=0) == dom.SEM_IMPRESSAO

    entregando = {**ligada_sem_impressao, "impressoes": 900, "cliques": 12}
    assert inv.pede_atencao(entregando, conta_falhou=False) is False

    # E a conta que caiu marca TUDO dela, porque nada pode ser afirmado.
    assert inv.pede_atencao(entregando, conta_falhou=True) is True
