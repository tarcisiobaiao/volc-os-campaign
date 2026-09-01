"""`persistencia.py` contra um Postgres DE VERDADE, com a v9_01 aplicada.

## Por que este arquivo não podia ser mais um teste com dublê

O defeito que `persistencia.py` fecha existia **porque tudo era dublado**: a
camada de acesso consultava `volc_trafego_conta`, `volc_trafego_campanha` e
`volc_trafego_sincronizacao`, três tabelas que nenhum schema deste repositório
cria, e as suítes passavam verdes. Um dublê responde o que o teste mandou
responder; ele nunca responde "esta tabela não existe".

Então aqui o banco é real: `initdb` cria um cluster descartável, a v9_01 é
aplicada nele, os testes rodam, o cluster morre. O que continua sendo uma
tradução é o **transporte** — não há PostgREST nesta máquina —, e o shim que faz
essa tradução está abaixo, dito em voz alta. A diferença que importa:

    dublê de banco   → o teste escolhe a resposta. CHECK, gatilho, FK, grant e
                       coluna inexistente NÃO existem.
    shim de HTTP     → o teste escolhe o CAMINHO até o banco. CHECK, gatilho,
                       FK, grant e coluna inexistente decidem o resultado.

⚠️ O shim é o ponto fraco conhecido deste arquivo, e ele é declarado: se o
PostgREST real traduzir algum destes filtros de outro jeito, o teste passa e a
produção falha. Por isso ele implementa SÓ a gramática que `persistencia.py`
emite, e qualquer operador fora dela levanta em vez de ser ignorado — um filtro
novo que o shim não conheça derruba o teste, em vez de sumir da cláusula
`WHERE` e fazer a consulta devolver a tabela inteira.

## O que roda como `service_role`

Toda instrução do shim roda depois de `SET ROLE service_role`, que é o papel do
backend. Grant faltando aparece como falha aqui, e não em produção.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from app.trafego import dominio as dom  # noqa: E402
from app.trafego import inventario as inv  # noqa: E402
from app.trafego import persistencia as pers  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIGRATION = os.path.join(RAIZ, "supabase", "migrations",
                         "v9_01_trafego_inventario.sql")

#: A v9_02 substitui a expressão de `atencao` na view. Ela precisa entrar aqui
#: porque `test_atencao_da_view_concorda_com_pede_atencao` compara a view com
#: `dominio.pede_atencao()`: com só a v9_01 aplicada, a view marca `removida`
#: como atenção e o domínio não, e a discordância seria do CLUSTER, não do
#: código. Um cluster de teste que não reflete o estado aplicado prova a coisa
#: errada com toda a confiança.
MIGRATION_ATENCAO = os.path.join(RAIZ, "supabase", "migrations",
                                 "v9_02_atencao_sem_removida.sql")

#: A v9_03 publica `historico` e `ordem_operacional`. Sem ela o cluster de teste
#: não tem as colunas que `params_de_campanhas` passou a filtrar e a ordenar, e
#: o shim devolveria erro de coluna inexistente — que é exatamente o que este
#: arquivo existe para pegar antes da produção.
MIGRATION_ORDEM = os.path.join(RAIZ, "supabase", "migrations",
                               "v9_03_historico_e_ordem_operacional.sql")

#: A v9_04 põe `url_final` entre os rótulos preservados. Sem ela, uma leitura de
#: anúncio que falha apaga a URL da conta inteira — e a reconciliação, sem o
#: sinal mais forte, volta a oferecer duplicação.
MIGRATION_URL = os.path.join(RAIZ, "supabase", "migrations",
                             "v9_04_url_final_preservada.sql")

#: A v12_02 cria `trafego_campanha_plano_de_mensuracao`, e `CONTRATO_DE_COLUNAS`
#: passou a citá-la. Sem aplicá-la aqui, `test_toda_coluna_do_contrato_existe_no_banco`
#: acusaria a tabela inteira como ausente — que é EXATAMENTE o que ele deve
#: fazer quando o módulo cita o que o schema não tem. O conserto é aplicar a
#: migration, nunca tirar a tabela do contrato.
MIGRATION_PLANO = os.path.join(RAIZ, "supabase", "migrations",
                               "v12_02_plano_de_mensuracao.sql")

pytestmark = pytest.mark.skipif(
    not shutil.which("initdb") or not shutil.which("pg_ctl")
    or not shutil.which("psql"),
    reason="sem PostgreSQL local: instale com `brew install postgresql@16`",
)


# ═══════════════════════════════════════════════════════════════════════════
# O CLUSTER DESCARTÁVEL
# ═══════════════════════════════════════════════════════════════════════════


class ErroDoBanco(RuntimeError):
    """O banco recusou. Carrega a mensagem dele, não uma reescrita."""


class Cluster:
    """Um Postgres que nasce e morre dentro desta sessão de teste.

    ⚠️ `LC_ALL=C LANG=C` valem para o PROCESSO INTEIRO, não só para o `initdb`.
    Medido nesta máquina: com o locale do sistema, o postmaster aborta no
    startup com "became multithreaded during startup" — carregar o locale do
    macOS cria uma thread antes do fork.
    """

    def __init__(self) -> None:
        self.base = tempfile.mkdtemp(prefix="volc-pg-pytest.")
        self.dados = os.path.join(self.base, "dados")
        self.sock = os.path.join(self.base, "sock")
        os.makedirs(self.sock, exist_ok=True)
        self.ambiente = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def subir(self) -> None:
        subprocess.run(["initdb", "-D", self.dados, "-U", "postgres",
                        "--encoding=UTF8", "--locale=C"],
                       check=True, capture_output=True, env=self.ambiente)
        subprocess.run(["pg_ctl", "-D", self.dados,
                        "-l", os.path.join(self.base, "postgres.log"),
                        "-o", f"-k {self.sock} -h ''", "-w", "start"],
                       check=True, capture_output=True, env=self.ambiente)
        # UTC no cluster inteiro. Sem isto, o mesmo instante volta como
        # `09:00-03:00` nesta máquina e como `12:00+00:00` na de outra pessoa —
        # e uma asserção sobre carimbo passaria a depender de onde ela roda.
        self.sql("ALTER DATABASE postgres SET TimeZone TO 'UTC';")
        # Os papéis do Supabase, INCLUSIVE o default ACL quebrado de `public`
        # (achado H). Sem reproduzir o defeito, a prova de que a migration fecha
        # a tabela mediria um ambiente mais seguro que o real.
        self.sql("""
            CREATE ROLE anon          NOLOGIN NOINHERIT;
            CREATE ROLE authenticated NOLOGIN NOINHERIT;
            CREATE ROLE service_role  NOLOGIN NOINHERIT BYPASSRLS;
            GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
              GRANT ALL ON TABLES TO anon, authenticated, service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
              GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
        """)
        self.arquivo(MIGRATION)
        # E a v9_02 logo em seguida: o cluster tem de refletir o estado
        # APLICADO, não o da primeira migration. Sem ela, a view marca
        # `removida` como atenção e discordaria de `pede_atencao()` — uma
        # discordância do ambiente de teste, não do código.
        self.arquivo(MIGRATION_ATENCAO)
        self.arquivo(MIGRATION_ORDEM)
        self.arquivo(MIGRATION_URL)
        self.arquivo(MIGRATION_PLANO)

    def derrubar(self) -> None:
        subprocess.run(["pg_ctl", "-D", self.dados, "-m", "immediate", "stop"],
                       capture_output=True, env=self.ambiente)
        shutil.rmtree(self.base, ignore_errors=True)

    # ── execução ────────────────────────────────────────────────────────────

    def _psql(self, argumentos: List[str], entrada: Optional[str] = None) -> str:
        r = subprocess.run(
            ["psql", "-X", "-q", "-tA", "-h", self.sock, "-U", "postgres",
             "-d", "postgres", "-v", "ON_ERROR_STOP=1", *argumentos],
            input=entrada, capture_output=True, text=True, env=self.ambiente)
        if r.returncode != 0:
            raise ErroDoBanco((r.stderr or r.stdout).strip())
        return r.stdout

    def sql(self, comando: str) -> str:
        return self._psql([], entrada=comando)

    def arquivo(self, caminho: str) -> str:
        return self._psql(["-f", caminho])

    def valor(self, consulta: str, *, papel: str = "postgres") -> str:
        return self._psql([], entrada=f"SET ROLE {papel};\n{consulta}").strip()

    def escrever(self, comando: str, *, papel: str = "service_role") -> List[Dict[str, Any]]:
        """`INSERT`/`UPDATE` com `RETURNING`, devolvido como JSON.

        Precisa de caminho próprio porque um CTE que ESCREVE tem de estar no topo
        da instrução: `SELECT ... FROM (WITH r AS (INSERT ...) ...)` é recusado
        pelo Postgres, e era assim que `linhas()` embrulhava tudo.
        """
        bruto = self._psql([], entrada=(
            f"SET ROLE {papel};\n"
            f"WITH r AS ({comando} RETURNING *) "
            f"SELECT coalesce(json_agg(r), '[]'::json) FROM r;"))
        return json.loads(bruto.strip() or "[]")

    def linhas(self, consulta: str, *, papel: str = "postgres") -> List[Dict[str, Any]]:
        """`json_agg` em vez de colunas separadas por caractere.

        Tipo preservado: `0` volta inteiro e `NULL` volta `None`. Com saída de
        texto os dois virariam string, e este arquivo inteiro existe para provar
        que ausência e zero não se confundem.
        """
        bruto = self._psql([], entrada=(
            f"SET ROLE {papel};\n"
            f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({consulta}) t;"))
        return json.loads(bruto.strip() or "[]")


@pytest.fixture(scope="module")
def banco() -> Cluster:
    c = Cluster()
    try:
        c.subir()
    except Exception:
        c.derrubar()
        raise
    yield c
    c.derrubar()


# ═══════════════════════════════════════════════════════════════════════════
# O SHIM DE POSTGREST — traduz a requisição em SQL. O BANCO É O REAL.
# ═══════════════════════════════════════════════════════════════════════════

_OPERADORES = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<",
               "lte": "<=", "like": "LIKE", "ilike": "ILIKE"}
_RESERVADOS = {"select", "order", "limit", "offset", "on_conflict",
               "or", "and", "columns"}


def _literal(valor: str) -> str:
    return "'" + str(valor).replace("'", "''") + "'"


def _lista_do_in(bruto: str) -> List[str]:
    """`(a,b,"c, d")` → os três valores. Aspas protegem vírgula, como no real."""
    dentro = bruto.strip()
    assert dentro.startswith("(") and dentro.endswith(")"), bruto
    itens, atual, aspas = [], "", False
    for ch in dentro[1:-1]:
        if ch == '"':
            aspas = not aspas
        elif ch == "," and not aspas:
            itens.append(atual)
            atual = ""
        else:
            atual += ch
    if atual or itens:
        itens.append(atual)
    return itens


def _fatiar(bruto: str) -> List[str]:
    """Vírgulas de profundidade ZERO. `and(a,b)` continua inteiro."""
    itens, atual, nivel, aspas = [], "", 0, False
    for ch in bruto:
        if ch == '"':
            aspas = not aspas
        if not aspas:
            if ch == "(":
                nivel += 1
            elif ch == ")":
                nivel -= 1
            elif ch == "," and nivel == 0:
                itens.append(atual)
                atual = ""
                continue
        atual += ch
    if atual:
        itens.append(atual)
    return itens


def _condicao(coluna: str, expressao: str) -> str:
    """`col`, `not.in.(a,b)` → `NOT (col IN ('a','b'))`.

    ⚠️ Operador desconhecido LEVANTA. Ignorá-lo faria a cláusula sumir do WHERE
    e a consulta devolver a tabela inteira — que é o modo silencioso de um
    filtro deixar de existir.
    """
    negado = expressao.startswith("not.")
    if negado:
        expressao = expressao[4:]
    operador, _, valor = expressao.partition(".")

    if operador == "in":
        itens = _lista_do_in(valor)
        sql = f"{coluna} IN ({', '.join(_literal(v) for v in itens)})"
    elif operador == "is":
        alvo = valor.strip().lower()
        if alvo not in ("null", "true", "false"):
            raise AssertionError(f"`is.{valor}` não é gramática do PostgREST")
        sql = f"{coluna} IS {alvo.upper()}"
    elif operador in _OPERADORES:
        # `*` é o coringa do PostgREST; `%` é o do SQL.
        literal = valor.replace("*", "%") if operador in ("like", "ilike") else valor
        sql = f"{coluna} {_OPERADORES[operador]} {_literal(literal)}"
    else:
        raise AssertionError(
            f"o shim não conhece o operador {operador!r} (coluna {coluna!r}). "
            f"Ensine-o aqui em vez de deixar o filtro sumir do WHERE.")
    return f"NOT ({sql})" if negado else sql


def _arvore(bruto: str) -> str:
    """`(a,and(b,c))` → `(a AND (b AND c))`. Recursivo, como o real."""
    texto = bruto.strip()
    partes = []
    for item in _fatiar(texto[1:-1] if texto.startswith("(") else texto):
        item = item.strip()
        if item.startswith("or(") or item.startswith("and("):
            juncao = " OR " if item.startswith("or(") else " AND "
            interno = item[item.index("(") + 1:-1]
            partes.append("(" + juncao.join(
                _arvore(p.strip()) for p in _fatiar(interno)) + ")")
        else:
            coluna, _, resto = item.partition(".")
            partes.append(_condicao(coluna, resto))
    return partes[0] if len(partes) == 1 else "(" + " AND ".join(partes) + ")"


def _onde(params: Dict[str, str]) -> str:
    condicoes: List[str] = []
    for chave, valor in params.items():
        if chave in _RESERVADOS:
            continue
        condicoes.append(_condicao(chave, valor))
    if "or" in params:
        interno = params["or"]
        condicoes.append("(" + " OR ".join(
            _arvore(p.strip()) for p in _fatiar(interno[1:-1])) + ")")
    if "and" in params:
        interno = params["and"]
        condicoes.append("(" + " AND ".join(
            _arvore(p.strip()) for p in _fatiar(interno[1:-1])) + ")")
    return " WHERE " + " AND ".join(condicoes) if condicoes else ""


def _select(alvo: str, params: Dict[str, str]) -> str:
    colunas = params.get("select", "*")
    sql = f"SELECT {colunas} FROM public.{alvo}{_onde(params)}"
    if params.get("order"):
        pedacos = []
        for termo in params["order"].split(","):
            coluna, _, direcao = termo.partition(".")
            pedacos.append(f"{coluna} {(direcao or 'asc').upper()}")
        sql += " ORDER BY " + ", ".join(pedacos)
    if params.get("limit"):
        sql += f" LIMIT {int(params['limit'])}"
    return sql


def shim_de_postgrest(banco: Cluster) -> httpx.MockTransport:
    """Um PostgREST de mentira na frente de um Postgres de verdade."""

    def responder(req: httpx.Request) -> httpx.Response:
        alvo = req.url.path.rsplit("/", 1)[-1]
        params = dict(req.url.params)
        prefer = req.headers.get("Prefer", "")
        devolve = "return=representation" in prefer
        try:
            if req.method in ("GET", "HEAD"):
                if "count=exact" in prefer:
                    total = banco.valor(
                        f"SELECT count(*) FROM ({_select(alvo, {k: v for k, v in params.items() if k != 'limit'})}) c;",
                        papel="service_role")
                    return httpx.Response(
                        206, headers={"content-range": f"0-0/{total.strip()}"})
                return httpx.Response(
                    200, json=banco.linhas(_select(alvo, params),
                                           papel="service_role"))

            corpo = json.loads(req.content.decode("utf-8"))

            if req.method == "POST":
                carga = json.dumps(corpo).replace("'", "''")
                colunas = ", ".join(corpo[0].keys())
                conflito = params.get("on_conflict")
                sql = (f"INSERT INTO public.{alvo} ({colunas}) "
                       f"SELECT {colunas} FROM jsonb_populate_recordset("
                       f"null::public.{alvo}, '{carga}'::jsonb)")
                if "resolution=merge-duplicates" in prefer:
                    setagem = ", ".join(f"{c} = EXCLUDED.{c}" for c in corpo[0])
                    sql += f" ON CONFLICT ({conflito}) DO UPDATE SET {setagem}"
                elif "resolution=ignore-duplicates" in prefer:
                    sql += f" ON CONFLICT ({conflito}) DO NOTHING"
                return _executar(banco, sql, devolve)

            if req.method == "PATCH":
                carga = json.dumps(corpo).replace("'", "''")
                colunas = ", ".join(corpo.keys())
                sql = (f"UPDATE public.{alvo} SET ({colunas}) = "
                       f"(SELECT {colunas} FROM jsonb_populate_record("
                       f"null::public.{alvo}, '{carga}'::jsonb))"
                       f"{_onde(params)}")
                return _executar(banco, sql, devolve)
        except ErroDoBanco as exc:
            # É assim que o PostgREST responde violação de CHECK, de gatilho e
            # de privilégio: 400 com a mensagem do Postgres no corpo.
            return httpx.Response(400, json={"message": str(exc)})

        raise AssertionError(f"o shim não conhece {req.method} {req.url}")

    return httpx.MockTransport(responder)


def _executar(banco: Cluster, sql: str, devolve: bool) -> httpx.Response:
    if devolve:
        return httpx.Response(201, json=banco.escrever(sql))
    banco.sql(f"SET ROLE service_role;\n{sql};")
    return httpx.Response(204)


@pytest.fixture()
def ligado(banco: Cluster, monkeypatch: pytest.MonkeyPatch) -> Cluster:
    """Aponta o `httpx` de `persistencia.py` para o shim, e limpa o banco."""
    transporte = shim_de_postgrest(banco)
    original = httpx.AsyncClient

    def fabricar(*a: Any, **kw: Any) -> httpx.AsyncClient:
        kw["transport"] = transporte
        return original(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", fabricar)
    # `trafego_evento` é append-only por gatilho; TRUNCATE não passa por ele, e
    # aqui isso é desejado — o gatilho protege o domínio, não a bancada.
    banco.sql("TRUNCATE public.trafego_evento, public.trafego_vinculo, "
              "public.trafego_campanha_espelho, public.trafego_campanha, "
              "public.trafego_snapshot_conta, public.trafego_linhagem CASCADE;")
    return banco


def rodar(corotina: Any) -> Any:
    return asyncio.run(corotina)


def _repo() -> pers.RepositorioDeSnapshotSupabase:
    return pers.RepositorioDeSnapshotSupabase("http://postgrest.local", "chave")


def _fonte() -> pers.FonteDeInventarioSupabase:
    return pers.FonteDeInventarioSupabase("http://postgrest.local", "chave")


AGORA = "2026-08-25T12:00:00+00:00"


def _campanha(campaign_id: str, **extra: Any) -> Dict[str, Any]:
    linha: Dict[str, Any] = {
        "volc_campaign_id": f"gads-8017851692-{campaign_id}",
        "customer_id": "8017851692",
        "campaign_id": campaign_id,
        "nome": f"Campanha {campaign_id}",
        "estado_externo": "ENABLED",
        "veiculacao": "SERVING",
        "canal": "SEARCH",
        "canal_bruto": "SEARCH",
        "estrategia": "MANUAL_CPC",
        "estrategia_bruta": "MANUAL_CPC",
        "verba_diaria_micros": 10_000_000,
        "lance_micros": 120_000,
        "moeda": "BRL",
        "presenca": dom.PRESENTE,
        "lido_em": AGORA,
    }
    linha.update(extra)
    return linha


def _conta(**extra: Any) -> Dict[str, Any]:
    linha = {"customer_id": "8017851692", "nome": "Credito Up",
             "resultado": "ok", "lido_em": AGORA,
             "ultima_leitura_boa_em": AGORA, "lidas": 2, "falhas": 0,
             "duracao_ms": 2400}
    linha.update(extra)
    return linha


# ═══════════════════════════════════════════════════════════════════════════
# 1. O CONTRATO — cada coluna que o módulo cita existe no schema de verdade
# ═══════════════════════════════════════════════════════════════════════════


def test_toda_coluna_do_contrato_existe_no_banco(banco: Cluster) -> None:
    """O gate que teria pego o defeito original no dia em que ele nasceu.

    `volc_trafego_conta` não existia; nenhum teste com dublê podia perceber. Aqui
    a lista de colunas do módulo é conferida contra `information_schema` de um
    banco com a v9_01 aplicada — tabela inexistente devolve zero colunas e o
    teste morre dizendo o nome dela.
    """
    reais = {}
    for linha in banco.linhas(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name LIKE 'trafego\\_%'"):
        reais.setdefault(linha["table_name"], set()).add(linha["column_name"])

    faltando: Dict[str, List[str]] = {}
    for relacao, colunas in pers.CONTRATO_DE_COLUNAS.items():
        ausentes = sorted(set(colunas) - reais.get(relacao, set()))
        if ausentes:
            faltando[relacao] = ausentes
    assert not faltando, f"o módulo cita o que o schema não tem: {faltando}"


def test_service_role_alcanca_o_que_o_modulo_usa(banco: Cluster) -> None:
    """Grant faltando aparece aqui, não em produção às duas da manhã."""
    for relacao in pers.CONTRATO_DE_COLUNAS:
        pode = banco.valor(
            f"SELECT has_table_privilege('service_role', "
            f"'public.{relacao}', 'SELECT')")
        assert pode == "t", f"service_role não lê {relacao}"


def test_anon_nao_alcanca_nem_as_views(banco: Cluster) -> None:
    """A view é o caminho mais fácil de furar a RLS das seis tabelas.

    Uma view sem `security_invoker` roda com os privilégios do DONO: quem
    tivesse SELECT nela leria tudo, por cima de toda a contenção. Aqui o teste
    troca de papel de verdade em vez de inspecionar catálogo — só `SET ROLE`
    prova que a operação falha.
    """
    for view in (pers.VIEW_CAMPANHAS, pers.VIEW_CONTAS):
        with pytest.raises(ErroDoBanco) as erro:
            banco.valor(f"SELECT count(*) FROM public.{view}", papel="anon")
        assert "permission denied" in str(erro.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 2. ESCRITA — a varredura chega ao banco canônico
# ═══════════════════════════════════════════════════════════════════════════


def test_gravar_campanhas_separa_identidade_de_espelho(ligado: Cluster) -> None:
    """A separação que conserta E-08, verificada onde ela existe: no banco."""
    rodar(_repo().gravar_campanhas([_campanha("24155134757")]))

    identidade = ligado.linhas("SELECT * FROM public.trafego_campanha")
    assert len(identidade) == 1
    assert identidade[0]["procedencia"] == "desconhecida", (
        "a varredura não sabe quem criou a campanha; declarar procedência aqui "
        "seria afirmar o que ninguém observou")
    assert identidade[0]["criada_por"] == pers.PRODUTOR_VARREDURA

    espelho = ligado.linhas("SELECT * FROM public.trafego_campanha_espelho")
    assert len(espelho) == 1
    assert espelho[0]["nome"] == "Campanha 24155134757"
    assert "customer_id" not in espelho[0], (
        "identidade não se repete no espelho — duas cópias do mesmo fato é como "
        "duas verdades começam a divergir")


def test_presente_vira_nulo_no_banco(ligado: Cluster) -> None:
    """Sete valores na API, seis no banco. Sem a tradução, tudo estoura.

    A CHECK `trafego_espelho_presenca_conhecida` recusa `presente`. Se
    `persistencia.py` mandasse o valor cru, TODA campanha viva derrubaria a
    gravação do lote e a varredura inteira da conta iria para o ramo de falha —
    apagando o inventário de uma conta que respondeu perfeitamente.
    """
    rodar(_repo().gravar_campanhas([_campanha("1"), _campanha("2", presenca="removida")]))
    guardado = {l["volc_campaign_id"]: l["presenca"] for l in
                ligado.linhas("SELECT volc_campaign_id, presenca "
                              "FROM public.trafego_campanha_espelho")}
    assert guardado["gads-8017851692-1"] is None
    assert guardado["gads-8017851692-2"] == "removida"

    # E a volta: o nulo projeta `presente`, e o módulo nunca grava o termo que a
    # view usa para "campanha sem espelho".
    projetado = ligado.linhas(
        f"SELECT presenca FROM public.{pers.VIEW_CAMPANHAS} "
        "WHERE volc_campaign_id = 'gads-8017851692-1'")
    assert projetado[0]["presenca"] is None
    assert dom.presenca_projetada(projetado[0]["presenca"], conta_falhou=False) \
        == dom.PRESENTE


def test_entrega_so_entra_com_carimbo(ligado: Cluster) -> None:
    """Regra A no caminho real: número sem data não chega ao banco."""
    rodar(_repo().gravar_campanhas([
        _campanha("1", impressoes=1, cliques=0, custo_micros=0,
                  entrega_lida_em=AGORA),
        # Sem `entrega_lida_em`: as três colunas nem entram no payload.
        _campanha("2", impressoes=99, cliques=99, custo_micros=99),
    ]))
    linhas = {l["volc_campaign_id"]: l for l in ligado.linhas(
        "SELECT volc_campaign_id, impressoes, cliques, custo_micros, "
        "entrega_lida_em, moeda FROM public.trafego_campanha_espelho")}

    assert linhas["gads-8017851692-1"]["impressoes"] == 1
    assert linhas["gads-8017851692-1"]["cliques"] == 0, "zero medido é zero"
    assert linhas["gads-8017851692-2"]["impressoes"] is None, (
        "número sem carimbo não vira zero nem entra: ele simplesmente não é fato")
    assert linhas["gads-8017851692-2"]["moeda"] == "BRL", (
        "moeda é unidade, não medida — ela denomina a verba, que tem outro carimbo")


def test_falha_de_entrega_nao_apaga_a_ultima_medida_nem_o_nome(ligado: Cluster) -> None:
    """Regra C dentro da linha, com o gatilho de verdade decidindo.

    O lote uniforme do PostgREST manda `impressoes: null` para a campanha que não
    teve entrega medida — é o gatilho que impede isso de apagar a última medição.
    E os rótulos: uma leitura que não trouxe `nome` deixaria a linha SEM NOME na
    tela, e uma campanha sem nome não é operável.
    """
    rodar(_repo().gravar_campanhas([
        _campanha("1", impressoes=7, cliques=3, custo_micros=500,
                  entrega_lida_em=AGORA)]))
    rodar(_repo().gravar_campanhas([{
        "volc_campaign_id": "gads-8017851692-1",
        "customer_id": "8017851692", "campaign_id": "1",
        "lido_em": "2026-08-25T13:00:00+00:00",
        "presenca": dom.PRESENTE,
        "nome": None, "estado_externo": None, "canal": None,
        "estrategia": None, "lance_micros": None,
    }]))
    linha = ligado.linhas("SELECT * FROM public.trafego_campanha_espelho")[0]

    assert linha["impressoes"] == 7 and linha["custo_micros"] == 500
    assert linha["entrega_lida_em"].startswith("2026-08-25T12:00"), (
        "o carimbo da medida preservada veio junto — número velho com data nova "
        "seria pior que apagar")
    assert linha["nome"] == "Campanha 1", "rótulo se preserva"
    assert linha["estado_externo"] == "ENABLED" and linha["canal"] == "SEARCH"
    assert linha["estrategia"] is None, (
        "estratégia MUDA na vida da campanha e o nulo pode ser medição: "
        "preservá-la calcularia um teto de cliques que não existe")
    assert linha["lance_micros"] is None, "número não se preserva sem carimbo"


def test_gravar_conta_traduz_e_o_gatilho_guarda_a_ultima_boa(ligado: Cluster) -> None:
    """Uma falha nova não apaga a última leitura BOA — nem o escritor precisa lembrar."""
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_conta(_conta(
        resultado="falhou", motivo="USER_PERMISSION_DENIED",
        lido_em="2026-08-25T13:00:00+00:00", ultima_leitura_boa_em=None,
        lidas=None)))

    linha = ligado.linhas("SELECT * FROM public.trafego_snapshot_conta")[0]
    assert linha["tentativa_resultado"] == "falhou"
    assert linha["tentativa_motivo"] == "USER_PERMISSION_DENIED"
    assert linha["leitura_boa_campanhas"] == 2, "a última leitura boa sobreviveu"
    assert linha["leitura_boa_em"].startswith("2026-08-25T12:00")


def test_motivo_da_falha_nao_sobrevive_a_leitura_boa_seguinte(ligado: Cluster) -> None:
    """O nulo é ENVIADO de propósito.

    A versão antiga removia chaves nulas do payload para proteger a leitura boa.
    O efeito colateral era este: o motivo da falha anterior continuava na linha
    depois de uma leitura perfeita, e a tela mostrava um erro que já não existia.
    """
    rodar(_repo().gravar_conta(_conta(resultado="falhou", motivo="TIMEOUT",
                                      ultima_leitura_boa_em=None, lidas=None)))
    rodar(_repo().gravar_conta(_conta(lido_em="2026-08-25T13:00:00+00:00")))
    linha = ligado.linhas("SELECT * FROM public.trafego_snapshot_conta")[0]
    assert linha["tentativa_resultado"] == "ok"
    assert linha["tentativa_motivo"] is None


def test_parcial_sobrevive_como_resultado(ligado: Cluster) -> None:
    """Regra E: frescor desconhecido NUNCA degrada para `recente`.

    Se `parcial` virasse `ok` na gravação, `frescor_da_conta()` responderia
    `recente` para uma conta que não entregou metade do que foi pedido — e o
    operador não teria nada na tela dizendo isso.
    """
    rodar(_repo().gravar_conta(_conta(
        resultado="parcial", motivo="entrega não voltou",
        escopo_parcial="entrega(ultimos_7d)")))
    linha = ligado.linhas(
        f"SELECT * FROM public.{pers.VIEW_CONTAS}")[0]
    assert linha["tentativa_resultado"] == "parcial"
    assert linha["escopo_parcial"] == "entrega(ultimos_7d)"
    assert inv.frescor_da_conta(inv.normalizar_linha_de_conta(linha)) == inv.PARCIAL


def test_marcar_ausentes_alcanca_so_a_conta_e_so_quem_sumiu(ligado: Cluster) -> None:
    """O espelho não tem `customer_id`; o alvo sai da identidade, não de um `like`."""
    import datetime as dt

    rodar(_repo().gravar_campanhas([_campanha("1"), _campanha("2")]))
    rodar(_repo().gravar_campanhas([{
        **_campanha("9"), "volc_campaign_id": "gads-3849678045-9",
        "customer_id": "3849678045"}]))

    # ⚠️ `vistos` são `volc_campaign_id`, como a porta documenta — NÃO
    # `campaign_id`. Este teste passava `["1"]` (o id externo) e continuava
    # verde porque a implementação também filtrava pela coluna errada: os dois
    # lados estavam errados do mesmo jeito, e o erro se cancelava.
    #
    # Na primeira varredura real ele apareceu inteiro: 84 campanhas lidas com
    # sucesso e marcadas `nao_encontrada`, porque um UUID nunca casa com um id
    # do Google.
    marcadas = rodar(_repo().marcar_ausentes(
        "8017851692", ["gads-8017851692-1"],
        dt.datetime(2026, 8, 25, 13, tzinfo=dt.timezone.utc)))
    assert marcadas == 1

    guardado = {l["volc_campaign_id"]: l["presenca"] for l in ligado.linhas(
        "SELECT volc_campaign_id, presenca FROM public.trafego_campanha_espelho")}
    assert guardado["gads-8017851692-1"] is None, "vista na varredura, intacta"
    assert guardado["gads-8017851692-2"] == "nao_encontrada"
    assert guardado["gads-3849678045-9"] is None, (
        "outra conta não é tocada — falha ou ausência de uma não contamina a outra")

    # Idempotente: rodar de novo não empurra `lido_em` para frente sem fato novo.
    # Mesmo `vistos` da chamada anterior — e no vocabulário certo.
    assert rodar(_repo().marcar_ausentes(
        "8017851692", ["gads-8017851692-1"],
        dt.datetime(2026, 8, 25, 14, tzinfo=dt.timezone.utc))) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. O DIÁRIO — idempotência que permite retry depois de fracasso
# ═══════════════════════════════════════════════════════════════════════════


def test_registro_vai_para_o_diario_e_volta_pela_chave(ligado: Cluster) -> None:
    registro = {"chave_idempotencia": "abc123", "customer_id": "8017851692",
                "janela": "ultimos_7d", "origem": "agendado",
                "iniciado_em": AGORA, "duracao_ms": 2400, "resultado": "ok",
                "lidas": 2, "falhas": 0, "consultas": 3,
                "detalhe": {"faltou": [], "marcadas_ausentes": 0}}
    rodar(_repo().registrar_sincronizacao(registro))

    achado = rodar(_repo().sincronizacao_por_chave("abc123"))
    assert achado["resultado"] == "ok" and achado["lidas"] == 2
    assert achado["chave_idempotencia"] == "abc123"
    assert achado["detalhe"] == {"faltou": [], "marcadas_ausentes": 0}

    assert rodar(_repo().ultima_sincronizacao("8017851692"))["janela"] == "ultimos_7d"
    assert rodar(_repo().sincronizacao_por_chave("nao-existe")) is None


def test_falha_memorizada_nao_bloqueia_o_retry(ligado: Cluster) -> None:
    """Regra D. Idempotência existe para não repetir trabalho FEITO.

    Uma falha não é trabalho feito; é justamente o que o retry veio refazer. O
    diário é append-only, então a mesma chave tem as duas linhas — e a que
    responde é a mais recente.
    """
    base = {"chave_idempotencia": "k1", "customer_id": "8017851692",
            "janela": "ultimos_7d", "origem": "agendado", "lidas": 0}
    rodar(_repo().registrar_sincronizacao(
        {**base, "iniciado_em": AGORA, "resultado": "falhou"}))
    assert rodar(_repo().sincronizacao_por_chave("k1"))["resultado"] == "falhou"

    rodar(_repo().registrar_sincronizacao(
        {**base, "iniciado_em": "2026-08-25T13:00:00+00:00",
         "resultado": "ok", "lidas": 2}))
    depois = rodar(_repo().sincronizacao_por_chave("k1"))
    assert depois["resultado"] == "ok" and depois["lidas"] == 2

    assert ligado.valor("SELECT count(*) FROM public.trafego_evento "
                        "WHERE chave_de_agrupamento = 'k1'") == "2", (
        "as duas tentativas ficam registradas: o diário não reescreve o passado")


def test_varredura_sem_chave_nunca_e_memorizada(ligado: Cluster) -> None:
    """Chave derivada leva o INSTANTE, e é por isso que ela nunca casa depois.

    Uma chave derivada só da conta faria toda varredura sem chave parecer "já
    rodei" para a seguinte — memorizando trabalho que ninguém pediu para
    memorizar.
    """
    rodar(_repo().registrar_sincronizacao(
        {"chave_idempotencia": None, "customer_id": "8017851692",
         "iniciado_em": AGORA, "resultado": "ok"}))
    chaves = [l["chave_de_agrupamento"] for l in
              ligado.linhas("SELECT chave_de_agrupamento FROM public.trafego_evento "
                            "WHERE produtor = 'backend:sincronizador'")]
    assert chaves and AGORA in chaves[0]


def test_gatilho_do_banco_e_o_registro_da_aplicacao_nao_se_confundem(ligado: Cluster) -> None:
    """Dois produtores, dois tipos. Fundi-los faria a contagem contar duas vezes."""
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().registrar_sincronizacao(
        {"chave_idempotencia": "x", "customer_id": "8017851692",
         "iniciado_em": AGORA, "resultado": "ok"}))
    tipos = {l["tipo"]: l["produtor"] for l in ligado.linhas(
        "SELECT tipo, produtor FROM public.trafego_evento")}
    assert tipos["sincronizacao.conta.ok"] == "banco:trafego_snapshot_registra_tentativa"
    assert tipos["sincronizacao.registro.ok"] == "backend:sincronizador"


# ═══════════════════════════════════════════════════════════════════════════
# 4. LEITURA — a projeção completa, saindo das views
# ═══════════════════════════════════════════════════════════════════════════


def test_inventario_completo_sai_do_banco(ligado: Cluster) -> None:
    """O caminho inteiro: varredura grava, `montar_inventario` lê e projeta."""
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", impressoes=1, cliques=0, custo_micros=0,
                  entrega_lida_em=AGORA),
        _campanha("2", impressoes=4, cliques=2, custo_micros=8000,
                  entrega_lida_em=AGORA),
    ]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    inventario = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(), agora=agora))

    assert inventario.totais["operacionais"] == 2
    assert inventario.totais["historicas"] == 0
    assert inventario.totais["geral"] == 2
    assert inventario.frescor == inv.RECENTE
    assert [c.customer_id for c in inventario.contas] == ["8017851692"]
    campanhas = {c.externa.campaign_id: c for c in inventario.contas[0].campanhas}
    assert campanhas["1"].nome == "Campanha 1"
    assert campanhas["1"].presenca == dom.PRESENTE
    assert campanhas["1"].entrega.impressoes == 1
    assert campanhas["1"].entrega.cliques == 0, "zero medido chega como zero"
    assert campanhas["1"].teto_de_cliques == 10_000_000 // 120_000
    assert campanhas["1"].vinculo is None


def test_conta_que_falhou_nao_apaga_o_ultimo_snapshot_bom(ligado: Cluster) -> None:
    """Regra C ponta a ponta: a falha muda o RÓTULO, não o dado."""
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([_campanha("1")]))
    rodar(_repo().gravar_conta(_conta(
        resultado="falhou", motivo="USER_PERMISSION_DENIED",
        lido_em="2026-08-25T13:00:00+00:00", ultima_leitura_boa_em=None,
        lidas=None)))

    import datetime as dt
    inventario = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(),
        agora=dt.datetime(2026, 8, 25, 13, 5, tzinfo=dt.timezone.utc)))

    conta = inventario.contas[0]
    assert conta.frescor == inv.FALHOU
    assert inventario.parcial and inventario.faltou[0].motivo == "USER_PERMISSION_DENIED"
    assert conta.ultima_leitura_boa is not None, (
        "a última leitura boa continua visível, com a idade dela à mostra")
    assert conta.campanhas[0].nome == "Campanha 1", "o snapshot continua na tela"
    assert conta.campanhas[0].presenca == inv.SINCRONIZACAO_FALHOU


def test_campanha_sem_espelho_nao_e_declarada_presente(ligado: Cluster) -> None:
    """A janela entre "o operador criou" e "a varredura passou".

    Nulo em `presenca` significa "presente, sem ressalva". Uma campanha que
    NUNCA foi lida não pode herdar essa afirmação — ninguém observou nada sobre
    ela. A view projeta um termo fora do vocabulário e a leitura degrada sozinha
    para a afirmação mais fraca disponível.
    """
    ligado.sql(
        "INSERT INTO public.trafego_campanha "
        "(volc_campaign_id, customer_id, campaign_id, criada_por) "
        "VALUES ('gads-8017851692-77','8017851692','77','porta-de-criacao');")
    rodar(_repo().gravar_conta(_conta()))

    linha = ligado.linhas(
        f"SELECT presenca, atencao FROM public.{pers.VIEW_CAMPANHAS}")[0]
    assert linha["presenca"] == pers.PRESENCA_NAO_ESPELHADA
    assert linha["atencao"] is True
    assert dom.presenca_projetada(linha["presenca"], conta_falhou=False) \
        == "conta_nao_identificada"
    assert linha["presenca"] not in dom.ESTADOS_DE_PRESENCA, (
        "está fora das seis de propósito: é o que faz a degradação ser automática")


def test_atencao_da_view_concorda_com_pede_atencao(ligado: Cluster) -> None:
    """UMA regra, dois lugares. Se discordarem, o sino e a aba mentem juntos.

    O filtro `?atencao=true` e a contagem do sino resolvem NO BANCO (senão a
    paginação mente e o sino conta só a página corrente); a aba e o quadro de
    alertas resolvem em Python. As duas expressões precisam ser a mesma, e é
    isto que prova que são.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_conta({**_conta(), "customer_id": "3849678045",
                                "resultado": "falhou", "motivo": "TIMEOUT",
                                "ultima_leitura_boa_em": None, "lidas": None}))
    casos = [
        _campanha("1", impressoes=5, cliques=2, custo_micros=90, entrega_lida_em=AGORA),
        _campanha("2", impressoes=0, cliques=0, custo_micros=0, entrega_lida_em=AGORA),
        _campanha("3", impressoes=9, cliques=0, custo_micros=90, entrega_lida_em=AGORA),
        _campanha("4"),
        _campanha("5", estado_externo="PAUSED"),
        _campanha("6", estado_externo="PAUSED", impressoes=0, cliques=0,
                  custo_micros=0, entrega_lida_em=AGORA),
        _campanha("7", estado_externo="REMOVED", presenca="removida"),
        {**_campanha("8"), "volc_campaign_id": "gads-3849678045-8",
         "customer_id": "3849678045"},
    ]
    rodar(_repo().gravar_campanhas(casos))

    discordancias = []
    for linha in ligado.linhas(f"SELECT * FROM public.{pers.VIEW_CAMPANHAS}"):
        esperado = dom.pede_atencao(
            presenca_armazenada=linha["presenca"],
            estado_externo=linha["estado_externo"],
            impressoes=linha["impressoes"],
            cliques=linha["cliques"],
            entrega_medida=linha["entrega_lida_em"] is not None,
            conta_falhou=linha["tentativa_resultado"] == "falhou")
        if linha["atencao"] != esperado:
            discordancias.append((linha["volc_campaign_id"], linha["atencao"],
                                  esperado))
    assert not discordancias, (
        f"view e dominio.pede_atencao() discordam: {discordancias}")


