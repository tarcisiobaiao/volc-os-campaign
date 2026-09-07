"""Provas herméticas do perfil de schema Meta — manifesto, verificador e leitor.

## Por que este arquivo existe

`SCHEMA-DEPLOY-MANIFEST.json` é a ÚNICA lista canônica de arquivos, ordem e
checksums do apply. Ele carregava, ao mesmo tempo:

  * um `produced_on_commit` que não continha três dos arquivos que ele declara;
  * contagens de diretório de uma árvore mais antiga (50/48/20 contra 56/54/23);
  * uma evidência de ciclo local descrevendo o apply de TRÊS arquivos enquanto o
    perfil tem CINCO — contradizendo `why_five_files` no mesmo arquivo;
  * dois perfis sem sonda de catálogo e sem contrato de runtime, num programa que
    rodava a conferência de runtime para TODOS eles contra uma fonte fixa.

Nada disso quebrava nada em tempo de execução. Era proveniência falsa: números
que ninguém mediu, num documento que existe justamente para ser a medida.

⚠️ **Estes testes MEDEM.** Nenhum número aqui é copiado do manifesto para o
teste; cada um é recontado a partir do disco e comparado com o que o manifesto
afirma. Um teste que copia o número prova apenas que a cópia deu certo.

## E eles não tocam banco nenhum

Zero rede, zero `psql`, zero credencial. O que se prova aqui é o LEITOR e o
VERIFICADOR — quem roda contra o catálogo oficial é um ato humano autorizado, em
outro momento, com estes dois já conferidos.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "docs/closure/traffic-operational-closure-v2"
MANIFESTO = PACOTE / "SCHEMA-DEPLOY-MANIFEST.json"
LEITOR_SQL = PACOTE / "ler-catalogo-meta.sql"
VERIFICADOR = RAIZ / "scripts/verificar_perfil_schema_meta.py"
MIGRATIONS = RAIZ / "supabase/migrations"

PERFIS = ("CREATE_ONLY", "META_READ_MODEL", "GOOGLE_PMAX")
PERFIS_META = ("CREATE_ONLY", "META_READ_MODEL")

#: A ordem única da união dos dois perfis Meta, conferida arquivo a arquivo.
#: `v13_01` e `v15_01` aparecem nos DOIS `apply_order`, com o MESMO sha256, e são
#: aplicados UMA vez — aplicá-los duas vezes faria a própria guarda abortar com
#: "ja parece aplicada", no meio da janela.
UNIAO_ESPERADA = [
    "v13_01_cofre_de_ativos.sql",
    "v15_01_meta_ads_read_model.sql",
    "20260904183418_meta_create_paused_executor.sql",
    "20260907120000_meta_recovery_snapshot.sql",
    "20260907190000_meta_worker_fencing.sql",
    "v15_02_meta_ads_insights.sql",
    "20260907210000_meta_read_model_consistency.sql",
]


def _carregar_verificador():
    """Importa o script pelo caminho — ele não vive num pacote importável."""
    spec = importlib.util.spec_from_file_location("verificador_schema_meta", VERIFICADOR)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


vsm = _carregar_verificador()


@pytest.fixture(scope="module")
def manifesto() -> dict:
    return json.loads(MANIFESTO.read_text(encoding="utf-8"))


def _perfil(manifesto: dict, nome: str) -> dict:
    for perfil in manifesto["profiles"]:
        if perfil["id"] == nome:
            return perfil
    raise AssertionError(f"o manifesto não declara o perfil {nome}")


def _rodar(*argumentos: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFICADOR), *argumentos],
        cwd=RAIZ, capture_output=True, text=True, timeout=120)


# ---------------------------------------------------------------------------
# O verificador roda, e falha pelo motivo certo — nunca por estouro
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", PERFIS)
def test_nenhum_perfil_estoura_o_verificador(nome: str) -> None:
    """Sair com erro é legítimo; sair com `AttributeError` não é conferência.

    ⚠️ `--perfil META_READ_MODEL` saía com 1 acusando o perfil de não declarar
    catorze RPCs do NASCIMENTO — que ele nunca serviu. O verificador rodava
    `conferir_runtime` para qualquer perfil contra uma fonte fixa
    (`meta_execucao/registro.py`), e um perfil sem `runtime_contract` era
    reprovado por não ser outro perfil.
    """
    saida = _rodar("--perfil", nome)
    assert "Traceback" not in saida.stderr, saida.stderr
    for estouro in ("AttributeError", "KeyError", "TypeError", "IndexError"):
        assert estouro not in saida.stderr, saida.stderr
    assert saida.returncode in (0, 1), saida


def test_meta_read_model_passa() -> None:
    saida = _rodar("--perfil", "META_READ_MODEL")
    assert saida.returncode == 0, saida.stderr
    assert "perfil META_READ_MODEL: conferido" in saida.stdout


def test_create_only_continua_passando() -> None:
    saida = _rodar("--perfil", "CREATE_ONLY")
    assert saida.returncode == 0, saida.stderr


def test_google_pmax_falha_com_lacuna_nomeada() -> None:
    """Perfil sem contrato de runtime é LACUNA NOMEADA, e lacuna não é sucesso.

    Pular em silêncio o que ninguém declarou é o defeito de R0-A01 com outra
    roupa: o verde afirmaria uma cobertura que ninguém mediu.
    `v12_03_pmax_observability_ledger.sql` não cria função nenhuma, então um
    contrato vazio seria uma AFIRMAÇÃO sobre consumidores que ninguém inventariou.
    """
    saida = _rodar("--perfil", "GOOGLE_PMAX")
    assert saida.returncode == 1
    assert "LACUNA NOMEADA" in saida.stderr
    assert "não declara contrato de runtime" in saida.stderr
    assert "Traceback" not in saida.stderr


# ---------------------------------------------------------------------------
# --arquivos: os checksums são do DISCO, recontados aqui
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", PERFIS)
def test_arquivos_passa_nos_tres_perfis(nome: str) -> None:
    saida = _rodar("--perfil", nome, "--arquivos")
    assert saida.returncode == 0, saida.stderr


@pytest.mark.parametrize("nome", PERFIS)
def test_sha256_declarado_bate_com_o_disco(manifesto: dict, nome: str) -> None:
    """Recontado aqui, e não perguntado ao verificador: se os dois errarem do
    mesmo jeito, um teste que só chama o verificador concorda com o erro."""
    perfil = _perfil(manifesto, nome)
    declarados = list(perfil["apply_order"]) + list(
        perfil.get("rollback_files_never_in_apply", []))
    assert declarados
    for item in declarados:
        caminho = RAIZ / item["file"]
        assert caminho.exists(), f"{item['file']} declarado e ausente"
        real = hashlib.sha256(caminho.read_bytes()).hexdigest()
        assert real == item["sha256"], f"{item['file']}: manifesto diverge do disco"


# ---------------------------------------------------------------------------
# Rollback nunca entra no apply — erro de CONSTRUÇÃO, não aviso
# ---------------------------------------------------------------------------

def test_nenhum_rollback_em_nenhum_apply_order(manifesto: dict) -> None:
    """Critério duplo: o que os perfis DECLARAM como rollback, e o que o
    diretório mostra pelo nome. Um arquivo novo `*_rollback.sql` que alguém
    colocasse num `apply_order` sem declará-lo passaria pelo primeiro critério."""
    declarados = {
        item["file"]
        for perfil in manifesto["profiles"]
        for item in perfil.get("rollback_files_never_in_apply", [])
    }
    por_nome = {
        f"supabase/migrations/{caminho.name}"
        for caminho in MIGRATIONS.glob("*.sql")
        if "rollback" in caminho.name.lower()
    }
    assert declarados <= por_nome, "rollback declarado que o nome não denuncia"
    proibidos = declarados | por_nome
    for perfil in manifesto["profiles"]:
        for passo in perfil["apply_order"]:
            assert passo["file"] not in proibidos, (
                f"{perfil['id']}: {passo['file']} é rollback e está no apply")


# ---------------------------------------------------------------------------
# A união dos dois perfis Meta: sete arquivos, compartilhadas UMA vez
# ---------------------------------------------------------------------------

def test_ordem_unica_da_uniao_meta(manifesto: dict) -> None:
    uniao: list[str] = []
    for nome in PERFIS_META:
        for passo in _perfil(manifesto, nome)["apply_order"]:
            arquivo = Path(passo["file"]).name
            if arquivo not in uniao:
                uniao.append(arquivo)
    assert uniao == UNIAO_ESPERADA


def test_compartilhadas_tem_o_mesmo_sha256_nos_dois_perfis(manifesto: dict) -> None:
    """`v13_01` e `v15_01` só podem ser aplicadas UMA vez porque são o MESMO
    arquivo. Se os dois perfis declarassem sha256 diferentes, "aplicar uma vez"
    deixaria de ser verdade e ninguém saberia qual das duas versões rodou."""
    por_arquivo: dict[str, set[str]] = {}
    for nome in PERFIS_META:
        for passo in _perfil(manifesto, nome)["apply_order"]:
            por_arquivo.setdefault(passo["file"], set()).add(passo["sha256"])
    compartilhadas = [
        "supabase/migrations/v13_01_cofre_de_ativos.sql",
        "supabase/migrations/v15_01_meta_ads_read_model.sql",
    ]
    for arquivo in compartilhadas:
        assert len(por_arquivo[arquivo]) == 1, f"{arquivo}: sha256 divergente entre perfis"


def test_lista_apply_e_a_unica_fonte(manifesto: dict) -> None:
    """O runbook manda PEDIR a lista, nunca digitá-la."""
    for nome in PERFIS:
        saida = _rodar("--perfil", nome, "--lista-apply")
        assert saida.returncode == 0, saida.stderr
        esperado = [Path(p["file"]).name for p in _perfil(manifesto, nome)["apply_order"]]
        assert saida.stdout.split() == esperado


# ---------------------------------------------------------------------------
# defined_by é o ÚLTIMO CREATE, e o verificador recalcula
# ---------------------------------------------------------------------------

def test_defined_by_recalculado_bate_com_o_declarado(manifesto: dict) -> None:
    """⚠️ O último, não o primeiro. Onze das catorze funções do nascimento são
    recriadas por mais de um degrau; conferir contra o primeiro aprovaria uma
    assinatura já substituída. `trafego_meta_persistir_snapshot` é o mesmo caso
    do outro lado: v15_02:127 cria e 20260907210000:657 recria."""
    padrao = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+public\.([a-z0-9_]+)")
    conferidas = 0
    for perfil in manifesto["profiles"]:
        contrato = perfil.get("runtime_contract")
        if not contrato:
            continue
        criadores: dict[str, str] = {}
        for passo in perfil["apply_order"]:
            corpo = (RAIZ / passo["file"]).read_text(encoding="utf-8")
            for nome in padrao.findall(corpo):
                criadores[nome] = Path(passo["file"]).name
        for rpc in contrato["rpcs"]:
            assert rpc["name"] in criadores, (
                f"{perfil['id']}/{rpc['name']}: nenhum arquivo do perfil a cria")
            assert rpc["defined_by"] == criadores[rpc["name"]], (
                f"{perfil['id']}/{rpc['name']}: declarado "
                f"{rpc['defined_by']}, último CREATE em {criadores[rpc['name']]}")
            conferidas += 1
    assert conferidas >= 15, "os dois contratos Meta somam 15 RPCs; caíram para menos"


def test_persistir_snapshot_esta_declarada_em_algum_perfil(manifesto: dict) -> None:
    """A RPC que rodava em produção sem perfil nenhum a declarar.

    Chamada em `backend/app/trafego/meta/read_model.py:347` e por um terceiro
    consumidor fora do backend (`n8n/volc_meta_insights_dia_d1.json`), e invisível
    para o verificador porque a fonte de RPCs era fixa em `registro.py`.
    """
    declarada = {
        rpc["name"]
        for perfil in manifesto["profiles"]
        for rpc in perfil.get("runtime_contract", {}).get("rpcs", [])
    }
    assert "trafego_meta_persistir_snapshot" in declarada

    # E a declaração tem de bater com a chamada real e com a assinatura real.
    chamada = (RAIZ / "backend/app/trafego/meta/read_model.py").read_text(encoding="utf-8")
    assert 'rpc("trafego_meta_persistir_snapshot"' in chamada
    criador = (RAIZ / "supabase/migrations/20260907210000_meta_read_model_consistency.sql"
               ).read_text(encoding="utf-8")
    assert ("CREATE OR REPLACE FUNCTION public.trafego_meta_persistir_snapshot(p_snapshot jsonb)"
            in criador)
    perfil = _perfil(manifesto, "META_READ_MODEL")
    (rpc,) = [r for r in perfil["runtime_contract"]["rpcs"]
              if r["name"] == "trafego_meta_persistir_snapshot"]
    assert rpc["identity_args"] == "p_snapshot jsonb"
    assert rpc["security_definer"] is True


def test_fonte_de_rpc_e_por_perfil(manifesto: dict) -> None:
    """Uma fonte fixa para todo perfil foi o que criou os dois defeitos ao mesmo
    tempo: META_READ_MODEL reprovado por RPCs alheias, e a RPC dele sem dono."""
    fontes = {
        perfil["id"]: perfil.get("runtime_contract", {}).get("derivado_de")
        for perfil in manifesto["profiles"]
    }
    assert fontes["CREATE_ONLY"] == "backend/app/trafego/meta_execucao/registro.py"
    assert fontes["META_READ_MODEL"] == "backend/app/trafego/meta/read_model.py"
    assert fontes["CREATE_ONLY"] != fontes["META_READ_MODEL"]
    for perfil_id, fonte in fontes.items():
        if fonte:
            assert (RAIZ / fonte).exists(), f"{perfil_id}: fonte declarada e ausente"


def test_regex_de_chamada_pega_as_duas_formas() -> None:
    """`self._rpc("x")` e `self._supa.rpc("x")` — e nunca a DEFINIÇÃO `def _rpc(`."""
    achados = vsm.PADRAO_CHAMADA_RPC.findall(
        'await self._rpc("a", {})\n'
        'await self._supa.rpc("b", {})\n'
        'def _rpc(self, funcao: str) -> None: ...\n'
        'def payload_rpc(self) -> dict: ...\n')
    assert achados == ["a", "b"]


# ---------------------------------------------------------------------------
# glob_hazard: o teste MEDE o diretório, não copia o número
# ---------------------------------------------------------------------------

def test_glob_hazard_bate_com_a_medicao_do_diretorio(manifesto: dict) -> None:
    """MEDE o diretório agora e cobra o manifesto — nunca o contrário.

    ⚠️ O número tem de viver no manifesto, e o teste tem de medi-lo. Um literal
    escrito aqui viraria mentira no dia seguinte e ninguém saberia: o `glob_hazard`
    é o que impede um `for f in supabase/migrations/*.sql`, e ele só assusta
    enquanto o número for verdade. Quando este teste falha, a mensagem diz
    exatamente qual campo do manifesto reescrever e com que valor.
    """
    perigo = manifesto["glob_hazard"]
    arquivos = sorted(p for p in MIGRATIONS.iterdir() if p.is_file())
    sql = [p for p in arquivos if p.suffix == ".sql"]
    rollbacks = [p for p in sql if "rollback" in p.name.lower()]

    medido = {
        "directory_file_count": len(arquivos),
        "sql_file_count": len(sql),
        "rollback_file_count": len(rollbacks),
    }
    divergentes = {
        campo: (perigo[campo], valor)
        for campo, valor in medido.items() if perigo[campo] != valor
    }
    assert not divergentes, (
        "glob_hazard está desatualizado em "
        f"{MANIFESTO.relative_to(RAIZ)}. Atualize (manifesto -> medido agora): "
        + "; ".join(f"{c}: {d}->{m}" for c, (d, m) in divergentes.items())
        + ". Comandos: `ls -1 supabase/migrations | wc -l`, "
          "`ls -1 supabase/migrations/*.sql | wc -l`, "
          "`ls -1 supabase/migrations/*.sql | grep -ic rollback`")

    assert sorted(perigo["non_sql_files"]) == sorted(
        p.name for p in arquivos if p.suffix != ".sql")


def test_rollback_nao_se_conta_por_grep_de_drop() -> None:
    """⚠️ `grep -l 'DROP '` devolve MAIS que o número de rollbacks, porque
    migrations FORWARD dropam para recriar — `20260907120000:84` dropa a
    assinatura antiga de `approve` antes de criar a estendida. Contar rollback
    por DROP transformaria oito arquivos de apply em "rollbacks"."""
    sql = [p for p in MIGRATIONS.glob("*.sql")]
    com_drop = [p for p in sql if "DROP " in p.read_text(encoding="utf-8")]
    rollbacks = [p for p in sql if "rollback" in p.name.lower()]
    forward_com_drop = [p for p in com_drop if "rollback" not in p.name.lower()]
    assert forward_com_drop, "o critério errado deixou de ser demonstrável"
    assert len(com_drop) > len(rollbacks)


def test_on_error_stop_e_verdade_no_escopo_declarado(manifesto: dict) -> None:
    """A afirmação antiga — "todo arquivo começa com `\\set ON_ERROR_STOP on`" —
    é falsa para o diretório e é o que justifica o executor `psql`. Aqui se prova
    onde ela VALE: nos arquivos que este manifesto manda aplicar e reverter."""
    metacomando = "\\set ON_ERROR_STOP on"
    sem = [p.name for p in sorted(MIGRATIONS.glob("*.sql"))
           if metacomando not in p.read_text(encoding="utf-8")]
    assert sem, "a ressalva do manifesto ficou sem base: agora todos têm"
    assert "v12_03_pmax_observability_ledger.sql" in sem, (
        "o apply_order[0] do GOOGLE_PMAX deixou de ser o contraexemplo")

    # ⚠️ O escopo NÃO é "o trilho Meta por nome". Medido: o padrão de nome do
    # trilho casa arquivos que NÃO têm o meta-comando — hoje,
    # `20260908000000_meta_insights_escopo.sql`. Uma regra por prefixo já
    # nasceria falsa.
    trilho_por_nome = re.compile(r"(^|_)meta(_|\.)|^v15_")
    casam = [p.name for p in sorted(MIGRATIONS.glob("*.sql"))
             if trilho_por_nome.search(p.name)]
    assert any(nome in sem for nome in casam), (
        "se o trilho inteiro passar a ter o meta-comando, a ressalva do "
        "manifesto sobre 'por nome' precisa ser reescrita")

    # O escopo que é verdadeiro é o DECLARADO, e ele é recalculado do manifesto:
    # declarar um arquivo novo passa a exigir o meta-comando dele, sozinho.
    declarados: set[str] = set()
    for nome in PERFIS_META:
        perfil = _perfil(manifesto, nome)
        for item in list(perfil["apply_order"]) + list(
                perfil.get("rollback_files_never_in_apply", [])):
            declarados.add(item["file"])
    assert declarados
    for arquivo in sorted(declarados):
        corpo = (RAIZ / arquivo).read_text(encoding="utf-8")
        assert metacomando in corpo, (
            f"{arquivo} está declarado num perfil Meta e NÃO tem "
            f"{metacomando!r}: a regra do executor `psql` deixou de valer para "
            "o perfil que o declara")

    afirmacao = manifesto["glob_hazard"]["on_error_stop_scope"]
    assert str(len(sem)) in afirmacao, (
        f"o manifesto afirma um número que não medi: são {len(sem)} arquivos "
        f"sem {metacomando!r} — atualize glob_hazard.on_error_stop_scope")


# ---------------------------------------------------------------------------
# Proveniência: o commit carimbado tem de conter o que o manifesto declara
# ---------------------------------------------------------------------------

def test_commit_de_proveniencia_contem_os_arquivos_declarados(manifesto: dict) -> None:
    """⚠️ O carimbo anterior (`d54e100`) NÃO continha três dos arquivos que este
    manifesto declara com sha256. Um manifesto que aponta para uma árvore sem os
    próprios arquivos não tem proveniência — tem uma frase."""
    commit = manifesto["produced_on_commit"]
    declarados = sorted({
        item["file"]
        for perfil in manifesto["profiles"]
        for item in list(perfil["apply_order"]) + list(
            perfil.get("rollback_files_never_in_apply", []))
    })
    if not (RAIZ / ".git").exists():
        pytest.skip("sem árvore git; a proveniência não é verificável aqui")
    for arquivo in declarados:
        conferencia = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{arquivo}"],
            cwd=RAIZ, capture_output=True, text=True)
        assert conferencia.returncode == 0, (
            f"{arquivo} não existe em {commit}: proveniência falsa")


def test_evidencia_do_ciclo_local_fala_dos_cinco_arquivos(manifesto: dict) -> None:
    """A evidência descrevia o apply de TRÊS arquivos enquanto o perfil tem
    CINCO — contradizendo `why_five_files` no mesmo arquivo."""
    perfil = _perfil(manifesto, "CREATE_ONLY")
    quantos = len(perfil["apply_order"])
    assert quantos == 5
    primeiro = manifesto["local_cycle_evidence"]["sequence"][0]
    assert primeiro["step"] == "apply"
    for arquivo in perfil["apply_order"]:
        raiz_do_nome = Path(arquivo["file"]).name.split("_")[0]
        assert raiz_do_nome in primeiro["detail"], (
            f"{raiz_do_nome} fora da sequência de apply da evidência")
    assert "tres" not in primeiro["result"].lower()


# ---------------------------------------------------------------------------
# As sondas de catálogo: derivadas do .sql, nunca inventadas
# ---------------------------------------------------------------------------

def _objetos_da_sonda(sonda: dict) -> list[tuple[str, str]]:
    """(chave, nome procurável no .sql) para cada item de uma sonda."""
    itens: list[tuple[str, str]] = []
    for chave, valores in sonda.items():
        for valor in valores:
            if chave == "columns":
                itens.append((chave, valor.split(".", 1)[1]))
            elif chave in ("indexes", "relations"):
                itens.append((chave, valor.split(".")[-1].split(":")[0]))
            elif chave == "triggers":
                tabela, gatilho = valor.split(".", 1)
                # O nome é montado com `format('%I', t || '_sem_truncate')`, então
                # o literal não aparece no arquivo — o sufixo aparece.
                itens.append((chave, gatilho[len(tabela):]))
            elif chave in ("functions", "granted_to_service_role"):
                itens.append((chave, valor.split("(", 1)[0]))
            elif chave == "grants":
                itens.append((chave, valor.split(":", 1)[0].split("(", 1)[0]))
            else:
                itens.append((chave, valor))
    return itens


@pytest.mark.parametrize("nome", PERFIS_META)
def test_toda_sonda_aponta_para_algo_que_o_arquivo_cria(manifesto: dict, nome: str) -> None:
    """⚠️ Não inventar coluna, constraint, índice, gatilho, assinatura ou grant.
    Se o nome não está no .sql do degrau, a sonda é ficção — e uma sonda de
    ficção reprova para sempre um catálogo correto."""
    perfil = _perfil(manifesto, nome)
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    assert degraus, f"{nome}: nenhum degrau tem catalog_probe"
    for passo in degraus:
        corpo = (RAIZ / passo["file"]).read_text(encoding="utf-8")
        for chave, procurado in _objetos_da_sonda(passo["catalog_probe"]):
            assert procurado in corpo, (
                f"{nome}/{Path(passo['file']).name}: sonda {chave}={procurado!r} "
                "não aparece no arquivo que deveria criá-la")


@pytest.mark.parametrize("nome", PERFIS_META)
def test_toda_chave_de_sonda_e_conhecida(manifesto: dict, nome: str) -> None:
    """Chave desconhecida daria um degrau por presente sem nada ser conferido."""
    for passo in _perfil(manifesto, nome)["apply_order"]:
        for chave in passo.get("catalog_probe", {}):
            assert chave in vsm.SONDAS, f"{nome}: sonda desconhecida {chave}"


def test_sonda_desconhecida_e_violacao() -> None:
    faltas = vsm._ausentes({"contraints": ["qualquer"]}, {})
    assert faltas and "sonda desconhecida" in faltas[0]


def test_guarda_de_20260907210000_omite_project_binding(manifesto: dict) -> None:
    """A guarda do .sql cobra OITO das NOVE tabelas de v15_01.

    Um catálogo sem `trafego_meta_project_binding` (v15_01:93) passa por ela. O
    conserto do arquivo pertence a quem edita migrations; o que se prova aqui é
    que o manifesto NOMEIA a lacuna e que a sonda do degrau `v15_01` cobra a
    tabela que a guarda deixa passar.
    """
    guarda = (RAIZ / "supabase/migrations/20260907210000_meta_read_model_consistency.sql"
              ).read_text(encoding="utf-8")
    criador = (RAIZ / "supabase/migrations/v15_01_meta_ads_read_model.sql"
               ).read_text(encoding="utf-8")
    tabelas_de_v15_01 = re.findall(r"CREATE TABLE public\.([a-z0-9_]+)", criador)
    assert len(tabelas_de_v15_01) == 9
    assert "trafego_meta_project_binding" in tabelas_de_v15_01

    # A lacuna medida: o bloco de dependência da guarda não cita a tabela.
    inicio = guarda.index("depende de v15_01_meta_ads_read_model.sql")
    bloco = guarda[max(0, inicio - 900):inicio]
    assert "trafego_meta_project_binding" not in bloco

    passo = _perfil(manifesto, "META_READ_MODEL")["apply_order"][1]
    assert Path(passo["file"]).name == "v15_01_meta_ads_read_model.sql"
    lacuna = passo["dependency_guard_gap"]
    assert sorted(lacuna["lista_correta_de_v15_01"]) == sorted(tabelas_de_v15_01)
    assert set(lacuna["declara"]) < set(lacuna["lista_correta_de_v15_01"])
    # E a sonda cobra o que a guarda perdoa.
    sondados = " ".join(str(v) for v in passo["catalog_probe"].values())
    assert "trafego_meta_project_binding" in sondados


# ---------------------------------------------------------------------------
# A escada, exercitada com catálogos sintéticos (nenhum banco envolvido)
# ---------------------------------------------------------------------------

def _catalogo_dos_degraus(perfil: dict, ate: int) -> dict:
    """Monta o JSON que o leitor produziria se os `ate` primeiros degraus
    estivessem aplicados. Cada item vem da própria sonda — que, por sua vez, já
    foi provada contra o .sql em `test_toda_sonda_aponta_para_algo_que_o_arquivo_cria`."""
    catalogo: dict = {
        "relations": [], "columns": [], "constraints": [], "indexes": [],
        "triggers": [], "functions": [], "granted": [], "grants": [],
        "security_definer": [], "rls": {"enabled": [], "forced": [], "policies": []},
    }
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    destino = {
        "relations": catalogo["relations"], "columns": catalogo["columns"],
        "constraints": catalogo["constraints"], "indexes": catalogo["indexes"],
        "triggers": catalogo["triggers"], "functions": catalogo["functions"],
        "granted_to_service_role": catalogo["granted"], "grants": catalogo["grants"],
        "rls_enabled": catalogo["rls"]["enabled"],
        "rls_forced": catalogo["rls"]["forced"],
        "policies": catalogo["rls"]["policies"],
    }
    for passo in degraus[:ate]:
        for chave, valores in passo["catalog_probe"].items():
            destino[chave].extend(valores)
    # A sonda de degrau prova a ESCADA; o contrato de runtime prova o que o
    # código exige. Quando a escada está inteira, as assinaturas do contrato
    # também estão vivas — senão `conferir_contrato_no_catalogo` reprovaria um
    # catálogo que a própria escada acabou de dar por completo.
    if ate == len(degraus):
        contrato = perfil.get("runtime_contract", {}).get("rpcs", [])
        assinaturas = [f"{r['name']}({r['identity_args']})" for r in contrato]
        catalogo["functions"].extend(assinaturas)
        catalogo["granted"].extend(
            a for a, r in zip(assinaturas, contrato) if r.get("service_role_execute", True))
        catalogo["security_definer"].extend(
            a for a, r in zip(assinaturas, contrato) if r.get("security_definer", True))
    # `functions` e `granted` compartilham assinatura; SECURITY DEFINER idem.
    catalogo["functions"] = sorted(set(catalogo["functions"]) | set(catalogo["granted"]))
    catalogo["security_definer"] = sorted(
        set(catalogo["security_definer"]) | set(catalogo["functions"]))
    return catalogo


@pytest.mark.parametrize("nome", PERFIS_META)
def test_escada_completa_classifica_como_perfil_atual(manifesto: dict, nome: str) -> None:
    perfil = _perfil(manifesto, nome)
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    catalogo = _catalogo_dos_degraus(perfil, len(degraus))
    estado, faltas = vsm.classificar(perfil, catalogo)
    assert estado == "PERFIL_ATUAL", faltas


@pytest.mark.parametrize("nome", PERFIS_META)
def test_escada_pela_metade_nomeia_o_degrau(manifesto: dict, nome: str) -> None:
    perfil = _perfil(manifesto, nome)
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    catalogo = _catalogo_dos_degraus(perfil, len(degraus) - 1)
    estado, _ = vsm.classificar(perfil, catalogo)
    assert estado == f"ESCADA_INCOMPLETA_ATE_{Path(degraus[-2]['file']).name}"


def test_catalogo_sem_project_binding_e_reprovado(manifesto: dict) -> None:
    """O caso exato que a guarda de 20260907210000:141-147 deixaria passar."""
    perfil = _perfil(manifesto, "META_READ_MODEL")
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    catalogo = _catalogo_dos_degraus(perfil, len(degraus))
    catalogo["columns"] = [c for c in catalogo["columns"]
                           if not c.startswith("trafego_meta_project_binding.")]
    catalogo["indexes"] = [i for i in catalogo["indexes"]
                           if "project_binding" not in i]
    estado, faltas = vsm.classificar(perfil, catalogo)
    assert estado != "PERFIL_ATUAL"
    assert any("project_binding" in falta for falta in faltas)


def test_existencia_de_tabela_sozinha_nao_classifica(manifesto: dict) -> None:
    """⚠️ O invariante de R0-A01: CREATE_ONLY antigo e perfil atual têm as MESMAS
    três tabelas. Um catálogo só com relações não pode ser PERFIL_ATUAL."""
    perfil = _perfil(manifesto, "CREATE_ONLY")
    so_tabelas = {
        "relations": [
            "trafego_meta_create_step:r",
            "trafego_meta_create_approval:r",
            "trafego_meta_validation_receipt:r",
        ],
        "columns": [], "constraints": [], "functions": [], "granted": [],
    }
    estado, faltas = vsm.classificar(perfil, so_tabelas)
    assert estado == "NAO_APLICADO"
    assert faltas


def test_perfil_sem_sonda_nao_e_nao_aplicado(manifesto: dict) -> None:
    """Zero sonda devolvia NAO_APLICADO para um catálogo COMPLETO — e o operador
    aplicaria por cima do que já existe."""
    estado, faltas = vsm.classificar(_perfil(manifesto, "GOOGLE_PMAX"), {})
    assert estado == "SEM_SONDA_DECLARADA"
    assert faltas and "catalog_probe" in faltas[0]


def test_sobrecarga_viva_e_fatal(manifesto: dict) -> None:
    """Duas assinaturas com o mesmo nome = PGRST203, e NENHUMA responde."""
    perfil = _perfil(manifesto, "META_READ_MODEL")
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    catalogo = _catalogo_dos_degraus(perfil, len(degraus))
    assert vsm.conferir_contrato_no_catalogo(perfil, catalogo) == []
    catalogo["functions"] = catalogo["functions"] + [
        "trafego_meta_persistir_snapshot(p_snapshot jsonb, p_legado text)"]
    problemas = vsm.conferir_contrato_no_catalogo(perfil, catalogo)
    assert any("sobrecargas vivas" in p for p in problemas)


def test_helpers_sem_grant_nao_sao_defeito(manifesto: dict) -> None:
    """⚠️ `trafego_meta_exigir_service_role()` e
    `trafego_meta_exigir_claim_vigente(...)` NÃO recebem GRANT a service_role, e
    isso é CORRETO (manifesto, `helpers_que_NAO_recebem_grant`). Um verificador
    que varresse o prefixo `trafego_meta%` marcaria falso positivo num schema
    correto — por isso a conferência é contra a lista canônica de RPCs."""
    perfil = _perfil(manifesto, "CREATE_ONLY")
    degraus = [p for p in perfil["apply_order"] if p.get("catalog_probe")]
    catalogo = _catalogo_dos_degraus(perfil, len(degraus))

    helpers = [h["name"] for h in perfil["runtime_contract"]["helpers_que_NAO_recebem_grant"]]
    assert helpers
    vivos = [
        "trafego_meta_exigir_service_role()",
        "trafego_meta_exigir_claim_vigente(p_passo trafego_meta_create_step, p_claim uuid)",
    ]
    # Presentes e SECURITY DEFINER de mentira à parte: eles existem, e NENHUM
    # deles aparece em `granted`.
    catalogo["functions"] = sorted(set(catalogo["functions"]) | set(vivos))
    catalogo["security_definer"] = sorted(
        set(catalogo["security_definer"]) | {vivos[0]})

    # E funções `trafego_meta%` de OUTRO trilho, com grant, vivas no mesmo
    # schema: nem elas nem os helpers podem virar defeito deste perfil. A
    # conferência é contra a lista canônica de RPCs, nunca contra o prefixo.
    de_outro_trilho = [
        "trafego_meta_reservar_registro_ativo(p_a text, p_b text, p_c text, p_d text)",
        "trafego_meta_concluir_registro_ativo(p_a uuid, p_b text, p_c uuid)",
        "trafego_meta_marcar_registro_ativo_ambiguo(p_a uuid, p_b uuid)",
        "trafego_meta_falhar_registro_ativo(p_a uuid, p_b text, p_c uuid)",
    ]
    catalogo["functions"] = sorted(set(catalogo["functions"]) | set(de_outro_trilho))
    catalogo["granted"] = sorted(set(catalogo["granted"]) | set(de_outro_trilho))

    estado, faltas = vsm.classificar(perfil, catalogo)
    assert estado == "PERFIL_ATUAL", faltas
    problemas = vsm.conferir_contrato_no_catalogo(perfil, catalogo)
    assert problemas == [], problemas
    for estranha in vivos + de_outro_trilho:
        nu = estranha.split("(", 1)[0]
        assert not any(nu in p for p in problemas)


def test_migrations_novas_nao_entraram_em_apply_order(manifesto: dict) -> None:
    """Migrations acrescentadas em paralelo NÃO entram em perfil nenhum aqui.

    A ordem delas depende de decisões de integração; declará-las por conta
    própria criaria exatamente a segunda lista que este manifesto existe para
    não ter. O que se prova é que os `apply_order` continuam sendo os declarados.
    """
    declarados = {
        passo["file"]
        for perfil in manifesto["profiles"]
        for passo in perfil["apply_order"]
    }
    em_disco = {f"supabase/migrations/{p.name}" for p in MIGRATIONS.glob("*.sql")}
    assert declarados <= em_disco
    nao_declaradas = sorted(em_disco - declarados)
    assert nao_declaradas, "todo arquivo do diretório entrou em algum perfil"
    # E nenhuma delas pode ter aparecido de contrabando numa ordem de apply.
    for perfil in manifesto["profiles"]:
        for passo in perfil["apply_order"]:
            assert passo["file"] not in nao_declaradas


# ---------------------------------------------------------------------------
# O leitor de catálogo: só lê, e lê o que separa os perfis
# ---------------------------------------------------------------------------

def _sql_sem_comentarios(texto: str) -> str:
    sem_bloco = re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)
    return "\n".join(re.sub(r"--.*$", "", linha) for linha in sem_bloco.splitlines())


def test_leitor_nao_escreve_nada() -> None:
    """⚠️ Ele pode ser apontado para o catálogo oficial. Uma única escrita aqui
    seria uma alteração de schema disfarçada de diagnóstico."""
    corpo = _sql_sem_comentarios(LEITOR_SQL.read_text(encoding="utf-8"))
    for proibido in ("CREATE ", "ALTER ", "DROP ", "INSERT ", "UPDATE ",
                     "DELETE ", "TRUNCATE", "GRANT ", "REVOKE ", "COMMIT", "BEGIN"):
        assert proibido not in corpo.upper(), f"o leitor contém {proibido!r}"


def test_leitor_usa_so_metacomando_compativel_com_psql() -> None:
    corpo = LEITOR_SQL.read_text(encoding="utf-8")
    metacomandos = re.findall(r"^\\(\S+)", corpo, flags=re.M)
    assert metacomandos == ["set"], metacomandos
    assert "\\set ON_ERROR_STOP on" in corpo


def test_leitor_deriva_o_conjunto_em_vez_de_digitar() -> None:
    """A versão anterior digitava DUAS tabelas e por isso era cega para
    `trafego_meta_validation_receipt` e para as nove tabelas de v15_01."""
    corpo = LEITOR_SQL.read_text(encoding="utf-8")
    codigo = _sql_sem_comentarios(corpo)
    assert "LIKE 'trafego_meta%'" in codigo
    # Nenhuma tabela do trilho pode estar digitada no CÓDIGO do leitor.
    for digitada in ("trafego_meta_create_step", "trafego_meta_create_approval",
                     "trafego_meta_validation_receipt", "trafego_meta_insight_daily"):
        assert digitada not in codigo, f"{digitada} está digitada no leitor"


def test_leitor_coleta_o_que_separa_os_perfis() -> None:
    """Existência de tabela não distingue nada. Coluna, constraint, assinatura,
    grant, índice, gatilho e RLS distinguem — e o leitor tem de trazer todos."""
    codigo = _sql_sem_comentarios(LEITOR_SQL.read_text(encoding="utf-8"))
    for chave in ("'relations'", "'columns'", "'constraints'", "'indexes'",
                  "'triggers'", "'rls'", "'functions'", "'functions_detail'",
                  "'security_definer'", "'granted'", "'grants'"):
        assert chave in codigo, f"o leitor não emite {chave}"
    # A parte que só o catálogo tem: retorno, prosecdef e ACL explodida.
    for fonte in ("pg_get_function_identity_arguments", "pg_get_function_result",
                  "prosecdef", "aclexplode", "relrowsecurity", "relforcerowsecurity",
                  "pg_index", "pg_trigger", "pg_policy"):
        assert fonte in codigo, f"o leitor não lê {fonte}"


def test_chaves_emitidas_pelo_leitor_cobrem_as_sondas_conhecidas() -> None:
    """Toda sonda que o verificador sabe conferir precisa ter fonte no leitor —
    senão a sonda reprova por falta de dado, não por schema errado."""
    codigo = _sql_sem_comentarios(LEITOR_SQL.read_text(encoding="utf-8"))
    for caminho, _rotulo in vsm.SONDAS.values():
        for chave in caminho:
            assert f"'{chave}'" in codigo, f"o leitor não emite a chave {chave!r}"
