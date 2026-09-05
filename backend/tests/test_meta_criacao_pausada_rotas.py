"""O caminho governado do nascimento Meta PAUSED, ponta a ponta e hermético.

## O que este módulo prova, e por que cada prova existe

A lane anterior parou com o executor pronto e **nenhuma rota montada**: a
`PROVA-VALIDATE-ONLY-REAL.md` registra doze sondas a `criar`, `nascer`,
`aprovar`, `habilitar` e `ativar`, todas 404. Agora `aprovar`, `criar-pausada`
e `reconciliar` existem, e existir é exatamente o que torna cada portão uma
afirmação verificável em vez de uma promessa.

Nenhum teste aqui fala com a Meta, com o Keychain ou com o Supabase. O
transporte é um `_GraphFalso` injetado no lugar de `httpx.AsyncClient`, o token
é uma string obviamente falsa e o ledger é um `_LedgerEmMemoria`. Quando um
teste afirma "zero Keychain", ele **substitui `_credencial_salva` por uma
armadilha que falha o teste se for chamada** — a ausência é medida, não
suposta.

⚠️ Este módulo apaga `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` no import. Não é
zelo: `backend/.env` existe nesta árvore e `app.config` o lê, então rodar este
arquivo ISOLADO deixaria `SupabaseService.enabled` verdadeiro e uma fábrica não
substituída tentaria falar com o Supabase operacional de verdade.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

for _chave in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
    os.environ[_chave] = ""

from app.routers import meta_local, trafego_meta_criacao, trafego_meta_validacao
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.registro import PassoPreparadoMeta


TOKEN = "token-meta-falso-que-nao-pode-vazar"
ATOR = "operador-meta"
CONTA_EXTERNA = "1234567890"
PAGINA_EXTERNA = "2222222222"
IMAGEM_EXTERNA = "hashImagemDeProva_0001"

#: Ids que o `_GraphFalso` devolve, na ordem de criação da saga.
IDS_CRIADOS = {"campaign": "1001", "adset": "1002", "creative": "1003", "ad": "1004"}

#: Instante em que o dublê "prepara" um passo, e o `created_time` que os objetos
#: falsos declaram. O segundo é POSTERIOR ao primeiro de propósito: é essa ordem
#: que prova que o objeto nasceu deste despacho, e invertê-la é o que o teste do
#: objeto antigo faz.
PREPARADO_EM = "2026-09-05T12:00:00+00:00"
NASCIDO_EM = "2026-09-05T12:00:30+0000"


# ---------------------------------------------------------------------------
# TRANSPORTE FALSO — um único cliente serve a leitura de ativos E a saga
# ---------------------------------------------------------------------------
# `_compilar` abre o seu próprio `httpx.AsyncClient` e o executor abre outro.
# Substituir a classe (em vez de usar `MockTransport`) é o que intercepta os
# dois, e é o padrão que `test_meta_paused_validation_routes.py` já usa.

class _Resposta:
    def __init__(self, corpo: Any, status: int = 200) -> None:
        self.status_code = status
        self._corpo = corpo

    def json(self) -> Any:
        return self._corpo


class _Cenario:
    """O estado do transporte falso, COMPARTILHADO entre todas as instâncias.

    ⚠️ `_compilar` abre um `httpx.AsyncClient` e o executor abre outro, e cada
    rota abre os seus de novo. Guardar os ganchos e o registro por instância
    faria um teste configurar a recusa numa cópia que já morreu — a primeira
    versão deste arquivo tinha exatamente esse defeito, e ele aparecia como
    "a Meta nunca recusou" num teste que existia para provar a recusa.
    """

    def __init__(self) -> None:
        self.reiniciar()

    def reiniciar(self) -> None:
        self.posts: list[tuple[str, dict[str, str]]] = []
        self.gets: list[str] = []
        self.criados: list[str] = []
        #: Ganchos que um teste liga para simular recusa, silêncio ou divergência.
        self.recusar_em: str | None = None
        self.silenciar_em: str | None = None
        self.divergir_em: str | None = None
        self.listagens: dict[str, list[dict[str, Any]]] = {}


CENARIO = _Cenario()


@pytest.fixture(autouse=True)
def _cenario_limpo():
    """Cada teste começa com um transporte virgem e sem gancho ligado."""
    CENARIO.reiniciar()
    yield
    CENARIO.reiniciar()


class _GraphFalso:
    """Grava tudo o que sai e devolve respostas plausíveis da Graph v26."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def __aenter__(self) -> "_GraphFalso":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    # -- leitura ------------------------------------------------------------
    async def get(self, url: str, *, params: Any = None, headers: Any = None):
        assert headers == {"Authorization": f"Bearer {TOKEN}"}
        CENARIO.gets.append(url)
        if url.endswith("/me/adaccounts"):
            return _Resposta({"data": [{
                "id": f"act_{CONTA_EXTERNA}", "name": "Conta de prova", "account_status": 1,
                "currency": "BRL", "timezone_name": "America/Sao_Paulo",
            }]})
        if url.endswith("/promote_pages"):
            return _Resposta({"data": [{"id": PAGINA_EXTERNA, "name": "Página de prova"}]})
        if url.endswith("/adimages"):
            return _Resposta({"data": [{
                "hash": IMAGEM_EXTERNA, "name": "Imagem de prova",
                "width": 1080, "height": 1080,
                "url_128": "https://scontent.example.fbcdn.net/preview.jpg",
            }]})
        if url.endswith("/advideos"):
            return _Resposta({"data": []})
        # Listagem de uma aresta da conta — só a reconciliação faz isto.
        for aresta, linhas in CENARIO.listagens.items():
            if url.endswith(aresta):
                return _Resposta({"data": linhas})
        return _Resposta(self._read_back(url.rsplit("/", 1)[-1]))

    # -- escrita ------------------------------------------------------------
    async def post(self, url: str, *, data: Any = None, headers: Any = None):
        assert headers == {"Authorization": f"Bearer {TOKEN}"}
        corpo = dict(data or {})
        CENARIO.posts.append((url, corpo))
        tipo = _tipo_do_endpoint(url)
        validacao = "execution_options" in corpo
        if validacao:
            return _Resposta({"success": True})
        if CENARIO.silenciar_em == tipo:
            raise httpx.ReadTimeout("tempo esgotado")
        if CENARIO.recusar_em == tipo:
            return _Resposta({"error": {
                "code": 100, "error_subcode": 1885183,
                "message": "Invalid parameter for this account",
            }}, status=400)
        CENARIO.criados.append(tipo)
        return _Resposta({"id": IDS_CRIADOS[tipo]})

    # -- read-back ----------------------------------------------------------
    @staticmethod
    def _read_back(identificador: str) -> dict[str, Any]:
        tipo = next((t for t, i in IDS_CRIADOS.items() if i == identificador), None)
        if tipo is None:
            return {"error": {"code": 803, "message": "objeto inexistente"}}
        dados = _objeto_lido(tipo)
        if CENARIO.divergir_em == tipo:
            # Um objeto que voltou ATIVO. É a divergência mais perigosa que
            # existe nesta lane: se ela virasse recibo verde, a tela diria
            # "tudo pausado" sobre uma campanha veiculando.
            #
            # ⚠️ SÓ `configured_status` muda. Mexer também em
            # `effective_status` faria o teste passar pela guarda errada: uma
            # mutação que aceitasse ACTIVE em `configured_status` continuaria
            # vermelha por causa do outro campo, e a prova do estado
            # configurado deixaria de existir sem ninguém notar. Medido: com os
            # dois campos ativos, afrouxar a guarda de `status` não quebrava
            # teste nenhum.
            dados = {**dados, "configured_status": "ACTIVE"}
        return dados