def test_filtro_de_atencao_e_a_contagem_saem_do_banco(ligado: Cluster) -> None:
    """`?atencao=true` sem coluna gerada: a projeção da view resolve.

    A condição era uma coluna GERADA que só existia na DDL apagada. Se ela
    voltasse a ser aplicada em Python, o limite cortaria ANTES do filtro e a
    paginação passaria a mentir.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", impressoes=5, cliques=2, custo_micros=90, entrega_lida_em=AGORA),
        _campanha("2", impressoes=0, cliques=0, custo_micros=0, entrega_lida_em=AGORA),
        _campanha("3"),
    ]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    todas = rodar(inv.montar_inventario(_fonte(), inv.FiltrosDoInventario(),
                                        agora=agora))
    assert todas.totais["operacionais"] == 3 and todas.totais["atencao"] == 2

    so_atencao = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(atencao=True), agora=agora))
    assert {c.externa.campaign_id for c in so_atencao.contas[0].campanhas} == {"2", "3"}

    sem_atencao = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(atencao=False), agora=agora))
    assert {c.externa.campaign_id for c in sem_atencao.contas[0].campanhas} == {"1"}


def test_paginacao_por_cursor_nao_pula_nem_repete(ligado: Cluster) -> None:
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([_campanha(str(n)) for n in range(1, 6)]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    vistas: List[str] = []
    cursor = None
    for _ in range(5):
        pagina = rodar(inv.montar_inventario(
            _fonte(), inv.FiltrosDoInventario(), limite=2, cursor=cursor,
            agora=agora))
        vistas += [c.externa.campaign_id for c in pagina.contas[0].campanhas]
        cursor = pagina.proximo_cursor
        if not cursor:
            break
    assert sorted(vistas) == ["1", "2", "3", "4", "5"]
    assert len(vistas) == len(set(vistas)), "nenhuma campanha apareceu duas vezes"


def test_a_guarda_de_numero_sem_carimbo_sobrevive_a_v9_04(ligado: Cluster) -> None:
    """`CREATE OR REPLACE FUNCTION` substitui o CORPO INTEIRO.

    Reescrever uma função de gatilho para acrescentar uma linha apaga tudo o que
    não for copiado de volta, em silêncio. Foi o que a primeira versão da v9_04
    fez com a guarda "nenhum número sem carimbo" — a regra A do schema —, e só a
    auditoria adversarial contra um Postgres real a pegou.

    Este teste existe para que a próxima migration que tocar nesta função não
    consiga apagá-la de novo.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", impressoes=10, cliques=1, custo_micros=5,
                  entrega_lida_em=AGORA),
    ]))

    with pytest.raises(Exception) as exc:
        ligado.sql(
            "SET ROLE service_role; "
            "UPDATE public.trafego_campanha_espelho "
            "   SET lido_em = '2026-08-25T13:00:00Z', impressoes = 99, "
            "       entrega_lida_em = NULL "
            " WHERE volc_campaign_id = 'gads-8017851692-1';")
    assert "sem carimbo" in str(exc.value), str(exc.value)[:200]


