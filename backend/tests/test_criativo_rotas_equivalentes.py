"""Equivalência observável da extração das rotas ``/bancada``.

``ROTAS_ANTES`` foi capturado no commit-base 9885459 antes da refatoração. A
comparação é deliberadamente literal: path, método, status, nome, tag e portão
fazem parte do contrato que S0 não pode mudar.
"""

from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import json
import os
import zlib
from dataclasses import dataclass
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
    "eNrtWcFu3DYQ/RVC7XHhtR0jKXxz4jQ1YMeu7eQSB+uxNNYyEEWFohaxjf2G3ntq0UPRc3soevWf9Af6C50hJa12V/J6AydtnJx2Jc68GQ7nzZDUVRBqlekUU5sHm1dBHg5Rgfv73fHxwUtIZARW6vSpMdrw68zoDI2V6IQitCAT/ictKvfqa4PnwWbwVX+C3C9h+7N4415gpU2Q5Lc9Er24yPgZjIGLYNyQaHOoFtdnbzC0DHiAkYz0Nj6BNMQEFDmg5x1X2sqRe6/g3S6msR0Gm+vfrPYCJdPq+cHE+J6Xr+3l1sg0dv4ZfFtIg1Gw+aqCfT1RbHXnBrcPjI6KELSPbh4amfF0SfaFEpkTEhGKjMWuf73+RYtEh5CsiOf8PyvOEhlCT6T8RLYMxtVTDlJEQL6ukP3paECmpbMI6cU+rd6r+bDMzLt3Vb1JiyQJxo0ZbzkwmtK5TN1yRXiUFPFMrB9uTIV6baL/ba2Ws9q8aYpypJeC3COFbjCrzZJopNEFZzBEaWEnmoFbW1/twjv0KjJqw8sRKyipCkWrsbbxaOObBw83Hq14RP96lZ8qxCNWqsFkajFGx7Y80Z7oNV3n4wHvdvzg2rrDr54a8A5llqpuvEgWkaqBc+zlF5FqEtLmajXSYC7VyrBV8609a+FlzbcWTi4sf0S9qWBO6NNJl3oxXjdK2y5R2LF8PqYqd4lZ5x7mOcTYlin+xUTU+SyO+e2iCPM8vKlSshGohSWXwTKwQxeBPmSyT0ULuA7m/TOqehBBHwwZG+n+lTVwBslQD2Q07l/x8oxZLUY7X/CO0IxQaAHG4jlY7YveJVdAV/O4luLKSXqS/v3jT//8+YPYFyFQpg21GKESJHb49MnO432qfwW5QcVPvDjcXRF7OrVgCLiSBpGRDWlY5W1BJk/SMJGMLhSkkS5EjjQlQc6PKP70jypwRMGz178bSThaCV1Yo0WqFXJ55SRxMeM6EJRRGJRRGFCMBnWMBrOjg0aMBoMBx2gw4ABxmA11EIsmd0kmOUocehpKaYCeGrpBc42tKbBXtvdmkhyX8mInasuSVhvs0a3Aj7xgF+oQia9mgguFHWojLysqTAycQ5JPWbgF0eb70hT8mIcM5rRFyT2Z11dX+Sek7KCl920x427K8v03OefkVcssD0sQ8dgvpNjyCym2MimeVMs8NyoaoRdCcKyEeIYloWaYUIQhJd55kYjKGjN+Y319KY9v2pq17a5aPJmIiEqG1qVQCswFDc9MkhcfYk7WoM734DWrdNQJV979crSWhO8LkLkopcTTo+Mtoa5/JlspEAspLDHRl6oE0RtibaBZHbblORpHamLvaWV74MBOe474kbyk36YJfCdzqu5EbKoRlGPq+o9UaoLdEpa2c1SSMJQ5FQRa4UjLfFMUyisL2nqRroGyqGBuYeKs25Gxo+7fSZppckqzgyEacaYtj1f7vEtpuotK6WlHUalGu+vHJ85CiCLJQ5AcNFqzr0idDN0rV7edodXoM7Tt3e4TJ2c5v6XJWfWWJj3bczKhxAfTkZI1zA1JSYQhl+ucTKSiPdbNyRjRHqFIyKkHq73JbnlttblJbuw9dyvI2X3ZfWlP70WMXbdwHbyoGtb9ZYaffgcxKFN1fkPSs+zinHcY/99KTMTL7WMdXdzZCs0dtMbTpw/OyPFcrq99+FznBF+c6gd+ve5frrvpv38PmD7KLe4IuJga0wef//bE81kWf1xMh+lTy73tA3hnzOiH/uLX3x7d3EBKySWJUqvd0Fo+F8p8uPY1dX9/qxb2ERhbOrUsbWu1+9vcKtLdFYsTmQ4hRnWLo48XXJLEtdqXtvfxzzw+9EuSqFa7v4ehMuXvikMGrVbTjXDaMQ4+359VWuL5/sv9xu08ukE0ir/29Ny1e8Wb5kWf+xJqEM6M+3qQWhnrFfFCidNzkAlGpyIuwNAMtfDfaxmZYAXl9BAi3RPo1aU5SSGDGNgv/vAihnRA5Dt/WBHbWuYiTCS3HJGCUJgrEH6OkbuNHKHh/GAusyka1ydpPbdUj8hSpg1fDpL8EEYorn8jX4wcMQI7aGTMcxWK7yRJ5/ovhUbzUGWo+2KwDPeShajS+rKZ+OgH0kMf+iXrUKV1b3t5OcGuMjQe/wscd0+y"
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