def _tipo_do_endpoint(url: str) -> str:
    fim = url.rsplit("/", 1)[-1]
    return {
        "campaigns": "campaign", "adsets": "adset",
        "adcreatives": "creative", "ads": "ad",
    }[fim]


def _objeto_lido(tipo: str) -> dict[str, Any]:
    """O que a Meta devolveria para cada objeto recém-criado da receita P0."""
    comum = {"id": IDS_CRIADOS[tipo], "account_id": CONTA_EXTERNA,
             "created_time": NASCIDO_EM}
    if tipo == "campaign":
        return {**comum, "name": PLANO["campaign_name"], "objective": "OUTCOME_TRAFFIC",
                "buying_type": "AUCTION", "configured_status": "PAUSED",
                "effective_status": "PAUSED", "special_ad_categories": [],
                "is_adset_budget_sharing_enabled": False}
    if tipo == "adset":
        return {**comum, "name": PLANO["adset_name"], "campaign_id": IDS_CRIADOS["campaign"],
                "configured_status": "PAUSED", "effective_status": "PAUSED",
                "daily_budget": str(PLANO["daily_budget_minor"]),
                "billing_event": "IMPRESSIONS", "optimization_goal": "LANDING_PAGE_VIEWS",
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "start_time": PLANO["start_time"],
                "targeting": {
                    "geo_locations": {"countries": ["BR"]}, "age_min": 18, "age_max": 65,
                    "targeting_automation": {"advantage_audience": 0},
                }}
    if tipo == "creative":
        variacao = PLANO["variations"][0]
        return {**comum, "name": variacao["creative_name"], "status": "ACTIVE",
                "effective_status": "ACTIVE",
                "object_story_spec": {
                    "page_id": PAGINA_EXTERNA,
                    "link_data": {
                        "image_hash": IMAGEM_EXTERNA,
                        "link": PLANO["destination_url"],
                        "message": variacao["message"],
                        "name": variacao["headline"],
                        "description": variacao["description"],
                        "call_to_action": {
                            "type": "LEARN_MORE",
                            "value": {"link": PLANO["destination_url"]},
                        },
                    },
                }}
    return {**comum, "name": PLANO["variations"][0]["ad_name"],
            "adset_id": IDS_CRIADOS["adset"], "configured_status": "PAUSED",
            "effective_status": "PAUSED", "creative": {"id": IDS_CRIADOS["creative"]}}


# ---------------------------------------------------------------------------
# LEDGER EM MEMÓRIA — a autoridade durável, sem Supabase
# ---------------------------------------------------------------------------

class _LedgerEmMemoria:
    """Reproduz o contrato das RPCs, incluindo o que elas RECUSAM.

    ⚠️ Não é um espelho complacente. `preparar_passo` devolve AMBIGUO na
    reentrada de um passo em voo e recusa passo fora do manifesto, porque são
    justamente essas regras que impedem o duplo nascimento — um dublê que
    sempre diz "DESPACHAR" faria os testes de duplicação passarem sem que a
    garantia existisse.
    """

    def __init__(self) -> None:
        self.eventos: list[tuple[str, str]] = []
        self.validacoes: dict[str, dict[str, Any]] = {}
        self.aprovacoes: dict[str, dict[str, Any]] = {}
        self.passos: dict[str, dict[str, Any]] = {}
        self._sequencia = 0

    # -- validação ----------------------------------------------------------
    async def registrar_validacao(self, **kwargs: Any) -> dict[str, Any]:
        self._sequencia += 1
        identificador = f"validation-{self._sequencia:04d}"
        self.validacoes[identificador] = dict(kwargs)
        self.eventos.append(("validacao", identificador))
        return {"ok": True, "validation_id": identificador,
                "validated_at": "2026-09-05T12:00:00+00:00"}

    async def consultar_validacao(self, validation_id: str) -> dict[str, Any]:
        validacao = self.validacoes.get(validation_id)
        if validacao is None:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_VALIDATION_RECEIPT_NOT_FOUND")
        return {
            "validation_id": validation_id,
            "plan_sha256": validacao["plano_sha256"],
            "account_ref": validacao["account_ref"],
            "actor_id": validacao["ator"],
            "coverage": validacao["cobertura"],
            "objects_created": validacao["objetos_criados"],
            "accepted": True,
            "operations_total": validacao["operacoes_totais"],
            "idade_s": 0,
            "ja_consumido": any(
                aprovacao["validation_id"] == validation_id
                for aprovacao in self.aprovacoes.values()),
        }

    # -- aprovação ----------------------------------------------------------
    async def aprovar(self, **kwargs: Any) -> dict[str, Any]:
        validacao = self.validacoes.get(kwargs["validation_id"])
        if validacao is None:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_VALIDATION_RECEIPT_NOT_FOUND")
        if validacao["plano_sha256"] != kwargs["plano_sha256"]:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_VALIDATION_PLAN_DIVERGED")
        if validacao["ator"] != kwargs["ator"]:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_VALIDATION_ACTOR_DIVERGED")
        if any(
            aprovacao["plano_sha256"] == kwargs["plano_sha256"]
            and aprovacao["state"] == "APPROVED"
            for aprovacao in self.aprovacoes.values()
        ):
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_APPROVAL_ALREADY_LIVE")
        self._sequencia += 1
        identificador = f"approval-{self._sequencia:04d}"
        self.aprovacoes[identificador] = {
            **kwargs, "state": "APPROVED", "approval_id": identificador,
        }
        self.eventos.append(("aprovacao", identificador))
        return {"ok": True, "approval_id": identificador,
                "expires_at": kwargs["expires_at"].isoformat()}

    async def manifesto(self, approval_id: str) -> dict[str, Any]:
        aprovacao = self.aprovacoes.get(approval_id)
        if aprovacao is None:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_APPROVAL_NOT_FOUND")
        return {
            "approval_id": approval_id,
            "plan_sha256": aprovacao["plano_sha256"],
            "account_ref": aprovacao["account_ref"],
            "actor_id": aprovacao["ator"],
            "capability": "META_CREATE_PAUSED",
            "daily_budget_minor": aprovacao["daily_budget_minor"],
            "currency": aprovacao["moeda"],
            "steps_expected": list(aprovacao["passos_esperados"]),
            "operations_expected": len(aprovacao["passos_esperados"]),
            "paused_birth_confirmed": True,
            "plan_request": aprovacao["pedido_do_operador"],
            "validation_id": aprovacao["validation_id"],
            "state": aprovacao["state"],
            "expires_at": aprovacao["expires_at"].isoformat(),
            "steps": [
                {"step_ref": ref, "name": passo["nome"], "ordinal": passo["ordinal"],
                 "state": passo["state"], "has_external_id": passo["id_externo"] is not None,
                 "error_code": passo["codigo"], "readback_error": passo["readback"],
                 "prepared_at": passo["prepared_at"]}
                for ref, passo in sorted(
                    self.passos.items(), key=lambda item: item[1]["ordinal"])
                if passo["approval_id"] == approval_id
            ],
        }

    # -- saga ---------------------------------------------------------------
    async def preparar_passo(
        self, *, plano_sha256: str, approval_id: str, ator: str, nome: str, payload_sha256: str,
    ) -> PassoPreparadoMeta:
        aprovacao = self.aprovacoes[approval_id]
        manifesto = list(aprovacao["passos_esperados"])
        if nome not in manifesto:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_STEP_OUTSIDE_APPROVED_PLAN")
        assert plano_sha256 == aprovacao["plano_sha256"]
        assert ator == aprovacao["ator"]
        assert len(payload_sha256) == 64
        self.eventos.append(("preparar", nome))
        ref = f"passo-{nome}"
        existente = self.passos.get(ref)
        if existente is not None:
            if existente["state"] == "CREATED":
                return PassoPreparadoMeta(ref, "CRIADO", existente["id_externo"])
            existente["state"] = "AMBIGUOUS"
            return PassoPreparadoMeta(ref, "AMBIGUO")
        self.passos[ref] = {
            "approval_id": approval_id, "nome": nome,
            "ordinal": manifesto.index(nome) + 1,
            "state": "IN_FLIGHT", "id_externo": None, "codigo": None,
            "readback": None, "prepared_at": PREPARADO_EM,
        }
        return PassoPreparadoMeta(ref, "DESPACHAR")

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None:
        self.eventos.append(("fechar", passo_ref))
        self.passos[passo_ref].update(state="CREATED", id_externo=id_externo)

    async def marcar_ambiguo(self, *, passo_ref: str) -> None:
        self.eventos.append(("ambiguo", passo_ref))
        self.passos[passo_ref]["state"] = "AMBIGUOUS"

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None:
        self.eventos.append(("falhar", passo_ref))
        self.passos[passo_ref].update(state="FAILED", codigo=codigo)

    async def resolver_ausente(
        self, *, passo_ref: str, codigo: str, idade_minima_s: int = 120,
    ) -> None:
        if self.passos[passo_ref]["state"] != "AMBIGUOUS":
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_STEP_NOT_AMBIGUOUS")
        # ⚠️ A RPC real recusa fechar um passo jovem demais: ele pode estar
        # ambíguo porque uma segunda chamada reentrou nele enquanto a PRIMEIRA
        # ainda está dentro do `await` do POST. O dublê reproduz a recusa para
        # que o teste da ordem exista.
        assert idade_minima_s >= 60
        if self.passos[passo_ref].get("jovem"):
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_RECONCILE_TOO_SOON")
        self.eventos.append(("ausente", passo_ref))
        self.passos[passo_ref].update(state="FAILED", codigo=codigo)

    async def marcar_readback_divergente(self, *, passo_ref: str, codigo: str) -> None:
        if self.passos[passo_ref]["state"] != "CREATED":
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED", "META_STEP_NOT_CREATED")
        self.eventos.append(("readback", passo_ref))
        self.passos[passo_ref].update(readback=codigo)

    async def recibo(self, approval_id: str) -> dict[str, Any]:
        manifesto = await self.manifesto(approval_id)
        return {
            "approval_id": approval_id,
            "plan_sha256": manifesto["plan_sha256"],
            "capability": "META_CREATE_PAUSED",
            "daily_budget_minor": manifesto["daily_budget_minor"],
            "currency": manifesto["currency"],
            "operations_expected": manifesto["operations_expected"],
            "paused_birth_confirmed": True,
            "state": manifesto["state"],
            "expires_at": manifesto["expires_at"],
            # ⚠️ Como a RPC real: afirma que o id existe, nunca o devolve.
            "steps": [
                {k: v for k, v in passo.items() if k != "step_ref"}
                for passo in manifesto["steps"]
            ],
        }


