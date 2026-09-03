"""AS 12 CONTRAPROVAS DA REAUDITORIA AO VIVO — o ato que faltava na espinha.

## O defeito medido que este arquivo trava

A barreira 3 exige, para deixar um destino elegível, um recibo cuja impressão
tenha sido carimbada SOBRE a página no ar (`fingerprint_scope == "live"`).
Nenhum caminho de produção emitia esse recibo: o portão 2 carimba o ARTEFATO —
o corpo que o motor escreveu — e a página no ar é esse corpo DENTRO do tema do
WordPress. Dois documentos diferentes por construção.

Consequência declarada em `docs/closure/paid-destination-policy-spine-v2/
REMAINING-RISKS.md`, seção 6bis: **NENHUM destino fica elegível para campanha**.
É fail-closed, portanto seguro — e é uma parada operacional total. Um portão que
nunca aprova é indistinguível de um portão quebrado, e a operação aprende a
contorná-lo, que é a pior falha possível num portão.

O que fechava o buraco não era afrouxar a régua: era o ATO EXPLÍCITO que
registra a aprovação ao vivo. Ele tem DUAS ETAPAS, e a separação É o assunto —
um portão que se autoaprova em silêncio não é portão:

    /reauditar/{page}/provar     lê ao vivo, avalia, devolve candidato + hash.
                                 ZERO escrita, em lugar nenhum.
    /reauditar/{page}/confirmar  RE-LÊ, RE-AVALIA, e só grava se a impressão
                                 nova bater com a que o operador viu.

## O que cada contraprova exige, e por que ela não passa por acidente

Cada prova aqui cobra o CÓDIGO ou o EFEITO exato, nunca um vermelho qualquer.
Um teste que só conferisse `elegivel is False` ficaria verde por causa de outro
achado — e continuaria verde no dia em que a regra que ele diz medir sumisse.
Onde existe o simétrico, ele está escrito: portão que só sabe reprovar é
desligado na primeira semana.

## Hermetismo

Nenhum socket (fixture autouse que derruba `connect`), nenhum Supabase real
(dublê em memória), nenhum WordPress, nenhum mutate no Google (sentinela de
arquivo inteiro em `volc_ads.subir.subir`). A leitura pública é injetada pelo
parâmetro `ler` nos testes de módulo e dublada em
`app.publisher_quality.fetch` nos testes de rota.

## Por que este arquivo IMPORTA fixtures de `test_barreira3_destino_de_campanha`

`HTML_CONFORME`, `_leitura`, `_instalar_linhas` e companhia já são as formas
EXATAS que o contrato produz e consome, e já foram provadas herméticas ali. Uma
segunda cópia envelheceria em separado — e no dia em que as duas divergissem, a
que mente é justamente a que ninguém está olhando.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.landing_policy import (
    CHAVE_DO_RECIBO,
    POLICY_CONTRACT_VERSION,
    PaginaObservada,
    elegibilidade_de_destino_de_campanha,
    impressao_canonica,
    recibo_da_url,
    url_canonica,
    versao_da_fonte,
)
from app.main import app
from app.publisher_quality import fetch as pqf
from app.routers import publicacao as pub
from app.routers import trafego

# ⚠️ A implementação da frente A. Enquanto ela não existir, este arquivo falha
# na COLETA — e essa falha é o vermelho pretendido, não um defeito do teste.
from app.redator import reauditoria as ra

from test_barreira3_destino_de_campanha import (  # noqa: E402
    HTML_CONFORME,
    IDENTIDADE,
    URL,
    _CORPO,
    _cenario_conforme,
    _corpo_de_subida,
    _html,
    _instalar_leitura,
    _instalar_linhas,
    _leitura,
    _preparar_subida,
    _provar,
    _recibo,
)
from test_trafego_canario import (  # noqa: E402
    _instalar_portas_hermeticas,
    _payload_da_rota,
)
from test_trafego_ledger import LedgerDeTeste  # noqa: E402
from test_trafego_plano_persistido import RepoDePlanoDeTeste  # noqa: E402


HOST_EXTERNO = "exemplo-externo.com.br"

#: A mesma página conforme, com UM hyperlink externo no CORPO — o defeito que
#: `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO` descreve.
HTML_LINK_NO_CORPO = _html(
    extra=f'<p>Veja <a href="https://{HOST_EXTERNO}/simulador">o simulador</a> ali.</p>'
)

#: O simétrico dela: a MESMA fonte, citada em prosa. A política proíbe a âncora,
#: não a citação — e uma régua que proibisse a citação proibiria escrever.
HTML_FONTE_EM_PROSA = _html(
    extra=f"<p>A fonte consultada foi o site {HOST_EXTERNO}, citada aqui em prosa.</p>"
)

#: O link que o TEMA renderiza. Mesmo host, mesma âncora, outra REGIÃO — e é a
#: região que decide o código, o próximo ato e o dono do conserto.
HTML_LINK_NO_TEMA = _html(
    extra=f'<footer class="site-footer"><a href="https://{HOST_EXTERNO}/tema">Tema</a></footer>'
)


# ── hermetismo, e as sentinelas de arquivo inteiro ─────────────────────────


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    """Um teste de portão que abre socket prova o site, não o portão."""

    def recusar_rede(_socket, _address):
        pytest.fail("uma contraprova da reauditoria tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


@pytest.fixture(autouse=True)
def _mutate_google_selado(monkeypatch: pytest.MonkeyPatch):
    """CONTRAPROVA 12, no arquivo inteiro: nenhum caminho alcança o mutate.

    Autouse e não por teste. Um `assert` de status devolvido não distingue
    "recusou" de "criou a campanha e depois reclamou" — só a sentinela
    distingue, e ela precisa valer para TODA rota exercitada aqui, inclusive as
    que ninguém desconfia que passem perto do Google.
    """
    try:
        from volc_ads import subir as sb
    except Exception:  # noqa: BLE001 — sem a lib do Google não há mutate possível
        return

    def nunca_subir(*_a, **_k):
        pytest.fail("um caminho da reauditoria alcançou volc_ads.subir — o mutate seria real")

    monkeypatch.setattr(sb, "subir", nunca_subir)


@pytest.fixture(autouse=True)
def _leituras_da_conta_desligadas(monkeypatch: pytest.MonkeyPatch):
    """As portas que `/provar` e `/subir` abrem para o Google por conta própria.

    Sem isto `_prontidao_do_lancamento` desce até o cliente `lru_cache` do Google
    Ads, que REFRESCA token antes de qualquer consulta — e a fixture de rede
    derrubaria o arquivo por um motivo que não é o dele. A exceção é o caminho
    honesto: é o que a rota produz quando a leitura não completa.
    """
    from app.trafego import contas as ct

    def _sem_metas(*_a, **_k):
        raise RuntimeError("leitura de metas desligada neste arquivo de teste")

    async def _sem_plano(*_a, **_k):
        return None

    monkeypatch.setattr(ct, "meta_de_conversao", _sem_metas)
    monkeypatch.setattr(trafego, "_plano_de_mensuracao", _sem_plano)


# ── a leitura pública, injetada ────────────────────────────────────────────


def _leitor(*, desktop: str = HTML_CONFORME, movel: str | None = None,
            rastreador: str | None = None, status: int = 200,
            saltos: list[dict] | None = None, erro: Exception | None = None):
    """Um dublê com a assinatura EXATA de `fetch_public_https_chain`.

    Ele escolhe o HTML pelo user-agent porque é o único jeito de exercitar
    cloaking sem servidor: cloaking É servir conteúdo diferente para quem se
    identifica como rastreador. O diário de agentes fica no atributo `agentes` —
    é ele que prova que as três leituras aconteceram.
    """
    agentes: list[str] = []

    def ler(url: str, *, user_agent: str = "", timeout: int = 20,
            max_bytes: int = 2_000_000) -> Dict[str, Any]:
        agentes.append(user_agent)
        if erro is not None:
            raise erro
        baixo = user_agent.lower()
        if "bot" in baixo or "crawler" in baixo or "spider" in baixo:
            html = rastreador if rastreador is not None else desktop
        elif "mobile" in baixo or "android" in baixo:
            html = movel if movel is not None else desktop
        else:
            html = desktop
        return _leitura(html, status=status, saltos=saltos, url=url)

    ler.agentes = agentes  # type: ignore[attr-defined]
    return ler


def _leitura_da_reauditoria(monkeypatch: pytest.MonkeyPatch, **kw: Any):
    """Instala o dublê de leitura no caminho que as ROTAS de reauditoria usam.

    ⚠️ Trocar `pqf.fetch_public_https_chain` NÃO alcança este caminho, e a razão
    é a assinatura: `ler` é um argumento com valor DEFAULT, e o default é
    resolvido no `def`, não na chamada. `trafego._ler_destino_ao_vivo` chama
    pelo atributo do módulo — ali o `setattr` funciona; aqui não funcionaria, e
    um teste que só trocasse `pqf` ficaria verde tendo aberto socket de verdade
    (a fixture de rede o derrubaria, mas por um motivo que esconderia este).

    Por isso o dublê entra pelos dois lugares: o atributo do módulo, para o que
    quer que passe por ele, e o `__kwdefaults__` das duas funções, que é o seam
    real de quem chama sem passar `ler`. `monkeypatch` restaura os dois.
    """
    ler = _leitor(**kw)
    monkeypatch.setattr(pqf, "fetch_public_https_chain", ler)
    for funcao in (ra.provar_destino, ra.confirmar_reauditoria):
        padroes = dict(funcao.__kwdefaults__ or {})
        assert "ler" in padroes, f"{funcao.__name__} deixou de aceitar `ler` injetável"
        padroes["ler"] = ler
        monkeypatch.setattr(funcao, "__kwdefaults__", padroes)
    return ler


@lru_cache(maxsize=None)
def _recibo_live_anterior(html: str = HTML_CONFORME) -> Dict[str, Any]:
    """O recibo `live` que uma reauditoria ANTERIOR desta página deixou.

    ⚠️ Ele é o estado de REGIME, e a distinção custou o achado central deste
    arquivo. `provar_destino` só consegue medir deriva contra um recibo do mesmo
    escopo; sem ele, `live_drift` é honestamente inobservável e
    `RECIBO_DE_APROVACAO_AUSENTE` reprova. As provas cujo assunto NÃO é o
    arranque partem daqui, para medirem o que dizem medir — o arranque tem
    prova própria, e é ela que está vermelha.
    """
    # ⚠️ `lru_cache` e não uma fábrica: `_recibo` carimba `time.time()` a cada
    # chamada, e duas cópias que diferem só no carimbo não são o MESMO recibo —
    # a prova da idempotência compararia dois objetos diferentes e ficaria verde
    # (ou vermelha) por um motivo que não é o dela.
    return _recibo(html, fingerprint_scope="live")


def _provar_modulo(**troca: Any) -> Any:
    """`provar_destino` no regime: página no ar com reauditoria anterior `live`."""
    argumentos: Dict[str, Any] = {
        "url": URL,
        "papel_do_motor": "LP",
        "recibo_anterior": _recibo_live_anterior(),
        "agora": time.time(),
        "ler": _leitor(),
    }
    argumentos.update(troca)
    return ra.provar_destino(**argumentos)


def _codigos(itens: List[Dict[str, Any]]) -> List[str]:
    return [str(i.get("code") or i.get("codigo") or "") for i in itens]


def _dono(itens: List[Dict[str, Any]], codigo: str) -> str:
    for item in itens:
        if (item.get("code") or item.get("codigo")) == codigo:
            return str(item.get("owner") or "")
    raise AssertionError(f"{codigo} não está entre {_codigos(itens)}")


# ── o Supabase de mentira, nas duas versões que o arquivo precisa ──────────


class SupaEspiao:
    """Guarda o que foi lido e APLICA o que foi gravado.

    Aplicar importa: a contraprova da idempotência precisa que a segunda
    confirmação enxergue o que a primeira gravou. Um dublê que só registrasse o
    PATCH deixaria a segunda chamada rodar contra o estado antigo — e a
    idempotência ficaria verde sem nunca ter sido exercitada.
    """

    enabled = True

    def __init__(self, tabelas: Dict[str, List[Dict[str, Any]]] | None = None) -> None:
        self.tabelas = tabelas or {}
        self.consultas: List[tuple] = []
        self.patches: List[Dict[str, Any]] = []

    async def select(self, tabela: str, params: Dict[str, Any]):
        self.consultas.append((tabela, params))
        return [dict(l) for l in self.tabelas.get(tabela, [])]

    async def patch(self, tabela: str, filtro: Dict[str, Any], valores: Dict[str, Any]):
        self.patches.append({"tabela": tabela, "filtro": filtro, "valores": valores})
        for linha in self.tabelas.get(tabela, []):
            linha.update(valores)
        return []

    async def insert(self, tabela: str, linhas: List[Dict[str, Any]]):
        raise AssertionError(f"insert inesperado em {tabela}: a reauditoria só faz PATCH")

    def paginas_publicadas(self) -> List[Dict[str, Any]]:
        linhas = self.tabelas.get(pub.TABELA_RUNS) or [{}]
        return [p for p in (linhas[0].get("paginas_publicadas") or []) if isinstance(p, dict)]


class SupaSentinela(SupaEspiao):
    """O mesmo dublê, com a ESCRITA armadilhada.

    É esta classe que separa "a rota é somente leitura" de "a rota devolveu 200
    e escreveu de lado". O status sozinho nunca provou nada sobre efeito.
    """

    async def patch(self, tabela: str, filtro: Dict[str, Any], valores: Dict[str, Any]):
        pytest.fail(f"a rota gravou em {tabela} num caminho que devia ser só leitura: "
                    f"{sorted(valores)}")

    async def insert(self, tabela: str, linhas: List[Dict[str, Any]]):
        pytest.fail(f"a rota inseriu em {tabela} num caminho que devia ser só leitura")


PERFIL_WP = {
    "project_id": 3, "wp_url": "https://portalmundomais.com.br", "wp_username": "volc",
    "wp_app_password_enc": "cifrado", "conexao_ok": True,
    "post_type": "rec", "lp_post_type": "r",
}

ROTA_PROVAR = "/api/publicacao/redator/runs/1/reauditar/1/provar"
ROTA_CONFIRMAR = "/api/publicacao/redator/runs/1/reauditar/1/confirmar"


def _run_publicado() -> Dict[str, Any]:
    return {
        "id": 1, "opportunity_id": 7, "project_id": 3,
        "run_id": "saque-anual-20260903", "status": "done", "modo": "publicado",
        "artefatos": {"pasta": "saque-anual-20260903"},
        "paginas_publicadas": [{
            "page_number": 1, "url_wp": URL, "post_id": 101,
            "status_wp": "publish", "role": "LP", "slug": "saque-anual",
            # A reauditoria ANTERIOR desta página. Ver `_recibo_live_anterior`.
            CHAVE_DO_RECIBO: _recibo_live_anterior(),
        }],
    }


def _estado_do_run() -> Dict[str, Any]:
    return {
        "run_id": "saque-anual-20260903",
        "plan": {"pages": [{"page_number": 1, "slug": "saque-anual", "role": "LP",
                            "h1_title": "Guia informativo"}]},
        "drafts": {"1": {"page_number": 1, "format": "gutenberg", "content": HTML_CONFORME}},
        "step_status": {"build_p1": {"status": "OK"}},
        "published": {"1": {"page_number": 1, "url_wp": URL, "post_id": 101}},
    }


def _montar_mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, supa: SupaEspiao):
    run_dir = tmp_path / "saque-anual-20260903"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "state.json").write_text(
        json.dumps(_estado_do_run(), ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(pub, "_supa", lambda: supa)
    monkeypatch.setattr(pub, "_pasta_do_run", lambda linha: run_dir)

    async def buscar(_supa, _project_id):
        return dict(PERFIL_WP)

    monkeypatch.setattr(pub, "_buscar", buscar)
    return run_dir


@pytest.fixture()
def cliente() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def mundo_espiao(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """O run no disco, o Supabase que APLICA o que a rota grava."""
    supa = SupaEspiao({pub.TABELA_RUNS: [_run_publicado()]})
    run_dir = _montar_mundo(monkeypatch, tmp_path, supa)
    _leitura_da_reauditoria(monkeypatch)
    return {"supa": supa, "run_dir": run_dir, "monkeypatch": monkeypatch}


@pytest.fixture()
def mundo_selado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """O mesmo run, com a ESCRITA armadilhada. Para os caminhos de só-leitura."""
    supa = SupaSentinela({pub.TABELA_RUNS: [_run_publicado()]})
    run_dir = _montar_mundo(monkeypatch, tmp_path, supa)
    _leitura_da_reauditoria(monkeypatch)
    return {"supa": supa, "run_dir": run_dir, "monkeypatch": monkeypatch}


def _prova_da_rota(cliente: TestClient) -> Dict[str, Any]:
    r = cliente.post(ROTA_PROVAR)
    assert r.status_code == 200, r.text
    return r.json()["prova"]


def _recibo_live_de(html: str = HTML_CONFORME) -> Dict[str, Any]:
    """Um recibo `live` produzido pelo ATO de reauditoria, não escrito à mão.

    ⚠️ É de propósito que ele venha de `confirmar_reauditoria` e não de uma
    fixture literal. Um recibo escrito à mão prova que a barreira 3 aceita o
    formato que o teste inventou; este prova que ela aceita o que o código
    EMITE — que é a pergunta que a rodada inteira existe para responder.
    """
    agora = time.time()
    anterior = _recibo_live_anterior(html)
    prova = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=anterior,
                              agora=agora, ler=_leitor(desktop=html))
    recibo, _ = ra.confirmar_reauditoria(
        prova_esperada=prova.impressao_da_prova, url=URL, papel_do_motor="LP",
        recibo_anterior=anterior, agora=agora, ler=_leitor(desktop=html))
    return recibo


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 1 — recibo de ARTEFATO nunca substitui recibo LIVE
# ═══════════════════════════════════════════════════════════════════════════


def test_recibo_de_artefato_nao_torna_o_destino_elegivel(monkeypatch: pytest.MonkeyPatch):
    """O recibo do portão 2 impressiona o corpo que o motor escreveu.

    A página no ar é esse corpo DENTRO do tema do WordPress: outro documento,
    por construção. Aceitar o recibo de artefato como aprovação ao vivo seria
    dizer que alguém verificou o que ninguém olhou — e o motivo devolvido tem
    de ser o VERDADEIRO ("ninguém reauditou ao vivo"), nunca o falso
    ("o conteúdo mudou"), que mandaria o operador consertar a página certa pelo
    diagnóstico errado.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo(fingerprint_scope="artifact"))
    _instalar_leitura(monkeypatch)

    d = _provar()

    assert d["destino"]["elegivel"] is False
    motivos = " ".join(d["destino"]["motivos"])
    assert "live_drift" in motivos, motivos
    assert "DERIVA_AO_VIVO" not in motivos, motivos
    assert d["autorizacao"]["plano_impressao"] is None, "o selo saiu com recibo de artefato"


