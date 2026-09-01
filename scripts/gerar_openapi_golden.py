#!/usr/bin/env python3
"""Gera e confere o golden OpenAPI da bancada criativa.

## Por que este arquivo existe

O contrato HTTP das oito rotas de ``/api/criativos/bancada`` ja estava congelado
antes desta rodada — mas EMBUTIDO, em zlib+base64, dentro do proprio teste que o
verifica (``backend/tests/test_criativo_rotas_equivalentes.py``). O comentario de
la confessa a razao: "Ele fica embutido porque esta rodada nao possui ownership
para criar outro arquivo".

⚠️ Um golden que so existe dentro do teste que o confere nao e reproduzivel por
terceiro. Ninguem consegue regenera-lo, ninguem consegue le-lo em code review, e
o diff de uma mudanca de contrato aparece como uma unica linha base64 trocada.
"Congelado" e "auditavel" viraram a mesma palavra sem serem a mesma coisa.

Aqui o mesmo fragmento vira arquivo versionado, com gerador declarado e comando
de regeneracao. O `sha256` canonico do fragmento e o MESMO do embutido —
``28bb086dcf5ca5f4667b9c0c4aecb1778783c66c288bc060f5cb674981b020e8`` — e
``backend/tests/test_openapi_golden.py`` confere essa igualdade, para que extrair
o golden nao possa ter, de quebra, mudado o contrato.

## Reprodutibilidade em checkout limpo

O documento vem de ``app.main:app.openapi()``. Antes de importar a aplicacao, o
script desliga a leitura de arquivos ``.env`` e apaga as variaveis VOLC do
processo: sem isso o resultado dependeria da maquina do operador.

⚠️ E ele DESFAZ tudo ao sair. A primeira versao deste script mutava
``Settings.model_config`` e ``os.environ`` sem restaurar; rodando dentro do
pytest isso vazava para os testes seguintes e quebrava
``backend/tests/test_config_env_server.py``, que confere justamente qual
``env_file`` o FastAPI usa. Um gerador de golden nao pode reprovar um vizinho.

    python3 scripts/gerar_openapi_golden.py --check
    python3 scripts/gerar_openapi_golden.py --write
    python3 scripts/gerar_openapi_golden.py --stdout
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
GOLDEN = BACKEND / "tests" / "goldens" / "openapi-criativos-bancada.json"
ESCOPO = "/api/criativos/bancada"

#: sha256 do fragmento canonico ``{"paths", "components"}`` no commit-base
#: 9885459, o mesmo valor que ``OPENAPI_ANTES_SHA256`` guarda embutido em
#: ``backend/tests/test_criativo_rotas_equivalentes.py``. Ele mora aqui para que
#: quem regerar o golden a mao veja imediatamente se mudou o contrato.
SHA256_FRAGMENTO = "28bb086dcf5ca5f4667b9c0c4aecb1778783c66c288bc060f5cb674981b020e8"

_ENV_PREFIXOS_VOLC = (
    "CLICKUP_",
    "CRIATIVO_",
    "DATAFORSEO_",
    "GEMINI_",
    "GOOGLE_",
    "OPENAI_",
    "PAUTADOR_",
    "PERPLEXITY_",
    "SUPABASE_",
    "VOLC_",
)


def _json(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _json_canonico(valor: Any) -> bytes:
    """A MESMA serializacao de ``_json_canonico`` do teste de equivalencia.

    Compacta e ordenada: e sobre ela que o `sha256` do contrato e calculado, e
    duas formas diferentes de serializar dariam dois hashes para o mesmo
    contrato — que e exatamente o tipo de dupla verdade que este golden existe
    para nao ter.
    """
    return json.dumps(
        valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _ordenar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {chave: _ordenar(valor[chave]) for chave in sorted(valor)}
    if isinstance(valor, list):
        return [_ordenar(item) for item in valor]
    return valor


def _referencias(valor: Any) -> set[str]:
    achadas: set[str] = set()

    def visitar(no: Any) -> None:
        if isinstance(no, dict):
            ref = no.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                achadas.add(ref.rsplit("/", 1)[-1])
            for filho in no.values():
                visitar(filho)
        elif isinstance(no, list):
            for filho in no:
                visitar(filho)

    visitar(valor)
    return achadas


@contextlib.contextmanager
def _ambiente_sem_env_local():
    """Desliga `.env` e variaveis VOLC — e devolve tudo ao sair.

    ⚠️ O `finally` nao e zelo: e conserto de defeito medido. Sem ele, chamar
    `gerar_documento()` de dentro do pytest deixava `Settings.model_config` com
    `env_file=None` para o resto da sessao, e o teste que confere qual `.env` o
    FastAPI le passava a estourar `TypeError` num modulo que ninguem tocou.
    """
    for caminho in (str(ROOT), str(BACKEND)):
        if caminho not in sys.path:
            sys.path.insert(0, caminho)

    apagadas = {
        chave: os.environ[chave]
        for chave in list(os.environ)
        if chave.startswith(_ENV_PREFIXOS_VOLC)
    }
    for chave in apagadas:
        os.environ.pop(chave, None)

    from app import config as app_config  # noqa: PLC0415

    model_config_antes = dict(app_config.Settings.model_config)
    app_config.Settings.model_config = {**model_config_antes, "env_file": None}
    app_config.get_settings.cache_clear()
    try:
        yield
    finally:
        app_config.Settings.model_config = model_config_antes
        os.environ.update(apagadas)
        app_config.get_settings.cache_clear()


def gerar_documento() -> dict[str, Any]:
    """Extrai o OpenAPI real, limitado a fronteira da bancada."""
    with _ambiente_sem_env_local():
        from app.main import app  # noqa: PLC0415

        # ⚠️ FastAPI memoriza `openapi_schema` na primeira chamada. Sem zerar,
        # um processo que ja tenha servido `/openapi.json` devolveria o schema
        # de antes de qualquer mudanca — um golden que confere consigo mesmo.
        app.openapi_schema = None
        schema = app.openapi()
        app.openapi_schema = None

    paths = {
        path: operacoes
        for path, operacoes in schema.get("paths", {}).items()
        if path.startswith(ESCOPO)
    }
    refs = _referencias(paths)
    componentes: dict[str, Any] = {}
    pendentes = sorted(refs)
    while pendentes:
        nome = pendentes.pop(0)
        if nome in componentes:
            continue
        componente = schema.get("components", {}).get("schemas", {}).get(nome)
        if componente is None:
            continue
        componentes[nome] = componente
        for novo in sorted(_referencias(componente) - set(componentes) - set(pendentes)):
            pendentes.append(novo)

    documento = {
        "openapi": schema["openapi"],
        "info": {
            "title": schema["info"]["title"],
            "version": schema["info"]["version"],
        },
        "paths": paths,
        "components": {"schemas": componentes},
        "x-volc-scope": ESCOPO,
        "x-volc-source": "app.main:app.openapi()",
    }
    _normalizar_ruido_de_serializacao(documento)
    _conferir_limpeza(documento)
    return _ordenar(documento)


def fragmento(documento: dict[str, Any]) -> dict[str, Any]:
    """A parte do documento que o teste de equivalencia ja congelava.

    O golden versionado carrega mais coisa (`openapi`, `info`, procedencia); o
    contrato comparavel com o embutido de 9885459 e so `paths` + `components`.
    """
    return {"paths": documento["paths"], "components": documento["components"]}


def _normalizar_ruido_de_serializacao(documento: dict[str, Any]) -> None:
    """Remove ruido conhecido do schema padrao de erro do Pydantic/FastAPI.

    As rotas, parametros, status, schemas de produto e headers de auth continuam
    literais. A normalizacao fica confinada ao componente generico
    ``ValidationError`` porque FastAPI 0.135 acrescenta campos opcionais que
    FastAPI 0.115.6 nao emitia, sem alterar o contrato da bancada.
    """
    schemas = documento.get("components", {}).get("schemas", {})
    validacao = schemas.get("ValidationError")
    if not isinstance(validacao, dict):
        return
    propriedades = validacao.get("properties")
    if not isinstance(propriedades, dict):
        return
    for campo in ("ctx", "input"):
        propriedades.pop(campo, None)


def _conferir_limpeza(documento: dict[str, Any]) -> None:
    texto = json.dumps(documento, sort_keys=True, ensure_ascii=False)
    proibidos = {
        str(ROOT),
        str(Path.home()),
        socket.gethostname(),
        ".env",
        "generated_at",
        "hostname",
    }
    achados = sorted(valor for valor in proibidos if valor and valor in texto)
    if achados:
        raise RuntimeError(
            "OpenAPI contem dado local/volatil: "
            + ", ".join(repr(valor) for valor in achados)
        )


def diff_json(esperado: Any, atual: Any) -> str:
    resumo = "\n".join(f"- {p}" for p in _caminhos_divergentes(esperado, atual)[:20])
    diff = "\n".join(
        difflib.unified_diff(
            _json(esperado).splitlines(),
            _json(atual).splitlines(),
            fromfile="openapi-criativos-bancada.golden.json",
            tofile="openapi-atual.json",
            lineterm="",
        )
    )
    return f"nodos divergentes:\n{resumo}\n{diff}" if resumo else diff


def _caminhos_divergentes(esperado: Any, atual: Any, caminho: str = "$") -> list[str]:
    if type(esperado) is not type(atual):
        return [f"{caminho}: tipo {type(esperado).__name__} != {type(atual).__name__}"]
    if isinstance(esperado, dict):
        diffs: list[str] = []
        for chave in sorted(set(esperado) - set(atual)):
            diffs.append(f"{caminho}.{chave}: ausente no atual")
        for chave in sorted(set(atual) - set(esperado)):
            diffs.append(f"{caminho}.{chave}: extra no atual")
        for chave in sorted(set(esperado) & set(atual)):
            diffs.extend(
                _caminhos_divergentes(esperado[chave], atual[chave], f"{caminho}.{chave}")
            )
        return diffs
    if isinstance(esperado, list):
        diffs = []
        limite = min(len(esperado), len(atual))
        for indice in range(limite):
            diffs.extend(
                _caminhos_divergentes(
                    esperado[indice], atual[indice], f"{caminho}[{indice}]"
                )
            )
        if len(esperado) != len(atual):
            diffs.append(f"{caminho}: tamanho {len(esperado)} != {len(atual)}")
        return diffs
    if esperado != atual:
        return [f"{caminho}: {esperado!r} != {atual!r}"]
    return []


def _rotulo(caminho: Path) -> str:
    try:
        return str(caminho.relative_to(ROOT))
    except ValueError:
        return str(caminho)


def escrever(caminho: Path = GOLDEN) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(_json(gerar_documento()), encoding="utf-8")


def conferir(caminho: Path = GOLDEN) -> bool:
    if not caminho.is_file():
        print(
            f"Golden OpenAPI ausente: {_rotulo(caminho)}\n"
            "regenerar: python3 scripts/gerar_openapi_golden.py --write",
            file=sys.stderr,
        )
        return False
    esperado = json.loads(caminho.read_text(encoding="utf-8"))
    atual = gerar_documento()
    if esperado == atual:
        import hashlib  # noqa: PLC0415

        digest = hashlib.sha256(_json_canonico(fragmento(atual))).hexdigest()
        print(f"OpenAPI da bancada confere ({_rotulo(caminho)}, fragmento {digest}).")
        return True
    print(
        "Golden OpenAPI divergente.\n"
        f"arquivo: {_rotulo(caminho)}\n"
        "regenerar: python3 scripts/gerar_openapi_golden.py --write\n"
        f"{diff_json(esperado, atual)}",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        type=Path,
        default=GOLDEN,
        help="arquivo golden a escrever ou conferir",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="reescreve backend/tests/goldens/openapi-criativos-bancada.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="confere o golden versionado contra a aplicacao atual",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="imprime o documento gerado, sem tocar em arquivo",
    )
    args = parser.parse_args(argv)
    if args.write:
        escrever(args.golden)
        return 0
    if args.check:
        return 0 if conferir(args.golden) else 1
    print(_json(gerar_documento()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
