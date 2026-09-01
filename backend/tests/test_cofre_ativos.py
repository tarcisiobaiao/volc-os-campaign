"""O Cofre de Ativos: o portao, a fronteira do segredo e a falha honesta.

## O que estes testes protegem

Tres promessas que, se quebradas, quebram em silencio:

1. **Nada de segredo sai.** Nem no corpo, nem no recibo, nem na MENSAGEM DE
   ERRO. O caminho mais provavel de vazamento nao e o campo — e a recusa: uma
   violacao de CHECK no Postgres anexa `DETAIL: Failing row contains (…)` com a
   linha inteira, incluindo o valor que acabou de ser recusado.
2. **Falha de banco nao vira lista vazia.** Um painel que responde `[]` porque o
   Supabase caiu afirma "voce nao tem ativos" com a mesma cara com que afirmaria
   "voce tem trinta".
3. **Retry nao duplica.** E o recibo diz qual foi qual.

Hermeticos: nenhum teste aqui fala com rede ou com banco. O repositorio e
substituido por um duble que registra o que recebeu.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.asset_vault import dominio as dom  # noqa: E402
from app.asset_vault import rotas  # noqa: E402
from app.asset_vault.aplicacao import CasosDeUso, CofreIndisponivel  # noqa: E402
from app.asset_vault.infraestrutura import RepositorioSupabase, _mensagem_segura  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "supabase" / "migrations" / "v13_01_cofre_de_ativos.sql"

#: O texto que NUNCA pode reaparecer em resposta, recibo ou mensagem.
SEGREDO = "Tr0ub4dor&3-NUNCA-PODE-VAZAR"
LOCALIZADOR = "op://VOLC/Pagina%20Piloto/credential"

ADMIN = Identidade(sub="11111111-1111-1111-1111-111111111111",
                   email="admin@agenciavolc.com.br", papel="ADMIN", origem="sessao")

ATIVO_VALIDO: dict[str, Any] = {
    "ativo_id": "asset:facebook-page:piloto",
    "kind": "facebook_page",
    "cluster": "social_presence",
    "nome": "Pagina monetizada do piloto",
    "plataforma": "Meta",
    "estado": "declared",
    "criticidade": "high",
    "resumo": "Pagina declarada pelo dono, sem identidade tecnica conferida no VOLC.",
    "dono_nome": "Tarcisio",
    "dono_custodia": "declared",
    "capacidades": ["Publicacao organica"],
    "tags": ["piloto"],
    "proxima_acao": "Conferir ID da pagina, Business Portfolio e administradores.",
}


class RepositorioDuble:
    """Duble do repositorio. Nao fala com nada; registra o que recebeu."""

    def __init__(self, *, listar=None, detalhar=None, engines=None,
                 postura=None, executar=None, configurado=True):
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self._listar = listar if listar is not None else {"gavetas": [], "ativos": []}
        self._detalhar = detalhar
        self._engines = engines if engines is not None else []
        self._postura = postura if postura is not None else []
        self._executar = executar
        self._configurado = configurado

    @property
    def configurado(self) -> bool:
        return self._configurado

    async def listar(self, **filtros):
        self.chamadas.append(("listar", filtros))
        if isinstance(self._listar, Exception):
            raise self._listar
        return self._listar

    async def detalhar(self, ativo_id):
        self.chamadas.append(("detalhar", {"ativo_id": ativo_id}))
        if isinstance(self._detalhar, Exception):
            raise self._detalhar
        return self._detalhar

    async def engines(self):
        self.chamadas.append(("engines", {}))
        if isinstance(self._engines, Exception):
            raise self._engines
        return self._engines

    async def postura_credencial(self, ativo_id):
        self.chamadas.append(("postura", {"ativo_id": ativo_id}))
        if isinstance(self._postura, Exception):
            raise self._postura
        return self._postura

    async def executar(self, funcao, argumentos):
        self.chamadas.append((funcao, argumentos))
        if isinstance(self._executar, Exception):
            raise self._executar
        if callable(self._executar):
            return self._executar(funcao, argumentos)
        return self._executar or {"operacao": funcao, "idempotente": False}


def montar(repo, *, quem: Identidade | None = ADMIN) -> TestClient:
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[rotas.obter_casos] = lambda: CasosDeUso(repo)
    if quem is not None:
        app.dependency_overrides[exigir_usuario] = lambda: quem
        app.dependency_overrides[exigir_admin] = lambda: quem
    return TestClient(app, raise_server_exceptions=False)


# ── 1. O dominio e o banco tem de concordar — provado, nao prometido ─────────


def test_os_tipos_do_dominio_sao_exatamente_os_do_banco():
    """Um tipo adicionado so num lugar derruba este teste, e e o ponto.

    Sem ele, `dominio.TIPO_DA_GAVETA` e `cofre_tipo` divergem em silencio ate
    alguem cadastrar um ativo do tipo novo e receber violacao de FK sem entender
    por que a API deixou passar.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = sql[sql.index("INSERT INTO public.cofre_tipo"):]
    bloco = bloco[:bloco.index(";")]
    no_sql = {(k, c) for k, c in re.findall(r"\('([a-z_]+)',\s*'([a-z_]+)'", bloco)}
    no_python = set(dom.TIPO_DA_GAVETA.items())
    assert no_sql == no_python, (
        f"so no SQL: {sorted(no_sql - no_python)} | so no Python: {sorted(no_python - no_sql)}")