def test_o_recibo_live_da_reauditoria_e_o_que_torna_o_destino_elegivel(
    monkeypatch: pytest.MonkeyPatch,
):
    """O SIMÉTRICO da prova acima — e a razão de existir desta rodada inteira.

    Trocar o escopo do recibo é a ÚNICA diferença entre este cenário e o
    anterior. Sem esta prova, as onze restantes descreveriam um portão que
    apenas aprendeu mais um jeito de dizer não: a `REMAINING-RISKS` 6bis mede
    que, sem produtor de recibo `live`, NENHUM destino fica elegível.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo_live_de(HTML_CONFORME))
    _instalar_leitura(monkeypatch)

    d = _provar()

    assert d["destino"]["elegivel"] is True, d["destino"]["motivos"]
    assert d["autorizacao"]["plano_impressao"], "o selo não saiu para um destino reauditado"


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 2 — ausência de recibo live permanece inelegível
# ═══════════════════════════════════════════════════════════════════════════


def test_ausencia_de_recibo_live_permanece_inelegivel(monkeypatch: pytest.MonkeyPatch):
    """Ninguém aprovou esta URL — e ausência entra no portão COMO ausência.

    O código é `RECIBO_DE_APROVACAO_AUSENTE`, e cobrá-lo pelo nome é o que
    impede esta prova de ficar verde por causa de outro achado qualquer. A
    reauditoria acrescentou um produtor de recibo; ela não pode ter
    acrescentado um caminho em que a falta de recibo vira silêncio.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=None)
    _instalar_leitura(monkeypatch)

    d = _provar()

    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_APROVACAO_AUSENTE" in d["destino"]["bloqueios"]
    assert d["autorizacao"]["plano_impressao"] is None


