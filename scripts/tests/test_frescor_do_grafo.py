"""O gate de frescor do Mapa Vivo — e por que ele precisa existir num clone.

## O defeito que este arquivo fecha

Até 06/09/2026 o gate oficial de frescor era `--check`, e ele só sabia responder
lendo `graphify-out/UPDATE_STATUS.json`. Só que `graphify-out/` inteiro é
derivado e **ignorado pelo Git**, de propósito — carrega dezenas de MB. Em
qualquer clone ou worktree limpa o gate respondia:

    {"current": false, "reason": "UPDATE_STATUS.json ausente"}

Não porque o grafo estivesse velho: porque a evidência era irreproduzível. Um
artefato de fechamento afirmava `current=true` e ninguém de fora conseguia
conferir a afirmação. Foi o único achado bloqueante da revisão independente.

O conserto é um manifesto pequeno e VERSIONADO
(`docs/volc-os-graph/BUILD-STATUS.json`), que qualquer clone tem, com o digest
dos insumos. O `graphify-out/UPDATE_STATUS.json` continua sendo escrito como
espelho local e deixou de decidir qualquer coisa.

Rodar:
    backend/.venv/bin/python -m pytest scripts/tests/test_frescor_do_grafo.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "atualizar_grafo_volc_os.py"
MANIFESTO = RAIZ / "docs" / "volc-os-graph" / "BUILD-STATUS.json"


def _modulo():
    spec = importlib.util.spec_from_file_location("atualizar_grafo", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _check(cwd: Path = RAIZ) -> tuple[int, dict]:
    """Roda o gate como um humano rodaria, e devolve (exit code, corpo)."""
    saida = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=cwd, capture_output=True, text=True,
    )
    try:
        corpo = json.loads(saida.stdout)
    except json.JSONDecodeError:  # pragma: no cover - só em falha real
        pytest.fail(f"--check não devolveu JSON: {saida.stdout!r} {saida.stderr!r}")
    return saida.returncode, corpo


@pytest.fixture
def manifesto_restaurado():
    """Guarda o manifesto e o devolve intacto — mesmo se o teste explodir."""
    original = MANIFESTO.read_bytes() if MANIFESTO.exists() else None
    yield
    if original is None:
        MANIFESTO.unlink(missing_ok=True)
    else:
        MANIFESTO.write_bytes(original)


# ═══════════════════════════════════════════════════════════════════════════
# 1 · A AUTORIDADE É VERSIONADA
# ═══════════════════════════════════════════════════════════════════════════


def test_o_manifesto_versionado_e_a_autoridade_e_responde_current():
    """CONTRAPROVA 1: manifesto válido → `current: true` e exit 0."""
    codigo, corpo = _check()
    assert codigo == 0, corpo
    assert corpo["current"] is True
    assert corpo["reason"] == "insumos idênticos"
    assert corpo["authority"] == "docs/volc-os-graph/BUILD-STATUS.json"


def test_o_manifesto_esta_versionado_e_o_graphify_out_nao():
    """CONTRAPROVA 9: a autoridade é rastreada; a saída pesada não entrou."""
    rastreado = subprocess.run(
        ["git", "ls-files", "--error-unmatch",
         "docs/volc-os-graph/BUILD-STATUS.json"],
        cwd=RAIZ, capture_output=True, text=True)
    assert rastreado.returncode == 0, "o manifesto precisa estar versionado"

    versionados = subprocess.run(
        ["git", "ls-files", "graphify-out"],
        cwd=RAIZ, check=True, capture_output=True, text=True).stdout.strip()
    assert versionados == "", (
        "algum arquivo de graphify-out/ foi versionado: " + versionados)

    ignorado = subprocess.run(
        ["git", "check-ignore", "-q", "graphify-out"],
        cwd=RAIZ, capture_output=True, text=True)
    assert ignorado.returncode == 0, "graphify-out/ deixou de ser ignorado"


def test_o_espelho_local_nunca_e_a_autoridade():
    """CONTRAPROVA 7: sem `graphify-out/UPDATE_STATUS.json`, o gate ainda sabe.

    ⚠️ Esta é a asserção que descreve o defeito original. O gate lia só o
    espelho, e num clone limpo ele não existe.
    """
    modulo = _modulo()
    fonte = SCRIPT.read_text(encoding="utf-8")
    corpo_do_check = fonte.split("def check_status()")[1].split("\ndef ")[0]
    assert "STATUS.read_text" not in corpo_do_check, (
        "o gate voltou a LER o espelho local para decidir")
    assert "MANIFESTO.read_text" in corpo_do_check

    codigo, corpo = _check()
    assert codigo == 0
    assert corpo["espelho_local"]["usado_como_autoridade"] is False
    # E o veredito não muda com o espelho presente ou ausente.
    assert corpo["current"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2 · FALHA FECHADA — não saber nunca é `current: true`
# ═══════════════════════════════════════════════════════════════════════════


def test_manifesto_ausente_falha_fechado(manifesto_restaurado):
    """CONTRAPROVA 2: sem manifesto, recusa — nunca um `true` por omissão."""
    MANIFESTO.unlink()
    codigo, corpo = _check()
    assert codigo == 1
    assert corpo["current"] is False
    assert "ausente" in corpo["reason"]


def test_manifesto_com_json_invalido_falha_fechado(manifesto_restaurado):
    """CONTRAPROVA 3: manifesto corrompido não vira permissão."""
    MANIFESTO.write_text("{ isto não é json", encoding="utf-8")
    codigo, corpo = _check()
    assert codigo == 1
    assert corpo["current"] is False
    assert "inválido" in corpo["reason"]


def test_manifesto_de_outro_esquema_falha_fechado(manifesto_restaurado):
    """CONTRAPROVA 3b: contrato desconhecido é o mesmo que evidência nenhuma."""
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    dados["schema_version"] = 99
    MANIFESTO.write_text(json.dumps(dados), encoding="utf-8")
    codigo, corpo = _check()
    assert codigo == 1
    assert corpo["current"] is False
    assert "incompat" in corpo["reason"]


def test_manifesto_sem_digest_falha_fechado(manifesto_restaurado):
    """Um manifesto que não carrega digest não tem o que provar."""
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    dados.pop("input_sha256", None)
    MANIFESTO.write_text(json.dumps(dados), encoding="utf-8")
    codigo, corpo = _check()
    assert codigo == 1
    assert corpo["current"] is False


def test_digest_incompativel_responde_stale(manifesto_restaurado):
    """CONTRAPROVA 4: digest que não bate → `current: false` e exit 1."""
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    dados["input_sha256"] = "0" * 64
    MANIFESTO.write_text(json.dumps(dados), encoding="utf-8")
    codigo, corpo = _check()
    assert codigo == 1
    assert corpo["current"] is False
    assert corpo["reason"] == "código, SQL ou fonte operacional mudou"


# ═══════════════════════════════════════════════════════════════════════════
# 3 · O DIGEST MEDE O QUE DEVE MEDIR
# ═══════════════════════════════════════════════════════════════════════════


def test_mudanca_real_em_insumo_rastreado_torna_stale(tmp_path):
    """CONTRAPROVA 5: mexer em código muda o digest."""
    modulo = _modulo()
    antes, _ = modulo.input_digest()

    alvo = RAIZ / "scripts" / "atualizar_grafo_volc_os.py"
    original = alvo.read_bytes()
    try:
        alvo.write_bytes(original + "\n# marca temporaria de teste\n".encode("utf-8"))
        depois, _ = modulo.input_digest()
    finally:
        alvo.write_bytes(original)

    assert antes != depois, "mudança em .py não moveu o digest"
    assert modulo.input_digest()[0] == antes, "a restauração não fechou o ciclo"


def test_mudanca_so_documental_fora_dos_insumos_nao_torna_stale():
    """CONTRAPROVA 6: documentação fora dos insumos não envelhece o grafo.

    ⚠️ É esta propriedade que quebra o ciclo infinito
    `build → commit → o HEAD mudou → rebuild → commit`. Se um commit de
    documentação tornasse o grafo velho, ele nunca convergiria.
    """
    modulo = _modulo()
    antes, _ = modulo.input_digest()

    alvo = RAIZ / "docs" / "closure" / "volc-os-multichannel-completion-v1" / "HANDOFF.md"
    original = alvo.read_bytes()
    try:
        alvo.write_bytes(original + "\n<!-- marca temporaria de teste -->\n".encode("utf-8"))
        depois, _ = modulo.input_digest()
    finally:
        alvo.write_bytes(original)

    assert antes == depois, "documentação fora dos insumos moveu o digest"


def test_o_manifesto_nao_participa_do_proprio_digest():
    """CONTRAPROVA 8: sem autorreferência — o manifesto não se conta.

    Se ele entrasse na própria conta, todo build produziria um manifesto que já
    nasce inválido: gravar o digest muda o arquivo, que muda o digest.
    """
    modulo = _modulo()
    assert MANIFESTO not in modulo.tracked_inputs()

    antes, _ = modulo.input_digest()
    original = MANIFESTO.read_bytes()
    try:
        MANIFESTO.write_bytes(original + b"\n")
        depois, _ = modulo.input_digest()
    finally:
        MANIFESTO.write_bytes(original)
    assert antes == depois, "o manifesto entrou no próprio digest"

    # E o gate continua verde depois do vaivém.
    assert _check()[0] == 0


def test_o_digest_so_conta_arquivo_rastreado():
    """Um rascunho não commitado não pode reprovar um checkout limpo.

    O digest era calculado sobre `git ls-files -co` — rastreados MAIS
    não-rastreados. Um `.py` de rascunho na árvore de alguém entrava na conta e
    fazia o gate acusar "stale" contra um commit que não o contém, que é o
    mesmo defeito de irreprodutibilidade que este arquivo fecha.
    """
    modulo = _modulo()
    antes, quantos_antes = modulo.input_digest()

    rascunho = RAIZ / "_rascunho_temporario_do_teste.py"
    assert not rascunho.exists()
    try:
        rascunho.write_text("# rascunho não commitado\n", encoding="utf-8")
        depois, quantos_depois = modulo.input_digest()
    finally:
        rascunho.unlink(missing_ok=True)

    assert antes == depois, "um arquivo não rastreado entrou no digest"
    assert quantos_antes == quantos_depois


def test_o_manifesto_declara_o_que_o_contrato_exige():
    """O manifesto carrega a evidência inteira, e diz que o commit não decide."""
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    for campo in ("schema_version", "generated_at", "built_at_commit",
                  "input_sha256", "input_file_count", "graphify_version",
                  "sources", "counts", "freshness_rule"):
        assert campo in dados, campo
    assert dados["schema_version"] == _modulo().SCHEMA_DO_MANIFESTO
    assert len(dados["input_sha256"]) == 64
    assert dados["counts"]["operational_nodes"] > 0
    assert "built_at_commit" in dados["built_at_commit_nao_decide"]
