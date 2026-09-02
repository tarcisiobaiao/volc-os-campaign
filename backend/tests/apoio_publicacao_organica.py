"""Um Postgres descartavel com a v14_01, servido por um PostgREST de mentira.

## Por que um shim de PostgREST, e nao um repositorio de teste

Um repositorio dublê em Python provaria a aplicacao e deixaria
`infraestrutura.py` inteiro sem teste — e e la que mora o filtro que impede a
linha crua do Postgres de chegar ao browser. Este arquivo faz o que
`backend/tests/test_trafego_persistencia.py::shim_de_postgrest` ja fazia para o
Hub de Trafego: um objeto com `.enabled` e `.rpc()` que fala como o
`SupabaseService`, levanta `httpx.HTTPStatusError` com corpo NO FORMATO DO
POSTGREST — inclusive `details` com a linha recusada — e por baixo executa a
funcao governada num Postgres DE VERDADE.

Consequencia: o E2E exercita `RepositorioSupabase`, `CasosDeUso`, `rotas.py`, o
`AdaptadorPostiz` real e a v14_01 real. Nada do caminho de producao e
substituido, exceto a rede.

## Sem driver, e de proposito

Nao ha `psycopg` neste interpretador (conferido em 02/09/2026 nos quatro venvs
do repositorio). O acesso e por `psql`, que existe. Trocar isso por um driver
seria acrescentar dependencia para nao ganhar prova nenhuma.

## Fail-closed

`VOLC_EXIGIR_POSTGRES=1` transforma "nao consegui subir o cluster" em FALHA e
nao em `skip`, igual a `conftest_postgres.py`. Sem a variavel o skip aparece —
mas e um skip VISIVEL, com motivo, e nunca um teste verde.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

RAIZ = Path(__file__).resolve().parents[2]
MIGRACOES = (
    RAIZ / "supabase" / "migrations" / "v11_01_estudio_criativo.sql",
    RAIZ / "supabase" / "migrations" / "v11_02_parque_criativo.sql",
    RAIZ / "supabase" / "migrations" / "v13_01_cofre_de_ativos.sql",
    RAIZ / "supabase" / "migrations" / "v14_01_publicacao_organica.sql",
)

#: Tag de dollar-quoting. Toda insercao de literal confere que o valor nao a
#: contem — caso contrario o SQL montado quebraria (ou pior, mudaria de sentido).
_TAG = "volcpub"
#: Tag do nivel de fora. Ver `Cluster.chamar`.
_TAG_ENVELOPE = "volcenvelope"


def motivo_de_indisponibilidade() -> str | None:
    for binario in ("initdb", "pg_ctl", "psql"):
        if shutil.which(binario) is None:
            return f"binario `{binario}` ausente no PATH"
    for arquivo in MIGRACOES:
        if not arquivo.is_file():
            return f"migration ausente: {arquivo.name}"
    return None


def exigido() -> bool:
    return os.environ.get("VOLC_EXIGIR_POSTGRES", "").strip() in {"1", "true", "sim"}


class ErroDoPostgres(RuntimeError):
    def __init__(self, sqlstate: str, mensagem: str, detalhe: str = "") -> None:
        super().__init__(mensagem)
        self.sqlstate = sqlstate
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass
class Cluster:
    """Um cluster que nasce e morre com a sessao de teste."""

    base: Path
    socket: Path
    dados: Path

    def psql(self, sql: str, *, arquivo: Path | None = None) -> str:
        ambiente = {
            **os.environ, "LC_ALL": "C", "LANG": "C",
            "PGHOST": str(self.socket), "PGUSER": "postgres", "PGDATABASE": "postgres",
        }
        comando = ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1"]
        comando += ["-f", str(arquivo)] if arquivo else ["-c", sql]
        r = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
        if r.returncode != 0:
            raise ErroDoPostgres("XXXXX", r.stderr.strip()[-800:])
        return r.stdout.strip()

    def json(self, sql: str) -> Any:
        bruto = self.psql(sql)
        return json.loads(bruto) if bruto else None

    def chamar(self, sql_da_funcao: str) -> Any:
        """Executa uma funcao governada e devolve o resultado OU levanta.

        O envelope `_chamar` roda a chamada dentro de um bloco com handler, que
        no Postgres e uma SUBTRANSACAO — do mesmo jeito que cada requisicao
        PostgREST e uma transacao propria. Sem esse envelope, o primeiro erro
        abortaria a sessao inteira do psql e os testes seguintes veriam um banco
        em estado invalido.
        """
        # ⚠️ A tag do ENVELOPE e outra, e tem de ser: o SQL interno JA contem
        # `$volcpub$` em volta de cada literal (`_literal`), entao reusar a
        # mesma tag aqui fecharia a string no primeiro literal. Cada nivel de
        # dollar-quoting precisa da sua.
        assert _TAG_ENVELOPE not in sql_da_funcao, "a chamada colide com a tag do envelope"
        envelope = f"SELECT public._chamar(${_TAG_ENVELOPE}${sql_da_funcao}${_TAG_ENVELOPE}$)"
        resposta = self.json(envelope)
        if not resposta.get("ok"):
            raise ErroDoPostgres(
                resposta.get("sqlstate") or "XXXXX",
                resposta.get("message") or "",
                resposta.get("detail") or "",
            )
        return resposta.get("resultado")

    def encerrar(self) -> None:
        subprocess.run(["pg_ctl", "-D", str(self.dados), "-m", "immediate", "stop"],
                       env={**os.environ, "LC_ALL": "C"}, capture_output=True)
        shutil.rmtree(self.base, ignore_errors=True)


def subir_cluster() -> Cluster:
    base = Path(tempfile.mkdtemp(prefix="volc-publicacao-pg."))
    dados, socket = base / "d", base / "s"
    socket.mkdir(parents=True, exist_ok=True)
    ambiente = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def rodar(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(args, env=ambiente, capture_output=True, text=True)

    r = rodar("initdb", "-D", str(dados), "-U", "postgres", "--encoding=UTF8", "--locale=C")
    if r.returncode != 0:
        shutil.rmtree(base, ignore_errors=True)
        raise RuntimeError(f"initdb falhou: {r.stderr[-400:]}")

    # ⚠️ `TimeZone=UTC` e o CONTROLE do teste de timezone, nao conveniencia. Se a
    # conversao de horario local dependesse do TZ do servidor, ela daria certo
    # numa maquina em America/Sao_Paulo e errado aqui — e o defeito so
    # apareceria em producao.
    r = rodar("pg_ctl", "-D", str(dados), "-l", str(base / "pg.log"),
              "-o", f"-k {socket} -h '' -c TimeZone=UTC", "-w", "start")
    if r.returncode != 0:
        shutil.rmtree(base, ignore_errors=True)
        raise RuntimeError(f"pg_ctl start falhou: {r.stderr[-400:]}")

    cluster = Cluster(base=base, socket=socket, dados=dados)
    try:
        # Os papeis do Supabase, com o BYPASSRLS de service_role reproduzido: sem
        # ele o teste concluiria que RLS protege o backend, e ela nao protege —
        # quem protege e o REVOKE nominal.
        cluster.psql(
            "CREATE ROLE anon NOLOGIN NOINHERIT;"
            " CREATE ROLE authenticated NOLOGIN NOINHERIT;"
            " CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;"
            " GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;"
            " ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES"
            "   TO anon, authenticated, service_role;"
            " ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS"
            "   TO anon, authenticated, service_role;"
        )
        for migracao in MIGRACOES:
            cluster.psql("", arquivo=migracao)
        cluster.psql(_ENVELOPE_SQL)
    except Exception:
        cluster.encerrar()
        raise
    return cluster


#: O envelope que transforma excecao em JSON, para que o chamador possa reagir
#: ao SQLSTATE — que e exatamente o que o PostgREST devolve.
_ENVELOPE_SQL = """
CREATE OR REPLACE FUNCTION public._chamar(p_sql text)
RETURNS jsonb LANGUAGE plpgsql AS $envelope$
DECLARE r jsonb; estado text; msg text; det text;
BEGIN
  EXECUTE p_sql INTO r;
  RETURN jsonb_build_object('ok', true, 'resultado', r);