def test_o_recibo_gravado_e_encontrado_pela_url_canonica(monkeypatch: pytest.MonkeyPatch):
    """O simétrico da ausência, no ponto exato em que ela é resolvida.

    `recibo_da_url` casa por URL CANÔNICA: um destino do Google chega com
    `gclid` grudado, e um recibo só encontrável com a query exata é um recibo
    que nunca é encontrado. Gravar o recibo certo numa chave que ninguém acha
    reproduziria a parada operacional com outro nome.
    """
    recibo = _recibo_live_de(HTML_CONFORME)
    publicadas, mudou = ra.aplicar_recibo([{"page_number": 1, "url_wp": URL}], URL, recibo)

    assert mudou is True
    com_rastreio = f"{URL}?gclid=EAIaIQobChMI&utm_source=google"
    assert recibo_da_url(publicadas, com_rastreio) == recibo
    assert url_canonica(com_rastreio) == url_canonica(URL)


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 3 — a prova LIMPA gera candidato e NÃO grava
# ═══════════════════════════════════════════════════════════════════════════


def test_prova_live_limpa_gera_candidato_com_escopo_live():
    """O caminho verde do ato novo. Sem ele, a rodada não fecha a parada.

    Três exigências, e nenhuma delas é decorativa: a leitura é TRIPLA (sem o par
    rastreador/usuário a verificação de cloaking sai `unavailable` e reprova), o
    candidato sai carimbado `live` (é o escopo que a barreira 3 cobra) e o papel
    avaliado é `paid_destination` (o ponto de campanha FORÇA o papel).
    """
    ler = _leitor()
    prova = _provar_modulo(ler=ler)

    assert prova.elegivel is True, prova.motivos
    assert prova.bloqueios == [], _codigos(prova.bloqueios)
    assert prova.desconhecidos == [], prova.desconhecidos
    assert prova.recibo_candidato["fingerprint_scope"] == "live"
    assert prova.recibo_candidato["paid_destination_ready"] is True
    assert prova.recibo_candidato["role"] == "paid_destination"
    # ⚠️ O PONTO É `live_audit`, e ele nasceu da correção focal desta rodada.
    # Avaliar no ponto de CAMPANHA exigia aprovação anterior de um ato de
    # aprovação — circular, e foi o que deixou o ciclo do recibo `live` sem
    # entrada. Ver `PontoDePortao.AUDITORIA_AO_VIVO`.
    assert prova.recibo_candidato["gate_point"] == "live_audit"
    assert len(prova.impressao_da_prova) == 64, prova.impressao_da_prova
    agentes = [a.lower() for a in ler.agentes]  # type: ignore[attr-defined]
    assert len(agentes) == 3, agentes
    # ⚠️ AdsBot, e não Googlebot. Quem busca a página de destino de um anúncio é
    # o AdsBot; sem um user-agent de rastreador na trinca, `cloaking` sai
    # `unavailable` e o portão reprova por ausência de evidência.
    assert any("adsbot" in a or "googlebot" in a for a in agentes), agentes