def test_url_final_sobrevive_a_leitura_que_nao_a_trouxe(ligado: Cluster) -> None:
    """A URL é rótulo, não medida — e é o sinal mais forte da reconciliação.

    Sem preservação, uma leitura de anúncio que falha manda `url_final: null`
    para a conta inteira (o payload é uniformizado) e apaga o destino de todas
    as campanhas. A reconciliação, sem o sinal, volta a responder `sem_campanha`
    e a convidar o operador a montar uma segunda campanha para o mesmo termo.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", url_final="https://creditoup.com.br/r/fgts-saque-aniversario/"),
    ]))

    # A varredura seguinte não trouxe URL: o perfil não conseguiu ler o anúncio.
    rodar(_repo().gravar_campanhas([
        _campanha("1", url_final=None, lido_em="2026-08-25T13:00:00+00:00"),
    ]))
    linha = ligado.linhas(
        "SELECT url_final, lido_em FROM public.trafego_campanha_espelho")[0]
    assert linha["url_final"] == "https://creditoup.com.br/r/fgts-saque-aniversario/"

    # E uma URL NOVA substitui — preservar não é congelar.
    rodar(_repo().gravar_campanhas([
        _campanha("1", url_final="https://creditoup.com.br/r/outra/",
                  lido_em="2026-08-25T14:00:00+00:00"),
    ]))
    assert ligado.linhas(
        "SELECT url_final FROM public.trafego_campanha_espelho"
    )[0]["url_final"] == "https://creditoup.com.br/r/outra/"


def test_removed_fica_fora_do_padrao_e_volta_quando_pedido(ligado: Cluster) -> None:
    """A mudança de comportamento da U0, contra o banco real.

    Medido em 26/08/2026: das 84 campanhas das contas da casa, 79 estão
    REMOVED. Abrir o Hub em história é abrir em 94% de ruído, com as 5 que
    existem empurradas para fora da primeira página.

    O histórico não sai do banco. Ele sai do PADRÃO.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", nome="viva ligada"),
        _campanha("2", nome="viva pausada", estado_externo="PAUSED"),
        _campanha("3", nome="ida 1", estado_externo="REMOVED", presenca=dom.REMOVIDA),
        _campanha("4", nome="ida 2", estado_externo="REMOVED", presenca=dom.REMOVIDA),
    ]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)

    padrao = rodar(inv.montar_inventario(_fonte(), inv.FiltrosDoInventario(),
                                         agora=agora))
    nomes = [c.nome for c in padrao.contas[0].campanhas]
    assert nomes == ["viva ligada", "viva pausada"], nomes
    assert padrao.totais["operacionais"] == 2
    assert padrao.totais["historicas"] == 2
    assert padrao.totais["geral"] == 4

    # Os dois números vivem lado a lado no MESMO envelope: a tela não precisa
    # de uma segunda requisição para saber que existe história.
    com = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(incluir_historico=True), agora=agora))
    assert len(com.contas[0].campanhas) == 4
    assert (com.totais["operacionais"], com.totais["historicas"]) == (2, 2)