def test_as_gavetas_do_dominio_sao_exatamente_as_do_banco():
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = sql[sql.index("INSERT INTO public.cofre_gaveta"):]
    bloco = bloco[:bloco.index(";")]
    no_sql = set(re.findall(r"\('([a-z_]+)',\s*'", bloco))
    assert no_sql == set(dom.GAVETAS)


def test_a_gramatica_do_localizador_concorda_com_a_do_banco():
    """As duas recusam a mesma coisa. Se divergirem, o banco recusa o que a API
    aceitou — e o operador ve um 400 generico onde deveria ver a forma esperada."""
    sql = MIGRATION.read_text(encoding="utf-8")
    padrao = r"op://[A-Za-z0-9._%~-]{1,64}/[A-Za-z0-9._%~-]{1,128}(/[A-Za-z0-9._%~-]{1,64}){1,2}"
    assert padrao in sql
    assert dom.GRAMATICA_DO_LOCALIZADOR["1password"].pattern == "^" + padrao + "$"


# ── 2. O portao ─────────────────────────────────────────────────────────────


def test_sem_papel_admin_a_rota_responde_403_e_nao_toca_no_repositorio():
    repo = RepositorioDuble()
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[rotas.obter_casos] = lambda: CasosDeUso(repo)
    operador = Identidade(sub="u2", email="op@volc", papel="OPERADOR", origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: operador
    cliente = TestClient(app, raise_server_exceptions=False)

    r = cliente.get("/api/cofre/ativos")
    assert r.status_code == 403
    assert repo.chamadas == [], "o portao deixou a chamada chegar no repositorio"


def test_todas_as_rotas_exigem_admin_no_nivel_do_router():
    """Uma rota nova nasce FECHADA. Se alguem adicionar um endpoint sem pensar em
    permissao, ele ainda assim exige ADMIN — o oposto do defeito de 24/08/2026,
    quando 17 rotas de trafego nasceram sem `Depends` nenhum."""
    dependencias = [d.dependency for d in rotas.router.dependencies]
    assert exigir_admin in dependencias


# ── 3. Falha de banco NAO vira lista vazia ──────────────────────────────────


def test_banco_indisponivel_responde_503_e_nao_lista_vazia():
    cliente = montar(RepositorioDuble(listar=CofreIndisponivel("banco fora")))
    r = cliente.get("/api/cofre/ativos")
    assert r.status_code == 503
    assert r.json()["detail"]["codigo"] == "cofre_indisponivel"
    assert "ativos" not in r.json()


def test_supabase_desconfigurado_falha_fechado():
    repo = RepositorioSupabase(supabase=type("X", (), {"enabled": False})())
    with pytest.raises(CofreIndisponivel):
        asyncio.run(repo.listar(p_cluster=None))


def test_resposta_em_forma_inesperada_vira_indisponivel_e_nao_vazio():
    """Um proxy que devolve HTML, ou um PostgREST que muda de forma, produz 503 —
    nunca um inventario vazio que parece verdade."""
    class SupaEstranho:
        enabled = True

        async def rpc(self, funcao, argumentos):
            return "<html>gateway timeout</html>"

    repo = RepositorioSupabase(SupaEstranho())
    with pytest.raises(CofreIndisponivel):
        asyncio.run(repo.listar(p_cluster=None))


def test_inventario_vazio_de_verdade_responde_200_com_as_gavetas():
    """Vazio E um estado legitimo, e tem de ser distinguivel de erro."""
    repo = RepositorioDuble(listar={"gavetas": [{"cluster": "paid_media", "total": 0}], "ativos": []})
    r = montar(repo).get("/api/cofre/ativos")
    assert r.status_code == 200
    assert r.json()["ativos"] == []
    assert r.json()["gavetas"][0]["total"] == 0


# ── 4. CONTRAPROVAS: simples, aninhado, alias, desconhecido ─────────────────


@pytest.mark.parametrize("campo", ["password", "senha", "access_token", "api_key", "cookie",
                                   "recovery_code", "private_key", "totp"])
def test_campo_sensivel_simples_e_recusado(campo):
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0001", "ativo": {**ATIVO_VALIDO, campo: SEGREDO}}
    r = montar(repo).post("/api/cofre/ativos", json=corpo)
    assert r.status_code == 400, "extra=forbid tinha de recusar antes de tudo"
    assert SEGREDO not in r.text, "a recusa ECOOU o valor recusado"
    assert campo in r.json()["detail"]["mensagem"], "a recusa tem de dizer QUAL campo"
    assert repo.chamadas == []


@pytest.mark.parametrize("chave", ["password", "accessToken", "ACCESS-TOKEN", "Access Token",
                                   "codigo_recuperacao", "vault_item_id", "localizador"])
def test_campo_sensivel_ANINHADO_e_recusado_por_qualquer_grafia(chave):
    """A allowlist do topo nao ve o que esta dentro de um campo permitido. Quem ve
    e a varredura recursiva — e ela compara a chave NORMALIZADA."""
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0002",
             "ativo": {**ATIVO_VALIDO, "capacidades": [{"meta": {chave: SEGREDO}}]}}
    r = montar(repo).post("/api/cofre/ativos", json=corpo)
    assert r.status_code == 400
    assert SEGREDO not in r.text, "a recusa ECOOU o valor recusado"
    assert repo.chamadas == []