# ---------------------------------------------------------------------------
# PLANO E CLIENTE
# ---------------------------------------------------------------------------

PLANO: dict[str, Any] = {
    "account_ref": "", "page_ref": "", "asset_ref": "",
    "campaign_name": "VOLC · Meta · Tráfego · LPV",
    "adset_name": "Brasil · Amplo · LPV · Automático",
    "creative_name": "Criativo estático · v1",
    "ad_name": "Anúncio estático · v1",
    "destination_url": "https://focogenial.com/",
    "message": "Descubra as informações importantes antes de decidir.",
    "headline": "Entenda como funciona",
    "description": "Conteúdo informativo e independente.",
    "daily_budget_minor": 1000,
    "start_time": "2027-01-02T12:00:00+00:00",
    "special_ad_categories": [],
    "special_categories_confirmed": True,
    "is_adset_budget_sharing_enabled": False,
    "advantage_audience": False,
    "call_to_action_type": "LEARN_MORE",
    "variations": [],
}


def _plano_para_envio() -> dict[str, Any]:
    """O plano com as referências opacas que o `_GraphFalso` sabe resolver."""
    import hashlib

    from app.trafego.meta.dominio import referencia_opaca_conta, referencia_opaca_objeto

    conta = referencia_opaca_conta(CONTA_EXTERNA)
    pagina = referencia_opaca_objeto(CONTA_EXTERNA, "page", PAGINA_EXTERNA)
    # ⚠️ Derivado pela MESMA fórmula de `ativos.py`, não copiado como literal.
    # Um digest fixo aqui viraria um teste que passa contra um resolvedor que
    # mudou de namespace — exatamente o que o inventário já evita.
    digest = hashlib.sha256(
        f"META_ADS:{CONTA_EXTERNA}:image_asset:{IMAGEM_EXTERNA}".encode("utf-8")
    ).hexdigest()[:24]
    imagem = f"metaasset_{digest}"
    plano = {**PLANO, "account_ref": conta, "page_ref": pagina, "asset_ref": imagem}
    plano["variations"] = [{
        "variation_key": "variation-001", "asset_ref": imagem,
        "creative_name": PLANO["creative_name"], "ad_name": PLANO["ad_name"],
        "message": PLANO["message"], "headline": PLANO["headline"],
        "description": PLANO["description"], "call_to_action_type": "LEARN_MORE",
    }]
    PLANO["variations"] = plano["variations"]
    return plano


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(trafego_meta_validacao.router)
    app.include_router(trafego_meta_criacao.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub=ATOR, email="admin@volc", papel="ADMIN", origem="sessao")
    return TestClient(app, headers={"host": "localhost"})


class _CredencialFalsa:
    token = TOKEN