@dataclass(frozen=True)
class _GoldenHTTP:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    absent_headers: tuple[str, ...] = ()
    json_tipado: bool = True

    def json(self) -> Any:
        # A expectativa nasce de bytes serializados e devolve uma árvore nova.
        return copy.deepcopy(json.loads(self.body.decode("utf-8")))


_HEADERS_VOLATEIS_COMUNS = frozenset({"date"})
_HEADERS_FIXOS_ARQUIVO = {"accept-ranges": "bytes"}
_HEADERS_VOLATEIS_ARQUIVO = frozenset({"etag", "last-modified"})


def _headers_normalizados(headers) -> dict[str, str]:
    return {chave.lower(): valor for chave, valor in headers.items()}


def _assert_headers_golden(resposta, golden: _GoldenHTTP) -> None:
    atuais = _headers_normalizados(resposta.headers)
    esperados = _headers_normalizados(dict(golden.headers))
    volateis = set(_HEADERS_VOLATEIS_COMUNS)

    if not golden.json_tipado:
        esperados.update(_HEADERS_FIXOS_ARQUIVO)
        volateis.update(_HEADERS_VOLATEIS_ARQUIVO)

    for chave in golden.absent_headers:
        chave_normalizada = chave.lower()
        assert chave_normalizada not in atuais, (
            f"header {chave_normalizada!r} deveria estar ausente"
        )

    faltantes = sorted(set(esperados) - set(atuais))
    extras = sorted(set(atuais) - set(esperados) - volateis)
    if faltantes or extras:
        raise AssertionError(
            f"headers divergentes: faltantes={faltantes}, extras={extras}"
        )

    for chave, valor in esperados.items():
        assert atuais[chave] == valor
    for chave in sorted(set(atuais) & volateis):
        assert atuais[chave], f"header volátil {chave!r} veio vazio"


def _regravar(resposta) -> None:
    """Imprime o golden ATUAL, para uma mudança DELIBERADA de contrato.

    ⚠️ Ele não regrava sozinho, e isso é a metade importante: um golden que se
    conserta a si mesmo no primeiro `pytest` deixa de ser golden. Com
    `CRIATIVO_MOSTRAR_GOLDEN=1` ele imprime os bytes e o `content-length` novos, e
    quem muda o contrato cola o literal — declarando a mudança no diff, que é
    onde ela precisa aparecer.

    Existia como lacuna: os goldens dos aceites 1 e 2 foram capturados à mão e
    não tinham caminho de regeneração escrito.
    """
    if os.environ.get("CRIATIVO_MOSTRAR_GOLDEN") != "1":
        return
    print("\n--- GOLDEN ATUAL ---")
    print("status =", resposta.status_code)
    print("content-length =", resposta.headers.get("content-length"))
    print("body =", repr(resposta.content))


def _assert_resposta_golden(resposta, golden: _GoldenHTTP) -> None:
    assert resposta.status_code == golden.status, resposta.text
    _regravar(resposta)
    assert resposta.content == golden.body
    _assert_headers_golden(resposta, golden)
    if golden.json_tipado:
        _assert_json_semantico(resposta.json(), golden.json())


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


#: Baseline do payload de leitura, congelado em bytes.
#:
#: ⚠️ Regravado em 01/09/2026 pela mudança DELIBERADA da fronteira pública:
#: `parametros` deixou de sair cru e passou a ser hash + campos allowlisted +
#: motivos de retenção. Vide `bancada/fronteira_publica.py`. Para regravar,
#: `CRIATIVO_MOSTRAR_GOLDEN=1 pytest -s` imprime o corpo atual.
_BASELINE_LEITURA = b'{"id":"t-1","estado":"rendered","tentativa":1,"maxTentativas":3,"operario":null,"leaseAte":null,"batimentoEm":null,"vivo":false,"falha":null,"recibo":{"trabalhoId":"t-1","produzidoPor":"worker-1","motorSlug":"tipografico-local","motorVersao":"1","seed":7,"versoes":{"fonte_sha256":"abc"},"parametros":{"hash":"sha256:547ec5543c6e03ee6b53c2e691fbcb7e9acb9e8261706bb4d2d41e6c2a6aba0d","campos":{},"retidos":{"titulo":"retido_texto_livre"}},"artefatos":[{"slot":"1x1","mime":"image/png","bytes":123,"sha256":"def","largura":1080,"altura":1080,"duracaoS":null,"video":null,"enquadramento":null}],"validacoes":[{"gate":"dimensao","resultado":"PASS","detalhe":null,"bloqueante":true}],"audio":null,"iniciadoEm":"2026-08-29T16:00:00+00:00","terminadoEm":"2026-08-29T16:00:01+00:00","custoEstimadoUsd":null,"custoRealUsd":null,"assinaturaDeterminista":"sig","procedencia":null,"insumo":null,"hashesDeEntrada":null,"tentativa":null,"custo":null,"duracaoDoTrabalhoS":null,"storage":null,"destinos":null,"aprovacao":null,"audioAusentePorque":null,"videoAusentePorque":null},"retomaDe":null,"retomadaN":0,"canceladoPor":null,"canceladoMotivo":null,"criadoEm":"2026-08-29T16:00:00+00:00","podeRetomar":false,"podeCancelar":false}'


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
    _regravar(resposta)
    assert resposta.content == _BASELINE_LEITURA
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


