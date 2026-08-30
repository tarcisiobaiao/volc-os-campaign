"""O portão do Hub — os testes que provam que ele RECUSA.

## Por que este arquivo existe

Inventário do Sprint 1A, medido em 24/08/2026 nesta árvore:

| defeito | onde | medida |
|---|---|---|
| rotas mutantes sem nenhuma dependência de identidade | os 4 routers de `app/main.py:62-68` | 37 |
| rotas de leitura sem nenhum portão | idem | 26 |
| o único portão existente falha ABERTO sem configuração | `app/deps.py:20-21` (`if not expected: return`) | guarda 21 rotas |
| a chave desse portão viaja para o navegador | `src/lib/pautadorApi.ts:37` (`VITE_PAUTADOR_API_KEY`) | — |
| `get_current_user_role()` lê `app.current_user_role`, que ninguém define | zero ocorrências no repositório | — |

Duas dessas rotas (`POST /api/trafego/subir`, `POST /api/trafego/remover`)
mudam uma conta real de anúncios, e os proxies de `api/supabase/*` respondem com
a `service_role` para qualquer um. CORS não é autenticação: `Access-Control-
Allow-Origin: *` não impede `curl`.

## O contrato deste arquivo

**Testes que FALHAM hoje são o gate do sprint, não defeito do teste.** Eles
descrevem o estado alvo — `exigir_usuario` / `exigir_admin` / `exigir_servico`
ligados às rotas, e `require_api_key` fechando quando a configuração falta. A
entrega do Sprint 1A só está pronta quando este arquivo fica inteiro verde.

Cada teste diz, no comentário, O QUE QUEBRA SEM ELE — não o que ele faz.

## O que este arquivo NUNCA faz

- não abre a trava de escrita (`FORGE_PERMITIR_ESCRITA` jamais é definida aqui);
- não chama rota destrutiva (`DELETE`/`PUT`) nem com id inventado — a cobertura
  dessas vem da INSPEÇÃO das rotas, não de exercê-las. Um teste de portão que
  precisa apagar alguma coisa para provar o portão é o próprio risco;
- não alcança o Supabase real: a fixture `_sem_alcance_de_rede` aponta a
  configuração para um host `.invalid` (RFC 6761, NXDOMAIN garantido).

## O irmão deste arquivo

`src/lib/__tests__/seguranca-bundle.test.ts` cobre a outra metade da superfície
— os proxies `api/supabase/*` e `api/users/*` (service_role sem portão, coluna
sensível, RPC arbitrária, autopromoção pelo proxy) e a varredura do bundle. Os
dois juntos fecham a lista do Sprint 1A; nenhum dos dois sozinho.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from types import SimpleNamespace
from typing import Any, Optional

import httpx
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.seguranca import identidade as ident
from app.trafego import escopo

# Este módulo existe para PROVAR que o portão recusa. O dublê de identidade do
# `conftest.py` (autouse) tornaria a suíte decorativa: toda rota responderia
# como se um ADMIN estivesse pedindo, e a recusa que se quer medir nunca
# aconteceria. Aqui o portão é o real.
pytestmark = pytest.mark.identidade_real

RAIZ = pathlib.Path(__file__).resolve().parents[2]

#: Um `sub` de verdade tem forma de UUID. Os dois abaixo são de duas PESSOAS
#: diferentes — o teste de acesso cruzado depende de eles não se confundirem.
SUB_A = "11111111-1111-4111-8111-111111111111"
SUB_B = "22222222-2222-4222-8222-222222222222"


# ── o ambiente destes testes ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _sem_alcance_de_rede(monkeypatch):
    """Configuração PRESENTE, banco INALCANÇÁVEL — e as duas coisas importam.

    Presente porque `identidade._config_ou_503` fecha em 503 quando falta
    `SUPABASE_URL`: sem valor nenhum, todo teste de 401 receberia 503 e provaria
    outra coisa. Inalcançável porque nenhum teste de portão pode ler — muito
    menos escrever — no Supabase de produção.

    `.invalid` é reservado por RFC 6761: não resolve em lugar nenhum, então uma
    tentativa de I/O falha na hora em vez de vazar para a rede.

    ⚠️ O `monkeypatch` mexe na INSTÂNCIA de `get_settings()` (que é `lru_cache`),
    não na classe — o mesmo motivo documentado em `test_seguranca_segredo.py:43`.
    """
    s = get_settings()
    monkeypatch.setattr(s, "supabase_url", "https://supabase.invalid", raising=False)
    monkeypatch.setattr(s, "supabase_service_role_key", "service-role-de-teste", raising=False)
    for chave in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        monkeypatch.setenv(chave, "")
    yield
    get_settings.cache_clear()


@pytest.fixture
def cliente() -> TestClient:
    """`raise_server_exceptions=False` de propósito.

    Um portão ausente deixa o handler correr e estourar contra o host inválido.
    Com o padrão do TestClient a exceção subiria e o teste viraria ERROR — que
    esconde a pergunta. O que se quer ler no relatório é o STATUS: 401 é o alvo,
    e 200/500 são as duas maneiras de não tê-lo.
    """
    return TestClient(app, raise_server_exceptions=False)


def _config(**extra: Any) -> Any:
    """Uma `Settings` de mentira, com só o que `identidade` lê.

    Namespace em vez da `Settings` real para não arrastar o `backend/.env` do
    desenvolvedor para dentro do teste. Se `identidade` passar a ler outro
    campo, isto estoura com `AttributeError` — o que é a falha certa: uma
    dependência nova de configuração tem de aparecer.
    """
    base = dict(
        supabase_url="https://supabase.invalid",
        supabase_service_role_key="service-role-de-teste",
        volc_service_key=None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


class _SupabaseDeMentira:
    """O Supabase que o `identidade` acha que está chamando.

    Guarda TODAS as chamadas para que os testes possam perguntar não só o que
    voltou, mas o que foi perguntado — é assim que se prova que o papel foi
    consultado pelo `sub` do token, e não por algo que o cliente mandou.
    """

    def __init__(
        self,
        *,
        usuario: Optional[dict] = None,
        status_auth: int = 200,
        linhas_papel: Optional[list] = None,
        status_papel: int = 200,
        erro_de_rede: bool = False,
    ) -> None:
        self.usuario = usuario if usuario is not None else {"id": SUB_A, "email": "a@volc.test"}
        self.status_auth = status_auth
        self.linhas_papel = linhas_papel if linhas_papel is not None else []
        self.status_papel = status_papel
        self.erro_de_rede = erro_de_rede
        self.chamadas: list[dict] = []

    def responder(self, url: str, headers: dict, params: Optional[dict] = None,
                  json: Optional[dict] = None) -> httpx.Response:
        self.chamadas.append({"url": url, "headers": headers or {},
                              "params": params or {}, "json": json or {}})
        if self.erro_de_rede:
            raise httpx.ConnectError("supabase fora do ar (simulado)")
        pedido = httpx.Request("GET", url)
        if "/auth/v1/user" in url:
            corpo = self.usuario if self.status_auth == 200 else {"msg": "invalid"}
            return httpx.Response(self.status_auth, json=corpo, request=pedido)
        if f"/rest/v1/rpc/{ident.RPC_PAPEL}" in url:
            # A RPC devolve ESCALAR (text), nao lista de linhas: `volc_role_of`
            # existe justamente para o backend nao navegar numa tabela de papeis.
            if self.status_papel >= 400:
                return httpx.Response(self.status_papel, json={"msg": "erro"}, request=pedido)
            papel = ""
            if self.linhas_papel:
                linha = self.linhas_papel[0]
                papel = "" if linha.get("revogado_em") or linha.get("revoked_at") else (linha.get("papel") or linha.get("role") or "")
            return httpx.Response(self.status_papel, json=papel, request=pedido)
        raise AssertionError(f"o portão chamou uma URL não prevista: {url}")

    @property
    def urls(self) -> list[str]:
        return [c["url"] for c in self.chamadas]


@pytest.fixture
def dublar(monkeypatch):
    """Instala o Supabase de mentira DENTRO do módulo `identidade`.

    Troca o atributo `httpx` do módulo, não o `httpx` global: um patch global
    valeria para o processo inteiro e contaminaria qualquer outro teste que
    rodasse no mesmo worker.
    """
    def instalar(duble: _SupabaseDeMentira) -> _SupabaseDeMentira:
        class _ClienteFalso:
            def __init__(self, *_a, **_k) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def post(self, url, headers=None, json=None):
                # A consulta de papel virou RPC (POST). Ver `identidade.RPC_PAPEL`.
                return duble.responder(url, headers, None, json)

            async def get(self, url, headers=None, params=None):
                return duble.responder(url, headers, params)

        monkeypatch.setattr(
            ident, "httpx", SimpleNamespace(AsyncClient=_ClienteFalso, HTTPError=httpx.HTTPError)
        )
        return duble

    return instalar


def _recusa(coro) -> HTTPException:
    """Roda a corrotina e devolve a `HTTPException` que ela levantou.

    `asyncio.run` em vez de `pytest-asyncio`: o plugin não está instalado neste
    backend (`requirements-dev.txt` só traz `pytest>=8`), e adicionar um por
    causa de um arquivo de teste é dívida que ninguém pediu.
    """
    with pytest.raises(HTTPException) as capturado:
        asyncio.run(coro)
    return capturado.value


# ══════════════════════════════════════════════════════════════════════════
# 1. A credencial do navegador — 401 é ausência de identidade
# ══════════════════════════════════════════════════════════════════════════

def test_sem_credencial_e_401_antes_de_qualquer_ida_ao_banco(dublar):
    """Sem isto, "não autenticado" custaria uma ida ao Supabase por requisição.

    Um portão que só descobre a ausência de credencial depois de falar com o
    banco é um amplificador de negação de serviço: quem quiser derrubar a API
    manda requisições vazias.
    """
    duble = dublar(_SupabaseDeMentira())
    erro = _recusa(ident.exigir_usuario(authorization=None, settings=_config()))
    assert erro.status_code == 401
    assert duble.chamadas == [], "o portão foi ao banco antes de conferir o cabeçalho"


@pytest.mark.parametrize("cabecalho", [
    "",                       # vazio
    "abcdef",                 # sem esquema
    "Token abcdef",           # esquema errado
    "Bearer",                 # esquema sem token
    "Bearer    ",             # só espaço
    "Basic dXNlcjpzZW5oYQ==",  # outro esquema conhecido
])
def test_cabecalho_malformado_e_401(dublar, cabecalho):
    """Cada uma destas formas já foi tentada por scanner automático.

    Aceitar qualquer uma delas como "tem alguma coisa no header" é o erro que
    transforma um portão em decoração.
    """
    duble = dublar(_SupabaseDeMentira())
    erro = _recusa(ident.exigir_usuario(authorization=cabecalho, settings=_config()))
    assert erro.status_code == 401
    assert duble.chamadas == []


def test_token_invalido_ou_expirado_e_401(dublar):
    """O Supabase é a AUTORIDADE sobre a validade da sessão, e é ele quem diz.

    Verificar assinatura localmente aceitaria token de sessão já revogada até a
    expiração — para uma rota que gasta dinheiro em anúncio, tarde demais.
    """
    dublar(_SupabaseDeMentira(status_auth=401))
    erro = _recusa(ident.exigir_usuario(authorization="Bearer token.expirado.qualquer",
                                        settings=_config()))
    assert erro.status_code == 401


def test_token_sem_sujeito_e_401(dublar):
    """Resposta 200 sem `id` não é sessão: é resposta de outra coisa.

    Sem esta checagem, um proxy mal configurado que devolve `{}` com 200 viraria
    uma identidade anônima com `sub` vazio — e `sub` vazio casa com linha vazia
    em qualquer consulta por igualdade.
    """
    dublar(_SupabaseDeMentira(usuario={"email": "sem-id@volc.test"}))
    erro = _recusa(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert erro.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# 2. FALHA FECHADA — indisponibilidade nunca vira permissão
# ══════════════════════════════════════════════════════════════════════════

def test_sem_configuracao_de_auth_o_portao_FECHA(dublar):
    """⚠️ A INVARIANTE CENTRAL DO SPRINT.

    É exatamente o oposto de `app/deps.py:20-21`, que devolve `None` (= passe
    livre) quando a chave não está configurada. Um deploy com credenciais reais
    e a variável esquecida fica ABERTO e parece protegido — que é o pior dos
    dois mundos, porque ninguém vai procurar.
    """
    duble = dublar(_SupabaseDeMentira())
    for config in (_config(supabase_url=""), _config(supabase_service_role_key="")):
        erro = _recusa(ident.exigir_usuario(authorization="Bearer t", settings=config))
        assert erro.status_code == 503, "configuração ausente não pode virar acesso liberado"
    assert duble.chamadas == []


def test_auth_fora_do_ar_nao_vira_permissao(dublar):
    """Se o Supabase cai, a API para — ela não passa a confiar em todo mundo.

    Este é o caminho por onde portões costumam ser abertos "temporariamente":
    um `except: pass` em volta da validação, para "não derrubar o sistema".
    """
    dublar(_SupabaseDeMentira(erro_de_rede=True))
    erro = _recusa(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert erro.status_code == 503

    dublar(_SupabaseDeMentira(status_auth=500))
    erro = _recusa(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert erro.status_code == 503


def test_falha_ao_ler_o_papel_nao_vira_admin(dublar):
    """Erro ao apurar a autorização é 503, não "sem papel" e muito menos ADMIN.

    Devolver papel vazio num erro seria defensável; devolver 200 com papel
    presumido não seria. O teste fixa que a ausência de resposta interrompe.
    """
    dublar(_SupabaseDeMentira(status_papel=500))
    erro = _recusa(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert erro.status_code == 503


def test_require_api_key_foi_APOSENTADA():
    """O portão que falhava aberto não existe mais.

    Ele fazia `if not expected: return` — sem `PAUTADOR_API_KEY` no ambiente,
    a requisição passava. Um deploy com credenciais reais e essa variável
    esquecida ficava aberto e PARECIA protegido, que é a pior combinação: nada
    falha, nada avisa, e ninguém procura o buraco que acha que já tapou.

    E ainda que ele fechasse, não serviria: a mesma chave viajava para o
    navegador como `VITE_PAUTADOR_API_KEY`, embutida no bundle. Segredo
    compartilhado com o navegador é público.

    A versão anterior deste teste apenas exigia que ele RECUSASSE. Isso teria
    aceitado um portão consertado — e um portão consertado continuaria sendo
    autenticação por chave compartilhada. Agora o teste exige a aposentadoria:
    a função não pode voltar, nem consertada.
    """
    from app import deps

    assert not hasattr(deps, "require_api_key"), (
        "`require_api_key` voltou. Ela é autenticação por segredo compartilhado "
        "com o navegador — use `exigir_usuario`/`exigir_admin`/`exigir_servico`."
    )

    fonte = (RAIZ / "backend" / "app").rglob("*.py")
    reincidentes = [
        f"{caminho.relative_to(RAIZ)}:{n}"
        for caminho in fonte
        for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
        if "Depends(require_api_key)" in linha
    ]
    assert reincidentes == [], f"rota ainda dependendo do portão aposentado: {reincidentes}"


# ══════════════════════════════════════════════════════════════════════════
# 3. O papel — 403 é identidade válida com permissão insuficiente
# ══════════════════════════════════════════════════════════════════════════

def test_papel_insuficiente_e_403_e_nao_401(dublar):
    """A distinção não é estética: 401 manda entrar de novo, 403 manda pedir
    acesso. Colapsar os dois faz o operador repetir o login que já funcionou e
    concluir que o sistema está quebrado."""
    dublar(_SupabaseDeMentira(linhas_papel=[{"papel": "VIEWER", "revogado_em": None}]))
    identidade = asyncio.run(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert identidade.papel == "VIEWER"
    erro = _recusa(ident.exigir_admin(identidade=identidade))
    assert erro.status_code == 403


def test_sem_linha_de_autorizacao_nao_e_admin(dublar):
    """Usuário autenticado ≠ usuário autorizado.

    Qualquer pessoa com e-mail pode existir em `auth.users`; ser da casa é ter
    linha na tabela de autorização. Sem esta separação, criar conta seria
    conceder acesso.
    """
    dublar(_SupabaseDeMentira(linhas_papel=[]))
    identidade = asyncio.run(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert identidade.papel == ""
    assert _recusa(ident.exigir_admin(identidade=identidade)).status_code == 403


def test_papel_revogado_deixa_de_valer_NA_HORA(dublar):
    """É a razão inteira de consultar o banco em vez de ler o token.

    Papel dentro do JWT só muda quando um token novo é emitido: demitir alguém
    às 9h deixaria a sessão dela ativa até a expiração. Aqui, `revogado_em`
    preenchido derruba o acesso na requisição seguinte.
    """
    dublar(_SupabaseDeMentira(
        linhas_papel=[{"papel": "ADMIN", "revogado_em": "2026-08-24T10:00:00Z"}]
    ))
    identidade = asyncio.run(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert identidade.e_admin is False
    assert _recusa(ident.exigir_admin(identidade=identidade)).status_code == 403


def test_admin_de_verdade_passa(dublar):
    """O caso feliz também é teste de segurança: um portão que recusa todo mundo
    é indistinguível de um sistema quebrado, e a reação humana a isso é
    desligá-lo."""
    dublar(_SupabaseDeMentira(linhas_papel=[{"papel": "ADMIN", "revogado_em": None}]))
    identidade = asyncio.run(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert identidade.e_admin is True
    assert asyncio.run(ident.exigir_admin(identidade=identidade)) is identidade


# ══════════════════════════════════════════════════════════════════════════
# 4. Autopromoção — o crachá não é assinado pelo visitante
# ══════════════════════════════════════════════════════════════════════════

def test_user_metadata_nao_e_autoridade(dublar):
    """⚠️ `user_metadata` é EDITÁVEL PELO PRÓPRIO USUÁRIO via API de auth.

    E `api/users/create.js:67` grava `user_metadata: { name, role }` — ou seja,
    o campo existe, tem cara de papel e está a um `updateUser` de distância.
    Quem ler papel dali entregou ADMIN a quem pedir.
    """
    duble = dublar(_SupabaseDeMentira(
        usuario={
            "id": SUB_A,
            "email": "atacante@volc.test",
            "user_metadata": {"role": "ADMIN", "papel": "ADMIN", "is_admin": True},
            "app_metadata": {"role": "ADMIN", "papel": "ADMIN"},
            "role": "ADMIN",  # o GoTrue também tem um `role` próprio ("authenticated")
        },
        linhas_papel=[],  # a fonte de verdade não conhece esta pessoa
    ))
    identidade = asyncio.run(ident.exigir_usuario(authorization="Bearer t", settings=_config()))
    assert identidade.papel == "", "papel veio do token, não da fonte protegida"
    assert _recusa(ident.exigir_admin(identidade=identidade)).status_code == 403
    assert any(ident.RPC_PAPEL in u for u in duble.urls), (
        "o papel tem de ser consultado server-side; nenhuma consulta foi feita"
    )


def test_a_identidade_e_imutavel_depois_de_montada():
    """Autopromoção também acontece DEPOIS do portão.

    Um handler que faça `identidade.papel = "ADMIN"` — por engano ou por
    conveniência — reabriria tudo sem passar por revisão de segurança. O
    `dataclass(frozen=True)` transforma isso em erro no ato.
    """
    eu = ident.Identidade(sub=SUB_A, email="a@volc.test", papel="VIEWER", origem="sessao")
    with pytest.raises(Exception):
        eu.papel = "ADMIN"  # type: ignore[misc]
    assert eu.e_admin is False


def test_a_tabela_de_papel_nao_e_public_users():
    """`public.users` tinha RLS DESABILITADA e zero policies em 24/08/2026, e seu
    `role` era gravável por qualquer um pelos proxies genéricos de
    `api/supabase/update.js`. Ler papel dali seria confiar num campo que o
    próprio atacante escreve."""
    assert ident.RPC_PAPEL != "users"
    assert ident.RPC_PAPEL.strip() != ""


# ══════════════════════════════════════════════════════════════════════════
# 5. Acesso cruzado — o `sub` é o do token, e de mais ninguém
# ══════════════════════════════════════════════════════════════════════════

def test_o_papel_e_consultado_pelo_sub_DO_TOKEN(dublar):
    """Sem isto, bastaria mandar o `sub` de um admin junto da própria sessão.

    O ataque é banal: pegar o id do admin (ele aparece em qualquer listagem de
    usuários) e mandá-lo como parâmetro. A defesa é o portão nunca aceitar
    `sub` vindo do cliente — nem por header, nem por query, nem pelo corpo.
    """
    duble = dublar(_SupabaseDeMentira(
        usuario={"id": SUB_A, "email": "a@volc.test"},
        linhas_papel=[{"papel": "VIEWER", "revogado_em": None}],
    ))
    identidade = asyncio.run(ident.exigir_usuario(authorization="Bearer t", settings=_config()))

    assert identidade.sub == SUB_A
    consulta = next(c for c in duble.chamadas if ident.RPC_PAPEL in c["url"])
    # O sub viaja no CORPO da RPC (`p_auth_user_id`), nao em query param —
    # `volc_role_of` e uma funcao, nao um recurso REST filtravel.
    filtro = "".join(str(v) for v in consulta["params"].values()) + \
             "".join(str(v) for v in consulta["json"].values())
    assert SUB_A in filtro, "a consulta de papel não filtrou pelo sub do token"
    assert SUB_B not in filtro


def test_sub_forjado_no_corpo_do_jwt_e_ignorado(dublar):
    """O payload de um JWT é base64, não cifra: qualquer um lê e reescreve.

    A única coisa que impede a reescrita de valer é a assinatura — e quem
    confere a assinatura aqui é o Supabase. Este teste fixa que a identidade sai
    da RESPOSTA do `/auth/v1/user`, não do que o cliente mandou.
    """
    duble = dublar(_SupabaseDeMentira(
        usuario={"id": SUB_A, "email": "a@volc.test"},
        linhas_papel=[{"papel": "VIEWER", "revogado_em": None}],
    ))
    # Um JWT de mentira cujo payload jura ser o SUB_B e ADMIN.
    forjado = "eyJhbGciOiJub25lIn0.eyJzdWIiOiIyMjIyMjIyMi0yMjIyLTQyMjItODIyMi0yMjIyMjIyMjIyMjIiLCJyb2xlIjoiQURNSU4ifQ."
    identidade = asyncio.run(
        ident.exigir_usuario(authorization=f"Bearer {forjado}", settings=_config())
    )
    assert identidade.sub == SUB_A, "o portão leu o sub do payload em vez do auth"
    assert identidade.papel == "VIEWER"
    assert all(SUB_B not in str(c["params"]) for c in duble.chamadas)


def test_o_token_do_usuario_nunca_e_usado_para_ler_a_autorizacao(dublar):
    """Duas credenciais, dois papéis, e trocá-los é um furo silencioso.

    A tabela de autorização é lida com a service role (o backend é dono dela).
    Se a leitura fosse feita com o token do usuário, bastaria uma policy frouxa
    para a pessoa enxergar — ou alterar — a própria linha de papel.
    """
    duble = dublar(_SupabaseDeMentira(linhas_papel=[{"papel": "ADMIN", "revogado_em": None}]))
    asyncio.run(ident.exigir_usuario(authorization="Bearer token-do-usuario", settings=_config()))
    consulta = next(c for c in duble.chamadas if ident.RPC_PAPEL in c["url"])
    assert "token-do-usuario" not in str(consulta["headers"])


# ══════════════════════════════════════════════════════════════════════════
# 6. A via de serviço — n8n e cron, nunca o navegador
# ══════════════════════════════════════════════════════════════════════════

def test_servico_sem_chave_configurada_FECHA():
    """O espelho de `require_api_key`: sem `VOLC_SERVICE_KEY`, nada passa.

    Se esta via falhasse aberta como a antiga, o Sprint 1A teria trocado um
    portão inútil por outro — com nome novo.
    """
    erro = _recusa(ident.exigir_servico(x_volc_service_key="qualquer-coisa",
                                        settings=_config(volc_service_key=None)))
    assert erro.status_code == 503


def test_servico_recusa_chave_errada_e_ausente():
    config = _config(volc_service_key="chave-de-servico-correta")
    assert _recusa(ident.exigir_servico(x_volc_service_key=None, settings=config)).status_code == 401
    assert _recusa(ident.exigir_servico(x_volc_service_key="chave-errada", settings=config)).status_code == 401
    # Prefixo correto não vale: é o caso que uma comparação byte a byte com saída
    # antecipada entregaria em ~200 tentativas por caractere.
    assert _recusa(ident.exigir_servico(x_volc_service_key="chave-de-servico-corret",
                                        settings=config)).status_code == 401


def test_servico_com_chave_certa_passa_e_nao_vira_admin():
    """A identidade de serviço é uma TERCEIRA coisa — nem usuário, nem admin.

    Deixar o n8n entrar como ADMIN significa que vazar a chave de integração
    entrega o painel inteiro. O papel dela é `SERVICO` e as rotas de operação
    humana continuam exigindo `exigir_admin`.
    """
    identidade = asyncio.run(ident.exigir_servico(
        x_volc_service_key="chave-de-servico-correta",
        settings=_config(volc_service_key="chave-de-servico-correta"),
    ))
    assert identidade.origem == "servico"
    assert identidade.e_admin is False


def test_a_chave_de_servico_nunca_ganha_equivalente_VITE():
    """⚠️ É COMO A `PAUTADOR_API_KEY` DEIXOU DE SER SEGREDO.

    Tudo que começa com `VITE_` é substituído literalmente dentro do bundle no
    build — ou seja, publicado. Basta alguém "resolver o 401 do front" criando
    `VITE_VOLC_SERVICE_KEY` para a via de serviço virar pública, e nada no
    build avisa. Este teste é o aviso.
    """
    alvos = [RAIZ / "src", RAIZ / ".env.example", RAIZ / "backend" / ".env.example"]
    achados: list[str] = []
    for alvo in alvos:
        arquivos = alvo.rglob("*") if alvo.is_dir() else [alvo]
        for arquivo in arquivos:
            if not arquivo.is_file() or arquivo.suffix not in ("", ".ts", ".tsx", ".js", ".jsx", ".example"):
                continue
            try:
                texto = arquivo.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"VITE_[A-Z_]*(SERVICE_KEY|SERVICE_ROLE)", texto):
                achados.append(str(arquivo.relative_to(RAIZ)))
    assert achados == [], f"credencial de serviço exposta ao bundle em: {achados}"


# ══════════════════════════════════════════════════════════════════════════
# 7. As rotas — a inspeção que cobre as 70 sem chamar nenhuma destrutiva
# ══════════════════════════════════════════════════════════════════════════

#: Rotas legitimamente públicas, com a razão de cada uma. Qualquer outra rota
#: `/api/*` precisa declarar um portão. A lista é curta de propósito: ela é o
#: lugar por onde uma exceção "temporária" viraria permanente.
PUBLICAS = {
    "/",                       # cartão de visita do serviço, sem dado
    "/health",                 # liveness do orquestrador, antes de qualquer sessão
    "/api/pautador/health",    # idem, consumido pelo painel para dizer "backend no ar"
    "/docs", "/redoc", "/openapi.json",
}

# ⚠️ `exigir_link_assinado` entrou em 27/08/2026, e ele NÃO é um afrouxamento.
#
# Os três primeiros portões exigem `Authorization`, e cobrem tudo que o
# navegador busca por `fetch`. Eles não cobrem `<img src>` e `<video src>`, que
# não mandam header nenhum: uma rota de mídia protegida por JWT simplesmente não
# carrega, e as duas saídas baratas para isso são deixar o arquivo público ou
# pendurar o token de sessão na URL. As duas são piores.
#
# O quarto portão exige uma prova que o PRÓPRIO servidor emitiu (HMAC), escopada
# a UMA chave de storage e válida por minutos, e quem a emite é um endpoint
# protegido por `exigir_usuario`. Ele é declarado como dependência justamente
# para que este teste continue conseguindo enxergá-lo — uma conferência
# escondida no corpo da função passaria aqui sem guarda nenhuma declarada.
#
# Ver `app/seguranca/link_assinado.py`.
GUARDAS_DE_IDENTIDADE = {"exigir_usuario", "exigir_admin", "exigir_servico"}

# ⚠️ `exigir_link_assinado` vale para LEITURA e NÃO para mutação, e a separação
# em dois conjuntos é conserto de 28/08/2026.
#
# Com um conjunto só, uma rota MUTANTE cujo único portão fosse o link assinado
# satisfazia a invariante "declara um portão de identidade" — e o próprio
# `app/seguranca/link_assinado.py` diz, com todas as letras, que ele "não é
# autorização de negócio e não sabe quem é o operador". Provar identidade com um
# portão que por construção não tem identidade é afrouxar a regra, não estendê-la.
GUARDAS_DE_LEITURA = GUARDAS_DE_IDENTIDADE | {"exigir_link_assinado"}

# Compatibilidade com quem lia o nome antigo.
GUARDAS = GUARDAS_DE_LEITURA

MUTANTES = {"POST", "PUT", "PATCH", "DELETE"}


def _guardas_da_rota(rota: APIRoute) -> set[str]:
    """Todos os nomes de dependência da rota, inclusive as aninhadas.

    Aninhadas importam: `exigir_admin` depende de `exigir_usuario`, e uma rota
    que declare só a primeira está protegida pelas duas.
    """
    nomes: set[str] = set()
    pilha = list(rota.dependant.dependencies)
    while pilha:
        dep = pilha.pop()
        chamada = getattr(dep, "call", None)
        if chamada is not None:
            nomes.add(getattr(chamada, "__name__", ""))
        pilha.extend(dep.dependencies)
    return nomes


def _rotas_api() -> list[APIRoute]:
    return [r for r in app.routes
            if isinstance(r, APIRoute) and r.path not in PUBLICAS]


def test_toda_rota_mutante_declara_um_portao_de_identidade():
    """⚠️ FALHA HOJE — é o gate do Sprint 1A, e é a razão de este teste inspecionar
    em vez de chamar.

    Entre as rotas descobertas estão `DELETE /api/pautador/entity-opportunities/
    {opp_id}` e `POST /api/trafego/subir`. Provar o portão CHAMANDO-as exigiria
    apagar uma oportunidade e subir uma campanha; a inspeção prova o mesmo sem
    tocar em nada. Medido em 24/08/2026: 0 das 37 rotas mutantes tinha portão.
    """
    desprotegidas = [
        f"{sorted(r.methods & MUTANTES)[0]} {r.path}"
        for r in _rotas_api()
        if (r.methods & MUTANTES) and not (_guardas_da_rota(r) & GUARDAS_DE_IDENTIDADE)
    ]
    assert desprotegidas == [], (
        f"{len(desprotegidas)} rotas mutam o sistema sem exigir identidade: "
        f"{desprotegidas[:8]}{' …' if len(desprotegidas) > 8 else ''}"
    )


def test_toda_rota_de_leitura_declara_um_portao_de_identidade():
    """Leitura também vaza: `/api/trafego/quadro` devolve o funil comercial e
    `/api/trafego/escopo` devolve a árvore de contas do Google Ads da casa.
    "É só GET" nunca foi um argumento de segurança."""
    desprotegidas = [
        f"GET {r.path}" for r in _rotas_api()
        if "GET" in r.methods and not (_guardas_da_rota(r) & GUARDAS_DE_LEITURA)
    ]
    assert desprotegidas == [], (
        f"{len(desprotegidas)} rotas de leitura sem portão: "
        f"{desprotegidas[:8]}{' …' if len(desprotegidas) > 8 else ''}"
    )


def test_o_portao_legado_sozinho_nao_conta():
    """`require_api_key` não pode ser a única proteção de uma rota mutante.

    Ele falha aberto (`app/deps.py:20-21`) e sua chave está no bundle
    (`src/lib/pautadorApi.ts:37`). Uma rota que só o declare está, na prática,
    aberta — e o relatório de cobertura diria que está protegida.
    """
    so_legado = [
        f"{sorted(r.methods & MUTANTES)[0]} {r.path}"
        for r in _rotas_api()
        if (r.methods & MUTANTES)
        and "require_api_key" in _guardas_da_rota(r)
        and not (_guardas_da_rota(r) & GUARDAS)
    ]
    assert so_legado == [], f"protegidas apenas pelo portão que falha aberto: {so_legado[:8]}"


# ══════════════════════════════════════════════════════════════════════════
# 8. As rotas — comportamento HTTP de ponta a ponta
# ══════════════════════════════════════════════════════════════════════════

#: Leituras de dado de negócio. Nenhuma delas alcança o banco nestes testes: a
#: fixture aponta a configuração para um host `.invalid`.
LEITURAS = [
    "/api/pautador/runs",
    "/api/pautador/entity-opportunities",
    "/api/trafego/quadro",
    "/api/trafego/projetos",
    "/api/publicacao/destinos",
    # Estúdio Criativo (27/08/2026). Entram aqui porque a biblioteca devolve
    # patrimônio criativo com procedência e o resumo devolve custo estimado:
    # "é só GET" continua não sendo argumento de segurança.
    "/api/criativos/resumo",
    "/api/criativos/assets",
    "/api/criativos/jobs",
    "/api/criativos/formatos",
    "/api/criativos/brand-packs",
    "/api/criativos/videos",
]


def _rota_registrada(rota: str) -> bool:
    """A rota existe NESTE build?

    Existe porque `publicacao` pode não estar registrado: o módulo nunca foi
    versionado (ver `app/main.py`), e num checkout limpo a rota simplesmente não
    existe. Um teste de portão que roda contra uma rota ausente mede 404 e chama
    isso de falha de segurança, o que é ruído: não há portão a provar onde não
    há porta.

    A checagem é pela EXISTÊNCIA da rota, não pelo resultado dela. Se o módulo
    estiver presente e o portão estiver errado, o teste roda e falha, como deve.
    """
    from app.main import app

    return any(getattr(r, "path", None) == rota for r in app.routes)


@pytest.mark.parametrize("rota", LEITURAS)
def test_leitura_sem_credencial_responde_401(cliente: TestClient, rota: str):
    """⚠️ FALHA HOJE — medido: `GET /api/pautador/runs` devolve 200 sem nenhum
    cabeçalho.

    Qualquer outro status aqui significa que a requisição PASSOU do portão: 200
    é o vazamento, 500/503 significa que o handler foi executado e tropeçou
    depois. O portão tem de responder antes de qualquer I/O.
    """
    if not _rota_registrada(rota):
        pytest.skip(f"{rota} não está registrada neste build: não há portão a provar")
    resposta = cliente.get(rota)
    assert resposta.status_code == 401, (
        f"{rota} respondeu {resposta.status_code} sem credencial nenhuma"
    )


@pytest.mark.parametrize("rota", LEITURAS)
def test_leitura_com_jwt_invalido_responde_401(cliente: TestClient, dublar, rota: str):
    """Um token qualquer não pode valer mais que nenhum token.

    O `Bearer` abaixo é sintaticamente perfeito e semanticamente lixo — é o que
    um scanner manda. Se a rota responder 200, o portão está olhando só a
    PRESENÇA do cabeçalho.

    O Supabase de mentira responde 401 ao `/auth/v1/user`, que é o que ele faria
    com um token expirado de verdade. Hoje a resposta é **502**: sem portão, o
    handler ignora o cabeçalho e vai direto tentar ler o banco.
    """
    if not _rota_registrada(rota):
        pytest.skip(f"{rota} não está registrada neste build: não há portão a provar")
    dublar(_SupabaseDeMentira(status_auth=401))
    lixo = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIiwiZXhwIjoxfQ.assinatura-invalida"
    resposta = cliente.get(rota, headers={"Authorization": f"Bearer {lixo}"})
    assert resposta.status_code == 401, (
        f"{rota} respondeu {resposta.status_code} com um JWT inválido"
    )


def test_escrita_sem_credencial_responde_401(cliente: TestClient):
    """⚠️ FALHA HOJE, e a forma da falha é informativa.

    Hoje `POST /api/trafego/subir` sem credencial responde **422** — a validação
    do corpo roda ANTES de qualquer conferência de identidade. Ou seja: um
    anônimo consegue usar a rota de escrita como validador de esquema e mapear o
    contrato interno. Depois do Sprint 1A o portão vem primeiro e a resposta é
    401, sem revelar nada sobre o payload esperado.

    ⚠️ Nenhuma rota destrutiva é chamada aqui — ver
    `test_toda_rota_mutante_declara_um_portao_de_identidade`.
    """
    resposta = cliente.post("/api/trafego/subir", json={})
    assert resposta.status_code == 401, (
        f"respondeu {resposta.status_code}; sem identidade a rota não deveria nem "
        f"olhar o corpo"
    )


def test_com_permissao_valida_a_leitura_responde_200(cliente: TestClient):
    """O portão precisa DEIXAR PASSAR quem tem direito.

    Sobrepõe `exigir_usuario`/`exigir_admin` com uma identidade fabricada — o
    mecanismo do próprio FastAPI, sem rede. Enquanto as rotas não declararem as
    dependências, a sobreposição é inerte e o teste passa por outro motivo; é
    `test_leitura_sem_credencial_responde_401` que fecha essa brecha, e os dois
    só ficam verdes ao mesmo tempo quando o portão existe de verdade.

    A rota é `/countries` porque ela não toca no banco: o que está sob teste é o
    portão deixar passar, não o Supabase responder.
    """
    admin = ident.Identidade(sub=SUB_A, email="admin@volc.test", papel="ADMIN", origem="sessao")
    app.dependency_overrides[ident.exigir_usuario] = lambda: admin
    app.dependency_overrides[ident.exigir_admin] = lambda: admin
    try:
        resposta = cliente.get("/api/pautador/countries")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["countries"]
    finally:
        app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════
# 9. O escopo de contas — identidade válida não move a fronteira
# ══════════════════════════════════════════════════════════════════════════

#: MCC do IESDE. A credencial da casa ALCANÇA este MCC (medido em 18/08/2026,
#: `app/trafego/escopo.py:26-30`) — é justamente por isso que ele serve de teste:
#: o portão não pode se apoiar em "o Google recusaria".
MCC_DE_TERCEIRO = "5838529870"


def test_mcc_de_terceiro_e_recusado_na_funcao_pura():
    """Sem rede, antes de a requisição sair da máquina.

    Um portão que depende de o Google recusar é um portão que depende do
    comportamento de terceiro continuar igual amanhã.
    """
    with pytest.raises(escopo.ForaDoEscopo):
        escopo.exigir_escopo("8552871761", MCC_DE_TERCEIRO)
    with pytest.raises(escopo.ForaDoEscopo):
        escopo.exigir_escopo("8017851692", "")


def test_mcc_de_terceiro_e_recusado_na_rota_MESMO_COM_ADMIN(cliente: TestClient):
    """⚠️ Ser admin da casa não é ser dono da conta do cliente.

    O erro que este teste impede é o mais fácil de cometer depois de um sprint
    de autenticação: concluir que "agora tem login, então pode". As duas
    fronteiras são independentes — identidade diz QUEM, escopo diz ONDE.
    """
    admin = ident.Identidade(sub=SUB_A, email="admin@volc.test", papel="ADMIN", origem="sessao")
    app.dependency_overrides[ident.exigir_usuario] = lambda: admin
    app.dependency_overrides[ident.exigir_admin] = lambda: admin
    try:
        resposta = cliente.post("/api/trafego/subir", json={
            "opportunity_id": 1,
            "customer_id": "8552871761",          # Colégio Positivo
            "login_customer_id": MCC_DE_TERCEIRO,  # sob o MCC do IESDE
            "motivo": "teste automatizado da recusa de escopo",
            "grupos": [], "budget_diario": 10.0,
        })
        assert resposta.status_code == 403, resposta.text
        assert MCC_DE_TERCEIRO in resposta.text
    finally:
        app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════
# 10. A trava de escrita — a segunda fechadura, que a identidade não abre
# ══════════════════════════════════════════════════════════════════════════

def _modo():
    """`volc_ads` só entra no `sys.path` depois do `_ponte()` do router — é a
    importação tardia documentada em `app/routers/trafego.py:96-110`."""
    from app.routers.trafego import _ponte

    _ponte()
    from volc_ads.gads import modo

    return modo


def test_a_trava_esta_fechada_e_recusa_escrita():
    """Se este teste falhar, alguém definiu `FORGE_PERMITIR_ESCRITA` no ambiente
    onde a suíte roda — e a suíte passaria a poder criar campanha de verdade
    numa conta real."""
    modo = _modo()
    assert modo.escrita_permitida() is False
    assert modo.estado()["env_presente"] is False
    with pytest.raises(modo.EscritaBloqueada):
        modo.exigir_leitura_apenas("subir campanha (teste)")


def test_nem_um_admin_autenticado_abre_a_trava():
    """As duas travas são independentes DE PROPÓSITO, e é fácil confundi-las.

    Identidade responde "quem"; a trava responde "se pode escrever agora". Um
    admin legítimo, autenticado e com escopo correto, continua barrado enquanto
    a trava estiver fechada — porque a trava protege contra o acidente, não
    contra o intruso.
    """
    modo = _modo()
    with pytest.raises(modo.EscritaBloqueada):
        with modo.destravar("subir campanha canário autorizada pelo admin"):
            pytest.fail("a trava abriu sem FORGE_PERMITIR_ESCRITA no ambiente")


# ══════════════════════════════════════════════════════════════════════════
# 11. Coluna sensível — o que o backend nunca deve saber ler
# ══════════════════════════════════════════════════════════════════════════

SENSIVEIS = ("password_hash", "token_primeiro_acesso", "token_expiracao")


def test_o_backend_nunca_menciona_coluna_de_credencial():
    """`public.users` guarda `password_hash`, `token_primeiro_acesso` e
    `token_expiracao`, e em 24/08/2026 estava com RLS DESABILITADA e zero
    policies — qualquer `select` que a alcance devolve tudo.

    Medido hoje: 0 ocorrências no backend. Este teste existe para que continue
    0: a primeira linha que selecionar essas colunas fica visível em revisão.
    A recusa equivalente do lado dos proxies está em
    `src/lib/__tests__/seguranca-bundle.test.ts`.
    """
    achados: list[str] = []
    for arquivo in (RAIZ / "backend" / "app").rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8", errors="ignore")
        for coluna in SENSIVEIS:
            if coluna in texto:
                achados.append(f"{arquivo.relative_to(RAIZ)}: {coluna}")
    assert achados == [], f"coluna de credencial referenciada no backend: {achados}"


def test_nenhuma_resposta_de_erro_devolve_a_credencial_configurada(dublar):
    """Mensagem de erro é o vazamento mais comum e o menos revisado.

    Um `detail` que ecoe a chave esperada — "esperava X, veio Y" — entrega o
    segredo para quem só mandou lixo. Aqui a chave de serviço é conhecida e a
    asserção é que ela não aparece em resposta nenhuma.
    """
    segredo = "chave-de-servico-que-nao-pode-vazar"
    erro = _recusa(ident.exigir_servico(x_volc_service_key="tentativa",
                                        settings=_config(volc_service_key=segredo)))
    assert segredo not in str(erro.detail)

    dublar(_SupabaseDeMentira(status_auth=401))
    erro = _recusa(ident.exigir_usuario(authorization="Bearer token-secreto-do-usuario",
                                        settings=_config()))
    assert "token-secreto-do-usuario" not in str(erro.detail), (
        "a mensagem de erro ecoou o token — ele vai parar no log de acesso"
    )


# ══════════════════════════════════════════════════════════════════════════
# 9. Os detectores de capacidade ausente
# ══════════════════════════════════════════════════════════════════════════
#
# Estes três testes existem porque a auditoria de 28/08/2026 mediu que, depois
# de o registro de router virar tolerante, NÃO SOBRAVA nenhum sinal automatizado
# de que oito arquivos-fonte tinham sumido: a suíte passava, o `tsc` passava, o
# gate passava, e `/health` dizia `degradado` para ninguém (zero consumidores).
#
# Subir degradado é melhor que não subir. Subir degradado sem que nada fique
# vermelho é como uma capacidade perdida vira permanente.

#: Capacidades que este build PODE não ter, com o motivo e a data.
#: Uma entrada aqui é uma dívida declarada, não um estado aceitável.
# O commit de consolidação versiona `publicacao.py` e `seguranca/segredo.py`.
# A lista fica explícita e vazia: uma nova exceção exige motivo e data, e uma
# capacidade que volte a existir não pode permanecer tolerada por inércia.
ROUTERS_OPCIONAIS_CONHECIDOS: set[str] = set()

ROTINAS_OPCIONAIS_CONHECIDAS = {
    # `backend/app/redator/` (6 módulos) nunca foi versionado. Sem ele, runs
    # interrompidos ficam presos em 'escrevendo' e nada os reconcilia.
    "redator.reconciliar",
}


def test_nenhuma_capacidade_some_sem_estar_declarada():
    """Um router ausente que NÃO esteja na lista de dívidas é falha.

    É este teste que impede a próxima capacidade perdida de virar silêncio.
    """
    from app.main import ROUTERS_AUSENTES, ROTINAS_AUSENTES

    surpresas = {r["router"] for r in ROUTERS_AUSENTES} - ROUTERS_OPCIONAIS_CONHECIDOS
    assert surpresas == set(), (
        f"router(es) sumiram sem declaração: {sorted(surpresas)}. "
        "Versione o módulo ou declare a dívida em ROUTERS_OPCIONAIS_CONHECIDOS."
    )
    surpresas_rot = {r["rotina"] for r in ROTINAS_AUSENTES} - ROTINAS_OPCIONAIS_CONHECIDAS
    assert surpresas_rot == set(), (
        f"rotina(s) sumiram sem declaração: {sorted(surpresas_rot)}"
    )


def test_a_divida_declarada_ainda_existe_de_verdade():
    """O inverso: uma dívida que já foi paga tem de sair da lista.

    Sem isto, `ROUTERS_OPCIONAIS_CONHECIDOS` vira um cemitério de exceções que
    ninguém revisita, e o teste acima passa a tolerar o que já foi consertado.
    """
    from app.main import ROUTERS_AUSENTES

    ausentes = {r["router"] for r in ROUTERS_AUSENTES}
    quitadas = ROUTERS_OPCIONAIS_CONHECIDOS - ausentes
    assert quitadas == set(), (
        f"{sorted(quitadas)} voltou a existir: tire da lista de dívidas."
    )


def test_toda_rota_de_LEITURAS_existe_neste_build():
    """`_rota_registrada` pula rota ausente. Este teste garante que o pulo é raro.

    Sem ele, renomear uma rota (ou digitá-la errado em `LEITURAS`) converte a
    prova comportamental de 401 num SKIP verde, e ninguém percebe.
    """
    opcionais: set[str] = set()
    sumidas = [r for r in LEITURAS if r not in opcionais and not _rota_registrada(r)]
    assert sumidas == [], (
        f"rota(s) de LEITURAS não existem neste build: {sumidas}. "
        "Renomeada? Digitada errada? Um SKIP verde esconderia isso."
    )