def _abrir(monkeypatch, ledger: _LedgerEmMemoria, *, criacao=True, ledger_flag=True):
    """Liga o ambiente hermético inteiro: macOS, flags, Keychain, rede, ledger."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    for nome, ligada in (
        ("META_CREATE_PAUSED_ENABLED", criacao),
        ("META_CREATE_LEDGER_WRITE_ENABLED", ledger_flag),
        ("META_VALIDATE_ONLY_ENABLED", True),
    ):
        if ligada:
            monkeypatch.setenv(nome, "1")
        else:
            monkeypatch.delenv(nome, raising=False)
    for modulo in (trafego_meta_criacao, trafego_meta_validacao):
        monkeypatch.setattr(modulo, "_credencial_salva", lambda *_: _CredencialFalsa())
        monkeypatch.setattr(modulo, "_registro_saga", lambda: ledger)
    monkeypatch.setattr(trafego_meta_validacao.httpx, "AsyncClient", _GraphFalso)


def _fechar_tudo(monkeypatch):
    """Servidor sem autorização nenhuma, com armadilhas no lugar dos recursos."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    for nome in ("META_CREATE_PAUSED_ENABLED", "META_CREATE_LEDGER_WRITE_ENABLED"):
        monkeypatch.delenv(nome, raising=False)
    for modulo in (trafego_meta_criacao, trafego_meta_validacao):
        monkeypatch.setattr(
            modulo, "_credencial_salva",
            lambda *_: pytest.fail("o Keychain foi aberto com a criação fechada"))
        monkeypatch.setattr(
            modulo, "_registro_saga",
            lambda: pytest.fail("o ledger foi tocado com a criação fechada"))
    monkeypatch.setattr(
        trafego_meta_validacao.httpx, "AsyncClient",
        lambda *a, **k: pytest.fail("saiu HTTP com a criação fechada"))


async def _aprovar(cliente: TestClient, ledger: _LedgerEmMemoria, plano: dict[str, Any]):
    """Compila, valida, grava o recibo durável e aprova — como a tela faz."""
    validacao = cliente.post("/api/trafego/meta/local/criacao/validar", json={
        "confirmar_validate_only": True, "plano": plano})
    assert validacao.status_code == 200, validacao.text
    corpo = validacao.json()
    assert corpo["prova_duravel"]["registrada"] is True
    return cliente.post("/api/trafego/meta/local/criacao/aprovar", json={
        "plano": plano,
        "plano_sha256_esperado": corpo["plano_sha256"],
        "validation_id": corpo["prova_duravel"]["validation_id"],
        "confirmar_nascimento_pausado": True,
        "confirmacao_digitada": "CRIAR PAUSADA",
    })


# ---------------------------------------------------------------------------
# 1. FLAGS FECHADAS — zero Keychain, zero banco, zero Meta
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rota", ["aprovar", "criar-pausada", "reconciliar", "recibo"])
def test_flags_fechadas_recusam_antes_de_keychain_banco_ou_rede(monkeypatch, rota) -> None:
    _fechar_tudo(monkeypatch)
    corpos = {
        "aprovar": {
            "plano": _plano_para_envio(), "plano_sha256_esperado": "a" * 64,
            "validation_id": "validation-0001",
            "confirmar_nascimento_pausado": True, "confirmacao_digitada": "CRIAR PAUSADA",
        },
        "criar-pausada": {"approval_id": "approval-0001", "plano_sha256_esperado": "a" * 64},
        "reconciliar": {"approval_id": "approval-0001"},
        "recibo": {"approval_id": "approval-0001"},
    }
    resposta = _cliente().post(f"/api/trafego/meta/local/criacao/{rota}", json=corpos[rota])
    assert resposta.status_code == 409
    detalhe = resposta.json()["detail"]
    assert detalhe["codigo"] == "META_CREATE_PAUSED_BLOCKED"
    # A causa chega em linguagem de operador; o nome da variável, nunca.
    texto = json.dumps(detalhe, ensure_ascii=False)
    assert "META_CREATE_PAUSED_ENABLED" not in texto
    assert "META_CREATE_LEDGER_WRITE_ENABLED" not in texto
    assert len(detalhe["autorizacoes_ausentes"]) == 2


def test_uma_flag_aberta_nao_basta_para_criar(monkeypatch) -> None:
    """A criação exige as DUAS autorizações; nenhuma delas sozinha serve."""
    _fechar_tudo(monkeypatch)
    monkeypatch.setenv("META_CREATE_PAUSED_ENABLED", "1")
    resposta = _cliente().post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": "approval-0001", "plano_sha256_esperado": "a" * 64})
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_CREATE_PAUSED_BLOCKED"
    assert len(resposta.json()["detail"]["autorizacoes_ausentes"]) == 1


def test_validate_only_ligado_nao_abre_a_criacao(monkeypatch) -> None:
    """⚠️ A licença de OLHAR nunca pode virar licença de GASTAR.

    Se `META_VALIDATE_ONLY_ENABLED` fosse aceita aqui, a lane inteira de
    segurança passaria a depender de qual variável alguém exportou primeiro.
    """
    _fechar_tudo(monkeypatch)
    monkeypatch.setenv("META_VALIDATE_ONLY_ENABLED", "1")
    resposta = _cliente().post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": "approval-0001", "plano_sha256_esperado": "a" * 64})
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_CREATE_PAUSED_BLOCKED"