def _motores_disponiveis_fixture() -> list[dict[str, Any]]:
    return [
        {
            "slug": "tipografico-local",
            "versao": "1.2.3",
            "versoes": {"fonte_sha256": "abc123", "adaptador": "2"},
            "produz": ["imagem"],
        }
    ]


def _trabalho_renderizado(trabalho_id: str = "t-rendered") -> SimpleNamespace:
    return _trabalho_contrato(
        trabalho_id,
        "rendered",
        tentativa=2,
        max_tentativas=4,
        batimento_em=_BATIMENTO_EM,
        recibo=_recibo_interno(trabalho_id),
        retoma_de="t-original",
        retomada_n=1,
    )


def _trabalho_executando() -> SimpleNamespace:
    falha = {
        "codigo": "tentativa_anterior",
        "permanente": False,
        "detalhes": ["timeout", 2],
    }
    return _trabalho_contrato(
        "t-running",
        "running",
        operario="worker-live",
        lease_ate=_LEASE_ATE,
        batimento_em=_BATIMENTO_EM,
        vivo=True,
        falha=falha,
    )


def _trabalho_falho(
    trabalho_id: str,
    *,
    retoma_de: str | None = None,
    retomada_n: int = 0,
) -> SimpleNamespace:
    falha = {
        "codigo": "motor_desconhecido",
        "mensagem": "Motor não registrado.",
        "permanente": True,
        "tentativas": [1, 2],
    }
    return _trabalho_contrato(
        trabalho_id,
        "failed",
        tentativa=2,
        falha=falha,
        retoma_de=retoma_de,
        retomada_n=retomada_n,
    )


def _trabalho_cancelado() -> SimpleNamespace:
    return _trabalho_contrato(
        "t-cancelled",
        "cancelled",
        cancelado_por="usuario-de-teste",
        cancelado_motivo="briefing substituído",
    )


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

_ARQUIVO_CONTEUDO = b"\x89PNG\r\n\x1a\nVOLC-contrato-binario\x00\xff"

_GOLDEN_MOTORES = _GoldenHTTP(
    status=200,
    headers=(("content-type", "application/json"), ("content-length", "131")),
    absent_headers=("x-criativo-idempotente",),
    body=(
        '{"motores":[{"slug":"tipografico-local","versao":"1.2.3",'
        '"versoes":{"fonte_sha256":"abc123","adaptador":"2"},'
        '"produz":["imagem"]}]}'
    ).encode("utf-8"),
)

_GOLDEN_CRIACAO_INICIAL = _GoldenHTTP(
    status=201,
    headers=(("content-type", "application/json"), ("content-length", "1692")),
    absent_headers=("x-criativo-idempotente",),
    body=b'{"id":"t-criado","estado":"rendered","tentativa":2,"maxTentativas":4,"operario":null,"leaseAte":null,"batimentoEm":"2026-08-29T16:04:00+00:00","vivo":false,"falha":null,"recibo":{"trabalhoId":"t-criado","produzidoPor":"worker-\xce\xb1","motorSlug":"tipografico-local","motorVersao":"1.2.3","seed":7,"versoes":{"adaptador":"2","fonte_sha256":"abc123"},"parametros":{"hash":"sha256:667ae94c6cb5cd229fc7e15b44947837cef639bb54984b2f8402bdc56addb12b","campos":{},"retidos":{"apoio":"retido_texto_livre","escala":"retido_nao_allowlisted","rascunho":"retido_nao_allowlisted","titulo":"retido_texto_livre"}},"artefatos":[{"slot":"1x1","mime":"image/png","bytes":123,"sha256":"def456","largura":1080,"altura":1080,"duracaoS":null,"video":null,"enquadramento":null},{"slot":"video-9x16","mime":"video/mp4","bytes":456,"sha256":"ghi789","largura":1080,"altura":1920,"duracaoS":2.5,"video":null,"enquadramento":null}],"validacoes":[{"gate":"dimensao","resultado":"PASS","detalhe":{"esperado":[1080,1080],"medido":[1080,1080]},"bloqueante":true},{"gate":"audio","resultado":"SKIPPED","detalhe":null,"bloqueante":false}],"audio":{"codec":"aac","canais":2,"normalizado":true},"iniciadoEm":"2026-08-29T16:00:00+00:00","terminadoEm":"2026-08-29T16:00:02+00:00","custoEstimadoUsd":0.75,"custoRealUsd":0.625,"assinaturaDeterminista":"sig-123","procedencia":null,"insumo":null,"hashesDeEntrada":null,"tentativa":null,"custo":null,"duracaoDoTrabalhoS":null,"storage":null,"destinos":null,"aprovacao":null,"audioAusentePorque":null,"videoAusentePorque":null},"retomaDe":"t-original","retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":false,"podeCancelar":false}',
)