def test_pedir_removed_explicitamente_nao_devolve_vazio(ligado: Cluster) -> None:
    """Nomear exatamente o que o padrão esconde e receber lista vazia é mentira.

    `normalizar_filtros` resolve isso na fronteira: filtro explícito de estado
    ou de presença DECLARA o universo, e o padrão sai de cena.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", nome="viva"),
        _campanha("2", nome="ida", estado_externo="REMOVED", presenca=dom.REMOVIDA),
    ]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)

    f = inv.normalizar_filtros({"estado_externo": ["REMOVED"]})
    assert f.incluir_historico is True
    r = rodar(inv.montar_inventario(_fonte(), f, agora=agora))
    assert [c.nome for c in r.contas[0].campanhas] == ["ida"]

    f2 = inv.normalizar_filtros({"presenca": ["removida"]})
    assert f2.incluir_historico is True
    r2 = rodar(inv.montar_inventario(_fonte(), f2, agora=agora))
    assert [c.nome for c in r2.contas[0].campanhas] == ["ida"]


def test_o_grupo_de_conta_nao_e_fatiado_entre_paginas(ligado: Cluster) -> None:
    """A conta é a PRIMEIRA chave da ordem, e é por isso que ela é.

    Com `ordem_operacional` na frente, a lista sairia intercalada — atenção da
    conta A, atenção da conta B, ligadas da conta A — e o envelope, que agrupa
    por conta, mostraria o cabeçalho de cada conta várias vezes, com uma fatia
    diferente em cada página. O operador veria a mesma conta três vezes na tela
    e não teria como saber que é a mesma.
    """
    for cid, nome in (("8017851692", "Credito Up"), ("3849678045", "PMUNDO+")):
        rodar(_repo().gravar_conta(_conta(customer_id=cid, nome=nome)))

    linhas = []
    for cid in ("3849678045", "8017851692"):
        for n, estado in enumerate(("ENABLED", "PAUSED", "UNKNOWN"), start=1):
            linhas.append({
                **_campanha(f"{cid[-1]}{n}", estado_externo=estado),
                "volc_campaign_id": f"gads-{cid}-{cid[-1]}{n}",
                "customer_id": cid,
                "campaign_id": f"{cid[-1]}{n}",
            })
    rodar(_repo().gravar_campanhas(linhas))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    ordem_vista: List[str] = []
    cursor = None
    for _ in range(8):
        pagina = rodar(inv.montar_inventario(
            _fonte(), inv.FiltrosDoInventario(), limite=2, cursor=cursor,
            agora=agora))
        for conta in pagina.contas:
            for c in conta.campanhas:
                ordem_vista.append(c.externa.customer_id)
        cursor = pagina.proximo_cursor
        if not cursor:
            break

    assert len(ordem_vista) == 6, ordem_vista
    # Contíguo: toda campanha de uma conta antes de qualquer uma da outra.
    blocos = [k for k, _ in __import__("itertools").groupby(ordem_vista)]
    assert blocos == sorted(set(ordem_vista)), (
        f"a conta apareceu fatiada: {ordem_vista}")


def test_conta_que_falhou_respeita_o_filtro_de_atencao(ligado: Cluster) -> None:
    """Dois defeitos que a auditoria provou, e eles são o mesmo defeito.

    `_familia_falha` descartava o filtro de atenção. Com `atencao=false` ela
    devolvia `None` e **apagava a conta inteira** — inclusive o histórico
    removido, que a própria view calcula como `atencao = false`. E a contagem do
    sino somava todas as campanhas da conta, enquanto `count(*) WHERE atencao`
    na mesma view devolvia outro número.

    A razão do descarte deixou de existir quando `atencao` virou COLUNA: ela já
    inclui a falha da conta no primeiro ramo, e já exclui `removida` antes dele.
    """
    rodar(_repo().gravar_conta(_conta(resultado="falhou",
                                      motivo="a API recusou a leitura")))
    rodar(_repo().gravar_campanhas(
        [_campanha(str(n), estado_externo="REMOVED", presenca=dom.REMOVIDA)
         for n in (1, 2, 3)]
        + [_campanha(str(n), estado_externo="ENABLED") for n in (4, 5)]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    todas = inv.FiltrosDoInventario(incluir_historico=True)

    # A verdade do banco, contra a qual as três leituras têm de concordar.
    do_banco = ligado.linhas(
        "SELECT atencao, count(*) AS quantas "
        "FROM public.trafego_inventario_campanha GROUP BY atencao",
        papel="service_role")
    por_atencao = {bool(l["atencao"]): int(l["quantas"]) for l in do_banco}
    assert por_atencao == {True: 2, False: 3}, por_atencao

    r = rodar(inv.montar_inventario(_fonte(), todas, agora=agora))
    assert r.totais["atencao"] == 2, (
        "o sino discordou da coluna `atencao` da view")

    sem = rodar(inv.montar_inventario(
        _fonte(), dataclasses.replace(todas, atencao=False), agora=agora))
    vistas = [c.externa.campaign_id for conta in sem.contas
              for c in conta.campanhas]
    assert sorted(vistas) == ["1", "2", "3"], (
        f"`atencao=false` apagou a conta que falhou: {vistas}")

    com = rodar(inv.montar_inventario(
        _fonte(), dataclasses.replace(todas, atencao=True), agora=agora))
    vistas = [c.externa.campaign_id for conta in com.contas
              for c in conta.campanhas]
    assert sorted(vistas) == ["4", "5"], vistas


def test_varredura_que_falha_no_meio_da_paginacao_nao_engole_campanha(
        ligado: Cluster) -> None:
    """O degrau é a SEGUNDA CHAVE do keyset, e keyset exige chave estável.

    ⚠️ Regressão que a auditoria adversarial provou, e que eu tinha introduzido.

    `ordem_operacional` chegou a incluir `tentativa_resultado`, que vem de
    `trafego_snapshot_conta` — é da CONTA, não da campanha. Uma única gravação de
    snapshot reescrevia o degrau de todas as campanhas dela ao mesmo tempo, e o
    cursor emitido antes passava a descrever um ponto que não existia mais.

    Medido então: página 1 devolvia C-1..C-3; uma varredura que falha entre as
    duas páginas levava as seis ao degrau 0; a página 2 voltava VAZIA com
    `proximo_cursor: null`. C-4, C-5 e C-6 sumiam da listagem inteira enquanto o
    cabeçalho continuava dizendo "6 campanhas". Nenhum erro, nenhum aviso.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha(str(n), estado_externo="ENABLED",
                  impressoes=900, cliques=30, custo_micros=1,
                  entrega_lida_em=AGORA)
        for n in range(1, 7)]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)

    pagina1 = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(), limite=3, agora=agora))
    vistas = [c.externa.campaign_id for c in pagina1.contas[0].campanhas]
    assert len(vistas) == 3 and pagina1.proximo_cursor

    # ── a varredura seguinte FALHA, entre as duas páginas ──────────────────
    rodar(_repo().gravar_conta(_conta(
        resultado="falhou", lido_em="2026-08-25T12:10:00+00:00",
        motivo="a API recusou a leitura")))

    pagina2 = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(), limite=3,
        cursor=pagina1.proximo_cursor, agora=agora))
    vistas += [c.externa.campaign_id for c in pagina2.contas[0].campanhas]

    assert sorted(vistas) == ["1", "2", "3", "4", "5", "6"], (
        f"a varredura moveu o degrau e a paginação engoliu campanhas: {vistas}")
    assert len(vistas) == len(set(vistas)), "campanha repetida"

    # E a falha da conta NÃO se perdeu: ela continua pedindo atenção e o
    # cabeçalho do grupo continua declarando o frescor.
    assert pagina2.totais["atencao"] == 6
    assert pagina2.contas[0].frescor == inv.FALHOU


