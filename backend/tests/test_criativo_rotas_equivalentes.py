"""Equivalência observável da extração das rotas ``/bancada``.

``ROTAS_ANTES`` foi capturado no commit-base 9885459 antes da refatoração. A
comparação é deliberadamente literal: path, método, status, nome, tag e portão
fazem parte do contrato que S0 não pode mudar.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import fastapi
import pydantic
import pytest
from app.config import get_settings
from app.routers import criativos, criativos_execucao
from app.seguranca import identidade as identidade_modulo
from app.seguranca.identidade import exigir_usuario
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ROTAS_ANTES = (
    ("GET", "/api/criativos/bancada/motores", 200, "bancada_motores"),
    ("POST", "/api/criativos/bancada/trabalhos", 201, "bancada_criar"),
    ("GET", "/api/criativos/bancada/trabalhos", 200, "bancada_listar"),
    ("GET", "/api/criativos/bancada/trabalhos/{trabalho_id}", 200, "bancada_ler"),
    (
        "POST",
        "/api/criativos/bancada/trabalhos/{trabalho_id}/cancelar",
        200,
        "bancada_cancelar",
    ),
    (
        "POST",
        "/api/criativos/bancada/trabalhos/{trabalho_id}/retomar",
        201,
        "bancada_retomar",
    ),
    (
        "GET",
        "/api/criativos/bancada/trabalhos/{trabalho_id}/linhagem",
        200,
        "bancada_linhagem",
    ),
    (
        "GET",
        "/api/criativos/bancada/arquivo/{trabalho_id}/{slot}",
        200,
        "bancada_arquivo",
    ),
)

# SHA-256 do fragmento OpenAPI das oito rotas no commit-base 9885459. O
# fragmento inclui operações completas e os schemas transitivamente
# referenciados: operationId, parâmetros, requestBody, responses, content
# types e components. Um tuple de path/método não provaria esse contrato.
OPENAPI_ANTES_SHA256 = (
    "28bb086dcf5ca5f4667b9c0c4aecb1778783c66c288bc060f5cb674981b020e8"
)

# Golden canônico do fragmento acima no commit 9885459. Ele fica embutido (zlib
# + base64) porque esta rodada não possui ownership para criar outro arquivo.
# No erro, _diff_json o expande e mostra um unified diff legível; o hash abaixo
# impede atualizar a expectativa junto com uma regressão sem perceber.
_OPENAPI_ANTES_ZLIB_B64 = (
    "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"
)
OPENAPI_ANTES = json.loads(
    zlib.decompress(base64.b64decode(_OPENAPI_ANTES_ZLIB_B64))
)

# O runtime aceita somente a faixa cujo OpenAPI desta fronteira foi exercitado
# (2.11.7 e 2.13.4). requirements-dev.txt fixa a ponta nova para que um checkout
# limpo não escolha outra versão ao gerar o golden.
PYDANTIC_MINIMO = (2, 11, 7)
PYDANTIC_MAXIMO_EXCLUSIVO = (2, 14, 0)
PYDANTIC_DEV_FIXO = "2.13.4"


def _versao_tripla(valor: str) -> tuple[int, int, int]:
    partes = valor.split(".", 3)
    return tuple(int(parte) for parte in partes[:3])  # type: ignore[return-value]


def _json_canonico(valor: Any) -> bytes:
    return json.dumps(
        valor,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _diff_json(esperado: Any, atual: Any) -> str:
    antes = json.dumps(
        esperado, sort_keys=True, indent=2, ensure_ascii=False
    ).splitlines()
    depois = json.dumps(
        atual, sort_keys=True, indent=2, ensure_ascii=False
    ).splitlines()
    return "\n".join(
        difflib.unified_diff(
            antes,
            depois,
            fromfile="openapi-9885459.golden.json",
            tofile="openapi-atual.json",
            lineterm="",
        )
    )


def _assert_json_semantico(atual: Any, esperado: Any, caminho: str = "$") -> None:
    """Igualdade JSON sensível a tipo, forma, chave e conteúdo.

    A igualdade comum de Python aceita True == 1. Para contrato HTTP isso seria
    uma mutação de tipo sobrevivente, então cada nó é comparado também pela
    classe concreta e o erro aponta o JSONPath divergente.
    """

    if type(atual) is not type(esperado):
        raise AssertionError(
            f"{caminho}: tipo {type(atual).__name__}, "
            f"esperado {type(esperado).__name__}"
        )
    if isinstance(esperado, dict):
        faltantes = sorted(set(esperado) - set(atual))
        extras = sorted(set(atual) - set(esperado))
        if faltantes or extras:
            raise AssertionError(
                f"{caminho}: chaves faltantes={faltantes}, extras={extras}"
            )
        for chave in esperado:
            _assert_json_semantico(atual[chave], esperado[chave], f"{caminho}.{chave}")
        return
    if isinstance(esperado, list):
        if len(atual) != len(esperado):
            raise AssertionError(
                f"{caminho}: tamanho {len(atual)}, esperado {len(esperado)}"
            )
        for indice, (item_atual, item_esperado) in enumerate(zip(atual, esperado)):
            _assert_json_semantico(
                item_atual, item_esperado, f"{caminho}[{indice}]"
            )
        return
    if atual != esperado:
        raise AssertionError(f"{caminho}: valor {atual!r}, esperado {esperado!r}")


def _assert_resposta_json(
    resposta,
    *,
    status: int,
    corpo: Any,
    idempotente: str | None = None,
) -> None:
    assert resposta.status_code == status, resposta.text
    assert resposta.headers["content-type"] == "application/json"
    assert resposta.headers.get("X-Criativo-Idempotente") == idempotente
    _assert_json_semantico(resposta.json(), corpo)


def _manifesto(rotas) -> tuple[tuple[str, str, int, str], ...]:
    manifesto = []
    for rota in rotas:
        if not isinstance(rota, APIRoute) or "/bancada" not in rota.path:
            continue
        metodos = sorted(rota.methods)
        assert len(metodos) == 1
        manifesto.append((metodos[0], rota.path, rota.status_code or 200, rota.name))
    return tuple(manifesto)


def _guardas(rota: APIRoute) -> set[object]:
    return {
        dependencia.call
        for dependencia in rota.dependant.dependencies
    }


def _fragmento_openapi(app: FastAPI) -> dict:
    schema = app.openapi()
    paths = {
        path: operacoes
        for path, operacoes in schema["paths"].items()
        if "/api/criativos/bancada" in path
    }
    referencias: set[str] = set()

    def visitar(valor) -> None:
        if isinstance(valor, dict):
            for chave, filho in valor.items():
                if (
                    chave == "$ref"
                    and isinstance(filho, str)
                    and filho.startswith("#/components/schemas/")
                ):
                    referencias.add(filho.rsplit("/", 1)[-1])
                else:
                    visitar(filho)
        elif isinstance(valor, list):
            for filho in valor:
                visitar(filho)

    visitar(paths)
    componentes: dict[str, dict] = {}
    pendentes = list(referencias)
    while pendentes:
        nome = pendentes.pop()
        if nome in componentes:
            continue
        componente = schema.get("components", {}).get("schemas", {}).get(nome)
        if componente is None:
            continue
        componentes[nome] = componente
        anteriores = set(referencias)
        visitar(componente)
        pendentes.extend(sorted(referencias - anteriores))
    return {"paths": paths, "components": {"schemas": componentes}}


def test_manifesto_http_e_identico_ao_commit_base():
    assert _manifesto(criativos_execucao.router.routes) == ROTAS_ANTES
    for rota in criativos_execucao.router.routes:
        if isinstance(rota, APIRoute):
            assert rota.tags == ["criativos"]
            assert exigir_usuario in _guardas(rota)


def test_toolchain_do_golden_e_declarada_e_esta_na_faixa_provada():
    assert fastapi.__version__ == "0.115.6", (
        f"FastAPI {fastapi.__version__} não gera o golden provado; "
        "instale backend/requirements-dev.txt"
    )
    versao = _versao_tripla(pydantic.__version__)
    assert PYDANTIC_MINIMO <= versao < PYDANTIC_MAXIMO_EXCLUSIVO, (
        f"Pydantic {pydantic.__version__} fora da faixa "
        f"[{PYDANTIC_MINIMO}, {PYDANTIC_MAXIMO_EXCLUSIVO}); "
        "instale backend/requirements-dev.txt"
    )

    requisitos_dev = (
        Path(__file__).resolve().parents[1] / "requirements-dev.txt"
    ).read_text(encoding="utf-8").splitlines()
    assert f"pydantic=={PYDANTIC_DEV_FIXO}" in requisitos_dev


def test_diagnostico_do_golden_mostra_arquivo_e_valor_que_mudou():
    diff = _diff_json(
        {"paths": {"/bancada": {"status": 201}}},
        {"paths": {"/bancada": {"status": 200}}},
    )
    assert "--- openapi-9885459.golden.json" in diff
    assert "+++ openapi-atual.json" in diff
    assert '-      "status": 201' in diff
    assert '+      "status": 200' in diff


def test_openapi_completo_e_byte_estavel_em_relacao_ao_commit_base():
    from app.main import app

    esperado = _json_canonico(OPENAPI_ANTES)
    assert hashlib.sha256(esperado).hexdigest() == OPENAPI_ANTES_SHA256

    atual = _fragmento_openapi(app)
    serializado = _json_canonico(atual)
    if serializado != esperado:
        pytest.fail(
            "O contrato OpenAPI das oito rotas divergiu do commit 9885459.\n"
            f"esperado sha256={OPENAPI_ANTES_SHA256}\n"
            f"atual    sha256={hashlib.sha256(serializado).hexdigest()}\n"
            f"{_diff_json(OPENAPI_ANTES, atual)}",
            pytrace=False,
        )


def test_router_de_produto_nao_mantem_copia_das_rotas_de_execucao():
    assert _manifesto(criativos.router.routes) == ()


def test_app_registra_cada_rota_da_bancada_uma_unica_vez():
    from app.main import app

    assert _manifesto(app.routes) == ROTAS_ANTES
    rotas_servidas = [
        rota
        for rota in app.routes
        if isinstance(rota, APIRoute) and "/bancada" in rota.path
    ]
    assert len(rotas_servidas) == len(ROTAS_ANTES)
    for rota in rotas_servidas:
        assert rota.endpoint.__module__ == "app.routers.criativos_execucao"
        assert exigir_usuario in _guardas(rota), (
            f"{next(iter(rota.methods))} {rota.path} está servida sem exigir_usuario"
        )


def test_oraculo_de_payload_mata_chave_tipo_forma_e_conteudo():
    esperado = {"estado": "rendered", "tentativa": 1, "recibo": {"ok": True}}
    mutantes = (
        {"status": "rendered", "tentativa": 1, "recibo": {"ok": True}},
        {"estado": "rendered", "tentativa": True, "recibo": {"ok": True}},
        {"estado": "rendered", "tentativa": 1, "recibo": [{"ok": True}]},
        {"estado": "failed", "tentativa": 1, "recibo": {"ok": True}},
    )
    for mutante in mutantes:
        with pytest.raises(AssertionError):
            _assert_json_semantico(mutante, esperado)


def _resetar_caches_criativos(app: FastAPI) -> None:
    """Nenhum singleton de outro teste pode escolher pasta ou identidade aqui."""

    from app.criativo.bancada import servico

    servico.parar_reaper()
    servico._BANCADA = None
    criativos._motor_cache = None
    criativos._executor_cache.clear()
    get_settings.cache_clear()
    app.openapi_schema = None


@pytest.mark.identidade_real
@pytest.mark.parametrize("credencial", [None, "Bearer token-invalido"])
def test_todas_as_rotas_recusam_credencial_ausente_ou_invalida(
    monkeypatch,
    tmp_path,
    credencial,
):
    """Prova as APIRoutes servidas sem aquecer fila ou escrever no caminho real."""

    from app.main import app

    async def token_invalido(*_args, **_kwargs):
        raise HTTPException(status_code=401, detail="Credencial inválida ou expirada.")

    raiz = tmp_path / "bancada-que-nao-pode-nascer"
    monkeypatch.setenv("CRIATIVO_BANCADA_DIR", str(raiz))
    _resetar_caches_criativos(app)
    monkeypatch.setattr(identidade_modulo, "_usuario_do_token", token_invalido)
    monkeypatch.setitem(
        app.dependency_overrides,
        get_settings,
        lambda: SimpleNamespace(
            supabase_url="https://auth.invalid",
            supabase_service_role_key="somente-teste",
        ),
    )
    assert exigir_usuario not in app.dependency_overrides

    cliente = TestClient(app)
    headers = {"Authorization": credencial} if credencial else {}
    casos = (
        ("GET", "/api/criativos/bancada/motores", None),
        (
            "POST",
            "/api/criativos/bancada/trabalhos",
            {
                "receitaId": "receita-1",
                "motorSlug": "motor-1",
                "modoSlug": "modo-1",
                "finalidadeSlug": "finalidade-1",
                "seed": 1,
                "slots": ["1x1"],
                "titulo": "Título",
            },
        ),
        ("GET", "/api/criativos/bancada/trabalhos", None),
        ("GET", "/api/criativos/bancada/trabalhos/t-1", None),
        (
            "POST",
            "/api/criativos/bancada/trabalhos/t-1/cancelar",
            {"motivo": "cancelamento de teste"},
        ),
        ("POST", "/api/criativos/bancada/trabalhos/t-1/retomar", None),
        ("GET", "/api/criativos/bancada/trabalhos/t-1/linhagem", None),
        ("GET", "/api/criativos/bancada/arquivo/t-1/1x1", None),
    )
    try:
        for metodo, path, corpo in casos:
            resposta = cliente.request(metodo, path, headers=headers, json=corpo)
            assert resposta.status_code == 401, (metodo, path, resposta.text)
        assert not raiz.exists(), "uma requisição recusada aqueceu/escreveu a bancada"
    finally:
        _resetar_caches_criativos(app)


def test_dtos_de_entrada_preservam_campos_obrigatorios_e_limites():
    producao = criativos_execucao.PedidoDeProducao.model_json_schema()
    assert list(producao["properties"]) == [
        "receitaId",
        "motorSlug",
        "modoSlug",
        "finalidadeSlug",
        "seed",
        "slots",
        "titulo",
        "apoio",
    ]
    assert producao["required"] == [
        "receitaId",
        "motorSlug",
        "modoSlug",
        "finalidadeSlug",
        "seed",
        "slots",
        "titulo",
    ]
    assert producao["properties"]["seed"] == {
        "maximum": 2**31 - 1,
        "minimum": 0,
        "title": "Seed",
        "type": "integer",
    }
    assert producao["properties"]["slots"]["minItems"] == 1
    assert producao["properties"]["slots"]["maxItems"] == 12

    cancelamento = criativos_execucao.PedidoDeCancelamento.model_json_schema()
    assert cancelamento["required"] == ["motivo"]
    assert cancelamento["properties"]["motivo"]["minLength"] == 3
    assert cancelamento["properties"]["motivo"]["maxLength"] == 280


class _Identidade:
    sub, role, email = "usuario-de-teste", "ADMIN", "t@volc"


class _DepositoFalso:
    def __init__(self, trabalho) -> None:
        self.trabalho = trabalho

    def por_id(self, trabalho_id: str, *, tenant_id: str):
        assert trabalho_id == "t-1"
        assert tenant_id == "usuario-de-teste"
        return self.trabalho


def _cliente(monkeypatch, trabalho) -> TestClient:
    deposito = _DepositoFalso(trabalho)
    monkeypatch.setattr(
        criativos_execucao.bancada_servico,
        "montar",
        lambda: (deposito, None, None),
    )
    app = FastAPI()
    app.include_router(criativos_execucao.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Identidade()
    return TestClient(app)


def test_payload_de_leitura_e_byte_equivalente_ao_baseline(monkeypatch):
    instante = datetime(2026, 8, 29, 16, 0, tzinfo=timezone.utc)
    trabalho = SimpleNamespace(
        id="t-1",
        estado=SimpleNamespace(value="rendered"),
        tentativa=1,
        max_tentativas=3,
        operario=None,
        lease_ate=None,
        batimento_em=None,
        vivo=False,
        falha=None,
        recibo={
            "trabalho_id": "t-1",
            "produzido_por": "worker-1",
            "motor_slug": "tipografico-local",
            "motor_versao": "1",
            "seed": 7,
            "versoes": {"fonte_sha256": "abc"},
            "parametros": {"titulo": "Peça"},
            "artefatos": [
                {
                    "slot": "1x1",
                    "caminho": "/nao-vaza/peca.png",
                    "mime": "image/png",
                    "bytes_": 123,
                    "sha256": "def",
                    "largura": 1080,
                    "altura": 1080,
                    "duracao_s": None,
                }
            ],
            "validacoes": [
                {
                    "gate": "dimensao",
                    "resultado": "PASS",
                    "detalhe": None,
                    "bloqueante": True,
                }
            ],
            "audio": None,
            "iniciado_em": "2026-08-29T16:00:00+00:00",
            "terminado_em": "2026-08-29T16:00:01+00:00",
            "custo_estimado_usd": None,
            "custo_real_usd": None,
            "assinatura_determinista": "sig",
        },
        retoma_de=None,
        retomada_n=0,
        cancelado_por=None,
        cancelado_motivo=None,
        criado_em=instante,
    )
    resposta = _cliente(monkeypatch, trabalho).get(
        "/api/criativos/bancada/trabalhos/t-1"
    )
    assert resposta.status_code == 200
    assert resposta.content == (
        b'{"id":"t-1","estado":"rendered","tentativa":1,"maxTentativas":3,'
        b'"operario":null,"leaseAte":null,"batimentoEm":null,"vivo":false,'
        b'"falha":null,"recibo":{"trabalhoId":"t-1","produzidoPor":"worker-1",'
        b'"motorSlug":"tipografico-local","motorVersao":"1","seed":7,'
        b'"versoes":{"fonte_sha256":"abc"},"parametros":{"titulo":"Pe\xc3\xa7a"},'
        b'"artefatos":[{"slot":"1x1","mime":"image/png","bytes":123,'
        b'"sha256":"def","largura":1080,"altura":1080,"duracaoS":null}],'
        b'"validacoes":[{"gate":"dimensao","resultado":"PASS","detalhe":null,'
        b'"bloqueante":true}],"audio":null,"iniciadoEm":"2026-08-29T16:00:00+00:00",'
        b'"terminadoEm":"2026-08-29T16:00:01+00:00","custoEstimadoUsd":null,'
        b'"custoRealUsd":null,"assinaturaDeterminista":"sig"},"retomaDe":null,'
        b'"retomadaN":0,"canceladoPor":null,"canceladoMotivo":null,'
        b'"criadoEm":"2026-08-29T16:00:00+00:00","podeRetomar":false,'
        b'"podeCancelar":false}'
    )
    assert b"caminho" not in resposta.content


def test_404_continua_indistinguivel_e_com_payload_exato(monkeypatch):
    resposta = _cliente(monkeypatch, None).get(
        "/api/criativos/bancada/trabalhos/t-1"
    )
    assert resposta.status_code == 404
    assert resposta.content == (
        b'{"detail":{"codigo":"ESTUDIO.trabalho_nao_encontrado",'
        b'"mensagem":"Trabalho n\xc3\xa3o encontrado."}}'
    )


_CRIADO_EM = datetime(2026, 8, 29, 15, 59, tzinfo=timezone.utc)
_BATIMENTO_EM = datetime(2026, 8, 29, 16, 4, tzinfo=timezone.utc)
_LEASE_ATE = datetime(2026, 8, 29, 16, 5, tzinfo=timezone.utc)


def _recibo_interno(trabalho_id: str) -> dict[str, Any]:
    return {
        "trabalho_id": trabalho_id,
        "produzido_por": "worker-α",
        "motor_slug": "tipografico-local",
        "motor_versao": "1.2.3",
        "seed": 7,
        "versoes": {"adaptador": "2", "fonte_sha256": "abc123"},
        "parametros": {
            "titulo": "Peça de prova",
            "apoio": "Linha de apoio",
            "escala": 1.25,
            "rascunho": False,
        },
        "artefatos": [
            {
                "slot": "1x1",
                "caminho": "/nao-vaza/peca.png",
                "mime": "image/png",
                "bytes_": 123,
                "sha256": "def456",
                "largura": 1080,
                "altura": 1080,
                "duracao_s": None,
            },
            {
                "slot": "video-9x16",
                "caminho": "/nao-vaza/peca.mp4",
                "mime": "video/mp4",
                "bytes_": 456,
                "sha256": "ghi789",
                "largura": 1080,
                "altura": 1920,
                "duracao_s": 2.5,
            },
        ],
        "validacoes": [
            {
                "gate": "dimensao",
                "resultado": "PASS",
                "detalhe": {
                    "esperado": [1080, 1080],
                    "medido": [1080, 1080],
                },
                "bloqueante": True,
            },
            {
                "gate": "audio",
                "resultado": "SKIPPED",
                "detalhe": None,
                "bloqueante": False,
            },
        ],
        "audio": {"codec": "aac", "canais": 2, "normalizado": True},
        "iniciado_em": "2026-08-29T16:00:00+00:00",
        "terminado_em": "2026-08-29T16:00:02+00:00",
        "custo_estimado_usd": 0.75,
        "custo_real_usd": 0.625,
        "assinatura_determinista": "sig-123",
    }


def _recibo_publico(trabalho_id: str) -> dict[str, Any]:
    return {
        "trabalhoId": trabalho_id,
        "produzidoPor": "worker-α",
        "motorSlug": "tipografico-local",
        "motorVersao": "1.2.3",
        "seed": 7,
        "versoes": {"adaptador": "2", "fonte_sha256": "abc123"},
        "parametros": {
            "titulo": "Peça de prova",
            "apoio": "Linha de apoio",
            "escala": 1.25,
            "rascunho": False,
        },
        "artefatos": [
            {
                "slot": "1x1",
                "mime": "image/png",
                "bytes": 123,
                "sha256": "def456",
                "largura": 1080,
                "altura": 1080,
                "duracaoS": None,
            },
            {
                "slot": "video-9x16",
                "mime": "video/mp4",
                "bytes": 456,
                "sha256": "ghi789",
                "largura": 1080,
                "altura": 1920,
                "duracaoS": 2.5,
            },
        ],
        "validacoes": [
            {
                "gate": "dimensao",
                "resultado": "PASS",
                "detalhe": {
                    "esperado": [1080, 1080],
                    "medido": [1080, 1080],
                },
                "bloqueante": True,
            },
            {
                "gate": "audio",
                "resultado": "SKIPPED",
                "detalhe": None,
                "bloqueante": False,
            },
        ],
        "audio": {"codec": "aac", "canais": 2, "normalizado": True},
        "iniciadoEm": "2026-08-29T16:00:00+00:00",
        "terminadoEm": "2026-08-29T16:00:02+00:00",
        "custoEstimadoUsd": 0.75,
        "custoRealUsd": 0.625,
        "assinaturaDeterminista": "sig-123",
    }


def _trabalho_contrato(
    trabalho_id: str,
    estado: str,
    *,
    tentativa: int = 1,
    max_tentativas: int = 3,
    operario: str | None = None,
    lease_ate: datetime | None = None,
    batimento_em: datetime | None = None,
    vivo: bool = False,
    falha: dict[str, Any] | None = None,
    recibo: dict[str, Any] | None = None,
    retoma_de: str | None = None,
    retomada_n: int = 0,
    cancelado_por: str | None = None,
    cancelado_motivo: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=trabalho_id,
        estado=SimpleNamespace(value=estado),
        tentativa=tentativa,
        max_tentativas=max_tentativas,
        operario=operario,
        lease_ate=lease_ate,
        batimento_em=batimento_em,
        vivo=vivo,
        falha=falha,
        recibo=recibo,
        retoma_de=retoma_de,
        retomada_n=retomada_n,
        cancelado_por=cancelado_por,
        cancelado_motivo=cancelado_motivo,
        criado_em=_CRIADO_EM,
    )


def _dto_esperado(
    trabalho_id: str,
    estado: str,
    *,
    tentativa: int = 1,
    max_tentativas: int = 3,
    operario: str | None = None,
    lease_ate: str | None = None,
    batimento_em: str | None = None,
    vivo: bool = False,
    falha: dict[str, Any] | None = None,
    recibo: dict[str, Any] | None = None,
    retoma_de: str | None = None,
    retomada_n: int = 0,
    cancelado_por: str | None = None,
    cancelado_motivo: str | None = None,
    pode_retomar: bool = False,
    pode_cancelar: bool = False,
) -> dict[str, Any]:
    return {
        "id": trabalho_id,
        "estado": estado,
        "tentativa": tentativa,
        "maxTentativas": max_tentativas,
        "operario": operario,
        "leaseAte": lease_ate,
        "batimentoEm": batimento_em,
        "vivo": vivo,
        "falha": falha,
        "recibo": recibo,
        "retomaDe": retoma_de,
        "retomadaN": retomada_n,
        "canceladoPor": cancelado_por,
        "canceladoMotivo": cancelado_motivo,
        "criadoEm": "2026-08-29T15:59:00+00:00",
        "podeRetomar": pode_retomar,
        "podeCancelar": pode_cancelar,
    }


def _renderizado(trabalho_id: str = "t-rendered"):
    trabalho = _trabalho_contrato(
        trabalho_id,
        "rendered",
        tentativa=2,
        max_tentativas=4,
        batimento_em=_BATIMENTO_EM,
        recibo=_recibo_interno(trabalho_id),
        retoma_de="t-original",
        retomada_n=1,
    )
    esperado = _dto_esperado(
        trabalho_id,
        "rendered",
        tentativa=2,
        max_tentativas=4,
        batimento_em="2026-08-29T16:04:00+00:00",
        recibo=_recibo_publico(trabalho_id),
        retoma_de="t-original",
        retomada_n=1,
    )
    return trabalho, esperado


def _executando():
    falha = {
        "codigo": "tentativa_anterior",
        "permanente": False,
        "detalhes": ["timeout", 2],
    }
    trabalho = _trabalho_contrato(
        "t-running",
        "running",
        operario="worker-live",
        lease_ate=_LEASE_ATE,
        batimento_em=_BATIMENTO_EM,
        vivo=True,
        falha=falha,
    )
    esperado = _dto_esperado(
        "t-running",
        "running",
        operario="worker-live",
        lease_ate="2026-08-29T16:05:00+00:00",
        batimento_em="2026-08-29T16:04:00+00:00",
        vivo=True,
        falha=falha,
        pode_cancelar=True,
    )
    return trabalho, esperado


def _falho(
    trabalho_id: str,
    *,
    retoma_de: str | None = None,
    retomada_n: int = 0,
):
    falha = {
        "codigo": "motor_desconhecido",
        "mensagem": "Motor não registrado.",
        "permanente": True,
        "tentativas": [1, 2],
    }
    trabalho = _trabalho_contrato(
        trabalho_id,
        "failed",
        tentativa=2,
        falha=falha,
        retoma_de=retoma_de,
        retomada_n=retomada_n,
    )
    esperado = _dto_esperado(
        trabalho_id,
        "failed",
        tentativa=2,
        falha=falha,
        retoma_de=retoma_de,
        retomada_n=retomada_n,
        pode_retomar=True,
    )
    return trabalho, esperado


def _cancelado():
    trabalho = _trabalho_contrato(
        "t-cancelled",
        "cancelled",
        cancelado_por="usuario-de-teste",
        cancelado_motivo="briefing substituído",
    )
    esperado = _dto_esperado(
        "t-cancelled",
        "cancelled",
        cancelado_por="usuario-de-teste",
        cancelado_motivo="briefing substituído",
        pode_retomar=True,
    )
    return trabalho, esperado


def _cliente_contrato(
    monkeypatch,
    deposito: Mock,
    despachante: Mock | None = None,
) -> TestClient:
    despachante = despachante or Mock()
    monkeypatch.setattr(
        criativos_execucao.bancada_servico,
        "montar",
        lambda: (deposito, None, despachante),
    )
    app = FastAPI()
    app.include_router(criativos_execucao.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Identidade()
    return TestClient(app)


def test_payload_de_motores_e_semanticamente_exato(monkeypatch):
    motores = [
        {
            "slug": "tipografico-local",
            "versao": "1.2.3",
            "versoes": {"fonte_sha256": "abc123", "adaptador": "2"},
            "produz": ["imagem"],
        }
    ]
    monkeypatch.setattr(
        criativos_execucao.bancada_servico,
        "motores_disponiveis",
        lambda: motores,
    )
    resposta = _cliente_contrato(monkeypatch, Mock()).get(
        "/api/criativos/bancada/motores"
    )
    _assert_resposta_json(resposta, status=200, corpo={"motores": motores})


_PEDIDO = {
    "receitaId": "receita-contrato",
    "motorSlug": "tipografico-local",
    "modoSlug": "typography_only",
    "finalidadeSlug": "google_display",
    "seed": 17,
    "slots": ["1x1", "4x5"],
    "titulo": "Título contratual",
    "apoio": "  apoio preservado nas bordas  ",
}


def test_payload_de_criacao_inicial_status_header_e_conteudo(monkeypatch):
    deposito = Mock()
    despachante = Mock()
    enfileirado = _trabalho_contrato("t-criado", "queued")
    final, esperado = _renderizado("t-criado")
    deposito.enfileirar.return_value = (enfileirado, True)
    deposito.por_id.return_value = final

    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos", json=_PEDIDO
    )
    _assert_resposta_json(resposta, status=201, corpo=esperado)
    despachante.despachar.assert_called_once_with("t-criado")
    deposito.por_id.assert_called_once_with(
        "t-criado", tenant_id="usuario-de-teste"
    )

    encomenda = deposito.enfileirar.call_args.args[0]
    assert (
        encomenda.receita_id,
        encomenda.tenant_id,
        encomenda.motor_slug,
        encomenda.modo_slug,
        encomenda.finalidade_slug,
        encomenda.seed,
    ) == (
        "receita-contrato",
        "usuario-de-teste",
        "tipografico-local",
        "typography_only",
        "google_display",
        17,
    )
    assert [
        (saida.slot, saida.largura, saida.altura, saida.midia, saida.mime)
        for saida in encomenda.saidas
    ] == [
        ("1x1", 1080, 1080, "imagem", "image/png"),
        ("4x5", 1080, 1350, "imagem", "image/png"),
    ]
    _assert_json_semantico(
        encomenda.parametros,
        {"titulo": "Título contratual", "apoio": "apoio preservado nas bordas"},
    )


def test_payload_de_replay_da_criacao_status_header_e_conteudo(monkeypatch):
    deposito = Mock()
    despachante = Mock()
    trabalho, esperado = _renderizado("t-replay")
    deposito.enfileirar.return_value = (trabalho, False)

    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos", json=_PEDIDO
    )
    _assert_resposta_json(
        resposta,
        status=200,
        corpo=esperado,
        idempotente="replay",
    )
    despachante.despachar.assert_not_called()
    deposito.por_id.assert_not_called()


def test_payload_de_listagem_e_semanticamente_exato(monkeypatch):
    deposito = Mock()
    executando, esperado_executando = _executando()
    renderizado, esperado_renderizado = _renderizado()
    deposito.listar.return_value = [executando, renderizado]

    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/trabalhos?limite=7"
    )
    _assert_resposta_json(
        resposta,
        status=200,
        corpo={"trabalhos": [esperado_executando, esperado_renderizado]},
    )
    deposito.listar.assert_called_once_with(
        tenant_id="usuario-de-teste", limite=7
    )


def test_payload_de_leitura_rico_e_semanticamente_exato(monkeypatch):
    deposito = Mock()
    trabalho, esperado = _renderizado("t-rico")
    deposito.por_id.return_value = trabalho
    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/trabalhos/t-rico"
    )
    _assert_resposta_json(resposta, status=200, corpo=esperado)
    deposito.por_id.assert_called_once_with(
        "t-rico", tenant_id="usuario-de-teste"
    )
    assert "caminho" not in resposta.text


def test_payload_de_cancelamento_e_semanticamente_exato(monkeypatch):
    deposito = Mock()
    trabalho, esperado = _cancelado()
    deposito.cancelar.return_value = trabalho

    resposta = _cliente_contrato(monkeypatch, deposito).post(
        "/api/criativos/bancada/trabalhos/t-cancelled/cancelar",
        json={"motivo": "briefing substituído"},
    )
    _assert_resposta_json(resposta, status=200, corpo=esperado)
    deposito.cancelar.assert_called_once_with(
        "t-cancelled",
        tenant_id="usuario-de-teste",
        por="usuario-de-teste",
        motivo="briefing substituído",
    )


def test_retomada_inicial_prova_status_header_despacho_e_payload(monkeypatch):
    deposito = Mock()
    despachante = Mock()
    antes = _trabalho_contrato(
        "t-retomado",
        "queued",
        retoma_de="t-original",
        retomada_n=1,
    )
    final, esperado = _falho(
        "t-retomado", retoma_de="t-original", retomada_n=1
    )
    deposito.retomar.return_value = (antes, True)
    deposito.por_id.return_value = final

    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos/t-original/retomar"
    )
    _assert_resposta_json(resposta, status=201, corpo=esperado)
    deposito.retomar.assert_called_once_with(
        "t-original", tenant_id="usuario-de-teste"
    )
    despachante.despachar.assert_called_once_with("t-retomado")
    deposito.por_id.assert_called_once_with(
        "t-retomado", tenant_id="usuario-de-teste"
    )


@pytest.mark.parametrize(
    ("rota", "preparar", "id_final"),
    [
        (
            "/api/criativos/bancada/trabalhos",
            lambda deposito: deposito.enfileirar.configure_mock(
                return_value=(_trabalho_contrato("t-criado", "queued"), True)
            ),
            "t-criado",
        ),
        (
            "/api/criativos/bancada/trabalhos/t-original/retomar",
            lambda deposito: deposito.retomar.configure_mock(
                return_value=(
                    _trabalho_contrato(
                        "t-retomado",
                        "queued",
                        retoma_de="t-original",
                        retomada_n=1,
                    ),
                    True,
                )
            ),
            "t-retomado",
        ),
    ],
)
def test_criacao_e_retomada_nao_releem_recibo_fora_do_tenant(
    monkeypatch, rota, preparar, id_final
):
    """O id do trabalho não substitui o portão de tenant no pós-despacho.

    O dublê deliberadamente recusa a chamada sem ``tenant_id``. Assim a prova
    falha no ponto da leitura (antes de comparar o DTO) se criação ou retomada
    voltarem a usar o UUID como se fosse autorização.
    """

    class DepositoComFronteira(Mock):
        def por_id(self, trabalho_id: str, *, tenant_id: str):
            assert trabalho_id == id_final
            assert tenant_id == "usuario-de-teste"
            return None

    deposito = DepositoComFronteira()
    preparar(deposito)
    despachante = Mock()
    cliente = _cliente_contrato(monkeypatch, deposito, despachante)

    if rota.endswith("/retomar"):
        resposta = cliente.post(rota)
    else:
        resposta = cliente.post(rota, json=_PEDIDO)

    assert resposta.status_code == 201, resposta.text
    despachante.despachar.assert_called_once_with(id_final)


def test_replay_da_retomada_prova_status_header_e_nao_redespacha(monkeypatch):
    deposito = Mock()
    despachante = Mock()
    retomado, esperado = _falho(
        "t-retomado", retoma_de="t-original", retomada_n=1
    )
    deposito.retomar.return_value = (retomado, False)

    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos/t-original/retomar"
    )
    _assert_resposta_json(
        resposta,
        status=200,
        corpo=esperado,
        idempotente="replay",
    )
    despachante.despachar.assert_not_called()
    deposito.por_id.assert_not_called()


def test_payload_de_linhagem_e_semanticamente_exato(monkeypatch):
    deposito = Mock()
    original, esperado_original = _falho("t-original")
    retomado, esperado_retomado = _falho(
        "t-retomado", retoma_de="t-original", retomada_n=1
    )
    deposito.linhagem.return_value = [original, retomado]

    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/trabalhos/t-retomado/linhagem"
    )
    _assert_resposta_json(
        resposta,
        status=200,
        corpo={"linhagem": [esperado_original, esperado_retomado]},
    )
    deposito.linhagem.assert_called_once_with(
        "t-retomado", tenant_id="usuario-de-teste"
    )


def test_payload_de_arquivo_preserva_bytes_mime_e_tamanho(
    monkeypatch, tmp_path
):
    raiz = tmp_path / "bancada"
    arquivo = raiz / "trabalhos" / "t-arquivo" / "1" / "peca.png"
    arquivo.parent.mkdir(parents=True)
    conteudo = b"\x89PNG\r\n\x1a\nVOLC-contrato-binario\x00\xff"
    arquivo.write_bytes(conteudo)
    trabalho = _trabalho_contrato(
        "t-arquivo",
        "rendered",
        recibo={
            "artefatos": [
                {
                    "slot": "1x1",
                    "caminho": str(arquivo),
                    "mime": "image/png",
                }
            ]
        },
    )
    deposito = Mock()
    deposito.por_id.return_value = trabalho
    monkeypatch.setattr(
        criativos_execucao.bancada_servico,
        "raiz_da_bancada",
        lambda: raiz,
    )

    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/arquivo/t-arquivo/1x1"
    )
    assert resposta.status_code == 200
    assert resposta.content == conteudo
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.headers["content-length"] == str(len(conteudo))
    assert "content-disposition" not in resposta.headers
    deposito.por_id.assert_called_once_with(
        "t-arquivo", tenant_id="usuario-de-teste"
    )


def test_fronteiras_futuras_sao_importaveis_e_vazias_de_comportamento():
    from app.criativo import deposito, destino, worker

    for modulo in (deposito, worker, destino):
        publicos = {nome for nome in vars(modulo) if not nome.startswith("__")}
        assert publicos == set()
