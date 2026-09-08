"""O grão conjunto/dia provado EM SQL, num cluster PostgreSQL descartável.

## Por que este arquivo existe

`atribuicao.py` sabe somar em Python e tem 33 testes provando isso. A migration
candidata `20260908120000_meta_financeiro_conjunto_dia.sql` sabe somar em SQL.
Duas implementações da mesma conta são duas chances de a conta estar errada —
a não ser que alguém as compare.

É o que este arquivo faz: carrega o MESMO golden derivado da operação real nas
tabelas reais do read model, soma pelos dois caminhos e exige igualdade exata.
Se um dia a view e o contrato divergirem, isto quebra antes de o operador ver
dois números diferentes na tela.

Ele também exerce o ciclo que a missão cobra: apply -> uso -> replay ->
concorrência -> rollback -> reapply.

## O que este cluster NÃO é

Ele não é o Supabase. Nasce em `mktemp -d`, escuta só num socket unix dentro
dele e morre no fim da sessão. `database.agenciavolc.com.br` não é tocado.

⚠️ `public.gam_metrics` é criada aqui como DUBLÊ da tabela legada. Ela não tem
DDL neste repositório — é do sistema legado — e o dublê existe só para exercitar
o LEFT JOIN da view de receita. Ele NÃO é o schema oficial e não prova nada
sobre o schema real.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.trafego.meta.atribuicao import (
    ATRIBUIDO_VIA_ADSET,
    LinhaAtribuicao,
    agregar_campanha_dia,
    totalizar,
)

RAIZ = Path(__file__).resolve().parents[2]
MIGRACOES = RAIZ / "supabase" / "migrations"
GOLDEN = Path(__file__).parent / "goldens" / "atribuicao-meta-adset-v1.json"

#: A cadeia mínima que faz o grão existir, na ordem em que ela precisa rodar.
CADEIA = [
    "v13_01_cofre_de_ativos.sql",
    "v15_01_meta_ads_read_model.sql",
    "v15_02_meta_ads_insights.sql",
    "20260907210000_meta_read_model_consistency.sql",
]
CANDIDATA = "20260908120000_meta_financeiro_conjunto_dia.sql"
ROLLBACK = "20260908120100_meta_financeiro_conjunto_dia_rollback.sql"

ATIVO = "meta_account_fixture"
CONTA = "100000000001"


def _exigido() -> bool:
    return os.environ.get("VOLC_EXIGIR_POSTGRES", "").strip() in {"1", "true", "sim"}


def _faltando() -> str | None:
    for b in ("initdb", "pg_ctl", "psql"):
        if shutil.which(b) is None:
            return f"binario `{b}` ausente no PATH"
    try:
        import psycopg  # noqa: F401, PLC0415
    except ImportError:
        return "driver `psycopg` ausente neste interpretador"
    for m in [*CADEIA, CANDIDATA, ROLLBACK]:
        if not (MIGRACOES / m).is_file():
            return f"migration ausente: {m}"
    return None


@pytest.fixture(scope="module")
def cluster():
    """Um cluster que nasce e morre neste módulo, com a cadeia Meta aplicada."""
    motivo = _faltando()
    if motivo:
        if _exigido():
            pytest.fail(f"VOLC_EXIGIR_POSTGRES ligado e o cluster nao pode nascer: {motivo}")
        pytest.skip(f"sem Postgres descartavel: {motivo}")

    base = Path(tempfile.mkdtemp(prefix="volc-meta-fin-pg."))
    dados, socket = base / "d", base / "s"
    socket.mkdir(parents=True, exist_ok=True)
    # ⚠️ `LC_ALL=C` nao e enfeite: sem ela o Postgres 16 do Homebrew no macOS
    # morre no arranque com "postmaster became multithreaded during startup".
    ambiente = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def rodar(*args, **kw):
        return subprocess.run(args, env=ambiente, capture_output=True, text=True, **kw)

    try:
        r = rodar("initdb", "-D", str(dados), "-U", "postgres", "--encoding=UTF8", "--locale=C")
        if r.returncode != 0:
            raise RuntimeError(f"initdb falhou: {r.stderr[-400:]}")
        r = rodar("pg_ctl", "-D", str(dados), "-l", str(base / "pg.log"),
                  "-o", f"-k {socket} -h ''", "-w", "start")
        if r.returncode != 0:
            raise RuntimeError(f"pg_ctl start falhou: {r.stderr[-400:]}")

        env = {**ambiente, "PGHOST": str(socket), "PGUSER": "postgres", "PGDATABASE": "postgres"}

        def sql(comando: str) -> subprocess.CompletedProcess:
            return subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-c", comando],
                                  env=env, capture_output=True, text=True)

        def arquivo(nome: str) -> subprocess.CompletedProcess:
            return subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f",
                                   str(MIGRACOES / nome)], env=env, capture_output=True, text=True)

        r = sql("create role anon nologin; create role authenticated nologin;"
                " create role service_role nologin bypassrls;")
        if r.returncode != 0:
            raise RuntimeError(f"papeis: {r.stderr[-400:]}")
        for m in CADEIA:
            r = arquivo(m)
            if r.returncode != 0:
                raise RuntimeError(f"{m}: {r.stderr[-800:]}")

        # O dublê da tabela legada. Só as colunas que a view toca.
        r = sql("""
            CREATE TABLE public.gam_metrics (
              gam_accounts_id    bigint NOT NULL,
              utm_campaign_value text   NOT NULL,
              date               date   NOT NULL,
              revenue            numeric,
              revenue_converted  numeric,
              updated_at         timestamptz,
              PRIMARY KEY (gam_accounts_id, utm_campaign_value, date)
            );""")
        if r.returncode != 0:
            raise RuntimeError(f"dublê gam_metrics: {r.stderr[-400:]}")

        yield {"env": env, "sql": sql, "arquivo": arquivo,
               "dsn": f"host={socket} user=postgres dbname=postgres"}
    finally:
        subprocess.run(["pg_ctl", "-D", str(dados), "-m", "immediate", "stop"],
                       env=ambiente, capture_output=True)
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _linhas_do_golden(golden: dict) -> list[LinhaAtribuicao]:
    return [
        LinhaAtribuicao(
            account_ref=r["account_ref"], campaign_id=r["campaign_id"],
            adset_id=r["adset_id"], date=date.fromisoformat(r["date"]),
            project_id=r["project_id"], spend=Decimal(r["spend"]),
            impressions=r["impressions"], clicks=r["clicks"],
            gam_revenue_original=Decimal(r["gam_revenue_original"]),
            gam_revenue_brl=Decimal(r["gam_revenue_brl"]),
            gam_impressions=r["gam_impressions"], gam_clicks=r["gam_clicks"],
            attribution_method="GAM.utm_campaign_value = adset_id",
            mapping_status=ATRIBUIDO_VIA_ADSET, currency="BRL",
            timezone="America/Sao_Paulo")
        for r in golden["linhas"] if r["adset_id"] is not None
    ]


@pytest.fixture(scope="module")
def carregado(cluster, golden):
    """Aplica a candidata e carrega o golden nas tabelas REAIS do read model."""
    r = cluster["arquivo"](CANDIDATA)
    assert r.returncode == 0, r.stderr[-1500:]

    linhas = _linhas_do_golden(golden)
    campanhas = sorted({l.campaign_id for l in linhas})
    conjuntos = sorted({(l.campaign_id, l.adset_id) for l in linhas})

    partes = [
        # O Cofre governa o par (kind, cluster) por FK em `cofre_tipo`; inventar
        # um par aqui derrubaria o INSERT com nome próprio, e é assim que o
        # dublê continua honesto sobre o schema real.
        "INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, "
        " criticidade, resumo, dono_nome, dono_custodia, capacidades, proxima_acao) "
        f"VALUES ('{ATIVO}', 'meta_ad_account', 'paid_media', 'Conta fixture', 'meta', 'active', "
        "'medium', 'Conta hermetica que existe so dentro do cluster descartavel.', "
        "'fixture', 'declared', ARRAY['read'], "
        "'Nenhuma: este ativo morre com o cluster no fim do modulo.') ON CONFLICT DO NOTHING;",
        "INSERT INTO public.trafego_meta_ad_account "
        "(cofre_ativo_id, account_external_id, moeda, timezone_name, readiness_state, observado_em) "
        f"VALUES ('{ATIVO}', '{CONTA}', 'BRL', 'America/Sao_Paulo', 'READY_FOR_READ', now());",
    ]
    for i, c in enumerate(campanhas):
        partes.append(
            "INSERT INTO public.trafego_meta_campaign "
            "(meta_campaign_id, ad_account_ativo_id, external_id, nome, observado_em, ultima_vez_visto_em) "
            f"VALUES ('00000000-0000-0000-0000-{i:012d}', '{ATIVO}', '{c}', 'campanha {i}', now(), now());")
    mapa = {c: f"00000000-0000-0000-0000-{i:012d}" for i, c in enumerate(campanhas)}
    for i, (camp, conj) in enumerate(conjuntos):
        partes.append(
            "INSERT INTO public.trafego_meta_adset "
            "(meta_adset_id, meta_campaign_id, external_id, nome, observado_em, ultima_vez_visto_em) "
            f"VALUES ('00000000-0000-0000-0001-{i:012d}', '{mapa[camp]}', '{conj}', 'conjunto {i}', now(), now());")
    for i, l in enumerate(linhas):
        partes.append(
            "INSERT INTO public.trafego_meta_insight_daily "
            "(meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel, "
            " objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown, "
            " time_increment, action_report_time, completo, currency, account_timezone, "
            " observado_em, spend, impressions, clicks) "
            f"VALUES ('ins-{i}', '{ATIVO}', 'META_ADS', '{CONTA}', 'adset', '{l.adset_id}', "
            f"'{l.date}', '{l.date}', 'default', 'none', '1', 'impression', true, 'BRL', "
            f"'America/Sao_Paulo', '2026-09-01T00:00:00Z', {l.spend}, {l.impressions}, {l.clicks});")
        partes.append(
            "INSERT INTO public.gam_metrics "
            "(gam_accounts_id, utm_campaign_value, date, revenue, revenue_converted, updated_at) "
            f"VALUES (8, '{l.adset_id}', '{l.date}', {l.gam_revenue_original}, "
            f"{l.gam_revenue_brl}, '2026-09-01T00:00:00Z') ON CONFLICT DO NOTHING;")

    r = cluster["sql"]("\n".join(partes))
    assert r.returncode == 0, r.stderr[-1500:]
    return linhas


#: A janela do golden. Tudo o que os testes INSEREM para provar uma recusa vai
#: para fora dela.
#:
#: ⚠️ POR QUE ISTO EXISTE. `20260907210000:496-511` instala gatilhos
#: `BEFORE DELETE` e `BEFORE TRUNCATE` que RECUSAM remoção nas três tabelas de
#: insight — o fato é um livro-razão, e livro-razão não se apaga. A primeira
#: versão destes testes "limpava" com DELETE e não conferia o resultado: as
#: limpezas falhavam em silêncio e a linha adversarial de um teste vazava para
#: o total do seguinte. O schema estava certo; os testes é que supunham poder
#: desfazer o que gravaram.
GOLDEN_INICIO, GOLDEN_FIM = "2026-08-09", "2026-08-25"
NA_JANELA_DO_GOLDEN = f"date BETWEEN '{GOLDEN_INICIO}' AND '{GOLDEN_FIM}'"
#: Data fora da janela, para as linhas adversariais que não podem ser removidas.
DIA_DE_PROVA = "2026-07-15"


def _consultar(cluster, consulta: str) -> list[list[str]]:
    r = subprocess.run(["psql", "-X", "-q", "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1",
                        "-c", consulta], env=cluster["env"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1200:]
    return [linha.split("|") for linha in r.stdout.strip().splitlines() if linha.strip()]


# ---------------------------------------------------------------------------
# A conta, pelos dois caminhos
# ---------------------------------------------------------------------------

def test_a_view_de_grao_devolve_uma_linha_por_conjunto_dia(cluster, carregado):
    total = _consultar(cluster, "SELECT count(*) FROM public.vw_trafego_meta_financeiro_conjunto_dia;")
    assert int(total[0][0]) == len(carregado)
    distintas = _consultar(cluster,
        "SELECT count(*) FROM (SELECT DISTINCT campaign_id, adset_id, date "
        "FROM public.vw_trafego_meta_financeiro_conjunto_dia) x;")
    assert int(distintas[0][0]) == len(carregado), "o grão não pode repetir"


def test_o_sql_e_o_python_somam_o_mesmo_total(cluster, carregado):
    """A prova central: duas implementações, um número."""
    em_python = totalizar(carregado)
    em_sql = _consultar(cluster,
        "SELECT sum(spend)::text, sum(impressions)::text, sum(clicks)::text "
        f"FROM public.vw_trafego_meta_financeiro_conjunto_dia WHERE {NA_JANELA_DO_GOLDEN};")[0]
    assert Decimal(em_sql[0]) == em_python.spend == Decimal("1029.410000")
    assert int(em_sql[1]) == em_python.impressions == 234333
    assert int(em_sql[2]) == em_python.clicks == 18961


def test_o_rollup_de_campanha_bate_conjunto_a_conjunto(cluster, carregado):
    em_python = agregar_campanha_dia(carregado)
    em_sql = {
        (linha[0], date.fromisoformat(linha[1])): linha
        for linha in _consultar(cluster,
            "SELECT campaign_id, date::text, spend::text, impressions::text, clicks::text, "
            "conjuntos_no_dia::text FROM public.vw_trafego_meta_financeiro_campanha_dia;")
    }
    assert set(em_sql) == set(em_python), "os dois caminhos precisam ver as mesmas campanhas/dias"
    for chave, total in em_python.items():
        linha = em_sql[chave]
        assert Decimal(linha[2]) == total.spend
        assert int(linha[3]) == total.impressions
        assert int(linha[4]) == total.clicks
        assert int(linha[5]) == total.razao.conjuntos


def test_a_campanha_abo_com_seis_conjuntos_soma_os_seis(cluster, carregado):
    maior = _consultar(cluster,
        "SELECT max(conjuntos_no_dia)::text FROM public.vw_trafego_meta_financeiro_campanha_dia;")
    assert int(maior[0][0]) == 6


def test_a_receita_do_gam_chega_pelo_conjunto(cluster, carregado):
    linha = _consultar(cluster,
        "SELECT sum(gam_revenue_brl)::text, count(*) FILTER (WHERE mapping_status = "
        "'FATURAMENTO_ATRIBUIDO_VIA_ADSET')::text "
        "FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam;")[0]
    assert Decimal(linha[0]) == Decimal("1140.73")
    assert int(linha[1]) == len(carregado)


# ---------------------------------------------------------------------------
# As recusas, em SQL
# ---------------------------------------------------------------------------

def test_a_leitura_campaign_level_nao_entra_na_view_de_grao(cluster, carregado):
    """A trava contra o double count, em SQL."""
    antes = Decimal(_consultar(cluster,
        "SELECT sum(spend)::text FROM public.vw_trafego_meta_financeiro_conjunto_dia;")[0][0])
    r = cluster["sql"](
        "INSERT INTO public.trafego_meta_insight_daily "
        "(meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel, objeto_externo,"
        " periodo_inicio, periodo_fim, janela_atribuicao, breakdown, time_increment,"
        " action_report_time, completo, currency, account_timezone, observado_em, spend)"
        f" VALUES ('ins-campaign-level', '{ATIVO}', 'META_ADS', '{CONTA}', 'campaign',"
        f" '{carregado[0].campaign_id}', '{carregado[0].date}', '{carregado[0].date}', 'default',"
        " 'none', '1', 'impression', true, 'BRL', 'America/Sao_Paulo', '2026-09-01T00:00:00Z', 99999);")
    # ⚠️ Achado do revisor adversarial: sem esta conferência, um INSERT que
    # falhasse por constraint deixaria o teste VERDE sem nenhuma parcela
    # campaign-level presente — provando que a trava funciona contra nada.
    assert r.returncode == 0, r.stderr[-800:]
    presente = _consultar(cluster,
        "SELECT count(*)::text FROM public.trafego_meta_insight_daily "
        "WHERE meta_insight_daily_id = 'ins-campaign-level';")
    assert int(presente[0][0]) == 1, "a parcela adversarial precisa existir de fato"
    depois = Decimal(_consultar(cluster,
        "SELECT sum(spend)::text FROM public.vw_trafego_meta_financeiro_conjunto_dia;")[0][0])
    assert depois == antes, "uma linha campaign-level não pode entrar no grão de conjunto"
    cluster["sql"]("DELETE FROM public.trafego_meta_insight_daily WHERE meta_insight_daily_id = 'ins-campaign-level';")


def test_uma_parcela_nula_torna_o_total_da_campanha_nulo(cluster, carregado):
    """`sum()` do Postgres ignora NULL — e é isso que produziria um total falso."""
    alvo = carregado[0]
    cluster["sql"](
        "INSERT INTO public.trafego_meta_insight_daily "
        "(meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel, objeto_externo,"
        " periodo_inicio, periodo_fim, janela_atribuicao, breakdown, time_increment,"
        " action_report_time, completo, currency, account_timezone, observado_em, spend)"
        f" VALUES ('ins-sem-gasto', '{ATIVO}', 'META_ADS', '{CONTA}', 'adset',"
        f" '{alvo.adset_id}', '2026-07-01', '2026-07-01', 'default', 'none', '1', 'impression',"
        " true, 'BRL', 'America/Sao_Paulo', '2026-09-01T00:00:00Z', NULL);")
    linha = _consultar(cluster,
        "SELECT coalesce(spend::text, 'NULO'), conjuntos_no_dia::text "
        "FROM public.vw_trafego_meta_financeiro_campanha_dia WHERE date = '2026-07-01';")[0]
    assert linha[0] == "NULO", "gasto desconhecido não pode virar total conhecido"
    cluster["sql"]("DELETE FROM public.trafego_meta_insight_daily WHERE meta_insight_daily_id = 'ins-sem-gasto';")


def test_duas_contas_gam_no_mesmo_conjunto_dia_nao_duplicam_o_gasto(cluster, carregado):
    """O defeito que o revisor adversarial encontrou, virado teste.

    `gam_metrics` e chaveada por (gam_accounts_id, utm_campaign_value, date).
    Com um LEFT JOIN simples por (adset_id, date), DUAS contas GAM com o mesmo
    id de conjunto no mesmo dia produziam DUAS linhas para o mesmo conjunto/dia
    — e qualquer `sum(spend)` sobre a view contava o gasto daquele conjunto
    DUAS VEZES. Um defeito de receita virava um defeito de GASTO, que e pior:
    o gasto nao depende do GAM para existir.
    """
    alvo = carregado[0]
    antes = _consultar(cluster,
        "SELECT count(*)::text, sum(spend)::text "
        "FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam;")[0]
    cluster["sql"](
        "INSERT INTO public.gam_metrics (gam_accounts_id, utm_campaign_value, date,"
        f" revenue, revenue_converted, updated_at) VALUES (99, '{alvo.adset_id}',"
        f" '{alvo.date}', 777, 3888, '2026-09-01T00:00:00Z');")
    depois = _consultar(cluster,
        "SELECT count(*)::text, sum(spend)::text "
        "FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam;")[0]
    assert depois[0] == antes[0], "uma segunda conta GAM nao pode criar uma segunda linha"
    assert Decimal(depois[1]) == Decimal(antes[1]), "o gasto nao pode contar duas vezes"

    linha = _consultar(cluster,
        "SELECT mapping_status, coalesce(gam_revenue_brl::text,'NULO'),"
        " coalesce(attribution_method,'NULO'), spend::text"
        " FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam"
        f" WHERE adset_id = '{alvo.adset_id}' AND date = '{alvo.date}';")[0]
    assert linha[0] == "GAM_AMBIGUO_MULTIPLAS_CONTAS"
    assert linha[1] == "NULO", "ambiguidade nao vira zero nem 'a primeira que apareceu'"
    assert linha[2] == "NULO"
    assert Decimal(linha[3]) == alvo.spend, "o gasto sobrevive a ambiguidade da receita"

    cluster["sql"]("DELETE FROM public.gam_metrics WHERE gam_accounts_id = 99;")


def test_moedas_diferentes_no_mesmo_dia_nao_viram_um_total(cluster, carregado):
    """Achado do revisor adversarial: `min()` escolhia um rótulo e somava.

    6 USD + 4 BRL viravam "10 BRL" com `completo=true` ao lado.
    """
    alvo = carregado[0]
    # Um conjunto NOVO da mesma campanha, medido em USD no mesmo dia. Precisa
    # ser outro conjunto: o grão é único por (conjunto, dia, observado_em), e a
    # view `latest` guarda uma revisão só — duas moedas no MESMO conjunto/dia
    # seriam duas revisões, não duas parcelas.
    r = cluster["sql"](
        "INSERT INTO public.trafego_meta_adset (meta_adset_id, meta_campaign_id, external_id,"
        " nome, observado_em, ultima_vez_visto_em) SELECT "
        "'00000000-0000-0000-0003-000000000001', meta_campaign_id, '888888888888888',"
        " 'conjunto em USD', now(), now() FROM public.trafego_meta_campaign "
        f"WHERE external_id = '{alvo.campaign_id}';")
    assert r.returncode == 0, r.stderr[-800:]
    # Uma parcela BRL e uma USD no MESMO dia da mesma campanha.
    r = cluster["sql"](
        "INSERT INTO public.trafego_meta_insight_daily "
        "(meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel, objeto_externo,"
        " periodo_inicio, periodo_fim, janela_atribuicao, breakdown, time_increment,"
        " action_report_time, completo, currency, account_timezone, observado_em, spend, impressions, clicks)"
        f" VALUES ('ins-usd', '{ATIVO}', 'META_ADS', '{CONTA}', 'adset',"
        f" '888888888888888', '{DIA_DE_PROVA}', '{DIA_DE_PROVA}', 'default', 'none', '1',"
        " 'impression', true, 'USD', 'America/Sao_Paulo', '2026-09-01T00:00:00Z', 6, 1, 1),"
        f" ('ins-brl', '{ATIVO}', 'META_ADS', '{CONTA}', 'adset',"
        f" '{alvo.adset_id}', '{DIA_DE_PROVA}', '{DIA_DE_PROVA}', 'default', 'none', '1',"
        " 'impression', true, 'BRL', 'America/Sao_Paulo', '2026-09-01T00:00:00Z', 4, 1, 1);")
    assert r.returncode == 0, r.stderr[-800:]
    linha = _consultar(cluster,
        "SELECT coalesce(spend::text,'NULO'), moedas_no_dia::text, completo::text "
        "FROM public.vw_trafego_meta_financeiro_campanha_dia "
        f"WHERE campaign_id = '{alvo.campaign_id}' AND date = '{DIA_DE_PROVA}';")[0]
    assert linha[1] == "2", "o dia precisa enxergar as duas moedas"
    assert linha[0] == "NULO", "somar moedas diferentes não pode produzir total"
    assert linha[2] == "false"
    # Sem limpeza: o gatilho `_sem_delete` recusa remoção, e a data de prova
    # está fora da janela do golden justamente para não precisar dela.


def test_conjunto_conhecido_sem_insight_nao_fica_invisivel(cluster, carregado):
    """Achado do revisor adversarial: a completude só via os insights EXISTENTES."""
    alvo = carregado[0]
    r = cluster["sql"](
        "INSERT INTO public.trafego_meta_adset (meta_adset_id, meta_campaign_id, external_id,"
        " nome, observado_em, ultima_vez_visto_em) SELECT "
        "'00000000-0000-0000-0002-000000000001', meta_campaign_id, '999999999999999',"
        " 'orfao', now(), now() FROM public.trafego_meta_campaign "
        f"WHERE external_id = '{alvo.campaign_id}';")
    assert r.returncode == 0, r.stderr[-800:]
    linha = _consultar(cluster,
        "SELECT conjuntos_no_dia::text, conjuntos_conhecidos_na_campanha::text, completo::text "
        "FROM public.vw_trafego_meta_financeiro_campanha_dia "
        f"WHERE campaign_id = '{alvo.campaign_id}' AND date = '{alvo.date}';")[0]
    assert int(linha[1]) > int(linha[0]), "a campanha conhece mais conjuntos do que mediu"
    assert linha[2] == "false", "com filho sem medida o dia NÃO é completo"
    # ⚠️ Não se apaga: `trafego_meta_adset_sem_delete` recusa remoção. A saída
    # honesta é a que o próprio schema oferece — marcar AUSENTE, que é o estado
    # que a view já filtra.
    limpou = cluster["sql"](
        "UPDATE public.trafego_meta_adset SET ausente_desde = now(),"
        " ausencia_causa = 'nao_encontrada' WHERE external_id = '999999999999999';")
    assert limpou.returncode == 0, limpou.stderr[-400:]


def test_alcance_nao_soma_no_rollup(cluster, carregado):
    linha = _consultar(cluster,
        "SELECT coalesce(reach::text, 'NULO') FROM public.vw_trafego_meta_financeiro_campanha_dia LIMIT 1;")
    assert linha[0][0] == "NULO"


def test_conjunto_sem_linha_no_gam_mantem_o_gasto_e_nao_ganha_receita_zero(cluster, carregado):
    alvo = carregado[0]
    cluster["sql"](
        f"DELETE FROM public.gam_metrics WHERE utm_campaign_value = '{alvo.adset_id}' "
        f"AND date = '{alvo.date}';")
    linha = _consultar(cluster,
        "SELECT coalesce(gam_revenue_brl::text, 'NULO'), mapping_status, spend::text "
        "FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam "
        f"WHERE adset_id = '{alvo.adset_id}' AND date = '{alvo.date}';")[0]
    assert linha[0] == "NULO", "associação desconhecida nunca é receita zero"
    assert linha[1] == "SEM_UTM_ADSET_NO_GAM"
    assert Decimal(linha[2]) == alvo.spend, "o gasto sobrevive à falta de receita"
    cluster["sql"](
        "INSERT INTO public.gam_metrics (gam_accounts_id, utm_campaign_value, date, revenue,"
        f" revenue_converted, updated_at) VALUES (8, '{alvo.adset_id}', '{alvo.date}',"
        f" {alvo.gam_revenue_original}, {alvo.gam_revenue_brl}, '2026-09-01T00:00:00Z');")


# ---------------------------------------------------------------------------
# Segurança e ciclo
# ---------------------------------------------------------------------------

def test_as_views_nascem_com_security_invoker_e_sem_grant_a_anon(cluster, carregado):
    invoker = _consultar(cluster,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'v' "
        "AND c.relname LIKE 'vw_trafego_meta_financeiro%' "
        "AND NOT (c.reloptions @> ARRAY['security_invoker=true']);")
    assert invoker == [], f"views sem security_invoker: {invoker}"
    vazado = _consultar(cluster,
        "SELECT table_name, grantee FROM information_schema.role_table_grants "
        "WHERE table_schema='public' AND table_name LIKE 'vw_trafego_meta_financeiro%' "
        "AND grantee IN ('anon','authenticated','PUBLIC');")
    assert vazado == [], f"grants indevidos: {vazado}"


def test_service_role_le_mas_nao_escreve_na_view(cluster, carregado):
    concedidos = _consultar(cluster,
        "SELECT DISTINCT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema='public' AND table_name LIKE 'vw_trafego_meta_financeiro%' "
        "AND grantee='service_role' ORDER BY 1;")
    assert [c[0] for c in concedidos] == ["SELECT"]


def test_leitura_concorrente_do_grao_devolve_o_mesmo_total(cluster, carregado):
    """Duas sessões simultâneas leem o mesmo total — a view não guarda estado."""
    consulta = ("SELECT sum(spend)::text FROM public.vw_trafego_meta_financeiro_conjunto_dia"
                f" WHERE {NA_JANELA_DO_GOLDEN};")
    processos = [
        subprocess.Popen(["psql", "-X", "-q", "-t", "-A", "-c", consulta],
                         env=cluster["env"], stdout=subprocess.PIPE, text=True)
        for _ in range(4)
    ]
    saidas = [p.communicate()[0].strip() for p in processos]
    assert len(set(saidas)) == 1, f"leituras concorrentes divergiram: {saidas}"
    assert Decimal(saidas[0]) == Decimal("1029.410000")


def test_ciclo_rollback_e_reapply_preserva_o_fato(cluster, carregado):
    antes = _consultar(cluster, "SELECT count(*)::text FROM public.trafego_meta_insight_daily;")[0][0]

    r = cluster["arquivo"](ROLLBACK)
    assert r.returncode == 0, r.stderr[-800:]
    sobrou = _consultar(cluster,
        "SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname LIKE 'vw_trafego_meta_financeiro%';")
    assert int(sobrou[0][0]) == 0
    # O rollback derruba VIEW; o fato não pode ter sido tocado.
    depois = _consultar(cluster, "SELECT count(*)::text FROM public.trafego_meta_insight_daily;")[0][0]
    assert depois == antes

    r = cluster["arquivo"](CANDIDATA)
    assert r.returncode == 0, r.stderr[-800:]
    total = _consultar(cluster,
        "SELECT sum(spend)::text FROM public.vw_trafego_meta_financeiro_conjunto_dia"
        f" WHERE {NA_JANELA_DO_GOLDEN};")
    assert Decimal(total[0][0]) == Decimal("1029.410000"), "reapply precisa devolver a mesma conta"


def test_replay_da_migration_por_cima_e_idempotente(cluster, carregado):
    r = cluster["arquivo"](CANDIDATA)
    assert r.returncode == 0, r.stderr[-800:]
    r = cluster["arquivo"](CANDIDATA)
    assert r.returncode == 0, r.stderr[-800:]
    total = _consultar(cluster,
        "SELECT sum(spend)::text FROM public.vw_trafego_meta_financeiro_conjunto_dia"
        f" WHERE {NA_JANELA_DO_GOLDEN};")
    assert Decimal(total[0][0]) == Decimal("1029.410000")