def test_ordem_da_view_concorda_com_o_dominio(ligado: Cluster) -> None:
    """A paridade que impede duas definições da mesma regra.

    `ordem_operacional` existe como coluna da view (para o PostgREST poder
    ordenar) e como função do domínio (para o resto do sistema raciocinar). Se
    as duas divergirem, a lista que o banco devolve e a ordem que o código
    afirma passam a ser coisas diferentes, e nada na tela denuncia.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", estado_externo="ENABLED",
                  impressoes=900, cliques=30, custo_micros=1, entrega_lida_em=AGORA),
        _campanha("2", estado_externo="PAUSED"),
        _campanha("3", estado_externo="ENABLED",
                  impressoes=0, cliques=0, custo_micros=0, entrega_lida_em=AGORA),
        _campanha("4", estado_externo="REMOVED", presenca=dom.REMOVIDA),
        _campanha("5", estado_externo="UNKNOWN"),
        _campanha("6", estado_externo="ENABLED", presenca="nao_encontrada"),
    ]))

    discordancias = []
    for linha in ligado.linhas(
            "SELECT volc_campaign_id, presenca, estado_externo, impressoes, "
            "cliques, entrega_lida_em, tentativa_resultado, ordem_operacional, "
            "historico FROM public.trafego_inventario_campanha",
            papel="service_role"):
        # ⚠️ SEM `conta_falhou` — a função nem o aceita mais. O degrau é da
        # CAMPANHA, porque ele é a segunda chave do keyset e keyset exige chave
        # estável. Ver `dominio.ordem_operacional`.
        esperado = dom.ordem_operacional(
            presenca_armazenada=linha["presenca"],
            estado_externo=linha["estado_externo"],
            impressoes=linha["impressoes"],
            cliques=linha["cliques"],
            entrega_medida=linha["entrega_lida_em"] is not None)
        if int(linha["ordem_operacional"]) != esperado:
            discordancias.append((linha["volc_campaign_id"],
                                  linha["ordem_operacional"], esperado))
        historico = dom.e_historico(presenca_armazenada=linha["presenca"],
                                    estado_externo=linha["estado_externo"])
        if bool(linha["historico"]) is not historico:
            discordancias.append((linha["volc_campaign_id"], "historico",
                                  linha["historico"], historico))
    assert not discordancias, discordancias


def test_ativas_sobem_e_historico_desce(ligado: Cluster) -> None:
    """A ordem responde "o que exige o operador agora?", não "o que está viva?".

    Uma PAUSADA que a conta não confirma sobe na frente de uma LIGADA que está
    bem: a primeira é uma divergência aberta, a segunda não é nada.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", nome="ligada saudavel", estado_externo="ENABLED",
                  impressoes=900, cliques=30, custo_micros=1, entrega_lida_em=AGORA),
        _campanha("2", nome="pausada", estado_externo="PAUSED"),
        _campanha("3", nome="pausada divergente", estado_externo="PAUSED",
                  presenca="nao_encontrada"),
        _campanha("4", nome="estado incomum", estado_externo="UNKNOWN"),
        _campanha("5", nome="removida", estado_externo="REMOVED",
                  presenca=dom.REMOVIDA),
    ]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    r = rodar(inv.montar_inventario(
        _fonte(), inv.FiltrosDoInventario(incluir_historico=True), agora=agora))
    assert [c.nome for c in r.contas[0].campanhas] == [
        "pausada divergente", "ligada saudavel", "pausada", "estado incomum",
        "removida",
    ]