def test_capacidades_declaram_a_criacao_fechada_sem_citar_variavel(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    for nome in ("META_CREATE_PAUSED_ENABLED", "META_CREATE_LEDGER_WRITE_ENABLED"):
        monkeypatch.delenv(nome, raising=False)
    corpo = _cliente().get("/api/trafego/meta/local/criacao/capacidades").json()
    assert corpo["create_paused"] == "BLOCKED_BY_SERVER_FLAG"
    assert corpo["activation"] == "NOT_IMPLEMENTED"
    assert "META_CREATE" not in json.dumps(corpo, ensure_ascii=False)


def test_capacidades_declaram_a_criacao_liberada_quando_as_duas_flags_abrem(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_CREATE_PAUSED_ENABLED", "1")
    monkeypatch.setenv("META_CREATE_LEDGER_WRITE_ENABLED", "1")
    corpo = _cliente().get("/api/trafego/meta/local/criacao/capacidades").json()
    assert corpo["create_paused"] == "ENABLED"
    # Liberar a criação NUNCA libera a ativação.
    assert corpo["activation"] == "NOT_IMPLEMENTED"


def test_nenhuma_rota_de_ativacao_existe_no_app_inteiro() -> None:
    """A varredura é no APP, não num router.

    ⚠️ A versão anterior desta prova olhava só `trafego_meta_validacao.router`.
    Como a criação nasceu num módulo novo, aquela asserção continuaria verde
    enquanto deixava de significar qualquer coisa — o defeito clássico de um
    tripwire que sobrevive à mudança que deveria detectar.
    """
    app = FastAPI()
    app.include_router(trafego_meta_validacao.router)
    app.include_router(trafego_meta_criacao.router)
    caminhos = {rota.path for rota in app.routes}
    assert "/api/trafego/meta/local/criacao/aprovar" in caminhos
    assert "/api/trafego/meta/local/criacao/criar-pausada" in caminhos
    assert "/api/trafego/meta/local/criacao/reconciliar" in caminhos
    for proibido in ("ativar", "enable", "habilitar", "publicar"):
        assert all(proibido not in caminho for caminho in caminhos), proibido
    # O plano de controle seguro continua sem autoridade de criação.
    seguros = {rota.path for rota in trafego_meta_validacao.router.routes}
    assert all("aprovar" not in caminho and "criar" not in caminho for caminho in seguros)


# ---------------------------------------------------------------------------
# 2. CONFIRMAÇÃO HUMANA E DIVERGÊNCIA DE PLANO
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("mudanca", "codigo"),
    [
        ({"confirmacao_digitada": "criar pausada"}, "META_CREATE_CONFIRMATION_MISSING"),
        ({"confirmacao_digitada": "CRIAR PAUSADO"}, "META_CREATE_CONFIRMATION_MISSING"),
        ({"confirmacao_digitada": "SIM"}, "META_CREATE_CONFIRMATION_MISSING"),
        ({"confirmar_nascimento_pausado": False}, "META_PAUSED_BIRTH_NOT_CONFIRMED"),
    ],
)
def test_aprovacao_exige_a_frase_exata_e_a_confirmacao_pausada(
    monkeypatch, mudanca, codigo,
) -> None:
    """A comparação é literal: sem minúsculas, sem sinônimo, sem quase.

    O Keychain permanece fechado nestas recusas — a confirmação é conferida
    antes de qualquer segredo existir no processo.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    monkeypatch.setattr(
        trafego_meta_criacao, "_credencial_salva",
        lambda *_: pytest.fail("o Keychain foi aberto sem confirmação humana"))
    corpo = {
        "plano": _plano_para_envio(), "plano_sha256_esperado": "a" * 64,
        "validation_id": "validation-0001",
        "confirmar_nascimento_pausado": True, "confirmacao_digitada": "CRIAR PAUSADA",
        **mudanca,
    }
    resposta = _cliente().post("/api/trafego/meta/local/criacao/aprovar", json=corpo)
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == codigo


def test_plano_alterado_depois_da_conferencia_nao_vira_aprovacao(monkeypatch) -> None:
    """O hash da tela precisa reproduzir o hash recompilado no servidor."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()
    validacao = cliente.post("/api/trafego/meta/local/criacao/validar", json={
        "confirmar_validate_only": True, "plano": plano}).json()

    # O operador editou o orçamento depois de conferir. O hash muda.
    alterado = {**plano, "daily_budget_minor": 5000}
    resposta = cliente.post("/api/trafego/meta/local/criacao/aprovar", json={
        "plano": alterado,
        "plano_sha256_esperado": validacao["plano_sha256"],
        "validation_id": validacao["prova_duravel"]["validation_id"],
        "confirmar_nascimento_pausado": True,
        "confirmacao_digitada": "CRIAR PAUSADA",
    })
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_APPROVED_PLAN_DIVERGED"
    assert ledger.aprovacoes == {}


def test_aprovacao_sem_recibo_duravel_falha_fechado(monkeypatch) -> None:
    """Um `validation_id` inventado pelo navegador não abre nada.

    ⚠️ Este é o teste do "recibo verde falso". Sem a tabela de validação, a
    aprovação teria que acreditar no cliente quando ele diz "eu fui validado".
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()
    validacao = cliente.post("/api/trafego/meta/local/criacao/validar", json={
        "confirmar_validate_only": True, "plano": plano}).json()
    resposta = cliente.post("/api/trafego/meta/local/criacao/aprovar", json={
        "plano": plano,
        "plano_sha256_esperado": validacao["plano_sha256"],
        "validation_id": "validation-inventada-pelo-browser",
        "confirmar_nascimento_pausado": True,
        "confirmacao_digitada": "CRIAR PAUSADA",
    })
    assert resposta.status_code == 409
    assert "META_VALIDATION_RECEIPT_NOT_FOUND" in resposta.json()["detail"]["mensagem"]
    assert ledger.aprovacoes == {}


def test_validate_only_com_criacao_fechada_nao_grava_prova_e_diz_isso(monkeypatch) -> None:
    """A validação continua verdadeira; o que ela NÃO faz é fingir durabilidade.

    ⚠️ O recibo de validação pertence à cadeia de autoridade da CRIAÇÃO. Gravá-lo
    com a criação fechada produziria linhas que ninguém pode usar — elas ficam
    velhas em 30 minutos — e faria a lane de criação escrever no Supabase sem as
    duas autorizações que ela exige. Achado 7 da revisão adversarial.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger, ledger_flag=False)
    monkeypatch.setattr(
        ledger, "registrar_validacao",
        lambda **_: pytest.fail("gravou recibo com a criação fechada"))
    corpo = _cliente().post("/api/trafego/meta/local/criacao/validar", json={
        "confirmar_validate_only": True, "plano": _plano_para_envio()}).json()
    # A Meta respondeu e nada foi criado: isso continua sendo dito.
    assert corpo["ok"] is True
    assert corpo["objetos_criados"] == 0
    assert corpo["cobertura"] == "INDEPENDENT_ROOTS_ONLY"
    # E a ausência de prova durável é declarada, não escondida.
    assert corpo["prova_duravel"]["registrada"] is False
    assert corpo["prova_duravel"]["codigo"] == "META_CREATE_PAUSED_BLOCKED"
    assert ledger.validacoes == {}


def test_validate_only_com_ledger_indisponivel_declara_a_falha(monkeypatch) -> None:
    """Criação aberta, mas a autoridade persistente recusa: falha declarada."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)

    async def _recusa(**_: Any) -> dict[str, Any]:
        raise ErroDeNascimentoMeta(
            "META_CREATE_LEDGER_UNAVAILABLE",
            "o Supabase operacional nao esta configurado neste backend")

    monkeypatch.setattr(ledger, "registrar_validacao", _recusa)
    corpo = _cliente().post("/api/trafego/meta/local/criacao/validar", json={
        "confirmar_validate_only": True, "plano": _plano_para_envio()}).json()
    assert corpo["ok"] is True
    assert corpo["prova_duravel"]["registrada"] is False
    assert corpo["prova_duravel"]["codigo"] == "META_CREATE_LEDGER_UNAVAILABLE"


def test_duas_aprovacoes_vivas_do_mesmo_plano_sao_recusadas(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        primeira = await _aprovar(cliente, ledger, plano)
        assert primeira.status_code == 200, primeira.text
        segunda = await _aprovar(cliente, ledger, plano)
        assert segunda.status_code == 409
        assert "META_APPROVAL_ALREADY_LIVE" in segunda.json()["detail"]["mensagem"]
        assert len(ledger.aprovacoes) == 1

    asyncio.run(cenario())


# ---------------------------------------------------------------------------
# 3. HAPPY PATH HERMÉTICO
# ---------------------------------------------------------------------------

def test_saga_nasce_na_ordem_com_recibo_antes_de_cada_chamada(monkeypatch) -> None:
    """A prova central: ordem, recibo antes do POST, PAUSED e read-back.

    A ordem dos eventos é conferida INTEIRA, não por amostragem. Um recibo
    aberto depois da chamada seria invisível numa asserção que só olhasse o
    conjunto de eventos.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _aprovar(cliente, ledger, plano)
        assert aprovacao.status_code == 200, aprovacao.text
        corpo_aprovacao = aprovacao.json()["aprovacao"]
        assert corpo_aprovacao["operacoes"] == 4
        assert corpo_aprovacao["manifesto"] == [
            "campaign", "adset", "creative:variation-001", "ad:variation-001"]
        assert corpo_aprovacao["orcamento_diario_minor"] == 1000
        assert corpo_aprovacao["moeda"] == "BRL"
        assert corpo_aprovacao["nascimento_pausado_confirmado"] is True

        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": corpo_aprovacao["approval_id"],
            "plano_sha256_esperado": corpo_aprovacao["plano_sha256"],
        })
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["desfecho"] == "CREATED_PAUSED"
        assert corpo["retry_permitido"] is False

        # ORDEM DA SAGA: cada passo prepara o recibo, cria e fecha, nesta ordem.
        saga = [evento for evento in ledger.eventos if evento[0] != "validacao"]
        assert saga == [
            ("aprovacao", "approval-0002"),
            ("preparar", "campaign"), ("fechar", "passo-campaign"),
            ("preparar", "adset"), ("fechar", "passo-adset"),
            ("preparar", "creative:variation-001"), ("fechar", "passo-creative:variation-001"),
            ("preparar", "ad:variation-001"), ("fechar", "passo-ad:variation-001"),
        ]
        assert CENARIO.criados == ["campaign", "adset", "creative", "ad"]

        # TUDO O QUE VEICULA NASCE PAUSADO — no payload e no read-back.
        for chave in ("campaign", "adset", "ad:variation-001"):
            assert corpo["read_back"][chave]["veiculavel"] is True
            assert corpo["read_back"][chave]["status"] == "PAUSED"
        assert corpo["read_back"]["creative:variation-001"]["veiculavel"] is False

        # O recibo fecha com os quatro passos criados.
        assert [passo["state"] for passo in corpo["recibo"]["steps"]] == ["CREATED"] * 4
        assert all(passo["has_external_id"] for passo in corpo["recibo"]["steps"])

    asyncio.run(cenario())