def test_a_primeira_reauditoria_de_uma_pagina_precisa_poder_ficar_verde():
    """⚠️ O ARRANQUE — o ciclo que esta rodada precisava abrir e não abriu.

    ## O ciclo, medido

    `provar_destino(recibo_anterior=None)` avalia no ponto de campanha, onde
    `varrer_recibo` emite `RECIBO_DE_APROVACAO_AUSENTE` e `live_drift` sai
    desconhecido — as duas coisas certas, porque sem aprovação do mesmo escopo
    a deriva é mesmo inobservável. Daí `elegivel=False`; daí
    `confirmar_reauditoria` levanta `ReauditoriaRecusada`; daí NADA é gravado;
    daí a próxima reauditoria também parte de `recibo_anterior=None`.

    `reauditoria.py:531` é a ÚNICA linha do backend que carimba
    `fingerprint_scope="live"` (medido: `grep escopo_da_impressao` em `app/`), e
    ela só é alcançada por quem já tem um recibo `live`. O ciclo não tem
    entrada.

    ## Por que isto é a prova, e não uma preferência

    A `REMAINING-RISKS` 6bis mede que, sem produtor de recibo `live`, NENHUM
    destino fica elegível — parada operacional total. Enquanto o arranque não
    existir, a rodada trocou o produtor ausente por um produtor inalcançável, e
    a parada continua exatamente onde estava. É fail-closed, e é vermelho.
    """
    prova = _provar_modulo(recibo_anterior=None)

    assert prova.elegivel is True, prova.motivos


def test_a_rota_provar_e_somente_leitura(cliente: TestClient, mundo_selado):
    """SENTINELA. O 200 sozinho não distingue "provou" de "provou e gravou".

    A separação em duas etapas é o assunto: se o `/provar` já persistisse o
    recibo, a confirmação seria enfeite e o portão estaria se autoaprovando em
    silêncio. `SupaSentinela` chama `pytest.fail` em qualquer escrita.
    """
    prova = _prova_da_rota(cliente)

    assert prova["elegivel"] is True, prova["motivos"]
    assert prova["recibo_candidato"]["fingerprint_scope"] == "live"
    assert mundo_selado["supa"].patches == []
    # E o candidato NÃO virou o recibo da linha: candidato não é aprovação.
    na_linha = mundo_selado["supa"].paginas_publicadas()[0][CHAVE_DO_RECIBO]
    assert na_linha == _recibo_live_anterior(), "o /provar trocou o recibo gravado"
    assert na_linha != prova["recibo_candidato"]