def test_cursor_atravessa_degraus_sem_pular_ninguem(ligado: Cluster) -> None:
    """O keyset de três chaves, no caso que o de duas quebrava.

    Com o cursor de `(conta, id)` e a ordem por degrau, a página 2 continuaria
    de `volc_campaign_id > <último do degrau 0>` — e toda campanha do degrau 1
    com id MENOR sumiria da listagem inteira. Sem erro, sem buraco visível.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        # Ids em ordem CRESCENTE mas degraus em ordem DECRESCENTE: é a
        # disposição que expõe o defeito. Com keyset de duas chaves, depois de
        # ler `1` (degrau 0) o filtro `id > 1` ainda alcança `2`…`6` — mas
        # depois de ler `3` o cursor guardaria `3`, e nada abaixo dele voltaria.
        _campanha("1", estado_externo="ENABLED", impressoes=0, cliques=0,
                  custo_micros=0, entrega_lida_em=AGORA),
        _campanha("2", estado_externo="ENABLED", presenca="nao_encontrada"),
        _campanha("3", estado_externo="ENABLED", impressoes=900, cliques=30,
                  custo_micros=1, entrega_lida_em=AGORA),
        _campanha("4", estado_externo="ENABLED", impressoes=800, cliques=20,
                  custo_micros=1, entrega_lida_em=AGORA),
        _campanha("5", estado_externo="PAUSED"),
        _campanha("6", estado_externo="UNKNOWN"),
    ]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    vistas: List[str] = []
    cursor = None
    for _ in range(8):
        pagina = rodar(inv.montar_inventario(
            _fonte(), inv.FiltrosDoInventario(), limite=2, cursor=cursor,
            agora=agora))
        vistas += [c.externa.campaign_id for c in pagina.contas[0].campanhas]
        cursor = pagina.proximo_cursor
        if not cursor:
            break

    assert sorted(vistas) == ["1", "2", "3", "4", "5", "6"], vistas
    assert len(vistas) == len(set(vistas)), "nenhuma campanha apareceu duas vezes"
    # E a ordem sobreviveu à paginação: degrau 0, depois 1, depois 2, depois 3.
    assert vistas == ["1", "2", "3", "4", "5", "6"]


def test_busca_sobrevive_a_pagina_2(ligado: Cluster) -> None:
    """A busca e o cursor disputavam a MESMA chave de query string.

    `and` é uma chave só. Escrevê-la duas vezes não soma condições — a segunda
    apaga a primeira. A busca montava `and=(or(nome.ilike…))`, o cursor
    sobrescrevia com `and=(or(customer_id.gt…))`, e a partir da página 2 a
    consulta devolvia o inventário inteiro a partir daquele ponto.

    O defeito era invisível de propósito: as linhas da página 2 eram
    verdadeiras, só não eram as que o operador tinha pedido. Com 84 campanhas em
    3 contas e uma delas ocupando a primeira página, esse é o caso comum, não a
    borda.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas(
        [_campanha(str(n), nome=f"FGTS Saque {n}") for n in range(1, 5)]
        + [_campanha(str(n), nome=f"Maquininha {n}") for n in range(5, 9)]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    filtros = inv.FiltrosDoInventario(busca="FGTS")

    vistas: List[str] = []
    cursor = None
    for _ in range(6):
        pagina = rodar(inv.montar_inventario(_fonte(), filtros, limite=2,
                                             cursor=cursor, agora=agora))
        vistas += [c.nome for c in pagina.contas[0].campanhas]
        cursor = pagina.proximo_cursor
        if not cursor:
            break

    assert len(vistas) == 4, f"a busca alcançou {len(vistas)} linhas: {vistas}"
    assert all(n.startswith("FGTS") for n in vistas), vistas


def test_total_nao_encolhe_conforme_o_operador_pagina(ligado: Cluster) -> None:
    """`dataclasses.replace` copiava o cursor para dentro da contagem.

    O total virava "quantas faltam depois deste ponto" enquanto a tela o
    apresentava como "quantas existem" — um número que se desmancha conforme se
    avança, e chega a zero na última página, sem nada dizendo isso.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha(str(n), impressoes=0, cliques=0, custo_micros=0,
                  entrega_lida_em=AGORA)
        for n in range(1, 6)]))

    import datetime as dt
    agora = dt.datetime(2026, 8, 25, 12, 5, tzinfo=dt.timezone.utc)
    totais: List[Tuple[int, int]] = []
    cursor = None
    for _ in range(5):
        pagina = rodar(inv.montar_inventario(
            _fonte(), inv.FiltrosDoInventario(), limite=2, cursor=cursor,
            agora=agora))
        totais.append((pagina.totais["operacionais"], pagina.totais["atencao"]))
        cursor = pagina.proximo_cursor
        if not cursor:
            break

    assert totais == [(5, 5)] * len(totais), (
        f"o total mudou entre páginas do MESMO conjunto: {totais}")


def test_vinculo_ativo_chega_na_linha_e_nao_multiplica(ligado: Cluster) -> None:
    """Vínculo desfeito fica na tabela; só o ativo entra na projeção."""
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([_campanha("1")]))
    ligado.sql("""
        INSERT INTO public.trafego_vinculo
          (vinculo_id, volc_campaign_id, opportunity_id, regra, confirmado_por,
           desfeito_por, desfeito_em, desfeito_motivo)
        VALUES ('00000000-0000-0000-0000-0000000000a1','gads-8017851692-1',
                11,'url_final','tarcisio','tarcisio', now(),'funil errado');
        INSERT INTO public.trafego_vinculo
          (volc_campaign_id, opportunity_id, project_id, regra, confirmado_por,
           vinculo_anterior)
        VALUES ('gads-8017851692-1', 65, 3, 'confirmacao_manual', 'tarcisio',
                '00000000-0000-0000-0000-0000000000a1');
    """)
    linhas = ligado.linhas(f"SELECT * FROM public.{pers.VIEW_CAMPANHAS}")
    assert len(linhas) == 1, (
        "o índice parcial de vínculo ativo é o que impede o LEFT JOIN de "
        "multiplicar a linha e o sino de contar a mesma campanha duas vezes")
    assert linhas[0]["opportunity_id"] == 65 and linhas[0]["project_id"] == 3
    assert linhas[0]["sem_vinculo"] is False


def test_procedencia_e_vinculo_nao_entram_no_sino(ligado: Cluster) -> None:
    """As duas são fato observado, e mesmo assim ficam fora de `atencao`.

    Procedência desconhecida é o estado de TODA campanha descoberta, e vínculo
    ausente é o estado normal de quase tudo. No sino, as duas marcariam o
    inventário inteiro no primeiro dia — a aba encheria de linhas CORRETAS, o
    operador pararia de olhar, e o alerta morreria. Elas viajam como coluna
    própria para que um filtro futuro as alcance sem passar pelo sino.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1", impressoes=5, cliques=2, custo_micros=90,
                  entrega_lida_em=AGORA)]))
    linha = ligado.linhas(f"SELECT * FROM public.{pers.VIEW_CAMPANHAS}")[0]
    assert linha["procedencia_desconhecida"] is True
    assert linha["sem_vinculo"] is True
    assert linha["atencao"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 5. A TRADUÇÃO DE FILTROS É A MESMA DA CLASSE QUE SERÁ SUBSTITUÍDA
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not hasattr(inv, "FonteSupabase"),
                    reason="a classe antiga já saiu; a equivalência cumpriu o papel")