def test_a_criacao_nunca_emite_status_diferente_de_paused(monkeypatch) -> None:
    """Nenhum POST desta lane pode carregar ACTIVE, e nenhum carrega ENABLE."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        veiculaveis = [
            corpo for url, corpo in CENARIO.posts
            if _tipo_do_endpoint(url) in {"campaign", "adset", "ad"}
        ]
        assert veiculaveis, "a saga não despachou nenhum objeto veiculável"
        for corpo in veiculaveis:
            assert corpo["status"] == "PAUSED"
        serializado = json.dumps([corpo for _, corpo in CENARIO.posts], ensure_ascii=False)
        for proibido in ("ACTIVE", "ENABLE", "ARCHIVED"):
            assert proibido not in serializado

    asyncio.run(cenario())


def test_a_resposta_da_criacao_nao_carrega_token_id_bruto_nem_image_hash(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        serializado = resposta.text
        for cru in (TOKEN, CONTA_EXTERNA, PAGINA_EXTERNA, IMAGEM_EXTERNA,
                    *IDS_CRIADOS.values()):
            assert cru not in serializado, cru
        # As referências que chegam ao navegador são opacas e do domínio.
        for referencia in resposta.json()["referencias_opacas"].values():
            assert referencia.startswith("metaobj_")

    asyncio.run(cenario())


def test_criar_com_hash_de_outra_versao_nao_executa_nada(monkeypatch) -> None:
    """Uma aba antiga pedindo a criação de uma versão que não foi aprovada."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": "f" * 64,
        })
        assert resposta.status_code == 409
        assert resposta.json()["detail"]["codigo"] == "META_APPROVED_PLAN_DIVERGED"
        assert not any(evento[0] == "preparar" for evento in ledger.eventos)

    asyncio.run(cenario())


def test_criacao_pedida_por_outra_pessoa_para_antes_do_keychain(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        # Depois da aprovação, o Keychain vira armadilha: a divergência de ator
        # precisa parar antes de qualquer segredo ser lido.
        monkeypatch.setattr(
            trafego_meta_criacao, "_credencial_salva",
            lambda *_: pytest.fail("o Keychain foi aberto para um ator divergente"))
        outro = FastAPI()
        outro.include_router(trafego_meta_criacao.router)
        outro.dependency_overrides[exigir_admin] = lambda: Identidade(
            sub="outro-operador", email="outro@volc", papel="ADMIN", origem="sessao")
        resposta = TestClient(outro, headers={"host": "localhost"}).post(
            "/api/trafego/meta/local/criacao/criar-pausada", json={
                "approval_id": aprovacao["approval_id"],
                "plano_sha256_esperado": aprovacao["plano_sha256"],
            })
        assert resposta.status_code == 409
        assert resposta.json()["detail"]["codigo"] == "META_APPROVAL_ACTOR_DIVERGED"

    asyncio.run(cenario())


# ---------------------------------------------------------------------------
# 4. A META RECUSA — passo FALHO, filhos não executados
# ---------------------------------------------------------------------------

def test_recusa_da_meta_no_adset_falha_o_passo_e_nao_cria_os_filhos(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        CENARIO.recusar_em = "adset"
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        # 422: a Meta OLHOU e recusou. Está provado que o AdSet não nasceu.
        assert resposta.status_code == 422
        detalhe = resposta.json()["detail"]
        assert detalhe["codigo"] == "META_REMOTE_CREATE_FAILED"
        assert detalhe["reconciliacao_necessaria"] is False
        assert detalhe["objetos_criados"] == ["campaign"]
        assert ledger.passos["passo-adset"]["state"] == "FAILED"
        # Os filhos do AdSet nunca foram preparados.
        assert "passo-creative:variation-001" not in ledger.passos
        assert "passo-ad:variation-001" not in ledger.passos
        assert CENARIO.criados == ["campaign"]

    asyncio.run(cenario())


# ---------------------------------------------------------------------------
# 5. TIMEOUT DEPOIS DO DESPACHO — AMBIGUO, sem retry, sem filhos
# ---------------------------------------------------------------------------

def test_silencio_depois_do_despacho_fica_ambiguo_e_nunca_autoriza_retry(monkeypatch) -> None:
    """⚠️ A diferença entre 422 e 502 é a diferença entre reenviar e duplicar.

    Um timeout na criação não prova nada: o objeto pode ter nascido enquanto
    ninguém olhava. A resposta precisa dizer isso sem ambiguidade de protocolo
    e sem uma única permissão de retentar.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        CENARIO.silenciar_em = "adset"
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        assert resposta.status_code == 502
        detalhe = resposta.json()["detail"]
        assert detalhe["codigo"] == "META_REMOTE_RESULT_AMBIGUOUS"
        assert detalhe["retry_permitido"] is False
        assert detalhe["reconciliacao_necessaria"] is True
        assert detalhe["objetos_criados"] == ["campaign"]
        # O passo silencioso ficou AMBÍGUO, e não FALHO.
        assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"
        assert "passo-creative:variation-001" not in ledger.passos
        assert CENARIO.criados == ["campaign"]

    asyncio.run(cenario())


def test_um_segundo_pedido_sobre_passo_ambiguo_nao_reenvia_o_post(monkeypatch) -> None:
    """O clique repetido não vira segunda campanha — nem com a tela cooperando.

    A garantia é do LEDGER, não da interface: reentrar num passo em voo devolve
    AMBIGUO, e a saga para ali.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        pedido = {
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        }
        CENARIO.silenciar_em = "adset"
        primeira = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json=pedido)
        assert primeira.status_code == 502
        criados_apos_a_primeira = list(CENARIO.criados)

        segunda = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json=pedido)
        assert segunda.status_code == 502
        assert segunda.json()["detail"]["codigo"] == "META_RECONCILIATION_REQUIRED"
        # Nenhum objeto novo saiu: a campanha foi retomada pelo recibo CRIADO e
        # o conjunto ambíguo barrou o lote.
        assert CENARIO.criados == criados_apos_a_primeira

    asyncio.run(cenario())