def test_a_varredura_do_dominio_pega_alias_aninhado_em_array():
    with pytest.raises(dom.PayloadRecusado) as exc:
        dom.recusar_chave_sensivel({"extras": [{"nivel": {"ACCESS-TOKEN": SEGREDO}}]}, "ativo")
    assert "ativo.extras[0].nivel.ACCESS-TOKEN" in str(exc.value)
    assert SEGREDO not in str(exc.value), "a recusa ecoou o valor recusado"


def test_campo_desconhecido_e_recusado_e_nao_ignorado():
    """Pydantic ignora campo desconhecido por padrao. Ignorar aqui faria a API
    responder 201 sem gravar — e sem dizer que nao gravou."""
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0003",
             "ativo": {**ATIVO_VALIDO, "campo_que_ninguem_declarou": 1}}
    r = montar(repo).post("/api/cofre/ativos", json=corpo)
    assert r.status_code == 400
    assert "campo_que_ninguem_declarou" in r.json()["detail"]["mensagem"]
    assert repo.chamadas == []


def test_gaveta_incoerente_e_recusada_antes_da_rede():
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0004",
             "ativo": {**ATIVO_VALIDO, "cluster": "paid_media"}}
    r = montar(repo).post("/api/cofre/ativos", json=corpo)
    assert r.status_code == 400
    assert "social_presence" in r.json()["detail"]["mensagem"]
    assert repo.chamadas == []


