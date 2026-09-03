"""A fronteira entre o Cofre e a prova visual — provada, não prometida.

`backend/app/visual_proof/__init__.py` afirma três coisas sobre a separação dos
dois domínios. Este arquivo transforma as três em teste, no mesmo padrão com que
`test_cofre_ativos.py` prova a concordância entre `dominio.py` e o SQL da
migration: uma promessa em comentário envelhece em silêncio; uma promessa em
teste cai quando alguém a quebra.

As três afirmações:

1. `visual_proof` **não importa** `asset_vault` (dependência de mão única);
2. as gramáticas compartilhadas (nome lógico, chave de idempotência) **são as
   mesmas**, apesar de duplicadas;
3. o vocabulário que a prova visual assume do Cofre — o tipo `browser_profile` e
   a relação `authenticates_through` — **existe** no catálogo.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.asset_vault import dominio as cofre
from app.visual_proof import aplicacao as vp_app
from app.visual_proof import dominio as vp

RAIZ = Path(__file__).resolve().parents[2]
PACOTE_VISUAL = RAIZ / "backend" / "app" / "visual_proof"


# ── 1. dependência de mão única ─────────────────────────────────────────────


def test_visual_proof_nao_importa_asset_vault():
    """Se importasse, o broker levaria FastAPI e httpx para o host isolado.

    `visual_proof.dominio` viaja para o sidecar (ver `tools/adspower-broker/`).
    Um import de `asset_vault` arrastaria junto `app.config`, `app.seguranca` e
    a árvore inteira do backend — e o pacote deixaria de ser `stdlib`-only.
    """
    for arquivo in sorted(PACOTE_VISUAL.glob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and (no.module or "").startswith("app."):
                assert no.module.startswith("app.visual_proof"), (
                    f"{arquivo.name} importa {no.module}: a prova visual só pode "
                    "depender de si mesma e da stdlib.")
            if isinstance(no, ast.Import):
                for alias in no.names:
                    assert not alias.name.startswith("app."), (
                        f"{arquivo.name} importa {alias.name}")


def test_dominio_da_prova_visual_e_stdlib_pura():
    """Nenhum pacote de terceiro. É a condição de o broker rodar no host isolado."""
    terceiros = {"fastapi", "httpx", "pydantic", "starlette", "supabase", "requests"}
    arvore = ast.parse((PACOTE_VISUAL / "dominio.py").read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        nomes: list[str] = []
        if isinstance(no, ast.Import):
            nomes = [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            nomes = [(no.module or "").split(".")[0]]
        for nome in nomes:
            assert nome not in terceiros, f"dominio.py importa {nome}"


ROTAS_DO_COFRE = RAIZ / "backend" / "app" / "asset_vault" / "rotas.py"


def _importes_de_prova_visual(fonte: str) -> tuple[set[str], set[str]]:
    """Separa o que o MÓDULO importa do que as fábricas importam por dentro.

    A distinção é o contrato: o import de topo é a superfície de acoplamento
    permanente; o import dentro de `obter_*` é a raiz de composição, e o
    repositório já usa esse mesmo padrão em `obter_casos` (que importa
    `SupabaseService` por dentro justamente para não acoplar o módulo).
    """
    arvore = ast.parse(fonte)
    de_topo: set[str] = set()
    de_fabrica: set[str] = set()
    dentro_de_funcao: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for filho in ast.walk(no):
                dentro_de_funcao.add(id(filho))
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and (no.module or "").startswith("app.visual_proof"):
            alvo = de_fabrica if id(no) in dentro_de_funcao else de_topo
            alvo.update(a.name for a in no.names)
    return de_topo, de_fabrica


def test_o_cofre_so_conhece_a_porta_de_leitura():
    """No TOPO, o Cofre conhece uma porta e uma função pura. Nada mais.

    Se `asset_vault.rotas` passasse a importar `ControleDeProvaVisual` no
    módulo, a fronteira "o Cofre responde e não executa" viraria comentário.
    Os adaptadores concretos entram só dentro das fábricas de dependência, que
    é onde a composição pode acontecer sem virar acoplamento.
    """
    de_topo, de_fabrica = _importes_de_prova_visual(
        ROTAS_DO_COFRE.read_text(encoding="utf-8"))
    assert de_topo == {"LeitorDeProvaVisual", "montar_prontidao"}, de_topo
    assert de_fabrica <= {"LeitorSemPersistencia", "BrokerHttp"}, de_fabrica


def test_o_cofre_nunca_conhece_o_executor_nem_o_contrato_de_operacao():
    """A prova complementar: nomes que não podem aparecer em lugar NENHUM.

    `BrokerHttp` é permitido porque a rota só lhe pergunta `.configurado` — uma
    leitura de configuração. O que não pode existir é o caminho que EXECUTA.
    """
    fonte = ROTAS_DO_COFRE.read_text(encoding="utf-8")
    for proibido in ("ControleDeProvaVisual", "AdsPowerBrokerRequest",
                     "RepositorioEmMemoria", "PedidoDeProvaVisual",
                     "ExecutorDoBroker", "capturar_superficie"):
        assert proibido not in fonte, (
            f"{proibido} apareceu em rotas.py: o Cofre voltou a saber executar.")
    # E a única coisa que a rota pede ao broker é se ele está configurado.
    assert ".configurado" in fonte and ".executar(" not in fonte


# ── 2. as gramáticas duplicadas concordam ───────────────────────────────────


def test_nome_logico_tem_a_mesma_gramatica_nos_dois_dominios():
    assert vp.NOME_LOGICO.pattern == cofre.NOME_LOGICO.pattern


@pytest.mark.parametrize("valor", [
    "ADSPOWER_API_KEY", "FB_PAGE_ADMIN", "P1", "A" * 64,
    "minusculo", "1COMECA_COM_DIGITO", "COM-HIFEN", "", "A" * 65, "op://x/y/z",
])
def test_nome_logico_decide_igual_nos_dois_dominios(valor):
    """Concordância no COMPORTAMENTO, não só no `pattern`.

    Comparar strings de regex pega a divergência óbvia; um corpus compartilhado
    pega a divergência que aparece quando alguém reescreve a expressão de um
    lado achando que é equivalente.
    """
    assert bool(vp.NOME_LOGICO.match(valor)) == bool(cofre.NOME_LOGICO.match(valor))


@pytest.mark.parametrize("valor", [
    "vpj-piloto-2026-09-02-01", "abcdefgh", "a.b:c-d_e",
    "curta", "", "x" * 121, "com espaco", "com/barra",
])
def test_chave_de_idempotencia_do_qa_aceita_o_que_o_cofre_aceita(valor):
    """A chave do QA visual DERIVA da chave da publicação.

    Ela aceita `#` a mais (o broker sufixa `#t<tentativa>`), e é por isso que a
    igualdade é de um lado só: tudo que o Cofre aceita, o QA aceita. O contrário
    não vale, e a assimetria é declarada aqui em vez de descoberta em produção.
    """
    if cofre.CHAVE_DE_IDEMPOTENCIA.match(valor):
        assert vp.CHAVE_DE_IDEMPOTENCIA.match(valor), (
            "o QA visual recusou uma chave que o Cofre aceita")


def test_o_sufixo_de_tentativa_do_broker_continua_valido():
    chave = "vpj-piloto-2026-09-02-01"
    assert cofre.CHAVE_DE_IDEMPOTENCIA.match(chave)
    vp.exigir_chave_de_idempotencia_visual(f"{chave}#t1")


# ── 3. o vocabulário assumido existe no Cofre ───────────────────────────────


def test_o_tipo_browser_profile_existe_no_catalogo_do_cofre():
    """`BrowserProfileReference.ativo_id` aponta para um ativo deste tipo."""
    assert "browser_profile" in cofre.TIPO_DA_GAVETA
    assert cofre.TIPO_DA_GAVETA["browser_profile"] == "automation"


def test_a_relacao_authenticates_through_existe_no_cofre():
    """É a aresta que o `handoff` lê para descobrir qual perfil abrir."""
    assert "authenticates_through" in cofre.RELACOES


def test_os_providers_do_perfil_sao_os_do_cofre():
    for provider in cofre.PROVIDERS:
        vp.BrowserProfileReference(
            ativo_id="asset:browser-profile:x", perfil_logico="P1", owner_sub="s",
            provider=provider, credencial_nome_logico="K1")
    with pytest.raises(vp.PayloadRecusado):
        vp.BrowserProfileReference(
            ativo_id="asset:browser-profile:x", perfil_logico="P1", owner_sub="s",
            provider="inventado", credencial_nome_logico="K1")


# ── 4. o que a prova visual devolve continua proibido no Cofre ──────────────


def test_projecao_do_job_passa_pela_blocklist_do_cofre():
    """O recibo do QA visual é gravado no Cofre como verificação.

    Então ele precisa sobreviver a `recusar_chave_sensivel` — que é a mesma
    peneira que o Cofre aplica a todo payload de escrita. Um campo `cookie` ou
    `localizador` na projeção faria a gravação falhar no banco, tarde demais.
    """
    job = vp.VisualProofJob.novo(
        job_id="vpj_1", owner_sub="s", ativo_id="asset:facebook-page:piloto",
        perfil=vp.BrowserProfileReference(
            ativo_id="asset:browser-profile:piloto", perfil_logico="PERFIL_PILOTO_01",
            owner_sub="s", provider="1password", credencial_nome_logico="ADSPOWER_API_KEY"),
        url_esperada="https://exemplo.com.br/post", dominio_esperado="exemplo.com.br",
        viewport=vp.Viewport(largura=1366, altura=768), timezone="America/Sao_Paulo",
        classe_de_agente="desktop-chromium", chave_idempotencia="vpj-piloto-01",
        criado_em="2026-09-02T12:00:00+00:00", timeout_s=45)
    cofre.recusar_chave_sensivel(job.para_dicionario(), "prova_visual")

    recibo = vp.AdsPowerBrokerReceipt(
        recibo_id="rcp_1", pedido_id="p", chave_idempotencia="vpj-piloto-01#t1",
        operacao="capturar_superficie", perfil_logico="PERFIL_PILOTO_01", owner_sub="s",
        ativo_id="asset:facebook-page:piloto", estado="executado", motivo_codigo="ok",
        motivo="ok", iniciado_em="2026-09-02T12:00:00+00:00",
        concluido_em="2026-09-02T12:00:03+00:00", duracao_ms=3000)
    cofre.recusar_chave_sensivel(recibo.para_dicionario(), "recibo")


def test_prontidao_inteira_sobrevive_a_blocklist_do_cofre():
    prontidao = vp_app.montar_prontidao(
        handoff={"destino": {"ativo_id": "asset:facebook-page:piloto", "estado": "active"},
                 "referencia_de_acesso": [{"provider": "1password",
                                           "nome_logico": "FB_PAGE_ADMIN",
                                           "verificacao_estado": "verified"}],
                 "perfis_de_navegador": [{"tipo": "authenticates_through",
                                          "destino_id": "asset:browser-profile:piloto",
                                          "destino_rotulo": "Perfil piloto"}],
                 "bloqueios": []},
        broker_configurado=True, persistencia=("ausente", "sem migration"))
    cofre.recusar_chave_sensivel(prontidao, "prontidao")
    assert "op://" not in json.dumps(prontidao, ensure_ascii=False)
