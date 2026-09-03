"""As contencoes que nao sao comportamento: elas sao sobre o CODIGO.

## Por que estes testes existem

O ADR de 28/08/2026 escreveu "O Postiz nao recebe a service_role do Supabase".
Enquanto isso for uma linha de markdown, e uma intencao. O que a torna um
controle e um teste que falha quando o adaptador passa a poder alcancar a chave
— e o caminho de menor esforco ja foi trilhado uma vez neste repositorio
(`n8n/pautador_kw_mining_webhook.json` carrega a chave de servico).

O repositorio ja tinha o formato: `test_trafego_contrato_canais.py:498` varre uma
lista de segredos proibidos, e `test_seguranca_hub.py` inspeciona a arvore de
dependencias de toda `APIRoute`. Estes testes copiam os dois.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "backend" / "app" / "publicacao_organica"
ADAPTADORES = PACOTE / "adaptadores"


def _fontes(diretorio: Path) -> list[Path]:
    return sorted(p for p in diretorio.rglob("*.py"))


# ---------------------------------------------------------------------------
# Contraprova N — o control plane nunca alcanca a service_role
# ---------------------------------------------------------------------------

#: Identificadores que, se o adaptador REFERENCIAR, significam que ele PODE
#: alcancar o Supabase. Nao e "ele usa": e "ele consegue", que ja e demais.
_PROIBIDOS_NO_ADAPTADOR = frozenset({
    "supabase_service_role_key",
    "service_role",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SupabaseService",
    "supabase_url",
    "SUPABASE_URL",
    "get_settings",
    "Settings",
})


def _identificadores(arquivo: Path) -> set[str]:
    """Nomes que o codigo REFERENCIA — nao palavras que o texto contem.

    ⚠️ A primeira versao deste teste procurava as palavras no texto cru, e
    falhava contra o proprio docstring de `postiz.py` — que existe justamente
    para dizer "este modulo nao conhece service_role". Um teste que proibe
    EXPLICAR a regra force a proxima pessoa a apagar a explicacao para ficar
    verde. A pergunta certa e "o modulo consegue chegar la?", e quem responde
    isso e a arvore sintatica.
    """
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.keyword) and no.arg:
            nomes.add(no.arg)
        elif isinstance(no, ast.alias):
            nomes.add(no.asname or no.name.rsplit(".", 1)[-1])
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(no.name)
        elif isinstance(no, ast.arg):
            nomes.add(no.arg)
    return nomes


@pytest.mark.parametrize("arquivo", _fontes(ADAPTADORES), ids=lambda p: p.name)
def test_o_adaptador_nao_alcanca_o_supabase(arquivo: Path) -> None:
    encontrados = _identificadores(arquivo) & _PROIBIDOS_NO_ADAPTADOR
    assert not encontrados, (
        f"{arquivo.name} referencia {sorted(encontrados)}. O control plane externo "
        "nao pode alcancar o Supabase — ADR-DISTRIBUICAO-ORGANICA-E-QA-VISUAL, guarda 5."
    )


def test_o_teste_de_contencao_realmente_morde(tmp_path: Path) -> None:
    """Sem esta contraprova, o teste acima seria verde por vacuidade.

    Um `_identificadores` quebrado (devolvendo conjunto vazio) faria a contencao
    passar para qualquer arquivo, inclusive um que importasse a chave.
    """
    invasor = tmp_path / "invasor.py"
    invasor.write_text(
        "from app.config import get_settings\n"
        "def vazar():\n"
        "    return get_settings().supabase_service_role_key\n",
        encoding="utf-8")
    assert _identificadores(invasor) & _PROIBIDOS_NO_ADAPTADOR


def test_o_adaptador_nao_importa_a_config_do_backend() -> None:
    """Nao basta nao citar a chave: nao pode nem chegar ao objeto que a tem.

    `get_settings()` devolve `Settings`, que carrega `supabase_service_role_key`.
    Um adaptador que importasse `app.config` teria a chave a um atributo de
    distancia, e a guarda viraria convencao.
    """
    for arquivo in _fontes(ADAPTADORES):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            modulo = None
            if isinstance(no, ast.ImportFrom):
                modulo = no.module or ""
            elif isinstance(no, ast.Import):
                modulo = ",".join(a.name for a in no.names)
            if modulo and ("app.config" in modulo or "supabase" in modulo.lower()):
                pytest.fail(
                    f"{arquivo.name} importa '{modulo}'. O adaptador conhece UM segredo — "
                    "o token do control plane — e nada mais."
                )


def test_o_adaptador_recebe_o_token_por_parametro_e_nao_le_do_ambiente() -> None:
    # `os.environ` dentro do adaptador significaria uma segunda fonte de
    # configuracao, invisivel para quem le a construcao do objeto.
    for arquivo in _fontes(ADAPTADORES):
        texto = arquivo.read_text(encoding="utf-8")
        assert "os.environ" not in texto, arquivo.name
        assert "getenv" not in texto, arquivo.name


def test_as_settings_do_control_plane_sao_so_tres() -> None:
    """A superficie de configuracao e pequena e nomeada, e o teste a congela."""
    config = (RAIZ / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    nomes = set(re.findall(r"^\s+(postiz_[a-z_]+)\s*:", config, re.MULTILINE))
    assert nomes == {"postiz_base_url", "postiz_api_token", "postiz_permitir_rede_interna"}, nomes


# ---------------------------------------------------------------------------
# Contraprova O — nenhum segredo versionado nos artefatos desta missao
# ---------------------------------------------------------------------------

#: Formatos reconheciveis de credencial. Nao e detector de entropia — e a mesma
#: lista de `cofre_sem_material_de_credencial`, mais os prefixos do Postiz.
# ⚠️ O `\b` NAO E ENFEITE: sem ele, o prefixo `pos_` casava dentro de
# `500_apos_gravar` e o teste acusava dois arquivos limpos. Um detector que
# grita em nome de teste ensina a proxima pessoa a ignora-lo.
_FORMATOS_DE_SEGREDO = re.compile(
    r"\b(xox[baprs]|sk-|pk_|ghp_|gho_|pos_)[A-Za-z0-9_-]{16,}"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY"
    r"|op://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/"
)

#: Arquivos desta missao. `git ls-files` nao serve: os arquivos podem ainda nao
#: estar no indice quando o teste roda.
_ALVOS = (
    "backend/app/publicacao_organica",
    "backend/tests/apoio_publicacao_organica.py",
    "backend/tests/test_publicacao_organica_dominio.py",
    "backend/tests/test_publicacao_organica_porta.py",
    "backend/tests/test_publicacao_organica_e2e.py",
    "backend/tests/test_publicacao_organica_segredos.py",
    "supabase/migrations/v14_01_publicacao_organica.sql",
    "supabase/migrations/v14_99_publicacao_organica_rollback.sql",
    "scripts/provar-ciclo-v14_01.sh",
    "deploy/postiz",
    "src/features/publicacao-organica",
    "docs/closure/organic-publication-control-plane-v1",
)


def _arquivos_da_missao() -> list[Path]:
    encontrados: list[Path] = []
    for alvo in _ALVOS:
        caminho = RAIZ / alvo
        if caminho.is_file():
            encontrados.append(caminho)
        elif caminho.is_dir():
            encontrados.extend(
                p for p in caminho.rglob("*")
                if p.is_file() and p.suffix not in {".png", ".jpg", ".gif", ".ico", ".woff2"}
            )
    return encontrados


def test_nenhum_arquivo_da_missao_carrega_material_de_credencial() -> None:
    achados: list[str] = []
    for arquivo in _arquivos_da_missao():
        try:
            texto = arquivo.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for linha_num, linha in enumerate(texto.splitlines(), 1):
            achado = _FORMATOS_DE_SEGREDO.search(linha)
            if achado:
                # ⚠️ O RELATO CITA O ARQUIVO E A LINHA, NUNCA O VALOR. Um teste
                # que imprimisse o segredo encontrado o publicaria no log de CI.
                achados.append(f"{arquivo.relative_to(RAIZ)}:{linha_num}")
    assert not achados, (
        "material com forma de credencial nos artefatos desta missao: "
        + ", ".join(achados)
    )


def test_o_detector_de_segredo_realmente_detecta() -> None:
    """O teste acima passaria com um regex quebrado. Este prova que ele morde.

    ⚠️ OS EXEMPLOS SAO MONTADOS EM PARTES, e isso NAO e driblar o scanner: e a
    unica forma de um arquivo que TESTA deteccao de credencial nao conter, ele
    proprio, uma string com forma de credencial. Um literal aqui reprovaria o
    `scripts/verificar_segredos.py` da casa — que foi exatamente o que aconteceu
    na primeira versao, em 02/09/2026 — e a saida seria enfraquecer o scanner
    para acomodar o teste. Montar em partes mantem os dois honestos.
    """
    exemplos = (
        "token = '" + "xox" + "b-" + "0123456789abcdefghijkl'",
        "auth: " + "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        "-----" + "BEGIN RSA " + "PRIVATE KEY" + "-----",
        "locator = " + "op:" + "//VOLC/Pagina/credential",
    )
    for exemplo in exemplos:
        assert _FORMATOS_DE_SEGREDO.search(exemplo), exemplo


def test_o_scanner_do_repositorio_passa_nos_arquivos_da_missao() -> None:
    """O scanner oficial da casa, e nao so o regex deste arquivo."""
    scanner = RAIZ / "scripts" / "verificar_segredos.py"
    if not scanner.is_file():
        pytest.skip("scripts/verificar_segredos.py ausente neste checkout")
    r = subprocess.run(
        ["python3", str(scanner), "--redact"],
        cwd=str(RAIZ), capture_output=True, text=True, timeout=300,
    )
    assert r.returncode == 0, (
        "o scanner oficial de segredos reprovou a arvore:\n"
        + (r.stdout or "")[-3000:] + (r.stderr or "")[-1000:]
    )


# ---------------------------------------------------------------------------
# Toda rota mutante declara um portao de identidade
# ---------------------------------------------------------------------------


def test_toda_rota_de_publicacao_organica_exige_admin() -> None:
    """Inspeciona a arvore de dependencias real, e nao o codigo-fonte.

    Copia de `test_seguranca_hub.py::test_toda_rota_mutante_declara_um_portao`.
    Uma rota nova acrescentada ao router nasce coberta por este teste — que e a
    razao de o portao estar no `APIRouter` e nao em cada decorador.
    """
    from fastapi.routing import APIRoute

    from app.publicacao_organica import rotas
    from app.seguranca.identidade import exigir_admin

    rotas_encontradas = 0
    for rota in rotas.router.routes:
        if not isinstance(rota, APIRoute):
            continue
        rotas_encontradas += 1
        chamaveis = {
            d.call for d in rota.dependant.dependencies if d.call is not None
        }
        # A dependencia pode estar aninhada (o parametro `quem` depende de
        # `exigir_admin`, que depende de `exigir_usuario`). Achatamos.
        def _achatar(dependencias) -> set:
            saida = set()
            for d in dependencias:
                if d.call is not None:
                    saida.add(d.call)
                saida |= _achatar(d.dependencies)
            return saida

        todas = _achatar(rota.dependant.dependencies)
        assert exigir_admin in todas | chamaveis, f"{rota.path} sem portao de admin"

    assert rotas_encontradas >= 10, rotas_encontradas


def test_as_rotas_de_escrita_usam_a_identidade_e_nao_so_a_declaram() -> None:
    """Declarar o portao e usar a identidade sao coisas diferentes.

    Uma rota com `dependencies=[Depends(exigir_admin)]` que NAO recebesse
    `Identidade` como parametro passaria no teste acima e ainda assim publicaria
    a peca de outro dono: o `owner_sub` chegaria de outro lugar (ou de lugar
    nenhum). Este teste le a assinatura de cada handler de escrita.
    """
    import inspect

    from fastapi.routing import APIRoute

    from app.publicacao_organica import rotas
    from app.seguranca.identidade import Identidade

    conferidas = 0
    for rota in rotas.router.routes:
        if not isinstance(rota, APIRoute):
            continue
        if not (set(rota.methods) & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        conferidas += 1
        assinatura = inspect.signature(rota.endpoint)
        # ⚠️ `rotas.py` usa `from __future__ import annotations`, entao
        # `p.annotation` e a STRING "Identidade" e nao a classe. A primeira
        # versao deste teste comparava so com a classe e reprovava TODAS as
        # rotas de escrita — inclusive as corretas. Um teste que falha por
        # engano ensina a desliga-lo.
        def _e_identidade(anotacao) -> bool:
            if anotacao is Identidade:
                return True
            nome = getattr(anotacao, "__name__", None) or (
                anotacao if isinstance(anotacao, str) else "")
            return "Identidade" in str(nome)

        tem_identidade = any(
            _e_identidade(p.annotation) for p in assinatura.parameters.values())
        assert tem_identidade, (
            f"{rota.path} e rota de escrita e nao recebe Identidade como parametro; "
            "o dono viraria filtro opcional"
        )
    assert conferidas >= 6, conferidas