def test_mesmos_query_params_da_fonte_antiga() -> None:
    """A duplicação da tradução de filtros é deliberada, e provada enquanto dá.

    `persistencia.py` não chama `inventario.FonteSupabase` porque é ela que vai
    ser apagada — um módulo novo não pode nascer dependendo do objeto que
    substitui. O preço é uma cópia, e o antídoto é este teste: as duas produzem
    os MESMOS query params, ou uma delas mudou sozinha.
    """
    antiga = inv.FonteSupabase("", "")
    filtros = [
        inv.FiltrosDoInventario(),
        inv.FiltrosDoInventario(atencao=True),
        inv.FiltrosDoInventario(atencao=False),
        inv.FiltrosDoInventario(canal=("SEARCH",), estado_externo=("ENABLED",)),
        inv.FiltrosDoInventario(presenca=("removida", "sincronizacao_falhou")),
        inv.FiltrosDoInventario(presenca=("sincronizacao_falhou",)),
        inv.FiltrosDoInventario(vinculado=True, projeto=(3,)),
        inv.FiltrosDoInventario(vinculado=False, procedencia=("volc_os",)),
        inv.FiltrosDoInventario(conta=("8017851692",)),
    ]
    for f in filtros:
        assert pers.params_de_contas(f) == antiga.params_de_contas(f), f
        for falhas, lidas in (((), ("8017851692",)),
                              (("3849678045",), ("8017851692",)),
                              (("3849678045",), ())):
            plano = inv.PlanoDeConsulta(filtros=f, contas_lidas=lidas,
                                        contas_falhas=falhas, limite=50,
                                        depois_de=("8017851692", "gads-x-1"))
            assert pers.params_de_campanhas(plano) == \
                antiga.params_de_campanhas(plano), (f, falhas, lidas)