_GOLDEN_CRIACAO_REPLAY = _GoldenHTTP(
    status=200,
    headers=(
        ("content-type", "application/json"),
        ("content-length", "1692"),
        ("x-criativo-idempotente", "replay"),
    ),
    body=b'{"id":"t-replay","estado":"rendered","tentativa":2,"maxTentativas":4,"operario":null,"leaseAte":null,"batimentoEm":"2026-08-29T16:04:00+00:00","vivo":false,"falha":null,"recibo":{"trabalhoId":"t-replay","produzidoPor":"worker-\xce\xb1","motorSlug":"tipografico-local","motorVersao":"1.2.3","seed":7,"versoes":{"adaptador":"2","fonte_sha256":"abc123"},"parametros":{"hash":"sha256:667ae94c6cb5cd229fc7e15b44947837cef639bb54984b2f8402bdc56addb12b","campos":{},"retidos":{"apoio":"retido_texto_livre","escala":"retido_nao_allowlisted","rascunho":"retido_nao_allowlisted","titulo":"retido_texto_livre"}},"artefatos":[{"slot":"1x1","mime":"image/png","bytes":123,"sha256":"def456","largura":1080,"altura":1080,"duracaoS":null,"video":null,"enquadramento":null},{"slot":"video-9x16","mime":"video/mp4","bytes":456,"sha256":"ghi789","largura":1080,"altura":1920,"duracaoS":2.5,"video":null,"enquadramento":null}],"validacoes":[{"gate":"dimensao","resultado":"PASS","detalhe":{"esperado":[1080,1080],"medido":[1080,1080]},"bloqueante":true},{"gate":"audio","resultado":"SKIPPED","detalhe":null,"bloqueante":false}],"audio":{"codec":"aac","canais":2,"normalizado":true},"iniciadoEm":"2026-08-29T16:00:00+00:00","terminadoEm":"2026-08-29T16:00:02+00:00","custoEstimadoUsd":0.75,"custoRealUsd":0.625,"assinaturaDeterminista":"sig-123","procedencia":null,"insumo":null,"hashesDeEntrada":null,"tentativa":null,"custo":null,"duracaoDoTrabalhoS":null,"storage":null,"destinos":null,"aprovacao":null,"audioAusentePorque":null,"videoAusentePorque":null},"retomaDe":"t-original","retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":false,"podeCancelar":false}',
)

_GOLDEN_LISTAGEM = _GoldenHTTP(
    status=200,
    headers=(("content-type", "application/json"), ("content-length", "2150")),
    absent_headers=("x-criativo-idempotente",),
    body=b'{"trabalhos":[{"id":"t-running","estado":"running","tentativa":1,"maxTentativas":3,"operario":"worker-live","leaseAte":"2026-08-29T16:05:00+00:00","batimentoEm":"2026-08-29T16:04:00+00:00","vivo":true,"falha":{"codigo":"tentativa_anterior","permanente":false,"detalhes":["timeout",2]},"recibo":null,"retomaDe":null,"retomadaN":0,"canceladoPor":null,"canceladoMotivo":null,"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":false,"podeCancelar":true},{"id":"t-rendered","estado":"rendered","tentativa":2,"maxTentativas":4,"operario":null,"leaseAte":null,"batimentoEm":"2026-08-29T16:04:00+00:00","vivo":false,"falha":null,"recibo":{"trabalhoId":"t-rendered","produzidoPor":"worker-\xce\xb1","motorSlug":"tipografico-local","motorVersao":"1.2.3","seed":7,"versoes":{"adaptador":"2","fonte_sha256":"abc123"},"parametros":{"hash":"sha256:667ae94c6cb5cd229fc7e15b44947837cef639bb54984b2f8402bdc56addb12b","campos":{},"retidos":{"apoio":"retido_texto_livre","escala":"retido_nao_allowlisted","rascunho":"retido_nao_allowlisted","titulo":"retido_texto_livre"}},"artefatos":[{"slot":"1x1","mime":"image/png","bytes":123,"sha256":"def456","largura":1080,"altura":1080,"duracaoS":null,"video":null,"enquadramento":null},{"slot":"video-9x16","mime":"video/mp4","bytes":456,"sha256":"ghi789","largura":1080,"altura":1920,"duracaoS":2.5,"video":null,"enquadramento":null}],"validacoes":[{"gate":"dimensao","resultado":"PASS","detalhe":{"esperado":[1080,1080],"medido":[1080,1080]},"bloqueante":true},{"gate":"audio","resultado":"SKIPPED","detalhe":null,"bloqueante":false}],"audio":{"codec":"aac","canais":2,"normalizado":true},"iniciadoEm":"2026-08-29T16:00:00+00:00","terminadoEm":"2026-08-29T16:00:02+00:00","custoEstimadoUsd":0.75,"custoRealUsd":0.625,"assinaturaDeterminista":"sig-123","procedencia":null,"insumo":null,"hashesDeEntrada":null,"tentativa":null,"custo":null,"duracaoDoTrabalhoS":null,"storage":null,"destinos":null,"aprovacao":null,"audioAusentePorque":null,"videoAusentePorque":null},"retomaDe":"t-original","retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":false,"podeCancelar":false}]}',
)

_GOLDEN_LEITURA = _GoldenHTTP(
    status=200,
    headers=(("content-type", "application/json"), ("content-length", "1688")),
    absent_headers=("x-criativo-idempotente",),
    body=b'{"id":"t-rico","estado":"rendered","tentativa":2,"maxTentativas":4,"operario":null,"leaseAte":null,"batimentoEm":"2026-08-29T16:04:00+00:00","vivo":false,"falha":null,"recibo":{"trabalhoId":"t-rico","produzidoPor":"worker-\xce\xb1","motorSlug":"tipografico-local","motorVersao":"1.2.3","seed":7,"versoes":{"adaptador":"2","fonte_sha256":"abc123"},"parametros":{"hash":"sha256:667ae94c6cb5cd229fc7e15b44947837cef639bb54984b2f8402bdc56addb12b","campos":{},"retidos":{"apoio":"retido_texto_livre","escala":"retido_nao_allowlisted","rascunho":"retido_nao_allowlisted","titulo":"retido_texto_livre"}},"artefatos":[{"slot":"1x1","mime":"image/png","bytes":123,"sha256":"def456","largura":1080,"altura":1080,"duracaoS":null,"video":null,"enquadramento":null},{"slot":"video-9x16","mime":"video/mp4","bytes":456,"sha256":"ghi789","largura":1080,"altura":1920,"duracaoS":2.5,"video":null,"enquadramento":null}],"validacoes":[{"gate":"dimensao","resultado":"PASS","detalhe":{"esperado":[1080,1080],"medido":[1080,1080]},"bloqueante":true},{"gate":"audio","resultado":"SKIPPED","detalhe":null,"bloqueante":false}],"audio":{"codec":"aac","canais":2,"normalizado":true},"iniciadoEm":"2026-08-29T16:00:00+00:00","terminadoEm":"2026-08-29T16:00:02+00:00","custoEstimadoUsd":0.75,"custoRealUsd":0.625,"assinaturaDeterminista":"sig-123","procedencia":null,"insumo":null,"hashesDeEntrada":null,"tentativa":null,"custo":null,"duracaoDoTrabalhoS":null,"storage":null,"destinos":null,"aprovacao":null,"audioAusentePorque":null,"videoAusentePorque":null},"retomaDe":"t-original","retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":false,"podeCancelar":false}',
)