EXCEPTION WHEN others THEN
  GET STACKED DIAGNOSTICS estado = RETURNED_SQLSTATE, msg = MESSAGE_TEXT,
                          det = PG_EXCEPTION_DETAIL;
  RETURN jsonb_build_object('ok', false, 'sqlstate', estado,
                            'message', msg, 'detail', coalesce(det, ''));
END $envelope$;
"""


# ---------------------------------------------------------------------------
# O shim de PostgREST
# ---------------------------------------------------------------------------


@dataclass
class SupabasePsql:
    """Fala como `SupabaseService`, executa no Postgres descartavel.

    ⚠️ O CORPO DE ERRO IMITA O POSTGREST INTEIRO, `details` incluso — e `details`
    e o campo que carrega a LINHA RECUSADA. Um shim que devolvesse so `message`
    faria o filtro de `infraestrutura.py` parecer correto sem nunca ser
    exercitado. E o filtro e a unica coisa entre a senha recusada e a tela.
    """

    cluster: Cluster
    enabled: bool = True
    chamadas: list[str] = field(default_factory=list)

    async def rpc(self, funcao: str, argumentos: dict[str, Any]) -> Any:
        self.chamadas.append(funcao)
        try:
            return self.cluster.chamar(f"SELECT public.{funcao}({_argumentos(argumentos)})")
        except ErroDoPostgres as exc:
            corpo = {
                "code": exc.sqlstate,
                "message": exc.mensagem,
                # A linha crua, como o PostgREST realmente devolve.
                "details": exc.detalhe or None,
                "hint": None,
            }
            resposta = httpx.Response(
                400, json=corpo,
                request=httpx.Request("POST", f"https://exemplo.invalid/rest/v1/rpc/{funcao}"),
            )
            raise httpx.HTTPStatusError("erro do postgrest", request=resposta.request,
                                        response=resposta) from exc


def _argumentos(argumentos: dict[str, Any]) -> str:
    partes: list[str] = []
    for nome, valor in argumentos.items():
        partes.append(f"{nome} := {_literal(nome, valor)}")
    return ", ".join(partes)


def _literal(nome: str, valor: Any) -> str:
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, (dict, list)):
        texto = json.dumps(valor, ensure_ascii=False)
        assert _TAG not in texto, "payload colide com a tag de dollar-quoting"
        return f"${_TAG}${texto}${_TAG}$::jsonb"
    texto = str(valor)
    assert _TAG not in texto, "valor colide com a tag de dollar-quoting"
    literal = f"${_TAG}${texto}${_TAG}$"
    if nome.endswith("_sub") or nome.endswith("_id"):
        # Os ids do dominio sao uuid no banco; `p_chave` e `p_autor_email` nao.
        if _parece_uuid(texto):
            return f"{literal}::uuid"
    if nome == "p_fencing":
        return f"{literal}::bigint"
    return literal


def _parece_uuid(texto: str) -> bool:
    try:
        uuid.UUID(texto)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# ---------------------------------------------------------------------------
# Cenario: dois donos, pecas aprovadas, destinos apto e inapto
# ---------------------------------------------------------------------------


@dataclass
class Cenario:
    dono_a: str
    dono_b: str
    master_a: str
    master_a_v2: str
    master_b: str
    aprov_a: str
    aprov_b: str
    aprov_revogada: str
    destino_apto: str
    destino_inapto: str
    destino_b: str


def semear(cluster: Cluster, *, referencia_do_canal: str = "integ-piloto-0001") -> Cenario:
    """Monta o mesmo cenario do ciclo SQL, pelas funcoes governadas.

    As pecas passam pelos MESMOS gatilhos de producao (`criativo_aprovacao`
    exige job em estado que produz ativo aprovavel E uma rendition `pronta`).
    Uma fixture que contornasse isso provaria um mundo que nao existe.
    """
    dono_a = "11111111-1111-1111-1111-111111111111"
    dono_b = "22222222-2222-2222-2222-222222222222"

    cluster.psql(f"""
    DO $semente$
    DECLARE
      dono_a uuid := '{dono_a}'; dono_b uuid := '{dono_b}';
      proj uuid; brief uuid; job uuid; m1 uuid; m2 uuid;
      projb uuid; briefb uuid; jobb uuid; mb uuid;
    BEGIN
      PERFORM public.cofre_cadastrar_ativo(jsonb_build_object(
        'ativo_id','asset:facebook-page:piloto','kind','facebook_page','cluster','social_presence',
        'nome','Pagina Piloto','plataforma','Facebook','estado','active','criticidade','high',
        'resumo','Pagina monetizada usada no piloto organico do VOLC O.S.',
        'dono_nome','VOLC','dono_custodia','declared',
        'proxima_acao','Ligar a porta de publicacao organica.',
        'capacidades','["publicar"]'::jsonb),
        'semente-cofre-fb-0000001', dono_a, 'a@agenciavolc.com.br');

      PERFORM public.cofre_cadastrar_ativo(jsonb_build_object(
        'ativo_id','asset:instagram-profile:sem-adapter','kind','instagram_profile',
        'cluster','social_presence','nome','Perfil sem adapter','plataforma','Instagram',
        'estado','declared','criticidade','medium',
        'resumo','Perfil inventariado que ainda nao tem integracao no control plane.',
        'dono_nome','VOLC','dono_custodia','declared',
        'proxima_acao','Conectar a integracao no control plane.',
        'capacidades','["publicar"]'::jsonb),
        'semente-cofre-ig-0000001', dono_a, 'a@agenciavolc.com.br');

      INSERT INTO public.criativo_projeto (titulo, dono_id) VALUES ('Projeto A', dono_a)
        RETURNING id INTO proj;
      INSERT INTO public.criativo_briefing (projeto_id, tipo, modo, formatos_pedidos)
        VALUES (proj, 'imagem', 'full_llm', '[{{"slot":"1x1"}}]'::jsonb) RETURNING id INTO brief;
      INSERT INTO public.criativo_job (briefing_id, motor, motor_versao, idempotency_key,
                                       insumo_hash, criado_por, estado, iniciado_em, terminado_em)
        VALUES (brief,'prova','1','semente-job-a-000000000001','h', dono_a, 'succeeded',
                now() - interval '1 hour', now()) RETURNING id INTO job;
      INSERT INTO public.criativo_master (job_id, projeto_id, slot, kind, storage_chave,
             content_hash, mime, motor, motor_versao, insumo_hash, versao)
        VALUES (job, proj, '1x1','imagem','criativos/semente/a-v1.png',
                'sha256:' || repeat('a',64),'image/png','prova','1','h',1) RETURNING id INTO m1;
      INSERT INTO public.criativo_master (job_id, projeto_id, slot, kind, storage_chave,
             content_hash, mime, motor, motor_versao, insumo_hash, versao, raiz_id)
        VALUES (job, proj, '1x1','imagem','criativos/semente/a-v2.png',
                'sha256:' || repeat('b',64),'image/png','prova','1','h',2, m1) RETURNING id INTO m2;
      INSERT INTO public.criativo_rendition (job_id, master_id, slot, estado, largura_pedida,
             altura_pedida, proporcao_rotulo, storage_chave, content_hash, concluida_em)
        VALUES (job, m1, '1x1','pronta',1080,1080,'1:1','criativos/semente/a-v1.png',
                'sha256:' || repeat('a',64), now());
      INSERT INTO public.criativo_rendition (job_id, master_id, slot, estado, largura_pedida,
             altura_pedida, proporcao_rotulo, storage_chave, content_hash, concluida_em)
        VALUES (job, m2, '1x1-v2','pronta',1080,1080,'1:1','criativos/semente/a-v2.png',
                'sha256:' || repeat('b',64), now());

      INSERT INTO public.criativo_projeto (titulo, dono_id) VALUES ('Projeto B', dono_b)
        RETURNING id INTO projb;
      INSERT INTO public.criativo_briefing (projeto_id, tipo, modo, formatos_pedidos)
        VALUES (projb, 'imagem', 'full_llm', '[{{"slot":"1x1"}}]'::jsonb) RETURNING id INTO briefb;
      INSERT INTO public.criativo_job (briefing_id, motor, motor_versao, idempotency_key,
                                       insumo_hash, criado_por, estado, iniciado_em, terminado_em)
        VALUES (briefb,'prova','1','semente-job-b-000000000001','h', dono_b, 'succeeded',
                now() - interval '1 hour', now()) RETURNING id INTO jobb;
      INSERT INTO public.criativo_master (job_id, projeto_id, slot, kind, storage_chave,
             content_hash, mime, motor, motor_versao, insumo_hash, versao)
        VALUES (jobb, projb, '1x1','imagem','criativos/semente/b-v1.png',
                'sha256:' || repeat('c',64),'image/png','prova','1','h',1) RETURNING id INTO mb;
      INSERT INTO public.criativo_rendition (job_id, master_id, slot, estado, largura_pedida,
             altura_pedida, proporcao_rotulo, storage_chave, content_hash, concluida_em)
        VALUES (jobb, mb, '1x1','pronta',1080,1080,'1:1','criativos/semente/b-v1.png',
                'sha256:' || repeat('c',64), now());

      INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade,
             decisao, ator_id) VALUES ('master', m1, 1, 'instagram_organic','aprovado', dono_a);
      INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade,
             decisao, ator_id) VALUES ('master', mb, 1, 'instagram_organic','aprovado', dono_b);
      INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade,
             decisao, ator_id, revogada_em)
        VALUES ('master', m1, 1, 'youtube_shorts','aprovado', dono_a, now());

      PERFORM public.publicacao_organica_registrar_destino(jsonb_build_object(
        'ativo_id','asset:facebook-page:piloto','plataforma','facebook',
        'identidade_logica','PAGINA_PILOTO','referencia_externa','{referencia_do_canal}',
        'adapter_apto', true, 'timezone_padrao','America/Sao_Paulo'),
        'semente-destino-apto-0001', dono_a, 'a@agenciavolc.com.br');
      PERFORM public.publicacao_organica_registrar_destino(jsonb_build_object(
        'ativo_id','asset:instagram-profile:sem-adapter','plataforma','instagram',
        'identidade_logica','PERFIL_SEM_ADAPTER','adapter_apto', false,
        'motivo_inapto','integracao ainda nao conectada no control plane'),
        'semente-destino-inapto-01', dono_a, 'a@agenciavolc.com.br');
      PERFORM public.publicacao_organica_registrar_destino(jsonb_build_object(
        'ativo_id','asset:facebook-page:piloto','plataforma','x',
        'identidade_logica','PAGINA_DO_DONO_B','referencia_externa','integ-b-0001',
        'adapter_apto', true),
        'semente-destino-b-0000001', dono_b, 'b@agenciavolc.com.br');
    END
    $semente$;
    """)

    def um(sql: str) -> str:
        return cluster.psql(sql)

    return Cenario(
        dono_a=dono_a,
        dono_b=dono_b,
        master_a=um("SELECT id::text FROM public.criativo_master WHERE versao=1 "
                    "AND storage_chave LIKE '%a-v1%'"),
        master_a_v2=um("SELECT id::text FROM public.criativo_master WHERE versao=2"),
        master_b=um("SELECT id::text FROM public.criativo_master WHERE storage_chave LIKE '%b-v1%'"),
        aprov_a=um("SELECT a.id::text FROM public.criativo_aprovacao a "
                   "JOIN public.criativo_master m ON m.id=a.subject_id "
                   "WHERE a.decisao='aprovado' AND a.revogada_em IS NULL "
                   "AND m.storage_chave LIKE '%a-v1%'"),
        aprov_b=um("SELECT a.id::text FROM public.criativo_aprovacao a "
                   "JOIN public.criativo_master m ON m.id=a.subject_id "
                   "WHERE a.decisao='aprovado' AND a.revogada_em IS NULL "
                   "AND m.storage_chave LIKE '%b-v1%'"),
        aprov_revogada=um("SELECT id::text FROM public.criativo_aprovacao "
                          "WHERE revogada_em IS NOT NULL"),
        destino_apto=um("SELECT id::text FROM public.publicacao_organica_destino "
                        "WHERE identidade_logica='PAGINA_PILOTO'"),
        destino_inapto=um("SELECT id::text FROM public.publicacao_organica_destino "
                          "WHERE identidade_logica='PERFIL_SEM_ADAPTER'"),
        destino_b=um("SELECT id::text FROM public.publicacao_organica_destino "
                     "WHERE identidade_logica='PAGINA_DO_DONO_B'"),
    )