# ═══════════════════════════════════════════════════════════════════════════
# 6. A FONTE DO QUADRO DE ALERTAS
# ═══════════════════════════════════════════════════════════════════════════


def _alertas() -> pers.FonteDeAlertasSupabase:
    return pers.FonteDeAlertasSupabase("http://postgrest.local", "chave")


def test_quadro_de_alertas_le_tudo_e_nao_filtra_estado(ligado: Cluster) -> None:
    """Campanha `PAUSED` tem de chegar ao quadro.

    Filtrar `estado_externo` no banco esconderia exatamente o caso que o quadro
    precisa mostrar: a campanha que a varredura viu pausada antes e não
    conseguiu reler agora vira `faltou`, e o filtro a apagaria justamente quando
    ninguém sabe nada dela.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([
        _campanha("1"), _campanha("2", estado_externo="PAUSED")]))

    estados = {l["volc_campaign_id"]: l["estado_externo"]
               for l in rodar(_alertas().campanhas())}
    assert estados == {"gads-8017851692-1": "ENABLED",
                       "gads-8017851692-2": "PAUSED"}
    assert [c["customer_id"] for c in rodar(_alertas().contas())] == ["8017851692"]


def test_transicoes_saem_do_diario_por_campanha(ligado: Cluster) -> None:
    """`horas_ligada` vem daqui, e `None` não é zero.

    Uma campanha sem transição registrada tem estado conhecido e antiguidade
    DESCONHECIDA. Devolver lista vazia (e não faltar a chave) é o que deixa
    `horas_ligada()` responder `None` em vez de "ligada há 0 horas" — que faria
    uma campanha parada há um mês parecer recém-criada.
    """
    from app.trafego import alertas as alr

    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([_campanha("1"), _campanha("2")]))
    ligado.sql(f"""
        INSERT INTO public.trafego_evento
          (ocorrido_em, tipo, chave_de_agrupamento, produtor, sujeito_tipo,
           volc_campaign_id, carga)
        VALUES
          ('2026-08-24T10:00:00Z', '{alr.TIPO_ESTADO}',
           '{alr.chave_de_estado("gads-8017851692-1")}', 'varredura', 'campanha',
           'gads-8017851692-1', '{{"de":"PAUSED","para":"ENABLED"}}'::jsonb),
          ('2026-08-23T10:00:00Z', '{alr.TIPO_ESTADO}',
           '{alr.chave_de_estado("gads-8017851692-1")}', 'varredura', 'campanha',
           'gads-8017851692-1', '{{"de":null,"para":"PAUSED"}}'::jsonb);
    """)

    saida = rodar(_alertas().transicoes_de_estado(
        ["gads-8017851692-1", "gads-8017851692-2"]))
    assert [t["para"] for t in saida["gads-8017851692-1"]] == ["PAUSED", "ENABLED"]
    assert saida["gads-8017851692-2"] == [], (
        "campanha sem transição vem com lista vazia, e não some do mapa: "
        "quem sumisse viraria KeyError no consumidor")

    import datetime as dt
    horas = alr.horas_ligada(saida["gads-8017851692-1"],
                             dt.datetime(2026, 8, 24, 16, tzinfo=dt.timezone.utc))
    assert horas == 6.0
    assert alr.horas_ligada(saida["gads-8017851692-2"],
                            dt.datetime(2026, 8, 24, 16, tzinfo=dt.timezone.utc)) is None


def test_paginacao_do_quadro_nao_para_no_corte_do_postgrest(ligado: Cluster) -> None:
    """O corte de `db-max-rows` é silencioso: 200, mil linhas, e nada avisando.

    Com o corte engolido, o quadro mostraria "nenhum alerta" para tudo que
    ficasse do outro lado. Aqui a página é forçada a 3 para que o laço keyset
    seja exercitado de verdade em vez de nunca rodar.
    """
    rodar(_repo().gravar_conta(_conta()))
    rodar(_repo().gravar_campanhas([_campanha(str(n)) for n in range(1, 11)]))

    fonte = _alertas()
    paginado = rodar(fonte._tudo(pers.VIEW_CAMPANHAS, {"select": "*"}, pagina=3))
    assert len(paginado) == 10
    assert len({l["volc_campaign_id"] for l in paginado}) == 10, (
        "keyset: nenhuma linha repetida entre páginas")