_GOLDEN_CANCELAMENTO = _GoldenHTTP(
    status=200,
    headers=(("content-type", "application/json"), ("content-length", "349")),
    absent_headers=("x-criativo-idempotente",),
    body=(
        '{"id":"t-cancelled","estado":"cancelled","tentativa":1,'
        '"maxTentativas":3,"operario":null,"leaseAte":null,'
        '"batimentoEm":null,"vivo":false,"falha":null,"recibo":null,'
        '"retomaDe":null,"retomadaN":0,"canceladoPor":"usuario-de-teste",'
        '"canceladoMotivo":"briefing substituído",'
        '"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":true,'
        '"podeCancelar":false}'
    ).encode("utf-8"),
)

_GOLDEN_RETOMADA_INICIAL = _GoldenHTTP(
    status=201,
    headers=(("content-type", "application/json"), ("content-length", "420")),
    absent_headers=("x-criativo-idempotente",),
    body=(
        '{"id":"t-retomado","estado":"failed","tentativa":2,'
        '"maxTentativas":3,"operario":null,"leaseAte":null,'
        '"batimentoEm":null,"vivo":false,'
        '"falha":{"codigo":"motor_desconhecido",'
        '"mensagem":"Motor não registrado.","permanente":true,'
        '"tentativas":[1,2]},"recibo":null,"retomaDe":"t-original",'
        '"retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,'
        '"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":true,'
        '"podeCancelar":false}'
    ).encode("utf-8"),
)

_GOLDEN_RETOMADA_REPLAY = _GoldenHTTP(
    status=200,
    headers=(
        ("content-type", "application/json"),
        ("content-length", "427"),
        ("x-criativo-idempotente", "replay"),
    ),
    body=(
        '{"id":"t-retomado-replay","estado":"failed","tentativa":2,'
        '"maxTentativas":3,"operario":null,"leaseAte":null,'
        '"batimentoEm":null,"vivo":false,'
        '"falha":{"codigo":"motor_desconhecido",'
        '"mensagem":"Motor não registrado.","permanente":true,'
        '"tentativas":[1,2]},"recibo":null,"retomaDe":"t-original",'
        '"retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,'
        '"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":true,'
        '"podeCancelar":false}'
    ).encode("utf-8"),
)

_GOLDEN_LINHAGEM = _GoldenHTTP(
    status=200,
    headers=(("content-type", "application/json"), ("content-length", "857")),
    absent_headers=("x-criativo-idempotente",),
    body=(
        '{"linhagem":[{"id":"t-original","estado":"failed","tentativa":2,'
        '"maxTentativas":3,"operario":null,"leaseAte":null,'
        '"batimentoEm":null,"vivo":false,'
        '"falha":{"codigo":"motor_desconhecido",'
        '"mensagem":"Motor não registrado.","permanente":true,'
        '"tentativas":[1,2]},"recibo":null,"retomaDe":null,'
        '"retomadaN":0,"canceladoPor":null,"canceladoMotivo":null,'
        '"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":true,'
        '"podeCancelar":false},{"id":"t-retomado-linhagem",'
        '"estado":"failed","tentativa":2,"maxTentativas":3,'
        '"operario":null,"leaseAte":null,"batimentoEm":null,"vivo":false,'
        '"falha":{"codigo":"motor_desconhecido",'
        '"mensagem":"Motor não registrado.","permanente":true,'
        '"tentativas":[1,2]},"recibo":null,"retomaDe":"t-original",'
        '"retomadaN":1,"canceladoPor":null,"canceladoMotivo":null,'
        '"criadoEm":"2026-08-29T15:59:00+00:00","podeRetomar":true,'
        '"podeCancelar":false}]}'
    ).encode("utf-8"),
)

_GOLDEN_ARQUIVO = _GoldenHTTP(
    status=200,
    headers=(("content-type", "image/png"), ("content-length", "31")),
    absent_headers=("content-disposition", "x-criativo-idempotente"),
    body=_ARQUIVO_CONTEUDO,
    json_tipado=False,
)


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



def _copia_para_dependencia(valor: Any) -> Any:
    return copy.deepcopy(valor)


def _resposta_motores(monkeypatch, motores: list[dict[str, Any]] | None = None):
    fonte = _motores_disponiveis_fixture() if motores is None else motores
    monkeypatch.setattr(
        criativos_execucao.bancada_servico,
        "motores_disponiveis",
        lambda: _copia_para_dependencia(fonte),
    )
    return _cliente_contrato(monkeypatch, Mock()).get(
        "/api/criativos/bancada/motores"
    )


