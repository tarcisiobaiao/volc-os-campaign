"""O ambiente real, preservado antes que os testes herméticos o apaguem.

## O defeito que este arquivo conserta

Mais de dez módulos de teste fazem isto NO IMPORT, para rodar offline:

    for _k in ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", …):
        os.environ[_k] = ""

String vazia SOBREPÕE o `.env` (variável de ambiente ganha do arquivo), e nada
restaura. Como o pytest importa TODOS os módulos de teste antes de rodar
qualquer um, a partir do primeiro import o Supabase está desligado para todo
mundo — inclusive para os testes que precisam dele de verdade.

⚠️ O resultado não era falha, era SILÊNCIO. Medido em 18/08/2026:

    pytest tests/test_trafego.py        28 passed
    pytest tests/                       4 desses 28 SKIPPED

Entre os que sumiam estavam os do portão de `app/trafego/escopo.py` — os que
provam que o sistema recusa operar em conta de cliente. Um teste que pula em
silêncio não protege nada, e o pior é que a contagem verde diz que protege.

## Como o conserto funciona

O `conftest.py` é o PRIMEIRO arquivo que o pytest importa, antes de qualquer
módulo de teste. O retrato tirado aqui é o ambiente ainda intacto. Quem precisa
dele pede a fixture — explicitamente, porque restaurar para todo mundo
quebraria os herméticos, que dependem do apagão.

    pytestmark = pytest.mark.usefixtures("ambiente_real")
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O retrato. Tirado no import do conftest, com o ambiente ainda intacto.
_ENV_INTACTO = dict(os.environ)

# Só o que os módulos herméticos zeram e os testes ao vivo precisam de volta.
# Não é `_ENV_INTACTO` inteiro: restaurar tudo desfaria `PAUTADOR_ENGINE=mock`
# e um teste ao vivo passaria a gastar chamada de LLM sem ninguém pedir.
_CHAVES = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
)


@pytest.fixture
def ambiente_real(monkeypatch):
    """Devolve as credenciais reais só para este teste.

    `monkeypatch` desfaz no teardown, então o apagão volta a valer para os
    herméticos que rodarem depois.
    """
    from app.config import get_settings

    # ⚠️ APAGAR, não restaurar — e a diferença é a razão de a primeira versão
    # deste conserto não ter funcionado.
    #
    # `SUPABASE_URL` NÃO está em `os.environ`: ela mora em `backend/.env`, e o
    # pydantic-settings lê o arquivo quando a variável não existe. É exatamente
    # por isso que os módulos herméticos gravam `""` — string vazia é uma
    # variável que EXISTE, e ela ganha do arquivo. Repor o retrato não adianta:
    # o retrato também não tem a chave. Quem devolve o `.env` é o `delenv`.
    for chave in _CHAVES:
        valor = _ENV_INTACTO.get(chave)
        if valor:
            monkeypatch.setenv(chave, valor)
        else:
            monkeypatch.delenv(chave, raising=False)

    # `get_settings` é `lru_cache`: sem limpar, ele devolve o Settings montado
    # com as variáveis zeradas e a restauração não teria efeito nenhum.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def ambiente_real_modulo():
    """A mesma coisa, com escopo de MÓDULO.

    ⚠️ Existe porque `monkeypatch` só existe por função, e fixture de módulo
    roda ANTES de qualquer fixture de função. `test_quadro.py` pede o quadro
    numa fixture de módulo: com a variante de função, a requisição saía com o
    ambiente ainda zerado, tomava 503 e o `skip` valia para o módulo inteiro —
    oito testes sumindo, e a `usefixtures` parecendo aplicada.

    Quem precisa dela tem de PEDI-LA por parâmetro, não por `usefixtures`: entre
    duas fixtures de mesmo escopo, só a dependência explícita ordena.
    """
    from app.config import get_settings

    mp = pytest.MonkeyPatch()
    for chave in _CHAVES:
        valor = _ENV_INTACTO.get(chave)
        if valor:
            mp.setenv(chave, valor)
        else:
            mp.delenv(chave, raising=False)
    get_settings.cache_clear()
    yield
    mp.undo()
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# IDENTIDADE NOS TESTES DE COMPORTAMENTO
# ---------------------------------------------------------------------------
# Desde 24/08/2026 todo router aplica `exigir_usuario`, e as rotas
# administrativas aplicam `exigir_admin`. Os testes de comportamento — os que
# perguntam "o quadro carrega a procedência?", "a trava está fechada?" — passam
# a tomar 401 antes de chegar na regra que queriam medir.
#
# A saída NÃO é afrouxar o portão. É dizer quem está pedindo, como o navegador
# diz. `dependency_overrides` troca a dependência por um dublê que devolve uma
# `Identidade` pronta, sem rede e sem Supabase.
#
# ⚠️ E é AUTOUSE de propósito, com recusa explícita: se fosse opcional, um teste
# novo nasceria tomando 401 e a correção mais rápida seria remover o portão da
# rota. Autouse faz o caminho fácil ser o certo.
#
# Quem precisa ver o portão DE VERDADE marca o módulo:
#
#     pytestmark = pytest.mark.identidade_real
#
# É o caso de `test_seguranca_hub.py`, cujo trabalho inteiro é provar que a
# recusa acontece. Um dublê ali tornaria a suíte de segurança decorativa.

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "identidade_real: não instala o dublê de identidade — a rota é exercitada "
        "com o portão real, para provar que ele recusa.",
    )


def _dublê_de_identidade():
    from app.seguranca.identidade import Identidade

    # ADMIN e não OPERATOR porque os testes de comportamento cobrem rotas dos
    # dois níveis; um dublê de OPERATOR faria metade falhar por 403 e a leitura
    # do resultado viraria adivinhação sobre qual portão barrou.
    return Identidade(
        sub="00000000-0000-0000-0000-000000000000",
        email="teste@agenciavolc.com.br",
        papel="ADMIN",
        origem="sessao",
    )


@pytest.fixture(scope="session", autouse=True)
def identidade_de_teste():
    """Instala o dublê para a sessão INTEIRA de testes.

    ⚠️ Escopo de sessão, e não de função, por um motivo medido: `test_quadro.py`
    pede o quadro numa fixture de MÓDULO, e fixture de módulo roda antes de
    qualquer fixture de função. Com a versão de função, aquelas oito requisições
    saíam sem identidade, tomavam 401 e o módulo inteiro virava erro de setup —
    exatamente a mesma armadilha que `ambiente_real_modulo` documenta acima,
    aparecendo pela segunda vez neste arquivo por outra porta.
    """
    try:
        from app.main import app
        from app.seguranca.identidade import exigir_admin, exigir_usuario
    except Exception:  # noqa: BLE001
        yield
        return

    dublê = _dublê_de_identidade()
    app.dependency_overrides[exigir_usuario] = lambda: dublê
    app.dependency_overrides[exigir_admin] = lambda: dublê
    yield
    app.dependency_overrides.pop(exigir_usuario, None)
    app.dependency_overrides.pop(exigir_admin, None)


@pytest.fixture(autouse=True)
def portao_real_quando_pedido(request):
    """Tira o dublê dos testes marcados com `identidade_real`.

    Eles existem para provar que a recusa acontece. Um dublê ali tornaria a
    suíte de segurança decorativa: toda rota responderia como se um ADMIN
    estivesse pedindo, e a recusa que se quer medir nunca aconteceria.
    """
    if not request.node.get_closest_marker("identidade_real"):
        yield
        return

    try:
        from app.main import app
        from app.seguranca.identidade import exigir_admin, exigir_usuario
    except Exception:  # noqa: BLE001
        yield
        return

    guardados = {
        chave: app.dependency_overrides.pop(chave)
        for chave in (exigir_usuario, exigir_admin)
        if chave in app.dependency_overrides
    }
    try:
        yield
    finally:
        app.dependency_overrides.update(guardados)