def test_url_nao_http_e_recusada():
    repo = RepositorioDuble()
    for url in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.com"):
        corpo = {"chave_idempotencia": "chave-teste-0005",
                 "ativo": {**ATIVO_VALIDO, "url_publica": url}}
        r = montar(repo).post("/api/cofre/ativos", json=corpo)
        assert r.status_code == 400, url
    assert repo.chamadas == []


def test_caminho_absoluto_de_disco_nao_vira_localizacao():
    """`canonical_path` dos manifestos de engine carrega o e-mail do operador. Um
    caminho desses nao vai para resposta HTTP so porque nao e 'segredo'."""
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0006",
             "ativo": {**ATIVO_VALIDO,
                       "localizacao_rotulo": "/Users/mac/Library/CloudStorage/GoogleDrive-x@y.com/z"}}
    r = montar(repo).post("/api/cofre/ativos", json=corpo)
    assert r.status_code == 400
    assert repo.chamadas == []


def test_material_de_credencial_em_prosa_e_recusado():
    repo = RepositorioDuble()
    for campo, valor in (
        ("resumo", "chave -----BEGIN RSA PRIVATE KEY----- anexada ao ativo aqui"),
        ("proxima_acao", "usar op://VOLC/Item/campo para entrar na conta agora"),
    ):
        corpo = {"chave_idempotencia": "chave-teste-0007", "ativo": {**ATIVO_VALIDO, campo: valor}}
        r = montar(repo).post("/api/cofre/ativos", json=corpo)
        assert r.status_code == 400, campo
    assert repo.chamadas == []


# ── 5. A FRONTEIRA DO SEGREDO ───────────────────────────────────────────────


def test_senha_bruta_no_localizador_e_recusada_sem_ecoar_o_valor():
    """O defeito medido em 01/09/2026 vivia exatamente aqui: a CHECK do banco
    recusava e o Postgres anexava `Failing row contains (…, Tr0ub4dor&3, …)`."""
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0008", "provider": "1password",
             "nome_logico": "FB_PAGE_ADMIN", "localizador": SEGREDO,
             "finalidade": "acesso administrativo", "owner_nome": "Tarcisio"}
    r = montar(repo).post("/api/cofre/ativos/asset:facebook-page:piloto/credencial", json=corpo)
    assert r.status_code == 400
    assert SEGREDO not in r.text, "a recusa ECOOU o valor recusado"
    assert "op://<cofre>/<item>" in r.json()["detail"]["mensagem"]
    assert repo.chamadas == []


def test_referencia_com_query_string_e_recusada():
    """`?attribute=otp` aponta para um TOTP, e o ADR diz que MFA nao entra no
    Cofre nem por referencia."""
    repo = RepositorioDuble()
    corpo = {"chave_idempotencia": "chave-teste-0009", "provider": "1password",
             "nome_logico": "FB_OTP", "localizador": "op://VOLC/Item/campo?attribute=otp",
             "finalidade": "segundo fator", "owner_nome": "Tarcisio"}
    r = montar(repo).post("/api/cofre/ativos/asset:facebook-page:piloto/credencial", json=corpo)
    assert r.status_code == 400
    assert repo.chamadas == []


def test_referencia_valida_passa_e_o_recibo_nao_traz_o_localizador():
    repo = RepositorioDuble(executar={"operacao": "cofre.referenciar_credencial",
                                      "ativo_id": "asset:facebook-page:piloto",
                                      "referencia_id": 1, "provider": "1password",
                                      "nome_logico": "FB_PAGE_ADMIN", "idempotente": False})
    corpo = {"chave_idempotencia": "chave-teste-0010", "provider": "1password",
             "nome_logico": "FB_PAGE_ADMIN", "localizador": LOCALIZADOR,
             "finalidade": "acesso administrativo a pagina do piloto", "owner_nome": "Tarcisio"}
    r = montar(repo).post("/api/cofre/ativos/asset:facebook-page:piloto/credencial", json=corpo)
    assert r.status_code == 201
    assert LOCALIZADOR not in r.text
    assert "op://" not in r.text
    # E o localizador CHEGOU ao repositorio: ele entra, so nao volta.
    assert repo.chamadas[0][1]["p_payload"]["localizador"] == LOCALIZADOR