def _resposta_criacao_inicial(
    monkeypatch, final: SimpleNamespace | None = None
):
    deposito = Mock()
    despachante = Mock()
    deposito.enfileirar.return_value = (
        _copia_para_dependencia(_trabalho_contrato("t-criado", "queued")),
        True,
    )
    deposito.por_id.return_value = _copia_para_dependencia(
        final if final is not None else _trabalho_renderizado("t-criado")
    )
    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos", json=_PEDIDO
    )
    return resposta, deposito, despachante


def _resposta_criacao_replay(monkeypatch, trabalho: SimpleNamespace | None = None):
    deposito = Mock()
    despachante = Mock()
    deposito.enfileirar.return_value = (
        _copia_para_dependencia(
            trabalho if trabalho is not None else _trabalho_renderizado("t-replay")
        ),
        False,
    )
    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos", json=_PEDIDO
    )
    return resposta, deposito, despachante


def _resposta_listagem(
    monkeypatch, trabalhos: list[SimpleNamespace] | None = None
):
    deposito = Mock()
    fonte = (
        [_trabalho_executando(), _trabalho_renderizado("t-rendered")]
        if trabalhos is None
        else trabalhos
    )
    deposito.listar.return_value = _copia_para_dependencia(fonte)
    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/trabalhos?limite=7"
    )
    return resposta, deposito


def _resposta_leitura(monkeypatch, trabalho: SimpleNamespace | None = None):
    deposito = Mock()
    deposito.por_id.return_value = _copia_para_dependencia(
        trabalho if trabalho is not None else _trabalho_renderizado("t-rico")
    )
    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/trabalhos/t-rico"
    )
    return resposta, deposito


def _resposta_cancelamento(monkeypatch, trabalho: SimpleNamespace | None = None):
    deposito = Mock()
    deposito.cancelar.return_value = _copia_para_dependencia(
        trabalho if trabalho is not None else _trabalho_cancelado()
    )
    resposta = _cliente_contrato(monkeypatch, deposito).post(
        "/api/criativos/bancada/trabalhos/t-cancelled/cancelar",
        json={"motivo": "briefing substituído"},
    )
    return resposta, deposito


def _resposta_retomada_inicial(
    monkeypatch, final: SimpleNamespace | None = None
):
    deposito = Mock()
    despachante = Mock()
    antes = _trabalho_contrato(
        "t-retomado",
        "queued",
        retoma_de="t-original",
        retomada_n=1,
    )
    deposito.retomar.return_value = (_copia_para_dependencia(antes), True)
    deposito.por_id.return_value = _copia_para_dependencia(
        final
        if final is not None
        else _trabalho_falho("t-retomado", retoma_de="t-original", retomada_n=1)
    )
    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos/t-original/retomar"
    )
    return resposta, deposito, despachante


def _resposta_retomada_replay(monkeypatch, trabalho: SimpleNamespace | None = None):
    deposito = Mock()
    despachante = Mock()
    deposito.retomar.return_value = (
        _copia_para_dependencia(
            trabalho
            if trabalho is not None
            else _trabalho_falho(
                "t-retomado-replay", retoma_de="t-original", retomada_n=1
            )
        ),
        False,
    )
    resposta = _cliente_contrato(monkeypatch, deposito, despachante).post(
        "/api/criativos/bancada/trabalhos/t-original/retomar"
    )
    return resposta, deposito, despachante


def _resposta_linhagem(
    monkeypatch, cadeia: list[SimpleNamespace] | None = None
):
    deposito = Mock()
    fonte = (
        [
            _trabalho_falho("t-original"),
            _trabalho_falho(
                "t-retomado-linhagem", retoma_de="t-original", retomada_n=1
            ),
        ]
        if cadeia is None
        else cadeia
    )
    deposito.linhagem.return_value = _copia_para_dependencia(fonte)
    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/trabalhos/t-retomado-linhagem/linhagem"
    )
    return resposta, deposito


def _resposta_arquivo(
    monkeypatch,
    tmp_path,
    *,
    conteudo: bytes = _ARQUIVO_CONTEUDO,
    mime: str = "image/png",
    sufixo: str = "base",
):
    raiz = tmp_path / f"bancada-{sufixo}"
    arquivo = raiz / "trabalhos" / "t-arquivo" / "1" / "peca.png"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(conteudo)
    trabalho = _trabalho_contrato(
        "t-arquivo",
        "rendered",
        recibo={
            "artefatos": [
                {
                    "slot": "1x1",
                    "caminho": str(arquivo),
                    "mime": mime,
                }
            ]
        },
    )
    deposito = Mock()
    deposito.por_id.return_value = _copia_para_dependencia(trabalho)
    monkeypatch.setattr(
        criativos_execucao.bancada_servico,
        "raiz_da_bancada",
        lambda: raiz,
    )
    resposta = _cliente_contrato(monkeypatch, deposito).get(
        "/api/criativos/bancada/arquivo/t-arquivo/1x1"
    )
    return resposta, deposito


def _mutar_trabalho_dto(monkeypatch, mutar) -> None:
    original = criativos_execucao._trabalho_dto

    def mutante(trabalho):
        dto = original(trabalho)
        mutar(dto)
        return dto

    monkeypatch.setattr(criativos_execucao, "_trabalho_dto", mutante)


