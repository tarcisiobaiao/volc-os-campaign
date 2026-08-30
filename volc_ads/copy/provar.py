"""Banco de provas da copy. SOMENTE LEITURA — `validate_only`, nada é criado.

## Por que existe

Até aqui, "essa copy é boa" era opinião. Este script troca opinião por três
juízes que não têm opinião nenhuma:

  1. FORMA        — determinístico e independente de idioma. Comprimento
                    (contando DKI pelo fallback, como o Google conta), contagem,
                    duplicata, repetição de palavra entre recursos, caixa alta,
                    símbolo e emoji por categoria Unicode.
  2. GOOGLE       — `validate_only` contra a conta real. É o único juiz
                    autoritativo e ele fala qualquer idioma. Custa zero e não
                    cria nada: a API valida o payload e descarta.
  3. CORPUS       — as taxas medidas em 6.651 headlines APROVADOS da operação.
                    Não é regra: é a distribuição contra a qual a copy nova é
                    comparada. Desvio grande para qualquer lado é sinal.

O juiz 3 não reprova nada. Ele existe porque a falha mais cara do gerador
anterior não era reprovação — era MORNIDÃO, e mornidão não aparece em
`validate_only`. Só aparece comparando com o que a operação de fato publica.

## O que ele NÃO prova

`validate_only` é preflight, não a revisão completa. O veredito definitivo só
vem de recurso persistido e revisado (`ad_group_ad.policy_summary` numa campanha
pausada). Passar aqui não garante aprovação; falhar aqui garante reprovação.

Uso:
    .venv/bin/python -m volc_ads.copy.provar copy.json
    .venv/bin/python -m volc_ads.copy.provar copy.json --json   # saída legível por agente

`copy.json` = {"headlines": [...], "descriptions": [...],
               "sitelinks": [{title, description1, description2}...],
               "callouts": [...], "snippet": {"header":..., "values":[...]}}
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]   # raiz do projeto Volc OS
sys.path.insert(0, str(RAIZ))
logging.disable(logging.CRITICAL)

from volc_ads.campanha import search  # noqa: E402
from volc_ads.campanha.brief import Brief, Copy, Sitelink, Snippet  # noqa: E402
from volc_ads.gads import modo  # noqa: E402
from volc_ads.gads.client import validar_mutacoes  # noqa: E402

from volc_ads.copy.contrato import (  # noqa: E402
    RX_ANO,
    RX_EXEC,
    RX_LEIT,
    RX_NUM,
    RX_PERG,
    comprimento_efetivo,
    sem_acento as _sem_acento,
    taxa as _taxa,
)

CORPUS = Path(__file__).resolve().parents[1] / "dados" / "corpus" / "calibracao_copy.json"

# Conta de prova. Zero campanhas, zero histórico — nada aqui pode ser
# perturbado, e `validate_only` não cria nem se quisesse.
CUSTOMER_ID = "8017851692"        # Crédito Up
LOGIN_CUSTOMER_ID = "6016739364"  # MCC VOLC Negócios Digitais

MAX = {"headline": 30, "description": 90, "sitelink_titulo": 25,
       "sitelink_desc": 35, "callout": 25, "snippet_valor": 25}

def prova_forma(c: dict) -> tuple[list[str], list[str]]:
    """Determinístico e sem uma palavra de idioma nenhum dentro.

    Devolve (falhas, avisos). Falha é o que a API recusa ou o que degrada
    Ad Strength por regra. Aviso é o que só um humano ou o Google resolve.
    """
    falhas: list[str] = []
    avisos: list[str] = []

    def checa(itens, rotulo, limite):
        vistos: dict[str, int] = {}
        for i, t in enumerate(itens):
            t = (t or "").strip()
            if not t:
                falhas.append(f"{rotulo}[{i}] vazio")
                continue
            n = comprimento_efetivo(t)
            if n > limite:
                falhas.append(f"{rotulo}[{i}] {n} chars > {limite}: {t!r}")
            k = _sem_acento(t.lower())
            if k in vistos:
                falhas.append(f"{rotulo}[{i}] duplica [{vistos[k]}]: {t!r}")
            vistos[k] = i
            # Emoji e símbolo por CATEGORIA Unicode — vale em qualquer alfabeto.
            simb = [ch for ch in t if unicodedata.category(ch) in ("So", "Sk", "Cs")]
            if simb:
                falhas.append(f"{rotulo}[{i}] símbolo/emoji {simb!r}: {t!r}")
            if re.search(r"[!?]{2,}|\.{3,}|\s{2,}", t):
                falhas.append(f"{rotulo}[{i}] pontuação/espaço repetido: {t!r}")
            # Caixa alta: AVISO, nunca falha. Distinguir sigla de grito exige
            # dicionário, e dicionário é por idioma — o que quebraria a promessa
            # de valer em qualquer país. `CCFGTS` e `INSS` são siglas legítimas
            # e indistinguíveis de `GRATIS` por regra. Quem adjudica é o Google.
            for p in re.findall(r"\b[^\W\d_]{6,}\b", t, re.UNICODE):
                if p.isupper():
                    avisos.append(f"{rotulo}[{i}] caixa alta {p!r} — sigla ou grito?")

    checa(c.get("headlines", []), "headline", MAX["headline"])
    checa(c.get("descriptions", []), "description", MAX["description"])
    checa(c.get("callouts", []), "callout", MAX["callout"])
    for i, s in enumerate(c.get("sitelinks", [])):
        checa([s.get("title", "")], f"sitelink{i}.title", MAX["sitelink_titulo"])
        checa([s.get("description1", ""), s.get("description2", "")],
              f"sitelink{i}.desc", MAX["sitelink_desc"])
    sn = c.get("snippet") or {}
    checa(sn.get("values", []), "snippet", MAX["snippet_valor"])

    # Repetição entre recursos (política 14848296): palavra longa em muitos
    # títulos vira redundância e derruba Ad Strength.
    palavras = Counter()
    for t in c.get("headlines", []):
        for p in set(re.findall(r"\b[^\W\d_]{4,}\b", _sem_acento((t or "").lower()))):
            palavras[p] += 1
    for p, n in palavras.items():
        if n > 4:
            falhas.append(f"palavra {p!r} aparece em {n} títulos (máx 4)")
    return falhas, avisos


def prova_google(c: dict, brief_base: Brief) -> tuple[bool, str]:
    """`validate_only` contra a conta real. Nada é criado."""
    copia = Copy(
        headlines=list(c.get("headlines", [])),
        descriptions=list(c.get("descriptions", [])),
        sitelinks=[Sitelink(s.get("title", ""), s.get("description1", ""),
                            s.get("description2", ""))
                   for s in c.get("sitelinks", [])],
        callouts=list(c.get("callouts", [])),
        snippet=(Snippet((c.get("snippet") or {}).get("header", ""),
                         list((c.get("snippet") or {}).get("values", [])))
                 if c.get("snippet") else None),
    )
    # `replace` e não `Brief(**__dict__)`: o Brief carrega campos derivados com
    # prefixo `_`, que não são parâmetros do construtor.
    brief = dataclasses.replace(brief_base, copy=copia)
    try:
        ops, res = search.construir(CUSTOMER_ID, brief,
                                    login_customer_id=LOGIN_CUSTOMER_ID)
    except Exception as exc:
        return False, f"construir() falhou: {str(exc)[:400]}"
    if not res.ok:
        return False, f"validação local do forge: {res.resumo()[:500]}"
    falha = validar_mutacoes(CUSTOMER_ID, ops,
                             login_customer_id=LOGIN_CUSTOMER_ID)
    if falha is not None:
        return False, falha.resumo()[:800]
    return True, f"aceito ({len(ops)} operações)"


def prova_corpus(c: dict) -> dict:
    """Compara a distribuição da copy nova com a dos aprovados reais.

    Não reprova. Mornidão não aparece em `validate_only` — só aparece aqui.
    """
    if not CORPUS.exists():
        return {"erro": f"corpus ausente em {CORPUS}"}
    aprovados = json.loads(CORPUS.read_text(encoding="utf-8"))["aprovados_search_limpos"]
    hs = [h for h in c.get("headlines", []) if h]
    medidas = {}
    for nome, rx in (("verbo_execucao", RX_EXEC), ("marcador_leitura", RX_LEIT),
                     ("pergunta", RX_PERG), ("ano", RX_ANO), ("numero", RX_NUM)):
        medidas[nome] = {"copy_nova": round(_taxa(hs, rx), 1),
                         "aprovados_reais": round(_taxa(aprovados, rx), 1)}
    medidas["_n_aprovados"] = len(aprovados)
    return medidas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    c = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    from volc_ads.briefs.fgts_saque_aniversario import BRIEF as BRIEF_BASE

    forma, avisos = prova_forma(c)
    ok_google, msg = prova_google(c, BRIEF_BASE)
    corpus = prova_corpus(c)

    resultado = {
        "forma_ok": not forma,
        "forma_falhas": forma,
        "forma_avisos": avisos,
        "google_ok": ok_google,
        "google": msg,
        "corpus": corpus,
        "trava_escrita": "fechada" if not modo.escrita_permitida() else "ABERTA",
    }

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=1))
        return 0 if (not forma and ok_google) else 1

    print("═" * 72)
    print(f"1 · FORMA        {'✅ ok' if not forma else f'❌ {len(forma)} falha(s)'}")
    for f in forma[:20]:
        print(f"      {f}")
    for a in avisos[:8]:
        print(f"      · aviso: {a}")
    print(f"\n2 · GOOGLE       {'✅' if ok_google else '❌'} {msg}")
    print("\n3 · CORPUS       taxa nesta copy  ·  taxa nos aprovados reais")
    for k, v in corpus.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            d = v["copy_nova"] - v["aprovados_reais"]
            print(f"      {k:20} {v['copy_nova']:5.1f}%  ·  {v['aprovados_reais']:5.1f}%"
                  f"   ({d:+.1f})")
    print(f"\ntrava de escrita: {resultado['trava_escrita']}")
    print("═" * 72)
    return 0 if (not forma and ok_google) else 1


if __name__ == "__main__":
    raise SystemExit(main())