# ---------------------------------------------------------------------------
# 6. READ-BACK DIVERGENTE — nunca um recibo verde
# ---------------------------------------------------------------------------

def test_objeto_que_volta_ativo_nao_vira_recibo_verde(monkeypatch) -> None:
    """A pior divergência possível: a Meta devolve ACTIVE onde pedimos PAUSED.

    Se isso virasse 200, a tela diria "tudo pausado" sobre uma campanha
    veiculando — e o operador só descobriria pela fatura.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        CENARIO.divergir_em = "campaign"
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        assert resposta.status_code == 502
        detalhe = resposta.json()["detail"]
        assert detalhe["codigo"] == "META_READBACK_DIVERGENT"
        # O campo exato: "effective_status" também contém "status", e uma
        # asserção frouxa aceitaria a guarda errada. As duas linhas juntas
        # fixam QUAL guarda recusou.
        assert "no campo status" in detalhe["mensagem"]
        assert "no campo effective_status" not in detalhe["mensagem"]
        assert detalhe["retry_permitido"] is False
        # A saga parou no primeiro degrau: nada dependente foi criado.
        assert CENARIO.criados == ["campaign"]
        assert "passo-adset" not in ledger.passos

    asyncio.run(cenario())


# ---------------------------------------------------------------------------
# 7. RECONCILIAÇÃO — só leitura, e nunca uma decisão de reenviar
# ---------------------------------------------------------------------------

async def _ambiguar(cliente, ledger, plano) -> dict[str, Any]:
    aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
    CENARIO.silenciar_em = "adset"
    resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": aprovacao["approval_id"],
        "plano_sha256_esperado": aprovacao["plano_sha256"],
    })
    assert resposta.status_code == 502
    assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"
    return aprovacao


def test_reconciliacao_fecha_como_criado_quando_a_leitura_encontra_o_objeto(
    monkeypatch,
) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _ambiguar(cliente, ledger, plano)
        # O objeto EXISTE na conta: o POST tinha chegado antes do silêncio.
        CENARIO.silenciar_em = None
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [_objeto_lido("adset")],
            "adcreatives": [],
            "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["efeito_externo"] == "NENHUM"
        assert corpo["passos_ambiguos"] == 1
        assert corpo["conclusoes"] == [{
            "passo": "adset", "tipo": "adset",
            "conclusao": "FECHADO_COMO_CRIADO",
            "explicacao": "o objeto existe na conta e confere com o plano aprovado",
        }]
        assert ledger.passos["passo-adset"]["state"] == "CREATED"
        # ⚠️ Reconciliar NUNCA despacha. Nenhum POST novo saiu.
        assert CENARIO.criados == ["campaign"]

    asyncio.run(cenario())


def test_reconciliacao_fecha_como_nao_encontrado_com_listagem_completa(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _ambiguar(cliente, ledger, plano)
        CENARIO.silenciar_em = None
        # A conta tem a campanha e NÃO tem o conjunto. A listagem terminou.
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [],
            "adcreatives": [],
            "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        assert resposta.status_code == 200, resposta.text
        conclusao = resposta.json()["conclusoes"][0]
        assert conclusao["conclusao"] == "FECHADO_COMO_NAO_ENCONTRADO"
        assert ledger.passos["passo-adset"]["state"] == "FAILED"
        assert ledger.passos["passo-adset"]["codigo"] == "META_RECONCILED_ABSENT"
        assert CENARIO.criados == ["campaign"]

    asyncio.run(cenario())


def test_leitura_inconclusiva_mantem_o_passo_ambiguo(monkeypatch) -> None:
    """Não conseguir provar a ausência não é prová-la.

    Dois objetos com o mesmo nome aprovado é ambiguidade REAL na conta.
    Escolher um seria inventar o recibo; fechar como ausente autorizaria um
    reenvio sobre um objeto que existe.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _ambiguar(cliente, ledger, plano)
        CENARIO.silenciar_em = None
        gemeo = {**_objeto_lido("adset"), "id": "9999"}
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [_objeto_lido("adset"), gemeo],
            "adcreatives": [],
            "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        assert resposta.status_code == 200, resposta.text
        conclusao = resposta.json()["conclusoes"][0]
        assert conclusao["conclusao"] == "PERMANECE_AMBIGUO"
        assert "mais de um objeto" in conclusao["explicacao"]
        assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"

    asyncio.run(cenario())


def test_reconciliacao_nao_fecha_objeto_que_diverge_do_plano_aprovado(monkeypatch) -> None:
    """Achar o NOME certo não basta: o objeto tem que ser o objeto aprovado."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _ambiguar(cliente, ledger, plano)
        CENARIO.silenciar_em = None
        impostor = {**_objeto_lido("adset"),
                    "configured_status": "ACTIVE", "effective_status": "ACTIVE"}
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [impostor],
            "adcreatives": [],
            "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        conclusao = resposta.json()["conclusoes"][0]
        assert conclusao["conclusao"] == "PERMANECE_AMBIGUO"
        assert "divergiu do plano aprovado" in conclusao["explicacao"]
        assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"

    asyncio.run(cenario())


def test_reconciliacao_de_recibo_sem_ambiguidade_nao_le_a_conta(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        assert resposta.status_code == 200
        assert resposta.json()["passos_ambiguos"] == 0
        assert resposta.json()["conclusoes"] == []

    asyncio.run(cenario())


def test_recibo_devolvido_ao_navegador_afirma_o_id_sem_entrega_lo(monkeypatch) -> None:
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        resposta = cliente.post("/api/trafego/meta/local/criacao/recibo", json={
            "approval_id": aprovacao["approval_id"]})
        assert resposta.status_code == 200
        texto = resposta.text
        for cru in IDS_CRIADOS.values():
            assert cru not in texto
        assert all(passo["has_external_id"] for passo in resposta.json()["recibo"]["steps"])

    asyncio.run(cenario())


# ---------------------------------------------------------------------------
# 8. OS ACHADOS DA REVISÃO ADVERSARIAL
# ---------------------------------------------------------------------------
# Cada teste abaixo nasceu de um achado verificado no código. Eles não provam
# "o conserto existe": provam o CENÁRIO que o conserto impede, e por isso
# continuam vermelhos se alguém reverter a correção.

def test_ambiguidade_por_erro_5xx_nao_e_apresentada_como_recusa_provada(
    monkeypatch,
) -> None:
    """ACHADO 5 — o ledger e o protocolo contavam histórias diferentes.

    Um 500 da Meta com objeto `error` NÃO prova que nada nasceu: `_post` não
    marca `criacao_descartada` e a saga deixa o passo AMBIGUOUS. A resposta,
    porém, era 422 com `reconciliacao_necessaria=false` — porque a rota
    classificava por uma lista de códigos em vez de perguntar à saga.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    class _CincoCentos(_GraphFalso):
        async def post(self, url: str, *, data: Any = None, headers: Any = None):
            corpo = dict(data or {})
            if "execution_options" not in corpo and _tipo_do_endpoint(url) == "adset":
                CENARIO.posts.append((url, corpo))
                return _Resposta({"error": {
                    "code": 2, "message": "Service temporarily unavailable"}}, status=500)
            return await super().post(url, data=data, headers=headers)

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        monkeypatch.setattr(trafego_meta_validacao.httpx, "AsyncClient", _CincoCentos)
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        detalhe = resposta.json()["detail"]
        # O passo ficou AMBÍGUO no livro...
        assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"
        # ...e o protocolo precisa dizer a mesma coisa.
        assert resposta.status_code == 502
        assert detalhe["reconciliacao_necessaria"] is True
        assert detalhe["retry_permitido"] is False

    asyncio.run(cenario())