def test_nenhuma_rota_de_leitura_devolve_localizador():
    """A prova central. Se um dia alguem adicionar `localizador` a uma projecao do
    banco, a peneira de `infraestrutura.executar` e esta varredura pegam."""
    detalhe = {"ativo_id": "asset:facebook-page:piloto", "nome": "Pagina",
               "credencial": [{"provider": "1password", "nome_logico": "FB_PAGE_ADMIN",
                               "estado": "referenced", "referencia_registrada": True}]}
    repo = RepositorioDuble(
        listar={"gavetas": [], "ativos": [{"ativo_id": "asset:facebook-page:piloto",
                                           "credencial_registrada": True}]},
        detalhar=detalhe,
        postura=[{"provider": "1password", "nome_logico": "FB_PAGE_ADMIN", "estado": "referenced"}],
        engines=[{"ativo_id": "asset:engine:x", "modalidade": "imagem"}])
    cliente = montar(repo)
    for caminho in ("/api/cofre/ativos",
                    "/api/cofre/ativos/asset:facebook-page:piloto",
                    "/api/cofre/ativos/asset:facebook-page:piloto/credencial",
                    "/api/cofre/engines"):
        r = cliente.get(caminho)
        assert r.status_code == 200, caminho
        assert "op://" not in r.text, caminho
        assert "localizador" not in r.text, caminho


def test_o_recibo_com_localizador_e_barrado_pela_peneira_da_infraestrutura():
    """Defesa em profundidade: mesmo que uma funcao do banco passasse a devolver o
    endereco, ele nao viraria resposta HTTP."""
    class SupaVazando:
        enabled = True

        async def rpc(self, funcao, argumentos):
            return {"operacao": funcao, "localizador": LOCALIZADOR}

    repo = RepositorioSupabase(SupaVazando())
    with pytest.raises(dom.PayloadRecusado):
        asyncio.run(repo.executar("cofre_referenciar_credencial", {}))


# ── 6. A MENSAGEM DE ERRO como superficie de vazamento ──────────────────────


def test_mensagem_do_postgres_com_a_linha_recusada_nunca_e_repassada():
    bruta = ('new row for relation "cofre_credencial_referencia" violates check constraint '
             f'"cofre_credencial_localizador_opaco"\nDETAIL: Failing row contains (1, x, {SEGREDO})')
    saida = _mensagem_segura(bruta, "regra_do_cofre")
    assert SEGREDO not in saida
    assert "cofre_credencial_referencia" not in saida, "nome de tabela chegou a tela"
    assert "check constraint" not in saida


def test_frase_propria_do_projeto_e_repassada_porque_cita_campo_e_nao_valor():
    bruta = "campo proibido no Cofre: ativo.tags[0].meta.accessToken — este schema guarda referencia"
    assert _mensagem_segura(bruta, "campo_proibido") == bruta


def test_erro_do_postgrest_vira_400_sanitizado_e_nao_500():
    class Supa:
        enabled = True

        async def rpc(self, funcao, argumentos):
            pedido = httpx.Request("POST", "https://x/rest/v1/rpc/cofre_cadastrar_ativo")
            resposta = httpx.Response(
                400, request=pedido,
                json={"code": "23514",
                      "message": 'violates check constraint "cofre_ativo_prosa_limpa"',
                      "details": f"Failing row contains ({SEGREDO})", "hint": None})
            raise httpx.HTTPStatusError("400", request=pedido, response=resposta)

    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[rotas.obter_casos] = lambda: CasosDeUso(RepositorioSupabase(Supa()))
    app.dependency_overrides[exigir_usuario] = lambda: ADMIN
    app.dependency_overrides[exigir_admin] = lambda: ADMIN
    c = TestClient(app, raise_server_exceptions=False)

    r = c.post("/api/cofre/ativos",
               json={"chave_idempotencia": "chave-teste-0011", "ativo": ATIVO_VALIDO})
    assert r.status_code == 400
    assert SEGREDO not in r.text
    assert "Failing row" not in r.text
    assert "cofre_ativo_prosa_limpa" not in r.text