def test_o_inventario_de_links_da_prova_e_sanitizado(cliente: TestClient, mundo_selado):
    """O portão lê HTML público de terceiros; devolvê-lo faria a API republicá-lo.

    A evidência é ESTRUTURAL — host, região, classe, botão, oculto. Âncora e
    corpo ficam de fora: um recibo que carrega a página vira coletor de
    conteúdo, e é a mesma doutrina que já impede a recusa de `/subir` de vazar
    o HTML do destino.
    """
    prova = _prova_da_rota(cliente)

    assert prova["inventario_de_links"], "uma página com links devolveu inventário vazio"
    for item in prova["inventario_de_links"]:
        for chave in ("host", "regiao", "classe", "em_botao", "oculto"):
            assert chave in item, (chave, item)
        assert "ancora" not in item, item
    assert _CORPO[:60] not in json.dumps(prova, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 4 — a confirmação com a impressão EXATA grava o recibo live
# ═══════════════════════════════════════════════════════════════════════════


def test_confirmacao_com_a_impressao_exata_grava_o_recibo_live(
    cliente: TestClient, mundo_espiao,
):
    """As duas etapas, ponta a ponta, no caminho que a operação vai usar.

    O que se cobra aqui não é o 200: é o EFEITO. O recibo tem de chegar a
    `pautador_funnel_runs.paginas_publicadas` — a coluna jsonb que já existe —
    carimbado `live`, na página certa, e tem de ser encontrável por
    `recibo_da_url`, que é como a barreira 3 vai procurá-lo.
    """
    prova = _prova_da_rota(cliente)

    r = cliente.post(ROTA_CONFIRMAR, json={"impressao_da_prova": prova["impressao_da_prova"]})

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["gravado"] is True
    assert corpo["recibo"]["fingerprint_scope"] == "live"
    assert corpo["recibo"]["paid_destination_ready"] is True

    supa: SupaEspiao = mundo_espiao["supa"]
    assert supa.patches, "a confirmação disse ter gravado e não gravou"
    assert supa.patches[-1]["tabela"] == pub.TABELA_RUNS
    assert "paginas_publicadas" in supa.patches[-1]["valores"], supa.patches[-1]["valores"]
    gravado = recibo_da_url(supa.paginas_publicadas(), URL)
    assert gravado is not None, supa.paginas_publicadas()
    assert gravado["fingerprint_scope"] == "live"
    assert gravado["policy_contract_version"] == POLICY_CONTRACT_VERSION
    assert gravado["policy_source_version"] == versao_da_fonte()


def test_a_confirmacao_nao_grava_recibo_de_recusa_como_se_fosse_aprovacao(
    cliente: TestClient, mundo_selado, monkeypatch: pytest.MonkeyPatch,
):
    """Destino inelegível recusa a confirmação — e recusa ANTES de escrever.

    Gravar um recibo com `paid_destination_ready: false` em
    `paginas_publicadas` seria pior que não gravar: `varrer_recibo` passa a ter
    um recibo fresco, desta política, e a operação lê "já reauditado". A
    sentinela de escrita é o que separa as duas coisas.
    """
    _leitura_da_reauditoria(monkeypatch, desktop=HTML_LINK_NO_CORPO)
    prova = _prova_da_rota(cliente)
    assert prova["elegivel"] is False

    r = cliente.post(ROTA_CONFIRMAR, json={"impressao_da_prova": prova["impressao_da_prova"]})

    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe.get("motivos"), "a recusa não disse por quê"
    assert mundo_selado["supa"].patches == []


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 5 — hash divergente OU página alterada recusa SEM ESCRITA
# ═══════════════════════════════════════════════════════════════════════════


def test_impressao_divergente_recusa_a_confirmacao_sem_escrever(
    cliente: TestClient, mundo_selado,
):
    """O operador confirma uma prova que não é a que ele viu.

    Sem o vínculo, `confirmar` viraria um botão "aprove o que estiver no ar
    agora" — e o ato de duas etapas colapsaria de volta no portão que se
    autoaprova. A resposta tem de dizer o que era esperado, o que foi observado
    e qual é o próximo ato, senão o operador não tem como sair do 409.
    """
    _prova_da_rota(cliente)
    inventada = hashlib.sha256(b"uma impressao que ninguem provou").hexdigest()

    r = cliente.post(ROTA_CONFIRMAR, json={"impressao_da_prova": inventada})

    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["esperado_12"] == inventada[:12]
    assert detalhe["observado_12"] != inventada[:12]
    assert detalhe["proxima_acao"] == "provar de novo"
    assert detalhe.get("erro")
    assert mundo_selado["supa"].patches == []


def test_pagina_alterada_entre_a_prova_e_a_confirmacao_recusa_sem_escrever(
    cliente: TestClient, mundo_selado, monkeypatch: pytest.MonkeyPatch,
):
    """A JANELA entre as duas etapas — o defeito que a impressão existe para pegar.

    A prova acontece sobre a página limpa; entre uma requisição e outra o site
    passa a servir outra coisa. A confirmação RE-LÊ: se ela reaproveitasse a
    avaliação da prova, o recibo `live` descreveria bytes que já não estão no
    ar, e a barreira 3 aprovaria o destino errado com evidência de verdade.
    """
    prova = _prova_da_rota(cliente)
    _leitura_da_reauditoria(monkeypatch, desktop=HTML_LINK_NO_CORPO)

    r = cliente.post(ROTA_CONFIRMAR, json={"impressao_da_prova": prova["impressao_da_prova"]})

    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["esperado_12"] == prova["impressao_da_prova"][:12]
    assert detalhe["observado_12"] != prova["impressao_da_prova"][:12]
    assert detalhe["proxima_acao"] == "provar de novo"
    assert mundo_selado["supa"].patches == []


def test_confirmar_reauditoria_levanta_prova_divergente_no_modulo():
    """O mesmo defeito, na camada em que ele é decidido.

    A rota traduz para 409; o módulo levanta `ProvaDivergente`. Provar só a
    tradução deixaria qualquer outro chamador do módulo — um script de
    manutenção, um worker — sem a garantia.
    """
    agora = time.time()
    prova = _provar_modulo(agora=agora)

    with pytest.raises(ra.ProvaDivergente):
        ra.confirmar_reauditoria(
            prova_esperada=prova.impressao_da_prova, url=URL, papel_do_motor="LP",
            recibo_anterior=None, agora=agora,
            ler=_leitor(desktop=HTML_LINK_NO_CORPO))


def test_leitura_que_falha_recusa_a_reauditoria_em_vez_de_liberar():
    """Falha FECHA. "Não consegui olhar" nunca é evidência de página limpa.

    É a mesma doutrina de `_ler_destino_ao_vivo`: leitura que não conclui vira
    recusa TRADUZIDA, nunca exceção engolida e nunca `unavailable` tratado como
    verde.
    """
    with pytest.raises(ra.ReauditoriaRecusada):
        ra.confirmar_reauditoria(
            prova_esperada=hashlib.sha256(b"x").hexdigest(), url=URL,
            papel_do_motor="LP", recibo_anterior=None, agora=time.time(),
            ler=_leitor(erro=OSError("DNS não resolveu")))


def test_status_diferente_de_200_nao_e_destino_elegivel():
    """Um destino que não serve a página não é destino.

    Avaliar o corpo de um 404 diria coisas verdadeiras sobre a página errada —
    e um "sem bloqueios" colhido de uma página de erro é a forma mais barata de
    um portão mentir sobre a própria cobertura. Por isso o status vira RECUSA
    antes da avaliação, e não um veredito sobre bytes que não são a página.
    """
    with pytest.raises(ra.ReauditoriaRecusada) as erro:
        _provar_modulo(ler=_leitor(status=500))

    assert "500" in str(erro.value), str(erro.value)


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 6 — o retry idêntico é idempotente
# ═══════════════════════════════════════════════════════════════════════════


def test_retry_identico_nao_duplica_e_devolve_gravado_falso(
    cliente: TestClient, mundo_espiao,
):
    """Rede treme, o operador clica de novo. O segundo clique não pode duplicar.

    Duplicar aqui não é ruído cosmético: `paginas_publicadas` casa por URL, e
    duas entradas para a mesma URL fazem `recibo_da_url` devolver a primeira que
    encontrar — que passa a ser questão de ordem de lista, não de fato.
    """
    prova = _prova_da_rota(cliente)
    corpo = {"impressao_da_prova": prova["impressao_da_prova"]}

    primeira = cliente.post(ROTA_CONFIRMAR, json=corpo)
    assert primeira.status_code == 200, primeira.text
    assert primeira.json()["gravado"] is True

    supa: SupaEspiao = mundo_espiao["supa"]
    patches_depois_da_primeira = len(supa.patches)

    segunda = cliente.post(ROTA_CONFIRMAR, json=corpo)
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["gravado"] is False, "a segunda confirmação regravou o mesmo recibo"
    assert len(supa.patches) == patches_depois_da_primeira, supa.patches[-1]

    publicadas = supa.paginas_publicadas()
    alvo = [p for p in publicadas if url_canonica(str(p.get("url_wp") or "")) == url_canonica(URL)]
    assert len(alvo) == 1, publicadas
    assert alvo[0][CHAVE_DO_RECIBO] == primeira.json()["recibo"]
    # ⚠️ E a história não pode ser empurrada para fora por um clique duplo. O
    # `landing_policy_receipt_anterior` responde "contra o que esta página
    # estava aprovada quando a campanha rodou"; se a segunda confirmação
    # gravasse de novo, a resposta viraria "contra o clique de dois segundos
    # atrás" — e a auditoria perderia justamente o registro que ela procura.
    assert alvo[0].get("landing_policy_receipt_anterior") == _recibo_live_anterior()


def test_aplicar_recibo_devolve_lista_nova_e_e_idempotente():
    """`aplicar_recibo` não muta em lugar, e recibo igual devolve `mudou=False`.

    Mutar a lista recebida transformaria um erro de ordem de execução em
    corrupção silenciosa do estado do run — é o mesmo motivo pelo qual
    `registro.anexar_recibo` devolve um dict novo.
    """
    recibo = _recibo_live_de(HTML_CONFORME)
    original = [{"page_number": 1, "url_wp": URL}]

    primeira, mudou_1 = ra.aplicar_recibo(original, URL, recibo)
    assert mudou_1 is True
    assert original == [{"page_number": 1, "url_wp": URL}], "a lista de entrada foi mutada"
    assert primeira is not original

    segunda, mudou_2 = ra.aplicar_recibo(primeira, URL, recibo)
    assert mudou_2 is False
    assert recibo_da_url(segunda, URL) == recibo
    assert len(segunda) == 1, segunda


def test_aplicar_recibo_guarda_o_anterior_em_vez_de_apagar_a_historia():
    """Reauditoria nova não apaga a prova da anterior.

    A anterior é justamente a que explica por que houve uma segunda — se ela
    sumir, ninguém consegue responder "o que mudou entre as duas?" sem reabrir o
    caso, que é a pergunta que todo recibo existe para responder sem reabrir.
    """
    antigo = _recibo_live_de(HTML_CONFORME)
    novo = _recibo_live_de(HTML_FONTE_EM_PROSA)
    assert antigo["content_fingerprint"] != novo["content_fingerprint"]

    com_antigo, _ = ra.aplicar_recibo([{"page_number": 1, "url_wp": URL}], URL, antigo)
    com_novo, mudou = ra.aplicar_recibo(com_antigo, URL, novo)

    assert mudou is True
    assert recibo_da_url(com_novo, URL) == novo
    assert com_novo[0]["landing_policy_receipt_anterior"] == antigo


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 7 — link externo no CORPO continua bloqueando
# ═══════════════════════════════════════════════════════════════════════════


def test_link_externo_no_corpo_bloqueia_com_o_codigo_do_funil():
    """O defeito literal do incidente, medido no ato novo.

    O código é cobrado pelo nome: `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO`, com
    `owner` do FUNIL — quem escreveu o corpo é quem conserta. Um teste que só
    conferisse `elegivel is False` ficaria verde por causa do
    `LINK_EXTERNO_NAO_CLASSIFICADO` que a mesma página também emite, e
    continuaria verde no dia em que a regra do corpo sumisse.
    """
    prova = _provar_modulo(ler=_leitor(desktop=HTML_LINK_NO_CORPO))

    assert prova.elegivel is False
    assert "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO" in _codigos(prova.bloqueios)
    assert _dono(prova.bloqueios, "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO") == "funil"
    assert "LINK_EXTERNO_NO_CHROME" not in _codigos(prova.bloqueios), (
        "um link do CORPO foi atribuído ao tema")


def test_a_mesma_fonte_citada_em_prosa_atravessa():
    """O SIMÉTRICO. A política proíbe a âncora, não a citação.

    A fonte fica no dossiê de evidência e é citada em prosa. Uma régua que
    proibisse a citação proibiria escrever — e régua que ninguém consegue
    atingir é régua que a operação contorna.
    """
    prova = _provar_modulo(ler=_leitor(desktop=HTML_FONTE_EM_PROSA),
                           recibo_anterior=_recibo_live_anterior(HTML_FONTE_EM_PROSA))

    assert "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO" not in _codigos(prova.bloqueios)
    assert prova.elegivel is True, prova.motivos


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 8 — o link do tema é CHROME, não autoria do funil
# ═══════════════════════════════════════════════════════════════════════════


def test_link_do_tema_e_atribuido_ao_chrome_e_nao_ao_funil():
    """Acusação falsa é como um portão perde a autoridade nos outros 42 códigos.

    O crédito do tema, o ícone de rede social e o link do autor são hyperlinks
    que o WordPress renderiza. Atribuí-los ao conteúdo dava ao operador uma
    recusa que ele não tinha como consertar mexendo no funil.

    A procedência NÃO libera: o código muda, o dono do conserto muda, e o
    destino continua inelegível. É por isso que esta prova cobra as três coisas
    juntas — código, `owner` e a região no inventário.
    """
    prova = _provar_modulo(ler=_leitor(desktop=HTML_LINK_NO_TEMA))

    assert prova.elegivel is False, "procedência de chrome não pode liberar o destino"
    assert "LINK_EXTERNO_NO_CHROME" in _codigos(prova.bloqueios)
    assert _dono(prova.bloqueios, "LINK_EXTERNO_NO_CHROME") == "tema/WordPress"
    assert "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO" not in _codigos(prova.bloqueios), (
        "o link do TEMA foi atribuído ao conteúdo do funil")

    do_tema = [i for i in prova.inventario_de_links if i.get("host") == HOST_EXTERNO]
    assert do_tema, prova.inventario_de_links
    assert all(i["regiao"] != "corpo" for i in do_tema), do_tema


def test_o_chrome_declarado_pelo_servidor_limpa_o_link_do_tema():
    """O SIMÉTRICO: com procedência de SERVIDOR, o link do tema deixa de acusar.

    Vazio é fail-closed — sem procedência confiável o link do tema continua
    reprovando. Declarado na configuração do site, ele vira `chrome_do_site` e
    o destino volta a ser elegível. Sem esta metade, a regra anterior seria
    apenas mais um jeito de nunca aprovar.
    """
    prova = _provar_modulo(
        ler=_leitor(desktop=HTML_LINK_NO_TEMA),
        recibo_anterior=_recibo_live_anterior(HTML_LINK_NO_TEMA),
        chrome_declarado_pelo_site=(HOST_EXTERNO,),
    )

    assert "LINK_EXTERNO_NO_CHROME" not in _codigos(prova.bloqueios)
    assert prova.elegivel is True, prova.motivos


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 9 — declaração do CLIENTE não autoriza host
# ═══════════════════════════════════════════════════════════════════════════


def test_a_reauditoria_nao_tem_porta_para_allowlist_do_cliente():
    """A allowlist do cliente não é recusada: ela não tem por onde entrar.

    `provar_destino` aceita `chrome_declarado_pelo_site` — configuração de
    servidor — e mais nada. Um parâmetro `hosts_declarados` ou
    `adtech_declarada` na assinatura seria a chave que abre a política de links
    a partir de um campo de payload, que é a classe de defeito que
    `papel_do_servidor` já existe para não cometer com o papel.
    """
    import inspect

    parametros = set(inspect.signature(ra.provar_destino).parameters)
    assert "chrome_declarado_pelo_site" in parametros
    assert "hosts_declarados" not in parametros, parametros
    assert "adtech_declarada" not in parametros, parametros

    confirmar = set(inspect.signature(ra.confirmar_reauditoria).parameters)
    assert "hosts_declarados" not in confirmar, confirmar
    assert "adtech_declarada" not in confirmar, confirmar


@pytest.mark.parametrize("declaracao", ["hosts_declarados", "adtech_declarada"])
def test_declaracao_do_cliente_nao_limpa_o_link_do_corpo_nem_o_do_chrome(declaracao: str):
    """A regra que a assinatura acima protege, medida onde ela vive.

    `hosts_declarados` é evidência de PESQUISA que o chamador trouxe;
    `adtech_declarada` autoriza RECURSO TÉCNICO (script, pixel), não navegação
    do leitor. Nenhuma das duas é procedência sobre o template do site, e é por
    isso que nenhuma limpa o link do chrome — nem, com mais razão, o do corpo.
    """
    for html, codigo in ((HTML_LINK_NO_TEMA, "LINK_EXTERNO_NO_CHROME"),
                         (HTML_LINK_NO_CORPO, "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO")):
        avaliacao = elegibilidade_de_destino_de_campanha(
            _pagina_ao_vivo(html, **{declaracao: (HOST_EXTERNO,)}))
        codigos = [a.codigo for a in avaliacao.bloqueios]
        assert codigo in codigos, (declaracao, html[:40], codigos)
        assert avaliacao.paid_destination_ready is False


def test_o_chrome_declarado_nao_libera_o_link_do_corpo():
    """Autorização de chrome vale para o CHROME. Ela não vaza para o corpo.

    Sem esta prova, a procedência do tema viraria a porta larga: bastaria
    declarar o host uma vez para o mesmo host passar a poder virar âncora no
    meio do texto do destino pago.
    """
    prova = _provar_modulo(
        ler=_leitor(desktop=HTML_LINK_NO_CORPO),
        chrome_declarado_pelo_site=(HOST_EXTERNO,),
    )

    assert prova.elegivel is False
    assert "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO" in _codigos(prova.bloqueios)


def test_o_papel_avaliado_e_o_do_servidor_e_nao_o_declarado_pelo_motor():
    """Uma campanha apontando para a URL faz dela um destino pago.

    `papel_do_motor` viaja para o recibo como `role_declared` — registro, não
    régua. O ponto de portão FORÇA `paid_destination`, e é por isso que um
    papel frouxo declarado rio acima não baixa o rigor da reauditoria.
    """
    prova = _provar_modulo(papel_do_motor="ORGANIC_ARTICLE",
                           ler=_leitor(desktop=HTML_LINK_NO_CORPO))

    assert prova.recibo_candidato["role"] == "paid_destination"
    # ⚠️ O PONTO É `live_audit`, e ele nasceu da correção focal desta rodada.
    # Avaliar no ponto de CAMPANHA exigia aprovação anterior de um ato de
    # aprovação — circular, e foi o que deixou o ciclo do recibo `live` sem
    # entrada. Ver `PontoDePortao.AUDITORIA_AO_VIVO`.
    assert prova.recibo_candidato["gate_point"] == "live_audit"
    assert prova.elegivel is False


def _pagina_ao_vivo(html: str, **campos: Any) -> PaginaObservada:
    """A `PaginaObservada` de uma leitura ao vivo conforme, com o recibo do escopo certo.

    Existe para as provas que medem a REGRA por baixo da reauditoria (o que a
    declaração do cliente limpa e o que ela não limpa) sem passar pelo módulo
    novo — assim elas continuam significando a mesma coisa mesmo se a forma do
    módulo mudar.
    """
    impressao = impressao_canonica(html)
    sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return PaginaObservada(
        url=URL, html=html, status_http=200, saltos_redirecionamento=[],
        cabecalhos={"content-type": "text/html; charset=utf-8"},
        variantes_sha256={"usuario_desktop": impressao, "usuario_movel": impressao,
                          "googlebot": impressao},
        sha256_observado=sha, impressao_aprovada=impressao,
        recibo_de_aprovacao=_recibo(html),
        avaliado_em_epoch=time.time(), **campos)


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 10 — o /provar de campanha continua READ-ONLY
# ═══════════════════════════════════════════════════════════════════════════


def test_o_provar_de_campanha_nao_escreve_e_continua_consultando_o_portao(
    monkeypatch: pytest.MonkeyPatch,
):
    """`validate_only` é leitura para todos os efeitos — e continua sendo.

    Duas metades, e as duas importam. Que a rota não escreva: o ledger não abre
    (um recibo `em_voo` para uma chamada que nunca sai deixa a camada 4
    bloqueando o item) e o repositório de plano não persiste. Que a rota AINDA
    consulte o portão: a reauditoria acrescentou um caminho para o recibo
    `live`, e o jeito mais fácil de "consertar" a parada operacional seria
    deixar de olhar o destino — que é exatamente o buraco que a barreira 3
    fechou.
    """
    _cenario_conforme(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo_live_de(HTML_CONFORME))
    agentes = _instalar_leitura(monkeypatch)

    ledger = LedgerDeTeste(diario=[])
    repo = RepoDePlanoDeTeste(diario=[])
    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: repo)

    d = _provar()

    assert d["destino"]["url"] == URL, "o portão do destino não foi consultado"
    assert d["destino"]["papel"] == "paid_destination"
    assert d["destino"]["elegivel"] is True, d["destino"]["motivos"]
    assert len(agentes) == 3, agentes
    assert ledger.diario == [], ledger.diario
    assert repo.diario == [], repo.diario


