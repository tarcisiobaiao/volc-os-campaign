"""Reusa o sensor real da Attention Matrix; nenhum cliente DataForSEO novo."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]


@lru_cache
def modulo_do_repo(caminho: str):
    nome = "_ff_" + caminho.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(nome, REPO / caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def perguntas(card: dict, cache_dir: Path, *, cliente=None, agora=None) -> dict:
    from funnelforge.domain.dossie import sha256_canonico
    sensor = modulo_do_repo("backend/app/motor_pautas/sensores/dataforseo.py")
    agora = time.time() if agora is None else agora
    raiz = [card.get("main_keyword", ""), card.get("country", ""),
            card.get("native_language", "")]
    arquivo = cache_dir / (sha256_canonico(raiz) + ".json")
    serp = card.get("serp")
    origem = "card.serp"
    try:
        cache = json.loads(arquivo.read_text())
        if 0 <= agora - cache["coletado_em"] <= 7 * 86400:
            serp, origem = cache["serp"], "cache_serp_recente"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    erro = ""
    if serp is None and cliente is not None and card.get("location_code") and card.get("language_code"):
        try:
            # UMA SERP de depth=10; sem retry; o Cliente é o já existente.
            resposta = cliente.chamar("serp", sensor.tarefa_serp(
                raiz[0], location_code=card["location_code"], language_code=card["language_code"]))
            serp = resposta["tasks"][0]["result"][0]
            origem = "attention_matrix.dataforseo"
            cache_dir.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(json.dumps({"coletado_em": agora, "serp": serp}))
        except Exception as exc:
            erro = type(exc).__name__  # nunca corpo HTTP ou credencial
    paa = sensor.perguntas_do_paa(serp or {})
    paa += [q for q in (card.get("contexto_de_leitura") or {}).get("perguntas_paa", [])
            if isinstance(q, str) and q not in paa]
    cabeca, recibo = sensor.cabeca_editorial_do_paa(paa, card.get("volumes") or {})
    return {"perguntas": paa, "cabeca": cabeca, "recibo": recibo,
            "origem": origem if paa else "paa_ausente", "erro": erro}