def test_migration_ausente_no_banco_vira_503_dizendo_o_que_faltou():
    """404 do PostgREST significa 'a funcao nao existe'. Um 503 mudo aqui mandaria
    o proximo a investigar procurar rede em vez de schema."""
    class Supa:
        enabled = True

        async def rpc(self, funcao, argumentos):
            pedido = httpx.Request("POST", "https://x/rest/v1/rpc/" + funcao)
            resposta = httpx.Response(404, request=pedido, json={})
            raise httpx.HTTPStatusError("404", request=pedido, response=resposta)

    repo = RepositorioSupabase(Supa())
    with pytest.raises(CofreIndisponivel) as exc:
        asyncio.run(repo.listar(p_cluster=None))
    assert "v13_01" in str(exc.value)


# ── 7. Idempotencia visivel ─────────────────────────────────────────────────


def test_primeira_execucao_responde_201_e_replay_responde_200():
    estado = {"n": 0}

    def executar(funcao, argumentos):
        estado["n"] += 1
        return {"operacao": funcao, "ativo_id": ATIVO_VALIDO["ativo_id"], "revisao": 1,
                "idempotente": estado["n"] > 1}

    cliente = montar(RepositorioDuble(executar=executar))
    corpo = {"chave_idempotencia": "chave-cadastro-0001", "ativo": ATIVO_VALIDO}

    primeira = cliente.post("/api/cofre/ativos", json=corpo)
    assert primeira.status_code == 201
    assert primeira.headers["X-Cofre-Idempotente"] == "novo"

    segunda = cliente.post("/api/cofre/ativos", json=corpo)
    assert segunda.status_code == 200
    assert segunda.headers["X-Cofre-Idempotente"] == "replay"
    assert segunda.json()["revisao"] == primeira.json()["revisao"]


def test_chave_de_idempotencia_malformada_e_recusada_antes_da_rede():
    repo = RepositorioDuble()
    r = montar(repo).post("/api/cofre/ativos",
                          json={"chave_idempotencia": "curta", "ativo": ATIVO_VALIDO})
    assert r.status_code == 400
    assert repo.chamadas == []


# ── 8. Relacoes, aposentadoria e verificacao ────────────────────────────────


def test_relacao_exige_exatamente_um_destino():
    repo = RepositorioDuble()
    cliente = montar(repo)
    base = {"chave_idempotencia": "chave-relacao-0001", "tipo": "depends_on",
            "destino_rotulo": "Alvo"}
    nenhum = cliente.post("/api/cofre/ativos/asset:x:y/relacoes", json=base)
    dois = cliente.post("/api/cofre/ativos/asset:x:y/relacoes",
                        json={**base, "destino_id": "asset:a:b", "destino_externo": "concept:c"})
    assert nenhum.status_code == 400 and dois.status_code == 400
    assert repo.chamadas == []


def test_aposentar_exige_motivo_e_devolve_recibo():
    repo = RepositorioDuble(executar={"operacao": "cofre.aposentar_ativo",
                                      "ativo_id": "asset:facebook-page:piloto",
                                      "revisao": 2, "idempotente": False})
    cliente = montar(repo)
    sem = cliente.post("/api/cofre/ativos/asset:facebook-page:piloto/aposentadoria",
                       json={"chave_idempotencia": "chave-aposenta-0001", "motivo": "curto"})
    assert sem.status_code == 400

    com = cliente.post("/api/cofre/ativos/asset:facebook-page:piloto/aposentadoria",
                       json={"chave_idempotencia": "chave-aposenta-0001",
                             "motivo": "piloto encerrado; a pagina sai de operacao"})
    assert com.status_code == 201
    assert com.json()["revisao"] == 2


def test_verificacao_exige_instante_observado_e_nao_o_inventa():
    """Sem default de 'agora': o instante da OBSERVACAO nao e o do registro."""
    repo = RepositorioDuble()
    r = montar(repo).post("/api/cofre/ativos/asset:facebook-page:piloto/verificacoes",
                          json={"chave_idempotencia": "chave-verif-0001", "alvo": "ativo",
                                "resultado": "verified", "metodo": "conferencia manual",
                                "procedencia": "owner_declaration",
                                "evidencia": "o dono confirmou a propriedade da pagina"})
    assert r.status_code == 400
    assert repo.chamadas == []