def test_o_provar_de_campanha_continua_recusando_destino_que_ninguem_reauditou(
    monkeypatch: pytest.MonkeyPatch,
):
    """O simétrico do read-only: ler não é aprovar.

    A rota continua olhando, e continua retendo o selo quando o destino não
    tem recibo `live`. Um `/provar` que passasse a ficar verde por consultar o
    portão sem cobrar o resultado seria leitura decorativa.
    """
    _cenario_conforme(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=None)
    _instalar_leitura(monkeypatch)

    d = _provar()

    assert d["destino"]["elegivel"] is False
    assert d["autorizacao"]["plano_impressao"] is None
    assert d["preparo"]["selo"] is None


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 11 — /subir reavalia e recusa deriva POSTERIOR à confirmação
# ═══════════════════════════════════════════════════════════════════════════


def test_subir_recusa_a_pagina_que_mudou_depois_da_reauditoria(
    monkeypatch: pytest.MonkeyPatch,
):
    """O recibo `live` descreve o que foi reauditado; o ar mudou DEPOIS.

    Esta é a prova de que o recibo novo não é um passe vitalício. Ele é emitido
    a partir de uma leitura datada, e `DERIVA_AO_VIVO` continua sendo cobrada
    contra ele em `/subir` — que RE-LÊ em vez de confiar no selo do `/provar`,
    porque o selo é hash do PAYLOAD e o payload não sabe o que o endereço serve
    agora.

    O ledger não pode abrir, e a sentinela de arquivo garante que
    `volc_ads.subir` não é alcançado.
    """
    _cenario_conforme(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo_live_de(HTML_CONFORME))
    _instalar_leitura(monkeypatch)

    prova = _provar()
    impressao = prova["autorizacao"]["plano_impressao"]
    assert impressao, prova["destino"]["motivos"]

    # A página muda DEPOIS da reauditoria e DEPOIS da prova de campanha.
    _instalar_leitura(monkeypatch, desktop=_html(
        titulo="Saque liberado pelo governo", extra="<h2>Receba hoje</h2>"))
    ledger = LedgerDeTeste(diario=[])
    _preparar_subida(monkeypatch, ledger=ledger, leitura_remota_proibida=True)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    detalhe = erro.value.detail
    assert detalhe["estado"] == "destino_nao_elegivel"
    assert "DERIVA_AO_VIVO" in detalhe["destino"]["bloqueios"], detalhe["destino"]["bloqueios"]
    assert ledger.diario == [], ledger.diario


