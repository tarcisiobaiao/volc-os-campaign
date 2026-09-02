"""O golden OpenAPI da bancada, reproduzivel em checkout limpo.

## O defeito que este modulo fecha

O contrato HTTP das oito rotas de ``/api/criativos/bancada`` ja estava congelado
antes desta rodada — mas dentro do proprio teste que o confere. O comentario de
``test_criativo_rotas_equivalentes.py`` diz a razao sem rodeio: "Ele fica
embutido porque esta rodada nao possui ownership para criar outro arquivo".

⚠️ Um golden embutido em zlib+base64 no teste que o verifica nao e reproduzivel
por terceiro: nao ha comando para regera-lo, nao ha arquivo para ler em revisao,
e uma mudanca de contrato aparece como uma linha base64 diferente. O congelamento
era real; a auditabilidade, nao.

## O que estas provas afirmam, e o que NAO afirmam

Afirmam: o arquivo versionado bate com a aplicacao real; ele bate byte a byte com
o golden que os aceites 1 e 2 ja tinham provado (mesmo `sha256`); o gerador nao
le `.env` nem carrega caminho, hostname ou timestamp; rodado duas vezes em
processo separado, com HOME e CWD temporarios, ele imprime os MESMOS bytes; e o
diagnostico aponta arquivo, comando de regeneracao e o no que mudou.

NAO afirmam nada sobre rotas fora de ``/api/criativos/bancada``. O escopo esta
declarado no proprio documento (`x-volc-scope`) para nao virar promessa larga.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "gerar_openapi_golden.py"
GOLDEN = RAIZ / "backend" / "tests" / "goldens" / "openapi-criativos-bancada.json"
DOC = RAIZ / "docs" / "architecture" / "OPENAPI-CRIATIVOS-BANCADA.md"

#: O mesmo valor que `OPENAPI_ANTES_SHA256` guarda embutido em
#: `test_criativo_rotas_equivalentes.py`, sobre a mesma serializacao canonica.
#: Ele esta repetido aqui de proposito: se extrair o golden para arquivo tivesse
#: mudado um byte do contrato, os dois numeros divergiriam e esta prova cairia.
SHA256_FRAGMENTO = "28bb086dcf5ca5f4667b9c0c4aecb1778783c66c288bc060f5cb674981b020e8"

METODOS_HTTP = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


def _env_file_original():
    """O `env_file` de `Settings` ANTES de qualquer teste deste modulo rodar."""
    from app.config import Settings

    return Settings.model_config.get("env_file")


#: Retrato tirado no import, com o `model_config` ainda intacto. Vide
#: `test_o_gerador_devolve_o_ambiente_que_encontrou`.
ENV_FILE_ORIGINAL = _env_file_original()


def _script() -> ModuleType:
    assert SCRIPT.is_file(), "faltou scripts/gerar_openapi_golden.py"
    spec = importlib.util.spec_from_file_location("gerar_openapi_golden", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _canonico(valor) -> bytes:
    return json.dumps(
        valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _ambiente_de_checkout_limpo(tmp_path: Path) -> dict[str, str]:
    """Um ambiente sem HOME, sem CWD e sem variavel do repositorio.

    ⚠️ `PYTHONWARNINGS=ignore` esta aqui por medida, nao por conveniencia:
    `app/routers/trafego.py` emite um `UserWarning` de shadowing de campo
    Pydantic no import, em stderr. Exigir stderr vazio faria esta prova falhar
    por um aviso de outro modulo — e o que ela mede e o STDOUT do gerador.
    """
    return {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join((str(RAIZ), str(RAIZ / "backend"))),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONWARNINGS": "ignore",
    }


def _rodar(tmp_path: Path, *args: str, cwd: Path | None = None):
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd or tmp_path),
        env=_ambiente_de_checkout_limpo(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. O golden versionado bate com a aplicacao — e com o golden ja provado
# ═══════════════════════════════════════════════════════════════════════════


def test_o_golden_versionado_bate_com_a_aplicacao_real():
    assert GOLDEN.is_file(), "faltou o golden OpenAPI versionado"
    modulo = _script()

    esperado = _golden()
    atual = modulo.gerar_documento()

    if atual != esperado:
        pytest.fail(
            "Golden OpenAPI divergente.\n"
            f"arquivo: {GOLDEN.relative_to(RAIZ)}\n"
            "comando: python3 scripts/gerar_openapi_golden.py --write\n"
            f"{modulo.diff_json(esperado, atual)}",
            pytrace=False,
        )


def test_o_arquivo_extraido_tem_o_MESMO_sha256_do_golden_ja_provado():
    """Extrair nao pode ter mudado o contrato.

    O fragmento `{paths, components}` do arquivo tem de dar exatamente o hash
    que os aceites 1 e 2 ja fecharam sobre o golden embutido do commit 9885459.
    Sem esta prova, "movemos o golden para um arquivo" e afirmacao de intencao.
    """
    modulo = _script()
    documento = _golden()

    digest = hashlib.sha256(_canonico(modulo.fragmento(documento))).hexdigest()

    assert digest == SHA256_FRAGMENTO, (
        "o fragmento do golden versionado nao e o mesmo contrato de 9885459"
    )
    assert modulo.SHA256_FRAGMENTO == SHA256_FRAGMENTO
    assert sorted(documento["paths"]) == [
        "/api/criativos/bancada/arquivo/{trabalho_id}/{slot}",
        "/api/criativos/bancada/motores",
        "/api/criativos/bancada/trabalhos",
        "/api/criativos/bancada/trabalhos/{trabalho_id}",
        "/api/criativos/bancada/trabalhos/{trabalho_id}/cancelar",
        "/api/criativos/bancada/trabalhos/{trabalho_id}/linhagem",
        "/api/criativos/bancada/trabalhos/{trabalho_id}/retomar",
    ]
    assert sorted(documento["components"]["schemas"]) == [
        "HTTPValidationError",
        "PedidoDeCancelamento",
        "PedidoDeProducao",
        "ValidationError",
    ]


def test_o_golden_declara_o_escopo_e_a_procedencia():
    """Um golden sem escopo declarado seria lido como se cobrisse o backend."""
    documento = _golden()
    assert documento["x-volc-scope"] == "/api/criativos/bancada"
    assert documento["x-volc-source"] == "app.main:app.openapi()"
    assert all(p.startswith("/api/criativos/bancada") for p in documento["paths"])


# ═══════════════════════════════════════════════════════════════════════════
# 2. Reprodutibilidade em checkout limpo (subprocesso, HOME e CWD temporarios)
# ═══════════════════════════════════════════════════════════════════════════


def test_o_gerador_e_deterministico_em_processo_limpo(tmp_path: Path):
    """Duas rodadas, processo novo, HOME e CWD temporarios: os MESMOS bytes.

    ⚠️ Em processo separado porque determinismo medido dentro do pytest mede o
    cache — `app.openapi_schema` ja aquecido, `Settings` ja montado. O que
    interessa e o que um terceiro obtem num checkout que nunca rodou nada.
    """
    primeira = _rodar(tmp_path, "--stdout")
    segunda = _rodar(tmp_path, "--stdout")

    assert primeira.returncode == 0, primeira.stdout + primeira.stderr
    assert segunda.returncode == 0, segunda.stdout + segunda.stderr
    assert primeira.stdout == segunda.stdout, "o gerador nao e deterministico"
    assert primeira.stdout, "o gerador nao imprimiu nada"
    assert json.loads(primeira.stdout) == _golden()


def test_a_saida_nao_carrega_caminho_da_maquina_hostname_nem_timestamp(tmp_path: Path):
    import socket

    saida = _rodar(tmp_path, "--stdout").stdout

    assert str(tmp_path) not in saida
    assert str(RAIZ) not in saida
    assert str(Path.home()) not in saida
    assert socket.gethostname() not in saida
    for volatil in ("generated_at", "generatedAt", "gerado_em", "hostname", ".env"):
        assert volatil not in saida


def test_check_em_checkout_limpo_confere_e_diz_o_que_conferiu(tmp_path: Path):
    resultado = _rodar(tmp_path, "--check", "--golden", str(GOLDEN))

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "OpenAPI da bancada confere" in resultado.stdout
    assert SHA256_FRAGMENTO in resultado.stdout


# ═══════════════════════════════════════════════════════════════════════════
# 3. Diagnostico util — o mutante tem de morrer com endereco
# ═══════════════════════════════════════════════════════════════════════════


def test_check_reprova_e_aponta_a_rota_quando_a_autenticacao_some(tmp_path: Path):
    """Mata o mutante "authorization sumiu de uma rota".

    Nao basta o `--check` devolver 1: um gate que so diz "divergente" obriga
    quem for consertar a comparar 17KB de JSON a mao. O diagnostico precisa
    nomear o arquivo, o comando de regeneracao e o no que mudou.
    """
    mutado = _golden()
    operacao = mutado["paths"]["/api/criativos/bancada/motores"]["get"]
    operacao["parameters"] = [
        p for p in operacao.get("parameters", []) if p.get("name") != "authorization"
    ]
    adulterado = tmp_path / "openapi-sem-auth.json"
    adulterado.write_text(
        json.dumps(mutado, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    resultado = _rodar(tmp_path, "--check", "--golden", str(adulterado))

    assert resultado.returncode == 1
    saida = resultado.stdout + resultado.stderr
    assert "openapi-sem-auth.json" in saida
    assert "python3 scripts/gerar_openapi_golden.py --write" in saida
    assert "/api/criativos/bancada/motores" in saida
    assert "authorization" in saida.lower()


def test_check_reprova_e_aponta_o_arquivo_quando_o_golden_some(tmp_path: Path):
    ausente = tmp_path / "nao-existe.json"

    resultado = _rodar(tmp_path, "--check", "--golden", str(ausente))

    assert resultado.returncode == 1
    saida = resultado.stdout + resultado.stderr
    assert "ausente" in saida
    assert "nao-existe.json" in saida
    assert "--write" in saida


def test_o_diff_nomeia_o_caminho_json_que_divergiu():
    modulo = _script()

    diff = modulo.diff_json(
        {"paths": {"/bancada": {"get": {"responses": {"200": {}}}}}},
        {"paths": {"/bancada": {"get": {"responses": {"201": {}}}}}},
    )

    assert "$.paths./bancada.get.responses.200: ausente no atual" in diff
    assert "$.paths./bancada.get.responses.201: extra no atual" in diff
    assert "--- openapi-criativos-bancada.golden.json" in diff
    assert "+++ openapi-atual.json" in diff


# ═══════════════════════════════════════════════════════════════════════════
# 4. O portao de identidade esta NO CONTRATO, e nao so no codigo
# ═══════════════════════════════════════════════════════════════════════════


def test_toda_rota_da_bancada_declara_authorization_no_openapi():
    """Enxerto da tentativa a2.

    O manifesto de `test_criativo_rotas_equivalentes.py` prova que
    `exigir_usuario` esta na lista de dependencias de cada rota. Esta prova
    pergunta outra coisa: o CLIENTE consegue saber disso lendo o contrato? Um
    portao que existe no servidor e nao aparece no OpenAPI e um portao que todo
    integrador descobre por 401.
    """
    documento = _golden()
    sem_header: list[str] = []
    for path, operacoes in documento["paths"].items():
        for metodo, operacao in operacoes.items():
            if metodo not in METODOS_HTTP:
                continue
            cabecalhos = [
                p for p in operacao.get("parameters", []) if p.get("in") == "header"
            ]
            if not any(
                p.get("name", "").lower() == "authorization" for p in cabecalhos
            ):
                sem_header.append(f"{metodo.upper()} {path}")

    assert sem_header == [], f"rota da bancada sem Authorization no OpenAPI: {sem_header}"


def test_as_oito_operacoes_do_manifesto_estao_no_golden():
    """O golden e o manifesto contam a mesma historia, ou um dos dois mente."""
    from tests.test_criativo_rotas_equivalentes import ROTAS_ANTES

    documento = _golden()
    no_golden = {
        (metodo.upper(), path)
        for path, operacoes in documento["paths"].items()
        for metodo in operacoes
        if metodo in METODOS_HTTP
    }

    assert no_golden == {(metodo, path) for metodo, path, _, _ in ROTAS_ANTES}
    assert len(no_golden) == 8


# ═══════════════════════════════════════════════════════════════════════════
# 5. Hermetismo do gerador
# ═══════════════════════════════════════════════════════════════════════════


def test_o_gerador_nao_le_env_local(monkeypatch):
    import builtins

    modulo = _script()
    abrir_real = builtins.open
    tentativas: list[str] = []

    def abrir_sem_env(arquivo, *args, **kwargs):
        nome = str(arquivo) if isinstance(arquivo, (str, bytes, os.PathLike)) else ""
        if nome and Path(nome).name in {".env", ".env.local", ".env.server"}:
            tentativas.append(nome)
            raise AssertionError(f"o gerador tentou ler arquivo local: {nome}")
        return abrir_real(arquivo, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", abrir_sem_env)
    documento = modulo.gerar_documento()

    assert documento["paths"]
    assert tentativas == []


def test_o_gerador_devolve_o_ambiente_que_encontrou():
    """Contraprova do defeito da tentativa a1.

    Ela mutava `Settings.model_config` e apagava as variaveis VOLC do processo
    SEM restaurar. Rodando dentro do pytest isso vazava para os testes seguintes:
    `test_config_env_server.py`, que confere qual `env_file` o FastAPI usa,
    passava a receber `None` e estourava — um modulo que ninguem tocou.

    ⚠️ A comparacao e contra `ENV_FILE_ORIGINAL`, tirado no IMPORT do modulo, e
    nao contra o valor lido no comeco deste teste. Medido: com a restauracao
    removida, a versao que comparava com o valor do momento passava — os testes
    acima ja tinham rodado o gerador, `env_file` ja era `None`, e a prova
    comparava o estrago com ele mesmo. Um invariante lido depois do dano nao e
    invariante.
    """
    from app.config import Settings

    assert ENV_FILE_ORIGINAL is not None, "o retrato do import nasceu ja quebrado"

    modulo = _script()
    ambiente_antes = dict(os.environ)

    modulo.gerar_documento()

    assert Settings.model_config.get("env_file") == ENV_FILE_ORIGINAL
    assert ".env" in tuple(Settings.model_config["env_file"])
    assert dict(os.environ) == ambiente_antes


def test_o_gerador_nao_confia_no_schema_ja_memorizado():
    """`app.openapi_schema` e cache: gerar duas vezes tem de dar o mesmo, e o
    segundo resultado nao pode ser o objeto que o primeiro devolveu."""
    modulo = _script()

    primeiro = modulo.gerar_documento()
    segundo = modulo.gerar_documento()

    assert primeiro == segundo
    assert primeiro is not segundo


# ═══════════════════════════════════════════════════════════════════════════
# 6. A regeneracao esta documentada — e o comando documentado funciona
# ═══════════════════════════════════════════════════════════════════════════


def test_o_comando_de_regeneracao_esta_documentado():
    assert DOC.is_file(), "faltou documentar a regeneracao do golden OpenAPI"
    texto = DOC.read_text(encoding="utf-8")

    assert "python3 scripts/gerar_openapi_golden.py --check" in texto
    assert "python3 scripts/gerar_openapi_golden.py --write" in texto
    assert str(GOLDEN.relative_to(RAIZ)) in texto
    assert SHA256_FRAGMENTO in texto


def test_write_regenera_o_mesmo_arquivo_byte_a_byte(tmp_path: Path):
    """⚠️ Escreve num destino TEMPORARIO. Um teste que reescreve o golden
    versionado apagaria a divergencia que ele deveria acusar."""
    destino = tmp_path / "regerado.json"

    resultado = _rodar(tmp_path, "--write", "--golden", str(destino))

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert destino.read_bytes() == GOLDEN.read_bytes()
