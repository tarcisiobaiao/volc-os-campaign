"""Varredura dos arquivos da thread C (R1-F25): nenhum identificador real de conta, campanha, GTM,
domínio monetizado ou segredo. Os padrões são montados por concatenação para não casarem consigo."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
DOC = RAIZ / "docs/data-intelligence/fundacao-20261016"
ARQUIVOS = [
    *sorted((RAIZ / "experiments/data-intelligence-lab/src/volc_dil/fundacao/identidade").glob("*.py")),
    *sorted((RAIZ / "tests/data-intelligence/fundacao").glob("test_identidade_*.py")),
    *sorted((DOC / "receipts/identidade").glob("*")),
    DOC / "03-MATRIZ-DE-ATRIBUICAO.md",
    DOC / "handoffs/HANDOFF-C.md",
]

PADROES = {
    "customer_id real": re.compile("5478" + "096539"),
    "campanha real": re.compile("2427" + "8665189"),
    "conta GTM": re.compile("6334" + "941389"),
    "container GTM": re.compile("2411" + "70721"),
    "id público GTM": re.compile("GTM-" + "N4KS27ZV"),
    "GA4 real": re.compile("G-" + "Z6WVMGWTVG|5487" + "31888"),
    "domínio monetizado": re.compile("credit" + "oup", re.I),
    "cliente da campanha": re.compile("sen" + "ac", re.I),
    "host supabase hosted": re.compile(re.escape("supabase" + ".co"), re.I),
    "IP do servidor": re.compile(r"178\.156\." + r"196\.149"),
    "JWT": re.compile("ey" + r"J[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "caminho de credencial": re.compile(r"\.ssh/" + r"|\.env\.server|volc-supabase-live"),
}


def test_lista_de_arquivos_nao_vazia():
    assert len(ARQUIVOS) >= 14 and all(p.exists() for p in ARQUIVOS)


def test_nenhum_identificador_real_nos_arquivos_da_thread_c():
    achados = []
    for p in ARQUIVOS:
        if p.resolve() == Path(__file__).resolve():
            continue
        texto = p.read_text(encoding="utf-8")
        for nome, rx in PADROES.items():
            for m in rx.finditer(texto):
                achados.append(f"{p.relative_to(RAIZ)}:{texto.count(chr(10), 0, m.start()) + 1}: {nome}")
    assert achados == []


def test_padroes_casam_amostras():
    amostras = {
        "customer_id real": "5478" + "096539", "campanha real": "2427" + "8665189",
        "conta GTM": "6334" + "941389", "container GTM": "2411" + "70721", "id público GTM": "GTM-" + "N4KS27ZV",
        "GA4 real": "G-" + "Z6WVMGWTVG", "domínio monetizado": "Credit" + "oUp", "cliente da campanha": "SEN" + "AC",
        "host supabase hosted": "x." + "supabase" + ".co", "IP do servidor": "178.156." + "196.149",
        "JWT": "ey" + "J" + "a" * 12 + "." + "b" * 12, "caminho de credencial": "~/.ssh/" + "id",
    }
    assert set(amostras) == set(PADROES)
    for nome, t in amostras.items():
        assert PADROES[nome].search(t), nome