def test_a_reauditoria_de_uma_pagina_nao_aprova_outra_url(monkeypatch: pytest.MonkeyPatch):
    """O recibo é DAQUELA URL. Reauditar a p1 não libera a p2.

    `paginas_publicadas` casa por URL canônica; um recibo que valesse para o
    run inteiro faria uma reauditoria limpa carregar consigo todas as páginas
    que ninguém olhou — e o funil publica de três a cinco por vez.
    """
    _cenario_conforme(monkeypatch)
    outra = "https://portalmundomais.com.br/outra-pagina/"
    _instalar_linhas(monkeypatch, recibo=_recibo_live_de(HTML_CONFORME))
    _instalar_leitura(monkeypatch)

    d = _provar(_payload_da_rota(url_final=outra))

    assert d["destino"]["url"] == outra
    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_APROVACAO_AUSENTE" in d["destino"]["bloqueios"]


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 12 — nenhum mutate no Google é alcançável
# ═══════════════════════════════════════════════════════════════════════════


def test_nenhum_caminho_da_reauditoria_alcanca_o_mutate(
    cliente: TestClient, mundo_selado, monkeypatch: pytest.MonkeyPatch,
):
    """As rotas novas não têm porta para o Google — e isto é medido, não alegado.

    A sentinela de arquivo (`_mutate_google_selado`) já cobre `volc_ads.subir`.
    Aqui ela é reforçada na porta de VALIDAÇÃO remota, que é a primeira que
    gastaria quota da conta, e os dois caminhos da reauditoria são percorridos
    inteiros — inclusive o divergente, que é onde um retry mal escrito costuma
    cair.
    """
    try:
        from volc_ads import subir as sb
    except Exception:  # noqa: BLE001
        pytest.skip("sem a biblioteca do Google Ads não há mutate a vigiar")

    def nunca_validar(*_a, **_k):
        pytest.fail("a reauditoria alcançou a validação remota do Google")

    monkeypatch.setattr(sb, "validar_mutacoes", nunca_validar)

    prova = _prova_da_rota(cliente)
    divergente = cliente.post(ROTA_CONFIRMAR, json={
        "impressao_da_prova": hashlib.sha256(b"outra").hexdigest()})
    assert divergente.status_code == 409, divergente.text
    assert prova["elegivel"] is True, prova["motivos"]
    assert mundo_selado["supa"].patches == []


