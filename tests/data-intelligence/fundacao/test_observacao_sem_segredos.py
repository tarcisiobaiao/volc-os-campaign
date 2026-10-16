"""Varredura dos arquivos da thread A: nenhum host Supabase hosted, nenhum segredo, nenhum caminho de credencial.

Os padrões são montados por concatenação para que este arquivo não case consigo mesmo.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
ARQUIVOS_DA_THREAD = [
    *sorted((RAIZ / "experiments/data-intelligence-lab/src/volc_dil/fundacao/observacao").glob("*.py")),
    RAIZ / "experiments/data-intelligence-lab/src/volc_dil/fundacao/__init__.py",
    *sorted((RAIZ / "experiments/data-intelligence-lab/migrations_candidatas").glob("dil_obs_*.sql")),
    *sorted((RAIZ / "tests/data-intelligence/fundacao").glob("test_observacao_*.py")),
    *sorted((RAIZ / "tests/data-intelligence/fundacao").glob("test_schema_pg_*.py")),
    RAIZ / "tests/data-intelligence/fundacao/conftest.py",
    *[p for p in (RAIZ / "docs/data-intelligence/fundacao-20261016/02-CONTRATO-DE-DADOS.md",
                  RAIZ / "docs/data-intelligence/fundacao-20261016/handoffs/HANDOFF-A.md") if p.exists()],
]

PADROES = {
    "host supabase hosted": re.compile(re.escape("supabase" + ".co"), re.I),
    "JWT": re.compile("ey" + r"J[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "chave privada": re.compile("BEGIN " + r"(RSA |OPENSSH |EC )?PRIVATE KEY"),
    "token de API": re.compile(r"\b(sk|pk|rk)" + r"_(live|test)_[A-Za-z0-9]{8,}"),
    "token GitHub": re.compile(r"\bgh" + r"[pousr]_[A-Za-z0-9]{20,}"),
    "chave AWS": re.compile(r"\bAK" + r"IA[0-9A-Z]{16}\b"),
    "senha em URL": re.compile(r"postgres(ql)?://[^\s:/]+:" + r"[^\s@/]+@"),
    "atribuição de senha": re.compile(r"(?i)\b(password|senha|secret)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"),
    "caminho de credencial": re.compile(r"\.ssh/" + r"|\.env\.server|volc-supabase-live"),
    "IP do servidor": re.compile(r"178\.156\." + r"196\.149"),
}


def test_lista_de_arquivos_nao_vazia():
    assert len(ARQUIVOS_DA_THREAD) >= 12 and all(p.exists() for p in ARQUIVOS_DA_THREAD)


def test_nenhum_segredo_ou_host_proibido():
    achados = []
    for p in ARQUIVOS_DA_THREAD:
        if p == Path(__file__).resolve():
            continue
        texto = p.read_text(encoding="utf-8")
        for nome, rx in PADROES.items():
            for m in rx.finditer(texto):
                linha = texto.count("\n", 0, m.start()) + 1
                achados.append(f"{p.relative_to(RAIZ)}:{linha}: {nome}")
    assert achados == []


def test_padroes_detectam_amostras_positivas():
    """Contraprova: a varredura não é vazia — cada padrão casa uma amostra montada aqui."""
    amostras = {
        "host supabase hosted": "https://abc." + "supabase" + ".co/rest",
        "JWT": "ey" + "J" + "a" * 12 + "." + "b" * 12 + ".c",
        "chave privada": "-----BEGIN " + "PRIVATE KEY-----",
        "token de API": "sk" + "_live_" + "a1b2c3d4e5",
        "token GitHub": "gh" + "p_" + "x" * 24,
        "chave AWS": "AK" + "IA" + "A" * 16,
        "senha em URL": "postgres://u:" + "p4ss@host/db",
        "atribuição de senha": "password = " + "'hunter22'",
        "caminho de credencial": "~/.ssh/" + "id",
        "IP do servidor": "178.156." + "196.149",
    }
    assert set(amostras) == set(PADROES)
    for nome, texto in amostras.items():
        assert PADROES[nome].search(texto), nome
