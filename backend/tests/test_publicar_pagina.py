"""O gatilho que completa um funil pela metade.

## O buraco que a rota fecha

O motor publicava tudo ou nada: `run-volc --publish` no disparo, e ponto. Uma
página que caísse num portão e fosse consertada depois não tinha caminho nenhum
de volta ao WordPress — nem pela tela, nem pela API. Só terminal.

Medido em 19/08/2026, run 9: p2, p3 e p4 ficaram escritas, aprovadas nos portões
e paradas no disco (11.774, 21.638 e 25.275 caracteres). O funil tinha duas
páginas no ar e três órfãs — e funil pela metade não é meio funil: os links
internos apontam para páginas que não existem, e a sessão comprada morre no
primeiro salto.

## ⚠️ O que estes testes NÃO fazem

Nenhum deles publica coisa alguma. Todos exercitam as RECUSAS, que acontecem
antes de o motor ser chamado. O caminho feliz depende de um subprocesso que
escreve num site de verdade — ele é exercitado à mão, com autorização, e o que
se prova aqui é que as portas fecham.

A trava mais importante é a da DUPLICATA. O WordPress não recusa post repetido:
ele aceita, dá outro `post_id` e acrescenta `-2` ao slug. A atribuição de receita
casa `url_wp` com `campaign_funnel_urls` por igualdade de string exata — um post
a mais aponta a campanha para o lugar errado, em silêncio.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ⚠️ Sem isto, estes testes PULAM na suíte inteira: os módulos herméticos
# gravam "" em SUPABASE_URL no import e ninguém restaura. Ver `tests/conftest.py`.
pytestmark = pytest.mark.usefixtures("ambiente_real")


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app)


def _runs(cliente: TestClient):
    r = cliente.get("/api/publicacao/redator/runs")
    if r.status_code == 503:
        pytest.skip("Supabase indisponível neste ambiente")
    return r.json()


def test_run_inexistente_nao_vira_500(cliente: TestClient):
    r = cliente.post("/api/publicacao/redator/runs/999999/publicar/3")
    if r.status_code == 503:
        pytest.skip("Supabase indisponível neste ambiente")
    assert r.status_code == 404, r.text


def test_pagina_ja_publicada_e_recusada_com_o_post_id(cliente: TestClient):
    """A trava que impede um SEGUNDO post para a mesma página.

    E a recusa cita o `post_id`: "já publicada" sem o número faria o operador
    procurar no admin para conferir, que é exatamente o trabalho que a mensagem
    existe para poupar.
    """
    alvo = None
    for run in _runs(cliente):
        det = cliente.get(f"/api/publicacao/redator/runs/{run['id']}")
        if det.status_code != 200:
            continue
        for p in (det.json().get("paginas_publicadas") or []):
            if p.get("page_number") and p.get("post_id"):
                alvo = (run["id"], p["page_number"], p["post_id"])
                break
        if alvo:
            break
    if not alvo:
        pytest.skip("nenhuma página publicada para exercitar a trava")

    run_id, page, post_id = alvo
    r = cliente.post(f"/api/publicacao/redator/runs/{run_id}/publicar/{page}")
    assert r.status_code == 409, r.text
    assert str(post_id) in r.json()["detail"]
    assert "segundo post" in r.json()["detail"]


def test_pagina_inexistente_no_run_e_recusada(cliente: TestClient):
    """Sem artigo no disco não há o que enviar — e o 409 diz isso."""
    runs = [x for x in _runs(cliente) if x.get("status") == "done"]
    if not runs:
        pytest.skip("nenhum run concluído")

    r = cliente.post(f"/api/publicacao/redator/runs/{runs[0]['id']}/publicar/99")
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    # Ou não há artigo, ou os arquivos não estão neste disco. As duas são
    # recusas honestas; o que não pode é 200 ou 500.
    assert ("não tem artigo escrito" in detalhe) or ("não estão no disco" in detalhe)


def test_run_em_andamento_e_recusado(cliente: TestClient):
    """Dois processos escrevendo o mesmo `state.json` se sobrescrevem — o último
    a fechar o arquivo vence, e o trabalho do outro some."""
    andando = [x for x in _runs(cliente) if x.get("status") in ("running", "queued")]
    if not andando:
        pytest.skip("nenhum run em andamento")

    r = cliente.post(f"/api/publicacao/redator/runs/{andando[0]['id']}/publicar/2")
    assert r.status_code == 409, r.text
    assert "ainda está rodando" in r.json()["detail"]


# ── o contrato do worker ────────────────────────────────────────────────────

def test_o_worker_usa_resume_com_only_e_publish():
    """O comando é `resume <run_id> --only pN --publish --perfil`.

    ⚠️ Sem `--only`, a retomada arrastaria o funil INTEIRO e publicaria páginas
    que ninguém autorizou. Sem `--publish`, ela roda e não publica: o
    `config.yaml` traz `publish: false`, e o operador veria "deu certo" com a
    página ainda parada.

    ⚠️ O `--publish` MUDOU DE DONO, e este teste mudou junto. Ele era montado
    aqui e também no `executar` — dois lugares independentes, e um portão num
    deles deixava o outro aberto. Agora quem monta é `_disparar_motor`, e é lá
    que a flag é conferida; esta função só diz `publicar=True` e entrega a
    autorização do portão. Ver `tests/test_barreira2_publicacao.py`.
    """
    import inspect

    from app.redator import worker as w

    fonte = inspect.getsource(w.publicar_pagina)
    assert '"resume", run_id' in fonte
    assert '"--only", f"p{page_number}"' in fonte
    assert '"--perfil"' in fonte
    assert "_disparar_motor(" in fonte
    assert "publicar=True" in fonte
    assert '"--publish"' in inspect.getsource(w._disparar_motor)


def test_o_worker_apaga_a_senha_do_disco():
    """O perfil vai para o disco com a senha DECIFRADA dentro. Ela sai de lá
    aconteça o que acontecer — é o mesmo contrato de `executar`."""
    import inspect

    from app.redator import worker as w

    fonte = inspect.getsource(w.publicar_pagina)
    assert "finally:" in fonte
    assert "shutil.rmtree(tmp" in fonte
    assert "0o600" in fonte


def test_sair_com_codigo_zero_sem_publicar_e_um_desfecho():
    """⚠️ O laço do motor engole a exceção da página, grava sob `page_N` e sai
    com código 0 sem imprimir nada. Foi assim que um 401 do WordPress passou
    despercebido por três tentativas.

    Quem chama precisa da diferença entre "publiquei" e "rodei sem publicar".
    """
    import inspect

    from app.redator import worker as w

    fonte = inspect.getsource(w.publicar_pagina)
    assert 'f"page_{page_number}"' in fonte, (
        "o worker voltou a confiar no código de saída do motor")
    assert '"ok": False' in fonte


def test_o_tempo_limite_da_publicacao_e_curto():
    """Publicar uma página não é um run. O texto já está pronto; o que falta é
    uma chamada REST. Herdar as 3h de `TIMEOUT_S` deixaria o operador olhando
    uma tela girando por um processo pendurado."""
    from app.redator import worker as w

    assert w.TEMPO_LIMITE_PUBLICACAO_S <= 10 * 60
    assert w.TEMPO_LIMITE_PUBLICACAO_S < w.TIMEOUT_S
