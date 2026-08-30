"""Regressão do gerador do Mapa Vivo — a curadoria humana precisa sobreviver.

## Por que este arquivo existe

Em 24/08/2026 a curadoria operacional foi editada em
`docs/volc-os-graph/volc-os-graph.json` e **desapareceu no build seguinte**: aquele
arquivo é saída gerada, e a curadoria de verdade morava numa lista embutida no
gerador. O `CLAUDE.md` apontava a saída como "fonte curada", então seguir a
instrução ao pé da letra custava o trabalho.

O conserto foi separar a fonte humana (`curadoria-operacional.json`) da saída. Estes
testes são o que impede o defeito de voltar: eles provam que a curadoria sobrevive ao
rebuild, que erro de curadoria falha alto em vez de sumir em silêncio, e que dois
builds do mesmo insumo produzem os mesmos bytes.

Rodar:
    backend/.venv/bin/python -m pytest scripts/tests/test_curadoria_do_grafo.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
GERADOR = RAIZ / "scripts" / "gerar_grafo_volc_os.py"
CURADORIA = RAIZ / "docs" / "volc-os-graph" / "curadoria-operacional.json"
SAIDA = RAIZ / "docs" / "volc-os-graph" / "volc-os-graph.json"
DB_SNAPSHOT = Path("/private/tmp/volc-supabase-inventory.json")

# O gerador exige o snapshot do Supabase; sem ele o build inteiro não roda e os
# testes que dependem de execução real não têm o que provar.
precisa_snapshot = pytest.mark.skipif(
    not DB_SNAPSHOT.exists(),
    reason="snapshot do Supabase ausente — rode scripts/inventariar_supabase.py",
)


def _carregar_gerador():
    """Importa o gerador como módulo isolado, sem rodar `main()`."""
    spec = importlib.util.spec_from_file_location("gerador_grafo", GERADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rebuild():
    r = subprocess.run([sys.executable, str(GERADOR)], cwd=RAIZ,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"o gerador falhou:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── a curadoria é fonte, não saída ────────────────────────────────────────────

def test_a_fonte_humana_existe_e_e_valida():
    assert CURADORIA.exists(), "a fonte humana da curadoria não existe"
    cur = json.loads(CURADORIA.read_text())
    for chave in ("meta", "capabilities", "concepts", "documents", "edges", "priorities"):
        assert chave in cur, f"falta a chave '{chave}'"
    assert cur["capabilities"], "curadoria sem capacidades"


def test_a_saida_se_declara_gerada():
    """Quem abrir a saída precisa descobrir, ali mesmo, que não é lugar de editar."""
    meta = json.loads(SAIDA.read_text())["meta"]
    assert meta.get("gerado") is True
    assert "curadoria-operacional.json" in meta.get("fonte_curada", "")
    assert "nao_editar" in meta


@precisa_snapshot
def test_a_curadoria_sobrevive_ao_rebuild():
    """O defeito original, em forma de teste: um conceito curado continua no grafo
    depois de reconstruir."""
    cur = json.loads(CURADORIA.read_text())
    esperados = {c["id"] for c in cur["capabilities"]} | {c["id"] for c in cur["concepts"]} \
        | {d["id"] for d in cur["documents"]}
    _rebuild()
    presentes = {n["id"] for n in json.loads(SAIDA.read_text())["nodes"]}
    faltando = esperados - presentes
    assert not faltando, f"a regeneração apagou nós curados: {sorted(faltando)}"


@precisa_snapshot
def test_um_segundo_rebuild_nao_apaga_decisao_humana():
    """Um build já passou acima; o segundo é o que pegava o defeito antigo."""
    cur = json.loads(CURADORIA.read_text())
    esperados = {c["id"] for c in cur["capabilities"]} | {c["id"] for c in cur["concepts"]}
    _rebuild()
    _rebuild()
    presentes = {n["id"] for n in json.loads(SAIDA.read_text())["nodes"]}
    assert esperados <= presentes, "o segundo rebuild perdeu decisões humanas"


@precisa_snapshot
def test_o_gerador_nao_toca_na_fonte_humana():
    antes = CURADORIA.read_bytes()
    _rebuild()
    assert CURADORIA.read_bytes() == antes, "o gerador escreveu na fonte humana"


@precisa_snapshot
def test_a_saida_e_deterministica():
    """Dois builds do mesmo insumo geram os mesmos bytes — sem isso, o diff do mapa
    vira ruído e ninguém revisa mudança de grafo."""
    _rebuild()
    primeiro = SAIDA.read_bytes()
    _rebuild()
    assert SAIDA.read_bytes() == primeiro, "a saída não é determinística"


# ── erro de curadoria falha alto ──────────────────────────────────────────────

def _curadoria_temporaria(tmp_path: Path, mutacao) -> "tuple":
    """Devolve (módulo, restaurar) com a curadoria apontada para uma cópia mutada."""
    cur = json.loads(CURADORIA.read_text())
    mutacao(cur)
    alvo = tmp_path / "curadoria-operacional.json"
    alvo.write_text(json.dumps(cur, ensure_ascii=False))
    mod = _carregar_gerador()
    mod.CURADORIA = alvo
    return mod


def test_id_duplicado_falha_dizendo_qual_e_onde(tmp_path):
    """A mensagem precisa nomear o id e as duas seções — "ID duplicado" sozinho
    manda o humano procurar a agulha em 59 nós."""
    duplicado = json.loads(CURADORIA.read_text())["capabilities"][0]["id"]

    def duplicar(cur):
        cur["concepts"].append(dict(cur["capabilities"][0]))
    mod = _curadoria_temporaria(tmp_path, duplicar)
    with pytest.raises(SystemExit) as exc:
        mod.carregar_curadoria()
    msg = str(exc.value)
    assert "ID duplicado" in msg, msg
    assert duplicado in msg, f"a mensagem não diz QUAL id: {msg}"
    assert "capabilities" in msg and "concepts" in msg, f"não diz ONDE: {msg}"


def test_cluster_inexistente_falha(tmp_path):
    def quebrar(cur):
        cur["capabilities"][0]["cluster"] = "nao_existe"
    mod = _curadoria_temporaria(tmp_path, quebrar)
    with pytest.raises(SystemExit, match="cluster inexistente"):
        mod.carregar_curadoria()


def test_estado_inexistente_falha(tmp_path):
    def quebrar(cur):
        cur["concepts"][0]["state"] = "talvez"
    mod = _curadoria_temporaria(tmp_path, quebrar)
    with pytest.raises(SystemExit, match="estado inexistente"):
        mod.carregar_curadoria()


def test_campo_obrigatorio_ausente_falha(tmp_path):
    def quebrar(cur):
        cur["capabilities"][0].pop("evidence")
    mod = _curadoria_temporaria(tmp_path, quebrar)
    with pytest.raises(SystemExit, match="sem 'evidence'"):
        mod.carregar_curadoria()


def test_relacao_com_destino_inexistente_falha(tmp_path):
    """⚠️ `add_edge` descarta em silêncio aresta com ponta faltando — correto para
    relação inferida de código, e errado para curada. Este teste protege a diferença."""
    def quebrar(cur):
        cur["edges"].append({"source": "cap_traffic_queue",
                             "target": "cap_que_nunca_existiu",
                             "relation": "aponta_para_o_vazio"})
    mod = _curadoria_temporaria(tmp_path, quebrar)
    cur = mod.carregar_curadoria()          # a validação de referência não é aqui
    mod.adicionar_nos_curados(cur)
    with pytest.raises(SystemExit) as exc:
        mod.aplicar_arestas_curadas(cur)
    msg = str(exc.value)
    assert "destino inexistente" in msg and "cap_que_nunca_existiu" in msg, msg


def test_relacao_com_origem_inexistente_falha(tmp_path):
    def quebrar(cur):
        cur["edges"].append({"source": "cap_fantasma",
                             "target": "cap_traffic_queue", "relation": "x"})
    mod = _curadoria_temporaria(tmp_path, quebrar)
    cur = mod.carregar_curadoria()
    mod.adicionar_nos_curados(cur)
    with pytest.raises(SystemExit, match="origem inexistente"):
        mod.aplicar_arestas_curadas(cur)


def test_documento_apontando_para_capacidade_inexistente_falha(tmp_path):
    def quebrar(cur):
        cur["documents"].append({"id": "doc:orfao", "label": "Órfão",
                                 "cluster": "acquisition", "documenta": "cap_inexistente"})
    mod = _curadoria_temporaria(tmp_path, quebrar)
    cur = mod.carregar_curadoria()
    mod.adicionar_nos_curados(cur)
    with pytest.raises(SystemExit, match="destino inexistente"):
        mod.aplicar_arestas_curadas(cur)


def test_curadoria_ausente_falha_dizendo_o_que_e(tmp_path):
    mod = _carregar_gerador()
    mod.CURADORIA = tmp_path / "nao-existe.json"
    with pytest.raises(SystemExit, match="fonte humana"):
        mod.carregar_curadoria()


def test_json_invalido_falha(tmp_path):
    alvo = tmp_path / "curadoria-operacional.json"
    alvo.write_text("{ isto não é json ]")
    mod = _carregar_gerador()
    mod.CURADORIA = alvo
    with pytest.raises(SystemExit, match="JSON inválido"):
        mod.carregar_curadoria()