def test_revisao_vazia_e_recusada():
    repo = RepositorioDuble()
    r = montar(repo).patch("/api/cofre/ativos/asset:facebook-page:piloto",
                           json={"chave_idempotencia": "chave-revisao-0001",
                                 "motivo": "sem mudanca nenhuma", "mudancas": {}})
    assert r.status_code == 400
    assert repo.chamadas == []


def test_o_422_do_fastapi_nao_pode_devolver_o_valor_recusado():
    """DEFEITO MEDIDO EM 01/09/2026, e a razao de este modulo ler o corpo cru.

    O handler padrao de `RequestValidationError` serializa `exc.errors()`, e cada
    erro do Pydantic v2 carrega `input` — o VALOR rejeitado:

        422 {"detail":[{"type":"extra_forbidden","loc":["body","password"],
                        "input":"SENHA-SECRETA-XYZ"}]}

    Num Cofre, esse `input` e a credencial. Este teste prova que a recusa diz
    QUAL campo sem repetir O QUE veio nele — em TODAS as rotas de escrita.
    """
    repo = RepositorioDuble()
    cliente = montar(repo)
    pedidos = [
        ("POST", "/api/cofre/ativos",
         {"chave_idempotencia": "chave-vaz-0001", "ativo": {**ATIVO_VALIDO, "password": SEGREDO}}),
        ("PATCH", "/api/cofre/ativos/asset:facebook-page:piloto",
         {"chave_idempotencia": "chave-vaz-0002", "motivo": "tentativa de vazamento",
          "mudancas": {"api_key": SEGREDO}}),
        ("POST", "/api/cofre/ativos/asset:facebook-page:piloto/relacoes",
         {"chave_idempotencia": "chave-vaz-0003", "tipo": "depends_on",
          "destino_rotulo": "X", "cookie": SEGREDO}),
        ("POST", "/api/cofre/ativos/asset:facebook-page:piloto/aposentadoria",
         {"chave_idempotencia": "chave-vaz-0004", "motivo": "motivo suficiente aqui",
          "totp": SEGREDO}),
        ("POST", "/api/cofre/ativos/asset:facebook-page:piloto/reativacao",
         {"chave_idempotencia": "chave-vaz-0005", "motivo": "motivo suficiente aqui",
          "estado": "active", "recovery_code": SEGREDO}),
        ("POST", "/api/cofre/ativos/asset:facebook-page:piloto/verificacoes",
         {"chave_idempotencia": "chave-vaz-0006", "alvo": "ativo", "resultado": "verified",
          "metodo": "manual", "procedencia": "owner_declaration",
          "evidencia": "o dono confirmou a propriedade", "observado_em": "2026-09-01T10:00:00Z",
          "private_key": SEGREDO}),
        ("POST", "/api/cofre/ativos/asset:facebook-page:piloto/credencial",
         {"chave_idempotencia": "chave-vaz-0007", "provider": "1password",
          "nome_logico": "X_TOKEN", "localizador": LOCALIZADOR,
          "finalidade": "acesso administrativo", "owner_nome": "V", "senha": SEGREDO}),
        ("DELETE", "/api/cofre/relacoes/1",
         {"chave_idempotencia": "chave-vaz-0008", "motivo": "motivo suficiente aqui",
          "access_token": SEGREDO}),
    ]
    for metodo, caminho, corpo in pedidos:
        r = cliente.request(metodo, caminho, json=corpo)
        assert r.status_code == 400, f"{metodo} {caminho} -> {r.status_code}"
        assert SEGREDO not in r.text, f"{metodo} {caminho} ECOOU o valor recusado"
    assert repo.chamadas == []


def test_corpo_que_nao_e_objeto_json_nao_ecoa_nada():
    """Um corpo que e so uma string tambem passaria pelo 422 padrao com `input`."""
    cliente = montar(RepositorioDuble())
    r = cliente.post("/api/cofre/ativos", content=f'"{SEGREDO}"',
                     headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert SEGREDO not in r.text