def test_readback_divergente_fica_gravado_no_recibo(monkeypatch) -> None:
    """ACHADO 3 — o recibo dizia só CREATED sobre um objeto que divergiu.

    A ordem fecha-antes-de-ler é DELIBERADA: o id precisa estar gravado antes de
    qualquer outra coisa, senão uma queda entre o POST e o INSERT o perde para
    sempre. O conserto não inverte a ordem — ele anota a divergência.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        CENARIO.divergir_em = "campaign"
        resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        assert resposta.status_code == 502
        passo = ledger.passos["passo-campaign"]
        # O objeto EXISTE — a Meta devolveu id — e o livro o registra.
        assert passo["state"] == "CREATED"
        assert passo["id_externo"] == IDS_CRIADOS["campaign"]
        # E o livro também registra que a leitura não confirmou o objeto.
        assert passo["readback"] == "META_READBACK_DIVERGENT"
        assert ("readback", "passo-campaign") in ledger.eventos

    asyncio.run(cenario())


def test_reconciliacao_recusa_objeto_que_ja_existia_antes_do_despacho(
    monkeypatch,
) -> None:
    """ACHADO 4 — nome igual não prova nascimento.

    A conta já tem uma campanha homônima, com a mesma receita, criada semana
    passada. Fechá-la como o objeto do nosso despacho penduraria o AdSet novo
    numa campanha antiga. O `created_time` é o que desempata.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _ambiguar(cliente, ledger, plano)
        CENARIO.silenciar_em = None
        antigo = {**_objeto_lido("adset"), "created_time": "2026-08-29T09:00:00+0000"}
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [antigo],
            "adcreatives": [], "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        conclusao = resposta.json()["conclusoes"][0]
        assert conclusao["conclusao"] == "PERMANECE_AMBIGUO"
        assert "já existia antes deste despacho" in conclusao["explicacao"]
        assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"

    asyncio.run(cenario())


def test_criativo_nunca_e_fechado_por_leitura(monkeypatch) -> None:
    """ACHADO 4, corolário — AdCreative não expõe `created_time`.

    Sem carimbo de nascimento não existe prova de que o criativo encontrado
    nasceu deste despacho. Um criativo antigo e homônimo seria adotado em
    silêncio, então a leitura nunca o fecha.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = (await _aprovar(cliente, ledger, plano)).json()["aprovacao"]
        CENARIO.silenciar_em = "creative"
        cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
            "approval_id": aprovacao["approval_id"],
            "plano_sha256_esperado": aprovacao["plano_sha256"],
        })
        assert ledger.passos["passo-creative:variation-001"]["state"] == "AMBIGUOUS"
        CENARIO.silenciar_em = None
        sem_carimbo = {k: v for k, v in _objeto_lido("creative").items()
                       if k != "created_time"}
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [_objeto_lido("adset")],
            "adcreatives": [sem_carimbo],
            "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        conclusao = resposta.json()["conclusoes"][0]
        assert conclusao["conclusao"] == "PERMANECE_AMBIGUO"
        assert "instante de criação" in conclusao["explicacao"]
        assert ledger.passos["passo-creative:variation-001"]["state"] == "AMBIGUOUS"

    asyncio.run(cenario())


def test_ausencia_nao_pode_ser_fechada_enquanto_alguem_ainda_pode_despachar(
    monkeypatch,
) -> None:
    """ACHADO 2 — o passo vira ambíguo antes de o POST original sair.

    Uma segunda chamada reentra no passo e o SQL o marca AMBIGUOUS enquanto a
    primeira ainda está dentro do `await` do POST. Fechar como ausente nesse
    instante gravaria "não existe" sobre um objeto prestes a nascer, e liberaria
    uma nova aprovação sobre ele.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()

    async def cenario() -> None:
        aprovacao = await _ambiguar(cliente, ledger, plano)
        # O passo é jovem: alguém ainda pode ter autoridade para despachar.
        ledger.passos["passo-adset"]["jovem"] = True
        CENARIO.silenciar_em = None
        CENARIO.listagens = {
            "campaigns": [_objeto_lido("campaign")],
            "adsets": [], "adcreatives": [], "ads": [],
        }
        resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar", json={
            "approval_id": aprovacao["approval_id"]})
        # A leitura concluiu AUSENTE, mas o ledger recusou fechar.
        assert resposta.status_code == 409
        assert "META_RECONCILE_TOO_SOON" in resposta.json()["detail"]["mensagem"]
        assert ledger.passos["passo-adset"]["state"] == "AMBIGUOUS"

    asyncio.run(cenario())


def test_recibo_de_validacao_inventado_para_antes_do_keychain(monkeypatch) -> None:
    """ACHADO 8 — a ordem prometida é ledger antes do segredo.

    A autoridade continua sendo a RPC de aprovação, que reconfere tudo. O que
    este teste fixa é a ORDEM: um `validation_id` que o banco não conhece não
    pode custar uma leitura do Keychain nem uma requisição à Meta.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    monkeypatch.setattr(
        trafego_meta_criacao, "_credencial_salva",
        lambda *_: pytest.fail("o Keychain foi aberto por um recibo inexistente"))
    monkeypatch.setattr(
        trafego_meta_validacao.httpx, "AsyncClient",
        lambda *a, **k: pytest.fail("saiu HTTP por um recibo inexistente"))
    resposta = _cliente().post("/api/trafego/meta/local/criacao/aprovar", json={
        "plano": _plano_para_envio(),
        "plano_sha256_esperado": "a" * 64,
        "validation_id": "validation-que-nao-existe",
        "confirmar_nascimento_pausado": True,
        "confirmacao_digitada": "CRIAR PAUSADA",
    })
    assert resposta.status_code == 409
    assert "META_VALIDATION_RECEIPT_NOT_FOUND" in resposta.json()["detail"]["mensagem"]


def test_recibo_de_outro_ator_para_antes_do_keychain(monkeypatch) -> None:
    """ACHADO 8 — validar como uma pessoa e aprovar como outra."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    plano = _plano_para_envio()
    validacao = cliente.post("/api/trafego/meta/local/criacao/validar", json={
        "confirmar_validate_only": True, "plano": plano}).json()

    monkeypatch.setattr(
        trafego_meta_criacao, "_credencial_salva",
        lambda *_: pytest.fail("o Keychain foi aberto para um recibo de outra pessoa"))
    outro = FastAPI()
    outro.include_router(trafego_meta_criacao.router)
    outro.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub="outro-operador", email="outro@volc", papel="ADMIN", origem="sessao")
    resposta = TestClient(outro, headers={"host": "localhost"}).post(
        "/api/trafego/meta/local/criacao/aprovar", json={
            "plano": plano,
            "plano_sha256_esperado": validacao["plano_sha256"],
            "validation_id": validacao["prova_duravel"]["validation_id"],
            "confirmar_nascimento_pausado": True,
            "confirmacao_digitada": "CRIAR PAUSADA",
        })
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_VALIDATION_ACTOR_DIVERGED"
