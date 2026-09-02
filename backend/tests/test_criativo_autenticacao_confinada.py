"""A regressao de autenticacao das rotas criativas, confinada ao `tmp_path`.

## As duas perguntas, e por que precisam ser respondidas juntas

1. **O portao recusa na ordem certa?** 401 sem credencial e sem CHAMAR o
   provedor; 401 com sessao invalida ou expirada, apurada no provedor; 503
   quando o provedor esta fora do ar (indisponibilidade nao vira permissao);
   403 para identidade valida sem papel; e so entao a rota real, que aqui
   responde 404 por id inexistente.
2. **A recusa escreve alguma coisa?** Um teste de recusa que cria o SQLite da
   bancada, ou a pasta `~/.volc-os`, esta provando o portao e sujando a maquina
   de quem o roda — e o rastro sobrevive ao teste.

⚠️ Elas andam juntas porque separa-las esconde o defeito: um portao que recusa
DEPOIS de montar a bancada passa na pergunta 1 e reprova na 2, e a suite que so
faz a primeira pergunta diz que esta tudo bem.

## O que e real e o que e dublado

Real: o app de PRODUCAO (`app.main:app`), o roteamento, as dependencias
`exigir_usuario` e `exigir_admin`, `_usuario_do_token`, `_papel_do_sub` e o
tratamento de erro do FastAPI.

Dublado: **so o transporte**. `ident.httpx` e trocado por um `AsyncClient` falso
que devolve respostas montadas a mao. Dublar a dependencia inteira faria o teste
medir o dublê; dublando o socket, a logica de decisao continua sendo a de
producao, e as CHAMADAS ficam contaveis — e a contagem e o que prova a ordem do
portao, nao so o codigo de status final.

## Confinamento

`HOME`, `CRIATIVO_BANCADA_DIR` e `CRIATIVO_STORAGE_DIR` apontam para dentro do
`tmp_path`. No fim, a arvore inteira do `tmp_path` e varrida e cada arquivo tem
de estar dentro dele; alem disso, `~/.volc-os` do HOME REAL e a listagem da raiz
do repositorio sao conferidas antes e depois, porque "nao escreveu fora" so vale
se alguem tiver olhado para fora.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.seguranca import identidade as ident

pytestmark = [pytest.mark.identidade_real, pytest.mark.sem_env_file]

SUB = "33333333-3333-4333-8333-333333333333"
RAIZ = Path(__file__).resolve().parents[2]

#: O HOME de verdade de quem roda a suite, capturado ANTES de qualquer
#: `monkeypatch`. E contra ele que o confinamento e conferido.
HOME_REAL = Path.home()


class _AuthFalso:
    """O Supabase, no lugar do socket. Conta o que foi perguntado, e em que ordem."""

    def __init__(
        self,
        *,
        usuario: dict[str, Any] | None = None,
        status_auth: int = 200,
        papel: str = "ADMIN",
        status_papel: int = 200,
        erro_de_rede: bool = False,
    ) -> None:
        self.usuario = (
            usuario
            if usuario is not None
            else {"id": SUB, "email": "operador@volc.test"}
        )
        self.status_auth = status_auth
        self.papel = papel
        self.status_papel = status_papel
        self.erro_de_rede = erro_de_rede
        self.chamadas: list[dict[str, Any]] = []

    def responder(
        self,
        metodo: str,
        url: str,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.chamadas.append(
            {
                "metodo": metodo,
                "url": url,
                "headers": headers or {},
                "json": json_body or {},
            }
        )
        if self.erro_de_rede:
            raise httpx.ConnectError("auth fora do ar (simulado)")
        request = httpx.Request(metodo, url)
        if "/auth/v1/user" in url:
            corpo = self.usuario if self.status_auth == 200 else {"msg": "invalid"}
            return httpx.Response(self.status_auth, json=corpo, request=request)
        if f"/rest/v1/rpc/{ident.RPC_PAPEL}" in url:
            if self.status_papel >= 400:
                return httpx.Response(
                    self.status_papel, json={"msg": "erro"}, request=request
                )
            return httpx.Response(200, json=self.papel, request=request)
        raise AssertionError(f"URL inesperada no auth falso: {url}")

    @property
    def chamadas_auth(self) -> list[dict[str, Any]]:
        return [c for c in self.chamadas if "/auth/v1/user" in c["url"]]

    @property
    def chamadas_papel(self) -> list[dict[str, Any]]:
        return [c for c in self.chamadas if ident.RPC_PAPEL in c["url"]]


@pytest.fixture
def instalar_auth(monkeypatch):
    """Troca SO o transporte de `app.seguranca.identidade`.

    ⚠️ `_usuario_do_token` e `_papel_do_sub` continuam sendo os de producao. Se
    o dublê fosse a dependencia (`exigir_usuario`), este modulo mediria o dublê
    e a suite de seguranca viraria decoracao — que e a razao de o `conftest.py`
    exigir o marcador `identidade_real` para tirar o dublê de identidade.
    """

    def instalar(auth: _AuthFalso) -> _AuthFalso:
        class ClienteFalso:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def get(self, url, headers=None, params=None):
                return auth.responder("GET", url, headers=headers)

            async def post(self, url, headers=None, json=None):
                return auth.responder("POST", url, headers=headers, json_body=json)

        monkeypatch.setattr(
            ident,
            "httpx",
            SimpleNamespace(AsyncClient=ClienteFalso, HTTPError=httpx.HTTPError),
        )
        return auth

    return instalar


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        supabase_url="https://auth.invalid",
        supabase_service_role_key="service-role-de-teste",
        criativo_url_secret="s" * 32,
        criativo_storage_dir=str(tmp_path / "storage"),
        volc_service_key=None,
    )


@pytest.fixture
def cliente_isolado(monkeypatch, tmp_path):
    """O app de producao, com todo caminho de escrita apontado para o `tmp_path`.

    ⚠️ A conferencia de threads no teardown nao e zelo: o `Reaper` e o
    `Batimento` sao daemons, e uma thread vazada continuaria batendo num SQLite
    de `tmp_path` que o pytest ja apagou — falha intermitente em OUTRO modulo,
    sem nenhum rastro apontando para aqui.
    """
    from app.criativo import armazenamento
    from app.criativo.bancada import servico
    from app.main import app
    from app.routers import criativos

    bancada = tmp_path / "bancada"
    casa = tmp_path / "home"
    casa.mkdir(parents=True, exist_ok=True)
    overrides_antes = dict(app.dependency_overrides)
    threads_antes = {
        t.ident
        for t in threading.enumerate()
        if t.name.startswith(("bancada-reaper", "batimento-"))
    }

    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("CRIATIVO_BANCADA_DIR", str(bancada))
    monkeypatch.setenv("CRIATIVO_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(servico, "_BANCADA", None, raising=False)
    monkeypatch.setattr(servico, "_REAPER", None, raising=False)
    monkeypatch.setattr(armazenamento, "_padrao", None, raising=False)
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    get_settings.cache_clear()

    try:
        yield TestClient(app, raise_server_exceptions=False), bancada
    finally:
        servico.parar_reaper()
        monkeypatch.setattr(servico, "_BANCADA", None, raising=False)
        monkeypatch.setattr(servico, "_REAPER", None, raising=False)
        monkeypatch.setattr(armazenamento, "_padrao", None, raising=False)
        criativos._executor_cache.clear()
        criativos._motor_cache = None
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_antes)
        get_settings.cache_clear()
        threads_depois = {
            t.ident
            for t in threading.enumerate()
            if t.name.startswith(("bancada-reaper", "batimento-"))
        }
        assert threads_depois == threads_antes, "thread da bancada vazou do teste"


@pytest.fixture(autouse=True)
def nada_escapa_do_tmp(tmp_path):
    """A varredura, aplicada a TODO teste do modulo — inclusive os que recusam.

    ⚠️ Autouse de proposito. Se a varredura fosse opcional, o teste seguinte
    nasceria sem ela, e o confinamento voltaria a ser promessa. Tres olhares:
    a arvore do `tmp_path` (tudo tem de estar dentro), o `~/.volc-os` do HOME
    REAL (nao pode nascer) e a listagem da raiz do repositorio (nao pode mudar).
    """
    volc_no_home_real = HOME_REAL / ".volc-os"
    existia_no_home = volc_no_home_real.exists()
    raiz_antes = sorted(os.listdir(RAIZ))
    backend_antes = sorted(os.listdir(RAIZ / "backend"))

    yield

    escritos = [p for p in tmp_path.rglob("*") if p.is_file()]
    alvo = tmp_path.resolve()
    fora = [p for p in escritos if not p.resolve().is_relative_to(alvo)]
    assert fora == [], f"arquivo escrito fora do diretorio temporario: {fora}"

    assert volc_no_home_real.exists() == existia_no_home, (
        f"o teste criou {volc_no_home_real} no HOME real"
    )
    assert sorted(os.listdir(RAIZ)) == raiz_antes, "o teste escreveu na raiz do repo"
    assert sorted(os.listdir(RAIZ / "backend")) == backend_antes, (
        "o teste escreveu em backend/"
    )


def _assert_json(resposta, status: int, detail: Any) -> None:
    assert resposta.status_code == status, resposta.text
    assert resposta.headers["content-type"].startswith("application/json")
    # ⚠️ O portao NAO manda `WWW-Authenticate`: o cliente e uma SPA com sessao
    # Supabase, e o header faria o navegador abrir o dialogo de basic-auth.
    assert "www-authenticate" not in resposta.headers
    assert resposta.json()["detail"] == detail


# ═══════════════════════════════════════════════════════════════════════════
# 1. Hermetismo: o teste nao depende do `.env` de quem o roda
# ═══════════════════════════════════════════════════════════════════════════


def test_settings_nao_le_env_file_nos_testes_de_autenticacao(monkeypatch):
    """Enxerto da tentativa a3, com o marcador `sem_env_file` do conftest.

    ⚠️ `env_file` inclui `".env"` e `".env.local"`, RELATIVOS ao diretorio
    corrente. Sem o marcador, este teste leria o `.env` plantado abaixo e
    `supabase_url` viria envenenado — e, pior, numa maquina com `backend/.env`
    de verdade a regressao de autenticacao passaria a depender das credenciais
    do operador.
    """
    for nome in Settings.model_fields:
        monkeypatch.delenv(nome.upper(), raising=False)
    get_settings.cache_clear()

    assert Settings.model_config.get("env_file") in ((), None, "")
    assert Settings().supabase_url is None
    assert Settings().supabase_service_role_key is None


def test_um_env_plantado_no_diretorio_corrente_nao_e_lido(monkeypatch, tmp_path):
    """A mesma prova, com o arquivo existindo de fato — e nao so a configuracao.

    Conferir `model_config` prova a CONFIGURACAO; plantar o arquivo prova o
    COMPORTAMENTO. Sem o marcador, `Settings()` aqui devolve `poison.invalid`.
    """
    (tmp_path / ".env").write_text(
        "SUPABASE_URL=https://poison.invalid\nSUPABASE_SERVICE_ROLE_KEY=poison\n",
        encoding="utf-8",
    )
    for nome in Settings.model_fields:
        monkeypatch.delenv(nome.upper(), raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    settings = Settings()

    assert settings.supabase_url is None, "o `.env` do diretorio corrente foi lido"
    assert settings.supabase_service_role_key is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. O portao recusa — e recusa antes de escrever
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_credencial_responde_401_sem_perguntar_ao_provedor(
    cliente_isolado, instalar_auth
):
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso())

    resposta = cliente.get("/api/criativos/bancada/trabalhos")

    _assert_json(resposta, 401, "Credencial ausente.")
    assert auth.chamadas == [], "o portao foi a rede antes de ver que nao ha token"
    assert not bancada.exists(), "a recusa montou a bancada"


def test_credencial_malformada_responde_401_sem_perguntar_ao_provedor(
    cliente_isolado, instalar_auth
):
    """`Basic ...` nao e `Bearer ...`, e isso se decide sem rede."""
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso())

    resposta = cliente.get(
        "/api/criativos/bancada/trabalhos",
        headers={"Authorization": "Basic YWRtaW46YWRtaW4="},
    )

    _assert_json(resposta, 401, "Credencial malformada.")
    assert auth.chamadas == []
    assert not bancada.exists()


def test_sessao_invalida_responde_401_e_nao_apura_papel(cliente_isolado, instalar_auth):
    """A ORDEM importa: papel de token invalido nao se pergunta."""
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(status_auth=401))

    resposta = cliente.get(
        "/api/criativos/bancada/trabalhos",
        headers={"Authorization": "Bearer token-invalido"},
    )

    _assert_json(resposta, 401, "Credencial inválida ou expirada.")
    assert len(auth.chamadas_auth) == 1
    assert auth.chamadas_papel == [], "apurou papel de uma sessao recusada"
    assert not bancada.exists()


def test_token_expirado_responde_401_pelo_contrato_do_provedor(
    cliente_isolado, instalar_auth
):
    """Expirado nao e um caso a parte: quem decide validade e o provedor.

    ⚠️ Validar a assinatura localmente aceitaria sessao ja revogada ate a
    expiracao — e o modulo de identidade documenta essa escolha. Por isso a
    prova exercita o token com `exp` no passado e mede que o veredito veio da
    resposta do provedor, nao de uma inspecao local do JWT.
    """
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(status_auth=401))
    expirado = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIiwiZXhwIjoxfQ.assinatura"

    resposta = cliente.get(
        "/api/criativos/bancada/trabalhos",
        headers={"Authorization": f"Bearer {expirado}"},
    )

    _assert_json(resposta, 401, "Credencial inválida ou expirada.")
    assert len(auth.chamadas_auth) == 1
    assert auth.chamadas_auth[0]["headers"]["Authorization"].endswith(expirado)
    assert auth.chamadas_papel == []
    assert not bancada.exists()


def test_provedor_fora_do_ar_responde_503_e_nao_vira_permissao(
    cliente_isolado, instalar_auth
):
    """Indisponibilidade do auth NAO e autorizacao — e nem e 401.

    401 mandaria o operador entrar de novo por um problema que nao e dele.
    """
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(erro_de_rede=True))

    resposta = cliente.get(
        "/api/criativos/bancada/trabalhos",
        headers={"Authorization": "Bearer token"},
    )

    _assert_json(resposta, 503, "Não foi possível validar a credencial.")
    assert len(auth.chamadas_auth) == 1
    assert auth.chamadas_papel == []
    assert not bancada.exists()


def test_fonte_de_papel_ausente_responde_503_e_diz_que_e_o_banco(
    cliente_isolado, instalar_auth
):
    """404 na RPC significa migration nao aplicada — e o 503 tem de dizer isso.

    Um 503 mudo aqui mandaria o proximo a investigar procurar rede, e nao schema.
    """
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(status_papel=404))

    resposta = cliente.get(
        "/api/criativos/bancada/trabalhos",
        headers={"Authorization": "Bearer token"},
    )

    _assert_json(resposta, 503, "Fonte de autorização indisponível no banco.")
    assert len(auth.chamadas_auth) == 1
    assert len(auth.chamadas_papel) == 1
    assert not bancada.exists()


def test_autenticado_sem_papel_recebe_403_em_rota_admin(cliente_isolado, instalar_auth):
    """403, e nao 401: a identidade vale, a permissao e que nao.

    Colapsar os dois faz o operador tentar o login errado.
    """
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(papel=""))

    resposta = cliente.post(
        "/api/criativos/assets/not-a-uuid/aprovacoes",
        headers={"Authorization": "Bearer token"},
        json={"decisao": "aprovado", "finalidade": "interno"},
    )

    _assert_json(resposta, 403, "Esta operação exige papel administrativo.")
    assert len(auth.chamadas_auth) == 1
    assert len(auth.chamadas_papel) == 1
    assert not bancada.exists()


def test_papel_permitido_chega_ao_contrato_real_e_toma_404(
    cliente_isolado, instalar_auth
):
    """O portao abre e a REGRA responde — 404 de asset inexistente, sem Supabase.

    Sem esta prova, todas as anteriores seriam compativeis com um portao que
    recusa tudo: um 401 universal passaria em sete testes de recusa.
    """
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(papel="ADMIN"))

    resposta = cliente.post(
        "/api/criativos/assets/not-a-uuid/aprovacoes",
        headers={"Authorization": "Bearer token"},
        json={"decisao": "aprovado", "finalidade": "interno"},
    )

    _assert_json(
        resposta,
        404,
        {"codigo": "ESTUDIO.asset_inexistente", "mensagem": "Este item não existe."},
    )
    assert len(auth.chamadas_auth) == 1
    assert len(auth.chamadas_papel) == 1
    assert not bancada.exists()


# ═══════════════════════════════════════════════════════════════════════════
# 3. O caminho feliz escreve — e escreve SO no temporario
# ═══════════════════════════════════════════════════════════════════════════


def test_usuario_autenticado_escreve_so_na_bancada_temporaria(
    cliente_isolado, instalar_auth, tmp_path
):
    """A unica rodada que tem permissao de criar arquivo, e ela cria dentro do tmp.

    ⚠️ Esta prova e o par das de cima: sem ela, "nao escreveu" poderia ser
    apenas "nada nesta suite escreve nunca", e o confinamento nao teria sido
    posto a prova em nenhum momento.
    """
    cliente, bancada = cliente_isolado
    auth = instalar_auth(_AuthFalso(papel="VIEWER"))

    resposta = cliente.get(
        "/api/criativos/bancada/trabalhos",
        headers={"Authorization": "Bearer token"},
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"].startswith("application/json")
    assert resposta.json() == {"trabalhos": []}
    assert len(auth.chamadas_auth) == 1
    assert len(auth.chamadas_papel) == 1
    assert auth.chamadas_papel[0]["json"] == {"p_auth_user_id": SUB}

    assert bancada.exists(), "a rota autenticada nao montou a bancada"
    escritos = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert escritos, "nenhum arquivo criado — a prova de confinamento seria vazia"
    assert any(p.name == "fila.db" for p in escritos), [p.name for p in escritos]
    alvo = tmp_path.resolve()
    assert all(p.resolve().is_relative_to(alvo) for p in escritos)


# ─────────────────────────────────────────────────────────────────────────────
# Leitura cruzada entre inquilinos (achado do revisor adversarial)
# ─────────────────────────────────────────────────────────────────────────────


class _RepoDeDoisDonos:
    """Espelha o `eq.` do PostgREST: com filtro de dono, não devolve linha alheia."""

    JOB_A = "11111111-1111-4111-8111-111111111111"
    JOB_B = "22222222-2222-4222-8222-222222222222"

    def __init__(self) -> None:
        self.jobs = {
            self.JOB_A: {"id": self.JOB_A, "briefing_id": "b-a", "motor": "gemini",
                         "motor_versao": "1", "estado": "succeeded",
                         "criado_por": "usuario-A", "criado_em": "2026-09-01"},
            self.JOB_B: {"id": self.JOB_B, "briefing_id": "b-b", "motor": "gemini",
                         "motor_versao": "1", "estado": "succeeded",
                         "criado_por": "usuario-B", "criado_em": "2026-09-01"},
        }

    async def buscar_job(self, job_id, *, criado_por=None):
        job = self.jobs.get(job_id)
        if job is not None and criado_por is not None and job["criado_por"] != criado_por:
            return None
        return job

    async def listar_jobs(self, *, estados=None, limite=20, criado_por=None):
        linhas = list(self.jobs.values())
        if criado_por is not None:
            linhas = [j for j in linhas if j["criado_por"] == criado_por]
        return linhas[:limite]

    async def renditions_do_job(self, job_id):
        return []

    async def ultimo_seq(self, job_id):
        return 0

    async def buscar_briefing(self, briefing_id):
        return {"projeto_id": "p", "tipo": "imagem", "modo": "full_llm"}

    async def buscar_projeto(self, projeto_id):
        return {"titulo": "BRIEFING CONFIDENCIAL DO USUARIO A"}


def _identidade(sub: str):
    from app.seguranca.identidade import Identidade

    return Identidade(sub=sub, email=f"{sub}@x", papel="", origem="sessao")


def test_ler_job_de_outro_dono_devolve_404_e_nao_o_briefing() -> None:
    """⚠️ VAZAMENTO ENTRE INQUILINOS, achado pelo revisor adversarial.

    `obter_job` ligava a identidade a `_` — literalmente descartava — e chamava
    `repo.buscar_job(job_id)` sem filtro. O repositório também não filtrava:
    `persistencia.buscar_job` consultava `id=eq.<uuid>` e nada mais. Qualquer
    usuário autenticado lia o job de qualquer outro pelo UUID, com o título do
    projeto junto.

    O comentário da rota IRMÃ, na bancada, já tinha escrito a regra: "O UUID não
    é autorização". A bancada aplicou; o Estúdio não.

    E o 404 é o MESMO de "não existe": responder diferente confirmaria a
    existência de job alheio.
    """
    import asyncio

    from fastapi import HTTPException

    from app.criativo.armazenamento import Assinador
    from app.routers.criativos import obter_job

    repo, ass = _RepoDeDoisDonos(), Assinador("s" * 32)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(obter_job(repo.JOB_A, _identidade("usuario-B"), repo, ass))
    assert erro.value.status_code == 404

    # E o dono legítimo continua lendo o próprio.
    meu = asyncio.run(obter_job(repo.JOB_A, _identidade("usuario-A"), repo, ass))
    assert meu["id"] == repo.JOB_A


def test_listar_jobs_nao_devolve_os_de_outro_dono() -> None:
    """Pior que a leitura por UUID: aqui nem era preciso conhecer um id.

    `repo.listar_jobs` não tinha nem PARÂMETRO de dono, então a rota devolvia os
    jobs de TODOS os usuários para qualquer um que a chamasse.
    """
    import asyncio

    from app.criativo.armazenamento import Assinador
    from app.routers.criativos import listar_jobs

    repo, ass = _RepoDeDoisDonos(), Assinador("s" * 32)
    saida = asyncio.run(
        listar_jobs(identidade=_identidade("usuario-B"), repo=repo, assinador=ass,
                    estado=None, limite=20)
    )
    assert len(saida["jobs"]) == 1, "a listagem atravessou inquilino"
    assert saida["jobs"][0]["id"] == repo.JOB_B


# ─────────────────────────────────────────────────────────────────────────────
# Isolamento dos ASSETS (bloqueador 1 da rodada corretiva)
# ─────────────────────────────────────────────────────────────────────────────


class _RepoDeAssetsDeDoisDonos:
    """Espelha o `!inner` do PostgREST: sem o dono casando, a linha SOME.

    ⚠️ Não é um duplo permissivo. Ele reproduz a semântica que a correção usa —
    embed obrigatório `criativo_job!inner(criado_por)` — porque um duplo mais
    frouxo que a produção deixaria a prova passar sobre um filtro que o banco
    real não aplicaria.
    """

    JOB_A, JOB_B = "aaaaaaaa-1111-4111-8111-111111111111", "bbbbbbbb-2222-4222-8222-222222222222"
    ASSET_A, ASSET_B = "a5e7a000-1111-4111-8111-111111111111", "b5e7b000-2222-4222-8222-222222222222"

    def __init__(self) -> None:
        self.jobs = {
            self.JOB_A: {"id": self.JOB_A, "briefing_id": "b-a", "motor": "gemini",
                         "motor_versao": "1", "estado": "succeeded",
                         "criado_por": "usuario-A", "criado_em": "2026-09-01",
                         "procedencia_execucao": "SEGREDO-DE-PROCEDENCIA-DE-A"},
            self.JOB_B: {"id": self.JOB_B, "briefing_id": "b-b", "motor": "gemini",
                         "motor_versao": "1", "estado": "succeeded",
                         "criado_por": "usuario-B", "criado_em": "2026-09-01",
                         "procedencia_execucao": "proc-de-B"},
        }
        self.masters = {
            self.ASSET_A: self._master(self.ASSET_A, self.JOB_A, "1x1"),
            self.ASSET_B: self._master(self.ASSET_B, self.JOB_B, "4x5"),
        }

    @staticmethod
    def _master(mid: str, job_id: str, slot: str) -> dict:
        return {"id": mid, "job_id": job_id, "projeto_id": "p", "slot": slot,
                "kind": "imagem", "versao": 1, "raiz_id": None,
                "storage_chave": f"criativos/p/{job_id}/{slot}_x.png",
                "content_hash": "sha256:" + "c" * 64, "mime": "image/png",
                "bytes_totais": 100, "largura": 10, "altura": 10,
                "motor": "gemini", "motor_versao": "1",
                "insumo_hash": "sha256:" + "d" * 64, "insumo_sanitizado": None,
                "criado_em": "2026-09-01", "arquivado_em": None}

    def _dono(self, master: dict) -> str:
        return self.jobs[master["job_id"]]["criado_por"]

    async def buscar_master_do_dono(self, master_id: str, *, criado_por: str):
        m = self.masters.get(master_id)
        return m if m is not None and self._dono(m) == criado_por else None

    async def versoes_do_master_do_dono(self, raiz_id: str, *, criado_por: str):
        return [m for m in self.masters.values()
                if (m["id"] == raiz_id or m.get("raiz_id") == raiz_id)
                and self._dono(m) == criado_por]

    async def listar_masters_do_dono(self, *, criado_por: str, **_kw):
        linhas = [m for m in self.masters.values() if self._dono(m) == criado_por]
        return linhas, len(linhas), len(linhas)

    async def buscar_job(self, job_id, *, criado_por=None):
        j = self.jobs.get(job_id)
        return j if j is not None and (criado_por is None or j["criado_por"] == criado_por) else None

    async def aprovacoes_de(self, tipo, alvo_id):
        return []

    async def aprovacoes_vigentes_de(self, ids):
        return {}

    async def procedencia_dos_jobs(self, ids):
        # ⚠️ Só responde pelos jobs pedidos. A listagem já foi filtrada pelo dono,
        # então este mapa nunca vê job alheio — e o teste prova isso.
        return {i: self.jobs[i]["procedencia_execucao"] for i in ids if i in self.jobs}

    async def renditions_do_job(self, job_id):
        return []

    async def ultimo_seq(self, job_id):
        return 0

    async def buscar_briefing(self, briefing_id):
        return {"projeto_id": "p", "tipo": "imagem", "modo": "full_llm"}

    async def buscar_projeto(self, projeto_id):
        return {"titulo": "PROJETO"}


def test_asset_de_outro_dono_devolve_o_mesmo_404_de_asset_inexistente() -> None:
    """⚠️ Bloqueador 1. `obter_asset` ligava a identidade a `_`.

    Quatro coisas atravessavam o dono no mesmo DTO — master, versões, aprovações
    e o job com a procedência de execução. O 404 é o MESMO de "não existe":
    responder diferente confirmaria a existência de ativo alheio.
    """
    import asyncio

    from fastapi import HTTPException

    from app.criativo.armazenamento import Assinador
    from app.routers.criativos import obter_asset

    repo, ass = _RepoDeAssetsDeDoisDonos(), Assinador("s" * 32)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(obter_asset(repo.ASSET_A, _identidade("usuario-B"), repo, ass))
    assert erro.value.status_code == 404
    assert erro.value.detail["codigo"] == "ESTUDIO.asset_inexistente"

    # E um id que NÃO existe dá exatamente a mesma resposta.
    with pytest.raises(HTTPException) as inexistente:
        asyncio.run(obter_asset("cccccccc-3333-4333-8333-333333333333",
                                _identidade("usuario-B"), repo, ass))
    assert inexistente.value.detail == erro.value.detail, (
        "a resposta distingue 'não é seu' de 'não existe' e confirma a existência"
    )


def test_o_dono_continua_lendo_o_proprio_asset_com_versoes_e_job() -> None:
    """A correção não pode fechar a porta para quem é dono."""
    import asyncio

    from app.criativo.armazenamento import Assinador
    from app.routers.criativos import obter_asset

    repo, ass = _RepoDeAssetsDeDoisDonos(), Assinador("s" * 32)
    saida = asyncio.run(obter_asset(repo.ASSET_A, _identidade("usuario-A"), repo, ass))
    assert saida["asset"]["id"] == repo.ASSET_A
    assert saida["job"] is not None and saida["job"]["id"] == repo.JOB_A
    assert len(saida["versoes"]) == 1


def test_nem_versoes_nem_job_nem_procedencia_de_outro_dono_entram_no_dto() -> None:
    """Fechar só o master deixaria as outras três passando pela mesma porta.

    A sentinela é a procedência de execução do job de A: ela não pode aparecer em
    NENHUM lugar do JSON que B recebe.
    """
    import asyncio
    import json

    from app.criativo.armazenamento import Assinador
    from app.routers.criativos import obter_asset

    repo, ass = _RepoDeAssetsDeDoisDonos(), Assinador("s" * 32)
    saida = asyncio.run(obter_asset(repo.ASSET_B, _identidade("usuario-B"), repo, ass))
    cru = json.dumps(saida, default=str, ensure_ascii=False)
    assert "SEGREDO-DE-PROCEDENCIA-DE-A" not in cru
    assert repo.ASSET_A not in cru and repo.JOB_A not in cru
    assert all(v["id"] != repo.ASSET_A for v in saida["versoes"])


def test_listar_assets_nao_devolve_nem_conta_os_de_outro_dono() -> None:
    """A contagem também é vazamento: `universo` global diria quantos ativos as
    outras pessoas têm."""
    import asyncio

    from app.criativo.armazenamento import Assinador
    from app.routers.criativos import listar_assets

    repo, ass = _RepoDeAssetsDeDoisDonos(), Assinador("s" * 32)
    saida = asyncio.run(
        listar_assets(identidade=_identidade("usuario-B"), repo=repo, assinador=ass,
                      busca=None, kind=None, estado=None, destino=None,
                      brandPack=None, desde=None, ate=None, limite=60, offset=0)
    )
    ids = [a["id"] for a in saida["assets"]]
    assert ids == [repo.ASSET_B], f"a listagem atravessou inquilino: {ids}"
    assert saida["universo"] == 1, "o universo contou a biblioteca de outra pessoa"


def test_a_porta_do_repositorio_exige_o_dono_no_proprio_contrato() -> None:
    """Não basta filtrar na rota: uma porta que aceita ser chamada sem dono acaba
    sendo chamada sem dono — foi assim que este vazamento nasceu."""
    import inspect

    from app.criativo.persistencia import Repositorio

    for nome in ("buscar_master_do_dono", "versoes_do_master_do_dono",
                 "listar_masters_do_dono"):
        p = inspect.signature(getattr(Repositorio, nome)).parameters["criado_por"]
        assert p.default is inspect.Parameter.empty, (
            f"{nome} aceita ser chamado sem dono"
        )
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
