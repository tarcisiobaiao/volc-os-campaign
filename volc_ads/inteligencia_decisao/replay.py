"""Adapter hermético do dataset e avaliação dourada."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .critica import CriticoDeterministico, PortaCritica
from .pipeline import executar_pipeline


CAMINHO_DATASET = Path(__file__).with_name("dados") / "cenarios_dourados.json"


def _dataset() -> dict[str, Any]:
    return json.loads(CAMINHO_DATASET.read_text(encoding="utf-8"))


def _mesclar(base: Mapping[str, Any], mudanca: Mapping[str, Any]) -> dict[str, Any]:
    saida = deepcopy(dict(base))
    for chave, valor in mudanca.items():
        if isinstance(valor, Mapping) and isinstance(saida.get(chave), Mapping):
            saida[chave] = _mesclar(saida[chave], valor)
        else:
            saida[chave] = deepcopy(valor)
    return saida


def catalogo_de_cenarios() -> list[dict[str, str]]:
    dados = _dataset()
    return [
        {
            "scenario_id": str(c["scenario_id"]),
            "rotulo": str(c["label"]),
            "grupo": str(c.get("group") or "dourado"),
        }
        for c in dados["scenarios"]
    ]


def carregar_cenario(scenario_id: str) -> dict[str, Any]:
    dados = _dataset()
    for cenario in dados["scenarios"]:
        if cenario["scenario_id"] != scenario_id:
            continue
        if cenario.get("kind", "observation") != "observation":
            return deepcopy(cenario)
        observacao = _mesclar(dados["base_observation"], cenario.get("override", {}))
        observacao.update({
            "scenario_id": cenario["scenario_id"],
            "label": cenario["label"],
            "expected": deepcopy(cenario.get("expected", {})),
        })
        return observacao
    raise KeyError(scenario_id)


def _agora() -> datetime:
    valor = _dataset()["as_of"]
    return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone(timezone.utc)


def projetar_cenario(
    scenario_id: str,
    *,
    critico: PortaCritica | None = None,
) -> dict[str, Any]:
    cenario = carregar_cenario(scenario_id)
    kind = cenario.get("kind", "observation")
    if kind == "observation":
        resultado = executar_pipeline(cenario, agora=_agora(), critico=critico)
        resultado["estado_da_superficie"] = resultado["estado_da_leitura"]
        return resultado
    base = {
        "versao_contrato": 1,
        "scenario_id": scenario_id,
        "rotulo": cenario["label"],
        "estado_da_superficie": kind,
        "marcas": ["PROTÓTIPO", "DADOS SINTÉTICOS"],
        "mutacoes_executadas": 0,
    }
    if kind == "falha_ultimo_bom":
        base["ultima_fotografia"] = projetar_cenario(
            str(cenario["last_good_scenario_id"]), critico=critico
        )
        base["falha"] = {"codigo": "LAB-FALHA-SINTETICA", "mensagem": "A tentativa mais recente falhou; a última fotografia boa permanece visível."}
    elif kind == "falha_sem_fotografia":
        base["ultima_fotografia"] = None
        base["falha"] = {"codigo": "LAB-SEM-FOTO-SINTETICA", "mensagem": "A leitura falhou antes da primeira fotografia boa."}
    elif kind == "vazio_confirmado":
        base["confirmacao"] = {"fonte": "dataset sintético", "lido_em": _dataset()["as_of"], "linhas": 0}
    elif kind == "versao_desconhecida":
        base["versao_contrato"] = 999
        base["versao_recebida"] = "lab-future-999"
    return base


def executar_replay(*, critico: PortaCritica | None = None) -> dict[str, Any]:
    dados = _dataset()
    casos: list[dict[str, Any]] = []
    for bruto in dados["scenarios"]:
        if bruto.get("kind", "observation") != "observation":
            continue
        observado = executar_pipeline(carregar_cenario(bruto["scenario_id"]), agora=_agora(), critico=critico)
        esperado = bruto["expected"]
        atual = {
            "estado_da_leitura": observado["estado_da_leitura"],
            "veredito": observado["veredito"]["tipo"],
            "health_gate": observado["health_gate"]["estado"],
            "propostas": len(observado["propostas_tipadas"]),
        }
        ok = atual == esperado
        observado["timeline"][-1]["estado"] = "passou" if ok else "divergiu"
        casos.append({"scenario_id": bruto["scenario_id"], "passou": ok, "esperado": esperado, "observado": atual})
    return {
        "dataset_version": dados["dataset_version"],
        "as_of": dados["as_of"],
        "total": len(casos),
        "passaram": sum(1 for c in casos if c["passou"]),
        "falharam": sum(1 for c in casos if not c["passou"]),
        "casos": casos,
        "critico": type(critico).__name__ if critico else None,
    }


def replay_com_critico_fake() -> dict[str, Any]:
    return executar_replay(critico=CriticoDeterministico())