def test_o_destino_inelegivel_nao_alcanca_o_mutate_em_subir(monkeypatch: pytest.MonkeyPatch):
    """A sentinela no executor, no caminho que de fato leva ao Google.

    O status 409 sozinho não prova nada: uma rota pode devolver 409 depois de
    já ter criado a campanha. `volc_ads.subir` chama `pytest.fail` se for
    invocado — é a única forma de a prova falar sobre EFEITO.
    """
    _cenario_conforme(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo_live_de(HTML_CONFORME))
    _instalar_leitura(monkeypatch)
    impressao = _provar()["autorizacao"]["plano_impressao"]
    assert impressao

    _instalar_linhas(monkeypatch, recibo=None)
    ledger = LedgerDeTeste(diario=[])
    _preparar_subida(monkeypatch, ledger=ledger)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert erro.value.detail["estado"] == "destino_nao_elegivel"
    assert ledger.diario == []


# ═══════════════════════════════════════════════════════════════════════════
# O VÍNCULO PROVA → CONFIRMAÇÃO, que é o que sustenta as contraprovas 4 e 5
# ═══════════════════════════════════════════════════════════════════════════


def test_a_impressao_sobrevive_ao_tempo_entre_a_prova_e_a_confirmacao():
    """Se o instante entrasse no vínculo, TODA confirmação divergiria.

    O operador lê a prova, confere os bloqueios e clica — segundos depois, às
    vezes minutos. Um hash que andasse com o relógio devolveria 409 sempre, e a
    parada operacional voltaria com outro nome. `lido_em_epoch` viaja na prova
    como evidência de quando se olhou; ele não entra no vínculo.
    """
    agora = time.time()
    primeira = _provar_modulo(agora=agora)
    depois = _provar_modulo(agora=agora + 300)

    assert primeira.impressao_da_prova == depois.impressao_da_prova
    assert depois.lido_em_epoch > primeira.lido_em_epoch

    recibo, _ = ra.confirmar_reauditoria(
        prova_esperada=primeira.impressao_da_prova, url=URL, papel_do_motor="LP",
        recibo_anterior=_recibo_live_anterior(), agora=agora + 300, ler=_leitor())
    assert recibo["fingerprint_scope"] == "live"


def test_a_impressao_muda_quando_qualquer_parte_da_prova_muda():
    """O vínculo tem de ser sensível ao que decide o veredito.

    Uma impressão que ignorasse os bloqueios deixaria o operador confirmar uma
    prova limpa com uma página que passou a bloquear — exatamente o que a
    contraprova 5 mede, e ela mediria nada se o hash não olhasse para isso.
    """
    limpa = _provar_modulo()
    com_link = _provar_modulo(ler=_leitor(desktop=HTML_LINK_NO_CORPO))
    outro_corpo = _provar_modulo(ler=_leitor(desktop=HTML_FONTE_EM_PROSA))

    assert limpa.impressao_da_prova != com_link.impressao_da_prova
    assert limpa.impressao_da_prova != outro_corpo.impressao_da_prova


def test_o_diff_com_o_recibo_anterior_diz_o_que_mudou():
    """A prova mostra ao operador o que ele está trocando.

    Confirmar sem ver o que muda é assinar em branco. `diff_com_o_recibo_anterior`
    é o que separa "reauditei e nada mudou" de "reauditei e a página é outra" —
    e a segunda é a que exige leitura humana antes do clique.
    """
    anterior = _recibo(HTML_CONFORME, fingerprint_scope="artifact")
    prova = _provar_modulo(recibo_anterior=anterior)

    diff = prova.diff_com_o_recibo_anterior
    assert diff["tinha_recibo"] is True
    assert diff["escopo_anterior"] == "artifact"
    assert diff["impressao_agora_12"] == prova.recibo_candidato["content_fingerprint"][:12]
    assert diff["impressao_anterior_12"] == anterior["content_fingerprint"][:12]
    assert diff["mudou"] is False, "a página não mudou; só o escopo do recibo é outro"

    sem_recibo = _provar_modulo(recibo_anterior=None)
    assert sem_recibo.diff_com_o_recibo_anterior["tinha_recibo"] is False


def test_para_json_da_prova_e_serializavel_e_traz_o_esquema():
    """A prova viaja pela API; ela tem de ser JSON de verdade, com nome.

    `ESQUEMA_DA_PROVA` existe para que, seis semanas depois, ninguém precise
    adivinhar contra qual formato aquele registro foi escrito.
    """
    prova = _provar_modulo()
    corpo = prova.para_json()

    assert json.loads(json.dumps(corpo, ensure_ascii=False))
    assert ra.ESQUEMA_DA_PROVA == "landing_policy_reaudit_proof.v1"
    for chave in ("url_canonica", "impressao_da_prova", "elegivel", "veredito",
                  "motivos", "bloqueios", "riscos", "desconhecidos",
                  "recibo_candidato", "inventario_de_links",
                  "diff_com_o_recibo_anterior", "lido_em_epoch"):
        assert chave in corpo, (chave, sorted(corpo))
    assert corpo["url_canonica"] == url_canonica(URL)