def _mutar_artefato_dto(monkeypatch, mutar) -> None:
    original = criativos_execucao._artefato_dto

    def mutante(artefato):
        dto = original(artefato)
        mutar(dto, artefato)
        return dto

    monkeypatch.setattr(criativos_execucao, "_artefato_dto", mutante)


def _mutar_bancada_ler_cache_publico(monkeypatch) -> None:
    original = criativos_execucao.bancada_ler

    async def mutante(
        trabalho_id: str,
        resposta: fastapi.Response,
        identidade: Any = fastapi.Depends(exigir_usuario),
    ):
        resposta.headers["Cache-Control"] = "public, max-age=3600"
        return await original(trabalho_id, identidade)

    monkeypatch.setattr(criativos_execucao, "bancada_ler", mutante)
    for rota in criativos_execucao.router.routes:
        if isinstance(rota, APIRoute) and rota.name == "bancada_ler":
            monkeypatch.setattr(rota, "endpoint", mutante)
            return
    raise AssertionError("rota bancada_ler não encontrada para mutação")


def test_goldens_http_serializados_sao_imutaveis_e_autossuficientes():
    goldens = (
        _GOLDEN_MOTORES,
        _GOLDEN_CRIACAO_INICIAL,
        _GOLDEN_CRIACAO_REPLAY,
        _GOLDEN_LISTAGEM,
        _GOLDEN_LEITURA,
        _GOLDEN_CANCELAMENTO,
        _GOLDEN_RETOMADA_INICIAL,
        _GOLDEN_RETOMADA_REPLAY,
        _GOLDEN_LINHAGEM,
        _GOLDEN_ARQUIVO,
    )
    for golden in goldens:
        assert dict(golden.headers)["content-length"] == str(len(golden.body))
        if not golden.json_tipado:
            continue
        primeiro = golden.json()
        segundo = golden.json()
        assert primeiro == segundo
        primeiro.clear()
        assert golden.json() == segundo


def test_rota_motores_equivale_ao_golden_serializado(monkeypatch):
    resposta = _resposta_motores(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_MOTORES)


def test_rota_criacao_inicial_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito, despachante = _resposta_criacao_inicial(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_CRIACAO_INICIAL)
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


def test_rota_criacao_replay_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito, despachante = _resposta_criacao_replay(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_CRIACAO_REPLAY)
    despachante.despachar.assert_not_called()
    deposito.por_id.assert_not_called()


def test_rota_listagem_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito = _resposta_listagem(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_LISTAGEM)
    deposito.listar.assert_called_once_with(
        tenant_id="usuario-de-teste", limite=7
    )


def test_rota_leitura_rica_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito = _resposta_leitura(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_LEITURA)
    deposito.por_id.assert_called_once_with(
        "t-rico", tenant_id="usuario-de-teste"
    )
    assert "caminho" not in resposta.text


def test_rota_cancelamento_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito = _resposta_cancelamento(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_CANCELAMENTO)
    deposito.cancelar.assert_called_once_with(
        "t-cancelled",
        tenant_id="usuario-de-teste",
        por="usuario-de-teste",
        motivo="briefing substituído",
    )


def test_rota_retomada_inicial_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito, despachante = _resposta_retomada_inicial(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_RETOMADA_INICIAL)
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
    falha no ponto da leitura se criação ou retomada voltarem a usar o UUID
    como se fosse autorização.
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


def test_rota_retomada_replay_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito, despachante = _resposta_retomada_replay(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_RETOMADA_REPLAY)
    despachante.despachar.assert_not_called()
    deposito.por_id.assert_not_called()


def test_rota_linhagem_equivale_ao_golden_serializado(monkeypatch):
    resposta, deposito = _resposta_linhagem(monkeypatch)
    _assert_resposta_golden(resposta, _GOLDEN_LINHAGEM)
    deposito.linhagem.assert_called_once_with(
        "t-retomado-linhagem", tenant_id="usuario-de-teste"
    )


def test_rota_arquivo_equivale_ao_golden_serializado(monkeypatch, tmp_path):
    resposta, deposito = _resposta_arquivo(monkeypatch, tmp_path)
    _assert_resposta_golden(resposta, _GOLDEN_ARQUIVO)
    deposito.por_id.assert_called_once_with(
        "t-arquivo", tenant_id="usuario-de-teste"
    )


def test_fronteiras_futuras_sao_importaveis_e_vazias_de_comportamento():
    from app.criativo import deposito, destino, worker

    for modulo in (deposito, worker, destino):
        publicos = {nome for nome in vars(modulo) if not nome.startswith("__")}
        assert publicos == set()


def test_mutante_real_motores_slug_nao_altera_golden_e_morre(monkeypatch):
    motores = _motores_disponiveis_fixture()
    esperado_antes = _GOLDEN_MOTORES.json()
    assert esperado_antes["motores"] is not motores
    assert esperado_antes["motores"][0] is not motores[0]

    motores[0]["slug"] = "motor-mutante"
    assert _GOLDEN_MOTORES.json()["motores"][0]["slug"] == "tipografico-local"

    resposta_mutante = _resposta_motores(monkeypatch, motores=motores)
    assert resposta_mutante.json()["motores"][0]["slug"] == "motor-mutante"
    with pytest.raises(AssertionError):
        _assert_resposta_golden(resposta_mutante, _GOLDEN_MOTORES)

    resposta_restaurada = _resposta_motores(monkeypatch)
    _assert_resposta_golden(resposta_restaurada, _GOLDEN_MOTORES)


