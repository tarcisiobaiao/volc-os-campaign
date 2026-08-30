"""A releitura do WordPress — o elo que fecha o ciclo PAUTA → FUNIL → CAMPANHA.

## O defeito que a rota conserta

`status_wp` e `lp_url` são gravados UMA VEZ, pelo worker, no instante da escrita.
O motor sobe tudo como rascunho de propósito (`engine/config.yaml:
publish_status: draft` — "generate → draft → human reviews and clicks publish").
Ninguém relê o WordPress depois.

Medido em 18/08/2026: o run #6 tem três páginas, as três `draft`, e o Hub de
Tráfego barra LP em rascunho e URL provisória. Sem esta rota, publicar a LP no
WordPress não muda nada no banco — e o Tráfego barraria PARA SEMPRE com a página
já no ar.

⚠️ Ela lê o WordPress e escreve SÓ na nossa tabela. Nenhum teste aqui publica,
edita ou apaga qualquer coisa no site.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ⚠️ Sem isto, estes testes PULAM na suíte inteira: os módulos herméticos
# gravam "" em SUPABASE_URL no import e ninguém restaura. Ver o cabeçalho
# de `tests/conftest.py` — 4 destes sumiam em silêncio, medido em 18/08/2026.
pytestmark = pytest.mark.usefixtures("ambiente_real")



@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app)


def test_run_inexistente_nao_vira_500(cliente: TestClient):
    r = cliente.post("/api/publicacao/redator/runs/999999/reler-wp")
    if r.status_code == 503:
        pytest.skip("Supabase indisponível neste ambiente")
    assert r.status_code == 404, r.text


def test_run_sem_pagina_publicada_recusa_e_diz_por_que(cliente: TestClient):
    """Não há o que reler antes de o motor publicar alguma coisa.

    O 409 tem de explicar isso: um 200 com lista vazia faria o operador achar
    que releu e que nada mudou — desfecho idêntico ao de um site fora do ar.
    """
    runs = cliente.get("/api/publicacao/redator/runs")
    if runs.status_code == 503:
        pytest.skip("Supabase indisponível neste ambiente")
    vazios = [x for x in runs.json() if (x.get("paginas_geradas") or 0) == 0
              and x.get("status") in ("error", "cancelled", "canceled")]
    if not vazios:
        pytest.skip("nenhum run sem página publicada para exercitar")

    r = cliente.post(f"/api/publicacao/redator/runs/{vazios[0]['id']}/reler-wp")
    assert r.status_code == 409, r.text
    assert "reler" in r.json()["detail"]


def test_a_releitura_e_idempotente_e_nao_inventa_publicacao(cliente: TestClient):
    """Rodar duas vezes seguidas não pode "publicar" nada sozinha.

    Este é o teste que importa: a rota escreve na nossa tabela, e uma escrita
    que muda estado a cada chamada transformaria releitura em efeito colateral.
    O que ela devolve tem de ser o que o WordPress diz, sempre igual enquanto o
    WordPress não mudar.
    """
    runs = cliente.get("/api/publicacao/redator/runs")
    if runs.status_code == 503:
        pytest.skip("Supabase indisponível neste ambiente")
    com_pagina = [x for x in runs.json() if x.get("status") == "done"]
    if not com_pagina:
        pytest.skip("nenhum run concluído para exercitar")

    alvo = com_pagina[0]["id"]
    primeira = cliente.post(f"/api/publicacao/redator/runs/{alvo}/reler-wp")
    if primeira.status_code in (409, 502, 503):
        pytest.skip(f"run {alvo} não relegível aqui: {primeira.json().get('detail','')[:80]}")
    a = primeira.json()

    segunda = cliente.post(f"/api/publicacao/redator/runs/{alvo}/reler-wp")
    assert segunda.status_code == 200, segunda.text
    b = segunda.json()

    # A segunda passada não pode ver mudança nenhuma: o WordPress não mudou
    # entre as duas, e é dele que o estado vem.
    assert b["mudaram"] == 0, f"releitura não é idempotente: {b['resumo']}"
    assert b["no_ar"] == a["no_ar"]
    assert [p["status_agora"] for p in b["paginas"]] == \
           [p["status_agora"] for p in a["paginas"]]


def test_pagina_sumida_do_wordpress_e_relatada_e_nao_apagada(cliente: TestClient):
    """⚠️ 404 no WP NÃO remove a linha de `paginas_publicadas`.

    Ela é o único registro de qual rascunho veio de qual run, e a atribuição de
    receita casa a URL exata. Sumir com a linha consertaria a tela e destruiria
    a rastreabilidade.
    """
    import inspect

    from app.routers import publicacao

    fonte = inspect.getsource(publicacao.reler_do_wordpress)
    assert "novas.append(nova)" in fonte, \
        "a rota deixou de acumular TODAS as páginas — 404 pode estar apagando linha"
    assert "não existe mais no WordPress" in fonte, \
        "o 404 do WordPress deixou de ser relatado"