def test_mutante_real_criacao_tentativa_bool_morre_e_restaura(monkeypatch):
    _assert_resposta_golden(
        _resposta_criacao_inicial(monkeypatch)[0], _GOLDEN_CRIACAO_INICIAL
    )

    with monkeypatch.context() as m:
        _mutar_trabalho_dto(
            m,
            lambda corpo: corpo.__setitem__("tentativa", True)
            if corpo["id"] == "t-criado"
            else None,
        )
        resposta_mutante = _resposta_criacao_inicial(m)[0]
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_CRIACAO_INICIAL)

    _assert_resposta_golden(
        _resposta_criacao_inicial(monkeypatch)[0], _GOLDEN_CRIACAO_INICIAL
    )


def test_mutante_real_listagem_vivo_false_morre_e_restaura(monkeypatch):
    _assert_resposta_golden(_resposta_listagem(monkeypatch)[0], _GOLDEN_LISTAGEM)

    with monkeypatch.context() as m:
        _mutar_trabalho_dto(
            m,
            lambda corpo: corpo.__setitem__("vivo", False)
            if corpo["id"] == "t-running"
            else None,
        )
        resposta_mutante = _resposta_listagem(m)[0]
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_LISTAGEM)

    _assert_resposta_golden(_resposta_listagem(monkeypatch)[0], _GOLDEN_LISTAGEM)


def test_mutante_real_leitura_vaza_caminho_morre_e_restaura(monkeypatch):
    _assert_resposta_golden(_resposta_leitura(monkeypatch)[0], _GOLDEN_LEITURA)

    with monkeypatch.context() as m:
        _mutar_artefato_dto(
            m,
            lambda dto, artefato: dto.__setitem__("caminho", artefato.get("caminho")),
        )
        resposta_mutante = _resposta_leitura(m)[0]
        assert "caminho" in resposta_mutante.text
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_LEITURA)

    _assert_resposta_golden(_resposta_leitura(monkeypatch)[0], _GOLDEN_LEITURA)


def test_mutante_real_leitura_cache_publico_em_header_extra_morre_e_restaura(
    monkeypatch,
):
    _assert_resposta_golden(_resposta_leitura(monkeypatch)[0], _GOLDEN_LEITURA)

    with monkeypatch.context() as m:
        _mutar_bancada_ler_cache_publico(m)
        resposta_mutante = _resposta_leitura(m)[0]
        assert resposta_mutante.headers["cache-control"] == "public, max-age=3600"
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_LEITURA)

    _assert_resposta_golden(_resposta_leitura(monkeypatch)[0], _GOLDEN_LEITURA)


def test_mutante_real_cancelamento_motivo_alterado_morre_e_restaura(monkeypatch):
    _assert_resposta_golden(
        _resposta_cancelamento(monkeypatch)[0], _GOLDEN_CANCELAMENTO
    )

    with monkeypatch.context() as m:
        _mutar_trabalho_dto(
            m,
            lambda corpo: corpo.__setitem__("canceladoMotivo", "outro motivo")
            if corpo["id"] == "t-cancelled"
            else None,
        )
        resposta_mutante = _resposta_cancelamento(m)[0]
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_CANCELAMENTO)

    _assert_resposta_golden(
        _resposta_cancelamento(monkeypatch)[0], _GOLDEN_CANCELAMENTO
    )


def test_mutante_real_retomada_linhagem_trocada_morre_e_restaura(monkeypatch):
    _assert_resposta_golden(
        _resposta_retomada_inicial(monkeypatch)[0], _GOLDEN_RETOMADA_INICIAL
    )

    with monkeypatch.context() as m:
        _mutar_trabalho_dto(
            m,
            lambda corpo: corpo.__setitem__("retomaDe", "t-outro")
            if corpo["id"] == "t-retomado"
            else None,
        )
        resposta_mutante = _resposta_retomada_inicial(m)[0]
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_RETOMADA_INICIAL)

    _assert_resposta_golden(
        _resposta_retomada_inicial(monkeypatch)[0], _GOLDEN_RETOMADA_INICIAL
    )


def test_mutante_real_linhagem_remove_estado_morre_e_restaura(monkeypatch):
    _assert_resposta_golden(_resposta_linhagem(monkeypatch)[0], _GOLDEN_LINHAGEM)

    with monkeypatch.context() as m:
        _mutar_trabalho_dto(
            m,
            lambda corpo: corpo.pop("estado")
            if corpo["id"] == "t-retomado-linhagem"
            else None,
        )
        resposta_mutante = _resposta_linhagem(m)[0]
        with pytest.raises(AssertionError):
            _assert_resposta_golden(resposta_mutante, _GOLDEN_LINHAGEM)

    _assert_resposta_golden(_resposta_linhagem(monkeypatch)[0], _GOLDEN_LINHAGEM)


def test_mutante_real_arquivo_bytes_alterados_morre_e_restaura(
    monkeypatch, tmp_path
):
    _assert_resposta_golden(
        _resposta_arquivo(monkeypatch, tmp_path, sufixo="base")[0],
        _GOLDEN_ARQUIVO,
    )

    resposta_mutante = _resposta_arquivo(
        monkeypatch,
        tmp_path,
        conteudo=_ARQUIVO_CONTEUDO + b"x",
        sufixo="mutante",
    )[0]
    with pytest.raises(AssertionError):
        _assert_resposta_golden(resposta_mutante, _GOLDEN_ARQUIVO)

    _assert_resposta_golden(
        _resposta_arquivo(monkeypatch, tmp_path, sufixo="restaurado")[0],
        _GOLDEN_ARQUIVO,
    )
